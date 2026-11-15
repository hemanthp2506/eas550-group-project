# Olist relational source schema and ingestion

Phase 1 lays the foundation for the rest of the project: a clean PostgreSQL database built
from about a tenth of the Olist Brazilian e-commerce data, before any analytics are added.
It has three parts:
- a schema in third normal form (3NF), designed around how the data actually behaves;
- a Python loader (pandas and SQLAlchemy) that checks every row and is safe to run again;
- verification that anyone can rerun, with the results saved in this repo.

## Team

- Hemanth Poondla
- Harini Karnati
- Saksham Saxena

## Where each Phase 1 deliverable lives

| Requirement | Where |
|---|---|
| ERD: primary and foreign keys, cardinalities, relationship constraints | [docs/erd.md](docs/erd.md) |
| Design note (about 2 pages): functional dependencies, 3NF, types, valid exceptions | [docs/design_note.md](docs/design_note.md) |
| `schema.sql` that builds the schema from an empty database | [sql/schema.sql](sql/schema.sql) |
| Schema tests: good data is accepted, bad data is rejected with the expected error | [tests/test_schema.py](tests/test_schema.py) |
| Ingestion: subset rule, validation, parent-first load | [src/olist_pipeline/](src/olist_pipeline/) (`subset.py`, `validate.py`, `ingest.py`) |
| Rerun safety: upsert into the existing tables, one transaction | [src/olist_pipeline/load.py](src/olist_pipeline/load.py) |
| Verification queries and their runner | [sql/verify.sql](sql/verify.sql), [src/olist_pipeline/verify.py](src/olist_pipeline/verify.py) |
| Count and check evidence: slice, run 1, run 2 | [docs/evidence/](docs/evidence/) |
| Source version, checksums, selection rule, row counts | [docs/source_manifest.json](docs/source_manifest.json) |
| Credentials from environment variables only | [.env.example](.env.example) (names only); `.env` is git-ignored |

## Data source and attribution

The data is the **Brazilian E-Commerce Public Dataset by Olist**, published on
[Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) under
**CC BY-NC-SA 4.0**; all credit for it goes to Olist. We don't redistribute it:
`scripts/download_olist.sh` downloads the archive, checks its SHA-256 and unpacks the files
we use into the git-ignored `data/` folder. The tests use a small made-up dataset instead.

| | Value |
|---|---|
| Archive | `brazilian-ecommerce.zip`, 44,717,580 bytes, dated 2021-10-01, SHA-256 `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784` |
| In scope | orders, customers, order items, products, sellers, plus the category translation (same archive) |
| Out of scope (for now) | reviews, payments, geolocation |
| Columns left out | three product listing fields: `product_name_lenght`, `product_description_lenght`, `product_photos_qty` (see the design note) |
| Selection rule | an order is kept when the first 8 hex digits of `sha256(order_id)`, read as a number, are divisible by 10; its items and every customer, product, category and seller it references come with it |

| Source file | Rows in file | Rows in subset | Loaded into |
|---|---:|---:|---|
| olist_orders_dataset.csv | 99,441 | 9,901 | `orders` (9,901) |
| olist_customers_dataset.csv | 99,441 | 9,901 | `order_customers` (9,901), `customers` (9,866 people) |
| olist_order_items_dataset.csv | 112,650 | 11,242 | `order_items` (11,242), `order_lines` (10,231), `order_sellers` (9,997) |
| olist_products_dataset.csv | 32,951 | 6,619 | `products` (6,619) |
| olist_sellers_dataset.csv | 3,095 | 1,617 | `sellers` (1,617) |
| product_category_name_translation.csv | 71 | 69 | `product_categories` (71; 2 have no English name) |

## Run it

You need Docker with Compose v2 and [uv](https://docs.astral.sh/uv/). `psql` is optional.

```bash
uv sync                                  # Python environment, versions pinned in uv.lock
cp .env.example .env                     # fill in values, e.g. PGHOST=localhost PGPORT=5432
                                         # PGDATABASE=olist PGUSER=olist PGPASSWORD=<choose> PGSSLMODE=disable
docker compose up -d                     # local PostgreSQL, reads its credentials from .env
scripts/download_olist.sh                # ~43 MB download, SHA-256 checked, 6 CSVs extracted

uv run olist-db init                     # schema.sql on the empty database
# (equivalent: psql -v ON_ERROR_STOP=1 --single-transaction -f sql/schema.sql)

# 1) Check a small slice first, in a throwaway database
PGDATABASE=olist_slice uv run olist-db init --create-database
PGDATABASE=olist_slice uv run olist-ingest --max-orders 200 | tee docs/evidence/ingest_slice.txt
PGDATABASE=olist_slice uv run olist-verify --label slice --out docs/evidence

# 2) Full subset, run twice, saving evidence after each run
uv run olist-ingest | tee docs/evidence/ingest_run1.txt
uv run olist-verify --label run1 --out docs/evidence
uv run olist-ingest | tee docs/evidence/ingest_run2.txt
uv run olist-verify --label run2 --out docs/evidence --compare run1   # fails if any data changed

# Tests (DDL and ingestion, each test on a fresh database) and SQL lint
uv run pytest
uv run sqlfluff lint sql/
```

**Other useful commands:**
- `uv run olist-ingest --dry-run` validates and reports without writing anything.
- `uv run olist-db reset --yes` drops and rebuilds both schemas, deleting the loaded data.
- **Neon or any hosted PostgreSQL:** put the connection string in `DATABASE_URL` in `.env`;
  it takes precedence over the `PG*` variables, and the same commands work.

## Evidence summary

Full reports: [run 1](docs/evidence/verify_run1.md), [run 2](docs/evidence/verify_run2.md),
[slice](docs/evidence/verify_slice.md). Raw ingestion output is in `docs/evidence/ingest_*.txt`.

| Run | Scope | Inserted | Updated | Unchanged | Checks |
|---|---|---:|---:|---:|---|
| slice | 200 orders, throwaway database | 1,620 | 0 | 0 | 49 pass, 3 warn, 0 fail |
| run 1 | full subset, empty schema | 69,445 | 0 | 0 | 43 pass, 9 warn, 0 fail |
| run 2 | full subset, same input | 0 | 0 | 69,445 | 43 pass, 9 warn, 0 fail; all 9 table fingerprints and 4 totals identical to run 1 |

What the checks cover:
- **Counts and totals:** every table's row count matches what the run validated, and item
  prices (R$ 1,329,141.86) and freight (R$ 224,877.74) match the source to the cent.
- **Keys and references:** no duplicate keys or orphaned foreign keys, exactly one customer
  record per order, the minimum cardinalities from the ERD, and a closed subset (everything
  referenced is loaded, and everything loaded is referenced).
- **Subset rule:** recomputed in SQL; every loaded order satisfies it.
- **Business rules:** items numbered 1..n within each order, and shipping deadlines after
  purchase.
- **Change detection:** an md5 fingerprint of every table, because row counts alone can miss
  an updated value.

**Data quality:** no rows were rejected. Three seller city names were corrected (an extra
space, a `´` used as an apostrophe, and an email address typed into the city field, now
NULL), and each correction is logged in `ingest.data_issues` with its original value. The 9
warnings are quirks in the source that we keep and report rather than quietly fix, such as
125 orders handed to the carrier before they were approved and 12 zip prefixes that appear
with two states. The database uses 17 MB of the 300 MB budget.

## Repository layout

```
sql/schema.sql            DDL: schemas olist (3NF source) and ingest (audit)
sql/verify.sql            verification queries (plain SQL, also runnable with psql)
src/olist_pipeline/       config, source (checksums), subset rule, validate, load (upsert), ingest, verify, db CLIs
scripts/download_olist.sh download + checksum + extract
tests/                    DDL tests and ingestion tests on a synthetic fixture
docs/                     ERD, design note, source manifest, evidence
docker-compose.yml        local PostgreSQL;  .env.example: variable names only
```

## Tested versions

Python 3.13.9 · pandas 3.1.1 · SQLAlchemy 2.1.8 · psycopg 3.3.9 · python-dotenv 1.2.4 ·
pytest 9.2.0 · SQLFluff 4.5.0 · PostgreSQL 16.12 (`postgres:16-alpine`) · Docker Compose
2.39.2 · uv 0.13.0. `uv.lock` pins the full dependency set. The schema uses nothing newer
than PostgreSQL 14, so it also runs on Neon's PostgreSQL 16 or 17.
