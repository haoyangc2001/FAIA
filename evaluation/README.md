# FAIA Evaluation Module

## 目标

`evaluation/` 是 FAIA 项目的第五阶段评估与实验系统，用于统一登记、汇总和比较 `data/`、`assortment/`、`simulation/`、`inventory/` 四条产线的实验结果。

评估系统是项目的统一裁判台。它不生成业务数据，不修改选品结果，不改写库存策略，也不替代 simulation 做回放；它只读取各阶段已经发布的 manifest、metrics 和 validation summary，在同一数据版本、同一时间窗口、同一仿真规则和同一成本口径下比较实验效果。

## 定位与边界

评估系统负责：

```text
汇总 data_version 与数据质量报告
汇总 assortment 选品评估结果
汇总 simulation 回放指标
汇总 inventory 策略产物和回放指标
维护 experiment_registry
输出统一 metrics_summary
生成 baseline comparison_table
生成 evaluation_report
校验同一次 evaluation 内的版本、窗口和指标口径是否可比
```

评估系统不负责：

```text
重新生成 synthetic data 或真实数据
重新训练选品、预测或库存模型
修改 simulation 规则
修改 assortment_result 或 transfer_recommendation
绕过 manifest 直接比较裸文件
把不同 data_version、split_version、simulation_rule_version 或 cost_config_version 的结果强行比较为同一组实验
```

## 目录说明

```text
evaluation/
├── README.md
├── configs/
│   └── evaluation_default.yaml
├── schemas/
│   ├── evaluation_manifest.schema.yaml
│   ├── experiment_registry.schema.yaml
│   ├── metrics_summary.schema.yaml
│   └── comparison_table.schema.yaml
├── src/
│   ├── __init__.py
│   ├── common.py
│   ├── metrics.py
│   ├── compare.py
│   ├── collect.py
│   ├── report.py
│   └── validation.py
├── scripts/
│   ├── collect_results.py
│   ├── build_report.py
│   └── validate_evaluation_run.py
├── tests/
├── runs/
│   └── eval_v001_baseline/
│       └── evaluation_manifest.yaml
└── reports/
```

各目录职责如下：

```text
configs/
存放统一评估配置，固定 evaluation_id、data_version、split_version、evaluation_window、baseline 方法矩阵和 manifest 扫描范围。

schemas/
存放评估系统契约。当前定义 evaluation_manifest、experiment_registry、metrics_summary 和 comparison_table。

src/
存放结果收集、指标归一、对比、报告和校验逻辑。

scripts/
存放 collect_results、build_report 和 validate_evaluation_run 等 CLI。

runs/
按 evaluation_id 保存每次综合评估的 registry、metrics、comparison 和 evaluation_manifest。

reports/
存放综合评估报告和校验报告。
```

## 统一实验协议

一次 evaluation 必须固定下面的实验口径：

```text
evaluation_id
综合评估 ID。默认第一版为 eval_v001_baseline。

evaluation_version
评估协议版本。默认第一版为 evaluation_protocol_v001。

data_version
输入数据版本。默认使用 v001。

split_version
时间切分版本。默认使用 split_v001，对应 data/splits/v001。

evaluation_split
评估切分。默认使用 test。

evaluation_window
评估日期窗口。默认使用 2026-06-03 到 2026-06-29。

assortment_version
库存和仿真实验消费的选品版本。

inventory_version
库存策略版本。没有库存 run 时也必须在协议中显式声明目标版本。

simulation_rule_version
仿真规则版本。

cost_config_version
成本配置版本。第一版通过 cost_config 路径和 data_version 固定口径。
```

同一个 `evaluation_id` 内，默认要求这些字段一致：

```text
data_version
split_version
evaluation_window
simulation_rule_version
cost_config_version
```

如果某个上游实验尚未产出，评估系统必须把它登记为 `missing` 或 `not_run`，不能静默跳过。当前 v001 默认链路中 `inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml` 已经存在，inventory 行登记为 `available/PASS`。

## Manifest 协议

每次综合评估写入：

```text
evaluation/runs/<evaluation_id>/evaluation_manifest.yaml
```

第一版 manifest 至少记录：

```yaml
evaluation_id: eval_v001_baseline
evaluation_version: evaluation_protocol_v001
status: protocol_defined
config: evaluation/configs/evaluation_default.yaml
run_dir: evaluation/runs/eval_v001_baseline
protocol:
  data_version: v001
  split_version: split_v001
  evaluation_split: test
  evaluation_window:
    start_date: 2026-06-03
    end_date: 2026-06-29
  assortment_version: assortment_hybrid_v001
  inventory_version: inventory_base_stock_v001
  simulation_rule_version: sim_rule_v001
  cost_config_version: cost_config_v001
manifest_sources:
  data:
    - data/versions/v001/manifest.yaml
  assortment:
    - assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml
  simulation:
    - simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml
  inventory:
    - inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml
```

collector、report builder 和 validator 会回填：

```text
experiment_registry.csv
metrics_summary.csv
comparison_table.csv
evaluation_validation_summary.json
evaluation_report.md
```

## 结果收集

当前第一版 collector 只读取各阶段 manifest、metrics JSON 和 validation summary 的元数据，不读取大 CSV 正文。真实端到端验收仍建议先 materialize 或重新生成 v001 数据，再运行 `make full`，确保所有上游 manifest 与指标来自同一次可复现流水线。

运行命令：

```bash
PYTHONPATH=. python3 evaluation/scripts/collect_results.py --config evaluation/configs/evaluation_default.yaml
```

输出文件：

```text
evaluation/runs/eval_v001_baseline/experiment_registry.csv
evaluation/runs/eval_v001_baseline/metrics_summary.csv
evaluation/runs/eval_v001_baseline/comparison_table.csv
evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
```

`metrics_summary.csv` 使用长表结构，每行是一个 `metric_name + metric_value`，并保留 stage、experiment、method、版本、评估窗口、metric_level 和 source_path。这个形态可以同时容纳数据规模、选品、仿真和库存指标。

如果某个声明的上游 manifest 不存在，collector 会在 `experiment_registry.csv` 里写入 `run_status=missing`，并在 `comparison_table.csv` 中保留对应 baseline 或组合实验的缺失状态。当前 v001 验收中 data、assortment、simulation、inventory 四类上游 registry 行均为 `available`。

## 报告与校验

生成综合评估报告：

```bash
PYTHONPATH=. python3 evaluation/scripts/build_report.py \
  --manifest evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
```

报告输出：

```text
evaluation/reports/eval_v001_baseline_report.md
```

报告包含实验目标、版本协议、实验注册表、数据层指标、主指标对比、trade-off 分析、异常分析和结论。当前 base-stock inventory 产物已可用，但默认配置没有开启库存策略 simulation 回放，因此库存策略服务率/成本类运营指标仍会显示为缺失；这表示“回放指标待增强”，不是 inventory run 缺失。

运行评估校验：

```bash
PYTHONPATH=. python3 evaluation/scripts/validate_evaluation_run.py \
  --manifest evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
```

校验输出：

```text
evaluation/runs/eval_v001_baseline/evaluation_validation_summary.json
evaluation/reports/eval_v001_baseline_validation_report.md
```

校验覆盖：

```text
必需文件存在
manifest row_counts 与 CSV 实际行数一致
registry 和 metrics 的 data_version、split_version、evaluation_window、simulation_rule_version、cost_config_version 一致
核心指标完整性
ratio 指标范围
count、qty、cost 非负
demand conservation
cost conservation
缺失上游实验显式登记
```

对于 inventory 这类短策略窗口实验，validator 允许 `effective_end_date` 早于 evaluation test 窗口结束日期，但必须从统一 evaluation start date 开始，并落在统一 evaluation window 内。

## 当前阶段状态

当前已完成：

```text
5.1 明确评估系统定位与边界
5.2 创建 evaluation/ 轻量目录骨架
5.3 定义 evaluation_default.yaml、evaluation_manifest 初始协议和 registry/manifest schema
5.4 定义统一 metrics_summary 长表 schema 和 comparison_table schema
5.5 从 baseline_matrix 生成 comparison_table.csv
5.6 实现 manifest collector，输出 experiment_registry.csv 和 metrics_summary.csv
5.7 生成 evaluation_report.md，包含主指标、trade-off、异常分析和结论
5.8 实现 evaluation validation summary/report，并回写 evaluation_manifest
```

当前第一版输出：

```text
experiment_registry.csv: 4 rows
metrics_summary.csv: 638 rows
comparison_table.csv: 14 rows
evaluation_validation: PASS
missing_runs: 0
latest_checked_at: 2026-06-28T21:00:02
```

最新端到端验收口径：

```text
pipeline_run_id: pipeline_20260628_204301
collect_results: passed
build_evaluation_report: passed
validate_evaluation: passed
data registry: available/PASS
assortment registry: available/PASS
simulation registry: available/PASS
inventory registry: available/PASS
evaluation_validation_failed_checks: 0
```
