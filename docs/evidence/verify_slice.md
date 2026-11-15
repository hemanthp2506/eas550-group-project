# Verification evidence: slice

- generated: 2026-11-15 02:15:43 UTC
- database: `localhost:5432/olist_slice`
- checks: 52 total, 49 pass, 3 warn (known source anomalies), 0 fail

## Ingestion runs

<sub>`runs` in sql/verify.sql</sub>

| run_id | status | started_at | finished_at | scope | error_message |
|---|---|---|---|---|---|
| 1 | succeeded | 2026-11-15 02:15:43+0000 | 2026-11-15 02:15:43+0000 | 200 | NULL |

## Source files used by the latest successful run (provenance and row accounting)

<sub>`source_files` in sql/verify.sql</sub>

| file_name | sha256 | rows_read | rows_in_subset | rows_rejected | rows_corrected |
|---|---|---|---|---|---|
| olist_customers_dataset.csv | 983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2 | 99441 | 200 | 0 | 0 |
| olist_order_items_dataset.csv | 0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279 | 112650 | 225 | 0 | 0 |
| olist_orders_dataset.csv | 8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf | 99441 | 200 | 0 | 0 |
| olist_products_dataset.csv | 3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc | 32951 | 200 | 0 | 0 |
| olist_sellers_dataset.csv | 1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e | 3095 | 157 | 0 | 1 |
| product_category_name_translation.csv | a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278 | 71 | 36 | 0 | 0 |

## Upsert outcome per table for every successful run

<sub>`table_loads` in sql/verify.sql</sub>

| run_id | table_name | rows_loaded | rows_inserted | rows_updated | rows_unchanged |
|---|---|---|---|---|---|
| 1 | customers | 200 | 200 | 0 | 0 |
| 1 | order_customers | 200 | 200 | 0 | 0 |
| 1 | sellers | 157 | 157 | 0 | 0 |
| 1 | product_categories | 36 | 36 | 0 | 0 |
| 1 | products | 200 | 200 | 0 | 0 |
| 1 | orders | 200 | 200 | 0 | 0 |
| 1 | order_sellers | 198 | 198 | 0 | 0 |
| 1 | order_lines | 204 | 204 | 0 | 0 |
| 1 | order_items | 225 | 225 | 0 | 0 |

## Rejected and corrected source rows in the latest successful run

<sub>`data_issues` in sql/verify.sql</sub>

| source_file | outcome | rule_code | row_count | source_rows |
|---|---|---|---|---|
| olist_sellers_dataset.csv | corrected | city_ascii_folded | 1 | 2341 |

## Row counts reconcile with the rows the latest successful run validated

<sub>`check_row_counts` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| rows in olist.customers | error | 200 | 200 | PASS |
| rows in olist.order_customers | error | 200 | 200 | PASS |
| rows in olist.sellers | error | 157 | 157 | PASS |
| rows in olist.product_categories | error | 36 | 36 | PASS |
| rows in olist.products | error | 200 | 200 | PASS |
| rows in olist.orders | error | 200 | 200 | PASS |
| rows in olist.order_sellers | error | 198 | 198 | PASS |
| rows in olist.order_lines | error | 204 | 204 | PASS |
| rows in olist.order_items | error | 225 | 225 | PASS |

## Measures reconcile with totals computed from the validated source rows

<sub>`check_measures` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| source vs database: order_items | error | 225 | 225 | PASS |
| source vs database: orders | error | 200 | 200 | PASS |
| source vs database: total_item_freight | error | 4129.80 | 4129.80 | PASS |
| source vs database: total_item_price | error | 27711.84 | 27711.84 | PASS |

## Duplicate-key checks (primary keys and the 1:1 customer record)

<sub>`check_duplicate_keys` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| duplicate keys: customers | error | 0 | 0 | PASS |
| duplicate keys: order_customers | error | 0 | 0 | PASS |
| duplicate keys: sellers | error | 0 | 0 | PASS |
| duplicate keys: product_categories | error | 0 | 0 | PASS |
| duplicate keys: products | error | 0 | 0 | PASS |
| duplicate keys: orders | error | 0 | 0 | PASS |
| duplicate keys: order_sellers | error | 0 | 0 | PASS |
| duplicate keys: order_lines | error | 0 | 0 | PASS |
| duplicate keys: order_items | error | 0 | 0 | PASS |
| orders sharing one customer_id (must be 1:1) | error | 0 | 0 | PASS |

## Referential checks, minimum cardinalities and subset closure

<sub>`check_referential` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| orphans: order_customers -> customers | error | 0 | 0 | PASS |
| orphans: orders -> order_customers | error | 0 | 0 | PASS |
| orphans: products -> product_categories | error | 0 | 0 | PASS |
| orphans: order_sellers -> orders | error | 0 | 0 | PASS |
| orphans: order_sellers -> sellers | error | 0 | 0 | PASS |
| orphans: order_lines -> order_sellers | error | 0 | 0 | PASS |
| orphans: order_lines -> products | error | 0 | 0 | PASS |
| orphans: order_items -> order_lines | error | 0 | 0 | PASS |
| customers with no order record (min 1) | error | 0 | 0 | PASS |
| order_customers not used by an order (1:1) | error | 0 | 0 | PASS |
| order_sellers with no order_lines (min 1) | error | 0 | 0 | PASS |
| order_lines with no order_items (min 1) | error | 0 | 0 | PASS |
| sellers outside the subset closure (no order_sellers) | error | 0 | 0 | PASS |
| products outside the subset closure (no order_lines) | error | 0 | 0 | PASS |
| categories outside the subset closure (no products) | error | 0 | 0 | PASS |

## Every loaded order satisfies the documented sha256 subset rule

<sub>`check_subset_rule` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| orders outside the subset rule | error | 0 | 0 | PASS |

## Domain-quality checks (error = business rule; warn = known source anomaly, kept and reported)

<sub>`check_domain_quality` in sql/verify.sql</sub>

| check | severity | observed | expected | status |
|---|---|---|---|---|
| orders whose order_item_id is not exactly 1..n | error | 0 | 0 | PASS |
| seller shipping deadline before purchase | error | 0 | 0 | PASS |
| delivered or shipped orders with no items | warn | 0 | 0 | PASS |
| orders past approval stage missing the approval time | warn | 0 | 0 | PASS |
| delivered orders missing the customer delivery time | warn | 0 | 0 | PASS |
| non-delivered orders that have a customer delivery time | warn | 0 | 0 | PASS |
| handed to carrier before purchase | warn | 2 | 0 | WARN |
| handed to carrier before approval | warn | 4 | 0 | WARN |
| delivered to customer before carrier pickup | warn | 0 | 0 | PASS |
| seller shipping deadline more than 365 days after purchase | warn | 0 | 0 | PASS |
| zip prefixes reported with more than one state | warn | 0 | 0 | PASS |
| products with weight 0 g | warn | 0 | 0 | PASS |
| cities containing / , \ or ( (state or country appended) | warn | 1 | 0 | WARN |

## Documented valid exceptions (allowed by the schema on purpose)

<sub>`valid_exceptions` in sql/verify.sql</sub>

| exception_kind | detail | row_count |
|---|---|---|
| categories without an English translation | NULL | 0 |
| cities set to NULL (source value was not a place) | customer_city / seller_city NULL | 0 |
| order lines with zero freight (free shipping) | item_freight_value = 0 | 0 |
| orders without items (by status) | unavailable | 3 |
| products without a category | product_category_name NULL | 5 |
| products without weight/dimensions | measurements NULL | 0 |

## Content fingerprints (row count + md5 of all rows in key order) for change detection

<sub>`fingerprints` in sql/verify.sql</sub>

| table_name | row_count | content_md5 |
|---|---|---|
| customers | 200 | 3dff58b9ff8a6c49e3e546ca9280eb35 |
| order_customers | 200 | b926ea709d39271dbac012263a881d0f |
| sellers | 157 | 973f02e53235065bb8d0378736276360 |
| product_categories | 36 | 2c40e2501ddfed22229f66542879282b |
| products | 200 | f86ebebb08d280523d24d2f9f940d546 |
| orders | 200 | a57dacfa5ba969bb95d8259ffaf06505 |
| order_sellers | 198 | bad9ced91c5bd795ad42e87687c0e09d |
| order_lines | 204 | b135a52771f0adfc4ea2029c32ef297e |
| order_items | 225 | 013167b5362f8b28827380fcc6316ff0 |

## Database storage used by the two schemas (target: well under 300 MB)

<sub>`storage` in sql/verify.sql</sub>

| schema_name | total_size |
|---|---|
| ingest | 176 kB |
| olist | 1032 kB |

