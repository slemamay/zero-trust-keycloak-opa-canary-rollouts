"""Minimal LLM clients (stdlib only): Ollama (local), OpenAI-compatible API, mock."""
import json
import os
import urllib.request
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _post(url, payload, headers=None, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat_ollama(messages, model):
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    out = _post(f"{url}/api/chat", {"model": model, "messages": messages, "stream": False,
                                    "options": {"temperature": 0}})
    return out["message"]["content"]


def chat_openai(messages, model):
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    key = os.environ["LLM_API_KEY"]
    out = _post(f"{base}/chat/completions", {"model": model, "messages": messages, "temperature": 0},
                {"Authorization": f"Bearer {key}"})
    return out["choices"][0]["message"]["content"]


class Mock:
    """Replays canned drafts (offline, reproducible demo): rejected first, then accepted."""

    def __init__(self, script="draft_1_rejected,draft_2_accepted"):
        self.files = [s.strip() for s in script.split(",")]
        self.i = 0

    def __call__(self, messages, model):
        f = self.files[min(self.i, len(self.files) - 1)]
        self.i += 1
        return (FIXTURES / f"{f}.md").read_text(encoding="utf-8")


def get_client(provider, mock_script=None):
    if provider == "ollama":
        return chat_ollama
    if provider == "openai":
        return chat_openai
    if provider == "mock":
        return Mock(mock_script) if mock_script else Mock()
    raise SystemExit(f"unknown provider {provider}")
