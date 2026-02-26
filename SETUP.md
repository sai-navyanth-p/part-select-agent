# How to Run

Two parts to start: the **Python backend** and the **Next.js frontend**. Both need to be running at the same time.

## Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI API key with GPT-4o access

## Backend

```bash
cd backend

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install the browser engine (only needed if you plan to run the scraper)
python -m playwright install chromium
```

Create a `.env` file in the `backend/` directory:

```
OPENAI_API_KEY=sk-your-key-here
```

Start the server:

```bash
PYTHONPATH=. uvicorn main:app --reload --port 8000
```

On first run, the server loads seed data automatically. You should see:

```
Database ready: 28 parts, 20 models
Multi-agent system initialized (router + 3 specialists)
Uvicorn running on http://127.0.0.1:8000
```

Verify it's working: open http://localhost:8000/api/health

## Frontend

In a separate terminal (keep the backend running):

```bash
# From the project root, not backend/
npm install
npm run dev
```

Open http://localhost:3000

## Try It Out

Here are some things you can ask:

| Query | What happens |
|-------|-------------|
| "My dishwasher is not draining" | Routes to Repair Expert → troubleshooting guide + part recommendations |
| "Is PS11753379 compatible with WDT780SAEM1?" | Routes to Product Expert → checks compatibility table |
| "How do I install part PS11752778?" | Routes to Repair Expert → step-by-step instructions |
| "Check order ORD-2024-78432" | Routes to Order Support → order status + tracking |
| "What drain pumps do you have?" | Routes to Product Expert → hybrid search results |

## Optional: Scraper

The app works with seed data by default. To scrape PartSelect.com for real data:

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python -m scraper.scraper
```

The scraper opens a visible browser window - this is intentional to bypass anti-bot protection. After scraping, restart the backend to reload data.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Agent not initialized" | Check `OPENAI_API_KEY` in `backend/.env` |
| Frontend can't connect | Backend must be running on port 8000 |
| ChromaDB errors | Delete `backend/data/chroma/` and restart |
| Database issues | Delete `backend/data/partselect.db` and restart |
| Port in use | `lsof -ti:8000 \| xargs kill -9` |
