# FAIA v001 Data Validation Report

- generated_at: 2026-06-28T20:59:05
- overall_status: PASS
- total_checks: 58
- failed_checks: 0
- warnings: 0

## Artifact Counts

```json
{
  "synthetic": {
    "sku_master": 3000,
    "warehouse_master": 14,
    "calendar": 180,
    "sku_fdc_eligibility": 36000,
    "promotion_plan": 1948,
    "cost_config": 4,
    "orders": 1234855,
    "order_items": 1856325,
    "inventory_snapshot": 4235400,
    "transfer_plan": 51692,
    "stockout_events": 2293194
  },
  "processed": {
    "fdc_sku_daily_demand": 624438,
    "order_type_table": 274420,
    "order_type_items": 695935,
    "inventory_daily_state": 4235400,
    "candidate_pool_base": 32734
  },
  "features": {
    "ml_topk_fdc_sku_features": 98202,
    "inventory_features": 52590
  },
  "splits": {
    "train_dates": 126,
    "val_dates": 27,
    "test_dates": 27
  }
}
```

## Checks

| Area | Check | Status | Details |
|---|---|---|---|
| files | required_artifacts_exist | PASS | all required files exist |
| schema | calendar_header_matches_schema | PASS | expected=['date', 'day_of_week', 'is_weekend', 'is_holiday', 'campaign_window', 'campaign_phase', 'demand_multiplier'], actual=['date', 'day_of_week', 'is_weekend', 'is_holiday', 'campaign_window', 'campaign_phase', 'demand_multiplier'] |
| schema | cost_config_header_matches_schema | PASS | expected=['cost_item', 'unit', 'value', 'currency', 'description'], actual=['cost_item', 'unit', 'value', 'currency', 'description'] |
| schema | inventory_snapshot_header_matches_schema | PASS | expected=['date', 'node_id', 'node_type', 'sku_id', 'on_hand_qty', 'reserved_qty', 'in_transit_qty'], actual=['date', 'node_id', 'node_type', 'sku_id', 'on_hand_qty', 'reserved_qty', 'in_transit_qty'] |
| schema | order_items_header_matches_schema | PASS | expected=['order_id', 'sku_id', 'qty', 'unit_price'], actual=['order_id', 'sku_id', 'qty', 'unit_price'] |
| schema | orders_header_matches_schema | PASS | expected=['order_id', 'order_date', 'rdc_id', 'fdc_id', 'user_region_id', 'order_item_count', 'is_multi_item'], actual=['order_id', 'order_date', 'rdc_id', 'fdc_id', 'user_region_id', 'order_item_count', 'is_multi_item'] |
| schema | promotion_plan_header_matches_schema | PASS | expected=['date', 'sku_id', 'promotion_type', 'discount_rate', 'coupon_value', 'planned_exposure_level', 'campaign_phase', 'planned_demand_lift'], actual=['date', 'sku_id', 'promotion_type', 'discount_rate', 'coupon_value', 'planned_exposure_level', 'campaign_phase', 'planned_demand_lift'] |
| schema | sku_fdc_eligibility_header_matches_schema | PASS | expected=['sku_id', 'fdc_id', 'rdc_id', 'eligible_flag', 'ineligible_reason'], actual=['sku_id', 'fdc_id', 'rdc_id', 'eligible_flag', 'ineligible_reason'] |
| schema | sku_master_header_matches_schema | PASS | expected=['sku_id', 'category_id', 'brand_id', 'price', 'temperature_zone', 'volume', 'weight', 'shelf_life_days', 'is_regular_product', 'base_popularity'], actual=['sku_id', 'category_id', 'brand_id', 'price', 'temperature_zone', 'volume', 'weight', 'shelf_life_days', 'is_regular_product', 'base_popularity'] |
| schema | stockout_events_header_matches_schema | PASS | expected=['date', 'node_id', 'node_type', 'sku_id', 'stockout_flag', 'stockout_qty', 'stockout_reason'], actual=['date', 'node_id', 'node_type', 'sku_id', 'stockout_flag', 'stockout_qty', 'stockout_reason'] |
| schema | transfer_plan_header_matches_schema | PASS | expected=['transfer_id', 'ship_date', 'arrival_date', 'rdc_id', 'fdc_id', 'sku_id', 'transfer_qty', 'lead_time_days'], actual=['transfer_id', 'ship_date', 'arrival_date', 'rdc_id', 'fdc_id', 'sku_id', 'transfer_qty', 'lead_time_days'] |
| schema | warehouse_master_header_matches_schema | PASS | expected=['node_id', 'node_type', 'rdc_id', 'city_id', 'region_id', 'capacity_units', 'support_ambient', 'support_chilled', 'support_frozen'], actual=['node_id', 'node_type', 'rdc_id', 'city_id', 'region_id', 'capacity_units', 'support_ambient', 'support_chilled', 'support_frozen'] |
| schema | fdc_sku_daily_demand.csv_header_matches_contract | PASS | expected=['date', 'fdc_id', 'sku_id', 'order_count', 'demand_qty'], actual=['date', 'fdc_id', 'sku_id', 'order_count', 'demand_qty'] |
| schema | order_type_table.csv_header_matches_contract | PASS | expected=['order_type_id', 'fdc_id', 'order_type_key', 'sku_count', 'order_count', 'total_qty', 'first_order_date', 'last_order_date'], actual=['order_type_id', 'fdc_id', 'order_type_key', 'sku_count', 'order_count', 'total_qty', 'first_order_date', 'last_order_date'] |
| schema | order_type_items.csv_header_matches_contract | PASS | expected=['order_type_id', 'fdc_id', 'sku_id', 'item_rank'], actual=['order_type_id', 'fdc_id', 'sku_id', 'item_rank'] |
| schema | inventory_daily_state.csv_header_matches_contract | PASS | expected=['date', 'node_id', 'node_type', 'sku_id', 'on_hand_qty', 'reserved_qty', 'in_transit_qty', 'available_qty', 'inventory_position_qty'], actual=['date', 'node_id', 'node_type', 'sku_id', 'on_hand_qty', 'reserved_qty', 'in_transit_qty', 'available_qty', 'inventory_position_qty'] |
| schema | candidate_pool_base.csv_header_matches_contract | PASS | expected=['fdc_id', 'sku_id', 'rdc_id', 'eligible_flag', 'category_id', 'brand_id', 'temperature_zone', 'price', 'volume', 'weight', 'shelf_life_days', 'is_regular_product', 'base_popularity', 'total_demand_qty', 'demand_order_count', 'active_demand_days'], actual=['fdc_id', 'sku_id', 'rdc_id', 'eligible_flag', 'category_id', 'brand_id', 'temperature_zone', 'price', 'volume', 'weight', 'shelf_life_days', 'is_regular_product', 'base_popularity', 'total_demand_qty', 'demand_order_count', 'active_demand_days'] |
| schema | fdc_sku_features.csv_header_matches_contract | PASS | expected=['anchor_date', 'fdc_id', 'sku_id', 'category_id', 'brand_id', 'temperature_zone', 'base_popularity', 'price', 'is_regular_product', 'hist_7d_qty', 'hist_7d_orders', 'hist_14d_qty', 'hist_14d_orders', 'hist_30d_qty', 'hist_30d_orders', 'hist_30d_active_days', 'hist_60d_qty', 'hist_60d_orders', 'future_promo_days_14d', 'future_campaign_days_14d'], actual=['anchor_date', 'fdc_id', 'sku_id', 'category_id', 'brand_id', 'temperature_zone', 'base_popularity', 'price', 'is_regular_product', 'hist_7d_qty', 'hist_7d_orders', 'hist_14d_qty', 'hist_14d_orders', 'hist_30d_qty', 'hist_30d_orders', 'hist_30d_active_days', 'hist_60d_qty', 'hist_60d_orders', 'future_promo_days_14d', 'future_campaign_days_14d'] |
| schema | inventory_features.csv_header_matches_contract | PASS | expected=['anchor_date', 'fdc_id', 'sku_id', 'on_hand_qty', 'reserved_qty', 'in_transit_qty', 'available_qty', 'inventory_position_qty', 'hist_7d_qty', 'hist_7d_orders', 'hist_14d_qty', 'hist_14d_orders', 'hist_30d_qty', 'hist_30d_orders', 'hist_30d_active_days', 'future_promo_days_14d', 'lead_time_min_days', 'lead_time_max_days'], actual=['anchor_date', 'fdc_id', 'sku_id', 'on_hand_qty', 'reserved_qty', 'in_transit_qty', 'available_qty', 'inventory_position_qty', 'hist_7d_qty', 'hist_7d_orders', 'hist_14d_qty', 'hist_14d_orders', 'hist_30d_qty', 'hist_30d_orders', 'hist_30d_active_days', 'future_promo_days_14d', 'lead_time_min_days', 'lead_time_max_days'] |
| primary_key | sku_master_sku_id_unique | PASS | duplicate_skus=0 |
| business_rule | sku_master_numeric_fields_valid | PASS | numeric_errors=0 |
| primary_key | warehouse_master_node_id_unique | PASS | duplicate_nodes=0 |
| foreign_key | fdc_rdc_relationship_valid | PASS | relationship_or_capacity_errors=0 |
| primary_key | calendar_date_unique | PASS | duplicate_dates=0 |
| business_rule | calendar_dates_sorted | PASS | calendar is chronological |
| business_rule | calendar_fields_valid | PASS | calendar_errors=0 |
| primary_key | sku_fdc_eligibility_pair_unique | PASS | duplicate_pairs=0 |
| foreign_key | sku_fdc_eligibility_references_valid | PASS | errors=0 |
| primary_key | promotion_plan_date_sku_unique | PASS | duplicate_promotions=0 |
| foreign_key | promotion_plan_references_valid | PASS | errors=0 |
| business_rule | cost_config_items_complete | PASS | cost_items=['holding_cost', 'lost_sales_cost', 'rdc_fallback_cost', 'transfer_cost'] |
| business_rule | cost_config_values_non_negative | PASS | errors=0 |
| primary_key | orders_order_id_unique | PASS | duplicate_orders=0 |
| foreign_key | orders_references_valid | PASS | errors=0 |
| foreign_key | order_items_references_orders_and_skus | PASS | unknown_order_items=0, item_errors=0 |
| business_rule | orders_item_count_matches_order_items | PASS | unmatched_orders=0 |
| business_rule | inventory_snapshot_references_and_quantities_valid | PASS | errors=0 |
| primary_key | transfer_plan_transfer_id_unique | PASS | duplicate_transfers=0 |
| foreign_key | transfer_plan_references_valid | PASS | errors=0 |
| business_rule | stockout_events_references_and_quantities_valid | PASS | errors=0 |
| primary_key | fdc_sku_daily_demand_key_unique | PASS | duplicate_keys=0 |
| foreign_key | fdc_sku_daily_demand_references_valid | PASS | errors=0 |
| primary_key | order_type_table_id_unique | PASS | duplicate_order_type_ids=0 |
| business_rule | order_type_table_values_valid | PASS | errors=0 |
| foreign_key | order_type_items_references_valid | PASS | errors=0 |
| business_rule | inventory_daily_state_derived_fields_valid | PASS | errors=0 |
| primary_key | candidate_pool_base_pair_unique | PASS | duplicate_candidates=0 |
| foreign_key | candidate_pool_base_subset_of_eligible_pairs | PASS | errors=0 |
| split | chronological_split_sorted | PASS | split dates are chronological |
| split | chronological_split_covers_calendar | PASS | cover_ok=True, disjoint_ok=True |
| leakage | feature_anchor_dates_match_split_boundaries | PASS | expected=['2026-05-06', '2026-06-02', '2026-06-29'], ml=['2026-05-06', '2026-06-02', '2026-06-29'], inventory=['2026-05-06', '2026-06-02', '2026-06-29'] |
| features | ml_topk_features_references_and_values_valid | PASS | errors=0 |
| features | inventory_features_references_and_values_valid | PASS | errors=0 |
| leakage | future_features_are_plan_fields | PASS | future-looking feature fields are promotion/calendar plan fields only |
| manifest | synthetic_manifest_counts_match_actual | PASS | all synthetic row counts match |
| manifest | processed_manifest_counts_match_actual | PASS | all processed row counts match |
| manifest | feature_manifest_counts_match_actual | PASS | all feature row counts match |
| manifest | split_manifest_counts_match_actual | PASS | all split counts match |
