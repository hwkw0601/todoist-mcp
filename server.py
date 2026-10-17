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
from datetime import datetime, timedelta, timezone

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


def _format_completed(task: dict) -> str:
    """Render one completed task as a single plain-text line."""
    task_id = task.get("id", "?")
    name = task.get("content", "(no name)")
    parts = [f"- [{task_id}] {name}"]
    when = task.get("completed_at") or ""
    if when:
        parts.append(f"completed: {when}")
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


@mcp.tool
async def create_task(
    content: str,
    due_date: str | None = None,
    due_datetime: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """Create a new Todoist task.

    Use when the user wants to add a to-do. Accepts a task name, an optional due
    date OR due date-time, and optional labels (categories). For a task with a
    specific time, pass `due_datetime` as `YYYY-MM-DDTHH:MM:SS` (e.g.
    `2026-10-18T15:30:00`) — it is treated as local time in the account's
    timezone (Asia/Seoul), so 15:30 means 3:30pm KST. For an all-day task, pass
    `due_date` as `YYYY-MM-DD`. Pass at most one of the two; omit both for no due
    date. Returns a confirmation with the new task's name, due, labels, and id.
    This writes to the live account — only call it when the user actually wants a
    task created.
    """
    logger.info(
        "create_task: creating task (due_date=%s, due_datetime=%s, label_count=%d)",
        due_date is not None,
        due_datetime is not None,
        len(labels or []),
    )
    if due_date and due_datetime:
        return "Pass either due_date or due_datetime, not both."

    token = os.environ.get(TOKEN_ENV)
    if not token:
        return (
            f"{TOKEN_ENV} is not set. Copy .env.example to .env and add your "
            "Todoist personal API token."
        )

    body: dict[str, object] = {"content": content}
    if due_datetime:
        # Floating local time (no offset) so Todoist applies the account tz.
        body["due_datetime"] = due_datetime
    elif due_date:
        body["due_date"] = due_date
    if labels:
        body["labels"] = labels

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{API_BASE}/tasks", headers=headers, json=body
            )
            resp.raise_for_status()
            task = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            return "Authentication failed — check the Todoist API token in .env."
        if status == 400:
            return (
                "Todoist rejected the task (400) — check the due format "
                "(YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) or the labels."
            )
        if status == 403:
            return "Access forbidden by Todoist (403) — the token may lack access."
        if status == 429:
            return "Rate limited by Todoist (429) — try again shortly."
        return f"Todoist returned an error (HTTP {status})."
    except httpx.RequestError as exc:
        return f"Could not reach Todoist: {type(exc).__name__}."

    new_id = task.get("id", "?")
    due_out = _format_due(task.get("due")) or "none"
    labels_out = ", ".join(task.get("labels") or []) or "none"
    logger.info("create_task: created task id=%s", new_id)
    return (
        f"Created task [{new_id}] {task.get('content', content)} | "
        f"due: {due_out} | labels: {labels_out}"
    )


@mcp.tool
async def set_task_status(task_id: str, done: bool) -> str:
    """Mark a Todoist task complete, or reopen a completed one.

    Use when the user says a task is done (`done=true`) or wants to undo
    completing a task (`done=false`). Get the `task_id` from list_active_tasks.
    Only changes a task's complete/incomplete status — it never edits, deletes,
    or moves anything else. This writes to the live account.
    """
    action = "close" if done else "reopen"
    logger.info("set_task_status: %s task id=%s", action, task_id)

    token = os.environ.get(TOKEN_ENV)
    if not token:
        return (
            f"{TOKEN_ENV} is not set. Copy .env.example to .env and add your "
            "Todoist personal API token."
        )

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # close/reopen return 204 No Content on success (no body to parse).
            resp = await client.post(
                f"{API_BASE}/tasks/{task_id}/{action}", headers=headers
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            return "Authentication failed — check the Todoist API token in .env."
        if status in (400, 404):
            return (
                f"No task with id {task_id} — it may be already "
                f"{'completed' if done else 'open'}, or the id is malformed or "
                "wrong (get it from list_active_tasks)."
            )
        if status == 403:
            return "Access forbidden by Todoist (403) — the token may lack access."
        if status == 429:
            return "Rate limited by Todoist (429) — try again shortly."
        return f"Todoist returned an error (HTTP {status})."
    except httpx.RequestError as exc:
        return f"Could not reach Todoist: {type(exc).__name__}."

    verb = "completed" if done else "reopened"
    logger.info("set_task_status: %s task id=%s", verb, task_id)
    return f"Task {task_id} {verb}."


@mcp.tool
async def update_task(
    task_id: str,
    content: str | None = None,
    due_date: str | None = None,
    due_datetime: str | None = None,
    clear_due: bool = False,
    labels: list[str] | None = None,
) -> str:
    """Update an existing Todoist task's due date/time (and optionally its name or labels).

    Use to reschedule a task — pass `due_datetime` (`YYYY-MM-DDTHH:MM:SS`, local
    Asia/Seoul time) for a specific time, or `due_date` (`YYYY-MM-DD`) for an
    all-day task — or pass `clear_due=true` to remove its due date entirely. Get
    `task_id` from list_active_tasks or list_completed_tasks. Only changes the due
    date/time, name, and labels — nothing else. This writes to the live account.
    """
    logger.info("update_task: id=%s clear_due=%s", task_id, clear_due)

    token = os.environ.get(TOKEN_ENV)
    if not token:
        return (
            f"{TOKEN_ENV} is not set. Copy .env.example to .env and add your "
            "Todoist personal API token."
        )

    body: dict[str, object] = {}
    if content is not None:
        body["content"] = content
    if clear_due:
        body["due_string"] = "no date"  # Todoist clears the due for this value
    elif due_datetime:
        body["due_datetime"] = due_datetime
    elif due_date:
        body["due_date"] = due_date
    if labels is not None:
        body["labels"] = labels
    if not body:
        return "Nothing to update."

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{API_BASE}/tasks/{task_id}", headers=headers, json=body
            )
            resp.raise_for_status()
            try:
                task = resp.json()
            except ValueError:
                task = {}
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            return "Authentication failed — check the Todoist API token in .env."
        if status in (400, 404):
            return (
                f"No task with id {task_id} (or the update was invalid) — get the "
                "id from list_active_tasks / list_completed_tasks."
            )
        if status == 403:
            return "Access forbidden by Todoist (403) — the token may lack access."
        if status == 429:
            return "Rate limited by Todoist (429) — try again shortly."
        return f"Todoist returned an error (HTTP {status})."
    except httpx.RequestError as exc:
        return f"Could not reach Todoist: {type(exc).__name__}."

    due_out = _format_due(task.get("due")) if task else ""
    tid = task.get("id", task_id) if task else task_id
    name = task.get("content", "") if task else ""
    logger.info("update_task: updated id=%s", tid)
    return f"Updated task [{tid}] {name} | due: {due_out or ('none' if clear_due else 'unchanged')}"


@mcp.tool
async def list_completed_tasks(days: int = 7) -> str:
    """List tasks I completed recently, within the last `days` days.

    Use when the user wants to see finished tasks, or needs a completed task's id
    in order to reopen it (with set_task_status, done=false) — including tasks
    checked off elsewhere, like on the phone. Read-only. `days` defaults to 7 and
    is capped at 92 (Todoist allows about a 3-month window). Returns one line per
    completed task with its id, name, completion time, and labels.
    """
    days = max(1, min(int(days), 92))
    logger.info("list_completed_tasks: fetching last %d day(s)", days)

    token = os.environ.get(TOKEN_ENV)
    if not token:
        return (
            f"{TOKEN_ENV} is not set. Copy .env.example to .env and add your "
            "Todoist personal API token."
        )

    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, str | int] = {"since": since, "until": until, "limit": 200}
    tasks: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # The endpoint returns {"items": [...]} and may paginate via cursor.
            while True:
                resp = await client.get(
                    f"{API_BASE}/tasks/completed/by_completion_date",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    tasks.extend(data)
                    break
                tasks.extend(data.get("items", data.get("results", [])))
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
        return f"Could not reach Todoist: {type(exc).__name__}."

    logger.info("list_completed_tasks: %d task(s) returned", len(tasks))
    if not tasks:
        return f"No tasks completed in the last {days} day(s)."

    lines = [_format_completed(t) for t in tasks]
    return (
        f"{len(tasks)} completed task(s) in the last {days} day(s):\n"
        + "\n".join(lines)
    )


def main() -> None:
    """Entry point: run the server over stdio."""
    logger.info("Starting todoist server (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
