# syntax=docker/dockerfile:1
#
# Production image for container_service.
#   Build:  docker build -t container-service:0.1.0 --build-arg APP_VERSION=0.1.0 .
#   Run:    docker run --rm -p 127.0.0.1:8000:8000 container-service:0.1.0
#
# Two stages: the builder installs dependencies into a virtual environment; the runtime stage copies only
# that environment and the application code, so compilers, pip caches and build files never ship.

# ---- Stage 1: builder -------------------------------------------------------------------------------
# Pinned tag (Python minor version + Debian release). For fully reproducible builds pin the digest too:
#   FROM python:3.13-slim-bookworm@sha256:<digest>
FROM python:3.13-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Copy only the dependency list first: this layer is cached until requirements-runtime.txt changes.
COPY requirements-runtime.txt /tmp/requirements-runtime.txt
RUN pip install --no-cache-dir -r /tmp/requirements-runtime.txt

# ---- Stage 2: runtime -------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

ARG APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="container-service" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    SERVICE_VERSION="${APP_VERSION}" \
    DATA_DIR=/app/data

# A dedicated unprivileged user with a fixed UID/GID (Kubernetes runAsNonRoot can check numeric ids).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Code stays owned by root, so the app user can read it but not modify it.
COPY container_service.py /app/
# The only writable path: mount a volume here to keep data across container restarts.
RUN mkdir -p /app/data && chown app:app /app/data

USER 10001:10001

EXPOSE 8000

# Liveness check without curl (not installed in slim images): exits non-zero if /healthz fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM directly, so shutdowns are graceful.
CMD ["uvicorn", "--factory", "container_service:create_app", "--host", "0.0.0.0", "--port", "8000"]
