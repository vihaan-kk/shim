"""Tool registry: one place that knows every tool the model can call.

A tool is a plain function decorated with @tool:

    @tool(
        name="get_job_progress",
        description="Use to ... Do not use to ...; use X instead.",
        parameters={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    )
    def get_job_progress(job_id: str) -> ToolResult: ...

The registry checks arguments against the schema before a tool runs, turns
exceptions into fatal results, and builds the tool list sent to the model.
"""

import importlib
import os
from dataclasses import dataclass
from typing import Callable

from common.result import ToolResult, fatal, fixable

# Modules that hold real tools. Missing ones are skipped, so the agent runs
# while teammates are still writing them.
REAL_MODULES = [
    "tools.cad.tools",
    "tools.printer.tools",
]
FAKE_MODULES = [
    "tools.fakes.cad_fakes",
    "tools.fakes.printer_fakes",
]

JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    function: Callable[..., ToolResult]

    def schema(self) -> dict:
        """The OpenAI-style tool definition vLLM expects."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_tools: dict[str, Tool] = {}


def tool(name: str, description: str, parameters: dict):
    """Decorator that registers a function as a tool."""

    def register(function):
        if name in _tools:
            raise ValueError(f"Tool {name!r} is registered twice")
        _tools[name] = Tool(name, description, parameters, function)
        return function

    return register


def load_tools(fake: bool | None = None) -> None:
    """Import the tool modules so their @tool decorators run."""
    if fake is None:
        fake = os.environ.get("FAKE_TOOLS", "0") == "1"
    for module in FAKE_MODULES if fake else REAL_MODULES:
        try:
            importlib.import_module(module)
        except ModuleNotFoundError as e:
            if e.name != module:
                raise  # a real import error inside the module
            print(f"[registry] skipping {module}: not written yet")


def names() -> list[str]:
    return sorted(_tools)


def schemas() -> list[dict]:
    return [t.schema() for t in _tools.values()]


def call(name: str, args: dict) -> ToolResult:
    """Validate the arguments, then run the tool."""
    if name not in _tools:
        return fixable(
            code="unknown_tool",
            reason=f"There is no tool named {name!r}.",
            message="Unknown tool. Choose one from the list.",
            valid_range=names(),
        )
    t = _tools[name]

    problem = check_arguments(t.parameters, args)
    if problem:
        return problem

    try:
        result = t.function(**args)
    except Exception as e:
        return fatal(
            code="tool_crashed",
            reason=f"{type(e).__name__}: {e}",
            message=f"{name} failed unexpectedly. Tell the user; do not retry.",
        )
    if not isinstance(result, ToolResult):
        return fatal(
            code="bad_tool_result",
            reason=f"{name} returned {type(result).__name__}, not ToolResult.",
            message=f"{name} returned an invalid result. Tell the user.",
        )
    return result


def check_arguments(schema: dict, args: dict) -> ToolResult | None:
    """Return a fixable result for the first problem found, or None if args are valid.

    Covers the parts of JSON schema our tools use: required, unknown fields,
    type, enum, minimum and maximum.
    """
    properties = schema.get("properties", {})

    for key in schema.get("required", []):
        if key not in args:
            return fixable(
                code="missing_argument",
                reason=f"Missing required argument {key!r}.",
                message=f"Call again with {key!r}.",
                hint=properties.get(key, {}).get("description"),
            )

    for key, value in args.items():
        if key not in properties:
            return fixable(
                code="unknown_argument",
                reason=f"{key!r} is not an argument of this tool.",
                message="Remove the unknown argument and call again.",
                valid_range=sorted(properties),
            )
        spec = properties[key]

        expected = JSON_TYPES.get(spec.get("type"))
        # bool is a subclass of int in Python, so reject it for numbers explicitly.
        wrong_bool = isinstance(value, bool) and spec.get("type") in ("integer", "number")
        if expected and (not isinstance(value, expected) or wrong_bool):
            return fixable(
                code="wrong_type",
                reason=f"{key!r} must be of type {spec['type']}, got {type(value).__name__}.",
                message=f"Call again with {key!r} as a {spec['type']}.",
            )

        if "enum" in spec and value not in spec["enum"]:
            return fixable(
                code="invalid_choice",
                reason=f"{key!r} = {value!r} is not an allowed value.",
                message=f"Call again with one of the allowed values for {key!r}.",
                valid_range=spec["enum"],
            )

        low, high = spec.get("minimum"), spec.get("maximum")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if (low is not None and value < low) or (high is not None and value > high):
                return fixable(
                    code="out_of_range",
                    reason=f"{key!r} = {value} is outside {low}–{high}.",
                    message=f"Call again with {key!r} between {low} and {high}, or ask the user.",
                    valid_range={"min": low, "max": high},
                )
    return None


def reset() -> None:
    """Forget all tools. Used by tests."""
    _tools.clear()
