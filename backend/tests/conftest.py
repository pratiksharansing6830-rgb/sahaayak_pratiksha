import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture()
def db():
    """Each test runs in a transaction that is rolled back; your dev data is untouched."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    limiter.enabled = False  # rate limits would make repeated test logins fail
    yield TestClient(app)
    app.dependency_overrides.clear()
    limiter.enabled = True