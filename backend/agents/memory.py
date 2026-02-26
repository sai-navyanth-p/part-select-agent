"""Conversation memory manager: sliding window with summarization."""

import tiktoken

# Max tokens to keep in conversation history before summarizing
MAX_HISTORY_TOKENS = 6000
# Number of recent messages to always keep (never summarize these)
KEEP_RECENT = 10
# Model used for token counting
TOKEN_MODEL = "gpt-4o"


def count_tokens(messages: list[dict], model: str = TOKEN_MODEL) -> int:
    """Approximate token count for a list of messages."""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    total = 0
    for msg in messages:
        # ~4 tokens per message overhead
        total += 4
        total += len(enc.encode(msg.get("content", "")))
        total += len(enc.encode(msg.get("role", "")))
    return total


def summarize_history(client, messages: list[dict]) -> list[dict]:
    """If the conversation is too long, summarize older messages.

    Keeps the most recent KEEP_RECENT messages verbatim and summarizes
    everything before that into a single context message.
    """
    if len(messages) <= KEEP_RECENT:
        return messages

    tokens = count_tokens(messages)
    if tokens <= MAX_HISTORY_TOKENS:
        return messages

    # Split into old (to summarize) and recent (to keep)
    old_messages = messages[:-KEEP_RECENT]
    recent_messages = messages[-KEEP_RECENT:]

    # Build a summary of the older conversation
    summary_prompt = (
        "Summarize this conversation concisely. Focus on: what parts/models were discussed, "
        "what problems were described, what was recommended, and any order IDs mentioned. "
        "Keep it under 200 words."
    )

    summary_messages = [
        {"role": "system", "content": summary_prompt},
        {"role": "user", "content": _format_messages_for_summary(old_messages)},
    ]

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=summary_messages,
            temperature=0,
            max_tokens=300,
        )
        summary_text = resp.choices[0].message.content or ""
    except Exception:
        # If summarization fails, just truncate
        return recent_messages

    # Prepend the summary as a system-like context message
    context_msg = {
        "role": "user",
        "content": f"[Previous conversation summary: {summary_text}]",
    }

    return [context_msg] + recent_messages


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Format messages into a readable string for the summarizer."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content and role in ("user", "assistant"):
            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
    return "\n".join(lines)
