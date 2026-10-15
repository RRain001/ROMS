# JAPAN_SEA ES3K：第二轮复审（P0-REV / P1-REV）整改报告

- 日期：2026-10-15
- 分支：`codex/es3k-i3-wet-domain-audit-20261014`（PR #3，保持 **Draft**，未合并 `main`）
- 依据：PR #3 评论 `#issuecomment-6193566184`（第二轮独立复审）
- 复审裁决：`REMEDIATION_SUBSTANTIALLY_COMPLETE_BUT_FINAL_ACCEPTANCE_HOLD`
- 本轮范围：**P0-REV-1/2 必修 + P1-REV-3/4/5 修复**。未运行任何 ROMS 时间积分。

## 一、结论

| 项 | 裁决要求 | 本轮处理 |
|---|---|---|
| P0-REV-1 | 潮汐检查并入最终 PASS/FAIL + 故障注入负向测试 | **已修** |
| P0-REV-2 | 五模式 CPP/产物归属严格化 + 负面测试 | **已修** |
| P1-REV-3 | 分别记录 HEAD、证据按 build_kind/SHA 不可混淆 | **已修** |
| P1-REV-4 | 关闭 BRYNAME 绕过、补必需轴、fail-open fallback | **已修**（含 `pilot_1day`/`online_*`，未推迟） |
| P1-REV-5 | 跨 checkout 一致性 | **已修**（改为 fail-closed 拒绝） |

提交：`c2c20ae`（P0-REV）、`f4f1911`（P1-REV）。

## 二、P0-REV-1：潮汐证据进入最终裁决

**问题**：`verify_case_build.py` 中 `tide_issues` 只写入报告字段，没有 `issues.extend(tide_issues)`，因此移除 `set_tides.f90` 的关键签名等情形仍会返回 `CASE_BINARY_AND_CPP_LINK_PASS`。

**修复**：`issues.extend(tide_issues)`，直接进入 `status` 与退出码。

**故障注入负向测试**（`ROMS_Build/tests/test_verify_case_build.py`，共 14 项）：

| 注入 | 断言 |
|---|---|
| 从 `set_tides.f90` 删除 `UV_Tmajor` | `tide_build_issues` 非空，`UV_TIDES` 出现在顶层 `issues`，status ≠ PASS |
| 删除 `set_tides.f90` | status ≠ PASS |
| 删除 `tides_date.o` | status ≠ PASS |
| 注入 `NESTING` 到 `checkdefs.f90` | `forbidden_options_present` 含 `NESTING`，status ≠ PASS |
| 抹掉必需 CPP（`MASKING`） | 顶层 issues 含 `MASKING`，status ≠ PASS |

## 三、P0-REV-2：只有产出该模式的构建才能声称 PASS

**问题**：`verify_mode()` 复用被审查构建的 `active_cpp`，Debug 审查会用 Debug 的 CPP 为 Release 模式背书；只确认了 `resolve_binary_path()` 找得到文件和 `declared_executables()` 找得到名字声明。

**修复**：

1. 每个 mode 依据其 `binary_name` 归属到声明它的 build config。
2. **非本构建**服务的模式 → `NOT_CHECKED_IN_THIS_BUILD`，不进入 PASS，顶层 `all_modes_covered_by_this_run: false`，并列出 `modes_not_checked_in_this_build`。
3. **本构建**服务的模式 → 额外要求其可执行文件 SHA256 等于该构建**provenance 中记录的** SHA256。
   关键点：对同一文件重新取指纹毫无意义（被掉包或手工改过的二进制与自身自洽），必须以 provenance 为外部参照。

**实测（真实 case，两套均重新完整编译）**：

```
======= DEBUG (roms_build_config.json) =======
status = CASE_BINARY_AND_CPP_LINK_PASS      all_modes_covered_by_this_run = false
  smoke                PASS                       binary=romsM_japan_sea
  external_startup     PASS                       binary=romsM_japan_sea
  external_1h          NOT_CHECKED_IN_THIS_BUILD  binary=romsM_japan_sea_release
  external_6h          NOT_CHECKED_IN_THIS_BUILD  binary=romsM_japan_sea_release
  external_24h         NOT_CHECKED_IN_THIS_BUILD  binary=romsM_japan_sea_release

======= RELEASE (roms_build_config.release.json) =======
status = CASE_BINARY_AND_CPP_LINK_PASS      all_modes_covered_by_this_run = false
  smoke                NOT_CHECKED_IN_THIS_BUILD  binary=romsM_japan_sea
  external_startup     NOT_CHECKED_IN_THIS_BUILD  binary=romsM_japan_sea
  external_1h          PASS                       binary=romsM_japan_sea_release
  external_6h          PASS                       binary=romsM_japan_sea_release
  external_24h         PASS                       binary=romsM_japan_sea_release
```

两次运行合起来覆盖全部五个模式，任一单次运行都不声称不归它的模式。

**产物**（重建后）：

| 构建 | 产物 | 字节 | SHA256 |
|---|---|---|---|
| Debug | `bin/romsM_japan_sea` | 53,701,592 | `3d458b5dbb211cd36de093b21c0228281d8e0f4e9cdeca94528f439f3ec1804d` |
| Release | `bin/romsM_japan_sea_release` | 8,757,648 | `d95ca605065ce7d4550c1dc6f89bed9ef96c7e83f1114ed8c402794518ef9347` |

**负面测试**：移除 Release 可执行文件、互换两个可执行文件、手工篡改产物、删除 provenance 记录 —— 四种情形均被检出，不再误判 PASS。

> 说明：上一轮我因测试卫生修正清空了真实 case 的 provenance。本轮**重新完整编译了两套构建**以生成真实 provenance，未手工补写任何记录。

## 四、P1-REV-3：HEAD 与证据分离

**问题**：`_git_head(context.roms_src)` 可能是冻结 ROMS 源码 checkout 的 HEAD，而非承载本次修复的 `RRain001/ROMS` 分支；且 Debug/Release 多次调用会覆写同一份 `build_verification.json` / `binary_links.log` / `compiler_versions.log`。

**修复**：

- 报告分别记录 `workflow_repo` 与 `roms_source_repo`，各含 `path` / `head` / `dirty`。
- 证据文件名带 build kind 与产物 SHA 前缀，两者永不互相覆盖：
  - `build_verification.<kind>.<sha12>.json`
  - `binary_links.<kind>.<sha12>.log`
  - `compiler_versions.<kind>.<sha12>.log`

测试 `test_evidence_files_are_distinct_per_build` 断言两套构建的证据路径不同且均已落盘；
`test_workflow_and_roms_source_heads_are_reported_separately` 断言两个仓库字段各自含 path/head/dirty。

## 五、P1-REV-4：关闭绕过路径

**问题一：BRYNAME=none 可绕过外部闸门。**
`validate_external_forcing_coverage()` 在无 `BRYNAME` token 时直接返回成功，且 `test_bryname_none_is_not_checked` 将其写作正常情形。

修复后：

- 声明为 `external_*` 的模式**必须**给出边界文件，`none` 即为 issue；
- 非 external 模式若 infile 要求数据边界（`Cha`/`Fla`/`Nud`/`RadNud`/`Rad`/`Gra`/`Mar`）也必须给出；
- 仅真正闭合或周期的设置（`Clo`/`Per`）豁免。

**问题二：只检查「已存在」的时间轴。**
`boundary_time_variables()` 只枚举存在的轴，因此「有一个合法 `zeta_time`、但 `temp_time` 缺失」看起来没问题。

修复：新增 `required_time_axes()`，从**场变量本身**推导必需轴
（`ubar`/`vbar`→`v2d_time`，`u`/`v`→`v3d_time`，`temp`→`temp_time`，`salt`→`salt_time`，`dye_*`→`dye_time`；
`dye_west_01` 这类序号在后缀之后的命名已正确处理）。缺轴即报 `UNKNOWN` 并列出是哪些场要求该轴。

**问题三：`external_model_stop()` 的历史 fail-open。**
裁决允许「另开兼容性任务，至少在报告中明确仍未整改」。本轮**直接修掉**：
该函数在无法判定外部覆盖时返回 `None`，`pilot_1day` / `online_*` 这些会自动缩短的模式随即**拒绝**
（`require_boundary_stop`），不再静默跑满配置窗口、越过边界数据末端。

`smoke` 不做自动缩短，因此仍可生成；但**任何**以 `--forcing-mode external` 生成的计划现在都携带实测覆盖证据，
无真实文件时被打上 `FORCING_UNVERIFIED`（不再只限 `external_*`）。

**负面测试**：external 模式 BRYNAME=none、闭合模式带数据边界却无 BRYNAME、场存在但缺轴。
另保留「闭合的非 external 模式无 BRYNAME 允许通过」的正向用例。

**真实数据上的实测证据**（重新生成的 `.in` 头部，smoke 与 external_* 均含）：

```
! boundary coverage evidence (measured, not assumed):
!   file = .../input/roms_bdy_japan_sea_es3k_test_glorys12v1_20180102_20180103.nc
!   status = OK
!   required window = 2018-01-02T00:00:00 -> 2018-01-02T00:00:50     (smoke)
!   dye_time:  n=2 units='days since 1858-11-17 00:00:00' calendar='gregorian' ... strictly_increasing=True
!   salt_time / temp_time / v2d_time / v3d_time / zeta_time: 同上
```

## 六、P1-REV-5：跨 checkout 不再可能混用

**问题**：`init_nesting_root()` 接受任何含三目录的 checkout，但 `DATA_PRE_ROOT`、`CASES_ROOT`、
`IMPLEMENTATION_DIR` 仍相对**正在运行的模块**解析 —— 会形成「旧 checkout 的配置/代码 + 新 checkout 的数据」，
与模块自身注释「one process never mixes two different worktrees」矛盾。

**修复**：采用裁决给出的第一种方案 —— 要求 root 与实际模块 checkout 一致，否则 **fail-closed**，
错误信息说明不支持跨树重绑定并给出可行做法（从目标树运行或 unset）。本 checkout 被显式设置时仍被尊重。

测试 `test_a_different_checkout_fails_closed` 断言另一个合法三目录 checkout 被拒绝、错误信息含
`different checkout` 与 `Cross-checkout rebinding is not supported`、且失败时环境未被改写。

## 七、回归测试

| 套件 | 上轮 | 本轮 |
|---|---|---|
| `Data_pre/tests` | 341 | **344 — OK** |
| `ROMS_Build/tests` | 6 | **20 — OK**（新增 14 项故障注入） |
| `ROMS_Run/tests` | 10 | **12 — OK** |
| `git diff --check` | PASS | PASS |
| `py_compile` | PASS | PASS |
| `check_isolation.py` | PASS | PASS |

CI 工作流补入 `test_verify_case_build.py`（paths 各 54 条 + 新增一条测试调用）。无不可解释回归。

## 八、第二阶段状态（维持不变）

**`PHASE2_HYDRO_BLOCKED_REAL_FORCING_MISSING`**。

- GLORYS ini（212 MB）/ bry（1.8 MB）/ TPXO tides（136 MB）已就绪并通过校验。
- **ERA5 辐射请求自 20:22 起一直停在 CDS `accepted`**（至本轮结束已逾 2 小时）；大气已下载但在脚本临时目录中，
  须待辐射完成才统一写盘。
- 未启动 startup / 1h / 6h / 24h，未声称任何水动力通过。
- 未用合成 CI PASS 代替真实构建：两套二进制的证据来自本机真实 `ifort` + Intel MPI 编译与链接审计。

## 九、仍未完成 / 明确声明

- 未运行任何 ROMS 时间积分。
- 未做 Debug/Release 前若干时间步状态对比（依赖 ERA5）。
- `smoke` 生成的未验证计划打标已覆盖，但 `pilot_1day`/`online_*` 因无真实边界文件将直接拒绝生成；
  这两个模式在 JAPAN_SEA 的 `run_modes` 中并未启用，故无实际影响。
- ES3K 静态指标 `rx0=0.241741`、`rx1=7.869365` 接近阈值 8；本报告不据此宣布数值稳定或物理可接受。
