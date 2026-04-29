# Proactive Assistant Greeting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the Assistant screen opens, show an animated typing indicator then replace it with an AI-generated greeting that mentions live events and active promotions.

**Architecture:** New `GET /api/assistant/greeting/` Django view fetches active events + promotions, calls Groq via the existing `GroqAssistantAIProvider`, caches the result 20 min per language. Frontend initialises the chat with a typing placeholder, fetches the greeting on mount, and replaces the placeholder with the AI text (or the static fallback on failure).

**Tech Stack:** Django REST Framework, Groq API (via existing `GroqAssistantAIProvider`), Django cache, React Native `Animated`, i18next

---

## File Map

| File | Change |
|---|---|
| `core/assistant_ai.py` | Add `generate_greeting` method to `GroqAssistantAIProvider` |
| `core/views.py` | Add `AssistantGreetingView` class |
| `api/urls.py` | Register `api/assistant/greeting/` URL |
| `core/tests.py` | Add `AssistantGreeetingViewTests` class |
| `src/components/TypingIndicator.tsx` | New animated 3-dot component |
| `src/api/services.ts` | Add `getGreeting` to `assistantService` |
| `src/screens/AssistantScreen.tsx` | Update `ChatMessage` type, init with typing placeholder, fetch on mount, update renderer |

---

## Task 1: Add `generate_greeting` to `GroqAssistantAIProvider`

**Files:**
- Modify: `Mobile/Api/core/assistant_ai.py`

- [ ] **Step 1: Read the existing `_chat_completion` signature**

Open `core/assistant_ai.py` and confirm `_chat_completion` exists on `GroqAssistantAIProvider` at the class level.

- [ ] **Step 2: Add the method**

Inside `GroqAssistantAIProvider`, after the `plan_query` method, add:

```python
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
```

- [ ] **Step 3: Commit**

```bash
cd Mobile/Api
git add core/assistant_ai.py
git commit -m "feat: add generate_greeting to GroqAssistantAIProvider"
```

---

## Task 2: Add `AssistantGreetingView` to `views.py`

**Files:**
- Modify: `Mobile/Api/core/views.py`

- [ ] **Step 1: Locate the insertion point**

Open `core/views.py`. Find `class AssistantQueryView` (around line 3127). Add the new view directly below it, after its closing line.

- [ ] **Step 2: Add the view**

```python
class AssistantGreetingView(APIView):
    """Returns an AI-generated greeting with today's events and active promotions.
    
    Cached 20 min per language. Returns {"greeting": null} on any failure.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from django.core.cache import cache
        from django.db import models as db_models
        from django.utils import timezone

        language = get_preferred_language(request)
        cache_key = f"assistant:greeting:{language}"

        cached = cache.get(cache_key)
        if cached is not None:
            return Response({"greeting": cached})

        today = timezone.now().date()

        title_field = f"title_{language}" if language in ("en", "mk") else "title"

        raw_events = list(
            Event.objects.filter(is_active=True)
            .order_by("-created_at")
            .values("title", "title_en", "title_mk", "date_time", "entry_price")[:3]
        )
        raw_promotions = list(
            Promotion.objects.filter(
                is_active=True
            ).filter(
                db_models.Q(valid_until__isnull=True) | db_models.Q(valid_until__gte=today)
            ).order_by("valid_until")
            .values("title", "title_en", "title_mk", "valid_until")[:3]
        )

        if not raw_events and not raw_promotions:
            return Response({"greeting": None})

        events = [
            {
                "title": e.get(title_field) or e["title"],
                "date_time": e["date_time"],
                "entry_price": e.get("entry_price"),
            }
            for e in raw_events
        ]
        promotions = [
            {
                "title": p.get(title_field) or p["title"],
                "valid_until": str(p["valid_until"]) if p.get("valid_until") else None,
            }
            for p in raw_promotions
        ]

        provider = get_assistant_ai_provider()
        if not provider:
            return Response({"greeting": None})

        try:
            greeting = provider.generate_greeting(
                language=language,
                events=events,
                promotions=promotions,
            )
        except AssistantAIError as exc:
            core_logger.warning("Assistant greeting generation failed: %s", exc)
            return Response({"greeting": None})

        if greeting:
            cache.set(cache_key, greeting, 1200)  # 20 min

        return Response({"greeting": greeting})
```

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: add AssistantGreetingView"
```

---

## Task 3: Register the URL

**Files:**
- Modify: `Mobile/Api/api/urls.py`

- [ ] **Step 1: Add the import**

Open `api/urls.py`. Find the existing import of `AssistantQueryView` and add `AssistantGreetingView` to the same import line:

```python
from core.views import (
    # ... existing imports ...
    AssistantQueryView,
    AssistantGreetingView,
)
```

Or if views are imported inline in `urlpatterns`, add the path directly:

- [ ] **Step 2: Add the URL pattern**

In `urlpatterns`, directly after the `assistant_query` path:

```python
path("api/assistant/greeting/", AssistantGreetingView.as_view(), name="assistant_greeting"),
```

- [ ] **Step 3: Verify the server starts**

```bash
cd Mobile/Api
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add api/urls.py
git commit -m "feat: register api/assistant/greeting/ URL"
```

---

## Task 4: Write tests for `AssistantGreetingView`

**Files:**
- Modify: `Mobile/Api/core/tests.py`

- [ ] **Step 1: Add the test class**

At the bottom of `core/tests.py`, add:

```python
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from django.utils import timezone


class AssistantGreetingViewTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.category = Category.objects.create(name="Food", slug="food", is_active=True)
        today = timezone.now().date()

        self.event = Event.objects.create(
            title="Live Jazz Night",
            title_en="Live Jazz Night",
            title_mk="Џез вечер",
            description="Great music",
            date_time="Tonight 21:00",
            location="City Square",
            entry_price="Free",
            category=self.category,
            is_active=True,
        )
        self.promotion = Promotion.objects.create(
            title="20% off at Pelister",
            title_en="20% off at Pelister",
            title_mk="20% попуст кај Пелистер",
            description="Great deal",
            is_active=True,
            valid_until=today + timezone.timedelta(days=7),
        )

    def test_returns_greeting_when_groq_succeeds(self):
        with patch("core.views.get_assistant_ai_provider") as mock_provider_fn:
            mock_provider = MagicMock()
            mock_provider.generate_greeting.return_value = "Live Jazz tonight at City Square — entry is free!"
            mock_provider_fn.return_value = mock_provider

            response = self.client.get(
                "/api/assistant/greeting/",
                HTTP_ACCEPT_LANGUAGE="en",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["greeting"], "Live Jazz tonight at City Square — entry is free!")

    def test_returns_null_when_no_provider(self):
        with patch("core.views.get_assistant_ai_provider", return_value=None):
            response = self.client.get("/api/assistant/greeting/", HTTP_ACCEPT_LANGUAGE="en")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["greeting"])

    def test_returns_null_when_groq_raises(self):
        with patch("core.views.get_assistant_ai_provider") as mock_provider_fn:
            mock_provider = MagicMock()
            mock_provider.generate_greeting.side_effect = AssistantAIError("timeout")
            mock_provider_fn.return_value = mock_provider

            response = self.client.get("/api/assistant/greeting/", HTTP_ACCEPT_LANGUAGE="en")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["greeting"])

    def test_returns_null_when_no_content(self):
        Event.objects.all().update(is_active=False)
        Promotion.objects.all().update(is_active=False)

        with patch("core.views.get_assistant_ai_provider") as mock_provider_fn:
            mock_provider_fn.return_value = MagicMock()
            response = self.client.get("/api/assistant/greeting/", HTTP_ACCEPT_LANGUAGE="en")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["greeting"])
        # provider should never have been called
        mock_provider_fn.return_value.generate_greeting.assert_not_called()

    def test_uses_mk_titles_for_mk_language(self):
        with patch("core.views.get_assistant_ai_provider") as mock_provider_fn:
            mock_provider = MagicMock()
            mock_provider.generate_greeting.return_value = "Џез вечер денеска!"
            mock_provider_fn.return_value = mock_provider

            self.client.get("/api/assistant/greeting/", HTTP_ACCEPT_LANGUAGE="mk")

        call_kwargs = mock_provider.generate_greeting.call_args[1]
        self.assertEqual(call_kwargs["language"], "mk")
        self.assertEqual(call_kwargs["events"][0]["title"], "Џез вечер")

    def test_result_is_cached(self):
        with patch("core.views.get_assistant_ai_provider") as mock_provider_fn:
            mock_provider = MagicMock()
            mock_provider.generate_greeting.return_value = "Great day in Gevgelija!"
            mock_provider_fn.return_value = mock_provider

            self.client.get("/api/assistant/greeting/", HTTP_ACCEPT_LANGUAGE="en")
            self.client.get("/api/assistant/greeting/", HTTP_ACCEPT_LANGUAGE="en")

        # Groq should only be called once — second request is served from cache
        self.assertEqual(mock_provider.generate_greeting.call_count, 1)
```

Also add to the imports at the top of the test file:
```python
from core.assistant_ai import AssistantAIError
```

- [ ] **Step 2: Run the tests (expect failures)**

```bash
cd Mobile/Api
python manage.py test core.tests.AssistantGreetingViewTests -v 2
```

Expected: all 6 tests fail with `AttributeError` or `404` since the view doesn't exist yet. (If you're running tasks in order, the view already exists and they should pass.)

- [ ] **Step 3: Run again after Tasks 2–3 are complete**

```bash
python manage.py test core.tests.AssistantGreetingViewTests -v 2
```

Expected output:
```
test_returns_greeting_when_groq_succeeds ... ok
test_returns_null_when_no_provider ... ok
test_returns_null_when_groq_raises ... ok
test_returns_null_when_no_content ... ok
test_uses_mk_titles_for_mk_language ... ok
test_result_is_cached ... ok

Ran 6 tests in 0.XXXs
OK
```

- [ ] **Step 4: Commit**

```bash
git add core/tests.py
git commit -m "test: add AssistantGreetingView tests"
```

---

## Task 5: Create `TypingIndicator` component

**Files:**
- Create: `Mobile/Frontend/src/components/TypingIndicator.tsx`

- [ ] **Step 1: Create the file**

```tsx
import React, { useEffect, useRef } from 'react';
import { View, Animated, StyleSheet } from 'react-native';

export default function TypingIndicator() {
  const dot1 = useRef(new Animated.Value(0.3)).current;
  const dot2 = useRef(new Animated.Value(0.3)).current;
  const dot3 = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const pulse = (dot: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(dot, { toValue: 1, duration: 300, useNativeDriver: true }),
          Animated.timing(dot, { toValue: 0.3, duration: 300, useNativeDriver: true }),
          Animated.delay(Math.max(0, 600 - delay)),
        ])
      );

    const a1 = pulse(dot1, 0);
    const a2 = pulse(dot2, 200);
    const a3 = pulse(dot3, 400);
    a1.start();
    a2.start();
    a3.start();

    return () => {
      a1.stop();
      a2.stop();
      a3.stop();
    };
  }, [dot1, dot2, dot3]);

  return (
    <View style={styles.container}>
      {([dot1, dot2, dot3] as Animated.Value[]).map((dot, i) => (
        <Animated.View key={i} style={[styles.dot, { opacity: dot }]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingVertical: 2,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#B91C1C',
  },
});
```

- [ ] **Step 2: Commit**

```bash
cd Mobile/Frontend
git add src/components/TypingIndicator.tsx
git commit -m "feat: add TypingIndicator animated component"
```

---

## Task 6: Add `getGreeting` to `assistantService`

**Files:**
- Modify: `Mobile/Frontend/src/api/services.ts`

- [ ] **Step 1: Update `assistantService`**

Find the `assistantService` export (around line 545) and add `getGreeting`:

```ts
export const assistantService = {
  query: async (payload: string | AssistantQueryRequest): Promise<AssistantResponse> => {
    const requestPayload = typeof payload === 'string' ? { message: payload } : payload;
    const response = await api.post('/api/assistant/query/', requestPayload);
    return response.data;
  },
  getGreeting: async (): Promise<{ greeting: string | null }> => {
    const response = await api.get('/api/assistant/greeting/');
    return response.data;
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add src/api/services.ts
git commit -m "feat: add assistantService.getGreeting"
```

---

## Task 7: Update `AssistantScreen`

**Files:**
- Modify: `Mobile/Frontend/src/screens/AssistantScreen.tsx`

- [ ] **Step 1: Update the `ChatMessage` type**

Find the `type ChatMessage` declaration (around line 26) and add `isTyping`:

```ts
type ChatMessage = {
  id: string;
  role: 'assistant' | 'user';
  text?: string;
  results?: AssistantContentResult[];
  actions?: AssistantAction[];
  suggestions?: string[];
  isTyping?: boolean;
};
```

- [ ] **Step 2: Add the `TypingIndicator` import**

At the top of the file, with the other component imports:

```ts
import TypingIndicator from '../components/TypingIndicator';
```

- [ ] **Step 3: Update `buildInitialMessage` to produce a typing placeholder**

Find `buildInitialMessage` (around line 164) and replace it:

```ts
const buildInitialMessage = React.useCallback((): ChatMessage => ({
  id: 'assistant-welcome',
  role: 'assistant',
  isTyping: true,
}), []);
```

Remove the `context` parameter — suggestions are attached by the greeting fetch effect, not at init time.

- [ ] **Step 4: Update the `messages` initialiser**

Find (around line 174):
```ts
const [messages, setMessages] = React.useState<ChatMessage[]>(() => [buildInitialMessage(routeContext)]);
```

Replace with:
```ts
const [messages, setMessages] = React.useState<ChatMessage[]>(() => [buildInitialMessage()]);
```

- [ ] **Step 5: Update the routeContext effect**

Find the effect that resets messages when `routeContextKey` changes (around line 176):

```ts
React.useEffect(() => {
  setActiveContext(routeContext);
  setMessages([buildInitialMessage(routeContext)]);
}, [buildInitialMessage, routeContext, routeContextKey]);
```

Replace with:
```ts
React.useEffect(() => {
  setActiveContext(routeContext);
  setMessages([buildInitialMessage()]);
}, [buildInitialMessage, routeContext, routeContextKey]);
```

- [ ] **Step 6: Add the greeting fetch effect**

After the existing `useEffect` blocks (after line ~190), add:

```ts
React.useEffect(() => {
  let cancelled = false;

  const staticWelcome: ChatMessage = {
    id: 'assistant-welcome',
    role: 'assistant',
    text: translate(
      'screens:assistant.welcomeMessage',
      'Ask me about places, events, promotions, currency, support, or how to use the app.'
    ),
    suggestions: buildContextSuggestions(routeContext, translate),
  };

  assistantService.getGreeting()
    .then(({ greeting }) => {
      if (cancelled) return;
      setMessages(prev => {
        // Only replace if the welcome placeholder is still there and no user has typed
        const hasUserMessage = prev.some(m => m.role === 'user');
        if (hasUserMessage) return prev;
        return prev.map(m =>
          m.id === 'assistant-welcome'
            ? greeting
              ? { ...m, isTyping: false, text: greeting, suggestions: buildContextSuggestions(routeContext, translate) }
              : staticWelcome
            : m
        );
      });
    })
    .catch(() => {
      if (cancelled) return;
      setMessages(prev => {
        const hasUserMessage = prev.some(m => m.role === 'user');
        if (hasUserMessage) return prev;
        return prev.map(m => m.id === 'assistant-welcome' ? staticWelcome : m);
      });
    });

  return () => { cancelled = true; };
}, []); // eslint-disable-line react-hooks/exhaustive-deps — intentionally run once on mount
```

- [ ] **Step 7: Update `renderMessage` to handle `isTyping`**

Find `renderMessage` (around line 352). Inside the assistant bubble, before the `<Text>` element:

```tsx
const renderMessage = ({ item }: { item: ChatMessage }) => {
  const isAssistant = item.role === 'assistant';

  return (
    <View style={[styles.messageRow, isAssistant ? styles.messageRowLeft : styles.messageRowRight]}>
      <View style={[styles.messageBubble, isAssistant ? styles.assistantBubble : styles.userBubble]}>
        {item.isTyping ? (
          <TypingIndicator />
        ) : (
          <Text style={[styles.messageText, isAssistant ? styles.assistantText : styles.userText]}>
            {item.text}
          </Text>
        )}

        {/* results, actions, suggestions blocks unchanged below */}
```

Keep all the existing `item.results`, `item.actions`, `item.suggestions` blocks exactly as they are — just wrap the existing `<Text>` in the `isTyping` conditional above.

- [ ] **Step 8: Commit**

```bash
git add src/screens/AssistantScreen.tsx src/components/TypingIndicator.tsx
git commit -m "feat: proactive AI greeting on AssistantScreen open"
```

---

## Self-Review

**Spec coverage:**
- ✅ New `GET /api/assistant/greeting/` endpoint — Task 2 + 3
- ✅ Fetches today's events + active promotions — Task 2
- ✅ Calls Groq via existing provider — Task 1
- ✅ Cache 20 min per language — Task 2
- ✅ Returns `{ greeting: null }` on failure — Task 2 (all error paths)
- ✅ Typing indicator while loading — Task 5 + 7
- ✅ Replaces with greeting or fallback — Task 7 Step 6
- ✅ User typing does not get replaced — Task 7 Step 6 (`hasUserMessage` guard)
- ✅ Cancelled on unmount — Task 7 Step 6 (`cancelled` flag)
- ✅ Tests — Task 4

**Type consistency:**
- `ChatMessage.isTyping: boolean` — defined in Task 7 Step 1, used in Task 7 Steps 6 and 7 ✅
- `assistantService.getGreeting` — defined in Task 6, called in Task 7 Step 6 ✅
- `provider.generate_greeting(language, events, promotions)` — defined in Task 1, called in Task 2 ✅
- `AssistantAIError` — already imported in `views.py`, added to `tests.py` imports in Task 4 ✅
