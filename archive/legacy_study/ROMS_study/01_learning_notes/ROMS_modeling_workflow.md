# ROMS 建模流程学习笔记

目标：把 ROMS project 拆成可审计、可复现、可写入论文方法的步骤。

## 1. 模型角色区分

| 组成 | 角色 | 当前来源 |
| --- | --- | --- |
| ROMS 主模式 | 求解海洋动力、温盐、示踪剂等方程，实际运行数值模拟 | `lhy-desktop:/home/lhy/ROMS/roms_src/roms` |
| 工作 case | 编译配置、CPP 选项、输入 namelist、输出文件 | `lhy-desktop:/home/lhy/ROMS/roms_work` |
| `my_roms_tools` | MATLAB 前处理/后处理工具 | `https://github.com/f-shake/my_roms_tools` |
| 论文方法 | 从真实配置和数据来源抽象出的可发表描述 | 本目录 `05_paper_methods/` |

## 2. 最小可复现链条

1. 定义研究目标：水动力、污染物扩散、示踪剂、漂浮子或源解析。
2. 建立网格：水平范围、分辨率、海陆掩膜、地形、垂向 sigma 层。
3. 准备初始场：温度、盐度、流速、海面高度，必要时包括生态变量或被动示踪剂。
4. 准备边界和气候态：开边界条件、HYCOM/CMEMS 等外部海洋资料插值。
5. 准备外部强迫：气象、辐射、潮汐、河流、点源或源项。
6. 配置 ROMS：CPP 选项、`*.in` 输入文件、并行划分、输出频率。
7. 编译和运行：记录源码版本、编译器、MPI、NetCDF/HDF5、编译脚本、运行命令。
8. 检查输出：历史场、平均场、诊断场、重启文件，核对维度、变量、时间轴。
9. 后处理和验证：流速统一、剖面、平面图、时间序列、模型-观测评价指标。
10. 方法写作：把数据来源、参数、边界条件、验证指标和限制写清楚。

## 3. 网格与地形

需要记录：

| 项目 | 内容 |
| --- | --- |
| 水平范围 | 经度/纬度或投影坐标范围 |
| 分辨率 | `Lm`, `Mm` 或网格间距 |
| 垂向层 | `N`, `theta_s`, `theta_b`, `Tcline`, `Vtransform`, `Vstretching` |
| 地形来源 | ETOPO/SRTM15/本地测深等 |
| 海陆掩膜 | 数据来源、人工修正方法、GridBuilder 或脚本 |
| 坐标点 | rho/u/v/psi 点维度关系 |

`my_roms_tools` 对应模块：`my_tools_core/roms_grid`。

## 4. 初始场、边界场、气候态

常见输入变量：

- 海表高度：`zeta` 或外部资料中的 `zos`/`surf_el`
- 三维流速：`u`, `v`
- 温度：`temp`/`thetao`
- 盐度：`salt`/`so`
- 可选生物或被动示踪剂变量

`my_roms_tools` 对应模块：`my_tools_core/roms_clm_bdy_ini`。

重点函数：

- `roms_create_clm_bdy_ini`
- `create_clm_nc`
- `create_bdy`
- `create_single_clm`
- `merge_clms`
- `rotate_uv`

论文中需要写清楚外部海洋资料来源、时间分辨率、空间范围、插值方法、边界条件类型和 nudging 设置。

## 5. 大气、潮汐和河流强迫

| 强迫 | 对应工具 | 需要记录 |
| --- | --- | --- |
| NCEP FNL | `roms_create_force_NCEP` | 时间分辨率、变量、下载来源、插值范围 |
| ERA5 辐射 | `roms_create_force_radiation_ERA5` | 短波/长波辐射、时间处理 |
| TPX/TPXO9 | `roms_create_tides_tpx`, `roms_create_tides_tpxo9` | 分潮、潮位/潮流、模拟时长 |
| 河流/点源 | `roms_create_rivers_core` | 位置、方向、流量、温盐、示踪剂浓度、垂向分配 |

后续如果做氚或污染物扩散，河流/点源和被动示踪剂配置会成为核心。

## 6. 被动示踪剂、漂浮子和污染物扩散

`my_roms_tools` 相关模块：

- `roms_tracer`：向初始场、边界场、气候态文件添加示踪剂。
- `roms_river`：制作包含流量和示踪剂浓度的河流/点源文件。
- `roms_floats`：创建漂浮子文件、释放策略和轨迹分析。
- `my_tools_project/hzw`：污染物扩散、溯源、水交换案例参考。

需要特别区分：

| 内容 | 说明 |
| --- | --- |
| 被动示踪剂 | 代表物质浓度或标记水团，是否衰减取决于 ROMS 配置和源项处理 |
| 漂浮子 | 粒子轨迹工具，适合路径、停留、贡献分析 |
| 污染物反应 | 若存在降解、沉降、交换或化学反应，需要额外模型假设 |
| 氚 | 需要明确 HTO、HT、OBT 或其他形态；海洋中通常要说明水相示踪、交换和衰变假设 |

## 7. 输出与验证

远端 `UPWELLING` case 已有输出：

| 文件 | 类型 | 当前大小 |
| --- | --- | --- |
| `roms_his.nc` | history file | 16 MB |
| `roms_avg.nc` | averages file | 44 MB |
| `roms_dia.nc` | diagnostics file | 80 MB |
| `roms_rst.nc` | restart file | 4.8 MB |

`roms_his.nc` 头信息显示：

- 维度：`xi_rho=43`, `eta_rho=82`, `s_rho=16`, `s_w=17`, `tracer=2`, `ocean_time=10`
- 变量包括：`zeta`, `ubar`, `vbar`, `u`, `v`, `w`, `omega`, `temp`, `salt`, `rho`
- 全局属性记录了 `git_url`, `git_rev`, `code_dir`, `header_file`, `compiler_command`, `CPP_options`

这说明 ROMS 输出文件本身包含大量可复现元数据。后续论文 project 应固定保存这些 NetCDF 全局属性。

