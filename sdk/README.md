# GlacierEQ SDK

Dependency-free Python SDK for integrating with the GlacierEQ computer-user
capability and quality system. Zero secrets, zero credentials, zero provider
SDKs in the repository.

## What it provides

| Module | Responsibility |
|--------|---------------|
| `sdk.capability` | Policy-aware connector surface (CapabilityTwin) |
| `sdk.runtime` | Policy-gated plan/execute runtime with injected adapters |
| `sdk.receipts` | Tamper-evident SHA-256 invocation & execution receipts |
| `sdk.quality` | Evidence chain, independent verification, quality threshold 9+ |
| `sdk.github` | GitHub connector module (14 tools, read-first, write-with-uplift) |
| `sdk.client` | Unified client: router → capability → execute → receipt → quality |

## Design principles (from computer-user)

- **Zero secrets:** connection metadata never contains tokens, passwords, or keys. Credentials resolve out-of-band via an injected credential broker.
- **Read-first:** all connectors default to `read` mode; mutations are not the default path.
- **Writes require uplift:** routine mutations and all consequential/external actions require explicit scoped authority (idempotency, precondition capture, provider readback, repair, receipt).
- **Destructive disabled by default:** delete/move/rename/overwrite/reset are blocked unless explicitly authorized.
- **Plan is not execute:** `plan()` resolves authority; `execute()` performs the provider call only after a pass decision.
- **No self-certification:** the executor must never be its own verifier; verification requires an independent readback.
- **Quality floor:** operations must evidence a quality score ≥ 9.0 to count as completion-grade.

## Quick start

```python
from sdk.client import GlaciereqSDK
from sdk.github import GitHubAdapter

sdk = GlaciereqSDK()

# 1. Select the best free model for a coding task
decision = sdk.router.select(
    task_type="coding",
    required_capabilities=("coding", "reasoning"),
    min_context_window=32768,
)
model = decision.selected

# 2. Plan a GitHub read through the capability twin
plan = sdk.capability.plan("github", "get_repository")
assert plan["allowed"]

# 3. Execute through an injected adapter (credentials resolved out-of-band)
result = sdk.runtime.execute(
    "github", "get_repository",
    payload={"owner": "GlacierEQ", "repo": "computer-user"},
    adapter=GitHubAdapter(credential_headers={...}),
)

# 4. Seal a tamper-evident receipt
receipt = sdk.receipts.finalize(task_id="task-1", status="completed", attempts=1, result=result)

# 5. Gate completion at quality ≥ 9
gate = sdk.quality.gate_effort(effort_score=9.5, verified=True)
assert gate["decision"] == "pass"
```

## Security

No API keys, tokens, or passwords are stored in this package. Connection metadata
(IDs, tool names, credential paths) is non-secret. Provider credentials are
resolved at runtime by an injected `CredentialBrokerClient` (see
`computer-user/connections.py`) and never enter this repository.

See `AGENTS.md` for the evidentiary standard (L0/L1/L2) and contribution
conventions.
