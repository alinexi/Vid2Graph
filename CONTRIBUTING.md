# Contributing to Vid2Graph

Thanks for helping! The project is intentionally small and readable — please keep it that way.

## Dev setup

```bash
make setup           # backend venv + frontend npm install
make backend         # FastAPI with reload on :8000
make frontend        # Next.js dev server on :3000
make test            # pytest with the mock LLM (no model required)
```

Set `VID2GRAPH_LLM_PROVIDER=mock` in `.env` to exercise the full pipeline without any model.

## Where things live

* Extraction prompts and schemas: `backend/app/pipeline/graph_gen.py`
* Entity resolution rules: `backend/app/pipeline/resolver.py`
* New transcript sources: `backend/app/pipeline/extractor.py` (return an `IngestResult`)
* New export formats: `backend/app/pipeline/exporter.py` + a route in `api/routes.py`
* Knowledge-level filter semantics: `frontend/src/lib/store.ts` → `nodeVisible`

## Guidelines

* Every structured LLM output goes through a Pydantic model; keep schemas flat so 7B models can fill them.
* Keep the pipeline testable with the mock provider — add a handler in `core/mock_llm.py` for any new schema.
* Run `npm run lint && npm run build` and `make test` before opening a PR.
* Prefer small PRs with a short description of the user-facing change.

## Feedback

Not a code contribution? Still valuable. Open an issue with what worked, what didn't, which model you used, and what kind of video you tried. Real-world results on different model families and video types directly shape prompt tuning and the roadmap.
