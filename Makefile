.PHONY: help setup backend frontend dev test lint docker models

help:
	@echo "make setup     - install backend (uv/pip) and frontend (npm) dependencies"
	@echo "make backend   - run FastAPI backend on :8000 (hot reload)"
	@echo "make frontend  - run Next.js frontend on :3000"
	@echo "make dev       - run both (requires two terminals or 'make -j2 dev')"
	@echo "make test      - run backend pytest suite with the mock LLM"
	@echo "make models    - pull the default Ollama models"
	@echo "make docker    - docker compose up --build"

setup:
	cd backend && (command -v uv >/dev/null && uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements.txt || (python3 -m venv .venv && .venv/bin/pip install -r requirements.txt))
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port $${PORT:-8000}

frontend:
	cd frontend && npm run dev

dev: backend frontend

test:
	cd backend && VID2GRAPH_LLM_PROVIDER=mock VID2GRAPH_EMBEDDING_PROVIDER=hash .venv/bin/python -m pytest -q

models:
	ollama pull qwen2.5:7b
	ollama pull nomic-embed-text

docker:
	docker compose up --build
