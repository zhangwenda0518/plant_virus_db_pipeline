.PHONY: pg-start pg-stop pg-status test lint format typecheck migrate ingest dev

# --- Postgres lifecycle (Homebrew, macOS) ----------------------------------
pg-start:
	brew services start postgresql@16

pg-stop:
	brew services stop postgresql@16

pg-status:
	brew services list | grep postgresql

# --- Quality ----------------------------------------------------------------
test:
	pytest

lint:
	ruff check src tests

format:
	ruff format src tests

typecheck:
	pyright src

# --- DB & app ---------------------------------------------------------------
migrate:
	alembic upgrade head

ingest:
	python -m neblab_rag.corpus.cli ingest

dev:
	uvicorn neblab_rag.api.main:create_app --factory --reload --port 8000
