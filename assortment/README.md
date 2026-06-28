# FAIA Assortment Module

## 目标

`assortment/` 是 FAIA 项目的第三阶段前置仓选品模块，用于解决“每个 FDC 应该放哪些 SKU”的问题。

本模块根据历史订单结构、候选 SKU 池、FDC 容量约束和未来已知需求信号，为每个 FDC、每个 `anchor_date` 生成可执行的 SKU assortment。选品结果会被后续 `simulation/` 和 `inventory/` 模块读取。

## 定位与边界

选品系统只解决“放什么”，不解决“放多少”。它输出 SKU-FDC 关系和排序结果，不直接输出库存数量、补货量或 RDC 到 FDC 的调拨量。

选品系统负责：

```text
读取 data/processed 和 data/features 中的候选、需求、订单结构和特征数据
构建每个 FDC、每个 anchor_date 的候选 SKU 池
计算每个 FDC 的选品容量 K
运行 Top-K、Reverse-Exclude、Hybrid Selection 和后续 ML-Top-K 方法
输出每个 FDC 的最终 SKU 集合、rank、score 和 source_tag
在验证或测试窗口评估订单结构覆盖率
记录 assortment_version、method_version、candidate_pool_version 和 manifest
```

选品系统不负责：

```text
决定每个 SKU 备多少库存
生成 RDC 到 FDC 的调拨量
回放库存消耗、到货、缺货和成本
修改原始订单需求
使用评估窗口之后的真实订单构建训练特征
绕过 SKU-FDC eligibility、FDC 容量和商品状态约束
```

## 目录说明

```text
assortment/
├── README.md
├── configs/
├── schemas/
├── methods/
├── models/
│   └── ml_topk/
├── src/
├── scripts/
├── tests/
├── runs/
└── reports/
```

各目录职责如下：

```text
configs/
存放选品运行配置，例如 data_version、anchor_date、历史窗口、评估窗口、K 计算规则和输出 experiment_id。

schemas/
存放候选池、K 表、选品结果和指标结果的 schema 契约。后续脚本应按这些契约读写。

methods/
存放不同选品方法的参数配置，例如 Top-K 排序字段、Reverse-Exclude 删除批次、Hybrid 融合权重和 ML-Top-K 模型版本。

models/
存放 ML-Top-K 相关模型产物、训练配置和离线预测结果。

src/
存放候选池构建、K 计算、选品算法、评估指标、版本管理和校验逻辑。

scripts/
存放选品运行、评估、调参和训练入口脚本。

tests/
存放选品模块单元测试和小规模集成测试。

runs/
按 experiment_id 保存每次选品实验的候选池、K 表、方法结果、最终结果、指标和 manifest。

reports/
存放选品实验报告和复盘文档。
```

## 第一版输入

第一版选品模块主要读取：

```text
data/synthetic/v001/sku_master.csv
data/synthetic/v001/warehouse_master.csv
data/synthetic/v001/sku_fdc_eligibility.csv
data/synthetic/v001/calendar.csv
data/synthetic/v001/promotion_plan.csv
data/processed/v001/fdc_sku_daily_demand.csv
data/processed/v001/order_type_table.csv
data/processed/v001/order_type_items.csv
data/processed/v001/candidate_pool_base.csv
data/features/ml_topk/v001/fdc_sku_features.csv
data/splits/v001/train_dates.txt
data/splits/v001/val_dates.txt
data/splits/v001/test_dates.txt
```

## 第一版输出

每次选品实验推荐输出到：

```text
assortment/runs/<experiment_id>/
```

核心输出文件：

```text
candidate_pool.csv
k_table.csv
topk_result.csv
reverse_exclude_result.csv
hybrid_result.csv
ml_topk_result.csv
assortment_result.csv
assortment_metrics.json
assortment_manifest.yaml
```

其中 `assortment_result.csv` 是对外稳定接口，后续 `simulation/` 和 `inventory/` 应优先通过 `assortment_version` 读取该结果。

## Schema 契约

当前已定义第一版 schema：

```text
assortment/schemas/candidate_pool.schema.yaml
assortment/schemas/k_table.schema.yaml
assortment/schemas/assortment_result.schema.yaml
assortment/schemas/assortment_metrics.schema.yaml
```

这些 schema 固定以下约定：

```text
所有实验输出必须包含 experiment_id 和 data_version
所有时间决策必须区分 anchor_date、effective_start_date 和 effective_end_date
候选池必须保留 eligible_flag、candidate_flag 和过滤原因
K 表必须记录 selected_k 的计算来源
选品结果必须包含 assortment_version、method_version、rank、score、selected_flag 和 source_tag
指标必须记录 evaluation_split、evaluation_start_date、evaluation_end_date 和核心评估口径
```

## 核心指标

第一版选品评估优先关注：

```text
local_order_fulfillment_rate
评估窗口内，订单中所有 regular SKU 都被选入对应 FDC assortment 的订单比例。

sku_frequency_recall_at_k
选中 SKU 覆盖未来 SKU order frequency 的比例。

ndcg_at_k
衡量高未来订单频次 SKU 是否排在更前面。

candidate_hit_rate
未来出现需求的 SKU 中，有多少进入了候选池。
```

## 版本规则

选品模块至少需要记录以下版本字段：

```text
data_version
candidate_pool_version
k_rule_version
method_version
assortment_version
experiment_id
```

推荐 manifest 字段：

```yaml
experiment_id: exp_assortment_001
data_version: v001
candidate_pool_version: candidate_pool_v001
k_rule_version: k_rule_v001
method_version: topk_v001
assortment_version: assortment_v001
anchor_date: 2026-06-02
effective_start_date: 2026-06-03
effective_end_date: 2026-06-29
created_at: 2026-06-26
```

## 当前阶段状态

当前第三阶段已完成并通过 v001 端到端验收。`exp_assortment_v001_topk` 会在根目录 `make full` 中运行、评估、校验，并向后续 `inventory/` 和 `evaluation/` 发布 `assortment_hybrid_v001`。

已完成工作：

```text
3.1 明确选品系统定位与边界
3.2 创建 assortment/ 目录骨架
3.3 定义候选池、K 表、选品结果和选品指标 schema
3.4 构建候选 SKU 池
3.5 计算每个 FDC 的 K 值
3.6 实现 Top-K baseline
3.7 实现 Reverse-Exclude
3.8 实现 Hybrid Selection
3.9 实现 ML-Top-K 第一版线性 baseline
3.10 实现选品评估器
3.11 定义选品结果输出与版本管理
3.12 实现选品校验与单元测试
```

## 当前运行入口

第一版候选池、K 表、Top-K baseline、Reverse-Exclude、Hybrid Selection、ML-Top-K、选品评估、结果发布和运行校验可以用下面命令生成：

```bash
PYTHONPATH=. python3 assortment/scripts/run_assortment.py \
  --config assortment/configs/assortment_small.yaml
```

只重算已有选品结果的评估指标时，可以运行：

```bash
PYTHONPATH=. python3 assortment/scripts/evaluate_assortment.py \
  --config assortment/configs/assortment_small.yaml
```

只校验已发布的 `assortment_result.csv` 和 `assortment_manifest.yaml` 时，可以运行：

```bash
PYTHONPATH=. python3 assortment/scripts/validate_assortment_run.py \
  --manifest assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml
```

当前 smoke run：

```text
experiment_id: exp_assortment_v001_topk
data_version: v001
candidate_pool_version: candidate_pool_v001
k_rule_version: k_rule_v001
method_version: topk_v001
assortment_version: assortment_topk_v001
reverse_exclude_method_version: reverse_exclude_v001
reverse_exclude_assortment_version: assortment_reverse_exclude_v001
hybrid_method_version: hybrid_v001
hybrid_assortment_version: assortment_hybrid_v001
ml_topk_method_version: ml_topk_v001
ml_topk_assortment_version: assortment_ml_topk_v001
published_method: hybrid
published_assortment_version: assortment_hybrid_v001
anchor_date: 2026-06-02
effective_window: 2026-06-03 to 2026-06-29
```

输出目录：

```text
assortment/runs/exp_assortment_v001_topk/
```

当前输出行数：

```text
candidate_pool.csv: 32734
k_table.csv: 12
topk_result.csv: 3851
reverse_exclude_result.csv: 3851
hybrid_result.csv: 3851
ml_topk_result.csv: 3851
assortment_result.csv: 3851
assortment_metrics.json: depends on evaluation window
assortment_validation_summary.json: PASS
```

当前 Reverse-Exclude 使用 `2026-04-04` 到 `2026-06-02` 的历史订单 basket，不读取生效窗口 `2026-06-03` 之后的订单，避免未来信息泄漏。

当前 Hybrid Selection 使用交替融合策略，从 Top-K 排序和 Reverse-Exclude 排序中轮流取 SKU，再用 `0.55 * normalized_topk_score + 0.45 * normalized_structure_score` 重新排序。

当前 ML-Top-K 使用 `ml_topk_linear_v001`，以历史订单频次、未来计划促销/活动和静态热度为确定性线性分数，输出 `ml_topk_result.csv` 和 `ml_topk_model_manifest.yaml`。后续可以替换为 LightGBM、线性回归、MLP 或时序模型，但应保持输出字段契约不变。

当前选品评估器会过滤非 regular product 订单，并计算：

```text
local_order_fulfillment_rate
sku_frequency_recall_at_k
ndcg_at_k
candidate_hit_rate
coverage_by_order_size
coverage_by_category
```

当前发布器默认将 `hybrid_result.csv` 发布为对外稳定的 `assortment_result.csv`，并生成 `assortment_manifest.yaml` 记录数据版本、候选池版本、K 规则版本、方法版本、assortment_version、输入输出路径和复现命令。

当前选品校验器会检查发布时间窗口、必需文件、结果 schema、manifest 行数一致性、SKU-FDC 候选合法性、regular product 约束、source_tag 合法性、selected_k 和 candidate_sku_count 一致性、rank 连续性、SKU 去重和 rank <= K。当前 v001 run 校验结果为 PASS。

最新端到端验收口径：

```text
pipeline_run_id: pipeline_20260628_204301
run_assortment: passed
evaluate_assortment: passed
validate_assortment: passed
published_method: hybrid
published_assortment_version: assortment_hybrid_v001
assortment_result_rows: 3851
```
