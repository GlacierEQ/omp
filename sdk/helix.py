"""Helix model orchestrator - binding gatekeeper for verification.

Helix loop: Verify → Analyze → Select Next Priority → Plan
Only Helix may call MissionTracker.certify(). All decisions are binding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .certification import MissionCertificationError, MissionTracker
from .errors import VerificationError


class HelixError(Exception):
    """Raised when Helix blocks progression."""


@dataclass
class HelixDecision:
    phase: str  # verify|analyze|select|plan|certify|block
    action: str
    blocked: bool = False
    reason: str = ""
    required_evidence: List[str] = field(default_factory=list)
    next_criterion: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None


class HelixOrchestrator:
    """Binding gatekeeper - prevents false completion and task splitting."""

    def __init__(self) -> None:
        self.missions: Dict[str, MissionTracker] = {}
        self.executors: Set[str] = set()
        self.verifiers: Set[str] = set()

    def start_mission(self, mission_id: str, criteria: Set[str], max_splits: int = 25) -> HelixDecision:
        tracker = MissionTracker(mission_id=mission_id, required_criteria=set(criteria), max_splits=max_splits)
        self.missions[mission_id] = tracker
        return HelixDecision(
            phase="analyze",
            action="mission_started",
            required_evidence=[f"Need coverage for: {sorted(criteria)}"],
        )

    def verify(
        self,
        mission_id: str,
        executor_id: str,
        verifier_id: str,
        readback_ref: str,
        evidence_refs: List[str],
    ) -> HelixDecision:
        """Verify phase - must be independent with readback."""
        if executor_id == verifier_id:
            raise VerificationError("self-certification forbidden - executor cannot verify itself")
        if not readback_ref:
            raise VerificationError("readback_ref required for verification")
        if not evidence_refs:
            raise VerificationError("evidence_refs required for verification")

        self.executors.add(executor_id)
        self.verifiers.add(verifier_id)
        if executor_id in self.verifiers and verifier_id not in self.executors:
            pass  # different roles OK
        elif executor_id in self.verifiers and verifier_id in self.executors and executor_id == verifier_id:
            raise VerificationError("self-certification forbidden")

        return HelixDecision(
            phase="analyze",
            action="verified",
            required_evidence=evidence_refs,
        )

    def analyze(self, mission_id: str) -> HelixDecision:
        tracker = self.missions.get(mission_id)
        if not tracker:
            return HelixDecision(phase="block", action="unknown_mission", blocked=True, reason="mission not found")
        if tracker.falsified:
            return HelixDecision(phase="block", action="falsified", blocked=True, reason="mission falsified")

        status = tracker.status()
        if status["missing"]:
            return HelixDecision(
                phase="select",
                action="gaps_found",
                required_evidence=[f"Missing: {status['missing']}"],
            )
        if tracker.independent_verifications < 1:
            return HelixDecision(
                phase="block",
                action="no_independent_verification",
                blocked=True,
                reason="need independent verification with readback",
            )
        return HelixDecision(phase="certify", action="ready_to_certify")

    def select_next_priority(self, mission_id: str) -> HelixDecision:
        tracker = self.missions.get(mission_id)
        if not tracker:
            return HelixDecision(phase="block", action="unknown_mission", blocked=True, reason="mission not found")

        if tracker.churn_count > tracker.max_churn_per_mission:
            raise HelixError("excessive churn - fracturing detected, must close existing criteria")

        missing = tracker.required_criteria - tracker.covered_criteria
        if not missing:
            return self.analyze(mission_id)

        # Select single highest priority missing criterion (anti-fracture)
        # Prefer criteria not yet attempted
        next_crit = sorted(list(missing))[0]
        return HelixDecision(
            phase="plan",
            action="prioritize",
            next_criterion=next_crit,
            required_evidence=[f"Need readback proof for {next_crit}"],
        )

    def plan(self, mission_id: str, criterion: str, expected_readback: str, verifier_id: str) -> HelixDecision:
        tracker = self.missions.get(mission_id)
        if not tracker:
            return HelixDecision(phase="block", action="unknown_mission", blocked=True, reason="mission not found")
        if criterion not in tracker.required_criteria:
            return HelixDecision(phase="block", action="invalid_criterion", blocked=True, reason="criterion not in required set")
        if criterion in tracker.covered_criteria:
            return HelixDecision(phase="block", action="already_covered", blocked=True, reason="criterion already covered")

        return HelixDecision(
            phase="plan",
            action="plan_created",
            next_criterion=criterion,
            plan={
                "criterion": criterion,
                "expected_readback": expected_readback,
                "verifier_id": verifier_id,
                "testable": True,
                "falsifiable": True,
            },
        )

    def record_step(
        self,
        mission_id: str,
        receipt: Dict[str, Any],
        covered: Set[str],
        executor_id: str,
        verifier_id: str,
        readback_ref: str,
    ) -> HelixDecision:
        tracker = self.missions.get(mission_id)
        if not tracker:
            return HelixDecision(phase="block", action="unknown_mission", blocked=True, reason="mission not found")

        try:
            tracker.record(
                receipt,
                covered,
                independent=(verifier_id != executor_id and bool(readback_ref)),
                readback_ref=readback_ref,
                executor_id=executor_id,
                verifier_id=verifier_id,
            )
        except MissionCertificationError as e:
            return HelixDecision(phase="block", action="blocked", blocked=True, reason=str(e))

        return self.analyze(mission_id)

    def certify(self, mission_id: str) -> Dict[str, Any]:
        tracker = self.missions.get(mission_id)
        if not tracker:
            raise HelixError("mission not found")
        # Only Helix may certify
        return tracker.certify()
