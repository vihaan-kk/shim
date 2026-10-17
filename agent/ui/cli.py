"""Terminal chat for the agent.

    uv run python -m agent.ui.cli

Reads .env for VLLM_BASE_URL, MODEL_NAME and FAKE_TOOLS. Prints every tool
call and result so you can follow what the model decided.
"""

import json
import os
from pathlib import Path

from agent.llm import VllmClient
from agent.loop import Agent, Pause
from tools import registry


def load_env(path: Path = Path(".env")) -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments. Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def show_event(kind: str, payload: dict) -> None:
    if kind == "tool_call":
        print(f"  → {payload['name']}({json.dumps(payload['args'])})")
    elif kind == "tool_result":
        r = payload["result"]
        line = f"  ← {r['status']}: {r['message']}"
        if r["error"]:
            line += f"  [{r['error']['code']}]"
        print(line)


def handle(agent: Agent, pause: Pause) -> None:
    """Keep resuming the agent until it gives an answer or stops."""
    while True:
        if pause.kind == "question":
            answer = input(f"\nagent asks: {pause.text}\nyou> ")
            pause = agent.answer_question(answer)
        elif pause.kind == "confirmation":
            print(f"\nCONFIRM {pause.details['action']} {pause.details['subject']}:\n  {pause.text}")
            approved = input("approve? [y/N] ").strip().lower() == "y"
            pause = agent.resolve_confirmation(approved)
        else:
            print(f"\nagent: {pause.text}\n")
            return


def main() -> None:
    load_env()
    registry.load_tools()
    print(f"Tools: {', '.join(registry.names())}")
    agent = Agent(VllmClient(), on_event=show_event)
    print("Type a request. Ctrl-D to quit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            return
        if text:
            handle(agent, agent.send(text))


if __name__ == "__main__":
    main()
