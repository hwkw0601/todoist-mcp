# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
A local MCP server (Python + FastMCP, run with `uv`) that gives Claude tools to manage my Todoist
tasks over stdio. The approved plan is in `PLAN.md`. The backend is the Todoist API v1, reached
over HTTPS with a personal token via `httpx` (not the official SDK).

## Commands
- **Run the server:** `uv run server.py` (starts over stdio; logs a startup line to stderr, then
  waits for a client — Ctrl-C to stop).
- **Sync the environment:** `uv sync`. **Add a dependency:** `uv add <pkg>` (venv only — nothing global).
- **Smoke-test tools without a client** (lists tools / calls one in-process):
  ```bash
  uv run python -c "import asyncio; from fastmcp import Client; from server import mcp
  async def m():
      async with Client(mcp) as c:
          print([t.name for t in await c.list_tools()])
  asyncio.run(m())"
  ```
  There is no automated test suite; verification is done live through an MCP client (see `PLAN.md`).

## Architecture
- **Single file:** `server.py` holds everything — the `FastMCP("todoist")` instance, the tools, and
  `main()` (runs `mcp.run(transport="stdio")`). Launched as a script, so `uv run server.py` executes
  the `if __name__ == "__main__"` block. No `src/` package, no console-script entry point.
- **Tools** are `async def` functions decorated with `@mcp.tool`; each returns a plain-text string.
  Their **docstrings are the tool descriptions** Claude reads to decide when to call them.
- **API access:** each tool reads `TODOIST_API_TOKEN` from the environment at call time, builds an
  `Authorization: Bearer` header, and calls `API_BASE` (`https://api.todoist.com/api/v1`) with a
  per-call `httpx.AsyncClient`. `list_active_tasks` follows `next_cursor` pagination.
- **Formatting helpers:** `_format_due` and `_format_task` turn API JSON into the one-line-per-task
  plain text the tools return.
- **Config:** `TODOIST_API_TOKEN` is loaded from `.env` via `python-dotenv` at import.

## Rules
- **Never print to stdout.** stdout carries the MCP protocol; use `logging` to **stderr** only.
- **Every tool** has a clear docstring and logs what it's doing with `logging.info()`.
- **Write boundaries:** `list_active_tasks` and `list_completed_tasks` are read-only. `create_task`
  (creates), `set_task_status` (complete/reopen), and `update_task` (change a task's due date/time,
  name, or labels) change data. **Never add a tool that deletes, bulk-edits, or changes
  projects/sections.**
- **Secrets:** the only secret is `TODOIST_API_TOKEN`, read from `.env`. `.env` is never committed;
  the token must never reach stdout, logs, or any returned/error message.
- **Privacy:** task content enters Claude's context only when listed; don't log full task contents.
- **Process:** add one tool at a time and stop after each phase. Follow `PLAN.md`. Ask before
  restructuring. Build only what is asked — nothing extra.

## Timezone
My account timezone is **Asia/Seoul (UTC+9)**. For `create_task`, send `due_datetime` as a floating
local datetime (no `Z`/offset) so Todoist applies the account timezone.
