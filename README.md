# hermes-plugin-antigravity-duet

Autonomous **Duet / Duffy ("Do-For-You") background task queue** (`duet_queue` tool + `/duffy` & `/duet` slash commands), **Ruflo Multi-Agent Swarm Orchestrator** (`ruflo_swarm` tool), **Human-in-the-Loop approval gate**, and **Multi-Model Antigravity CLI Worker** for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

> **Note on Model Routing:** If you want to use the Google Antigravity CLI or subscription as Hermes's primary LLM provider, please use one of the three dedicated model plugins listed in the Hermes catalog: `antigravity-agy`, `antigravity-oauth`, or `antigravity-subscription-directsdk`. `antigravity-duet` is purpose-built as an autonomous background task worker and multi-agent queue with human-in-the-loop safety.

## What It Does

1. **Duffy / Duet Background Queue (`duet_queue` tool & `/duffy` / `/duet` commands):**
   - Enqueue asynchronous background tasks from any Hermes session (CLI, Desktop, WhatsApp, Telegram, Discord, Slack).
   - Tasks are persisted in `$HERMES_HOME/plugin-data/antigravity-duet/duet.db` (SQLite WAL mode) with per-task workspaces and structured execution logs.
   - **True Human-in-the-Loop Safety:** Tasks enqueued by model agents are created in `awaiting_approval` status. The model cannot self-approve; only a human operator (via `/duffy approve <id>` or the authenticated dashboard) can mark them `approved` for worker execution.
   - **Resume on Approval:** When a task paused at a sensitive action is approved, the worker resumes execution and delivers the final verified result.

2. **Ruflo Multi-Agent Swarm Orchestration (`ruflo_swarm` tool):**
   - Spawn, list, stop, and coordinate specialized Ruflo sub-agents (`coder`, `researcher`, `reviewer`, `tester`, `planner`, `security-architect`).
   - Initialize and launch V3 multi-agent swarms (`swarm_init`, `swarm_start`, `status`) and query AgentDB vector memory (`memory_search`).

3. **Multi-Model Antigravity CLI Quota Fallback:**
   - Background worker routes execution through the official Google Antigravity CLI (`agy`) across the subscription model pool (`gemini-3.8-flash-high` → `claude-sonnet-5-5-high` → `gemini-3.8-flash-medium` → `gemini-3.1-pro-high` → `claude-opus-5-5-high` → `gpt-oss-120b-medium`).
   - Automatically falls over to the next available model when an individual model hits quota limits (`RESOURCE_EXHAUSTED` / `Individual quota reached`).
   - Worker runs in confined mode with `--no-tools` to ensure safe headless execution.

4. **Token-Authenticated Local Web Dashboard & DAAK Duffy Worker:**
   - Start the standalone background worker & web UI: `python3 -m daak_duffy worker` (or `python3 -m duet_engine worker`).
   - **Host & CSRF Locked:** Enforces `127.0.0.1` / `localhost` Host validation and strict Origin checks.
   - **Launch Token Security:** Every run generates a cryptographically random token stored with `0600` permissions under `$HERMES_HOME/plugin-data/antigravity-duet/.dashboard_token`, required on all GET/POST requests.
   - Includes a native macOS companion source (`macos-companion/DAAKDuffyCompanionApp.swift`) for operator roster and queue monitoring.

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
/duffy add Audit repository dependencies and draft an upgrade plan
/duffy list
/duffy show 1
/duffy approve 1
/duffy swarm
```

## Disclosures (Hermes Catalog Rule 11, 12 & 13)

- **Official CLI Subprocesses:** When the optional background worker or Ruflo swarm tool is invoked by the user, the plugin runs the locally installed `agy` or `ruflo` CLI binary (`shutil.which("agy")`, `shutil.which("ruflo")`, or `~/.local/bin/`) under its existing sign-in. Usage counts against the user's own Antigravity/Gemini subscription.
- **Zero Credential Store Access:** This plugin never reads, copies, symlinks, or modifies any OAuth token files, keychains, or `~/.hermes/.env` secrets.
- **Respects Approvals:** Model agents cannot self-approve tasks. Actions require explicit human approval via `/duffy approve` or the token-authenticated web UI.

## License

MIT
