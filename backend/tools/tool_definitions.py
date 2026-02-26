"""Tool definitions and execution for the chat agent.

Tools are grouped by specialist so each agent only sees the tools it needs.
The execute_tool() function handles all tools regardless of group.
"""
import json
from data.database import (
    search_parts, get_part_by_ps, check_compatibility,
    get_model_info, find_troubleshooting_guide,
    get_installation_guide, lookup_order,
)
from data.vector_store import get_vector_store


# -- Tool Schemas (grouped by specialist) --

_SEARCH_PRODUCTS = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": (
            "Search for refrigerator or dishwasher replacement parts by keyword, "
            "part number, symptom, or description."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PS number, part name, symptom, or natural language",
                },
                "category": {
                    "type": "string",
                    "enum": ["refrigerator", "dishwasher"],
                    "description": "Optional: filter by appliance type",
                },
            },
            "required": ["query"],
        },
    },
}

_CHECK_COMPATIBILITY = {
    "type": "function",
    "function": {
        "name": "check_compatibility",
        "description": "Check if a specific part is compatible with a specific appliance model.",
        "parameters": {
            "type": "object",
            "properties": {
                "ps_number": {"type": "string", "description": "e.g. 'PS11752778'"},
                "model_number": {"type": "string", "description": "e.g. 'WDT780SAEM1'"},
            },
            "required": ["ps_number", "model_number"],
        },
    },
}

_GET_MODEL_INFO = {
    "type": "function",
    "function": {
        "name": "get_model_info",
        "description": "Get information about an appliance model and all its compatible parts.",
        "parameters": {
            "type": "object",
            "properties": {
                "model_number": {"type": "string", "description": "e.g. 'WDT780SAEM1'"},
            },
            "required": ["model_number"],
        },
    },
}

_GET_TROUBLESHOOTING = {
    "type": "function",
    "function": {
        "name": "get_troubleshooting_guide",
        "description": "Get a troubleshooting guide for a specific appliance problem or symptom.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["refrigerator", "dishwasher"],
                    "description": "Appliance type",
                },
                "symptom": {
                    "type": "string",
                    "description": "e.g. 'ice maker not working' or 'not draining'",
                },
            },
            "required": ["category", "symptom"],
        },
    },
}

_GET_INSTALLATION = {
    "type": "function",
    "function": {
        "name": "get_installation_guide",
        "description": "Get step-by-step installation instructions for a specific part.",
        "parameters": {
            "type": "object",
            "properties": {
                "ps_number": {"type": "string", "description": "PS number of the part"},
            },
            "required": ["ps_number"],
        },
    },
}

_LOOKUP_ORDER = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": "Look up an order by order ID to check status, tracking, and details.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "e.g. 'ORD-2024-78432'"},
            },
            "required": ["order_id"],
        },
    },
}

# Grouped for specialists
PRODUCT_TOOLS = [_SEARCH_PRODUCTS, _CHECK_COMPATIBILITY, _GET_MODEL_INFO]
REPAIR_TOOLS = [_GET_TROUBLESHOOTING, _GET_INSTALLATION, _SEARCH_PRODUCTS]
ORDER_TOOLS = [_LOOKUP_ORDER]

# All tools (for backward compat, if needed)
ALL_TOOLS = [_SEARCH_PRODUCTS, _CHECK_COMPATIBILITY, _GET_TROUBLESHOOTING,
             _GET_INSTALLATION, _LOOKUP_ORDER, _GET_MODEL_INFO]

# Fields we include in part responses
_PART_FIELDS = [
    "ps_number", "name", "manufacturer_part", "price", "category",
    "brand", "in_stock", "rating", "review_count",
    "installation_difficulty", "url",
]


def _format_part(part: dict) -> dict:
    out = {k: part.get(k, "") for k in _PART_FIELDS}
    out["description"] = (part.get("description") or "")[:200]
    return out


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name and return JSON."""

    if name == "search_products":
        query = arguments.get("query", "")
        category = arguments.get("category")

        sql_results = search_parts(query, category=category, limit=5)
        try:
            semantic_results = get_vector_store().search_products(
                query, category=category, n_results=5
            )
        except Exception:
            semantic_results = []

        seen = {r["ps_number"] for r in sql_results}
        merged = [_format_part(r) for r in sql_results]
        for sr in semantic_results:
            if sr["ps_number"] not in seen:
                full = get_part_by_ps(sr["ps_number"])
                if full:
                    merged.append(_format_part(full))
                    seen.add(sr["ps_number"])

        return json.dumps({"results": merged[:10], "count": len(merged[:10])})

    if name == "check_compatibility":
        result = check_compatibility(
            arguments.get("ps_number", ""), arguments.get("model_number", "")
        )
        if result.get("part"):
            result["part"] = _format_part(result["part"])
        return json.dumps(result)

    if name == "get_troubleshooting_guide":
        category = arguments.get("category", "")
        symptom = arguments.get("symptom", "")
        guide = find_troubleshooting_guide(category, symptom)

        if not guide:
            try:
                hits = get_vector_store().search_guides(symptom, category=category, n_results=1)
                if hits:
                    guide = find_troubleshooting_guide(category, hits[0].get("problem_key", ""))
            except Exception:
                pass

        if guide:
            if guide.get("recommended_parts"):
                guide["recommended_parts"] = [_format_part(p) for p in guide["recommended_parts"]]
            return json.dumps(guide)

        return json.dumps({
            "error": f"No guide found for '{symptom}' in {category}",
            "suggestion": "Try a specific symptom like 'not cooling', 'not draining', or 'leaking'.",
        })

    if name == "get_installation_guide":
        ps = arguments.get("ps_number", "")
        guide = get_installation_guide(ps)
        if guide:
            return json.dumps(guide)
        part = get_part_by_ps(ps)
        if part:
            return json.dumps({
                "error": f"No installation guide for {ps}",
                "part": _format_part(part),
                "suggestion": f"Check the product page: {part.get('url', '')}",
            })
        return json.dumps({"error": f"Part {ps} not found"})

    if name == "lookup_order":
        order = lookup_order(arguments.get("order_id", ""))
        if order:
            return json.dumps(order)
        return json.dumps({
            "error": "Order not found",
            "suggestion": "Check the order ID format: ORD-YYYY-XXXXX",
        })

    if name == "get_model_info":
        model = get_model_info(arguments.get("model_number", ""))
        if model:
            if model.get("compatible_parts"):
                model["compatible_parts"] = [_format_part(p) for p in model["compatible_parts"]]
            return json.dumps(model)
        return json.dumps({
            "error": "Model not found",
            "suggestion": "Check the model number - usually on a sticker inside the appliance door.",
        })

    return json.dumps({"error": f"Unknown tool: {name}"})
