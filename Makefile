.PHONY: help install migrate seed api web test lint up down logs

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm install

migrate: ## Apply database migrations
	cd backend && .venv/bin/alembic upgrade head

seed: ## Seed sample jobs plus demo and admin accounts
	cd backend && PYTHONPATH=. .venv/bin/python -m scripts.seed --with-demo-user

api: ## Run the backend on :8000
	cd backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000

web: ## Run the frontend on :3000
	cd frontend && npm run dev

test: ## Run the backend test suite
	cd backend && PYTHONPATH=. .venv/bin/pytest

lint: ## Typecheck the frontend
	cd frontend && npm run typecheck

up: ## Start the whole stack with Docker
	docker compose up --build -d

down: ## Stop the stack
	docker compose down

logs: ## Follow container logs
	docker compose logs -f
