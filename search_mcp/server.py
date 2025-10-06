from __future__ import annotations

import logging
import os
import sys
import time
import uuid

import structlog
from mcp.server.fastmcp import FastMCP

from .perplexity_adapter import search_perplexity

# External-Code-Usage-Docs: Model Context Protocol Python library — Context7 LibraryID /modelcontextprotocol/python-sdk — read: 2025-10-03 — installed version: mcp==unknown
# External-Code-Usage-Docs: Perplexity Python SDK — Context7 LibraryID /llmstxt/perplexity_ai-llms-full.txt — read: 2025-10-03 — installed version: perplexity==0.13.0


def _parse_log_level(value: str | None) -> int:
    if not value:
        return logging.INFO
    try:
        # Allow numeric or name
        if value.isdigit():
            return int(value)
        return getattr(logging, value.upper())
    except Exception:
        return logging.INFO


def configure_logging() -> None:
    """Configure structlog and stdlib logging for JSON/console based on environment."""
    log_format = os.getenv("LOG_FORMAT", "").strip().lower()
    use_console = False
    if log_format == "console":
        use_console = True
    elif log_format == "json":
        use_console = False
    else:
        # Default: console if stdout is a TTY, otherwise JSON
        use_console = sys.stdout.isatty()

    level = _parse_log_level(os.getenv("LOG_LEVEL"))

    # Configure stdlib root logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logging.basicConfig(level=level, handlers=[handler], force=True)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor
    if use_console:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *processors,
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


mcp = FastMCP("Perplexity Search MCP")


@mcp.tool()
def perplexity_search(
    query: str,
    num_results: int = 10,
) -> dict:
    """Run a Perplexity Search and return structured results.

    Inputs:
      - query: str (required)
      - num_results: int (default 10, clamped to [1,30])

    Output:
      - { "results": [ { "title": str, "url": str, "date": str?, "last_update": str, "snippet": str }, ... ] }
    """
    logger = structlog.get_logger()

    request_id = uuid.uuid4().hex
    start = time.perf_counter()

    query_length = len(query) if isinstance(query, str) else 0

    base_log = {
        "request_id": request_id,
        "query": query,
        "query_length": query_length,
        "num_results": num_results,
        "timeout_ms": 5000,
    }

    logger.info("perplexity_search.start", **base_log)

    try:
        results = search_perplexity(
            query=query,
            num_results=num_results,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "perplexity_search.success",
            **base_log,
            result_count=len(results),
            duration_ms=duration_ms,
            provider_status="ok",
        )
        return {"results": results}
    except ValueError:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(
            "perplexity_search.invalid_input",
            **base_log,
            duration_ms=duration_ms,
            provider_status="invalid_input",
            exc_info=True,
        )
        raise
    except (OSError, RuntimeError):
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "perplexity_search.auth_error",
            **base_log,
            duration_ms=duration_ms,
            provider_status="auth_error",
            exc_info=True,
        )
        raise
    except Exception as e:  # Provider/network failures bubbled up from adapter
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "perplexity_search.provider_error",
            **base_log,
            duration_ms=duration_ms,
            provider_status="provider_error",
            exc_info=True,
        )
        # Re-raise as a concise MCP-surfaced error message (no HTTP mapping)
        raise Exception(f"perplexity_search failed: {e.__class__.__name__}: {e}") from e


def main() -> None:
    configure_logging()
    mcp.run()


if __name__ == "__main__":
    main()
