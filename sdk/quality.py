"""Quality gates: evidence chain, independent verification, quality floor.

Implements the computer-user evidentiary standard:
  - Evidence chain CLAIM → SOURCE → REVISION → EXECUTION → VERIFICATION → RECEIPT
  - Independent verification (self-certification is forbidden)
  - Quality floor: completion-grade operations evidence score >= 9.0
  - Epistemic ladder L0 (presence) / L1 (structure) / L2 (behavior verified)
  - Gate is a pitstop, not a wall: every failure carries severity + remediation_route
"""

from __future__ import annotations

import hmac
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

QUALITY_THRESHOLD = 9.0

REQUIRED_STAGES = ("claim", "source", "revision", "execution", "verification", "receipt")

EPISTEMIC_LABELS = ("L0", "L1", "L2")


class QualityError(Exception):
    """Raised when a quality gate fails."""


class SelfCertificationError(QualityError):
    """Raised when the executor is also presented as its own verifier."""


class EvidenceChainError(QualityError):
    """Raised when an evidence chain is incomplete or inconsistent."""


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise QualityError(f"{name} is required")
    return text


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QualityError(f"{name} must be an object")
    return dict(value)


def _is_lower_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in "0123456789abcdef" for ch in value)


def seal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of payload sealed with canonical SHA-256."""
    body = dict(payload)
    body.pop("receipt_sha256", None)
    body["receipt_sha256"] = sha256_json(body)
    return body


def sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def verify_receipt_integrity(receipt: Mapping[str, Any]) -> bool:
    """Fail closed unless the receipt's canonical hash matches its contents."""
    body = dict(receipt)
    supplied = str(body.pop("receipt_sha256", "")).strip()
    if not _is_lower_hex(supplied, 64):
        raise QualityError("receipt_sha256 must be a lowercase SHA-256 digest")
    expected = sha256_json(body)
    if not hmac.compare_digest(supplied, expected):
        raise QualityError("receipt SHA-256 does not match canonical receipt content")
    return True


def classify_epistemic(observation: Mapping[str, Any]) -> str:
    """Classify an observation on the epistemic ladder.

    L0: presence only (e.g. file_exists) — observation only, do not act.
    L1: structure (e.g. structure_ok) — do not assume behavior.
    L2: behavior verified (e.g. tests_passed / readback) — the only level
        you may state as fact.
    """
    obs = _mapping(observation, "observation")
    if obs.get("tests_passed") is True or obs.get("readback_verified") is True or obs.get("compiled") is True:
        return "L2"
    if obs.get("structure_ok") is True or obs.get("parsed") is True:
        return "L1"
    if obs.get("file_exists") is True or obs.get("present") is True:
        return "L0"
    return "L0"


def validate_claim_chain(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Validate CLAIM → SOURCE → REVISION → EXECUTION → VERIFICATION → RECEIPT.

    Returns a normalized summary. Raises EvidenceChainError / SelfCertificationError
    on any gap. Does not manufacture evidence.
    """
    chain = _mapping(evidence, "evidence")
    for stage in REQUIRED_STAGES:
        if stage not in chain:
            raise EvidenceChainError(f"missing evidence stage: {stage}")
        _mapping(chain[stage], stage)

    claim = _mapping(chain["claim"], "claim")
    source = _mapping(chain["source"], "source")
    revision = _mapping(chain["revision"], "revision")
    execution = _mapping(chain["execution"], "execution")
    verification = _mapping(chain["verification"], "verification")
    receipt = _mapping(chain["receipt"], "receipt")

    claim_id = _text(claim.get("claim_id"), "claim.claim_id")
    _text(claim.get("statement"), "claim.statement")

    source_ref = _text(source.get("ref"), "source.ref")
    source_sha = _text(source.get("sha256"), "source.sha256")
    if not _is_lower_hex(source_sha, 64):
        raise EvidenceChainError("source.sha256 must be a lowercase SHA-256 digest")

    _text(revision.get("repository"), "revision.repository")
    revision_sha = _text(revision.get("sha"), "revision.sha")
    if not (_is_lower_hex(revision_sha, 40) or _is_lower_hex(revision_sha, 64)):
        raise EvidenceChainError("revision.sha must be a 40- or 64-character lowercase hex digest")

    executor_id = _text(execution.get("executor_id"), "execution.executor_id")
    _text(execution.get("run_id"), "execution.run_id")
    exec_receipt_sha = _text(execution.get("receipt_sha256"), "execution.receipt_sha256")
    if not _is_lower_hex(exec_receipt_sha, 64):
        raise EvidenceChainError("execution.receipt_sha256 must be a lowercase SHA-256 digest")

    verifier_id = _text(verification.get("verifier_id"), "verification.verifier_id")
    if executor_id == verifier_id:
        raise SelfCertificationError(
            "executor and verifier identities must be distinct; self-certification is forbidden"
        )
    status = _text(verification.get("status"), "verification.status")
    if status != "VERIFIED":
        raise EvidenceChainError(f"verification.status must be VERIFIED, got {status!r}")
    _text(verification.get("readback_ref"), "verification.readback_ref")

    verify_receipt_integrity(receipt)
    receipt_claim_id = _text(receipt.get("claim_id"), "receipt.claim_id")
    if receipt_claim_id != claim_id:
        raise EvidenceChainError(
            f"receipt.claim_id {receipt_claim_id!r} does not match claim.claim_id {claim_id!r}"
        )

    return {
        "claim_id": claim_id,
        "source_ref": source_ref,
        "revision": {"repository": revision["repository"], "sha": revision_sha},
        "executor_id": executor_id,
        "verifier_id": verifier_id,
        "verification_status": status,
        "receipt_sha256": receipt["receipt_sha256"],
        "receipt_integrity": True,
    }


class QualityGate:
    """Gate an operation against quality criteria.

    Result shape:
        {"decision": "pass"|"fail", "pitstop": bool, "checked": int,
         "failed_ids": [..], "classified_failures": [{id, severity, remediation_route, ..}]}

    Every failure carries severity + remediation_route so the gate is a
    pitstop (forward route always present), not a wall.
    """

    SEVERITY_OPERATOR_ONLY = "operator_only"
    SEVERITY_REMEDIABLE = "remediable"
    SEVERITY_APPROVAL_BYPASS = "approval_bypass"

    def __init__(
        self,
        *,
        quality_threshold: float = QUALITY_THRESHOLD,
        require_independent_verification: bool = True,
    ) -> None:
        self.quality_threshold = float(quality_threshold)
        self.require_independent_verification = require_independent_verification

    def gate_effort(
        self,
        *,
        effort_score: float,
        verified: bool,
        criterion_id: str = "quality_effort",
        criterion_type: str = "quality",
    ) -> dict[str, Any]:
        """Gate a single quality-effort criterion."""
        checks = [
            {
                "id": criterion_id,
                "type": criterion_type,
                "passed": effort_score >= self.quality_threshold,
                "score": effort_score,
                "verified": bool(verified),
            }
        ]
        return self.quality_gate(checks)

    def quality_gate(self, criteria: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Evaluate a list of criteria; every failure is a pitstop."""
        checked = 0
        failed_ids: list[str] = []
        classified: list[dict[str, Any]] = []

        for raw in criteria:
            item = _mapping(raw, "criterion")
            cid = _text(item.get("id"), "criterion.id")
            ctype = str(item.get("type", "generic"))
            passed = bool(item.get("passed"))
            checked += 1

            if passed:
                continue

            failed_ids.append(cid)
            score = item.get("score")
            severity = self._classify_severity(item)
            route = self._remediation_route(ctype, severity)
            entry: dict[str, Any] = {
                "id": cid,
                "type": ctype,
                "severity": severity,
                "remediation_route": route,
            }
            if score is not None:
                entry["score"] = score
            if "verified" in item:
                entry["verified"] = bool(item["verified"])
            classified.append(entry)

        decision = "pass" if not failed_ids else "fail"
        return {
            "decision": decision,
            "pitstop": True,
            "checked": checked,
            "failed_ids": failed_ids,
            "classified_failures": classified,
        }

    @staticmethod
    def _classify_severity(item: Mapping[str, Any]) -> str:
        itype = str(item.get("type", "generic")).lower()
        if itype == "authorization":
            return QualityGate.SEVERITY_OPERATOR_ONLY
        if itype == "review":
            return QualityGate.SEVERITY_APPROVAL_BYPASS
        return QualityGate.SEVERITY_REMEDIABLE

    @staticmethod
    def _remediation_route(ctype: str, severity: str) -> str:
        if severity == QualityGate.SEVERITY_OPERATOR_ONLY:
            return ("§8 operator-only failure: scoped operator authority required; "
                    "escalate to the operator, do not auto-bypass.")
        if severity == QualityGate.SEVERITY_APPROVAL_BYPASS:
            return ("§8 approval-bypass failure: override only with an auditable "
                    "approval token; record the token and rationale.")
        return ("§8 remediable failure: address the criterion, re-run verification, "
                "then re-submit through the gate.")


class EvidenceChain:
    """Facade for building and validating evidence chains end-to-end."""

    def __init__(self, verifier_id: str) -> None:
        self.verifier_id = _text(verifier_id, "verifier_id")

    def build_claim(self, claim_id: str, statement: str) -> dict[str, Any]:
        return {"claim_id": claim_id, "statement": statement}

    def build_source(self, ref: str, sha256: str) -> dict[str, Any]:
        if not _is_lower_hex(sha256, 64):
            raise QualityError("source.sha256 must be a lowercase SHA-256 digest")
        return {"ref": ref, "sha256": sha256}

    def build_revision(self, repository: str, sha: str) -> dict[str, Any]:
        if not (_is_lower_hex(sha, 40) or _is_lower_hex(sha, 64)):
            raise QualityError("revision.sha must be a 40- or 64-character lowercase hex digest")
        return {"repository": repository, "sha": sha}

    def build_execution(
        self,
        executor_id: str,
        run_id: str,
        receipt_sha256: str,
    ) -> dict[str, Any]:
        if not _is_lower_hex(receipt_sha256, 64):
            raise QualityError("execution.receipt_sha256 must be a lowercase SHA-256 digest")
        if executor_id == self.verifier_id:
            raise SelfCertificationError("executor must not equal verifier")
        return {
            "executor_id": executor_id,
            "run_id": run_id,
            "receipt_sha256": receipt_sha256,
        }

    def build_verification(
        self,
        status: str,
        readback_ref: str,
    ) -> dict[str, Any]:
        return {
            "verifier_id": self.verifier_id,
            "status": status,
            "readback_ref": readback_ref,
        }

    def build_chain(
        self,
        *,
        claim: Mapping[str, Any],
        source: Mapping[str, Any],
        revision: Mapping[str, Any],
        execution: Mapping[str, Any],
        verification: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        return seal_receipt({
            "schema": "glaciereq.sdk.evidence-chain.v1",
            "claim": dict(claim),
            "source": dict(source),
            "revision": dict(revision),
            "execution": dict(execution),
            "verification": dict(verification),
            "receipt": dict(receipt),
        })

    def validate(self, chain: Mapping[str, Any]) -> dict[str, Any]:
        return validate_claim_chain(chain)
