# LAHAGUE 案例构建经验

本文记录 LAHAGUE 核心区 ROMS 案例从研究范围、真实海岸线和 bathymetry
校正、网格生成、连续 forcing、潮汐修正、ROMS-ready 输入到构建验证的流程。
本文中的数值和文件名是 LAHAGUE 实例；流程可以复用，但研究范围、源项强度、
时间窗和网格分辨率不能直接照搬。

相关文件：

- [LAHAGUE 配置](../cases/LAHAGUE/config/project_parameters.json)
- [LAHAGUE 工作流](../cases/LAHAGUE/docs/workflow.md)
- [LAHAGUE readiness report](../cases/LAHAGUE/docs/readiness_report.md)
- [新案例添加指南](adding_a_case.md)

## 1. 当前状态快照

截至 2026-08-24：

| 项目 | 状态 | 说明 |
|---|---|---|
| GEBCO/GSHHG 和最终网格 | 已完成 | `500 m` 网格、mask 和 bathymetry 已固定 |
| GLORYS12V1 连续数据 | 已完成 | 覆盖 `2024-10-01` 至 `2026-01-01` |
| ERA5 连续数据 | 已完成 | 大气和辐射覆盖完整窗口 |
| 修正后的 TPXO9 | 已完成 | 复数潮汐常数、潮位和 UV 椭圆均已生成 |
| ROMS-ready 输入和在线 executable | 已完成 | 连续 `.in`、潮汐文件和 executable 已验证 |
| LAHAGUE 计算 | 未启动 | 本次只准备和验证，不启动 LAHAGUE |

## 2. 研究范围和最终网格

当前活动范围为：

- 经度：`-3.00` 至 `-1.55` E；
- 纬度：`49.27` 至 `50.05` N；
- 水平分辨率：`500 m`；
- 垂向层数：`N=40`；
- 最终网格：`xi_rho=211`、`eta_rho=176`，即 `Lm=209`、`Mm=174`；
- 最小水深约束：`Hmin=10 m`。

只要 mask 或 bathymetry 平滑改变最终网格，就必须重新生成海洋初始场、边界
场、潮汐、源项和 `.in` 文件，不能继续使用旧网格的派生文件。

## 3. 单一连续计算设计

当前默认任务不是独立的冷启动和热启动，而是一个连续积分：

| 时段 | 设置 |
|---|---|
| `2024-10-01` 至 `2025-01-01` | 可配置的 3 个月 preproduction 窗口，`river_dye_01=0` |
| `2025-01-01` 至 `2026-01-01` | 正式结果窗口，使用正式源项 |
| 整个窗口 | 同一个 executable、同一个 `.in`、`NRREC=0` |

初始场使用 `2024-10-01` 的 GLORYS 初始场；海洋状态不是静止冷水，而是
GLORYS 初始化状态。潮汐由同一个 executable 在任务开始时执行一次 `RAMP_TIDES`，
不会在 `2025-01-01` 重新 ramp。输出覆盖整个窗口，后处理再截取正式结果窗口。

restart 文件是异常中断后的恢复检查点，不是正式阶段交接文件。旧的
spin-up/production run modes 保留用于历史结果兼容，但不属于 LAHAGUE 默认流程。

## 4. 源点和单位换算

LAHAGUE 的 `(-1.87, 49.67)` 只是参考坐标，不代表已经核实的海上排放口。源点
按以下规则放置：

```text
参考坐标 -> mask_rho 湿点 -> 满足 h >= Hmin 的最近有效 RHO 网格
```

当前连续源文件记录：

- `xi=163`，`eta=86`；
- `source_lon=-1.874524`，`source_lat=49.653314`；
- 水深：`11.280 m`；
- 吸附距离：`1.886 km`，低于 `5 km` 警告阈值。

源项为总液态放射性活度等效示踪剂：

```text
11.15 PBq/year = 3.535641806e8 Bq/s
```

载体流量为 `1 m3/s` 数值占位值，不是实测排放流量。连续源文件中载体输运仍
可保持为 1，但 `river_dye_01` 在 `2025-01-01` 前必须严格为零。PBq/TBq 到
Bq/s 的换算统一由共享 `source_activity.py` 完成。

## 5. 连续数据文件

原始 forcing 使用以下 canonical 文件：

```text
data/raw/ocean/glorys12v1/glorys12v1_static_lahague.nc
data/raw/ocean/glorys12v1/glorys12v1_initial_20241001.nc
data/raw/ocean/glorys12v1/glorys12v1_boundary_20241001_20260101.nc
data/raw/atmosphere/era5_atm_lahague_20241001_20260101.nc
data/raw/atmosphere/era5_rad_lahague_20241001_20260101.nc
data/raw/tides/tpxo9_lahague_20241001_20260101.nc
data/raw/source/lahague_source_discharge.csv
```

ROMS-ready 文件为：

```text
input/roms_ini_lahague_glorys12v1_20241001_online_my25_uvtide.nc
input/roms_bdy_lahague_glorys12v1_20241001_20260101_online_my25_uvtide.nc
input/roms_atm_lahague_20241001_20260101.nc
input/roms_rad_lahague_20241001_20260101.nc
input/roms_tides_lahague_online_my25_uvtide.nc
input/roms_rivers_lahague_online_continuous_my25_uvtide.nc
```

GLORYS 日平均资料时间中心为 `12:00`，ROMS-ready 转换显式映射到模型日
`00:00`，验证时必须读取真实 time variable，不能只看文件名。

## 6. TPXO 潮汐修正

TPXO atlas 使用交错复数记录：潮位为 `[Re, Im]`，流速为
`[URe, UIm, VRe, VIm]`。当前流程先插值复数实部/虚部，再重建潮汐量：

- `tide_Ephase = -angle(Re + i Im)`，遵循 OTPS 约定；
- `tide_Cmax/Cmin/Cangle/Cphase` 从复数流速重建 ROMS current ellipse；
- 原始 TPXO/OTPS 参考、`V0` 处理、节点修正和重构方式写入 NetCDF metadata；
- ROMS-ready 文件固定 `zero_phase_date=20241001`，不会被模拟开始日期覆盖。

CPP header 必须同时包含：

```text
SSH_TIDES UV_TIDES RAMP_TIDES TIDES_DATE
```

`Lnodal=F`，因为外部 TPXO 系数已经按当前流程处理，不再由 ROMS 重复施加
外部潮汐节点修正。

## 7. 准备、验证和构建

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py --case-name LAHAGUE
python3 Data_pre/scripts/validation/validate_staged_data_deep.py --case-name LAHAGUE
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py \
  --case-name LAHAGUE --profile online_my25_uvtide --require-uv-tides \
  --infile projects/LAHAGUE/run/ocean_lahague_online_continuous_my25_uvtide_glorys12v1.in
python3 Data_pre/scripts/validation/validate_formal_online_workflow.py \
  --case-name LAHAGUE --profile online_my25_uvtide --phase pre-run
python3 ROMS_Build/scripts/build/show_build_plan.py \
  --case-name LAHAGUE --variant online_my25_uvtide
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py \
  --case-name LAHAGUE --mode online_continuous_my25_uvtide
python3 ROMS_Run/scripts/run/run_case.py \
  --case-name LAHAGUE --mode online_continuous_my25_uvtide --dry-run
```

需要重新准备时，先固定最终网格，再按连续窗口生成源项、GLORYS、ERA5、TPXO、
ROMS-ready 输入和 `.in`。下载使用 `--resume`，原始 NetCDF、大型缓存和运行
输出不提交 Git。

## 8. 后台运行和验收

正式启动前确认：

1. 连续 `.in` 使用 `NRREC=0` 和 `2024-10-01` 初始场；
2. `NTIMES` 覆盖至 `2026-01-01`；
3. `river_dye_01` 在正式开始前为零；
4. formal workflow、run prerequisites 和 CPP build artifact 检查全部通过。

后台任务需要同时监控 ROMS/MPI 进程、日志中的模型时间和 restart 的有效
`ocean_time`。不要把“进程曾出现”或“restart 文件已创建”当成完成依据。
异常中断时从最近 checkpoint 恢复；正常情况下不需要等待 preproduction 完成
后再手动启动 production。
