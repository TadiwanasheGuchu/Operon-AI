.PHONY: help setup db-init migrate seed-demo api web test test-api test-web lint typecheck check up down

help: ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install API and web dependencies
	cd apps/api && uv sync
	pnpm install

db-init: ## Create roles and databases on a local Postgres (without Docker)
	sudo -u postgres psql -v ON_ERROR_STOP=1 -f infrastructure/database/init/01-roles.sql

migrate: ## Apply database migrations
	cd apps/api && uv run alembic upgrade head

seed-demo: ## Create a demo organisation for an existing account: make seed-demo EMAIL=you@example.com
	cd apps/api && uv run python -m operon.cli seed-demo --owner-email "$(EMAIL)"

api: ## Run the API with reload on :8000
	cd apps/api && OPERON_LOG_JSON=false uv run uvicorn operon.main:create_app --factory --reload --port 8000

web: ## Run the web app on :3000
	pnpm dev:web

test: test-api test-web ## Run all tests

test-api:
	cd apps/api && uv run pytest

test-web:
	pnpm test:web

lint: ## Lint everything
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
	pnpm lint:web

typecheck: ## Type-check everything
	cd apps/api && uv run mypy src tests
	pnpm typecheck:web

check: lint typecheck test ## Everything CI runs

up: ## Start the full stack in Docker
	docker compose up --build

down: ## Stop the Docker stack
	docker compose down
