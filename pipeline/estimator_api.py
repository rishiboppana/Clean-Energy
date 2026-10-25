"""Estimator HTTP service (specs.md AP-estimate). Stdlib only: one thread per request, the estimator is pure so no locks.

Run: python3 -m pipeline.estimator_api [port]
POST /v1/jobs/parse      {"text": "..."} -> {"fields", "needs_input", "parser": "llm"|"form", ...}; never fails because the LLM is down
POST /v1/jobs/estimate   body = job fields           -> record, or 422 {"error", "detail"}
                         body = {"jobs": [...]}      -> {"results": [...]} (200, per-job errors inline)
POST /v1/chat            {"session_id", "text", "home_hub"?} -> {"reply", "job", "needs_input", "estimate", "home_hub"}; 503 chat_unavailable
                         without the agent environment (run with .venv-agent/bin/python to enable it)
GET  /v1/hubs/gpus       -> per-hub GPU type and count
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .location import HUB_NAMES, detect_hub
from .estimator import HUB_GPUS, EstimateError, estimate, estimate_many
from .parser import ParseError, parse

MAX_BODY = 1_000_000
MAX_BATCH = 5000


_agent = None


def _chat(body):
    """-> (status, body). The agent is built on first use so the rest of the service runs without LangGraph installed."""
    global _agent
    sid, text, home = body.get("session_id"), body.get("text"), body.get("home_hub")
    if not (isinstance(sid, str) and 0 < len(sid) <= 64 and isinstance(text, str) and 0 < len(text.strip()) <= 2000):
        return 422, {"error": "validation_failed", "detail": "session_id (1-64 chars) and text (1-2000 chars) are required"}
    if home is not None and home not in HUB_NAMES:
        return 422, {"error": "validation_failed", "detail": "unknown home_hub"}
    try:
        if _agent is None:
            from .agent import make_agent
            _agent = make_agent()
        from .agent import chat
        out = chat(_agent, sid, text)
    except Exception:
        return 503, {"error": "chat_unavailable"}
    found = detect_hub(text)
    if found and found != home:
        home = found
        out["reply"] = f"Location set to {HUB_NAMES[home]}.\n" + out["reply"]
    return 200, {**out, "home_hub": home}


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
        if self.path not in ("/v1/jobs/estimate", "/v1/jobs/parse", "/v1/chat"):
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
