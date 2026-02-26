"""Input/output guardrails for the chat agent."""

import re

MAX_INPUT_LENGTH = 2000  # characters
MIN_INPUT_LENGTH = 1     # characters

# Topics we explicitly don't handle (fast keyword check, no LLM needed)
OFF_TOPIC_KEYWORDS = [
    "microwave", "oven", "washer", "dryer", "stove", "range",
    "air conditioner", "hvac", "furnace", "water heater",
    "lawn mower", "vacuum", "toaster",
]

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
    r"you\s+are\s+now\s+a",
    r"forget\s+(everything|your\s+instructions)",
    r"system\s*prompt",
    r"act\s+as\s+if",
]


class GuardrailResult:
    def __init__(self, passed: bool, message: str = ""):
        self.passed = passed
        self.message = message


def check_input(text: str) -> GuardrailResult:
    """Validate user input before sending to the LLM."""
    if not text or len(text.strip()) < MIN_INPUT_LENGTH:
        return GuardrailResult(False, "Please type a message to get started.")

    if len(text) > MAX_INPUT_LENGTH:
        return GuardrailResult(
            False,
            f"Message is too long ({len(text)} chars). Please keep it under {MAX_INPUT_LENGTH} characters."
        )

    # Check for prompt injection attempts
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            return GuardrailResult(
                False,
                "I'm here to help with refrigerator and dishwasher parts. How can I assist you?"
            )

    # Check for clearly off-topic appliance types
    for keyword in OFF_TOPIC_KEYWORDS:
        if keyword in text_lower and not _has_relevant_context(text_lower):
            return GuardrailResult(
                False,
                f"I specialize in **refrigerator** and **dishwasher** parts only. "
                f"I can't help with {keyword}s, but I'd be happy to help if you have "
                f"a refrigerator or dishwasher question!"
            )

    return GuardrailResult(True)


def clean_output(text: str) -> str:
    """Clean the agent's output before sending to the user."""
    # Strip any accidentally leaked system/internal content
    text = re.sub(r"<\|.*?\|>", "", text)

    # Ensure product cards format is valid if present
    if "<<<PRODUCT_CARDS:" in text:
        try:
            start = text.index("<<<PRODUCT_CARDS:") + len("<<<PRODUCT_CARDS:")
            end = text.index(">>>", start)
            import json
            json.loads(text[start:end])  # validate JSON
        except (ValueError, json.JSONDecodeError):
            # Strip malformed product cards entirely
            text = re.sub(r"<<<PRODUCT_CARDS:.*?>>>", "", text, flags=re.DOTALL)

    return text.strip()


def _has_relevant_context(text: str) -> bool:
    """Check if a message mentioning off-topic appliances also has relevant context.
    e.g. 'I have a dishwasher and a microwave, the dishwasher won't drain' is valid.
    """
    relevant = ["refrigerator", "fridge", "dishwasher", "freezer", "ice maker"]
    return any(r in text for r in relevant)
