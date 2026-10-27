"""Estimator HTTP service (specs.md AP-estimate). Stdlib only: one thread per request, the estimator is pure so no locks.

Run: python3 -m pipeline.estimator_api [port]
POST /v1/jobs/parse      {"text": "..."} -> {"fields", "needs_input", "parser": "llm"|"form", ...}; never fails because the LLM is down
POST /v1/jobs/estimate   body = job fields           -> record, or 422 {"error", "detail"}
                         body = {"jobs": [...]}      -> {"results": [...]} (200, per-job errors inline)
POST /v1/chat            {"session_id", "text", "home_hub"?} -> {"reply", "job", "needs_input", "estimate", "home_hub", "suggestions", "guarded", "ended"}; 429 rate_limited; 503 chat_unavailable
POST /v1/chat/placement  {"session_id", "hub"} -> {"reply", "awaiting_end"}; for the scheduler (not built yet). Away from home it asks "is that everything?"
                         and a "yes" to that ends the chat (ended: true) and deletes the conversation
                         without the agent environment (run with .venv-agent/bin/python to enable it)
POST /v1/jobs/preview    {fields..., "home_hub", "latency_class"?} -> scheduler verdict (covered|held|not_covered|infeasible|data_unavailable), read-only.
                         Surplus is SIMULATED until the surplus rule exists; `basis` says so.
GET  /v1/hubs/gpus       -> per-hub GPU type and count
"""
import json
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import guardrails
from .location import HUB_NAMES, detect_hub, strip_location
from .estimator import HUB_GPUS, EstimateError, estimate, estimate_many
from .parser import ParseError, parse
from . import scheduler

MAX_BODY = 1_000_000
MAX_BATCH = 5000


_agent = None
_sessions = {}  # session_id -> {"job", "needs", "asks", "times"}; in memory, oldest dropped past MAX_SESSIONS
MAX_SESSIONS = 1000


def _get_agent():
    global _agent
    if _agent is None:
        from .agent import make_agent
        _agent = make_agent()
    return _agent


def _placement(body):
    sid, hub = body.get("session_id"), body.get("hub")
    if not isinstance(sid, str) or hub not in HUB_NAMES:
        return 422, {"error": "validation_failed", "detail": "session_id and a known hub are required"}
    if sid not in _sessions:
        return 404, {"error": "no_session"}
    try:
        from .agent import notify_placement
        return 200, notify_placement(_get_agent(), sid, hub)
    except Exception:
        return 503, {"error": "chat_unavailable"}


def _preview(body):
    home = body.get("home_hub")
    if home not in HUB_NAMES or body.get("latency_class", "regional") not in ("local", "regional", "batch"):
        return 422, {"error": "validation_failed", "detail": "home_hub and latency_class must be valid"}
    try:
        rec = estimate(body)
    except EstimateError as e:
        return 422, {"error": e.code, "detail": e.detail}
    except (TypeError, ValueError, AttributeError):
        return 422, {"error": "validation_failed", "detail": None}
    now = scheduler.floor_h(datetime.now(timezone.utc)) + scheduler.H1
    hubs = scheduler.load_hubs()
    forecast = scheduler.synthetic_surplus({h["grid"] for h in hubs.values()}, now, scheduler.CFG["horizon_h"])  # stand-in until D6
    job = scheduler.make_job(rec, home, now, body.get("latency_class", "regional"))
    out = scheduler.preview(job, now, forecast, hubs, energy_kwh=rec["energy_kwh"])
    return 200, {**out, "basis": "simulated", "plan_basis_asof": now.isoformat(), "valid_until": (now + scheduler.H1).isoformat(), "estimate": rec}


def _chat(body):
    """-> (status, body). The agent is built on first use so the rest of the service runs without LangGraph installed."""
    sid, text, home = body.get("session_id"), body.get("text"), body.get("home_hub")
    if not (isinstance(sid, str) and 0 < len(sid) <= 64 and isinstance(text, str) and 0 < len(text.strip()) <= 2000):
        return 422, {"error": "validation_failed", "detail": "session_id (1-64 chars) and text (1-2000 chars) are required"}
    if home is not None and home not in HUB_NAMES:
        return 422, {"error": "validation_failed", "detail": "unknown home_hub"}
    st = _sessions.setdefault(sid, {"job": {}, "needs": [], "asks": 0, "times": []})
    while len(_sessions) > MAX_SESSIONS:
        _sessions.pop(next(iter(_sessions)))
    now = time.time()
    st["times"] = [t for t in st["times"] if now - t < 3600]
    if len(st["times"]) >= guardrails.MAX_MSGS_PER_HOUR:
        return 429, {"error": "rate_limited"}
    st["times"].append(now)

    found = detect_hub(text)
    if found and found != home:
        home = found
    refusal = guardrails.check(text, bool(st["job"]) or st["asks"] > 0 or found is not None)  # a place or a conversation in progress is on-topic
    if refusal:  # no LLM call
        return 200, {"reply": refusal, "job": st["job"], "needs_input": st["needs"], "estimate": None, "home_hub": home,
                     "suggestions": guardrails.suggestions(st["needs"], False), "guarded": True}
    loc_note = f"Location set to {HUB_NAMES[home]}.\n" if found and found != body.get("home_hub") else ""
    job_text = strip_location(text) if found else text  # the location is handled in code, the LLM only reads the job
    if not job_text:
        reply = loc_note + "Now describe the job you want to run."
        return 200, {"reply": reply, "job": st["job"], "needs_input": st["needs"], "estimate": None, "home_hub": home,
                     "suggestions": guardrails.suggestions(st["needs"] or ["job_type"], False), "guarded": False}
    text_in, assumed = guardrails.apply_defaults(job_text, st["needs"], st["asks"])
    try:
        from .agent import chat
        out = chat(_get_agent(), sid, text_in, home=home, assumed=assumed)
    except Exception:
        return 503, {"error": "chat_unavailable"}
    if out["ended"]:
        _sessions.pop(sid, None)  # the conversation is deleted, here as well as in the agent's memory
        return 200, {**out, "home_hub": None, "suggestions": [], "guarded": False}
    st["job"], st["needs"] = out["job"], out["needs_input"]
    st["asks"] = 0 if out["estimate"] or not out["needs_input"] else st["asks"] + 1
    prefix = loc_note + (guardrails.assumed_note(assumed) if assumed else "")
    out["reply"] = prefix + out["reply"]
    return 200, {**out, "home_hub": home, "suggestions": guardrails.suggestions(out["needs_input"], bool(out["estimate"])), "guarded": False}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/v1/hubs/gpus":
            self._send(200, HUB_GPUS)
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self):
        if self.path not in ("/v1/jobs/estimate", "/v1/jobs/parse", "/v1/chat", "/v1/chat/placement", "/v1/jobs/preview"):
            return self._send(404, {"error": "not_found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= MAX_BODY:
                raise ValueError
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._send(422, {"error": "validation_failed", "detail": "body must be a JSON object under 1 MB"})
        if self.path == "/v1/chat":
            return self._send(*_chat(body))
        if self.path == "/v1/chat/placement":
            return self._send(*_placement(body))
        if self.path == "/v1/jobs/preview":
            return self._send(*_preview(body))
        if self.path == "/v1/jobs/parse":
            try:
                return self._send(200, parse(body.get("text")))
            except ParseError:
                return self._send(422, {"error": "validation_failed", "detail": "text must be 1-2000 characters"})
        if "jobs" in body:
            jobs = body["jobs"]
            if not isinstance(jobs, list) or len(jobs) > MAX_BATCH or not all(isinstance(j, dict) for j in jobs):
                return self._send(422, {"error": "validation_failed", "detail": f"jobs must be a list of at most {MAX_BATCH} objects"})
            return self._send(200, {"results": estimate_many(jobs)})
        try:
            self._send(200, estimate(body))
        except EstimateError as e:
            self._send(422, {"error": e.code, "detail": e.detail})
        except (TypeError, ValueError, AttributeError):
            self._send(422, {"error": "validation_failed", "detail": None})

    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    request_queue_size = 128  # default 5 resets connections when many callers connect at once
    daemon_threads = True


def make_server(port=8000):
    return Server(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    s = make_server(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
    print("estimator on", s.server_address)
    s.serve_forever()
