import pytest

from app.models.user import User

REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"


def register_payload(**overrides):
    payload = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "password": "password123",
    }
    payload.update(overrides)
    return payload


# ---------- register ----------

def test_register_returns_201_and_user(client):
    response = client.post(REGISTER, json=register_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "Account created"
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["user_id"] > 0


def test_register_never_returns_password_or_hash(client):
    body = client.post(REGISTER, json=register_payload()).json()
    text = str(body)
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert "password123" not in text


def test_register_stores_hashed_password(client, db_session):
    client.post(REGISTER, json=register_payload())
    stored = db_session.query(User).one()
    assert stored.password_hash != "password123"
    assert stored.password_hash.startswith("$2")  # bcrypt prefix


def test_register_lowercases_email(client):
    body = client.post(REGISTER, json=register_payload(email="Ada@Example.COM")).json()
    assert body["user"]["email"] == "ada@example.com"


def test_register_duplicate_email_is_409(client):
    client.post(REGISTER, json=register_payload())
    response = client.post(REGISTER, json=register_payload())
    assert response.status_code == 409


def test_register_duplicate_email_different_case_is_409(client):
    client.post(REGISTER, json=register_payload(email="ada@example.com"))
    response = client.post(REGISTER, json=register_payload(email="ADA@example.com"))
    assert response.status_code == 409


@pytest.mark.parametrize("email", ["not-an-email", "a@", "@b.com", ""])
def test_register_invalid_email_is_422(client, email):
    assert client.post(REGISTER, json=register_payload(email=email)).status_code == 422


@pytest.mark.parametrize("field", ["first_name", "last_name"])
def test_register_empty_name_is_422(client, field):
    assert client.post(REGISTER, json=register_payload(**{field: ""})).status_code == 422


def test_register_name_over_50_chars_is_422(client):
    assert client.post(REGISTER, json=register_payload(first_name="a" * 51)).status_code == 422


@pytest.mark.parametrize("field", ["first_name", "last_name", "email", "password"])
def test_register_missing_field_is_422(client, field):
    payload = register_payload()
    del payload[field]
    assert client.post(REGISTER, json=payload).status_code == 422


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("a" * 7, 422),      # below minimum
        ("a" * 8, 201),      # minimum
        ("a" * 72, 201),     # bcrypt byte limit
        ("a" * 73, 422),     # over bcrypt byte limit
        ("😀" * 18, 201),    # 18 chars = 72 bytes
        ("😀" * 19, 422),    # only 19 chars but 76 bytes
    ],
)
def test_register_password_length_boundaries(client, password, expected):
    response = client.post(REGISTER, json=register_payload(password=password))
    assert response.status_code == expected


# ---------- login ----------

def test_login_success(client, make_user):
    make_user(email="ada@example.com", password="password123")
    response = client.post(LOGIN, json={"email": "ada@example.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["message"] == "Login successful"
    assert response.json()["user"]["email"] == "ada@example.com"


@pytest.mark.parametrize("email", ["ADA@EXAMPLE.COM", "  ada@example.com  ", " Ada@Example.com"])
def test_login_ignores_email_case_and_spaces(client, make_user, email):
    make_user(email="ada@example.com", password="password123")
    response = client.post(LOGIN, json={"email": email, "password": "password123"})
    assert response.status_code == 200


def test_login_wrong_password_is_401(client, make_user):
    make_user(email="ada@example.com", password="password123")
    response = client.post(LOGIN, json={"email": "ada@example.com", "password": "wrongpass1"})
    assert response.status_code == 401


def test_login_password_is_case_sensitive(client, make_user):
    make_user(email="ada@example.com", password="Password123")
    response = client.post(LOGIN, json={"email": "ada@example.com", "password": "password123"})
    assert response.status_code == 401


def test_login_does_not_reveal_whether_email_exists(client, make_user):
    make_user(email="ada@example.com", password="password123")
    wrong_password = client.post(LOGIN, json={"email": "ada@example.com", "password": "nope12345"})
    unknown_email = client.post(LOGIN, json={"email": "ghost@example.com", "password": "nope12345"})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_with_malformed_stored_hash_is_401_not_500(client, db_session):
    db_session.add(User(first_name="X", last_name="Y", email="bad@example.com", password_hash="not-a-bcrypt-hash"))
    db_session.commit()
    response = client.post(LOGIN, json={"email": "bad@example.com", "password": "anything1"})
    assert response.status_code == 401


def test_login_missing_fields_is_422(client):
    assert client.post(LOGIN, json={"email": "ada@example.com"}).status_code == 422
    assert client.post(LOGIN, json={"password": "x"}).status_code == 422
