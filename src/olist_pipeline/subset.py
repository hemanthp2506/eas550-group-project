"""The documented, reproducible subset rule.

An order is in the subset when the first 8 hex digits of sha256(order_id), read as an
unsigned integer, are congruent to 0 modulo 10. The rule

* does not depend on file order or on a random seed, so any copy of the source gives the
  same subset;
* is spread evenly over time and order status (the hash is unrelated to both), so monthly
  and per-category analysis is not biased toward one period;
* can be re-checked inside PostgreSQL with sha256() (see sql/verify.sql).

All items of a selected order are kept, plus every customer, product (with its category)
and seller that those rows reference, so parent rows are never lost.
"""

from __future__ import annotations

import hashlib

import pandas as pd

DEFAULT_MODULUS = 10
SUBSET_BUCKET = 0


def bucket(order_id: str, modulus: int = DEFAULT_MODULUS) -> int:
    return int(hashlib.sha256(order_id.encode("utf-8")).hexdigest()[:8], 16) % modulus


def describe_rule(modulus: int = DEFAULT_MODULUS, max_orders: int | None = None) -> str:
    rule = (
        f"orders where int(first 8 hex digits of sha256(order_id))"
        f" mod {modulus} = {SUBSET_BUCKET}"
    )
    if max_orders:
        rule += f"; slice: first {max_orders} of those by order_id"
    return rule + "; plus all their items and the customers, products, categories and sellers they reference"


def select_orders(orders: pd.DataFrame, modulus: int = DEFAULT_MODULUS,
                  max_orders: int | None = None) -> pd.DataFrame:
    """Apply the rule to the raw order_id text (before validation)."""
    mask = orders["order_id"].map(lambda oid: bucket(oid, modulus) == SUBSET_BUCKET)
    selected = orders[mask]
    if max_orders:
        selected = selected.sort_values("order_id", kind="stable").head(max_orders)
    return selected
