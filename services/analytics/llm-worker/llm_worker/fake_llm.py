"""A tiny OpenAI-compatible chat server: LOTUS -> LiteLLM -> HTTP -> here. No model, no network.

Used by the tests and by `python -m llm_worker fake-llm` (compose profile `stub`), so coworkers can run the whole
worker without Ollama or cluster access. `answer(messages)` decides the reply; `mode` simulates failures:
'ok' | 'garbage' (unparseable answers) | 'error' (HTTP 500).
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BENIGN_HINTS = ("flu shot", "vaccin", "wine", "beer", "zermatt", "altitude", "interval session", "marathon")
_IDS = re.compile(r"\b(?:n:[a-z_0-9]+|c:\d+)\b")


def default_answer(messages: list[dict]) -> str:
    content = str(messages[-1].get("content", ""))
    if "Claim:" in content:  # LOTUS sem_filter prompt
        hint = next((h for h in BENIGN_HINTS if h in _section(content, "Context").lower()), None)
        if hint:
            return f"Reasoning:\nThe context documents '{hint}' shortly before the night.\nAnswer: True"
        return "Reasoning:\nNo documented benign cause explains the values.\nAnswer: False"
    ids = _IDS.findall(content)
    cited = [i for i in ids if i.startswith("n:")][:2] + [i for i in ids if i.startswith("c:")][:1]
    return json.dumps(
        {
            "explanation": "[fake model] Values differ from the patient's baseline; see cited evidence.",
            "cited_ids": cited,
        }
    )


def _section(content: str, name: str) -> str:
    start = content.find(f"[{name}]: «")
    if start == -1:
        return content
    end = content.find("»", start)
    return content[start : end if end != -1 else None]


class FakeLLM:
    def __init__(self, answer=default_answer, host: str = "127.0.0.1", port: int = 0) -> None:
        self.answer, self.mode, self.requests = answer, "ok", []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(200, {"object": "list", "data": [{"id": "fake-small", "object": "model"}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                if fake.mode == "error":
                    return self._send(500, {"error": {"message": "upstream down", "type": "server_error"}})
                content = "maybe?" if fake.mode == "garbage" else fake.answer(body["messages"])
                self._send(
                    200,
                    {
                        "id": "fake",
                        "object": "chat.completion",
                        "created": 0,
                        "model": body["model"],
                        "choices": [
                            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    },
                )

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.base_url = f"http://{host}:{self.server.server_address[1]}/v1"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
