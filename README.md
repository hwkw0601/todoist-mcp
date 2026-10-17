# todoist-mcp

A small **local MCP server** that lets Claude manage your Todoist tasks over stdio, so a
weekly-scheduler workflow can sync tasks and their done/undone status with Todoist.

It talks directly to the [Todoist API v1](https://developer.todoist.com/api/v1/) over HTTPS
using a personal API token. Local, single-user, stdio only.

## Tools

| Tool | What it does | Writes? |
|------|--------------|---------|
| `list_active_tasks` | List your current open tasks (id, name, due, labels) | Read-only |
| `create_task` | Create a task with a name, an optional `due_date` (`YYYY-MM-DD`) or `due_datetime` (`YYYY-MM-DDTHH:MM:SS`), and optional labels | Creates |
| `set_task_status` | Mark a task complete, or reopen a completed one, by id | Changes status only |

No deleting, no editing of other fields, no project changes — by design.

> **Status:** built in phases. `list_active_tasks` is implemented; `create_task` and
> `set_task_status` are added next.

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)
- A Todoist **personal API token**: Todoist → Settings → Integrations → Developer → API token.

## Setup

1. Install dependencies (creates the project venv):
   ```bash
   uv sync
   ```
2. Create your `.env` from the template and paste your token:
   ```bash
   cp .env.example .env
   # then edit .env and set TODOIST_API_TOKEN=...
   ```
   `.env` is git-ignored and must never be committed.

## Run

```bash
uv run server.py
```

The server communicates over stdio, so there is no visible output on success — it waits for an
MCP client to connect. Logs go to stderr. Press Ctrl-C to stop.

## Register with Claude

Point your MCP client at the project. Use the **absolute path to `uv`** if `uv` isn't on the
client's PATH (find it with `which uv`).

**Claude Desktop** — add to its MCP config:
```json
{
  "mcpServers": {
    "todoist": {
      "command": "/Users/hyowonkwon/.local/bin/uv",
      "args": ["--directory", "/Users/hyowonkwon/Desktop/todoist-mcp", "run", "server.py"]
    }
  }
}
```

**Claude Code** — from the project directory:
```bash
claude mcp add todoist -- /Users/hyowonkwon/.local/bin/uv --directory /Users/hyowonkwon/Desktop/todoist-mcp run server.py
```

After registering, restart/reconnect the client and confirm the `todoist` server connects.

## Security

- The Todoist personal token is **unscoped** — it grants full read/write/delete on your whole
  account. To narrow access you must use OAuth scopes (e.g. `data:read`, `task:add`) instead.
- Keep the token only in `.env` (git-ignored). It is never written to stdout, logs, or error
  messages.
- `create_task` and `set_task_status` change your live account; wrong calls are tedious to undo.
- Task names enter Claude's context when listed — `list_active_tasks` returns only id, name, due,
  and labels (no notes/comments).
