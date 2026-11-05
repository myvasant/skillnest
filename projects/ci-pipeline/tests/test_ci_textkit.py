"""Tests for the ci-pipeline project: the library (milestone 1) and the workflow (2-4).

The workflow checks read the YAML with ``parse_yaml_subset`` below - a deliberately
tiny reader for the subset of YAML that GitHub workflows use - so the kit does not
depend on PyYAML. It is a structure check, not a full YAML implementation.
"""

import re
import textwrap
from pathlib import Path
from typing import Any

import pytest
from ci_textkit import KeyValueError, parse_key_values, slugify, word_frequencies

# ---------------------------------------------------------------------------
# Helper: a minimal reader for the YAML subset used in workflow files
# (block mappings, block sequences, [flow, lists], quoted scalars, "|" text
# blocks and comments). Anchors, flow mappings and multi-document files are
# not supported - and not needed here.
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_BLOCK_INDICATORS = {"|", "|-", "|+", ">", ">-", ">+"}


def _strip_comment(line: str) -> str:
    """Remove a trailing ``# comment`` that is outside quotes."""
    quote = ""
    for index, char in enumerate(line):
        previous = line[index - 1] if index else " "
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"" and previous in " [,:":
            quote = char
        elif char == "#" and previous in " \t":
            return line[:index].rstrip()
    return line.rstrip()


def _is_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _split_items(inner: str) -> list[str]:
    """Split the inside of a flow list on commas that are outside quotes."""
    parts, current, quote = [], "", ""
    for char in inner:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == ",":
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)
    return [part.strip() for part in parts if part.strip()]


def _scalar(text: str) -> Any:
    """Convert a scalar the way YAML would (bools, null, numbers, quoted strings)."""
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(part) for part in _split_items(text[1:-1])]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if _NUMBER.fullmatch(text):
        return float(text) if "." in text else int(text)
    return text


def _split_key(content: str, line_number: int) -> tuple[str, str]:
    index = content.find(": ")
    if index == -1:
        if not content.endswith(":"):
            raise ValueError(f"line {line_number}: expected 'key: value', got {content!r}")
        key, rest = content[:-1], ""
    else:
        key, rest = content[:index], content[index + 2 :].strip()
    return str(_scalar(key.strip())), rest


class _MiniYaml:
    """Recursive-descent reader over the lines of a document."""

    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()
        self.i = 0

    def parse(self) -> Any:
        value = self._block(0)
        if self._peek() is not None:
            raise ValueError(f"line {self.i + 1}: unexpected indentation or content")
        return value

    def _peek(self) -> tuple[int, str] | None:
        """The next meaningful line as (indent, content); skips blanks and comments."""
        while self.i < len(self.lines):
            content = _strip_comment(self.lines[self.i])
            if content.strip() and content.strip() != "---":
                return len(content) - len(content.lstrip(" ")), content.strip()
            self.i += 1
        return None

    def _block(self, min_indent: int) -> Any:
        first = self._peek()
        if first is None or first[0] < min_indent:
            return None
        if _is_item(first[1]):
            return self._sequence(first[0])
        return self._mapping(first[0])

    def _mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while (line := self._peek()) and line[0] == indent and not _is_item(line[1]):
            self.i += 1
            key, rest = _split_key(line[1], self.i)
            result[key] = self._value(rest, indent)
        return result

    def _value(self, rest: str, indent: int) -> Any:
        if rest in _BLOCK_INDICATORS:
            return self._text_block(indent, folded=rest.startswith(">"))
        if rest:
            return _scalar(rest)
        child = self._peek()
        if child and (child[0] > indent or (child[0] == indent and _is_item(child[1]))):
            return self._block(child[0])
        return None

    def _sequence(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while (line := self._peek()) and line[0] == indent and _is_item(line[1]):
            rest = line[1][1:].lstrip()
            if rest and not rest.startswith(("'", '"', "[")) and (": " in rest or rest.endswith(":")):
                # "- key: value" starts a mapping whose keys line up with "key".
                item_indent = indent + len(line[1]) - len(rest)
                self.lines[self.i] = " " * item_indent + rest
                items.append(self._mapping(item_indent))
                continue
            self.i += 1
            items.append(_scalar(rest) if rest else self._block(indent + 1))
        return items

    def _text_block(self, indent: int, *, folded: bool) -> str:
        collected: list[str] = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= indent:
                break
            collected.append(raw)
            self.i += 1
        while collected and not collected[-1].strip():
            collected.pop()
        width = min((len(r) - len(r.lstrip(" ")) for r in collected if r.strip()), default=0)
        return (" " if folded else "\n").join(r[width:] for r in collected)


def parse_yaml_subset(text: str) -> Any:
    """Parse ``text`` (the small YAML subset described above) into Python objects."""
    return _MiniYaml(text).parse()


# ---------------------------------------------------------------------------
# Helpers for reading a parsed workflow
# ---------------------------------------------------------------------------


@pytest.fixture
def workflow_text(workflow_path: Path) -> str:
    assert workflow_path.exists(), f"Create the workflow file at {workflow_path}."
    return workflow_path.read_text(encoding="utf-8")


@pytest.fixture
def workflow(workflow_text: str) -> dict[str, Any]:
    doc = parse_yaml_subset(workflow_text)
    assert isinstance(doc, dict), "The workflow should be a YAML mapping (name:, on:, jobs: ...)."
    return doc


def _jobs(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and jobs, "The workflow needs a `jobs:` mapping with at least one job."
    return jobs


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps") or []
    assert isinstance(steps, list), "`steps:` must be a list of steps (each starting with '- ')."
    return [step for step in steps if isinstance(step, dict)]


def _all_steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for job in _jobs(doc).values() for step in _steps(job)]


def _runs(doc: dict[str, Any]) -> list[str]:
    return [str(step["run"]) for step in _all_steps(doc) if "run" in step]


def _triggers(doc: dict[str, Any]) -> set[str]:
    # Note: PyYAML would read an unquoted `on` key as the boolean True; GitHub does not.
    on = doc.get("on")
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(event) for event in on}
    if isinstance(on, dict):
        return set(on)
    return set()


def _matrix_job(doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for job_id, job in _jobs(doc).items():
        matrix = (job.get("strategy") or {}).get("matrix") or {}
        if isinstance(matrix, dict) and "python-version" in matrix:
            return job_id, job
    pytest.fail("No job has `strategy: matrix: python-version: [...]`. Add a Python version matrix.")


def _step_index(steps: list[dict[str, Any]], needle: str) -> int | None:
    for index, step in enumerate(steps):
        if needle in str(step.get("run", "")):
            return index
    return None


# ---------------------------------------------------------------------------
# The helper itself (so you can trust the workflow checks)
# ---------------------------------------------------------------------------


class TestHelperMiniYaml:
    def test_reads_nested_mappings_lists_and_text_blocks(self) -> None:
        doc = parse_yaml_subset(
            textwrap.dedent(
                """\
                name: demo  # a comment
                on:
                  push:
                    branches: [main, "release"]
                jobs:
                  build:
                    strategy:
                      matrix:
                        v: ["3.11", 3.12]
                    steps:
                      - uses: actions/checkout@v5
                      - name: Run
                        run: |
                          echo one
                          echo two
                """
            )
        )
        assert doc == {
            "name": "demo",
            "on": {"push": {"branches": ["main", "release"]}},
            "jobs": {
                "build": {
                    "strategy": {"matrix": {"v": ["3.11", 3.12]}},
                    "steps": [
                        {"uses": "actions/checkout@v5"},
                        {"name": "Run", "run": "echo one\necho two"},
                    ],
                }
            },
        }

    def test_rejects_badly_indented_documents(self) -> None:
        with pytest.raises(ValueError):
            parse_yaml_subset("jobs:\n    a: 1\n  b: 2\n")


# ---------------------------------------------------------------------------
# Milestone 1 - the library under test
# ---------------------------------------------------------------------------


class TestMilestone1Library:
    def test_slugify_basic(self) -> None:
        assert slugify("Hello, World!") == "hello-world"

    def test_slugify_strips_accents_and_separators(self) -> None:
        assert slugify("Crème Brûlée") == "creme-brulee", "Use NFKD normalisation, then drop non-ASCII."
        assert slugify("  --Already--slugged__ ") == "already-slugged"

    def test_slugify_shortens_at_a_word_boundary(self) -> None:
        title = "Continuous integration for tiny libraries"
        assert slugify(title, max_length=25) == "continuous-integration", (
            "A slug cut in the middle of a word should fall back to the last whole word."
        )
        assert slugify(title, max_length=22) == "continuous-integration"
        assert slugify("Supercalifragilistic", max_length=5) == "super", "One long word is cut hard."

    def test_slugify_rejects_bad_input(self) -> None:
        with pytest.raises(ValueError):
            slugify("!!! ???")
        with pytest.raises(ValueError):
            slugify("fine", max_length=0)

    def test_word_frequencies_ranks_by_count_then_alphabetically(self) -> None:
        text = "The cat and the hat. THE end"
        assert word_frequencies(text) == [("the", 3), ("and", 1), ("cat", 1), ("end", 1), ("hat", 1)]
        assert word_frequencies(text, top=2) == [("the", 3), ("and", 1)]

    def test_word_frequencies_keeps_apostrophes_inside_words(self) -> None:
        assert word_frequencies("Don't stop, don't!") == [("don't", 2), ("stop", 1)]
        assert word_frequencies("") == []

    def test_word_frequencies_rejects_non_positive_top(self) -> None:
        with pytest.raises(ValueError):
            word_frequencies("a b", top=0)

    def test_parse_key_values(self) -> None:
        text = textwrap.dedent(
            """\
            # database settings
            DB_HOST = localhost

            DB_NAME="notes app"
            DSN=postgres://u@h/db?sslmode=require
            EMPTY=
            """
        )
        assert parse_key_values(text) == {
            "DB_HOST": "localhost",
            "DB_NAME": "notes app",
            "DSN": "postgres://u@h/db?sslmode=require",
            "EMPTY": "",
        }

    @pytest.mark.parametrize(
        ("text", "line"),
        [("A=1\nnot a pair\n", 2), ("A=1\n\nA=2\n", 3), ("1BAD=x\n", 1), ("=value\n", 1)],
    )
    def test_parse_key_values_reports_the_line_number(self, text: str, line: int) -> None:
        with pytest.raises(KeyValueError) as info:
            parse_key_values(text)
        assert info.value.line_number == line
        assert f"line {line}" in str(info.value)
        assert isinstance(info.value, ValueError), "KeyValueError should subclass ValueError."


# ---------------------------------------------------------------------------
# Milestone 2 - triggers, permissions and concurrency
# ---------------------------------------------------------------------------


class TestMilestone2Triggers:
    def test_workflow_has_a_name(self, workflow: dict[str, Any]) -> None:
        assert isinstance(workflow.get("name"), str) and workflow["name"], "Give the workflow a `name:`."

    def test_runs_on_push_and_pull_request(self, workflow: dict[str, Any]) -> None:
        triggers = _triggers(workflow)
        assert {"push", "pull_request"} <= triggers, (
            f"Run on push and pull_request; found {sorted(triggers)}."
        )

    def test_never_uses_pull_request_target(self, workflow: dict[str, Any]) -> None:
        assert "pull_request_target" not in _triggers(workflow), (
            "pull_request_target runs untrusted PR code with write access - use pull_request."
        )

    def test_permissions_are_read_only(self, workflow: dict[str, Any]) -> None:
        permissions = workflow.get("permissions")
        assert isinstance(permissions, dict), "Add a top-level `permissions:` mapping (contents: read)."
        assert permissions.get("contents") == "read", "The jobs only need `contents: read`."
        writable = {scope for scope, level in permissions.items() if level not in {"read", "none"}}
        assert not writable, f"Do not grant write access in CI: {sorted(writable)}."

    def test_concurrency_cancels_superseded_runs(self, workflow: dict[str, Any]) -> None:
        concurrency = workflow.get("concurrency")
        assert isinstance(concurrency, dict), "Add `concurrency:` with a group and cancel-in-progress."
        assert "github.ref" in str(concurrency.get("group", "")), "Group runs per branch: use github.ref."
        assert concurrency.get("cancel-in-progress") is True, "Set `cancel-in-progress: true`."


# ---------------------------------------------------------------------------
# Milestone 3 - a lint + test job on a matrix of Python versions
# ---------------------------------------------------------------------------


class TestMilestone3MatrixJob:
    def test_has_a_quoted_python_version_matrix(self, workflow: dict[str, Any]) -> None:
        _, job = _matrix_job(workflow)
        strategy = job["strategy"]
        versions = strategy["matrix"]["python-version"]
        assert isinstance(versions, list) and len(versions) >= 3, "Test at least three Python versions."
        unquoted = [v for v in versions if not isinstance(v, str)]
        assert not unquoted, f"Quote the versions {unquoted}: unquoted 3.10 is the number 3.1 in YAML."
        assert "3.11" in versions, "Include the oldest supported version, 3.11."
        assert strategy.get("fail-fast") is False, "Set `fail-fast: false` so every version reports."

    def test_every_job_has_a_runner_and_a_timeout(self, workflow: dict[str, Any]) -> None:
        for job_id, job in _jobs(workflow).items():
            assert job.get("runs-on"), f"Job {job_id!r} needs `runs-on:`."
            timeout = job.get("timeout-minutes")
            assert isinstance(timeout, int) and 1 <= timeout <= 30, (
                f"Job {job_id!r} needs `timeout-minutes:` between 1 and 30 (got {timeout!r})."
            )

    def test_actions_are_pinned(self, workflow: dict[str, Any]) -> None:
        uses = [str(step["uses"]) for step in _all_steps(workflow) if "uses" in step]
        assert any(u.startswith("actions/setup-python@") for u in uses), "Use actions/setup-python."
        for action in uses:
            name, _, ref = action.partition("@")
            assert ref and ref not in {"main", "master", "latest"}, (
                f"Pin {name} to a release tag or commit SHA (got {action!r})."
            )
        for job_id, job in _jobs(workflow).items():
            job_uses = [str(step.get("uses", "")) for step in _steps(job)]
            assert any(u.startswith("actions/checkout@") for u in job_uses), (
                f"Job {job_id!r} must check out the code first (actions/checkout)."
            )

    def test_setup_python_uses_the_matrix_version_and_pip_cache(self, workflow: dict[str, Any]) -> None:
        job_id, job = _matrix_job(workflow)
        setups = [s for s in _steps(job) if str(s.get("uses", "")).startswith("actions/setup-python@")]
        assert setups, f"Job {job_id!r} should set up Python with actions/setup-python."
        options = setups[0].get("with") or {}
        assert re.fullmatch(r"\$\{\{\s*matrix\.python-version\s*\}\}", str(options.get("python-version"))), (
            "Pass `python-version: ${{ matrix.python-version }}` to setup-python."
        )
        assert options.get("cache") == "pip", "Turn on dependency caching with `cache: pip`."

    def test_installs_dev_requirements(self, workflow: dict[str, Any]) -> None:
        assert any("pip install" in run and "-r requirements-dev.txt" in run for run in _runs(workflow)), (
            "Install the tools with `python -m pip install -r requirements-dev.txt`."
        )

    def test_lints_with_ruff(self, workflow: dict[str, Any]) -> None:
        assert any("ruff check" in run for run in _runs(workflow)), "Add a step that runs `ruff check .`."


# ---------------------------------------------------------------------------
# Milestone 4 - quality gates: coverage threshold, ordering, hygiene
# ---------------------------------------------------------------------------


class TestMilestone4QualityGates:
    def test_pytest_runs_with_a_coverage_gate(self, workflow: dict[str, Any]) -> None:
        _, job = _matrix_job(workflow)
        runs = [str(step.get("run", "")) for step in _steps(job)]
        pytest_runs = [run for run in runs if "pytest" in run]
        assert pytest_runs, "The matrix job should run pytest."
        command = pytest_runs[-1]
        assert "--cov=ci_textkit" in command, "Measure coverage of the library: --cov=ci_textkit."
        threshold = re.search(r"--cov-fail-under[= ](\d+)", command)
        assert threshold, "Fail the build when coverage drops: add --cov-fail-under=90."
        assert int(threshold.group(1)) >= 90, f"Use a threshold of at least 90 (got {threshold.group(1)})."

    def test_tests_run_only_after_lint(self, workflow: dict[str, Any]) -> None:
        jobs = _jobs(workflow)
        test_id, test_job = _matrix_job(workflow)
        steps = _steps(test_job)
        lint_index, test_index = _step_index(steps, "ruff check"), _step_index(steps, "pytest")
        if lint_index is not None and test_index is not None:
            assert lint_index < test_index, "Lint before testing so style errors fail fast."
            return
        needs = test_job.get("needs") or []
        needs = [needs] if isinstance(needs, str) else list(needs)
        lint_jobs = [jid for jid, job in jobs.items() if _step_index(_steps(job), "ruff check") is not None]
        assert lint_jobs, "Some job must run `ruff check`."
        assert set(lint_jobs) & set(needs), f"Make job {test_id!r} `needs:` the lint job {lint_jobs[0]!r}."

    def test_run_steps_do_not_interpolate_untrusted_input(self, workflow: dict[str, Any]) -> None:
        for run in _runs(workflow):
            assert "github.event." not in run and "github.head_ref" not in run, (
                "Interpolating PR titles/branch names into `run:` allows script injection; "
                f"pass them through `env:` instead. Offending step: {run!r}"
            )

    def test_needs_no_secrets(self, workflow_text: str) -> None:
        uses_secrets = re.search(r"\$\{\{[^}]*\bsecrets\.", workflow_text)
        assert not uses_secrets, "Lint and tests need no secrets; do not reference any ${{ secrets.* }}."

    def test_dev_requirements_pin_the_tools(self, kit_root: Path) -> None:
        lines = (kit_root / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
        requirements = {re.split(r"[<>=!~ ]", line, maxsplit=1)[0]: line for line in lines if line.strip()}
        requirements = {name: line for name, line in requirements.items() if not name.startswith("#")}
        for tool in ("pytest", "pytest-cov", "ruff"):
            assert tool in requirements, f"requirements-dev.txt should list {tool}."
            assert re.search(r"[<>=~]", requirements[tool]), f"Give {tool} a version range."
