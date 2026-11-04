# omp/sdk — GlacierEQ Capability + Quality SDK

## Scope

Dependency-free Python SDK integrating the omp model router (best-agent fallback
over free models) with the computer-user capability system (policy-aware
connectors, injected adapters, tamper-evident receipts, quality gates at floor
9.0).

## Package Layout

```
omp/sdk/
├── pyproject.toml   # glaciereq-sdk, stdlib-only
├── README.md        # quick start + design principles
├── AGENTS.md        # this file
├── __init__.py      # public exports
├── errors.py        # SDKError, PolicyError, VerificationError, QualityError,
│                    # ReceiptError, AdapterError, ConfigurationError
├── capability.py    # CapabilityClient (CapabilityTwin wrapper)
├── runtime.py       # ConnectorRuntimeClient (policy-gated plan/execute)
├── receipts.py      # ReceiptStore (tamper-evident SHA-256 receipts)
├── quality.py       # QualityGate, EvidenceChain, evidence chain CLAIM→RECEIPT
├── github.py        # GitHubClient + GitHubAdapter (14 tools, read-first)
└── client.py        # GlaciereqSDK unified client
```

## Conventions (from computer-user / apex-impact-engine)

- Two-space indentation is NOT used here; Python follows PEP 8 (4 spaces).
- Frozen-style validation: constructors raise on invalid input; never silent.
- Scores are floats in `[0, 10]`; quality floor `QUALITY_THRESHOLD = 9.0`.
- YAML/JSON: `schema_version`, `snake_case` keys, no comments/trailing commas.
- Model `status` one of: `unverified`, `available`, `unavailable`, `rate_limited`.
- No secrets in repo: connection metadata never holds tokens/passwords/keys.
- Read-first: connectors default to `read`; writes require uplift/approval.
- Destructive disabled by default.
- Plan is not execute: `plan()` resolves authority; `execute()` performs the call.
- No self-certification: executor ≠ verifier; independent readback required.

## Evidentiary Standard (Anti-Hallucination Protocol)

- L0: "I see a file named X." — observation only, do not act.
- L1: "It contains these functions/classes." — structure only.
- L2: "I ran it. It works." — the only level you may state as fact.

Never ship stubs, silent-swallowing fallbacks, or "return True" no-ops. Every
module must actually perform its task.

## Build / Test Commands

From `/workspace/projects/omp`:

```sh
# Import + smoke test the SDK
PYTHONPATH=. python3 -c "
from sdk.client import GlaciereqSDK
from sdk.quality import QualityGate
sdk = GlaciereqSDK()
print(sdk.health())
print(sdk.quality_floor())
"

# Validate quality gate behavior
PYTHONPATH=. python3 -c "
from sdk.quality import QualityGate, QUALITY_THRESHOLD
g = QualityGate()
print(g.gate_effort(effort_score=9.5, verified=True))   # pass
print(g.gate_effort(effort_score=6.0, verified=True))   # fail (pitstop)
"

# Run SDK unit checks if pytest is available
PYTHONPATH=. python3 -m pytest -q 2>/dev/null || echo "no pytest configured"
```

## Security

No API keys, tokens, or passwords are stored in this package. Provider
credentials resolve out-of-band through an injected adapter / credential broker
(computer-user/connections.py) and never enter the repository or receipt
payloads.

## Validation

After edits, re-run the import smoke test and confirm:
- `glaciereq-sdk` imports with no external dependencies
- quality gate passes at ≥ 9.0, fails (pitstop) below
- receipt SHA-256 integrity verification is fail-closed
- capability plan blocks destructive / undeclared operations
