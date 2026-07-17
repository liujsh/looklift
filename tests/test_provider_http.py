import io
import json
from urllib.error import HTTPError, URLError

import pytest

from looklift import provider_http


class _Response:
    def __init__(self, data: dict):
        self._body = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://api.example", code, "bad", {}, io.BytesIO(b'{"error":"bad"}'))


def test_post_json_sends_json_headers_and_timeout():
    captured = {}

    def opener(request, timeout):
        captured.update(request=request, timeout=timeout)
        return _Response({"ok": True})

    result = provider_http.post_json(
        "https://api.example/v1",
        {"hello": "世界"},
        headers={"Authorization": "Bearer secret"},
        timeout=23,
        opener=opener,
    )

    assert result == {"ok": True}
    assert captured["timeout"] == 23
    assert json.loads(captured["request"].data) == {"hello": "世界"}
    assert captured["request"].get_header("Content-type") == "application/json"
    assert captured["request"].get_header("Authorization") == "Bearer secret"


def test_post_json_retries_5xx_once_without_real_sleep():
    calls = []
    sleeps = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise _http_error(503)
        return _Response({"ok": True})

    assert provider_http.post_json(
        "https://api.example", {}, timeout=10, opener=opener, sleeper=sleeps.append
    ) == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [pytest.approx(0.25)]


def test_post_json_does_not_retry_4xx():
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(401)

    with pytest.raises(provider_http.HTTPStatusError) as exc:
        provider_http.post_json("https://api.example", {}, timeout=10, opener=opener)
    assert exc.value.status == 401
    assert calls == 1


def test_post_json_reports_5xx_after_single_retry():
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(503)

    with pytest.raises(provider_http.HTTPStatusError) as exc:
        provider_http.post_json(
            "https://api.example", {}, timeout=10, opener=opener, sleeper=lambda _: None
        )
    assert exc.value.status == 503
    assert calls == 2


def test_post_json_retries_connection_failure_once():
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise URLError("refused")

    with pytest.raises(provider_http.HTTPConnectionError):
        provider_http.post_json(
            "https://api.example", {}, timeout=10, opener=opener, sleeper=lambda _: None
        )
    assert calls == 2
