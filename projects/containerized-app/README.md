# Containerised app: from "works on my machine" to a production image

Take a small FastAPI service and make it ready to run in a container platform (Docker, Kubernetes,
a cloud container service):

* configuration from **environment variables** with validated defaults,
* a **liveness** probe (`/healthz`) and a **readiness** probe (`/readyz`),
* a **multi-stage Dockerfile**: pinned base image, cached dependency layer, non-root user,
  `HEALTHCHECK`, exec-form `CMD`, no secrets,
* a `.dockerignore` that keeps secrets and junk out of the build context,
* a hardened `compose.yaml` with a named volume for data.

```text
GET  /            -> {"service": "container-service", "version": "0.1.0"}
POST /api/visits  -> {"visits": 1}          (stored in $DATA_DIR/visits.txt)
GET  /healthz     -> 200 {"status": "ok"}   (never touches dependencies)
GET  /readyz      -> 200 {"status": "ready", "checks": {"data_dir": "ok"}}
                  -> 503 {"status": "not ready", "checks": {"data_dir": "failing"}, "failing": ["data_dir"]}
```

## Setup

Windows PowerShell:

```powershell
cd projects\containerized-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/containerized-app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the service without Docker (create the data directory first, or `/readyz` reports `503`):

```powershell
mkdir data -Force; python -m uvicorn --factory container_service:create_app --app-dir starter --reload
```

```bash
mkdir -p data && python -m uvicorn --factory container_service:create_app --app-dir starter --reload
```

## Running the tests

```bash
python -m pytest                 # all milestones, against starter/
python -m pytest -k Milestone3   # one milestone
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

Milestones 3 and 4 read `Dockerfile`, `.dockerignore` and `compose.yaml` **as text** and check their
structure (multi-stage, pinned tags, non-root `USER`, exec-form `CMD`, healthcheck, no secrets, hardened
compose settings). **They do not build or run an image**: that needs Docker, which the automated tests
cannot assume. Milestone 5 is the manual check.

## Milestones

| # | Tests | What you build |
|---|-------|----------------|
| 1 | `TestMilestone1Service` | `ServiceSettings.from_env`, `VisitCounter` (atomic file writes) |
| 2 | `TestMilestone2Probes` | `/healthz`, `/readyz`, `run_checks`, `data_dir_is_writable`, `default_checks` |
| 3 | `TestMilestone3Dockerfile` | rewrite `starter/Dockerfile` and `starter/requirements-runtime.txt` |
| 4 | `TestMilestone4BuildContextAndCompose` | `starter/.dockerignore`, `starter/compose.yaml` |
| 5 | manual (below) | build, run and inspect the image with Docker |

## Milestone 5 (manual): build and run with Docker

Requires Docker Desktop (Windows/macOS) or Docker Engine (Linux). **Not verified by the automated tests.**
The build context is the `starter/` (or `solution/`) directory:

```bash
docker build -t container-service:0.1.0 --build-arg APP_VERSION=0.1.0 ./starter
docker run --rm -d --name cs -p 127.0.0.1:8000:8000 container-service:0.1.0
curl http://127.0.0.1:8000/readyz             # PowerShell: Invoke-RestMethod http://127.0.0.1:8000/readyz
docker exec cs id                             # expect uid=10001, not uid=0(root)
docker inspect --format "{{.State.Health.Status}}" cs   # "healthy" after ~30 s
docker image ls container-service             # compare the size with the naive starter image
docker history container-service:0.1.0        # no secrets in any layer
docker stop cs                                # should stop within a second or two (SIGTERM reaches uvicorn)

cd starter && docker compose up --build -d    # then POST /api/visits a few times
docker compose restart && curl http://127.0.0.1:8000/api/visits   # count survived: the volume persists
docker compose down                           # add -v to delete the volume too
```

Optional: scan the image with a vulnerability scanner such as `docker scout cves container-service:0.1.0`
or Trivy (`trivy image container-service:0.1.0`).

## Layout

```text
containerized-app/
  README.md
  requirements.txt            # dev + test dependencies for your machine
  conftest.py                 # GW_TARGET=solution switches the tests (and the static checks) to solution/
  starter/                    # your code AND your Docker build context
    container_service.py
    requirements-runtime.txt  # what goes into the image
    Dockerfile  .dockerignore  compose.yaml
  solution/                   # same files, reference versions
  tests/test_container_service.py
```
