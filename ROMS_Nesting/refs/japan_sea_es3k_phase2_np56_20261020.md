# JAPAN_SEA ES3K：第二阶段受控试验（np=56 / 7×8）

- 日期：2026-10-20
- 分支：`codex/es3k-i3-wet-domain-audit-20261014`（PR #3，Draft）
- 试验窗口：`2018-01-02T00:00:00 → 2018-01-03T00:00:00`（长关卡按 1h / 6h 截取）
- 并行分解：**np=56，NtileI=7，NtileJ=8**（与 FDNPP 一致）
- 依据：PR #3 复审 `#issuecomment-6205558777` 批准的受控启动顺序与 stop gate

## 一、结论

| 关卡 | 模式 | 构建 | 退出码 | 墙钟 | 结论 |
|---|---|---|---|---|---|
| gate1_smoke | smoke（5 步） | Debug | **0** | 122.97 s | `PASS_WITH_EVIDENCE` |
| gate2_startup | external_startup（5 步） | Debug | **0** | 111.08 s | `PASS_WITH_EVIDENCE`（输出元数据 `NOT_ASSESSED`） |
| gate3_1h | external_1h（360 步） | Release | **0** | 537.90 s | `PASS_WITH_EVIDENCE` |
| gate4_6h | external_6h（2160 步） | Release | **0** | 3225.46 s | `PASS_WITH_EVIDENCE` |
| gate5_24h | external_24h（8640 步） | Release | — | — | **`NOT_RUN`**（待复审就分解变更作出裁定后决定） |

四关均按顺序执行，脚本在任一关非零退出时立即中止后续关卡；本轮四关全部退出码 0。

## 二、基准（`logs/phase2/baseline.json`）

| 项 | 值 |
|---|---|
| workflow HEAD | `c4e2dc3`（`roms_src/roms` 与之同仓库，HEAD 相同） |
| 活动网格 | `df7fd493e81a379e…`（38,616,410 B，732×464，193,920 湿点） |
| ini / bdy | `135344c1012c10d5…`（212.6 MB）/ `7854db2601e6f5ff…`（1.84 MB） |
| atm / rad | `813bc9d5bafc74b2…`（791.3 MB）/ `eb0a9c947c16bbe6…`（239.3 MB） |
| tides | `6f016acd9c8a608c…`（136.7 MB） |
| Debug 二进制 | `3d458b5dbb211cd3…` 53,701,592 B，`-g -check all -check bounds -traceback -check uninit -gen-interfaces` |
| Release 二进制 | `d95ca605065ce7d4…` 8,757,648 B，`-ip -O3 -traceback -check uninit` |
| 参数 | DT=10 s、NDTFAST=20、tiles 7×8=np 56 |

五模式 `validate_run_prereqs` 全部 `status: OK`，`required_np: 56`。

## 三、逐关证据

### gate1_smoke（Debug）

- `ROMS: DONE 2026-10-20 09:28:01`，6 行时间步表（步 0–5），走到 `2018-01-02T00:00:50`
- 错误扫描（FATAL/BLOWUP/NaN/Infinity/forrtl/abort/Segmentation）：**0**
- CFL 最大值：`Cu=5.811866E-03` / `Cv=2.187989E-03` / `Cw=2.716666E-01`；MaxSpeed 1.561035
- NET_VOLUME：`2.125096E+15` 全程不变
- 输出 `his_japan_sea_smoke.nc`：2 条记录，**0 个非有限值**
- 量程（排除陆地填充值）：zeta −2.244~+2.305 m；u −0.569~+1.447；v −0.937~+1.246 m/s；temp −1.966~+19.16 °C；salt 29.16~35.43
- 边界带 zeta：west[+0.030,+0.036]、east[−0.614,+1.175]、south[−0.123,+0.498]、north[−0.511,+0.516]；内部[−2.244,+2.305] —— **边界带均窄于内部**

### gate2_startup（Debug）

- `ROMS: DONE 2026-10-20 09:29:53`，6 行，走到 `2018-01-02T00:00:50`
- 错误扫描：**0**；CFL 与 netvol 与 gate1 完全相同（同一配置同一轨迹）
- **输出元数据 `NOT_ASSESSED`**：该模式的 `.in` 为 `NHIS=360`、`NRST=8640`，均大于 `NTIMES=5`，ROMS 在 5 步内不写出任何 NetCDF 文件。这是既定配置事实，本轮未修改 `.in` 去"修"它，以免破坏冻结基准。该关的评估依据是 ROMS 日志；字段量程沿用同配置同轨迹的 gate1 输出。

### gate3_1h（Release）

- `ROMS: DONE 2026-10-20 09:38:51`，361 行，走到 `2018-01-02T01:00:00`
- 错误扫描：**0**
- CFL 最大值：`Cu=6.566233E-03` / `Cv=2.580679E-03` / `Cw=2.716666E-01`；MaxSpeed 2.024728
- NET_VOLUME：`2.125096E+15 → 2.125092E+15`，相对漂移 **−1.9e-6**
- 输出：2 条记录，**0 个非有限值**；zeta −1.264~+1.705 m；u −0.822~+1.661；v −1.091~+1.247 m/s；temp −2.587~+19.16 °C；salt 29.16~35.43
- 边界带 zeta：west[−0.013,+0.015]、east[−0.317,+0.655]、south[−0.137,+0.257]、north[−0.234,+0.098]；内部[−1.264,+1.705] —— 边界带均窄于内部

### gate4_6h（Release）

- `ROMS: DONE 2026-10-20 10:32:36`，2161 行，走到 `2018-01-02T06:00:00`
- 错误扫描：**0**
- CFL 最大值：`Cu=6.566233E-03` / `Cv=2.857179E-03` / `Cw=2.716666E-01`；MaxSpeed 2.024728
- NET_VOLUME：`2.125096E+15 → 2.125086E+15`，相对漂移 **−4.7e-6**，过程非单调（1e-5 量级振荡）
- 动能轨迹：2.099e-3 →（1h）2.207e-3 →（3h）4.134e-3 →（4.5h 峰值）5.114e-3 →（6h）4.837e-3 —— **见顶后回落**，为 `RAMP_TIDES` 驱动的 spin-up 过渡，非失控增长
- 输出：7 条记录，**0 个非有限值**；zeta −1.442~+1.784 m；u −1.61~+1.667；v −1.171~+1.852 m/s；temp −2.813~+19.22 °C；salt 29.16~35.43
- 边界带 zeta：west[−0.191,−0.150]、east[−0.099,+0.561]、south[−0.246,+0.041]、north[−0.294,+0.140]；内部[−1.278,+1.421] —— 边界带均窄于内部

## 四、分解不变性（逐位比对）

np=56 与此前 np=4 的完整时间步表**逐位相同**：

| 关卡 | 行数 | 比对结果 |
|---|---|---|
| external_1h | 361 | **IDENTICAL** |
| external_6h | 2161 | **IDENTICAL** |

比对内容为每一行的步号、模型时刻、KINETIC_ENRG、POTEN_ENRG、TOTAL_ENRG、NET_VOLUME。

这同时说明：此前在 np=4 下取得的 smoke / startup / 1h / 6h 证据，与 np=56 下的对应结果
在打印精度内完全一致；改分解没有改变物理结果。**但本报告仍以 np=56 的实测数据作为本轮证据**，
不以后者替代前者。

## 五、加速比（实测）

| 关卡 | np=4 | np=56 | 倍数 |
|---|---|---|---|
| external_startup | 1108.58 s | 111.08 s | **10.0×** |
| external_1h | 2416.73 s | 537.90 s | **4.5×** |
| external_6h | 64,038.37 s（含 MITgcm 争用） | 3225.46 s | 约 4.6×（对比空闲 np=4 外推值） |

np=4 的 6h 是在另一作业占满 56 核时跑的，不能直接与 np=56 的空闲测量相比，故按空闲速率外推标注。

## 六、边界与未完成项

- **未运行 24h 关卡**。复审批准的顺序要求 6h 通过后再跑 24h，但本轮并行分解已由 2×2 改为 7×8，
  复审评论 #6281134932 第三节已请求裁定；在获得答复前不擅自启动 24h。
- **完整开边界体积收支 `NOT_ASSESSED`**：`.in` 中 `Hout(idTsur)==F`，且未开启开边界通量诊断；
  仅以 `NET_VOLUME` 漂移作为体积守恒的可用度量。
- 本报告只说明 ES3K 测试窗口内的数值启动与稳定性，**不推断**正式多年模拟、海峡水动力科学质量、
  UD1K/300 m 嵌套耦合或示踪剂结果已验收。
- 未修改冻结 ROMS 源码，未启用在线 `contact.nc` 嵌套，PR 保持 Draft，未合并 `main`。

## 七、证据路径

```
projects/JAPAN_SEA/logs/phase2/baseline.json
projects/JAPAN_SEA/logs/phase2/np56/gates.txt
projects/JAPAN_SEA/logs/phase2/np56/gate1_smoke/       {exit_code, run.stderr, roms.log}
projects/JAPAN_SEA/logs/phase2/np56/gate2_startup/     {同上}
projects/JAPAN_SEA/logs/phase2/np56/gate3_1h/          {同上, analysis.json}
projects/JAPAN_SEA/logs/phase2/np56/gate4_6h/          {同上, analysis.json}
projects/JAPAN_SEA/logs/phase2/np56/smoke.analysis.json
projects/JAPAN_SEA/output/                             np=56 的 his/avg/dia/rst（33 G）
```

（`projects/` 受 `.gitignore` 约束，以上为运行证据，不入库；本文件与 `refs/` 下的记录入库。）

> **2026-10-20 更新**：np=4 的原始结果目录 `output/np4_baseline/`（95 G）已按用户指示清理删除。
> 第四节"逐位一致"的结论不依赖那些文件 —— 它比对的是 np=4 与 np=56 的 **ROMS 时间步日志**
> （`logs/phase2/gate3_1h/roms.log`、`logs/phase2/gate4_6h/roms.log` 与
> `logs/phase2/np56/gate3_1h/roms.log`、`logs/phase2/np56/gate4_6h/roms.log`），这些日志均已保留。
> np=4 的 NetCDF 结果文件不再存在，若需字段级比对须重跑。
