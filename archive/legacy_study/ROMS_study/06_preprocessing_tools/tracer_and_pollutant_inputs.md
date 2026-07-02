# 示踪剂与污染物输入前处理

来源快照：`/private/tmp/my_roms_tools`  
核验 commit：`7b94657341d25ea7d975093c71780b267a36a6f4`  
核验日期：2026-06-24

## 目标

为 ROMS project 添加被动示踪剂、污染物或氚迁移相关输入。当前工具链支持两类路径：

1. 直接从 `roms.tracer.*` 配置数组写入初始场和边界场。
2. 从外部 XYZ NetCDF 数据插值到 ROMS sigma 网格，再写入 clm/bdy/ini。

## 入口函数

| 函数 | 源码路径 | 作用 |
| --- | --- | --- |
| `roms_add_passive_tracer_core` | `my_tools_core/roms_tracer/roms_add_passive_tracer_core.m` | 向 ini 和 bdy 文件添加 `dye_*` 被动示踪剂 |
| `roms_add_tracer_from_xyz` | `my_tools_core/roms_tracer/roms_add_tracer_from_xyz.m` | 从 XYZ NetCDF 插值并写入 clm/bdy/ini |
| `roms_add_tracer_to_bdy_nc` | `my_tools_core/roms_tracer/roms_add_tracer_to_bdy_nc.m` | 向 bdy 文件写入边界示踪剂 |
| `roms_add_tracer_to_clm_nc` | `my_tools_core/roms_tracer/roms_add_tracer_to_clm_nc.m` | 向 clm 或 ini 文件写入示踪剂变量 |
| `interpolate_xyz_to_sigma` | `my_tools_core/roms_interpolate/interpolate_xyz_to_sigma.m` | XYZ/z 层资料插值到 ROMS sigma 坐标 |

## 路径一：直接写入被动示踪剂

入口：

```matlab
roms_add_passive_tracer_core(roms, ini, bdy)
```

参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `roms` | 必填 | 配置结构体 |
| `ini` | `true` | 是否写入初始场 |
| `bdy` | `true` | 是否写入边界场 |

必备配置：

| 字段 | 含义 |
| --- | --- |
| `roms.input.initialization` | 初始场文件 |
| `roms.input.boundary` | 边界场文件 |
| `roms.tracer.count` | 示踪剂数量 |
| `roms.tracer.age` | 是否启用 age 变量 |
| `roms.tracer.densities{i}` | 第 i 个示踪剂初始浓度 |
| `roms.tracer.ages{i}` | 第 i 个示踪剂初始年龄 |
| `roms.tracer.times` | 边界示踪剂时间 |
| `roms.tracer.east/west/south/north{i}` | 四边界浓度 |
| `roms.tracer.east_age/...{i}` | 四边界年龄 |

生成变量：

| 文件 | 变量 |
| --- | --- |
| ini | `dye_01`, `dye_02`, ... |
| ini age | `dye_01_age`, ... |
| bdy | `dye_time`, `dye_east_01`, `dye_west_01`, `dye_south_01`, `dye_north_01` |
| bdy age | 源码按奇偶编号写浓度和年龄，例如 `dye_east_01`, `dye_east_02` |

单位：

- 浓度：`kilogram meter-3`
- 年龄：`second`
- 时间：`days`

## 路径二：从 XYZ NetCDF 插值写入

入口：

```matlab
roms_add_tracer_from_xyz(input, output, clm, bdy, ini, options)
```

输入结构字段：

| 字段 | 含义 |
| --- | --- |
| `input.inputFile` | 一个或多个 XYZ NetCDF 文件 |
| `input.xvar`, `input.yvar`, `input.zvar` | 输入经度、纬度、深度变量名 |
| `input.vvar` | 输入值变量名 |
| `input.times` | 输出时间，double days |
| `input.mag` | 倍数换算，默认 1 |
| `input.depthValueFunc` | 二维变量扩展成三维时的深度权重 |
| `input.dim` | 2 或 3 |

输出结构字段：

| 字段 | 含义 |
| --- | --- |
| `output.type` | `u`, `v`, `rho` 或空字符串，决定目标网格类型 |
| `output.units` | 输出单位 |

写入目标：

| 结构 | 关键字段 |
| --- | --- |
| `clm` | `clmFile`, `clmVarName`, `clmVarLongName`, `clmDimX/Y/Z` |
| `bdy` | `bdyFile`, `bdyVarName`, `bdyDimX/Y/Z` |
| `ini` | `iniFile`, `iniVarName`, `iniVarLongName`, `iniDimX/Y/Z` |

插值选项：

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| `options.roms_grid_info` | 自动读取 | ROMS 网格信息 |
| `options.interpolate_method` | `linear` | z 转 sigma 的垂向插值方法 |

## `interpolate_xyz_to_sigma` 逻辑

该函数支持：

- 2D 数据：水平插值到 `lon_rho/lat_rho`。
- 3D 数据：先逐层水平插值，再调用 `interpolate_z_to_sigma` 转到 ROMS sigma 坐标。
- `output_order="xyz"` 时输出为水平优先，便于写入 clm/bdy/ini。
- 水平插值后使用 `fill_invalid_data` 外推无效点。

常见用途：

- 将外部三维污染物浓度场插入初始场。
- 将外部生物/化学变量加入 clm/bdy。
- 将二维面源按 `depthValueFunc` 分配到垂向。

## 与河流/点源的关系

若污染物或氚从点源进入，优先使用 `roms_create_rivers_core` 写入：

- `river_transport`
- `river_temp`
- `river_salt`
- `river_dye_01...`

若污染物在开边界或初始场已有背景浓度，使用：

- `roms_add_passive_tracer_core`
- `roms_add_tracer_from_xyz`

## ROMS 编译和输入文件注意项

仅写入 NetCDF 变量不够，还需要 ROMS 编译和输入文件支持：

- CPP 选项中需要启用相应 passive tracer 或 dye 变量。
- `roms.in` 中 `NPT` 应与 passive tracer 数量匹配。
- 历史输出中要开启 `Hout(inert)` 或对应示踪剂输出。
- 若启用 mean age，需要 ROMS 端对应 age tracer 配置。

当前远端 `UPWELLING` case 的 `roms_upwelling.in` 中 `NPT = 0`，只是学习基线，不适合直接用于示踪剂 project。

## 检查项

```matlab
ncinfo(roms.input.initialization)
ncinfo(roms.input.boundary)
ncinfo(roms.input.climatology)
```

重点检查：

- `dye_*` 变量是否存在。
- `dye_time` 是否覆盖模拟时间。
- 边界变量维度是否为 `[boundary_width, s_rho, dye_time]`。
- 浓度单位是否与源项一致。
- 初始场和边界场的 tracer 数量是否与 ROMS `NPT` 一致。
- 是否有 NaN、负值或异常大值。

## 氚/污染物 project 的待定假设

正式写论文前必须明确：

| 问题 | 需要决定 |
| --- | --- |
| 物质形态 | HTO、HT、OBT 或一般被动污染物 |
| 单位 | Bq m-3、kg m-3 或 mol m-3 |
| 源项 | 点源、河流、边界背景、初始背景 |
| 时间变化 | 连续排放、脉冲排放、月/年变化 |
| 衰变 | 是否考虑放射性衰变 |
| 相互作用 | 是否考虑沉降、吸附、挥发、再悬浮 |
| 输出指标 | 浓度、通量、贡献率、停留时间、剂量接口 |

## 论文方法写法

可写：

> 被动示踪剂用于表征 `[待填：氚/污染物]` 在海洋中的输运过程。示踪剂初始浓度、开边界浓度和源项浓度分别由 `[待填数据来源]` 给定，并写入 ROMS 初始场、边界场和河流/点源强迫文件。若采用点源输入，源项文件同时包含流量、位置、垂向分配和示踪剂浓度时间序列。

不要写：

- “示踪剂等同于真实剂量”。
- 未说明单位和形态。
- 未说明是否考虑衰变或相互作用。

