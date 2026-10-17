"""Built-in tools that need a person: ask_user and request_confirmation.

They are not in tools/ because they run no code. When the model calls one,
the agent loop pauses and the UI asks the person. The answer goes back to
the model as that tool call's result.
"""

ASK_USER = "ask_user"
REQUEST_CONFIRMATION = "request_confirmation"

CONFIRMABLE_ACTIONS = ["start_print"]

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": ASK_USER,
            "description": (
                "Ask the user a question when information is missing or ambiguous: "
                "units, sizes, which part, or whether to retry after a failure. Never "
                "guess a value instead. To get approval for a print, use "
                "request_confirmation instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "One clear question."}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": REQUEST_CONFIRMATION,
            "description": (
                "Ask the user to approve an action that needs a person's sign-off. "
                "Required before start_print. Returns a one-time confirmation_id if they "
                "approve. Summarize what will happen, including estimated time and filament."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": CONFIRMABLE_ACTIONS},
                    "subject": {"type": "string", "description": "The job_id to print."},
                    "summary": {"type": "string", "description": "What the user is approving."},
                },
                "required": ["action", "subject", "summary"],
            },
        },
    },
]

NAMES = {ASK_USER, REQUEST_CONFIRMATION}
