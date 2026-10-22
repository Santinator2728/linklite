import pytest

from link_service.validation import MAX_URL_LENGTH, InvalidURLError, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1#frag",
        "https://sub.example.co.uk:8443/a/b",
        "HTTPS://EXAMPLE.COM",
    ],
)
def test_accepts_valid_http_urls(url):
    assert validate_url(url) == url


def test_strips_surrounding_whitespace():
    assert validate_url("  https://example.com  ") == "https://example.com"


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "must not be empty"),
        ("   ", "must not be empty"),
        ("javascript:alert(1)", "Only http and https"),
        ("data:text/html,<script>alert(1)</script>", "Only http and https"),
        ("ftp://example.com/file", "Only http and https"),
        ("file:///etc/passwd", "Only http and https"),
        ("example.com", "Only http and https"),
        ("https://", "must include a host"),
        ("https://user:pass@example.com", "embedded credentials"),
        ("https://trusted.com@evil.com", "embedded credentials"),
        ("https://example.com:99999", "invalid port"),
        ("https://exa mple.com", "spaces or control characters"),
        ("https://example.com/\x00", "spaces or control characters"),
    ],
)
def test_rejects_invalid_or_dangerous_urls(url, reason):
    with pytest.raises(InvalidURLError, match=reason):
        validate_url(url)


def test_rejects_urls_over_the_length_limit():
    url = "https://example.com/" + "a" * MAX_URL_LENGTH
    with pytest.raises(InvalidURLError, match="at most"):
        validate_url(url)
