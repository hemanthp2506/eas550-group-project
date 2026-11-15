-- =====================================================================
-- Olist source schema (3NF) and ingestion audit tables
--
-- Creates everything from an empty database. Run it as one transaction:
--   psql -v ON_ERROR_STOP=1 --single-transaction -f sql/schema.sql
-- or:
--   uv run olist-db init
--
-- Design notes (functional dependencies, 3NF, valid exceptions) are in
-- docs/design_note.md; the ERD is in docs/erd.md.
-- =====================================================================

CREATE SCHEMA olist;
COMMENT ON SCHEMA olist IS
'Normalized (3NF) source tables for the Olist Brazilian e-commerce subset.';

-- ---------------------------------------------------------------------
-- Domains: one definition per kind of value, reused by every column
-- ---------------------------------------------------------------------

-- Olist identifiers are 32 lowercase hexadecimal characters.
CREATE DOMAIN olist.hex_id AS text
CHECK (value ~ '^[0-9a-f]{32}$');

-- Brazilian CEP prefix: exactly five digits, kept as text so leading zeros survive.
CREATE DOMAIN olist.zip_prefix AS text
CHECK (value ~ '^[0-9]{5}$');

-- The 26 Brazilian states plus the Federal District (UF codes).
CREATE DOMAIN olist.state_code AS text
CHECK (
    value IN (
        'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO',
        'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR',
        'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'
    )
);

-- Free-text city as cleaned by ingestion: trimmed, lowercase, non-empty.
CREATE DOMAIN olist.city_name AS text
CHECK (value = lower(btrim(value)) AND value <> '');

-- Product category key, snake_case as published by Olist.
CREATE DOMAIN olist.category_key AS text
CHECK (value ~ '^[a-z0-9_]+$');

-- ---------------------------------------------------------------------
-- Customers: a person (customer_unique_id) and the per-order customer
-- record (customer_id) that carries the delivery location.
-- ---------------------------------------------------------------------

CREATE TABLE olist.customers (
    customer_unique_id olist.hex_id PRIMARY KEY
);
COMMENT ON TABLE olist.customers IS
'One row per real customer (person). Olist issues a new customer_id for every order; customer_unique_id links them.';

CREATE TABLE olist.order_customers (
    customer_id olist.hex_id PRIMARY KEY,
    customer_unique_id olist.hex_id NOT NULL
    REFERENCES olist.customers (customer_unique_id),
    customer_zip_code_prefix olist.zip_prefix NOT NULL,
    customer_city olist.city_name,
    customer_state olist.state_code NOT NULL
);
COMMENT ON TABLE olist.order_customers IS
'Customer record of exactly one order. The address depends on customer_id, not on the person.';
COMMENT ON COLUMN olist.order_customers.customer_city IS
'NULL only when the source value is not a place name; the original is kept in ingest.data_issues.';

CREATE INDEX order_customers_customer_unique_id_idx
ON olist.order_customers (customer_unique_id);

-- ---------------------------------------------------------------------
-- Sellers
-- ---------------------------------------------------------------------

CREATE TABLE olist.sellers (
    seller_id olist.hex_id PRIMARY KEY,
    seller_zip_code_prefix olist.zip_prefix NOT NULL,
    seller_city olist.city_name,
    seller_state olist.state_code NOT NULL
);
COMMENT ON COLUMN olist.sellers.seller_city IS
'NULL only when the source value is not a place name; the original is kept in ingest.data_issues.';

-- ---------------------------------------------------------------------
-- Products and categories
-- ---------------------------------------------------------------------

CREATE TABLE olist.product_categories (
    product_category_name olist.category_key PRIMARY KEY,
    product_category_name_english olist.category_key UNIQUE
);
COMMENT ON COLUMN olist.product_categories.product_category_name_english IS
'NULL when Olist publishes no translation (pc_gamer, portateis_cozinha_e_preparadores_de_alimentos).';

CREATE TABLE olist.products (
    product_id olist.hex_id PRIMARY KEY,
    product_category_name olist.category_key
    REFERENCES olist.product_categories (product_category_name),
    product_weight_g integer CHECK (product_weight_g >= 0),
    product_length_cm smallint CHECK (product_length_cm > 0),
    product_height_cm smallint CHECK (product_height_cm > 0),
    product_width_cm smallint CHECK (product_width_cm > 0)
);
COMMENT ON COLUMN olist.products.product_category_name IS
'NULL for products Olist left uncategorized (valid exception, 610 in the full source).';
COMMENT ON COLUMN olist.products.product_weight_g IS
'Zero is allowed but flagged by verification: the source lists four products at 0 g.';

CREATE INDEX products_product_category_name_idx
ON olist.products (product_category_name);

-- ---------------------------------------------------------------------
-- Orders
-- ---------------------------------------------------------------------

CREATE TABLE olist.orders (
    order_id olist.hex_id PRIMARY KEY,
    customer_id olist.hex_id NOT NULL UNIQUE
    REFERENCES olist.order_customers (customer_id),
    order_status text NOT NULL CHECK (
        order_status IN (
            'created', 'approved', 'invoiced', 'processing',
            'shipped', 'delivered', 'canceled', 'unavailable'
        )
    ),
    order_purchase_timestamp timestamp NOT NULL,
    order_approved_at timestamp,
    order_delivered_carrier_date timestamp,
    order_delivered_customer_date timestamp,
    order_estimated_delivery_date date NOT NULL,
    CONSTRAINT orders_approved_after_purchase
    CHECK (order_approved_at >= order_purchase_timestamp),
    CONSTRAINT orders_delivered_after_purchase
    CHECK (order_delivered_customer_date >= order_purchase_timestamp),
    CONSTRAINT orders_estimate_not_before_purchase
    CHECK (order_estimated_delivery_date >= order_purchase_timestamp::date)
);
COMMENT ON TABLE olist.orders IS
'One row per order. customer_id is UNIQUE: each per-order customer record belongs to exactly one order (1:1).';
COMMENT ON COLUMN olist.orders.order_purchase_timestamp IS
'Local time as published (no time zone in the source), so stored as timestamp without time zone.';
COMMENT ON COLUMN olist.orders.order_delivered_carrier_date IS
'Set once the order reaches the carrier. Not forced after approval: the source has inversions (reported).';

-- ---------------------------------------------------------------------
-- Order items, decomposed to 3NF
--   source key (order_id, order_item_id) -> product_id, seller_id,
--   shipping_limit_date, price, freight_value, with two further FDs:
--     (order_id, seller_id)  -> shipping_limit_date
--     (order_id, product_id) -> seller_id, price, freight_value
-- ---------------------------------------------------------------------

CREATE TABLE olist.order_sellers (
    order_id olist.hex_id NOT NULL REFERENCES olist.orders (order_id),
    seller_id olist.hex_id NOT NULL REFERENCES olist.sellers (seller_id),
    shipping_limit_date timestamp NOT NULL,
    PRIMARY KEY (order_id, seller_id)
);
COMMENT ON TABLE olist.order_sellers IS
'Resolves orders M:N sellers: the part of an order fulfilled by one seller, with that seller''s shipping deadline.';

CREATE INDEX order_sellers_seller_id_idx ON olist.order_sellers (seller_id);

CREATE TABLE olist.order_lines (
    order_id olist.hex_id NOT NULL,
    product_id olist.hex_id NOT NULL
    REFERENCES olist.products (product_id),
    seller_id olist.hex_id NOT NULL,
    item_price numeric(10, 2) NOT NULL CHECK (item_price > 0),
    item_freight_value numeric(10, 2) NOT NULL CHECK (item_freight_value >= 0),
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id, seller_id)
    REFERENCES olist.order_sellers (order_id, seller_id)
);
COMMENT ON TABLE olist.order_lines IS
'Resolves orders M:N products: one product in one order. Quantity is the number of order_items rows for the line.';
COMMENT ON COLUMN olist.order_lines.item_price IS
'Price of ONE unit (source column price, identical on every unit of the line).';
COMMENT ON COLUMN olist.order_lines.item_freight_value IS
'Freight allocated to ONE unit (source column freight_value). Zero is valid (free shipping).';

CREATE INDEX order_lines_order_seller_idx ON olist.order_lines (order_id, seller_id);
CREATE INDEX order_lines_product_id_idx ON olist.order_lines (product_id);

CREATE TABLE olist.order_items (
    order_id olist.hex_id NOT NULL,
    order_item_id smallint NOT NULL CHECK (order_item_id >= 1),
    product_id olist.hex_id NOT NULL,
    PRIMARY KEY (order_id, order_item_id),
    FOREIGN KEY (order_id, product_id)
    REFERENCES olist.order_lines (order_id, product_id)
);
COMMENT ON TABLE olist.order_items IS
'One row per unit sold, keyed as in the source by (order_id, order_item_id); this is the fact grain.';

CREATE INDEX order_items_order_product_idx ON olist.order_items (order_id, product_id);

-- =====================================================================
-- Ingestion audit: provenance, per-run counts and data-quality decisions
-- =====================================================================

CREATE SCHEMA ingest;
COMMENT ON SCHEMA ingest IS
'Run log, source checksums, load counts and row-level data-quality decisions.';

CREATE TABLE ingest.runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'succeeded', 'failed')),
    subset_rule text NOT NULL,
    max_orders integer CHECK (max_orders > 0),
    source_archive_sha256 text CHECK (source_archive_sha256 ~ '^[0-9a-f]{64}$'),
    error_message text,
    CONSTRAINT runs_finished_iff_not_running
    CHECK ((status = 'running') = (finished_at IS NULL))
);
COMMENT ON COLUMN ingest.runs.max_orders IS
'Slice size for a trial load; NULL means the full documented subset.';

CREATE TABLE ingest.source_files (
    run_id bigint NOT NULL REFERENCES ingest.runs (run_id),
    file_name text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    rows_read integer NOT NULL CHECK (rows_read >= 0),
    rows_in_subset integer NOT NULL CHECK (rows_in_subset >= 0),
    rows_rejected integer NOT NULL CHECK (rows_rejected >= 0),
    rows_corrected integer NOT NULL CHECK (rows_corrected >= 0),
    PRIMARY KEY (run_id, file_name)
);

CREATE TABLE ingest.table_loads (
    run_id bigint NOT NULL REFERENCES ingest.runs (run_id),
    table_name text NOT NULL,
    rows_loaded integer NOT NULL CHECK (rows_loaded >= 0),
    rows_inserted integer NOT NULL CHECK (rows_inserted >= 0),
    rows_updated integer NOT NULL CHECK (rows_updated >= 0),
    rows_unchanged integer NOT NULL CHECK (rows_unchanged >= 0),
    PRIMARY KEY (run_id, table_name),
    CONSTRAINT table_loads_counts_add_up
    CHECK (rows_inserted + rows_updated + rows_unchanged = rows_loaded)
);

CREATE TABLE ingest.run_measures (
    run_id bigint NOT NULL REFERENCES ingest.runs (run_id),
    measure_name text NOT NULL,
    measure_value numeric NOT NULL,
    PRIMARY KEY (run_id, measure_name)
);
COMMENT ON TABLE ingest.run_measures IS
'Totals computed from the validated source rows, reconciled against the loaded tables by verification.';

CREATE TABLE ingest.data_issues (
    issue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES ingest.runs (run_id),
    source_file text NOT NULL,
    source_row integer NOT NULL CHECK (source_row >= 1),
    record_key text NOT NULL,
    rule_code text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('rejected', 'corrected')),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
COMMENT ON COLUMN ingest.data_issues.outcome IS
'rejected = source row not loaded; corrected = loaded with the change described in detail.';
COMMENT ON COLUMN ingest.data_issues.source_row IS
'1-based data row number in the source CSV (header excluded).';

CREATE INDEX data_issues_run_id_idx ON ingest.data_issues (run_id);
