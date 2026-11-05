"""
antigravity-duet — Autonomous background task queue (Duet / Duffy Do-For-You worker)
with Human-in-the-Loop approval gates, Ruflo multi-agent swarm orchestration,
and multi-model Antigravity CLI quota fallback.

Registers:
- Tool `duet_queue`: Enqueue, list, and inspect background tasks (Human-in-the-Loop gated).
- Tool `ruflo_swarm`: Spawn, inspect, coordinate, and manage Ruflo multi-agent swarms.
- Slash commands `/duet` and `/duffy`: Interactive operator queue & swarm management.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

try:
    from .duet_engine import DuetQueueStore, run_ruflo_command
except (ImportError, ValueError):
    from duet_engine import DuetQueueStore, run_ruflo_command

_DUET_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "duet_queue",
    "description": (
        "Manage the autonomous Duet / Duffy ('Do-For-You') background task queue. "
        "Use this tool to enqueue long-running or asynchronous background tasks, "
        "check queue status, or view execution logs. "
        "Note: Tasks enqueued by agents are placed in 'awaiting_approval' status and "
        "require human operator approval via /duffy approve or the dashboard before running."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "show"],
                "description": "Operation to perform on the Duet/Duffy queue (add, list, show).",
            },
            "title": {
                "type": "string",
                "description": "Task instruction (required when action='add').",
            },
            "category": {
                "type": "string",
                "description": "Optional task category (e.g., general, research, code, ops, swarm).",
            },
            "task_id": {
                "type": "integer",
                "description": "Task ID (required for show).",
            },
        },
        "required": ["action"],
    },
}

_RUFLO_SWARM_SCHEMA: Dict[str, Any] = {
    "name": "ruflo_swarm",
    "description": (
        "Orchestrate Ruflo multi-agent swarms and specialized sub-agents (coder, researcher, "
        "reviewer, tester, planner, security-architect). Supports spawning agents, checking "
        "swarm/agent health, scaling parallel workers, and querying AgentDB vector memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status",
                    "agent_list",
                    "agent_spawn",
                    "agent_stop",
                    "swarm_init",
                    "swarm_start",
                    "memory_search",
                ],
                "description": "Ruflo orchestration action to run.",
            },
            "agent_type": {
                "type": "string",
                "description": "Agent role when action='agent_spawn' (e.g., coder, researcher, reviewer, tester).",
            },
            "agent_id": {
                "type": "string",
                "description": "Target agent identifier when action='agent_stop'.",
            },
            "objective": {
                "type": "string",
                "description": "Swarm objective or memory search query.",
            },
        },
        "required": ["action"],
    },
}

_HELP_TEXT = """\
/duffy (or /duet) — Autonomous Do-For-You Background Queue & Ruflo Swarm Controller

Operator Subcommands:
  list                       List recent tasks in the Duet/Duffy queue
  add <instruction>          Enqueue a runnable task directly as the operator
  show <id>                  Show detailed summary and logs for task #<id>
  approve <id>               Approve a task paused at a Human-in-the-Loop gate (makes runnable)
  reject <id>                Reject/cancel a task
  retry <id>                 Re-queue a failed or rejected task
  swarm                      Show Ruflo multi-agent swarm & agent pool status
"""


def _handle_duet_tool(args: Optional[Dict[str, Any]] = None, **_: Any) -> str:
    params = dict(args or {})
    action = str(params.get("action") or "list").strip().lower()
    store = DuetQueueStore()

    if action == "add":
        title = str(params.get("title") or "").strip()
        if not title:
            return json.dumps({"ok": False, "error": "Missing 'title' for action='add'."})
        category = str(params.get("category") or "general").strip()
        # Human-in-the-Loop gate: agent-submitted tasks require operator approval
        tid = store.add_task(
            title=title,
            category=category,
            status="awaiting_approval",
            log_note="Enqueued by model agent via duet_queue tool (awaiting human operator approval).",
        )
        return json.dumps({
            "ok": True,
            "task_id": tid,
            "status": "awaiting_approval",
            "message": (
                f"Task #{tid} added to Duet/Duffy queue in 'awaiting_approval' status. "
                f"It requires human operator approval via '/duffy approve {tid}' or web dashboard before running."
            ),
        })

    if action == "list":
        tasks = store.list_tasks(limit=20)
        return json.dumps({"ok": True, "tasks": tasks}, ensure_ascii=False)

    tid = int(params.get("task_id") or 0)
    if tid <= 0:
        return json.dumps({"ok": False, "error": f"Valid 'task_id' is required for action={action!r}."})

    if action == "show":
        detail = store.get_task_detail(tid)
        if not detail:
            return json.dumps({"ok": False, "error": f"Task #{tid} not found."})
        return json.dumps({"ok": True, "task": detail}, ensure_ascii=False)

    if action in ("approve", "reject", "retry"):
        return json.dumps({
            "ok": False,
            "error": (
                f"Action {action!r} is restricted to the human operator. "
                "The model agent cannot self-approve or retry tasks; use the /duffy slash command or web dashboard."
            ),
        })

    return json.dumps({"ok": False, "error": f"Unsupported action: {action!r}"})


def _handle_ruflo_tool(args: Optional[Dict[str, Any]] = None, **_: Any) -> str:
    params = dict(args or {})
    action = str(params.get("action") or "status").strip().lower()

    if action == "status":
        res = run_ruflo_command(["swarm", "status"])
        return json.dumps(res, ensure_ascii=False)

    if action == "agent_list":
        res = run_ruflo_command(["agent", "list"])
        return json.dumps(res, ensure_ascii=False)

    if action == "agent_spawn":
        role = str(params.get("agent_type") or "coder").strip()
        res = run_ruflo_command(["agent", "spawn", "-t", role])
        return json.dumps(res, ensure_ascii=False)

    if action == "agent_stop":
        aid = str(params.get("agent_id") or "").strip()
        if not aid:
            return json.dumps({"ok": False, "error": "Missing 'agent_id' for action='agent_stop'."})
        res = run_ruflo_command(["agent", "stop", aid])
        return json.dumps(res, ensure_ascii=False)

    if action == "swarm_init":
        res = run_ruflo_command(["swarm", "init", "--v3-mode"])
        return json.dumps(res, ensure_ascii=False)

    if action == "swarm_start":
        obj = str(params.get("objective") or "Execute parallel multi-agent workflow").strip()
        res = run_ruflo_command(["swarm", "start", "-o", obj])
        return json.dumps(res, ensure_ascii=False)

    if action == "memory_search":
        query = str(params.get("objective") or "").strip()
        if not query:
            return json.dumps({"ok": False, "error": "Missing 'objective' query for memory_search."})
        # Pass '--' before positional query as safety guard
        res = run_ruflo_command(["memory", "search", "--", query])
        return json.dumps(res, ensure_ascii=False)

    return json.dumps({"ok": False, "error": f"Unsupported ruflo_swarm action: {action!r}"})


def _handle_duet_slash(raw_args: str) -> str:
    parts = raw_args.strip().split(maxsplit=1)
    if not parts or parts[0] in ("help", "-h", "--help"):
        return _HELP_TEXT

    cmd = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    store = DuetQueueStore()

    if cmd == "swarm":
        res = run_ruflo_command(["agent", "list"])
        return res.get("stdout") or res.get("stderr") or res.get("error") or "Ruflo status checked."

    if cmd in ("list", "ls"):
        rows = store.list_tasks(limit=15)
        if not rows:
            return "Duffy/Duet queue is empty. Use `/duffy add <instruction>` to enqueue a task."
        lines: List[str] = ["Duffy / Duet Queue:"]
        for r in rows:
            lines.append(
                f"  [#{r['id']}] ({r['status'].upper()}) [{r['category']}] {r['title']} "
                f"— model: {r.get('model_used') or '-'}"
            )
        return "\n".join(lines)

    if cmd == "add":
        if not rest:
            return "Usage: /duffy add <instruction>"
        # Operator addition is runnable (pending)
        tid = store.add_task(title=rest, category="general", status="pending", log_note="Enqueued directly by operator via /duffy add.")
        return f"Added task #{tid} to Duffy/Duet queue (pending/runnable): {rest}"

    if cmd in ("show", "approve", "reject", "retry"):
        if not rest.isdigit():
            return f"Usage: /duffy {cmd} <task_id>"
        tid = int(rest)
        if cmd == "show":
            detail = store.get_task_detail(tid)
            if not detail:
                return f"Task #{tid} not found."
            out = [
                f"=== Task #{detail['id']}: {detail['title']} ===",
                f"Status: {detail['status']} | Category: {detail['category']} | Model: {detail.get('model_used') or '-'}",
            ]
            if detail.get("approval_action"):
                out.append(f"Pending Approval: {detail['approval_action']}")
            if detail.get("result_summary"):
                out.append(f"\n--- Summary ---\n{detail['result_summary']}")
            return "\n".join(out)

        target_map = {"approve": "approved", "reject": "rejected", "retry": "pending"}
        new_status = target_map[cmd]
        note = f"Operator ran /duffy {cmd} #{tid}"
        if store.set_status(tid, new_status, note):
            if cmd == "approve":
                return f"Task #{tid} explicitly approved. Status updated to 'approved' (worker will execute/resume task)."
            return f"Task #{tid} status updated to '{new_status}'."
        return f"Task #{tid} not found."

    return f"Unknown subcommand: {cmd}\n\n{_HELP_TEXT}"


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="duet_queue",
        toolset="duet",
        schema=_DUET_TOOL_SCHEMA,
        handler=_handle_duet_tool,
        description="Manage the autonomous Duet / Duffy ('Do-For-You') background task queue (tasks await human operator approval).",
    )
    ctx.register_tool(
        name="ruflo_swarm",
        toolset="duet",
        schema=_RUFLO_SWARM_SCHEMA,
        handler=_handle_ruflo_tool,
        description="Orchestrate Ruflo multi-agent swarms and specialized agents (spawn, list, stop, swarm start, memory search).",
    )
    ctx.register_command(
        "duet",
        handler=_handle_duet_slash,
        description="Manage the autonomous Duet/Duffy background task queue (/duet list|add|show|approve|reject|swarm).",
    )
    ctx.register_command(
        "duffy",
        handler=_handle_duet_slash,
        description="Alias for /duet ('Do-For-You' autonomous worker & Ruflo swarm controller).",
    )
