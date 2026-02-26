# Backend

Python backend for the PartSelect Chat Agent. Handles user queries through a multi-agent pipeline: guardrails → memory → router → specialist.

## Structure

```
main.py                     FastAPI app, /api/chat and /api/chat/stream endpoints
agents/
├── base.py                 SpecialistAgent base class (sync + streaming)
├── router.py               Intent classifier using gpt-4o-mini
├── specialists.py          Product Expert, Repair Expert, Order Support
├── memory.py               Sliding window + summarization via tiktoken
└── guardrails.py           Input validation, prompt injection blocking
tools/
└── tool_definitions.py     6 tools grouped by specialist
data/
├── database.py             SQLite: parts, models, compatibility, guides, orders
├── vector_store.py         ChromaDB: semantic search over products and guides
├── seed_data.py            28 parts, 20 models, guides, sample orders
└── load_data.py            Loads seed data + scraped data into DBs
scraper/
└── scraper.py              Playwright scraper for PartSelect.com
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check + DB stats |
| `POST` | `/api/chat` | Sync chat endpoint |
| `POST` | `/api/chat/stream` | SSE streaming endpoint |

## Running

```bash
source venv/bin/activate
PYTHONPATH=. uvicorn main:app --reload --port 8000
```

## Dependencies

Core: `fastapi`, `uvicorn`, `openai`, `chromadb`, `tiktoken`, `sse-starlette`

Scraper: `playwright`, `playwright-stealth`, `beautifulsoup4`

Full list in `requirements.txt`.
