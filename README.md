# FAIA: Fulfillment-Oriented Assortment and Inventory Allocation

FAIA 是一个面向即时零售 RDC-FDC 两级仓网的工程化实验项目，用来研究两个核心决策：

1. 每个前置仓 FDC 应该经营哪些 SKU。
2. 在选品确定后，RDC 每天应该向各 FDC 分配多少库存。

项目已经拆成六个稳定工程域：数据、仿真、选品、库存分配、评估和工程化编排。当前 v001 原型已经完成真实端到端验收，可以从根目录重新生成数据、运行各阶段策略、收集评估结果并复现实验报告。

## 当前状态

```text
计划状态: Phase 1-6 全部完成，MVP 与 big_goal 已验收
最新端到端 run_id: pipeline_20260628_204301
pipeline 状态: passed
pipeline steps: 14/14 passed
evaluation_id: eval_v001_baseline
evaluation 状态: validated
inventory 状态: exp_inventory_v001_base_stock available/PASS
```

最新验收产物：

```text
artifacts/run_logs/pipeline_20260628_204301_summary.json
inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml
evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
evaluation/reports/eval_v001_baseline_report.md
```

## 快速开始

环境要求：

```bash
python3 --version
python3 -m pip install -e .
```

查看可用阶段：

```bash
make list-stages
```

先做一次不执行命令的编排检查：

```bash
make dry-run
```

运行完整 pipeline：

```bash
make full
```

也可以按阶段运行：

```bash
make data
make assortment
make simulation
make inventory
make evaluation
make test
```

所有根层命令默认读取 [configs/project.yaml](configs/project.yaml)。全链路 runner 位于 [scripts/run_full_pipeline.py](scripts/run_full_pipeline.py)，执行日志写入 `artifacts/run_logs/`。

## 数据与 LFS

仓库中的 CSV 大文件由 Git LFS 管理，规则见 [.gitattributes](.gitattributes)。如果要复用已经提交的 `v001` CSV，需要先拉取 LFS 对象：

```bash
git lfs pull
```

如果本地没有真实 CSV，只看到 `version https://git-lfs.github.com/spec/v1` 这类 pointer 内容，可以直接重新生成数据：

```bash
make data
```

`make full` 会按配置从数据阶段开始重新生成并串联后续阶段。

## 阶段目录

```text
FAIA/
├── README.md
├── Makefile
├── pyproject.toml
├── configs/
│   └── project.yaml
├── scripts/
│   └── run_full_pipeline.py
├── data/
├── simulation/
├── assortment/
├── inventory/
├── evaluation/
├── doc/
└── artifacts/
```

各阶段职责：

```text
data/
生成、加工、切分、校验和登记统一数据版本。

simulation/
在统一业务规则下回放库存、调拨、履约、缺货和成本。

assortment/
生成 FDC-SKU 选品结果，并输出可被库存和仿真模块消费的 assortment_result。

inventory/
基于选品结果、库存状态、需求预测和业务约束生成 RDC 到 FDC 的调拨建议。

evaluation/
汇总 data、assortment、simulation、inventory 的 manifest 和 metrics，输出统一实验比较。
```

每个阶段都保留独立 README、配置、schema、脚本、测试和 run/report 目录。根目录只负责编排，不替代阶段内部逻辑。

## 统一命令

根层 Makefile 当前提供：

```text
make setup        安装运行依赖
make data         生成、加工、校验和登记 v001 数据
make assortment   运行并校验选品实验
make simulation   运行并校验 no-transfer 仿真 baseline
make inventory    运行并校验 base-stock 库存 baseline
make evaluation   收集、报告并校验统一评估结果
make full         按 project.yaml 的 stage_order 运行全链路
make validate     对已发布产物重新执行校验
make test         运行各阶段单元测试
make dry-run      只打印全链路命令，不执行
```

`scripts/run_full_pipeline.py` 支持常用调度参数：

```bash
PYTHONPATH=. python3 scripts/run_full_pipeline.py --stages data,evaluation
PYTHONPATH=. python3 scripts/run_full_pipeline.py --from-stage assortment --to-stage evaluation
PYTHONPATH=. python3 scripts/run_full_pipeline.py --dry-run
```

## 版本口径

第一版默认工程口径由 [configs/project.yaml](configs/project.yaml) 固定：

```text
data_version: v001
split_version: split_v001
assortment_version: assortment_hybrid_v001
inventory_version: inventory_base_stock_v001
simulation_rule_version: sim_rule_v001
evaluation_id: eval_v001_baseline
```

各阶段输出 manifest，评估阶段通过 manifest 追溯实验版本和指标口径。当前 v001 默认 inventory run 已经生成并登记为 `available`；如果后续声明的新实验尚未产出，evaluation 仍会显式登记为 `missing` 或 `not_run`，不会静默跳过。

## 主要产物

```text
data/versions/v001/manifest.yaml
assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml
simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml
inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml
evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
evaluation/reports/eval_v001_baseline_report.md
```

## 验证命令

当前验收推荐使用：

```bash
make full
make validate
make test
```

`make validate` 会重新校验已发布产物，`make test` 会运行 simulation、assortment、inventory、evaluation 和根目录 integration tests。

## 文档

- 项目计划：[doc/plan/FAIA_project_plan.json](doc/plan/FAIA_project_plan.json)
- 实施说明：[doc/plan/FAIA_implementation_plan.md](doc/plan/FAIA_implementation_plan.md)
- Manifest 标准：[doc/engineering/manifest_standards.md](doc/engineering/manifest_standards.md)
- 日志与异常约定：[doc/engineering/logging_and_error_handling.md](doc/engineering/logging_and_error_handling.md)
- 参考论文 Markdown：[doc/material/Reference_Paper.md](doc/material/Reference_Paper.md)
- 参考论文 PDF：[doc/material/Reference_Paper.pdf](doc/material/Reference_Paper.pdf)
