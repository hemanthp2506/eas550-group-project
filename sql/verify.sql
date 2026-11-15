-- =====================================================================
-- Verification queries for the Olist source schema.
--
-- Run directly:   psql -v ON_ERROR_STOP=1 -f sql/verify.sql
-- Or with pass/fail evaluation and saved evidence:
--                 uv run olist-verify --label run1 --out docs/evidence
--
-- Each block starts with "-- name:" and "-- title:" lines. Blocks whose name
-- starts with "check_" return (check_name, severity, observed, expected):
--   error = must equal expected, otherwise verification fails
--   warn  = known data-quality finding; reported, does not fail
-- =====================================================================

-- name: runs
-- title: Ingestion runs
SELECT
    r.run_id,
    r.status,
    r.started_at,
    r.finished_at,
    coalesce(r.max_orders::text, 'full subset') AS scope,
    left(r.error_message, 140) AS error_message
FROM ingest.runs AS r
ORDER BY r.run_id;

-- name: source_files
-- title: Source files used by the latest successful run (provenance and row accounting)
WITH latest AS (
    SELECT max(run_id) AS run_id
    FROM ingest.runs
    WHERE status = 'succeeded'
)

SELECT
    sf.file_name,
    sf.sha256,
    sf.rows_read,
    sf.rows_in_subset,
    sf.rows_rejected,
    sf.rows_corrected
FROM ingest.source_files AS sf
INNER JOIN latest ON sf.run_id = latest.run_id
ORDER BY sf.file_name;

-- name: table_loads
-- title: Upsert outcome per table for every successful run
SELECT
    tl.run_id,
    tl.table_name,
    tl.rows_loaded,
    tl.rows_inserted,
    tl.rows_updated,
    tl.rows_unchanged
FROM ingest.table_loads AS tl
INNER JOIN ingest.runs AS r ON tl.run_id = r.run_id
WHERE r.status = 'succeeded'
ORDER BY
    tl.run_id,
    array_position(
        ARRAY[
            'customers', 'order_customers', 'sellers', 'product_categories',
            'products', 'orders', 'order_sellers', 'order_lines', 'order_items'
        ],
        tl.table_name
    );

-- name: data_issues
-- title: Rejected and corrected source rows in the latest successful run
-- (original values stay in ingest.data_issues.detail; they are not repeated in evidence)
WITH latest AS (
    SELECT max(run_id) AS run_id
    FROM ingest.runs
    WHERE status = 'succeeded'
)

SELECT
    di.source_file,
    di.outcome,
    di.rule_code,
    count(*) AS row_count,
    string_agg(di.source_row::text, ', ' ORDER BY di.source_row) AS source_rows
FROM ingest.data_issues AS di
INNER JOIN latest ON di.run_id = latest.run_id
GROUP BY di.source_file, di.outcome, di.rule_code
ORDER BY di.source_file, di.outcome, di.rule_code;

-- name: check_row_counts
-- title: Row counts reconcile with the rows the latest successful run validated
WITH latest AS (
    SELECT max(run_id) AS run_id
    FROM ingest.runs
    WHERE status = 'succeeded'
),

actual AS (
    SELECT
        'customers' AS table_name,
        count(*) AS row_count
    FROM olist.customers
    UNION ALL
    SELECT
        'order_customers',
        count(*)
    FROM olist.order_customers
    UNION ALL
    SELECT
        'sellers',
        count(*)
    FROM olist.sellers
    UNION ALL
    SELECT
        'product_categories',
        count(*)
    FROM olist.product_categories
    UNION ALL
    SELECT
        'products',
        count(*)
    FROM olist.products
    UNION ALL
    SELECT
        'orders',
        count(*)
    FROM olist.orders
    UNION ALL
    SELECT
        'order_sellers',
        count(*)
    FROM olist.order_sellers
    UNION ALL
    SELECT
        'order_lines',
        count(*)
    FROM olist.order_lines
    UNION ALL
    SELECT
        'order_items',
        count(*)
    FROM olist.order_items
)

-- Column order (check_name, severity, observed, expected) is read by olist-verify.
SELECT  -- noqa: ST06
    'rows in olist.' || a.table_name AS check_name,
    'error' AS severity,
    a.row_count AS observed,
    tl.rows_loaded AS expected
FROM actual AS a
INNER JOIN ingest.table_loads AS tl ON a.table_name = tl.table_name
INNER JOIN latest ON tl.run_id = latest.run_id
ORDER BY
    array_position(
        ARRAY[
            'customers', 'order_customers', 'sellers', 'product_categories',
            'products', 'orders', 'order_sellers', 'order_lines', 'order_items'
        ],
        a.table_name
    );

-- name: check_measures
-- title: Measures reconcile with totals computed from the validated source rows
WITH latest AS (
    SELECT max(run_id) AS run_id
    FROM ingest.runs
    WHERE status = 'succeeded'
),

db AS (
    SELECT
        'orders' AS measure_name,
        count(*)::numeric AS db_value
    FROM olist.orders
    UNION ALL
    SELECT
        'order_items',
        count(*)::numeric
    FROM olist.order_items
    UNION ALL
    SELECT
        'total_item_price',
        sum(ol.item_price)
    FROM olist.order_items AS oi
    INNER JOIN olist.order_lines AS ol
        ON oi.order_id = ol.order_id AND oi.product_id = ol.product_id
    UNION ALL
    SELECT
        'total_item_freight',
        sum(ol.item_freight_value)
    FROM olist.order_items AS oi
    INNER JOIN olist.order_lines AS ol
        ON oi.order_id = ol.order_id AND oi.product_id = ol.product_id
)

-- Column order (check_name, severity, observed, expected) is read by olist-verify.
SELECT  -- noqa: ST06
    'source vs database: ' || db.measure_name AS check_name,
    'error' AS severity,
    db.db_value AS observed,
    rm.measure_value AS expected
FROM db
INNER JOIN ingest.run_measures AS rm ON db.measure_name = rm.measure_name
INNER JOIN latest ON rm.run_id = latest.run_id
ORDER BY db.measure_name;

-- name: check_duplicate_keys
-- title: Duplicate-key checks (primary keys and the 1:1 customer record)
SELECT
    'duplicate keys: customers' AS check_name,
    'error' AS severity,
    count(*) AS observed,
    0 AS expected
FROM (
    SELECT customer_unique_id FROM olist.customers
    GROUP BY customer_unique_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: order_customers',
    'error',
    count(*),
    0
FROM (
    SELECT customer_id FROM olist.order_customers
    GROUP BY customer_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: sellers',
    'error',
    count(*),
    0
FROM (
    SELECT seller_id FROM olist.sellers
    GROUP BY seller_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: product_categories',
    'error',
    count(*),
    0
FROM (
    SELECT product_category_name FROM olist.product_categories
    GROUP BY product_category_name
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: products',
    'error',
    count(*),
    0
FROM (
    SELECT product_id FROM olist.products
    GROUP BY product_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: orders',
    'error',
    count(*),
    0
FROM (
    SELECT order_id FROM olist.orders
    GROUP BY order_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: order_sellers',
    'error',
    count(*),
    0
FROM (
    SELECT
        order_id,
        seller_id
    FROM olist.order_sellers
    GROUP BY order_id, seller_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: order_lines',
    'error',
    count(*),
    0
FROM (
    SELECT
        order_id,
        product_id
    FROM olist.order_lines
    GROUP BY order_id, product_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'duplicate keys: order_items',
    'error',
    count(*),
    0
FROM (
    SELECT
        order_id,
        order_item_id
    FROM olist.order_items
    GROUP BY order_id, order_item_id
    HAVING count(*) > 1
) AS d
UNION ALL
SELECT
    'orders sharing one customer_id (must be 1:1)',
    'error',
    count(*),
    0
FROM (
    SELECT customer_id FROM olist.orders
    GROUP BY customer_id
    HAVING count(*) > 1
) AS d;

-- name: check_referential
-- title: Referential checks, minimum cardinalities and subset closure
SELECT
    'orphans: order_customers -> customers' AS check_name,
    'error' AS severity,
    count(*) AS observed,
    0 AS expected
FROM olist.order_customers AS oc
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.customers AS c
        WHERE c.customer_unique_id = oc.customer_unique_id
    )
UNION ALL
SELECT
    'orphans: orders -> order_customers',
    'error',
    count(*),
    0
FROM olist.orders AS o
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_customers AS oc
        WHERE oc.customer_id = o.customer_id
    )
UNION ALL
SELECT
    'orphans: products -> product_categories',
    'error',
    count(*),
    0
FROM olist.products AS p
WHERE
    p.product_category_name IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM olist.product_categories AS pc
        WHERE pc.product_category_name = p.product_category_name
    )
UNION ALL
SELECT
    'orphans: order_sellers -> orders',
    'error',
    count(*),
    0
FROM olist.order_sellers AS os
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.orders AS o
        WHERE o.order_id = os.order_id
    )
UNION ALL
SELECT
    'orphans: order_sellers -> sellers',
    'error',
    count(*),
    0
FROM olist.order_sellers AS os
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.sellers AS s
        WHERE s.seller_id = os.seller_id
    )
UNION ALL
SELECT
    'orphans: order_lines -> order_sellers',
    'error',
    count(*),
    0
FROM olist.order_lines AS ol
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_sellers AS os
        WHERE os.order_id = ol.order_id AND os.seller_id = ol.seller_id
    )
UNION ALL
SELECT
    'orphans: order_lines -> products',
    'error',
    count(*),
    0
FROM olist.order_lines AS ol
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.products AS p
        WHERE p.product_id = ol.product_id
    )
UNION ALL
SELECT
    'orphans: order_items -> order_lines',
    'error',
    count(*),
    0
FROM olist.order_items AS oi
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_lines AS ol
        WHERE ol.order_id = oi.order_id AND ol.product_id = oi.product_id
    )
UNION ALL
SELECT
    'customers with no order record (min 1)',
    'error',
    count(*),
    0
FROM olist.customers AS c
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_customers AS oc
        WHERE oc.customer_unique_id = c.customer_unique_id
    )
UNION ALL
SELECT
    'order_customers not used by an order (1:1)',
    'error',
    count(*),
    0
FROM olist.order_customers AS oc
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.orders AS o
        WHERE o.customer_id = oc.customer_id
    )
UNION ALL
SELECT
    'order_sellers with no order_lines (min 1)',
    'error',
    count(*),
    0
FROM olist.order_sellers AS os
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_lines AS ol
        WHERE ol.order_id = os.order_id AND ol.seller_id = os.seller_id
    )
UNION ALL
SELECT
    'order_lines with no order_items (min 1)',
    'error',
    count(*),
    0
FROM olist.order_lines AS ol
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_items AS oi
        WHERE oi.order_id = ol.order_id AND oi.product_id = ol.product_id
    )
UNION ALL
SELECT
    'sellers outside the subset closure (no order_sellers)',
    'error',
    count(*),
    0
FROM olist.sellers AS s
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_sellers AS os
        WHERE os.seller_id = s.seller_id
    )
UNION ALL
SELECT
    'products outside the subset closure (no order_lines)',
    'error',
    count(*),
    0
FROM olist.products AS p
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_lines AS ol
        WHERE ol.product_id = p.product_id
    )
UNION ALL
SELECT
    'categories outside the subset closure (no products)',
    'error',
    count(*),
    0
FROM olist.product_categories AS pc
WHERE NOT EXISTS (
    SELECT 1 FROM olist.products AS p
    WHERE p.product_category_name = pc.product_category_name
);

-- name: check_subset_rule
-- title: Every loaded order satisfies the documented sha256 subset rule
-- Column order (check_name, severity, observed, expected) is read by olist-verify.
SELECT  -- noqa: ST06
    'orders outside the subset rule' AS check_name,
    'error' AS severity,
    count(*) AS observed,
    0 AS expected
FROM olist.orders AS o
WHERE
    mod(
        ('x' || left(encode(sha256(convert_to(o.order_id, 'UTF8')), 'hex'), 8))::bit(32)::bigint,
        10
    ) <> 0;

-- name: check_domain_quality
-- title: Domain-quality checks (error = business rule; warn = known source anomaly, kept and reported)
SELECT
    'orders whose order_item_id is not exactly 1..n' AS check_name,
    'error' AS severity,
    count(*) AS observed,
    0 AS expected
FROM (
    SELECT order_id FROM olist.order_items
    GROUP BY order_id
    HAVING min(order_item_id) <> 1 OR max(order_item_id) <> count(*)
) AS g
UNION ALL
SELECT
    'seller shipping deadline before purchase',
    'error',
    count(*),
    0
FROM olist.order_sellers AS os
INNER JOIN olist.orders AS o ON os.order_id = o.order_id
WHERE os.shipping_limit_date < o.order_purchase_timestamp
UNION ALL
SELECT
    'delivered or shipped orders with no items',
    'warn',
    count(*),
    0
FROM olist.orders AS o
WHERE
    o.order_status IN ('delivered', 'shipped')
    AND NOT EXISTS (
        SELECT 1 FROM olist.order_items AS oi
        WHERE oi.order_id = o.order_id
    )
UNION ALL
SELECT
    'orders past approval stage missing the approval time',
    'warn',
    count(*),
    0
FROM olist.orders
WHERE
    order_approved_at IS NULL
    AND order_status NOT IN ('created', 'canceled', 'unavailable')
UNION ALL
SELECT
    'delivered orders missing the customer delivery time',
    'warn',
    count(*),
    0
FROM olist.orders
WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL
UNION ALL
SELECT
    'non-delivered orders that have a customer delivery time',
    'warn',
    count(*),
    0
FROM olist.orders
WHERE order_status <> 'delivered' AND order_delivered_customer_date IS NOT NULL
UNION ALL
SELECT
    'handed to carrier before purchase',
    'warn',
    count(*),
    0
FROM olist.orders
WHERE order_delivered_carrier_date < order_purchase_timestamp
UNION ALL
SELECT
    'handed to carrier before approval',
    'warn',
    count(*),
    0
FROM olist.orders
WHERE order_delivered_carrier_date < order_approved_at
UNION ALL
SELECT
    'delivered to customer before carrier pickup',
    'warn',
    count(*),
    0
FROM olist.orders
WHERE order_delivered_customer_date < order_delivered_carrier_date
UNION ALL
SELECT
    'seller shipping deadline more than 365 days after purchase',
    'warn',
    count(*),
    0
FROM olist.order_sellers AS os
INNER JOIN olist.orders AS o ON os.order_id = o.order_id
WHERE os.shipping_limit_date > o.order_purchase_timestamp + interval '365 days'
UNION ALL
SELECT
    'zip prefixes reported with more than one state',
    'warn',
    count(*),
    0
FROM (
    SELECT z.zip_prefix
    FROM (
        SELECT
            customer_zip_code_prefix AS zip_prefix,
            customer_state AS state
        FROM olist.order_customers
        UNION ALL
        SELECT
            seller_zip_code_prefix,
            seller_state
        FROM olist.sellers
    ) AS z
    GROUP BY z.zip_prefix
    HAVING count(DISTINCT z.state) > 1
) AS conflicts
UNION ALL
SELECT
    'products with weight 0 g',
    'warn',
    count(*),
    0
FROM olist.products
WHERE product_weight_g = 0
UNION ALL
SELECT
    'cities containing / , \ or ( (state or country appended)',
    'warn',
    count(*),
    0
FROM (
    SELECT customer_city AS city FROM olist.order_customers
    UNION ALL
    SELECT seller_city FROM olist.sellers
) AS cities
WHERE cities.city ~ '[/,\\(]';

-- name: valid_exceptions
-- title: Documented valid exceptions (allowed by the schema on purpose)
SELECT
    'orders without items (by status)' AS exception_kind,
    o.order_status AS detail,
    count(*) AS row_count
FROM olist.orders AS o
WHERE
    NOT EXISTS (
        SELECT 1 FROM olist.order_items AS oi
        WHERE oi.order_id = o.order_id
    )
GROUP BY o.order_status
UNION ALL
SELECT
    'orders never approved (approved_at NULL, by status)',
    order_status,
    count(*)
FROM olist.orders
WHERE order_approved_at IS NULL AND order_status IN ('created', 'canceled', 'unavailable')
GROUP BY order_status
UNION ALL
SELECT
    'products without a category',
    'product_category_name NULL',
    count(*)
FROM olist.products
WHERE product_category_name IS NULL
UNION ALL
SELECT
    'products without weight/dimensions',
    'measurements NULL',
    count(*)
FROM olist.products
WHERE product_weight_g IS NULL
UNION ALL
SELECT
    'categories without an English translation',
    string_agg(product_category_name, ', ' ORDER BY product_category_name),
    count(*)
FROM olist.product_categories
WHERE product_category_name_english IS NULL
UNION ALL
SELECT
    'order lines with zero freight (free shipping)',
    'item_freight_value = 0',
    count(*)
FROM olist.order_lines
WHERE item_freight_value = 0
UNION ALL
SELECT
    'cities set to NULL (source value was not a place)',
    'customer_city / seller_city NULL',
    count(*)
FROM (
    SELECT customer_city AS city FROM olist.order_customers
    UNION ALL
    SELECT seller_city FROM olist.sellers
) AS cities
WHERE cities.city IS NULL
ORDER BY exception_kind, detail;

-- name: fingerprints
-- title: Content fingerprints (row count + md5 of all rows in key order) for change detection
SELECT
    'customers' AS table_name,
    count(*) AS row_count,
    md5(string_agg(t::text, E'\n' ORDER BY t.customer_unique_id)) AS content_md5
FROM olist.customers AS t
UNION ALL
SELECT
    'order_customers',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.customer_id))
FROM olist.order_customers AS t
UNION ALL
SELECT
    'sellers',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.seller_id))
FROM olist.sellers AS t
UNION ALL
SELECT
    'product_categories',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.product_category_name))
FROM olist.product_categories AS t
UNION ALL
SELECT
    'products',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.product_id))
FROM olist.products AS t
UNION ALL
SELECT
    'orders',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.order_id))
FROM olist.orders AS t
UNION ALL
SELECT
    'order_sellers',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.order_id, t.seller_id))
FROM olist.order_sellers AS t
UNION ALL
SELECT
    'order_lines',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.order_id, t.product_id))
FROM olist.order_lines AS t
UNION ALL
SELECT
    'order_items',
    count(*),
    md5(string_agg(t::text, E'\n' ORDER BY t.order_id, t.order_item_id))
FROM olist.order_items AS t;

-- name: storage
-- title: Database storage used by the two schemas (target: well under 300 MB)
SELECT
    n.nspname AS schema_name,
    pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS total_size
FROM pg_class AS c
INNER JOIN pg_namespace AS n ON c.relnamespace = n.oid
WHERE n.nspname IN ('olist', 'ingest') AND c.relkind IN ('r', 'p')
GROUP BY n.nspname
ORDER BY n.nspname;
