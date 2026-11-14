.PHONY: install dev dev-bot-poll test test-unit migrate-up seed fmt lint

install:
	pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-bot-poll:
	BOT_MODE=polling uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Requires ngrok installed; set NGROK_AUTHTOKEN in .env
dev-bot-webhook:
	@echo "Start ngrok http 8000, set BACKEND_URL, then BOT_MODE=webhook uvicorn app.main:app --reload"

test:
	pytest -q

test-unit:
	pytest tests/unit -q

test-integration:
	pytest tests/integration -q

migrate-new:
	alembic revision --autogenerate -m "$(m)"

migrate-up:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

seed:
	python -m app.core.seed

fmt:
	black app tests && isort app tests

lint:
	ruff check app tests

typecheck:
	mypy app

docker-up:
	docker compose up --build -d

docker-logs:
	docker compose logs -f app
