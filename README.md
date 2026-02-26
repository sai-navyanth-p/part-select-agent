# PartSelect Chat Agent

An AI-powered customer support agent for [PartSelect.com](https://www.partselect.com/), specialized in refrigerator and dishwasher replacement parts. Built with a multi-agent architecture where a lightweight router classifies user intent and delegates to domain-specific specialists.

## Demo

https://www.loom.com/share/16d774ea0adb4f06b49e779dc22ac075

## Architecture, Design choices and all other Details:

https://github.com/sai-navyanth-p/part-select-agent/blob/main/ARCHITECTURE.md

## What It Does

- **Find parts** - Search by part number, keyword, symptom, or model number
- **Check compatibility** - Verify if a part fits a specific appliance model
- **Troubleshoot problems** - Diagnose issues with step-by-step guidance
- **Installation help** - Get difficulty ratings and install instructions
- **Track orders** - Look up order status and shipping info

## Architecture

```
User ──► Guardrails ──► Memory ──► Router (gpt-4o-mini)
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼           ▼
                    Product       Repair       Order
                    Expert        Expert       Support
                   (gpt-4o)     (gpt-4o)     (gpt-4o)
                          │           │           │
                          └───────────┼───────────┘
                                      ▼
                               SSE Streaming
                                      │
                                      ▼
                              Next.js Frontend
```

- **Router** uses gpt-4o-mini for fast, cheap intent classification (~200ms)
- **Specialists** use gpt-4o with focused prompts and only the tools they need
- **Responses stream** token-by-token via Server-Sent Events
- **Guardrails** block off-topic queries and prompt injection before hitting the LLM
- **Memory** keeps conversations manageable by summarizing older messages

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | GPT-4o + GPT-4o-mini (OpenAI) |
| Backend | FastAPI, Python |
| Frontend | Next.js, React, TypeScript |
| Databases | SQLite (relational) + ChromaDB (semantic search) |
| Streaming | Server-Sent Events |
| Scraper | Playwright with stealth mode |

## Quick Start

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo 'OPENAI_API_KEY=sk-your-key' > .env
PYTHONPATH=. uvicorn main:app --port 8000

# Frontend (new terminal)
npm install && npm run dev
```

Open http://localhost:3000

See [SETUP.md](SETUP.md) for detailed instructions and [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical breakdown.

## Project Structure

```
backend/
├── main.py                     # FastAPI app + SSE streaming
├── agents/
│   ├── base.py                 # Specialist base class
│   ├── router.py               # Intent classifier
│   ├── specialists.py          # Product, Repair, Order agents
│   ├── memory.py               # Conversation memory
│   └── guardrails.py           # Input/output validation
├── tools/tool_definitions.py   # 6 tools grouped by specialist
├── data/
│   ├── database.py             # SQLite (28 parts, 20 models)
│   ├── vector_store.py         # ChromaDB semantic search
│   └── load_data.py            # Data loader
└── scraper/scraper.py          # Playwright scraper

src/app/
├── page.tsx                    # Chat UI with streaming
└── globals.css                 # PartSelect-branded theme
```
