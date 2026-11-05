"""OPTIONAL: the same research agent built with LangGraph instead of the hand-written engine.

VERSION-DEPENDENT. Written against the LangGraph 1.x Python API as documented on docs.langchain.com
(checked 2026-10-22; the latest release on PyPI was langgraph 1.2.16, requiring Python >= 3.10):
``StateGraph``/``START``/``END`` from ``langgraph.graph``, ``InMemorySaver`` from
``langgraph.checkpoint.memory``, and ``interrupt``/``Command`` from ``langgraph.types``. LangGraph is
not installed in this repository's default environment, so this file is not executed by the default
test run; ``tests/test_langgraph_optional.py`` runs it when LangGraph is available.

Install and run (from the kit folder)::

    python -m pip install -r optional/requirements.txt
    python -m pytest tests/test_langgraph_optional.py
    PYTHONPATH=solution python optional/langgraph_research.py        # macOS / Linux
    $env:PYTHONPATH="solution"; python optional/langgraph_research.py  # Windows PowerShell

The node *logic* is imported from ``agent_graph`` — only the engine changes:

=====================================  =============================================================
your engine (agent_graph.py)           LangGraph
=====================================  =============================================================
``StateGraph(ResearchState, defaults)`` ``StateGraph(ResearchState)``; defaults go in the input
``Annotated[list[str], operator.add]``  the same: reducers come from ``Annotated`` metadata
``add_node`` / ``add_edge(START, x)``   the same method names
``add_conditional_edges(src, r, map)``  the same, path map included
``compile(checkpointer=...)``           ``compile(checkpointer=InMemorySaver())``
``invoke(values, thread_id)``           ``invoke(values, {"configurable": {"thread_id": ...}})``
``ctx.interrupt(payload)``              ``interrupt(payload)`` (a function; context is implicit)
``RunResult.interrupt``                 ``result["__interrupt__"][0].value``
``resume(thread_id, value)``            ``invoke(Command(resume=value), config)``
``get_state(thread_id).next_node``      ``get_state(config).next`` (``()`` when finished)
=====================================  =============================================================
"""

import operator
from collections.abc import Mapping
from typing import Annotated, Any, TypedDict

from agent_graph import (
    CORPUS,
    RESEARCH_DEFAULTS,
    Model,
    RuleBasedModel,
    plan_step,
    research_step,
    review_update,
    route_after_research,
    route_after_review,
    summarise_step,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ResearchState(TypedDict):
    """Identical to ``agent_graph.ResearchState``: LangGraph reads the same ``Annotated`` reducers."""

    question: str
    queries: Annotated[list[str], operator.add]
    notes: Annotated[list[str], operator.add]
    sources: Annotated[list[str], operator.add]
    searches: int
    approved: bool
    feedback: str
    summary: str


def initial_state(question: str) -> dict[str, Any]:
    """LangGraph has no ``defaults`` argument, so the input carries every key."""
    return {
        key: (list(value) if isinstance(value, list) else value) for key, value in RESEARCH_DEFAULTS.items()
    } | {"question": question}


def build_langgraph_research(
    model: Model | None = None,
    corpus: Mapping[str, str] = CORPUS,
    *,
    require_review: bool = True,
    max_searches: int = 3,
    min_notes: int = 3,
    checkpointer: Any = None,
) -> Any:
    """The research agent as a compiled LangGraph graph (with an in-memory checkpointer by default)."""
    llm = model or RuleBasedModel()

    def plan(state: ResearchState) -> dict[str, Any]:
        return plan_step(state, llm)

    def research(state: ResearchState) -> dict[str, Any]:
        return research_step(state, corpus)

    def review(state: ResearchState) -> dict[str, Any]:
        if not require_review:
            return {"approved": True}
        # Like ctx.interrupt(): pauses the first time; on resume the node re-runs and this returns the value.
        decision = interrupt(
            {"question": state["question"], "notes": state["notes"], "sources": state["sources"]}
        )
        return review_update(decision)

    def summarise(state: ResearchState) -> dict[str, Any]:
        return summarise_step(state, llm)

    def after_research(state: ResearchState) -> str:
        return route_after_research(state, max_searches=max_searches, min_notes=min_notes)

    builder = StateGraph(ResearchState)
    builder.add_node("plan", plan)
    builder.add_node("research", research)
    builder.add_node("review", review)
    builder.add_node("summarise", summarise)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "research")
    builder.add_conditional_edges("research", after_research, {"research": "research", "review": "review"})
    builder.add_conditional_edges(
        "review", route_after_review, {"summarise": "summarise", "research": "research", "end": END}
    )
    builder.add_edge("summarise", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def main() -> None:
    """Run once, approve at the interrupt, print the summary."""
    graph = build_langgraph_research()
    config = {"configurable": {"thread_id": "demo"}}
    first = graph.invoke(initial_state("How do heat pumps work and how much can insulation save?"), config)
    payload = first["__interrupt__"][0].value
    print(f"paused for review with {len(payload['notes'])} notes")
    final = graph.invoke(Command(resume={"approved": True}), config)
    print(final["summary"])


if __name__ == "__main__":
    main()
