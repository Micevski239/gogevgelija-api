# Proactive Assistant Greeting — Design Spec

**Date:** 2026-04-29  
**Scope:** Mobile API (Django) + Mobile Frontend (React Native)

---

## Problem

The Assistant screen opens to a static i18n string. Tourists don't know what to ask and often close it. Time-sensitive information (tonight's events, expiring deals) exists in the system but is never surfaced proactively.

## Solution

On AssistantScreen mount, fetch an AI-generated greeting that mentions what is actually happening in Gevgelija today. The greeting is written by Groq using live event and promotion data. A typing indicator plays while it loads; the static welcome is the fallback if anything fails.

---

## Backend

### New endpoint

```
GET /api/assistant/greeting/
```

- Permission: `AllowAny` (same as `AssistantQueryView`)
- Language: resolved from `Accept-Language` header via existing `get_preferred_language(request)`

### Data fetched

- **Events:** `is_active=True`, `date_time` date = today (local server date), ordered by `date_time`, limit 2
- **Promotions:** `is_active=True`, not expired (`valid_until` is null or ≥ today), ordered by `valid_until` asc, limit 2

### Groq prompt

System prompt instructs Groq to act as a friendly local concierge for GoGevgelija. User prompt passes the fetched data as a short structured summary and asks for a warm 2-sentence greeting in the correct language (en or mk) that mentions the specific items. No filler, no "Welcome to the app" boilerplate.

Uses the existing `GroqAssistantAIProvider` — calls `_chat_completion` directly (no tool schema needed, plain text response). Timeout: existing `ASSISTANT_GROQ_TIMEOUT_SECONDS` (default 10s).

### Caching

- Cache key: `assistant:greeting:{language}` (values: `en`, `mk`)
- TTL: 1200 seconds (20 min)
- All users of the same language share one cached greeting
- Cache is bypassed when no events or promotions exist (avoids caching a content-free greeting)

### Response shape

```json
{ "greeting": "There's live music at Sunset Bar tonight at 21:00 — entry is free. Restoran Pelister also has a 20% discount running this week." }
```

On Groq failure, timeout, or empty data: `{ "greeting": null }`. Always returns HTTP 200.

### Error handling

- Groq timeout or `AssistantAIError`: return `{ "greeting": null }`, log warning
- No events + no promotions: return `{ "greeting": null }` (skip Groq call entirely)
- DB error: return `{ "greeting": null }`, log error

---

## Frontend

### New service call

Add to `src/api/services.ts`:

```ts
getGreeting: () => api.get<{ greeting: string | null }>('/api/assistant/greeting/')
```

The existing Axios client sends `Accept-Language` automatically via the interceptor.

### AssistantScreen changes

**Typing placeholder message type:**

Add `isTyping?: boolean` to the `ChatMessage` interface in `src/types/index.ts`.

**Initialisation:**

Messages initialise with one typing placeholder message (`id: 'assistant-welcome'`, `role: 'assistant'`, `isTyping: true`) instead of the static welcome text.

**On mount effect:**

```
fetch greeting
  → success + greeting != null  → replace placeholder with greeting ChatMessage
  → success + greeting == null  → replace placeholder with static welcome text
  → network error               → replace placeholder with static welcome text
```

The replacement targets the message with `id: 'assistant-welcome'` to avoid clobbering any user messages that arrive quickly.

**TypingIndicator component:**

New file: `src/components/TypingIndicator.tsx`

Three dots, staggered opacity animation using `Animated` from react-native. Each dot pulses on a 600ms loop with 200ms stagger between dots. Rendered inside the existing assistant message bubble when `message.isTyping === true`.

**Message renderer update:**

In the FlatList `renderItem`, check `message.isTyping` and render `<TypingIndicator />` inside the assistant bubble instead of the text content.

---

## Constraints

- No new dependencies
- Greeting is never shown as a user message — always `role: 'assistant'`
- Greeting has no `suggestions` array (the existing context suggestions are attached separately)
- The typing indicator does not block the input field — user can type immediately
- If the user sends a message before the greeting loads, the greeting is discarded silently (do not replace a user-initiated exchange)

---

## Files changed

**API:**
- `core/views.py` — add `AssistantGreetingView` class and register URL
- `api/urls.py` — add `path("api/assistant/greeting/", ...)`

**Frontend:**
- `src/types/index.ts` — add `isTyping?: boolean` to `ChatMessage`
- `src/api/services.ts` — add `getGreeting`
- `src/components/TypingIndicator.tsx` — new component
- `src/screens/AssistantScreen.tsx` — initialise with typing placeholder, fetch on mount, update renderer
