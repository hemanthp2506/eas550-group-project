"""Ingestion tests on a tiny synthetic fixture (made-up identifiers, no Olist data), so they
can run anywhere, including public CI.

Covers: the subset rule and parent closure, rejections and corrections with counts, rerun
safety (second run changes nothing), change detection (an updated price is updated in place,
not duplicated), the FD guard behind the 3NF decomposition, and the verification checks.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import text

from conftest import hex_id
from olist_pipeline.config import VERIFY_SQL
from olist_pipeline.ingest import run_ingest
from olist_pipeline.source import SOURCE_FILES
from olist_pipeline.subset import bucket
from olist_pipeline.verify import evaluate, parse_blocks, run_blocks, snapshot

HEADERS = {
    "customers": ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                  "customer_city", "customer_state"],
    "orders": ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
               "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["order_id", "order_item_id", "product_id", "seller_id",
                    "shipping_limit_date", "price", "freight_value"],
    "products": ["product_id", "product_category_name", "product_name_lenght",
                 "product_description_lenght", "product_photos_qty", "product_weight_g",
                 "product_length_cm", "product_height_cm", "product_width_cm"],
    "sellers": ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    "category_translation": ["product_category_name", "product_category_name_english"],
}


def subset_id(label: str, inside: bool = True) -> str:
    """A synthetic order_id that the sha256 subset rule selects (or, if inside=False, skips)."""
    for i in range(10_000):
        candidate = hex_id(f"{label}-{i}")
        if (bucket(candidate) == 0) == inside:
            return candidate
    raise AssertionError("no candidate id found")


O_A, O_B, O_C = subset_id("order-a"), subset_id("order-b"), subset_id("order-c")
O_OUT = subset_id("order-out", inside=False)
C_A, C_B, C_C, C_OUT = (hex_id(f"cust-{x}") for x in "abco")
PERSON, PERSON2 = hex_id("person-1"), hex_id("person-2")
S1, S2 = hex_id("seller-1"), hex_id("seller-2")
P1, P2, P3 = hex_id("product-1"), hex_id("product-2"), hex_id("product-3")
TS = "2018-03-01 10:00:00"


def fixture_rows() -> dict[str, list[list[str]]]:
    return {
        "customers": [
            [C_A, PERSON, "1310", " São  Paulo", "sp"],  # zip padded, city cleaned, state upper
            [C_B, PERSON, "04571", "sao paulo", "SP"],     # same person, second order
            [C_C, PERSON2, "20040", "rio de janeiro", "RJ"],
            [C_OUT, PERSON2, "20040", "rio de janeiro", "RJ"],
        ],
        "orders": [
            [O_A, C_A, "delivered", TS, "2018-03-01 10:30:00", "2018-03-02 09:00:00",
             "2018-03-06 15:00:00", "2018-03-15 00:00:00"],
            [O_B, C_B, "canceled", TS, "", "", "", "2018-03-20 00:00:00"],  # no items: valid
            [O_C, C_C, "lost", TS, "", "", "", "2018-03-20 00:00:00"],      # invalid status
            [O_OUT, C_OUT, "delivered", TS, "", "", "", "2018-03-20 00:00:00"],  # not in subset
        ],
        "order_items": [
            [O_A, "1", P1, S1, "2018-03-05 10:30:00", "29.99", "8.72"],
            [O_A, "2", P1, S1, "2018-03-05 10:30:00", "29.99", "8.72"],  # quantity 2 of P1
            [O_A, "3", P3, S2, "2018-03-06 10:30:00", "10.00", "0.00"],  # second seller, free freight
            [O_A, "3", P3, S2, "2018-03-06 10:30:00", "10.00", "0.00"],  # exact duplicate row
            [O_C, "1", P2, S1, "2018-03-05 10:30:00", "50.00", "5.00"],  # parent order rejected
            [O_OUT, "1", P1, S1, "2018-03-05 10:30:00", "29.99", "8.72"],
        ],
        "products": [
            [P1, "perfumaria", "40", "287", "1", "225", "16", "10", "14"],
            [P2, "", "", "", "", "", "", "", ""],  # uncategorized: valid NULLs
            [P3, "perfumaria", "40", "287", "1", "-5", "10", "10", "10"],  # bad weight -> NULL
        ],
        "sellers": [
            [S1, "13023", "campinas", "SP"],
            [S2, "88015", "vendas@example.com", "SC"],  # not a city -> NULL
        ],
        "category_translation": [["perfumaria", "perfumery"]],
    }


def write_fixture(folder: Path, rows: dict[str, list[list[str]]]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for key, name in SOURCE_FILES.items():
        with (folder / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADERS[key])
            writer.writerows(rows[key])
    return folder


def ingest(engine, folder: Path):
    return run_ingest(engine, folder, manifest=None)


def counts(engine) -> dict[str, int]:
    tables = ["customers", "order_customers", "sellers", "product_categories", "products",
              "orders", "order_sellers", "order_lines", "order_items"]
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM olist.{t}")).scalar_one()
                for t in tables}


def test_subset_closure_rejections_and_corrections(fresh_db, tmp_path):
    result = ingest(fresh_db, write_fixture(tmp_path, fixture_rows()))

    assert counts(fresh_db) == {
        "customers": 1, "order_customers": 2, "sellers": 2, "product_categories": 1,
        "products": 2, "orders": 2, "order_sellers": 2, "order_lines": 2, "order_items": 3,
    }
    stats = {k: (s.rows_in_subset, s.rows_rejected, s.rows_corrected)
             for k, s in result.subset.file_stats.items()}
    assert stats == {
        "customers": (3, 1, 1),        # C_C dropped with its rejected order; C_A corrected
        "orders": (3, 1, 0),           # O_C invalid status; O_OUT never selected
        "order_items": (5, 2, 0),      # exact duplicate + item of the rejected order
        "products": (3, 1, 1),         # P2 only belonged to the rejected order; P3 weight
        "sellers": (2, 0, 1),          # S2 city was an e-mail address
        "category_translation": (1, 0, 0),
    }
    rules = {(i.source_file.split("_dataset")[0], i.rule, i.action) for i in result.subset.issues}
    assert {
        ("olist_orders", "invalid_order_status", "rejected"),
        ("olist_order_items", "exact_duplicate", "rejected"),
        ("olist_order_items", "dependent_on_rejected_row", "rejected"),
        ("olist_customers", "zip_prefix_zero_padded", "corrected"),
        ("olist_customers", "city_ascii_folded", "corrected"),
        ("olist_customers", "state_normalized", "corrected"),
        ("olist_sellers", "city_not_a_place_set_null", "corrected"),
        ("olist_products", "invalid_measurement_set_null", "corrected"),
    } <= rules

    with fresh_db.connect() as conn:
        city, state, zip_prefix = conn.execute(text(
            "SELECT customer_city, customer_state, customer_zip_code_prefix "
            "FROM olist.order_customers WHERE customer_id = :c"), {"c": C_A}).one()
        logged = conn.execute(text("SELECT count(*) FROM ingest.data_issues")).scalar_one()
    assert (city, state, zip_prefix) == ("sao paulo", "SP", "01310")
    assert logged == len(result.subset.issues)


def test_rerun_with_unchanged_input_changes_nothing(fresh_db, tmp_path):
    folder = write_fixture(tmp_path, fixture_rows())
    ingest(fresh_db, folder)
    blocks = parse_blocks(VERIFY_SQL.read_text())
    before = snapshot(run_blocks(fresh_db, parse_blocks(VERIFY_SQL.read_text())))

    second = ingest(fresh_db, folder)

    assert all(c.inserted == 0 and c.updated == 0 and c.unchanged == c.loaded
               for c in second.loads.values())
    after_blocks = run_blocks(fresh_db, blocks)
    assert snapshot(after_blocks) == before
    assert [c for c in evaluate(after_blocks) if c["status"] == "FAIL"] == []


def test_changed_value_is_updated_in_place_not_duplicated(fresh_db, tmp_path):
    rows = fixture_rows()
    ingest(fresh_db, write_fixture(tmp_path / "v1", rows))
    before = snapshot(run_blocks(fresh_db, parse_blocks(VERIFY_SQL.read_text())))

    for item in rows["order_items"]:
        if item[0] == O_A and item[2] == P1:
            item[5] = "31.50"  # price correction on both units of the line
    third = ingest(fresh_db, write_fixture(tmp_path / "v2", rows))

    assert third.loads["order_lines"].updated == 1
    assert sum(c.inserted for c in third.loads.values()) == 0
    after = snapshot(run_blocks(fresh_db, parse_blocks(VERIFY_SQL.read_text())))
    lines_before, lines_after = before["fingerprints"]["order_lines"], after["fingerprints"]["order_lines"]
    assert lines_after["rows"] == lines_before["rows"]   # row counts alone miss the change ...
    assert lines_after["md5"] != lines_before["md5"]     # ... the content fingerprint does not
    assert after["measures"]["total_item_price"] != before["measures"]["total_item_price"]


def test_order_breaking_the_decomposition_fds_is_rejected_whole(fresh_db, tmp_path):
    rows = fixture_rows()
    rows["order_items"][1][5] = "28.00"  # same product, same order, different unit price
    result = ingest(fresh_db, write_fixture(tmp_path, rows))

    rules = {i.rule for i in result.subset.issues if i.record_key == O_A}
    assert "fd_violation_order_product_price_seller" in rules
    with fresh_db.connect() as conn:
        left = conn.execute(text("SELECT count(*) FROM olist.order_items WHERE order_id = :o"),
                            {"o": O_A}).scalar_one()
    assert left == 0


def test_dry_run_writes_nothing(fresh_db, tmp_path):
    result = run_ingest(fresh_db, write_fixture(tmp_path, fixture_rows()), manifest=None,
                        dry_run=True)
    assert result.run_id is None
    assert sum(counts(fresh_db).values()) == 0
    with fresh_db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ingest.runs")).scalar_one() == 0


@pytest.mark.parametrize("bad_price", ["0", "-3.00", "12.345", "abc"])
def test_invalid_price_rejects_the_whole_order(fresh_db, tmp_path, bad_price):
    rows = fixture_rows()
    rows["order_items"][2][5] = bad_price
    result = ingest(fresh_db, write_fixture(tmp_path, rows))
    with fresh_db.connect() as conn:
        orders = conn.execute(text("SELECT order_id FROM olist.orders")).scalars().all()
    assert orders == [O_B]  # O_A would be incomplete without item 3, so it is not loaded
    assert any(i.rule == "invalid_price" for i in result.subset.issues)
