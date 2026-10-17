"""Shared tool result envelope (README section 8.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

SUCCESS = "success"
FIXABLE = "fixable"
FATAL = "fatal"


@dataclass
class ToolError:
    code: str
    reason: str
    valid: Optional[Any] = None  # only for fixable errors: what would be accepted


@dataclass
class ToolResult:
    status: str
    message: str
    data: dict = field(default_factory=dict)
    error: Optional[ToolError] = None

    def to_dict(self) -> dict:
        err = None
        if self.error is not None:
            err = {"code": self.error.code, "reason": self.error.reason}
            if self.error.valid is not None:
                err["valid"] = self.error.valid
        return {"status": self.status, "message": self.message, "data": self.data, "error": err}


def success(message: str, **data: Any) -> ToolResult:
    return ToolResult(SUCCESS, message, dict(data))


def fixable(code: str, reason: str, valid: Any = None, message: str = "") -> ToolResult:
    return ToolResult(FIXABLE, message or reason, {}, ToolError(code, reason, valid))


def fatal(code: str, reason: str, message: str = "") -> ToolResult:
    return ToolResult(FATAL, message or reason, {}, ToolError(code, reason))
