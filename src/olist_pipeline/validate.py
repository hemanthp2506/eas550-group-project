"""Validate and normalize the subset before anything touches the database.

Every row that is not loaded is recorded as ``rejected`` and every value that is changed is
recorded as ``corrected`` (with the original value), so the counts in the run log can be
explained row by row. Parents are validated before their dependents, and a dependent row
whose parent was rejected is rejected too, so a partial order is never loaded.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from .source import ROW, SourceFile
from .subset import DEFAULT_MODULUS, select_orders

HEX_ID = re.compile(r"[0-9a-f]{32}")
ZIP_PREFIX = re.compile(r"[0-9]{5}")
SHORT_DIGITS = re.compile(r"[0-9]{1,4}")
CATEGORY_KEY = re.compile(r"[a-z0-9_]+")
WHOLE_NUMBER = re.compile(r"[0-9]+")
MONEY = re.compile(r"[0-9]{1,8}(\.[0-9]{1,2})?")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

STATES = frozenset(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)
ORDER_STATUSES = frozenset(
    "created approved invoiced processing shipped delivered canceled unavailable".split()
)
SMALLINT_MAX = 32767

# Target tables in parent-before-child load order, with their primary keys.
LOAD_ORDER: list[tuple[str, list[str]]] = [
    ("customers", ["customer_unique_id"]),
    ("order_customers", ["customer_id"]),
    ("sellers", ["seller_id"]),
    ("product_categories", ["product_category_name"]),
    ("products", ["product_id"]),
    ("orders", ["order_id"]),
    ("order_sellers", ["order_id", "seller_id"]),
    ("order_lines", ["order_id", "product_id"]),
    ("order_items", ["order_id", "order_item_id"]),
]


# ----------------------------------------------------------------------------- issue log

@dataclass
class Issue:
    source_file: str
    source_row: int
    record_key: str
    rule: str
    action: str  # "rejected" (row not loaded) or "corrected" (row loaded with a changed value)
    detail: dict = field(default_factory=dict)


class IssueLog:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def reject(self, source: str, row: int, key: str, rule: str, **detail) -> None:
        self.issues.append(Issue(source, int(row), key, rule, "rejected", detail))

    def correct(self, source: str, row: int, key: str, rule: str, **detail) -> None:
        self.issues.append(Issue(source, int(row), key, rule, "corrected", detail))

    def rows(self, source: str, action: str) -> set[int]:
        return {i.source_row for i in self.issues if i.source_file == source and i.action == action}


# ----------------------------------------------------------------------------- value helpers

def parse_timestamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, TIMESTAMP_FORMAT)
    except ValueError:
        return None


def parse_money(text: str) -> Decimal | None:
    if not MONEY.fullmatch(text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:  # pragma: no cover - the regex already guarantees a number
        return None


def ascii_fold(text: str) -> str:
    """Remove diacritics and use a plain apostrophe, matching how most source cities are spelled."""
    text = text.replace("´", "'").replace("’", "'").replace("`", "'")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def clean_city(raw: str) -> tuple[str | None, list[tuple[str, dict]]]:
    """Return the cleaned city plus the corrections applied (rule, detail)."""
    fixes: list[tuple[str, dict]] = []
    value = " ".join(raw.split())
    if value != raw:
        fixes.append(("city_whitespace_normalized", {"original": raw}))
    lowered = value.lower()
    if lowered != value:
        fixes.append(("city_lowercased", {"original": value}))
    folded = ascii_fold(lowered)
    if folded != lowered:
        fixes.append(("city_ascii_folded", {"original": lowered}))
    if not folded:
        return None, fixes
    if "@" in folded or not any(ch.isalpha() for ch in folded):
        fixes.append(("city_not_a_place_set_null", {"original": raw}))
        return None, fixes
    return folded, fixes


# ----------------------------------------------------------------------------- result

@dataclass
class FileStats:
    file_name: str
    sha256: str
    size_bytes: int
    rows_read: int
    rows_in_subset: int
    rows_rejected: int = 0
    rows_corrected: int = 0


@dataclass
class ValidatedSubset:
    frames: dict[str, pd.DataFrame]
    file_stats: dict[str, FileStats]
    issues: list[Issue]
    measures: dict[str, Decimal]


# ----------------------------------------------------------------------------- validator

class SubsetValidator:
    def __init__(self, sources: dict[str, SourceFile], modulus: int = DEFAULT_MODULUS,
                 max_orders: int | None = None) -> None:
        self.sources = sources
        self.modulus = modulus
        self.max_orders = max_orders
        self.log = IssueLog()
        self.names = {key: src.name for key, src in sources.items()}

    # -- shared field checks ------------------------------------------------------------
    def _hex(self, src: str, rec: dict, column: str, key: str) -> str | None:
        value = rec[column]
        if not HEX_ID.fullmatch(value):
            self.log.reject(self.names[src], rec[ROW], key, f"invalid_{column}", value=value)
            return None
        return value

    def _zip(self, src: str, rec: dict, column: str, key: str) -> str | None:
        value = rec[column].strip()
        if SHORT_DIGITS.fullmatch(value):  # leading zeros lost upstream, e.g. 1151 -> 01151
            padded = value.zfill(5)
            self.log.correct(self.names[src], rec[ROW], key, "zip_prefix_zero_padded",
                             original=rec[column], corrected=padded)
            value = padded
        if not ZIP_PREFIX.fullmatch(value):
            self.log.reject(self.names[src], rec[ROW], key, "invalid_zip_prefix", value=rec[column])
            return None
        return value

    def _state(self, src: str, rec: dict, column: str, key: str) -> str | None:
        value = rec[column].strip().upper()
        if value not in STATES:
            self.log.reject(self.names[src], rec[ROW], key, "invalid_state", value=rec[column])
            return None
        if value != rec[column]:
            self.log.correct(self.names[src], rec[ROW], key, "state_normalized",
                             original=rec[column], corrected=value)
        return value

    def _city(self, src: str, rec: dict, column: str, key: str) -> str | None:
        value, fixes = clean_city(rec[column])
        for rule, detail in fixes:
            self.log.correct(self.names[src], rec[ROW], key, rule, column=column, **detail)
        return value

    def _dedupe(self, src: str, records: list[dict], key_columns: list[str]) -> list[dict]:
        """Keep one copy of exact duplicates; reject every copy of a key with conflicting values."""
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for rec in records:
            groups[tuple(rec[c] for c in key_columns)].append(rec)
        kept = []
        for key, recs in groups.items():
            if len(recs) == 1:
                kept.append(recs[0])
                continue
            label = "|".join(map(str, key))
            payloads = {tuple((k, v) for k, v in r.items() if k != ROW) for r in recs}
            if len(payloads) == 1:
                kept.append(recs[0])
                for dup in recs[1:]:
                    self.log.reject(self.names[src], dup[ROW], label, "exact_duplicate",
                                    duplicate_of_row=recs[0][ROW])
            else:
                for rec in recs:
                    self.log.reject(self.names[src], rec[ROW], label, "conflicting_duplicate_key",
                                    rows=[r[ROW] for r in recs])
        return kept

    # -- per-source validation ----------------------------------------------------------
    def _orders(self, frame: pd.DataFrame) -> dict[str, dict]:
        src, out = "orders", []
        for rec in frame.to_dict("records"):
            key = rec["order_id"]
            order_id = self._hex(src, rec, "order_id", key)
            customer_id = order_id and self._hex(src, rec, "customer_id", key)
            if not customer_id:
                continue
            status = rec["order_status"].strip().lower()
            if status not in ORDER_STATUSES:
                self.log.reject(self.names[src], rec[ROW], key, "invalid_order_status",
                                value=rec["order_status"])
                continue
            purchased = parse_timestamp(rec["order_purchase_timestamp"])
            if purchased is None:
                self.log.reject(self.names[src], rec[ROW], key, "invalid_purchase_timestamp",
                                value=rec["order_purchase_timestamp"])
                continue
            optional = {}
            for column in ("order_approved_at", "order_delivered_carrier_date",
                           "order_delivered_customer_date"):
                text = rec[column].strip()
                optional[column] = parse_timestamp(text) if text else None
                if text and optional[column] is None:
                    self.log.correct(self.names[src], rec[ROW], key, "unparseable_timestamp_set_null",
                                     column=column, original=rec[column])
            estimated = parse_timestamp(rec["order_estimated_delivery_date"])
            if estimated is None:
                self.log.reject(self.names[src], rec[ROW], key, "invalid_estimated_delivery_date",
                                value=rec["order_estimated_delivery_date"])
                continue
            if estimated.time() != datetime.min.time():
                self.log.correct(self.names[src], rec[ROW], key, "estimated_delivery_time_dropped",
                                 original=rec["order_estimated_delivery_date"])
            # Rules the schema enforces with CHECK constraints: reject rather than load half an order.
            approved = optional["order_approved_at"]
            delivered = optional["order_delivered_customer_date"]
            broken = [name for name, bad in (
                ("approved_before_purchase", approved is not None and approved < purchased),
                ("delivered_before_purchase", delivered is not None and delivered < purchased),
                ("estimate_before_purchase", estimated.date() < purchased.date()),
            ) if bad]
            if broken:
                self.log.reject(self.names[src], rec[ROW], key, broken[0])
                continue
            out.append({
                ROW: rec[ROW], "order_id": order_id, "customer_id": customer_id,
                "order_status": status, "order_purchase_timestamp": purchased, **optional,
                "order_estimated_delivery_date": estimated.date(),
            })
        out = self._dedupe(src, out, ["order_id"])
        # customer_id identifies the customer record of ONE order (1:1); reject any reuse.
        by_customer = defaultdict(list)
        for rec in out:
            by_customer[rec["customer_id"]].append(rec)
        valid = {}
        for customer_id, recs in by_customer.items():
            if len(recs) > 1:
                for rec in recs:
                    self.log.reject(self.names[src], rec[ROW], rec["order_id"],
                                    "customer_id_shared_by_orders", customer_id=customer_id)
            else:
                valid[recs[0]["order_id"]] = recs[0]
        return valid

    def _address_entity(self, src: str, frame: pd.DataFrame, id_column: str, prefix: str,
                        extra_ids: tuple[str, ...] = ()) -> dict[str, dict]:
        out = []
        for rec in frame.to_dict("records"):
            key = rec[id_column]
            ident = self._hex(src, rec, id_column, key)
            extras = {c: self._hex(src, rec, c, key) for c in extra_ids} if ident else {}
            if not ident or not all(extras.values()):
                continue
            zip_prefix = self._zip(src, rec, f"{prefix}_zip_code_prefix", key)
            state = zip_prefix and self._state(src, rec, f"{prefix}_state", key)
            if not state:
                continue
            out.append({
                ROW: rec[ROW], id_column: ident, **extras,
                f"{prefix}_zip_code_prefix": zip_prefix,
                f"{prefix}_city": self._city(src, rec, f"{prefix}_city", key),
                f"{prefix}_state": state,
            })
        return {rec[id_column]: rec for rec in self._dedupe(src, out, [id_column])}

    def _items(self, frame: pd.DataFrame) -> list[dict]:
        src, out = "order_items", []
        for rec in frame.to_dict("records"):
            key = f"{rec['order_id']}|{rec['order_item_id']}"
            if not WHOLE_NUMBER.fullmatch(rec["order_item_id"]) or not (
                1 <= int(rec["order_item_id"]) <= SMALLINT_MAX
            ):
                self.log.reject(self.names[src], rec[ROW], key, "invalid_order_item_id",
                                value=rec["order_item_id"])
                continue
            product_id = self._hex(src, rec, "product_id", key)
            seller_id = product_id and self._hex(src, rec, "seller_id", key)
            if not seller_id:
                continue
            limit = parse_timestamp(rec["shipping_limit_date"])
            price = parse_money(rec["price"])
            freight = parse_money(rec["freight_value"])
            problem = (
                "invalid_shipping_limit_date" if limit is None else
                "invalid_price" if price is None or price <= 0 else
                "invalid_freight_value" if freight is None else None
            )
            if problem:
                self.log.reject(self.names[src], rec[ROW], key, problem,
                                shipping_limit_date=rec["shipping_limit_date"],
                                price=rec["price"], freight_value=rec["freight_value"])
                continue
            out.append({
                ROW: rec[ROW], "order_id": rec["order_id"],
                "order_item_id": int(rec["order_item_id"]), "product_id": product_id,
                "seller_id": seller_id, "shipping_limit_date": limit, "price": price,
                "freight_value": freight,
            })
        return self._dedupe(src, out, ["order_id", "order_item_id"])

    def _products(self, frame: pd.DataFrame) -> dict[str, dict]:
        src, out = "products", []
        for rec in frame.to_dict("records"):
            key = rec["product_id"]
            product_id = self._hex(src, rec, "product_id", key)
            if not product_id:
                continue
            category = rec["product_category_name"].strip().lower() or None
            if category and not CATEGORY_KEY.fullmatch(category):
                self.log.correct(self.names[src], rec[ROW], key, "invalid_category_set_null",
                                 original=rec["product_category_name"])
                category = None
            row = {ROW: rec[ROW], "product_id": product_id, "product_category_name": category}
            for column, minimum, maximum in (
                ("product_weight_g", 0, 2**31 - 1),
                ("product_length_cm", 1, SMALLINT_MAX),
                ("product_height_cm", 1, SMALLINT_MAX),
                ("product_width_cm", 1, SMALLINT_MAX),
            ):
                text = rec[column].strip()
                value = int(text) if WHOLE_NUMBER.fullmatch(text) else None
                if text and (value is None or not minimum <= value <= maximum):
                    self.log.correct(self.names[src], rec[ROW], key, "invalid_measurement_set_null",
                                     column=column, original=rec[column])
                    value = None
                row[column] = value
            out.append(row)
        return {rec["product_id"]: rec for rec in self._dedupe(src, out, ["product_id"])}

    def _translations(self, frame: pd.DataFrame) -> dict[str, dict]:
        src, out = "category_translation", []
        for rec in frame.to_dict("records"):
            key = rec["product_category_name"]
            name = key.strip().lower()
            english = rec["product_category_name_english"].strip().lower() or None
            if not CATEGORY_KEY.fullmatch(name):
                self.log.reject(self.names[src], rec[ROW], key, "invalid_category_name", value=key)
                continue
            if english and not CATEGORY_KEY.fullmatch(english):
                self.log.correct(self.names[src], rec[ROW], key, "invalid_translation_set_null",
                                 original=rec["product_category_name_english"])
                english = None
            out.append({ROW: rec[ROW], "product_category_name": name,
                        "product_category_name_english": english})
        return {r["product_category_name"]: r
                for r in self._dedupe(src, out, ["product_category_name"])}

    # -- orchestration ------------------------------------------------------------------
    def run(self) -> ValidatedSubset:
        raw = {key: src.frame for key, src in self.sources.items()}

        # 1. Subset rule on the raw order_id, then the raw rows each selected order pulls in.
        sel_orders = select_orders(raw["orders"], self.modulus, self.max_orders)
        sel_items = raw["order_items"][raw["order_items"]["order_id"].isin(sel_orders["order_id"])]
        sel_customers = raw["customers"][raw["customers"]["customer_id"].isin(sel_orders["customer_id"])]
        sel_products = raw["products"][raw["products"]["product_id"].isin(sel_items["product_id"])]
        sel_sellers = raw["sellers"][raw["sellers"]["seller_id"].isin(sel_items["seller_id"])]
        sel_translation = raw["category_translation"][
            raw["category_translation"]["product_category_name"].str.strip().str.lower().isin(
                sel_products["product_category_name"].str.strip().str.lower())
        ]
        candidates = {"orders": sel_orders, "order_items": sel_items, "customers": sel_customers,
                      "products": sel_products, "sellers": sel_sellers,
                      "category_translation": sel_translation}

        # 2. Validate parents before dependents, cascading rejections down to items.
        orders = self._orders(sel_orders)
        customers = self._address_entity("customers", sel_customers, "customer_id", "customer",
                                         extra_ids=("customer_unique_id",))
        rejected_orders: dict[str, str] = {
            oid: "customer_missing_or_rejected" for oid, rec in orders.items()
            if rec["customer_id"] not in customers
        }
        items = self._items(sel_items[sel_items["order_id"].isin(list(orders))])
        # A dropped exact duplicate loses no information; any other rejected item would
        # leave the order incomplete, so the whole order is rejected.
        rejected_item_rows = {
            i.source_row for i in self.log.issues
            if i.source_file == self.names["order_items"] and i.action == "rejected"
            and i.rule != "exact_duplicate"
        }
        for rec in sel_items.to_dict("records"):
            if rec[ROW] in rejected_item_rows and rec["order_id"] in orders:
                rejected_orders.setdefault(rec["order_id"], "order_has_rejected_item")
        products = self._products(sel_products)
        sellers = self._address_entity("sellers", sel_sellers, "seller_id", "seller")
        for rec in items:
            if rec["product_id"] not in products:
                rejected_orders.setdefault(rec["order_id"], "product_missing_or_rejected")
            if rec["seller_id"] not in sellers:
                rejected_orders.setdefault(rec["order_id"], "seller_missing_or_rejected")
        # The 3NF decomposition relies on two FDs; an order violating them cannot be stored.
        by_order_seller: dict[tuple, set] = defaultdict(set)
        by_order_product: dict[tuple, set] = defaultdict(set)
        for rec in items:
            by_order_seller[(rec["order_id"], rec["seller_id"])].add(rec["shipping_limit_date"])
            by_order_product[(rec["order_id"], rec["product_id"])].add(
                (rec["seller_id"], rec["price"], rec["freight_value"]))
        for (oid, _), values in by_order_seller.items():
            if len(values) > 1:
                rejected_orders.setdefault(oid, "fd_violation_order_seller_shipping_limit")
        for (oid, _), values in by_order_product.items():
            if len(values) > 1:
                rejected_orders.setdefault(oid, "fd_violation_order_product_price_seller")
        for oid, rule in rejected_orders.items():
            self.log.reject(self.names["orders"], orders[oid][ROW], oid, rule)

        # 3. Final closure from the surviving orders only.
        final_orders = {oid: rec for oid, rec in orders.items() if oid not in rejected_orders}
        final_items = [rec for rec in items if rec["order_id"] in final_orders]
        final_customers = {orders[oid]["customer_id"]: customers[orders[oid]["customer_id"]]
                           for oid in final_orders}
        final_products = {pid: products[pid] for pid in {r["product_id"] for r in final_items}}
        final_sellers = {sid: sellers[sid] for sid in {r["seller_id"] for r in final_items}}
        translations = self._translations(sel_translation)
        category_names = sorted({p["product_category_name"] for p in final_products.values()
                                 if p["product_category_name"]})
        used_translation_rows = {translations[c][ROW] for c in category_names if c in translations}

        loaded_rows = {
            "orders": {r[ROW] for r in final_orders.values()},
            "order_items": {r[ROW] for r in final_items},
            "customers": {r[ROW] for r in final_customers.values()},
            "products": {r[ROW] for r in final_products.values()},
            "sellers": {r[ROW] for r in final_sellers.values()},
            "category_translation": used_translation_rows,
        }
        # Any selected row that is neither loaded nor already rejected was dropped because a
        # related row was rejected; record it so rows_in_subset = loaded + rejected per file.
        for key, frame in candidates.items():
            name = self.names[key]
            already = self.log.rows(name, "rejected")
            for rec in frame.to_dict("records"):
                if rec[ROW] not in loaded_rows[key] and rec[ROW] not in already:
                    self.log.reject(name, rec[ROW], str(rec[frame.columns[1]]),
                                    "dependent_on_rejected_row")

        frames = self._frames(final_orders, final_items, final_customers, final_products,
                              final_sellers, category_names, translations)
        stats = {}
        for key, src in self.sources.items():
            rejected = self.log.rows(src.name, "rejected")
            corrected = self.log.rows(src.name, "corrected") & loaded_rows[key]
            stats[key] = FileStats(src.name, src.sha256, src.size_bytes, len(src.frame),
                                   len(candidates[key]), len(rejected), len(corrected))
        measures = {
            "orders": Decimal(len(final_orders)),
            "order_items": Decimal(len(final_items)),
            "total_item_price": sum((r["price"] for r in final_items), Decimal("0")),
            "total_item_freight": sum((r["freight_value"] for r in final_items), Decimal("0")),
        }
        return ValidatedSubset(frames, stats, self.log.issues, measures)

    @staticmethod
    def _frames(orders, items, customers, products, sellers, category_names,
                translations) -> dict[str, pd.DataFrame]:
        def frame(records, columns, dtypes=None):
            df = pd.DataFrame.from_records(
                [{c: r[c] for c in columns} for r in records], columns=columns)
            return df.astype(dtypes) if dtypes else df

        order_sellers = {(r["order_id"], r["seller_id"]): r["shipping_limit_date"] for r in items}
        order_lines = {(r["order_id"], r["product_id"]): r for r in items}
        return {
            "customers": pd.DataFrame(
                {"customer_unique_id": sorted({c["customer_unique_id"] for c in customers.values()})}),
            "order_customers": frame(
                customers.values(),
                ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                 "customer_city", "customer_state"]),
            "sellers": frame(
                sellers.values(),
                ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]),
            "product_categories": pd.DataFrame({
                "product_category_name": category_names,
                "product_category_name_english": [
                    translations[c]["product_category_name_english"] if c in translations else None
                    for c in category_names],
            }),
            "products": frame(
                products.values(),
                ["product_id", "product_category_name", "product_weight_g", "product_length_cm",
                 "product_height_cm", "product_width_cm"],
                {"product_weight_g": "Int64", "product_length_cm": "Int64",
                 "product_height_cm": "Int64", "product_width_cm": "Int64"}),
            "orders": frame(
                orders.values(),
                ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
                 "order_approved_at", "order_delivered_carrier_date",
                 "order_delivered_customer_date", "order_estimated_delivery_date"]),
            "order_sellers": pd.DataFrame(
                [{"order_id": o, "seller_id": s, "shipping_limit_date": d}
                 for (o, s), d in order_sellers.items()],
                columns=["order_id", "seller_id", "shipping_limit_date"]),
            "order_lines": pd.DataFrame(
                [{"order_id": o, "product_id": p, "seller_id": r["seller_id"],
                  "item_price": r["price"], "item_freight_value": r["freight_value"]}
                 for (o, p), r in order_lines.items()],
                columns=["order_id", "product_id", "seller_id", "item_price", "item_freight_value"]),
            "order_items": frame(items, ["order_id", "order_item_id", "product_id"]),
        }


def validate_subset(sources: dict[str, SourceFile], modulus: int = DEFAULT_MODULUS,
                    max_orders: int | None = None) -> ValidatedSubset:
    return SubsetValidator(sources, modulus, max_orders).run()


__all__ = ["LOAD_ORDER", "FileStats", "Issue", "ValidatedSubset", "validate_subset"]
