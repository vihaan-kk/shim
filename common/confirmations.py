"""Human confirmations, created by the agent loop and checked by tools.

Only the agent loop calls create(), and only after a person approves in the
UI. The model can pass a confirmation_id along but cannot make one.

Each confirmation is bound to one action and one subject (for example
action="start_print", subject=job_id) and can be used once.

In memory for now, because tools run in the same process as the agent.
Moves to SQLite in common/ when the MCP servers run as separate processes.
"""

import secrets
from dataclasses import dataclass


@dataclass
class Confirmation:
    action: str
    subject: str
    summary: str
    used: bool = False


_confirmations: dict[str, Confirmation] = {}


def create(action: str, subject: str, summary: str) -> str:
    confirmation_id = "conf_" + secrets.token_hex(4)
    _confirmations[confirmation_id] = Confirmation(action, subject, summary)
    return confirmation_id


def check(confirmation_id: str, action: str, subject: str) -> str | None:
    """Return None if the confirmation is valid, otherwise the reason it is not."""
    c = _confirmations.get(confirmation_id)
    if c is None:
        return "No confirmation with this id exists. Ask the user with request_confirmation."
    if c.action != action or c.subject != subject:
        return f"This confirmation was given for {c.action} on {c.subject}, not {action} on {subject}."
    if c.used:
        return "This confirmation was already used. Ask the user again."
    return None


def consume(confirmation_id: str, action: str, subject: str) -> str | None:
    """Like check(), but marks the confirmation as used when it is valid."""
    problem = check(confirmation_id, action, subject)
    if problem is None:
        _confirmations[confirmation_id].used = True
    return problem


def reset() -> None:
    """Forget all confirmations. Used by tests."""
    _confirmations.clear()
