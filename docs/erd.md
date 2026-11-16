# ERD: Olist source schema (`olist`)

The diagram shows the nine tables of the `olist` schema, their keys and how they relate.
GitHub draws it from the Mermaid code below.

How to read it: the line ends use crow's-foot notation, where `||` means exactly one, `|o`
zero or one, `|{` one or more and `o{` zero or more. PK = primary key, FK = foreign key,
UK = unique. Column types are PostgreSQL types or the domains defined in
[`sql/schema.sql`](../sql/schema.sql) (`hex_id`, `zip_prefix`, `state_code`, `city_name`,
`category_key`).

```mermaid
erDiagram
    customers ||--|{ order_customers : "is recorded on"
    order_customers ||--|| orders : "belongs to exactly one"
    orders ||--o{ order_sellers : "is fulfilled by"
    sellers ||--o{ order_sellers : "fulfils"
    order_sellers ||--|{ order_lines : "ships"
    products ||--o{ order_lines : "is sold as"
    product_categories |o--o{ products : "classifies"
    order_lines ||--|{ order_items : "has units"

    customers {
        hex_id customer_unique_id PK "the person"
    }
    order_customers {
        hex_id customer_id PK "one per order"
        hex_id customer_unique_id FK "NOT NULL"
        zip_prefix customer_zip_code_prefix "NOT NULL"
        city_name customer_city "nullable"
        state_code customer_state "NOT NULL"
    }
    orders {
        hex_id order_id PK
        hex_id customer_id FK, UK "NOT NULL (1:1)"
        text order_status "CHECK one of 8"
        timestamp order_purchase_timestamp "NOT NULL"
        timestamp order_approved_at "nullable, >= purchase"
        timestamp order_delivered_carrier_date "nullable"
        timestamp order_delivered_customer_date "nullable, >= purchase"
        date order_estimated_delivery_date "NOT NULL, >= purchase day"
    }
    sellers {
        hex_id seller_id PK
        zip_prefix seller_zip_code_prefix "NOT NULL"
        city_name seller_city "nullable"
        state_code seller_state "NOT NULL"
    }
    product_categories {
        category_key product_category_name PK
        category_key product_category_name_english UK "nullable"
    }
    products {
        hex_id product_id PK
        category_key product_category_name FK "nullable"
        integer product_weight_g ">= 0"
        smallint product_length_cm "> 0"
        smallint product_height_cm "> 0"
        smallint product_width_cm "> 0"
    }
    order_sellers {
        hex_id order_id PK, FK
        hex_id seller_id PK, FK
        timestamp shipping_limit_date "NOT NULL"
    }
    order_lines {
        hex_id order_id PK, FK "FK (order_id, seller_id) to order_sellers"
        hex_id product_id PK, FK
        hex_id seller_id FK "NOT NULL"
        numeric item_price "(10,2) > 0, per unit"
        numeric item_freight_value "(10,2) >= 0, per unit"
    }
    order_items {
        hex_id order_id PK, FK "FK (order_id, product_id) to order_lines"
        smallint order_item_id PK ">= 1, numbered 1..n"
        hex_id product_id FK "NOT NULL"
    }
```

## Relationships and how each rule is enforced

| Relationship | Cardinality | Enforced by |
|---|---|---|
| customers to order_customers | 1 to 1..N | FK `order_customers.customer_unique_id` (NOT NULL); the minimum of 1 is checked by verification |
| order_customers to orders | 1 to 1 | FK + UNIQUE on `orders.customer_id`; "every record used by an order" is checked by verification |
| orders to order_sellers | 1 to 0..N | FK; orders with no items (canceled/unavailable) are a valid exception |
| sellers to order_sellers | 1 to 0..N | FK; in the subset every seller has at least one (closure check) |
| order_sellers to order_lines | 1 to 1..N | composite FK `(order_id, seller_id)`; minimum of 1 checked by verification |
| products to order_lines | 1 to 0..N | FK; in the subset every product has at least one (closure check) |
| product_categories to products | 0..1 to 0..N | nullable FK (90 subset products have no category) |
| order_lines to order_items | 1 to 1..N | composite FK `(order_id, product_id)`; minimum of 1 checked by verification |

**Many-to-many relationships:** orders and sellers are linked through `order_sellers`.
Orders and products, and products and sellers (the same product can be sold by several
sellers), are linked through `order_lines`.

**Fact table:** `order_items`, one row per unit sold. Each unit takes its price and freight
from its `order_lines` row, and its seller and shipping deadline from `order_sellers`. Later
phases can slice it by product and category, seller, customer (through `orders` and
`order_customers`) and purchase date.

The `ingest` schema holds the loader's audit tables (`runs`, `source_files`, `table_loads`,
`run_measures`, `data_issues`). They record each run, are keyed by `run_id`, and are not
part of the business model.
