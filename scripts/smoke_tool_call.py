"""Check that the served model returns a parsed tool call. Run on your laptop
with the Brev tunnel up.

Usage: set -a && . ./.env && set +a && PYTHONPATH=. uv run python scripts/smoke_tool_call.py

Sends one request twice: with and without chat_template_kwargs.force_nonempty_content,
so you can see whether agent/llm.py needs that flag.
"""
import json
import os
import sys

import requests

BASE = os.environ["VLLM_BASE_URL"].rstrip("/")
MODEL = os.environ["MODEL_NAME"]
TOOL = {
    "type": "function",
    "function": {
        "name": "get_printer_status",
        "description": "Read the virtual printer's connection and state.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def ask(extra: dict) -> dict:
    r = requests.post(
        f"{BASE}/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "Is the printer ready?"}],
            "tools": [TOOL],
            "tool_choice": "auto",
            "temperature": 0.2,
            **extra,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


ok = True
for label, extra in [("default", {}), ("force_nonempty_content", {"chat_template_kwargs": {"force_nonempty_content": True}})]:
    msg = ask(extra)
    calls = msg.get("tool_calls") or []
    names = [c["function"]["name"] for c in calls]
    print(f"{label:<24} tool_calls={names} content={json.dumps(msg.get('content'))[:60]}")
    ok &= names == ["get_printer_status"]
sys.exit(0 if ok else 1)
