"""OPTIONAL tests for the LangGraph version in ``optional/langgraph_research.py``.

Skipped unless LangGraph is installed (``python -m pip install -r optional/requirements.txt``).
They check that the framework version of the graph behaves exactly like your engine — same queries,
notes, sources and summary — including pausing at the review and resuming with ``Command(resume=...)``.
Version-dependent: written for the LangGraph 1.x API.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from agent_graph import RuleBasedModel, build_research_graph

langgraph = pytest.importorskip("langgraph")

OPTIONAL_FILE = Path(__file__).resolve().parent.parent / "optional" / "langgraph_research.py"
QUESTION = "How do heat pumps work and how much can insulation save?"


@pytest.fixture(scope="module")
def lg() -> ModuleType:
    """Load the optional module from its file (it is not on sys.path)."""
    spec = importlib.util.spec_from_file_location("langgraph_research", OPTIONAL_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_same_result_as_your_engine(lg: ModuleType) -> None:
    ours = build_research_graph(RuleBasedModel(), require_review=False).invoke({"question": QUESTION}).state
    theirs = lg.build_langgraph_research(RuleBasedModel(), require_review=False).invoke(
        lg.initial_state(QUESTION), config("same")
    )
    for key in ("queries", "notes", "sources", "searches", "summary"):
        assert theirs[key] == ours[key], key


def test_interrupt_and_resume(lg: ModuleType) -> None:
    graph = lg.build_langgraph_research(RuleBasedModel())
    first = graph.invoke(lg.initial_state(QUESTION), config("hitl"))
    assert "__interrupt__" in first
    payload = first["__interrupt__"][0].value
    assert payload["question"] == QUESTION and len(payload["notes"]) == 4
    assert graph.get_state(config("hitl")).next == ("review",)
    final = graph.invoke(lg.Command(resume={"approved": True}), config("hitl"))
    assert final["summary"].startswith("Based on 4 notes")
    assert graph.get_state(config("hitl")).next == ()


def test_rejection_with_feedback(lg: ModuleType) -> None:
    graph = lg.build_langgraph_research(RuleBasedModel())
    graph.invoke(lg.initial_state(QUESTION), config("again"))
    second = graph.invoke(lg.Command(resume={"approved": False, "feedback": "solar panels"}), config("again"))
    assert second["__interrupt__"][0].value["sources"][-1] == "solar-panels"
    final = graph.invoke(lg.Command(resume={"approved": True}), config("again"))
    assert "solar-panels" in final["summary"]
