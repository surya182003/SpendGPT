def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_categories_empty_when_none_seeded(client):
    response = client.get("/api/categories/")
    assert response.status_code == 200
    assert response.json() == []


def test_categories_listed_in_id_order(client, categories):
    response = client.get("/api/categories/")
    assert response.status_code == 200
    body = response.json()
    assert [c["category_id"] for c in body] == sorted(c["category_id"] for c in body)
    assert [c["category_name"] for c in body] == ["Groceries", "Entertainment"]
    assert set(body[0]) == {"category_id", "category_name", "spend_type"}
