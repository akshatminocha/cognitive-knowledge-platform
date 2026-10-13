"""
Model Adapters — Provider-specific message format serializers.

Converts canonical messages (CanonicalMessage) to and from provider-specific
formats: Gemini, OpenAI, Anthropic, Ollama.

This is what enables mid-session model switching — the ContextEngine stores
messages in canonical format, and the adapter converts them on-the-fly.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from agent_harness.context_engine import CanonicalMessage, Role

logger = logging.getLogger(__name__)


class ModelAdapter(ABC):
    """
    Base class for provider-specific message format adapters.

    Subclasses implement to_provider_format() and from_provider_format()
    to convert between CanonicalMessage and the provider's native format.
    """

    provider_name: str = "base"

    @abstractmethod
    def to_provider_format(self, messages: list[CanonicalMessage]) -> list[dict]:
        """Convert canonical messages to the provider's native format."""
        ...

    @abstractmethod
    def from_provider_format(self, messages: list[dict]) -> list[CanonicalMessage]:
        """Convert provider-native messages back to canonical format."""
        ...


class GeminiAdapter(ModelAdapter):
    """
    Adapter for Google Gemini / Google AI / Vertex AI.

    Gemini uses 'user' and 'model' roles with 'parts' containing text.
    System instructions are passed separately in the API call.
    """

    provider_name = "gemini"

    def to_provider_format(self, messages: list[CanonicalMessage]) -> list[dict]:
        """Convert to Gemini's content format."""
        result = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                # Gemini handles system instructions separately
                continue

            role = "model" if msg.role == Role.ASSISTANT else "user"

            if msg.role == Role.TOOL_CALL:
                result.append({
                    "role": "model",
                    "parts": [{
                        "function_call": {
                            "name": msg.tool_name,
                            "args": msg.tool_input or {},
                        }
                    }],
                })
            elif msg.role == Role.TOOL_RESULT:
                result.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": msg.tool_name,
                            "response": {"result": msg.tool_output},
                        }
                    }],
                })
            else:
                result.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })

        return result

    def get_system_instruction(self, messages: list[CanonicalMessage]) -> str | None:
        """Extract system instruction from canonical messages."""
        for msg in messages:
            if msg.role == Role.SYSTEM:
                return msg.content
        return None

    def from_provider_format(self, messages: list[dict]) -> list[CanonicalMessage]:
        """Convert Gemini format back to canonical."""
        result = []
        for msg in messages:
            role_str = msg.get("role", "user")
            parts = msg.get("parts", [])

            role = Role.ASSISTANT if role_str == "model" else Role.USER

            for part in parts:
                if "text" in part:
                    result.append(CanonicalMessage(role=role, content=part["text"]))
                elif "function_call" in part:
                    fc = part["function_call"]
                    result.append(CanonicalMessage(
                        role=Role.TOOL_CALL,
                        content="",
                        tool_name=fc.get("name"),
                        tool_input=fc.get("args"),
                    ))
                elif "function_response" in part:
                    fr = part["function_response"]
                    result.append(CanonicalMessage(
                        role=Role.TOOL_RESULT,
                        content="",
                        tool_name=fr.get("name"),
                        tool_output=fr.get("response", {}).get("result"),
                    ))

        return result


class OpenAIAdapter(ModelAdapter):
    """
    Adapter for OpenAI API (GPT-4o, GPT-4, etc.).

    OpenAI uses 'system', 'user', 'assistant', 'tool' roles
    with 'content' and optional 'tool_calls'.
    """

    provider_name = "openai"

    def to_provider_format(self, messages: list[CanonicalMessage]) -> list[dict]:
        """Convert to OpenAI's chat completion format."""
        result = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                result.append({"role": "system", "content": msg.content})
            elif msg.role == Role.USER:
                result.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                result.append({"role": "assistant", "content": msg.content})
            elif msg.role == Role.TOOL_CALL:
                result.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": msg.tool_call_id or msg.message_id,
                        "type": "function",
                        "function": {
                            "name": msg.tool_name,
                            "arguments": str(msg.tool_input or {}),
                        },
                    }],
                })
            elif msg.role == Role.TOOL_RESULT:
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or msg.message_id,
                    "content": str(msg.tool_output),
                })

        return result

    def from_provider_format(self, messages: list[dict]) -> list[CanonicalMessage]:
        """Convert OpenAI format back to canonical."""
        result = []
        for msg in messages:
            role_str = msg.get("role", "user")
            content = msg.get("content", "")

            if role_str == "system":
                result.append(CanonicalMessage(role=Role.SYSTEM, content=content or ""))
            elif role_str == "user":
                result.append(CanonicalMessage(role=Role.USER, content=content or ""))
            elif role_str == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        result.append(CanonicalMessage(
                            role=Role.TOOL_CALL,
                            content="",
                            tool_name=tc["function"]["name"],
                            tool_input=tc["function"].get("arguments"),
                            tool_call_id=tc.get("id"),
                        ))
                else:
                    result.append(CanonicalMessage(
                        role=Role.ASSISTANT, content=content or ""
                    ))
            elif role_str == "tool":
                result.append(CanonicalMessage(
                    role=Role.TOOL_RESULT,
                    content="",
                    tool_output=content,
                    tool_call_id=msg.get("tool_call_id"),
                ))

        return result


class AnthropicAdapter(ModelAdapter):
    """
    Adapter for Anthropic API (Claude).

    Anthropic uses 'user' and 'assistant' roles.
    System prompts are passed as a top-level parameter.
    Tool use follows their specific content block format.
    """

    provider_name = "anthropic"

    def to_provider_format(self, messages: list[CanonicalMessage]) -> list[dict]:
        """Convert to Anthropic's messages format."""
        result = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                # Anthropic handles system separately
                continue
            elif msg.role == Role.USER:
                result.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                result.append({"role": "assistant", "content": msg.content})
            elif msg.role == Role.TOOL_CALL:
                result.append({
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": msg.tool_call_id or msg.message_id,
                        "name": msg.tool_name,
                        "input": msg.tool_input or {},
                    }],
                })
            elif msg.role == Role.TOOL_RESULT:
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or msg.message_id,
                        "content": str(msg.tool_output),
                    }],
                })

        return result

    def get_system_prompt(self, messages: list[CanonicalMessage]) -> str | None:
        """Extract system prompt for Anthropic's top-level parameter."""
        for msg in messages:
            if msg.role == Role.SYSTEM:
                return msg.content
        return None

    def from_provider_format(self, messages: list[dict]) -> list[CanonicalMessage]:
        """Convert Anthropic format back to canonical."""
        result = []
        for msg in messages:
            role_str = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, str):
                role = Role.USER if role_str == "user" else Role.ASSISTANT
                result.append(CanonicalMessage(role=role, content=content))
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        role = Role.USER if role_str == "user" else Role.ASSISTANT
                        result.append(CanonicalMessage(
                            role=role, content=block.get("text", "")
                        ))
                    elif block.get("type") == "tool_use":
                        result.append(CanonicalMessage(
                            role=Role.TOOL_CALL,
                            content="",
                            tool_name=block.get("name"),
                            tool_input=block.get("input"),
                            tool_call_id=block.get("id"),
                        ))
                    elif block.get("type") == "tool_result":
                        result.append(CanonicalMessage(
                            role=Role.TOOL_RESULT,
                            content="",
                            tool_output=block.get("content"),
                            tool_call_id=block.get("tool_use_id"),
                        ))

        return result


class OllamaAdapter(ModelAdapter):
    """
    Adapter for Ollama local models.

    Ollama follows OpenAI-compatible format with
    'system', 'user', 'assistant' roles.
    """

    provider_name = "ollama"

    def to_provider_format(self, messages: list[CanonicalMessage]) -> list[dict]:
        """Convert to Ollama's chat format (OpenAI-compatible)."""
        result = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                result.append({"role": "system", "content": msg.content})
            elif msg.role == Role.USER:
                result.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                result.append({"role": "assistant", "content": msg.content})
            elif msg.role in (Role.TOOL_CALL, Role.TOOL_RESULT):
                # Ollama has limited tool support — serialize as assistant/user text
                if msg.role == Role.TOOL_CALL:
                    result.append({
                        "role": "assistant",
                        "content": f"[Tool Call: {msg.tool_name}({msg.tool_input})]",
                    })
                else:
                    result.append({
                        "role": "user",
                        "content": f"[Tool Result: {msg.tool_output}]",
                    })

        return result

    def from_provider_format(self, messages: list[dict]) -> list[CanonicalMessage]:
        """Convert Ollama format back to canonical."""
        result = []
        for msg in messages:
            role_map = {"system": Role.SYSTEM, "user": Role.USER, "assistant": Role.ASSISTANT}
            role = role_map.get(msg.get("role", "user"), Role.USER)
            result.append(CanonicalMessage(role=role, content=msg.get("content", "")))
        return result


# ---------------------------------------------------------------------------
# Adapter Registry
# ---------------------------------------------------------------------------
ADAPTERS: dict[str, ModelAdapter] = {
    "gemini": GeminiAdapter(),
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
    "ollama": OllamaAdapter(),
}


def get_adapter(provider: str) -> ModelAdapter:
    """Get a model adapter by provider name."""
    adapter = ADAPTERS.get(provider.lower())
    if not adapter:
        raise ValueError(
            f"Unknown provider: '{provider}'. "
            f"Available: {list(ADAPTERS.keys())}"
        )
    return adapter
