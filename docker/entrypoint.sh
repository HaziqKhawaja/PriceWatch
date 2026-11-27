#!/bin/sh
set -e

# If arguments are given, run them instead (e.g. `docker compose run --rm api pytest`).
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
