# my_roms_tools 来源与模块清单

核验日期：2026-06-24

## 来源

- GitHub：`https://github.com/f-shake/my_roms_tools`
- 本地只读快照：`/private/tmp/my_roms_tools`
- 当前核验 commit：`7b94657341d25ea7d975093c71780b267a36a6f4`
- README 定位：基于 MATLAB 的 ROMS 区域海洋模式预处理、后处理工具包。
- 许可和使用限制：README 写明公开代码可用于学习、科研等，不能商业使用、不能盈利。若使用作者修改的 `my_tools_` 目录产出成果，可考虑 Star 或按学术严谨性引用相关论文。

## 软件依赖

README 中列出的依赖：

| 软件 | 版本/组件 |
| --- | --- |
| MATLAB | R2019b+ |
| MATLAB toolboxes | Image Processing, Mapping, Optimization, Parallel Computing, Statistics and Machine Learning, Symbolic Math |
| Python | 3.5+ |
| Python package | `requests` |

## 顶层目录

| 目录 | 来源/性质 | 用途 |
| --- | --- | --- |
| `inwave_tools` | COAWST 工具 | inwave 模式工具 |
| `m_map` | 地图工具 | 地图绘制 |
| `mtools` | COAWST/ROMS 工具 | ROMS 网格、NC 文件、SCRIP、WRF 网格转换 |
| `roms_clm` | COAWST 工具 | 创建边界、初始、气候文件；主驱动 `roms_master_climatology_coawst_mw.m` |
| `rutgers` | Rutgers 工具 | 水深、边界、海岸线、强迫、网格、陆地掩膜、NetCDF、海水和实用函数 |
| `swan_forc` | SWAN/WW3 工具 | 读取 WW3 Grib2 并创建 SWAN 边界 |
| `tides` | 潮汐工具 | 为 ROMS 创建潮汐强迫 |
| `nctoolbox` | MATLAB NetCDF 工具 | 由 `add_paths.m` 注册 |
| `my_tools_core` | 作者核心工具 | ROMS 输入输出、插值、绘图、评价指标 |
| `my_tools_project` | 作者项目代码 | 污染物扩散、溯源、生态、水交换等案例参考 |

## `my_tools_core` 模块

| 模块 | 代表函数 | 学习重点 |
| --- | --- | --- |
| `roms_grid` | `roms_create_grid_core`, `roms_fill_grid_h_core`, `roms_get_grid_details`, `roms_get_volumes` | 网格、地形、rho/psi/u/v 点关系、体积计算 |
| `roms_clm_bdy_ini` | `roms_create_clm_bdy_ini`, `create_clm_nc`, `create_bdy`, `create_single_clm`, `merge_clms`, `rotate_uv` | 初始场、边界场、气候态文件，HYCOM/CMEMS 插值到 ROMS |
| `roms_atom` | `roms_create_force_NCEP`, `roms_add_radiations_NCEP`, `roms_create_force_radiation_ERA5` | 大气强迫，NCEP FNL 和 ERA5 辐射 |
| `roms_tides` | `roms_create_tides_tpx`, `roms_create_tides_tpxo9` | TPX/TPXO9 潮汐强迫 |
| `roms_river` | `roms_create_rivers_core` | 河流/点源输入文件 |
| `roms_tracer` | `roms_add_passive_tracer_core`, `roms_add_tracer_from_xyz`, `roms_get_dye` | 被动示踪剂、边界示踪剂、XYZ 到 sigma 坐标插值 |
| `roms_floats` | `roms_create_floats`, `roms_create_timely_floats`, `show_floats`, `floats_contribution` | 漂浮子释放、轨迹和贡献分析 |
| `roms_interpolate` | `interpolate_xyz_to_sigma`, `interpolate_z_to_sigma`, `fill_invalid_data`, `convert_rho_to_uv` | 正交网格或 z 层资料到 ROMS sigma 坐标 |
| `roms_output` | `roms_get_times`, `roms_unify_uv` | 输出时间读取、U/V 统一和流速计算 |
| `nc` | `nc_compact`, `nc_extract_variables`, `read_data`, `roms_add_variable_to_xyzt_nc` | NetCDF 变量读写、压缩、拆分 |
| `graph` | `draw_map`, `draw_profile`, `draw_time_series_maps`, `save_all_figures` | 论文图和诊断图 |
| `evaluation_metrics` | `get_ioa`, `get_r`, `get_mb` | 模型-观测评价指标 |

## `my_tools_project` 使用边界

README 对 `my_tools_project` 明确提示：最新项目代码丢失，该版本是不确定时间的备份，不同代码版本可能不一致，不能保证正确联调运行。因此本目录只作为案例学习来源，不作为直接复现的稳定 workflow。

可重点参考的项目思路：

| 子项目 | 可借鉴内容 |
| --- | --- |
| `hzw/diffuse` | 杭州湾污染物扩散、排放点、观测对比、年平均图 |
| `hzw/trace` | 虚拟排放点、源强估算、区域贡献 |
| `hzw/water_exchange` | 水交换示踪剂、半交换时间 |
| `hzw/hydrodynamics` | 水动力和潮汐验证 |
| `dh/input` | 东海生态项目输入文件、生物变量和河流 |
| `dh/compare` | SST、叶绿素等与再分析/遥感/Argo 对比 |

## 对论文 project 的意义

- `my_roms_tools` 适合作为“ROMS 前后处理工具箱”学习，不应和 ROMS 主模式源码混淆。
- 对后续氚/污染物海洋扩散 project，最相关的是 `roms_grid`、`roms_clm_bdy_ini`、`roms_atom`、`roms_tides`、`roms_river`、`roms_tracer`、`roms_output`、`evaluation_metrics`。
- 所有来自 `my_tools_project` 的做法都需要重新核对数据、路径和代码版本，不能直接写成已验证方法。

