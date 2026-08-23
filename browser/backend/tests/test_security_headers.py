"""Every response from the app carries the browser-hardening headers set by SecurityHeadersMiddleware."""
from __future__ import annotations

import httpx
import pytest

from app import app
from security_headers import SECURITY_HEADERS


def _csp_directives() -> dict[str, str]:
    directives = SECURITY_HEADERS["Content-Security-Policy"].split("; ")
    return {name: value for name, _, value in (d.partition(" ") for d in directives)}


@pytest.mark.parametrize("path", ["/api/summary/titles", "/api/no-such-route"])
async def test_security_headers_present_on_every_response(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def test_csp_forbids_inline_scripts_framing_and_plugins():
    directives = _csp_directives()
    assert directives["script-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"
    assert directives["connect-src"] == "'self'"
