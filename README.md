# hermes-plugin-antigravity-duet

Autonomous **Claude Duet-style background task queue** (`duet_queue` tool + `/duet` slash command), **Human-in-the-Loop approval gate**, and **Multi-Model Antigravity CLI Bridge** for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

## What It Does

1. **Duet Background Queue (`duet_queue` tool & `/duet` command):**
   - Enqueue asynchronous tasks from any Hermes session (CLI, Desktop, WhatsApp, Telegram, Discord, Slack).
   - Tasks are persisted in `$HERMES_HOME/duet/duet.db` (SQLite WAL mode) with per-task workspaces (`$HERMES_HOME/duet/workspaces/task_<id>`) and structured execution logs.
   - **Human-in-the-Loop Safety:** Tasks that require sensitive external actions pause in `awaiting_approval` state (`[APPROVAL_REQUIRED: ...]`) until explicitly approved or rejected by the operator via `/duet approve <id>`, the `duet_queue` tool, or the local web dashboard.

2. **Multi-Model Antigravity CLI Quota Fallback:**
   - Routes inference through the official Google Antigravity CLI (`agy`) across the subscription model pool (`gemini-3.8-flash-high` → `claude-sonnet-5-5-high` → `gemini-3.8-flash-medium` → `gemini-3.1-pro-high` → `claude-opus-5-5-high` → `gpt-oss-120b-medium`).
   - Automatically falls over to the next available model when an individual model hits a rate or quota limit (`RESOURCE_EXHAUSTED` / `Individual quota reached`).

3. **Optional Local OpenAI-Compatible Bridge & Web Dashboard:**
   - Run `python3 -m duet_engine bridge` to expose `http://127.0.0.1:8765/v1` for zero-API-cost `custom` provider routing.
   - Run `python3 -m duet_engine worker` to process queued Duet tasks in the background and serve the local status/approval dashboard on `http://127.0.0.1:8899`.

## Installation

```bash
hermes plugins install https://github.com/benfirad/hermes-plugin-antigravity-duet
```

Or once merged in the Hermes Plugin Catalog:

```bash
hermes plugins install antigravity-duet
```

## Usage inside Hermes

Use the `/duet` slash command or let the agent call `duet_queue`:

```text
/duet add Audit the repository dependencies and draft an upgrade plan
/duet list
/duet show 1
/duet approve 1
/duet reject 1
```

## Disclosure (Hermes Catalog Rule 11, 12 & 13)

- **Official CLI Subprocess:** When the optional background worker or bridge is started by the user, inference is executed by invoking the user's locally installed `agy` CLI binary (`shutil.which("agy")` or `~/.local/bin/agy`) under its existing sign-in. Usage counts against the user's own Antigravity/Gemini subscription.
- **No Credential Store Access:** This plugin never reads, copies, symlinks, or modifies any OAuth token files, keychains, or `~/.hermes/.env` secrets.
- **Respects Approvals:** The plugin registers only the `duet_queue` tool and `/duet` command on public Hermes surfaces (`ctx.register_tool`, `ctx.register_command`) and never bypasses Hermes's built-in approval gates.

## License

MIT
