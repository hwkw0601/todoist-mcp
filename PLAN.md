# PLAN.md — Todoist MCP Server

A local MCP server that gives Claude three tools for Todoist: list my open tasks, create a task
(with a due date/time and labels), and mark a task done or reopen it. Groundwork for syncing my
weekly scheduler with Todoist; the scheduler↔Todoist sync itself is out of scope (see Limitations).

## Planning decisions (locked 2026-10-17)
These resolve choices the original brief left open or recommended differently:
- **HTTP client: `httpx`** (not the `todoist-api-python` SDK) — transparent, auditable calls,
  minimal deps, no SDK version-churn.
- **`create_task` due = ISO string** (not natural-language `due_string`): `YYYY-MM-DD` → `due_date`;
  `YYYY-MM-DDTHH:MM:SS` → `due_datetime`; `None` → no due.
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

**Tool 2 — `create_task`** *(creates)* — inputs: `content: str` (required); `due: str | None`
(ISO date or date-time, see decisions); `labels: list[str] | None` (my categories: Academics,
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
- Open tasks only; no completed-history reporting.
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
