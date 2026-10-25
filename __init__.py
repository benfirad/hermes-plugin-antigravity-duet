"""
antigravity-duet — Autonomous background task queue (Claude Duet-style worker)
with Human-in-the-Loop approval gates and multi-model Antigravity CLI fallback.

Registers:
- Tool `duet_queue`: Add, list, inspect, approve, or reject background tasks.
- Slash command `/duet`: Interactive queue management from TUI, Desktop, or messaging platforms.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .duet_engine import DuetQueueStore

_DUET_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "duet_queue",
    "description": (
        "Manage the autonomous Duet background task queue. Use this tool to enqueue "
        "long-running or asynchronous background tasks, check queue status, view task logs, "
        "or record human-in-the-loop approvals/rejections for paused tasks."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "show", "approve", "reject", "retry"],
                "description": "Operation to perform on the Duet queue.",
            },
            "title": {
                "type": "string",
                "description": "Task instruction (required when action='add').",
            },
            "category": {
                "type": "string",
                "description": "Optional task category (e.g., general, research, code, ops).",
            },
            "task_id": {
                "type": "integer",
                "description": "Task ID (required for show, approve, reject, retry).",
            },
        },
        "required": ["action"],
    },
}

_HELP_TEXT = """\
/duet — Autonomous Duet Background Task Queue & Multi-Model Bridge

Subcommands:
  list                       List recent tasks in the Duet queue
  add <instruction>          Enqueue a new autonomous background task
  show <id>                  Show detailed summary and logs for task #<id>
  approve <id>               Approve a task paused at a Human-in-the-Loop gate
  reject <id>                Reject/cancel a task
  retry <id>                 Re-queue a failed or rejected task
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
        tid = store.add_task(title=title, category=category)
        return json.dumps({
            "ok": True,
            "task_id": tid,
            "status": "pending",
            "message": f"Task #{tid} added to Duet queue.",
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

    if action == "approve":
        ok = store.set_status(tid, "approved", "Approved by operator via duet_queue tool.")
        return json.dumps({"ok": ok, "task_id": tid, "status": "approved" if ok else "not_found"})

    if action == "reject":
        ok = store.set_status(tid, "rejected", "Rejected by operator via duet_queue tool.")
        return json.dumps({"ok": ok, "task_id": tid, "status": "rejected" if ok else "not_found"})

    if action == "retry":
        ok = store.set_status(tid, "pending", "Re-queued by operator via duet_queue tool.")
        return json.dumps({"ok": ok, "task_id": tid, "status": "pending" if ok else "not_found"})

    return json.dumps({"ok": False, "error": f"Unsupported action: {action!r}"})


def _handle_duet_slash(raw_args: str) -> str:
    parts = raw_args.strip().split(maxsplit=1)
    if not parts or parts[0] in ("help", "-h", "--help"):
        return _HELP_TEXT

    cmd = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    store = DuetQueueStore()

    if cmd in ("list", "ls"):
        rows = store.list_tasks(limit=15)
        if not rows:
            return "Duet queue is empty. Use `/duet add <instruction>` to enqueue a task."
        lines: List[str] = ["Duet Queue:"]
        for r in rows:
            lines.append(
                f"  [#{r['id']}] ({r['status'].upper()}) [{r['category']}] {r['title']} "
                f"— model: {r.get('model_used') or '-'}"
            )
        return "\n".join(lines)

    if cmd == "add":
        if not rest:
            return "Usage: /duet add <instruction>"
        tid = store.add_task(title=rest, category="general")
        return f"Added task #{tid} to Duet queue: {rest}"

    if cmd in ("show", "approve", "reject", "retry"):
        if not rest.isdigit():
            return f"Usage: /duet {cmd} <task_id>"
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
        if store.set_status(tid, new_status, f"Operator ran /duet {cmd} #{tid}"):
            return f"Task #{tid} status updated to '{new_status}'."
        return f"Task #{tid} not found."

    return f"Unknown subcommand: {cmd}\n\n{_HELP_TEXT}"


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="duet_queue",
        toolset="duet",
        schema=_DUET_TOOL_SCHEMA,
        handler=_handle_duet_tool,
        description="Manage the autonomous Duet background task queue and Human-in-the-Loop approvals.",
    )
    ctx.register_command(
        "duet",
        handler=_handle_duet_slash,
        description="Manage the autonomous Duet background task queue (/duet list|add|show|approve|reject).",
    )
