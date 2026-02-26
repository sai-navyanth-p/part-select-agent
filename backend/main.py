"""FastAPI backend for PartSelect Chat Agent.

Architecture: Router (gpt-4o-mini) → Specialists (gpt-4o) with streaming.
"""
import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from sse_starlette.sse import EventSourceResponse

from agents.router import Router
from agents.specialists import create_specialists
from agents.memory import summarize_history
from agents.guardrails import check_input, clean_output
from tools.tool_definitions import execute_tool
from data.database import init_db, get_stats

load_dotenv()


def _ensure_database():
    init_db()
    stats = get_stats()
    if stats["parts"] == 0:
        print("Database empty, loading seed data...")
        from data.load_data import load_seed_data
        load_seed_data()
    else:
        print(f"Database ready: {stats['parts']} parts, {stats['models']} models")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_database()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: OPENAI_API_KEY not set.")
        app.state.client = None
        app.state.router = None
        app.state.specialists = None
    else:
        client = OpenAI(api_key=api_key)
        app.state.client = client
        app.state.router = Router(client)
        app.state.specialists = create_specialists(client)
        print("Multi-agent system initialized (router + 3 specialists)")
    yield


app = FastAPI(title="PartSelect Chat Agent API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    response: str
    products: list[dict] = []
    intent: str = ""
    specialist: str = ""


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "agent_ready": app.state.router is not None,
        "database": get_stats(),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint - routes to specialist, returns full response."""
    if not app.state.router:
        raise HTTPException(503, "Agent not initialized. Set OPENAI_API_KEY.")

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Guardrails: validate input
    last_msg = messages[-1]["content"] if messages else ""
    guard = check_input(last_msg)
    if not guard.passed:
        return ChatResponse(response=guard.message, intent="blocked", specialist="guardrails")

    # Memory: trim if conversation is too long
    messages = summarize_history(app.state.client, messages)

    # Route to the right specialist
    classification = app.state.router.classify(messages)
    intent = classification["intent"]
    specialist_name = classification["specialist"]

    if specialist_name is None:
        # General/greeting - router handles directly
        response_text = app.state.router.handle_general(messages)
        response_text = clean_output(response_text)
        return ChatResponse(response=response_text, intent=intent, specialist="router")

    specialist = app.state.specialists.get(specialist_name)
    if not specialist:
        raise HTTPException(500, f"Unknown specialist: {specialist_name}")

    response_text = specialist.run(messages, execute_tool)
    response_text = clean_output(response_text)

    # Extract product cards
    products = []
    clean_response = response_text
    if "<<<PRODUCT_CARDS:" in response_text:
        try:
            start = response_text.index("<<<PRODUCT_CARDS:") + len("<<<PRODUCT_CARDS:")
            end = response_text.index(">>>", start)
            products = json.loads(response_text[start:end])
            clean_response = response_text[:response_text.index("<<<PRODUCT_CARDS:")].strip()
        except (ValueError, json.JSONDecodeError):
            pass

    return ChatResponse(
        response=clean_response,
        products=products,
        intent=intent,
        specialist=specialist_name,
    )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint - returns SSE events as tokens arrive."""
    if not app.state.router:
        raise HTTPException(503, "Agent not initialized. Set OPENAI_API_KEY.")

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Guardrails
    last_msg = messages[-1]["content"] if messages else ""
    guard = check_input(last_msg)
    if not guard.passed:
        async def blocked_stream():
            yield {"event": "message", "data": json.dumps({"token": guard.message})}
            yield {"event": "done", "data": json.dumps({"intent": "blocked", "specialist": "guardrails"})}
        return EventSourceResponse(blocked_stream())

    # Memory
    messages = summarize_history(app.state.client, messages)

    # Route
    classification = app.state.router.classify(messages)
    intent = classification["intent"]
    specialist_name = classification["specialist"]

    async def token_stream():
        full_response = []
        try:
            if specialist_name is None:
                # General - stream from router
                for token in app.state.router.stream_general(messages):
                    full_response.append(token)
                    yield {"event": "message", "data": json.dumps({"token": token})}
            else:
                specialist = app.state.specialists.get(specialist_name)
                if specialist:
                    for token in specialist.stream(messages, execute_tool):
                        full_response.append(token)
                        yield {"event": "message", "data": json.dumps({"token": token})}

            # Final event with metadata
            complete_text = clean_output("".join(full_response))
            products = []
            if "<<<PRODUCT_CARDS:" in complete_text:
                try:
                    start = complete_text.index("<<<PRODUCT_CARDS:") + len("<<<PRODUCT_CARDS:")
                    end = complete_text.index(">>>", start)
                    products = json.loads(complete_text[start:end])
                except (ValueError, json.JSONDecodeError):
                    pass

            yield {
                "event": "done",
                "data": json.dumps({
                    "intent": intent,
                    "specialist": specialist_name or "router",
                    "products": products,
                }),
            }
        except Exception as e:
            print(f"Stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": "Something went wrong. Please try again."}),
            }

    return EventSourceResponse(token_stream())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
