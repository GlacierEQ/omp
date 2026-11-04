omp
└── free model roster + best-agent fallback router

  roster.yaml   curated free-tier model roster (schema_version 1)
  model.py      frozen dataclass contracts with validation
  router.py     scoring, ranking, fallback chain, attempt tracking
  __init__.py   package exports
  AGENTS.md     project conventions

model.py contracts:
  ModelEntry        single roster row (id, provider, endpoint, context window,
                    capabilities, rate limits, cost, status, capability scores)
  TaskRequest       what the caller needs (task type, required capabilities,
                    min context window, providers to avoid)
  RouteAttempt      one attempt record (model, timestamp, success, error, latency)
  RouterDecision    selected model + ordered fallback chain + attempts + rationale

router behavior:
  - scores every available model against the request
  - builds a best-first fallback chain (highest score first)
  - on attempt failure (error / rate limit / unavailable) advances to the next
    model in the chain and records the attempt
  - unverified models are penalized but still eligible; verified models preferred
  - returns RouterDecision so callers can observe routing rationale and retry
