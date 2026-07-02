# Data_pre 多地区通用框架改造计划

## Summary

将 `/home/lhy/ROMS/Data_pre` 从“以 Fukushima 为中心的共享预处理目录”重构为“支持多个地区案例并行的通用 ROMS 预处理框架”。本次目标按“完整多案例框架”执行，并按你的选择直接切换到新通用规则，不再优先保留 Fukushima 专属命名和旧兼容入口。

职责边界补充：

- `Data_pre` 包含下载、离线共享数据集定位与裁剪、staged raw 整理、网格与地形预处理、ROMS-ready 输入生成、校验、运行输入文件装配
- `Data_pre` 不包含 ROMS 编译、MPI/集群启动、实际积分运行、运行期稳定性调参
- 框架终点是“交付一套通过校验的 ROMS 运行输入”，而不是“模型已经成功跑完”

计划产出应包含一份保存到 `/home/lhy/ROMS/Data_pre/` 的总说明计划文档，实施后 `Data_pre` 应满足：

- 新案例只需新增 `cases/<case_name>/config` 和最少量案例文档即可接入。
- 公共脚本、输出命名、标题、默认路径不再硬编码 `Fukushima`、`202401`、`gebco_fukushima`、`ocean_fukushima_*`。
- 公共逻辑通过案例配置驱动，支持不同区域、时间窗、源项、数据集来源和输出命名。
- 旧 Fukushima 路径和旧文件名不再作为优先兼容目标；需要时通过迁移文档说明新规则。

## Key Changes

### 1. 抽象案例元数据，建立统一 Case Schema

将现有 `project_parameters.json` 从“项目参数文件”升级为“案例主配置”，统一承载：

- `case.name`
- `case.slug`
- `case.title`
- `case.cpp_name`
- `case.description`
- `domain.*`
- `time.*`
- `vertical.*`
- `source.*`
- `naming.*`
- `paths.*`

新增或规范的关键字段：

- `case.slug`
  用于所有输出文件前缀、运行输入文件名、日志名、标题模板。
- `case.cpp_name`
  取代硬编码 `FUKUSHIMA_202401`。
- `naming.grid_subset_name`
  例如 `gebco_<case_slug>.nc`。
- `naming.roms_prefix`
  例如 `<case_slug>`，统一生成 `ocean_<case_slug>_pilot_1day.in`、`his_<case_slug>_pilot.nc` 等。
- `source.kind`
  支持 `point_release`、`river_like_source`、`none`，替代 Fukushima 语义。
- `paths.global_bathymetry`
  指向 `/workspace/GEBCO/GEBCO_2026.nc` 这类共享大文件。
- `paths.case_root`
  不再把 `/home/lhy/ROMS/projects/fukushima_202401_50m` 写死在描述性文本里。

保留现有 `domain/time/vertical/source` 字段语义，但要求所有公共脚本只从新 schema 读值。

### 2. 重构 core，使路径、命名、标题全部案例驱动

重点改造：

- `core/case_context.py`
- `core/ocean_source_utils.py`
- `core/roms_preprocessing_utils.py`
- 需要时新增 `core/case_naming.py`

改造要求：

- `DEFAULT_CASE_NAME` 不再固定为 `fukushima_202401_50m`，改为：
  优先读 `ROMS_CASE_NAME`，否则要求显式传参，或使用可配置默认值文件。
- 增加统一命名接口，集中生成：
  - 输入文件名
  - 输出文件名
  - staged raw 文件名
  - run `.in` 文件名
  - log 文件名
  - title / global attributes
- `ocean_source_utils.py` 不再返回任何带 `fukushima` 或 `202401` 的默认路径；全部通过 `case.slug`、`time`、`ocean_source` 拼接。
- `roms_preprocessing_utils.py` 的标题、版本标识、默认网格路径、源项辅助路径都只依赖案例配置，不依赖案例名常量。

### 3. 系统性去 Fukushima 化实现层

对 `/home/lhy/ROMS/Data_pre/impl/preprocessing/` 做一次完整“案例语义清洗”，按以下规则处理：

- 所有脚本 docstring 改成区域无关描述。
- 所有 `ds.title`、`print()`、markdown 报告标题改为配置驱动。
- 所有默认输出文件名改为命名模板生成。
- 所有固定文件名改为通过 `case.slug + time label + data role` 生成。

优先处理的高影响脚本：

- `create_pilot_infile.py`
  目前硬编码最重；需完全改为模板化命名、标题、`MyAppCPP`、`RST/HIS/AVG/DIA/XTR/QCK` 输出名。
- `create_grid_from_bathymetry.py`
  默认 bathymetry 子集文件名改为 `naming.grid_subset_name`。
- `stage_and_subset_bathymetry.py`
  重命名为更通用的入口，例如 `stage_and_subset_bathymetry.py`；默认输出不再是 `gebco_fukushima.nc`。
- `create_ocean_ini_*` / `create_ocean_bry_*` / `create_atm_forcing_from_era5.py` / `create_tides_from_tpxo.py`
  清理标题和默认输出命名。
- `validate_staged_data*.py` / `validate_roms_ready_inputs.py`
  输出提示从 “Fukushima staged data validation” 改为通用案例标题。
- `create_source_timeseries.py` / `create_river_source_production.py` / `stage_source_discharge.py`
  文件名、标题、变量说明从 Fukushima 专项改成通用源项语义。

### 4. 统一 scripts 与 impl 的入口命名

`scripts/` 层要与通用框架目标一致，入口名也应去掉误导性的案例残留：

- `stage_and_subset_bathymetry.py`
  改为 `stage_and_subset_bathymetry.py`
- `create_pilot_infile.py`
  可保留，但生成的文件名不再含固定案例名
- 其余入口文件名尽量保持功能性命名，不含区域名

`entrypoint_runner.py` 继续作为包装器，但新通用规则下应：

- 支持 `--case-name`
- 支持 `--case-root`
- 可选支持 `--case-config`
- 不再假定 legacy `projects/<fukushima>/preprocessing` 必然存在

### 5. 重组文档体系和案例模板

文档层分两类：

- `Data_pre/docs/`
  只保留通用框架文档：
  - overview
  - case schema
  - bathymetry workflow
  - staged data conventions
  - naming rules
  - adding a new case
  - readiness report / run handoff conventions
- `cases/<case_name>/docs/`
  只保留案例专属说明

对现有文档的处理：

- `docs/workflow_fukushima.md`
  拆成通用工作流文档 + Fukushima 个案文档
- `README.md`
  改为框架导向，不再把 Fukushima 作为默认叙述主体
- `cases/fukushima_202401_50m/docs/*`
  保留，但明确标注为案例资料，而非框架标准文档

新增一个正式案例模板：

- `cases/_template/`
  含最小 `config/`
  含 `README_case.md`
  含命名字段示例
  含数据目录约定示例

### 6. 明确不保留旧 Fukushima 兼容层作为目标

由于你选择“直接切换新框架”，实施时应：

- 不再继续维护 `/projects/fukushima_202401_50m/preprocessing` 作为长期兼容入口
- 不再保证旧的 `ocean_fukushima_202401_*.in`、`roms_bdy_202401.nc`、`gebco_fukushima.nc` 是主命名
- 可以保留一份迁移说明文档，列出旧名到新名的映射，但实现上以新命名为准
- 如需短期过渡，只允许在文档里说明，不要求公共代码同时维护两套规则

## Public Interfaces / Types

实施后需要稳定下来的公共接口包括：

- 案例解析接口
  - `--case-name`
  - `--case-root`
  - 可选 `--case-config`
- 统一命名函数
  - 输入：`case slug + data role + source + time window + mode`
  - 输出：规范文件名 / 标题 / 日志名
- 案例主配置结构
  - `case`
  - `domain`
  - `time`
  - `vertical`
  - `source`
  - `naming`
  - `paths`
- bathymetry 入口默认行为
  - 优先使用共享全局地形路径
  - 输出案例子集文件名从配置读取
- run-support 入口默认行为
  - `.in` 文件名、输出产品名、标题、CPP 名全从配置读取

## Test Plan

### 1. 结构与接口验证

- `Data_pre/scripts/*` 全部 `--help` 可运行。
- `--case-name` 切换到不同案例时，路径和命名随之变化。
- `_template` 可复制为新案例并通过基础解析检查。

### 2. 命名与配置驱动验证

- 以 `fukushima_202401_50m` 为案例，重新生成：
  - bathymetry subset
  - grid
  - pilot `.in`
  - ini/bdy/atm/rad/tides/source 输出
- 检查输出名不再依赖硬编码字符串，而来自 `case.slug` 和命名规则。
- 新建一个最小虚拟案例名，例如 `test_region_202402`，仅做 dry-run，验证输出名全部切换。

### 3. 功能回归验证

- `create_grid_from_bathymetry.py --dry-run`
- `validate_staged_data.py`
- `validate_staged_data_deep.py`
- `validate_roms_ready_inputs.py`
- `create_pilot_infile.py --mode pilot_1day --forcing-mode external`

要求：

- 功能结果与改造前等价
- 仅命名、标题、配置来源发生变化
- 不引入新的路径硬编码

### 4. 文档与模板验证

- `README.md` 能指导用户从零创建一个新案例目录
- `_template` 中每个字段都有示例
- 通用文档不再以 Fukushima 作为默认主体叙述
- Fukushima 案例文档仍能独立描述该案例，而不污染通用文档

## Assumptions

- 本次计划仅制定方案，不在当前计划模式下写入 `/home/lhy/ROMS/Data_pre/`。
- 实施阶段允许直接切换到新命名和新配置结构，不要求长期维护旧 Fukushima 兼容层。
- `/workspace/GEBCO/GEBCO_2026.nc` 继续作为共享全局地形大文件默认来源。
- Fukushima 仍作为第一个正式案例保留，但不再作为框架中的隐式默认区域语义。
- 不要求一次性支持所有 ROMS 科学场景；本次通用化目标聚焦“多地区、多案例预处理框架”，不是求解器层修改。
