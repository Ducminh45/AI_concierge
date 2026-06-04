"""Unified interface for multiple LLM providers with automatic fallback routing."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from ..monitoring.logging_utils import logger


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: List[LLMToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None


@dataclass
class LLMResponse:
    content: str
    tool_calls: List[LLMToolCall] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[dict]] = None,
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def translate_tool_schemas(self, openai_schemas: List[dict]) -> List[dict]:
        """Convert OpenAI-format tool schemas to this provider's format."""
        ...

    @property
    def supports_response_format(self) -> bool:
        """Whether this provider supports native response_format parameter."""
        return False

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        import openai

        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model
        self._provider_name = "openrouter" if base_url else "openai"
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def supports_response_format(self) -> bool:
        return True

    def translate_tool_schemas(self, openai_schemas: List[dict]) -> List[dict]:
        return openai_schemas

    def _to_openai_messages(self, messages: List[LLMMessage]) -> List[dict]:
        out = []
        for m in messages:
            msg: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            out.append(msg)
        return out

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[dict]] = None,
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> LLMResponse:
        kwargs: Dict[str, Any] = {
            "model": model or self._model,
            "messages": self._to_openai_messages(messages),
        }
        if tools:
            kwargs["tools"] = self.translate_tool_schemas(tools)
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens

        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        tool_calls = []
        if getattr(msg, "tool_calls", None):
            tool_calls = [
                LLMToolCall(
                    id=tc.id, name=tc.function.name, arguments=tc.function.arguments
                )
                for tc in msg.tool_calls
            ]

        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }

        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            model=resp.model,
            provider=self._provider_name,
            usage=usage,
        )


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return "anthropic"

    def translate_tool_schemas(self, openai_schemas: List[dict]) -> List[dict]:
        """Convert OpenAI tool schemas to Anthropic format."""
        anthropic_tools = []
        for schema in openai_schemas:
            fn = schema.get("function", {})
            anthropic_tools.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get(
                        "parameters", {"type": "object", "properties": {}}
                    ),
                }
            )
        return anthropic_tools

    def _to_anthropic_messages(
        self, messages: List[LLMMessage]
    ) -> tuple[str, List[dict]]:
        """Extract system message and convert to Anthropic message format."""
        system_text = ""
        anthropic_msgs = []

        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
                continue

            if m.role == "tool":
                anthropic_msgs.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id or "",
                                "content": m.content,
                            }
                        ],
                    }
                )
                continue

            if m.role == "assistant" and m.tool_calls:
                content_blocks: List[dict] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": json.loads(tc.arguments),
                        }
                    )
                anthropic_msgs.append({"role": "assistant", "content": content_blocks})
                continue

            anthropic_msgs.append({"role": m.role, "content": m.content})

        return system_text.strip(), anthropic_msgs

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[dict]] = None,
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> LLMResponse:
        system_text, anthropic_msgs = self._to_anthropic_messages(messages)

        kwargs: Dict[str, Any] = {
            "model": model or self._model,
            "max_tokens": 4096,
            "messages": anthropic_msgs,
        }
        if system_text:
            # Prompt caching: reduces latency/cost on multi-turn conversations
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        if tools:
            kwargs["tools"] = self.translate_tool_schemas(tools)
        # Anthropic does not support response_format; parameter is accepted
        # for interface compatibility but ignored.

        resp = await self._client.messages.create(**kwargs)

        content_text = ""
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    LLMToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
                "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
            }
            # Track prompt cache metrics when available
            cache_creation = getattr(resp.usage, "cache_creation_input_tokens", 0)
            cache_read = getattr(resp.usage, "cache_read_input_tokens", 0)
            if cache_creation or cache_read:
                usage["cache_creation_tokens"] = cache_creation
                usage["cache_read_tokens"] = cache_read

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            model=resp.model,
            provider="anthropic",
            usage=usage,
        )


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = httpx.AsyncClient(timeout=120.0)

    @property
    def name(self) -> str:
        return "ollama"

    def translate_tool_schemas(self, openai_schemas: List[dict]) -> List[dict]:
        return openai_schemas  # Ollama uses OpenAI-compatible format

    def _to_ollama_messages(self, messages: List[LLMMessage]) -> List[dict]:
        out = []
        for m in messages:
            msg: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            out.append(msg)
        return out

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[dict]] = None,
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": model or self._model,
            "messages": self._to_ollama_messages(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = self.translate_tool_schemas(tools)
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"

        resp = await self._http.post(f"{self._base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message", {})
        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            tool_calls.append(
                LLMToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=(
                        json.dumps(fn.get("arguments", {}))
                        if isinstance(fn.get("arguments"), dict)
                        else fn.get("arguments", "{}")
                    ),
                )
            )

        return LLMResponse(
            content=msg.get("content", ""),
            tool_calls=tool_calls,
            model=payload["model"],
            provider="ollama",
            usage={},
        )


class ModelRouter:
    def __init__(self, providers: List[LLMProvider], fallback_enabled: bool = True):
        self.providers = providers
        self.fallback_enabled = fallback_enabled

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[dict]] = None,
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> LLMResponse:
        last_error: Optional[Exception] = None

        for provider in self.providers:
            try:
                logger.info(f"Trying LLM provider: {provider.name}")
                response = await provider.chat(messages, tools, model, response_format)
                logger.info(f"LLM provider {provider.name} succeeded")
                return response
            except Exception as e:
                last_error = e
                logger.warning(f"LLM provider {provider.name} failed: {e}")
                if not self.fallback_enabled:
                    raise

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")
