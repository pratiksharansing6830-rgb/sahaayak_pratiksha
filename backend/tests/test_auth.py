from sqlalchemy import func, select

from app.models import AuditEvent, Role, User
from tests.helpers import PASSWORD, auth_headers, make_user

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def _count_audit(db, action):
    return db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action))


def test_register_creates_citizen_and_hides_password(client, db):
    r = client.post(REGISTER, json={"email": "Rani@Example.com", "password": PASSWORD, "full_name": "Rani"})
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "CITIZEN"
    assert body["email"] == "rani@example.com"
    assert "password" not in body and "password_hash" not in body
    user = db.scalar(select(User).where(User.email == "rani@example.com"))
    assert user.password_hash != PASSWORD and user.password_hash.startswith("$2")


def test_register_cannot_choose_a_role(client):
    r = client.post(REGISTER, json={
        "email": "evil@example.com", "password": PASSWORD, "full_name": "Evil", "role": "ADMIN",
    })
    assert r.status_code == 422


def test_duplicate_email_rejected(client, db):
    make_user(db, "dup@example.com")
    r = client.post(REGISTER, json={"email": "dup@example.com", "password": PASSWORD, "full_name": "X"})
    assert r.status_code == 409


def test_login_and_me(client, db):
    make_user(db, "me@example.com")
    headers = auth_headers(client, "me@example.com")
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["email"] == "me@example.com"


def test_wrong_password_is_rejected_and_audited(client, db):
    make_user(db, "wp@example.com")
    before = _count_audit(db, "LOGIN_FAILED")
    r = client.post(LOGIN, data={"username": "wp@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    assert _count_audit(db, "LOGIN_FAILED") == before + 1


def test_no_token_is_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_deactivated_user_token_stops_working(client, db):
    user = make_user(db, "off@example.com")
    headers = auth_headers(client, "off@example.com")
    user.is_active = False
    db.flush()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401