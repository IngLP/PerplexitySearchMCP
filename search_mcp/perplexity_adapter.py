from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any
from typing import TypedDict

# External-Code-Usage-Docs: Model Context Protocol Python library — Context7 LibraryID /modelcontextprotocol/python-sdk — read: 2025-10-03 — installed version: mcp==unknown
# External-Code-Usage-Docs: Perplexity Python SDK — Context7 LibraryID /llmstxt/perplexity_ai-llms-full.txt — read: 2025-10-03 — installed version: perplexity==0.13.0

try:
    # Optional: only used for exception typing heuristics; adapter works without httpx
    import httpx  # type: ignore
except (
    Exception
):  # pragma: no cover - httpx is declared in deps, but keep adapter robust
    httpx = None  # type: ignore


class SearchResult(TypedDict, total=False):
    title: str
    url: str
    date: str  # optional
    last_update: str
    snippet: str


_MIN_RESULTS = 1
_MAX_RESULTS = 30
_DEFAULT_RESULTS = 10


class _TimeoutController:
    """Run a callable in a separate thread and enforce an overall timeout."""

    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s

    def run(self, fn: Callable[[], Any]) -> Any:
        with ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pplx-call"
        ) as executor:
            future: Future[Any] = executor.submit(fn)
            try:
                return future.result(timeout=self._timeout_s)
            except FuturesTimeout as exc:
                # Attempt to cancel; thread will be left to terminate naturally
                future.cancel()
                raise TimeoutError(
                    f"Perplexity search timed out after {int(self._timeout_s * 1000)}ms"
                ) from exc


def _is_transient_error(exc: BaseException) -> bool:
    """Heuristically detect transient connection-level errors suitable for one retry."""
    if httpx is not None:
        if isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.TransportError,
            ),
        ):
            return True
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    # Heuristic fallbacks
    if any(k in name for k in ("timeout", "connect", "network", "transport")):
        return True
    if any(
        k in msg
        for k in (
            "timeout",
            "timed out",
            "connection",
            "transport",
            "temporarily unavailable",
            "try again",
        )
    ):
        return True
    return False


def _validate_query(query: str) -> str:
    q = query.strip()
    if not q:
        raise ValueError("query must be a non-empty string after trimming whitespace")
    if len(q) > 4096:
        raise ValueError("query exceeds maximum length of 4096 characters")
    return q


def _clamp_num_results(n: int | None) -> int:
    if n is None:
        return _DEFAULT_RESULTS
    try:
        v = int(n)
    except Exception as e:
        raise ValueError("num_results must be an integer") from e
    if v < _MIN_RESULTS:
        return _MIN_RESULTS
    if v > _MAX_RESULTS:
        return _MAX_RESULTS
    return v


def _create_client() -> Any:
    # Perplexity client auto-reads PERPLEXITY_API_KEY from env if not passed explicitly
    from perplexity import Perplexity  # type: ignore

    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        # While the SDK can auto-read, we enforce explicit presence for clear errors per PRD
        raise OSError("PERPLEXITY_API_KEY is required but missing or empty")
    return Perplexity()


def _call_search(
    client: Any,
    query: str,
    max_results: int,
) -> Any:
    # API does not support domain filters; always call without it
    return client.search.create(query=query, max_results=max_results)


def _normalize_results(search_response: Any) -> list[SearchResult]:
    # Expecting search_response.results iterable with items having title, url, and optional date
    out: list[SearchResult] = []
    results = getattr(search_response, "results", None)
    if not results:
        return out
    for item in results:
        title = getattr(item, "title", None) or ""
        url = getattr(item, "url", None) or ""
        # date may be absent or None
        date = getattr(item, "date", None)
        snippet = getattr(item, "snippet", None)
        last_update = str(date) if date else ""
        entry: SearchResult = {
            "title": str(title),
            "url": str(url),
            "last_update": last_update,
            "snippet": str(snippet) if snippet else "",
        }
        if date:
            entry["date"] = str(date)
        out.append(entry)
    return out


def search_perplexity(
    query: str,
    num_results: int | None = None,
    *,
    _client_factory: Callable[[], Any] = _create_client,
    _timeout_seconds: float = 5.0,
) -> list[SearchResult]:
    """Execute a Perplexity search and return a normalized list of results.

    Input validation:
    - query: non-empty after trimming, length ≤ 4096
    - num_results: clamped to [1, 30], default 10

    Behavior:
    - Single request via SDK's client.search.create
    - 5s overall timeout
    - 1 retry on transient connection errors only
    """
    q = _validate_query(query)
    max_results = _clamp_num_results(num_results)

    client = _client_factory()

    def invoke() -> list[SearchResult]:
        resp = _call_search(client, q, max_results)
        return _normalize_results(resp)

    controller = _TimeoutController(timeout_s=_timeout_seconds)

    # First attempt
    try:
        return controller.run(invoke)
    except BaseException as exc:
        # Do not retry on validation/auth errors
        if isinstance(exc, (ValueError, EnvironmentError, RuntimeError)):
            raise
        if not _is_transient_error(exc):
            raise
        # Single retry
        try:
            return controller.run(invoke)
        except BaseException as exc2:
            raise Exception(
                f"perplexity_search failed after retry: {exc2.__class__.__name__}: {exc2}"
            ) from exc2
