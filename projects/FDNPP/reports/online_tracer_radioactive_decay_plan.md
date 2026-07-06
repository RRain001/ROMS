# Online Passive Tracer Radioactive Decay Plan

- decay profile: `online_my25_uvtide_decay` enabled=True
- no-decay profile: `online_my25_uvtide` enabled=False
- species: `HTO`
- target tracer: `dye_01`
- half-life years: `12.32`
- lambda s-1: `1.7828335004569908e-09`
- year conversion: `365.25` days/year
- CPP switch: `RADIOACTIVE_DECAY` in decay header only
- implementation: `roms_src/roms/ROMS/Nonlinear/step3d_t.F`, exponential sink on `inert(1)` / `dye_01`
- no-decay profile preserved: `True`

## Checks

- hto_half_life_years: `True`
- lambda_positive: `True`
- nodecay_disabled: `True`
- decay_enabled: `True`
- target_is_dye_01: `True`
- apply_to_temp_salt_false: `True`
- decay_header_has_cpp: `True`
- nodecay_header_lacks_cpp: `True`
- build_variant_distinct: `True`

## Mass Budget Note

For decay runs, use `source_input ~= domain_inventory + open_boundary_export + decay_loss + numerical_residual`.
`decay_loss` is estimated offline as `integral(lambda * dye_01 * cell_volume dt)`.
