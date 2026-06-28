# FAIA Inventory Module

## 目标

`inventory/` 是 FAIA 项目的第四阶段库存分配模块，用于解决“选好 SKU 后，每天给每个 FDC 分多少库存”的问题。

本模块消费 `assortment/` 发布的 FDC-SKU 选品结果，结合当前 RDC/FDC 库存、在途库存、历史需求、未来已知促销、lead time、成本参数和业务约束，生成每日 RDC -> FDC 的库存分配建议。库存策略效果通过 `simulation/` 回放评估。

## 定位与边界

库存分配系统只解决“放多少”，不解决“放什么”。FDC 能经营哪些 SKU 由 `assortment/` 决定；库存分配只在已选品、可履约、可调拨的 SKU-FDC 组合内生成安全库存、目标库存和建议调拨量。

库存分配系统负责：

```text
读取 assortment_result 中的 FDC-SKU 选品结果
读取 RDC/FDC 当前库存、预留库存和在途库存
读取历史 FDC-SKU 需求、未来已知促销和日历特征
生成需求预测 baseline 或消费外部预测
生成 safety_stock 和 target_inventory
生成 RDC -> FDC recommended_transfer_qty
管理 RDC 自留库存与 FDC 下发库存之间的权衡
输出 transfer_recommendation、inventory_manifest 和策略报告
调用或对接 simulation 回放策略效果
```

库存分配系统不负责：

```text
决定 FDC 应该经营哪些 SKU
修改用户真实需求或订单回放数据
替代 simulation 模块做库存履约回放
绕过 RDC 库存、FDC 容量、SKU-FDC 合法性和 lead time 等硬约束
使用 decision_date 之后的真实需求作为线上推理特征
直接训练选品模型或修改 assortment_version
```

## 目录说明

```text
inventory/
├── README.md
├── configs/
│   ├── inventory_small.yaml
│   └── inventory_default.yaml
├── schemas/
│   ├── inventory_state.schema.yaml
│   ├── demand_forecast.schema.yaml
│   ├── tiss_result.schema.yaml
│   └── transfer_recommendation.schema.yaml
├── policies/
├── models/
│   ├── forecasting/
│   └── tiss/
├── src/
├── scripts/
├── tests/
├── runs/
└── reports/
```

各目录职责如下：

```text
configs/
存放库存分配运行配置，例如 data_version、assortment_version、decision_date、预测窗口、策略版本和输出目录。

schemas/
存放库存状态、需求预测、SS/TI 结果和调拨建议的 schema 契约。后续脚本应按这些契约读写。

policies/
存放库存分配 baseline 策略配置，例如 historical_mean、base_stock、parameter_search 和 greedy_allocation。

models/
存放需求预测模型和 TI/SS 模型产物。第一版规则 baseline 可为空。

src/
存放库存状态构建、预测、TISS 生成、调拨分配、端到端接口、评估和校验逻辑。

scripts/
存放库存 baseline 运行、推理、训练、评估和校验入口脚本。

tests/
存放库存分配模块单元测试和小规模集成测试。

runs/
按 experiment_id 保存每次库存实验的 inventory_state、demand_forecast、tiss_result、transfer_recommendation、simulation_metrics 和 manifest。

reports/
存放库存策略实验报告和复盘文档。
```

## 第一版输入

第一版库存分配模块主要读取：

```text
assortment/runs/exp_assortment_v001_topk/assortment_result.csv
data/synthetic/v001/sku_master.csv
data/synthetic/v001/warehouse_master.csv
data/synthetic/v001/sku_fdc_eligibility.csv
data/synthetic/v001/calendar.csv
data/synthetic/v001/promotion_plan.csv
data/synthetic/v001/transfer_plan.csv
data/synthetic/v001/cost_config.csv
data/processed/v001/fdc_sku_daily_demand.csv
data/processed/v001/inventory_daily_state.csv
simulation/rules/simulation_rule_v001.yaml
```

`assortment_result.csv` 是 FDC-SKU mask 的稳定上游接口。后续若 `simulation/` 仍需要 candidate-pair 输入，库存模块应将已发布 assortment 转换为 simulation 可消费的 SKU-FDC 集合。

## 第一版输出

每次库存实验推荐输出到：

```text
inventory/runs/<experiment_id>/
```

核心输出文件：

```text
inventory_state.csv
demand_forecast.csv
tiss_result.csv
transfer_recommendation.csv
simulation_metrics.json
inventory_manifest.yaml
```

其中 `transfer_recommendation.csv` 是对接 simulation 的核心策略输出，必须至少包含 `recommended_transfer_qty`、`ship_date`、`arrival_date`、`lead_time_days`、`policy_version`、`inventory_version` 和版本血缘字段。

## Schema 契约

当前已定义第一版 schema：

```text
inventory/schemas/inventory_state.schema.yaml
inventory/schemas/demand_forecast.schema.yaml
inventory/schemas/tiss_result.schema.yaml
inventory/schemas/transfer_recommendation.schema.yaml
```

这些 schema 固定以下约定：

```text
所有库存实验输出必须包含 experiment_id、data_version、assortment_version、inventory_version 和 simulation_rule_version
所有预测和策略特征必须满足 feature_window_end_date <= decision_date
未进入 assortment 的 SKU-FDC 不允许生成正向 FDC SS/TI 或正向调拨
不可履约 SKU-FDC 不允许生成正向调拨
TI 必须大于等于 SS，SS 必须非负
recommended_transfer_qty 必须非负
actual_transfer_qty 如已生成，不能超过 recommended_transfer_qty 和 RDC 可调拨库存
arrival_date 必须由 ship_date + lead_time_days 推导
```

## 第一版策略口径

第一版先使用可解释规则 baseline：

```text
HistoricalMeanForecast
使用 decision_date 之前的历史需求窗口生成未来需求预测。

RuleTISS
根据 forecast demand、lead time、历史需求波动和 service_factor 生成 SS 和 TI。

BaseStockPolicy
基于 FDC inventory_position 与 target_inventory 的缺口生成建议调拨。

RDCReserveRule
为 RDC 保留业务预留库存和/或 RDC 安全库存，只允许 rdc_allocatable_inventory 参与 FDC 补货。

GreedyAllocation
当同一 RDC-SKU 库存不足时，按 forecast_demand、缺货成本、促销权重和当前库存位置计算 priority_score 分配库存。
```

## 版本规则

库存模块至少需要记录以下版本字段：

```text
data_version
assortment_version
inventory_version
simulation_rule_version
policy_name
policy_version
model_version
experiment_id
```

推荐 manifest 字段：

```yaml
experiment_id: exp_inventory_v001_base_stock
data_version: v001
assortment_version: assortment_hybrid_v001
inventory_version: inventory_base_stock_v001
simulation_rule_version: sim_rule_v001
policy_name: base_stock
policy_version: inventory_base_stock_v001
model_version: none
decision_date: 2026-06-02
effective_start_date: 2026-06-03
effective_end_date: 2026-06-29
forecast_horizon_days: 7
rollout_window_days: 7
```

## 当前阶段状态

当前库存分配阶段已完成并通过 v001 端到端验收。`exp_inventory_v001_base_stock` 已生成 `inventory_manifest.yaml` 和 `transfer_recommendation.csv`，并在 `evaluation/runs/eval_v001_baseline/experiment_registry.csv` 中登记为 `available/PASS`。

已完成工作：

```text
4.1 明确库存分配系统定位与边界
4.2 创建 inventory/ 目录骨架
4.3 定义 inventory_state、demand_forecast、tiss_result 和 transfer_recommendation schema
4.4 构建库存状态样本
4.5 实现 HistoricalMeanForecast baseline
4.6 实现 RuleTISS SS/TI 规则计算
4.7 实现 NoTransfer、HistoricalMean、BaseStock 和 ParameterSearch 预留配置
4.8 实现 RDC reserve 和 GreedyAllocation 分配
4.9 接入 simulation 回放评估并输出 simulation_metrics.json
4.10 预留 ForecastingModule、TISSGenerationModule、SimulationModule 和 LossComputer 接口
4.11 定义 inventory_manifest 和 inventory_version
4.12 实现库存分配校验、单元测试和报告
```

## 当前配置

当前提供两份运行配置：

```text
inventory/configs/inventory_small.yaml
inventory/configs/inventory_default.yaml
```

`inventory_small.yaml` 用于开发和 smoke 测试，默认配置较短预测和回放窗口。`inventory_default.yaml` 用于 v001 完整测试窗口配置。

## 当前运行入口

第一版库存 baseline 链路可以用下面命令运行：

```bash
PYTHONPATH=. python3 inventory/scripts/run_inventory_baseline.py \
  --config inventory/configs/inventory_small.yaml
```

该入口会依次生成：

```text
inventory_state.csv
demand_forecast.csv
tiss_result.csv
transfer_recommendation.csv
simulation_metrics.json
inventory_manifest.yaml
inventory_validation_summary.json
inventory_run_summary.yaml
```

若配置中 `simulation.enabled: false`，入口会跳过库存策略的 simulation 回放指标，但仍生成 manifest、validation summary 和 report。当前 v001 默认链路已经生成库存建议并通过结构、版本、行数和策略约束校验；把 `transfer_recommendation.csv` 接入 simulation 回放并产出库存策略服务率/成本指标，是下一轮增强任务。

单独对已有 `transfer_recommendation.csv` 做 simulation 回放：

```bash
PYTHONPATH=. python3 inventory/scripts/evaluate_inventory.py \
  --config inventory/configs/inventory_small.yaml
```

单独校验库存运行：

```bash
PYTHONPATH=. python3 inventory/scripts/validate_inventory_run.py \
  --manifest inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml
```

当前实现模块：

```text
inventory/src/state_builder.py
inventory/src/forecasting.py
inventory/src/tiss.py
inventory/src/policies.py
inventory/src/allocator.py
inventory/src/evaluator.py
inventory/src/manifest.py
inventory/src/interfaces.py
inventory/src/loss.py
inventory/src/validation.py
```

最新端到端验收口径：

```text
pipeline_run_id: pipeline_20260628_204301
run_inventory_baseline: passed
validate_inventory: passed
experiment_id: exp_inventory_v001_base_stock
inventory_version: inventory_base_stock_v001
effective_window: 2026-06-03 to 2026-06-09
inventory_state_rows: 4875
demand_forecast_rows: 34125
tiss_result_rows: 4875
transfer_recommendation_rows: 3829
simulation_metrics_status: skipped by default config
```
