# Evaluation Report: eval_v001_baseline

## Experiment Goal

Compare the available v001 data, assortment, simulation and inventory artifacts under one fixed evaluation protocol.

## Protocol

- evaluation_version: evaluation_protocol_v001
- data_version: v001
- split_version: split_v001
- evaluation_split: test
- evaluation_window: 2026-06-03 to 2026-06-29
- assortment_version: assortment_hybrid_v001
- inventory_version: inventory_base_stock_v001
- simulation_rule_version: sim_rule_v001
- cost_config_version: cost_config_v001

## Registry

- available_runs: 4
- missing_runs: 0
- metric_rows_by_stage: {'data': 14, 'assortment': 605, 'simulation': 15, 'inventory': 4}

| stage | experiment_id | status | method | validation | notes |
| --- | --- | --- | --- | --- | --- |
| data | v001 | available | data_version | PASS |  |
| assortment | exp_assortment_v001_topk | available | hybrid | PASS |  |
| simulation | sim_smoke_v001_no_transfer | available | no_transfer | PASS |  |
| inventory | exp_inventory_v001_base_stock | available | base_stock | PASS |  |

## Data Metrics

| metric | value |
| --- | ---: |
| num_orders | 1234855 |
| num_order_items | 1856325 |
| num_skus | 3000 |
| num_warehouses | 14 |
| candidate_pool_rows | 32734 |
| inventory_daily_state_rows | 4235400 |
| validation_error_count | 0 |

## Main Comparison

| type | id | status | metrics | selected_sku_count | fdc_fulfillment_rate | loss_ratio | lost_sales_qty | transfer_cost | total_cost | notes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| assortment_method | topk | available | available | 3851 |  |  |  |  |  |  |
| assortment_method | reverse_exclude | available | available | 3851 |  |  |  |  |  |  |
| assortment_method | hybrid | available | available | 3851 |  |  |  |  |  |  |
| assortment_method | ml_topk | available | available | 3851 |  |  |  |  |  |  |
| inventory_method | no_transfer | available | available |  | 0.00335091 | 0.95095266 | 283789 | 0.0 | 1444241.06 | using simulation policy metrics as inventory baseline |
| inventory_method | historical_mean | planned | missing |  |  |  |  |  |  | inventory run or simulation metrics missing |
| inventory_method | base_stock | available | missing |  |  |  |  |  |  | inventory run or simulation metrics missing |
| inventory_method | greedy_allocation | planned | missing |  |  |  |  |  |  | inventory run or simulation metrics missing |
| inventory_method | e2e_inventory_model | planned | missing |  |  |  |  |  |  | inventory run or simulation metrics missing |
| combination | topk_base_stock | available | missing | 3851 |  |  |  |  |  |  |
| combination | reverse_exclude_base_stock | available | missing | 3851 |  |  |  |  |  |  |
| combination | hybrid_base_stock | available | missing | 3851 |  |  |  |  |  |  |
| combination | hybrid_greedy_allocation | missing_inventory_run | missing | 3851 |  |  |  |  |  | combination waits for a matching inventory run |
| combination | ml_topk_e2e_inventory | missing_inventory_run | missing | 3851 |  |  |  |  |  | combination waits for a matching inventory run |

## Trade-Off Analysis

- no_transfer: fdc_fulfillment_rate=0.00335091, loss_ratio=0.95095266, transfer_cost=0.0, total_cost=1444241.06.
- Only one operational baseline is currently available, so cost/service trade-offs are directional rather than comparative.

## Anomaly Analysis

- 9 comparison rows have partial or missing metrics.

## Conclusion

- Current operational baseline is no_transfer with fdc_fulfillment_rate=0.00335091 and total_cost=1444241.06.
- Next step is to add complete inventory and assortment metric runs for richer trade-off analysis.
