.PHONY: up up-local down seed seed-load indexes test test-unit test-int lint typecheck eval explain openapi check

PYTHON ?= python

up:
	docker compose up -d

up-local:
	docker compose up -d

down:
	docker compose down

seed:
	cd backend && $(PYTHON) seed.py

seed-load:
	cd backend && $(PYTHON) seed.py

indexes:
	cd backend && $(PYTHON) -c "import asyncio; from app.db.client import mongo_manager; from app.db.indexes import ensure_indexes; async def run(): await mongo_manager.connect(); await ensure_indexes(mongo_manager.get_database()); await mongo_manager.close(); asyncio.run(run())"

test:
	cd backend && $(PYTHON) -m pytest tests

test-unit:
	cd backend && $(PYTHON) -m pytest tests/test_domain_models.py tests/test_policy.py tests/test_workflow.py

test-int:
	cd backend && $(PYTHON) -m pytest tests/test_integration_concurrency.py tests/test_outbox_worker.py tests/test_search_and_pagination.py tests/test_ai.py

lint:
	cd backend && $(PYTHON) -m ruff check app tests scripts
	cd frontend && npm run lint

typecheck:
	cd backend && $(PYTHON) -m mypy app/domain app/infra
	cd frontend && npx tsc --noEmit

eval:
	cd backend && $(PYTHON) scripts/eval_retrieval.py

explain:
	cd backend && $(PYTHON) scripts/explain_queries.py

openapi:
	cd backend && $(PYTHON) -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > backend/openapi.json

check: test explain eval
