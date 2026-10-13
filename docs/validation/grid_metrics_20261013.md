# 规则经纬度网格度量修复与案例影响评估（2026-10-13）

本次只修改新建网格的四个度量字段，增加已有文件修复工具和检查；未改变任何正式网格、案例配置、CPP 头文件、ROMS 4.3 核心源代码或运行入口，未启动模拟。真实网格修复样本放在各案例 `projects/<case>/output/grid_metrics_audit_20261013/roms_grid_metrics_fixed.nc`，不是活动输入。完整统计、文件哈希、非目标变量检查清单和输入文件清单见同目录的 `roms_grid_metrics_fixed.nc.audit.json` 及仓库中的 [案例审计 JSON](grid_metrics_case_audit_20261013.json)。

## 原因、定义与边界约定

`xi_rho=lm+2` 实际有 `lm+1` 个间隔，`eta_rho=mm+2` 实际有 `mm+1` 个间隔。旧实现用 `width/lm`、`height/mm`，还以中心纬度和 `111320 m/degree` 近似整个区域，因而两方向间距都有偏差。规则角度网格不等于等距物理网格；东西尺度随纬度变化。

官方 [mod_grid.F](https://github.com/myroms/roms/blob/develop/ROMS/Modules/mod_grid.F) 定义 `pm/pn` 为坐标变换尺度（m⁻¹），`dndx=d(1/pn)/dXI`、`dmde=d(1/pm)/dETA`。官方 [ana_grid.h](https://github.com/myroms/roms/blob/develop/ROMS/Functionals/ana_grid.h) 的中心差分也与本地 ROMS 4.3 源码一致。本地依据为 `roms_src/roms/ROMS/Functionals/ana_grid.h:758–771`，不是对物理 x/y 求导。

运行环境需有 numpy、netCDF4、pyproj；本次验证版本为 numpy 2.2.6、netCDF4 1.7.4、pyproj 3.7.1。新模块使用 `pyproj.Geod(ellps="WGS84")` 计算每对相邻 RHO 点的测地距离。内部 RHO 尺度取两个入射边长度均值；最外侧取唯一入射边长度。导数内部取半差，边缘取前向/后向一阶差分。这相当于线性外推边缘外的尺度，再应用 ROMS 中心差分；它是本工具对缺失外侧点的明确约定，**不宣称 ROMS 官方要求所有文件边缘采用此约定**。常量及线性尺度均满足该约定，非均匀与最小 2×2 网格有回归测试。非周期单网格适用；周期接缝与曲线网格的 angle/正交性需要另行检查，本工具不修复它们。

`x_rho/y_rho` 和 staggered x/y 仍是旧近似平面坐标；`xl/el` 仍为旧近似区域长度，不能用来推回真实地理间距。本地 `get_grid.F` 在 spherical 模式按 lon/lat 填充地理坐标；`metrics.F:349–351` 用 `1/pm`、`1/pn`、`1/(pm*pn)` 生成实际尺度和面积。当前单网格动力尺度不从 x/y 或 xl/el 重算。它们可能影响可视化、用户自定义 analytical 功能或其他外部程序，故保留原值并记录限制；此次不连带修改。ROMS 面积是度量乘积近似，不等于另行积分的椭球多边形面积，库存应使用求解器一致的面积。

## 代码与工具

- `Data_pre/core/grid_metrics.py`：统一距离、尺度及计算坐标导数；检查形状、有限值、纬度及正边长。
- `Data_pre/impl/preprocessing/create_grid_from_bathymetry.py`：保留点数、meshgrid、地形插值及所有参数，只替换度量计算；添加方法和辅助坐标限制元数据。现有 GSHHG 清理、平滑和后续流程未修改。
- `Data_pre/scripts/bathymetry/repair_grid_metrics.py`：复制完整原文件，再只更新四字段和 `grid_metrics_repair` 全局记录。拒绝输入等于输出、任何已有输出/报告、Cartesian 网格及非浮点或打包尺度字段。原有四个字段须存在，维度须为 `(eta_rho, xi_rho)`。
- `Data_pre/impl/preprocessing/check_roms_grid_quality.py`：保留正交、mask、h、源位置检查；增加独立重建距离及四度量检查，FAIL 时返回 1，完整报告仍写出。
- `Data_pre/tests/test_grid_metrics.py`：8 个测试方法，其中一个以五种纬度范围运行子测试。
- 本说明与案例审计 JSON：可审阅的静态实测结果。

修复示例（先 dry-run，实际执行时换用另一个报告路径）：

```bash
python3 Data_pre/scripts/bathymetry/repair_grid_metrics.py \
  --input projects/FDNPP/input/roms_grid_bathy_500m_maskclean_smoothed.nc \
  --output projects/FDNPP/output/metrics_review/roms_grid_metrics_fixed.nc \
  --report projects/FDNPP/output/metrics_review/dry_run.json --dry-run
python3 Data_pre/scripts/bathymetry/repair_grid_metrics.py \
  --input projects/FDNPP/input/roms_grid_bathy_500m_maskclean_smoothed.nc \
  --output projects/FDNPP/output/metrics_review/roms_grid_metrics_fixed.nc
python3 Data_pre/scripts/check_roms_grid_quality.py --case-name FDNPP \
  --grid projects/FDNPP/output/metrics_review/roms_grid_metrics_fixed.nc \
  --output-dir projects/FDNPP/output/metrics_review/quality
```

默认审计文件为 `OUTPUT.audit.json`。dry-run 只写审计，不写 NetCDF，输出文件哈希为 null，统计是按目标 dtype 转换后的预期值。正式修复提供输入、输出 SHA256，各字段前后 min/max/mean/非有限计数及变化 max/P95。逐变量验证原始编码值、dtype、维度、属性、压缩、chunking、endianness、组和全局元数据，任何意外变化均阻止发布；文件使用原格式，原文件哈希在修复后再核对。发布以原子方式创建新文件，不提供覆盖选项。

质量容差：`pm/pn` 相对误差 `1e-6`（比 float32 舍入上界约 `6e-8` 留有余量）；导数绝对误差 `max(1e-7 m, 16*eps_storage*max_spacing)`，涵盖倒数及邻点差分舍入，避免对理论零导数计算相对误差。float64 当前三个案例为 `1e-7 m`。测试确认 float32 文件可通过、旧零 dmde 与错误/非正/非有限度量不能通过。质量代码独立重建边距离、中心尺度和差分，未调用生产函数。更独立的距离参考是测试内的标量 WGS84 Vincenty inverse 算法（不调用 PROJ），距离符合 `rtol=2e-9, atol=2e-5 m`。

## 三案例实测

FDNPP/LAHAGUE 使用现有 `roms_grid_bathy_500m_maskclean_smoothed.nc`；WOLSONG 实际活动文件是 `roms_grid_bathy_500m_smoothed.nc`，按其 `.in` 与解析器使用该文件，没有假定存在 maskclean_smoothed 版本。

| 案例 | RHO 形状 eta×xi | 旧 pm 相对误差 max / P95 | 旧 pn 相对误差 max / P95 | 旧 dmde 绝对误差 max / P95（m/index） |
|---|---:|---:|---:|---:|
| FDNPP | 190×201 | 0.936308% / 0.882834% | 0.834980% / 0.834347% | 0.0295763 / 0.0295510 |
| WOLSONG | 203×201 | 0.949895% / 0.893865% | 0.829774% / 0.829078% | 0.0280058 / 0.0279773 |
| LAHAGUE | 176×211 | 1.081846% / 1.008574% | 0.665204% / 0.664627% | 0.0457996 / 0.0457770 |

三例旧 dndx 与地理参考一致，为零；没有人为制造非零值。修复后四字段 max/P95 误差在独立质量计算中均为 0，三个完整质量入口全部 PASS（旧文件均 FAIL）。这是同一 WGS84 距离算法不同构造路径的数值一致性；额外 Vincenty 测试提供不同算法参考，不能把 0 误差解释成地理学上的无限精度。

三例均可以直接复制修复，原 lon/lat、h、四种 mask、f、angle、辅助坐标及所有其他科学变量逐变量保持一致。它们仍需后续数值验证，不能据此认定一年期模拟已经准备好。

| 案例 | 湿区总面积变化 | 湿区总体积变化（zeta=0） | 单元面积变化范围 | 同 dt/u/v 时 XI CFL 比值范围 | ETA CFL 比值范围 |
|---|---:|---:|---:|---:|---:|
| FDNPP | −1.20217% | −1.12611% | −1.74955% 至 −0.66002% | 0.99824–1.00945 | 1.00828–1.00842 |
| WOLSONG | −1.19118% | −1.39355% | −1.75714% 至 −0.66096% | 0.99830–1.00959 | 1.00822–1.00837 |
| LAHAGUE | −0.98066% | −1.07806% | −1.72662% 至 −0.15651% | 0.99491–1.01094 | 1.00656–1.00670 |

面积采用 `A=1/(pm*pn)`，体积采用 `A*h`，以 `mask_rho=1` 的文件 RHO 点汇总（包含文件边缘点；作为一致的前后审计，不是另行裁剪模型内区的全球守恒诊断）。瞬时体积和示踪库存实际应使用 `A*Hz` 与浓度。修复保持水深与垂向配置，改变面积和各层水体积；任意非均匀示踪库存须逐单元重算，不能统一乘湿区总体积比。

实际重力波 CFL 路径是 `metrics.F:852–879` 的 `dtfast*sqrt(g*h*(pm²+pn²))`。固定 dtfast/h 的单元比值和最大 Cg 比值写入审计 JSON；没有运行求解器，不推断模拟中的实际 u/v。水平平流使用新物理距离，扩散算子及按面积缩放的混合系数也改变，扩散稳定性应重新计算。旧稳定 dt 的裕度不能直接继承。

## 求解器与输入复用

三个案例当前 `projects/<case>/run/*.h`（default、online_my25_uvtide、decay）均定义 `UV_ADV`，未定义 `CURVGRID`。本地 `get_grid.F:231–241,992–1099` 在 `CURVGRID && UV_ADV` 下读取导数；`rhs3d.F:628–`、`step2d_LF_AM3.h:1530–` 在同条件下使用曲率转换项。没有启用该宏时，修复的 pm/pn 仍进入面积、通量、混合与 CFL，但 dndx/dmde 不进入动量方程。保持案例兼容意味着本 PR 不静默启用 CURVGRID。若准备采用完整球面变尺度曲率项，须在隔离测试变体启用、通过 ROMS_Build 重编译并对照后，再确认是否推广到正式案例。

审计了 FDNPP 24 个、WOLSONG 17 个、LAHAGUE 17 个非网格输入文件的 schema，均没有 pm/pn、导数、cell_area/cell_volume 字段。这个检查本身不足以证明复用，以下结论同时核对了生成代码及共享 helper：

| 输入或派生量 | 结论与依据 |
|---|---|
| GEBCO/GSHHG、格点坐标、水深、mask | 保留，已经验证逐变量相同。 |
| GLORYS 初始温盐、速度、zeta，海洋边界 | 当前 `create_ocean_ini_from_glorys.py` / `create_ocean_bry_from_glorys.py` 只用 lon/lat 插值、h/垂向配置、mask 与 angle 旋转；它们均未改变，因此可作为点值/速度输入复用。边界速度对应的积分输运会随面宽变化，须在新运行中重核预算。 |
| ERA5 大气、辐射 | `create_atm_forcing_from_era5.py` / `create_rad_forcing_from_era5.py` 插值只依赖相同 lon/lat/mask，可复用；表面单位面积通量的全域积分须用新面积。 |
| TPXO 潮汐 | `create_tides_from_tpxo.py` 用 lon/lat 插值、TPXO 自身深度处理和角度，不依赖 ROMS pm/pn，可复用；模型潮流响应会变。 |
| river/source 输入 | `create_river_source_production.py` 和 pilot 版本用 `C=release_Bq_s/Q_m3_s`，位置 helper 仅使用 lon/lat/h/mask；垂向形状未改变。实测所有当前源文件 Q=1 m³/s，Vshape 和为 1；逐文件 QΣ(Vshape·C) 范围及源位置记录于 JSON。可复用这些源文件，活动通量不变，单元浓度增量因体积变小而增加。 |
| 面积/体积缓存、浓度增量式源项、积分边界输运、总库存/衰变损失/守恒报告 | 使用 pm/pn 的派生量必须按新网格重算。现有 `audit_online_profile.py`、`case_tools/fdnpp/validate_online_7d.py`、`compare_decay_vs_nodecay.py` 从输出 pm/pn 重建体积，须在新结果上重新执行。当前输入清单中未发现需重写的面积/体积字段。 |
| 已有 history/restart、spinup 状态 | 不覆盖旧结果，不把旧动力轨迹/守恒报告视为新网格结果；隔离对照从相同初始点值起步。切换指标后延续旧 restart 的物理库存会改变，须另行建立转换和预算核查，不能作为无缝续算。 |

复用结论限于当前已检查的生成路径和输入；自定义或后续新增面积归一化源项、面积依赖 nudging/sponge 产品仍需独立检查。本次没有重新生成地形、掩膜、初始场或任何强迫。

## 自动测试与静态兼容性

`python3 -m unittest discover -s Data_pre/tests -v`：13/13 通过（8 个新增度量测试、5 个现有潮汐测试）。覆盖赤道、37°N、35.7°N、49.7°N、5–70° 纬度范围，边缘和非均匀间距、非零 dndx 的扭曲坐标差分，2×2 最小维度，lm+2 回归，理论零 dndx/非零 dmde，float32 和 NetCDF3/4 存储，打包科学变量、fill 值、组、元数据保全，以及新建/修复结果逐位一致、dry-run、覆盖和 Cartesian 拒绝。

`python3 -m py_compile $(find Data_pre ROMS_Build ROMS_Run -path '*/__pycache__' -prune -o -name '*.py' -print)` 与 `git diff --check` 均通过。

三例 `validate_staged_data.py`、`validate_roms_ready_inputs.py`、`show_build_plan.py --case-name CASE` 均退出 0。`validate_run_prereqs.py --case-name CASE --mode pilot_1day`：WOLSONG 退出 0；FDNPP 退出 1（缺 default pilot 可执行文件与 pilot 专用输入）；LAHAGUE 退出 1（缺 pilot 专用初始、边界、气象、辐射、river、潮汐文件）。这些是本次未更改的 pilot 路径现状，连续 formal 输入验证已通过；未生成兼容别名绕过检查。全部日志在各案例审计输出目录。

## 后续最小数值对照方案（尚未执行）

1. 经确认后为每例准备隔离的 1 天输入、输出及独立二进制目录，使用相同冷启动 ini 和已验证可复用的强迫。FDNPP 通过 ROMS_Build 新编译；补齐实际 pilot 时间片/路径，避免使用历史 FDNPP binary。56 ranks 与 7×8 tiles 保持一致，在 sandbox 外启动 MPI。
2. A 使用原网格和现有 CPP；B 使用修复样本、相同 CPP。只改 GRDNAME 和独立输出路径。记录 dt/dtfast、最大重力波及平流 CFL、极值、wet/land 行为、边界体积输运、源 Q·C、I(t)=Σ(C·Hz/(pm·pn))。量化度量变化本身的影响，不要求 A/B 场完全一致。
3. C 使用修复网格与隔离的 CURVGRID 变体，重新编译；对照 B/C 检查曲率项。构建日志必须显示 CURVGRID 和 UV_ADV。确认 dndx 接近零、dmde 按新字段实际读入，angle 仍符合规则经纬度方向。
4. 先做零源或均匀保守示踪物，再做实际源；各自用本次网格的面积/体积计算库存，闭合源输入、净边界通量、衰变及储量变化。对需要估计的积分项提高输出频率，并用半 dt 或更密输出核对闭合残差是否收敛，而非把 A/B 库存差直接判为不守恒。无 BLOWUP、CFL 有裕度且预算可靠后，才扩展至 7 天验证潮汐与扩散响应。
5. 审核上述结果并得到用户确认，才切换正式活动网格或 CPP；不直接推进一年期模拟。
