"""Validation of user-supplied URLs before they are stored as short links."""

from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = frozenset({"http", "https"})


class InvalidURLError(ValueError):
    """Raised when a URL cannot be accepted as a short-link target."""


def validate_url(raw_url: str) -> str:
    """Return the cleaned URL, or raise InvalidURLError with a user-facing reason."""
    url = raw_url.strip()
    if not url:
        raise InvalidURLError("URL must not be empty")
    if len(url) > MAX_URL_LENGTH:
        raise InvalidURLError(f"URL must be at most {MAX_URL_LENGTH} characters")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise InvalidURLError("URL must not contain spaces or control characters")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidURLError("Only http and https URLs are allowed")
    if not parts.hostname:
        raise InvalidURLError("URL must include a host")
    if parts.username is not None or parts.password is not None:
        # "https://trusted.com@evil.com" is a classic phishing trick.
        raise InvalidURLError("URLs with embedded credentials are not allowed")
    try:
        parts.port  # noqa: B018 - accessing .port validates it
    except ValueError as exc:
        raise InvalidURLError("URL has an invalid port") from exc

    return url
