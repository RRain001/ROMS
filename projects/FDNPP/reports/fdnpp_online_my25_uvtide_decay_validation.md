# FDNPP Online MY25 UV-Tide Decay Validation

- status: `ok`
- profile: `online_my25_uvtide_decay`
- lambda s-1: `1.7828335004569908e-09`
- decay loss estimate: `290134.0567451178` Bq
- build: `ok`
- run: `ok`
- no-decay last inventory: `15068493133.136677` Bq
- decay last inventory: `15068202875.375084` Bq
- decay inventory lower: `True`
- no NaN detected: `True`
- source cumulative input: `15068493150.68493` Bq

## Implementation

- configuration: `passive_tracer.radioactive_decay` with profile override in `project_parameters.json`
- CPP: decay build defines `RADIOACTIVE_DECAY`, no-decay build does not
- ROMS source: `step3d_t.F` applies `C_new = C_old * exp(-lambda * dt)` to `inert(1)` / `dye_01` only
- defaults: species `HTO`, unit `Bq m-3`, half-life `12.32 years`, year conversion `365.25 days/year`
- no-decay profile preserved: `online_my25_uvtide`

## Budget Form

`source_input ~= domain_inventory + open_boundary_export + decay_loss + numerical_residual`.
The `decay_loss` above is an offline trapezoidal estimate of `integral(lambda * dye_01 * cell_volume dt)`.

## Recommendation

The decay profile passed a 6-hour smoke validation. Run a longer multi-day comparison before using it for 1-year production.
