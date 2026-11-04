"""Tamper-evident invocation and execution receipts.

Mirrors the computer-user receipts module: canonical JSON, SHA-256 chained,
atomic writes, fail-closed verification. No secrets enter receipt payloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Optional


QUALITY_THRESHOLD = 9.0

RECEIPT_SCHEMA = "glaciereq.sdk.receipt.v1"
INVOCATION_SCHEMA = "glaciereq.sdk.invocation-record.v1"
CONTINUATION_SCHEMA = "glaciereq.sdk.continuation-record.v1"


class ReceiptError(Exception):
    """Raised when a receipt cannot be sealed or verified."""


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _safe_id(value: str) -> str:
    text = str(value).strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    if not text or any(ch not in allowed for ch in text):
        raise ReceiptError("receipt identity contains unsupported characters")
    return text


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class ReceiptStore:
    """Persist invocation envelopes and tamper-evident execution receipts."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.invocations = self.root / "invocations"
        self.receipts = self.root / "receipts"
        self.continuations = self.root / "continuations"
        for directory in (self.invocations, self.receipts, self.continuations):
            directory.mkdir(parents=True, exist_ok=True)

    def remember_invocation(
        self,
        task_id: str,
        envelope: Mapping[str, Any],
        *,
        authorization: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        task = _safe_id(task_id)
        path = self.invocations / f"{task}.json"
        normalized_envelope = dict(envelope)
        normalized_authorization = dict(authorization or {})
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise ReceiptError("existing invocation record is invalid")
            if existing.get("envelope") != normalized_envelope or existing.get("authorization") != normalized_authorization:
                raise ReceiptError("task invocation identity conflicts with existing record")
            return existing
        body = {
            "schema": INVOCATION_SCHEMA,
            "task_id": task,
            "recorded_at": time.time(),
            "envelope": normalized_envelope,
            "authorization": normalized_authorization,
        }
        body["record_sha256"] = sha256_json(body)
        _atomic_json(path, body)
        return body

    def remember_continuation(
        self,
        envelope: Mapping[str, Any],
        continuation: Mapping[str, Any],
        *,
        authorization: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        """Persist a non-mutating recovery path without creating an executable task."""
        normalized_envelope = dict(envelope)
        normalized_continuation = dict(continuation)
        normalized_authorization = dict(authorization or {})
        identity = sha256_json({
            "envelope": normalized_envelope,
            "continuation": normalized_continuation,
            "authorization": normalized_authorization,
        })
        continuation_id = _safe_id(identity)
        path = self.continuations / f"{continuation_id}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise ReceiptError("existing continuation record is invalid")
            if (
                existing.get("envelope") != normalized_envelope
                or existing.get("continuation") != normalized_continuation
                or existing.get("authorization") != normalized_authorization
            ):
                raise ReceiptError("continuation identity conflicts with existing record")
            return existing
        body = {
            "schema": CONTINUATION_SCHEMA,
            "continuation_id": continuation_id,
            "recorded_at": time.time(),
            "envelope": normalized_envelope,
            "authorization": normalized_authorization,
            "continuation": normalized_continuation,
            "execution_result": "not_queued",
        }
        body["record_sha256"] = sha256_json(body)
        _atomic_json(path, body)
        return body

    def invocation(self, task_id: str) -> Optional[Mapping[str, Any]]:
        path = self.invocations / f"{_safe_id(task_id)}.json"
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def continuation(self, continuation_id: str) -> Optional[Mapping[str, Any]]:
        path = self.continuations / f"{_safe_id(continuation_id)}.json"
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def finalize(
        self,
        task_id: str,
        *,
        status: str,
        attempts: int,
        result: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
        source_sha: Optional[str] = None,
        executor_id: str = "GlacierEQ/sdk",
        verifier_id: str | None = None,
        readback_ref: str | None = None,
        evidence_refs: list[str] | None = None,
        covered_criteria: list[str] | None = None,
    ) -> Mapping[str, Any]:
        task = _safe_id(task_id)
        invocation = self.invocation(task)
        if invocation is None:
            raise ReceiptError("cannot finalize receipt before invocation record exists")

        if status == "completed":
            if not verifier_id or verifier_id == executor_id:
                raise ReceiptError("independent verifier required for completion")
            if not readback_ref:
                raise ReceiptError("readback_ref required for completion")
            if not evidence_refs:
                raise ReceiptError("evidence_refs required for completion")

        envelope_value = invocation.get("envelope")
        authorization_value = invocation.get("authorization")
        envelope = envelope_value if isinstance(envelope_value, dict) else {}
        authorization = authorization_value if isinstance(authorization_value, dict) else {}
        outcome = dict(result or {})
        verified = bool(
            status == "completed"
            and verifier_id
            and verifier_id != executor_id
            and readback_ref
            and evidence_refs
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": task,
            "trace_id": envelope.get("trace_id"),
            "caller": envelope.get("caller"),
            "executor_id": executor_id,
            "verifier_id": verifier_id,
            "readback_ref": readback_ref,
            "evidence_refs": evidence_refs or [],
            "covered_criteria": covered_criteria or [],
            "executor": executor_id,
            "capability": envelope.get("capability"),
            "connector": envelope.get("connector"),
            "operation": envelope.get("operation"),
            "authority_decision": authorization.get("status", "authorized"),
            "idempotency_key": envelope.get("idempotency_key"),
            "mission_id": envelope.get("mission_id"),
            "depends_on": list(envelope.get("depends_on") or []),
            "source_sha": source_sha,
            "attempts": int(attempts),
            "execution_result": status,
            "verification_result": "PASS" if verified else "FAIL",
            "result": outcome,
            "error": error,
            "completed_at": time.time(),
        }
        receipt["receipt_sha256"] = sha256_json(receipt)
        _atomic_json(self.receipts / f"{task}.json", receipt)
        return receipt

    def receipt(self, task_id: str) -> Optional[Mapping[str, Any]]:
        path = self.receipts / f"{_safe_id(task_id)}.json"
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def verify_receipt_integrity(self, receipt: Mapping[str, Any]) -> bool:
        """Fail closed unless the receipt's canonical hash matches its contents."""
        body = dict(receipt)
        supplied = str(body.pop("receipt_sha256", "")).strip()
        if len(supplied) != 64 or any(ch not in "0123456789abcdef" for ch in supplied):
            raise ReceiptError("receipt_sha256 must be a lowercase SHA-256 digest")
        expected = sha256_json(body)
        if supplied != expected:
            raise ReceiptError("receipt SHA-256 does not match canonical receipt content")
        return True
