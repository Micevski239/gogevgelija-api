import json
import logging
import os
from typing import Any

import requests


logger = logging.getLogger(__name__)


class AssistantAIError(Exception):
    pass


def _strict_json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


class BaseAssistantAIProvider:
    provider_name = "base"

    def is_enabled(self) -> bool:
        return False

    def plan_query(self, *, message: str, language: str, context: dict[str, Any] | None = None, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def compose_answer(
        self,
        *,
        message: str,
        language: str,
        context: dict[str, Any] | None,
        plan: dict[str, Any],
        tool_response: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError


class GroqAssistantAIProvider(BaseAssistantAIProvider):
    provider_name = "groq"
    api_url = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        self.api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.model = (os.getenv("ASSISTANT_GROQ_MODEL") or "openai/gpt-oss-20b").strip()
        self.timeout_seconds = float(os.getenv("ASSISTANT_GROQ_TIMEOUT_SECONDS", "20"))

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def _chat_completion(self, *, messages: list[dict[str, str]], schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
        if not self.is_enabled():
            raise AssistantAIError("Groq provider is not configured")

        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0.1,
                "messages": messages,
                "response_format": _strict_json_schema(schema_name, schema),
            },
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            logger.warning("Groq assistant call failed: status=%s body=%s", response.status_code, response.text[:800])
            raise AssistantAIError(f"Groq assistant call failed with status {response.status_code}")

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AssistantAIError("Groq assistant response was not valid structured JSON") from exc

    def plan_query(self, *, message: str, language: str, context: dict[str, Any] | None = None, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        context = context or {}
        history = history or []
        history_slice = history[-6:]

        messages = [
            {
                "role": "system",
                "content": (
                    "You orchestrate the GoGevgelija in-app assistant. "
                    "Choose exactly one backend tool. Never answer from general knowledge. "
                    "Use context when the user refers to the current screen item. "
                    "Prefer search when in doubt, and clarify only when absolutely needed.\n\n"
                    "Available tools:\n"
                    "- context: current listing/event/promotion/blog already open in the app. tool_query should be short keywords like "
                    "'open hours', 'call phone', 'discount code', 'summary', 'directions', 'events', 'promotions', 'price', 'age limit', 'where use', 'related link'.\n"
                    "- faq: app help like language, wishlist, support, collaboration, currency, border cameras, guest/account.\n"
                    "- category: listing discovery for accommodation, food, dental, fuel, services.\n"
                    "- feed: general overview for events, promotions, or blogs.\n"
                    "- search: named entities or broad lookup against app content.\n"
                    "- clarify: ask a short clarification question if intent is too ambiguous.\n\n"
                    "Return compact tool_query values. Use the user's language."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": message,
                        "language": language,
                        "context": context,
                        "history": history_slice,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        schema = {
            "type": "object",
            "properties": {
                "tool": {
                    "type": "string",
                    "enum": ["context", "faq", "category", "feed", "search", "clarify"],
                },
                "intent": {"type": "string"},
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                },
                "tool_query": {"type": "string"},
                "content_type": {
                    "type": "string",
                    "enum": ["all", "listings", "events", "promotions", "blogs"],
                },
                "clarification_question": {"type": ["string", "null"]},
            },
            "required": ["tool", "intent", "confidence", "tool_query", "content_type", "clarification_question"],
            "additionalProperties": False,
        }

        return self._chat_completion(messages=messages, schema_name="assistant_plan", schema=schema)

    def compose_answer(
        self,
        *,
        message: str,
        language: str,
        context: dict[str, Any] | None,
        plan: dict[str, Any],
        tool_response: dict[str, Any],
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You write the final answer for the GoGevgelija in-app assistant. "
                    "Use only the provided tool result. Do not invent facts. "
                    "If unsupported filters are present, say so clearly and keep the answer helpful. "
                    "Keep the answer concise, natural, and in the user's language. "
                    "Suggestions should be short follow-up prompts."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": message,
                        "language": language,
                        "context": context or {},
                        "plan": plan,
                        "tool_response": tool_response,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["answer", "suggestions"],
            "additionalProperties": False,
        }

        return self._chat_completion(messages=messages, schema_name="assistant_answer", schema=schema)


def get_assistant_ai_provider() -> BaseAssistantAIProvider | None:
    provider = (os.getenv("ASSISTANT_EXTERNAL_AI_PROVIDER") or "").strip().lower()
    if not provider:
        return None

    if provider == "groq":
        candidate = GroqAssistantAIProvider()
        return candidate if candidate.is_enabled() else None

    logger.warning("Unsupported assistant external AI provider '%s'; external AI disabled", provider)
    return None
