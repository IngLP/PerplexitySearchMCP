# Perplexity Search MCP — PRD

Status: Draft
Last updated: 2025-10-06

## Vision

Deliver a minimal, reliable MCP server exposing a single tool "perplexity_search" that returns structured web search results using the Perplexity Python SDK search.create, configured via the PERPLEXITY_API_KEY environment variable. The server emphasizes fast responses, safe defaults, and observability via structlog. It explicitly excludes any LLM/sonar endpoints and any pagination. It supports a num_results parameter with default 10 and maximum 30, and an optional domain filter to constrain sources. The query is a single string.

## Key decisions agreed for Vision

- Tool name: perplexity_search
- Input shape: query (str); num_results (int, default 10, max 30); search_domain_filter (list of str, optional)
- SDK call: client.search.create
- Config: PERPLEXITY_API_KEY environment variable
- Logging: structlog
- Runtime: Python 3.12+, uv for packaging and workflow

## Goals and Non-Goals

### Goals

- Provide a single MCP tool "perplexity_search" that invokes the Perplexity Python SDK search.create.
- Inputs:
  - query: str (required)
  - num_results: int (default 10, max 30)
  - search_domain_filter: list[str] (optional, include-only domains)
- Output: structured list of results with: title, url, optional date, and always include last_update and snippet. Stable JSON shape documented in this PRD.
- Configuration: PERPLEXITY_API_KEY environment variable (no other secret sources).
- Observability: structlog with request_id, duration_ms, result_count, provider_status; never log secrets.
- Reliability: sensible request timeout and minimal retry on transient network errors; clear MCP error mapping for SDK exceptions.
- Simplicity: minimal footprint, no extra features beyond the agreed scope.

### Non-Goals

- Any LLM/sonar/generation endpoints; summarization; snippet generation.
- Pagination or multi-query (no list[str] for query).
- Source scraping or downloading content; only metadata/links.
- Advanced filters (besides search_domain_filter) or ranking customization.
- Caching, persistence, or background jobs.
- Rollout/ops playbooks; containerization; CI/CD.

## Scope (MVP)

- One MCP tool: "perplexity_search".
- Inputs:
  - query: str (required)
  - num_results: int (default 10; clamped to [1, 30])
  - search_domain_filter: list[str] (optional, include-only domains)
- Behavior:
  - No pagination.
  - Search executed via Perplexity Python SDK [python.client.search.create()](README.md:1); a single request returns up to num_results.
  - Output: stable JSON object:
    - results: list of objects with keys: title (str), url (str), date (str, optional when available), last_update (str), snippet (str)
- Configuration: PERPLEXITY_API_KEY environment variable.
- Observability: structlog-enabled logging (no secrets in logs).

## Functional Requirements

### Tool

- Name: "perplexity_search"
- Implementation: Perplexity Python SDK via [python.Perplexity()](README.md:1) and [python.client.search.create()](README.md:1)

### Inputs and validation

- query: str (required). Must be non-empty after trimming whitespace.
- num_results: int (default 10; clamped to [1, 30]). Values \<1 become 1; values >30 become 30.
- search_domain_filter: list[str] (optional). If provided, must be a non-empty list of non-empty domain strings (hostnames). Duplicates are ignored; schema/protocol not allowed.

### Behavior

- Client initialization: Instantiate Perplexity client using env-based auth (PERPLEXITY_API_KEY) via [python.Perplexity()](README.md:1). If the env var is missing/empty, raise [python.EnvironmentError()](README.md:1) (or [python.RuntimeError()](README.md:1)).
- Search invocation: Call [python.client.search.create()](README.md:1) with:
  - query = query
  - max_results = num_results
  - search_domain_filter = search_domain_filter (only if provided)
- Timeout: Apply an overall request timeout of 5 seconds for the search call.
- Retry: Perform 1 retry only on transient connection errors; no retry on authentication or validation errors.
- Pagination: None. A single request returns up to num_results.

### Output (MCP tool result)

- JSON object with stable shape:
  - results: list of objects, each containing:
    - title: str
    - url: str
    - date: str (optional; present only when provided by the SDK)
    - last_update: str
    - snippet: str

### Errors (MCP-aligned)

- Invalid input (e.g., empty query, invalid num_results, invalid domain list) → raise [python.ValueError()](README.md:1) with a clear message.
- Missing/invalid API key → raise [python.EnvironmentError()](README.md:1) (or [python.RuntimeError()](README.md:1)).
- Provider/network failures → catch SDK/network exceptions and re-raise a generic [python.Exception()](README.md:1) with a concise message (no HTTP-style status mapping). FastMCP surfaces tool exceptions to the client.

### Logging (structlog)

- Emit structured logs with fields: request_id, query (full string), domain_filter (full list), query_length, domain_filter_count, num_results, duration_ms, result_count, provider_status (string if available).
- Never log secrets.

### Configuration

- Environment variable: PERPLEXITY_API_KEY
- No other configuration sources.

## Technical Design Overview

Components (refer to Vision, Goals/Non‑Goals, Scope, and Functional Requirements for details; this section avoids repetition):

- FastMCP server (stdio transport).
- Single tool "perplexity_search".
- Perplexity adapter module encapsulating SDK usage, timeout, retry, and clamping.

File layout

- [search_mcp/server.py](search_mcp/server.py): FastMCP app initialization and tool definition.
  - Create server via [python.FastMCP()](README.md:1).
  - Define tool via decorator [python.@mcp.tool()](README.md:1) with function name/docstring as metadata.
  - Entrypoint calls [python.mcp.run()](README.md:1) to serve over stdio.
  - Initialize structlog in JSON mode; never log secrets. Log full query and full domain_filter as per Observability.
- [search_mcp/perplexity_adapter.py](search_mcp/perplexity_adapter.py): Perplexity SDK integration.
  - Client factory using [python.Perplexity()](README.md:1) that reads PERPLEXITY_API_KEY at call time.
  - Wrapper function (e.g., search(query: str, max_results: int, search_domain_filter: list[str] | None) -> list[dict]) calls [python.client.search.create()](README.md:1), applies clamping (1–30), 5s overall timeout, and 1 retry on transient connection errors. Returns a normalized list of {title, url, date?, last_update, snippet} dicts.

Execution and installation (command-launchable)

- Development (stdio): uv run search_mcp/server.py
- Installed CLI command: provide a console script "perplexity-search-mcp" that invokes server.main (to start the FastMCP server over stdio).
  - Example pyproject entry (implementation detail; not repeated here): [project.scripts] perplexity-search-mcp = "search_mcp.server:main"
- Editor discovery (MCP registry):
  - Register the server entry with: uv run mcp install search_mcp/server.py
  - After installation, the tool can be launched via the command "perplexity-search-mcp" as desired.

Control flow (references to FR)

1. Validate inputs (query non-empty; num_results clamped to 1–30; search_domain_filter when provided is non-empty list of non-empty domains).
1. Initialize log context (request_id, query, domain_filter, query_length, num_results, domain_filter_count).
1. Build client with [python.Perplexity()](README.md:1) reading PERPLEXITY_API_KEY.
1. Call [python.client.search.create()](README.md:1) with query, max_results, and search_domain_filter (if provided); 5s timeout; 1 retry on connection errors only.
1. Return stable JSON: { results: [{ title, url, date?, last_update, snippet }] }.
1. Raise exceptions per FR for invalid inputs, missing API key, and provider/network failures (no HTTP-style mappings).

Transport and schema

- Transport: stdio only.
- Schemas: input/output JSON Schema inferred from Python type hints in the tool function (no manual schema duplication needed).

Configuration

- Environment variable: PERPLEXITY_API_KEY (single source).
- No .env or alternate secret sources.

## Security & Privacy

Secrets

- Single secret: PERPLEXITY_API_KEY read from environment at call time.
- Never persist or echo secrets; do not include secrets in errors.
- Fail closed if the key is missing/empty with a clear, concise error message.

Input validation

- query: trim whitespace; must be non-empty; maximum length 4096 characters (longer inputs rejected).
- num_results: clamp to [1, 30] (as defined in Scope/FR).
- search_domain_filter: when provided, must be a non-empty list of ASCII hostnames (a–z, 0–9, dot, hyphen). Each item max length 253 characters; drop duplicates; reject invalid items.

Data handling

- No caching or persistence; responses are processed in-memory per request only.
- Output includes only metadata from the SDK (title, url, date?, last_update, snippet); no content scraping or storage.

Logging (privacy by default, explicit allowances)

- Use structured JSON logging (structlog).
- Log: request_id, query (full string), domain_filter (full list), query_length, domain_filter_count, num_results, result_count, duration_ms, and provider_status when available.
- Never log secrets. Avoid logging stack traces for expected validation/auth errors.

Timeouts and retries

- Apply a 5s overall timeout per request.
- Perform 1 retry only on transient connection errors; do not retry on auth/validation errors.

Least privilege & attack surface

- Only outbound calls are via the Perplexity Python SDK; no other network access.
- No file I/O and no dynamic code or shell execution.

Error messages

- Use concise, user-actionable messages without leaking sensitive details or internal state.

## Observability & Rate Limits

Observability (structlog + stdlib logging)

- Goals: unified JSON logs by default; console-friendly logs in local TTY; preserve stdlib logs; consistent per-request context.
- Initialization (server startup):
  - Configure stdlib root logger with a single StreamHandler to stdout using a processor formatter ([python.ProcessorFormatter()](README.md:1)).
  - Renderer selection: JSON by default ([python.JSONRenderer()](README.md:1)). If LOG_FORMAT=console or stdout is a TTY and LOG_FORMAT unset, use [python.ConsoleRenderer()](README.md:1).
  - Root level derived from LOG_LEVEL (numeric or name). Optional library level overrides via LOG_LIB_LEVELS (e.g., "httpx=INFO").
  - Structlog processors chain:
    - Base chain (order): merge_contextvars; add_logger_name; add_log_level; ISO-UTC timestamp; stack info renderer; format_exc_info.
      - References: [python.structlog.contextvars.merge_contextvars()](README.md:1), [python.structlog.stdlib.add_logger_name()](README.md:1), [python.structlog.stdlib.add_log_level()](README.md:1), [python.structlog.processors.TimeStamper()](README.md:1), [python.structlog.processors.StackInfoRenderer()](README.md:1), [python.structlog.processors.format_exc_info()](README.md:1).
    - Foreign stdlib logs pre-chain: [python.structlog.stdlib.ExtraAdder()](README.md:1), [python.structlog.stdlib.PositionalArgumentsFormatter()](README.md:1), then the same base chain.
    - Finish with [python.structlog.stdlib.ProcessorFormatter.wrap_for_formatter()](README.md:1) to route through the stdlib handler.
  - Single point of control: all library/component loggers propagate to root; remove extra handlers to avoid duplicates.
- Per-request context and fields:
  - Generate a request_id per tool invocation; bind it at the start of the call.
  - Log fields per request: request_id, query (full string), domain_filter (full list), query_length, domain_filter_count, num_results, result_count, duration_ms, provider_status (string if available), timeout_ms, retry_attempts.
  - Never log secrets. Avoid stack traces for expected validation/auth errors; include exception type and concise message.
- Development toggles:
  - LOG_FORMAT in {"json","console"}; LOG_LEVEL (e.g., "DEBUG", "INFO", 20); LOG_LIB_LEVELS for fine-grained library levels (comma-separated "logger=LEVEL" entries).

Rate limits

- Behavior on rate limiting:
  - Surface a concise tool error message to the caller; do not auto-wait. Log provider_status="rate_limited" and include retry_after (ms/s) if exposed by the SDK.
- Retries/backoff:
  - No custom backoff beyond the single retry on transient connection errors defined in Functional Requirements. Fail fast and let callers decide.
