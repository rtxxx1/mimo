"""The agent loop.

Pattern: classic ReAct-with-tools.

  1. Send messages + tool schemas to MiMo.
  2. If the assistant message has `tool_calls`, run each tool, append the
     results as `role=tool` messages, loop.
  3. If the assistant message is plain text, that's the final answer.
  4. Cap iterations at `max_turns`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .client import MimoClient, Usage
from .tools import TOOL_SCHEMAS, ToolBox


@dataclass(slots=True)
class Turn:
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass(slots=True)
class AgentState:
    messages: list[Turn] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    turns: int = 0


class Agent:
    def __init__(
        self,
        client: MimoClient,
        toolbox: ToolBox,
        *,
        model: str,
        system: str,
        temperature: float = 0.2,
        max_turns: int = 12,
    ) -> None:
        self.client = client
        self.tools = toolbox
        self.model = model
        self.temperature = temperature
        self.max_turns = max_turns
        self.state = AgentState(messages=[Turn("system", content=system)])

    # ------------------------------------------------------------------

    def add_user(self, text: str) -> None:
        self.state.messages.append(Turn("user", content=text))

    async def run(self, on_event: Callable[[str, dict], None] | None = None) -> str:
        """Run the agent loop until a final assistant message lands.

        `on_event(kind, payload)` is invoked for UI hooks:
          - "assistant_text" {"text": str}
          - "tool_call"      {"name": str, "args": dict}
          - "tool_result"    {"name": str, "ok": bool, "output": str}
          - "usage"          {"prompt": int, "completion": int}
        """
        emit = on_event or (lambda *_: None)

        for _ in range(self.max_turns):
            self.state.turns += 1
            resp = await self.client.chat(
                model=self.model,
                messages=[m.to_openai() for m in self.state.messages],
                tools=TOOL_SCHEMAS,
                temperature=self.temperature,
            )
            self.state.usage.add(resp.get("usage"))
            emit(
                "usage",
                {
                    "prompt": resp.get("usage", {}).get("prompt_tokens", 0),
                    "completion": resp.get("usage", {}).get("completion_tokens", 0),
                },
            )

            choice = resp["choices"][0]["message"]
            tool_calls = choice.get("tool_calls") or []
            content = choice.get("content")

            self.state.messages.append(
                Turn(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls or None,
                )
            )

            if not tool_calls:
                emit("assistant_text", {"text": content or ""})
                return content or ""

            for call in tool_calls:
                fn = call["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                emit("tool_call", {"name": name, "args": args})
                result = self.tools.call(name, args)
                emit(
                    "tool_result",
                    {"name": name, "ok": result.ok, "output": result.output[:2000]},
                )
                self.state.messages.append(
                    Turn(
                        role="tool",
                        content=result.to_message_content(),
                        tool_call_id=call["id"],
                        name=name,
                    )
                )

        # max_turns hit
        msg = "(stopped: max_turns reached)"
        self.state.messages.append(Turn("assistant", content=msg))
        emit("assistant_text", {"text": msg})
        return msg
