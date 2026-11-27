FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt

# Dev target: runtime deps plus pytest/ruff; used by docker compose.
FROM builder AS dev-builder
RUN pip install -r requirements-dev.txt

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH"
RUN useradd --create-home --uid 1000 app && install -d -o app -g app /app
WORKDIR /app

FROM base AS dev
COPY --from=dev-builder /opt/venv /opt/venv
COPY --chown=app:app app/ ./app/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini pyproject.toml ./
COPY --chown=app:app docker/ ./docker/
COPY --chown=app:app tests/ ./tests/
RUN chmod +x docker/entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]

FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app/ ./app/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini pyproject.toml ./
COPY --chown=app:app docker/ ./docker/
RUN chmod +x docker/entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
