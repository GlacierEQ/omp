# omp — Free Model Roster + Best-Agent Fallback Router

## Scope

Curates a roster of free-tier models and routes requests across them with a
best-first fallback chain. Greenfield package under `/workspace/projects/omp/`.

## Project Structure

```
omp/
├── README.md        # package overview + model contracts
├── roster.yaml      # curated free-tier model roster (schema_version 1)
├── model.py         # frozen dataclass contracts with validation
├── router.py        # scoring, ranking, fallback chain, attempt tracking
├── __init__.py      # package exports
└── AGENTS.md        # this file
```

## Build, Test, and Development Commands

Run these commands from the workspace root (`/workspace/projects`):

```sh
# Validate roster YAML syntax
python3 - <<'EOF'
import yaml
yaml.safe_load(open("omp/roster.yaml"))
print("roster.yaml OK")
EOF

# Smoke-test the router (exercises scoring, selection, fallback, attempts)
python3 -m omp.router_smoke  # if a smoke script is added
```

There is no local test runner configured. Do not describe upstream test results as
checks performed in this workspace.

## Coding Style & Naming Conventions

- Two-space indentation for YAML; valid YAML without comments or trailing commas.
- `snake_case` keys in YAML; preserve `schema_version` and source identities.
- Python: frozen `@dataclass` contracts with `__post_init__` validation (matches
  `First/dependencies/apex-impact-engine/src/apex_impact/model.py`).
- Scores are floats in `[0, 10]`; context windows and rate limits are non-negative ints.
- Model `status` must be one of: `unverified`, `available`, `unavailable`, `rate_limited`.

## Validation Guidelines

After edits, validate roster YAML syntax and review affected identifiers, providers,
capability scores, and status values. Syntax validation does not establish provider
availability. None of the roster entries have been live-verified in this workspace;
treat every `status: unverified` entry as a hypothesis until a router attempt
confirms a successful call.

## Security & Configuration

Record secret references rather than credentials. `roster.yaml` contains no API keys
or tokens. Endpoints are public documentation URLs only.

## Evidentiary Standard (The Anti-Hallucination Protocol)

- L0: "I see a file named X." — observation only, do not act.
- L1: "It contains these functions/classes." — structure only, do not assume behavior.
- L2: "I ran it. It works." — the only level you may state as fact.

Never write stubs, fallbacks that silently swallow errors, or "return True" no-ops.
Every module shipped must actually perform its task.
