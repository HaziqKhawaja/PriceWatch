.PHONY: up down test lint migrate logs

up:
	docker compose up --build -d

down:
	docker compose down

test:
	docker compose up -d --wait db-test
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check .

migrate:
	docker compose run --rm api alembic upgrade head

logs:
	docker compose logs -f api
