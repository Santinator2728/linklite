import pytest
from fastapi.testclient import TestClient

from analytics_service.main import create_app
from analytics_service.store import MAX_REFERRER_LENGTH, ClickStore


@pytest.fixture
def store():
    return ClickStore(":memory:")


@pytest.fixture
def client(store):
    return TestClient(create_app(store))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_recorded_clicks_are_counted(client):
    for _ in range(3):
        response = client.post("/clicks", json={"code": "abc1234", "referrer": None})
        assert response.status_code == 202

    assert client.get("/stats/abc1234").json() == {"code": "abc1234", "total_clicks": 3}


def test_unknown_code_has_zero_clicks(client):
    assert client.get("/stats/nothing").json()["total_clicks"] == 0


@pytest.mark.parametrize("code", ["", "has space", "<script>", "x" * 33])
def test_invalid_code_is_rejected(client, code):
    assert client.post("/clicks", json={"code": code}).status_code == 422


def test_long_referrer_is_truncated(store):
    store.record("abc", "r" * (MAX_REFERRER_LENGTH + 100))

    (stored,) = store._conn.execute("SELECT referrer FROM clicks").fetchone()
    assert len(stored) == MAX_REFERRER_LENGTH
