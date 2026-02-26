# Architecture

## Overview

This is a customer support chat agent for [PartSelect.com](https://www.partselect.com/), focused on refrigerator and dishwasher replacement parts. The system uses a multi-agent architecture where a lightweight router classifies user intent and delegates to specialized agents, each with its own tools and expertise.

The backend is built with FastAPI and uses OpenAI's function-calling API for tool execution. Data lives in SQLite (relational queries) and ChromaDB (semantic search). The frontend is a Next.js app that streams responses via Server-Sent Events.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                           │
│                                                                     │
│   User Input ──► SSE Stream Reader ──► Message Renderer             │
│                                         ├── Markdown (text)         │
│                                         ├── Product Cards           │
│                                         └── Specialist Badge        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ POST /api/chat/stream (SSE)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          FastAPI Backend                            │
│                                                                     │
│   ┌──────────────┐                                                  │
│   │  Guardrails   │◄── Input validation, off-topic detection,       │
│   │               │    prompt injection blocking                    │
│   └──────┬───────┘                                                  │
│          ▼                                                          │
│   ┌──────────────┐                                                  │
│   │    Memory     │◄── Sliding window (last 10 messages)            │
│   │   Manager     │    + older message summarization                │
│   └──────┬───────┘                                                  │
│          ▼                                                          │
│   ┌──────────────┐    gpt-4o-mini                                   │
│   │    Router     │◄── Classifies intent + extracts entities        │
│   │               │    ~200ms, low cost                             │
│   └──────┬───────┘                                                  │
│          │                                                          │
│          ├── product_search ──► Product Expert (gpt-4o)             │
│          ├── compatibility  ──► Product Expert (gpt-4o)             │
│          ├── troubleshooting ─► Repair Expert (gpt-4o)              │
│          ├── installation ───► Repair Expert (gpt-4o)               │
│          ├── order_lookup ───► Order Support (gpt-4o)               │
│          └── general ────────► Router responds directly             │
│                                                                     │
│   Each specialist has:                                              │
│   • A focused system prompt                                         │
│   • A subset of tools (not all tools)                               │
│   • Streaming support (tokens sent as SSE events)                   │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Data Layer                                 │
│                                                                     │
│   ┌────────────────────┐    ┌────────────────────┐                  │
│   │   SQLite            │    │   ChromaDB          │                 │
│   │   (Relational)      │    │   (Semantic)        │                 │
│   │                     │    │                     │                 │
│   │   • parts           │    │   • products        │                 │
│   │   • models          │    │     (embeddings)    │                 │
│   │   • compatibility   │    │   • guides          │                 │
│   │   • troubleshooting │    │     (embeddings)    │                 │
│   │   • installation    │    │                     │                 │
│   │   • orders          │    │                     │                 │
│   └────────────────────┘    └────────────────────┘                  │
│                                                                     │
│   Search is hybrid: SQL keyword + vector semantic, merged           │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow

A single user message goes through this pipeline:

```
1. User types "My dishwasher won't drain"

2. Guardrails (no LLM)
   ├── Check input length (1–2000 chars)
   ├── Scan for prompt injection patterns
   └── Check for off-topic appliances (microwave, oven, etc.)
   Result: PASS

3. Memory Manager
   ├── Count tokens in conversation history
   ├── If > 6000 tokens: summarize older messages via gpt-4o-mini
   └── Keep last 10 messages verbatim
   Result: Trimmed message list

4. Router (gpt-4o-mini, ~200ms)
   ├── Input: "My dishwasher won't drain"
   └── Output: { intent: "troubleshooting", specialist: "repair" }

5. Repair Expert (gpt-4o)
   ├── Turn 1: Calls get_troubleshooting_guide("dishwasher", "not draining")
   │           → Returns diagnosis steps + recommended parts
   ├── Turn 2: Calls search_products("dishwasher drain pump")
   │           → Returns matching parts with prices
   └── Turn 3: Generates response with diagnosis + product cards

6. Response streams back via SSE
   ├── event: message → { token: "First, let's..." }
   ├── event: message → { token: "check the..." }
   ├── ...
   └── event: done → { intent, specialist, products }
```

## Agent Details

### Router (`agents/router.py`)

Uses `gpt-4o-mini` for fast, cheap intent classification. Classifies into one of six intents and maps each to a specialist:

| Intent | Specialist | Description |
|--------|-----------|-------------|
| `product_search` | Product Expert | Looking for parts by name, number, or symptom |
| `compatibility` | Product Expert | Checking if a part fits a model |
| `troubleshooting` | Repair Expert | Describing an appliance problem |
| `installation` | Repair Expert | Asking how to install a part |
| `order_lookup` | Order Support | Checking order status/tracking |
| `general` | Router (direct) | Greetings, thanks, off-topic |

### Specialists (`agents/specialists.py`)

Each specialist is an instance of `SpecialistAgent` (defined in `agents/base.py`) with:

**Product Expert**
- Model: gpt-4o
- Tools: `search_products`, `check_compatibility`, `get_model_info`
- Prompt focus: Part recommendations, pricing, compatibility checks

**Repair Expert**
- Model: gpt-4o
- Tools: `get_troubleshooting_guide`, `get_installation_guide`, `search_products`
- Prompt focus: Safety warnings, diagnosis steps, difficulty assessment

**Order Support**
- Model: gpt-4o
- Tools: `lookup_order`
- Prompt focus: Order status, tracking info, empathetic tone

### Memory (`agents/memory.py`)

Manages conversation length to stay within context limits:

- Counts tokens using `tiktoken`
- If conversation exceeds 6000 tokens and has >10 messages:
  - Keeps the 10 most recent messages verbatim
  - Summarizes everything older into one context message via gpt-4o-mini

### Guardrails (`agents/guardrails.py`)

Pre-LLM validation (no API calls, fast):

- **Input length**: 1–2000 characters
- **Prompt injection**: Regex patterns for common injection attempts
- **Off-topic detection**: Keyword check for unsupported appliances (microwave, oven, washer, dryer, etc.)
- **Output cleaning**: Strips leaked internal tokens, validates product card JSON

## Tools

Six tools available to specialists:

| Tool | Specialist(s) | Description |
|------|---------------|-------------|
| `search_products` | Product, Repair | Hybrid search: SQL keyword + ChromaDB semantic, merged and deduplicated |
| `check_compatibility` | Product | Checks the compatibility table for a (part, model) pair |
| `get_model_info` | Product | Returns model details and all compatible parts |
| `get_troubleshooting_guide` | Repair | Finds diagnosis steps by category + symptom |
| `get_installation_guide` | Repair | Returns step-by-step install instructions for a part |
| `lookup_order` | Order | Looks up order by ID, returns status and tracking |

## Data Layer

### SQLite (`data/database.py`)

Six tables:

- `parts` - 28 products (PS number, name, price, brand, compatibility, etc.)
- `models` - 20 appliance models (model number, brand, type)
- `compatibility` - 86 part-model links
- `troubleshooting_guides` - 8 guides with diagnosis steps
- `installation_guides` - 6 guides with step-by-step instructions
- `orders` - 4 sample orders with tracking

### ChromaDB (`data/vector_store.py`)

Two collections for semantic search:

- `products` - Part descriptions embedded for natural language queries
- `guides` - Troubleshooting guide content embedded

### Hybrid Search

When a user searches for parts, we query both:

1. **SQLite** - LIKE queries across name, PS number, description, brand (fast, exact)
2. **ChromaDB** - Semantic similarity on the query text (fuzzy, handles synonyms)

Results are merged and deduplicated by PS number, SQL results first.

### Data Loading (`data/load_data.py`)

On first startup, loads seed data from `data/seed_data.py` into both SQLite and ChromaDB. If scraped data exists (from the Playwright scraper), it's merged on top of the seed data.

## Scraper (`scraper/scraper.py`)

A Playwright-based scraper that collects real product data from PartSelect.com:

- Runs in visible browser mode (headless=False) to bypass anti-bot detection
- Uses `playwright-stealth` for fingerprint masking
- Extracts: part details, pricing, compatibility info, model data
- Saves to JSON files in `data/scraped/`

The scraper runs offline. The app works with seed data by default.

## Frontend (`src/app/page.tsx`)

A single-page Next.js app with:

- **SSE streaming**: Reads tokens from `/api/chat/stream` as they arrive
- **Typewriter render**: Displays tokens with a blinking cursor during streaming
- **Specialist badge**: Shows which agent (Product Expert, Repair Expert, etc.) is responding
- **Product cards**: Renders interactive cards with pricing, ratings, stock status, and install difficulty
- **Sync fallback**: If streaming fails, falls back to the regular `/api/chat` endpoint

The design matches PartSelect.com's branding: white header, teal nav bar, golden hero section, and their color palette.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check + database stats |
| `POST` | `/api/chat` | Sync chat (returns full response) |
| `POST` | `/api/chat/stream` | Streaming chat (returns SSE events) |

### Chat Request
```json
{
  "messages": [
    { "role": "user", "content": "My dishwasher won't drain" }
  ]
}
```

### Chat Response (sync)
```json
{
  "response": "Let's troubleshoot your dishwasher...",
  "products": [{ "ps_number": "PS3406971", "name": "Drain Pump", "price": 38.50, ... }],
  "intent": "troubleshooting",
  "specialist": "repair"
}
```

### SSE Events (streaming)
```
event: message
data: {"token": "Let's "}

event: message
data: {"token": "troubleshoot "}

event: done
data: {"intent": "troubleshooting", "specialist": "repair", "products": [...]}
```

## Project Structure

```
├── backend/
│   ├── main.py                     # FastAPI app, endpoints, lifespan
│   ├── agents/
│   │   ├── base.py                 # SpecialistAgent class (sync + streaming)
│   │   ├── router.py               # Intent classifier (gpt-4o-mini)
│   │   ├── specialists.py          # Product, Repair, Order specialists
│   │   ├── memory.py               # Conversation memory management
│   │   └── guardrails.py           # Input/output validation
│   ├── tools/
│   │   └── tool_definitions.py     # Tool schemas + execute_tool()
│   ├── data/
│   │   ├── database.py             # SQLite schema + queries
│   │   ├── vector_store.py         # ChromaDB semantic search
│   │   ├── seed_data.py            # Fallback product/model data
│   │   └── load_data.py            # Data loader
│   └── scraper/
│       └── scraper.py              # Playwright web scraper
├── src/app/
│   ├── page.tsx                    # Chat UI with SSE streaming
│   └── globals.css                 # PartSelect-branded styles
├── ARCHITECTURE.md                 # This file
├── SETUP.md                        # How to run the app
└── README.md                       # Project overview
```

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| LLM | GPT-4o + GPT-4o-mini | 4o for quality responses, 4o-mini for fast/cheap routing |
| Backend | FastAPI + SSE | Async, streaming support, Pydantic validation |
| Relational DB | SQLite | Zero setup, good for structured queries |
| Vector DB | ChromaDB | Local embeddings, simple API |
| Scraper | Playwright + stealth | Handles JavaScript-heavy pages and anti-bot |
| Frontend | Next.js + React | SSR, TypeScript, fast dev |
| Streaming | Server-Sent Events | Simpler than WebSockets for one-way streaming |

## Design Decisions

### 1. Multi-Agent Architecture Over Single Agent

A single agent with all 6 tools works for a simple demo, but has real problems as the product grows:

- **Prompt bloat**: One system prompt explaining parts, repairs, orders, and safety warnings becomes long and vague. The model starts mixing concerns - giving safety disclaimers when someone's just searching for a water filter.
- **Tool confusion**: With 6 tools available, a single agent sometimes calls the wrong tool (e.g., calling `get_troubleshooting_guide` when the user asked for a price). Specialists with 2-3 tools rarely make this mistake.
- **Scalability**: Adding a new domain (e.g., "Returns Expert") means adding one file with a prompt and registering it in the router. With a single agent, you'd have to modify one increasingly fragile system prompt.

The tradeoff is latency - there's an extra LLM call for routing (~200ms). But we mitigate this by using `gpt-4o-mini` for the router, which is fast and cheap

### 2. Model Selection (GPT-4o + GPT-4o-mini)

We use two models strategically:

| Task | Model | Why |
|------|-------|-----|
| Router (intent classification) | gpt-4o-mini | Fast (~200ms), cheap ($0.15/1M input), classification doesn't need reasoning |
| Specialists (tool use + response) | gpt-4o | Better at multi-step tool use, follows system prompts more faithfully, generates higher quality responses |
| Memory summarization | gpt-4o-mini | Summarization is straightforward, doesn't need the expensive model |

This dual-model approach cuts costs by roughly 60% compared to using gpt-4o for everything, while keeping response quality high where it matters most.

### 3. Router Design - Classification Before Delegation

The router uses a structured prompt that asks gpt-4o-mini to return JSON with an intent and entities. We considered two alternatives:

- **Embedding-based classification**: Faster but would require labeled training data we didn't have. Also can't extract entities like part numbers and model numbers from the message.
- **Direct delegation** (let the model pick which agent): More flexible but less predictable - hard to guarantee consistent routing behavior.

The structured classification approach gives us a clear audit trail (every message has an intent label) and makes debugging easy. The router also considers the last 3 messages for context, so follow-up messages like "just list any" stay correctly routed.

### 4. Tool Subsetting - Not Every Agent Gets Every Tool

Each specialist gets only the tools relevant to its domain:

```
Product Expert  →  search_products, check_compatibility, get_model_info
Repair Expert   →  get_troubleshooting_guide, get_installation_guide, search_products
Order Support   →  lookup_order
```

This is a deliberate constraint. When an agent has access to tools it doesn't need, it sometimes calls them anyway (e.g., a Repair Expert calling `check_compatibility` instead of `get_troubleshooting_guide`). Restricting tools improves tool selection accuracy significantly.

Note that `search_products` is shared between Product and Repair - the Repair Expert needs it to recommend replacement parts after diagnosing an issue.

### 5. Hybrid Search - SQL + Semantic

We run two searches in parallel and merge results:

- **SQLite LIKE queries** catch exact matches: PS numbers ("PS3406971"), brand names ("Samsung"), specific part names ("drain pump"). These are fast and precise.
- **ChromaDB semantic search** catches fuzzy queries: "that thing that makes ice in my fridge" correctly finds the Ice Maker Assembly even though the query shares no keywords.

Results are merged with SQL results first (higher confidence), then semantic results, deduplicated by PS number. This gives us coverage of both precise and vague queries without requiring the user to know exact terminology.

### 6. SSE Streaming Over WebSockets

We stream responses using Server-Sent Events (SSE) instead of WebSockets:

- **SSE is one-directional** - the server pushes tokens to the client. Chat is inherently request-response (user sends, agent responds), so bidirectional communication isn't needed.
- **SSE works over HTTP** - no special proxy configuration, works behind standard load balancers, and reconnection is built into the browser's `EventSource` API.
- **Simpler error handling** - if the stream fails, the frontend falls back to the synchronous `/api/chat` endpoint. With WebSockets, you'd need to manage connection state, heartbeats, and reconnection logic.

The SSE stream sends individual tokens as they're generated, giving a typewriter effect. The final `done` event includes structured data (intent, specialist, product cards) that the frontend uses for rendering.

### 7. Conversation Memory - Sliding Window + Summarization

Long conversations cause two problems: they exceed the model's context window, and they increase cost (tokens aren't free). Our memory strategy:

- **Keep the last 10 messages verbatim** - recent context is the most important for maintaining coherent conversation flow.
- **Summarize everything older** - a single gpt-4o-mini call condenses older messages into a brief context paragraph. This preserves key facts (model numbers, parts discussed) without keeping every token.
- **Token counting with tiktoken** - we count tokens accurately rather than guessing by character count. The threshold is 6000 tokens, which leaves room for the system prompt and tool responses.

This approach keeps costs predictable while maintaining conversational context across long sessions.

### 8. Guardrails - Pre-LLM Validation

Guardrails run before any LLM call, using regex and keyword matching (no LLM cost):

- **Input length** (1–2000 chars): Prevents empty messages and context-stuffing attacks.
- **Prompt injection detection**: Regex patterns catch common injection attempts ("ignore all previous instructions", "system prompt", etc.).
- **Off-topic filtering**: Keyword check for unsupported appliances (microwave, oven, washer, dryer, AC). These get a polite redirect rather than a confusing response.
- **Output cleaning**: Strips any leaked internal tokens (like `<<<PRODUCT_CARDS:...>>>`) before they reach the user, and validates product card JSON.

We chose regex over LLM-based guardrails because they're instant (no API latency), free, and predictable. LLM-based moderation could be added as an additional layer if needed.

### 9. Local Databases - SQLite + ChromaDB

Both databases run in-process with zero infrastructure:

- **SQLite** stores structured data (parts, models, compatibility mappings, guides, orders) with proper foreign keys and JOIN support. No separate database server needed.
- **ChromaDB** stores embeddings locally in a persistent directory. It uses its own embedding model (all-MiniLM-L6-v2) so we don't need to make API calls for embeddings.

For production, SQLite → PostgreSQL and ChromaDB → Pinecone/Weaviate would be the natural migration path. The app's data access layer is abstracted enough that this swap wouldn't require changes to the agent code.

### 10. Playwright Scraper - Visible Browser with Stealth

The scraper uses Playwright in visible mode (headless=False) with `playwright-stealth`:

- **Not headless**: PartSelect.com has anti-bot detection that blocks headless browsers. Running in visible mode with realistic browser fingerprints avoids detection.
- **Stealth plugin**: Patches common headless-detection vectors (navigator.webdriver, chrome.runtime, etc.).
- **Offline scraping**: The scraper runs separately from the app. Scraped data is saved to JSON files and loaded on startup. The app works with seed data even without scraping.

This design means the app never depends on the scraper running - it's a data enrichment tool, not a runtime dependency.
