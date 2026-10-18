"""Clients for the language model.

VllmClient talks to Nemotron 3.5 Lightning served by vLLM. vLLM speaks the
OpenAI chat-completions format, so this is a plain HTTP POST; no OpenAI
models or SDK are involved.

ScriptedLLM replays fixed replies, for testing the loop without a GPU.
Both have the same chat() method, so the agent works with either.
"""

import os

import requests


class VllmClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 120,
    ):
        self.base_url = (base_url or os.environ["VLLM_BASE_URL"]).rstrip("/")
        self.model = model or os.environ["MODEL_NAME"]
        # Set when the shared vLLM server was started with --api-key.
        self.api_key = api_key or os.environ.get("VLLM_API_KEY", "")
        self.timeout_s = timeout_s

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Send the conversation and tool list; return the assistant message."""
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=auth_headers(self.api_key),
            json={
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.2,
                # Nemotron with reasoning on can return an empty message beside a
                # tool call without this (per the vLLM Nemotron notes; not yet
                # verified on our instance).
                "chat_template_kwargs": {"force_nonempty_content": True},
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class ScriptedLLM:
    """Returns the given assistant messages in order. For tests and demos without vLLM."""

    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []  # the messages each call received

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.seen.append([dict(m) for m in messages])
        if not self.replies:
            return {"role": "assistant", "content": "(script finished)"}
        return self.replies.pop(0)


def tool_call(call_id: str, name: str, arguments: str) -> dict:
    """Build an assistant message that calls one tool. Handy for scripts."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
        ],
    }
