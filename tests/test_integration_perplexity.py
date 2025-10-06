import os

import pytest

from search_mcp.perplexity_adapter import search_perplexity


pytestmark = pytest.mark.skipif(
    not os.getenv("PERPLEXITY_API_KEY"),
    reason="PERPLEXITY_API_KEY not set; skipping real Perplexity API integration test",
)


def test_real_perplexity_search_smoke() -> None:
    """Smoke test against the real Perplexity Search API.

    - Uses num_results=1 to minimize cost/time.
    - Ensures call succeeds and returns the documented shape when results exist.
    """
    results = search_perplexity("latest AI developments 2024", num_results=1, _timeout_seconds=5.0)
    assert isinstance(results, list)
    if results:
        first = results[0]
        assert "title" in first and isinstance(first["title"], str)
        assert "url" in first and isinstance(first["url"], str)
        # date is optional