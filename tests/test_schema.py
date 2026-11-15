"""DDL tests: schema.sql builds from an empty database, accepts a valid order graph and the
documented valid exceptions, and rejects data that breaks the documented design."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import hex_id

PERSON, CUST, CUST2 = hex_id("person"), hex_id("cust"), hex_id("cust2")
SELLER, SELLER2 = hex_id("seller"), hex_id("seller2")
PROD, PROD2 = hex_id("product"), hex_id("product2")
ORDER, ORDER2 = hex_id("order"), hex_id("order2")

BASE_GRAPH = f"""
INSERT INTO olist.customers VALUES ('{PERSON}');
INSERT INTO olist.order_customers VALUES ('{CUST}', '{PERSON}', '01310', 'sao paulo', 'SP');
INSERT INTO olist.order_customers VALUES ('{CUST2}', '{PERSON}', '04571', 'sao paulo', 'SP');
INSERT INTO olist.sellers VALUES ('{SELLER}', '13023', 'campinas', 'SP');
INSERT INTO olist.sellers VALUES ('{SELLER2}', '88015', 'florianopolis', 'SC');
INSERT INTO olist.product_categories VALUES ('perfumaria', 'perfumery');
INSERT INTO olist.products VALUES ('{PROD}', 'perfumaria', 225, 16, 10, 14);
INSERT INTO olist.products VALUES ('{PROD2}', 'perfumaria', 300, 20, 10, 10);
INSERT INTO olist.orders VALUES ('{ORDER}', '{CUST}', 'delivered', '2017-10-02 10:56:33',
    '2017-10-02 11:07:15', '2017-10-04 19:55:00', '2017-10-10 21:25:13', '2017-10-18');
INSERT INTO olist.order_sellers VALUES ('{ORDER}', '{SELLER}', '2017-10-06 11:07:15');
INSERT INTO olist.order_lines VALUES ('{ORDER}', '{PROD}', '{SELLER}', 29.99, 8.72);
INSERT INTO olist.order_items VALUES ('{ORDER}', 1, '{PROD}'), ('{ORDER}', 2, '{PROD}');
"""

OLIST_TABLES = {"customers", "order_customers", "sellers", "product_categories", "products",
                "orders", "order_sellers", "order_lines", "order_items"}
INGEST_TABLES = {"runs", "source_files", "table_loads", "run_measures", "data_issues"}


def run_sql(engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execution_options(no_parameters=True).exec_driver_sql(sql)


def test_schema_builds_expected_tables(fresh_db):
    with fresh_db.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('olist', 'ingest') AND table_type = 'BASE TABLE'")).all()
    assert {t for s, t in rows if s == "olist"} == OLIST_TABLES
    assert {t for s, t in rows if s == "ingest"} == INGEST_TABLES


def test_valid_order_graph_loads(fresh_db):
    run_sql(fresh_db, BASE_GRAPH)
    with fresh_db.connect() as conn:
        units = conn.execute(text("SELECT count(*) FROM olist.order_items")).scalar_one()
    assert units == 2


VALID_EXCEPTIONS = {
    "order without items (canceled before fulfilment)": f"""
        INSERT INTO olist.orders VALUES ('{ORDER2}', '{CUST2}', 'canceled',
            '2017-10-03 09:00:00', NULL, NULL, NULL, '2017-10-20')""",
    "product without category or measurements": f"""
        INSERT INTO olist.products VALUES ('{hex_id("bare")}', NULL, NULL, NULL, NULL, NULL)""",
    "product weighing 0 g (flagged, not rejected)": f"""
        UPDATE olist.products SET product_weight_g = 0 WHERE product_id = '{PROD}'""",
    "category without English translation": """
        INSERT INTO olist.product_categories VALUES ('pc_gamer', NULL)""",
    "seller city unknown": f"""
        UPDATE olist.sellers SET seller_city = NULL WHERE seller_id = '{SELLER}'""",
    "free shipping (freight 0)": f"""
        UPDATE olist.order_lines SET item_freight_value = 0 WHERE order_id = '{ORDER}'""",
    "carrier pickup recorded before approval (source anomaly kept)": f"""
        UPDATE olist.orders SET order_delivered_carrier_date = '2017-10-02 11:00:00'
        WHERE order_id = '{ORDER}'""",
}


@pytest.mark.parametrize("sql", VALID_EXCEPTIONS.values(), ids=VALID_EXCEPTIONS.keys())
def test_documented_valid_exceptions_are_allowed(fresh_db, sql):
    run_sql(fresh_db, BASE_GRAPH + ";\n" + sql)


VIOLATIONS = {
    # domains / CHECK constraints (SQLSTATE 23514)
    "malformed identifier": ("INSERT INTO olist.customers VALUES ('NOT-A-HEX-ID')", "23514"),
    "zip prefix with 4 digits": (
        f"UPDATE olist.sellers SET seller_zip_code_prefix = '1302' WHERE seller_id = '{SELLER}'", "23514"),
    "unknown state code": (
        f"UPDATE olist.sellers SET seller_state = 'XX' WHERE seller_id = '{SELLER}'", "23514"),
    "city not normalized": (
        f"UPDATE olist.sellers SET seller_city = ' Campinas' WHERE seller_id = '{SELLER}'", "23514"),
    "unknown order status": (
        f"UPDATE olist.orders SET order_status = 'lost' WHERE order_id = '{ORDER}'", "23514"),
    "approval before purchase": (
        f"UPDATE olist.orders SET order_approved_at = '2017-10-01' WHERE order_id = '{ORDER}'", "23514"),
    "delivery before purchase": (
        f"UPDATE olist.orders SET order_delivered_customer_date = '2017-09-30' "
        f"WHERE order_id = '{ORDER}'", "23514"),
    "estimate before purchase day": (
        f"UPDATE olist.orders SET order_estimated_delivery_date = '2017-10-01' "
        f"WHERE order_id = '{ORDER}'", "23514"),
    "zero price": (
        f"UPDATE olist.order_lines SET item_price = 0 WHERE order_id = '{ORDER}'", "23514"),
    "negative freight": (
        f"UPDATE olist.order_lines SET item_freight_value = -1 WHERE order_id = '{ORDER}'", "23514"),
    "item number 0": (f"INSERT INTO olist.order_items VALUES ('{ORDER}', 0, '{PROD}')", "23514"),
    "zero product length": (
        f"UPDATE olist.products SET product_length_cm = 0 WHERE product_id = '{PROD}'", "23514"),
    "negative weight": (
        f"UPDATE olist.products SET product_weight_g = -1 WHERE product_id = '{PROD}'", "23514"),
    "load counts that do not add up": (
        "INSERT INTO ingest.runs (subset_rule) VALUES ('t');"
        "INSERT INTO ingest.table_loads VALUES (1, 'orders', 10, 5, 0, 0)", "23514"),
    # keys and UNIQUE (23505)
    "second order reusing a customer_id (1:1)": (
        f"INSERT INTO olist.orders VALUES ('{ORDER2}', '{CUST}', 'created', '2017-10-03 09:00:00', "
        "NULL, NULL, NULL, '2017-10-20')", "23505"),
    "duplicate order item key": (f"INSERT INTO olist.order_items VALUES ('{ORDER}', 1, '{PROD}')", "23505"),
    "duplicate English category name": (
        "INSERT INTO olist.product_categories VALUES ('perfumes', 'perfumery')", "23505"),
    # foreign keys (23503)
    "order for an unknown customer record": (
        f"INSERT INTO olist.orders VALUES ('{ORDER2}', '{hex_id('ghost')}', 'created', "
        "'2017-10-03 09:00:00', NULL, NULL, NULL, '2017-10-20')", "23503"),
    "line whose seller is not part of the order": (
        f"INSERT INTO olist.order_lines VALUES ('{ORDER}', '{PROD2}', '{SELLER2}', 10.00, 1.00)", "23503"),
    "unit whose product is not a line of the order": (
        f"INSERT INTO olist.order_items VALUES ('{ORDER}', 3, '{PROD2}')", "23503"),
    "product in an unknown category": (
        f"UPDATE olist.products SET product_category_name = 'nope' WHERE product_id = '{PROD}'", "23503"),
    # NOT NULL (23502)
    "missing zip prefix": (
        f"UPDATE olist.order_customers SET customer_zip_code_prefix = NULL WHERE customer_id = '{CUST}'",
        "23502"),
    "missing purchase timestamp": (
        f"UPDATE olist.orders SET order_purchase_timestamp = NULL WHERE order_id = '{ORDER}'", "23502"),
}


@pytest.mark.parametrize(("sql", "sqlstate"), VIOLATIONS.values(), ids=VIOLATIONS.keys())
def test_constraints_reject_invalid_data(fresh_db, sql, sqlstate):
    with pytest.raises(DBAPIError) as caught:
        run_sql(fresh_db, BASE_GRAPH + ";\n" + sql)
    assert caught.value.orig.sqlstate == sqlstate


def test_schema_sql_requires_an_empty_database(fresh_db):
    from olist_pipeline.db import apply_schema

    with pytest.raises(DBAPIError):
        apply_schema(fresh_db)
