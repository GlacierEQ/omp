"""Unified GlaciereqSDK client: router → capability → execute → receipt → quality.

Ties the omp model router (best-agent fallback over free models) together with
the computer-user capability system (policy-aware connectors, injected adapters,
tamper-evident receipts, quality gates at floor 9.0).
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from .capability import CapabilityClient
from .errors import PolicyError, QualityError, SDKError
from .github import GitHubClient
from .quality import QualityGate, QUALITY_THRESHOLD
from .receipts import ReceiptStore
from .runtime import ConnectorRuntimeClient
from .helix import HelixOrchestrator
from .certification import MissionTracker, MissionCertificationError
from .mission_batch import MissionBatchExecutor

# Import the omp router lazily so the SDK can be imported even when the omp
# package path isn't on sys.path; the unified client wires it in.
try:  # pragma: no cover - environment dependent
    import sys as _sys
    from pathlib import Path as _Path
    _projects_root = _Path(__file__).resolve().parents[2]
    if str(_projects_root) not in _sys.path:
        _sys.path.insert(0, str(_projects_root))
    from omp.router import ModelRouter  # type: ignore
    from omp.model import TaskRequest  # type: ignore
except Exception:  # pragma: no cover
    ModelRouter = None  # type: ignore[assignment]
    TaskRequest = None  # type: ignore[assignment]


class GlaciereqSDK:
    """Unified client for GlacierEQ capability + quality integration.

    Example:
        sdk = GlaciereqSDK(router_roster="omp/roster.yaml")
        model = sdk.best_model_for("coding", ["coding", "reasoning"], 32768)
        result = sdk.github.execute("get_repository",
            payload={"owner": "GlacierEQ", "repo": "computer-user"})
    """

    def __init__(
        self,
        *,
        router_roster: Optional[str] = None,
        receipts_root: str = "sdk-receipts",
        quality_threshold: float = 9.0,
        capability_catalog: Optional[str] = None,
    ) -> None:
        self.router_roster = router_roster
        self.quality_threshold = float(quality_threshold)
        self.receipts = ReceiptStore(receipts_root)
        self.capability = CapabilityClient()
        self.quality = QualityGate(quality_threshold=quality_threshold)
        self.runtime = ConnectorRuntimeClient(
            capability=self.capability,
            audit_path=self.receipts.root / "audit.jsonl",
        )
        self.github = GitHubClient(
            capability=self.capability,
            runtime=self.runtime,
            receipts=self.receipts,
            quality=self.quality,
        )
        self._router = None
        self._router_roster_path = router_roster
        self.helix = HelixOrchestrator()
        self.missions: dict = {}
        self.auto_missions = True
        self.batch_executor = MissionBatchExecutor(self.helix)

    # ---------- model router (best-agent fallback) ----------

    def _load_router(self):
        if ModelRouter is None:
            raise SDKError(
                "omp router is not importable; ensure omp/ is on PYTHONPATH"
            )
        if self._router is None:
            roster = self._router_roster_path or "roster.yaml"
            self._router = ModelRouter(roster)
        return self._router

    def best_model_for(
        self,
        task_type: str,
        required_capabilities: Optional[list[str]] = None,
        min_context_window: int = 0,
        avoid_providers: Optional[list[str]] = None,
        avoid_models: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Select the best free model via the fallback router.

        Returns the RouterDecision as a dict: selected model, fallback chain,
        scores, rationale. No provider call is made; availability is a
        hypothesis until a live call succeeds.
        """
        router = self._load_router()
        from model import TaskRequest as _TaskRequest  # type: ignore[no-redef]

        request = _TaskRequest(
            task_type=task_type,
            required_capabilities=tuple(required_capabilities or ()),
            min_context_window=int(min_context_window),
            avoid_providers=tuple(avoid_providers or ()),
            avoid_models=tuple(avoid_models or ()),
        )
        decision = router.select(request)
        return {
            "selected": {
                "id": decision.selected.id,
                "provider": decision.selected.provider,
                "endpoint": decision.selected.endpoint,
                "context_window": decision.selected.context_window,
                "capabilities": list(decision.selected.capabilities),
                "status": decision.selected.status,
            }
            if decision.selected
            else None,
            "fallback_chain": [
                {
                    "id": m.id,
                    "provider": m.provider,
                    "score": router.score(m, request),
                }
                for m in decision.fallback_chain
            ],
            "rationale": decision.rationale,
            "attempts": [
                {
                    "model_id": a.model_id,
                    "provider": a.provider,
                    "timestamp": a.timestamp,
                    "success": a.success,
                    "error": a.error,
                    "latency_ms": a.latency_ms,
                }
                for a in decision.attempts
            ],
        }

    def record_router_attempt(
        self,
        decision: dict[str, Any],
        model_id: str,
        *,
        success: bool,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> dict[str, Any]:
        """Record a router attempt and advance the fallback chain on failure."""
        router = self._load_router()
        # Rebuild a RouterDecision-like object from the stored dict is not
        # supported directly; instead the caller should keep the RouterDecision.
        raise SDKError(
            "use router.advance_on_failure with a RouterDecision object; "
            "see omp.router.ModelRouter"
        )

    # ---------- capability ----------

    def plan(self, connector: str, action: str, *, human_approved: bool = False) -> dict[str, Any]:
        return self.capability.plan(connector, action, human_approved=human_approved)

    def capabilities(self) -> dict[str, dict[str, Any]]:
        return self.capability.capabilities()

    def health(self) -> dict[str, Any]:
        return {
            "sdk_version": "1.0.0",
            "quality_threshold": self.quality_threshold,
            "receipts_root": str(self.receipts.root),
            "capability": self.capability.connectors,
            "runtime": self.runtime.health(),
        }

    # ---------- convenience: GitHub ----------

    def register_github_adapter(self, adapter) -> None:
        self.github.register_adapter(adapter)

    def github_plan(self, action: str, *, human_approved: bool = False) -> dict[str, Any]:
        return self.github.plan(action, human_approved=human_approved)

    async def github_execute(
        self,
        action: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        human_approved: bool = False,
        verify: bool = True,
        mission_id: str | None = None,
        auto_helix: bool = True,
        executor_id: str = "sdk-client",
        verifier_id: str | None = None,
        readback_ref: str | None = None,
    ) -> dict[str, Any]:
        result = await self.github.execute(
            action, payload=payload,
            human_approved=human_approved, verify=verify,
        )
        if auto_helix and getattr(self, 'auto_missions', True):
            mid = mission_id or f"auto-{action}"
            if mid not in self.helix.missions:
                self.helix.start_mission(mid, {action})
            vid = verifier_id or f"verifier-{action}-{int(time.time())}"
            rb = readback_ref or f"readback://{action}/{int(time.time())}"
            try:
                self.record_mission_step(mid, result, {action}, executor_id, vid, rb)
            except Exception:
                pass
        return result

    def github_execute_sync(self, *args, **kwargs) -> dict[str, Any]:
        return self.github.execute_sync(*args, **kwargs)

    # ---------- quality gate ----------

    def gate_quality(
        self,
        *,
        effort_score: float,
        verified: bool,
        criterion_id: str = "quality_effort",
    ) -> dict[str, Any]:
        return self.quality.gate_effort(
            effort_score=effort_score,
            verified=verified,
            criterion_id=criterion_id,
        )

    def validate_evidence_chain(self, chain: Mapping[str, Any]) -> dict[str, Any]:
        return self.quality.validate(chain)

    def quality_floor(self) -> float:
        return QUALITY_THRESHOLD

    def start_mission(self, mission_id: str, criteria: set):
        decision = self.helix.start_mission(mission_id, criteria)
        self.missions[mission_id] = self.helix.missions[mission_id]
        return decision

    def select_next_priority(self, mission_id: str):
        return self.helix.select_next_priority(mission_id)

    def record_mission_step(self, mission_id: str, receipt: dict, covered: set, executor_id: str, verifier_id: str, readback_ref: str):
        return self.helix.record_step(mission_id, receipt, covered, executor_id, verifier_id, readback_ref)

    def certify_mission(self, mission_id: str):
        return self.helix.certify(mission_id)
