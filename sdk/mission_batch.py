"""Proactive batch execution - tackle multiple criteria, don't stop for single gaps."""

from __future__ import annotations
from typing import Set, List, Dict, Any
from .helix import HelixOrchestrator
from .certification import MissionCertificationError


class MissionBatchExecutor:
    def __init__(self, helix: HelixOrchestrator):
        self.helix = helix

    def execute_batch(self, mission_id: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for step in steps:
            try:
                d = self.helix.record_step(
                    mission_id,
                    step['receipt'],
                    set(step['covered']),
                    step['executor_id'],
                    step['verifier_id'],
                    step['readback_ref'],
                )
                results.append({'status': 'ok', 'decision': d.phase, 'blocked': d.blocked})
            except Exception as e:
                results.append({'status': 'error', 'error': str(e)})
        # Try to certify if complete
        try:
            cert = self.helix.certify(mission_id)
            return {'results': results, 'certified': cert}
        except MissionCertificationError as e:
            return {'results': results, 'certified': None, 'reason': str(e)}
