"""Thin async client for the MiMo OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "Usage | dict | None") -> None:  # noqa: UP037 (forward ref kept for clarity)
        if other is None:
            return
        if isinstance(other, dict):
            self.prompt_tokens += int(other.get("prompt_tokens", 0))
            self.completion_tokens += int(other.get("completion_tokens", 0))
            self.total_tokens += int(other.get("total_tokens", 0))
        else:
            self.prompt_tokens += other.prompt_tokens
            self.completion_tokens += other.completion_tokens
            self.total_tokens += other.total_tokens


class MimoClient:
    """Async client for MiMo / OpenAI-compatible Chat Completions.

    The MiMo platform exposes an OpenAI-compatible interface, so the request
    shape mirrors `POST /v1/chat/completions` exactly. Streaming is server-sent
    events (`data: {...}\\n\\n`) terminated by `data: [DONE]`.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.xiaomimimo.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "mimo-coder/0.1",
        }
        self._timeout = timeout

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if max_tokens:
            body["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base}/chat/completions",
                headers=self._headers,
                json=body,
            )
            r.raise_for_status()
            return r.json()

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[dict[str, Any]]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                "POST",
                f"{self._base}/chat/completions",
                headers=self._headers,
                json=body,
            ) as resp,
        ):
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[len("data:") :].strip()
                if payload == "[DONE]":
                    return
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue
