"""Behaviour tests for the tool-using assistant, one class per milestone.

Run everything with ``python -m pytest projects/tool-using-assistant`` or one milestone with
``-k Milestone3``. The "model" is always a :class:`ScriptedModel`, so every run is reproducible;
files live in ``tmp_path``.
"""

import json
import os
from pathlib import Path

import pytest
from tool_assistant import (
    Agent,
    FinalAnswer,
    Message,
    ModelOutputError,
    OllamaModel,
    RegistryError,
    ScriptedModel,
    ScriptExhaustedError,
    Tool,
    ToolCall,
    ToolError,
    ToolRegistry,
    build_system_prompt,
    convert_units,
    default_registry,
    format_number,
    make_calculator_tool,
    make_file_reader_tool,
    make_unit_converter_tool,
    parse_action,
    read_sandboxed_file,
    resolve_in_sandbox,
    safe_calculate,
    validate_arguments,
)

ECHO_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "maxLength": 10},
        "times": {"type": "integer", "minimum": 1, "maximum": 3},
        "mode": {"type": "string", "enum": ["upper", "lower"]},
        "loud": {"type": "boolean"},
        "ratio": {"type": "number"},
    },
    "required": ["text"],
    "additionalProperties": False,
}


def echo_tool(name: str = "echo") -> Tool:
    """A tiny tool used to test the registry without depending on the real tools."""
    return Tool(name, "Repeat some text.", ECHO_SCHEMA, lambda text, times=1, **_: " ".join([text] * times))


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A sandbox folder with two notes, plus a secret file *outside* it."""
    root = tmp_path / "sandbox"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "todo.txt").write_text("buy milk\ncall Sam\n", encoding="utf-8")
    (root / "readme.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    return root


def call(tool: str, **arguments: object) -> dict:
    """A scripted tool-call reply."""
    return {"tool": tool, "arguments": arguments}


def final(text: str) -> dict:
    """A scripted final-answer reply."""
    return {"final": text}


class TestMilestone1Registry:
    """Milestone 1: tool definitions, the registry and argument validation."""

    def test_register_and_list_specs(self) -> None:
        registry = ToolRegistry([echo_tool()])
        assert registry.names() == ["echo"]
        assert registry.get("echo") is not None and registry.get("nope") is None
        assert registry.specs() == [
            {"name": "echo", "description": "Repeat some text.", "parameters": ECHO_SCHEMA}
        ]
        json.dumps(registry.specs())  # specs are what the model sees: they must be JSON-serialisable

    def test_duplicate_and_invalid_names_are_rejected(self) -> None:
        registry = ToolRegistry([echo_tool()])
        with pytest.raises(RegistryError, match="already registered"):
            registry.register(echo_tool())
        for bad in ["", "Echo", "has space", "1st", "dash-name"]:
            with pytest.raises(RegistryError):
                registry.register(echo_tool(bad))

    def test_tools_need_a_description_and_a_valid_schema(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(RegistryError, match="description"):
            registry.register(Tool("quiet", "  ", ECHO_SCHEMA, print))
        bad_schemas = [
            {"type": "array"},
            {"type": "object"},
            {"type": "object", "properties": {"x": {"type": "date"}}},
            {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["y"]},
        ]
        for schema in bad_schemas:
            with pytest.raises(RegistryError):
                registry.register(Tool("bad", "A tool.", schema, print))

    def test_valid_arguments_produce_no_errors(self) -> None:
        assert validate_arguments(ECHO_SCHEMA, {"text": "hi"}) == []
        assert (
            validate_arguments(
                ECHO_SCHEMA, {"text": "hi", "times": 2, "mode": "upper", "loud": True, "ratio": 1}
            )
            == []
        )
        assert validate_arguments(ECHO_SCHEMA, {"text": "hi", "ratio": 0.5}) == []

    @pytest.mark.parametrize(
        ("arguments", "fragment"),
        [
            ([1, 2], "JSON object"),
            ({}, "missing required argument 'text'"),
            ({"text": 5}, "'text' must be of type string"),
            ({"text": "hi", "times": "2"}, "'times' must be of type integer"),
            ({"text": "hi", "times": 1.5}, "'times' must be of type integer"),
            ({"text": "hi", "times": True}, "'times' must be of type integer"),
            ({"text": "hi", "ratio": False}, "'ratio' must be of type number"),
            ({"text": "hi", "times": 9}, "'times' must be <= 3"),
            ({"text": "hi", "times": 0}, "'times' must be >= 1"),
            ({"text": "a" * 11}, "at most 10 characters"),
            ({"text": "hi", "mode": "shout"}, "must be one of: upper, lower"),
            ({"text": "hi", "colour": "red"}, "unexpected argument 'colour'"),
        ],
    )
    def test_invalid_arguments_are_explained(self, arguments: object, fragment: str) -> None:
        errors = validate_arguments(ECHO_SCHEMA, arguments)
        assert any(fragment in error for error in errors), (
            f"expected an error containing {fragment!r}, got {errors}"
        )

    def test_execute_validates_then_runs(self) -> None:
        registry = ToolRegistry([echo_tool()])
        outcome = registry.execute("echo", {"text": "hi", "times": 2})
        assert (outcome.ok, outcome.content, outcome.error_kind) == (True, "hi hi", None)
        unknown = registry.execute("shout", {})
        assert not unknown.ok and unknown.error_kind == "unknown_tool" and "echo" in unknown.content
        invalid = registry.execute("echo", {"times": 2})
        assert not invalid.ok and invalid.error_kind == "invalid_arguments" and "text" in invalid.content

    def test_execute_turns_tool_exceptions_into_outcomes(self) -> None:
        def broken(text: str) -> str:
            raise ToolError("the printer is out of paper")

        def buggy(text: str) -> str:
            return {}["missing"]

        schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
        registry = ToolRegistry(
            [Tool("broken", "Fails politely.", schema, broken), Tool("buggy", "Has a bug.", schema, buggy)]
        )
        polite = registry.execute("broken", {"text": "x"})
        assert (polite.ok, polite.content, polite.error_kind) == (
            False,
            "the printer is out of paper",
            "tool_error",
        )
        crash = registry.execute("buggy", {"text": "x"})
        assert not crash.ok and crash.error_kind == "crash" and "KeyError" in crash.content
        assert "Traceback" not in crash.content


class TestMilestone2CalculatorAndUnits:
    """Milestone 2: a calculator that never calls eval, and a unit converter."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("2 + 3 * 4", 14),
            ("(2 + 3) * 4", 20),
            ("10 / 4", 2.5),
            ("7 // 2", 3),
            ("7 % 4", 3),
            ("2 ** 10", 1024),
            ("-3 + +5", 2),
        ],
    )
    def test_arithmetic(self, expression: str, expected: float) -> None:
        assert safe_calculate(expression) == expected

    @pytest.mark.parametrize(
        "expression",
        [
            "__import__('os').getcwd()",
            "open('x')",
            "x + 1",
            "(1).real",
            "[1, 2]",
            "'a' * 3",
            "True + 1",
            "1 if 1 else 2",
            "1j",
        ],
    )
    def test_anything_but_arithmetic_is_rejected(self, expression: str) -> None:
        with pytest.raises(ToolError):
            safe_calculate(expression)

    @pytest.mark.parametrize(
        ("expression", "fragment"),
        [
            ("1 / 0", "division by zero"),
            ("9 ** 9 ** 9", "exponent"),
            ("10 ** 99 * 10 ** 99", "too large"),
            ("2 +", "parse"),
        ],
    )
    def test_dangerous_or_broken_input_gives_clear_errors(self, expression: str, fragment: str) -> None:
        with pytest.raises(ToolError, match=fragment):
            safe_calculate(expression)

    def test_long_expressions_are_rejected(self) -> None:
        with pytest.raises(ToolError, match="longer than"):
            safe_calculate("1+" * 150 + "1")

    def test_format_number(self) -> None:
        assert [format_number(v) for v in (4, 2.0, 2.5, 1 / 3, 0.1 + 0.2)] == [
            "4",
            "2",
            "2.5",
            "0.3333333333",
            "0.3",
        ]

    def test_calculator_tool_returns_text(self) -> None:
        registry = ToolRegistry([make_calculator_tool()])
        assert registry.execute("calculator", {"expression": "(3 + 4) * 2"}).content == "14"
        assert registry.execute("calculator", {"expression": "1/0"}).error_kind == "tool_error"

    @pytest.mark.parametrize(
        ("value", "source", "target", "expected"),
        [(1, "km", "m", 1000), (1, "mi", "km", 1.609344), (12, "in", "ft", 1), (1, "kg", "lb", 2.2046226218),
         (100, "c", "f", 212), (32, "f", "c", 0), (0, "c", "k", 273.15)],
    )  # fmt: skip
    def test_conversions(self, value: float, source: str, target: str, expected: float) -> None:
        assert convert_units(value, source, target) == pytest.approx(expected)

    def test_conversion_errors(self) -> None:
        with pytest.raises(ToolError, match="different things"):
            convert_units(1, "km", "kg")
        with pytest.raises(ToolError, match="unknown unit"):
            convert_units(1, "parsec", "km")
        with pytest.raises(ToolError, match="absolute zero"):
            convert_units(-300, "c", "f")

    def test_unit_tool_schema_lists_units_and_formats_result(self) -> None:
        tool = make_unit_converter_tool()
        assert "mi" in tool.parameters["properties"]["to_unit"]["enum"]
        registry = ToolRegistry([tool])
        assert (
            registry.execute("convert_units", {"value": 5, "from_unit": "km", "to_unit": "m"}).content
            == "5 km = 5000 m"
        )
        assert registry.execute(
            "convert_units", {"value": 5, "from_unit": "km", "to_unit": "lightyear"}
        ).error_kind == ("invalid_arguments")


class TestMilestone3Sandbox:
    """Milestone 3: a file reader that can only read inside its sandbox."""

    def test_reads_files_inside_the_sandbox(self, sandbox: Path) -> None:
        assert read_sandboxed_file(sandbox, "notes/todo.txt") == "buy milk\ncall Sam\n"
        assert read_sandboxed_file(sandbox, "notes\\todo.txt") == "buy milk\ncall Sam\n"
        assert resolve_in_sandbox(sandbox, "readme.txt") == (sandbox / "readme.txt").resolve()

    @pytest.mark.parametrize(
        "path",
        ["../secret.txt", "notes/../../secret.txt", "..\\secret.txt", "notes/..", "./../secret.txt"],
    )
    def test_parent_directory_traversal_is_blocked(self, sandbox: Path, path: str) -> None:
        with pytest.raises(ToolError, match="denied"):
            resolve_in_sandbox(sandbox, path)

    def test_absolute_paths_are_blocked(self, sandbox: Path) -> None:
        secret = str((sandbox.parent / "secret.txt").resolve())
        for path in [
            secret,
            "/etc/passwd",
            "C:\\Windows\\win.ini",
            "C:secret.txt",
            "\\\\server\\share\\x.txt",
        ]:
            with pytest.raises(ToolError, match="absolute"):
                resolve_in_sandbox(sandbox, path)

    def test_empty_and_nul_paths_are_rejected(self, sandbox: Path) -> None:
        for path in ["", "   ", "notes/\x00todo.txt"]:
            with pytest.raises(ToolError):
                resolve_in_sandbox(sandbox, path)

    def test_symlink_pointing_outside_is_blocked(self, sandbox: Path) -> None:
        link = sandbox / "shortcut.txt"
        try:
            os.symlink(sandbox.parent / "secret.txt", link)
        except (OSError, NotImplementedError):
            pytest.skip("this system does not allow creating symlinks (Windows without Developer Mode)")
        with pytest.raises(ToolError, match="outside the sandbox"):
            read_sandboxed_file(sandbox, "shortcut.txt")

    def test_missing_directories_binary_and_large_files(self, sandbox: Path) -> None:
        with pytest.raises(ToolError, match="not found"):
            read_sandboxed_file(sandbox, "nope.txt")
        with pytest.raises(ToolError, match="not a regular file"):
            read_sandboxed_file(sandbox, "notes")
        (sandbox / "image.bin").write_bytes(b"\x89PNG\x00\x00")
        with pytest.raises(ToolError, match="binary"):
            read_sandboxed_file(sandbox, "image.bin")
        (sandbox / "big.txt").write_text("x" * 50, encoding="utf-8")
        text = read_sandboxed_file(sandbox, "big.txt", max_bytes=10)
        assert text.startswith("x" * 10) and "truncated after 10 bytes" in text

    def test_error_messages_do_not_leak_host_paths(self, sandbox: Path) -> None:
        registry = ToolRegistry([make_file_reader_tool(sandbox)])
        outcome = registry.execute("read_file", {"path": "../secret.txt"})
        assert not outcome.ok and outcome.error_kind == "tool_error"
        assert str(sandbox) not in outcome.content and "TOP SECRET" not in outcome.content

    def test_default_registry_has_three_tools(self, sandbox: Path) -> None:
        assert default_registry(sandbox).names() == ["calculator", "convert_units", "read_file"]


class TestMilestone4ParsingAndLoop:
    """Milestone 4: parse the model's reply and run the basic agent loop."""

    def test_parse_tool_call_and_final_answer(self) -> None:
        assert parse_action('{"tool": "calculator", "arguments": {"expression": "1+1"}}') == ToolCall(
            "calculator", {"expression": "1+1"}
        )
        assert parse_action('{"thought": "easy", "final": "2"}') == FinalAnswer("2", "easy")
        assert parse_action('{"tool": "list_things"}') == ToolCall("list_things", {})
        assert parse_action('```json\n{"final": "fenced"}\n```') == FinalAnswer("fenced")

    @pytest.mark.parametrize(
        "reply",
        [
            "The answer is 4.",
            "[1, 2]",
            "{}",
            '{"tool": "calculator", "final": "4"}',
            '{"tool": "", "arguments": {}}',
            '{"tool": "calculator", "arguments": "1+1"}',
            '{"final": 4}',
            '{"final": "4", "arguments": {}}',
            '{"final": "4", "confidence": 0.9}',
            '{"thought": 3, "final": "4"}',
        ],
    )
    def test_invalid_replies_raise(self, reply: str) -> None:
        with pytest.raises(ModelOutputError):
            parse_action(reply)

    def test_scripted_model_replays_and_records(self) -> None:
        model = ScriptedModel([final("one"), '{"final": "two"}'])
        first = [Message("user", "hi")]
        assert model.complete(first, []) == '{"final": "one"}'
        assert model.complete(first + [Message("user", "again")], []) == '{"final": "two"}'
        assert [len(seen) for seen in model.seen] == [1, 2]
        with pytest.raises(ScriptExhaustedError):
            model.complete(first, [])

    def test_system_prompt_lists_tools_and_protocol(self, sandbox: Path) -> None:
        prompt = build_system_prompt(default_registry(sandbox).specs())
        for fragment in ['"tool"', '"final"', "calculator", "convert_units", "read_file", "ERROR"]:
            assert fragment in prompt

    def test_answers_directly_without_tools(self, sandbox: Path) -> None:
        result = Agent(ScriptedModel([final("Hello!")]), default_registry(sandbox)).run("Say hello")
        assert (result.status, result.answer, result.steps) == ("completed", "Hello!", 1)
        assert result.tools_used() == []
        assert [m.role for m in result.messages] == ["system", "user", "assistant"]

    def test_runs_tools_and_feeds_results_back(self, sandbox: Path) -> None:
        model = ScriptedModel([
            call("read_file", path="notes/todo.txt"),
            call("calculator", expression="2 * 21"),
            final("You have 2 tasks; 2 * 21 = 42."),
        ])  # fmt: skip
        result = Agent(model, default_registry(sandbox)).run("What is on my list, and what is 2*21?")
        assert result.status == "completed" and result.steps == 3
        assert result.tools_used() == ["read_file", "calculator"]
        assert [e.kind for e in result.transcript] == [
            "tool_call",
            "tool_result",
            "tool_call",
            "tool_result",
            "final_answer",
        ]
        assert [e.step for e in result.transcript] == [1, 1, 2, 2, 3]
        second_view = model.seen[1]
        assert second_view[-1] == Message("tool", "buy milk\ncall Sam\n", name="read_file")
        assert model.seen[2][-1] == Message("tool", "42", name="calculator")
        assert model.seen[0][0].role == "system" and model.seen[0][1] == Message(
            "user", "What is on my list, and what is 2*21?"
        )

    def test_transcript_records_arguments_and_thoughts(self, sandbox: Path) -> None:
        model = ScriptedModel(
            [
                {"thought": "convert", **call("convert_units", value=1, from_unit="km", to_unit="m")},
                final("1000 m"),
            ]
        )
        result = Agent(model, default_registry(sandbox)).run("1 km in m?")
        first = result.transcript[0]
        assert first.data == {
            "tool": "convert_units",
            "arguments": {"value": 1, "from_unit": "km", "to_unit": "m"},
            "thought": "convert",
        }
        assert result.transcript[1].data == {"tool": "convert_units", "content": "1 km = 1000 m"}


class TestMilestone5ErrorsAndBudget:
    """Milestone 5: errors become observations, and the step budget always ends the run."""

    def test_tool_errors_are_fed_back_and_the_model_recovers(self, sandbox: Path) -> None:
        model = ScriptedModel(
            [call("calculator", expression="1 / 0"), call("calculator", expression="1 / 2"), final("0.5")]
        )
        result = Agent(model, default_registry(sandbox)).run("1/0?")
        assert result.status == "completed" and result.answer == "0.5"
        assert [e.kind for e in result.transcript] == [
            "tool_call",
            "tool_error",
            "tool_call",
            "tool_result",
            "final_answer",
        ]
        assert result.transcript[1].data["kind"] == "tool_error"
        feedback = model.seen[1][-1]
        assert feedback.role == "tool" and feedback.name == "calculator"
        assert feedback.content.startswith("ERROR:") and "division by zero" in feedback.content

    def test_unknown_tools_and_bad_arguments_are_reported(self, sandbox: Path) -> None:
        model = ScriptedModel([
            call("web_search", query="weather"),
            call("convert_units", value="5", from_unit="km", to_unit="m"),
            final("I cannot search the web."),
        ])  # fmt: skip
        result = Agent(model, default_registry(sandbox)).run("weather?")
        kinds = [e.data["kind"] for e in result.transcript if e.kind == "tool_error"]
        assert kinds == ["unknown_tool", "invalid_arguments"]
        assert "Available tools: calculator, convert_units, read_file" in model.seen[1][-1].content
        assert "'value' must be of type number" in model.seen[2][-1].content

    def test_sandbox_violations_are_tool_errors_not_crashes(self, sandbox: Path) -> None:
        model = ScriptedModel([call("read_file", path="../secret.txt"), final("Access was denied.")])
        result = Agent(model, default_registry(sandbox)).run("read the secret")
        assert result.status == "completed"
        assert all("TOP SECRET" not in m.content for m in result.messages)
        assert "denied" in model.seen[1][-1].content

    def test_invalid_output_is_reported_back(self, sandbox: Path) -> None:
        model = ScriptedModel(["Sure! The answer is 4.", final("4")])
        result = Agent(model, default_registry(sandbox)).run("2+2?")
        assert result.status == "completed" and result.steps == 2
        assert result.transcript[0].kind == "invalid_output"
        assert result.transcript[0].data["reply"] == "Sure! The answer is 4."
        feedback = model.seen[1][-1]
        assert (
            feedback.role == "user" and feedback.content.startswith("ERROR:") and "JSON" in feedback.content
        )

    def test_step_budget_stops_a_looping_model(self, sandbox: Path) -> None:
        model = ScriptedModel([call("calculator", expression="1 + 1")] * 10)
        result = Agent(model, default_registry(sandbox), max_steps=3).run("loop forever")
        assert (result.status, result.answer, result.steps) == ("max_steps", None, 3)
        assert len(model.seen) == 3, "the model must be called at most max_steps times"
        assert result.transcript[-1].kind == "budget_exhausted"
        assert result.transcript[-1].data == {"max_steps": 3}

    def test_invalid_output_counts_against_the_budget(self, sandbox: Path) -> None:
        result = Agent(ScriptedModel(["nope"] * 5), default_registry(sandbox), max_steps=2).run("?")
        assert result.status == "max_steps" and [e.kind for e in result.transcript] == [
            "invalid_output",
            "invalid_output",
            "budget_exhausted",
        ]

    def test_long_observations_are_truncated(self, sandbox: Path) -> None:
        (sandbox / "long.txt").write_text("y" * 3000, encoding="utf-8")
        model = ScriptedModel([call("read_file", path="long.txt"), final("long")])
        Agent(model, default_registry(sandbox), max_observation_chars=100).run("read it")
        observation = model.seen[1][-1].content
        assert observation.startswith("y" * 100) and "truncated" in observation and len(observation) < 200

    def test_max_steps_must_be_positive(self, sandbox: Path) -> None:
        with pytest.raises(ValueError):
            Agent(ScriptedModel([]), default_registry(sandbox), max_steps=0)

    def test_ollama_adapter_only_accepts_local_urls(self) -> None:
        assert OllamaModel(base_url="http://127.0.0.1:11434").url == "http://127.0.0.1:11434/api/chat"
        for url in ["https://api.example.com", "ftp://localhost:11434", "http://10.0.0.5:11434"]:
            with pytest.raises(ValueError):
                OllamaModel(base_url=url)
