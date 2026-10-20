# JAPAN_SEA ES3K：存储布局与并行配置

- 日期：2026-10-19
- 分支：`codex/es3k-i3-wet-domain-audit-20261014`（PR #3，Draft）
- 适用：JAPAN_SEA 案例（`ROMS_Nesting/projects/JAPAN_SEA`）

## 一、并行配置：对齐 FDNPP

用户要求与 FDNPP 保持一致。FDNPP 的实测值（`/home/lhy/ROMS/Data_pre/cases/FDNPP/config/roms_run_config.json` 与 `AGENTS.md`）：

| 参数 | FDNPP | JAPAN_SEA（本次调整后） |
|---|---|---|
| MPI ranks `np` | **56** | **56** |
| `NtileI` | **7** | **7** |
| `NtileJ` | **8** | **8** |
| `NtileI*NtileJ` | 56 | 56 |

改动位置：

- `Data_pre/cases/JAPAN_SEA/config/project_parameters.json` → `run.ntile_i = 7`、`run.ntile_j = 8`
- `Data_pre/cases/JAPAN_SEA/config/roms_run_config.json` → `np = 56`
- 五个 `.in` 由 `prepare_external_test_case.py` 重新生成，全部为 `NtileI == 7` / `NtileJ == 8`

**验证**：

- 五模式 `validate_run_prereqs` 全部 `status: OK`，`required_np: 56`。
- np=56 的 Debug smoke 实际积分完成：`ROMS: DONE`，`WALL_SECONDS=172.75`（np=4 时同等 smoke 约 900 s，约 **5–6×** 加速）。
- 时间步表与 np=4 的运行**逐位一致**（KE/PE/TOTAL_ENRG/NET_VOLUME 打印位全同），说明 7×8 分解未改变物理结果。

**注意**：ES3K 网格为 732×464，`464/7 ≈ 66`、`732/8 = 91.5`，tile 尺寸非整除属正常，ROMS 允许余数 tile。

## 二、存储布局

### 设备

| 设备 | 型号 | 类型 | 挂载 | 容量 |
|---|---|---|---|---|
| `/dev/nvme0n1p2` | Samsung MZVL21T0HCLR 1TB | NVMe SSD（`rotational=0`） | `/` | 938 G |
| `/dev/sda2` | Seagate ST4000DM004 4TB | 机械硬盘（`rotational=1`） | `/workspace` | 3.6 T |

### 约定

**机械硬盘承载所有"大且冷"的数据** —— 前处理输入与计算结果：

```
/workspace/roms_cases/JAPAN_SEA/
├── data/      前处理原始与中间数据（ERA5/GLORYS 下载、TPXO 裁剪、staged 产品）
├── input/     ROMS-ready 强迫场（前处理产物，ROMS 直接读取）
└── output/    ROMS 计算结果（his / avg / dia / rst）
```

**SSD 只保留运行与代码所需的小文件**：

```
ROMS_Nesting/projects/JAPAN_SEA/
├── run/        .in 运行文件
├── logs/       运行日志、证据、provenance
├── bin/        ROMS 可执行文件
├── build/      编译中间产物
├── archive/    网格候选与审计产物
└── data, input, output  →  符号链接到机械盘
```

### 实现方式

三个大目录以**符号链接**指向机械盘：

```
projects/JAPAN_SEA/data   -> /workspace/roms_cases/JAPAN_SEA/data
projects/JAPAN_SEA/input  -> /workspace/roms_cases/JAPAN_SEA/input
projects/JAPAN_SEA/output -> /workspace/roms_cases/JAPAN_SEA/output
```

**为什么用符号链接而不是改绝对路径**：生成的 `.in` 中 `ININAME` / `BRYNAME` / `FRCNAME` / `TIDENAME`
以及 `HISNAME` / `RSTNAME` / `AVGNAME` / `DIANAME` 都写作 `../input/...`、`../output/...`（相对 `run/`）。
符号链接让这些既有引用原样可用，无需改动生成器，也不会因为路径写法不同而出现第二套真值。
物理位置只有一处，`readlink -f` 可随时查证。

### 迁移记录（2026-10-19）

迁移脚本：`/tmp/migrate_to_hdd.sh`。流程为 **rsync → 逐文件比对（路径+大小）→ 确认一致后才删 SSD 副本 → 建符号链接**；
任一步失败即中止并保留 SSD 副本。实际结果：

```
VERIFIED data   files=6
VERIFIED input  files=6
VERIFIED output files=12
MIGRATION_OK
```

迁移后 SSD 可用空间从 525 G 增至 **594 G**（`/` 使用率 42% → 34%）；
机械盘 `/workspace` 使用率 65% → 68%（`/workspace/roms_cases/JAPAN_SEA` 共 97 G）。

### 后续规则

1. 新的前处理数据与计算结果**一律**写入上述机械盘路径；不要写回 SSD 的案例目录。
2. 需要新增数据类目时，在 `/workspace/roms_cases/<CASE>/` 下新增子目录，并在案例目录建同名符号链接，不要在别处另起路径。
3. `run/`、`logs/`、`bin/`、`build/` 继续留在 SSD（体积小、读写频繁）。
4. 迁移或清理前，确认没有运行中的 ROMS 进程持有目标文件句柄。

### 其他案例（2026-10-20 一并迁移）

同一约定套用到 `/home/lhy/ROMS/projects/` 下的其余案例。脚本：`/tmp/migrate_case.sh`
（`migrate_case.sh <CASE_DIR> <HDD_BASE> <SUBDIR>...`），流程与 JAPAN_SEA 完全相同：
rsync → 逐文件比对（相对路径 + 大小）→ 一致后才删 SSD 副本 → 建符号链接。

| 案例 | 迁移的目录 | 校验结果 | 机械盘占用 |
|---|---|---|---|
| FDNPP | data, input, output, archive | input 28 / output 23 / archive 13 文件 | 27 G |
| LAHAGUE | data, input, output, archive | input 20 / output 27 / archive 108 文件 | 21 G |
| WOLSONG | data, input, output | data / input 21 / output 35 文件 | 21 G |
| WOLSONG_H3_4000BQL | input, output | input 2 / output 0 文件 | 284 K |
| JAPAN_SEA | data, input, output | data 6 / input 6 / output 12 文件 | 97 G |

`archive/` 一并迁移，因为它符合"大且冷"的判据（FDNPP 8.1 G、LAHAGUE 3.9 G），
且不属于运行期读写路径。若后续需要把 `archive/` 放回 SSD，删掉符号链接、
把目录拷回原处即可，无其它依赖。

**全局效果**：SSD 可用空间 525 G → **661 G**（使用率 42% → 26%）；
机械盘 `/workspace` 65% → 70%，`/workspace/roms_cases/` 合计 166 G。

## 三、对第二阶段验收的影响（需注意）

此前完成的 Phase 2 关卡（Debug smoke、Debug external_startup、Release external_1h、Release external_6h）
以及被中止的 24h 试验，**都是在 `np=4` / `2×2` 下跑的**；本次改为 `np=56` / `7×8` 后基线已重新冻结。

np=56 与 np=4 的 Debug smoke 时间步表逐位一致，说明分解方式不改变物理结果；
但五步的逐位一致不足以证明 2160/8640 步仍逐位一致。因此第二轮 Phase 2 关卡应
**在 np=56 下重跑并重新出具证据**，或者由复审明确接受"分解不变性"的论证后再沿用 np=4 的结果。
本文件不对此作结论。
