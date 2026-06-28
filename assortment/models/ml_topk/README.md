# ML-Top-K

第一版 ML-Top-K 固定输入输出接口，先使用无外部依赖的线性 baseline。

输入来自 `data/features/ml_topk/<data_version>/fdc_sku_features.csv`，核心字段包括：

```text
anchor_date
fdc_id
sku_id
hist_7d_orders
hist_14d_orders
hist_30d_orders
hist_60d_orders
future_promo_days_14d
future_campaign_days_14d
base_popularity
```

输出写入：

```text
assortment/runs/<experiment_id>/ml_topk_result.csv
assortment/runs/<experiment_id>/ml_topk_model_manifest.yaml
```

当前 `ml_topk_linear_v001` 的分数是历史订单频次、未来计划促销/活动和静态热度的确定性加权和。后续可以替换为 LightGBM、线性回归、MLP 或时序模型，但应保持 `ml_topk_result.csv` 的字段契约不变。
