"""Local Todoist MCP server.

Gives Claude a small set of tools to manage Todoist tasks over stdio. Talks to
the Todoist API v1 over HTTPS using a personal API token read from the
environment (loaded from .env).

Rules (see CLAUDE.md): nothing is ever written to stdout except the MCP protocol
itself; all logging goes to stderr; the API token is never logged or included in
any message returned to the client.
"""

import logging
import os
import sys

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

# Log to stderr only. stdout is reserved for the MCP (stdio) protocol — writing
# anything else there would corrupt the client connection.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("todoist")

load_dotenv()

API_BASE = "https://api.todoist.com/api/v1"
TOKEN_ENV = "TODOIST_API_TOKEN"

mcp = FastMCP("todoist")


def _format_due(due: dict | None) -> str:
    """Render a task's due object as a short human-readable string, or ''."""
    if not due:
        return ""
    # The v1 due object may carry a date-only or date+time value plus a
    # natural-language string. Prefer the explicit datetime/date; fall back to
    # the string. Be defensive about which keys are present.
    when = due.get("datetime") or due.get("date") or ""
    text = due.get("string") or ""
    if when and text and text != when:
        return f"{when} ({text})"
    return when or text


def _format_task(task: dict) -> str:
    """Render one task as a single plain-text line."""
    task_id = task.get("id", "?")
    name = task.get("content", "(no name)")
    parts = [f"- [{task_id}] {name}"]
    due = _format_due(task.get("due"))
    if due:
        parts.append(f"due: {due}")
    labels = task.get("labels") or []
    if labels:
        parts.append(f"labels: {', '.join(labels)}")
    return " | ".join(parts)


@mcp.tool
async def list_active_tasks() -> str:
    """List my current open Todoist tasks.

    Use when the user asks what is on their list, what is due, or what tasks they
    have. Also use to find a task's id before completing or reopening it. Returns
    open tasks only; does not include completed tasks. Read-only: it never
    creates, changes, or deletes anything. Returns one line per task with the
    task id, name, due date/time (if set), and labels (if any).
    """
    logger.info("list_active_tasks: fetching open tasks")
    token = os.environ.get(TOKEN_ENV)
    if not token:
        return (
            f"{TOKEN_ENV} is not set. Copy .env.example to .env and add your "
            "Todoist personal API token."
        )

    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, str | int] = {"limit": 200}
    tasks: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # The v1 list endpoint is paginated: follow next_cursor until done.
            while True:
                resp = await client.get(
                    f"{API_BASE}/tasks", headers=headers, params=params
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):  # tolerate a plain-array response
                    tasks.extend(data)
                    break
                tasks.extend(data.get("results", []))
                cursor = data.get("next_cursor")
                if not cursor:
                    break
                params["cursor"] = cursor
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            return "Authentication failed — check the Todoist API token in .env."
        if status == 403:
            return "Access forbidden by Todoist (403) — the token may lack access."
        if status == 429:
            return "Rate limited by Todoist (429) — try again shortly."
        return f"Todoist returned an error (HTTP {status})."
    except httpx.RequestError as exc:
        # Report the error type, not the request details (no token leakage).
        return f"Could not reach Todoist: {type(exc).__name__}."

    logger.info("list_active_tasks: %d task(s) returned", len(tasks))
    if not tasks:
        return "No active tasks."

    lines = [_format_task(t) for t in tasks]
    return f"{len(tasks)} active task(s):\n" + "\n".join(lines)


def main() -> None:
    """Entry point: run the server over stdio."""
    logger.info("Starting todoist server (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
