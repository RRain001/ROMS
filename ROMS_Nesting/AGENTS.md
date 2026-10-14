# ROMS_Nesting — isolation rules

- Only modify files beneath `ROMS_Nesting/`, plus its dedicated GitHub Actions CI file and branch-local implementation plan.
- Never import or execute code from the repository-root `Data_pre/`, `ROMS_Build/`, `ROMS_Run/`, or `roms_src/`.
- Do not symlink source code into or out of this subtree. A one-time code copy is permitted; thereafter maintain it independently.
- Treat `ROMS_NESTING_ROOT` as the absolute root of this subtree when resolving dedicated case and build paths.
- Store generated grids/forcing/executables/logs only under `ROMS_Nesting/projects/`; keep external raw data sources read-only.
- Always distinguish completed I0 static/config tests from numerical ROMS runs. Do not claim a physical PASS without an actual supported runner and inputs.
- Never merge to `main` without explicit authorization. Follow the staged plan and capture first failure instead of weakening tests.
