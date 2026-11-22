import pytest

BASE = "/api/budgets/"


def budget_payload(**overrides):
    payload = {
        "amount_limit": "200.00",
        "start_date": "2026-11-01",
        "end_date": "2026-11-30",
        "category_id": None,
    }
    payload.update(overrides)
    return payload


def create_budget(client, user_id, **overrides):
    return client.post(BASE, params={"user_id": user_id}, json=budget_payload(**overrides))


# ---------- create: validation ----------

def test_create_budget_returns_201(client, user):
    response = create_budget(client, user["user_id"])
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user["user_id"]
    assert body["amount_limit"] == "200.00"
    assert body["category_id"] is None
    assert body["created_at"]


def test_create_budget_with_category(client, user, categories):
    category_id = categories[0]["category_id"]
    response = create_budget(client, user["user_id"], category_id=category_id)
    assert response.status_code == 201
    assert response.json()["category_id"] == category_id


def test_create_budget_unknown_user_is_404(client):
    assert create_budget(client, 999).status_code == 404


def test_create_budget_unknown_category_is_404(client, user):
    assert create_budget(client, user["user_id"], category_id=999).status_code == 404


@pytest.mark.parametrize("category_id", [0, -1])
def test_create_budget_non_positive_category_is_422(client, user, category_id):
    assert create_budget(client, user["user_id"], category_id=category_id).status_code == 422


@pytest.mark.parametrize(
    ("amount", "expected"),
    [("0", 422), ("-10", 422), ("0.01", 201), ("1.999", 422), ("99999999.99", 201)],
)
def test_create_budget_amount_validation(client, user, amount, expected):
    assert create_budget(client, user["user_id"], amount_limit=amount).status_code == expected


def test_create_budget_end_before_start_is_422(client, user):
    response = create_budget(client, user["user_id"], start_date="2026-11-30", end_date="2026-11-01")
    assert response.status_code == 422


def test_create_budget_single_day_is_allowed(client, user):
    response = create_budget(client, user["user_id"], start_date="2026-11-15", end_date="2026-11-15")
    assert response.status_code == 201


# ---------- create: overlap rules ----------

@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-11-01", "2026-11-30"),  # identical
        ("2026-11-10", "2026-11-20"),  # inside
        ("2026-10-01", "2026-12-31"),  # surrounds
        ("2026-10-15", "2026-11-05"),  # overlaps start
        ("2026-11-25", "2026-12-10"),  # overlaps end
        ("2026-11-30", "2026-12-31"),  # shares only the last day
        ("2026-10-01", "2026-11-01"),  # shares only the first day
    ],
)
def test_overlapping_budget_same_category_is_409(client, user, start, end):
    create_budget(client, user["user_id"])
    response = create_budget(client, user["user_id"], start_date=start, end_date=end)
    assert response.status_code == 409


def test_back_to_back_budgets_are_allowed(client, user):
    create_budget(client, user["user_id"])
    response = create_budget(client, user["user_id"], start_date="2026-12-01", end_date="2026-12-31")
    assert response.status_code == 201


def test_overlapping_budget_same_real_category_is_409(client, user, categories):
    category_id = categories[0]["category_id"]
    create_budget(client, user["user_id"], category_id=category_id)
    response = create_budget(client, user["user_id"], category_id=category_id, start_date="2026-11-15")
    assert response.status_code == 409


def test_overall_and_category_budget_can_share_a_period(client, user, categories):
    assert create_budget(client, user["user_id"], category_id=None).status_code == 201
    assert create_budget(client, user["user_id"], category_id=categories[0]["category_id"]).status_code == 201


def test_different_categories_can_share_a_period(client, user, categories):
    assert create_budget(client, user["user_id"], category_id=categories[0]["category_id"]).status_code == 201
    assert create_budget(client, user["user_id"], category_id=categories[1]["category_id"]).status_code == 201


def test_different_users_can_have_same_period(client, make_user):
    alice, bob = make_user(), make_user()
    assert create_budget(client, alice["user_id"]).status_code == 201
    assert create_budget(client, bob["user_id"]).status_code == 201


# ---------- list / get ----------

def test_list_budgets_newest_start_first(client, user):
    create_budget(client, user["user_id"], start_date="2026-10-01", end_date="2026-10-31")
    create_budget(client, user["user_id"], start_date="2026-12-01", end_date="2026-12-31")
    create_budget(client, user["user_id"], start_date="2026-11-01", end_date="2026-11-30")

    body = client.get(f"{BASE}user/{user['user_id']}").json()
    assert [b["start_date"] for b in body] == ["2026-12-01", "2026-11-01", "2026-10-01"]


def test_list_budgets_only_that_user(client, make_user):
    alice, bob = make_user(), make_user()
    create_budget(client, alice["user_id"])
    assert client.get(f"{BASE}user/{bob['user_id']}").json() == []


def test_list_budgets_unknown_user_is_404(client):
    assert client.get(f"{BASE}user/999").status_code == 404


def test_get_budget(client, user):
    created = create_budget(client, user["user_id"]).json()
    response = client.get(f"{BASE}{created['budget_id']}", params={"user_id": user["user_id"]})
    assert response.status_code == 200
    assert response.json() == created


def test_get_budget_unknown_is_404(client, user):
    assert client.get(f"{BASE}999", params={"user_id": user["user_id"]}).status_code == 404


def test_cannot_get_another_users_budget(client, make_user):
    alice, bob = make_user(), make_user()
    budget = create_budget(client, alice["user_id"]).json()
    response = client.get(f"{BASE}{budget['budget_id']}", params={"user_id": bob["user_id"]})
    assert response.status_code == 404


# ---------- update ----------

def update_budget(client, budget_id, user_id, **overrides):
    return client.put(f"{BASE}{budget_id}", params={"user_id": user_id}, json=budget_payload(**overrides))


def test_update_budget(client, user):
    created = create_budget(client, user["user_id"]).json()
    response = update_budget(client, created["budget_id"], user["user_id"], amount_limit="350.00")
    assert response.status_code == 200
    assert response.json()["amount_limit"] == "350.00"
    assert response.json()["budget_id"] == created["budget_id"]


def test_update_budget_does_not_conflict_with_itself(client, user):
    created = create_budget(client, user["user_id"]).json()
    response = update_budget(client, created["budget_id"], user["user_id"], end_date="2026-11-20")
    assert response.status_code == 200


def test_update_budget_into_another_budgets_period_is_409(client, user):
    create_budget(client, user["user_id"], start_date="2026-11-01", end_date="2026-11-30")
    december = create_budget(client, user["user_id"], start_date="2026-12-01", end_date="2026-12-31").json()
    response = update_budget(
        client, december["budget_id"], user["user_id"], start_date="2026-11-20", end_date="2026-12-31"
    )
    assert response.status_code == 409


def test_update_budget_invalid_dates_is_422(client, user):
    created = create_budget(client, user["user_id"]).json()
    response = update_budget(
        client, created["budget_id"], user["user_id"], start_date="2026-11-30", end_date="2026-11-01"
    )
    assert response.status_code == 422


def test_update_budget_unknown_category_is_404(client, user):
    created = create_budget(client, user["user_id"]).json()
    assert update_budget(client, created["budget_id"], user["user_id"], category_id=999).status_code == 404


def test_cannot_update_another_users_budget(client, make_user):
    alice, bob = make_user(), make_user()
    budget = create_budget(client, alice["user_id"]).json()
    response = update_budget(client, budget["budget_id"], bob["user_id"], amount_limit="1.00")
    assert response.status_code == 404
    # and alice's budget is unchanged
    original = client.get(f"{BASE}{budget['budget_id']}", params={"user_id": alice["user_id"]}).json()
    assert original["amount_limit"] == "200.00"


# ---------- delete ----------

def test_delete_budget(client, user):
    created = create_budget(client, user["user_id"]).json()
    response = client.delete(f"{BASE}{created['budget_id']}", params={"user_id": user["user_id"]})
    assert response.status_code == 200
    assert client.get(f"{BASE}user/{user['user_id']}").json() == []


def test_deleted_budget_period_can_be_reused(client, user):
    created = create_budget(client, user["user_id"]).json()
    client.delete(f"{BASE}{created['budget_id']}", params={"user_id": user["user_id"]})
    assert create_budget(client, user["user_id"]).status_code == 201


def test_cannot_delete_another_users_budget(client, make_user):
    alice, bob = make_user(), make_user()
    budget = create_budget(client, alice["user_id"]).json()
    response = client.delete(f"{BASE}{budget['budget_id']}", params={"user_id": bob["user_id"]})
    assert response.status_code == 404
    assert len(client.get(f"{BASE}user/{alice['user_id']}").json()) == 1


def test_delete_unknown_budget_is_404(client, user):
    assert client.delete(f"{BASE}999", params={"user_id": user["user_id"]}).status_code == 404
