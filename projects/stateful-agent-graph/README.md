# Stateful agent graph: build the engine, then the agent

LangGraph and similar frameworks describe an agent as a **graph**: nodes are functions, edges decide
which node runs next, and a shared, typed **state** flows through it. After every node the framework
saves a **checkpoint**, which is what makes "pause for a human, resume tomorrow" possible.

In this project you build that machinery yourself — a state-graph engine of about 200 lines of logic,
standard library only — and then use it for a research-then-summarise agent. Finally you can compare
it with the same agent written in LangGraph (`optional/`).

```
START ─► plan ─► research ──(enough notes?)──► review ──(approved?)──► summarise ─► END
                   ▲     │ no                    │  ⏸ interrupt: a person approves,
                   └─────┘                       │     rejects, or asks for more ("solar panels")
                   ▲                             │
                   └──────── rejected with feedback (feedback becomes a new search query)
```

## What you will learn

* **Typed shared state and reducers**: a `TypedDict` schema where `Annotated[list[str], operator.add]`
  means "append" and everything else means "overwrite"; updates are type-checked.
* **Graph construction and validation**: entry point, static and conditional edges, path maps, and
  catching dead ends and unreachable nodes *before* running.
* **Checkpoints after every node** (in memory or JSON files, written atomically), a recursion limit,
  and resuming a run that crashed.
* **Interrupt and resume**: a node pauses for a person; on resume the node runs again from the top and
  `interrupt()` returns the person's answer — exactly LangGraph's semantics.
* How a framework maps onto what you built, so its documentation reads as familiar ideas.

## Setup

Python 3.11 or newer. The core and its tests need only `pytest`.

Windows (PowerShell):

```powershell
cd projects\stateful-agent-graph
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pytest
```

macOS / Linux:

```bash
cd projects/stateful-agent-graph
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pytest
```

## Running the tests

```powershell
python -m pytest                    # your code in starter/ (LangGraph tests are skipped)
python -m pytest -k Milestone4      # one milestone
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # the reference solution
```

```bash
GW_TARGET=solution python -m pytest
```

Run the finished agent: `python solution/agent_graph.py` (it pauses at the review, approves, and prints
the summary and the checkpoint history).

## Milestones

Work in `starter/agent_graph.py`.

1. **Typed state and reducers** — `channels_from_schema`, `matches_type`, `apply_update`.
2. **Graph building and routing** — `add_node`, `add_edge`, `add_conditional_edges`, `validate`,
   `_reachable`, and the run loop (`invoke`, `_run`, `_call`, `_next`) with a recursion limit. Nodes get a
   *copy* of the state, so the only way to change it is to return an update.
3. **Checkpoints** — `_save` after every node (JSON-serialisable, deep-copied), `MemoryCheckpointer`,
   `JsonFileCheckpointer` (atomic writes, safe thread ids), `get_state`, `history`, and `resume` after a
   crash in a brand-new engine instance.
4. **Interrupt and resume** — `NodeContext.interrupt`, the `interrupted` checkpoint, `resume(thread_id,
   value)`; the node re-runs from the top on resume (the tests count it).
5. **The research agent** — `parse_plan` (never trust model output), `plan_step`, `research_step`,
   `route_after_research`, `review_update`, `review_step`, `route_after_review`, `summarise_step` and
   `build_research_graph`.

## Optional: the same agent in LangGraph (version-dependent)

`optional/langgraph_research.py` wires the *same node functions* into LangGraph. It was written against
the LangGraph 1.x API as documented on docs.langchain.com (checked 2026-10-22; the latest release on
PyPI was 1.2.16) and its tests passed with langgraph 1.2.16. LangGraph evolves quickly, so treat it as
version-dependent.

```powershell
python -m pip install -r optional/requirements.txt
python -m pytest tests/test_langgraph_optional.py
$env:PYTHONPATH="solution"; python optional/langgraph_research.py
```

```bash
python -m pip install -r optional/requirements.txt
python -m pytest tests/test_langgraph_optional.py
PYTHONPATH=solution python optional/langgraph_research.py
```

| your engine (`agent_graph.py`) | LangGraph 1.x |
|---|---|
| `StateGraph(ResearchState, defaults=...)` | `StateGraph(ResearchState)`; defaults go in the input |
| `Annotated[list[str], operator.add]` | the same — reducers come from `Annotated` metadata |
| `add_node`, `add_edge(START, "plan")`, `add_conditional_edges(src, router, path_map)` | the same names (`from langgraph.graph import StateGraph, START, END`) |
| `compile(checkpointer=JsonFileCheckpointer(folder))` | `compile(checkpointer=InMemorySaver())` (`langgraph.checkpoint.memory`) or a database saver |
| `invoke(values, "thread-1")` | `invoke(values, {"configurable": {"thread_id": "thread-1"}})` |
| `ctx.interrupt(payload)` | `interrupt(payload)` from `langgraph.types` (context is implicit) |
| `RunResult.status == "interrupted"`, `.interrupt` | `result["__interrupt__"][0].value` |
| `resume("thread-1", value)` | `invoke(Command(resume=value), config)` |
| `get_state(t).next_node`, `history(t)` | `get_state(config).next` (`()` when done), `get_state_history(config)` |
| `recursion_limit=25` | `recursion_limit` in the config (default 1000 since 1.0.6) |

What LangGraph adds on top: streaming, parallel branches (a "super-step" runs several nodes at once),
subgraphs, durable database checkpointers, time travel (`update_state`, replay from any checkpoint) and
tooling. What it does not change: the ideas you just implemented.

## Optional: a free local model

`OllamaModel` (in `agent_graph.py`) calls a local Ollama server with `urllib`, localhost only. Install
Ollama, `ollama pull llama3.2` (about 2 GB; 8 GB RAM is comfortable), then pass
`build_research_graph(OllamaModel())`. A real model's plan may not be valid JSON — `parse_plan` falls back
to the question itself. The tests never need it.

## Design notes

* **Nodes return updates; reducers merge them.** Nodes never mutate shared state, so every change goes
  through one function that validates types and keys — the same reason LangGraph has reducers.
* **Checkpoints are JSON.** If the state cannot be serialised, the run fails immediately rather than
  when you first try to resume it.
* **Interrupts replay.** Resuming re-runs the interrupted node, so code before `interrupt()` must be safe
  to run twice (no emails sent before asking for approval!).
* **Routers return keys, path maps name nodes.** That keeps routing logic testable on plain dicts and
  lets `validate()` check every possible target before the first run.

## Security notes

* Thread ids become file names in `JsonFileCheckpointer`; they are restricted to `[A-Za-z0-9_.-]` so a
  thread id like `../../etc/x` cannot escape the folder.
* Model output (the plan) is parsed defensively and capped; a model cannot inject extra state keys or
  unbounded queries. Notes are passed to the summariser as data, with an instruction saying so.
* Checkpoints can contain user questions and retrieved text; store them like any other user data.
