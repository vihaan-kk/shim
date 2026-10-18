# Folder structure

What each folder in the repository is for, and the rules for where code goes.

```
shim/
├── agent/              agent loop, LLM client, system prompt, built-in tools
│   └── ui/             chat interface (terminal first, web page later)
├── common/             shared result type, error codes, storage, config
├── tools/              the tool calls, as plain Python functions
│   ├── cad/            template, edit, inspect, validate and export tools
│   ├── printer/        slicer and OctoPrint tools
│   └── fakes/          stub tools with the same signatures and scripted results
├── tests/              deterministic tests that need no model
├── data/               standard limb and socket data
│   ├── profiles/       standard limb and socket profiles
│   └── reference/      standardized limb and socket files and reports
├── scripts/            one-off and demo scripts
│   └── octoprint/      OctoPrint Virtual Printer configuration
├── docs/               project documentation and the architecture diagram
└── workspace/          generated parts, revisions and G-code (not committed)
```

## Folders

| Folder | Holds | Does not hold |
|---|---|---|
| `agent/` | The loop that sends messages and tool schemas to the model, runs the requested tool, and returns the result. Also `ask_user` and `request_confirmation`, because they need a person to answer. | Tool logic. |
| `agent/ui/` | The chat interface the user types into, including the confirmation buttons. | Anything the model calls directly. |
| `common/` | The shared tool result type (`success` / `fixable` / `fatal`), error codes, the SQLite store for revisions, validations, confirmations and jobs, and config loaded from `.env`. | Imports from any other project folder. |
| `tools/` | One plain function per tool. Each one checks its arguments, does the work, and returns the shared result type. A registry maps tool names to functions, descriptions and schemas. | Prompts, or UI. |
| `tools/cad/` | `list_templates`, `describe_template`, `create_from_template`, `import_part`, `set_parameter`, `add_hole`, `inspect_part`, `validate_geometry`, `export_part`. | Printer calls. |
| `tools/printer/` | `slice`, `get_printer_status`, `start_print`, `get_job_progress`, `cancel_print`, plus a small OctoPrint REST client. | Fault injection. |
| `tools/fakes/` | Stand-ins for every tool, so the agent loop can be built and tested before the real tools work. Selected with an environment variable. | Real geometry or printer calls. |
| `tests/` | Unit tests for tools, templates, the result type and the confirmation store. They run without a model. | Tests that call the model. |
| `data/` | The standard limb and socket the project uses: profiles in `data/profiles/`, standardized files and reports in `data/reference/`. | Generated files. |
| `scripts/` | The feasibility spike, the demo fault injector, and setup files. | Anything the model can call. Fault injection must never become a tool. |
| `docs/` | This file and the architecture diagram used in the README. | Code. |
| `workspace/` | Files the system writes at runtime: imported parts, each revision, exported STL and G-code. | Anything committed to git, apart from `.gitkeep`. |

## Rules

**Imports flow one way.** `common/` ← `tools/` ← `agent/`. A tool never imports from `agent/`. In Java terms, the service layer never depends on the controller.

**Every edit writes a new revision** under `workspace/`. The original file is never changed.

**Demo controls stay out of `tools/`.** Anything that injects faults or bypasses safety checks lives in `scripts/`, so the model cannot reach it.
