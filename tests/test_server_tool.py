import json
from typing import Any, List

import pytest

import search_mcp.server as srv


def _fake_results() -> List[dict[str, str]]:
    return [
        {"title": "A", "url": "https://a", "date": "2024-01-01"},
        {"title": "B", "url": "https://b"},
    ]


def test_tool_happy_path_monkeypatched(monkeypatch) -> None:
    # Arrange: monkeypatch adapter call inside server
    called: dict[str, Any] = {}

    def _fake_search_perplexity(query: str, num_results: int | None = None, search_domain_filter=None):
        called["query"] = query
        called["num_results"] = num_results
        called["search_domain_filter"] = search_domain_filter
        return _fake_results()

    monkeypatch.setattr(srv, "search_perplexity", _fake_search_perplexity)

    # Act
    out = srv.perplexity_search(
        query="hello world",
        num_results=7,
        search_domain_filter=["example.com"],
    )

    # Assert
    assert out == {"results": _fake_results()}
    assert called["query"] == "hello world"
    assert called["num_results"] == 7
    assert called["search_domain_filter"] == ["example.com"]


def test_tool_bubbles_validation_error(monkeypatch) -> None:
    def _raise_validation(*args, **kwargs):
        raise ValueError("query must be non-empty")

    monkeypatch.setattr(srv, "search_perplexity", _raise_validation)

    with pytest.raises(ValueError):
        srv.perplexity_search(query="   ", num_results=10, search_domain_filter=None)


def test_logging_includes_requested_fields(monkeypatch, capsys) -> None:
    """Configure logging and verify key fields are present in output.

    We do not assert the full structlog shape to avoid brittleness across environments,
    but we do check presence of critical fields as per PRD and user decision:
    - full query
    - full domain_filter
    - num_results
    """
    # Make logging console to simplify capture
    monkeypatch.setenv("LOG_FORMAT", "console")
    # Reconfigure logging fresh
    srv.configure_logging()

    # Patch adapter to avoid network
    monkeypatch.setattr(srv, "search_perplexity", lambda **kwargs: _fake_results())

    out = srv.perplexity_search(
        query="observability test",
        num_results=9,
        search_domain_filter=["foo.com", "bar.org"],
    )
    assert isinstance(out, dict) and "results" in out

    captured = capsys.readouterr().out
    # Start log should contain our fields
    assert "perplexity_search.start" in captured
    assert "observability test" in captured  # full query present
    assert "['foo.com', 'bar.org']" in captured  # full domain_filter present
    assert "num_results" in captured