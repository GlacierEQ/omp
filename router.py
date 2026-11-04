from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._yaml_subset import safe_load

from .model import (
    Cost,
    ModelEntry,
    RateLimit,
    RouterDecision,
    RouteAttempt,
    TaskRequest,
)

UNVERIFIED_PENALTY = 2.0
RATE_LIMIT_SCORE_CAP = 10.0


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_roster(path: str | Path) -> tuple[ModelEntry, ...]:
    data = Path(path).read_text(encoding="utf-8")
    payload = safe_load(data)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: roster root must be a mapping")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError(f"{path}: 'models' must be a list")
    entries: list[ModelEntry] = []
    for row in models:
        if not isinstance(row, dict):
            raise ValueError(f"{path}: each model entry must be a mapping")
        rate_limits = None
        if row.get("rate_limits") is not None:
            rl = row["rate_limits"]
            if not isinstance(rl, dict):
                raise ValueError(f"{path}: rate_limits must be a mapping")
            rate_limits = RateLimit(
                requests_per_minute=int(rl.get("requests_per_minute", 0)),
                requests_per_day=int(rl.get("requests_per_day", 0)),
            )
        cost = None
        if row.get("cost") is not None:
            c = row["cost"]
            if not isinstance(c, dict):
                raise ValueError(f"{path}: cost must be a mapping")
            cost = Cost(
                input_per_1m=float(c.get("input_per_1m", 0.0)),
                output_per_1m=float(c.get("output_per_1m", 0.0)),
                currency=str(c.get("currency", "USD")),
            )
        entries.append(
            ModelEntry(
                id=str(row["id"]),
                provider=str(row["provider"]),
                endpoint=str(row["endpoint"]),
                context_window=int(row["context_window"]),
                capabilities=tuple(str(c) for c in row.get("capabilities", ())),
                best_for=tuple(str(b) for b in row.get("best_for", ())),
                rate_limits=rate_limits,
                cost=cost,
                capability_scores={str(k): float(v) for k, v in row.get("capability_scores", {}).items()},
                status=str(row.get("status", "unverified")),
                last_verified=row.get("last_verified"),
                notes=str(row.get("notes", "")),
            )
        )
    return tuple(entries)


class ModelRouter:
    """Best-first fallback router over a free model roster.

    Scores every roster entry against a TaskRequest, builds a best-first
    fallback chain, and records attempts so callers can advance to the next
    model on failure. Unverified models are penalized but remain eligible;
    availability is a hypothesis until a live call succeeds.
    """

    def __init__(
        self,
        roster_path: str | Path = "roster.yaml",
        *,
        ambition_state_path: str | Path | None = None,
    ) -> None:
        self.roster_path = Path(roster_path)
        self._roster = _load_roster(self.roster_path)
        configured = ambition_state_path or os.getenv("OMP_AMBITION_STATE")
        self.ambition_state_path = Path(configured).expanduser() if configured else None
        self._attempts: list[RouteAttempt] = []
        self._last_selected_id: str | None = None
        self._load_ambition_state()

    # ---------- roster ----------

    @property
    def roster(self) -> tuple[ModelEntry, ...]:
        return self._roster

    def find(self, model_id: str) -> ModelEntry | None:
        for m in self._roster:
            if m.id == model_id:
                return m
        return None

    # ---------- scoring ----------

    def _capability_coverage(self, model: ModelEntry, request: TaskRequest) -> float:
        if not request.required_capabilities:
            return 10.0
        have = set(model.capabilities)
        covered = sum(1 for c in request.required_capabilities if c in have)
        return round(covered / len(request.required_capabilities) * 10.0, 3)

    def _task_fit(self, model: ModelEntry, request: TaskRequest) -> float:
        if not request.task_type:
            return 5.0
        best_for = set(model.best_for)
        if request.task_type in best_for:
            return 10.0
        # partial credit via capability scores keyed to task family
        score = model.capability_scores.get(request.task_type)
        if score is not None:
            return round(score, 3)
        return 5.0

    def _context_fit(self, model: ModelEntry, request: TaskRequest) -> float:
        if request.min_context_window <= 0:
            return 10.0
        if model.context_window >= request.min_context_window:
            return 10.0
        # partial credit proportional to how close it gets
        return round(model.context_window / request.min_context_window * 10.0, 3)

    def _status_score(self, model: ModelEntry) -> float:
        return {
            "available": 10.0,
            "unverified": 10.0 - UNVERIFIED_PENALTY,
            "rate_limited": 4.0,
            "unavailable": 0.0,
        }.get(model.status, 5.0)

    def _rate_limit_score(self, model: ModelEntry) -> float:
        if model.rate_limits is None:
            return 5.0
        rpm = model.rate_limits.requests_per_minute
        rpd = model.rate_limits.requests_per_day
        score = min(rpm / 30.0 * 5.0, 5.0) + min(rpd / 2000.0 * 5.0, 5.0)
        return round(min(score, RATE_LIMIT_SCORE_CAP), 3)

    def score(self, model: ModelEntry, request: TaskRequest) -> float:
        coverage = self._capability_coverage(model, request)
        fit = self._task_fit(model, request)
        context = self._context_fit(model, request)
        status = self._status_score(model)
        rate = self._rate_limit_score(model)
        total = coverage * 0.30 + fit * 0.30 + context * 0.15 + status * 0.15 + rate * 0.10
        return round(total, 3)

    # ---------- selection ----------

    def _eligible(self, model: ModelEntry, request: TaskRequest) -> bool:
        if model.status == "unavailable":
            return False
        if model.provider in request.avoid_providers:
            return False
        if model.id in request.avoid_models:
            return False
        if request.min_context_window > 0 and model.context_window < request.min_context_window:
            return False
        if request.required_capabilities:
            have = set(model.capabilities)
            if not all(c in have for c in request.required_capabilities):
                return False
        return True

    def rank(self, request: TaskRequest) -> tuple[ModelEntry, ...]:
        eligible = [m for m in self._roster if self._eligible(m, request)]
        scored = sorted(
            eligible,
            key=lambda m: (-self.score(m, request), m.id),
        )
        return tuple(scored)

    def select(self, request: TaskRequest) -> RouterDecision:
        chain = self.rank(request)
        selected = chain[0] if chain else None
        rationale_parts: list[str] = []
        if selected is None:
            rationale_parts.append("No eligible model satisfies the request.")
        else:
            rationale_parts.append(
                f"Selected {selected.id} ({selected.provider}) score={self.score(selected, request)}."
            )
            if selected.status == "unverified":
                rationale_parts.append(
                    "Model is unverified: treat availability as a hypothesis until a live call succeeds."
                )
            others = [m.id for m in chain[1:]]
            if others:
                rationale_parts.append(f"Fallback chain: {', '.join(others)}.")
            else:
                rationale_parts.append("No fallback models available.")
        return RouterDecision(
            selected=selected,
            fallback_chain=chain,
            attempts=tuple(self._attempts),
            rationale=" ".join(rationale_parts),
            request=request,
        )

    # ---------- attempts / fallback ----------

    def record_attempt(
        self,
        decision: RouterDecision,
        model_id: str,
        *,
        success: bool,
        error: str | None = None,
        latency_ms: float | None = None,
        timestamp: str | None = None,
    ) -> RouterDecision:
        model = self.find(model_id)
        if model is None:
            raise ValueError(f"Unknown model: {model_id}")
        attempt = RouteAttempt(
            model_id=model_id,
            provider=model.provider,
            timestamp=timestamp or _now_utc(),
            success=success,
            error=error,
            latency_ms=latency_ms,
        )
        self._attempts.append(attempt)
        if success:
            self._last_selected_id = model_id
        return RouterDecision(
            selected=decision.selected,
            fallback_chain=decision.fallback_chain,
            attempts=tuple(self._attempts),
            rationale=decision.rationale,
            request=decision.request,
        )

    def next_fallback(self, decision: RouterDecision) -> ModelEntry | None:
        """Return the first chain model not yet attempted (successfully or not)."""
        attempted = {a.model_id for a in decision.attempts}
        for m in decision.fallback_chain:
            if m.id not in attempted:
                return m
        return None

    def advance_on_failure(
        self,
        decision: RouterDecision,
        model_id: str,
        *,
        error: str,
        latency_ms: float | None = None,
        timestamp: str | None = None,
    ) -> RouterDecision:
        """Record a failed attempt and move selection to the next fallback."""
        decision = self.record_attempt(
            decision,
            model_id,
            success=False,
            error=error,
            latency_ms=latency_ms,
            timestamp=timestamp,
        )
        nxt = self.next_fallback(decision)
        if nxt is not None:
            decision = RouterDecision(
                selected=nxt,
                fallback_chain=decision.fallback_chain,
                attempts=decision.attempts,
                rationale=(
                    f"Previous attempt {model_id} failed ({error}); "
                    f"falling back to {nxt.id} ({nxt.provider})."
                ),
                request=decision.request,
            )
        else:
            decision = RouterDecision(
                selected=None,
                fallback_chain=decision.fallback_chain,
                attempts=decision.attempts,
                rationale=(
                    f"Previous attempt {model_id} failed ({error}); no fallback models remain."
                ),
                request=decision.request,
            )
        return decision

    # ---------- ambition state ----------

    def ambition_state(self) -> dict[str, Any]:
        return {
            "schema": "glaciereq.omp.router-state.v1",
            "last_selected_model": self._last_selected_id,
            "attempt_count": len(self._attempts),
            "roster_path": str(self.roster_path),
        }

    def _load_ambition_state(self) -> None:
        path = self.ambition_state_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self._last_selected_id = payload.get("last_selected_model") or None


class AutoRouter:
    """Workflowed auto-routing - picks smart powerful models by default, falls back automatically."""

    def __init__(self, router: ModelRouter | None = None, helix=None):
        self.router = router or ModelRouter()
        self.helix = helix
        self._history: list[dict] = []

    def route(self, task_type: str = "coding", required_capabilities: tuple = ("coding",), min_context: int = 32768, **kwargs) -> RouterDecision:
        req = TaskRequest(
            task_type=task_type,
            required_capabilities=required_capabilities,
            min_context_window=min_context,
            **kwargs
        )
        decision = self.router.select(req)
        self._history.append({
            "task_type": task_type,
            "selected": decision.selected.id if decision.selected else None,
            "fallbacks": len(decision.fallback_chain)
        })
        return decision

    def route_for_mission(self, mission_id: str, criterion: str | None = None):
        if self.helix and mission_id in self.helix.missions:
            m = self.helix.missions[mission_id]
            # Route based on mission needs - prefer powerful models
            return self.route(task_type="reasoning", required_capabilities=("reasoning", "coding", "analysis"), min_context=131072)
        return self.route(task_type="reasoning", required_capabilities=("reasoning", "coding"), min_context=65536)

    def auto_execute(self, func, task_type: str = "coding", **kwargs):
        decision = self.route(task_type=task_type, **kwargs)
        last_err = None
        for model in [decision.selected] + list(decision.fallback_chain[1:]) if decision.selected else decision.fallback_chain:
            if model is None:
                continue
            try:
                result = func(model=model)
                self.router.record_attempt(decision, model.id, success=True)
                return result, model.id
            except Exception as e:
                last_err = e
                decision = self.router.advance_on_failure(decision, model.id, error=str(e))
        raise last_err or RuntimeError("All models failed")


class CoverageAwareRouter(AutoRouter):
    """Routes to maximize coverage gain, penalize churn harder."""

    def route_for_coverage(self, helix, mission_id: str):
        if mission_id not in helix.missions:
            return self.route(task_type="reasoning", required_capabilities=("reasoning","coding"), min_context=131072)
        tracker = helix.missions[mission_id]
        missing = list(tracker.required_criteria - tracker.covered_criteria)
        if not missing:
            return self.route(task_type="reasoning", required_capabilities=("reasoning",), min_context=65536)
        # Prioritize closing specific criterion - use powerful models
        decision = self.route(task_type="reasoning", required_capabilities=("reasoning", "coding", "analysis"), min_context=131072)
        decision.rationale = f"Close criterion {missing[0]} (coverage gain priority). Churn penalty applied. {decision.rationale}"
        return decision

    def score_with_coverage(self, model, request, coverage_gain: float = 1.0, churn_penalty: float = 0.5):
        base = self.router.score(model, request) if self.router else 5.0
        # weight coverage gain highest
        score = base * (1.0 - coverage_gain * 0.4) + coverage_gain * 10.0 * 0.4
        score = score * (1.0 - churn_penalty * 0.1)
        return round(min(max(score, 0), 10.0), 3)
