# 远端 ROMS 环境审计

核验日期：2026-06-24

远端主机：`lhy-desktop`

SSH 配置：

- HostName：`192.168.1.100`
- User：`lhy`
- Port：`22`
- 认证：本机 SSH config 使用 `~/.ssh/id_ed25519`

## 网络和主机

| 检查 | 结果 |
| --- | --- |
| 本机 Wi-Fi 地址 | `10.181.226.203` |
| `ping 192.168.1.100` | 2/2 成功，0% 丢包，约 4.5-5.8 ms |
| `ssh hostname` | `lhy-desktop` |
| `ssh pwd` | `/home/lhy` |
| `uname -a` | Linux `6.8.0-106-generic`, Ubuntu 22.04 系列内核，x86_64 |

## 目录结构

根目录：`/home/lhy/ROMS`

```text
/home/lhy/ROMS
├── roms_src
│   └── roms
└── roms_work
    └── Build_romsM
```

`/home/lhy/ROMS/roms_work` 主要文件：

| 文件 | 大小 | 用途 |
| --- | ---: | --- |
| `build_roms.sh` | 7.4 KB | 当前编译脚本 |
| `build_roms.sh.backup.20260205_170351` | 17 KB | 编译脚本备份 |
| `my_local_paths.sh` | 1.1 KB | 本地 MPI/NetCDF/HDF5 路径设置 |
| `upwelling.h` | 1.8 KB | `UPWELLING` case CPP 选项 |
| `roms_upwelling.in` | 171 KB | ROMS 标准输入文件 |
| `varinfo.yaml` | 373 KB | 变量元数据 |
| `romsM` | 7.5 MB | 已编译 MPI 可执行文件 |
| `roms_his.nc` | 16 MB | 历史输出 |
| `roms_avg.nc` | 44 MB | 平均输出 |
| `roms_dia.nc` | 80 MB | 诊断输出 |
| `roms_rst.nc` | 4.8 MB | 重启输出 |

## ROMS 源码版本

| 项目 | 结果 |
| --- | --- |
| 源码目录 | `/home/lhy/ROMS/roms_src/roms` |
| Git remote | `https://github.com/myroms/roms.git` |
| Git HEAD | `133dc4786dc1549e3ce4f732737dfd437dd4030c` |
| Git 状态 | 有本地修改：`Compilers/my_build_paths.sh`, `makefile`; 未跟踪：`makefile.old` |

注意：源码不是干净工作树。后续若要把该环境作为论文可复现基线，需要保存这些本地修改的 diff 或归档整个源码快照。

## 编译配置

来源：`/home/lhy/ROMS/roms_work/build_roms.sh`

| 字段 | 值 |
| --- | --- |
| `ROMS_APPLICATION` | `UPWELLING` |
| `MY_ROOT_DIR` | `$HOME/ROMS/roms_src/roms` |
| `MY_PROJECT_DIR` | `$HOME/ROMS/roms_work` |
| `MY_ROMS_SRC` | `$HOME/ROMS/roms_src/roms` |
| `MY_HEADER_DIR` | `${MY_PROJECT_DIR}` |
| `MY_ANALYTICAL_DIR` | `${MY_PROJECT_DIR}` |
| `BINDIR` | `${MY_PROJECT_DIR}` |
| `BUILD_DIR` | `${MY_PROJECT_DIR}/Build_romsM` |
| `myBIN` | `${BINDIR}/romsM` |
| `USE_MPI` | `on` |
| `USE_MPIF90` | `on` |
| `which_MPI` | `intel` |
| `FORT` | `ifort` |
| `USE_LARGE` | `on` |
| `STATIC` | `on` |
| `EXEC` | `on` |
| `USE_NETCDF4` | `on` |
| `USE_PARALLEL_IO` | `on` |
| `NETCDF` | `$HOME/roms_build/install` |
| `HDF5` | `$NETCDF` |
| `MPI_ROOT` | `$HOME/intel/oneapi/mpi/2021.9.0` |

编译脚本支持：

- `-g`：调试编译
- `-j [N]`：并行 make
- `-pio`：启用 PIO
- `-noclean`：不清理已有对象
- `-p macro`：打印 makefile 宏

## 本地库路径配置

来源：`/home/lhy/ROMS/roms_work/my_local_paths.sh`

功能：

- 若设置 `MPI_ROOT`，把 `${MPI_ROOT}/bin` 加入 `PATH`，并设置 `MPI_INCDIR`。
- 若设置 `NETCDF`，设置 `NC_CONFIG`, `NF_CONFIG`, `NETCDF_INCDIR`, `NETCDF_LIBDIR`, `NETCDF4=1`。
- 若设置 `HDF5`，设置 `HDF5_INCDIR`, `HDF5_LIBDIR`。

## 编译器和库版本

| 项目 | 核验结果 |
| --- | --- |
| `ifort` 绝对路径 | `/home/lhy/intel/oneapi/compiler/2023.1.0/linux/bin/intel64/ifort` |
| `ifort --version` | `ifort (IFORT) 2021.9.0 20230302` |
| Intel MPI 路径 | `/home/lhy/intel/oneapi/mpi/2021.9.0` |
| `mpif90 --version` 非交互默认 | GNU Fortran 4.7.4 |
| NetCDF C | `netCDF 4.8.0` |
| NetCDF Fortran | `netCDF-Fortran 4.5.3` |
| Intel runtime | `libimf.so` 位于 `/home/lhy/intel/oneapi/compiler/2023.1.0/linux/compiler/lib/intel64_lin/` |

风险：非交互 SSH 环境中直接执行 `ifort --version` 返回“未找到命令”；直接运行 `/home/lhy/roms_build/install/bin/ncdump` 会报 `libimf.so` 缺失。需要显式加载 oneAPI 环境或设置 `PATH`/`LD_LIBRARY_PATH`。

可用的只读 NetCDF 头查看方式：

```bash
ssh lhy-desktop env LD_LIBRARY_PATH=/home/lhy/intel/oneapi/compiler/2023.1.0/linux/compiler/lib/intel64_lin \
  /home/lhy/roms_build/install/bin/ncdump -h /home/lhy/ROMS/roms_work/roms_his.nc
```

## 可执行文件

`/home/lhy/ROMS/roms_work/romsM`

| 属性 | 值 |
| --- | --- |
| 类型 | ELF 64-bit LSB executable, x86-64 |
| 链接 | dynamically linked |
| BuildID | `58f79925ebd8564c54bf0bdb1256c46ec310ee80` |
| 权限 | `0775/-rwxrwxr-x` |
| 大小 | `7,765,576` bytes |
| 修改时间 | `2026-02-05 17:30:21 +0800` |

未执行 `romsM`，因为即使无参数也可能启动模拟或写日志；当前审计保持只读。

## 当前 case：UPWELLING

来源文件：

- CPP 选项：`/home/lhy/ROMS/roms_work/upwelling.h`
- 输入文件：`/home/lhy/ROMS/roms_work/roms_upwelling.in`

`upwelling.h` 关键选项：

- 动力：`UV_ADV`, `UV_COR`, `UV_LDRAG`, `UV_VIS2`
- 三维：`SOLVE3D`
- 温盐：`SALINITY`, `TS_DIF2`
- 输出：`AVERAGES`, `DIAGNOSTICS_TS`, `DIAGNOSTICS_UV`
- 解析场：`ANA_GRID`, `ANA_INITIAL`, `ANA_SMFLUX`, `ANA_STFLUX`, `ANA_SSFLUX`, `ANA_BTFLUX`, `ANA_BSFLUX`, `ANA_VMIX`

`roms_upwelling.in` 关键参数：

| 参数 | 值 |
| --- | --- |
| `TITLE` | Wind-Driven Upwelling/Downwelling over a Periodic Channel |
| `MyAppCPP` | `UPWELLING` |
| `VARNAME` | `varinfo.yaml` |
| `Ngrids` | `1` |
| `Lm` | `41` |
| `Mm` | `80` |
| `N` | `16` |
| `NAT` | `2` |
| `NPT` | `0` |
| `NtileI` | `2` |
| `NtileJ` | `2` |
| `NTIMES` | `1440` |
| `DT` | `300.0d0` seconds |
| `NDTFAST` | `30` |
| `NHIS` | `72` |
| `NAVG` | `72` |
| `NDIA` | `72` |
| `RSTNAME` | `roms_rst.nc` |
| `HISNAME` | `roms_his.nc` |
| `AVGNAME` | `roms_avg.nc` |
| `DIANAME` | `roms_dia.nc` |

解释：`NTIMES=1440` 且 `DT=300 s`，总模拟时间为 `432000 s`，即 5 天。`NHIS/NAVG/NDIA=72`，输出间隔为 `72*300 s = 21600 s`，即 6 小时。

## 输出 NetCDF 审计

`roms_his.nc` 头信息：

| 内容 | 结果 |
| --- | --- |
| 格式 | `netCDF-3 64bit offset file` |
| Conventions | `CF-1.4, SGRID-0.3` |
| 类型 | `ROMS history file` |
| `ocean_time` | 10 records |
| 维度 | `xi_rho=43`, `eta_rho=82`, `s_rho=16`, `s_w=17`, `tracer=2` |
| 变量示例 | `zeta`, `ubar`, `vbar`, `u`, `v`, `w`, `omega`, `temp`, `salt`, `rho` |
| 输出元数据 | 包含 `git_url`, `git_rev`, `code_dir`, `header_file`, `compiler_command`, `compiler_flags`, `CPP_options` |

`roms_avg.nc` 头信息：

| 内容 | 结果 |
| --- | --- |
| 类型 | `ROMS nonlinear model averages file` |
| `ocean_time` | 9 records |
| 平均变量示例 | `zeta`, `ubar`, `vbar`, `u`, `v`, `omega`, `w`, `temp`, `salt`, `rho`, `Huon`, `Hvom`, `temp_2`, `salt_2` |

## 对后续 project 的启示

1. 远端环境已经能编译并产出标准 ROMS case，适合作为学习基线。
2. 当前 case 使用解析网格、解析初始场和解析强迫，不代表真实海域模拟；正式 project 需要接入真实网格、地形、边界、气象、潮汐和源项。
3. NetCDF 输出全局属性能自动记录源码版本、编译器、CPP 选项和输入脚本，应纳入论文可复现证据。
4. 正式运行前需要写一个环境加载脚本，确保 `ifort`、Intel MPI、NetCDF/HDF5 和 Intel runtime 在非交互 SSH 下也可用。

