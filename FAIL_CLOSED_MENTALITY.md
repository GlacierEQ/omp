# Fail-Closed on Promotion, Fail-Open on Progress

## Core Principle
Block false claims, never block progress.

## Rules
1. **Progress is always possible** - Missing evidence -> get it, don't stop
2. **Promotion requires proof** - Only Helix.certify() can mark DONE
3. **Independence required** - executor != verifier for completion
4. **All-or-nothing** - 100% coverage of criteria required
5. **No self-certification** - Hard block
6. **No fracture rewards** - Churn tracked, coverage-based progression

## Implementation
- Helix: verify→analyze→select→plan, blocks only self-cert/falsification
- Certification: permissive recording, strict on certify()
- Runtime: defaults to executed_unverified, needs independent readback for completed
- Receipts: independence enforced only on promotion to completed
- Router: tracks attempts but doesn't block progress
