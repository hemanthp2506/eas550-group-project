# Verification evidence: run2

- generated: 2026-11-15 02:15:54 UTC
- database: `localhost:5432/olist`
- checks: 52 total, 43 pass, 9 warn (known source anomalies), 0 fail

## Comparison with `run1`

13 of 13 fingerprints/measures identical (logical data unchanged).

| item | before | after | same |
|---|---|---|---|
| fingerprint: customers | {"rows": 9866, "md5": "fafd152b56d2620d0557a3091a87a9ef"} | {"rows": 9866, "md5": "fafd152b56d2620d0557a3091a87a9ef"} | yes |
| fingerprint: order_customers | {"rows": 9901, "md5": "783a4007a5c7c23e7578b26e8de4a95b"} | {"rows": 9901, "md5": "783a4007a5c7c23e7578b26e8de4a95b"} | yes |
| fingerprint: order_items | {"rows": 11242, "md5": "1b4c4a8621707018c179aad0fc967ae1"} | {"rows": 11242, "md5": "1b4c4a8621707018c179aad0fc967ae1"} | yes |
| fingerprint: order_lines | {"rows": 10231, "md5": "29b572b2766b23249152eb0511e35717"} | {"rows": 10231, "md5": "29b572b2766b23249152eb0511e35717"} | yes |
| fingerprint: order_sellers | {"rows": 9997, "md5": "56a97b8d685aee98852835bba7ef0d92"} | {"rows": 9997, "md5": "56a97b8d685aee98852835bba7ef0d92"} | yes |
| fingerprint: orders | {"rows": 9901, "md5": "9d3a5899f50a9f7158a96420d526bf23"} | {"rows": 9901, "md5": "9d3a5899f50a9f7158a96420d526bf23"} | yes |
| fingerprint: product_categories | {"rows": 71, "md5": "ee1682a4a14109f47181eb5279a88b5e"} | {"rows": 71, "md5": "ee1682a4a14109f47181eb5279a88b5e"} | yes |
| fingerprint: products | {"rows": 6619, "md5": "32ac69800c02115046e94e441cf3ffac"} | {"rows": 6619, "md5": "32ac69800c02115046e94e441cf3ffac"} | yes |
| fingerprint: sellers | {"rows": 1617, "md5": "d34fed9740265a598338da7567d1b9b9"} | {"rows": 1617, "md5": "d34fed9740265a598338da7567d1b9b9"} | yes |
| measure: order_items | "11242" | "11242" | yes |
| measure: orders | "9901" | "9901" | yes |
| measure: total_item_freight | "224877.74" | "224877.74" | yes |
| measure: total_item_price | "1329141.86" | "1329141.86" | yes |

## Ingestion runs

<sub>`runs` in sql/verify.sql</sub>

| run_id | status | started_at | finished_at | scope | error_message |
|---|---|---|---|---|---|
| 1 | succeeded | 2026-11-15 02:15:45+0000 | 2026-11-15 02:15:49+0000 | full subset | NULL |
| 2 | succeeded | 2026-11-15 02:15:50+0000 | 2026-11-15 02:15:53+0000 | full subset | NULL |

## Source files used by the latest successful run (provenance and row accounting)

<sub>`source_files` in sql/verify.sql</sub>

| file_name | sha256 | rows_read | rows_in_subset | rows_rejected | rows_corrected |
|---|---|---|---|---|---|
| olist_customers_dataset.csv | 983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2 | 99441 | 9901 | 0 | 0 |
| olist_order_items_dataset.csv | 0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279 | 112650 | 11242 | 0 | 0 |
| olist_orders_dataset.csv | 8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf | 99441 | 9901 | 0 | 0 |
| olist_products_dataset.csv | 3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc | 32951 | 6619 | 0 | 0 |
| olist_sellers_dataset.csv | 1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e | 3095 | 1617 | 0 | 3 |
| product_category_name_translation.csv | a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278 | 71 | 69 | 0 | 0 |

## Upsert outcome per table for every successful run

<sub>`table_loads` in sql/verify.sql</sub>

| run_id | table_name | rows_loaded | rows_inserted | rows_updated | rows_unchanged |
|---|---|---|---|---|---|
| 1 | customers | 9866 | 9866 | 0 | 0 |
| 1 | order_customers | 9901 | 9901 | 0 | 0 |
| 1 | sellers | 1617 | 1617 | 0 | 0 |
| 1 | product_categories | 71 | 71 | 0 | 0 |
| 1 | products | 6619 | 6619 | 0 | 0 |
| 1 | orders | 9901 | 9901 | 0 | 0 |
| 1 | order_sellers | 9997 | 9997 | 0 | 0 |
| 1 | order_lines | 10231 | 10231 | 0 | 0 |
| 1 | order_items | 11242 | 11242 | 0 | 0 |
| 2 | customers | 9866 | 0 | 0 | 9866 |
| 2 | order_customers | 9901 | 0 | 0 | 9901 |
| 2 | sellers | 1617 | 0 | 0 | 1617 |
| 2 | product_categories | 71 | 0 | 0 | 71 |
| 2 | products | 6619 | 0 | 0 | 6619 |
| 2 | orders | 9901 | 0 | 0 | 9901 |
| 2 | order_sellers | 9997 | 0 | 0 | 9997 |
| 2 | order_lines | 10231 | 0 | 0 | 10231 |
| 2 | order_items | 11242 | 0 | 0 | 11242 |

## Rejected and corrected source rows in the latest successful run

<sub>`data_issues` in sql/verify.sql</sub>

| source_file | outcome | rule_code | row_count | source_rows |
|---|---|---|---|---|
| olist_sellers_dataset.csv | corrected | city_ascii_folded | 1 | 2341 |
| olist_sellers_dataset.csv | corrected | city_not_a_place_set_null | 1 | 2259 |
| olist_sellers_dataset.csv | corrected | city_whitespace_normalized | 1 | 1706 |

## Row counts reconcile with the rows the latest successful run validated

<sub>`check_row_counts` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| rows in olist.customers | error | 9866 | 9866 | PASS |
| rows in olist.order_customers | error | 9901 | 9901 | PASS |
| rows in olist.sellers | error | 1617 | 1617 | PASS |
| rows in olist.product_categories | error | 71 | 71 | PASS |
| rows in olist.products | error | 6619 | 6619 | PASS |
| rows in olist.orders | error | 9901 | 9901 | PASS |
| rows in olist.order_sellers | error | 9997 | 9997 | PASS |
| rows in olist.order_lines | error | 10231 | 10231 | PASS |
| rows in olist.order_items | error | 11242 | 11242 | PASS |

## Measures reconcile with totals computed from the validated source rows

<sub>`check_measures` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| source vs database: order_items | error | 11242 | 11242 | PASS |
| source vs database: orders | error | 9901 | 9901 | PASS |
| source vs database: total_item_freight | error | 224877.74 | 224877.74 | PASS |
| source vs database: total_item_price | error | 1329141.86 | 1329141.86 | PASS |

## Duplicate-key checks (primary keys and the 1:1 customer record)

<sub>`check_duplicate_keys` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| duplicate keys: product_categories | error | 0 | 0 | PASS |
| duplicate keys: sellers | error | 0 | 0 | PASS |
| duplicate keys: products | error | 0 | 0 | PASS |
| duplicate keys: order_sellers | error | 0 | 0 | PASS |
| duplicate keys: order_customers | error | 0 | 0 | PASS |
| duplicate keys: order_lines | error | 0 | 0 | PASS |
| orders sharing one customer_id (must be 1:1) | error | 0 | 0 | PASS |
| duplicate keys: order_items | error | 0 | 0 | PASS |
| duplicate keys: orders | error | 0 | 0 | PASS |
| duplicate keys: customers | error | 0 | 0 | PASS |

## Referential checks, minimum cardinalities and subset closure

<sub>`check_referential` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| orphans: products -> product_categories | error | 0 | 0 | PASS |
| categories outside the subset closure (no products) | error | 0 | 0 | PASS |
| orphans: order_sellers -> sellers | error | 0 | 0 | PASS |
| sellers outside the subset closure (no order_sellers) | error | 0 | 0 | PASS |
| orphans: order_lines -> products | error | 0 | 0 | PASS |
| products outside the subset closure (no order_lines) | error | 0 | 0 | PASS |
| orphans: order_customers -> customers | error | 0 | 0 | PASS |
| customers with no order record (min 1) | error | 0 | 0 | PASS |
| order_customers not used by an order (1:1) | error | 0 | 0 | PASS |
| orphans: orders -> order_customers | error | 0 | 0 | PASS |
| orphans: order_sellers -> orders | error | 0 | 0 | PASS |
| order_lines with no order_items (min 1) | error | 0 | 0 | PASS |
| order_sellers with no order_lines (min 1) | error | 0 | 0 | PASS |
| orphans: order_items -> order_lines | error | 0 | 0 | PASS |
| orphans: order_lines -> order_sellers | error | 0 | 0 | PASS |

## Every loaded order satisfies the documented sha256 subset rule

<sub>`check_subset_rule` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| orders outside the subset rule | error | 0 | 0 | PASS |

## Domain-quality checks (error = business rule; warn = known source anomaly, kept and reported)

<sub>`check_domain_quality` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| products with weight 0 g | warn | 1 | 0 | WARN |
| delivered orders missing the customer delivery time | warn | 1 | 0 | WARN |
| delivered to customer before carrier pickup | warn | 2 | 0 | WARN |
| handed to carrier before approval | warn | 125 | 0 | WARN |
| handed to carrier before purchase | warn | 19 | 0 | WARN |
| cities containing / , \ or ( (state or country appended) | warn | 7 | 0 | WARN |
| orders past approval stage missing the approval time | warn | 1 | 0 | WARN |
| non-delivered orders that have a customer delivery time | warn | 1 | 0 | WARN |
| orders whose order_item_id is not exactly 1..n | error | 0 | 0 | PASS |
| zip prefixes reported with more than one state | warn | 12 | 0 | WARN |
| seller shipping deadline before purchase | error | 0 | 0 | PASS |
| seller shipping deadline more than 365 days after purchase | warn | 0 | 0 | PASS |
| delivered or shipped orders with no items | warn | 0 | 0 | PASS |

## Documented valid exceptions (allowed by the schema on purpose)

<sub>`valid_exceptions` in sql/verify.sql</sub>

| exception_kind | detail | row_count |
|---|---|---|
| categories without an English translation | pc_gamer, portateis_cozinha_e_preparadores_de_alimentos | 2 |
| cities set to NULL (source value was not a place) | customer_city / seller_city NULL | 1 |
| order lines with zero freight (free shipping) | item_freight_value = 0 | 33 |
| orders never approved (approved_at NULL, by status) | canceled | 12 |
| orders without items (by status) | canceled | 14 |
| orders without items (by status) | unavailable | 44 |
| products without a category | product_category_name NULL | 90 |
| products without weight/dimensions | measurements NULL | 1 |

## Content fingerprints (row count + md5 of all rows in key order) for change detection

<sub>`fingerprints` in sql/verify.sql</sub>

| table_name | row_count | content_md5 |
|---|---|---|
| product_categories | 71 | ee1682a4a14109f47181eb5279a88b5e |
| sellers | 1617 | d34fed9740265a598338da7567d1b9b9 |
| products | 6619 | 32ac69800c02115046e94e441cf3ffac |
| order_customers | 9901 | 783a4007a5c7c23e7578b26e8de4a95b |
| customers | 9866 | fafd152b56d2620d0557a3091a87a9ef |
| order_items | 11242 | 1b4c4a8621707018c179aad0fc967ae1 |
| order_lines | 10231 | 29b572b2766b23249152eb0511e35717 |
| order_sellers | 9997 | 56a97b8d685aee98852835bba7ef0d92 |
| orders | 9901 | 9d3a5899f50a9f7158a96420d526bf23 |

## Database storage used by the two schemas (target: well under 300 MB)

<sub>`storage` in sql/verify.sql</sub>

| schema_name | total_size |
|---|---|
| ingest | 176 kB |
| olist | 17 MB |

