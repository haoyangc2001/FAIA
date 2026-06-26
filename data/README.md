# FAIA Data Module

## 目标

`data/` 是 FAIA 项目的第一阶段数据体系模块，用于构建可控、可复现、可校验的合成业务数据。后续的业务仿真、前置仓选品、库存分配和实验评估都应从该目录读取统一版本的数据。

当前项目没有真实业务数据，因此第一版目标是先构造一个可回放的 RDC-FDC 两级仓网虚拟业务世界。

## 目录说明

```text
data/
├── README.md
├── configs/
├── schemas/
├── raw/
├── synthetic/
├── processed/
├── features/
├── splits/
├── validation/
│   └── reports/
└── scripts/
```

各目录职责如下：

```text
configs/
存放数据生成配置，例如业务规模、订单规模、促销比例、lead time、随机种子和输出版本。

schemas/
存放核心数据表 schema，定义字段、类型、主键、外键和业务约束。

raw/
预留真实原始数据入口。当前没有真实数据时保持为空。

synthetic/
存放合成数据原始输出，按 data_version 分目录保存，例如 synthetic/v001_small/。

processed/
存放清洗、聚合、对齐后的中间表，例如 FDC-SKU-day 需求、订单类型表、库存每日状态和候选池基础表。

features/
存放后续模型与算法使用的特征产物，例如 ML-Top-K 特征和库存分配特征。

splits/
存放 train / validation / test 时间切分结果。FAIA 是时间序列决策问题，必须按时间切分，不能随机打散。

validation/
存放数据校验规则和校验报告。

scripts/
存放数据生成、加工、切分和校验脚本入口。
```

## 数据生成流程

第一版数据链路按以下顺序推进：

```text
1. 读取 data/configs/ 下的数据生成配置
2. 按 data/schemas/ 定义生成基础表
3. 生成 SKU、仓网和 SKU-FDC 可履约关系
4. 生成 calendar 和 promotion_plan
5. 生成 orders 和 order_items
6. 生成 inventory_snapshot、transfer_plan、stockout_events 和 cost_config
7. 构建 processed 中间表
8. 构建 features 特征产物
9. 构建 train / validation / test 时间切分
10. 输出 validation report 和 manifest
```

## 当前生成入口

第一版合成数据由下面脚本生成：

```bash
python3 data/scripts/generate_synthetic_data.py \
  --config data/configs/synthetic_small.yaml \
  --data-version v001
```

该命令会输出到：

```text
data/synthetic/v001/
```

当前 `v001` 包含以下原始合成表：

```text
sku_master.csv
warehouse_master.csv
sku_fdc_eligibility.csv
calendar.csv
promotion_plan.csv
orders.csv
order_items.csv
inventory_snapshot.csv
transfer_plan.csv
stockout_events.csv
cost_config.csv
manifest.yaml
```

## 当前加工入口

`processed` 中间表、`features` 特征产物和时间切分由下面脚本生成：

```bash
python3 data/scripts/build_stage1_artifacts.py \
  --config data/configs/synthetic_small.yaml \
  --data-version v001
```

该命令会输出：

```text
data/processed/v001/
data/features/ml_topk/v001/
data/features/inventory/v001/
data/splits/v001/
```

当前 `processed/v001` 包含：

```text
fdc_sku_daily_demand.csv
order_type_table.csv
order_type_items.csv
inventory_daily_state.csv
candidate_pool_base.csv
manifest.yaml
```

当前 `features` 包含：

```text
data/features/ml_topk/v001/fdc_sku_features.csv
data/features/inventory/v001/inventory_features.csv
```

当前 `splits/v001` 包含：

```text
train_dates.txt
val_dates.txt
test_dates.txt
manifest.yaml
```

## 当前校验入口

`v001` 数据校验由下面脚本执行：

```bash
python3 data/scripts/validate_stage1_data.py --data-version v001
```

该命令会输出：

```text
data/validation/reports/v001_validation_report.md
data/validation/reports/v001_validation_summary.json
```

当前 `v001` 校验结果：

```text
overall_status: PASS
total_checks: 58
failed_checks: 0
warnings: 0
```

## 当前版本登记入口

`v001` 数据版本由下面脚本登记：

```bash
python3 data/scripts/register_data_version.py \
  --config data/configs/synthetic_small.yaml \
  --data-version v001
```

该命令会输出：

```text
data/versions/v001/manifest.yaml
data/versions/version_registry.yaml
```

## 版本规则

每次生成数据都必须有独立 `data_version`，并在输出目录中写入 `manifest.yaml`。

推荐 manifest 字段：

```yaml
data_version: v001_small
seed: 20260626
config: data/configs/synthetic_small.yaml
schema_version: v001
generator_version: v001
created_at: 2026-06-26
```

后续模块读取数据时，应显式指定 `data_version`，不要直接读取未标记版本的临时文件。

## 后续模块读取约定

```text
simulation/
读取 synthetic、processed 和 cost_config，按天回放库存、调拨、履约和缺货。

assortment/
读取 sku_fdc_eligibility、order_type_table、order_type_items、fdc_sku_daily_demand 和 candidate_pool_base。

inventory/
读取 inventory_daily_state、fdc_sku_daily_demand、promotion_plan、calendar 和 transfer_plan。

evaluation/
读取 simulation 输出、策略输出和统一切分结果，进行指标对比。
```
