# JAPAN_SEA ES3K 第一阶段：待决问题清单

- 日期：2026-10-15
- 分支：`codex/es3k-i3-wet-domain-audit-20261014`（PR #3，Draft，目标 `feature/japan-sea-nesting`）
- 上下文报告：同目录 `japan_sea_es3k_stage1_acceptance_20261015.md`
- 当前阶段：**第一阶段工程就绪 PASS**；水动力验收 **NOT RUN**（真实强迫数据尚未准备）
- 硬约束：不合并 `main`、不改冻结的 ROMS 源码、不启用 ROMS 原生在线 `contact.nc` 嵌套、不伪造输入

本文件把当前**已确认但尚未解决**的问题集中列出，每条给出背景、证据、可选方案与待决问题，便于外部评审逐条回答。

---

## Q1. 第二阶段该用调试构建还是优化构建？

**背景**
`ROMS_Nesting/Data_pre/cases/JAPAN_SEA/config/roms_build_config.json` 把 `use_debug` 由 `false` 改为 `true`。
ROMS makefile 在 `USE_DEBUG` 下 `BIN = $(BINDIR)/romsG`，因此最终链接产物是 `romsG`，
再由 `build_context.py` 复制为 `bin/romsM_japan_sea`（两个文件逐字节相同）。

**证据**
- `projects/JAPAN_SEA/logs/external_test/build_netcdf4.log` 末尾：
  `mpiifort ... -o .../bin/romsG ...` 以及 `ifort: warning #10182: disabling optimization; runtime debug checks enabled`
- 二进制内嵌 FFLAGS：
  `-fp-model precise -heap-arrays -g -check all -check bounds -traceback -check uninit -warn interfaces,nouncalled -gen-interfaces -free`
- 参考基准：FDNPP 的 `Data_pre/cases/FDNPP/config/roms_build_config.json` 为 `use_debug: false`
- `bin/romsM_japan_sea`：53,720,752 B，sha256 `cd0f86fd6ed7ee9f5459ca518e5451266ff6302aadb3bf5aee3991f1958baef4`

**权衡**
- 支持保留：`-check uninit` / `-check bounds` 对首次试跑新网格能抓出未初始化变量与越界；第一阶段不跑积分，无代价。
- 支持切换：`-O0` + 运行时检查 + `-gen-interfaces`，在 732×464×41、4 进程下，
  1h/6h/24h 试验耗时可能高一个数量级，24 小时试验可能不可行。

**待决**
1. 第二阶段是先用调试构建跑启动测试与 1h，再切优化构建跑 6h/24h，还是一开始就用优化构建？
2. 若保留调试构建，`verify_case_build.py` 的报告应补记 `use_debug` / FFLAGS（目前不记录，单看 JSON 无法判断）。

---

## Q2. 外部测试的边界覆盖闸门是 fail-open 的（**建议第二阶段前修**）

**背景**
`ROMS_Nesting/Data_pre/impl/preprocessing/create_pilot_infile.py:600`：

```python
if stop > boundary_stop:
    raise SystemExit("test stop exceeds configured boundary coverage; refusing to shorten test")
```

`boundary_stop` 来自 `external_model_stop()`（`:429-453`），该函数在**任何**无法判定的情形下都回落到配置的 `time["stop"]`：

```python
except Exception:  # noqa: BLE001
    return configured
```

**触发条件**
边界文件不存在、缺 `zeta_time`、缺 `units`、数组为空、`num2date` 抛异常。

**后果**
- 文件**不存在**时 `boundary_stop` == 配置停止时间，`external_24h` 的 24h 恰好不越界 → 守卫**静默通过**。
  该情形目前由下游 `ROMS_Run/scripts/checks/validate_run_prereqs.py` 兜住，第一阶段不受影响。
- 更危险的是「文件存在但时间轴无法解析」：守卫通过，ROMS 积分到真实边界覆盖之外，运行时外插或报错。
- 代码与文档宣称的「refuse to shorten a test to fit insufficient boundary coverage」只在解析成功时成立。

**另一处潜在不一致**
守卫校验 `forcing_preview["bry"]`（未叠加 `--start-time`/`--stop-time` 的路径），
而写入 `.in` 的 `BRYNAME` 用 `forcing["bry"]`（叠加后）。
JAPAN_SEA 因显式传了 `--bry-path` 两者相同，但依赖 GLORYS 默认路径推导的案例会校验与实际写入**不同**的文件。

**待决**
1. 是否把「无法判定覆盖」与「判定为覆盖不足」区分开，前者直接失败（fail-closed）？
2. 若这样做，`pilot_1day` 与正式模式是否也应采用同样严格语义，还是只针对 `external_*` 测试模式？

---

## Q3. `templates/*.in` 是无人读取的冗余文件

**背景**
`ROMS_Nesting/Data_pre/cases/JAPAN_SEA/templates/` 下有 5 个 `.in`（`smoke`、`external_startup`、`external_1h`、`external_6h`、`external_24h`，各 627 行）。

**证据**
- 唯一读取 `templates/` 的代码是 `Data_pre/core/external_test_case.py:144`，
  且只取 `spec['header_template']`（即 `japan_sea.h`）。
- `create_pilot_infile.py:862-879` 的 `resolve_template_path()` 候选列表只有
  `--template`、`paths.roms_in_template`、`roms_src/ROMS/External/roms_upwelling.in`、`run/roms_upwelling.in`，**没有** `templates/`。
- 这 5 个文件已把 67 行 ROMS 样板头换成 2 行手写说明，与生成器实际输出（3537 行）不一致。
- CI 的 `ROMS_Nesting/Data_pre/cases/JAPAN_SEA/**` 路径过滤会让它们看起来受验证，实际无人检查。

**待决**
1. 它们的定位是「生成结果的可读快照」（则应标注并定期重生成），还是本意让生成器通过 `--template` 读取（则接线缺失）？
2. 若只是快照，是否改为由脚本从 `run/*.in` 自动导出，避免手工维护导致静默过期？

---

## Q4. `verify_case_build.py` 只验一个模式，且字段名过度声明

**证据**（`ROMS_Nesting/ROMS_Build/scripts/build/verify_case_build.py`）
- `:23` 写死 `mode='external_startup'`，`smoke` / `external_1h` / `external_6h` / `external_24h`
  的 `required_cpp_defs` 与 `.in` 从未被核对（四个模式目前 defs 相同，暂无实际差异）。
- `:60` 的 `'tide_phase_date_compiled': not validate_tide_build_artifacts(run, binary)`
  实为「潮汐构建**完全无**任何问题」；缺 `set_tides.f90`、mtime 异常等都会让它为 `False`。
- 同一函数在 `:40` 与 `:60` 被调用两次。
- 报告不记录 `use_debug` / FFLAGS（见 Q1）。

**待决**
1. 是否改为遍历 `run_config.run_modes` 的全部模式？
2. 字段是否拆成 `tide_build_issues: []` 与 `tides_date_compiled: bool`？

（该脚本的 CPP 提取逻辑本身可靠：本次独立复核确认 52 个选项、13 个必需项 + `MPI`/`T_PASSIVE` 全部存在，
`my_fort = "ifort"` 与 `Hfile = "japan_sea.h"` 均在编译产物中。）

---

## Q5. `use_parallel_io: false` 偏离 FDNPP 基准

**证据**
- FDNPP 基准 `use_parallel_io: true`；JAPAN_SEA 改为 `false`。
- `$HOME/roms_build/install/lib` 下**没有 PnetCDF**，只有 `libnetcdf` / `libnetcdff`。
- 并行 NetCDF4 的**库层** ABI 已由 `validate_toolchain.py` 探针验证通过（`MPI_NETCDF4_ABI_PASS ranks=2`）。
- 当前 I/O 策略为 master rank 写出，配置内 `io_policy` 字段已如实记录。

**待决**
1. 这是长期选择还是临时措施？
2. 若 ROMS 侧要开 `USE_PARALLEL_IO`，需要补装 PnetCDF，还是仅靠 netCDF-4/HDF5 的并行能力即可？

---

## Q6. `build_plan.json` 是过期快照

`projects/JAPAN_SEA/logs/external_test/build_plan.json`（17:25）仍记录 `use_parallel_io: true` 且 `USE_PARALLEL_IO: on`，
与最终构建（17:35 的 `build_plan.log`，`use_parallel_io: false`，无 `USE_PARALLEL_IO`）不符。
两个文件同名不同后缀，易被误读为同一份记录。

**待决**：删除过期快照，还是在文件名上标注阶段/时间？

---

## Q7. `case_context.py` 导入时无条件覆写环境变量

```python
# ROMS_Nesting/Data_pre/core/case_context.py:14
os.environ["ROMS_NESTING_ROOT"] = str(DATA_PRE_ROOT.parent)
```

这是让 `${ROMS_NESTING_ROOT}` 在不同检出路径下都能解析的可移植性机制，意图明确；
但会在任何 `import case_context` 时**覆盖**用户已显式设置的值（`scripts/check_isolation.py:11` 已有同样写法，属既有模式）。
若将来需要让框架指向另一棵 `roms_src`，此处会静默失效。

**待决**：改为 `setdefault`（尊重外部设置）还是保留无条件覆写（以检出路径为准）？

---

## Q8. 若干轻微项（不阻塞，可一并决定是否修）

| 项 | 位置 | 说明 |
|---|---|---|
| `active_grid` 路径未做 `~` 展开 | `Data_pre/core/roms_preprocessing_utils.py:228-233` | 同文件 `grid_arg` 分支做了 `.expanduser()`，此处没有 |
| GNU profile 绑定系统 netcdf | `ROMS_Build/env/linux_gnu_openmpi.sh:3,9` | `PATH=/usr/bin:/bin` 且 `NF_CONFIG=/usr/bin/nf-config`，但本机 `which nf-config` 为 `/usr/local/bin/nf-config` |
| oneAPI 版本号硬编码 | `ROMS_Build/env/linux_intel.sh:5` | `2023.1.0` 写死；升级 oneAPI 会静默失配（好在 `command -v` 会报错） |
| 测试名强于断言 | `Data_pre/tests/test_external_test_case.py:52` | 断言 `NtileI*NtileJ == 4`（写死）而非交叉核对 `run_config.np` |
| 测试名不副实 | `ROMS_Build/tests/test_build_context.py:11` | 名为 `test_default_matches_explicitly_selected_fdnpp_toolchain`，实际未与 FDNPP 比对 |

---

## 数据准备阶段新发现（2026-10-15 追加）

### Q9. GLORYS 下载窗口的起点会静默决定初始场是哪一天

**背景**
`download_glorys12v1_staged.py:55` 的 `center_time()` 取的是**窗口起始日**的 12:00，不是窗口中点：

```python
def center_time(config: dict, window: TimeWindow) -> datetime:
    hh, mm, ss = [int(item) for item in str(config["time_mean_center"]).split(":")]
    return datetime(window.start.year, window.start.month, window.start.day, hh, mm, ss)
```

`write_initial_product()` 用它挑「离它最近的一帧」：

```python
target = np.datetime64(center_time(config, requested_window).strftime(...))
time_index = int(np.argmin(np.abs(values - target)))
```

**后果（实测）**
为「保险」把窗口从 `2018-01-02T00:00` 加宽到 `2018-01-01T12:00` 起点后，
初始场被静默选成 **2018-01-01 12:00** 那一帧，而模型需要的是 **2018-01-02 12:00**。
转换器不会报错（源文件只有一帧，`np.argmin` 返回 0），生成的 ini 表面上完全正常：

```
time_index=0
source_time=2018-01-01T12:00:00     # 错：差一天
model_time=2018-01-02T00:00:00
```

用 `--start 2018-01-02T00:00:00` 重下后恢复正常（与微型测试基线一致）：

```
time_index=0
source_time=2018-01-02T12:00:00     # 对
model_time=2018-01-02T00:00:00
```

**注意**：边界场不受影响 —— `write_boundary_product()` 保留请求窗口内的**全部**帧，
再由 `create_ocean_bry_from_glorys.py` 按 `[start+12h, stop+12h]` 选取，所以窗口加宽只是多下几帧。

**待决**
1. `center_time()` 是否应改为取窗口中点（或显式接受一个 `--initial-time` 参数）？
2. 是否应在 `write_initial_product()` 里校验「选中帧的时刻 == 期望源时刻」，不符即失败（fail-closed）？
   当前这个静默错位只有把 `source_time` 与模型时刻对照才看得出来。

### Q10. ERA5 凭据有两份，其中一份已失效

**实测**
- `/home/lhy/ROMS/credentials/era5_key.txt`（mode 664，2026-06-26）→ **401 Unauthorized**
  （`cds.climate.copernicus.eu/api/retrieve/v1/processes/reanalysis-era5-single-levels/execution`，
  `Authentication failed / operation not allowed`）
- `/home/lhy/.config/roms/era5.env`（mode 600，2026-10-15 16:38 更新）→ **认证通过**，
  请求 `0a813dcd-9a66-4cf6-9dae-775f61b9835b` 正常提交
- 两份文件格式相同（`url:` + `key:`，key 均为 36 字符），但 key 值不同

**待决**
1. `credentials/era5_key.txt` 是应该更新为有效 key，还是删除以免误用？
2. `download_era5_staged.py` 默认不读配置里的 `era5.credentials_file`，必须显式传
   `--credentials-file` 或设 `CDSAPI_KEY`；是否应让默认路径也回退到 `~/.config/roms/era5.env`？

### 关于 CDS 队列延迟（已知风险，非新问题）

2026-10-15 上午的微型尝试中，大气请求成功、辐射请求长期停在 `accepted`（`era5_request_diagnosis.json`）。
本轮全量请求同样在 `accepted` 排队。辐射请求是全流程最可能的时间瓶颈。

---

## 附：已完成且无需决策的修复（本轮）

1. **CI 路径过滤补漏**：`.github/workflows/japan-sea-ud1k-bry-schema-contract.yml` 的 `push` 与
   `pull_request` 两个 `paths` 列表均补入 `Data_pre/core/case_context.py`、
   `Data_pre/core/roms_preprocessing_utils.py`、`ROMS_Build/env/**`、
   `ROMS_Build/scripts/build/verify_case_build.py`、`ROMS_Build/scripts/env/validate_toolchain.py`、
   `configs/templates/**`。
2. **子网格模板参数化**：`configs/templates/external_single_grid/external_test_config.json.template`
   把写死的 `"header_template": "japan_sea.h"` 改为 `"${CASE_SLUG}.h"`，
   并把 ES3K 专属坡度闸门 `max_rx0: 0.35 / max_rx1: 8.0 / max_orthogonality_deg: 1.0`
   改为 `${MAX_RX0}` / `${MAX_RX1}` / `${MAX_ORTHOGONALITY_DEG}`
   （ES3K 实测 `rx1 = 7.87`，已逼近 8.0 上限，其他子网格照抄会误触）。

## 附：跨案例影响评估（结论：无污染）

`ROMS_Nesting/Data_pre/impl/preprocessing/create_pilot_infile.py` 是**独立 vendored 副本**（commit `814ee1d`）。
FDNPP / LAHAGUE / WOLSONG 使用顶层 `Data_pre/` 下的另一份未改动副本。已逐行比对，本次改动不影响其他案例。
若将来回填到共享副本，需注意三处语义变化：

1. `source.release_mode` 以 `"disabled"` 开头时把 `river` 置为 `"none"`（当前各案例均为
   `constant_rate_over_year`，暂不触发，但未来任何 `disabled...` 案例会被静默去掉源项文件）；
2. 移除 smoke → analytical 的降级，`smoke` 语义从「无数据自检」变为「需要外部强迫」；
3. `DSTART` 回退由 `common_year_offset_days(start)` 改为 `to_mjd(start)` —— 相对
   `TIME_REF = 18581117.0d0` 这是**修正**，但 ini 缺失时生成结果会变。
