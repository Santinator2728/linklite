import httpx
import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from redirect_service.clients import (
    DEPENDENCY_CALL_SECONDS,
    AnalyticsClient,
    LinkClient,
    LinkServiceError,
)
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


def test_analytics_client_marks_rejected_click_as_error(caplog):
    before = dependency_calls("analytics", "error")
    client = AnalyticsClient(
        "http://analytics", transport=httpx.MockTransport(lambda req: httpx.Response(422))
    )

    client.record_click("abc", None)

    assert dependency_calls("analytics", "error") == before + 1
    assert "status 422" in caplog.text


# --- Metrics (XP-45) ---------------------------------------------------------


DEPENDENCY_REGISTRY = CollectorRegistry()
DEPENDENCY_REGISTRY.register(DEPENDENCY_CALL_SECONDS)


def dependency_calls(dependency, outcome):
    labels = {"dependency": dependency, "outcome": outcome}
    value = DEPENDENCY_REGISTRY.get_sample_value("linklite_dependency_call_seconds_count", labels)
    return value or 0


def test_metrics_endpoint_is_not_taken_by_the_redirect_route(analytics):
    links = FakeLinks(error=AssertionError("/metrics must not be looked up as a short code"))
    client = make_client(links, analytics)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_redirects_are_counted_per_route(analytics):
    client = make_client(FakeLinks({"abc1234": "https://example.com"}), analytics)
    client.get("/abc1234")

    body = client.get("/metrics").text

    assert 'http_requests_total{handler="/{code}",method="GET",status="3xx"}' in body


def test_link_client_times_successful_and_failed_calls():
    ok_before = dependency_calls("link", "ok")
    error_before = dependency_calls("link", "error")

    link_client(lambda req: httpx.Response(404)).resolve("a")
    with pytest.raises(LinkServiceError):
        link_client(lambda req: httpx.Response(500)).resolve("a")

    assert dependency_calls("link", "ok") == ok_before + 1
    assert dependency_calls("link", "error") == error_before + 1


def test_analytics_client_times_recorded_clicks():
    before = dependency_calls("analytics", "ok")
    client = AnalyticsClient(
        "http://analytics", transport=httpx.MockTransport(lambda req: httpx.Response(202))
    )

    client.record_click("abc", None)

    assert dependency_calls("analytics", "ok") == before + 1


def test_dependency_times_are_published_by_the_redirect_app(analytics):
    client = make_client(FakeLinks(), analytics)
    link_client(lambda req: httpx.Response(404)).resolve("a")

    assert "linklite_dependency_call_seconds_count" in client.get("/metrics").text
