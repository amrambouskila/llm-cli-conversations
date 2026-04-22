"""Unit tests for _parse_cors_origins — exercises default/override/edge paths."""
from __future__ import annotations

from app import _DEFAULT_CORS_ORIGINS, _parse_cors_origins


def test_parse_cors_origins_none_returns_default() -> None:
    parsed = _parse_cors_origins(None)
    assert parsed == [
        "http://localhost:5174",
        "http://localhost:5050",
        "http://127.0.0.1:5174",
    ]
    assert ",".join(parsed) == _DEFAULT_CORS_ORIGINS


def test_parse_cors_origins_single_value() -> None:
    assert _parse_cors_origins("https://example.com") == ["https://example.com"]


def test_parse_cors_origins_multiple_comma_separated() -> None:
    assert _parse_cors_origins("https://a.example,https://b.example,https://c.example") == [
        "https://a.example",
        "https://b.example",
        "https://c.example",
    ]


def test_parse_cors_origins_strips_whitespace() -> None:
    assert _parse_cors_origins(" https://a.example , https://b.example ") == [
        "https://a.example",
        "https://b.example",
    ]


def test_parse_cors_origins_empty_string_returns_empty_list() -> None:
    # Explicit `CORS_ORIGINS=""` means "no CORS origins allowed" — the user
    # chose empty rather than unset. We do not fall back to the default here
    # because that would override an explicit lockdown.
    assert _parse_cors_origins("") == []


def test_parse_cors_origins_filters_empty_entries() -> None:
    assert _parse_cors_origins("https://a.example,,,https://b.example,") == [
        "https://a.example",
        "https://b.example",
    ]
