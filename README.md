# Perplexity Search MCP

Minimal MCP server exposing a single tool `perplexity_search` that returns structured web search results using the Perplexity Python SDK (`client.search.create`). Configuration via `PERPLEXITY_API_KEY`. Structured logging with structlog. No LLM/sonar endpoints and no pagination.

Status: MVP

## Quick start

Editor MCP config example (mcp-settings.json)

This config launches the server via uvx, pulling directly from the Git remote. Set PERPLEXITY_API_KEY in env.

```json
{
  "mcpServers": {
    "perplexity-search-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/IngLP/PerplexitySearchMCP.git@main",
        "perplexity-search-mcp"
      ],
      "env": {
        "PERPLEXITY_API_KEY": "pplx-...",
        "LOG_FORMAT": "console"
      }
    }
  }
}
```

## Features

- One MCP tool: `perplexity_search`
- Inputs:
  - `query`: str (required, non-empty after trim, max length 4096)
  - `num_results`: int (default 10, clamped to [1, 30])
- Output: `{ "results": [ { "title": str, "url": str, "date": str?, "last_update": str, "snippet": str }, ... ] }`
- Observability: structlog JSON/console logs with per-request context
- Timeout and retry: 5s overall timeout; single retry on transient connection errors only
- Configuration: `PERPLEXITY_API_KEY` in environment

## Behavioral details

- No pagination; a single call returns up to `num_results`
- Transient error handling: one retry only on connection-level errors
- Timeout: 5 seconds total per provider call
- Exceptions surfaced as tool errors (no HTTP-style mapping)

## Logging

- Structured logging with structlog
- Startup config chooses JSON by default; console when `LOG_FORMAT=console` or stdout is a TTY and `LOG_FORMAT` unset
- Per-request fields:
  - `request_id`, `query` (full string), `query_length`, `num_results`, `result_count`, `duration_ms`, `provider_status`, `timeout_ms`
- Never log secrets. Validation/auth errors log as warnings/errors with concise messages.

## Environment variables

- `PERPLEXITY_API_KEY`: Perplexity API key (required)
- `LOG_FORMAT`: `json` or `console` (optional)
- `LOG_LEVEL`: e.g., `INFO`, `DEBUG`, or numeric (optional)

## Project layout

- Server and tool: search_mcp/server.py
- Provider adapter: search_mcp/perplexity_adapter.py
- Tests: tests/

## Development workflows

- Run tests

```
uv run pytest
```

- Pre-commit (runs linters, mypy, mdformat, and pytest)

```
uv run pre-commit run -a || uv run pre-commit run -a || uv run pre-commit run -a
```

- Integration test (real API)
  - Skipped unless `PERPLEXITY_API_KEY` is set
  - Executes a single real query with `num_results=1`

## Notes and constraints

- No LLM/sonar chat completions in this server (out of scope)
- No caching, persistence, or scraping
- Output is stable: `title`, `url`, optional `date`, plus `last_update` and `snippet` for all results

## Security

- Only reads `PERPLEXITY_API_KEY` from the environment at call time
- Fails closed with clear error if key is missing/empty
- Error messages are concise and do not leak sensitive data
