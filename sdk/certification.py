"""Mission-level certification - enforces all-or-nothing completion.

Only MissionTracker.certify() can produce CERTIFIED/DONE status.
Requires 100% coverage of acceptance criteria, independent verification,
and anti-fracture/churn limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Set


class MissionCertificationError(Exception):
    """Raised when mission cannot be certified."""


@dataclass
class MissionTracker:
    mission_id: str
    required_criteria: Set[str]
    covered_criteria: Set[str] = field(default_factory=set)
    receipts: list[Dict[str, Any]] = field(default_factory=list)
    independent_verifications: int = 0
    falsified: bool = False
    max_splits: int = 25  # anti-fracture limit
    executor_ids: Set[str] = field(default_factory=set)
    verifier_ids: Set[str] = field(default_factory=set)
    readback_refs: Set[str] = field(default_factory=set)
    churn_count: int = 0
    max_churn_per_mission: int = 10

    def record(
        self,
        receipt: Dict[str, Any],
        covered: Set[str],
        independent: bool = False,
        readback_ref: str | None = None,
        executor_id: str | None = None,
        verifier_id: str | None = None,
    ) -> None:
        if self.falsified:
            raise MissionCertificationError("mission falsified")
        if len(self.receipts) >= self.max_splits:
            raise MissionCertificationError("excessive task splitting detected")
        self.churn_count += 1
        if self.churn_count > self.max_churn_per_mission:
            raise MissionCertificationError("excessive churn detected - prefer single coherent attempt")

        # Validate independent verification
        if executor_id:
            self.executor_ids.add(executor_id)
        if verifier_id:
            self.verifier_ids.add(verifier_id)
            if executor_id and verifier_id == executor_id:
                raise MissionCertificationError("self-certification forbidden")
        if readback_ref:
            self.readback_refs.add(readback_ref)
        if independent and readback_ref and verifier_id and (not executor_id or verifier_id != executor_id):
            self.independent_verifications += 1

        self.receipts.append(receipt)
        self.covered_criteria |= covered

    def falsify(self, reason: str) -> None:
        self.falsified = True
        raise MissionCertificationError(f"falsification detected: {reason}")

    def certify(self) -> Dict[str, Any]:
        if self.falsified:
            raise MissionCertificationError("falsification detected")
        missing = self.required_criteria - self.covered_criteria
        if missing:
            raise MissionCertificationError(f"missing acceptance criteria: {sorted(missing)}")
        if self.covered_criteria != self.required_criteria:
            raise MissionCertificationError("incomplete coverage - not all criteria satisfied")
        if self.independent_verifications < 1:
            raise MissionCertificationError("no independent verification with readback")
        if not self.readback_refs:
            raise MissionCertificationError("no readback references provided")
        if len(self.receipts) == 0:
            raise MissionCertificationError("no receipts recorded")

        return {
            "status": "CERTIFIED",
            "mission_id": self.mission_id,
            "coverage": 1.0,
            "receipts": len(self.receipts),
            "independent_verifications": self.independent_verifications,
            "readback_refs": len(self.readback_refs),
            "covered_criteria": sorted(self.covered_criteria),
        }

    def status(self) -> Dict[str, Any]:
        missing = self.required_criteria - self.covered_criteria
        return {
            "mission_id": self.mission_id,
            "covered": len(self.covered_criteria),
            "required": len(self.required_criteria),
            "missing": sorted(missing),
            "coverage_pct": len(self.covered_criteria) / len(self.required_criteria) * 100 if self.required_criteria else 100,
            "receipts": len(self.receipts),
            "independent_verifications": self.independent_verifications,
            "churn_count": self.churn_count,
            "falsified": self.falsified,
        }
