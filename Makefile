.PHONY: up down test lint migrate logs

up:
	docker compose up --build -d

down:
	docker compose down

test:
	docker compose up -d --wait db-test
	docker compose run --rm api pytest

lint:
	docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check ."

migrate:
	docker compose run --rm api alembic upgrade head

logs:
	docker compose logs -f api
