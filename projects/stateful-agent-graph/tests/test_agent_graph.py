"""Behaviour tests for the state-graph engine and the research agent, one class per milestone.

Run everything with ``python -m pytest`` or one milestone with ``-k Milestone2``. Models are fakes,
checkpoint files live in ``tmp_path``, and nothing touches the network.
"""

import json
import operator
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import pytest
from agent_graph import (
    CORPUS,
    END,
    START,
    Channel,
    CompiledGraph,
    GraphError,
    JsonFileCheckpointer,
    MemoryCheckpointer,
    OllamaModel,
    RuleBasedModel,
    ScriptedModel,
    StateGraph,
    apply_update,
    build_research_graph,
    channels_from_schema,
    matches_type,
    parse_plan,
    research_step,
    review_update,
    route_after_research,
    route_after_review,
    search_corpus,
    summary_prompt,
    tokenize,
)

QUESTION = "How do heat pumps work and how much can insulation save?"


class Counter(TypedDict):
    """A tiny state used to test the engine."""

    count: int
    log: Annotated[list[str], operator.add]
    mode: Literal["up", "down"]
    note: str | None


DEFAULTS = {"count": 0, "log": [], "mode": "up", "note": None}


def increment(state: dict) -> dict:
    return {"count": state["count"] + 1, "log": [f"inc {state['count'] + 1}"]}


def counter_graph(limit: int = 3, **compile_options) -> CompiledGraph:
    """START -> inc --(count < limit)--> inc ... -> END."""
    graph = StateGraph(Counter, defaults=DEFAULTS)
    graph.add_node("inc", increment)
    graph.add_edge(START, "inc")
    graph.add_conditional_edges(
        "inc", lambda s: "again" if s["count"] < limit else "stop", {"again": "inc", "stop": END}
    )
    return graph.compile(**compile_options)


class TestMilestone1TypedState:
    """Milestone 1: read the schema, check types, and merge updates with reducers."""

    def test_channels_from_schema(self) -> None:
        channels = channels_from_schema(Counter)
        assert list(channels) == ["count", "log", "mode", "note"]
        assert channels["log"] == Channel("log", list[str], operator.add)
        assert channels["count"].reducer is None and channels["count"].annotation is int

    @pytest.mark.parametrize(
        ("value", "annotation", "ok"),
        [
            (3, int, True), (True, int, False), (2.5, float, True), (2, float, True), ("x", int, False),
            (["a", "b"], list[str], True), (["a", 1], list[str], False), ("ab", list[str], False),
            ({"a": 1}, dict[str, int], True), ({"a": "1"}, dict[str, int], False),
            (None, str | None, True), ("x", str | None, True), (3, str | None, False),
            ("up", Literal["up", "down"], True), ("sideways", Literal["up", "down"], False),
        ],
    )  # fmt: skip
    def test_matches_type(self, value: object, annotation: object, ok: bool) -> None:
        assert matches_type(value, annotation) is ok

    def test_reducers_append_and_plain_keys_overwrite(self) -> None:
        channels = channels_from_schema(Counter)
        state = {"count": 1, "log": ["a"], "mode": "up", "note": None}
        new = apply_update(channels, state, {"count": 5, "log": ["b"], "note": "hi"})
        assert new == {"count": 5, "log": ["a", "b"], "mode": "up", "note": "hi"}
        assert state == {"count": 1, "log": ["a"], "mode": "up", "note": None}, (
            "the old state is not modified"
        )
        assert apply_update(channels, state, None) == state

    def test_bad_updates_are_rejected(self) -> None:
        channels = channels_from_schema(Counter)
        state = {"count": 1, "log": [], "mode": "up", "note": None}
        with pytest.raises(GraphError, match="unknown state key 'colour'"):
            apply_update(channels, state, {"colour": "red"})
        with pytest.raises(GraphError, match="'count'"):
            apply_update(channels, state, {"count": "two"})
        with pytest.raises(GraphError, match="'mode'"):
            apply_update(channels, state, {"mode": "sideways"})
        with pytest.raises(GraphError, match="'log'"):
            apply_update(channels, state, {"log": [1]})
        with pytest.raises(GraphError, match="dict"):
            apply_update(channels, state, ["count", 2])  # type: ignore[arg-type]


class TestMilestone2GraphAndRouting:
    """Milestone 2: build, validate and run graphs with static and conditional edges."""

    def test_linear_graph(self) -> None:
        graph = StateGraph(Counter, defaults=DEFAULTS)
        graph.add_node("first", increment).add_node("second", lambda s: {"note": f"count is {s['count']}"})
        graph.add_edge(START, "first").add_edge("first", "second").add_edge("second", END)
        result = graph.compile().invoke({"mode": "down"})
        assert result.status == "done" and result.step == 2
        assert result.state == {"count": 1, "log": ["inc 1"], "mode": "down", "note": "count is 1"}

    def test_conditional_loop(self) -> None:
        result = counter_graph(limit=4).invoke({})
        assert result.state["count"] == 4 and result.state["log"] == ["inc 1", "inc 2", "inc 3", "inc 4"]
        assert result.step == 4

    def test_router_without_path_map_returns_node_names(self) -> None:
        graph = StateGraph(Counter, defaults=DEFAULTS)
        graph.add_node("inc", increment).add_node("done", lambda s: {"note": "done"})
        graph.add_edge(START, "inc").add_edge("done", END)
        graph.add_conditional_edges("inc", lambda s: "inc" if s["count"] < 2 else "done")
        assert graph.compile().invoke({}).state["note"] == "done"

    def test_node_registration_errors(self) -> None:
        graph = StateGraph(Counter, defaults=DEFAULTS)
        graph.add_node("inc", increment)
        for name in (START, END, ""):
            with pytest.raises(GraphError):
                graph.add_node(name, increment)
        with pytest.raises(GraphError, match="already exists"):
            graph.add_node("inc", increment)
        with pytest.raises(GraphError, match=r"\(state\)"):
            graph.add_node("bad", lambda: {})
        graph.add_edge("inc", END)
        with pytest.raises(GraphError, match="already has an outgoing edge"):
            graph.add_edge("inc", "inc")
        with pytest.raises(GraphError):
            StateGraph(Counter, defaults={"colour": "red"})

    @pytest.mark.parametrize(
        ("build", "fragment"),
        [
            (lambda g: g.add_node("a", increment).add_edge("a", END), "entry point"),
            (lambda g: g.add_node("a", increment).add_edge(START, "a").add_edge("a", "b"), "unknown node"),
            (lambda g: g.add_node("a", increment).add_edge(START, "a"), "no outgoing edge"),
            (lambda g: g.add_node("a", increment).add_node("b", increment).add_edge(START, "a")
             .add_edge("a", END).add_edge("b", END), r"unreachable node\(s\): b"),
            (lambda g: g.add_node("a", increment).add_edge(START, "a")
             .add_conditional_edges("a", lambda s: "x", {"x": "nowhere"}), "unknown node"),
        ],
    )  # fmt: skip
    def test_validation(self, build, fragment: str) -> None:
        graph = StateGraph(Counter, defaults=DEFAULTS)
        build(graph)
        with pytest.raises(GraphError, match=fragment):
            graph.compile()

    def test_runtime_errors(self) -> None:
        graph = StateGraph(Counter, defaults=DEFAULTS)
        graph.add_node("inc", increment).add_edge(START, "inc")
        graph.add_conditional_edges("inc", lambda s: "sideways", {"again": "inc", "stop": END})
        with pytest.raises(GraphError, match="'sideways'"):
            graph.compile().invoke({}, "t1")
        with pytest.raises(GraphError, match="recursion limit of 5"):
            counter_graph(limit=100, recursion_limit=5).invoke({})
        with pytest.raises(GraphError, match="missing state keys"):
            StateGraph(Counter).add_node("inc", increment).add_edge(START, "inc").add_edge(
                "inc", END
            ).compile().invoke({"count": 0})

    def test_nodes_cannot_change_state_in_place(self) -> None:
        def sneaky(state: dict) -> dict:
            state["log"].append("smuggled")
            state["count"] = 99
            return {"note": "returned"}

        graph = StateGraph(Counter, defaults=DEFAULTS)
        graph.add_node("sneaky", sneaky).add_edge(START, "sneaky").add_edge("sneaky", END)
        assert graph.compile().invoke({}).state == {"count": 0, "log": [], "mode": "up", "note": "returned"}


class TestMilestone3Checkpoints:
    """Milestone 3: a checkpoint after every node, in memory or in JSON files."""

    def test_history_has_one_checkpoint_per_step(self) -> None:
        graph = counter_graph(limit=2)
        graph.invoke({}, "t1")
        history = graph.history("t1")
        assert [(c.step, c.next_node, c.status) for c in history] == [
            (0, "inc", "running"),
            (1, "inc", "running"),
            (2, END, "done"),
        ]
        assert [c.state["count"] for c in history] == [0, 1, 2]
        assert graph.get_state("t1") == history[-1] and graph.get_state("other") is None

    def test_checkpoints_are_snapshots(self) -> None:
        checkpointer = MemoryCheckpointer()
        graph = counter_graph(limit=2, checkpointer=checkpointer)
        graph.invoke({}, "t1")
        assert checkpointer.history("t1")[1].state["log"] == ["inc 1"], (
            "later steps must not change earlier snapshots"
        )

    def test_threads_are_independent_and_runs_restart_only_when_done(self) -> None:
        graph = counter_graph(limit=2)
        graph.invoke({}, "a")
        graph.invoke({"count": 5}, "b")
        assert graph.get_state("a").state["count"] == 2 and graph.get_state("b").state["count"] == 6
        assert graph.invoke({}, "a").state["count"] == 2, "a finished thread can be run again"

    def test_json_checkpoints_survive_a_restart(self, tmp_path: Path) -> None:
        counter_graph(limit=3, checkpointer=JsonFileCheckpointer(tmp_path)).invoke({}, "job-1")
        files = sorted(p.name for p in tmp_path.iterdir())
        assert files == ["job-1.json"], "one file per thread and no temporary files left"
        reloaded = JsonFileCheckpointer(tmp_path).history("job-1")
        assert [c.step for c in reloaded] == [0, 1, 2, 3] and reloaded[-1].state["log"] == [
            "inc 1",
            "inc 2",
            "inc 3",
        ]
        assert json.loads((tmp_path / "job-1.json").read_text(encoding="utf-8"))[-1]["status"] == "done"

    @pytest.mark.parametrize("thread_id", ["../escape", "a/b", "..", "", "x" * 65, "C:\\temp"])
    def test_thread_ids_cannot_escape_the_folder(self, tmp_path: Path, thread_id: str) -> None:
        with pytest.raises(GraphError, match="invalid thread id"):
            JsonFileCheckpointer(tmp_path).history(thread_id)

    def test_state_must_be_json_serialisable(self) -> None:
        class Loose(TypedDict):
            thing: object

        graph = (
            StateGraph(Loose)
            .add_node("n", lambda s: {"thing": {1, 2}})
            .add_edge(START, "n")
            .add_edge("n", END)
        )
        with pytest.raises(GraphError, match="JSON"):
            graph.compile().invoke({"thing": None})

    def test_resume_after_a_crash(self, tmp_path: Path) -> None:
        attempts = {"n": 0}

        def flaky(state: dict) -> dict:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ConnectionError("the process died here")
            return {"note": "recovered"}

        def build() -> CompiledGraph:
            graph = StateGraph(Counter, defaults=DEFAULTS)
            graph.add_node("inc", increment).add_node("flaky", flaky)
            graph.add_edge(START, "inc").add_edge("inc", "flaky").add_edge("flaky", END)
            return graph.compile(checkpointer=JsonFileCheckpointer(tmp_path))

        with pytest.raises(ConnectionError):
            build().invoke({}, "job")
        latest = JsonFileCheckpointer(tmp_path).get("job")
        assert (latest.step, latest.next_node, latest.status) == (1, "flaky", "running")
        with pytest.raises(GraphError, match="unfinished"):
            build().invoke({}, "job")
        result = build().resume("job")  # a new engine instance, as after a restart
        assert result.status == "done" and result.state["count"] == 1 and result.state["note"] == "recovered"
        with pytest.raises(GraphError, match="already finished"):
            build().resume("job")
        with pytest.raises(GraphError, match="no checkpoint"):
            build().resume("never-started")


class TestMilestone4InterruptResume:
    """Milestone 4: pause inside a node, resume later with a value — the node runs again from the top."""

    @staticmethod
    def approval_graph(calls: dict, checkpointer=None) -> CompiledGraph:
        def ask(state: dict, ctx) -> dict:
            calls["before"] += 1  # code before interrupt() runs again on resume
            answer = ctx.interrupt({"question": f"approve count {state['count']}?"})
            calls["after"] += 1
            return {"note": f"human said {answer}"}

        graph = StateGraph(Counter, defaults=DEFAULTS)
        graph.add_node("inc", increment).add_node("ask", ask).add_node(
            "finish", lambda s: {"log": ["finished"]}
        )
        graph.add_edge(START, "inc").add_edge("inc", "ask").add_edge("ask", "finish").add_edge("finish", END)
        return graph.compile(checkpointer=checkpointer)

    def test_interrupt_pauses_with_a_payload(self) -> None:
        calls = {"before": 0, "after": 0}
        graph = self.approval_graph(calls)
        result = graph.invoke({}, "t")
        assert (result.status, result.interrupt, result.step) == (
            "interrupted",
            {"question": "approve count 1?"},
            1,
        )
        latest = graph.get_state("t")
        assert (latest.status, latest.next_node, latest.interrupt) == (
            "interrupted",
            "ask",
            {"question": "approve count 1?"},
        )
        assert calls == {"before": 1, "after": 0}

    def test_resume_reruns_the_node_with_the_value(self) -> None:
        calls = {"before": 0, "after": 0}
        graph = self.approval_graph(calls)
        graph.invoke({}, "t")
        result = graph.resume("t", "yes")
        assert result.status == "done" and result.state["note"] == "human said yes"
        assert result.state["log"] == ["inc 1", "finished"]
        assert calls == {"before": 2, "after": 1}, "the interrupted node runs again from the start"
        assert [c.status for c in graph.history("t")] == [
            "running",
            "running",
            "interrupted",
            "running",
            "done",
        ]

    def test_resume_rules(self) -> None:
        graph = self.approval_graph({"before": 0, "after": 0})
        graph.invoke({}, "t")
        with pytest.raises(GraphError, match="waiting for input"):
            graph.resume("t")
        with pytest.raises(GraphError, match="unfinished"):
            graph.invoke({}, "t")
        graph.resume("t", None)
        assert graph.get_state("t").state["note"] == "human said None", "None is a valid answer"

    def test_resume_in_another_process(self, tmp_path: Path) -> None:
        self.approval_graph({"before": 0, "after": 0}, JsonFileCheckpointer(tmp_path)).invoke({}, "ticket-7")
        fresh = self.approval_graph({"before": 0, "after": 0}, JsonFileCheckpointer(tmp_path))
        assert fresh.get_state("ticket-7").interrupt == {"question": "approve count 1?"}
        assert fresh.resume("ticket-7", "ok").state["note"] == "human said ok"

    def test_one_interrupt_per_node_run(self) -> None:
        def greedy(state: dict, ctx) -> dict:
            first = ctx.interrupt("first?")
            ctx.interrupt("second?")
            return {"note": first}

        graph = (
            StateGraph(Counter, defaults=DEFAULTS)
            .add_node("g", greedy)
            .add_edge(START, "g")
            .add_edge("g", END)
        )
        compiled = graph.compile()
        compiled.invoke({}, "t")
        with pytest.raises(GraphError, match="one interrupt"):
            compiled.resume("t", "yes")


class TestMilestone5ResearchAgent:
    """Milestone 5: the research-then-summarise agent on your engine."""

    def test_tokenize_and_search(self) -> None:
        assert tokenize("How do heat pumps work?") == ["heat", "pumps", "work"]
        assert search_corpus(CORPUS, "heat pumps") == [
            (
                "heat-pump-efficiency",
                "Heat pumps deliver about three units of heat for every unit of electricity they use.",
            ),
            (
                "heat-pumps",
                "Modern air-source heat pumps keep working in cold weather down to about minus 20 degrees.",
            ),
        ]
        assert search_corpus(CORPUS, "the and of") == []
        assert [doc for doc, _ in search_corpus(CORPUS, "insulation", k=5)] == [
            "insulation",
            "insulation-savings",
        ]

    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ('["heat pumps", "insulation"]', ["heat pumps", "insulation"]),
            ('["a", "b", "c", "d"]', ["a", "b", "c"]),
            ('["ok", 3, "", "  "]', ["ok"]),
            ("Sure! Here are some queries", ["Q?"]),
            ('{"queries": ["x"]}', ["Q?"]),
            ("[]", ["Q?"]),
            (json.dumps(["x" * 101]), ["Q?"]),
        ],
    )
    def test_parse_plan_never_trusts_the_model(self, reply: str, expected: list[str]) -> None:
        assert parse_plan(reply, "Q?") == expected

    def test_research_step_and_routing(self) -> None:
        state = {"queries": ["heat pumps", "heat pump efficiency"], "searches": 0, "notes": [], "sources": []}
        first = research_step(state, CORPUS)
        assert first["sources"] == ["heat-pump-efficiency", "heat-pumps"] and first["searches"] == 1
        state = {**state, "searches": 1, "notes": first["notes"], "sources": first["sources"]}
        assert research_step(state, CORPUS)["sources"] == [], "documents already used are skipped"
        route = {"max_searches": 3, "min_notes": 3}
        assert (
            route_after_research({"queries": ["a", "b"], "searches": 1, "notes": ["n"]}, **route)
            == "research"
        )
        assert (
            route_after_research({"queries": ["a", "b"], "searches": 1, "notes": ["n"] * 3}, **route)
            == "review"
        )
        assert route_after_research({"queries": ["a", "b"], "searches": 2, "notes": []}, **route) == "review"
        assert route_after_research({"queries": ["a"] * 5, "searches": 3, "notes": []}, **route) == "review"

    def test_review_decisions(self) -> None:
        assert review_update({"approved": True}) == {"approved": True, "feedback": ""}
        assert review_update({"approved": False, "feedback": " solar panels "}) == {
            "approved": False,
            "feedback": "solar panels",
            "queries": ["solar panels"],
        }
        for bad in [
            "yes",
            {"approved": "yes"},
            {"approved": False, "feedback": 3},
            {"approved": True, "feedback": "x" * 101},
        ]:
            with pytest.raises(GraphError):
                review_update(bad)
        assert route_after_review({"approved": True, "searches": 1, "queries": ["a"]}) == "summarise"
        assert route_after_review({"approved": False, "searches": 1, "queries": ["a", "b"]}) == "research"
        assert route_after_review({"approved": False, "searches": 1, "queries": ["a"]}) == "end"

    def test_runs_without_review(self) -> None:
        result = build_research_graph(require_review=False).invoke({"question": QUESTION}, "r1")
        state = result.state
        assert result.status == "done"
        assert state["queries"] == ["How do heat pumps work", "how much can insulation save"]
        assert state["searches"] == 2 and len(state["notes"]) == 4
        assert state["sources"] == ["heat-pump-efficiency", "heat-pumps", "insulation", "insulation-savings"]
        assert state["summary"].startswith("Based on 4 notes:") and "insulation-savings" in state["summary"]

    def test_pauses_for_review_then_summarises(self) -> None:
        graph = build_research_graph()
        paused = graph.invoke({"question": QUESTION}, "r2")
        assert paused.status == "interrupted" and graph.get_state("r2").next_node == "review"
        assert paused.interrupt["question"] == QUESTION and len(paused.interrupt["notes"]) == 4
        assert paused.state["summary"] == ""
        final = graph.resume("r2", {"approved": True})
        assert final.status == "done" and final.state["approved"] is True and final.state["summary"]

    def test_rejection_with_feedback_researches_more(self) -> None:
        graph = build_research_graph()
        graph.invoke({"question": QUESTION}, "r3")
        again = graph.resume("r3", {"approved": False, "feedback": "solar panels"})
        assert again.status == "interrupted", "after more research the reviewer is asked again"
        assert again.interrupt["sources"][-1] == "solar-panels" and again.state["searches"] == 3
        final = graph.resume("r3", {"approved": True})
        assert "solar-panels" in final.state["summary"]

    def test_rejection_without_feedback_ends_without_a_summary(self) -> None:
        graph = build_research_graph()
        graph.invoke({"question": QUESTION}, "r4")
        final = graph.resume("r4", {"approved": False})
        assert (
            final.status == "done" and final.state["summary"] == "" and graph.get_state("r4").next_node == END
        )

    def test_budget_and_untrusted_plans(self) -> None:
        model = ScriptedModel(["not json at all", "A short answer."])
        result = build_research_graph(model, require_review=False, max_searches=1).invoke(
            {"question": "solar panels"}
        )
        assert result.state["queries"] == ["solar panels"] and result.state["searches"] == 1
        assert result.state["summary"] == "A short answer."
        assert model.prompts[0].startswith("PLAN:") and model.prompts[1].startswith("SUMMARISE:")
        assert "- Solar panels turn sunlight into electricity" in model.prompts[1]

    def test_summary_prompt_contains_only_notes_and_sources(self) -> None:
        prompt = summary_prompt({"question": "Q", "notes": ["n1", "n2"], "sources": ["a", "b"]})
        assert prompt.splitlines()[-4:] == ["Notes:", "- n1", "- n2", "Sources: a, b"]

    def test_resume_the_agent_after_a_restart(self, tmp_path: Path) -> None:
        build_research_graph(checkpointer=JsonFileCheckpointer(tmp_path)).invoke(
            {"question": QUESTION}, "case-42"
        )
        later = build_research_graph(RuleBasedModel(), checkpointer=JsonFileCheckpointer(tmp_path))
        final = later.resume("case-42", {"approved": True})
        assert final.state["summary"].startswith("Based on 4 notes")
        assert [c.next_node for c in later.history("case-42")][-3:] == ["review", "summarise", END]

    def test_ollama_adapter_is_local_only(self) -> None:
        assert OllamaModel(base_url="http://localhost:11434").url == "http://localhost:11434/api/chat"
        with pytest.raises(ValueError):
            OllamaModel(base_url="http://example.com:11434")
