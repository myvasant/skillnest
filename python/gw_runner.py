"""Groundwork learner-code runner.

This module runs inside Pyodide (CPython compiled to WebAssembly). The browser
worker and the automated content tests both load this exact file, so the code a
learner runs and the code the test-suite verifies go through the same path.

Public entry points return JSON strings so the JavaScript side never has to deal
with Python proxies:

* ``run_json(code, stdin)``                 -> execute a program
* ``trace_json(code, stdin, max_steps)``    -> execute while recording each step
* ``grade_json(code, tests_json, stdin)``   -> execute, then run exercise tests

Safety model (see SECURITY.md): learner code runs in a Web Worker, isolated from
the page DOM and from saved progress. Wall-clock time limits are enforced by the
JavaScript host terminating the worker; this module limits output size and the
number of recorded trace steps.
"""

from __future__ import annotations

import ast
import builtins
import dis
import inspect
import io
import json
import linecache
import sys
import time
import traceback
import types

LEARNER_FILE = "<learner>"
TEST_FILE = "<test>"
MAX_OUTPUT_CHARS = 200_000
DEFAULT_MAX_STEPS = 400
HARD_MAX_STEPS = 2_000
MAX_CONTAINER_ITEMS = 25
MAX_REPR_CHARS = 120
MAX_HEAP_DEPTH = 5


class OutputLimitExceeded(Exception):
    """Raised when a program prints far more than any lesson needs."""


class TraceLimitReached(Exception):
    """Raised internally to stop tracing after the step budget is used."""


class _Capture(io.TextIOBase):
    """A write-only text stream that remembers what was written."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self.length = 0

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError(f"write() argument must be str, not {type(text).__name__}")
        if self.length + len(text) > MAX_OUTPUT_CHARS:
            room = max(0, MAX_OUTPUT_CHARS - self.length)
            self._parts.append(text[:room])
            self.length += room
            raise OutputLimitExceeded(
                f"Output limit reached ({MAX_OUTPUT_CHARS:,} characters). "
                "Is a loop printing forever?"
            )
        self._parts.append(text)
        self.length += len(text)
        return len(text)

    def getvalue(self) -> str:
        return "".join(self._parts)


class _Session:
    """Holds the redirected streams for one program execution."""

    def __init__(self, stdin_text: str) -> None:
        self.out = _Capture()
        self.err = _Capture()
        self.stdin = io.StringIO(stdin_text or "")
        self.events: list[dict] = []

    def input(self, prompt: object = "") -> str:
        self.out.write(str(prompt))
        line = self.stdin.readline()
        if line == "":
            raise EOFError(
                "input() asked for a value, but no input was provided. "
                "Type the values your program needs into the Input box (one per line)."
            )
        value = line[:-1] if line.endswith("\n") else line
        self.events.append({"kind": "input", "at": self.out.length, "value": value})
        return value


def _register_source(filename: str, source: str) -> None:
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)


def _error_info(exc: BaseException) -> dict:
    """Describe an exception using only frames from learner (or test) code."""
    te = traceback.TracebackException(type(exc), exc, exc.__traceback__)
    keep = [f for f in te.stack if f.filename in (LEARNER_FILE, TEST_FILE)]
    te.stack = traceback.StackSummary.from_list(keep)
    line = keep[-1].lineno if keep else None
    column = None
    if isinstance(exc, SyntaxError):
        if exc.filename in (LEARNER_FILE, TEST_FILE):
            line = exc.lineno
            column = exc.offset
        message = exc.msg
    else:
        message = str(exc)
    if isinstance(exc, KeyError) and exc.args:
        message = repr(exc.args[0])
    formatted = "".join(te.format())
    return {
        "type": type(exc).__name__,
        "message": message,
        "line": line,
        "column": column,
        "traceback": formatted.rstrip("\n"),
    }


def _execute(code: str, stdin: str, tracer=None) -> tuple[dict, dict]:
    """Run ``code`` as ``__main__``; return (result, namespace)."""
    session = _Session(stdin)
    namespace: dict = {"__name__": "__main__", "__builtins__": builtins}
    _register_source(LEARNER_FILE, code)
    saved = (sys.stdout, sys.stderr, sys.stdin, builtins.input)
    error = None
    exit_code = None
    started = time.perf_counter()
    try:
        sys.stdout, sys.stderr, sys.stdin = session.out, session.err, session.stdin
        builtins.input = session.input
        # dont_inherit: this module's `from __future__ import annotations` must not
        # leak into learner code, which should behave like a normal Python 3.14 script.
        compiled = compile(code, LEARNER_FILE, "exec", dont_inherit=True)
        if tracer is not None:
            tracer.session = session
            sys.settrace(tracer)
        exec(compiled, namespace)
    except TraceLimitReached:
        pass
    except SystemExit as exc:
        exit_code = exc.code
        if exc.code not in (None, 0):
            error = _error_info(exc)
    except BaseException as exc:  # noqa: BLE001 - we report every failure to the learner
        error = _error_info(exc)
    finally:
        sys.settrace(None)
        sys.stdout, sys.stderr, sys.stdin, builtins.input = saved
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    result = {
        "ok": error is None,
        "stdout": session.out.getvalue(),
        "stderr": session.err.getvalue(),
        "events": session.events,
        "error": error,
        "exitCode": exit_code if isinstance(exit_code, (int, type(None))) else str(exit_code),
        "durationMs": duration_ms,
    }
    return result, namespace


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------


def run(code: str, stdin: str = "") -> dict:
    result, _ = _execute(code, stdin)
    return result


def run_json(code: str, stdin: str = "") -> str:
    return json.dumps(run(code, stdin))


# --------------------------------------------------------------------------
# Tracing: record every executed line with the stack and the objects it uses
# --------------------------------------------------------------------------

_PRIMITIVES = (int, float, complex, bool, str, bytes, type(None))


def _short_repr(value: object) -> str:
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001 - user-defined __repr__ may fail
        text = f"<{type(value).__name__} object>"
    if len(text) > MAX_REPR_CHARS:
        text = text[: MAX_REPR_CHARS - 1] + "…"
    return text


_GENERATOR_FLAGS = inspect.CO_GENERATOR | inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR
_YIELD_OPCODES = {dis.opmap[name] for name in ("YIELD_VALUE",) if name in dis.opmap}


def _is_suspended_at_yield(frame) -> bool:
    """True when a generator/coroutine frame is pausing at a yield rather than finishing."""
    code = frame.f_code
    if not code.co_flags & _GENERATOR_FLAGS:
        return False
    try:
        return code.co_code[frame.f_lasti] in _YIELD_OPCODES
    except (IndexError, TypeError):
        return False


class _Tracer:
    def __init__(self, max_steps: int) -> None:
        self.max_steps = max_steps
        self.steps: list[dict] = []
        self.labels: dict[int, int] = {}
        # Keep every object we label alive so CPython cannot reuse its id()
        # for a different object later in the same run.
        self._keepalive: list[object] = []
        self.session: _Session | None = None
        self.truncated = False

    # sys.settrace entry point: called for every new frame.
    def __call__(self, frame, event, arg):
        if frame.f_code.co_filename != LEARNER_FILE:
            return None
        if event == "call" and frame.f_code.co_name != "<module>":
            self._record(frame, "call", arg)
        return self._local

    def _local(self, frame, event, arg):
        if event in ("line", "return", "exception"):
            self._record(frame, event, arg)
        return self._local

    def _label(self, obj: object) -> int:
        key = id(obj)
        label = self.labels.get(key)
        if label is None:
            label = len(self.labels) + 1
            self.labels[key] = label
            self._keepalive.append(obj)
        return label

    def _encode(self, obj: object, heap: dict, depth: int) -> int:
        label = self._label(obj)
        if label in heap:
            return label
        entry: dict = {"type": type(obj).__name__}
        heap[label] = entry
        if isinstance(obj, _PRIMITIVES):
            entry["kind"] = "primitive"
            entry["repr"] = _short_repr(obj)
            return label
        entry["repr"] = _short_repr(obj)
        if depth >= MAX_HEAP_DEPTH:
            entry["kind"] = "other"
            return label
        if isinstance(obj, (list, tuple)):
            entry["kind"] = "list" if isinstance(obj, list) else "tuple"
            entry["items"] = [self._encode(v, heap, depth + 1) for v in obj[:MAX_CONTAINER_ITEMS]]
            entry["size"] = len(obj)
        elif isinstance(obj, (set, frozenset)):
            entry["kind"] = "set"
            items = list(obj)[:MAX_CONTAINER_ITEMS]
            entry["items"] = [self._encode(v, heap, depth + 1) for v in items]
            entry["size"] = len(obj)
        elif isinstance(obj, dict):
            entry["kind"] = "dict"
            pairs = list(obj.items())[:MAX_CONTAINER_ITEMS]
            entry["entries"] = [
                [self._encode(k, heap, depth + 1), self._encode(v, heap, depth + 1)] for k, v in pairs
            ]
            entry["size"] = len(obj)
        elif isinstance(obj, (types.FunctionType, types.BuiltinFunctionType, types.MethodType)):
            entry["kind"] = "function"
            entry["repr"] = f"function {getattr(obj, '__qualname__', '?')}"
        elif isinstance(obj, type):
            entry["kind"] = "class"
            entry["repr"] = f"class {obj.__qualname__}"
        elif isinstance(obj, types.ModuleType):
            entry["kind"] = "module"
            entry["repr"] = f"module {obj.__name__}"
        elif hasattr(obj, "__dict__") and isinstance(getattr(obj, "__dict__", None), dict):
            entry["kind"] = "instance"
            attrs = list(vars(obj).items())[:MAX_CONTAINER_ITEMS]
            entry["attrs"] = [[name, self._encode(v, heap, depth + 1)] for name, v in attrs]
        else:
            entry["kind"] = "other"
        return label

    def _frame_vars(self, frame) -> list[tuple[str, object]]:
        if frame.f_code.co_name == "<module>":
            source = frame.f_globals
        else:
            source = frame.f_locals
        return [
            (name, value)
            for name, value in list(source.items())
            if not (name.startswith("__") and name.endswith("__"))
        ]

    def _record(self, frame, event: str, arg) -> None:
        if len(self.steps) >= self.max_steps:
            self.truncated = True
            raise TraceLimitReached()
        chain = []
        f = frame
        while f is not None and f.f_code.co_filename == LEARNER_FILE:
            chain.append(f)
            f = f.f_back
        chain.reverse()
        heap: dict = {}
        stack = []
        for fr in chain:
            variables = [
                {"name": name, "ref": self._encode(value, heap, 0)}
                for name, value in self._frame_vars(fr)
            ]
            stack.append(
                {
                    "name": "Global frame" if fr.f_code.co_name == "<module>" else fr.f_code.co_name,
                    "line": fr.f_lineno,
                    "vars": variables,
                }
            )
        step: dict = {
            "event": event,
            "line": frame.f_lineno,
            "stack": stack,
            "heap": {str(k): v for k, v in heap.items()},
            "stdoutLength": self.session.out.length if self.session else 0,
        }
        if event == "return":
            # sys.settrace reports a generator's `yield` as a "return" event, but the
            # frame is suspended, not finished. Tell the two apart by the instruction
            # the frame stopped on.
            if _is_suspended_at_yield(frame):
                step["event"] = "yield"
            step["returnRef"] = self._encode(arg, heap, 0)
            step["heap"] = {str(k): v for k, v in heap.items()}
        elif event == "exception" and isinstance(arg, tuple) and len(arg) >= 2:
            step["exception"] = {"type": arg[0].__name__, "message": str(arg[1])}
        self.steps.append(step)


def trace(code: str, stdin: str = "", max_steps: int = DEFAULT_MAX_STEPS) -> dict:
    max_steps = max(1, min(int(max_steps), HARD_MAX_STEPS))
    tracer = _Tracer(max_steps)
    result, _ = _execute(code, stdin, tracer=tracer)
    result["steps"] = tracer.steps
    result["truncated"] = tracer.truncated
    return result


def trace_json(code: str, stdin: str = "", max_steps: int = DEFAULT_MAX_STEPS) -> str:
    return json.dumps(trace(code, stdin, max_steps))


# --------------------------------------------------------------------------
# Grading: run the learner program, then run each exercise test against it
# --------------------------------------------------------------------------


def _node_names(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {type(node).__name__ for node in ast.walk(tree)}


def _called_names(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _make_helpers(code: str, stdin: str, result: dict, namespace: dict) -> dict:
    nodes = _node_names(code)
    called = _called_names(code)

    def output() -> str:
        """Everything the learner's program printed."""
        return result["stdout"]

    def output_lines() -> list[str]:
        """Printed lines with trailing spaces removed (blank lines kept)."""
        return [line.rstrip() for line in result["stdout"].rstrip("\n").split("\n")] if result["stdout"] else []

    def uses(*node_types: str) -> bool:
        """True if the code contains any of the given syntax nodes, e.g. uses('For')."""
        return any(n in nodes for n in node_types)

    def calls(name: str) -> bool:
        """True if the code calls a function or method with this name."""
        return name in called

    def defined(name: str) -> bool:
        return name in namespace

    def run_program(stdin_text: str = "") -> str:
        """Run the learner's whole program again with different input; return its output."""
        again, _ = _execute(code, stdin_text)
        if again["error"]:
            err = again["error"]
            raise RuntimeError(
                f"With input {stdin_text!r} your program raised {err['type']}: {err['message']}"
            )
        return again["stdout"]

    return {
        "output": output,
        "output_lines": output_lines,
        "uses": uses,
        "calls": calls,
        "defined": defined,
        "run_program": run_program,
        "source": code,
    }


def _run_test(test: dict, namespace: dict, helpers: dict) -> dict:
    test_code = test.get("code", "")
    _register_source(TEST_FILE, test_code)
    scope = dict(namespace)
    scope.update(helpers)
    capture = _Capture()
    saved = sys.stdout
    passed = False
    message = ""
    try:
        sys.stdout = capture
        exec(compile(test_code, TEST_FILE, "exec", dont_inherit=True), scope)
        passed = True
    except AssertionError as exc:
        if exc.args:
            message = str(exc.args[0])
        else:
            tb = traceback.extract_tb(exc.__traceback__)
            lines = [f for f in tb if f.filename == TEST_FILE]
            line = lines[-1].line if lines else ""
            message = f"This check failed: {line}" if line else "A check failed."
    except BaseException as exc:  # noqa: BLE001
        info = _error_info(exc)
        message = f"{info['type']}: {info['message']}"
    finally:
        sys.stdout = saved
    return {
        "name": test.get("name", "check"),
        "passed": passed,
        "message": message,
        "printed": capture.getvalue()[:2000],
    }


def grade(code: str, tests: list[dict], stdin: str = "") -> dict:
    result, namespace = _execute(code, stdin)
    helpers = _make_helpers(code, stdin, result, namespace)
    syntax_failed = bool(result["error"]) and result["error"]["type"] in (
        "SyntaxError",
        "IndentationError",
        "TabError",
    )
    outcomes = []
    for test in tests:
        if syntax_failed:
            outcomes.append(
                {
                    "name": test.get("name", "check"),
                    "passed": False,
                    "message": "Not checked: fix the syntax error first.",
                    "printed": "",
                }
            )
        else:
            outcomes.append(_run_test(test, namespace, helpers))
    return {
        "run": result,
        "tests": outcomes,
        "passed": bool(outcomes) and all(t["passed"] for t in outcomes) and result["error"] is None,
    }


def grade_json(code: str, tests_json: str, stdin: str = "") -> str:
    return json.dumps(grade(code, json.loads(tests_json), stdin))
