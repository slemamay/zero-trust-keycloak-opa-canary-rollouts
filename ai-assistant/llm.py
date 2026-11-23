"""Minimal LLM clients (stdlib only): any OpenAI-compatible API, and an offline mock.

Configured only through environment variables (nothing is vendor-specific):
  LLM_BASE_URL  e.g. http://localhost:11434/v1 (Ollama, default), https://api.groq.com/openai/v1,
                https://openrouter.ai/api/v1, https://api.openai.com/v1 ...
  LLM_API_KEY   not needed for a local server (localhost); required for hosted providers
  LLM_MODEL     model name as the provider spells it (or use --model)
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_BASE = "http://localhost:11434/v1"   # Ollama (local, free, offline); override with LLM_BASE_URL
DEFAULT_MODEL = "qwen2.5-coder:7b"            # override with LLM_MODEL or --model
RETRY_CODES = (429, 500, 502, 503, 504)


def _post(url, payload, headers=None, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          # Some providers (Cloudflare in front of Groq...) reject the default
                                          # "Python-urllib" User-Agent with HTTP 403 / error code 1010.
                                          "User-Agent": "projet44-policy-assistant/1.0",
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat_openai(messages, model):
    """OpenAI-compatible chat call. Retries twice on temporary overload (429/5xx)."""
    base = os.getenv("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    if not key and urllib.parse.urlparse(base).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise KeyError("LLM_API_KEY")   # handled by assistant.py with a clear message
    for attempt, wait in enumerate((0, 5, 10)):
        if wait:
            print(f"   Service occupé : nouvel essai dans {wait} s ({attempt}/2)...", flush=True)
            time.sleep(wait)
        try:
            out = _post(f"{base}/chat/completions", {"model": model, "messages": messages, "temperature": 0},
                        {"Authorization": f"Bearer {key or 'none'}"})
            return out["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or attempt == 2:
                raise


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
    if provider == "openai":
        return chat_openai
    if provider == "mock":
        return Mock(mock_script) if mock_script else Mock()
    raise SystemExit(f"unknown provider {provider}")
