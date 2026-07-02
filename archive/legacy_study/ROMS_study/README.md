# ROMS 学习资料库

创建日期：2026-06-24

本目录用于记录 ROMS 学习、`my_roms_tools` 前后处理工具梳理、远端已编译 ROMS 环境审计，以及后续论文 project 的方法学材料。

## 当前资料源

| 来源 | 用途 | 当前状态 |
| --- | --- | --- |
| `https://github.com/f-shake/my_roms_tools` | MATLAB ROMS 预处理、后处理工具学习 | 已克隆只读快照，commit `7b94657341d25ea7d975093c71780b267a36a6f4` |
| `lhy-desktop:/home/lhy/ROMS/` | 已编译 ROMS 主程序和可运行基线 | 已通过 SSH 只读审计，主机名 `lhy-desktop` |
| `lhy-desktop:/home/lhy/ROMS/roms_src/roms` | ROMS 主模式源码 | 来源 `https://github.com/myroms/roms.git`，HEAD `133dc4786dc1549e3ce4f732737dfd437dd4030c` |
| `lhy-desktop:/home/lhy/ROMS/roms_work` | `UPWELLING` 测试 case、编译脚本、输出文件 | 已发现 `romsM`、`roms_upwelling.in`、`upwelling.h`、`roms_his.nc`、`roms_avg.nc`、`roms_dia.nc`、`roms_rst.nc` |

## 目录说明

| 目录 | 内容 |
| --- | --- |
| `00_source_inventory/` | 来源、版本、依赖、许可证、模块清单 |
| `01_learning_notes/` | ROMS 建模流程学习笔记 |
| `02_code_walkthrough/` | `my_roms_tools` 关键代码入口和参数表 |
| `03_remote_roms_env/` | 远端 ROMS 源码、编译和输出环境审计 |
| `04_project_templates/` | 后续 project 的数据、配置、运行和论文检查清单 |
| `05_paper_methods/` | 可发展为论文方法部分的中文草稿 |

## 关键结论

1. `my_roms_tools` 不是 ROMS 主模式源码，而是基于 MATLAB 的 ROMS 输入文件制作、输出分析和绘图工具包。它适合服务“数据准备、NetCDF 输入生成、结果后处理、图表和验证”。
2. 远端 `/home/lhy/ROMS/` 才是当前可运行的 ROMS 主程序基线。已编译的 `romsM` 是 Linux x86-64 ELF 可执行文件，工作 case 为 `UPWELLING`。
3. 当前远端 case 是 ROMS 标准上升流/下降流测试，不是论文 project 的实际研究区。后续正式 project 需要替换网格、初边界、气象/潮汐/河流强迫、示踪剂或污染物参数。
4. 远端非交互 SSH 环境没有自动加载 Intel oneAPI 运行环境；直接执行 `ifort` 失败，直接运行本地 `ncdump` 也会因 `libimf.so` 缺失失败。使用显式路径或补充 `LD_LIBRARY_PATH` 后可以读 NetCDF 头信息。

## 下一步建议

1. 先用远端 `UPWELLING` case 熟悉 ROMS 输入文件、CPP 选项、输出 NetCDF 结构。
2. 再用 `my_roms_tools` 梳理实际 project 所需的前处理链：网格、地形、水文初边界、气象、潮汐、河流、示踪剂。
3. 写论文前，把每个模型设置都绑定到可追溯来源：源码路径、配置行、输入数据文件、生成脚本、输出文件和验证指标。

