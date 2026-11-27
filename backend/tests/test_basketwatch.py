"""Receipt price comparison with BasketWatch.

No test calls the real server: the endpoint gets FakeBasketWatch through a
dependency override, and the client itself is tested with httpx.MockTransport.
"""
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.models.receipt_item import ReceiptItem
from app.models.reference_price import ReferencePrice
from app.models.transaction import Transaction
from app.services.basketwatch_service import (
    BasketWatchClient,
    BasketWatchError,
    clean_item_name,
    get_basketwatch_client,
    store_for_merchant,
)

KETCHUP = {"product": "Heinz Tomato Ketchup (460 g)", "pack": "460 g",
           "prices": {"aldi": 1.39, "tesco": 1.25, "lidl": 1.49}, "as_of": "2026-11-27"}


class FakeBasketWatch:
    """Stands in for BasketWatchClient and remembers what it was asked."""

    def __init__(self, answers=None, offline=False):
        self.answers = answers or {}
        self.offline = offline
        self.queries = []

    def compare_prices(self, query):
        if self.offline:
            raise BasketWatchError("fake offline")
        self.queries.append(query)
        return self.answers.get(query)

    def close(self):
        pass


@pytest.fixture
def receipt(db, user):
    t = Transaction(user_id=user["user_id"], amount=Decimal("3.18"), merchant_name="Aldi",
                    transaction_date=date(2026, 10, 7), receipt_hash="a" * 64)
    t.items = [
        ReceiptItem(item_name="646397 TOMATO KETCHUP", normalized_name="646397 tomato ketchup",
                    quantity=Decimal("1"), unit_price=Decimal("1.39")),
        ReceiptItem(item_name="TUNA SWATER", normalized_name="tuna swater",
                    quantity=Decimal("3"), unit_price=Decimal("0.79")),
    ]
    db.add(t)
    db.commit()
    return t.transaction_id


def use_fake(fake):
    app.dependency_overrides[get_basketwatch_client] = lambda: fake
    return fake


def url(receipt_id, user_id):
    return f"/api/ai/receipts/{receipt_id}/price-comparison?user_id={user_id}"


def test_compare_receipt(client, db, user, receipt):
    fake = use_fake(FakeBasketWatch({"tomato ketchup": KETCHUP}))
    response = client.get(url(receipt, user["user_id"]))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["store"] == "aldi"
    assert body["items_total"] == 2 and body["items_matched"] == 1
    ketchup, tuna = body["items"]
    assert ketchup["matched"] is True
    assert ketchup["same_store_price"] == 1.39
    assert (ketchup["cheapest_store"], ketchup["cheapest_price"]) == ("tesco", 1.25)
    assert ketchup["possible_saving"] == 0.14
    assert tuna["matched"] is False and tuna["possible_saving"] == 0
    # the unmatched tuna is left out of the totals
    assert body["matched_paid_total"] == 1.39 and body["possible_saving"] == 0.14
    assert fake.queries == ["tomato ketchup", "tuna swater"]


def test_prices_are_saved_and_reused_the_same_day(client, db, user, receipt):
    use_fake(FakeBasketWatch({"tomato ketchup": KETCHUP}))
    client.get(url(receipt, user["user_id"]))
    rows = db.scalars(select(ReferencePrice).where(ReferencePrice.source == "basketwatch")).all()
    assert sorted(r.retailer for r in rows) == ["aldi", "lidl", "tesco"]

    second = use_fake(FakeBasketWatch({"tomato ketchup": KETCHUP}))
    body = client.get(url(receipt, user["user_id"])).json()
    assert body["items"][0]["cheapest_price"] == 1.25
    # ketchup came from reference_prices, only the unmatched tuna was asked again
    assert second.queries == ["tuna swater"]


def test_paying_less_than_online_is_no_saving(client, db, user, receipt):
    dear = {**KETCHUP, "prices": {"aldi": 1.99, "tesco": 1.89}}
    use_fake(FakeBasketWatch({"tomato ketchup": dear}))
    body = client.get(url(receipt, user["user_id"])).json()
    assert body["items"][0]["possible_saving"] == 0
    assert body["possible_saving"] == 0


def test_basketwatch_down_gives_503(client, user, receipt):
    use_fake(FakeBasketWatch(offline=True))
    response = client.get(url(receipt, user["user_id"]))
    assert response.status_code == 503
    assert "BasketWatch" in response.json()["detail"]


def test_other_users_receipt_is_404(client, make_user, receipt):
    use_fake(FakeBasketWatch())
    other = make_user()
    assert client.get(url(receipt, other["user_id"])).status_code == 404


@pytest.mark.parametrize(
    ("merchant", "store"),
    [("Lidl", "lidl"), ("ALDI Stores (Ireland) Ltd", "aldi"), ("Dunnes Stores", "dunnes"),
     ("SuperValu Cork", "supervalu"), ("Tesco Ireland", "tesco"), ("Corner Shop", None), (None, None)],
)
def test_store_for_merchant(merchant, store):
    assert store_for_merchant(merchant) == store


@pytest.mark.parametrize(
    ("raw", "clean"),
    [("381837 BREAD WHOLEMEAL", "bread wholemeal"), ("Natural Yogurt 1.5%", "natural yogurt 1.5%"),
     ("SAUCE PASTA 500G", "sauce pasta 500g"), ("", "")],
)
def test_clean_item_name(raw, clean):
    assert clean_item_name(raw) == clean


# ---------- the MCP client itself ----------

def fake_server(tool_result, as_event_stream=False):
    """A pretend BasketWatch that answers initialize and tools/call."""
    seen = []

    def handler(request):
        message = json.loads(request.content)
        seen.append(message["method"])
        if "id" not in message:
            return httpx.Response(202)
        result = tool_result if message["method"] == "tools/call" else {"protocolVersion": "2025-03-26"}
        body = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result})
        if as_event_stream:
            return httpx.Response(200, text=f"event: message\ndata: {body}\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})

    return httpx.MockTransport(handler), seen


SERVER_ANSWER = {"structuredContent": {
    "as_of": "2026-11-27",
    "matches": [{"product": "Heinz Ketchup", "pack": "460 g",
                 "prices": {"aldi": {"price": 1.39}, "tesco": {"price": 1.25}, "dunnes": None}}],
}}


@pytest.mark.parametrize("as_event_stream", [False, True])
def test_client_reads_compare_prices(as_event_stream):
    transport, seen = fake_server(SERVER_ANSWER, as_event_stream)
    client = BasketWatchClient(url="http://test/mcp", transport=transport)
    found = client.compare_prices("ketchup")
    client.close()
    assert found == {"product": "Heinz Ketchup", "pack": "460 g",
                     "prices": {"aldi": 1.39, "tesco": 1.25}, "as_of": "2026-11-27"}
    assert seen == ["initialize", "notifications/initialized", "tools/call"]


def test_client_no_match_is_none():
    transport, _ = fake_server({"structuredContent": {"matches": []}})
    client = BasketWatchClient(url="http://test/mcp", transport=transport)
    assert client.compare_prices("nothing like this") is None


def test_client_server_error_raises():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    client = BasketWatchClient(url="http://test/mcp", transport=transport)
    with pytest.raises(BasketWatchError):
        client.compare_prices("ketchup")
