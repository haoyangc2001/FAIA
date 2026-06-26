# FAIA 项目从 0 实现计划方案

## 1. 项目目标

FAIA 项目目标是实现一套面向 RDC-FDC 两级仓网的履约优化系统，用于解决两个核心问题：

```text
1. 每个 FDC 应该选择哪些 SKU？
2. 选好 SKU 后，RDC 每天应该给各 FDC 分配多少库存？
```

最终希望形成完整闭环：

```text
数据构建
  -> 业务仿真
  -> 前置仓选品
  -> 库存分配
  -> 指标评估
  -> 实验复现
```

## 2. 总体建设思路

由于当前没有真实业务数据，项目不能一开始就直接训练模型。应先构建一个可控的模拟业务环境，再逐步实现算法和实验评估流程。

整体路线是：

```text
先搭数据和仿真地基，
再做选品和库存 baseline，
最后逐步加入机器学习和端到端模型。
```

项目整体不是单纯训练一个模型，而是建设一套完整的：

```text
数据构建 + 仓网仿真 + 选品优化 + 库存分配 + 实验评估
```

## 3. 阶段计划

### 阶段 1：数据体系建设

目标：构建一套可用于训练、仿真和评估的合成数据体系。由于当前没有真实业务数据，第一阶段的核心不是直接训练模型，而是先造出一个可控、可复现、能支撑后续选品和库存仿真的虚拟业务世界。

这一阶段不是简单生成几张 CSV，而是要打通完整的数据链路：

```text
业务规模配置
  -> 数据 schema
  -> 合成业务世界
  -> 订单与需求生成
  -> 库存、调拨、促销、成本数据生成
  -> processed 中间表
  -> features 特征产物
  -> train / validation / test 时间切分
  -> 数据校验报告
  -> 数据版本归档
```

#### 1.1 目录规划

第一阶段是项目的数据底座。因此，数据体系相关内容不应只存放在 `doc/` 中，而应在 FAIA 根目录下建立独立的 `data/` 目录，与 `doc/` 同级。`doc/` 负责说明材料和方案文档，`data/` 负责数据生成、数据 schema、数据校验、数据切分、特征产物和数据版本管理。

建议目录结构：

```text
FAIA/
├── doc/
│   ├── material/
│   └── plan/
│
├── data/
│   ├── README.md
│   ├── configs/
│   ├── schemas/
│   ├── raw/
│   ├── synthetic/
│   ├── processed/
│   ├── features/
│   ├── splits/
│   ├── validation/
│   └── scripts/
│
├── simulation/
│   └── ...
│
├── assortment/
│   └── ...
│
├── inventory/
│   └── ...
│
├── evaluation/
│   └── ...
│
└── README.md
```

`data/` 目录职责：

```text
data/README.md
说明第一阶段数据体系的目标、目录含义、数据生成流程、输入输出关系。

data/configs/
存放数据生成配置，例如 RDC 数量、FDC 数量、SKU 数量、订单天数、促销比例、多商品订单比例等。

data/schemas/
存放所有数据表结构定义，例如 sku_master、warehouse_master、orders、order_items、inventory_snapshot、promotion_plan、transfer_plan、cost_config 等 schema。

data/raw/
预留真实原始数据入口。当前没有真实数据时，可保留空目录或 .gitkeep。

data/synthetic/
存放合成数据生成后的原始模拟数据，按 data_version 分版本保存。

data/processed/
存放清洗、对齐、聚合后的中间表，例如 FDC-SKU-day 需求、订单类型表、SKU-FDC 可履约关系、每日库存状态等。

data/features/
存放算法和模型使用的特征产物，例如 ML-Top-K 特征、库存分配特征等。

data/splits/
存放训练、验证、测试时间切分。该项目必须按时间切分，不能随机打散。

data/validation/
存放数据校验规则和校验报告，例如字段缺失、主键重复、库存负数、未来信息泄漏等检查结果。

data/scripts/
存放第一阶段数据构建相关脚本入口，例如生成合成数据、构建中间表、构建特征、数据校验、生成切分等脚本。
```

#### 1.2 工作 1：明确数据建设范围

第一步需要确定第一版要模拟的业务规模。这个配置会影响数据量、算法运行速度、仿真复杂度和后续实验成本。

需要定义的内容：

```text
RDC 数量
每个 RDC 下挂多少 FDC
SKU 数量
类目数量
品牌数量
模拟天数
每日订单量
多商品订单比例
促销比例
调拨 lead time 范围
FDC 容量约束
随机种子
```

第一版建议先使用较小规模，保证流程能快速跑通：

```text
RDC 数量：2
FDC 数量：12
SKU 数量：3000 到 5000
模拟天数：180
每日订单量：5000 到 10000
多商品订单比例：30% 到 40%
促销 SKU 比例：3% 到 8%
lead time：1 到 3 天
```

阶段产出：

```text
data/configs/synthetic_small.yaml
data/configs/synthetic_medium.yaml
```

具体步骤：

```text
1. 定义 synthetic_small.yaml，用于快速开发和单元测试。
2. 定义 synthetic_medium.yaml，用于后续接近真实规模的实验。
3. 在配置中固定 seed，保证数据可以复现。
4. 在配置中明确输出 data_version，例如 v001。
```

#### 1.3 工作 2：设计基础数据 schema

在生成任何数据之前，需要先定义每张表的字段、主键、外键关系和业务含义。后续所有算法、仿真、特征构建和校验都必须按 schema 读写。

核心 schema：

```text
sku_master
商品主数据：sku_id、类目、品牌、价格、温层、体积、重量、保质期、是否 regular product。

warehouse_master
仓网主数据：rdc_id、fdc_id、城市、区域、FDC 容量、温区能力、所属 RDC。

sku_fdc_eligibility
SKU-FDC 可履约关系：哪些 SKU 可以进入哪些 FDC。

calendar
日期表：date、星期、是否周末、节假日、大促窗口、活动阶段。

promotion_plan
促销计划：sku_id、date、促销类型、折扣、优惠券、曝光计划、活动阶段。

orders
订单主表：order_id、order_date、rdc_id、fdc_id、用户区域、订单类型标记。

order_items
订单明细：order_id、sku_id、qty。

inventory_snapshot
库存快照：date、node_id、node_type、sku_id、on_hand_qty。

transfer_plan
调拨记录：ship_date、arrival_date、rdc_id、fdc_id、sku_id、transfer_qty。

stockout_events
缺货事件：date、fdc_id、sku_id、stockout_flag、stockout_reason。

cost_config
成本配置：transfer_cost、rdc_fallback_cost、lost_sales_cost、holding_cost。
```

阶段产出：

```text
data/schemas/sku_master.schema.yaml
data/schemas/warehouse_master.schema.yaml
data/schemas/sku_fdc_eligibility.schema.yaml
data/schemas/calendar.schema.yaml
data/schemas/promotion_plan.schema.yaml
data/schemas/orders.schema.yaml
data/schemas/order_items.schema.yaml
data/schemas/inventory_snapshot.schema.yaml
data/schemas/transfer_plan.schema.yaml
data/schemas/stockout_events.schema.yaml
data/schemas/cost_config.schema.yaml
```

具体步骤：

```text
1. 为每张表定义主键。
2. 为每个字段定义类型、是否可空、默认值和业务说明。
3. 定义跨表引用关系，例如 order_items.sku_id 必须存在于 sku_master。
4. 定义必要的业务约束，例如库存不能为负、订单日期必须存在于 calendar。
5. 为后续数据校验模块提供 schema 输入。
```

#### 1.4 工作 3：构建合成业务世界

这一部分生成静态世界，包括商品、仓库、区域和可履约关系。它决定后续订单、库存和选品问题的业务边界。

需要生成的内容：

```text
SKU 池
为 SKU 分配类目、品牌、价格、温层、体积、重量、保质期、基础热度。

RDC/FDC 仓网
定义每个 FDC 所属 RDC、城市、区域、容量、温区能力、服务范围。

SKU-FDC 可履约关系
根据温层、体积、区域权限、RDC 供给范围判断哪些 SKU 能进入哪些 FDC。
```

阶段产出：

```text
data/synthetic/v001/sku_master.csv
data/synthetic/v001/warehouse_master.csv
data/synthetic/v001/sku_fdc_eligibility.csv
```

具体步骤：

```text
1. 生成 SKU 主数据。
2. 按类目和品牌给 SKU 分配基础热度，形成头部 SKU 和长尾 SKU。
3. 生成 RDC 和 FDC 主数据。
4. 给 FDC 设置容量、温区能力和服务区域。
5. 根据履约能力生成 sku_fdc_eligibility。
6. 检查每个 FDC 至少有足够数量的可履约 SKU。
```

#### 1.5 工作 4：生成需求与订单数据

订单数据是第一阶段最关键的模拟对象。订单不能纯随机生成，否则后续 Top-K、Reverse-Exclude、Hybrid Selection 和 ML-Top-K 都学不到有意义的结构。

需求生成需要模拟：

```text
SKU 热度长尾分布
不同 FDC 的区域偏好
类目 / 品牌偏好
商品共购关系
单品订单与多商品订单
周末 / 节假日需求变化
促销带来的需求冲击
```

重点是生成 basket，即多商品订单。因为前置仓选品优化的是订单完整覆盖，而不是单品销量。

阶段产出：

```text
data/synthetic/v001/orders.csv
data/synthetic/v001/order_items.csv
```

具体步骤：

```text
1. 为每个 FDC 生成区域需求偏好。
2. 为每个 SKU 生成基础需求强度。
3. 根据 calendar 生成日期级需求放大系数。
4. 根据 promotion_plan 生成促销需求放大系数。
5. 按每日订单量生成 orders。
6. 按单品订单和多商品订单比例生成 order_items。
7. 对多商品订单引入共购结构，例如同类目互补、同品牌组合、常见搭配。
8. 确保订单中的 SKU 属于该 FDC 可服务范围或可由 RDC 兜底履约范围。
```

#### 1.6 工作 5：生成促销与日历数据

促销和日历既影响订单生成，也会作为后续 ML-Top-K 和库存分配模型的未来可见特征。

关键原则：

```text
促销数据必须是预测时点已知的计划数据。
不能使用未来真实销量、未来真实曝光、未来订单结果作为特征。
```

阶段产出：

```text
data/synthetic/v001/calendar.csv
data/synthetic/v001/promotion_plan.csv
```

具体步骤：

```text
1. 生成完整日期表。
2. 标记 weekday、weekend、holiday、campaign_window。
3. 为部分 SKU 生成促销计划。
4. 定义促销类型，例如 direct_discount、coupon、flash_sale、platform_campaign。
5. 定义折扣强度、优惠券强度、计划曝光等级和活动阶段。
6. 将促销影响写入订单需求生成逻辑。
```

#### 1.7 工作 6：生成库存、缺货、调拨和成本数据

第一阶段虽然主要建设数据体系，但必须提前为第二阶段库存仿真预留接口。

需要生成的内容：

```text
RDC 初始库存
FDC 初始库存
每日库存快照
简单补货 / 调拨记录
stockout flag
成本配置
```

第一版可以先使用简单规则生成库存和调拨数据，不需要复杂库存优化。

阶段产出：

```text
data/synthetic/v001/inventory_snapshot.csv
data/synthetic/v001/transfer_plan.csv
data/synthetic/v001/stockout_events.csv
data/synthetic/v001/cost_config.csv
```

具体步骤：

```text
1. 根据 SKU 基础需求生成 RDC 初始库存。
2. 根据 FDC 可履约 SKU 和容量生成 FDC 初始库存。
3. 使用简单规则生成每日补货和调拨记录。
4. 根据库存不足情况生成 stockout_events。
5. 设置调拨成本、RDC 代履约成本、lost sales 成本和持有成本。
6. 确保库存、调拨、需求之间的日期关系可以被仿真器回放。
```

#### 1.8 工作 7：构建 processed 中间表

原始订单表不适合直接给算法使用，需要聚合、对齐和加工成中间表。

需要构建的中间表：

```text
fdc_sku_daily_demand
按 fdc_id、sku_id、date 聚合订单包含次数。

order_type_table
将同一 FDC、同一窗口内 SKU 组合相同的订单聚合为订单类型。

order_type_items
记录每个订单类型包含哪些 SKU。

inventory_daily_state
整理 RDC/FDC 每日库存状态。

candidate_pool_base
构建候选 SKU 池基础表，供 Top-K、Reverse-Exclude、ML-Top-K 使用。
```

阶段产出：

```text
data/processed/v001/fdc_sku_daily_demand.csv
data/processed/v001/order_type_table.csv
data/processed/v001/order_type_items.csv
data/processed/v001/inventory_daily_state.csv
data/processed/v001/candidate_pool_base.csv
```

具体步骤：

```text
1. 从 orders 和 order_items 聚合 FDC-SKU-day 订单包含次数。
2. 将订单中的 SKU 去重排序，生成 order_type_key。
3. 按 FDC 和 order_type_key 聚合订单需求量。
4. 生成 order_type_items，保留订单类型与 SKU 的多对多关系。
5. 对 inventory_snapshot 和 transfer_plan 做日期对齐。
6. 生成 candidate_pool_base，作为后续候选池构建的基础输入。
```

#### 1.9 工作 8：构建 features 特征产物

第一阶段不一定立即训练 ML 模型，但需要提前规划特征产物目录。特征构建应与数据版本和特征版本分离，便于后续复现实验。

需要支持的特征方向：

```text
ML-Top-K 特征
历史 FDC-SKU 订单序列、类目序列、品牌序列、全国 SKU 热度、未来促销、日历、静态 SKU/FDC embedding key。

库存分配特征
历史需求、当前库存、在途库存、lead time、促销计划、SKU/FDC/RDC 静态特征。
```

阶段产出：

```text
data/features/ml_topk/v001/
data/features/inventory/v001/
```

具体步骤：

```text
1. 为 ML-Top-K 构建样本粒度：fdc_id、sku_id、anchor_date。
2. 构建历史窗口特征，例如最近 L 天订单序列。
3. 构建未来窗口特征，例如未来 H 天促销和日历计划。
4. 构建静态特征 key，例如 sku_id、category_id、brand_id、fdc_id、city_id。
5. 为库存分配预留库存状态、lead time 和在途库存特征。
6. 记录 feature_version，保证训练和推理口径一致。
```

#### 1.10 工作 9：构建训练 / 验证 / 测试时间切分

该项目必须按时间切分，不能随机切分。选品和库存分配都是时间序列决策，随机切分会导致未来信息泄漏。

推荐切分方式：

```text
前 70% 日期：train
中间 15% 日期：validation
最后 15% 日期：test
```

阶段产出：

```text
data/splits/v001/train_dates.txt
data/splits/v001/val_dates.txt
data/splits/v001/test_dates.txt
```

具体步骤：

```text
1. 读取 calendar 中完整日期范围。
2. 按时间顺序切分 train、validation、test。
3. 检查每个切分窗口内是否有足够订单量。
4. 确保 validation 和 test 的特征只能使用其 anchor_date 之前的数据。
5. 将切分结果写入 data/splits/<data_version>/。
```

#### 1.11 工作 10：做数据校验

数据校验要尽早建设，否则后面算法问题会和数据问题混在一起。

基础校验内容：

```text
主键是否唯一
字段是否缺失
字段类型是否符合 schema
order_items.sku_id 是否存在于 sku_master
orders.fdc_id 是否存在于 warehouse_master
库存是否出现负数
订单日期是否在模拟日期范围内
促销日期是否存在于 calendar
候选池是否包含不可履约 SKU
训练特征是否使用未来数据
train / validation / test 是否按时间切分
```

阶段产出：

```text
data/validation/reports/v001_validation_report.md
```

具体步骤：

```text
1. 根据 data/schemas/ 读取字段规则。
2. 对 synthetic 表做字段、主键、外键校验。
3. 对 processed 表做聚合一致性校验。
4. 对 features 表做窗口边界校验，防止未来信息泄漏。
5. 对 splits 做时间顺序校验。
6. 输出 validation report，记录通过项、失败项和警告项。
```

#### 1.12 工作 11：建立数据版本管理

每次生成数据都必须能复现。数据版本管理需要记录生成配置、随机种子、schema 版本、脚本版本和数据规模统计。

每个数据版本建议包含 manifest：

```text
data/synthetic/v001/manifest.yaml
```

manifest 推荐字段：

```text
data_version: v001
seed: 20260626
config: synthetic_small.yaml
schema_version: v001
generator_version: v001
num_skus: 5000
num_rdcs: 2
num_fdcs: 12
num_days: 180
created_at: 2026-06-26
```

具体步骤：

```text
1. 每次生成数据前确定 data_version。
2. 将配置文件、seed、schema_version 写入 manifest。
3. 生成后统计订单量、SKU 数、FDC 数、促销数量、库存记录数量等规模信息。
4. 将校验报告路径写入 manifest。
5. 后续 processed、features、splits 都引用同一个 data_version。
```

#### 1.13 第一阶段推荐实施顺序

建议按下面顺序推进：

```text
1. 创建 data/ 目录骨架
2. 编写 data/README.md
3. 编写 data/configs/synthetic_small.yaml
4. 编写 data/schemas/ 下的核心 schema
5. 生成 sku_master 和 warehouse_master
6. 生成 sku_fdc_eligibility
7. 生成 calendar 和 promotion_plan
8. 生成 orders 和 order_items
9. 生成 inventory_snapshot、transfer_plan、stockout_events、cost_config
10. 构建 processed 中间表
11. 构建 features 特征产物的第一版目录和样例
12. 生成 train / validation / test 时间切分
13. 跑数据校验并输出 validation report
14. 写入 manifest.yaml，完成 data_version 归档
```

#### 1.14 第一阶段完成标准

第一阶段完成后，至少需要满足：

```text
数据能稳定生成
schema 清楚
数据能按版本复现
训练 / 验证 / 测试能按时间切分
processed 中间表能支撑 Top-K / Reverse-Exclude
features 目录能支撑后续 ML-Top-K 和库存分配模型
库存、调拨、成本数据能支撑仿真器读取
数据校验报告无严重错误
没有明显未来信息泄漏
```

做到这里，第一阶段就算真正打好了项目地基。后续阶段的选品算法、库存分配模型和仿真评估都应基于该数据体系继续推进。

### 阶段 2：业务仿真环境建设

目标：实现一个可以模拟真实 RDC-FDC 履约过程的业务仿真器。仿真器是连接“策略输出”和“业务指标”的核心模块，用来回答：如果按照某个选品结果和库存分配策略执行，每一天会发生多少 FDC 本地履约、RDC 代履约、lost sales、调拨成本和库存变化。

这一阶段的核心不是训练模型，而是搭建一个稳定、可复现、可回放的业务环境。后续 Top-K、Reverse-Exclude、Hybrid Selection、库存 baseline、端到端库存模型都要通过这个仿真器评估效果。

仿真主流程：

```text
初始库存状态
  -> 历史在途调拨到货
  -> 策略生成当日调拨建议
  -> 调拨进入 pipeline
  -> 当日真实需求到达
  -> FDC 本地履约
  -> FDC 不足部分由 RDC 代履约
  -> RDC 也不足则 lost sales
  -> RDC 自身需求履约
  -> 成本和指标计算
  -> 库存状态更新
  -> 进入下一天
```

#### 2.1 仿真器定位与边界

业务仿真器需要保持策略无关。它不应该只服务某一个算法，而应该接收不同策略输出，并统一按照同一套业务规则回放履约结果。

仿真器需要支持的策略来源：

```text
固定规则策略
例如按历史均值、按预测需求、按安全库存系数补货。

一阶段选品结果
限制哪些 SKU-FDC 组合可以进行 FDC 侧库存分配。

库存 baseline
例如简单补货策略、参数搜索策略、贪心分配策略。

端到端模型输出
例如 Forecasting + TI/SS 模块输出的 target_inventory 和 safety_stock。
```

仿真器不负责：

```text
训练 ML 模型
决定最终选哪些 SKU
学习最优库存策略
修改原始订单需求
使用未来不可见信息生成策略
```

仿真器负责：

```text
按照给定策略执行库存调拨
按照统一履约优先级消耗库存
记录每一天库存状态
计算履约结果、缺货结果和运营成本
为后续评估模块提供标准输出
```

#### 2.2 目录与模块规划

第二阶段应建立独立的 `simulation/` 目录，与第一阶段的 `data/` 目录同级。这样项目结构更符合阶段边界：`data/` 负责数据建设，`simulation/` 负责业务仿真环境建设。第二阶段相关的配置、规则、策略、源码、脚本、测试、运行产物和报告都应优先放在 `simulation/` 下，避免散落到全局 `configs/`、`src/` 和 `experiments/` 中。

建议目录结构：

```text
FAIA/
├── data/
│   └── ...
│
├── simulation/
│   ├── README.md
│   ├── configs/
│   │   ├── simulation_small.yaml
│   │   └── simulation_default.yaml
│   ├── schemas/
│   │   ├── daily_state.schema.yaml
│   │   ├── transfer_result.schema.yaml
│   │   ├── fulfillment_result.schema.yaml
│   │   └── cost_result.schema.yaml
│   ├── rules/
│   │   └── simulation_rule_v001.yaml
│   ├── policies/
│   │   ├── no_transfer.yaml
│   │   ├── historical_mean.yaml
│   │   └── base_stock.yaml
│   ├── src/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── state.py
│   │   ├── policy.py
│   │   ├── allocation.py
│   │   ├── fulfillment.py
│   │   ├── cost.py
│   │   ├── metrics.py
│   │   └── validation.py
│   ├── scripts/
│   │   ├── run_simulation.py
│   │   └── replay_simulation.py
│   ├── tests/
│   │   ├── test_state.py
│   │   ├── test_allocation.py
│   │   ├── test_fulfillment.py
│   │   └── test_engine.py
│   ├── runs/
│   │   └── <experiment_id>/
│   │       ├── daily_state.csv
│   │       ├── fulfillment_result.csv
│   │       ├── transfer_result.csv
│   │       ├── cost_result.csv
│   │       ├── metrics_summary.json
│   │       └── simulation_manifest.yaml
│   └── reports/
│       └── <experiment_id>_simulation_report.md
│
├── doc/
│   └── ...
```

`simulation/` 目录职责：

```text
simulation/README.md
说明第二阶段业务仿真环境的目标、输入输出、运行方式、规则版本和结果解释口径。

simulation/configs/
存放仿真运行配置，例如仿真日期范围、输入 data_version、策略版本、成本配置、是否启用容量约束等。

simulation/schemas/
存放仿真输出表结构定义，例如 daily_state、transfer_result、fulfillment_result、cost_result 等 schema。

simulation/rules/
存放仿真业务规则配置，例如履约优先级、RDC 保留库存规则、调拨裁剪规则、整数化规则和约束开关。

simulation/policies/
存放 baseline 策略配置，例如不调拨、历史均值补货、base-stock 策略等。

simulation/src/
存放仿真器核心实现代码。

simulation/scripts/
存放仿真运行入口脚本和回放脚本。

simulation/tests/
存放仿真器单元测试和小规模集成测试。

simulation/runs/
存放每次仿真运行结果，按 experiment_id 分目录管理。

simulation/reports/
存放仿真报告和复盘文档。
```

`simulation/src/` 模块职责：

```text
engine.py
仿真主引擎，负责按日期滚动执行完整 simulation loop。

state.py
定义库存状态、在途库存、每日仿真状态和状态更新逻辑。

policy.py
定义策略接口，例如固定补货策略、TI/SS 策略、外部调拨计划策略。

allocation.py
根据策略输出、RDC 可用库存、FDC 容量和 lead time 生成实际可执行调拨。

fulfillment.py
模拟 FDC 本地履约、RDC 代履约、RDC 自身履约和 lost sales。

cost.py
计算调拨成本、RDC 代履约成本、lost sales 成本、库存持有成本等。

metrics.py
聚合 FDC Ful.、Reg. Loss、Loss Ratio、Transfer Cost、Stock Availability 等指标。

validation.py
校验仿真输入和输出状态，例如库存不能为负、调拨不能超过可用库存。
```

这种目录方式的好处是阶段边界清晰：第一阶段所有数据建设内容沉淀在 `data/` 下，第二阶段所有仿真环境内容沉淀在 `simulation/` 下。后续第三阶段也可以按同样思想建立 `assortment/` 目录，第四阶段建立 `inventory/` 目录。

#### 2.3 工作 1：定义仿真输入与输出契约

仿真器必须先明确输入输出，否则后续策略模块和评估模块很难对接。

核心输入：

```text
sku_master
商品主数据，用于获取 SKU 属性、体积、温层、是否 regular product。

warehouse_master
仓网主数据，用于获取 RDC-FDC 关系、FDC 容量、温区能力。

sku_fdc_eligibility
SKU-FDC 可履约关系，用于限制 FDC 侧可调拨和可履约的 SKU。

orders / order_items
真实需求回放数据，用于模拟每日订单到达。

inventory_snapshot
初始库存和每日库存状态输入。

transfer_plan 或 policy output
调拨策略输入，可以来自 baseline、模型或外部固定计划。

promotion_plan / calendar
可选输入，用于策略特征，不直接改变仿真器中的真实订单。

cost_config
成本参数，用于计算运营损失。

lead_time_config
RDC 到 FDC 的调拨提前期配置。

assortment_result
第一阶段选品结果，决定哪些 SKU-FDC 组合允许在 FDC 层经营。
```

核心输出：

```text
daily_state
每日 RDC/FDC/SKU 库存状态。

transfer_result
每日 RDC -> FDC 的建议调拨量、实际调拨量、到货日期。

fulfillment_result
每日 FDC 本地履约量、RDC 代履约量、RDC 自身履约量、lost sales。

cost_result
每日调拨成本、RDC 代履约成本、lost sales 成本、库存持有成本。

metrics_summary
仿真周期内的核心指标汇总。
```

具体步骤：

```text
1. 明确仿真器读取哪些 data/synthetic 和 data/processed 表。
2. 明确策略模块输入输出字段。
3. 明确仿真结果表字段。
4. 规定所有输出必须带 run_date、simulation_date、experiment_id、simulation_rule_version。
5. 为后续评估模块固定输出接口。
```

#### 2.4 工作 2：定义核心状态变量

仿真器本质上是一个状态递推系统。当前日期的库存状态由前一天库存、在途到货、当日调拨、当日履约和当日缺货共同决定。

需要维护的状态：

```text
rdc_on_hand_inventory
RDC 当前可用库存，粒度为 date、rdc_id、sku_id。

fdc_on_hand_inventory
FDC 当前可用库存，粒度为 date、fdc_id、sku_id。

pipeline_inventory
已经从 RDC 发出但尚未到 FDC 的在途库存，粒度为 ship_date、arrival_date、rdc_id、fdc_id、sku_id。

last_transfer_qty
上一期调拨量，用于调拨平滑、复盘和状态检查。

last_fulfillment_result
上一期履约结果，用于指标累计和后续策略扩展。

lost_sales_state
缺货损失记录，用于成本和服务水平评估。
```

状态更新关系：

```text
FDC 下一期库存
= FDC 当前库存
 到货调拨
- FDC 本地履约消耗

RDC 下一期库存
= RDC 当前库存
 外部补货
- RDC 发给 FDC 的调拨
- RDC 代履约消耗
- RDC 自身履约消耗
```

具体步骤：

```text
1. 设计 SimulationState 数据结构。
2. 定义初始化方法，从 inventory_snapshot 读取起始库存。
3. 定义 pipeline_inventory 数据结构。
4. 定义 update_state 方法，统一处理库存扣减和到货。
5. 加入状态校验，确保库存不出现非法负数。
```

#### 2.5 工作 3：实现仿真初始化

仿真开始前，需要根据指定起始日期建立初始库存状态、在途库存状态和策略上下文。

初始化输入：

```text
simulation_start_date
simulation_end_date
initial_inventory_snapshot
initial_pipeline_inventory
warehouse_master
sku_fdc_eligibility
assortment_result
cost_config
lead_time_config
simulation_config
```

阶段产出：

```text
initial_simulation_state
simulation_context
```

具体步骤：

```text
1. 读取仿真日期范围。
2. 读取起始日期前的库存快照。
3. 读取尚未到货的在途调拨。
4. 读取 RDC-FDC 网络关系。
5. 读取 SKU-FDC 可履约关系和选品结果。
6. 初始化 SimulationState。
7. 对初始状态做合法性校验。
```

#### 2.6 工作 4：实现调拨到货与 lead time 逻辑

RDC 到 FDC 的调拨不能默认当天到达，必须通过 lead time 进入在途队列。该逻辑是库存动态仿真的关键。

需要实现：

```text
ArrivalUpdate
把当日到期的 pipeline_inventory 加入 FDC 可用库存。

PipelineShift
将在途库存按日期推进。

TransferPipelineUpdate
将当日新调拨量写入对应 arrival_date 的 pipeline。
```

具体步骤：

```text
1. 根据 lead_time_config 计算每条调拨的 arrival_date。
2. 每日仿真开始时先处理当日到货。
3. 到货后增加对应 FDC-SKU 的 on_hand_inventory。
4. 当日新调拨不会直接增加 FDC 库存，而是写入 pipeline。
5. 检查 pipeline 中是否存在过期未处理记录。
```

#### 2.7 工作 5：实现策略接口

仿真器需要能接入不同库存策略。策略模块只负责给出“想调多少”或“目标库存水位”，仿真器负责把策略输出裁剪成业务可执行调拨。

策略接口可以支持两种形式：

```text
transfer_qty 策略
策略直接输出 RDC -> FDC 的建议调拨量。

TI/SS 策略
策略输出 target_inventory 和 safety_stock，由仿真器计算缺口并生成调拨量。
```

第一版需要实现的 baseline 策略：

```text
NoTransferPolicy
不调拨，用于验证仿真器基础逻辑。

HistoricalMeanPolicy
按历史平均需求补货。

DemandForecastPolicy
按未来预测需求补货。

BaseStockPolicy
按 safety_stock 和 target_inventory 补货。
```

具体步骤：

```text
1. 定义统一 Policy 接口。
2. 定义 policy.generate_decision(date, state, context)。
3. 支持输出 recommended_transfer_qty。
4. 支持输出 target_inventory 和 safety_stock。
5. 确保策略不能读取仿真日期之后的真实需求。
6. 为每个 baseline 策略写最小实现。
```

#### 2.8 工作 6：实现调拨分配与硬约束裁剪

策略输出不一定可执行。仿真器必须根据 RDC 可用库存、FDC 容量、收货能力、RDC 出库能力、SKU-FDC 可履约关系等硬约束生成实际调拨量。

需要考虑的硬约束：

```text
SKU-FDC 必须可履约
SKU 必须在第一阶段选品集合中
RDC 可调拨库存不能为负
FDC 仓容不能超限
FDC 收货能力不能超限
RDC 出库能力不能超限
调拨量必须非负
线上执行量必须是整数
```

调拨裁剪逻辑：

```text
actual_transfer_qty
= min(
    recommended_transfer_qty,
    rdc_allocatable_inventory,
    fdc_capacity_remaining,
    fdc_receiving_limit,
    rdc_shipping_limit
  )
```

具体步骤：

```text
1. 根据 assortment_result 和 sku_fdc_eligibility 过滤非法 SKU-FDC。
2. 计算 RDC 自身保留库存。
3. 计算 RDC 可调拨库存。
4. 计算 FDC 剩余容量和收货上限。
5. 对 recommended_transfer_qty 做非负、整数化和上限裁剪。
6. 将 actual_transfer_qty 写入 transfer_result 和 pipeline_inventory。
```

#### 2.9 工作 7：实现履约仿真逻辑

履约仿真是业务仿真器的核心。它把订单需求转化为 FDC 本地履约、RDC 代履约和 lost sales。

默认履约优先级：

```text
1. FDC 服务区域订单优先由对应 FDC 本地履约。
2. 如果 FDC 库存不足，不足部分由对应 RDC 代履约。
3. 如果 RDC 也不足，则产生 lost sales。
4. RDC 自身需求由 RDC 履约，不足部分产生 RDC lost sales。
```

需要处理的需求流：

```text
FDC local demand
FDC 服务区域的 SKU 需求。

RDC fallback demand
FDC 未满足部分转化为 RDC 代履约需求。

RDC self demand
RDC 自身区域需求。
```

具体步骤：

```text
1. 按 simulation_date 读取当日订单和订单明细。
2. 聚合为 FDC-SKU-day 需求。
3. 使用 FDC on-hand inventory 先履约本地需求。
4. 计算 FDC unmet demand。
5. 将 unmet demand 转给 RDC fallback。
6. 使用 RDC on-hand inventory 履约 fallback demand。
7. 使用 RDC on-hand inventory 履约 RDC self demand。
8. 计算所有未满足需求的 lost sales。
9. 扣减 FDC 和 RDC 库存。
10. 写入 fulfillment_result。
```

#### 2.10 工作 8：实现成本和指标计算

仿真器需要在每日回放后计算运营成本和业务指标，为后续策略比较提供统一口径。

成本项：

```text
transfer_cost
RDC -> FDC 调拨成本。

rdc_fallback_cost
FDC 缺货后由 RDC 代履约带来的额外成本。

lost_sales_cost
FDC 和 RDC 都无法满足需求时产生的缺货损失。

holding_cost
库存持有成本，可在第一版中先作为可选项。
```

核心指标：

```text
FDC Fulfillment Rate
FDC 需求中由 FDC 本地满足的比例。

Regional Lost Sales
区域内 lost sales 数量或比例。

Loss Ratio
regional lost sales / FDC fulfilled sales。

Transfer Cost
总调拨成本。

Stock Availability
需求被库存满足的能力。

Local Fulfillment Quantity
FDC 本地履约量。

RDC Fallback Quantity
RDC 代履约量。
```

具体步骤：

```text
1. 从 transfer_result 计算调拨成本。
2. 从 fulfillment_result 计算 RDC 代履约成本。
3. 从 lost_sales_qty 计算缺货损失。
4. 按 day、FDC、RDC、SKU、region 多层级聚合指标。
5. 输出 cost_result。
6. 输出 metrics_summary。
```

#### 2.11 工作 9：实现仿真输出与复盘日志

仿真器输出必须可复盘。任何一个指标异常，都应该能回查到当日库存、当日需求、调拨建议、实际调拨、履约路径和库存更新。

需要输出的表：

```text
daily_state.csv
每日节点库存状态。

transfer_result.csv
调拨建议、实际调拨、出发日期、到货日期。

fulfillment_result.csv
FDC 本地履约、RDC 代履约、lost sales。

cost_result.csv
每日成本明细。

metrics_summary.json
仿真整体指标。

simulation_manifest.yaml
仿真版本、输入数据版本、策略版本、规则版本和配置。
```

具体步骤：

```text
1. 为每次仿真生成 experiment_id。
2. 将仿真输出写入 simulation/runs/<experiment_id>/。
3. 每张输出表都带 simulation_date、data_version、policy_version、simulation_rule_version。
4. 保存 simulation_config。
5. 保存 metrics_summary。
```

#### 2.12 工作 10：实现仿真校验与单元测试

仿真器一旦有 bug，后续所有算法评估都会失真。因此第二阶段必须建立基础校验和小规模单元测试。

基础校验：

```text
库存不能为负
调拨不能超过 RDC 可调拨库存
FDC 库存不能超过容量
不可履约 SKU-FDC 不能产生调拨
未选品 SKU 不能进入 FDC 调拨
订单需求 = FDC 本地履约 + RDC 代履约 + lost sales
期末库存 = 期初库存 + 到货 - 履约消耗 - 调拨消耗
pipeline 到货日期必须符合 lead time
```

推荐单元测试场景：

```text
单 FDC、单 SKU、库存充足，全部 FDC 本地履约。
单 FDC、单 SKU、FDC 缺货但 RDC 充足，触发 RDC 代履约。
单 FDC、单 SKU、FDC 和 RDC 都缺货，触发 lost sales。
存在 lead time，调拨不会当天到货。
FDC 容量不足，调拨被裁剪。
SKU 未被选品，不能调拨到 FDC。
```

具体步骤：

```text
1. 构建最小 toy dataset。
2. 为 ArrivalUpdate 写测试。
3. 为 TransferPipelineUpdate 写测试。
4. 为 FulfillmentSimulation 写测试。
5. 为 CostComputer 写测试。
6. 为完整 one-day simulation 写集成测试。
7. 为 multi-day rollout 写集成测试。
```

#### 2.13 工作 11：建立仿真规则版本管理

仿真规则会影响所有实验结果，因此必须版本化。不同的履约优先级、调拨裁剪方式、RDC 保留库存规则、容量约束口径都会改变指标。

需要记录的版本字段：

```text
simulation_rule_version
policy_version
data_version
assortment_version
cost_config_version
lead_time_config_version
experiment_id
```

simulation_manifest 推荐字段：

```text
experiment_id: exp_001
data_version: v001
assortment_version: baseline_topk_v001
policy_version: base_stock_v001
simulation_rule_version: sim_v001
cost_config_version: cost_v001
lead_time_config_version: leadtime_v001
simulation_start_date: 2026-01-01
simulation_end_date: 2026-01-30
created_at: 2026-06-26
```

具体步骤：

```text
1. 每次仿真运行前生成 experiment_id。
2. 记录输入数据版本、策略版本、选品版本和仿真规则版本。
3. 将配置、输出和指标放入同一个 experiment 目录。
4. 确保后续能用 manifest 复现同一次仿真。
```

#### 2.14 第二阶段推荐实施顺序

建议按下面顺序推进：

```text
1. 定义仿真输入输出表契约
2. 设计 SimulationState 和 SimulationContext
3. 实现仿真初始化
4. 实现 lead time 和 pipeline 到货逻辑
5. 实现 NoTransferPolicy 和 HistoricalMeanPolicy
6. 实现调拨裁剪与硬约束检查
7. 实现 FDC 本地履约、RDC 代履约和 lost sales
8. 实现库存状态更新
9. 实现成本计算和指标汇总
10. 实现仿真输出表和 manifest
11. 构建 toy dataset 做单元测试
12. 使用 synthetic v001 跑完整多日仿真
13. 输出第一版 simulation report
```

#### 2.15 第二阶段完成标准

第二阶段完成后，至少需要满足：

```text
能读取第一阶段生成的数据
能初始化 RDC/FDC/SKU 库存状态
能处理 lead time 和在途库存
能接入至少一种 baseline 调拨策略
能模拟 FDC 本地履约、RDC 代履约和 lost sales
能跨多天滚动更新库存状态
能输出 transfer_result、fulfillment_result、cost_result、daily_state 和 metrics_summary
能计算 FDC Ful.、Reg. Loss、Loss Ratio、Transfer Cost 等指标
能通过基础库存守恒和需求守恒校验
能通过 toy dataset 单元测试
能通过 experiment_id 和 simulation_manifest 复现仿真结果
```

做到这里，业务仿真环境就可以作为后续选品算法和库存分配算法的统一评估底座。

### 阶段 3：前置仓选品系统建设

目标：解决“每个 FDC 应该放哪些 SKU”的问题。第三阶段的核心是根据历史订单结构、候选 SKU 池、FDC 容量约束和未来需求信号，为每个 FDC 生成可执行的 SKU assortment。

这一阶段只解决“放什么”，不解决“放多少”。也就是说，前置仓选品决定的是 FDC 的商品池和订单结构覆盖能力；库存数量、补货和调拨由后续库存分配阶段处理。

选品主流程：

```text
读取 data/processed 和 data/features
  -> 构建每个 FDC、每个 anchor_date 的候选 SKU 池
  -> 计算每个 FDC 的 K 值
  -> 运行 Top-K baseline
  -> 运行 Reverse-Exclude
  -> 运行 Hybrid Selection
  -> 后续加入 ML-Top-K
  -> 在 validation / test 窗口回放订单覆盖
  -> 输出 assortment_result 和指标报告
```

#### 3.1 选品系统定位与边界

前置仓选品系统需要保持与库存分配解耦。它输出 SKU-FDC 关系，不直接输出库存数量。

选品系统负责：

```text
构建每个 FDC 的候选 SKU 池
计算每个 FDC 的选品容量 K
实现不同选品算法
生成每个 FDC 的最终 SKU 集合
评估订单结构覆盖率
记录选品结果版本
```

选品系统不负责：

```text
决定每个 SKU 备多少库存
生成 RDC 到 FDC 的调拨量
模拟库存消耗和 lost sales
修改真实订单需求
使用测试窗口订单构建训练特征
```

核心业务指标：

```text
Local Order Fulfillment Rate
测试窗口内，订单中所有 regular SKU 都被选入对应 FDC assortment 的比例。

SKU Frequency Recall@K
Top-K SKU 覆盖未来 SKU order frequency 的比例。

NDCG@K
衡量高未来订单频次 SKU 是否排在更前面。
```

#### 3.2 目录与模块规划

第三阶段应建立独立的 `assortment/` 目录，与 `data/`、`simulation/` 同级。这样选品相关的配置、算法、输出、指标、报告和版本都沉淀在 `assortment/` 下。

建议目录结构：

```text
FAIA/
├── data/
│   └── ...
│
├── simulation/
│   └── ...
│
├── assortment/
│   ├── README.md
│   ├── configs/
│   │   ├── assortment_small.yaml
│   │   └── assortment_default.yaml
│   ├── schemas/
│   │   ├── candidate_pool.schema.yaml
│   │   ├── k_table.schema.yaml
│   │   ├── assortment_result.schema.yaml
│   │   └── assortment_metrics.schema.yaml
│   ├── methods/
│   │   ├── topk.yaml
│   │   ├── reverse_exclude.yaml
│   │   ├── hybrid.yaml
│   │   └── ml_topk.yaml
│   ├── models/
│   │   └── ml_topk/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── candidate_pool.py
│   │   ├── k_selector.py
│   │   ├── topk.py
│   │   ├── reverse_exclude.py
│   │   ├── hybrid.py
│   │   ├── ml_topk.py
│   │   ├── evaluator.py
│   │   ├── metrics.py
│   │   └── validation.py
│   ├── scripts/
│   │   ├── run_assortment.py
│   │   ├── evaluate_assortment.py
│   │   ├── tune_hybrid_ratio.py
│   │   └── train_ml_topk.py
│   ├── tests/
│   │   ├── test_candidate_pool.py
│   │   ├── test_topk.py
│   │   ├── test_reverse_exclude.py
│   │   ├── test_hybrid.py
│   │   └── test_evaluator.py
│   ├── runs/
│   │   └── <experiment_id>/
│   │       ├── candidate_pool.csv
│   │       ├── k_table.csv
│   │       ├── topk_result.csv
│   │       ├── reverse_exclude_result.csv
│   │       ├── hybrid_result.csv
│   │       ├── assortment_result.csv
│   │       ├── assortment_metrics.json
│   │       └── assortment_manifest.yaml
│   └── reports/
│       └── <experiment_id>_assortment_report.md
│
├── inventory/
│   └── ...
```

`assortment/` 目录职责：

```text
assortment/README.md
说明第三阶段选品系统目标、输入输出、运行方式、算法版本和指标口径。

assortment/configs/
存放选品运行配置，例如 data_version、anchor_date、历史窗口、预测窗口、K 计算规则、候选池版本等。

assortment/schemas/
存放候选池、K 表、选品结果表和指标表的 schema。

assortment/methods/
存放不同选品算法的配置，例如 Top-K 排序字段、Reverse-Exclude batch size、Hybrid ratio 等。

assortment/models/
存放 ML-Top-K 模型产物和训练配置。

assortment/src/
存放候选池构建、K 计算、Top-K、Reverse-Exclude、Hybrid、ML-Top-K、评估和校验代码。

assortment/scripts/
存放选品运行、评估、调参和训练入口脚本。

assortment/tests/
存放选品系统单元测试和小规模集成测试。

assortment/runs/
存放每次选品实验运行结果，按 experiment_id 分目录管理。

assortment/reports/
存放选品实验报告和复盘文档。
```

#### 3.3 工作 1：定义选品输入与输出契约

选品系统需要先明确读取哪些数据、输出哪些表。后续仿真和库存分配都依赖选品输出。

核心输入：

```text
sku_master
商品主数据，用于过滤 regular product、大件、特殊商品、不可售商品。

warehouse_master
仓网主数据，用于确定 FDC 所属 RDC、城市、区域和容量。

sku_fdc_eligibility
SKU-FDC 可履约关系，用于过滤不能进入某个 FDC 的 SKU。

fdc_sku_daily_demand
FDC-SKU-day 历史订单包含次数，用于 Top-K 和特征构建。

order_type_table / order_type_items
订单类型和订单内 SKU 组合，用于 Reverse-Exclude 和订单覆盖评估。

candidate_pool_base
候选池基础表，来自第一阶段 processed 数据。

promotion_plan / calendar
未来已知促销和日历计划，用于 ML-Top-K 和候选池召回。

features/ml_topk
ML-Top-K 使用的历史序列、未来外生特征和静态特征。

splits
训练、验证、测试日期切分。
```

核心输出：

```text
candidate_pool
每个 fdc_id、anchor_date 下可参与选品排序的 SKU 集合。

k_table
每个 fdc_id、anchor_date 的 K 值和计算来源。

method_result
每个算法输出的 SKU、rank、score、source_tag。

assortment_result
最终对外提供的 FDC-SKU 选品结果。

assortment_metrics
不同算法在验证或测试窗口上的订单覆盖指标。

assortment_manifest
记录数据版本、候选池版本、算法版本、K 规则和评估窗口。
```

具体步骤：

```text
1. 明确选品系统读取 data/ 下的哪些表。
2. 定义 candidate_pool、k_table、assortment_result、assortment_metrics 的 schema。
3. 规定所有输出必须带 run_date、anchor_date、effective_date、data_version、assortment_version。
4. 固定选品结果供 simulation 和 inventory 阶段消费的接口。
```

#### 3.4 工作 2：构建候选 SKU 池

候选池决定算法能从哪些 SKU 中选择。候选池过窄会让算法无法选到关键 SKU；候选池过宽会增加计算成本并引入大量无意义 SKU。

候选池构建原则：

```text
必须按 fdc_id 和 anchor_date 构建，不能全局共用一个 SKU 池。
只能使用 anchor_date 当时可见的信息。
必须过滤不可售、不可履约、大件、特殊商品、直发商品等 SKU。
不能因为 FDC 级历史销量低就直接过滤低频 SKU。
必须保留未来已知促销 SKU、新品、战略 SKU 和共购结构中重要的 SKU。
```

候选池来源：

```text
当前 FDC 已有 assortment
FDC 近期有需求的 SKU
城市近期热门 SKU
全国热门 SKU
未来已知促销 SKU
计划上新 SKU
战略 SKU
Reverse-Exclude 订单窗口中出现过的 SKU
```

阶段产出：

```text
assortment/runs/<experiment_id>/candidate_pool.csv
```

具体步骤：

```text
1. 读取 candidate_pool_base。
2. 按 fdc_id、anchor_date 过滤 RDC 供给范围。
3. 过滤非 regular product、大件、特殊商品、虚拟商品、直发商品。
4. 根据 sku_fdc_eligibility 过滤不可履约 SKU。
5. 根据上下架状态和生命周期过滤不可售 SKU。
6. 通过多路召回保留低频但可能重要的 SKU。
7. 为每个候选 SKU 记录 candidate_source。
8. 输出 candidate_pool 并记录 candidate_pool_version。
```

#### 3.5 工作 3：计算每个 FDC 的 K 值

K 表示每个 FDC 最终可以选入多少 SKU。K 不建议写死成全局常量，因为不同 FDC 的服务区域、订单结构、仓容和运营能力不同。

K 的推荐口径：

```text
K_j_t = min(K_history_coverage, K_physical_capacity)
```

其中：

```text
K_history_coverage
使用 anchor_date 之前的历史 regular orders，找到能覆盖目标历史订单比例的最小 SKU 数。

K_physical_capacity
由 FDC 物理货位、温区能力、SKU 体积、业务限制等决定。
```

第一版可先使用简化口径：

```text
按历史 Top-K 覆盖 70% regular orders 计算 K_history_coverage。
如果没有真实容量约束，先使用配置中的 fdc_capacity_k。
```

阶段产出：

```text
assortment/runs/<experiment_id>/k_table.csv
```

具体步骤：

```text
1. 读取每个 FDC 在历史窗口内的 regular orders。
2. 基于候选池统计 SKU 历史订单包含次数。
3. 按历史订单包含次数排序。
4. 逐步增加 SKU，计算历史订单完整覆盖率。
5. 找到达到目标覆盖率的最小 K。
6. 与物理容量 K 取较小值。
7. 输出 k_table，记录 k_value、coverage_target、physical_capacity、k_source。
```

#### 3.6 工作 4：实现 Top-K baseline

Top-K 是第一阶段最重要的 baseline。它用于建立最简单可解释的对照组，也用于验证候选池、K 计算和评估流程是否正确。

默认 Top-K 分数：

```text
topk_score = history_order_frequency
```

其中 history_order_frequency 表示历史窗口内 SKU 被去重订单包含的次数，不是销售件数。

同分排序规则：

```text
primary_score desc
current_fdc_assortment desc
recent_order_cnt desc
future_promo_known desc
sku_id asc
```

阶段产出：

```text
assortment/runs/<experiment_id>/topk_result.csv
```

具体步骤：

```text
1. 读取 candidate_pool 和 k_table。
2. 统计每个 FDC-SKU 在历史窗口内的订单包含次数。
3. 按 topk_score 排序。
4. 每个 FDC 选择前 K 个 SKU。
5. 输出 sku_id、rank、score、method=topk。
6. 用 evaluator 在验证窗口计算 local_order_fulfillment_rate@K。
```

#### 3.7 工作 5：实现 Reverse-Exclude

Reverse-Exclude 用于捕捉多商品订单的共购结构。它不是从空集合开始添加 SKU，而是从候选全集开始，逐步删除对订单完整覆盖影响最小的 SKU。

核心思想：

```text
如果删除某个 SKU 后，受影响的订单很少，说明它对订单完整覆盖不重要，可以优先删除。
如果删除某个 SKU 后，很多订单都会失效，说明它在订单结构中重要，应该保留。
```

核心数据结构：

```text
sku_to_orders
快速找到包含某个 SKU 的订单类型。

order_to_skus
记录每个订单类型包含哪些 SKU。

active_order
标记订单类型是否仍可能被完整覆盖。

active_sku
标记 SKU 是否仍保留。

influence
当前有效订单集合下 SKU 的 order influence。

min_heap
按 influence 从小到大删除 SKU。
```

阶段产出：

```text
assortment/runs/<experiment_id>/reverse_exclude_result.csv
```

具体步骤：

```text
1. 读取 candidate_pool、order_type_table、order_type_items 和 k_table。
2. 只保留候选池内 regular SKU 组成的订单类型。
3. 初始化 active_sku 和 active_order。
4. 计算每个 SKU 的初始 influence。
5. 将 influence 写入最小堆。
6. 当 active_sku_count > K 时，删除 influence 最小的 SKU。
7. 删除 SKU 后，将包含该 SKU 的 active_order 置为失效。
8. 将失效订单对其他 SKU 的 influence 贡献扣除。
9. 使用 lazy heap update 避免全量重算。
10. 输出最终保留 SKU 集合 R、reverse_score、reverse_rank。
```

复杂度目标：

```text
朴素实现约为 O((|N|-K) * E_order_sku)
增量堆实现应尽量接近 O(E_order_sku * log |N|)
```

#### 3.8 工作 6：实现 Hybrid Selection

Hybrid Selection 融合 ML-Top-K 或 Top-K 的未来需求信号，以及 Reverse-Exclude 的历史共购结构信号。第一版没有 ML-Top-K 时，可以先使用 Top-K 结果代替 ML 结果；后续再切换到 ML-Top-K。

集合定义：

```text
M = ML-Top-K 或 Top-K 输出集合
R = Reverse-Exclude 输出集合
I = M ∩ R
D_M = M - I
D_R = R - I
```

名额分配：

```text
remaining = K - |I|
n_M = ceil(remaining * r)
n_R = remaining - n_M
```

默认 hybrid ratio：

```text
r = 0.4
```

后续通过验证窗口调参：

```text
candidate_r = [0.0, 0.1, 0.2, ..., 1.0]
选择 validation local_order_fulfillment_rate@K 最高的 r。
```

阶段产出：

```text
assortment/runs/<experiment_id>/hybrid_result.csv
```

具体步骤：

```text
1. 读取 Top-K 或 ML-Top-K 输出集合 M。
2. 读取 Reverse-Exclude 输出集合 R。
3. 计算交集 I 和差集 D_M、D_R。
4. 交集 SKU 直接进入最终集合。
5. 按 r 分配剩余名额。
6. D_M 按 ML 或 Top-K score 排序选取。
7. D_R 按 reverse_score 排序选取。
8. 如果某侧不足，从另一侧回填。
9. 如果仍不足，从 candidate_pool 按 fallback_score 补齐。
10. 输出最终集合 S，并记录 source_tag。
```

source_tag：

```text
intersection
ml_only
reverse_only
fallback
```

#### 3.9 工作 7：预留并逐步实现 ML-Top-K

ML-Top-K 是前置仓选品中的机器学习版本，用于预测每个 SKU 未来会出现在多少订单中，然后按预测订单包含次数选 Top-K。

第一版可以暂时不训练复杂模型，但需要提前固定接口，避免后续接入困难。

ML-Top-K 输入：

```text
fdc_id
sku_id
anchor_date
历史 L 天 FDC-SKU 订单序列
类目、品牌、区域、全国 SKU 历史需求
未来 H 天促销计划
未来 H 天日历特征
SKU、类目、品牌、FDC、城市静态特征
```

ML-Top-K 输出：

```text
ml_score
未来 H 天预测 order frequency 之和。

daily_forecast
未来 H 天逐日 SKU order frequency 预测。

ml_rank
每个 FDC 内的排序名次。
```

阶段产出：

```text
assortment/models/ml_topk/
assortment/runs/<experiment_id>/ml_topk_result.csv
```

具体步骤：

```text
1. 先定义 ML-Top-K 的输入特征表和输出结果表。
2. 第一版可使用简单模型，例如 LightGBM、线性模型或小型 MLP。
3. 训练标签使用未来 H 天订单包含次数，不使用销售件数。
4. 训练、验证、测试必须按时间切分。
5. 模型选择主指标仍然是 validation local_order_fulfillment_rate@K，而不是单纯预测误差。
6. 后续再升级为 Trend/Seasonal + TCN + MLP Path 的深度模型。
```

#### 3.10 工作 8：实现选品评估器

选品评估器用于比较不同选品方法在验证或测试窗口上的订单结构覆盖效果。

核心评估逻辑：

```text
对每个 fdc_id 和 anchor_date：
  1. 读取该 FDC 的选品集合 S
  2. 读取评估窗口内真实 regular orders
  3. 对每个订单判断订单内所有 SKU 是否都在 S 中
  4. fulfilled_by_assortment = all sku in order are in S
  5. local_order_fulfillment_rate = fulfilled_order_count / total_order_count
```

评估指标：

```text
local_order_fulfillment_rate@K
主指标，直接对应论文第一阶段指标。

SKU_Frequency_Recall@K
辅助指标，衡量 Top-K SKU 覆盖未来 SKU order frequency 的能力。

NDCG@K
辅助排序指标，衡量高未来订单频次 SKU 是否排在前面。

coverage_by_order_size
按单品订单、2 件订单、3 件及以上订单分层看覆盖率。

coverage_by_category
按品类分析覆盖情况。
```

阶段产出：

```text
assortment/runs/<experiment_id>/assortment_metrics.json
assortment/reports/<experiment_id>_assortment_report.md
```

具体步骤：

```text
1. 读取选品结果和评估窗口订单。
2. 过滤非 regular product orders。
3. 对每个订单计算是否被 assortment 完整覆盖。
4. 聚合 FDC、RDC、city、整体层级指标。
5. 比较 Top-K、Reverse-Exclude、Hybrid、ML-Top-K。
6. 输出 metrics_summary 和报告。
```

#### 3.11 工作 9：定义选品结果输出与版本管理

选品结果会被第二阶段仿真器和第四阶段库存分配模块消费，因此必须标准化、版本化。

assortment_result 推荐字段：

```text
run_date
anchor_date
effective_date
rdc_id
fdc_id
sku_id
rank
score
method
source_tag
k_value
data_version
candidate_pool_version
k_rule_version
method_version
assortment_version
experiment_id
```

assortment_manifest 推荐字段：

```text
experiment_id: exp_assortment_001
data_version: v001
candidate_pool_version: candidate_v001
k_rule_version: k_rule_v001
method: hybrid
method_version: hybrid_v001
hybrid_ratio: 0.4
history_window: 56
eval_window: 14
assortment_version: assortment_v001
created_at: 2026-06-26
```

具体步骤：

```text
1. 每次选品运行前生成 experiment_id。
2. 记录 data_version、candidate_pool_version、K 规则版本和方法版本。
3. 生成 assortment_version。
4. 将候选池、K 表、各方法结果、最终结果和指标放入同一个 runs 目录。
5. 保证 simulation 阶段只通过 assortment_version 读取选品结果。
```

#### 3.12 工作 10：实现选品校验与单元测试

选品系统必须保证输出结果合法，否则后续库存分配和仿真都会受到影响。

基础校验：

```text
每个 FDC 输出 SKU 数量不能超过 K
输出 SKU 必须来自 candidate_pool
输出 SKU 必须满足 sku_fdc_eligibility
输出 SKU 必须是 regular product
同一 FDC 内 sku_id 不能重复
rank 必须连续且唯一
source_tag 必须来自合法枚举
评估窗口不能参与训练特征构建
```

推荐单元测试场景：

```text
候选池过滤能排除不可履约 SKU。
K 计算能在达到目标覆盖率时停止。
Top-K 能按历史订单包含次数排序。
Reverse-Exclude 能在简单共购例子中保留关键共购 SKU。
Hybrid 能正确保留交集并按 r 分配差集名额。
Evaluator 能正确判断多商品订单是否完整覆盖。
```

具体步骤：

```text
1. 构建 toy candidate pool。
2. 构建 toy orders 和 order_items。
3. 测试 Top-K 排序。
4. 测试 Reverse-Exclude 删除逻辑。
5. 测试 Hybrid Selection 名额分配和回填。
6. 测试 local_order_fulfillment_rate 计算。
7. 测试输出 schema 和版本字段。
```

#### 3.13 第三阶段推荐实施顺序

建议按下面顺序推进：

```text
1. 创建 assortment/ 目录骨架
2. 编写 assortment/README.md
3. 定义 candidate_pool、k_table、assortment_result、assortment_metrics schema
4. 实现候选池构建
5. 实现 K 计算
6. 实现 Top-K baseline
7. 实现选品评估器
8. 实现 Reverse-Exclude
9. 实现 Hybrid Selection
10. 实现 hybrid ratio 调参流程
11. 定义 ML-Top-K 输入输出接口
12. 后续实现 ML-Top-K 简版模型
13. 输出 assortment_manifest 和选品报告
14. 将 assortment_result 接入 simulation 阶段
```

#### 3.14 第三阶段完成标准

第三阶段完成后，至少需要满足：

```text
能读取 data/processed 和 data/features
能为每个 FDC、anchor_date 构建候选 SKU 池
能为每个 FDC 计算 K
能运行 Top-K baseline
能运行 Reverse-Exclude
能运行 Hybrid Selection
能输出标准 assortment_result
能计算 local_order_fulfillment_rate@K
能比较不同选品方法的效果
能通过候选池、K、Top-K、Reverse-Exclude、Hybrid 和 evaluator 单元测试
能通过 assortment_version 被 simulation 阶段读取
能通过 assortment_manifest 复现同一次选品实验
```

做到这里，前置仓选品系统就可以为后续库存分配提供稳定的 FDC-SKU 商品池。

### 阶段 4：库存分配系统建设

目标：解决“选好 SKU 后，每天给 FDC 分多少库存”的问题。第四阶段的核心是基于前置仓选品结果、当前库存、在途库存、需求预测、lead time、成本参数和业务约束，生成每日 RDC -> FDC 的库存分配建议。

这一阶段解决的是“放多少”，而不是“放什么”。`assortment/` 阶段输出哪些 SKU-FDC 组合可以经营，`inventory/` 阶段在这些组合内决定安全库存、目标库存和建议调拨量。

库存分配主流程：

```text
读取 data、assortment、simulation 输入
  -> 构建库存分配样本和状态
  -> 生成需求预测或读取预测结果
  -> 运行库存 baseline 策略
  -> 生成 safety_stock 和 target_inventory
  -> 生成 recommended_transfer_qty
  -> 调用 simulation 回放履约效果
  -> 计算 FDC Ful.、Reg. Loss、Loss Ratio、Transfer Cost
  -> 后续加入 Forecasting + TI/SS + Simulation 端到端模型
```

#### 4.1 库存分配系统定位与边界

库存分配系统需要承接前两个核心模块：它消费 `assortment/` 的 FDC-SKU 商品池，也依赖 `simulation/` 来评估策略执行效果。

库存分配系统负责：

```text
读取 FDC-SKU 选品结果
读取 RDC/FDC 当前库存和在途库存
生成未来需求预测或消费已有预测
生成安全库存 SS 和目标库存 TI
生成 RDC -> FDC 建议调拨量
管理 RDC 自留库存与 FDC 下发库存之间的权衡
输出库存策略结果并记录版本
```

库存分配系统不负责：

```text
决定 FDC 应该经营哪些 SKU
修改用户真实需求
替代 simulation 模块做履约回放
绕过业务硬约束直接输出非法调拨
使用未来真实需求作为线上推理特征
```

核心业务目标：

```text
提高 FDC 本地需求满足率
降低 RDC 代履约量
降低 lost sales
控制 RDC -> FDC 调拨成本
保证 RDC 自身和兜底履约库存安全
```

#### 4.2 目录与模块规划

第四阶段应建立独立的 `inventory/` 目录，与 `data/`、`simulation/`、`assortment/` 同级。库存分配相关的配置、策略、模型、输出、训练结果和报告都沉淀在 `inventory/` 下。

建议目录结构：

```text
FAIA/
├── data/
│   └── ...
│
├── simulation/
│   └── ...
│
├── assortment/
│   └── ...
│
├── inventory/
│   ├── README.md
│   ├── configs/
│   │   ├── inventory_small.yaml
│   │   └── inventory_default.yaml
│   ├── schemas/
│   │   ├── inventory_state.schema.yaml
│   │   ├── demand_forecast.schema.yaml
│   │   ├── tiss_result.schema.yaml
│   │   ├── transfer_recommendation.schema.yaml
│   │   └── inventory_metrics.schema.yaml
│   ├── policies/
│   │   ├── historical_mean.yaml
│   │   ├── base_stock.yaml
│   │   ├── parameter_search.yaml
│   │   └── greedy_allocation.yaml
│   ├── models/
│   │   ├── forecasting/
│   │   └── tiss/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── state_builder.py
│   │   ├── forecasting.py
│   │   ├── tiss.py
│   │   ├── policies.py
│   │   ├── allocator.py
│   │   ├── loss.py
│   │   ├── trainer.py
│   │   ├── inference.py
│   │   ├── evaluator.py
│   │   └── validation.py
│   ├── scripts/
│   │   ├── run_inventory_baseline.py
│   │   ├── run_inventory_inference.py
│   │   ├── train_forecasting.py
│   │   ├── train_tiss.py
│   │   └── evaluate_inventory.py
│   ├── tests/
│   │   ├── test_state_builder.py
│   │   ├── test_forecasting.py
│   │   ├── test_tiss.py
│   │   ├── test_allocator.py
│   │   └── test_inference.py
│   ├── runs/
│   │   └── <experiment_id>/
│   │       ├── inventory_state.csv
│   │       ├── demand_forecast.csv
│   │       ├── tiss_result.csv
│   │       ├── transfer_recommendation.csv
│   │       ├── simulation_metrics.json
│   │       └── inventory_manifest.yaml
│   └── reports/
│       └── <experiment_id>_inventory_report.md
```

`inventory/` 目录职责：

```text
inventory/README.md
说明第四阶段库存分配系统目标、输入输出、策略口径、训练推理方式和指标解释。

inventory/configs/
存放库存分配运行配置，例如 data_version、assortment_version、simulation_rule_version、预测窗口、rollout 窗口等。

inventory/schemas/
存放库存状态、需求预测、TI/SS 输出、调拨建议和指标结果的 schema。

inventory/policies/
存放库存分配 baseline 策略配置，例如历史均值、base-stock、参数搜索、贪心分配等。

inventory/models/
存放需求预测模型和 TI/SS 模型产物。

inventory/src/
存放库存状态构建、预测、TI/SS 生成、调拨分配、训练、推理、评估和校验代码。

inventory/scripts/
存放 baseline 运行、模型训练、模型推理和评估入口脚本。

inventory/tests/
存放库存分配模块单元测试和小规模集成测试。

inventory/runs/
存放每次库存分配实验运行结果，按 experiment_id 分目录管理。

inventory/reports/
存放库存分配实验报告和复盘文档。
```

#### 4.3 工作 1：定义库存分配输入与输出契约

库存分配系统要和 `data/`、`assortment/`、`simulation/` 打通，因此必须先固定输入输出契约。

核心输入：

```text
assortment_result
第三阶段输出的 FDC-SKU 选品结果，用于限制哪些 SKU 可以进入 FDC 库存分配。

inventory_daily_state
RDC/FDC 当前库存状态。

transfer_plan / pipeline_inventory
历史已发出但未到货的在途调拨。

fdc_sku_daily_demand
历史 FDC-SKU 需求序列。

orders / order_items
真实需求回放数据，用于训练标签和仿真评估。

promotion_plan / calendar
未来已知促销和日期特征。

warehouse_master
RDC-FDC 网络关系、容量、温区、收货限制等。

sku_master
SKU 类目、品牌、温层、体积、保质期等属性。

cost_config
调拨成本、RDC 代履约成本、lost sales 成本。

lead_time_config
RDC 到 FDC 的调拨提前期。

simulation_rule_version
用于调用仿真器评估策略效果。
```

核心输出：

```text
demand_forecast
未来 H 天 SKU-node 需求预测。

tiss_result
每个 SKU-node-date 的 safety_stock 和 target_inventory。

transfer_recommendation
RDC -> FDC 的建议调拨量。

inventory_metrics
库存分配策略经 simulation 回放后的指标。

inventory_manifest
记录输入版本、策略版本、模型版本、仿真规则版本和实验配置。
```

具体步骤：

```text
1. 定义 inventory_state、demand_forecast、tiss_result、transfer_recommendation 的 schema。
2. 明确库存分配读取哪些 data/processed、assortment/runs 和 simulation 配置。
3. 固定所有输出字段必须带 data_version、assortment_version、inventory_version、simulation_rule_version。
4. 保证 transfer_recommendation 可以直接被 simulation 阶段消费。
```

#### 4.4 工作 2：构建库存状态样本

库存分配不是静态预测任务，它依赖当前库存、在途库存、历史需求、lead time 和选品结果。

需要构建的状态：

```text
rdc_on_hand_inventory
每个 RDC-SKU 当前可用库存。

fdc_on_hand_inventory
每个 FDC-SKU 当前可用库存。

pipeline_inventory
已经发出但尚未到 FDC 的在途库存。

assortment_mask
第一阶段选品结果，未选入 SKU-FDC 不允许生成有效 FDC 库存水位。

eligible_mask
SKU-FDC 是否可履约、可售、可调拨。

lead_time
RDC 到 FDC 的调拨提前期。

capacity_state
FDC 剩余容量、收货上限、RDC 出库上限。
```

阶段产出：

```text
inventory/runs/<experiment_id>/inventory_state.csv
```

具体步骤：

```text
1. 读取 simulation 或 data 中的库存状态。
2. 根据 assortment_result 构建 assortment_mask。
3. 根据 sku_fdc_eligibility 构建 eligible_mask。
4. 读取 pipeline_inventory，按到货剩余天数展开。
5. 读取 lead_time_config。
6. 计算 RDC 可用库存、RDC 预留库存、FDC 可用库存和 FDC 剩余容量。
7. 输出库存状态表，供 baseline、模型和仿真使用。
```

#### 4.5 工作 3：实现需求预测模块

需求预测是库存分配的输入之一。第一版不必直接上复杂深度模型，可以先使用简单、可解释、可调试的预测方法。

第一版预测 baseline：

```text
HistoricalMeanForecast
使用最近 L 天均值预测未来需求。

MovingAverageForecast
使用滑动平均和短期趋势预测。

SeasonalNaiveForecast
使用同星期历史需求预测。

PromotionAdjustedForecast
在历史均值基础上叠加促销放大系数。
```

后续模型升级方向：

```text
ForecastingModule
输入历史需求、多层级需求、促销、日历、SKU/FDC/RDC 静态特征，输出未来 H 天需求预测。
```

阶段产出：

```text
inventory/runs/<experiment_id>/demand_forecast.csv
```

具体步骤：

```text
1. 定义预测粒度，例如 sku_id、node_id、date。
2. 构建历史窗口 [t-L, t-1]。
3. 构建预测窗口 [t, t+H-1]。
4. 实现历史均值和移动平均预测。
5. 将未来已知促销和日历特征作为修正项。
6. 输出 demand_forecast。
7. 使用真实未来需求计算预测诊断指标，但模型选择不能只看预测误差。
```

#### 4.6 工作 4：实现安全库存和目标库存策略

库存分配阶段需要生成两个可解释库存水位：

```text
SS：Safety Stock，安全库存
TI：Target Inventory，目标库存
```

SS 用于抵御需求波动、预测误差和 lead time 风险。TI 用于表达希望补到的目标库存水位。

第一版规则：

```text
demand_during_lead_time = forecast_daily_demand * lead_time
uncertainty_buffer = service_factor * historical_demand_std * sqrt(lead_time)
SS = demand_during_lead_time + uncertainty_buffer
TI = SS + forecast_demand_during_replenishment_window
```

约束：

```text
TI >= SS >= 0
未选入 assortment 的 SKU-FDC，SS = 0 且 TI = 0
不可履约 SKU-FDC，SS = 0 且 TI = 0
```

阶段产出：

```text
inventory/runs/<experiment_id>/tiss_result.csv
```

具体步骤：

```text
1. 读取 demand_forecast。
2. 读取 historical_demand_std 和 forecast_error。
3. 读取 lead_time。
4. 按规则计算 SS_base。
5. 按规则计算 TI_base。
6. 应用 assortment_mask 和 eligible_mask。
7. 做 ConstraintProjection，保证 TI >= SS >= 0。
8. 输出 tiss_result。
```

#### 4.7 工作 5：实现库存分配 baseline 策略

在端到端模型之前，需要先实现可解释 baseline，作为后续模型比较对象。

推荐 baseline：

```text
NoTransfer
不调拨，只用于验证仿真器和指标下界。

HistoricalMeanReplenishment
根据历史均值补货。

BaseStockPolicy
根据 SS 和 TI 计算缺口，优先补安全库存，再补目标库存。

ParameterSearchPolicy
搜索不同 service_factor 或 safety_factor，通过 simulation 选择表现最好的参数。

GreedyAllocationPolicy
当 RDC 库存不足时，按需求强度、缺货成本、服务权重排序分配库存。
```

阶段产出：

```text
inventory/runs/<experiment_id>/transfer_recommendation.csv
```

具体步骤：

```text
1. 实现 NoTransfer baseline。
2. 实现 HistoricalMeanReplenishment。
3. 实现 BaseStockPolicy，基于 SS/TI 缺口生成 recommended_transfer_qty。
4. 实现 ParameterSearchPolicy，搜索安全系数和目标库存系数。
5. 实现 GreedyAllocationPolicy，用于 RDC 库存不足时的分配排序。
6. 所有策略输出统一 transfer_recommendation schema。
```

#### 4.8 工作 6：实现 RDC 自留库存与 FDC 调拨权衡

库存分配的核心难点是 RDC 既是 FDC 的上游补货仓，又是自身需求和 FDC 缺货后的兜底履约节点。因此，RDC 不能把所有库存都发给 FDC。

RDC 库存用途：

```text
RDC 自身需求履约
FDC 缺货后的 RDC 代履约
向 FDC 调拨库存
RDC 安全库存预留
```

推荐规则：

```text
rdc_reserved_inventory = max(SS_rdc, business_reserved_inventory)
rdc_allocatable_inventory = max(rdc_on_hand_inventory - rdc_reserved_inventory, 0)
```

FDC 缺口优先级：

```text
priority_score =
  forecast_demand
  * lost_sales_cost
  * service_weight
  * promo_weight
  / max(current_inventory + expected_arrival, 1)
```

具体步骤：

```text
1. 为 RDC 节点也计算 SS 和 TI。
2. 计算 RDC 自留库存。
3. 只允许 rdc_allocatable_inventory 参与 FDC 调拨。
4. 当 RDC 库存不足时，按 priority_score 分配给 FDC。
5. 输出被满足缺口和未满足缺口。
6. 将规则版本写入 inventory_manifest。
```

#### 4.9 工作 7：调用 simulation 评估库存策略

库存分配策略本身只能输出建议调拨量，真正效果必须通过 `simulation/` 回放评估。

评估闭环：

```text
inventory strategy 输出 transfer_recommendation
  -> simulation 读取 transfer_recommendation
  -> simulation 回放库存、调拨、履约、缺货
  -> 输出 fulfillment_result、cost_result、metrics_summary
  -> inventory 汇总策略效果
```

阶段产出：

```text
inventory/runs/<experiment_id>/simulation_metrics.json
inventory/reports/<experiment_id>_inventory_report.md
```

具体步骤：

```text
1. 将 transfer_recommendation 写成 simulation 可消费格式。
2. 调用 simulation/runs 或 simulation engine。
3. 使用相同 simulation_rule_version 比较不同库存策略。
4. 读取 simulation 输出的 metrics_summary。
5. 汇总 FDC Ful.、Reg. Loss、Loss Ratio、Transfer Cost。
6. 输出库存策略对比报告。
```

#### 4.10 工作 8：预留端到端库存分配框架

端到端库存分配是第四阶段后续高级版本，不建议第一版直接做复杂模型。第一版应先固定接口，跑通 baseline 和 simulation 闭环，再逐步替换模块。

端到端框架组成：

```text
ForecastingModule
预测未来 SKU-node 需求。

TISSGenerationModule
根据需求预测、库存状态、lead time、历史误差生成 SS 和 TI。

SimulationModule
使用 simulation 逻辑回放调拨、履约和 lost sales。

LossComputer
计算预测损失、运营损失和安全库存违反惩罚。
```

复合损失：

```text
L = lambda_op * L_op + lambda_pred * L_sales_pred + lambda_ss * L_ss
```

其中：

```text
L_op
运营损失，包括 lost sales 成本、调拨成本、RDC 代履约成本。

L_sales_pred
需求预测误差。

L_ss
安全库存违反惩罚。
```

具体步骤：

```text
1. 固定 ForecastingModule 输入输出接口。
2. 固定 TISSGenerationModule 输入输出接口。
3. 固定 LossComputer 输入输出接口。
4. 第一版使用规则 TISS 替代神经网络 TISS。
5. 后续再引入可学习 residual policy。
6. 仿真模块若使用硬规则，先作为评估闭环；若需要严格反传，再考虑 soft allocation 或 straight-through estimator。
```

#### 4.11 工作 9：定义库存结果输出与版本管理

库存分配结果会进入 simulation，也会进入最终业务报告，因此必须标准化和版本化。

transfer_recommendation 推荐字段：

```text
run_date
decision_date
effective_date
rdc_id
fdc_id
sku_id
demand_forecast_qty
safety_stock
target_inventory
current_inventory
pipeline_inventory
recommended_transfer_qty
actual_transfer_qty
policy_name
policy_version
model_version
data_version
assortment_version
simulation_rule_version
inventory_version
experiment_id
```

inventory_manifest 推荐字段：

```text
experiment_id: exp_inventory_001
data_version: v001
assortment_version: assortment_v001
simulation_rule_version: sim_v001
policy_name: base_stock
policy_version: base_stock_v001
model_version: none
inventory_version: inventory_v001
forecast_horizon: 7
rollout_window: 14
created_at: 2026-06-26
```

具体步骤：

```text
1. 每次库存分配运行前生成 experiment_id。
2. 记录 data_version、assortment_version、simulation_rule_version、policy_version。
3. 生成 inventory_version。
4. 将需求预测、TI/SS、调拨建议、仿真指标和报告放入同一个 runs 目录。
5. 确保 simulation 能通过 inventory_version 或 transfer_recommendation 复现策略输入。
```

#### 4.12 工作 10：实现库存分配校验与单元测试

库存分配输出如果非法，会直接破坏仿真结果。因此需要在这一阶段加入校验。

基础校验：

```text
recommended_transfer_qty 必须非负
actual_transfer_qty 不能超过 RDC 可调拨库存
未选入 assortment 的 SKU-FDC 不能生成 FDC 库存水位
不可履约 SKU-FDC 不能生成调拨
TI >= SS >= 0
FDC 调拨后不能超过容量
lead time 到货日期必须合法
训练和推理特征不能使用未来真实需求
```

推荐单元测试场景：

```text
无需求时不应生成明显调拨。
FDC 库存高于 TI 时不应补货。
FDC 库存低于 SS 时应优先补 SS。
RDC 库存不足时，应按 priority_score 分配。
未选品 SKU 的 SS/TI 和调拨量应为 0。
TI/SS 约束应保证 TI >= SS >= 0。
```

具体步骤：

```text
1. 构建 toy inventory state。
2. 测试需求预测 baseline。
3. 测试 SS/TI 计算。
4. 测试 BaseStockPolicy。
5. 测试 RDC 自留库存规则。
6. 测试 GreedyAllocationPolicy。
7. 测试 transfer_recommendation schema。
8. 用 toy simulation 验证库存策略输出可被仿真器消费。
```

#### 4.13 第四阶段推荐实施顺序

建议按下面顺序推进：

```text
1. 创建 inventory/ 目录骨架
2. 编写 inventory/README.md
3. 定义 inventory_state、demand_forecast、tiss_result、transfer_recommendation schema
4. 构建 inventory_state
5. 实现 HistoricalMeanForecast 和 MovingAverageForecast
6. 实现 SS/TI 规则计算
7. 实现 NoTransfer、HistoricalMeanReplenishment、BaseStockPolicy
8. 实现 RDC 自留库存规则
9. 实现 GreedyAllocationPolicy
10. 输出 transfer_recommendation
11. 调用 simulation 回放策略效果
12. 输出 inventory report
13. 固定端到端框架接口
14. 后续逐步加入 ForecastingModule 和 TISSGenerationModule
```

#### 4.14 第四阶段完成标准

第四阶段完成后，至少需要满足：

```text
能读取 data、assortment 和 simulation 的必要输入
能构建 RDC/FDC/SKU 库存状态
能生成需求预测 baseline
能生成 SS 和 TI
能输出 recommended_transfer_qty
能处理 RDC 自留库存和 FDC 调拨之间的权衡
能运行至少一种库存 baseline 策略
能调用 simulation 回放库存策略效果
能输出 FDC Ful.、Reg. Loss、Loss Ratio、Transfer Cost 等指标
能通过库存分配基础校验和单元测试
能通过 inventory_manifest 复现同一次库存策略实验
```

做到这里，库存分配系统就可以形成“库存策略输出 -> 仿真回放 -> 指标评估”的完整闭环，并为后续端到端库存分配模型打好接口基础。

### 阶段 5：评估与实验系统建设

目标：建立统一实验框架，能够稳定比较不同阶段、不同算法、不同策略的效果。第五阶段不是再实现一个新算法，而是把 `data/`、`simulation/`、`assortment/`、`inventory/` 的输出统一收口，形成可复现、可对比、可解释的实验体系。

评估系统要回答的问题：

```text
1. 数据是否可靠？
2. 选品算法是否提升了订单结构覆盖率？
3. 库存策略是否提升了 FDC 本地满足率？
4. 提升是否以更高 lost sales 或调拨成本为代价？
5. 不同 baseline 和模型之间是否在同一口径下公平比较？
6. 一次实验能否被完整复现？
```

#### 5.1 评估系统定位与边界

评估系统是项目的统一裁判。它不直接生成数据、不直接改变选品结果、不直接修改库存策略，而是读取各阶段产物，按照统一指标和统一实验协议进行比较。

评估系统负责：

```text
汇总数据质量报告
汇总选品评估结果
汇总仿真回放结果
汇总库存分配指标
比较 baseline、启发式算法和模型方法
生成实验报告
维护 experiment registry
```

评估系统不负责：

```text
重新生成 synthetic data
重新训练 ML 模型
修改 simulation 规则
修改 assortment 或 inventory 策略输出
绕过版本记录直接比较结果
```

#### 5.2 轻量目录规划

第五阶段可以建立独立的 `evaluation/` 目录，但它不需要像算法阶段那样承载大量核心逻辑。它主要负责指标汇总、实验注册、对比报告和可视化结果。

建议目录结构：

```text
FAIA/
├── evaluation/
│   ├── README.md
│   ├── configs/
│   │   └── evaluation_default.yaml
│   ├── schemas/
│   │   ├── experiment_registry.schema.yaml
│   │   └── metrics_summary.schema.yaml
│   ├── src/
│   │   ├── __init__.py
│   │   ├── collect.py
│   │   ├── metrics.py
│   │   ├── compare.py
│   │   ├── report.py
│   │   └── validation.py
│   ├── scripts/
│   │   ├── collect_results.py
│   │   ├── compare_experiments.py
│   │   └── build_report.py
│   ├── runs/
│   │   └── <evaluation_id>/
│   │       ├── experiment_registry.csv
│   │       ├── metrics_summary.csv
│   │       ├── comparison_table.csv
│   │       └── evaluation_manifest.yaml
│   └── reports/
│       └── <evaluation_id>_report.md
```

#### 5.3 工作 1：统一实验协议

所有算法必须在同一数据版本、同一时间切分、同一仿真规则和同一指标口径下比较。否则结果不可解释。

需要统一的实验口径：

```text
data_version
使用同一批 synthetic 或真实数据。

split_version
使用同一 train / validation / test 日期切分。

assortment_version
库存分配实验必须明确消费哪个选品版本。

simulation_rule_version
库存策略比较必须使用同一仿真规则。

cost_config_version
成本指标比较必须使用同一成本参数。

evaluation_window
明确评估窗口，例如 validation 14 天或 test 14 天。
```

具体步骤：

```text
1. 定义 evaluation_config。
2. 固定数据版本和时间窗口。
3. 固定选品评估口径。
4. 固定库存仿真评估口径。
5. 明确 baseline 和待比较方法列表。
6. 记录所有版本到 evaluation_manifest。
```

#### 5.4 工作 2：统一指标体系

评估指标需要分层，不同阶段看不同主指标，最终再看综合业务指标。

数据层指标：

```text
num_orders
订单数量。

num_order_items
订单明细数量。

num_skus
SKU 数量。

num_rdcs / num_fdcs
仓网规模。

stockout_rate
缺货记录比例。

validation_error_count
数据校验错误数量。
```

选品层指标：

```text
Local Order Fulfillment Rate
订单中所有 SKU 都被选入 FDC assortment 的比例。

SKU_Frequency_Recall@K
选中 SKU 覆盖未来 SKU order frequency 的比例。

NDCG@K
排序质量指标。

coverage_by_order_size
按单品订单、2 件订单、3 件及以上订单分层覆盖率。

coverage_by_category
按品类覆盖率。
```

仿真与库存层指标：

```text
FDC Fulfillment Rate
FDC 需求中由 FDC 本地满足的比例。

RDC Fallback Quantity
FDC 不足后由 RDC 代履约的数量。

Regional Lost Sales
区域 lost sales 数量或比例。

Loss Ratio
regional lost sales / FDC fulfilled sales。

Transfer Cost
RDC -> FDC 调拨成本。

Stock Availability
需求被库存满足的能力。

Inventory Holding Cost
库存持有成本，可作为后续可选指标。
```

综合对比指标：

```text
service_score
服务水平综合得分，可由 FDC Ful.、Stock Availability、Local Fulfillment 加权。

cost_score
成本综合得分，可由 Transfer Cost、Lost Sales Cost、Holding Cost 加权。

business_score
综合业务得分，第一版可以不强制使用，只在报告中保留口径。
```

具体步骤：

```text
1. 为每个指标定义计算公式。
2. 明确指标聚合粒度：SKU、FDC、RDC、day、overall。
3. 明确主指标和辅助指标。
4. 输出统一 metrics_summary.csv。
5. 对关键指标生成分层报告。
```

#### 5.5 工作 3：建立 baseline 对比矩阵

项目需要从一开始保留 baseline，否则后续模型提升无法解释。

选品方法对比：

```text
Top-K
Reverse-Exclude
Hybrid Selection
ML-Top-K
```

库存方法对比：

```text
NoTransfer
HistoricalMeanReplenishment
BaseStockPolicy
ParameterSearchPolicy
GreedyAllocationPolicy
End-to-End Inventory Model
```

组合实验：

```text
Top-K + BaseStock
Reverse-Exclude + BaseStock
Hybrid + BaseStock
Hybrid + GreedyAllocation
ML-Top-K + End-to-End Inventory
```

具体步骤：

```text
1. 定义每次实验的方法组合。
2. 确保每组组合使用同一 data_version 和 simulation_rule_version。
3. 运行各阶段 pipeline 或读取已有 runs。
4. 汇总 comparison_table。
5. 标注每个方法是否为 baseline、heuristic、ml_model 或 e2e_model。
```

#### 5.6 工作 4：实验注册与结果收集

每次实验都要有唯一 `experiment_id`，每次综合评估要有唯一 `evaluation_id`。

experiment_registry 推荐字段：

```text
experiment_id
stage
method_name
data_version
feature_version
candidate_pool_version
assortment_version
inventory_version
simulation_rule_version
policy_version
model_version
run_path
metrics_path
created_at
notes
```

具体步骤：

```text
1. 扫描 data/、simulation/、assortment/、inventory/ 下的 manifest。
2. 抽取 experiment_id 和版本字段。
3. 校验同一 evaluation_id 下的实验是否可比较。
4. 汇总 experiment_registry.csv。
5. 汇总 metrics_summary.csv。
```

#### 5.7 工作 5：生成实验报告

报告不只是列指标，还需要解释提升来源和 trade-off。

报告内容：

```text
实验目标
说明本次比较要回答什么问题。

数据版本
说明 data_version、split_version、评估日期范围。

方法列表
列出 baseline、启发式、模型方法。

主指标对比
展示 Local Order Fulfillment Rate、FDC Ful.、Reg. Loss、Loss Ratio、Transfer Cost。

分层指标
按 FDC、RDC、品类、订单大小、促销期/非促销期拆解。

trade-off 分析
说明 FDC Ful. 提升是否带来更高 lost sales 或 transfer cost。

异常分析
列出指标异常的 FDC、SKU、日期或策略输出。

结论与下一步
给出当前最优策略、剩余问题和后续实验建议。
```

阶段产出：

```text
evaluation/reports/<evaluation_id>_report.md
evaluation/runs/<evaluation_id>/comparison_table.csv
evaluation/runs/<evaluation_id>/metrics_summary.csv
```

#### 5.8 工作 6：评估校验

评估系统也需要校验，避免错误比较。

校验内容：

```text
同一次 evaluation 中 data_version 是否一致
split_version 是否一致
simulation_rule_version 是否一致
cost_config_version 是否一致
评估窗口是否一致
指标分母是否一致
是否存在缺失指标
是否存在未来信息泄漏标记
```

具体步骤：

```text
1. 读取 experiment_registry。
2. 检查可比实验的版本字段。
3. 检查指标字段完整性。
4. 检查指标取值范围，例如履约率应在 [0, 1]。
5. 输出 evaluation validation report。
```

#### 5.9 第五阶段推荐实施顺序

建议按下面顺序推进：

```text
1. 创建 evaluation/ 目录骨架
2. 定义评估指标公式
3. 定义 experiment_registry schema
4. 实现结果收集脚本
5. 实现选品指标汇总
6. 实现库存和仿真指标汇总
7. 实现 baseline 对比表
8. 实现 evaluation report 生成
9. 实现评估校验
10. 用已有 data、simulation、assortment、inventory runs 生成第一版综合报告
```

#### 5.10 第五阶段完成标准

第五阶段完成后，至少需要满足：

```text
能收集 data、simulation、assortment、inventory 的 manifest 和指标
能生成 experiment_registry
能统一输出 metrics_summary
能比较选品方法
能比较库存分配方法
能输出 baseline 对比报告
能识别指标 trade-off
能校验实验版本是否可比
能通过 evaluation_id 复现一次综合评估
```

### 阶段 6：工程化与版本管理

目标：让整个项目可运行、可复现、可扩展。第六阶段不是单独的业务算法阶段，而是把前五个阶段统一成稳定工程体系。

工程化要解决的问题：

```text
1. 新人能否按 README 跑通 MVP？
2. 每个阶段能否独立运行？
3. 全链路能否一键或分步运行？
4. 每次实验能否复现？
5. 数据、配置、模型、规则版本能否追踪？
6. 单元测试能否保护核心逻辑不被改坏？
```

#### 6.1 项目最终目录口径

推荐最终目录结构：

```text
FAIA/
├── README.md
├── pyproject.toml
├── Makefile
├── doc/
│   ├── material/
│   └── plan/
├── data/
├── simulation/
├── assortment/
├── inventory/
├── evaluation/
├── scripts/
│   ├── run_data_pipeline.py
│   ├── run_simulation_pipeline.py
│   ├── run_assortment_pipeline.py
│   ├── run_inventory_pipeline.py
│   └── run_full_pipeline.py
├── configs/
│   └── project.yaml
├── tests/
│   └── integration/
└── artifacts/
    └── README.md
```

说明：

```text
data/、simulation/、assortment/、inventory/、evaluation/
分别承载各阶段内部配置、代码、脚本、测试、运行结果和报告。

scripts/
只放跨阶段编排脚本，不放具体业务逻辑。

configs/project.yaml
只放全局项目配置，例如默认 data_version、默认运行环境、路径根目录。

tests/integration/
放跨阶段集成测试，例如 data -> assortment -> simulation 的最小链路。

artifacts/
预留模型、报告或导出产物的统一索引，不建议直接堆放原始数据。
```

#### 6.2 统一配置管理

每个阶段可以有自己的配置，但跨阶段运行需要一个统一配置入口。

配置层级：

```text
configs/project.yaml
全局默认配置。

data/configs/*.yaml
数据生成配置。

simulation/configs/*.yaml
仿真配置。

assortment/configs/*.yaml
选品配置。

inventory/configs/*.yaml
库存分配配置。

evaluation/configs/*.yaml
评估配置。
```

具体要求：

```text
1. 所有配置必须显式写 data_version 或引用方式。
2. 所有配置必须支持 seed。
3. 所有配置必须支持 output_dir。
4. 所有配置必须写入对应 manifest。
5. 不允许脚本里硬编码关键版本和路径。
```

#### 6.3 统一命令入口

为了降低使用成本，需要提供统一命令。

推荐命令：

```text
make data
生成 synthetic data、processed 表、features 和 splits。

make simulation
运行业务仿真 baseline。

make assortment
运行前置仓选品。

make inventory
运行库存分配 baseline。

make evaluation
汇总实验并生成报告。

make full
从数据生成到综合报告完整跑通 MVP。

make test
运行单元测试和集成测试。
```

对应脚本：

```text
scripts/run_data_pipeline.py
scripts/run_simulation_pipeline.py
scripts/run_assortment_pipeline.py
scripts/run_inventory_pipeline.py
scripts/run_full_pipeline.py
```

#### 6.4 版本体系

所有阶段都必须显式记录版本。版本不是为了好看，而是为了复现。

核心版本字段：

```text
data_version
schema_version
feature_version
split_version
candidate_pool_version
assortment_version
simulation_rule_version
policy_version
inventory_version
model_version
evaluation_id
experiment_id
```

版本依赖关系：

```text
data_version
  -> feature_version
  -> candidate_pool_version
  -> assortment_version
  -> inventory_version
  -> simulation result
  -> evaluation_id
```

每个阶段必须输出 manifest：

```text
data/synthetic/<data_version>/manifest.yaml
simulation/runs/<experiment_id>/simulation_manifest.yaml
assortment/runs/<experiment_id>/assortment_manifest.yaml
inventory/runs/<experiment_id>/inventory_manifest.yaml
evaluation/runs/<evaluation_id>/evaluation_manifest.yaml
```

#### 6.5 日志、报告和异常处理

工程化阶段需要统一日志和错误处理，避免排查困难。

日志要求：

```text
每个阶段记录开始时间、结束时间、耗时
记录输入版本和输出版本
记录配置文件路径
记录核心数据规模
记录校验错误和警告
记录输出目录
```

异常处理要求：

```text
schema 校验失败应中断
版本不一致应中断
关键输入缺失应中断
指标缺失应中断
非关键数据质量问题可输出 warning
```

报告要求：

```text
每个阶段输出阶段报告
evaluation 输出综合报告
README 中说明如何找到最新报告
```

#### 6.6 测试体系

测试需要覆盖阶段内逻辑和跨阶段链路。

测试层级：

```text
单元测试
测试单个函数或模块，例如 Reverse-Exclude、库存状态更新、指标计算。

阶段集成测试
测试一个阶段能否独立跑通，例如 data pipeline 或 simulation rollout。

跨阶段集成测试
测试 data -> assortment -> simulation -> inventory -> evaluation 的最小闭环。
```

最低测试要求：

```text
data：schema 校验和时间切分测试
simulation：库存守恒、需求守恒、lead time 测试
assortment：候选池、Top-K、Reverse-Exclude、Hybrid、Evaluator 测试
inventory：SS/TI、BaseStock、RDC 自留库存、调拨建议测试
evaluation：指标聚合和版本一致性测试
```

#### 6.7 第六阶段推荐实施顺序

建议按下面顺序推进：

```text
1. 统一顶层 README
2. 确定最终目录结构
3. 增加 pyproject.toml 或项目依赖说明
4. 增加 Makefile
5. 增加 configs/project.yaml
6. 为每个阶段补 README
7. 为每个阶段补 manifest 输出
8. 为每个阶段补基础单元测试
9. 实现 scripts/run_full_pipeline.py
10. 实现跨阶段 integration test
11. 跑通 MVP 全链路
12. 固化报告输出和复现实验说明
```

#### 6.8 第六阶段完成标准

第六阶段完成后，至少需要满足：

```text
项目有清晰 README
每个阶段有独立 README
每个阶段能独立运行
全链路能通过统一命令跑通
所有阶段输出 manifest
实验结果能通过版本字段追溯
核心模块有单元测试
最小闭环有集成测试
MVP 结果能被复现
```

## 4. 推荐实施顺序

建议按“先闭环、再增强”的方式推进，不要一开始就直接做复杂模型。

整体实施顺序：

```text
1. 创建顶层目录骨架：data、simulation、assortment、inventory、evaluation、doc。
2. 完成 data 阶段：生成 synthetic v001、processed 表、features 样例、splits、validation report。
3. 完成 simulation 阶段：跑通 NoTransferPolicy 和 HistoricalMeanPolicy 的多日仿真。
4. 完成 assortment 阶段：跑通 Top-K、Reverse-Exclude、Hybrid 和 local order fulfillment 评估。
5. 将 assortment_result 接入 simulation，验证选品结果能约束 FDC 调拨与履约。
6. 完成 inventory 阶段：跑通 HistoricalMeanForecast、SS/TI、BaseStockPolicy、GreedyAllocation。
7. 将 inventory transfer_recommendation 接入 simulation，形成库存策略回放闭环。
8. 完成 evaluation 阶段：汇总选品、库存、仿真指标，生成第一版综合报告。
9. 完成工程化基础：README、Makefile、manifest、统一配置、基础测试。
10. 加入 ML-Top-K 简版模型。
11. 加入端到端库存分配模型接口。
12. 逐步升级 ForecastingModule、TISSGenerationModule 和端到端训练。
```

核心原则：

```text
先跑通规则 baseline，再加入 ML 模型。
先用小数据闭环，再扩大数据规模。
先固定评估口径，再讨论模型提升。
先保证可复现，再做复杂优化。
```

## 5. 第一版 MVP 目标

第一版不追求复杂模型，先追求完整闭环。

MVP 范围：

```text
data：
能够生成 synthetic_small 数据，包含 SKU、仓网、订单、库存、促销、成本和切分。

simulation：
能够用 NoTransferPolicy / HistoricalMeanPolicy 回放多日履约。

assortment：
能够运行 Top-K、Reverse-Exclude、Hybrid，并输出 local_order_fulfillment_rate@K。

inventory：
能够运行 HistoricalMeanForecast + SS/TI + BaseStockPolicy，输出 transfer_recommendation。

evaluation：
能够比较至少两种选品方法和两种库存策略，输出综合报告。
```

MVP 不包含：

```text
复杂深度学习 ML-Top-K
完整端到端库存分配训练
线上服务部署
真实业务数据接入
复杂可视化看板
```

MVP 完成标准：

```text
数据能造
流程能跑
策略能评估
结果能复现
baseline 能比较
报告能解释
```

后续再逐步把 ML-Top-K、ForecastingModule、TISSGenerationModule 和端到端库存分配模型加进去。

## 6. 当前优先级判断

当前项目最重要的起点不是模型，而是两个基础能力：

```text
1. 构建可控、可复现的虚拟业务数据世界
2. 构建能够回放库存、调拨、履约和缺货的仿真闭环
```

在这两个基础能力之后，优先级依次是：

```text
3. 跑通 Top-K / Reverse-Exclude / Hybrid 选品闭环
4. 跑通 BaseStock 库存分配闭环
5. 建立 evaluation 统一比较口径
6. 做 ML-Top-K
7. 做端到端库存分配模型
```

只有数据、仿真、选品、库存和评估这五条链路都能稳定运行，复杂模型的提升才有可信验证基础。
