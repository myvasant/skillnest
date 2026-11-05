"""A small FastAPI service made ready for containers.

* Configuration comes from environment variables (12-factor style) with safe defaults.
* ``/healthz`` is a cheap liveness probe: "the process is up and serving HTTP".
* ``/readyz`` is a readiness probe: "my dependencies are usable, send me traffic".
* ``/api/visits`` keeps a counter in ``DATA_DIR`` so you can watch a volume survive container restarts.

Fill in every function that raises ``NotImplementedError`` (milestones 1-2), then make the Dockerfile,
.dockerignore and compose.yaml in this directory production-grade (milestones 3-4).

Run locally::

    python -m uvicorn --factory container_service:create_app --app-dir starter --reload
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
        # TODO(milestone 1):
        #   env = os.environ if environ is None else environ
        #   read SERVICE_NAME, SERVICE_VERSION and DATA_DIR, falling back to the defaults above
        #   validate name/version with SERVICE_NAME_PATTERN.fullmatch / VERSION_PATTERN.fullmatch
        #   raise ValueError("SERVICE_NAME must be ...") so the operator knows exactly what to fix
        raise NotImplementedError("TODO(milestone 1): ServiceSettings.from_env")


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
        raise NotImplementedError("TODO(milestone 1): VisitCounter.read")

    def increment(self) -> int:
        """Add one visit and return the new count."""
        # TODO(milestone 1): under self._lock, read, add 1, write to a ".tmp" file next to self._path,
        # then os.replace(tmp, self._path) so a crash never leaves a half-written file.
        raise NotImplementedError("TODO(milestone 1): VisitCounter.increment")


# ---------------------------------------------------------------------------
# Milestone 2: liveness and readiness probes
# ---------------------------------------------------------------------------


def data_dir_is_writable(path: Path) -> bool:
    """Readiness check: ``path`` exists, is a directory, and this process may write to it."""
    raise NotImplementedError("TODO(milestone 2): data_dir_is_writable (hint: Path.is_dir, os.access)")


def run_checks(checks: Mapping[str, ReadinessCheck]) -> dict[str, bool]:
    """Run every readiness check. A check that raises is reported as failing (and logged), not re-raised."""
    raise NotImplementedError("TODO(milestone 2): run_checks")


def default_checks(settings: ServiceSettings) -> dict[str, ReadinessCheck]:
    """The checks used when ``create_app`` is not given any: the data directory must be writable."""
    raise NotImplementedError("TODO(milestone 2): default_checks -> {'data_dir': ...}")


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
        raise NotImplementedError("TODO(milestone 2): return {'status': 'ok'}")

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        """Readiness: 200 if every check passes, otherwise 503 listing the failing checks."""
        # TODO(milestone 2): use `checks` (or default_checks(settings) when it is None) with run_checks.
        #   all pass -> 200 {"status": "ready", "checks": {"name": "ok", ...}}
        #   otherwise -> 503 {"status": "not ready", "checks": {...}, "failing": ["name", ...]}
        #   (return JSONResponse(body, status_code=status.HTTP_503_SERVICE_UNAVAILABLE))
        raise NotImplementedError("TODO(milestone 2): /readyz")

    return app
