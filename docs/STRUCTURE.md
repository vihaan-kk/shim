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
├── templates/          parametric prosthetic part templates
├── servers/            MCP servers that expose tools/ to the agent
├── eval/               evaluation of the agent
│   ├── cases/          test prompts with expected tool calls and questions
│   └── results/        output of evaluation runs
├── tests/              deterministic tests that need no model
├── data/               open data, with provenance in data/README.md
│   └── openlimbtt/     pinned OpenLimbTT files
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
| `tools/` | One plain function per tool. Each one checks its arguments, does the work, and returns the shared result type. A registry maps tool names to functions, descriptions and schemas. | MCP code, prompts, or UI. |
| `tools/cad/` | `list_templates`, `describe_template`, `create_from_template`, `import_part`, `set_parameter`, `add_hole`, `inspect_part`, `validate_geometry`, `export_part`. | Printer calls. |
| `tools/printer/` | `slice`, `get_printer_status`, `start_print`, `get_job_progress`, `cancel_print`, plus a small OctoPrint REST client. | Fault injection. |
| `tools/fakes/` | Stand-ins for every tool, so the agent loop can be built and tested before the real tools work. Selected with an environment variable. | Real geometry or printer calls. |
| `templates/` | One file per part type (for example foot, socket, adapter). Each lists its parameters with units and ranges and builds the part from them. | Tool code. Adding a part type means adding one file here. |
| `servers/` | Thin MCP wrappers: the CAD server exposes `tools/cad/`, the printer server exposes `tools/printer/`. | Logic. If MCP causes problems, the agent can call `tools/` directly. |
| `eval/` | Test prompts, the evaluation runner, and recorded results for the README metrics. | Unit tests. |
| `tests/` | Unit tests for tools, templates, the result type and the confirmation store. They run without a model. | Tests that call the model. |
| `data/` | Open data the project uses, with source, license and date in `data/README.md`. | Generated files. |
| `scripts/` | The feasibility spike, the demo fault injector, and setup files. | Anything the model can call. Fault injection must never become a tool. |
| `docs/` | This file and the architecture diagram used in the README. | Code. |
| `workspace/` | Files the system writes at runtime: imported parts, each revision, exported STL and G-code. | Anything committed to git, apart from `.gitkeep`. |

## Rules

**Imports flow one way.** `common/` ← `tools/` ← `servers/` and `agent/`. A tool never imports from `agent/` or `servers/`. In Java terms, the service layer never depends on the controller.

**Every edit writes a new revision** under `workspace/`. The original file is never changed.

**Demo controls stay out of `tools/`.** Anything that injects faults or bypasses safety checks lives in `scripts/`, so the model cannot reach it.
