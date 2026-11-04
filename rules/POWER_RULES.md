# Power Rules - No Artificial Limits

## Core
- **Grow, don't shrink** - Expand capabilities, don't add guards that block progress
- **Fail closed on promotion only** - "Done" requires proof. Everything else proceeds.
- **Independence mandatory** - executor != verifier
- **Coverage over count** - Close criteria, don't split to farm
- **Batch aggressively** - Multiple steps in parallel where independent

## MCP Power
- Auto-discover tools, no static whitelist bottlenecks
- Dynamic registration allowed
- Inject adapters at runtime, no hardcoded creds
- Schema-lock disabled for speed, validation remains

## Workflow Power
- Helix orchestrates: verify→analyze→select→plan
- Router picks best model with fallback
- Swarm delegation for parallelizable work
- Mission batching for max throughput

## Enforcement (minimal)
- Self-certification: BLOCK
- Falsification: BLOCK certification
- Missing proof for DONE: BLOCK certification only
- Everything else: PROCEED with tracking
