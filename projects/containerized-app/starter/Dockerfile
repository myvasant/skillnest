# This Dockerfile WORKS -- and it is exactly what you should not ship. Milestone 3: make it production-grade.
#
# TODO(milestone 3):
#   - split it into a builder stage and a runtime stage (FROM ... AS builder, then COPY --from=builder)
#   - pin the base image tag (e.g. python:3.13-slim-bookworm); "latest" changes under you
#   - COPY requirements-runtime.txt and pip install it (with --no-cache-dir) BEFORE copying the code,
#     so the dependency layer is cached between builds
#   - copy only the code the image needs, never the whole directory (and never .env files)
#   - create an unprivileged user and switch to it with USER (containers run as root by default)
#   - set PYTHONDONTWRITEBYTECODE=1 and PYTHONUNBUFFERED=1
#   - add a HEALTHCHECK that calls http://127.0.0.1:8000/healthz (slim images have no curl: use python -c)
#   - use the exec form: CMD ["uvicorn", "--factory", "container_service:create_app", "--host", "0.0.0.0", ...]
FROM python:latest

WORKDIR /app
COPY . .
RUN pip install -r requirements-runtime.txt

CMD uvicorn --factory container_service:create_app --host 0.0.0.0 --port 8000
