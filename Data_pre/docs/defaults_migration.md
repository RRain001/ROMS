# Defaults Migration: HYCOM/N30 to GLORYS12V1/N40

The framework's current canonical defaults are:

| Setting | Current standard | Historical standard |
|---|---|---|
| Ocean source | `GLORYS12V1` | `HYCOM` |
| Vertical levels | `N=40` | `N=30` |

FDNPP explicitly uses the current standard in
`Data_pre/cases/FDNPP/config/project_parameters.json`.

## Compatibility rules

- Existing historical cases and reports are not rewritten.
- HYCOM remains supported through `--ocean-source hycom` and its staged-download
  configuration.
- An explicit case `vertical.N` value remains authoritative, even when it is
  not 40.
- Existing generated files with unsuffixed or legacy names are historical or
  compatibility products unless the active run configuration references them.
- New cases should use the canonical GLORYS source-suffixed input names.

When reviewing an older report, first check its case directory and generation
date. `Data_pre/cases/FDNPP_202501` and material under `archive/` are historical
snapshots; `Data_pre/cases/FDNPP` is the current active FDNPP configuration.
