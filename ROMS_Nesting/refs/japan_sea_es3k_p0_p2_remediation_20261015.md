# JAPAN_SEA ES3K：P0–P2 独立评审整改验收报告

- 日期：2026-10-15
- 分支：`codex/es3k-i3-wet-domain-audit-20261014`（PR #3，保持 **Draft**，未合并 `main`）
- 执行依据：PR #3 评论 `#issuecomment-6190945862`（独立技术评审裁决）
- 范围：**Q1–Q8 整改 + 回归测试 + GitHub 提交**。未运行任何 ROMS 时间积分。

## 一、结论

| 项目 | 结论 |
|---|---|
| P0 整改（Q1 / Q2 / Q4） | **完成** |
| P1 整改（Q5 / Q6 / Q7） | **完成** |
| P2 整改（Q3 / Q8） | **完成** |
| 回归测试 | Data_pre **341**、ROMS_Build **6**、ROMS_Run **10**，全 PASS |
| 双构建验证 | Debug 与 Release 均 `CASE_BINARY_AND_CPP_LINK_PASS`，五模式逐项 PASS |
| 第二阶段水动力 | **`PHASE2_HYDRO_BLOCKED_REAL_FORCING_MISSING`**（详见第六节） |
| PR 状态 | Draft，未合并 `main`，未改动冻结 ROMS 源码，未启用在线 `contact.nc` 嵌套 |

## 二、提交与文件变更

| 阶段 | 提交 | 文件 | 变更量 |
|---|---|---|---|
| **P0** | `f229495` | 10 | +1111 / −81 |
| **P1** | `02b475c` | 6 | +348 / −9 |
| **P2** | `1104487` | 9 | +73 / −3139 |
| 后续 | `068b296` | 1 | 测试卫生修正（见第八节） |

### P0 `f229495` — Q1 / Q2 / Q4

```
.github/workflows/japan-sea-ud1k-bry-schema-contract.yml   |  17 +
ROMS_Nesting/Data_pre/core/external_forcing_coverage.py    | 211 +   (新)
ROMS_Nesting/Data_pre/impl/preprocessing/create_pilot_infile.py | 81 +-
ROMS_Nesting/Data_pre/tests/test_external_forcing_coverage.py | 201 + (新)
ROMS_Nesting/Data_pre/tests/test_external_test_case.py     |  36 +-
ROMS_Nesting/Data_pre/cases/JAPAN_SEA/config/roms_build_config.release.json | 48 + (新)
ROMS_Nesting/Data_pre/cases/JAPAN_SEA/config/roms_run_config.json | 13 +-
ROMS_Nesting/ROMS_Build/scripts/build/verify_case_build.py | 366 +-
ROMS_Nesting/ROMS_Run/core/run_context.py                  |  73 +-
ROMS_Nesting/ROMS_Run/tests/test_external_forcing_gate.py  | 146 +   (新)
```

### P1 `02b475c` — Q5 / Q6 / Q7

```
ROMS_Nesting/Data_pre/core/case_context.py                 |  64 +-
ROMS_Nesting/Data_pre/core/entrypoint_runner.py            |   9 +-
ROMS_Nesting/Data_pre/tests/test_nesting_root_init.py      | 131 +   (新)
ROMS_Nesting/ROMS_Build/core/build_context.py              |  88 +-  (provenance)
ROMS_Nesting/ROMS_Build/tests/test_build_context.py        |  57 +-
ROMS_Nesting/scripts/check_isolation.py                    |   8 +-
```

### P2 `1104487` — Q3 / Q8

```
ROMS_Nesting/Data_pre/cases/JAPAN_SEA/templates/*.in       | 5 × 627 −  (删除)
ROMS_Nesting/Data_pre/core/roms_preprocessing_utils.py     |   4 +-
ROMS_Nesting/ROMS_Build/env/linux_gnu_openmpi.sh           |  34 +-
ROMS_Nesting/ROMS_Build/env/linux_intel.sh                 |  14 +-
ROMS_Nesting/Data_pre/cases/JAPAN_SEA/config/staged_download_config.json | 25 + (新)
```

**归属偏差（如实披露）**：`ROMS_Run/core/run_context.py` 同时含 Q2（`)` 覆盖闸门）与 Q7（`init_nesting_root()` 调用）两处改动，两处都落在 P0 提交里；Q7 的主体在 P1。不影响内容正确性，仅影响分阶段归属。

## 三、逐项验收证据

### Q1 — Debug / Release 双构建 ✅

- `roms_build_config.release.json`：`use_debug: false`，`-O3 -ip`，**独立 build 目录** `build/Build_romsM_release`（不破坏 Debug 产物），**独立可执行名** `romsM_japan_sea_release`（两者不可能互相冒充）。
- 模式分配：`smoke` / `external_startup` → Debug；`external_1h` / `6h` / `24h` → Release。由 `roms_run_config.json` 的 `build_kind_by_mode` 与 `build_kind_note` 显式记录。
- 原始产物、FFLAGS、`USE_DEBUG`、CPP 列表、库依赖、config hash、binary SHA256 全部留存（见 Q6 provenance）。Debug 原始产物另备份于 `projects/JAPAN_SEA/build_artifacts/debug/`。

| 构建 | 产物 | 字节 | SHA256 |
|---|---|---|---|
| Debug | `bin/romsM_japan_sea` | 53,720,752 | `cd0f86fd6ed7ee9f5459ca518e5451266ff6302aadb3bf5aee3991f1958baef4` |
| Release | `bin/romsM_japan_sea_release` | 8,757,648 | `28bab2ede4d51c76d35b2804f39289776860a98aeac27040b455e13c5ddd2827` |

两者字节数相差 6 倍（Debug 含调试信息），Release 是**独立编译器输出**（链接行为 `-o .../bin/romsM`），**不是** `romsG` 的副本。

**未完成**：Release 的**启动验证**（对比前若干时间步）尚未执行 —— 依赖 ERA5，见第六节。

### Q2 — 外部时间覆盖 fail-closed ✅

新模块 `Data_pre/core/external_forcing_coverage.py`：

- 把 **UNKNOWN**（无法判定：文件缺失 / 无时间轴 / 缺 `units` / 空数组 / 历法无法解析 / 变量不可读）与 **INSUFFICIENT**（已判定但覆盖不足：非严格递增 / 起点未覆盖 / 末端不足）**区分为两种拒绝**，二者都不允许进入运行。
- 检查**实际存在的全部边界时间轴**（`zeta_time`/`v2d_time`/`v3d_time`/`temp_time`/`salt_time`/`dye_time`），不只是 `zeta_time`。
- 校验的是**真正写入 `BRYNAME` 的文件**（此前校验的是未叠加 start/stop 的 preview 路径，两者可能不同）。
- `smoke` 显式 external forcing 同样受检（闸门按 `BRYNAME` 触发，不按模式名）。
- 静态生成与运行权限分离：`--allow-unverified-forcing` 允许无真实数据时出计划，但 `.in` 会被打上 `FORCING_UNVERIFIED` 并内嵌实测证据；运行闸门拒绝该标记，并拒绝 UNKNOWN/INSUFFICIENT。
- 请求的外部窗口**不会被静默缩短**。

真实数据上的实测证据（已嵌入生成的 `.in` 头部）：

```
! boundary coverage evidence (measured, not assumed):
!   file = .../input/roms_bdy_japan_sea_es3k_test_glorys12v1_20180102_20180103.nc
!   status = OK
!   required window = 2018-01-02T00:00:00 -> 2018-01-03T00:00:00
!   dye_time:  n=2 units='days since 1858-11-17 00:00:00' calendar='gregorian' 2018-01-02T00:00 -> 2018-01-03T00:00 strictly_increasing=True
!   salt_time: ... (同上)
!   temp_time: ... (同上)
!   v2d_time:  ... (同上)
!   v3d_time:  ... (同上)
!   zeta_time: ... (同上)
```

负面测试 17 项（`Data_pre/tests/test_external_forcing_coverage.py`）：文件不存在、无时间轴、缺 units、空数组、历法不可解析、文件非 NetCDF → UNKNOWN；时间倒序、重复时间戳、末端不足、起点未覆盖、多轴中一轴过短、请求窗口倒置 → INSUFFICIENT；另有合成合法时间轴通过、边界等值通过、多轴全足通过、MJD↔datetime 往返。

运行闸门负面测试 10 项（`ROMS_Run/tests/test_external_forcing_gate.py`）：边界文件缺失、UNKNOWN、INSUFFICIENT、起点未覆盖、`FORCING_UNVERIFIED` 标记（即使文件本身合格）、缺 `DSTART`、smoke 走 external 同样受检；另加三项通过用例。

### Q4 — 完整构建 / 模式验证 ✅

`verify_case_build.py` 重写：

- 不再固定 `external_startup`，改为遍历 `roms_run_config.json.run_modes` 的**全部五个模式**，逐项输出 verdict（必需 CPP、禁用 CPP、variant、可执行文件、`.in` 标识、`NtileI*NtileJ` 与 `np`）。
- `Hfile` 不再硬编码，取自 `context.variant.header_name`。
- `validate_tide_build_artifacts` **只调用一次**。
- 过度声明的 `tide_phase_date_compiled` 已替换为可核验的 `tides_date_evidence`：

```json
"tides_date_evidence": {
  "cpp_in_checkdefs_list": false,
  "defined_in_header": true,
  "source_generated": true,
  "object_compiled": true,
  "note": "build evidence only; not tidal-dynamics acceptance"
}
```

（`cpp_in_checkdefs_list` 为 `false` 是 ROMS 事实：`checkdefs.f90` 只枚举部分选项，`TIDES_DATE` 不在其中；其证据是头文件宏 + 生成的 `tides_date.f90` + 已编译的 `tides_date.o`。字段名与证据一一对应，不再声称超出实际检查范围。）

- 报告新增 `build_kind`、`use_debug`、`use_parallel_io`、`use_netcdf4`、`io_policy`、真实 `fflags`、`build_config_sha256`、`forbidden_options_present`、`mode_verdicts`。
- 支持 `--config`，因此 Debug / Release **各自独立验证**。

实测输出（两套构建 × 五模式）：

```
======= DEBUG BUILD =======      build_kind=debug   binary=romsM_japan_sea (53,720,752B)
  smoke                PASS  tiles=4 np=4 binary=romsM_japan_sea         (roms_build_config.json)
  external_startup     PASS  tiles=4 np=4 binary=romsM_japan_sea         (roms_build_config.json)
  external_1h          PASS  tiles=4 np=4 binary=romsM_japan_sea_release (roms_build_config.release.json)
  external_6h          PASS  tiles=4 np=4 binary=romsM_japan_sea_release (roms_build_config.release.json)
  external_24h         PASS  tiles=4 np=4 binary=romsM_japan_sea_release (roms_build_config.release.json)

======= RELEASE BUILD =======    build_kind=release binary=romsM_japan_sea_release (8,757,648B)
  (五模式同样全 PASS，binary 归属同上)
```

### Q5 — 暂不启用并行 I/O ✅

- Debug 与 Release 两份配置均为 `use_parallel_io: false`；测试断言 Release 与 Debug 在该字段上一致，防止漂移。
- 未新增任何依赖（未装 PnetCDF）。
- `MPI_NETCDF4_ABI_PASS` 在报告中仍表述为**库层探针**，`io_policy` 字段明确写出 "MPI compute; NetCDF4/HDF5 output via master rank; parallel-capable NetCDF library ABI also probed"，不被当作 ROMS 并行 I/O 集成验收。

### Q6 — 构建证据可追溯 ✅

- 每次成功构建写入 `logs/build_provenance/<UTC微秒>_<config>_<variant>.json`，字段：`generated_utc`、`git_head`、`build_config_sha256`、`header_sha256`、`binary_sha256`、`binary_bytes`、`build_kind`、`use_debug`、`use_parallel_io`、`use_netcdf4`、`io_policy`、`compiler`、`fflags`（从编译产物 `mod_strings.f90` 实测读回）、`compiled_options`（从 `checkdefs.f90` 实测读回）、`build_directory`、`build_command`。
- 记录**不复用**：文件名冲突自动加序号后缀；测试断言两次构建产生两个不同路径。
- 旧 `logs/external_test/build_plan.json`（仍写 `use_parallel_io=true`）已改名为 `build_plan.STALE_NOT_FOR_ACCEPTANCE.20261015T1725Z.json`。

### Q7 — 路径解析无隐式全局副作用 ✅

- `case_context.py` **不再**在 import 时写 `ROMS_NESTING_ROOT`。
- 新增显式 `init_nesting_root()`，在 `resolve_case_context()`、build/run context 解析器、预处理入口 runner、`check_isolation.py` 处调用。
- 已设的值指向**真实 nesting checkout**（含 `Data_pre`/`ROMS_Build`/`ROMS_Run`）时被尊重，允许用户有意指向另一棵树；否则（笔误、普通目录、过期 export）**fail-closed**，不静默替换。
- `paths.case_root` 若含未展开的 `${...}`，现在直接报错，而不是生成一个静默不存在的路径。
- 测试 9 项：import 无副作用（干净环境 / 预置值两条，均为子进程验证）、未设时初始化为本检出、显式合法路径被采纳、非 checkout 目录失败、部分 checkout 失败、路径不存在失败、失败时不改写环境、`is_nesting_root` 正确性。
- `scripts/check_isolation.py` 仍 PASS：`I0 copied-path isolation/config PASS`。

### Q3 — 删除未使用的 `.in` 冗余文件 ✅

先重新审计引用：`templates/` 的唯一消费者是 `external_test_case.py:144`，只取 `header_template`；`resolve_template_path()` 的候选列表不含 `templates/`。确认后删除五个 `.in`（各 627 行，共 −3135 行）。保留 `templates/japan_sea.h`（它确实被读取）。唯一权威来源现为 `create_pilot_infile.py` + ROMS 原始模板。

### Q8 — 工程整理 ✅

| 项 | 改动 | 回归测试 |
|---|---|---|
| `active_grid` 未展开 `~` | 补 `expanduser` + `expandvars` + 相对路径归一化 + `resolve()` | `test_external_test_case` / 网格解析用例 |
| GNU profile 硬绑 `/usr/bin/nf-config` | 改为 `ROMS_GNU_NF_CONFIG` / `ROMS_GNU_NC_CONFIG` 显式覆盖或 PATH 探测，找不到即 fail-closed | 该 host 上 `nf-config` 实为 `/usr/local/bin`，已非硬编码 |
| oneAPI 编译器路径写死版本 | 改为扫描 `$HOME/intel/oneapi/compiler/*/linux`（版本序取最高）或 `ROMS_INTEL_COMPILER_ROOT` 覆盖 | `bash -n` 语法校验 + 解析路径断言 |
| `NtileI*NtileJ` 与真实 `np` 未交叉断言 | 改为对 `roms_run_config.json` 的 `np` 交叉断言 | `test_independent_external_durations_and_mpi_tiles` |
| 测试名不副实 | `test_default_matches_explicitly_selected_fdnpp_toolchain` → `test_default_uses_the_fdnpp_toolchain_family`，并**实际**断言构成该家族的 8 个字段；注释说明为何不读外部 FDNPP 配置（本子树须自包含） | 同文件 |

## 四、回归测试与 CI

| 套件 | 结果 |
|---|---|
| `Data_pre/tests` 全量 | **Ran 341 — OK** |
| `ROMS_Build/tests` 全量 | **Ran 6 — OK** |
| `ROMS_Run/tests` 全量 | **Ran 10 — OK** |
| CI 受影响子集（18 个目标） | **181 = 171 + 10，全 OK** |
| `py_compile`（Data_pre + ROMS_Build + ROMS_Run 全部 `.py`） | PASS |
| `git diff --check` | PASS |
| `scripts/check_isolation.py` | PASS |

对比首轮：Data_pre 313 → **341**，ROMS_Build 4 → **6**，ROMS_Run 0 → **10**（新建），CI 子集 141 → **181**。无不可解释回归。

CI 工作流已补入新增路径（`ROMS_Run/**`、`external_forcing_coverage.py`、`entrypoint_runner.py`、两个新测试文件、`scripts/check_isolation.py`）与新增测试调用；两个 `paths` 列表各 53 条。

## 五、构建验证产物路径

- Debug：`projects/JAPAN_SEA/logs/external_test/build_verification.json`
- Release：同上（以 `--config roms_build_config.release.json` 覆盖写入）
- 链接证据：`logs/external_test/binary_links.log`
- 编译器版本：`logs/external_test/compiler_versions.log`
- 构建溯源：`logs/build_provenance/*.json`
- 覆盖证据：生成 `.in` 头部的 `boundary coverage evidence` 块
- 网格审计：`logs/external_test/active_grid_audit.json`

## 六、第二阶段阻塞：`PHASE2_HYDRO_BLOCKED_REAL_FORCING_MISSING`

已就绪并通过校验的真实输入（ES3K 全域 732×464）：

| 文件 | 大小 | 状态 |
|---|---|---|
| `input/roms_ini_japan_sea_es3k_test_glorys12v1_20180102.nc` | 212 MB | ✅ |
| `input/roms_bdy_japan_sea_es3k_test_glorys12v1_20180102_20180103.nc` | 1.8 MB | ✅ |
| `input/roms_tides_japan_sea_es3k_test_20180102.nc` | 136 MB | ✅ |

仍缺 **ERA5 大气与辐射**：

- 大气请求于 20:22 **成功并从 CDS 下载**（5.85 MB）。
- 辐射请求（`4df2688b-4101-417a-a5a6-697e0b0484b5`）自 20:22 起停在 `accepted`，与上午微型尝试同一现象。
- `download_era5_staged.py` 使用 `TemporaryDirectory`，**先下大气、再下辐射、最后才写输出**；因此在大气已到手的情况下，若进程终止，大气结果也会一并丢失 —— 这是脚本的脆弱点，已记录。
- 运行前检查因此在 `external_*` 全部模式下仍报 `missing referenced input file: ...roms_atm... / ...roms_rad...`。

**因此不启动任何水动力试验，不声称 1h/6h/24h 通过。**

## 七、科学与验收边界（遵照裁决，未越界）

- ES3K 静态指标 `rx0=0.241741`、`rx1=7.869365` 接近阈值 8；网格审计自述为 `STATIC_TEST_GRID_ADMISSION_PASS_NOT_PHYSICAL_ACCEPTANCE`。本报告**不**据此宣布数值稳定或物理可接受。
- 未把 4×5 `ON_SYNTHETIC_TARGET` 微型样本计入真实强迫。
- 测试窗口固定 `2018-01-02 → 2018-01-03`，未触碰正式生产期。
- 未改动 `main`、其他现有案例、冻结 ROMS 源码、UD1K/L3 科学设计。

## 八、本轮新发现（如实披露）

1. **`center_time()` 锚定窗口起始日**（已在 `b8e3dc3` 记录 Q9）：加宽 GLORYS 下载窗口起点会静默把初始场选成错误日期。本轮实际踩到并修正（`--start 2018-01-02T00:00:00` 重下后 `source_time=2018-01-02T12:00` 与微型基线一致）。
2. **ERA5 凭据双份**（已在 `b8e3dc3` 记录 Q10）：`credentials/era5_key.txt` 返回 401，可用的是 `~/.config/roms/era5.env`。
3. **ERA5 脚本临时目录脆弱**（Q6 节第六节）：大气数据在手但未落盘，进程终止即丢失。
4. **测试卫生**：`test_debug_executable_is_published_under_case_name` 只替换 `paths` 未替换 `case_root`，导致 `write_build_provenance` 在真实 case 目录留下记录。已修（`068b296`）并加断言，真实目录已清理。

## 九、未执行项

- 未运行任何 ROMS 时间积分（启动 / 1h / 6h / 24h 全未跑）。
- 未做 Release 与 Debug 的前若干时间步状态对比（依赖 ERA5）。
- 未验证 UD1K / L3 模板在真实子网格上的可用性（模板仅参数化整理，未激活任何子案例）。
- `/workspace` 上的 GEBCO / GSHHG / TPXO 离线源未重新校验，仅使用既有文件。
