#!/usr/bin/env python3
"""
Sanitized, generic Duet Queue Store, Multi-Model Antigravity CLI Bridge,
and Human-in-the-Loop Web Dashboard for Hermes Agent.

Contains zero personal data, hardcoded paths, or third-party credentials.
All state is stored inside `$HERMES_HOME/duet/` (default `~/.hermes/duet/`).
"""

from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import uuid
from datetime import datetime

DEFAULT_FALLBACK_MODELS: Tuple[str, ...] = (
    "gemini-3.8-flash-high",
    "claude-sonnet-5-5-high",
    "gemini-3.8-flash-medium",
    "gemini-3.1-pro-high",
    "claude-opus-5-5-high",
    "gpt-oss-120b-medium",
)

MODEL_ALIASES: Dict[str, str] = {
    "flash": "gemini-3.8-flash-high",
    "gemini-3.8-flash": "gemini-3.8-flash-high",
    "gemini-3.8-flash-high": "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-low": "gemini-3.8-flash-low",
    "pro": "gemini-3.1-pro-high",
    "gemini-3.1-pro": "gemini-3.1-pro-high",
    "gemini-3.1-pro-high": "gemini-3.1-pro-high",
    "sonnet": "claude-sonnet-5-5-high",
    "claude-sonnet-5.5": "claude-sonnet-5-5-high",
    "claude-sonnet-5-5-high": "claude-sonnet-5-5-high",
    "opus": "claude-opus-5-5-high",
    "claude-opus-5.5": "claude-opus-5-5-high",
    "claude-opus-5-5-high": "claude-opus-5-5-high",
    "gpt-oss-120b": "gpt-oss-120b-medium",
    "gpt-oss-120b-medium": "gpt-oss-120b-medium",
}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_hermes_home() -> Path:
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def resolve_agy_bin(custom_bin: Optional[str] = None) -> str:
    if custom_bin:
        return custom_bin
    found = shutil.which("agy")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "agy"
    if candidate.is_file():
        return str(candidate)
    return "agy"


def resolve_model_id(name: Optional[str]) -> str:
    if not name:
        return DEFAULT_FALLBACK_MODELS[0]
    cleaned = name.strip().lower()
    if cleaned.startswith("antigravity/"):
        cleaned = cleaned.split("/", 1)[1]
    return MODEL_ALIASES.get(cleaned, DEFAULT_FALLBACK_MODELS[0])


class DuetQueueStore:
    """SQLite-backed persistent queue for autonomous Duet tasks and Human-in-the-Loop approvals."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or (resolve_hermes_home() / "duet")
        self.db_path = self.base_dir / "duet.db"
        self.workspaces_dir = self.base_dir / "workspaces"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS duet_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    status TEXT DEFAULT 'pending',
                    model_used TEXT,
                    result_summary TEXT,
                    approval_action TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS duet_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    level TEXT DEFAULT 'INFO',
                    message TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def add_log(self, task_id: int, message: str, level: str = "INFO") -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO duet_logs (task_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (task_id, level, message, _now_str()),
            )
            conn.commit()
        finally:
            conn.close()

    def add_task(self, title: str, category: str = "general") -> int:
        ts = _now_str()
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO duet_tasks (title, category, status, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?)
                """,
                (title, category, ts, ts),
            )
            tid = int(cur.lastrowid or 0)
            conn.commit()
        finally:
            conn.close()
        self.add_log(tid, f"Task added to queue (category={category}).")
        return tid

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM duet_tasks ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_task_detail(self, task_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM duet_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            logs = conn.execute(
                "SELECT * FROM duet_logs WHERE task_id = ? ORDER BY id ASC", (task_id,)
            ).fetchall()
            data = dict(row)
            data["logs"] = [dict(l) for l in logs]
            return data
        finally:
            conn.close()

    def set_status(self, task_id: int, status: str, log_note: Optional[str] = None) -> bool:
        conn = self._connect()
        try:
            row = conn.execute("SELECT id FROM duet_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return False
            ts = _now_str()
            completed = ts if status in ("done", "rejected", "failed") else None
            conn.execute(
                "UPDATE duet_tasks SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at) WHERE id = ?",
                (status, ts, completed, task_id),
            )
            conn.commit()
        finally:
            conn.close()
        if log_note:
            self.add_log(task_id, log_note)
        return True


def run_agy_with_fallback(
    prompt: str,
    preferred_model: Optional[str] = None,
    agy_bin: Optional[str] = None,
    working_dir: Optional[Path] = None,
    timeout_sec: int = 180,
) -> Tuple[str, str]:
    """
    Invoke the official Antigravity CLI (`agy`) in print mode (`-p`),
    automatically falling back across the subscription model pool on quota exhaustion.
    """
    binary = resolve_agy_bin(agy_bin)
    primary = resolve_model_id(preferred_model)
    candidates = [primary] + [m for m in DEFAULT_FALLBACK_MODELS if m != primary]
    cwd = str(working_dir or resolve_hermes_home())

    last_err = ""
    for candidate in candidates:
        cmd = [
            binary,
            "--model",
            candidate,
            "--disable-slash-commands",
            "--print-timeout",
            f"{timeout_sec}s",
            "-p",
            prompt,
        ]
        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec + 15,
            )
            out = (res.stdout or "").strip()
            err = (res.stderr or "").strip()
            if (
                res.returncode == 0
                and out
                and "RESOURCE_EXHAUSTED" not in out
                and "Individual quota reached" not in out
            ):
                return out, candidate
            last_err = err or out or f"agy exited with status {res.returncode}"
        except Exception as exc:
            last_err = str(exc)

    raise RuntimeError(last_err or "All fallback models in Antigravity CLI pool failed.")


# =============================================================================
# OpenAI-Compatible Multi-Model Bridge HTTP Handler
# =============================================================================


def _build_prompt_from_openai_messages(messages: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for msg in messages:
        role = str(msg.get("role") or "user").upper()
        content = msg.get("content") or ""
        if isinstance(content, list):
            text_items = [
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            content = "\n".join(text_items)
        text = str(content).strip()
        if text:
            parts.append(f"[{role}]:\n{text}")
    return "\n\n".join(parts)


class AntigravityBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    agy_bin: Optional[str] = None

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.startswith("/v1/models") or self.path.startswith("/models"):
            models = [
                {
                    "id": m,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "antigravity",
                    "context_length": 1048576,
                }
                for m in DEFAULT_FALLBACK_MODELS
            ]
            self._send_json(200, {"object": "list", "data": models})
        elif self.path.startswith("/health"):
            self._send_json(
                200,
                {
                    "status": "ok",
                    "agy_bin": resolve_agy_bin(self.agy_bin),
                    "fallback_models": list(DEFAULT_FALLBACK_MODELS),
                },
            )
        else:
            self._send_json(200, {"status": "ok"})

    def do_POST(self) -> None:
        if not (self.path.startswith("/v1/chat/completions") or self.path.startswith("/chat/completions")):
            self._send_json(404, {"error": {"message": f"Unsupported path: {self.path}"}})
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req = json.loads(body)
        except Exception as exc:
            self._send_json(400, {"error": {"message": f"Invalid JSON: {exc}"}})
            return

        model_req = str(req.get("model") or DEFAULT_FALLBACK_MODELS[0])
        messages = req.get("messages") or []
        stream = bool(req.get("stream", False))
        prompt = _build_prompt_from_openai_messages(messages)

        try:
            reply_text, used_model = run_agy_with_fallback(
                prompt=prompt,
                preferred_model=model_req,
                agy_bin=self.agy_bin,
            )
        except Exception as exc:
            self._send_json(500, {"error": {"message": str(exc), "type": "antigravity_cli_error"}})
            return

        comp_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        created = int(time.time())

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            chunk1 = {
                "id": comp_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": used_model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply_text}, "finish_reason": None}],
            }
            chunk2 = {
                "id": comp_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": used_model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            self.wfile.write(f"data: {json.dumps(chunk1, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(chunk2, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self._send_json(
                200,
                {
                    "id": comp_id,
                    "object": "chat.completion",
                    "created": created,
                    "model": used_model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": reply_text},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )


# =============================================================================
# Duet Worker & Web Dashboard
# =============================================================================

_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Antigravity Duet — Autonomous Task Queue</title>
<style>
  :root {
    --bg: #0b0f17; --card: #151c28; --border: #263147;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --amber: #f59e0b; --red: #ef4444;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 1020px; margin-left: auto; margin-right: auto;
  }
  header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 20px;
    flex-wrap: wrap; gap: 10px;
  }
  .badge {
    background: rgba(34,197,94,0.15); color: var(--green);
    border: 1px solid var(--green); padding: 5px 12px; border-radius: 999px;
    font-size: 13px; font-weight: 600;
  }
  .new-box, .task-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; margin-bottom: 16px;
  }
  .new-form { display: flex; gap: 10px; flex-wrap: wrap; }
  input[type=text], select {
    background: #0f1520; color: var(--text); border: 1px solid var(--border);
    padding: 10px 14px; border-radius: 8px; font-size: 14px;
  }
  input[type=text] { flex: 1; min-width: 240px; }
  button {
    cursor: pointer; border: none; padding: 10px 16px; border-radius: 8px;
    font-weight: 600; font-size: 13px;
  }
  .btn-primary { background: var(--accent); color: #090d16; }
  .btn-approve { background: var(--green); color: #052e16; }
  .btn-reject { background: var(--red); color: #fff; }
  .status-pill {
    padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; text-transform: uppercase;
  }
  .meta { font-size: 12px; color: var(--muted); }
  pre {
    background: #090d14; padding: 12px; border-radius: 8px; border: 1px solid #1e293b;
    white-space: pre-wrap; word-wrap: break-word; font-size: 13px; color: #cbd5e1;
    max-height: 300px; overflow-y: auto; margin: 10px 0;
  }
</style>
</head>
<body>
  <header>
    <div>
      <h2 style="margin:0;">Hermes Antigravity Duet</h2>
      <div class="meta">Autonomous Background Queue • Multi-Model Antigravity CLI Fallback • Human-in-the-Loop Safety</div>
    </div>
    <span class="badge">Multi-Model Subscription Pool</span>
  </header>
  <div class="new-box">
    <form class="new-form" method="POST" action="/add">
      <select name="category">
        <option value="general">General</option>
        <option value="research">Research</option>
        <option value="code">Code</option>
        <option value="ops">Ops</option>
      </select>
      <input type="text" name="title" placeholder="Describe an autonomous background task..." required>
      <button type="submit" class="btn-primary">+ Enqueue Task</button>
    </form>
  </div>
  __TASKS_HTML__
</body>
</html>
"""


class DuetDashboardHandler(BaseHTTPRequestHandler):
    store: DuetQueueStore

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _redirect(self, loc: str = "/") -> None:
        self.send_response(303)
        self.send_header("Location", loc)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/api/status"):
            tasks = self.store.list_tasks(limit=30)
            raw = json.dumps({"status": "ok", "tasks": tasks}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        tasks = self.store.list_tasks(limit=30)
        cards: List[str] = []
        for t in tasks:
            tid = int(t["id"])
            st = str(t["status"])
            approval_html = ""
            if st == "awaiting_approval":
                approval_html = f"""
                <div style="margin-top:10px; padding:10px; border:1px solid #f59e0b; border-radius:8px;">
                  <strong>Approval Required:</strong> {html.escape(str(t.get('approval_action') or ''))}
                  <div style="margin-top:8px; display:flex; gap:8px;">
                    <form method="POST" action="/approve"><input type="hidden" name="id" value="{tid}"><button class="btn-approve">Approve</button></form>
                    <form method="POST" action="/reject"><input type="hidden" name="id" value="{tid}"><button class="btn-reject">Reject</button></form>
                  </div>
                </div>
                """
            summary_html = (
                f"<pre>{html.escape(str(t['result_summary']))}</pre>"
                if t.get("result_summary")
                else ""
            )
            cards.append(
                f"""
                <div class="task-card">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong>#{tid} [{html.escape(str(t['category']))}] — {html.escape(str(t['title']))}</strong>
                    <span class="status-pill">{html.escape(st)}</span>
                  </div>
                  <div class="meta">Created: {html.escape(str(t['created_at']))} • Model: {html.escape(str(t.get('model_used') or '-'))}</div>
                  {approval_html}
                  {summary_html}
                </div>
                """
            )
        body_html = "\n".join(cards) if cards else "<div class='task-card'>No tasks in queue yet.</div>"
        page = _DASHBOARD_TEMPLATE.replace("__TASKS_HTML__", body_html).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        params = urllib.parse.parse_qs(raw)

        if self.path == "/add":
            title = (params.get("title", [""])[0]).strip()
            category = (params.get("category", ["general"])[0]).strip()
            if title:
                self.store.add_task(title=title, category=category)
        elif self.path == "/approve":
            tid = int(params.get("id", ["0"])[0])
            self.store.set_status(tid, "approved", "Approved via Web Dashboard.")
        elif self.path == "/reject":
            tid = int(params.get("id", ["0"])[0])
            self.store.set_status(tid, "rejected", "Rejected via Web Dashboard.")
        self._redirect("/")


def process_next_task(store: DuetQueueStore, agy_bin: Optional[str] = None) -> bool:
    conn = store._connect()
    try:
        row = conn.execute(
            "SELECT * FROM duet_tasks WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            return False
        tid = int(row["id"])
        conn.execute(
            "UPDATE duet_tasks SET status = 'running', updated_at = ? WHERE id = ?",
            (_now_str(), tid),
        )
        conn.commit()
    finally:
        conn.close()

    task_ws = store.workspaces_dir / f"task_{tid}"
    task_ws.mkdir(parents=True, exist_ok=True)
    store.add_log(tid, f"Starting autonomous task #{tid}: {row['title']}")

    worker_prompt = (
        f"You are an autonomous Duet background worker.\n"
        f"Task #{tid} ({row['category']}): {row['title']}\n"
        f"Working directory: {task_ws}\n\n"
        f"Complete all research, analysis, drafting, and local file preparation autonomously. "
        f"If the task requires an external or sensitive side-effect (sending external messages, "
        f"modifying production records, or destructive actions), do NOT execute that final step; "
        f"instead end your response with:\n"
        f"[APPROVAL_REQUIRED: <concise description of the pending action>]"
    )

    try:
        output, used_model = run_agy_with_fallback(
            prompt=worker_prompt,
            agy_bin=agy_bin,
            working_dir=task_ws,
        )
        match = re.search(r"\[APPROVAL_REQUIRED:\s*(.+?)\]", output, flags=re.DOTALL)
        conn2 = store._connect()
        try:
            if match:
                action_desc = match.group(1).strip()
                clean_out = output[: match.start()].strip()
                conn2.execute(
                    """
                    UPDATE duet_tasks
                    SET status = 'awaiting_approval',
                        model_used = ?,
                        result_summary = ?,
                        approval_action = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (used_model, clean_out, action_desc, _now_str(), tid),
                )
            else:
                conn2.execute(
                    """
                    UPDATE duet_tasks
                    SET status = 'done',
                        model_used = ?,
                        result_summary = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (used_model, output, _now_str(), _now_str(), tid),
                )
            conn2.commit()
        finally:
            conn2.close()
        store.add_log(tid, f"Completed pass with model {used_model}.")
    except Exception as exc:
        store.add_log(tid, f"Task execution failed: {exc}", level="ERROR")
        store.set_status(tid, "failed", f"Error: {exc}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hermes Antigravity Duet — Multi-Model Bridge & Autonomous Worker"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_bridge = sub.add_parser("bridge", help="Run the local OpenAI-compatible multi-model agy bridge")
    p_bridge.add_argument("--host", default="127.0.0.1")
    p_bridge.add_argument("--port", type=int, default=8765)
    p_bridge.add_argument("--agy-bin", default=None)

    p_worker = sub.add_parser("worker", help="Run the Duet background worker + Web Dashboard")
    p_worker.add_argument("--host", default="127.0.0.1")
    p_worker.add_argument("--port", type=int, default=8899)
    p_worker.add_argument("--agy-bin", default=None)

    args = parser.parse_args()
    if args.cmd == "bridge":
        AntigravityBridgeHandler.agy_bin = args.agy_bin
        srv = ThreadingHTTPServer((args.host, args.port), AntigravityBridgeHandler)
        print(f"Antigravity OpenAI Bridge listening on http://{args.host}:{args.port}/v1", flush=True)
        srv.serve_forever()
    elif args.cmd == "worker":
        store = DuetQueueStore()
        DuetDashboardHandler.store = store
        srv = ThreadingHTTPServer((args.host, args.port), DuetDashboardHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        print(f"Duet Worker & Dashboard listening on http://{args.host}:{args.port}", flush=True)
        while True:
            did = process_next_task(store, agy_bin=args.agy_bin)
            time.sleep(3 if did else 12)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
