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

    def plan_query(
        self,
        *,
        message: str,
        language: str,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        catalog: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class GroqAssistantAIProvider(BaseAssistantAIProvider):
    provider_name = "groq"
    api_url = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        self.api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.model = (os.getenv("ASSISTANT_GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
        self.timeout_seconds = float(os.getenv("ASSISTANT_GROQ_TIMEOUT_SECONDS", "10"))

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

    def plan_query(
        self,
        *,
        message: str,
        language: str,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        catalog: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        history = history or []
        catalog = catalog or {}
        history_slice = history[-6:]

        category_slugs = catalog.get("category_slugs") or []
        entity_catalog = catalog.get("entities") or []

        catalog_block = ""
        if category_slugs:
            catalog_block += "\nAvailable category_hint values (closed list, pick one or null):\n"
            catalog_block += ", ".join(category_slugs) + "\n"
        if entity_catalog:
            catalog_block += (
                "\nKnown entities (use for resolved_entity_id when the user names one; "
                "match loosely across Latin/Cyrillic/English):\n"
            )
            catalog_block += "\n".join(
                f"- {item['type']}#{item['id']}: {item['title']}"
                + (f" / {item['title_mk']}" if item.get('title_mk') else "")
                for item in entity_catalog[:60]
            ) + "\n"

        system_prompt = (
            "You orchestrate the GoGevgelija in-app assistant. "
            "Your ONLY job is to understand the user and return structured fields. "
            "You never write user-facing answers — the backend does.\n\n"
            "Language handling:\n"
            "- Users may write Macedonian in Cyrillic (каде, музика), Latin-transliterated (kade, muzika), or English.\n"
            "- Latin-transliterated Macedonian examples: kade=where, da=to, jadam=eat, slusam=listen, vecherva=tonight, nastani=events.\n"
            "- When ambiguous between mk-latin and English, prefer mk-latin for tourism queries.\n"
            "- ALWAYS produce BOTH normalized_query_en and normalized_query_mk (Cyrillic) so the "
            "backend can search bilingual DB fields. Translate and transliterate as needed.\n\n"
            "Query extraction:\n"
            "- Users ask full questions, not keywords. Extract the core subject only.\n"
            "- Strip filler words (kade, where, najdi, find, мислам, please, ima, дали, some).\n"
            "- Example: 'Kade da slusam muzika vecheras?' -> normalized_query_en='live music tonight', "
            "normalized_query_mk='музика вечер', category_hint='nightlife' (or closest slug), "
            "entity_type_hint='event', time_filter='tonight'.\n\n"
            "Tool selection:\n"
            "- context: user refers to the entity already open on their screen (hours, phone, price, directions).\n"
            "- faq: app help (app language setting, wishlist, support, collaboration, currency, border cameras, guest/account).\n"
            "- category: 'show me restaurants', 'kade da jadam' — category discovery.\n"
            "- feed: generic overview of events / promotions / blogs without a specific entity in mind.\n"
            "- search: named entities, specific places, or any broad lookup not matching category/feed.\n"
            "- clarify: ONLY if the message is truly ambiguous and you cannot make a reasonable guess, "
            "OR if the message is a pure greeting with no query (hey, hi, hello, здраво, alo, hej, ej, yo).\n"
            "- Set content_type to 'all' when the user does not specify a content kind; otherwise pick the closest matching type.\n"
            "- Set clarification_question to null for every tool other than 'clarify'.\n\n"
            "Follow-up resolution:\n"
            "- If the user says 'it', 'that', 'ова', 'тоа', 'тие' and history contains a resolved entity, "
            "set followup_of_entity_id to its id.\n"
            "- Re-use the same tool as the prior turn if the follow-up is about the same entity.\n\n"
            "Filters:\n"
            "- time_filter: tonight|today|this_week|weekend|null — set whenever user mentions time.\n"
            "- price_filter: cheap|mid|premium|null — cheap means free entry or budget; premium means paid/upscale.\n"
            "- open_now_requested: true if user asks 'open now', 'otvoreno sega', 'raboti li', etc.\n\n"
            + catalog_block
        )

        messages = [
            {"role": "system", "content": system_prompt},
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
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "tool_query": {"type": "string"},
                "content_type": {
                    "type": "string",
                    "enum": ["all", "listings", "events", "promotions", "blogs"],
                },
                "detected_language": {
                    "type": "string",
                    "enum": ["en", "mk-cyrillic", "mk-latin", "unknown"],
                },
                "normalized_query_en": {"type": "string"},
                "normalized_query_mk": {"type": "string"},
                "category_hint": {"type": ["string", "null"]},
                "entity_type_hint": {
                    "type": ["string", "null"],
                    "enum": ["listing", "event", "promotion", "blog", None],
                },
                "resolved_entity_id": {"type": ["integer", "null"]},
                "resolved_entity_type": {
                    "type": ["string", "null"],
                    "enum": ["listing", "event", "promotion", "blog", None],
                },
                "time_filter": {
                    "type": ["string", "null"],
                    "enum": ["tonight", "today", "this_week", "weekend", None],
                },
                "price_filter": {
                    "type": ["string", "null"],
                    "enum": ["cheap", "mid", "premium", None],
                },
                "open_now_requested": {"type": "boolean"},
                "followup_of_entity_id": {"type": ["integer", "null"]},
                "clarification_question": {"type": ["string", "null"]},
            },
            "required": [
                "tool",
                "intent",
                "confidence",
                "tool_query",
                "content_type",
                "detected_language",
                "normalized_query_en",
                "normalized_query_mk",
                "category_hint",
                "entity_type_hint",
                "resolved_entity_id",
                "resolved_entity_type",
                "time_filter",
                "price_filter",
                "open_now_requested",
                "followup_of_entity_id",
                "clarification_question",
            ],
            "additionalProperties": False,
        }

        return self._chat_completion(messages=messages, schema_name="assistant_plan", schema=schema)


def get_assistant_ai_provider() -> BaseAssistantAIProvider | None:
    provider = (os.getenv("ASSISTANT_EXTERNAL_AI_PROVIDER") or "").strip().lower()
    if not provider:
        return None

    if provider == "groq":
        candidate = GroqAssistantAIProvider()
        return candidate if candidate.is_enabled() else None

    logger.warning("Unsupported assistant external AI provider '%s'; external AI disabled", provider)
    return None
