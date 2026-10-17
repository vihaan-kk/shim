"""The agent loop.

    send(user text)
      → ask the model, giving it the conversation and every tool schema
      → run each tool it calls and add the result to the conversation
      → repeat until the model answers, or calls ask_user / request_confirmation

The loop never picks the next tool; the model does. The loop only runs what
was asked, enforces the step and retry limits, and pauses for a person.

Each public method returns a Pause saying why the loop stopped:
    "answer"        the model replied to the user
    "question"      the model called ask_user; resume with answer_question()
    "confirmation"  the model called request_confirmation; resume with resolve_confirmation()
    "stopped"       a limit was hit
"""

import json
from dataclasses import dataclass, field
from typing import Callable

from agent import builtins
from agent.prompt import SYSTEM_PROMPT
from common import confirmations
from common.result import FIXABLE, SUCCESS, ToolResult, fatal, fixable, success
from tools import registry


@dataclass
class Pause:
    kind: str  # "answer" | "question" | "confirmation" | "stopped"
    text: str
    details: dict = field(default_factory=dict)


@dataclass
class PendingCall:
    """A built-in tool call waiting for the person."""

    call_id: str
    name: str
    args: dict


def no_events(kind: str, payload: dict) -> None:
    pass


class Agent:
    def __init__(
        self,
        llm,
        max_steps: int = 20,
        max_fixable_in_a_row: int = 3,
        on_event: Callable[[str, dict], None] = no_events,
    ):
        self.llm = llm
        self.max_steps = max_steps
        self.max_fixable_in_a_row = max_fixable_in_a_row
        self.on_event = on_event  # lets the UI show the tool trace
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.pending: PendingCall | None = None
        self.fixable_streak: dict[str, int] = {}

    # ----- public API, called by the UI -----

    def send(self, text: str) -> Pause:
        if self.pending:
            raise RuntimeError("Answer the pending question or confirmation first.")
        self.messages.append({"role": "user", "content": text})
        return self._run()

    def answer_question(self, answer: str) -> Pause:
        call = self._take_pending(builtins.ASK_USER)
        self._add_tool_result(call.call_id, success("The user answered.", {"answer": answer}))
        return self._run()

    def resolve_confirmation(self, approved: bool) -> Pause:
        call = self._take_pending(builtins.REQUEST_CONFIRMATION)
        if approved:
            confirmation_id = confirmations.create(
                call.args["action"], call.args["subject"], call.args["summary"]
            )
            result = success(
                f"The user approved {call.args['action']} for {call.args['subject']}.",
                {"approved": True, "confirmation_id": confirmation_id},
            )
        else:
            result = success(
                f"The user declined {call.args['action']}. Do not do it.",
                {"approved": False},
            )
        self._add_tool_result(call.call_id, result)
        return self._run()

    # ----- the loop -----

    def _run(self) -> Pause:
        tool_schemas = registry.schemas() + builtins.SCHEMAS
        for _ in range(self.max_steps):
            reply = self.llm.chat(self.messages, tool_schemas)
            self.messages.append(clean_assistant_message(reply))

            calls = reply.get("tool_calls") or []
            if not calls:
                return Pause("answer", reply.get("content") or "")

            pause = self._run_tool_calls(calls)
            if pause:
                return pause

        return Pause(
            "stopped",
            f"Stopped after {self.max_steps} model steps without finishing. "
            "Rephrase the request or break it into smaller steps.",
        )

    def _run_tool_calls(self, calls: list[dict]) -> Pause | None:
        """Run every call in one model reply. Return a Pause if one needs the person."""
        pause = None
        for call in calls:
            call_id = call["id"]
            name = call["function"]["name"]
            args, problem = parse_arguments(call["function"].get("arguments"))
            self.on_event("tool_call", {"name": name, "args": args})

            if problem:
                self._add_tool_result(call_id, problem)
                continue

            if name in builtins.NAMES:
                if pause:
                    # One person-facing step at a time; the model can ask again later.
                    self._add_tool_result(call_id, fixable(
                        code="one_at_a_time",
                        reason="Another question or confirmation is already waiting for the user.",
                        message="Ask this again after the user has answered.",
                    ))
                    continue
                pause = self._pause_for_person(call_id, name, args)
                continue

            result = self._limit_retries(name, registry.call(name, args))
            self.on_event("tool_result", {"name": name, "result": result.to_dict()})
            self._add_tool_result(call_id, result)
        return pause

    def _pause_for_person(self, call_id: str, name: str, args: dict) -> Pause | None:
        if name == builtins.ASK_USER:
            question = args.get("question", "").strip()
            if not question:
                self._add_tool_result(call_id, fixable(
                    code="missing_argument", reason="ask_user needs a question.",
                    message="Call ask_user with a question."))
                return None
            self.pending = PendingCall(call_id, name, args)
            return Pause("question", question)

        problem = registry.check_arguments(builtins.SCHEMAS[1]["function"]["parameters"], args)
        if problem:
            self._add_tool_result(call_id, problem)
            return None
        self.pending = PendingCall(call_id, name, args)
        return Pause("confirmation", args["summary"], {"action": args["action"], "subject": args["subject"]})

    def _limit_retries(self, name: str, result: ToolResult) -> ToolResult:
        """After too many fixable results in a row from one tool, make the next one fatal."""
        if result.status == FIXABLE:
            self.fixable_streak[name] = self.fixable_streak.get(name, 0) + 1
            if self.fixable_streak[name] > self.max_fixable_in_a_row:
                self.fixable_streak[name] = 0
                return fatal(
                    code="retry_limit",
                    reason=f"{name} returned fixable {self.max_fixable_in_a_row + 1} times in a row. "
                    f"Last error: {result.error.reason}",
                    message="Stop retrying. Explain the problem to the user or ask them what to do.",
                )
        elif result.status == SUCCESS:
            self.fixable_streak[name] = 0
        return result

    # ----- helpers -----

    def _add_tool_result(self, call_id: str, result: ToolResult) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result.to_dict()),
        })

    def _take_pending(self, expected: str) -> PendingCall:
        if not self.pending or self.pending.name != expected:
            raise RuntimeError(f"No pending {expected} to resolve.")
        call, self.pending = self.pending, None
        return call


def parse_arguments(raw) -> tuple[dict, ToolResult | None]:
    """Tool arguments arrive as a JSON string. Return (args, problem)."""
    if raw in (None, ""):
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as e:
        return {}, fixable(
            code="invalid_json",
            reason=f"Arguments are not valid JSON: {e.msg}.",
            message="Call again with the arguments as a JSON object.",
        )
    if not isinstance(args, dict):
        return {}, fixable(
            code="invalid_json",
            reason="Arguments must be a JSON object.",
            message="Call again with the arguments as a JSON object.",
        )
    return args, None


def clean_assistant_message(reply: dict) -> dict:
    """Keep only the fields the chat format needs (drop e.g. reasoning text)."""
    message = {"role": "assistant", "content": reply.get("content")}
    if reply.get("tool_calls"):
        message["tool_calls"] = reply["tool_calls"]
    return message
