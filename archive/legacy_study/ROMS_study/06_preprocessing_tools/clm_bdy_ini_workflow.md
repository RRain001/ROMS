# 初始场、边界场与气候态前处理

来源快照：`/private/tmp/my_roms_tools`  
核验 commit：`7b94657341d25ea7d975093c71780b267a36a6f4`  
核验日期：2026-06-24

## 目标

将外部海洋再分析或模式资料插值到 ROMS 网格，生成：

- 气候态文件：`roms_clm.nc`
- 边界文件：`roms_bdy.nc`
- 初始场文件：`roms_ini.nc`
- 初始场备份：`roms_ini_raw.nc`

## 入口函数

| 函数 | 源码路径 | 作用 |
| --- | --- | --- |
| `roms_create_clm_bdy_ini` | `my_tools_core/roms_clm_bdy_ini/roms_create_clm_bdy_ini.m` | 主入口：生成 clm、bdy、ini |
| `create_clm_nc` | `my_tools_core/roms_clm_bdy_ini/create_clm_nc.m` | 创建/写入单时刻或合并后的 clm NetCDF |
| `create_bdy` | `my_tools_core/roms_clm_bdy_ini/create_bdy.m` | 从 clm 文件四边切出边界文件 |
| `merge_clms` | `my_tools_core/roms_clm_bdy_ini/merge_clms.m` | 合并多个单时刻 clm 文件 |
| `rotate_uv` | `my_tools_core/roms_clm_bdy_ini/rotate_uv.m` | 将外部 U/V 旋转到 ROMS 网格方向 |

## 主函数参数

```matlab
roms_create_clm_bdy_ini(skip_existed, repeat_years, delete_clms, offset_days, clms_dir)
```

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `skip_existed` | `true` | 是否跳过已存在的单时刻 clm 文件 |
| `repeat_years` | `1` | 将已有一年资料重复到多年的年数 |
| `delete_clms` | `false` | 合并后是否删除单时刻 clm |
| `offset_days` | `0` | 读取数据源时间与写入 ROMS 时间的偏移 |
| `clms_dir` | `"clms"` | 单时刻 clm 文件目录 |

## 工作流

`roms_create_clm_bdy_ini` 的实际执行链：

1. 调用 `configs`。
2. 切到 `roms.project_dir`。
3. 调用 `roms_fix_h` 修正网格水深。
4. 根据 `roms.time.start`, `roms.time.stop`, `roms.res.hydrodynamics_step_time_hour` 生成时间序列。
5. 读取 ROMS 网格信息：`get_roms_grid_info(roms.input.grid)`。
6. 调用 `create_clms(...)` 生成单时刻 clm 文件。
7. 调用 `create_bdy(roms.input.climatology, roms.input.boundary, roms_grid_info)` 从合并 clm 生成边界。
8. 调用 `updatinit_coawst_mw(files(1), ..., roms.input.initialization, ...)` 用首个 clm 生成初始场。
9. 复制初始场为 `roms.input.initialization_raw`。

## 输入数据与配置

| 类型 | 字段/变量 | 说明 |
| --- | --- | --- |
| 网格 | `roms.input.grid` | 已完成水深和 mask 的 ROMS 网格 |
| 时间 | `roms.time.start`, `roms.time.stop` | 模拟起止时间 |
| 外部水文资料 | `roms.res.hydrodynamics` | HYCOM 或 CMEMS 数据目录 |
| 数据源类型 | `roms.res.hydrodynamics_type` | 当前配置支持 `HYCOM` 或 `CMEMS` |
| 时间步长 | `roms.res.hydrodynamics_step_time_hour` | 外部水文资料时间分辨率 |
| HYCOM 变量名 | `roms.res.hycom_*` | `lat/lon/depth/time/water_u/water_v/water_temp/salinity/surf_el` |
| CMEMS 变量名 | `roms.res.cmems_*` | `latitude/longitude/depth/time/uo/vo/thetao/so/zos` |

## 生成的 clm 变量

`create_clm_nc` 创建这些核心维度和变量：

| 类型 | 变量 |
| --- | --- |
| 时间 | `ocean_time`, `temp_time`, `salt_time`, `v2d_time`, `v3d_time`, `zeta_time` |
| 坐标 | `lon_rho`, `lat_rho` |
| 海表 | `zeta` |
| 温盐 | `temp`, `salt` |
| 三维流速 | `u`, `v` |
| 二维流速 | `ubar`, `vbar` |

单位：

- `zeta`: meter
- `temp`: C
- `salt`: psu
- `u/v/ubar/vbar`: meter second-1
- 时间：modified Julian day 风格的 days

## 生成的 bdy 变量

`create_bdy` 从 clm 四边生成：

| 变量组 | 边界变量 |
| --- | --- |
| 海表 | `zeta_east/west/south/north` |
| 二维流速 | `ubar_east/west/south/north`, `vbar_east/west/south/north` |
| 三维流速 | `u_east/west/south/north`, `v_east/west/south/north` |
| 温盐 | `temp_east/west/south/north`, `salt_east/west/south/north` |

维度规则：

- east/west 使用 `erho` 或 `eu/ev` 宽度。
- south/north 使用 `xrho` 或 `xu/xv` 宽度。
- 三维变量包含 `s_rho` 和对应时间维。

## ROMS `*.in` 对应字段

| 生成文件 | ROMS 输入字段 |
| --- | --- |
| `roms_clm.nc` | `CLMNAME` |
| `roms_bdy.nc` | `BRYNAME` |
| `roms_ini.nc` | `ININAME` |
| `roms_nud.nc` | `NUDNAME`，若使用 nudging |

同时还需要在 `*.in` 中开启对应开关，例如 `LsshCLM`, `Lm2CLM`, `Lm3CLM`, `LtracerCLM`, `Lnudge*` 等，具体取决于 ROMS case。

## 检查项

```matlab
ncinfo(roms.input.climatology)
ncinfo(roms.input.boundary)
ncinfo(roms.input.initialization)
```

重点检查：

- clm 和 bdy 时间维长度一致。
- `temp/salt/u/v/zeta` 没有 NaN 或异常常数填充值。
- `u/v` 已旋转到 ROMS 网格方向。
- `ubar/vbar` 与三维流速垂向积分关系合理。
- `roms_ini.nc` 使用的是期望的首个时刻。
- 外部资料时间轴与 `roms.time.base`、modified Julian day 处理一致。

## 常见失败点

| 问题 | 风险 |
| --- | --- |
| `repeat_years` 重复一年资料 | 可用于理想化或多年循环强迫，但不能当作真实多年变化 |
| `offset_days` 使用不当 | 会造成读入数据时间和写入 ROMS 时间错位 |
| HYCOM/CMEMS 变量名不匹配 | 脚本会读不到变量或读错变量 |
| 外部资料覆盖范围不足 | 边界或网格外缘可能出现 NaN |
| `rotate_uv` 未正确使用 | 流向与 ROMS 曲线网格不一致 |
| bdy 文件只从 clm 四边切出 | 边界物理质量取决于 clm 插值质量 |

## 论文方法写法

可写：

> 模型初始场和开边界条件由 `[待填：HYCOM/CMEMS]` 数据插值至 ROMS 网格生成，变量包括海表高度、三维流速、温度和盐度。外部资料按照 `[待填：时间分辨率]` 处理，并在边界文件中写入东西南北四侧的海表高度、流速、温度和盐度边界条件。

必须补充：

- 外部资料版本、下载时间和空间/时间分辨率。
- 插值方法、时间基准和边界条件类型。
- 是否使用 nudging。
- 是否做 spin-up。

