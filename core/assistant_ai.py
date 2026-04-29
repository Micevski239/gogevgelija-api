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
                "response_format": {"type": "json_object"},
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
            "- chat: greetings (hey, hi, hello, здраво, alo, hej), identity questions (who are you, what can you do, "
            "кој си ти, што можеш), general Gevgelija knowledge questions (history, geography, border, spa, lake), "
            "OR anything clearly out of scope (weather, sports, politics, non-Gevgelija topics).\n"
            "- clarify: ONLY if the message is truly ambiguous and you cannot make a reasonable guess.\n"
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
            + "\nYou MUST respond with a JSON object containing EXACTLY these fields:\n"
            '{"tool": "...", "intent": "...", "confidence": "high|medium|low", '
            '"tool_query": "...", "content_type": "all|listings|events|promotions|blogs", '
            '"detected_language": "en|mk-cyrillic|mk-latin|unknown", '
            '"normalized_query_en": "...", "normalized_query_mk": "...", '
            '"category_hint": "...or null", "entity_type_hint": "listing|event|promotion|blog|null", '
            '"resolved_entity_id": null, "resolved_entity_type": null, '
            '"time_filter": "tonight|today|this_week|weekend|null", '
            '"price_filter": "cheap|mid|premium|null", '
            '"open_now_requested": false, "followup_of_entity_id": null, '
            '"clarification_question": "...or null"}\n'
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
                    "enum": ["context", "faq", "category", "feed", "search", "chat", "clarify"],
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

    def generate_greeting(
        self,
        *,
        language: str,
        events: list[dict],
        promotions: list[dict],
    ) -> str | None:
        events_block = ""
        if events:
            events_block = "Upcoming events:\n" + "\n".join(
                f"- {e['title']}: {e['date_time']}"
                + (f" (entry: {e['entry_price']})" if e.get("entry_price") and e["entry_price"] != "Free" else " (free entry)")
                for e in events
            )
        promos_block = ""
        if promotions:
            promos_block = "Active promotions:\n" + "\n".join(
                f"- {p['title']}"
                + (f" (valid until {p['valid_until']})" if p.get("valid_until") else "")
                for p in promotions
            )

        context_block = "\n\n".join(filter(None, [events_block, promos_block]))
        if not context_block:
            return None

        lang_instruction = (
            "Respond in Macedonian using Cyrillic script." if language == "mk"
            else "Respond in English."
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a friendly local concierge for GoGevgelija, a tourism app for Gevgelija, North Macedonia. "
                    "Write a warm, natural 1-2 sentence greeting for a tourist just opening the app. "
                    "Mention 1-2 specific things from the provided data. "
                    "Be conversational — like a local friend, not a corporate announcement. "
                    "No generic phrases like 'Welcome to the app'. "
                    "Return JSON with a single key: {\"greeting\": \"...\"}. "
                    f"{lang_instruction}"
                ),
            },
            {
                "role": "user",
                "content": f"Write a greeting based on this:\n\n{context_block}",
            },
        ]

        result = self._chat_completion(
            messages=messages,
            schema_name="greeting",
            schema={
                "type": "object",
                "properties": {"greeting": {"type": "string"}},
                "required": ["greeting"],
                "additionalProperties": False,
            },
        )
        return result.get("greeting") or None

    def generate_display_message(
        self,
        *,
        user_message: str,
        language: str,
        tool: str,
        results_summary: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        if not self.is_enabled():
            raise AssistantAIError("Groq provider is not configured")

        history = history or []
        history_slice = history[-4:]

        system_prompt = (
            "You are GoAI, Your GoGevgelija Guide — the friendly AI assistant inside the GoGevgelija "
            "tourism discovery app for Gevgelija, North Macedonia.\n\n"
            "About Gevgelija:\n"
            "- City in southern North Macedonia, on the Greek border (Bogorodica/Gevgelija crossing)\n"
            "- Known for: Negorci thermal spa, Lake Dojran (25 km east), Vardar river, "
            "warm climate, wine culture, close to Thessaloniki (~70 km)\n"
            "- Popular with Greek day-trippers and regional tourists\n\n"
            "About the app:\n"
            "- GoGevgelija lists: restaurants, cafes, hotels, nightlife, services (Listings), "
            "upcoming events, active promotions/deals, travel blogs\n"
            "- You ONLY reference real data provided to you — never invent place names, prices, or hours\n\n"
            "Response rules:\n"
            "- Be friendly, warm, and SHORT: 1-3 sentences maximum\n"
            "- Match the user's language exactly: Macedonian message → Macedonian Cyrillic reply; English → English\n"
            "- If DB results were provided: mention 1-2 place names naturally, say the cards below show full details\n"
            "- If no results: honestly say you don't have that in the database right now\n"
            "- Greetings (hey/hi/здраво): say hi back, introduce yourself as GoAI, offer to help find places/events/deals\n"
            "- Identity (who are you / кој си): explain you are GoAI, the GoGevgelija assistant; "
            "you help tourists find restaurants, hotels, events, promotions, and local guides in Gevgelija\n"
            "- Out-of-scope (weather, sports, politics, non-Gevgelija): politely say you only know Gevgelija "
            "and offer to help with tourism instead\n"
            "- Never use bullet points or markdown — plain conversational text only\n"
        )

        user_parts = [f"User message: {user_message}"]
        if results_summary:
            user_parts.append(f"Database results:\n{results_summary}")
        user_parts.append("Write your short, friendly response now.")

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for h in history_slice:
            role = h.get("role") or "user"
            content = h.get("content") or h.get("text") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0.5,
                "messages": messages,
                "max_tokens": 140,
            },
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            logger.warning("GoAI display message call failed: status=%s body=%s", response.status_code, response.text[:400])
            raise AssistantAIError(f"GoAI display message call failed with status {response.status_code}")

        try:
            payload = response.json()
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AssistantAIError("GoAI display message response was not valid") from exc


def get_assistant_ai_provider() -> BaseAssistantAIProvider | None:
    provider = (os.getenv("ASSISTANT_EXTERNAL_AI_PROVIDER") or "").strip().lower()
    if not provider:
        return None

    if provider == "groq":
        candidate = GroqAssistantAIProvider()
        return candidate if candidate.is_enabled() else None

    logger.warning("Unsupported assistant external AI provider '%s'; external AI disabled", provider)
    return None
