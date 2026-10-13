import os

# Tests must NEVER touch the real database. Set this before the app is imported.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://sahaayak:sahaayak_dev_password@localhost:5433/sahaayak_test",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers all tables)
from app.core.database import Base, engine, get_db
from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _test_schema():
    assert str(engine.url.database).endswith("_test"), "Tests must run on a *_test database"
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def db():
    """Each test runs in a transaction that is rolled back."""
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
    limiter.enabled = False
    yield TestClient(app)
    app.dependency_overrides.clear()
    limiter.enabled = True