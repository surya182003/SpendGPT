
import pytest

BASE = "/api/transactions/"


def txn_payload(**overrides):
    payload = {
        "merchant_name": "Aldi",
        "amount": "12.50",
        "transaction_date": "2026-11-01",
    }
    payload.update(overrides)
    return payload


def create_txn(client, user_id, **overrides):
    return client.post(BASE, params={"user_id": user_id}, json=txn_payload(**overrides))


# ---------- create ----------

def test_create_transaction_returns_201(client, user):
    response = create_txn(client, user["user_id"])
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user["user_id"]
    assert body["merchant_name"] == "Aldi"
    assert body["amount"] == "12.50"
    assert body["transaction_date"] == "2026-11-01"
    assert body["is_recurring"] is False
    assert body["category_id"] is None


def test_create_transaction_with_category(client, user, categories):
    category_id = categories[0]["category_id"]
    response = create_txn(client, user["user_id"], category_id=category_id, is_recurring=True)
    assert response.status_code == 201
    assert response.json()["category_id"] == category_id
    assert response.json()["is_recurring"] is True


def test_create_transaction_unknown_user_is_404(client):
    assert create_txn(client, 999).status_code == 404


def test_create_transaction_unknown_category_is_404(client, user):
    assert create_txn(client, user["user_id"], category_id=999).status_code == 404


def test_create_transaction_requires_user_id(client):
    assert client.post(BASE, json=txn_payload()).status_code == 422


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0", 422),
        ("-5.00", 422),
        ("0.01", 201),
        ("1.234", 422),
        ("99999999.99", 201),
        ("100000000.00", 422),
        ("abc", 422),
    ],
)
def test_create_transaction_amount_validation(client, user, amount, expected):
    assert create_txn(client, user["user_id"], amount=amount).status_code == expected


@pytest.mark.parametrize(
    ("merchant", "expected"),
    [("", 422), ("a", 201), ("a" * 100, 201), ("a" * 101, 422)],
)
def test_create_transaction_merchant_length(client, user, merchant, expected):
    assert create_txn(client, user["user_id"], merchant_name=merchant).status_code == expected



def test_create_transaction_whitespace_only_merchant_is_422(client, user):
    response = create_txn(client, user["user_id"], merchant_name="   ")
    assert response.status_code == 422

@pytest.mark.parametrize("bad_date", ["2026-13-01", "2026-02-30", "yesterday", ""])
def test_create_transaction_invalid_date_is_422(client, user, bad_date):
    assert create_txn(client, user["user_id"], transaction_date=bad_date).status_code == 422


# ---------- bad input: clean 422s, never a crash ----------

def error_fields(response):
    """The field names a 422 response complains about."""
    return {err["loc"][-1] for err in response.json()["detail"] if len(err["loc"]) > 1}


def test_empty_body_lists_every_missing_field(client, user):
    response = client.post(BASE, params={"user_id": user["user_id"]}, json={})
    assert response.status_code == 422
    assert error_fields(response) == {"merchant_name", "amount", "transaction_date"}
    assert all(err["msg"] == "Field required" for err in response.json()["detail"])


@pytest.mark.parametrize("body", [None, [1, 2], "just a string", 42])
def test_body_that_is_not_an_object_is_422(client, user, body):
    assert client.post(BASE, params={"user_id": user["user_id"]}, json=body).status_code == 422


def test_malformed_json_is_422(client, user):
    response = client.post(
        BASE,
        params={"user_id": user["user_id"]},
        content=b'{"merchant_name": "Aldi", ',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "NaN"),
        ("amount", "Infinity"),
        ("amount", True),
        ("amount", None),
        ("merchant_name", 123),
        ("merchant_name", None),
        ("transaction_date", 20261101),
        ("transaction_date", "2026-11-01T10:00:00"),
        ("transaction_date", None),
        ("category_id", "abc"),
        ("category_id", 1.5),
        ("is_recurring", "maybe"),
        ("is_recurring", None),
    ],
)
def test_wrong_type_is_422_and_names_the_field(client, user, field, value):
    response = create_txn(client, user["user_id"], **{field: value})
    assert response.status_code == 422
    assert field in error_fields(response)


def test_non_numeric_user_id_is_422(client):
    response = client.post(BASE, params={"user_id": "abc"}, json=txn_payload())
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "user_id"]


def test_error_message_is_understandable(client, user):
    response = create_txn(client, user["user_id"], amount="-1")
    error = response.json()["detail"][0]
    assert response.status_code == 422
    assert error["loc"] == ["body", "amount"]
    assert error["msg"] == "Input should be greater than 0"


def test_rejected_input_saves_nothing(client, user):
    create_txn(client, user["user_id"], amount="-1")
    create_txn(client, user["user_id"], merchant_name="")
    create_txn(client, user["user_id"], transaction_date="not-a-date")
    assert client.get(f"{BASE}user/{user['user_id']}").json() == []


HUGE_ID = 10**23


@pytest.mark.xfail(
    strict=True,
    reason="BUG: IDs larger than 64 bits crash the server (500, SQLite OverflowError). "
    "Bound IDs, e.g. Annotated[int, Field(gt=0, le=2_147_483_647)] for query/path/body IDs.",
)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda c: c.post(BASE, params={"user_id": HUGE_ID}, json=txn_payload()), id="create-huge-user_id"),
        pytest.param(lambda c: c.post(BASE, params={"user_id": 1}, json=txn_payload(category_id=HUGE_ID)), id="create-huge-category_id"),
        pytest.param(lambda c: c.get(f"{BASE}{HUGE_ID}", params={"user_id": 1}), id="get-huge-transaction_id"),
        pytest.param(lambda c: c.get(f"{BASE}user/{HUGE_ID}"), id="list-huge-user_id"),
        pytest.param(lambda c: c.delete(f"{BASE}{HUGE_ID}", params={"user_id": 1}), id="delete-huge-transaction_id"),
        pytest.param(lambda c: c.put(f"{BASE}{HUGE_ID}", params={"user_id": 1}, json=txn_payload()), id="update-huge-transaction_id"),
    ],
)
def test_huge_ids_do_not_crash_the_server(client, user, call):
    assert call(client).status_code in (404, 422)


# ---------- list ----------

def test_list_transactions_newest_first(client, user):
    for day in ["2026-11-05", "2026-11-20", "2026-11-01"]:
        create_txn(client, user["user_id"], transaction_date=day)

    response = client.get(f"{BASE}user/{user['user_id']}")
    assert response.status_code == 200
    dates = [t["transaction_date"] for t in response.json()]
    assert dates == ["2026-11-20", "2026-11-05", "2026-11-01"]


def test_list_transactions_only_returns_that_users_rows(client, make_user):
    alice, bob = make_user(), make_user()
    create_txn(client, alice["user_id"], merchant_name="Alice shop")
    create_txn(client, bob["user_id"], merchant_name="Bob shop")

    body = client.get(f"{BASE}user/{alice['user_id']}").json()
    assert [t["merchant_name"] for t in body] == ["Alice shop"]


def test_list_transactions_empty_for_new_user(client, user):
    assert client.get(f"{BASE}user/{user['user_id']}").json() == []


def test_list_transactions_unknown_user_is_404(client):
    assert client.get(f"{BASE}user/999").status_code == 404


# ---------- get ----------

def test_get_transaction(client, user):
    created = create_txn(client, user["user_id"]).json()

    response = client.get(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": user["user_id"]},
    )

    assert response.status_code == 200
    assert response.json() == created


def test_get_transaction_requires_user_id(client, user):
    created = create_txn(client, user["user_id"]).json()

    response = client.get(f"{BASE}{created['transaction_id']}")

    assert response.status_code == 422


def test_get_another_users_transaction_is_404(client, make_user):
    alice, bob = make_user(), make_user()
    created = create_txn(client, alice["user_id"]).json()

    response = client.get(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": bob["user_id"]},
    )

    assert response.status_code == 404


def test_get_unknown_transaction_is_404(client, user):
    response = client.get(f"{BASE}999", params={"user_id": user["user_id"]})
    assert response.status_code == 404


# ---------- update ----------

def test_update_transaction(client, user):
    created = create_txn(client, user["user_id"]).json()

    updated_payload = txn_payload(
        merchant_name="Tesco",
        amount="25.50",
        transaction_date="2026-11-20",
        is_recurring=True,
    )

    response = client.put(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": user["user_id"]},
        json=updated_payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_name"] == "Tesco"
    assert body["amount"] == "25.50"
    assert body["transaction_date"] == "2026-11-20"
    assert body["is_recurring"] is True


def test_update_another_users_transaction_is_404(client, make_user):
    alice, bob = make_user(), make_user()
    created = create_txn(client, alice["user_id"]).json()

    response = client.put(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": bob["user_id"]},
        json=txn_payload(merchant_name="Changed shop"),
    )

    assert response.status_code == 404

    original = client.get(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": alice["user_id"]},
    )
    assert original.status_code == 200
    assert original.json()["merchant_name"] == "Aldi"


def test_update_transaction_unknown_category_is_404(client, user):
    created = create_txn(client, user["user_id"]).json()

    response = client.put(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": user["user_id"]},
        json=txn_payload(category_id=999),
    )

    assert response.status_code == 404


def test_update_unknown_transaction_is_404(client, user):
    response = client.put(
        f"{BASE}999",
        params={"user_id": user["user_id"]},
        json=txn_payload(),
    )

    assert response.status_code == 404


def test_update_transaction_requires_user_id(client, user):
    created = create_txn(client, user["user_id"]).json()

    response = client.put(
        f"{BASE}{created['transaction_id']}",
        json=txn_payload(merchant_name="Tesco"),
    )

    assert response.status_code == 422


# ---------- delete ----------

def test_delete_transaction(client, user):
    created = create_txn(client, user["user_id"]).json()

    response = client.delete(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": user["user_id"]},
    )

    assert response.status_code == 200

    get_response = client.get(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": user["user_id"]},
    )
    assert get_response.status_code == 404


def test_delete_another_users_transaction_is_404(client, make_user):
    alice, bob = make_user(), make_user()
    created = create_txn(client, alice["user_id"]).json()

    response = client.delete(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": bob["user_id"]},
    )

    assert response.status_code == 404

    original = client.get(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": alice["user_id"]},
    )
    assert original.status_code == 200


def test_delete_transaction_requires_user_id(client, user):
    created = create_txn(client, user["user_id"]).json()

    response = client.delete(f"{BASE}{created['transaction_id']}")

    assert response.status_code == 422


def test_delete_unknown_transaction_is_404(client, user):
    response = client.delete(f"{BASE}999", params={"user_id": user["user_id"]})
    assert response.status_code == 404


def test_delete_transaction_twice_is_404_second_time(client, user):
    created = create_txn(client, user["user_id"]).json()
    transaction_id = created["transaction_id"]
    params = {"user_id": user["user_id"]}

    first_response = client.delete(f"{BASE}{transaction_id}", params=params)
    second_response = client.delete(f"{BASE}{transaction_id}", params=params)

    assert first_response.status_code == 200
    assert second_response.status_code == 404


# ---------- category deletion ----------

def test_deleting_category_sets_transaction_category_to_null(client, user, categories, db_session):
    from app.models.category import Category

    category_id = categories[0]["category_id"]
    created = create_txn(client, user["user_id"], category_id=category_id).json()

    db_session.delete(db_session.get(Category, category_id))
    db_session.commit()

    response = client.get(
        f"{BASE}{created['transaction_id']}",
        params={"user_id": user["user_id"]},
    )

    assert response.status_code == 200
    assert response.json()["category_id"] is None
