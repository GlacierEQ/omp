from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

QUALITY_THRESHOLD = 9.0


@dataclass(frozen=True)
class RateLimit:
    requests_per_minute: int
    requests_per_day: int

    def __post_init__(self) -> None:
        if self.requests_per_minute < 0:
            raise ValueError("requests_per_minute must be >= 0")
        if self.requests_per_day < 0:
            raise ValueError("requests_per_day must be >= 0")


@dataclass(frozen=True)
class Cost:
    input_per_1m: float
    output_per_1m: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.input_per_1m < 0:
            raise ValueError("input_per_1m must be >= 0")
        if self.output_per_1m < 0:
            raise ValueError("output_per_1m must be >= 0")
        if not self.currency:
            raise ValueError("currency must be non-empty")


@dataclass(frozen=True)
class ModelEntry:
    id: str
    provider: str
    endpoint: str
    context_window: int
    capabilities: tuple[str, ...]
    best_for: tuple[str, ...] = ()
    rate_limits: RateLimit | None = None
    cost: Cost | None = None
    capability_scores: Mapping[str, float] = field(default_factory=dict)
    status: str = "unverified"
    last_verified: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("model id must be non-empty")
        if not self.provider:
            raise ValueError("provider must be non-empty")
        if not self.endpoint:
            raise ValueError("endpoint must be non-empty")
        if self.context_window <= 0:
            raise ValueError("context_window must be > 0")
        for name, score in self.capability_scores.items():
            if not 0 <= score <= 10:
                raise ValueError(f"{self.id}.{name}: score must be in [0, 10]")
        if self.status not in ("unverified", "available", "unavailable", "rate_limited"):
            raise ValueError(
                f"{self.id}: status must be one of unverified/available/unavailable/rate_limited"
            )

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class TaskRequest:
    task_type: str
    required_capabilities: tuple[str, ...] = ()
    min_context_window: int = 0
    avoid_providers: tuple[str, ...] = ()
    avoid_models: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_type:
            raise ValueError("task_type must be non-empty")
        if self.min_context_window < 0:
            raise ValueError("min_context_window must be >= 0")


@dataclass(frozen=True)
class RouteAttempt:
    model_id: str
    provider: str
    timestamp: str
    success: bool
    error: str | None = None
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id must be non-empty")
        if not self.provider:
            raise ValueError("provider must be non-empty")
        if not self.timestamp:
            raise ValueError("timestamp must be non-empty")


@dataclass(frozen=True)
class RouterDecision:
    selected: ModelEntry | None
    fallback_chain: tuple[ModelEntry, ...]
    attempts: tuple[RouteAttempt, ...] = ()
    rationale: str = ""
    request: TaskRequest | None = None
