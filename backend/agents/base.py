"""Base specialist agent with streaming function-calling loop."""

import json
from openai import OpenAI


class SpecialistAgent:
    """Base class for specialist agents. Each specialist has a system prompt
    and a set of tools it can call."""

    def __init__(self, client: OpenAI, system_prompt: str, tools: list[dict],
                 model: str = "gpt-4o"):
        self.client = client
        self.system_prompt = system_prompt
        self.tools = tools
        self.model = model

    def run(self, messages: list[dict], tool_executor, max_turns: int = 5) -> str:
        """Run the agent loop: call GPT, execute tools, repeat until text response."""
        full = [{"role": "system", "content": self.system_prompt}] + messages

        for _ in range(max_turns):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=full,
                tools=self.tools if self.tools else None,
                tool_choice="auto" if self.tools else None,
                temperature=0.7,
                max_tokens=2000,
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                return msg.content or ""

            # Append tool calls and execute them
            full.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = tool_executor(tc.function.name, args)
                full.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return "I'm having trouble processing that. Could you try rephrasing?"

    def stream(self, messages: list[dict], tool_executor, max_turns: int = 5):
        """Like run(), but yields tokens as they arrive.

        During tool-calling turns, yields nothing (tools run silently).
        On the final text turn, yields each token chunk.
        """
        full = [{"role": "system", "content": self.system_prompt}] + messages

        for _ in range(max_turns):
            # First, check if we need tool calls (non-streaming probe)
            probe = self.client.chat.completions.create(
                model=self.model,
                messages=full,
                tools=self.tools if self.tools else None,
                tool_choice="auto" if self.tools else None,
                temperature=0.7,
                max_tokens=2000,
            )
            probe_msg = probe.choices[0].message

            if probe_msg.tool_calls:
                # Execute tools silently
                full.append({
                    "role": "assistant",
                    "content": probe_msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in probe_msg.tool_calls
                    ],
                })
                for tc in probe_msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    result = tool_executor(tc.function.name, args)
                    full.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            # No tool calls - stream the final response
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=full,
                tools=self.tools if self.tools else None,
                temperature=0.7,
                max_tokens=2000,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
            return

        yield "I'm having trouble processing that. Could you try rephrasing?"
