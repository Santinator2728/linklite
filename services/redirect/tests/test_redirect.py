import httpx
import pytest
from fastapi.testclient import TestClient

from redirect_service.clients import AnalyticsClient, LinkClient, LinkServiceError
from redirect_service.main import create_app


class FakeLinks:
    def __init__(self, links=None, error=None):
        self.links = links or {}
        self.error = error

    def resolve(self, code):
        if self.error:
            raise self.error
        return self.links.get(code)


class FakeAnalytics:
    def __init__(self):
        self.clicks = []

    def record_click(self, code, referrer):
        self.clicks.append((code, referrer))


@pytest.fixture
def analytics():
    return FakeAnalytics()


def make_client(links, analytics):
    return TestClient(create_app(links, analytics), follow_redirects=False)


def test_health(analytics):
    client = make_client(FakeLinks(), analytics)
    assert client.get("/health").json() == {"status": "ok"}


def test_known_code_redirects_and_records_click(analytics):
    client = make_client(FakeLinks({"abc1234": "https://example.com"}), analytics)

    response = client.get("/abc1234", headers={"Referer": "https://social.example"})

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com"
    assert analytics.clicks == [("abc1234", "https://social.example")]


def test_unknown_code_returns_404_without_recording(analytics):
    client = make_client(FakeLinks(), analytics)

    assert client.get("/abc1234").status_code == 404
    assert analytics.clicks == []


def test_malformed_code_is_rejected_before_lookup(analytics):
    links = FakeLinks(error=AssertionError("lookup must not happen"))
    client = make_client(links, analytics)

    assert client.get("/bad-code!").status_code == 404


def test_unsafe_stored_target_is_never_redirected(analytics):
    client = make_client(FakeLinks({"abc1234": "javascript:alert(1)"}), analytics)

    assert client.get("/abc1234").status_code == 404


def test_link_service_failure_returns_503(analytics):
    client = make_client(FakeLinks(error=LinkServiceError("down")), analytics)

    assert client.get("/abc1234").status_code == 503


# --- HTTP clients -----------------------------------------------------------


def link_client(handler):
    return LinkClient("http://link", transport=httpx.MockTransport(handler))


def test_link_client_returns_url_for_known_code():
    client = link_client(lambda req: httpx.Response(200, json={"code": "a", "url": "https://x.io"}))
    assert client.resolve("a") == "https://x.io"


def test_link_client_returns_none_for_unknown_code():
    client = link_client(lambda req: httpx.Response(404))
    assert client.resolve("a") is None


def test_link_client_raises_on_server_error():
    client = link_client(lambda req: httpx.Response(500))
    with pytest.raises(LinkServiceError):
        client.resolve("a")


def test_link_client_raises_when_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LinkServiceError):
        link_client(handler).resolve("a")


def test_analytics_client_posts_click():
    sent = []

    def handler(request):
        sent.append(request.read())
        return httpx.Response(202)

    AnalyticsClient("http://analytics", transport=httpx.MockTransport(handler)).record_click(
        "abc", "https://ref.example"
    )

    assert sent == [b'{"code":"abc","referrer":"https://ref.example"}']


def test_analytics_client_swallows_errors(caplog):
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    client = AnalyticsClient("http://analytics", transport=httpx.MockTransport(handler))
    client.record_click("abc", None)

    assert "not recorded" in caplog.text
