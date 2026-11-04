# Deployment Map - Highest Level Per Item

## Core
- **router.py**: ModelRouter + AutoRouter + CoverageAwareRouter - MAXIMIZED (auto-routing, coverage-aware, fallbacks)
- **model.py**: Data models - SOLID
- **_yaml_subset.py**: Dependency-free parser - SOLID
- **roster.yaml**: 8 free models configured - SOLID

## SDK
- **sdk/client.py**: GlaciereqSDK with auto-helix wiring - MAXIMIZED
- **sdk/helix.py**: Double helix orchestrator, durable/persistent - MAXIMIZED (fail-open progress, fail-closed promotion)
- **sdk/certification.py**: MissionTracker strict on certify only - MAXIMIZED
- **sdk/runtime.py**: Policy-gated execution, independence enforcement - SOLID
- **sdk/receipts.py**: Tamper-evident, independence on promotion only - SOLID
- **sdk/github.py**: GitHub integration helix-aware - SOLID
- **sdk/quality.py**: Quality gates pitstop not wall - SOLID
- **sdk/mission_batch.py**: Proactive batching - MAXIMIZED
- **sdk/persistence.py**: MissionStore + DurableMissionStore + GlobalStateStore - MAXIMIZED

## Power Stack
- **mcp/mcp_power.py**: Dynamic discovery, no limits - DEPLOYED
- **workflows/power_workflow.yaml**: Batching workflow - DEPLOYED
- **swarm/power_swarm.py**: 32 concurrent workers - DEPLOYED
- **rules/POWER_RULES.md**: Tension not force - DEPLOYED
- **cli/omp.py**: Power CLI - DEPLOYED
- **config/power_config.yaml**: Max power config - DEPLOYED
- **config/availability.yaml**: Model availability config - DEPLOYED

## Tracking
- **model_availability.py**: Persistent health tracking - DEPLOYED
- **__init__.py**: Full exports - DEPLOYED

All items reviewed, maximized, and deployed.
