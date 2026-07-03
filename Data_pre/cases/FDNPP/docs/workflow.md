# FDNPP 全流程使用说明

本文档记录 FDNPP 案例从 `Data_pre` 到 `ROMS_Build` 再到 `ROMS_Run` 的标准执行方式。运行时配置统一来自 `Data_pre/cases/FDNPP/config`，计算产物统一写入 `/home/lhy/ROMS/projects/FDNPP`。

## 1. 案例设置

- case name: `FDNPP`
- project root: `/home/lhy/ROMS/projects/FDNPP`
- 研究范围: `140.88-142.00E`, `37.00-37.84N`
- 积分窗口: `2025-01-01 00:00:00` 到 `2025-02-01 00:00:00`
- 默认海洋数据: HYCOM
- 垂向层数: `N=30`
- 当前并行设置: build jobs `56`, MPI ranks `56`, ROMS tiles `NtileI=7`, `NtileJ=8`
- 当前活动网格: `input/roms_grid_bathy_500m_maskclean_smoothed.nc`

## 2. 已准备的数据

FDNPP 的 Data_pre 数据已经按当前研究范围准备好，后续测试应使用这些数据，不依赖历史编译产物。

- `data/raw/bathymetry/gebco_fdnpp.nc`
- `data/raw/ocean/hycom_initial_20250101.nc`
- `data/raw/ocean/hycom_boundary_202501.nc`
- `data/raw/atmosphere/era5_atm_fdnpp_202501.nc`
- `data/raw/atmosphere/era5_rad_fdnpp_202501.nc`
- `data/raw/tides/tpxo9_fdnpp_202501.nc`
- `data/raw/source/fdnpp_source_discharge.csv`
- `input/roms_grid_bathy_500m_maskclean_smoothed.nc`
- `input/roms_ini_fdnpp_20250101.nc`
- `input/roms_bdy_fdnpp_202501.nc`
- `input/roms_atm_fdnpp_202501.nc`
- `input/roms_rad_fdnpp_202501.nc`
- `input/roms_tides_fdnpp_202501.nc`
- `input/fdnpp_source_hourly.csv`
- `input/roms_rivers_production.nc`

## 3. 预处理检查

在 `/home/lhy/ROMS` 下执行：

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py --case-name FDNPP --ocean-source hycom
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name FDNPP
```

如需重新生成运行输入文件：

```bash
python3 Data_pre/scripts/run_support/create_pilot_infile.py --case-name FDNPP --mode pilot_1day --forcing-mode external
python3 Data_pre/scripts/run_support/create_pilot_infile.py --case-name FDNPP --mode pilot_month --forcing-mode external
```

生成后的关键文件：

- `projects/FDNPP/run/ocean_fdnpp_pilot_1day.in`
- `projects/FDNPP/run/ocean_fdnpp_pilot.in`

nudging 关闭时，`.in` 文件应写 `NUDNAME == none`，不需要准备 `roms_nud_fdnpp.nc`。

## 4. 构建

先查看构建计划：

```bash
python3 ROMS_Build/scripts/build/show_build_plan.py --case-name FDNPP
```

如需重新编译：

```bash
python3 ROMS_Build/scripts/build/build_roms_case.py --case-name FDNPP
```

FDNPP 的网格包含 land/sea mask，CPP 头文件必须启用：

```c
#define MASKING
```

若未启用 `MASKING`，ROMS 会忽略 `mask_rho`，把掩膜陆地点当作浅水格点参与积分，可能在十几个模型小时内触发 BLOWUP。

当前配置会使用 `56` 个并行构建任务，标准可执行文件为：

```text
/home/lhy/ROMS/projects/FDNPP/bin/romsM_fdnpp
```

构建后可检查二进制：

```bash
python3 ROMS_Build/scripts/build/inspect_binary.py --case-name FDNPP
```

## 5. 运行前验证

1 天测试：

```bash
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP --mode pilot_1day
python3 ROMS_Run/scripts/run/run_case.py --case-name FDNPP --mode pilot_1day --dry-run
```

1 个月积分：

```bash
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP --mode pilot_month
python3 ROMS_Run/scripts/run/run_case.py --case-name FDNPP --mode pilot_month --dry-run
```

`dry-run` 应显示 56 核启动命令，并指向：

```text
/home/lhy/ROMS/projects/FDNPP/bin/romsM_fdnpp
/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_pilot.in
```

## 6. 真实运行

真实 Intel MPI/Hydra 运行需要在普通终端或已批准的非沙箱环境执行；沙箱环境可能阻止本地 socket 创建，导致 MPI 启动失败。

当前 `.in` 文件已显式关闭非必要的平均 tracer 二次项和体积通量项：

```text
Aout(idTTav) == F F F
Aout(idUTav) == F F F
Aout(idVTav) == F F F
Aout(iHUTav) == F F F
Aout(iHVTav) == F F F
```

这样可避免 ROMS 在写 `Huon_dye_01` 平均场时触发 NetCDF `Numeric conversion not representable`。`Aout(inert)` 仍保留为 `T`，平均文件继续输出 `dye_01` 本身。

手动触发 1 个月积分：

```bash
cd /home/lhy/ROMS
python3 ROMS_Run/scripts/run/run_case.py --case-name FDNPP --mode pilot_month
```

查看日志：

```bash
python3 ROMS_Run/scripts/run/tail_run_log.py --case-name FDNPP --mode pilot_month
```

或直接：

```bash
tail -f /home/lhy/ROMS/projects/FDNPP/logs/pilot_month.log
```

## 7. 输出位置

- 运行日志: `/home/lhy/ROMS/projects/FDNPP/logs/pilot_month.log`
- 历史输出: `/home/lhy/ROMS/projects/FDNPP/output/his_fdnpp_pilot.nc`
- 重启动输出: `/home/lhy/ROMS/projects/FDNPP/output/rst_fdnpp_pilot.nc`
- 平均输出: `/home/lhy/ROMS/projects/FDNPP/output/avg_fdnpp_pilot.nc`
- 诊断输出: `/home/lhy/ROMS/projects/FDNPP/output/dia_fdnpp_pilot.nc`

2026-07-03 的 16 小时短测已验证 `MASKING` 版二进制可以越过此前 `2025-01-01 14:00:00` 的 BLOWUP 点并正常结束。月积分仍建议先做 `pilot_month --dry-run` 和 `validate_run_prereqs`，确认二进制、`.in`、NetCDF 输入和 `NtileI*NtileJ=np=56` 全部一致后再提交真实运行。
