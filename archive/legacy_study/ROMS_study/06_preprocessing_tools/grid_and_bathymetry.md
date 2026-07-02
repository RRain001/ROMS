# 网格与地形前处理

来源快照：`/private/tmp/my_roms_tools`  
核验 commit：`7b94657341d25ea7d975093c71780b267a36a6f4`  
核验日期：2026-06-24

## 目标

生成或修正 ROMS 网格文件，至少包含：

- 水平网格：`lon_rho`, `lat_rho`
- 海陆掩膜：`mask_rho`, `mask_u`, `mask_v`, `mask_psi`
- 水深：`h`
- 后续水文、强迫、潮汐、河流和示踪剂前处理所需的网格维度

## 入口函数

| 函数 | 源码路径 | 作用 |
| --- | --- | --- |
| `roms_create_grid_core` | `my_tools_core/roms_grid/roms_create_grid_core.m` | 根据经纬度范围和 DEM 创建 ROMS 网格，并写入 mask |
| `roms_fill_grid_h_core` | `my_tools_core/roms_grid/roms_fill_grid_h_core.m` | 将 DEM 插值到 ROMS 网格，写入 `h` |
| `roms_fix_h` | `my_tools_core/roms_grid/roms_fix_h.m` | 将小于 `Hmin` 的水深和陆地点水深修正为 `Hmin` |
| `roms_get_grid_details` | `my_tools_core/roms_grid/roms_get_grid_details.m` | 根据配置读取 DEM 子区并生成 ROMS 经纬度网格 |

## 必备配置

`configs.m` 当前默认写出了 `roms.grid.size`, `N`, `theta_s`, `theta_b`, `Tcline`, `Hmin`, `Vtransform`, `Vstretching`，但网格创建函数还需要这些字段：

| 字段 | 用途 |
| --- | --- |
| `roms.grid.longitude` | `[west, east]`，研究区经度范围 |
| `roms.grid.latitude` | `[south, north]`，研究区纬度范围 |
| `roms.res.elevation` | DEM NetCDF 文件 |
| `roms.res.elevation_longitude` | DEM 经度变量名 |
| `roms.res.elevation_latitude` | DEM 纬度变量名 |
| `roms.res.elevation_altitude` | DEM 高程变量名 |
| `roms.input.grid` | 输出 ROMS 网格文件名，示例为 `roms_grid.nc` |

这些字段不是 `configs.m` 当前示例的完整默认项，正式 project 必须补齐。

## 工作流

1. 配置研究区范围和 DEM 变量名。
2. 运行 `add_paths` 注册工具箱和 `nctoolbox`。
3. 在 MATLAB 中调用 `configs`，确认 `roms` 结构体字段完整。
4. 调用 `roms_create_grid_core`：
   - 读取 DEM 子区。
   - 按 `roms.grid.size` 生成 ROMS rho 网格。
   - 使用 `mat2roms_mw` 创建基础网格文件。
   - 根据 DEM 中 `alt < 0` 判断水体，并写入 `mask_rho/u/v/psi`。
   - 调用 `editmask(roms.input.grid,'f')` 进行交互式 mask 修正。
5. 调用 `roms_fill_grid_h_core`：
   - 将 DEM 高程取负得到水深。
   - 使用 `griddata` 插值到 `lon_rho/lat_rho`。
   - 对内部点做一次五点平滑。
   - 将小于 `roms.grid.Hmin` 和陆地点设为 `Hmin`。
   - 写入 `h`。
6. 必要时调用 `roms_fix_h` 再次保证水深下限。

## 生成文件

| 文件 | 来源字段 | 应包含变量 |
| --- | --- | --- |
| `roms_grid.nc` | `roms.input.grid` | `lon_rho`, `lat_rho`, `mask_rho`, `mask_u`, `mask_v`, `mask_psi`, `h` |

## NetCDF 检查项

运行后检查：

```matlab
ncinfo(roms.input.grid)
ncread(roms.input.grid,'lon_rho')
ncread(roms.input.grid,'lat_rho')
ncread(roms.input.grid,'mask_rho')
ncread(roms.input.grid,'h')
```

重点检查：

- `size(lon_rho)` 与 `roms.grid.size + 2` 是否一致。
- `mask_rho` 是否只包含 0/1。
- `h` 是否存在 NaN。
- `min(h(:)) >= roms.grid.Hmin`。
- 岸线附近 mask 是否符合研究区实际。

## 常见失败点

| 问题 | 原因 | 处理 |
| --- | --- | --- |
| 找不到 `roms.grid.longitude` 或 `roms.res.elevation` | `configs.m` 示例未完整配置这些字段 | 在 project 配置中补齐 |
| DEM 裁剪索引为空 | DEM 范围不覆盖研究区，或经纬度顺序不一致 | 先单独读 DEM 经纬度范围 |
| `!del temp.mat` 在 macOS/Linux 失败 | 源码使用 Windows `del` | 非 Windows 环境需要改为 `delete('temp.mat')` 或手动删除 |
| `editmask` 需要交互 | 该步骤可能打开 GUI | 无 GUI 环境应提前准备 mask 或跳过交互修正 |
| 水深过浅导致 ROMS 不稳定 | `Hmin`、平滑和岸线处理不足 | 需要做 bathymetry smoothing 和 CFL 检查 |

## 论文方法写法

可写：

> 模型水平网格基于研究区经纬度范围构建，地形数据由 `[待填 DEM 来源]` 插值至 ROMS rho 网格。海陆掩膜根据地形高程和岸线信息生成，并对近岸区域进行人工核查。水深小于最小水深阈值的格点被设定为 `[待填 Hmin] m`，以保证数值稳定性。

不要写：

- “自动生成的网格完全准确”。
- “地形处理无需人工核查”。
- 未说明 DEM 来源、分辨率、最小水深和平滑处理。

