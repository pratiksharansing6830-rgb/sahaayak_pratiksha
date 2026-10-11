from app.core.security import hash_password
from app.models import Role, User

PASSWORD = "Passw0rd!test"


def make_user(db, email, role=Role.CITIZEN, organization_id=None):
    user = User(
        email=email, password_hash=hash_password(PASSWORD), full_name="Test User",
        role=role, organization_id=organization_id,
    )
    db.add(user)
    db.flush()
    return user


def auth_headers(client, email, password=PASSWORD):
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}