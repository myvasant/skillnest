"""Behaviour tests for the containerised service, grouped by milestone.

Milestones 1-2 exercise the FastAPI app. Milestones 3-4 read the Dockerfile, .dockerignore and
compose.yaml as text and check their structure: they cannot prove the image builds (that needs Docker,
see the README's manual milestone 5), but they catch the mistakes that matter most in production.

Run one milestone with:  python -m pytest -k Milestone3
"""

import json
import re
from pathlib import Path

import container_service as svc
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers for the static checks (milestones 3-4)
# ---------------------------------------------------------------------------

SECRET_NAME = re.compile(r"(?i)(secret|passw(or)?d|token|api_?key|private_?key|credential)")


def dockerfile_instructions(text: str) -> list[tuple[str, str]]:
    """Parse a Dockerfile into (INSTRUCTION, arguments) pairs, joining ``\\`` continuation lines."""
    instructions: list[tuple[str, str]] = []
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            current += line[:-1].strip() + " "
            continue
        current += line
        keyword, _, args = current.partition(" ")
        instructions.append((keyword.upper(), args.strip()))
        current = ""
    if current.strip():
        keyword, _, args = current.strip().partition(" ")
        instructions.append((keyword.upper(), args.strip()))
    return instructions


def final_stage(instructions: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The instructions after the last FROM (what the shipped image is made of)."""
    last_from = max(i for i, (kw, _) in enumerate(instructions) if kw == "FROM")
    return instructions[last_from:]


def env_names(args: str) -> list[str]:
    """Variable names declared by one ENV or ARG instruction (``A=1 B=2`` or legacy ``A 1``)."""
    if "=" not in args.split()[0]:
        return [args.split()[0]]
    return re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=", args)


@pytest.fixture
def dockerfile(target_dir: Path) -> list[tuple[str, str]]:
    path = target_dir / "Dockerfile"
    assert path.is_file(), f"create {path}"
    instructions = dockerfile_instructions(path.read_text(encoding="utf-8"))
    assert any(kw == "FROM" for kw, _ in instructions), "a Dockerfile needs at least one FROM"
    return instructions


@pytest.fixture
def compose_text(target_dir: Path) -> str:
    path = target_dir / "compose.yaml"
    assert path.is_file(), f"create {path}"
    # Ignore comments so that commented-out examples do not satisfy (or fail) the checks.
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("#")
    )


@pytest.fixture
def settings(tmp_path: Path) -> svc.ServiceSettings:
    return svc.ServiceSettings(service_name="test-service", version="1.2.3", data_dir=tmp_path)


@pytest.fixture
def client(settings: svc.ServiceSettings) -> TestClient:
    return TestClient(svc.create_app(settings))


# ---------------------------------------------------------------------------
# Milestone 1: settings and service endpoints
# ---------------------------------------------------------------------------


class TestMilestone1Service:
    def test_defaults_when_nothing_is_set(self) -> None:
        settings = svc.ServiceSettings.from_env({})
        assert settings == svc.ServiceSettings(), "an empty environment should give the documented defaults"
        assert settings.service_name == "container-service" and settings.data_dir == Path("data")

    def test_reads_environment_variables(self) -> None:
        env = {"SERVICE_NAME": "billing-api", "SERVICE_VERSION": "2.0.1", "DATA_DIR": "/srv/data"}
        settings = svc.ServiceSettings.from_env(env)
        assert (settings.service_name, settings.version, settings.data_dir) == (
            "billing-api",
            "2.0.1",
            Path("/srv/data"),
        )

    def test_reads_os_environ_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SERVICE_VERSION", "9.9.9")
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        assert svc.ServiceSettings.from_env().version == "9.9.9", (
            "from_env() with no argument reads os.environ"
        )

    @pytest.mark.parametrize(
        ("variable", "value"),
        [("SERVICE_NAME", "Billing API"), ("SERVICE_NAME", ""), ("SERVICE_VERSION", "1 0")],
    )
    def test_invalid_values_fail_fast_naming_the_variable(self, variable: str, value: str) -> None:
        with pytest.raises(ValueError, match=variable):
            svc.ServiceSettings.from_env({variable: value})

    def test_root_reports_name_and_version(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"service": "test-service", "version": "1.2.3"}

    def test_visits_are_counted_and_persisted_in_data_dir(self, settings: svc.ServiceSettings) -> None:
        client = TestClient(svc.create_app(settings))
        assert client.get("/api/visits").json() == {"visits": 0}
        assert client.post("/api/visits").json() == {"visits": 1}
        assert client.post("/api/visits").json() == {"visits": 2}
        restarted = TestClient(svc.create_app(settings))
        assert restarted.get("/api/visits").json() == {"visits": 2}, (
            "the count must survive a restart (it lives in DATA_DIR)"
        )
        assert (settings.data_dir / "visits.txt").read_text(encoding="utf-8").strip() == "2"


# ---------------------------------------------------------------------------
# Milestone 2: liveness and readiness probes
# ---------------------------------------------------------------------------


class TestMilestone2Probes:
    def test_liveness_is_cheap_and_ignores_dependencies(self, settings: svc.ServiceSettings) -> None:
        calls: list[str] = []

        def broken() -> bool:
            calls.append("called")
            return False

        client = TestClient(svc.create_app(settings, checks={"database": broken}))
        response = client.get("/healthz")
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        assert calls == [], (
            "liveness must not run readiness checks (a DB outage should not restart every pod)"
        )

    def test_ready_when_all_checks_pass(self, settings: svc.ServiceSettings) -> None:
        client = TestClient(
            svc.create_app(settings, checks={"database": lambda: True, "cache": lambda: True})
        )
        response = client.get("/readyz")
        assert response.status_code == 200, f"all checks pass -> 200, got {response.status_code}"
        assert response.json()["status"] == "ready"
        assert response.json()["checks"] == {"database": "ok", "cache": "ok"}

    def test_not_ready_names_the_failing_checks(self, settings: svc.ServiceSettings) -> None:
        client = TestClient(
            svc.create_app(settings, checks={"database": lambda: False, "cache": lambda: True})
        )
        response = client.get("/readyz")
        assert response.status_code == 503, "a failing check -> 503 Service Unavailable"
        assert response.json()["failing"] == ["database"]

    def test_a_crashing_check_is_not_ready_and_does_not_leak_details(
        self, settings: svc.ServiceSettings
    ) -> None:
        def explode() -> bool:
            raise ConnectionError("db.internal:5432 refused, user=admin")

        client = TestClient(svc.create_app(settings, checks={"database": explode}))
        response = client.get("/readyz")
        assert response.status_code == 503, "an exception inside a check means 'not ready', not a 500"
        assert "db.internal" not in response.text, (
            "do not expose internal error messages on a public endpoint"
        )

    def test_default_check_uses_the_data_dir(self, tmp_path: Path) -> None:
        missing = svc.ServiceSettings(data_dir=tmp_path / "does-not-exist")
        response = TestClient(svc.create_app(missing)).get("/readyz")
        assert response.status_code == 503 and response.json()["failing"] == ["data_dir"]
        present = svc.ServiceSettings(data_dir=tmp_path)
        assert TestClient(svc.create_app(present)).get("/readyz").status_code == 200

    def test_data_dir_is_writable(self, tmp_path: Path) -> None:
        assert svc.data_dir_is_writable(tmp_path) is True
        assert svc.data_dir_is_writable(tmp_path / "missing") is False
        a_file = tmp_path / "file.txt"
        a_file.write_text("x", encoding="utf-8")
        assert svc.data_dir_is_writable(a_file) is False, "a file is not a data directory"


# ---------------------------------------------------------------------------
# Milestone 3: a production-grade Dockerfile (static checks)
# ---------------------------------------------------------------------------


class TestMilestone3Dockerfile:
    def test_multi_stage_build(self, dockerfile: list[tuple[str, str]]) -> None:
        froms = [args for kw, args in dockerfile if kw == "FROM"]
        assert len(froms) >= 2, "use a builder stage and a runtime stage (two FROM lines)"
        assert any(re.search(r"(?i)\s+as\s+\w+", args) for args in froms), (
            "name the build stage: FROM ... AS builder"
        )
        assert any(kw == "COPY" and "--from=" in args for kw, args in dockerfile), (
            "COPY --from=builder the result"
        )

    def test_base_images_are_pinned(self, dockerfile: list[tuple[str, str]]) -> None:
        stages: set[str] = set()
        for kw, args in dockerfile:
            if kw != "FROM":
                continue
            parts = args.split()
            image = next(p for p in parts if not p.startswith("--"))
            if image.lower() not in stages:
                assert "@sha256:" in image or ":" in image, (
                    f"pin a tag for {image!r} (e.g. python:3.13-slim-bookworm)"
                )
                tag = image.split("@")[0].rsplit(":", 1)[-1] if ":" in image.split("@")[0] else ""
                assert tag != "latest", f"{image!r}: 'latest' changes under you; pin an explicit version"
            if len(parts) >= 3 and parts[-2].lower() == "as":
                stages.add(parts[-1].lower())

    def test_runs_as_a_non_root_user(self, dockerfile: list[tuple[str, str]]) -> None:
        users = [args for kw, args in final_stage(dockerfile) if kw == "USER"]
        assert users, "add a USER instruction in the final stage; containers run as root by default"
        assert users[-1].split(":")[0] not in {"root", "0"}, f"USER {users[-1]} is still root"

    def test_cmd_is_exec_form_running_the_factory(self, dockerfile: list[tuple[str, str]]) -> None:
        commands = [args for kw, args in final_stage(dockerfile) if kw in {"CMD", "ENTRYPOINT"}]
        assert commands, "add a CMD"
        assert commands[-1].startswith("["), (
            'use the exec form CMD ["..."] so the server is PID 1 and gets SIGTERM'
        )
        argv = json.loads(commands[-1])
        assert "container_service:create_app" in argv and "--factory" in argv, (
            f"start the app factory, got {argv}"
        )
        all_interfaces = "0.0.0.0"  # noqa: S104 - checking the container binds to every interface
        assert all_interfaces in argv, "inside a container, bind to 0.0.0.0 or nothing outside can reach it"

    def test_healthcheck_probes_liveness(self, dockerfile: list[tuple[str, str]]) -> None:
        checks = [args for kw, args in final_stage(dockerfile) if kw == "HEALTHCHECK"]
        assert checks and "/healthz" in checks[-1], "add a HEALTHCHECK that calls /healthz"

    def test_python_runtime_settings(self, dockerfile: list[tuple[str, str]]) -> None:
        names = {n for kw, args in final_stage(dockerfile) if kw == "ENV" for n in env_names(args)}
        missing = {"PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE"} - names
        assert not missing, f"set {sorted(missing)} in the runtime stage (unbuffered logs, no .pyc writes)"

    def test_no_secrets_baked_into_the_image(self, dockerfile: list[tuple[str, str]]) -> None:
        for kw, args in dockerfile:
            if kw in {"ENV", "ARG"}:
                for name in env_names(args):
                    assert not SECRET_NAME.search(name), (
                        f"{kw} {name}: secrets in ENV/ARG end up in the image history"
                    )
            if kw in {"COPY", "ADD"}:
                assert ".env" not in args.split(), f"{kw} {args}: never copy .env files into an image"

    def test_dependency_layer_is_cached_and_lean(self, dockerfile: list[tuple[str, str]]) -> None:
        copies = [args for kw, args in dockerfile if kw == "COPY"]
        req = next((i for i, a in enumerate(copies) if "requirements-runtime.txt" in a), None)
        code = next(
            (i for i, a in enumerate(copies) if "container_service.py" in a or a.split()[0] == "."), None
        )
        assert req is not None, "COPY requirements-runtime.txt and pip install it"
        assert code is not None and req < code, "copy the requirements (and install) before copying the code"
        installs = [args for kw, args in dockerfile if kw == "RUN" and "pip install" in args]
        no_cache_env = any(kw == "ENV" and "PIP_NO_CACHE_DIR" in args for kw, args in dockerfile)
        assert installs and (no_cache_env or all("--no-cache-dir" in a for a in installs)), (
            "pip install --no-cache-dir"
        )

    def test_runtime_requirements_are_pinned_and_lean(self, target_dir: Path) -> None:
        path = target_dir / "requirements-runtime.txt"
        assert path.is_file(), f"create {path}"
        lines = [ln.split("#")[0].strip() for ln in path.read_text(encoding="utf-8").splitlines()]
        packages = [ln for ln in lines if ln]
        assert any(p.lower().startswith("fastapi") for p in packages) and any(
            "uvicorn" in p.lower() for p in packages
        )
        assert all("==" in p for p in packages), (
            "pin exact versions (==) so every build installs the same thing"
        )
        dev_tools = [p for p in packages if re.match(r"(?i)(pytest|httpx|ruff|mypy)\b", p)]
        assert not dev_tools, f"test/dev tools do not belong in the image: {dev_tools}"


# ---------------------------------------------------------------------------
# Milestone 4: build context and compose file (static checks)
# ---------------------------------------------------------------------------


class TestMilestone4BuildContextAndCompose:
    @pytest.mark.parametrize("pattern", [".env", ".git", ".venv", "__pycache__", "tests"])
    def test_dockerignore_excludes(self, target_dir: Path, pattern: str) -> None:
        path = target_dir / ".dockerignore"
        assert path.is_file(), f"create {path}"
        entries = {
            ln.strip().rstrip("/").removeprefix("**/") for ln in path.read_text(encoding="utf-8").splitlines()
        }
        assert pattern in entries, f"add {pattern!r} to .dockerignore"

    def test_compose_defines_services_and_volumes(self, compose_text: str) -> None:
        top_level = set(re.findall(r"(?m)^([A-Za-z][\w-]*):", compose_text))
        assert "services" in top_level, "compose.yaml needs a top-level 'services:' key"
        assert "volumes" in top_level, "declare the named volume under a top-level 'volumes:' key"

    def test_compose_builds_and_publishes_port_8000_on_loopback(self, compose_text: str) -> None:
        assert re.search(r"(?m)^\s+build:", compose_text), "build the image from this directory (build: .)"
        assert re.search(r"""(?m)^\s+-\s*["']?127\.0\.0\.1:\d+:8000["']?\s*$""", compose_text), (
            'publish the port on loopback only, e.g. - "127.0.0.1:8000:8000"'
        )

    def test_compose_mounts_a_named_volume_for_data(self, compose_text: str) -> None:
        assert re.search(r"(?m)^\s+-\s*[\w-]+:/app/data\s*$", compose_text), (
            "mount a named volume at /app/data"
        )

    def test_compose_restart_and_hardening(self, compose_text: str) -> None:
        assert re.search(r"(?m)^\s+restart:\s*(unless-stopped|always|on-failure)", compose_text), (
            "set a restart policy"
        )
        assert re.search(r"(?m)^\s+read_only:\s*true", compose_text), (
            "make the root filesystem read_only: true"
        )
        assert re.search(r"(?m)^\s+-\s*ALL\s*$", compose_text), (
            "drop all Linux capabilities (cap_drop: [ALL])"
        )
        assert "no-new-privileges:true" in compose_text.replace(" ", ""), (
            "add security_opt: no-new-privileges:true"
        )
        assert not re.search(r"(?m)^\s+privileged:\s*true", compose_text), "never run the service privileged"

    def test_compose_contains_no_secrets_or_latest_tags(self, compose_text: str) -> None:
        assert ":latest" not in compose_text, "pin image tags in compose.yaml too"
        keys = re.findall(r"(?m)^\s+([A-Za-z_][\w-]*)\s*[:=]", compose_text)
        leaked = [k for k in keys if SECRET_NAME.search(k)]
        assert not leaked, f"do not put secrets in compose.yaml ({leaked}); use env_file or Docker secrets"
