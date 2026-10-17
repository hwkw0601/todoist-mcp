# PLAN.md — Todoist MCP Server

A local MCP server that gives Claude three tools for Todoist: list my open tasks, create a task
(with a due date/time and labels), and mark a task done or reopen it. Groundwork for syncing my
weekly scheduler with Todoist; the scheduler↔Todoist sync itself is out of scope (see Limitations).

## Planning decisions (locked 2026-10-17)
These resolve choices the original brief left open or recommended differently:
- **HTTP client: `httpx`** (not the `todoist-api-python` SDK) — transparent, auditable calls,
  minimal deps, no SDK version-churn.
- **`create_task` due = two separate params** `due_date` (`YYYY-MM-DD`) and `due_datetime`
  (`YYYY-MM-DDTHH:MM:SS`), mirroring the Todoist API field names. (Revised after a live test showed
  the model reaching for `due_datetime`; the earlier single-`due` param lost the date.)
- **Flat layout:** a single `server.py` at the project root, run with `uv run server.py`.
- **Names:** FastMCP instance and client registration key are both `todoist`.
- **`set_task_status`** inputs: `task_id: str`, `done: bool`.

## API facts (Todoist API v1, verified 2026-10-17)
- Base: `https://api.todoist.com/api/v1`. Auth header: `Authorization: Bearer <token>`.
- Token: Todoist → Settings → Integrations → Developer → "API token". Personal token is **not
  scopeable** — one token grants full read/write/delete on the whole account. OAuth (`data:read`,
  `task:add`) is the only way to narrow it; not used here (single personal account).
- Endpoints: list open tasks `GET /tasks` (open only; no completed); create `POST /tasks`
  (`content`, `due_date` | `due_datetime`, `labels`); complete `POST /tasks/{id}/close`; reopen
  `POST /tasks/{id}/reopen`.
- Read vs write: `GET /tasks` read-only; `POST /tasks` creates; `close`/`reopen` change status.

## Tools (exact names)
**Tool 1 — `list_active_tasks`** *(read-only)* — inputs: none. Returns plain text, one line per
open task with its **id**, name, due date/time (if any), and labels. The id is shown so Tool 3 can
act on it.

**Tool 2 — `create_task`** *(creates)* — inputs: `content: str` (required); `due_date: str | None`
(`YYYY-MM-DD`, all-day); `due_datetime: str | None` (`YYYY-MM-DDTHH:MM:SS`, specific local time —
pass at most one of the two); `labels: list[str] | None` (my categories: Academics,
Extracurricular, Application, RA, …). Returns text confirming the created task's name, due, labels,
and new id.

**Tool 3 (stretch) — `set_task_status`** *(changes status only)* — inputs: `task_id: str`;
`done: bool` (true → close, false → reopen). Returns text confirming which task was closed/reopened.

## Dependencies (uv project venv only — nothing global)
- `fastmcp` — MCP server framework.
- `httpx` — direct REST calls to the endpoints above.
- `python-dotenv` — read the token from `.env`.
- Python 3.11+ (pinned in `pyproject.toml`; local interpreter 3.13).

## Configuration
- One secret: `TODOIST_API_TOKEN`, read from `.env` in the project folder.
- `.env.example` ships with `TODOIST_API_TOKEN=` (no value). `.gitignore` excludes `.env`, `.venv`,
  `__pycache__`. I paste the real token into `.env` myself; Claude never reads, prints, or commits it.

## Security (real risks for this app)
- **Unscoped token** opens the whole account. Limit blast radius: expose **only** these three tools;
  nothing that deletes or bulk-edits. OAuth `data:read` noted as the only true read-only option.
- **Accidental writes:** `create_task`/`set_task_status` change the live account; they confirm their
  action in the returned text so mistakes are visible. No delete tool exists, by design.
- **Token leakage:** the token must never reach stdout, logs, or error messages; API errors return a
  short, token-free message.
- **Task content is private:** names/notes enter Claude's context when listed; don't log full task
  contents to stderr.

## Conflicts
- FastMCP 4.x on Python 3.13 (requires ≥3.11); `httpx`/`python-dotenv` compatible. No SDK, so no
  SDK/FastMCP version coupling.

## Limitations
- `list_completed_tasks` covers a recent window only (default 7 days, max ~3 months per the
  Todoist API); it is not full completed-history reporting.
- No projects, sections, comments, reminders, recurring-rule editing, or deletion.
- Timezone **Asia/Seoul (UTC+9)**: `due_datetime` is sent as floating local time so Todoist applies
  the account timezone — a 3:30pm task must land at 3:30pm KST (verified in testing).
- The two-way scheduler↔Todoist sync is a separate piece, not this server.

## Constraints
- Local only, over stdio. Never print to stdout; log to stderr via `logging`.
- `list_active_tasks` read-only; `create_task` may create; `set_task_status` may change
  complete/incomplete status — nothing else is written (no deleting, no editing other fields, no
  project changes).
- Token read from `.env`, never committed. Ask before restructuring. Build only what's listed.

## Files
`pyproject.toml`, `server.py`, `.env.example`, `.gitignore`, `CLAUDE.md`, `PLAN.md`, `README.md`.

## Build order and testing
- **Phase 1 — scaffold:** uv project, FastMCP server named `todoist` over stdio, no tools, startup
  log to stderr. *Test:* `uv run server.py` logs and waits; connects to both clients with 0 tools. ✅
- **Phase 2 — `list_active_tasks`:** *Test:* ask "what's on my Todoist list?" without naming the
  tool; Claude calls it and shows real open tasks with ids. Commit.
- **Phase 3 — `create_task`:** *Test:* "add 'test from MCP' due tomorrow 3:30pm with label
  Academics"; confirm it appears on my phone at 3:30pm KST with the label. Commit.
- **Phase 4 — `set_task_status` (stretch):** *Test:* complete the test task by id → leaves the open
  list; reopen → returns. Commit.

Two working tools (Phases 1–3) is a complete deliverable; Phase 4 is a bonus.

## Added later — list_completed_tasks (2026-10-17)
- New read-only tool `list_completed_tasks(days=7)` → `GET /api/v1/tasks/completed/by_completion_date`
  with `since`/`until` RFC3339 timestamps (window capped at 92 days). Response is `{items:[...]}`
  (verified live); items carry the task `id`, so a completed task can be reopened with
  `set_task_status(done=false)` — including tasks checked off on the phone. Added so the button
  app's 되돌리기 can list completed tasks rather than only ones completed within that app.

## Build notes — what changed during the build (2026-10-17)
- **Layout:** the initial scaffold used a uv src-layout package; flattened to a single root
  `server.py` (run `uv run server.py`) to match the guide's commands and configs.
- **`create_task` due params:** started as a single `due` (ISO) param; a live test showed the
  calling model passing Todoist's own field name `due_datetime`, which the single param rejected,
  so the date was lost. Changed to **separate `due_date` + `due_datetime`** params matching the API.
- **`set_task_status` errors:** a malformed id returns HTTP 400 (not 404); both are mapped to the
  same "no task with that id" hint.
- **API shape confirmed (live, read-only):** `GET /tasks` returns `{results, next_cursor}` (handled
  by pagination); the `due` object exposes the value under `date` (no separate `datetime` key),
  which `_format_due` already handles via fallback.

## Audit summary (Part 10)
- Network: HTTPS to `api.todoist.com/api/v1` only (list/create/close/reopen), sending the Bearer
  token and the task fields above. (FastMCP separately pings pypi.org on startup — not our code.)
- Filesystem: reads `.env`; writes no files (logs to stderr).
- Writes to Todoist: `create_task` (create) and `set_task_status` (close/reopen) only — no delete,
  no field edits, no project changes. Within all PLAN.md constraints.

## Comparison with existing servers (Part 10)
- Official `Doist/todoist-mcp` (TypeScript, broad toolset, also streamable HTTP) and community
  `greirson/mcp-todoist` (~19 tools consolidated via an `action` param, includes delete).
- Ours is Python/httpx, local stdio, **three narrow tools with no delete/edit** — a smaller,
  auditable surface for personal use.
