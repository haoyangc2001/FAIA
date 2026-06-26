# FAIA Simulation Module

## 目标

`simulation/` 是 FAIA 项目的第二阶段业务仿真模块，用于在统一业务规则下回放 RDC-FDC 两级仓网的库存、调拨、履约、缺货和成本变化。

第一阶段已经生成并校验了 `data/versions/v001`。第二阶段第一版应优先读取 `v001` 数据版本，先跑通 baseline 仿真闭环，再接入更复杂的选品和库存分配策略。

## 定位与边界

仿真器必须保持策略无关。它不负责训练模型，也不负责学习最优策略，而是接收外部策略输出，并按照统一业务规则回放结果。

仿真器负责：

```text
读取指定 data_version 的数据
初始化 RDC/FDC/SKU 库存状态
处理 lead time 和在途调拨 pipeline
接收策略给出的调拨建议或目标库存
将策略建议裁剪为业务可执行调拨
按统一履约优先级消耗库存
记录 FDC 本地履约、RDC 代履约和 lost sales
计算调拨成本、代履约成本、缺货损失和持有成本
输出可复盘的仿真结果和指标
```

仿真器不负责：

```text
训练机器学习模型
决定最终选哪些 SKU
修改原始订单需求
使用仿真日期之后的真实需求生成策略
绕过容量、库存、SKU-FDC 合法性等硬约束
```

## 第一版输入

第一版仿真器主要读取：

```text
data/synthetic/v001/sku_master.csv
data/synthetic/v001/warehouse_master.csv
data/synthetic/v001/cost_config.csv
data/processed/v001/fdc_sku_daily_demand.csv
data/processed/v001/inventory_daily_state.csv
data/processed/v001/candidate_pool_base.csv
data/splits/v001/train_dates.txt
data/splits/v001/val_dates.txt
data/splits/v001/test_dates.txt
```

后续接入选品系统后，`candidate_pool_base` 会被具体的 `assortment_result` 替代或进一步过滤。

## 当前初始化入口

第一版初始化配置：

```text
simulation/configs/simulation_small.yaml
simulation/rules/simulation_rule_v001.yaml
```

可以用下面命令检查仿真初始化：

```bash
PYTHONPATH=. python3 simulation/scripts/check_initialization.py \
  --config simulation/configs/simulation_small.yaml
```

该检查会完成：

```text
读取 data_version v001
构造 SimulationContext
从 initial_inventory_date 加载 RDC/FDC/SKU 库存
从 transfer_plan 加载尚未到货的 pipeline_inventory
校验 simulation_rule_version 与规则文件一致
输出初始化摘要
```

## 当前策略与调拨裁剪入口

第一版已定义三类 baseline 策略配置：

```text
simulation/policies/no_transfer.yaml
simulation/policies/historical_mean.yaml
simulation/policies/base_stock.yaml
```

策略模块只负责生成 `TransferDecision`，不直接修改库存。硬约束裁剪由 `simulation/src/allocation.py` 统一执行。

可以用下面命令检查策略加载与调拨裁剪：

```bash
PYTHONPATH=. python3 simulation/scripts/check_policy_allocation.py \
  --config simulation/configs/simulation_small.yaml
```

该检查会验证：

```text
NoTransferPolicy 不生成调拨建议
recommended_transfer_qty 超过 RDC 可用库存时被裁剪
非法 SKU-FDC 组合被取消
actual_transfer_qty 入 pipeline 前会消耗 RDC 库存
arrival_date 由 ship_date + lead_time_days 得到
```

## 当前履约仿真入口

第一版履约逻辑位于：

```text
simulation/src/fulfillment.py
```

可以用下面命令检查单日履约回放：

```bash
PYTHONPATH=. python3 simulation/scripts/check_fulfillment.py \
  --config simulation/configs/simulation_small.yaml \
  --simulation-date 2026-06-03
```

该检查会完成：

```text
处理 simulation_date 当日到货
读取当日 fdc_sku_daily_demand
FDC 本地优先履约
FDC 未满足部分转为 RDC fallback
RDC 不足部分记为 lost sales
校验 demand = fdc_fulfilled + rdc_fallback + lost_sales
校验库存不为负
```

## 当前成本与指标入口

第一版成本与指标逻辑位于：

```text
simulation/src/cost.py
simulation/src/metrics.py
```

可以用下面命令检查单日成本和指标计算：

```bash
PYTHONPATH=. python3 simulation/scripts/check_cost_metrics.py \
  --config simulation/configs/simulation_small.yaml \
  --simulation-date 2026-06-03
```

该检查会完成：

```text
读取 cost_config
根据 transfer_result 计算 transfer_cost
根据 fulfillment_result 计算 rdc_fallback_cost 和 lost_sales_cost
根据 daily_state 计算 holding_cost
汇总 metrics_summary
校验需求守恒、成本守恒和指标范围
```

## 当前仿真运行入口

完整仿真输出由下面脚本生成：

```bash
PYTHONPATH=. python3 simulation/scripts/run_simulation.py \
  --config simulation/configs/simulation_small.yaml
```

当前第一版 smoke run：

```text
experiment_id: sim_smoke_v001_no_transfer
data_version: v001
assortment_version: assortment_v001
policy_version: no_transfer_v001
simulation_rule_version: sim_rule_v001
date_range: 2026-06-03 to 2026-06-29
```

输出目录：

```text
simulation/runs/sim_smoke_v001_no_transfer/
```

输出文件：

```text
daily_state.csv
transfer_result.csv
fulfillment_result.csv
cost_result.csv
metrics_summary.json
daily_log.json
simulation_config.yaml
simulation_manifest.yaml
```

复盘报告：

```text
simulation/reports/sim_smoke_v001_no_transfer_simulation_report.md
```

## 当前仿真校验入口

完整仿真结束后，可以用下面命令校验 run 级输出：

```bash
PYTHONPATH=. python3 simulation/scripts/validate_simulation_run.py \
  --manifest simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml
```

该校验会完成：

```text
检查 manifest、config、policy、rules、metrics 和 CSV 输出版本一致
检查 data_version、assortment_version、policy_version、simulation_rule_version、experiment_id 版本血缘
检查输出文件存在且 row_counts 与 manifest 一致
检查 daily_state 非负库存、available_qty 和 inventory_position_qty
检查 fulfillment_result 需求守恒
检查 transfer_result 的 lead time、调拨裁剪、RDC-FDC 关系和 SKU-FDC 合法性
检查跨日库存守恒和 FDC 在途库存
```

校验输出：

```text
simulation/runs/<experiment_id>/validation_summary.json
simulation/reports/<experiment_id>_validation_report.md
```

核心单元测试位于：

```text
simulation/tests/
```

运行方式：

```bash
PYTHONPATH=. python3 -m unittest discover -s simulation/tests
```

## 第一版输出

每次仿真运行输出到：

```text
simulation/runs/<experiment_id>/
```

核心输出：

```text
daily_state.csv
transfer_result.csv
fulfillment_result.csv
cost_result.csv
metrics_summary.json
simulation_manifest.yaml
validation_summary.json
```

所有输出都必须携带：

```text
experiment_id
data_version
policy_version
simulation_rule_version
simulation_date
```

`simulation_manifest.yaml` 额外记录：

```text
experiment_id
data_version
assortment_version
policy_version
simulation_rule_version
version_lineage
validation
```

## 仿真主流程

```text
1. 读取 simulation config 和 data_version
2. 初始化 SimulationContext
3. 从起始日期库存快照初始化 SimulationState
4. 每日开始时处理当日到货
5. 调用策略接口生成 recommended_transfer_qty
6. 根据库存、容量、合法性和 lead time 裁剪为 actual_transfer_qty
7. 将实际调拨写入 pipeline
8. 读取当日 FDC-SKU 需求
9. FDC 本地优先履约
10. FDC 不足部分转为 RDC fallback
11. RDC 不足部分记为 lost sales
12. 计算成本和指标
13. 输出 daily state 与当日结果
14. 进入下一天
```

## 目录说明

```text
simulation/configs/
存放仿真运行配置，例如 data_version、日期范围、策略版本、规则版本和输出 experiment_id。

simulation/schemas/
存放仿真输出契约，例如 daily_state、transfer_result、fulfillment_result、cost_result 和 metrics_summary。

simulation/rules/
存放仿真业务规则配置，例如履约优先级、调拨裁剪规则、容量约束和整数化规则。

simulation/policies/
存放 baseline 策略配置，例如 no_transfer、historical_mean、base_stock。

simulation/src/
存放仿真器核心实现。

simulation/scripts/
存放仿真运行入口和回放入口。

simulation/tests/
存放 toy dataset 单元测试和集成测试。

simulation/runs/
存放每次仿真运行结果。

simulation/reports/
存放仿真报告和复盘文档。
```

## 核心状态口径

仿真器内部最核心的状态是：

```text
rdc_on_hand_inventory
fdc_on_hand_inventory
pipeline_inventory
last_transfer_qty
last_fulfillment_result
lost_sales_state
```

状态更新必须满足：

```text
FDC 下一期库存 = FDC 当前库存 + 到货调拨 - FDC 本地履约消耗
RDC 下一期库存 = RDC 当前库存 - 发给 FDC 的调拨 - RDC 代履约消耗
```

第一版暂不模拟外部采购入库；后续库存分配阶段可以扩展外部补货逻辑。
