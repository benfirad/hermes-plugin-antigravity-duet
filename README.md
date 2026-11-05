<div align="center">

# 🦆 DAAK Duffy (Antigravity Duet)

### 7/24 Autonomous Background Worker, Human-in-the-Loop Task Queue & Ruflo Swarm Controller for Hermes Agent

[![Hermes Catalog](https://img.shields.io/badge/Hermes_Agent-Plugin_Catalog-7c3aed?style=for-the-badge&logo=openai&logoColor=white)](https://github.com/NousResearch/hermes-agent)
[![Antigravity](https://img.shields.io/badge/Google_Antigravity-Multi--Model_Pool-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://github.com/benfirad/hermes-plugin-antigravity-duet)
[![Zero API Cost](https://img.shields.io/badge/API_Cost-0_EUR_(Subscription)-059669?style=for-the-badge)](https://github.com/benfirad/hermes-plugin-antigravity-duet)
[![Human-in-the-Loop](https://img.shields.io/badge/Safety-Human--in--the--Loop_Gate-d97706?style=for-the-badge)](https://github.com/benfirad/hermes-plugin-antigravity-duet)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

<p align="center">
  <b>Enqueue long-running tasks asynchronously, enforce strict operator approval for sensitive actions, orchestrate multi-agent Ruflo swarms, and leverage zero-cost multi-model quota failover.</b>
</p>

[Quick Start](#-quick-start) • [Architecture](#-architecture) • [Features](#-core-features) • [Multi-Model Pool](#-multi-model-subscription-fallback-pool) • [Slash Commands](#-slash-commands--usage) • [Security & Hardening](#-security--hitl-approval-contract) • [Disclosures](#-hermes-catalog-disclosures)

</div>

---

> [!NOTE]
> **Primary Model Routing vs. Background Worker:**
> If you want to use the Google Antigravity CLI or subscription as Hermes's primary conversational LLM provider, install one of the three dedicated model providers in the catalog: `antigravity-agy`, `antigravity-oauth`, or `antigravity-subscription-directsdk`.
>
> **`antigravity-duet` (DAAK Duffy 🦆)** is purpose-built as an **autonomous background execution worker, human-in-the-loop task queue, and multi-agent swarm orchestrator**.

---

## 🏛️ Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                 Hermes Agent Operator Surfaces                         │
│    (CLI Terminal • Desktop App • WhatsApp • Telegram • Discord)        │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
   User: /duffy add <task>               Model Agent: duet_queue(add)
                   │                                 │
                   ▼                                 ▼
            [PENDING (Runnable)]         [AWAITING_APPROVAL (Locked)]
                   │                                 │
                   │                 Human Operator confirms:
                   │                 /duffy approve <id> or Web UI
                   │                                 │
                   │                                 ▼
                   └──────────────► [APPROVED] ◄─────┘
                                       │
                                       ▼
                   ┌───────────────────────────────────────┐
                   │       DAAK Duffy Worker Engine        │
                   │        (python3 -m daak_duffy)        │
                   └───────────────────┬───────────────────┘
                                       │
               ┌───────────────────────┴───────────────────────┐
               ▼                                               ▼
   ┌────────────────────────┐                     ┌────────────────────────┐
   │ Multi-Model agy Pool   │                     │  Ruflo Multi-Agent     │
   │  (Automatic Failover)  │                     │   Swarm Orchestration  │
   │ • gemini-3.8-flash     │                     │ • Coder & Researcher   │
   │ • claude-sonnet-5.5    │                     │ • Tester & Reviewer    │
   │ • gemini-3.1-pro       │                     │ • AgentDB Vector Memory│
   │ • claude-opus-5.5      │                     └────────────────────────┘
   └────────────────────────┘
```

---

## ✨ Core Features

| Feature | Description |
| :--- | :--- |
| 🦆 **DAAK Duffy Background Queue** | Asynchronous execution of long-running tasks without blocking your active Hermes session. Backed by SQLite WAL in `$HERMES_HOME/plugin-data/antigravity-duet/duet.db`. |
| 🛡️ **True Human-in-the-Loop Safety** | Tasks created by AI agents are placed in `awaiting_approval`. Agents cannot self-approve; only the operator can mark tasks `approved`. Sensitive commands pause for approval before executing. |
| ⚡ **Multi-Model Quota Failover** | Executes tasks via the official Google Antigravity CLI (`agy`) with zero API token cost, seamlessly cascading between Gemini 3.8 Flash, Claude 3.5/5.5 Sonnet, Gemini Pro, and Claude Opus on rate limits. |
| 🐝 **Ruflo Swarm Orchestration** | Spawn, coordinate, and inspect specialized Ruflo sub-agents (`coder`, `researcher`, `reviewer`, `tester`, `planner`, `security-architect`) and query AgentDB vector memory. |
| 🔒 **Hardened Web Dashboard** | Local dashboard with Host header validation (`127.0.0.1` / `localhost`), Origin protection, and launch tokens stored with `0600` permissions. |
| 🖥️ **macOS Companion App** | Includes Swift source code (`macos-companion/`) for a native menu-bar status icon and agent roster. |

---

## ⚡ Multi-Model Subscription Fallback Pool

When executing background tasks, Duffy runs through `agy` across your active Antigravity subscription tier with automatic failover on `RESOURCE_EXHAUSTED` or `Individual quota reached`:

```
[gemini-3.8-flash-high] ──► [claude-sonnet-5-5-high] ──► [gemini-3.8-flash-medium]
          │
          └──► [gemini-3.1-pro-high] ──► [claude-opus-5-5-high] ──► [gpt-oss-120b]
```

* **Zero API Key Cost:** Uses your existing local Antigravity subscription session.
* **Confined Execution:** Worker tasks execute with `--no-tools` and `--disable-slash-commands` to prevent unauthorized side-effects outside operator view.

---

## 🚀 Quick Start

### 1. Install Plugin

```bash
hermes plugins install https://github.com/benfirad/hermes-plugin-antigravity-duet
```

*Or once available directly in the Hermes Plugin Catalog:*

```bash
hermes plugins install antigravity-duet
```

### 2. Verify Installation

```bash
hermes plugins doctor antigravity-duet
```

### 3. Launch Background Worker & Dashboard (Optional Standalone Service)

```bash
python3 -m daak_duffy worker
```

*Output:*
```text
DAAK Duffy Worker & Dashboard listening on http://127.0.0.1:8899/?token=4a7c...
Security token stored with 0600 permissions in ~/.hermes/plugin-data/antigravity-duet/.dashboard_token
```

---

## 💻 Slash Commands & Usage

Use the `/duffy` (or `/duet`) command in any Hermes interface:

```text
# Enqueue a background task directly as the operator (runnable)
/duffy add Analyze repository dependencies, identify security gaps and draft upgrade plan

# View recent queue items and statuses
/duffy list

# Inspect detailed task progress, output summary, and pending approvals
/duffy show 1

# Approve a task paused at a Human-in-the-Loop gate (makes runnable)
/duffy approve 1

# Reject or cancel a task
/duffy reject 1

# Re-queue a failed task
/duffy retry 1

# Check Ruflo multi-agent swarm status and active sub-agents
/duffy swarm
```

### Agent Tool (`duet_queue`)

Model agents in Hermes can interact with the queue using the `duet_queue` tool:
* `action: "add"` — Enqueues a new background task. **Always enqueued as `awaiting_approval`** to ensure human operator consent.
* `action: "list"` — Queries recent tasks and execution states.
* `action: "show"` — Retrieves task details and logs.
* *(Note: `approve` and `retry` actions are omitted from the agent's tool schema so the agent cannot approve its own tasks).*

### Agent Tool (`ruflo_swarm`)

Orchestrate Ruflo multi-agent swarms:
* `action: "status"` — Check swarm health and worker topology.
* `action: "agent_spawn"` — Launch specialized workers (`coder`, `researcher`, `reviewer`, `tester`).
* `action: "swarm_start"` — Start an objective-driven multi-agent swarm.
* `action: "memory_search"` — Query AgentDB semantic vector memory.

---

## 🔒 Security & HITL Approval Contract

1. **Strict Human Gate:** Any task enqueued by an autonomous model agent enters the queue in `awaiting_approval`. It will not execute until an operator explicitly runs `/duffy approve <id>` or clicks **Approve** in the dashboard.
2. **Dashboard Host & CSRF Protection:** The local HTTP dashboard refuses requests with non-loopback `Host` headers and verifies `Origin` to prevent malicious cross-origin website attacks.
3. **Launch Token (0600):** Every worker launch generates a cryptographic token saved with `0600` permissions (`$HERMES_HOME/plugin-data/antigravity-duet/.dashboard_token`). All GET and POST endpoints require this token.
4. **Sandboxed Data Storage:** All state, SQLite WAL databases, and workspaces are isolated in `$HERMES_HOME/plugin-data/antigravity-duet/`.

---

## 📋 Hermes Catalog Disclosures

* **Official CLI Subprocesses (Rule 11 & 12):** When the optional background worker or Ruflo swarm tool is invoked, the plugin executes the user's locally installed `agy` or `ruflo` binary under its existing authentication. Usage counts against the user's Antigravity/Gemini subscription.
* **Zero Credential Store Access (Rule 13):** The plugin never reads, copies, symlinks, or modifies any OAuth token files, OS keychains, or `~/.hermes/.env` secrets.
* **Respects Approvals:** Model agents cannot self-approve tasks. Sensitive side-effects strictly require operator intervention.

---

## 📜 License

[MIT](LICENSE) © [benfirad](https://github.com/benfirad)
