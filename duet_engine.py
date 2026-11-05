#!/usr/bin/env python3
"""
Sanitized, generic Duet Queue Store, Multi-Model Antigravity CLI Fallback,
and Secure Human-in-the-Loop Web Dashboard for Hermes Agent.

Contains zero personal data, hardcoded paths, or third-party credentials.
All state is stored inside `$HERMES_HOME/plugin-data/antigravity-duet/`.
"""

from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
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
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home()).resolve()
    except Exception:
        pass
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def get_plugin_data_dir() -> Path:
    base = resolve_hermes_home() / "plugin-data" / "antigravity-duet"
    base.mkdir(parents=True, exist_ok=True)
    return base


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


def resolve_ruflo_bin(custom_bin: Optional[str] = None) -> str:
    if custom_bin:
        return custom_bin
    found = shutil.which("ruflo")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "ruflo"
    if candidate.is_file():
        return str(candidate)
    return "ruflo"


def run_ruflo_command(
    sub_args: List[str],
    ruflo_bin: Optional[str] = None,
    working_dir: Optional[Path] = None,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    """Execute a sanitized Ruflo command inside the plugin data directory."""
    binary = resolve_ruflo_bin(ruflo_bin)
    ruflo_cwd = working_dir or (get_plugin_data_dir() / "ruflo")
    ruflo_cwd.mkdir(parents=True, exist_ok=True)
    cmd = [binary] + [str(a) for a in sub_args]
    try:
        res = subprocess.run(
            cmd,
            cwd=str(ruflo_cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        return {
            "ok": res.returncode == 0,
            "exit_code": res.returncode,
            "stdout": out,
            "stderr": err,
        }
    except Exception as exc:
        return {"ok": False, "exit_code": -1, "error": str(exc)}


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
        self.base_dir = base_dir or get_plugin_data_dir()
        self.db_path = self.base_dir / "duet.db"
        self.workspaces_dir = self.base_dir / "workspaces"
        self.token_file = self.base_dir / "dashboard_token.txt"
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
                    status TEXT DEFAULT 'awaiting_approval',
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS duet_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def add_chat(self, agent_id: str, sender: str, message: str) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO duet_chats (agent_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
                (agent_id, sender, message, _now_str()),
            )
            cid = int(cur.lastrowid or 0)
            conn.commit()
            return cid
        finally:
            conn.close()

    def list_chats(self, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM duet_chats ORDER BY id ASC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]
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

    def add_task(
        self,
        title: str,
        category: str = "general",
        status: str = "awaiting_approval",
    ) -> int:
        ts = _now_str()
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO duet_tasks (title, category, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, category, status, ts, ts),
            )
            tid = int(cur.lastrowid or 0)
            conn.commit()
        finally:
            conn.close()
        self.add_log(tid, f"Task added to queue (category={category}, status={status}).")
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
    Invoke the official Antigravity CLI (`agy`) in print mode (`-p`) with tools confined (`--no-tools`),
    automatically falling back across the subscription model pool on quota exhaustion.
    """
    binary = resolve_agy_bin(agy_bin)
    primary = resolve_model_id(preferred_model)
    candidates = [primary] + [m for m in DEFAULT_FALLBACK_MODELS if m != primary]
    cwd = str(working_dir or get_plugin_data_dir())

    last_err = ""
    for candidate in candidates:
        cmd = [
            binary,
            "--model",
            candidate,
            "--no-tools",
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


def get_or_generate_launch_token(data_dir: Path) -> str:
    """Generate a random auth token per launch, stored with permissions 0600 in plugin-data."""
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    token_file = data_dir / "dashboard_token.txt"
    try:
        fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w") as f:
            f.write(token)
    except Exception:
        token_file.write_text(token)
        try:
            os.chmod(str(token_file), 0o600)
        except Exception:
            pass
    return token


# =============================================================================
# Duet Worker & Secure Web Dashboard
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
      <div class="meta">Autonomous Background Queue • Human-in-the-Loop Approval Gate • Ruflo Swarm Controller</div>
    </div>
    <span class="badge">Authenticated Session</span>
  </header>
  <div class="new-box">
    <form class="new-form" method="POST" action="/add">
      <input type="hidden" name="token" value="__AUTH_TOKEN__">
      <select name="category">
        <option value="general">General</option>
        <option value="research">Research</option>
        <option value="code">Code</option>
        <option value="ops">Ops</option>
      </select>
      <input type="text" name="title" placeholder="Describe an autonomous background task..." required>
      <button type="submit" class="btn-primary">+ Enqueue Task (Approved)</button>
    </form>
  </div>
  __TASKS_HTML__
</body>
</html>
"""


class DuetDashboardHandler(BaseHTTPRequestHandler):
    store: DuetQueueStore
    auth_token: str
    server_port: int = 8899
    server_host: str = "127.0.0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _is_valid_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        valid = {
            f"127.0.0.1:{self.server_port}",
            f"localhost:{self.server_port}",
            "127.0.0.1",
            "localhost",
        }
        return host in valid

    def _is_valid_origin(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            valid = {
                f"http://127.0.0.1:{self.server_port}",
                f"http://localhost:{self.server_port}",
            }
            return origin in valid
        referer = (self.headers.get("Referer") or "").strip()
        if referer:
            return (
                referer.startswith(f"http://127.0.0.1:{self.server_port}")
                or referer.startswith(f"http://localhost:{self.server_port}")
            )
        # If neither is sent (e.g. direct programmatic call), rely on token authentication
        return True

    def _extract_token(self, post_params: Optional[Dict[str, List[str]]] = None) -> Optional[str]:
        auth_hdr = (self.headers.get("Authorization") or "").strip()
        if auth_hdr.lower().startswith("bearer "):
            return auth_hdr[7:].strip()
        x_tok = (self.headers.get("X-Duet-Token") or "").strip()
        if x_tok:
            return x_tok
        if post_params and "token" in post_params:
            return (post_params["token"][0] or "").strip()
        query = urllib.parse.urlparse(self.path).query
        if query:
            q_dict = urllib.parse.parse_qs(query)
            if "token" in q_dict:
                return (q_dict["token"][0] or "").strip()
        cookie_header = self.headers.get("Cookie") or ""
        for item in cookie_header.split(";"):
            k, _, v = item.strip().partition("=")
            if k.strip() == "duet_token":
                return v.strip()
        return None

    def _is_authenticated(self, post_params: Optional[Dict[str, List[str]]] = None) -> bool:
        supplied = self._extract_token(post_params)
        if not supplied:
            return False
        return secrets.compare_digest(supplied, self.auth_token)

    def _send_forbidden(self, reason: str) -> None:
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": False, "error": f"Forbidden: {reason}"}).encode("utf-8"))

    def _redirect(self, loc: str = "/") -> None:
        query_token = f"?token={urllib.parse.quote(self.auth_token)}"
        target = loc if ("?" in loc or "#" in loc) else f"{loc}{query_token}"
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header("Set-Cookie", f"duet_token={self.auth_token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._is_valid_host():
            self._send_forbidden("Host header mismatch.")
            return

        if self.path.startswith("/api/status"):
            if not self._is_authenticated():
                self._send_forbidden("Authentication token required for /api/status.")
                return
            tasks = self.store.list_tasks(limit=30)
            chats = self.store.list_chats(limit=200)
            raw = json.dumps({"status": "ok", "tasks": tasks, "chats": chats}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        # Dashboard web UI
        if not self._is_authenticated():
            self._send_forbidden("Valid launch token required to view dashboard. Pass ?token=<launch_token>.")
            return

        tasks = self.store.list_tasks(limit=30)
        cards: List[str] = []
        token_val = html.escape(self.auth_token)
        for t in tasks:
            tid = int(t["id"])
            st = str(t["status"])
            approval_html = ""
            if st == "awaiting_approval":
                approval_html = f"""
                <div style="margin-top:10px; padding:10px; border:1px solid #f59e0b; border-radius:8px;">
                  <strong>Human Approval Required:</strong> {html.escape(str(t.get('approval_action') or 'Task queued as awaiting approval.'))}
                  <div style="margin-top:8px; display:flex; gap:8px;">
                    <form method="POST" action="/approve">
                      <input type="hidden" name="token" value="{token_val}">
                      <input type="hidden" name="id" value="{tid}">
                      <button class="btn-approve">Approve Task</button>
                    </form>
                    <form method="POST" action="/reject">
                      <input type="hidden" name="token" value="{token_val}">
                      <input type="hidden" name="id" value="{tid}">
                      <button class="btn-reject">Reject</button>
                    </form>
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
        page = _DASHBOARD_TEMPLATE.replace("__AUTH_TOKEN__", token_val).replace("__TASKS_HTML__", body_html).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Set-Cookie", f"duet_token={self.auth_token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self) -> None:
        if not self._is_valid_host():
            self._send_forbidden("Host header mismatch.")
            return

        if not self._is_valid_origin():
            self._send_forbidden("Cross-origin request rejected.")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        params = urllib.parse.parse_qs(raw)

        if not self._is_authenticated(params):
            self._send_forbidden("Invalid or missing authorization token.")
            return

        if self.path == "/add":
            title = (params.get("title", [""])[0]).strip()
            category = (params.get("category", ["general"])[0]).strip()
            if title:
                # Explicit human action from dashboard creates an approved, runnable task
                self.store.add_task(title=title, category=category, status="approved")
        elif self.path == "/approve":
            tid = int(params.get("id", ["0"])[0])
            self.store.set_status(tid, "approved", "Approved by operator via Web Dashboard.")
        elif self.path == "/reject":
            tid = int(params.get("id", ["0"])[0])
            self.store.set_status(tid, "rejected", "Rejected by operator via Web Dashboard.")
        elif self.path == "/chat":
            agent_id = (params.get("agent_id", ["duffy"])[0]).strip()
            msg = (params.get("message", [""])[0]).strip()
            if msg:
                self.store.add_chat(agent_id, "user", msg)
                threading.Thread(
                    target=_handle_public_agent_chat,
                    args=(self.store, agent_id, msg),
                    daemon=True,
                ).start()
            raw_json = json.dumps({"status": "queued"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw_json)))
            self.end_headers()
            self.wfile.write(raw_json)
            return

        self._redirect("/")


def _handle_public_agent_chat(store: DuetQueueStore, agent_id: str, user_msg: str) -> None:
    try:
        prompt = (
            f"You are specialist agent '{agent_id}' inside the Hermes Antigravity Duet system.\n"
            f"User message: {user_msg}\n\n"
            f"Respond concisely and helpfully."
        )
        reply, _ = run_agy_with_fallback(prompt=prompt)
        store.add_chat(agent_id, "agent", reply.strip())
    except Exception as exc:
        store.add_chat(agent_id, "agent", f"Error generating response: {exc}")


def process_next_task(store: DuetQueueStore, agy_bin: Optional[str] = None) -> bool:
    """
    Process the next human-approved task in the queue.
    Only tasks with status='approved' are executed by the worker.
    """
    conn = store._connect()
    try:
        row = conn.execute(
            "SELECT * FROM duet_tasks WHERE status = 'approved' ORDER BY id ASC LIMIT 1"
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
    store.add_log(tid, f"Starting approved task #{tid}: {row['title']}")

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
        description="Hermes Antigravity Duet — Autonomous Task Worker & Dashboard"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_worker = sub.add_parser("worker", help="Run the Duet background worker + Web Dashboard")
    p_worker.add_argument("--host", default="127.0.0.1")
    p_worker.add_argument("--port", type=int, default=8899)
    p_worker.add_argument("--agy-bin", default=None)

    args = parser.parse_args()
    cmd = args.cmd or "worker"
    if cmd == "worker":
        store = DuetQueueStore()
        token = get_or_generate_launch_token(store.base_dir)
        DuetDashboardHandler.store = store
        DuetDashboardHandler.auth_token = token
        DuetDashboardHandler.server_port = args.port
        DuetDashboardHandler.server_host = args.host

        srv = ThreadingHTTPServer((args.host, args.port), DuetDashboardHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        print(f"Duet Worker & Dashboard listening on http://{args.host}:{args.port}/?token={token}", flush=True)
        print(f"Auth token (stored 0600 in {store.token_file}): {token}", flush=True)
        while True:
            did = process_next_task(store, agy_bin=args.agy_bin)
            time.sleep(3 if did else 10)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
