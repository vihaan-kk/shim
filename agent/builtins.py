"""Built-in tools that need the host UI: ask_user, request_confirmation, move_to_stage.

They are not in tools/ because they run no code of their own. ask_user and
request_confirmation pause the loop and the UI asks the person; the answer
goes back to the model as that tool call's result. move_to_stage is handled
by the host (the web workbench performs the stage change and navigates);
the loop just forwards it to the host's stage handler.
"""

ASK_USER = "ask_user"
REQUEST_CONFIRMATION = "request_confirmation"
MOVE_TO_STAGE = "move_to_stage"

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
                "properties": {
                    "question": {"type": "string", "description": "One clear question."},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 6,
                        "description": (
                            "Optional: 2-6 short, distinct choices when the question has a "
                            "small set of likely answers (for example what to do after a "
                            "failed check). The UI shows them as buttons; the user can "
                            "still type a different answer. Omit for open questions."
                        ),
                    },
                },
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
    {
        "type": "function",
        "function": {
            "name": MOVE_TO_STAGE,
            "description": (
                "Take the user to a workbench stage when they say they want to move on "
                "(for example 'I want to work on the socket now' or 'let's print it'). "
                "The host performs whatever the move requires: going to the socket stage "
                "builds the socket from the current limb first if there is none, and "
                "going to the printer stage confirms the socket first if it has passed "
                "its checks. The result tells you what happened; report it briefly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string", "enum": ["limb", "socket", "printer"]},
                },
                "required": ["stage"],
            },
        },
    },
]

NAMES = {ASK_USER, REQUEST_CONFIRMATION, MOVE_TO_STAGE}
