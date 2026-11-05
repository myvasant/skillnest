# Tool-using assistant: the agent loop from scratch

Build a small assistant that answers questions by calling tools — a calculator, a unit converter and a
file reader locked inside a sandbox folder — using nothing but the Python standard library. No agent
framework: you write the loop, the tool registry, the argument validation and the error handling
yourself, so that when you later use LangGraph, an SDK or MCP you know exactly what they do for you.

```
question ──► Agent.run ──► model.complete(messages, tool specs) ──► reply text
                 ▲                                                    │
                 │                                       parse_action │
                 │                    ┌───────────────────────────────┴──────────┐
                 │               ToolCall                         FinalAnswer / invalid
                 │                    │                                    │
                 │      ToolRegistry.execute (validate → run)        stop / report error
                 │                    │
                 └──── tool message ◄─┘   (results AND errors are fed back; max_steps ends the loop)
```

The model is replaceable. Tests use `ScriptedModel`, which replays a fixed list of replies, so every run
is reproducible and free. `OllamaModel` is an optional adapter for a local model; nothing requires it.

## What you will learn

* The agent loop: call the model, act on its reply, feed back the observation, stop on an answer or a budget.
* Tool design: small tools with precise descriptions and JSON-schema-like parameter specs.
* Treating model output as untrusted input: validate arguments, never `eval`, block path traversal.
* Turning failures into observations the model can recover from, instead of crashes.
* Why a transcript matters: it is how you debug and later evaluate an agent.

## Setup

Python 3.11 or newer. The core and the tests need only `pytest`.

Windows (PowerShell):

```powershell
cd projects\tool-using-assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pytest
```

macOS / Linux:

```bash
cd projects/tool-using-assistant
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pytest
```

## Running the tests

From the kit folder:

```powershell
python -m pytest                  # your code in starter/
python -m pytest -k Milestone1    # one milestone
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # the reference solution
```

```bash
python -m pytest -k Milestone2
GW_TARGET=solution python -m pytest   # the reference solution
```

One symlink test is skipped on Windows unless Developer Mode allows creating symlinks.

Try the finished program: `python solution/tool_assistant.py --demo` prints a scripted run's transcript.

## Milestones

Work in `starter/tool_assistant.py`. Each milestone has a test class (`TestMilestone1Registry`, …).

1. **Tool registry and argument validation** — `Tool.spec`, `check_parameter_schema`,
   `validate_arguments`, `ToolRegistry.register/names/get/specs/execute`. Execution never raises:
   unknown tools, invalid arguments, `ToolError`s and crashes all become a `ToolOutcome` with an
   `error_kind`.
2. **Calculator and unit converter** — `safe_calculate` walks an `ast` tree and allows only numbers
   and arithmetic operators (no `eval`), with limits on length, exponents and magnitude;
   `convert_units` handles length, mass and temperature; `make_unit_converter_tool` defines the tool.
3. **Sandboxed file reader** — `resolve_in_sandbox` blocks absolute paths, drive letters, UNC shares,
   `..` and symlinks that escape; `read_sandboxed_file` rejects directories and binary files and
   truncates large files; `make_file_reader_tool`, `default_registry`.
4. **Parsing replies and the basic loop** — `ScriptedModel`, `parse_action` (tool call vs final
   answer, strict shape checks), and `Agent.run` for the happy path with a transcript.
5. **Errors and budgets** — tool errors, unknown tools, invalid arguments and invalid output are fed
   back to the model as `ERROR:` messages; the `max_steps` budget always ends the run; long
   observations are truncated.

## The reply protocol

The system prompt (`build_system_prompt`) asks the model for exactly one JSON object:

```json
{"thought": "I need the notes first.", "tool": "read_file", "arguments": {"path": "notes/todo.txt"}}
{"thought": "I have everything.", "final": "You have two tasks: buy milk and call Sam."}
```

Real model APIs offer native tool calling (structured `tool_calls` fields). The JSON protocol here is
the same idea made visible: the model *proposes* a call, your code decides whether and how to run it.

## Optional: a free local model with Ollama

Nothing in the tests needs this.

1. Install Ollama from https://ollama.com and run `ollama pull llama3.2` (about 2 GB download;
   8 GB of RAM is comfortable; a GPU helps but is not required — expect a few seconds per step on a CPU).
2. Make sure the server is running (`ollama serve`, or the desktop app).
3. `python solution/tool_assistant.py --ollama llama3.2 --sandbox ./my-notes "How many km is 26 miles?"`

`OllamaModel` uses only `urllib`, sends `"format": "json"` so the model replies with JSON, and refuses
any URL that is not localhost. Small local models make mistakes — which is exactly when the validation
and error feedback you built earn their keep. Watch the transcript.

## Design notes

* **The registry is the only door to tools.** Validation happens in one place, before any tool runs.
* **Errors are observations.** A model can fix `missing required argument 'path'`; it cannot fix a
  stack trace that crashed your program. Messages are written for the model and never include host
  paths or tracebacks.
* **Budgets are not optional.** A model that repeats the same call forever is a real failure mode;
  `max_steps` turns it into a clean `max_steps` status.
* **Transcripts are data.** Every event has a step number and a kind, which is what an evaluation
  harness (see the `agent-evaluation-recovery` project) scores.

## Security notes

* The calculator parses with `ast` and evaluates only whitelisted nodes; `eval` would execute arbitrary code.
* The file reader resolves paths and checks containment after following symlinks; it never accepts
  absolute paths or `..`, and caps how much it reads.
* Tool output can contain text written by someone else (a file could say "ignore your instructions").
  The system prompt says tool results are data, but that is not a guarantee — keep tools read-only and
  least-privilege so a manipulated model cannot do damage.
* The Ollama adapter only talks to localhost, so file contents never leave your machine.
