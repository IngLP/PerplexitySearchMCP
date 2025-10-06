from typing import Any

import pytest

import search_mcp.server as srv


def _fake_results() -> list[dict[str, str]]:
    return [
        {"title": "A", "url": "https://a", "date": "2024-01-01"},
        {"title": "B", "url": "https://b"},
    ]


def test_tool_happy_path_monkeypatched(monkeypatch) -> None:
    # Arrange: monkeypatch adapter call inside server
    called: dict[str, Any] = {}

    def _fake_search_perplexity(query: str, num_results: int | None = None):
        called["query"] = query
        called["num_results"] = num_results
        return _fake_results()

    monkeypatch.setattr(srv, "search_perplexity", _fake_search_perplexity)

    # Act
    out = srv.perplexity_search(
        query="hello world",
        num_results=7,
    )

    # Assert
    assert out == {"results": _fake_results()}
    assert called["query"] == "hello world"
    assert called["num_results"] == 7


def test_tool_bubbles_validation_error(monkeypatch) -> None:
    def _raise_validation(*args, **kwargs):
        raise ValueError("query must be non-empty")

    monkeypatch.setattr(srv, "search_perplexity", _raise_validation)

    with pytest.raises(ValueError):
        srv.perplexity_search(query="   ", num_results=10)


def test_logging_includes_requested_fields(monkeypatch, capsys) -> None:
    """Configure logging and verify key fields are present in output.

    We do not assert the full structlog shape to avoid brittleness across environments,
    but we do check presence of critical fields:
    - full query
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
    )
    assert isinstance(out, dict) and "results" in out

    captured = capsys.readouterr().out
    # Start log should contain our fields
    assert "perplexity_search.start" in captured
    assert "observability test" in captured  # full query present
    assert "num_results" in captured


def test_tool_rejects_unknown_param() -> None:
    # Passing an unsupported argument should fail fast at call-time (schema/signature)
    import search_mcp.server as srv  # local import to avoid circulars in other tests
    import pytest

    with pytest.raises(TypeError):
        srv.perplexity_search(
            query="hello", num_results=1, search_domain_filter=["example.com"]
        )
