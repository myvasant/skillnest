"""A small FastAPI service made ready for containers.

* Configuration comes from environment variables (12-factor style) with safe defaults.
* ``/healthz`` is a cheap liveness probe: "the process is up and serving HTTP".
* ``/readyz`` is a readiness probe: "my dependencies are usable, send me traffic".
* ``/api/visits`` keeps a counter in ``DATA_DIR`` so you can watch a volume survive container restarts.

Run locally::

    python -m uvicorn --factory container_service:create_app --app-dir solution --reload

In the container the same factory is started by the ``CMD`` in the Dockerfile.
"""

import logging
import os
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ReadinessCheck = Callable[[], bool]
"""Returns True when a dependency is usable. Raising an exception counts as "not ready"."""

SERVICE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")


# ---------------------------------------------------------------------------
# Milestone 1: settings from the environment and the service endpoints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceSettings:
    """Runtime configuration. Every field can be set with an environment variable."""

    service_name: str = "container-service"  # SERVICE_NAME
    version: str = "0.1.0"  # SERVICE_VERSION (the Dockerfile sets it from a build argument)
    data_dir: Path = field(default_factory=lambda: Path("data"))  # DATA_DIR

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ServiceSettings":
        """Build settings from ``environ`` (default: ``os.environ``).

        Raise ``ValueError`` whose message names the bad variable (never a stack of pydantic noise).
        """
        env = os.environ if environ is None else environ
        defaults = cls()
        name = env.get("SERVICE_NAME", defaults.service_name).strip()
        version = env.get("SERVICE_VERSION", defaults.version).strip()
        data_dir = env.get("DATA_DIR", "").strip()
        if not SERVICE_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "SERVICE_NAME must be 1-63 lowercase letters, digits or '-', starting with a letter/digit"
            )
        if not VERSION_PATTERN.fullmatch(version):
            raise ValueError(
                "SERVICE_VERSION must be 1-64 characters of letters, digits, '.', '+', '_' or '-'"
            )
        return cls(
            service_name=name, version=version, data_dir=Path(data_dir) if data_dir else defaults.data_dir
        )


class ServiceInfo(BaseModel):
    """Response of ``GET /``."""

    service: str
    version: str


class VisitCount(BaseModel):
    """Response of the visit counter endpoints."""

    visits: int


class VisitCounter:
    """A counter persisted in ``<data_dir>/visits.txt``. Writes are atomic (write temp file, then rename)."""

    FILENAME = "visits.txt"

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / self.FILENAME
        self._lock = threading.Lock()

    def read(self) -> int:
        """Return the stored count (0 if nothing was stored yet)."""
        try:
            return int(self._path.read_text(encoding="utf-8").strip() or 0)
        except FileNotFoundError:
            return 0

    def increment(self) -> int:
        """Add one visit and return the new count."""
        with self._lock:
            count = self.read() + 1
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(str(count), encoding="utf-8")
            os.replace(tmp, self._path)
            return count


# ---------------------------------------------------------------------------
# Milestone 2: liveness and readiness probes
# ---------------------------------------------------------------------------


def data_dir_is_writable(path: Path) -> bool:
    """Readiness check: ``path`` exists, is a directory, and this process may write to it."""
    return path.is_dir() and os.access(path, os.W_OK)


def run_checks(checks: Mapping[str, ReadinessCheck]) -> dict[str, bool]:
    """Run every readiness check. A check that raises is reported as failing (and logged), not re-raised."""
    results: dict[str, bool] = {}
    for name, check in checks.items():
        try:
            results[name] = bool(check())
        except Exception:
            logger.exception("readiness check %r raised", name)
            results[name] = False
    return results


def default_checks(settings: ServiceSettings) -> dict[str, ReadinessCheck]:
    """The checks used when ``create_app`` is not given any: the data directory must be writable."""
    return {"data_dir": lambda: data_dir_is_writable(settings.data_dir)}


def get_counter(request: Request) -> VisitCounter:
    """Dependency: the app's visit counter."""
    return request.app.state.counter


def create_app(
    settings: ServiceSettings | None = None,
    *,
    checks: Mapping[str, ReadinessCheck] | None = None,
) -> FastAPI:
    """Build the service. With no arguments, settings come from the environment (uvicorn --factory)."""
    settings = settings if settings is not None else ServiceSettings.from_env()
    readiness = dict(checks) if checks is not None else default_checks(settings)

    app = FastAPI(title=settings.service_name, version=settings.version)
    app.state.settings = settings
    app.state.counter = VisitCounter(settings.data_dir)
    Counter = Annotated[VisitCounter, Depends(get_counter)]

    @app.get("/", response_model=ServiceInfo)
    def info() -> ServiceInfo:
        """Name and version of the running service (handy to confirm which image is deployed)."""
        return ServiceInfo(service=settings.service_name, version=settings.version)

    @app.get("/api/visits", response_model=VisitCount)
    def get_visits(counter: Counter) -> VisitCount:
        """Current number of recorded visits."""
        return VisitCount(visits=counter.read())

    @app.post("/api/visits", response_model=VisitCount)
    def add_visit(counter: Counter) -> VisitCount:
        """Record one visit."""
        return VisitCount(visits=counter.increment())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness: answers as long as the process can serve HTTP. Never checks dependencies."""
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        """Readiness: 200 if every check passes, otherwise 503 listing the failing checks."""
        results = run_checks(readiness)
        report = {name: "ok" if passed else "failing" for name, passed in results.items()}
        if all(results.values()):
            return JSONResponse({"status": "ready", "checks": report})
        failing = sorted(name for name, passed in results.items() if not passed)
        body = {"status": "not ready", "checks": report, "failing": failing}
        return JSONResponse(body, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return app
