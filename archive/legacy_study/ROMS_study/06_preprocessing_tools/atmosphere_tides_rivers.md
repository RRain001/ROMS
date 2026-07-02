# 大气、潮汐与河流/点源前处理

来源快照：`/private/tmp/my_roms_tools`  
核验 commit：`7b94657341d25ea7d975093c71780b267a36a6f4`  
核验日期：2026-06-24

## 目标

为 ROMS 生成外部强迫文件：

- 大气 bulk forcing：风、气压、气温、湿度、降水。
- 辐射 forcing：短波、长波、下行长波。
- 潮汐 forcing：分潮振幅、相位和潮流椭圆参数。
- 河流/点源 forcing：流量、温盐、示踪剂浓度。

注意：海水温度、盐度和洋流不是“大气强迫”。它们通常由 `roms_clm.nc`、`roms_bdy.nc`、`roms_ini.nc` 提供，属于水文初始场和开边界条件。实际 project 中需要同时准备大气强迫和海洋初边界，不能只准备气象数据。

## 入口函数

| 模块 | 函数 | 源码路径 |
| --- | --- | --- |
| NCEP FNL 大气 | `roms_create_force_NCEP` | `my_tools_core/roms_atom/roms_create_force_NCEP.m` |
| ERA5 辐射 | `roms_create_force_radiation_ERA5` | `my_tools_core/roms_atom/roms_create_force_radiation_ERA5.m` |
| TPXO9 潮汐 | `roms_create_tides_tpxo9` | `my_tools_core/roms_tides/roms_create_tides_tpxo9.m` |
| 河流/点源 | `roms_create_rivers_core` | `my_tools_core/roms_river/roms_create_rivers_core.m` |

## NCEP FNL 大气强迫

入口：

```matlab
roms_create_force_NCEP(repeat_years)
```

必备配置：

| 字段 | 用途 |
| --- | --- |
| `roms.input.atom` | 输出强迫文件名，示例 `roms_atom.nc` |
| `roms.res.force_ncep_dir` | FNL grib2 文件目录 |
| `roms.res.force_ncep_step` | 时间步长，单位小时 |
| `roms.time.start/stop/base` | 生成时间轴 |
| `roms.input.grid` | 用于确定裁剪范围 |

脚本读取的 FNL 变量：

| 输出变量 | 输入变量 | 单位处理 |
| --- | --- | --- |
| `Tair` | `Temperature_height_above_ground` | K 转 Celsius |
| `Pair` | `Pressure_surface` | Pa 乘 0.01 转 millibar |
| `Qair` | `Relative_humidity_height_above_ground` | 百分比 |
| `Uwind` | `U-component_of_wind_height_above_ground` | meter second-1 |
| `Vwind` | `V-component_of_wind_height_above_ground` | meter second-1 |
| `rain` | 脚本内置 | 当前全部置 0 |

输出 NetCDF：

- 维度：`xr`, `er`, `time`
- 坐标：`lon`, `lat`
- 变量：`Uwind`, `Vwind`, `Pair`, `Tair`, `Qair`, `rain`

注意：文件名模式写死为 `fnl_yyyymmdd_HH_MM.grib2`。

## ERA5 辐射强迫

入口：

```matlab
roms_create_force_radiation_ERA5
```

必备配置：

| 字段 | 用途 |
| --- | --- |
| `roms.input.atom_radiation` | 输出文件名，示例 `roms_rad.nc` |
| `roms.res.force_era5_radiation_file` | ERA5 NetCDF 文件 |
| `roms.input.grid` | 裁剪范围 |
| `roms.time.start/stop/base` | 时间裁剪和 ROMS 时间轴 |

脚本读取：

| 输出变量 | ERA5 变量 | 处理 |
| --- | --- | --- |
| `swrad` | `ssr` | 除以 3600，负值置 0 |
| `lwrad` | `str` | 除以 3600，负值置 0 |
| `lwrad_down` | `strd` | 除以 3600，负值置 0，写入时取负号 |

输出 NetCDF：

- 维度：`xr`, `er`, `time`
- 坐标：`lon`, `lat`
- 变量：`swrad`, `lwrad`, `lwrad_down`

## TPXO9 潮汐强迫

入口：

```matlab
roms_create_tides_tpxo9(start_time, grid_file, tpxo9_dir, tpxo9_days, output_file)
```

参数：

| 参数 | 含义 |
| --- | --- |
| `start_time` | `[yyyy,mm,dd,HH,MM,SS]` |
| `grid_file` | ROMS 网格文件 |
| `tpxo9_dir` | TPXO9 atlas 目录 |
| `tpxo9_days` | 估计模拟天数 |
| `output_file` | 输出潮汐 NetCDF |

默认分潮列表：

```text
MM, MF, Q1, O1, P1, K1, S1, N2, M2, S2, K2, 2N2, MN4, M4, MS4
```

依赖的 TPXO9 文件名包括：

- `grid_tpxo9_atlas_30_v5.nc`
- `h_*_tpxo9_atlas_30_v5.nc`
- 对应潮流文件由内部 `TPXO9v5_ROMS` 使用

ROMS `*.in` 对应：

- `TIDENAME`
- 若使用 `TIME_REF=-2`，需关注脚本注释里的 `TIDE_START`。

## 河流/点源强迫

入口：

```matlab
roms_create_rivers_core(roms, from1)
```

参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `roms` | 必填 | 配置结构体 |
| `from1` | `false` | 若输入位置从 1 开始，则写入时减 1 |

必备配置：

| 字段 | 含义 |
| --- | --- |
| `roms.input.rivers` | 输出河流文件 |
| `roms.input.grid` | 网格文件路径，写入全局属性 |
| `roms.grid.N` | 垂向层数 |
| `roms.grid.size` | 网格范围，用于 position valid_max |
| `roms.rivers.count` | 河流/点源数量 |
| `roms.rivers.time` | 河流时间 |
| `roms.rivers.location` | `[X, E]` 网格位置 |
| `roms.rivers.direction` | 0 为 u，1 为 v，2 为 w |
| `roms.rivers.v_shape` | 垂向分配 |
| `roms.rivers.transport` | m3 s-1 |
| `roms.rivers.temp` | Celsius |
| `roms.rivers.salt` | 盐度 |
| `roms.rivers.dye` | 示踪剂浓度 |
| `roms.rivers.ages` | 示踪剂年龄，若启用 age |

输出变量：

| 变量 | 含义 |
| --- | --- |
| `river_time` | runoff time，写入 `roms.rivers.time + roms.time.start_julian` |
| `river` | 河流编号 |
| `river_Xposition`, `river_Eposition` | 网格位置 |
| `river_direction` | 输入方向 |
| `river_Vshape` | 垂向分配 |
| `river_transport` | 体积流量 |
| `river_temp`, `river_salt` | 温盐 |
| `river_dye_01...` | 被动示踪剂浓度或年龄 |

## ROMS `*.in` 对应字段

| 生成文件 | ROMS 输入字段 |
| --- | --- |
| `roms_atom.nc` | `FRCNAME` 中的风、气压、气温、湿度、降水文件 |
| `roms_rad.nc` | `FRCNAME` 中的辐射文件 |
| `roms_tides.nc` | `TIDENAME` |
| `roms_rivers.nc` | `SSFNAME` 或 river/source 相关输入 |

具体字段名随 ROMS 版本和 CPP 选项变化；正式 project 应以当前 `roms_upwelling.in` 或新 project 输入文件为准。

## 检查项

```matlab
ncinfo(roms.input.atom)
ncinfo(roms.input.atom_radiation)
ncinfo(roms.input.tides)
ncinfo(roms.input.rivers)
```

重点检查：

- 大气和辐射文件时间轴覆盖模拟期。
- 风速、气压、气温、湿度没有异常填充值。
- 当前 NCEP 脚本 `rain(:)=0`，若降水重要必须替换真实降水。
- TPXO9 文件覆盖研究区，潮汐输出包含所需分潮。
- 河流位置落在水体格点，`river_Vshape` 每条河流垂向和为 1。
- 河流/点源示踪剂单位和 ROMS 变量单位一致。

## 气象与海洋数据边界

| 用户常说的数据 | ROMS 中的类别 | 典型变量 | 典型文件 |
| --- | --- | --- | --- |
| 风速、风向 | 大气强迫 | `Uwind`, `Vwind` | `roms_atom.nc` |
| 大气压 | 大气强迫 | `Pair` | `roms_atom.nc` |
| 气温、湿度 | 大气强迫 | `Tair`, `Qair` | `roms_atom.nc` |
| 短波、长波辐射 | 辐射强迫 | `swrad`, `lwrad`, `lwrad_down` | `roms_rad.nc` |
| 降水、蒸发 | 表面淡水通量/大气强迫 | `rain`, `EminusP` | `roms_atom.nc` 或单独 forcing |
| 海水温度 | 海洋初边界 | `temp` | `roms_ini.nc`, `roms_bdy.nc`, `roms_clm.nc` |
| 海水盐度 | 海洋初边界 | `salt` | `roms_ini.nc`, `roms_bdy.nc`, `roms_clm.nc` |
| 洋流 | 海洋初边界 | `u`, `v`, `ubar`, `vbar` | `roms_ini.nc`, `roms_bdy.nc`, `roms_clm.nc` |
| 海面高度 | 海洋初边界/潮位 | `zeta`, tidal elevation | `roms_ini.nc`, `roms_bdy.nc`, `roms_tides.nc` |

第一阶段可接受的简化是“先用 500 m 或 250 m 网格 + 完整外部强迫”。不建议在缺少真实温盐流场、气象强迫和潮汐时直接追求 50 m 分辨率。

## 论文方法写法

可写：

> 大气强迫包括近地面风场、海平面气压、气温和相对湿度，来源为 `[待填：NCEP FNL/ERA5]`，并插值/裁剪至覆盖 ROMS 研究区域的规则网格。潮汐边界由 TPXO9 分潮资料生成，包含主要半日潮、全日潮和长周期分潮。河流或点源输入通过 ROMS river/source 文件给定，包含位置、方向、流量、温盐和示踪剂浓度时间序列。

必须补充：

- 数据版本、下载日期、时间分辨率。
- 降水是否真实输入；若使用当前脚本默认值，必须说明未考虑降水。
- 河流/点源的坐标、流量和浓度来源。
- 潮汐分潮列表和 `TIDE_START/TIME_REF` 设置。
