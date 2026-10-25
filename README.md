# hermes-plugin-antigravity-duet

Autonomous **Duet / Duffy ("Do-For-You") background task queue** (`duet_queue` tool + `/duffy` & `/duet` slash commands), **Ruflo Multi-Agent Swarm Orchestrator** (`ruflo_swarm` tool), **Human-in-the-Loop approval gate**, and **Multi-Model Antigravity CLI Bridge** for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

## What It Does

1. **Duffy / Duet Background Queue (`duet_queue` tool & `/duffy` / `/duet` commands):**
   - Enqueue asynchronous tasks from any Hermes session (CLI, Desktop, WhatsApp, Telegram, Discord, Slack).
   - Tasks are persisted in `$HERMES_HOME/duet/duet.db` (SQLite WAL mode) with per-task workspaces (`$HERMES_HOME/duet/workspaces/task_<id>`) and structured execution logs.
   - **Human-in-the-Loop Safety:** Tasks that require sensitive external actions pause in `awaiting_approval` state (`[APPROVAL_REQUIRED: ...]`) until explicitly approved or rejected by the operator via `/duffy approve <id>`, the `duet_queue` tool, or the local web dashboard.

2. **Ruflo Multi-Agent Swarm Orchestration (`ruflo_swarm` tool — Grok Heavy / Multi-Agent Bot style):**
   - Spawn, list, stop, and coordinate specialized Ruflo sub-agents (`coder`, `researcher`, `reviewer`, `tester`, `planner`, `security-architect`).
   - Initialize and launch V3 multi-agent swarms (`swarm_init`, `swarm_start`, `status`) and query AgentDB vector memory (`memory_search`).

3. **Multi-Model Antigravity CLI Quota Fallback:**
   - Routes inference through the official Google Antigravity CLI (`agy`) across the subscription model pool (`gemini-3.8-flash-high` → `claude-sonnet-5-5-high` → `gemini-3.8-flash-medium` → `gemini-3.1-pro-high` → `claude-opus-5-5-high` → `gpt-oss-120b-medium`).
   - Automatically falls over to the next available model when an individual model hits a rate or quota limit (`RESOURCE_EXHAUSTED` / `Individual quota reached`).

4. **Optional Local OpenAI-Compatible Bridge & Web Dashboard:**
   - Run `python3 -m duet_engine bridge` to expose `http://127.0.0.1:8765/v1` for zero-API-cost `custom` provider routing.
   - Run `python3 -m duet_engine worker` to process queued Duet/Duffy tasks in the background and serve the local status/approval dashboard on `http://127.0.0.1:8899`.

## Installation

```bash
hermes plugins install https://github.com/benfirad/hermes-plugin-antigravity-duet
```

Or once merged in the Hermes Plugin Catalog:

```bash
hermes plugins install antigravity-duet
```

## Usage inside Hermes

Use the `/duffy` (or `/duet`) slash command, or let the agent call `duet_queue` and `ruflo_swarm`:

```text
/duffy add Audit the repository dependencies and draft an upgrade plan
/duffy list
/duffy show 1
/duffy approve 1
/duffy swarm
```

## Disclosure (Hermes Catalog Rule 11, 12 & 13)

- **Official CLI Subprocesses:** When the optional background worker, local bridge, or Ruflo swarm tool is invoked by the user, the plugin runs the locally installed `agy` or `ruflo` CLI binary (`shutil.which("agy")`, `shutil.which("ruflo")`, or `~/.local/bin/`) under its existing sign-in. Usage counts against the user's own Antigravity/Gemini subscription.
- **No Credential Store Access:** This plugin never reads, copies, symlinks, or modifies any OAuth token files, keychains, or `~/.hermes/.env` secrets.
- **Respects Approvals:** The plugin registers only `duet_queue`, `ruflo_swarm`, `/duet`, and `/duffy` on public Hermes surfaces (`ctx.register_tool`, `ctx.register_command`) and never bypasses Hermes's built-in approval gates.

## License

MIT
