#!/usr/bin/env python3
"""
Hermes Dashboard API Server
Serves static files + REST API at http://localhost:19800

Endpoints:
  GET  /                          -> dashboard.html
  GET  /api/status                -> agent status
  GET  /api/stats                 -> overview stats
  GET  /api/sessions              -> session list (query: limit, offset)
  GET  /api/sessions/{id}/messages -> messages in a session
  GET  /api/memory                -> memory entries
  POST /api/memory/add            -> add a memory entry
  DELETE /api/memory              -> delete a memory entry
  GET  /api/cron                  -> cron job list
  GET  /api/config                -> read config
  POST /api/config                -> write config key
  GET  /api/logs                  -> recent log lines
  POST /v1/chat/completions       -> proxy to agent (streaming SSE)
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Path setup ──────────────────────────────────────────────────────────────
THIS_DIR = Path(__file__).parent.resolve()
ROOT_DIR = THIS_DIR.parent.parent  # hermes-agent-windows/
sys.path.insert(0, str(ROOT_DIR))

try:
    from aiohttp import web, ClientSession, ClientTimeout
    AIOHTTP_OK = True
except ImportError:
    AIOHTTP_OK = False
    print("ERROR: aiohttp not installed. Run: pip install aiohttp")
    sys.exit(1)

logger = logging.getLogger("hermes.dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PORT = 19800
AGENT_API = "http://127.0.0.1:8642"  # api_server.py

# ── CORS helper ─────────────────────────────────────────────────────────────
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
}

def json_resp(data, status=200):
    return web.Response(
        text=json.dumps(data, ensure_ascii=False, default=str),
        content_type="application/json",
        headers=CORS,
        status=status,
    )

def err_resp(msg, status=500):
    return json_resp({"error": msg}, status)

# ── Lazy hermes imports ─────────────────────────────────────────────────────
_state_db = None
def _db():
    global _state_db
    if _state_db is None:
        try:
            from hermes_state import SessionDB
            _state_db = SessionDB()
        except Exception as e:
            logger.warning("SessionDB unavailable: %s", e)
    return _state_db

def _memory_store():
    try:
        from tools.memory_tool import MemoryStore
        store = MemoryStore()
        store.load_from_disk()
        return store
    except Exception as e:
        logger.warning("MemoryStore unavailable: %s", e)
        return None

# ── /api/status ─────────────────────────────────────────────────────────────
async def handle_status(request):
    """Check whether the agent API server is reachable."""
    agent_ok = False
    agent_info = {}
    try:
        async with ClientSession(timeout=ClientTimeout(total=2)) as s:
            async with s.get(f"{AGENT_API}/health") as r:
                if r.status == 200:
                    agent_ok = True
                    try:
                        agent_info = await r.json(content_type=None)
                    except Exception:
                        agent_info = {}
    except Exception:
        pass

    # Read current model from config.yaml
    model = "unknown"
    provider = "unknown"
    try:
        import yaml
        from hermes_cli.config import get_config_path
        cfg = yaml.safe_load(get_config_path().read_text(encoding="utf-8"))
        model = cfg.get("model", {}).get("default", "unknown")
        provider = cfg.get("model", {}).get("provider", "unknown")
    except Exception:
        pass

    return json_resp({
        "agent_running": agent_ok,
        "agent_api": AGENT_API,
        "agent_info": agent_info,
        "model": model,
        "provider": provider,
    })

# ── /api/stats ───────────────────────────────────────────────────────────────
async def handle_stats(request):
    db = _db()
    total_sessions = 0
    total_tokens = 0
    if db:
        try:
            total_sessions = db.session_count()
            # Sum tokens from all sessions
            import sqlite3
            conn = sqlite3.connect(str(db._db_path if hasattr(db, "_db_path") else
                                       __import__("hermes_state").DEFAULT_DB_PATH))
            row = conn.execute(
                "SELECT SUM(input_tokens+output_tokens) FROM sessions"
            ).fetchone()
            conn.close()
            total_tokens = int(row[0] or 0)
        except Exception as e:
            logger.debug("stats error: %s", e)

    # Count cron jobs
    active_tasks = 0
    try:
        from cron.jobs import list_jobs
        active_tasks = len(list_jobs())
    except Exception:
        pass

    # Count skills
    active_skills = 0
    try:
        from hermes_cli.skills_config import list_enabled_skills
        active_skills = len(list_enabled_skills())
    except Exception:
        try:
            skills_dir = ROOT_DIR / "skills"
            if skills_dir.exists():
                active_skills = sum(1 for _ in skills_dir.rglob("*.md"))
        except Exception:
            pass

    def _fmt_tokens(n):
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)

    return json_resp({
        "total_sessions": total_sessions,
        "total_tokens": total_tokens,
        "total_tokens_fmt": _fmt_tokens(total_tokens),
        "active_skills": active_skills,
        "active_tasks": active_tasks,
    })

# ── /api/sessions ────────────────────────────────────────────────────────────
async def handle_sessions(request):
    db = _db()
    if not db:
        return json_resp({"sessions": [], "total": 0})
    try:
        limit = int(request.rel_url.query.get("limit", 20))
        offset = int(request.rel_url.query.get("offset", 0))
        sessions = db.list_sessions_rich(limit=limit, offset=offset)
        total = db.session_count()
        return json_resp({"sessions": sessions, "total": total})
    except Exception as e:
        return err_resp(str(e))

# ── /api/sessions/{id}/messages ──────────────────────────────────────────────
async def handle_session_messages(request):
    session_id = request.match_info["id"]
    db = _db()
    if not db:
        return json_resp({"messages": []})
    try:
        msgs = db.get_messages(session_id)
        return json_resp({"messages": msgs})
    except Exception as e:
        return err_resp(str(e))

# ── /api/memory ──────────────────────────────────────────────────────────────
async def handle_memory_get(request):
    store = _memory_store()
    if not store:
        return json_resp({"memory": [], "user": []})
    return json_resp({
        "memory": store.memory_entries,
        "user": store.user_entries,
    })

async def handle_memory_add(request):
    try:
        body = await request.json()
        target = body.get("target", "memory")  # "memory" or "user"
        content = body.get("content", "").strip()
        if not content:
            return err_resp("content required", 400)
        store = _memory_store()
        if not store:
            return err_resp("memory unavailable")
        result = store.add(target, content)
        return json_resp(result)
    except Exception as e:
        return err_resp(str(e))

async def handle_memory_delete(request):
    try:
        body = await request.json()
        target = body.get("target", "memory")
        old_text = body.get("text", "")
        if not old_text:
            return err_resp("text required", 400)
        store = _memory_store()
        if not store:
            return err_resp("memory unavailable")
        result = store.remove(target, old_text)
        return json_resp(result)
    except Exception as e:
        return err_resp(str(e))

# ── /api/cron ────────────────────────────────────────────────────────────────
async def handle_cron(request):
    try:
        from cron.jobs import list_jobs
        jobs = list_jobs(include_disabled=True)
        return json_resp({"jobs": jobs})
    except Exception as e:
        return json_resp({"jobs": [], "error": str(e)})

async def handle_cron_run(request):
    job_id = request.match_info["id"]
    try:
        from cron.jobs import trigger_job
        job = trigger_job(job_id)
        return json_resp({"ok": bool(job), "job": job})
    except Exception as e:
        return err_resp(str(e))

# ── /api/config ──────────────────────────────────────────────────────────────
async def handle_provider_models(request):
    """Return provider → models mapping from hermes_cli/models.py."""
    try:
        import ast
        src = (ROOT_DIR / "hermes_cli" / "models.py").read_text(encoding="utf-8")
        m = re.search(r'_PROVIDER_MODELS\s*:\s*[^=]+=\s*(\{.*?\n\})', src, re.DOTALL)
        if m:
            data = ast.literal_eval(m.group(1))
            return json_resp(data)
    except Exception as e:
        logger.debug("provider_models parse error: %s", e)
    # hardcoded fallback
    return json_resp({
        "kimi-coding":  ["kimi-k2.5","kimi-k2-thinking","kimi-k2-thinking-turbo","kimi-k2-turbo-preview","kimi-k2-0905-preview"],
        "moonshot":     ["kimi-k2.5","kimi-k2-thinking","kimi-k2-turbo-preview"],
        "minimax-cn":   ["MiniMax-M2.7","MiniMax-M2.5","MiniMax-M1","MiniMax-M1-40k","MiniMax-M1-80k"],
        "minimax":      ["MiniMax-M2.7","MiniMax-M2.5","MiniMax-M1","MiniMax-M1-40k"],
        "anthropic":    ["claude-opus-4-6","claude-sonnet-4-6","claude-haiku-4-5-20251001"],
        "deepseek":     ["deepseek-chat","deepseek-reasoner"],
        "openrouter":   [],
        "custom":       [],
    })

async def handle_config_get(request):
    result = {}
    try:
        import yaml
        from hermes_cli.config import get_config_path, get_env_path
        cfg_path = get_config_path()
        env_path = get_env_path()

        if cfg_path.exists():
            result["yaml"] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        else:
            result["yaml"] = {}

        # Read .env, redact secrets
        env_vars = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    sensitive = any(x in k.lower() for x in ["key", "secret", "token", "pass", "auth"])
                    env_vars[k] = "••••••" if (sensitive and v) else v
        result["env"] = env_vars
    except Exception as e:
        result["error"] = str(e)
    return json_resp(result)

async def handle_config_post(request):
    try:
        body = await request.json()
        # Expect: { "type": "env", "key": "KIMI_API_KEY", "value": "..." }
        #      or { "type": "yaml", "key": "model.default", "value": "..." }
        cfg_type = body.get("type", "env")
        key = body.get("key", "").strip()
        value = str(body.get("value", "")).strip()
        if not key:
            return err_resp("key required", 400)

        from hermes_cli.config import get_env_path, get_config_path

        if cfg_type == "env":
            env_path = get_env_path()
            lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
            found = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(key + "=") or stripped.startswith(key + " ="):
                    new_lines.append(f'{key}="{value}"')
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f'{key}="{value}"')
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            return json_resp({"ok": True, "key": key})

        elif cfg_type == "yaml":
            import yaml
            cfg_path = get_config_path()
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {} if cfg_path.exists() else {}
            # dotted key
            parts = key.split(".")
            d = cfg
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = value
            cfg_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
            return json_resp({"ok": True, "key": key})

        return err_resp("unknown type", 400)
    except Exception as e:
        return err_resp(str(e))

# ── /api/logs ────────────────────────────────────────────────────────────────
# Capture recent log output via a memory handler
_log_buffer: List[Dict] = []
_LOG_MAX = 500

class _BufferHandler(logging.Handler):
    def emit(self, record):
        _log_buffer.append({
            "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": self.format(record),
        })
        if len(_log_buffer) > _LOG_MAX:
            del _log_buffer[0]

_buf_handler = _BufferHandler()
_buf_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_buf_handler)

async def handle_logs(request):
    limit = int(request.rel_url.query.get("limit", 100))
    level = request.rel_url.query.get("level", "")
    logs = _log_buffer[-limit:] if not level else [
        l for l in _log_buffer if l["level"] == level
    ][-limit:]
    return json_resp({"logs": list(reversed(logs))})

# ── /v1/chat/completions proxy ───────────────────────────────────────────────
async def handle_chat_proxy(request):
    """Proxy POST /v1/chat/completions to AGENT_API with SSE passthrough."""
    body_bytes = await request.read()
    try:
        body = json.loads(body_bytes)
    except Exception:
        return err_resp("invalid JSON", 400)

    stream = body.get("stream", False)

    try:
        async with ClientSession(timeout=ClientTimeout(total=300)) as s:
            async with s.post(
                f"{AGENT_API}/v1/chat/completions",
                data=body_bytes,
                headers={"Content-Type": "application/json"},
            ) as upstream:
                if not stream:
                    data = await upstream.read()
                    return web.Response(
                        body=data,
                        content_type="application/json",
                        headers=CORS,
                        status=upstream.status,
                    )
                # SSE streaming — if upstream returned error status, wrap as SSE error
                if upstream.status != 200:
                    err_body = await upstream.read()
                    try:
                        err_json = json.loads(err_body)
                        err_msg = (err_json.get("error") or {}).get("message") or err_json.get("detail") or err_body.decode()
                    except Exception:
                        err_msg = err_body.decode(errors="replace")
                    err_event = (
                        f'data: {json.dumps({"error": {"message": err_msg}})}\n\n'
                        'data: [DONE]\n\n'
                    )
                    return web.Response(
                        text=err_event,
                        content_type="text/event-stream",
                        headers=CORS,
                        status=200,
                    )
                resp = web.StreamResponse(
                    status=200,
                    headers={
                        **CORS,
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )
                await resp.prepare(request)
                async for chunk in upstream.content.iter_any():
                    await resp.write(chunk)
                await resp.write_eof()
                return resp
    except Exception as e:
        logger.error("chat proxy error: %s", e)
        # Agent not running — return helpful error
        if stream:
            error_chunk = 'data: {"error": {"message": "Agent API not running at ' + AGENT_API + '", "type": "connection_error"}}\n\ndata: [DONE]\n\n'
            return web.Response(
                text=error_chunk,
                content_type="text/event-stream",
                headers=CORS,
                status=503,
            )
        return json_resp({
            "error": {
                "message": f"Agent API not running at {AGENT_API}",
                "type": "connection_error",
            }
        }, 503)

# ── Static file server ───────────────────────────────────────────────────────
async def handle_static(request):
    path = request.match_info.get("path", "")
    if not path or path == "/":
        path = "dashboard.html"
    # security: no path traversal
    safe_path = Path(path.lstrip("/"))
    if ".." in safe_path.parts:
        raise web.HTTPForbidden()
    full = THIS_DIR / safe_path
    if not full.exists() or not full.is_file():
        raise web.HTTPNotFound()
    ct, _ = mimetypes.guess_type(str(full))
    return web.FileResponse(full, headers={**CORS, "Content-Type": ct or "text/plain"})

# ── CORS preflight ────────────────────────────────────────────────────────────
async def handle_options(request):
    return web.Response(headers=CORS, status=204)

# ── App assembly ──────────────────────────────────────────────────────────────
def make_app():
    app = web.Application()
    app.router.add_options("/{path_info:.*}", handle_options)

    # API routes
    app.router.add_get("/api/status",                   handle_status)
    app.router.add_get("/api/stats",                    handle_stats)
    app.router.add_get("/api/sessions",                 handle_sessions)
    app.router.add_get("/api/sessions/{id}/messages",   handle_session_messages)
    app.router.add_get("/api/memory",                   handle_memory_get)
    app.router.add_post("/api/memory/add",              handle_memory_add)
    app.router.add_delete("/api/memory",                handle_memory_delete)
    app.router.add_get("/api/cron",                     handle_cron)
    app.router.add_post("/api/cron/run/{id}",           handle_cron_run)
    app.router.add_get("/api/config",                   handle_config_get)
    app.router.add_post("/api/config",                  handle_config_post)
    app.router.add_get("/api/provider-models",          handle_provider_models)
    app.router.add_get("/api/logs",                     handle_logs)

    # Chat proxy
    app.router.add_post("/v1/chat/completions",         handle_chat_proxy)

    # Static files
    app.router.add_get("/",                             handle_static)
    app.router.add_get("/{path:.+}",                    handle_static)

    return app

if __name__ == "__main__":
    app = make_app()
    print(f"Hermes Dashboard API running at http://localhost:{PORT}/dashboard.html")
    web.run_app(app, host="127.0.0.1", port=PORT, access_log=None)
