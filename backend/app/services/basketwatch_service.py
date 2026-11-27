"""Compares the items of a grocery receipt with the supermarkets' online prices.

The prices come from BasketWatch (https://basketwatchireland.com/mcp), an MCP server
that reads the websites of Aldi, Tesco, SuperValu, Dunnes and Lidl every night.
MCP is just JSON-RPC over HTTP, so we call it with httpx like the LM Studio client.

We only use the free compare_prices tool (one product per call, no account).
Whatever we get back is saved in reference_prices, so the same item is not looked
up again on the same day.
"""
import json
import logging
import re
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.models.reference_price import ReferencePrice
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

SOURCE = "basketwatch"
STORES = ["aldi", "tesco", "supervalu", "dunnes", "lidl"]


class BasketWatchError(Exception):
    """BasketWatch could not be reached or sent back something we can't read."""


class BasketWatchClient:
    """Talks to the BasketWatch MCP server. One client is used for a whole receipt."""

    def __init__(self, url=None, timeout=None, transport=None):
        self.url = url or config.BASKETWATCH_MCP_URL
        self.timeout = timeout or config.BASKETWATCH_TIMEOUT
        self.transport = transport  # only set by the tests, to fake the server
        self.http = None
        self.session_id = None
        self.next_id = 1

    def _post(self, message):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "spendgpt-backend",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        try:
            response = self.http.post(self.url, json=message, headers=headers)
        except httpx.HTTPError as error:
            raise BasketWatchError(f"Cannot reach BasketWatch: {error}") from error

        if response.status_code >= 400:
            raise BasketWatchError(f"BasketWatch returned HTTP {response.status_code}")
        if response.headers.get("mcp-session-id"):
            self.session_id = response.headers["mcp-session-id"]
        # a notification gets an empty answer
        if "id" not in message or not response.text.strip():
            return None
        return self._read_body(response)

    @staticmethod
    def _read_body(response):
        # the server can answer with plain json or as a server-sent event ("data: {...}")
        text = response.text
        if "text/event-stream" in response.headers.get("content-type", ""):
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = data_lines[-1] if data_lines else ""
        try:
            body = json.loads(text)
        except ValueError as error:
            raise BasketWatchError("BasketWatch sent back something that is not JSON") from error
        if "error" in body:
            raise BasketWatchError(f"BasketWatch error: {body['error'].get('message')}")
        return body.get("result")

    def _request(self, method, params=None):
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.next_id += 1
        return self._post(message)

    def open(self):
        # every MCP conversation starts with initialize and then the initialized notification
        self.http = httpx.Client(timeout=self.timeout, transport=self.transport)
        self._request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "spendgpt-backend", "version": "1.0"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def close(self):
        if self.http is not None:
            self.http.close()
            self.http = None

    def compare_prices(self, query):
        """The best match for query and its price at each shop, or None if nothing matched."""
        if self.http is None:
            self.open()
        result = self._request("tools/call", {
            "name": "compare_prices",
            "arguments": {"query": query, "limit": 1},
        })
        if not result or result.get("isError"):
            return None
        data = result.get("structuredContent")
        if data is None:
            # older servers only send the json as text
            try:
                data = json.loads(result["content"][0]["text"])
            except (KeyError, IndexError, ValueError):
                return None

        matches = data.get("matches") or []
        if not matches:
            return None
        match = matches[0]
        prices = {}
        for store, info in (match.get("prices") or {}).items():
            if info and info.get("price") is not None:
                prices[store] = float(info["price"])
        if not prices:
            return None
        return {
            "product": match.get("product"),
            "pack": match.get("pack"),
            "prices": prices,
            "as_of": data.get("as_of"),
        }


def get_basketwatch_client():
    """FastAPI dependency, so the tests can swap in a fake one."""
    return BasketWatchClient()


def store_for_merchant(merchant_name):
    """'Lidl' or 'ALDI Stores' -> 'lidl' / 'aldi'. None if it is not one of the five shops."""
    if not merchant_name:
        return None
    name = merchant_name.lower()
    if "dunnes" in name:
        return "dunnes"
    if "super valu" in name or "supervalu" in name:
        return "supervalu"
    for store in STORES:
        if store in name:
            return store
    return None


def clean_item_name(name):
    """Turns a receipt line like '381837 BREAD WHOLEMEAL' into 'bread wholemeal' for searching."""
    if not name:
        return ""
    text = name.lower()
    text = re.sub(r"\b\d{4,}\b", " ", text)        # product codes printed by aldi/lidl
    text = re.sub(r"[^a-z0-9%.& ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _cached_prices(db, search_name, today):
    rows = db.scalars(
        select(ReferencePrice).where(
            ReferencePrice.source == SOURCE,
            ReferencePrice.normalized_name == search_name,
            ReferencePrice.observed_on == today,
        )
    ).all()
    if not rows:
        return None
    return {
        "product": rows[0].product_name,
        "pack": rows[0].unit_size,
        "prices": {row.retailer: float(row.price) for row in rows},
        "as_of": today.isoformat(),
    }


def _save_prices(db, search_name, found, today):
    for store, price in found["prices"].items():
        db.add(ReferencePrice(
            product_name=(found["product"] or search_name)[:150],
            normalized_name=search_name[:150],
            retailer=store,
            unit_size=found["pack"][:50] if found["pack"] else None,
            price=Decimal(str(price)),
            source=SOURCE,
            observed_on=today,
        ))


def compare_receipt(db: Session, transaction: Transaction, client: BasketWatchClient, today=None):
    """Price every item of a receipt at the five supermarkets.

    Raises BasketWatchError if BasketWatch can't be reached at all.
    """
    today = today or date.today()
    store = store_for_merchant(transaction.merchant_name)

    items = []
    total_paid = 0.0
    total_cheapest = 0.0
    matched_count = 0
    as_of = None
    lookups = 0

    try:
        for item in transaction.items:
            quantity = float(item.quantity or 1)
            paid_each = float(item.unit_price)
            search_name = clean_item_name(item.normalized_name or item.item_name)
            row = {
                "item_name": item.item_name,
                "quantity": quantity,
                "paid_unit_price": paid_each,
                "matched": False,
                "matched_product": None,
                "pack": None,
                "same_store_price": None,
                "cheapest_store": None,
                "cheapest_price": None,
                "possible_saving": 0.0,
                "prices": {},
            }

            found = None
            if search_name:
                found = _cached_prices(db, search_name, today)
                if found is None and lookups < config.BASKETWATCH_MAX_ITEMS:
                    lookups += 1
                    found = client.compare_prices(search_name)
                    if found:
                        _save_prices(db, search_name, found, today)

            if found:
                cheapest_store = min(found["prices"], key=found["prices"].get)
                cheapest_price = found["prices"][cheapest_store]
                saving = max(0.0, (paid_each - cheapest_price) * quantity)
                row.update({
                    "matched": True,
                    "matched_product": found["product"],
                    "pack": found["pack"],
                    "same_store_price": found["prices"].get(store) if store else None,
                    "cheapest_store": cheapest_store,
                    "cheapest_price": cheapest_price,
                    "possible_saving": round(saving, 2),
                    "prices": found["prices"],
                })
                matched_count += 1
                total_paid += paid_each * quantity
                total_cheapest += min(paid_each, cheapest_price) * quantity
                as_of = as_of or found["as_of"]

            items.append(row)
        db.commit()
    finally:
        client.close()

    return {
        "transaction_id": transaction.transaction_id,
        "merchant_name": transaction.merchant_name,
        "store": store,
        "as_of": as_of,
        "items_total": len(items),
        "items_matched": matched_count,
        "matched_paid_total": round(total_paid, 2),
        "matched_cheapest_total": round(total_cheapest, 2),
        "possible_saving": round(total_paid - total_cheapest, 2),
        "items": items,
        "note": "Online prices from BasketWatch; prices in store can differ. "
                "Items it could not match are left out of the totals.",
    }
