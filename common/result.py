"""The result shape every tool returns.

Every tool, real or fake, returns a ToolResult built with one of three
factory functions:

    success(message, data)          the call worked
    fixable(code, reason, message)  the arguments were wrong; correct and retry
    fatal(code, reason, message)    retrying will not help; tell the user

to_dict() gives the JSON the model sees:

    {
      "status": "success" | "fixable" | "fatal",
      "data": {...},
      "message": "short summary for the model",
      "error": {"code": ..., "reason": ..., "valid_range" | "hint": ...} or None,
      "retryable": bool
    }
"""

from dataclasses import dataclass, field
from typing import Any

SUCCESS = "success"
FIXABLE = "fixable"
FATAL = "fatal"


@dataclass(frozen=True)
class ToolError:
    code: str
    reason: str
    valid_range: Any = None
    hint: str | None = None

    def to_dict(self) -> dict:
        error = {"code": self.code, "reason": self.reason}
        if self.valid_range is not None:
            error["valid_range"] = self.valid_range
        if self.hint is not None:
            error["hint"] = self.hint
        return error


@dataclass(frozen=True)
class ToolResult:
    status: str
    message: str
    data: dict = field(default_factory=dict)
    error: ToolError | None = None
    retryable: bool = False

    @property
    def ok(self) -> bool:
        return self.status == SUCCESS

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "data": self.data,
            "message": self.message,
            "error": self.error.to_dict() if self.error else None,
            "retryable": self.retryable,
        }


def success(message: str, data: dict | None = None) -> ToolResult:
    return ToolResult(status=SUCCESS, message=message, data=data or {})


def fixable(
    code: str,
    reason: str,
    message: str,
    valid_range: Any = None,
    hint: str | None = None,
    data: dict | None = None,
) -> ToolResult:
    return ToolResult(
        status=FIXABLE,
        message=message,
        data=data or {},
        error=ToolError(code=code, reason=reason, valid_range=valid_range, hint=hint),
        retryable=True,
    )


def fatal(
    code: str,
    reason: str,
    message: str,
    hint: str | None = None,
    data: dict | None = None,
) -> ToolResult:
    return ToolResult(
        status=FATAL,
        message=message,
        data=data or {},
        error=ToolError(code=code, reason=reason, hint=hint),
        retryable=False,
    )
