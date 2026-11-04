"""Policy-gated execution runtime with injected adapters.

Mirrors the computer-user ConnectorRuntime: adapters are injected at startup,
credentials and provider SDKs never enter this repository, plans are not
executions, and results are auditable.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .capability import CapabilityClient
from .errors import AdapterError, PolicyError, SDKError


class ConnectorRuntimeClient:
    """One execution surface for declared connectors and injected adapters.

    Usage:
        runtime = ConnectorRuntimeClient(capability=cap, audit_path="audit.jsonl")
        runtime.register("github", GitHubAdapter(...))
        decision = runtime.plan("github", "get_repository")
        result = await runtime.execute("github", "get_repository",
                                       payload={"owner": "GlacierEQ", "repo": "computer-user"},
                                       verify=GitHubAdapter.verify)
    """

    def __init__(
        self,
        capability: Optional[CapabilityClient] = None,
        adapters: Optional[Mapping[str, Any]] = None,
        audit_path: Optional[Path] = None,
    ) -> None:
        self.capability = capability or CapabilityClient()
        self.adapters: dict[str, Any] = dict(adapters or {})
        self.audit_path = Path(audit_path) if audit_path else None

    def register(self, connector: str, adapter: Any) -> None:
        """Inject an adapter for a connector. Credentials live in the adapter,
        never in this package."""
        self.adapters[connector] = adapter

    def has_adapter(self, connector: str) -> bool:
        return connector in self.adapters

    def plan(
        self,
        connector: str,
        action: str,
        *,
        human_approved: bool = False,
    ) -> dict[str, Any]:
        """Resolve mission authority. Does not execute."""
        return self.capability.plan(connector, action, human_approved=human_approved)

    async def execute(
        self,
        connector: str,
        action: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        human_approved: bool = False,
        verify: Optional[Callable[[Any], Any]] = None,
        policy_action: Optional[str] = None,
        verifier_id: str | None = None,
        executor_id: str = "sdk",
        readback_ref: str | None = None,
    ) -> dict[str, Any]:
        """Execute a provider-backed action only after a pass policy decision.

        `policy_action` (defaults to `action`) is the capability-twin operation
        used for the policy decision; `action` is the adapter method invoked.
        This decouples provider method names from declared capability ops.
        Independent verification required for completion; self-certification forbidden.
        Returns a result dict with status in {blocked, completed,
        executed_unverified, failed}.
        """
        payload = dict(payload or {})
        policy = policy_action or action
        decision = self.plan(connector, policy, human_approved=human_approved)
        base = {
            "connector": connector,
            "action": action,
            "executed": False,
            "verified": False,
            "policy": decision,
        }

        if not decision["allowed"]:
            result = {**base, "status": "blocked", "reason": decision["reason"]}
            self._audit(result, payload)
            return result

        adapter = self.adapters.get(connector)
        if adapter is None:
            result = {**base, "status": "blocked", "reason": "adapter not registered"}
            self._audit(result, payload)
            return result

        method = getattr(adapter, action, None)
        if method is None:
            method = getattr(adapter, "execute", None)
            if method is None:
                result = {**base, "status": "blocked", "reason": "adapter does not implement action"}
                self._audit(result, payload)
                return result
            call = method(action, **payload)
        else:
            call = method(**payload)

        try:
            value = await call if inspect.isawaitable(call) else call
        except Exception as exc:
            result = {
                **base,
                "status": "failed",
                "reason": f"provider error: {exc.__class__.__name__}: {exc}",
                "executed": True,
            }
            self._audit(result, payload)
            raise AdapterError(result["reason"]) from exc

        if verifier_id and verifier_id == executor_id:
            from .errors import VerificationError
            raise VerificationError("self-certification forbidden")

        verifier = verify or getattr(adapter, "verify", None)
        verified = False
        if verifier and readback_ref and verifier_id and verifier_id != executor_id:
            check = verifier(value)
            verified = bool(await check if inspect.isawaitable(check) else check) and bool(readback_ref)
        else:
            verified = False  # never trust self-report alone

        result = {
            **base,
            "status": "completed" if verified else "executed_unverified",
            "executed": True,
            "verified": verified,
            "result": value,
            "reason": (
                "independent verification passed"
                if verified
                else "no independent verification/readback - cannot complete"
            ),
        }
        self._audit(result, payload)
        return result

    def execute_sync(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return asyncio.run(self.execute(*args, **kwargs))

    def _audit(self, result: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **{k: result.get(k) for k in (
                "connector", "action", "status", "executed", "verified", "reason",
            )},
            "provenance": self._safe_provenance(payload),
        }
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")

    @staticmethod
    def _safe_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {"source_id", "file_id", "path", "query", "account", "folder_id", "case_id"}
        return {key: payload[key] for key in allowed if key in payload}

    def health(self) -> dict[str, Any]:
        """Redacted health report; no secrets."""
        return {
            "adapters_registered": sorted(self.adapters),
            "capability_connectors": sorted(self.capability.connectors),
            "audit_enabled": self.audit_path is not None,
        }
