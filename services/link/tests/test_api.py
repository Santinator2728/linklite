import pytest
from fastapi.testclient import TestClient

from link_service import store as store_module
from link_service.main import create_app
from link_service.store import CODE_LENGTH, CodeGenerationError, LinkStore


@pytest.fixture
def store():
    return LinkStore(":memory:")


@pytest.fixture
def client(store):
    return TestClient(create_app(store))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_link_returns_201_and_short_code(client):
    response = client.post("/links", json={"url": "https://example.com/tutorial"})

    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://example.com/tutorial"
    assert len(body["code"]) == CODE_LENGTH
    assert body["code"].isalnum()


def test_created_link_can_be_read_back(client):
    code = client.post("/links", json={"url": "https://example.com"}).json()["code"]

    response = client.get(f"/links/{code}")

    assert response.status_code == 200
    assert response.json() == {"code": code, "url": "https://example.com"}


def test_invalid_url_returns_422_with_reason(client):
    response = client.post("/links", json={"url": "javascript:alert(1)"})

    assert response.status_code == 422
    assert "Only http and https" in response.json()["detail"]


def test_missing_url_field_returns_422(client):
    assert client.post("/links", json={}).status_code == 422


def test_unknown_code_returns_404(client):
    assert client.get("/links/doesNotExist").status_code == 404


def test_store_gives_up_after_repeated_code_collisions(store, monkeypatch):
    monkeypatch.setattr(store_module.secrets, "choice", lambda alphabet: "a")
    store.create("https://example.com")

    with pytest.raises(CodeGenerationError):
        store.create("https://example.org")
