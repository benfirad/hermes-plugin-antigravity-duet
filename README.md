# hermes-plugin-antigravity-duet

Autonomous **Duet / Duffy ("Do-For-You") background task queue** (`duet_queue` tool + `/duffy` & `/duet` slash commands), **Ruflo Multi-Agent Swarm Orchestrator** (`ruflo_swarm` tool), **Human-in-the-Loop approval gate** (`pre_tool_call` hook), and **Multi-Model Antigravity CLI Task Worker** for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

> **Note on Model Routing:** This plugin is dedicated to autonomous task queuing, worker execution, and swarm orchestration. If you are looking to route Hermes Agent's primary conversation model through Google Antigravity, please install one of the catalog's model provider plugins: `antigravity-subscription-directsdk`, `antigravity-oauth`, or `antigravity-agy`.

## What It Does

1. **Duffy / Duet Background Queue (`duet_queue` tool & `/duffy` / `/duet` commands):**
   - Enqueue asynchronous tasks from any Hermes session (CLI, Desktop, WhatsApp, Telegram, Discord, Slack).
   - Tasks are persisted in `$HERMES_HOME/plugin-data/antigravity-duet/duet.db` (SQLite WAL mode) with isolated per-task workspaces (`workspaces/task_<id>`) and structured execution logs.
   - **Real Human-in-the-Loop Gate:** Tasks enqueued by the agent model automatically enter `awaiting_approval` status. The model-facing `duet_queue` tool does not allow self-approval. Only explicit human operator action via `/duffy approve <id>` (or `/duet approve <id>`) or the local web dashboard marks tasks as `approved` and runnable.

2. **Autonomous Background Worker & Confined Execution:**
   - Run `python3 -m duet_engine worker` to process approved tasks in the background.
   - Worker tasks invoke `agy` with `--no-tools` and isolated workspaces, ensuring no untracked host tools or side-effects execute outside Hermes approval gates.
   - If a running task encounters a sensitive or external step, it pauses in `awaiting_approval` (`[APPROVAL_REQUIRED: ...]`) until re-approved by the operator.
   - **Multi-Model Fallback:** Automatically falls over across the subscription pool (`gemini-3.8-flash-high` → `claude-sonnet-5-5-high` → `gemini-3.8-flash-medium` → `gemini-3.1-pro-high` → `claude-opus-5-5-high` → `gpt-oss-120b-medium`) when an individual model hits rate or quota limits (`RESOURCE_EXHAUSTED` / `Individual quota reached`).

3. **Ruflo Multi-Agent Swarm Orchestration (`ruflo_swarm` tool & `pre_tool_call` hook):**
   - Spawn, list, stop, and coordinate specialized Ruflo sub-agents (`coder`, `researcher`, `reviewer`, `tester`, `planner`, `security-architect`).
   - Runs from isolated plugin-data storage (`plugin-data/antigravity-duet/ruflo`).
   - `pre_tool_call` automatically escalates multi-agent operations (`agent_spawn`, `swarm_start`) to the human approval gate before execution.
   - All positional parameters pass `--` guards to prevent argument injection.

4. **Hardened Local Web Dashboard:**
   - Web interface served on `http://127.0.0.1:8899`.
   - **CSRF & Origin Lockdown:** Generates a random cryptographic token per launch (stored mode `0600` at `$HERMES_HOME/plugin-data/antigravity-duet/dashboard_token.txt`). Requires the token on all requests and POST actions, enforces strict `Host` validation (`127.0.0.1` / `localhost`), and rejects cross-origin requests.

## Installation

```bash
hermes plugins install https://github.com/benfirad/hermes-plugin-antigravity-duet
```

Or once listed in the Hermes Plugin Catalog:

```bash
hermes plugins install antigravity-duet
```

## Usage inside Hermes

Use the `/duffy` (or `/duet`) slash command, or let the agent call `duet_queue` and `ruflo_swarm`:

```text
/duffy add Audit repository dependencies and draft upgrade plan
/duffy list
/duffy show 1
/duffy approve 1
/duffy swarm
```

## Running the Background Worker

```bash
python3 -m duet_engine worker --port 8899
```

The worker prints the authenticated dashboard URL:
`http://127.0.0.1:8899/?token=<launch_token>`

## Disclosures (Hermes Catalog Rules 11, 12 & 13)

- **Official CLI Subprocesses:** When the optional background worker or Ruflo swarm tool is invoked, the plugin runs the locally installed `agy` (with `--no-tools`) or `ruflo` CLI binary (`shutil.which("agy")`, `shutil.which("ruflo")`, or `~/.local/bin/`) under its existing user sign-in. Usage counts against the user's subscription.
- **No Credential Store Access:** The plugin never reads, copies, symlinks, or modifies OAuth tokens, OS keychains, or `~/.hermes/.env` secrets.
- **Respects Approvals:** Registers only `duet_queue`, `ruflo_swarm`, `pre_tool_call`, `/duet`, and `/duffy` on public Hermes surfaces (`ctx.register_tool`, `ctx.register_hook`, `ctx.register_command`) and enforces human operator approval gates.

## License

MIT
