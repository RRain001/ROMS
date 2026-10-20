# JAPAN_SEA ES3K 第一阶段独立验收报告

- 日期：2026-10-15
- 分支：`codex/es3k-i3-wet-domain-audit-20261014`（PR #3，保持 Draft，目标 `feature/japan-sea-nesting`）
- 工作区：`ROMS_Nesting/`（本分支新增的离线单向嵌套框架，复用原单网格编译/运行机制）
- 验收范围：**仅第一阶段工程就绪** —— 活动网格、运行头文件、`.in`、MPI 环境、可执行文件
- 明确不在范围内：启动测试、1h/6h/24h 水动力试验、正式模拟年份

## 一、结论

| 项目 | 结论 |
|---|---|
| 第一阶段工程就绪 | **PASS**（`CASE_BINARY_AND_CPP_LINK_PASS`） |
| 水动力验收 | **NOT RUN** —— 真实强迫输入缺失，明确阻塞 |
| ROMS 是否启动过 | 否（`ROMS_started: false`） |
| 是否伪造输入 | 否 |
| 是否合并候选网格 / 改 `main` | 否 |

本报告不是对上一轮 JSON 结论的转述。以下每一项都在恢复后的工作区**重新执行**过，命令与原始输出见各节。

## 二、独立复核方法与结果

| # | 复核项 | 命令 | 结果 |
|---|---|---|---|
| 1 | 语法编译 | `python3 -m py_compile $(find ROMS_Nesting/{Data_pre,ROMS_Build,ROMS_Run} -name '*.py')` | PASS |
| 2 | 空白/冲突检查 | `git diff --check` | PASS |
| 3 | `Data_pre` 全量测试 | `unittest discover -s ROMS_Nesting/Data_pre/tests` | **Ran 313 tests — OK** |
| 4 | `ROMS_Build` 测试 | `unittest discover -s ROMS_Nesting/ROMS_Build/tests` | **Ran 4 tests — OK** |
| 5 | 新增 CI 测试（`test_external_test_case.py`） | 同上，`-p test_external_test_case.py` | **Ran 7 tests — OK** |
| 6 | 工具链 ABI | `ROMS_Build/scripts/env/validate_toolchain.py --case-name JAPAN_SEA` | `abi_pass: true`, rc 0 |
| 7 | 产物/CPP/链接审计 | `ROMS_Build/scripts/build/verify_case_build.py --case-name JAPAN_SEA` | `CASE_BINARY_AND_CPP_LINK_PASS`, `issues: []` |
| 8 | 运行前检查（5 个模式） | `ROMS_Run/scripts/checks/validate_run_prereqs.py --mode <m>` | 5/5 模式 rc 1，均因输入缺失阻塞 |
| 9 | 平台配置可加载 | `show_build_plan.py --config roms_build_config.{macos,linux_gnu}.json` | 两个 profile 均正常解析 |

测试计数与上一轮报告的「130 项原有 + 11 项新增」逐项吻合：

- CI 子集（`.github/workflows/japan-sea-ud1k-bry-schema-contract.yml` 中 15 个 `unittest discover` 目标）
  合计 **141 项全过**；其中新增的 `test_external_test_case.py`(7) + `test_build_context.py`(4) = 11 项，
  故原有为 **130 项**。
- 全量 `Data_pre` 套件（`discover` 所有 `test_*.py`）另为 **313 项全过**，覆盖面大于 CI 子集。

## 三、已核验事实

### 3.1 活动网格

- 活动副本 `projects/JAPAN_SEA/input/ES3K_JAPAN_SEA_TEST_ACTIVE.nc`
  与归档候选 `archive/github_run_38680030642/ES3K_JAPAN_SEA_CORE_SMOOTHED_I3_CANDIDATE.nc`
  **SHA256 逐字节一致**：`df7fd493e81a379e791a6c858836f2410a1c3809d0571d03dce597379274fa18`（本次重新计算确认）。
- 尺寸 732 × 464（rho），湿点 **193,920**，4-邻接连通湿分量 **1** 个。
- 坡度指标 `rx0 = 0.241741`、`rx1 = 7.869365`，最大正交偏差 `0.00276°`。
- 四角误差 ≤ 3.9e-9 m，`angle` 误差 5.3e-13 rad。
- 边界湿点（W/E/S/N）= **0 / 312 / 160 / 348**。西边界全为陆地，已按 `LBC(isFsur) == Clo` 关闭。
- 原始候选文件**未被覆盖**；`mask_was_modified: false`，仅做了副本与静态审计。

审计状态自述为 `STATIC_TEST_GRID_ADMISSION_PASS_NOT_PHYSICAL_ACCEPTANCE`，即静态准入，**不是**物理验收 —— 与本次结论一致。

### 3.2 工具链

- `ifort (IFORT) 2021.9.0` + Intel MPI `2021.9` + `netCDF-Fortran 4.5.3` / `netCDF 4.8.0`。
- 两进程 MPI + 并行 NetCDF4 读写 ABI 探针 `MPI_NETCDF4_ABI_PASS ranks=2`。
- 动态库全部解析到配置前缀（`$HOME/roms_build/install/lib`、`$HOME/intel/oneapi/...`），**无 `not found`**，未混入 OpenMPI。
- `oneapi_setvars` 在共享框架中为可选配置项（`Path | None`），共享代码内**无硬编码 Intel 路径**，也无 `/home/lhy` 绝对路径。
- GNU/OpenMPI（Linux）与 macOS/Homebrew 为独立 profile，经 `--config` 选择；macOS profile 自述 `unverified on this Linux host`，未虚报验证状态。

### 3.3 可执行文件

- `projects/JAPAN_SEA/bin/romsM_japan_sea`，53,720,752 字节，
  SHA256 `cd0f86fd6ed7ee9f5459ca518e5451266ff6302aadb3bf5aee3991f1958baef4`。
- `file` 输出：ELF 64-bit LSB executable, x86-64, dynamically linked, **with debug_info, not stripped**。
- 内嵌标识为 `japan_sea.h`；`strings` 中 **`UPWELLING` 出现次数为 0** ——
  即该产物确为 JAPAN_SEA 应用，未以 UPWELLING 编译成功替代验收。
- 编译期 CPP 选项 52 个，包含 `MASKING`、`CURVGRID`、`SOLVE3D`、`SALINITY`、
  `MY25_MIXING`、`UV_SMAGORINSKY`、`TS_SMAGORINSKY`、`BULK_FLUXES`、
  `SSH_TIDES`、`UV_TIDES`、`RAMP_TIDES`、`TIDES_DATE`、`HDF5`。
- 禁止项 `ANA_GRID` / `ANA_INITIAL` / `ANA_SMFLUX` / `ANA_STFLUX` / **`NESTING`** 均**未**编译进去
  —— 未切换到 ROMS 原生在线 `contact.nc` 嵌套。
- `NetCDF4_output_compiled: true`（`CMODE = nf90_netcdf4` 存在于 `mod_netcdf.f90`）。

### 3.4 `.in` 与运行模式

- 5 个模式：`smoke`、`external_startup`、`external_1h`、`external_6h`、`external_24h`。
- 全部满足 `NtileI(2) × NtileJ(2) == np(4)`。
- `DSTART = 58120.0d0`（MJD 58120 = 2018-01-02），`TIME_REF = 18581117.0d0`（ROMS 标准历元），自洽。
- `smoke` 与 `external_startup` 的强迫/边界/潮汐段**逐行相同**，仅 `TITLE`、输出频率与输出文件名不同
  —— 证明「显式 external forcing 时 smoke 不再被悄悄改成 analytical」的修复已生效。
- 测试窗口 `2018-01-02 → 2018-01-03`，与正式配置日期分离；`external_test_config.json` 声明
  `hydrodynamics_authorized_in_this_stage: false`、`production_year_selected: false`、
  `candidate_design_promoted: false`。
- `external_*` 模式在停止时间超出边界场覆盖时会**报错退出**，而不是自动缩短测试。

## 四、阻塞项（未验收，如实报告）

5 个运行模式全部 `returncode 1`，缺 5 个 ROMS-ready 输入：

```
../input/roms_ini_japan_sea_es3k_test_glorys12v1_20180102.nc
../input/roms_bdy_japan_sea_es3k_test_glorys12v1_20180102_20180103.nc
../input/roms_atm_japan_sea_es3k_test_20180102_20180103.nc
../input/roms_rad_japan_sea_es3k_test_20180102_20180103.nc
../input/roms_tides_japan_sea_es3k_test_20180102.nc
```

上游 `validate_staged_data.py` 另报 7 个 staged 数据集缺失（GLORYS 静态/初始/边界、ERA5 大气/辐射、TPXO9 潮汐、源项排放 CSV）。

`projects/JAPAN_SEA/data/local_micro/` 中只有**微型样本**（真实源数据被转换到合成的 4×5 目标网格上），
其文件名明确标注 `ON_SYNTHETIC_TARGET`，**不能**代表覆盖 ES3K 全域的强迫场。

凭据已就位（`credentials/era5_key.txt`、`~/.copernicusmarine/.copernicusmarine-credentials`，
`copernicusmarine 2.4.1` 与 `cdsapi` 已安装）。因此阻塞原因是**真实强迫数据尚未下载与预处理**，
不是凭据缺失。

**结论：本阶段不得声称任何水动力验收通过。**

## 五、发现的问题与需决策事项

### 5.1 `use_debug: true` —— 产物是调试构建（需决策）

`roms_build_config.json` 把 `use_debug` 由 `false` 改为 `true`。ROMS makefile 在 `USE_DEBUG` 下
`BIN = $(BINDIR)/romsG`，故最终链接产物是 `romsG`，再复制为 `romsM_japan_sea`。
嵌入的编译选项为：

```
-fp-model precise -heap-arrays -g -check all -check bounds -traceback
-check uninit -warn interfaces,nouncalled -gen-interfaces
```

链接时 ifort 给出 `warning #10182: disabling optimization; runtime debug checks enabled`。

- 对**第一阶段**（只要求产物就绪）可接受，且 `-check uninit` / `-check bounds` 对首次试跑新网格是有价值的。
- 但对**第二阶段**（1h/6h/24h）是实质风险：这是 `-O0` 且开启运行时检查与接口生成的构建，
  在 732×464×41、4 进程下 24 小时试验的耗时可能高出一个数量级以上。
- 建议：第二阶段开跑前另建一个 `use_debug: false` 的优化变体，或至少先实测单步耗时再决定。
- 另注：`verify_case_build.py` 的报告**未记录** `use_debug` 或编译 FFLAGS，
  单看 `build_verification.json` 无法判断这是调试构建。建议补记。

### 5.2 `use_parallel_io: false` 偏离 FDNPP 基准

FDNPP 基准为 `use_parallel_io: true`；JAPAN_SEA 改为 `false`。
`$HOME/roms_build/install/lib` 下**没有 PnetCDF**，只有 `libnetcdf`/`libnetcdff`，
因此该改动很可能是有意为之。当前 I/O 策略为 master rank 写出，
而并行 NetCDF4 的库层 ABI 已单独探针验证通过。配置内 `io_policy` 字段已如实记录该策略。
此项与 FDNPP 不一致，需确认是长期选择还是临时措施。

### 5.3 `build_plan.json` 是过期快照

`logs/external_test/build_plan.json`（17:25）仍记录 `use_parallel_io: true` 且 `USE_PARALLEL_IO: on`，
与最终构建（17:35 的 `build_plan.log`，`use_parallel_io: false`，无 `USE_PARALLEL_IO`）不符。
两个文件同名不同后缀易被误读为同一份记录。建议删除过期快照或在文件名上标注阶段。

### 5.4 `case_context.py` 在导入时无条件覆写环境变量

```python
os.environ["ROMS_NESTING_ROOT"] = str(DATA_PRE_ROOT.parent)
```

这是让 `${ROMS_NESTING_ROOT}` 在不同检出路径下都能解析的可移植性机制，意图明确；
但它会在任何 `import case_context` 时**覆盖**用户已显式设置的值（`scripts/check_isolation.py`
已有同样写法，属既有模式）。若将来需要让框架指向另一棵 `roms_src`，此处会静默失效。
非阻塞，建议改用 `setdefault` 或显式校验。

### 5.5 外部测试的边界覆盖闸门是 fail-open 的（**建议在第二阶段前修**）

`create_pilot_infile.py:600` 的守卫 `if stop > boundary_stop: raise SystemExit(...)`
依赖 `external_model_stop()`（`:429-453`）。该函数在**任何**无法判定的情形下都回落到配置的
`time["stop"]`：

```python
except Exception:  # noqa: BLE001
    return configured
```

触发条件包括：边界文件不存在、缺 `zeta_time`、缺 `units`、数组为空、`num2date` 抛异常。

- 当边界文件**不存在**时，`boundary_stop` 等于配置停止时间，`external_24h` 的 24 小时恰好
  不越界，守卫**静默通过**。此情形目前由下游 `validate_run_prereqs.py` 兜住，所以第一阶段不受影响。
- 真正危险的是「文件存在但覆盖时段无法解析」：守卫会通过，而 ROMS 会积分到真实边界覆盖之外，
  在运行时外插或报错。代码与文档宣称的「refuse to shorten a test to fit insufficient boundary coverage」
  只在解析成功时成立。
- 另有一处潜在不一致：守卫校验 `forcing_preview["bry"]`（未叠加 start/stop 的路径），
  而写入 `.in` 的 `BRYNAME` 用 `forcing["bry"]`（叠加后）。JAPAN_SEA 因显式传了 `--bry-path` 两者相同，
  但依赖 GLORYS 默认路径推导的案例会校验与实际写入**不同**的文件。

建议：外部模式下把「无法判定覆盖」与「判定为覆盖不足」区分开，前者直接失败。

### 5.6 `templates/*.in` 是无人读取的冗余文件（会静默过期）

`Data_pre/cases/JAPAN_SEA/templates/` 下的 5 个 `.in` 文件（每个 627 行）**没有任何代码读取**：
`external_test_case.py:144` 只取 `spec['header_template']`（即 `japan_sea.h`），
`resolve_template_path()` 的候选列表里也没有 `templates/`。
它们已经把 67 行 ROMS 样板头替换成 2 行手写说明，与生成器实际输出（3537 行）不同。
若其用途是「生成结果的可读快照」，则应明确标注并定期重生成；若本意是让生成器读取，
则该接线缺失。目前 CI 的 `cases/JAPAN_SEA/**` 路径过滤会让它们看起来受验证，实际无人检查。

### 5.7 测试模式窗口与 staged 校验窗口不一致（提示）

`external_test_config.json` 用 `2018-01-02 → 2018-01-03`，
而 `validate_staged_data.py` 校验的是正式窗口 `2018-01-01 → 2018-01-08`。
两者用途不同（测试 vs 正式），但同一份阻塞报告里并列出现，容易误读为测试输入也要覆盖正式窗口。

### 5.8 `verify_case_build.py` 只验一个模式，且字段名过度声明

- `:23` 把 `mode='external_startup'` 写死，因此 `smoke` / `external_1h` / `external_6h` / `external_24h`
  的 `required_cpp_defs` 与 `.in` 从未被该脚本核对（四个模式的 defs 目前相同，暂无实际差异）。
- `:60` 的 `'tide_phase_date_compiled': not validate_tide_build_artifacts(run, binary)`
  实为「潮汐构建**完全无**任何问题」；缺 `set_tides.f90`、mtime 异常等都会让它为 `False`。
  字段名声称的比实际检查的窄。该函数还在 `:40` 与 `:60` 被调用两次。
- 报告也未记录 `use_debug` / 编译 FFLAGS，单看 `build_verification.json` 无法判断这是调试构建（见 5.1）。

（该脚本的 CPP 提取逻辑本身是可靠的：本次独立复核确认 52 个选项、13 个必需项 + `MPI`/`T_PASSIVE`
全部存在，`my_fort = "ifort"` 与 `Hfile = "japan_sea.h"` 均在编译产物中。）

### 5.9 若干轻微项（不阻塞）

| 项 | 位置 | 说明 |
|---|---|---|
| `active_grid` 路径未做 `~` 展开 | `roms_preprocessing_utils.py:228-233` | 同文件 `grid_arg` 分支做了 `.expanduser()`，此处没有 |
| GNU profile 绑定系统 netcdf | `ROMS_Build/env/linux_gnu_openmpi.sh:3,9` | `PATH=/usr/bin:/bin` 且 `NF_CONFIG=/usr/bin/nf-config`，但本机 `which nf-config` 为 `/usr/local/bin/nf-config` |
| oneAPI 版本号硬编码 | `ROMS_Build/env/linux_intel.sh:5` | `2023.1.0` 写死；升级 oneAPI 会静默失配（好在 `command -v` 会报错） |
| 测试名强于断言 | `test_external_test_case.py:52` | 断言 `NtileI*NtileJ == 4`（写死）而非交叉核对 `run_config.np` |
| 测试名不副实 | `test_build_context.py:11` | 名为 `test_default_matches_explicitly_selected_fdnpp_toolchain`，实际未与 FDNPP 比对 |

### 5.10 本轮已修复

- **CI 路径过滤**（对应上轮遗留）：`.github/workflows/japan-sea-ud1k-bry-schema-contract.yml`
  的 `push` 与 `pull_request` 两个 `paths` 列表均补入此前遗漏的
  `Data_pre/core/case_context.py`、`Data_pre/core/roms_preprocessing_utils.py`、
  `ROMS_Build/env/**`、`ROMS_Build/scripts/build/verify_case_build.py`、
  `ROMS_Build/scripts/env/validate_toolchain.py`、`configs/templates/**`。
  此前修改这些文件不会触发该 job。
- **子网格模板参数化**：`configs/templates/external_single_grid/external_test_config.json.template`
  把写死的 `"header_template": "japan_sea.h"` 改为 `"${CASE_SLUG}.h"`，
  并把 ES3K 专属的坡度闸门 `max_rx0: 0.35 / max_rx1: 8.0 / max_orthogonality_deg: 1.0`
  改为 `${MAX_RX0}` / `${MAX_RX1}` / `${MAX_ORTHOGONALITY_DEG}` 占位符
  （ES3K 实测 `rx1 = 7.87`，已逼近 8.0 上限，其他子网格照抄会误触）。

### 5.11 跨案例影响评估（结论：无污染）

`ROMS_Nesting/Data_pre/impl/preprocessing/create_pilot_infile.py` 是**独立 vendored 副本**
（commit `814ee1d`），FDNPP / LAHAGUE / WOLSONG 使用的是顶层 `Data_pre/` 下的另一份未改动副本。
已逐行比对两份，本次改动**不会**影响其他案例。若将来回填到共享副本，需注意三处语义变化：

1. `source.release_mode` 以 `"disabled"` 开头时把 `river` 置为 `"none"`（当前各案例均为
   `constant_rate_over_year`，暂不触发，但未来任何 `disabled...` 案例会被静默去掉源项文件）；
2. 移除 smoke → analytical 的降级，`smoke` 语义从「无数据自检」变为「需要外部强迫」；
3. `DSTART` 回退由 `common_year_offset_days(start)` 改为 `to_mjd(start)` —— 相对
   `TIME_REF = 18581117.0d0` 这是**修正**，但 ini 缺失时生成结果会变。

## 六、下一步

1. **本阶段交付物**：本报告 + 配置/测试/构建记录提交到分支（不推 `main`，PR #3 保持 Draft）。
2. **解除阻塞**：用现有 GLORYS / ERA5 / TPXO 预处理器准备 ES3K 全域真实强迫，
   时间窗固定在 `2018-01-02 → 2018-01-03`，不触碰尚未确定的正式模拟年份。
3. **第二阶段**：依次执行启动测试 → 1h → 6h → 24h；
   每步检查稳定性、CFL、NaN、温盐范围、海面高度、质量守恒与边界异常；
   **任一步不通过即停止，不自动延长**。
4. 开跑前先决定 5.1 的调试/优化构建问题。

---

## 附：本报告未覆盖的内容

- 未运行任何 ROMS 时间积分。
- 未做海岸线/海峡水道的科学质量评审。
- 未验证 UD1K / L3 模板在真实子网格上的可用性（模板仅做了参数化整理，未激活任何子案例）。
- `rx1 = 7.869` 是否满足正式稳定性门槛，需由第二阶段试算评估，本报告不作判断。
