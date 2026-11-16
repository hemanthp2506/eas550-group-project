# Design note: Phase 1 relational model and ingestion

How we modeled the Olist data, why the tables are in third normal form (3NF), and how the
loader stays safe to rerun. Figures come from the source files and
[`docs/evidence/`](evidence/).

## 1. Data and subset

We use the Olist Brazilian E-Commerce dataset (Kaggle archive dated 2021-10-01, CC BY-NC-SA
4.0) and leave reviews, payments and geolocation for later phases.
[`source_manifest.json`](source_manifest.json) records each file's checksum and row count,
and ingestion stops if a file changes.

**Which orders.** An order is in the subset when the first 8 hex digits of
`sha256(order_id)`, read as a number, are divisible by 10: 9,901 of 99,441 orders, with
their 11,242 items and every row they refer to (9,866 customers, 6,619 products,
71 categories, 1,617 sellers). Unlike a date window or a random sample, the rule ignores
file order and needs no seed, and every month and order status keeps its full-data share to
within half a percentage point.

**Which columns.** All of them except three product fields, `product_name_lenght`,
`product_description_lenght` and `product_photos_qty`. They describe the listing (title and
description length, photo count), not the sale, and none of our questions (sales by
category and month, prices and freight by seller) use them.

**Slice first.** A 200-order trial load into a throwaway database caught a real bug before
the full load (pandas was sending prices as text), and the failed run rolled back cleanly.

## 2. Entities and relationships

The [ERD](erd.md) shows every table, key and cardinality. Olist gives every order a new
`customer_id`, even for repeat buyers, while `customer_unique_id` is the person. So
`order_customers` holds one order's customer record (1:1 with `orders`, enforced by a
UNIQUE foreign key), and `customers` holds the person, who can have several records
(35 people in the subset ordered more than once).

An order can have several sellers and products, and a product can have several sellers
(1,225 in the source do). `order_sellers` (one row per order and seller) and `order_lines`
(one row per order and product) resolve these many-to-many relationships. `order_items`
keeps Olist's key (order_id, order_item_id), one row per unit sold, and is the fact table.

## 3. Functional dependencies and 3NF

A dependency A → B means each value of A always comes with the same value of B. We tested
every candidate on all source rows, not just the subset.

| Dependency | What the data shows | Result |
|---|---|---|
| customer_id → customer_unique_id, address | holds (99,441 rows) | `order_customers` |
| customer_unique_id → address | fails: 250 people have 2+ zip prefixes | address stays per order |
| (order_id, seller_id) → shipping_limit_date | holds (100,010 pairs) | `order_sellers` |
| (order_id, product_id) → seller_id, price, freight | holds (102,425 pairs) | `order_lines` |
| product_category_name → English name | holds (translation file) | `product_categories` |
| zip prefix → state or city; city → state | fail: 33, 136, 188 conflicts | not used (see below) |

**Why the raw items file isn't in 3NF, and the fix.** Its key is (order_id, order_item_id),
yet the shipping deadline depends only on the order and seller, and price and freight only
on the order and product. Olist repeats a line once per unit (7,088 source lines have
several units), so one price is stored many times and a careless update could make the
copies disagree. Splitting the file into `order_sellers` (deadline), `order_lines` (seller,
price, freight) and `order_items` (one row per unit), linked by composite foreign keys,
stores each fact once. Every non-key column now depends on the whole key and nothing else,
which is 3NF, and every determinant is a candidate key, so the tables are in BCNF too.

**Zip prefix and state.** A zip prefix should map to one state, but 33 in the source (12 in
the subset) appear with two, all in seller addresses. Rather than guess which is wrong in a
lookup table, we keep city and state on each address and let verification list the
conflicts.

## 4. Types, constraints and valid exceptions

IDs are 32-character lowercase hex (a domain type), as in the source. Zip prefixes are
5-digit text so leading zeros survive, and states must be one of the 27 Brazilian codes.
Money is `numeric(10,2)`, exact to the cent, and timestamps have no time zone because the
source has none. Every table has a primary key and every reference a foreign key. Required
columns are NOT NULL, UNIQUE enforces one order per customer record, and CHECK constraints
cover statuses, prices, measurement ranges and dates: nothing is approved, delivered or due
before it was purchased, a rule the source never breaks.

**Exceptions we allow on purpose.** Some rules sound right, but real data breaks them, so
verification reports them as warnings instead of rejecting orders: 125 carrier pickups
before approval (19 even before purchase), 2 deliveries before pickup, and two delivered
orders missing a delivery or an approval time. Other cases are simply normal: empty
timestamps for steps an order hasn't reached, 58 canceled or unavailable orders with no
items, 90 products with no category, 2 categories with no English name, and 33
free-shipping lines. Verification also checks rules no constraint can express, such as
"every order line has at least one unit".

## 5. Ingestion and reruns

`olist-ingest` checks the checksums, applies the subset rule and validates types, missing
values, ID formats, references and the two dependencies above. It loads all nine tables,
parents first, in one transaction, using pandas `to_sql(if_exists="append")` with an upsert
(`INSERT … ON CONFLICT … DO UPDATE`) that rewrites a row only when a value changed. A
failure rolls everything back, and the designed tables are never dropped or replaced.

**Data quality.** Every decision is logged in `ingest.data_issues` with the original value,
and an order loads whole or not at all. This run rejected **0 rows** and corrected
**3 seller city names** (a double space, a `´` used as an apostrophe, and an email address
in the city field, set to NULL). Tests on a small made-up dataset cover the other rules,
such as bad statuses, duplicates and lost leading zeros.

**Running it twice.** Run 1 inserted 69,445 rows; run 2, on the same input, changed
nothing. Both pass the same checks (43 pass, 9 warnings, 0 failures), and item totals match
the source to the cent (R$ 1,329,141.86 in prices, R$ 224,877.74 in freight). Counts alone
can miss a changed value, so verification also fingerprints each table with an md5 hash,
and all nine match across runs. Upserts never delete, so if the source or the subset rule
changes, the documented rebuild is `olist-db reset --yes` and a fresh load.
