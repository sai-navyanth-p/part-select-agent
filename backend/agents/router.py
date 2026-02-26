"""Router agent: classifies user intent and delegates to the right specialist."""

import json
from openai import OpenAI

# Intent categories the router can classify into
INTENTS = [
    "product_search",    # searching for parts, browsing
    "compatibility",     # checking if a part fits a model
    "troubleshooting",   # diagnosing a problem / symptom
    "installation",      # how to install a part
    "order_lookup",      # checking order status
    "general",           # greetings, thanks, off-topic, chitchat
]

ROUTER_PROMPT = """You are an intent classifier for PartSelect.com customer support.

Given a user message, classify it into exactly ONE of these intents:
- product_search: user is looking for a part, browsing parts, asking about a specific PS number
- compatibility: user asks if a part works with their appliance model
- troubleshooting: user describes a problem or symptom with their appliance
- installation: user asks how to install or replace a part
- order_lookup: user asks about an order status, tracking, or delivery
- general: greetings, thank you, chitchat, or anything that doesn't fit above

Respond with ONLY a JSON object, no other text:
{"intent": "<intent>", "entities": {"query": "...", "ps_number": "...", "model_number": "...", "order_id": "..."}}

Only include entity fields that are present in the user's message. The "query" field should contain the core search terms or symptom description.
"""

# Map intents to specialist names
INTENT_TO_SPECIALIST = {
    "product_search": "product",
    "compatibility": "product",
    "troubleshooting": "repair",
    "installation": "repair",
    "order_lookup": "order",
    "general": None,  # router handles directly
}

GENERAL_PROMPT = """You are the PartSelect AI Assistant.
You specialize in refrigerator and dishwasher replacement parts.
For general greetings, be warm and briefly mention what you can help with.
If the user asks about something outside refrigerators/dishwashers, politely redirect.
Keep responses concise - 1-3 sentences max for general chat."""


class Router:
    def __init__(self, client: OpenAI):
        self.client = client
        self.model = "gpt-4o-mini"

    def classify(self, messages: list[dict]) -> dict:
        """Classify the latest user message into an intent + extracted entities.

        Uses the last few messages for context so follow-ups stay routed
        correctly (e.g. 'just list any' after a product search question).
        """
        # Build a short context snippet from recent messages
        recent = messages[-3:] if len(messages) > 3 else messages
        context = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in recent
        )

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0,
            max_tokens=200,
        )

        text = resp.choices[0].message.content or ""
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Fall back to general if parsing fails
            result = {"intent": "general", "entities": {}}

        intent = result.get("intent", "general")
        if intent not in INTENTS:
            intent = "general"

        return {
            "intent": intent,
            "specialist": INTENT_TO_SPECIALIST.get(intent),
            "entities": result.get("entities", {}),
        }

    def handle_general(self, messages: list[dict]) -> str:
        """Handle general/greeting messages directly without a specialist."""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": GENERAL_PROMPT}] + messages,
            temperature=0.7,
            max_tokens=300,
        )
        return resp.choices[0].message.content or ""

    def stream_general(self, messages: list[dict]):
        """Stream a general response token by token."""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": GENERAL_PROMPT}] + messages,
            temperature=0.7,
            max_tokens=300,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
