import os
import time
from typing import Any, List, Optional

import pytest

from search_mcp.perplexity_adapter import search_perplexity


class _FakeResult:
    def __init__(self, title: str, url: str, date: Optional[str] = None, snippet: Optional[str] = None) -> None:
        self.title = title
        self.url = url
        self.date = date
        self.snippet = snippet


class _FakeResponse:
    def __init__(self, results: list[_FakeResult]) -> None:
        self.results = results


class _FakeClient:
    def __init__(self, response: Any) -> None:
        class _Search:
            def __init__(self, outer: "_FakeClient") -> None:
                self._outer = outer

            def create(self, *, query: str, max_results: int, search_domain_filter: list[str] | None = None) -> Any:
                self._outer.last_query = query
                self._outer.last_max_results = max_results
                self._outer.last_filter = search_domain_filter
                return response

        self.search = _Search(self)
        self.last_query: str | None = None
        self.last_max_results: int | None = None
        self.last_filter: list[str] | None = None


def _factory_from_client(c: Any):
    def _factory() -> Any:
        return c

    return _factory


def test_query_validation_rejects_empty() -> None:
    with pytest.raises(ValueError) as ei:
        search_perplexity(
            query="   ",
            _client_factory=lambda: None,  # must not be called if validation happens first
        )
    assert "non-empty" in str(ei.value)


def test_query_validation_rejects_too_long() -> None:
    with pytest.raises(ValueError):
        search_perplexity("x" * 4097, _client_factory=lambda: None)


def test_num_results_default_and_clamping() -> None:
    response = _FakeResponse([_FakeResult("t", "u")])
    client = _FakeClient(response)

    # default -> 10
    out = search_perplexity("hello", None, _client_factory=_factory_from_client(client))
    assert isinstance(out, list)
    assert client.last_max_results == 10

    # clamp low -> 1
    out = search_perplexity("hello", 0, _client_factory=_factory_from_client(client))
    assert client.last_max_results == 1

    # clamp high -> 30
    out = search_perplexity("hello", 99, _client_factory=_factory_from_client(client))
    assert client.last_max_results == 30


def test_domain_filter_normalization_and_duplicates() -> None:
    response = _FakeResponse([_FakeResult("t", "https://a")])
    client = _FakeClient(response)

    out = search_perplexity(
        "hello",
        5,
        ["Example.com", "example.com", "sub.domain.com"],
        _client_factory=_factory_from_client(client),
    )
    # duplicates collapsed and normalized to lowercase
    assert client.last_filter == ["example.com", "sub.domain.com"]

    # invalid hostname with path should raise
    with pytest.raises(ValueError):
        search_perplexity("hello", 5, ["good.com", "bad.com/path"], _client_factory=_factory_from_client(client))


def test_retry_on_transient_connect_error(monkeypatch) -> None:
    import httpx  # ensure installed per deps

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

            class _Search:
                def __init__(self, outer: "_FlakyClient") -> None:
                    self._outer = outer

                def create(self, *, query: str, max_results: int, search_domain_filter: list[str] | None = None):
                    self._outer.calls += 1
                    if self._outer.calls == 1:
                        # First call simulates transient connection error
                        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://api.perplexity.ai"))
                    return _FakeResponse([_FakeResult("ok", "https://x")])

            self.search = _Search(self)

    client = _FlakyClient()
    out = search_perplexity("retry me", 3, _client_factory=lambda: client)
    assert isinstance(out, list)
    assert client.calls == 2


def test_timeout_errors_out_fast() -> None:
    class _SlowClient:
        class _Search:
            @staticmethod
            def create(*, query: str, max_results: int, search_domain_filter: list[str] | None = None):
                time.sleep(0.2)
                return _FakeResponse([_FakeResult("late", "https://z")])

        def __init__(self) -> None:
            self.search = _SlowClient._Search()

    with pytest.raises(TimeoutError):
        search_perplexity("slow", 3, _client_factory=lambda: _SlowClient(), _timeout_seconds=0.05)


def test_output_shape_normalization() -> None:
    response = _FakeResponse(
        [
            _FakeResult("Title A", "https://a", "2024-01-01", "Alpha snippet"),
            _FakeResult("Title B", "https://b"),
        ]
    )
    client = _FakeClient(response)
    out = search_perplexity("normalize", 2, _client_factory=_factory_from_client(client))
    assert out == [
        {"title": "Title A", "url": "https://a", "date": "2024-01-01", "last_update": "2024-01-01", "snippet": "Alpha snippet"},
        {"title": "Title B", "url": "https://b", "last_update": "", "snippet": ""},
    ]