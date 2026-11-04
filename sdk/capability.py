"""Policy-aware connector surface (CapabilityTwin wrapper).

Wraps the computer-user CapabilityTwin so the SDK can resolve mission authority
for connector operations without storing credentials or performing provider
mutations itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "First" / "computer-user" / "config" / "capability_twin.json"

DEFAULT_CATALOG = {
    "schema_version": "1.1.0",
    "identity": "computer-user-capability-twin",
    "purpose": "Route real work through declared connectors while increasing verification, recoverability, provenance, and execution quality without manufacturing blanket permission gates.",
    "connectors": [
        {"id": "filesystem", "provider": "local-filesystem", "adapter": "native", "native": True, "operations": ["read", "search", "inspect", "verify", "index"], "default_mode": "read"},
        {"id": "browser", "provider": "chromium", "adapter": "native", "native": True, "operations": ["inspect", "read", "verify", "write"], "default_mode": "read"},
        {"id": "github", "provider": "GitHub", "adapter": "connections.py", "service": "github", "operations": ["read", "search", "inspect", "verify", "write", "create", "update"], "default_mode": "read"},
        {"id": "gmail", "provider": "Gmail", "adapter": "connections.py", "service": "gmail", "operations": ["read", "search", "inspect", "verify", "create", "send", "update"], "default_mode": "read"},
        {"id": "google_drive", "provider": "Google Drive", "adapter": "connections.py", "service": "google_drive", "operations": ["read", "search", "inspect", "verify", "create", "update", "upload"], "default_mode": "read"},
        {"id": "dropbox", "provider": "Dropbox", "adapter": "connections.py", "service": "dropbox", "operations": ["read", "search", "inspect", "verify", "upload"], "default_mode": "read"},
        {"id": "onedrive", "provider": "OneDrive", "adapter": "connections.py", "service": "onedrive", "operations": ["read", "search", "inspect", "verify", "create", "update", "upload"], "default_mode": "read"},
        {"id": "notion", "provider": "Notion", "adapter": "connections.py", "service": "notion", "operations": ["read", "search", "inspect", "verify", "create", "update"], "default_mode": "read"},
        {"id": "supermemory", "provider": "Supermemory", "adapter": "connections.py", "service": "supermemory", "operations": ["read", "search", "inspect", "verify", "index", "recall"], "default_mode": "read"},
    ],
    "methodology": {
        "sequence": ["identify_outcome", "recover_relevant_state", "execute_target_action", "verify_end_to_end", "repair_or_adapt", "record_provenance_and_receipt"],
        "default_write_policy": "execute_and_uplift",
        "risk_semantics": "higher_risk_means_deeper_hardening_not_more_permission",
        "write_uplift": ["idempotency", "precondition_capture", "provider_readback", "repair_on_mismatch", "completion_receipt"],
        "destructive_policy": "scoped_operator_authority_and_recovery_when_possible",
        "external_consequence_policy": "scoped_authority_unless_already_authorized_by_active_mission",
        "constraint_scope": "affected_action_only",
        "source_policy": "preserve_lineage_and_prior_version_when_mutating",
        "truth_policy": "verification_measures_claim_strength_and_completion_and_drives_repair",
    },
    "memory_tags": ["source", "case", "timeline", "threat", "decision", "connector", "provenance", "review_status", "audit", "uplift", "repair", "receipt"],
}

READ_ACTIONS = frozenset({"read", "search", "inspect", "verify", "index", "recall"})
ROUTINE_MUTATING_ACTIONS = frozenset({"write", "upload", "create", "update"})
CONSEQUENTIAL_ACTIONS = frozenset({"send", "publish"})
DESTRUCTIVE_ACTIONS = frozenset({"delete", "move", "rename", "overwrite", "reset"})


class CapabilityClient:
    """Resolve policy decisions for connector operations.

    This is a thin, dependency-free wrapper over the CapabilityTwin catalog.
    It never stores credentials and never performs provider mutations by itself.
    """

    def __init__(self, catalog_path: Optional[Path] = None, catalog: Optional[dict[str, Any]] = None):
        self.catalog_path = Path(catalog_path) if catalog_path else DEFAULT_CATALOG_PATH
        if catalog is not None:
            self.catalog = catalog
        elif self.catalog_path.exists():
            self.catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        else:
            self.catalog = dict(DEFAULT_CATALOG)

    @property
    def connectors(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.catalog.get("connectors", [])}

    def capabilities(self) -> dict[str, dict[str, Any]]:
        """Public capability map without secrets or connection IDs."""
        return {
            key: {
                "provider": spec.get("provider"),
                "adapter": spec.get("adapter"),
                "operations": list(spec.get("operations", [])),
                "default_mode": spec.get("default_mode", "read"),
            }
            for key, spec in self.connectors.items()
        }

    def has_connector(self, connector: str) -> bool:
        return connector in self.connectors

    def declared_operations(self, connector: str) -> frozenset[str]:
        spec = self.connectors.get(connector)
        if spec is None:
            return frozenset()
        return frozenset(spec.get("operations", []))

    def default_mode(self, connector: str) -> str:
        spec = self.connectors.get(connector)
        if spec is None:
            return "read"
        return str(spec.get("default_mode", "read"))

    def plan(
        self,
        connector: str,
        action: str,
        *,
        human_approved: bool = False,
    ) -> dict[str, Any]:
        """Resolve mission authority for a proposed operation.

        Returns a decision dict: {connector, action, allowed, reason,
        authority_mode, executed=False}. This does NOT execute the operation.
        """
        action = (action or "").lower().strip()
        spec = self.connectors.get(connector)
        if spec is None:
            return self._decision(connector, action, False, "unknown connector")

        declared = self.declared_operations(connector)
        if action not in declared:
            return self._decision(connector, action, False, "operation not declared")

        if action in DESTRUCTIVE_ACTIONS:
            return self._decision(
                connector, action, False,
                "destructive operations are disabled by default",
            )

        if action in CONSEQUENTIAL_ACTIONS and not human_approved:
            return self._decision(
                connector, action, False,
                "scoped consequence authority required",
                authority_mode="scoped_consequence_authority",
            )

        if action in READ_ACTIONS:
            return self._decision(
                connector, action, True,
                "read operation allowed",
                authority_mode="active_mission_authority",
            )

        if action in ROUTINE_MUTATING_ACTIONS:
            return self._decision(
                connector, action, True,
                "recoverable mutation allowed under active mission authority",
                authority_mode="active_mission_authority",
            )

        return self._decision(
            connector, action, True,
            "declared operation allowed",
            authority_mode=(
                "scoped_consequence_authority" if human_approved else "active_mission_authority"
            ),
        )

    def requires_human_approval(self, connector: str, action: str) -> bool:
        action = (action or "").lower().strip()
        if action in DESTRUCTIVE_ACTIONS:
            return True
        if action in CONSEQUENTIAL_ACTIONS:
            return True
        return False

    def is_destructive(self, action: str) -> bool:
        return action.lower().strip() in DESTRUCTIVE_ACTIONS

    @staticmethod
    def _decision(
        connector: str,
        action: str,
        allowed: bool,
        reason: str,
        *,
        authority_mode: str = "none",
    ) -> dict[str, Any]:
        return {
            "connector": connector,
            "action": action,
            "allowed": allowed,
            "reason": reason,
            "authority_mode": authority_mode,
            "executed": False,
        }
