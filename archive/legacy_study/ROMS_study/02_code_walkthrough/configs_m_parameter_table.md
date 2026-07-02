# `configs.m` 参数表与代码入口

来源：`/private/tmp/my_roms_tools/configs.m`

核验日期：2026-06-24

## 入口函数

```matlab
function configs (river_count,tracer_count)
```

默认参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `river_count` | `1` | 河流/点源数量 |
| `tracer_count` | `1` | 被动示踪剂数量 |

函数最后使用：

```matlab
assignin('caller','roms',roms);
```

因此调用后会在调用者工作区生成 `roms` 配置结构体。

## 路径配置

| 字段 | 示例值 | 用途 | project 迁移时是否必须改 |
| --- | --- | --- | --- |
| `roms.project_dir` | `C:\Users\autod\Desktop\dhbio` | 预处理项目目录 | 是 |
| `roms.build_dir` | `C:\Users\autod\Desktop` | 模式运行目录 | 是 |

注意：当前示例是 Windows 路径。若在 macOS 或 Linux 使用，需要改成对应绝对路径，并注意路径分隔符。

## 时间配置

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.time.start` | `[2021,1,1,0,0,0]` | 模拟开始时间 |
| `roms.time.stop` | `[2022,1,1,0,0,0]` | 模拟结束时间 |
| `roms.time.base` | `[1858,11,17,0,0,0]` | 简化儒略日基准 |
| `roms.time.start_julian` | 由 `juliandate` 计算 | 开始时刻 modified Julian date |
| `roms.time.stop_julian` | 由 `juliandate` 计算 | 结束时刻 modified Julian date |
| `roms.time.days` | 由 stop-start 计算 | 总天数 |

论文记录时需要明确时间范围、时区、外部强迫资料的时间分辨率。

## 网格配置

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.grid.size` | `[300 300]` | 与 ROMS `in` 文件中的 `Lm`, `Mm` 对应 |
| `roms.grid.N` | `15` | 垂向层数 |
| `roms.grid.theta_s` | `8` | S 坐标 surface control |
| `roms.grid.theta_b` | `4` | S 坐标 bottom control |
| `roms.grid.Tcline` | `20` | 关键深度参数 |
| `roms.grid.Hmin` | `10` | 最小水深 |
| `roms.grid.Vtransform` | `2` | 垂向变换公式 |
| `roms.grid.Vstretching` | `4` | 垂向拉伸函数 |

## 输入文件

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.input.grid` | `roms_grid.nc` | 网格文件 |
| `roms.input.atom` | `roms_atom.nc` | 气象强迫文件 |
| `roms.input.atom_radiation` | `roms_rad.nc` | 辐射强迫文件 |
| `roms.input.climatology` | `roms_clm.nc` | 物理气候态文件 |
| `roms.input.climatology_biology` | `roms_clm_bio.nc` | 生物气候态文件 |
| `roms.input.initialization` | `roms_ini.nc` | 初始场 |
| `roms.input.initialization_raw` | `roms_ini_raw.nc` | 初始场备份 |
| `roms.input.boundary` | `roms_bdy.nc` | 物理边界场 |
| `roms.input.boundary_biology` | `roms_bdy_bio.nc` | 生物边界场 |
| `roms.input.tides` | `roms_tides.nc` | 潮汐强迫 |
| `roms.input.rivers` | `roms_rivers.nc` | 河流/点源文件 |
| `roms.input.nudgcoef` | `roms_nud.nc` | 气候态逼近系数 |

## 输出文件

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.output.hisotry` | `ocean_his.nc` | 历史输出文件。字段名疑似拼写为 `hisotry`，使用时需核对下游代码。 |
| `roms.output.floats` | `ocean_flt.nc` | 漂浮子输出文件 |

## 数据资源路径

### 气象

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.res.force_ncep_dir` | `data\fnl` | NCEP FNL 数据目录 |
| `roms.res.force_ncep_step` | `6` | FNL 时间分辨率，小时 |
| `roms.res.force_ncep_radiation_files` | Windows 通配路径 | NCEP DS083.3 辐射数据 |
| `roms.res.force_era5_radiation_file` | `data/era5.nc` | ERA5 辐射数据 |

### 潮汐

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.res.tpx_uv` | `data/tpx_uv.mat` | 潮汐水平运动 |
| `roms.res.tpx_h` | `data/tpx_h.mat` | 潮汐高度 |
| `roms.res.tpxo9` | `data/tpxo9` | TPXO9 目录 |
| `roms.res.tpxo9_days` | `365*10` | TPXO9 估计模拟时间 |

### 水动力

| 字段 | 示例值 | 含义 |
| --- | --- | --- |
| `roms.res.hydrodynamics` | `data\hycom` | HYCOM 或 CMEMS 数据目录 |
| `roms.res.hydrodynamics_type` | `HYCOM` | 数据源类型 |
| `roms.res.hydrodynamics_step_time_hour` | `3` | 时间分辨率，小时 |
| `roms.res.hycom_*` | `lat`, `lon`, `depth`, `time`, `water_u`, `water_v`, `water_temp`, `salinity`, `surf_el` | HYCOM 变量名映射 |
| `roms.res.cmems_*` | `latitude`, `longitude`, `depth`, `time`, `uo`, `vo`, `thetao`, `so`, `zos` | CMEMS 变量名映射 |

## 被动示踪剂

| 字段 | 含义 |
| --- | --- |
| `roms.tracer.count` | 示踪剂数量 |
| `roms.tracer.age` | 是否启用平均年龄，需要 ROMS 中对应 CPP 选项 |
| `roms.tracer.densities` | 初始示踪剂浓度，cell 数量等于示踪剂数 |
| `roms.tracer.ages` | 初始年龄 |
| `roms.tracer.times` | 示踪剂边界时间，示例为 `[0, roms.time.days]` |
| `roms.tracer.east/west/south/north` | 四个边界浓度 |
| `roms.tracer.east_age/west_age/south_age/north_age` | 四个边界年龄 |

代码按 `roms.grid.size(1)+2`, `roms.grid.size(2)+2`, `roms.grid.N` 初始化数组。迁移到实际 project 时必须核对这些维度和 ROMS 网格文件维度一致。

## 河流/点源

| 字段 | 含义 |
| --- | --- |
| `roms.rivers.count` | 河流数量 |
| `roms.rivers.direction` | 0 为 u 方向，1 为 v 方向，2 为 w 方向 |
| `roms.rivers.time` | 河流时间，示例从 0 到总天数 |
| `roms.rivers.location` | 每条河流的水平坐标 |
| `roms.rivers.transport` | 流量，示例维度为河流数 x 时间数 |
| `roms.rivers.v_shape` | 垂向流量分配，每条河流各层之和应为 1 |
| `roms.rivers.temp` | 河流水温 |
| `roms.rivers.salt` | 河流盐度 |
| `roms.rivers.dye` | 被动示踪剂浓度 |
| `roms.rivers.ages` | 被动示踪剂年龄 |

## `add_paths.m`

来源：`/private/tmp/my_roms_tools/add_paths.m`

功能：

```matlab
path=fileparts(mfilename('fullpath'));
addpath(genpath(path));
run(fullfile(path,'nctoolbox','setup_nctoolbox.m'));
clear path
```

含义：

- 将整个工具包递归加入 MATLAB path。
- 运行 `nctoolbox/setup_nctoolbox.m`。
- 后续使用前应先在 MATLAB 中运行 `add_paths`。

## 当前使用风险

1. 示例路径是 Windows，本地 macOS 和远端 Linux 都需要改路径。
2. `roms.output.hisotry` 拼写疑似错误，调用下游函数时应确认字段名。
3. `configs_check` 函数存在但默认被注释，不会自动验证配置。
4. `my_tools_project` 不能作为稳定联调代码，只能参考思路。
5. 真实论文 project 不能直接沿用示例 `grid.size`, `N`, `theta_s`, `theta_b`, `Tcline`，必须根据研究区和稳定性测试确定。

