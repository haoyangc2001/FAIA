# Assortment Report: exp_assortment_v001_topk

- data_version: v001
- evaluation_split: test
- evaluation_window: 2026-06-03 to 2026-06-29
- regular_order_count: 158970

## Method Comparison

| method | local_order_fulfillment_rate | sku_frequency_recall_at_k | ndcg_at_k | candidate_hit_rate |
| --- | ---: | ---: | ---: | ---: |
| ml_topk | 0.79214946 | 0.83838411 | 0.98031186 | 0.92786096 |
| reverse_exclude | 0.75418003 | 0.81028481 | 0.98351548 | 0.92786096 |
| hybrid | 0.75384035 | 0.81020396 | 0.98349106 | 0.92786096 |
| topk | 0.75295968 | 0.80953023 | 0.98326199 | 0.92786096 |

## Outputs

```json
{
  "assortment_metrics": "assortment/runs/exp_assortment_v001_topk/assortment_metrics.json",
  "assortment_report": "assortment/reports/exp_assortment_v001_topk_assortment_report.md"
}
```
