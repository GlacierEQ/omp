# Priority Scan & Improvements

## Completed (Durable & Leveraged)
1. **Helix Persistence** - Mission state saved to ~/.omp/missions.json with auto-load, survives restarts ✓
2. **Durable Mission Store** - File locking (fcntl) for multi-process safety, GC support ✓
3. **Global State Store** - Central persistence for all subsystems ✓
4. **Model Availability** - Persistent health tracking, solidified across restarts ✓
5. **Auto-Wiring** - Helix auto-attached to SDK/GitHub operations ✓
6. **Coverage-Aware Routing** - Prioritizes coverage gain, penalizes churn harder ✓
7. **Power Stack** - MCP/workflows/swarm/rules/CLI all integrated ✓

## Next Priorities (To Maximize)
1. **Cross-process coordination** - Add mission locks to prevent concurrent certification conflicts
2. **Auto-evidence capture** - Extract readbacks from results automatically without manual passing
3. **Router integration** - Wire CoverageAwareRouter into AutoRouter for default coverage-aware behavior
4. **Health auto-refresh** - Periodic model health checks with fallback updates
5. **Mission completion hooks** - Auto-certify when all criteria met with valid evidence

## System Health
- Models: 8 (all tracked)
- Missions: Persistent & durable
- Enforcement: Fail-open progress, fail-closed promotion ✓
- Tension not force ✓
