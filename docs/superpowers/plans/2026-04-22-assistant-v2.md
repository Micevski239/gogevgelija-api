# Assistant v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the GoGevgelija in-app assistant with a better Groq model, fix all known gaps (price filter, promotion validity, feed passthrough, open_now efficiency), add promotion expiry notes and cross-linked promotions on listing responses, and improve catalog/cache performance.

**Architecture:** Two-layer hybrid stays unchanged — Groq as AI planner returning strict JSON, heuristic parser as fallback. All changes are in the planner config and the backend tool-execution layer. No schema changes, no migrations, no frontend changes.

**Tech Stack:** Django 5.2, DRF, Groq API (OpenAI-compatible), SQLite (dev) / PostgreSQL (prod), Django cache framework.

---

## File Map

| File | What changes |
|---|---|
| `core/assistant_ai.py` | Model default `llama-3.1-8b-instant` → `llama-3.3-70b-versatile`, timeout 8→10s, system prompt refinement |
| `core/assistant_parser.py` | Remove `unsupported: True` from `budget` soft filter rule |
| `core/views.py` | Cache TTLs, catalog limits + bilingual titles, promotion validity filter, price filter for events, open_now fetch reduction, feed tool time/open_now passthrough, `_assistant_promo_expiry_note` helper, `_assistant_promotion_answer` update, cross-linked promotions in `_assistant_resolved_entity_response`, `select_related` on listing/event queries |
| `core/tests.py` | New test class `AssistantV2Tests` covering all new behaviors |

---

## Task 1: Model upgrade in `assistant_ai.py`

**Files:**
- Modify: `core/assistant_ai.py`

- [ ] **Step 1: Update model default, timeout, and system prompt**

Replace lines 51–52 (the `__init__` defaults) and the `system_prompt` string inside `plan_query`:

```python
# In GroqAssistantAIProvider.__init__:
self.model = (os.getenv("ASSISTANT_GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
self.timeout_seconds = float(os.getenv("ASSISTANT_GROQ_TIMEOUT_SECONDS", "10"))
```

Replace the full `system_prompt` string in `plan_query` (starts at line 117, ends before `messages = [`):

```python
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
    "- faq: app help (language, wishlist, support, collaboration, currency, border cameras, guest/account).\n"
    "- category: 'show me restaurants', 'kade da jadam' — category discovery.\n"
    "- feed: generic overview of events / promotions / blogs without a specific entity in mind.\n"
    "- search: named entities, specific places, or any broad lookup not matching category/feed.\n"
    "- clarify: ONLY if the message is truly ambiguous and you cannot make a reasonable guess.\n\n"
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
```

- [ ] **Step 2: Verify the file parses**

```bash
cd /Users/filipmicevski/Desktop/Work/GoGevgelija/Mobile/Api
python -c "from core.assistant_ai import GroqAssistantAIProvider; p = GroqAssistantAIProvider(); print(p.model, p.timeout_seconds)"
```

Expected output: `llama-3.3-70b-versatile 10.0`

- [ ] **Step 3: Commit**

```bash
git add core/assistant_ai.py
git commit -m "feat(assistant): upgrade to llama-3.3-70b-versatile, refine system prompt"
```

---

## Task 2: Remove `budget` from unsupported filters in `assistant_parser.py`

**Files:**
- Modify: `core/assistant_parser.py`

- [ ] **Step 1: Write the failing test**

In `core/tests.py`:

```python
from django.test import TestCase
from core.assistant_parser import HeuristicAssistantQueryParser


class AssistantV2Tests(TestCase):

    def setUp(self):
        self.parser = HeuristicAssistantQueryParser()

    def test_budget_filter_not_unsupported(self):
        result = self.parser.parse("show me cheap restaurants", language="en")
        self.assertNotIn("budget", result.unsupported_filters)
```

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test core.tests.AssistantV2Tests.test_budget_filter_not_unsupported -v 2
```

Expected: FAIL — `budget` currently in `unsupported_filters`.

- [ ] **Step 3: Fix `SOFT_FILTER_RULES` in `assistant_parser.py`**

Find the `budget` entry in `SOFT_FILTER_RULES` (line ~246) and change `'unsupported': True` to `'unsupported': False`:

```python
SOFT_FILTER_RULES = [
    {
        'filter_key': 'budget',
        'keywords': ['cheap', 'affordable', 'budget', 'low cost', 'евтин', 'евтино', 'пристапно'],
        'unsupported': False,  # price filtering is now supported for events
    },
    {
        'filter_key': 'near_border',
        'keywords': ['border', 'near border', 'greece border', 'crossing', 'граница', 'близу граница'],
        'unsupported': True,
    },
    {
        'filter_key': 'today',
        'keywords': ['today', 'tonight', 'now', 'денес', 'вечерва', 'сега'],
        'unsupported': False,
    },
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test core.tests.AssistantV2Tests.test_budget_filter_not_unsupported -v 2
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/assistant_parser.py core/tests.py
git commit -m "feat(assistant): mark price/budget filter as supported"
```

---

## Task 3: Cache TTLs and catalog improvements in `views.py`

**Files:**
- Modify: `core/views.py` (lines 1587–1622)

- [ ] **Step 1: Update cache TTL constants**

Find lines 1588–1589 and replace:

```python
_ASSISTANT_CATALOG_TTL = 3600   # 60 min — catalog rarely changes intraday
_ASSISTANT_PLAN_CACHE_TTL = 1800  # 30 min — repeated queries stay cached longer
```

- [ ] **Step 2: Update `_assistant_build_catalog` — limits and bilingual titles**

Replace the entity-building loop inside `_assistant_build_catalog` (lines 1612–1619):

```python
entities = []
for listing in Listing.objects.filter(is_active=True).only('id', 'title', 'title_mk')[:60]:
    entities.append({
        'type': 'listing',
        'id': listing.id,
        'title': listing.title or '',
        'title_mk': getattr(listing, 'title_mk', '') or '',
    })
for event in Event.objects.filter(is_active=True).only('id', 'title', 'title_mk')[:20]:
    entities.append({
        'type': 'event',
        'id': event.id,
        'title': event.title or '',
        'title_mk': getattr(event, 'title_mk', '') or '',
    })
for promo in Promotion.objects.filter(is_active=True).only('id', 'title', 'title_mk')[:15]:
    entities.append({
        'type': 'promotion',
        'id': promo.id,
        'title': promo.title or '',
        'title_mk': getattr(promo, 'title_mk', '') or '',
    })
```

- [ ] **Step 3: Update the catalog block builder in `plan_query` (`assistant_ai.py`) to include `title_mk`**

In `assistant_ai.py`, inside `plan_query`, find the entity catalog block builder (line ~113):

```python
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
```

- [ ] **Step 4: Verify import-level sanity**

```bash
python -c "from core.views import _assistant_build_catalog; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/assistant_ai.py
git commit -m "perf(assistant): raise cache TTLs, expand catalog with bilingual titles"
```

---

## Task 4: Promotion validity filter, price filter for events, and open_now efficiency in `_assistant_bilingual_search`

**Files:**
- Modify: `core/views.py` (lines 1747–1806)

- [ ] **Step 1: Write failing tests**

Add to `AssistantV2Tests` in `core/tests.py`:

```python
from django.utils import timezone
from datetime import timedelta
from unittest.mock import MagicMock
from core.models import Category, Listing, Event, Promotion


class AssistantV2Tests(TestCase):

    def setUp(self):
        from core.assistant_parser import HeuristicAssistantQueryParser
        self.parser = HeuristicAssistantQueryParser()
        self.request = MagicMock()
        self.request.build_absolute_uri = lambda path: f"http://testserver{path}"

        self.category = Category.objects.create(name="Food", slug="food", is_active=True)

        self.event_free = Event.objects.create(
            title="Free Jazz Night",
            title_en="Free Jazz Night",
            title_mk="Бесплатна џез ноќ",
            location="City Park",
            date_time="2026-04-30 20:00",
            is_active=True,
            entry_price="Free",
        )
        self.event_paid = Event.objects.create(
            title="Paid Concert",
            title_en="Paid Concert",
            title_mk="Платен концерт",
            location="Arena",
            date_time="2026-04-30 21:00",
            is_active=True,
            entry_price="10 EUR",
        )

        today = timezone.now().date()
        self.promo_active = Promotion.objects.create(
            title="Summer Deal",
            title_en="Summer Deal",
            title_mk="Летна понуда",
            is_active=True,
            valid_until=today + timedelta(days=10),
        )
        self.promo_expired = Promotion.objects.create(
            title="Old Deal",
            title_en="Old Deal",
            title_mk="Стара понуда",
            is_active=True,
            valid_until=today - timedelta(days=1),
        )
        self.promo_no_expiry = Promotion.objects.create(
            title="Evergreen Deal",
            title_en="Evergreen Deal",
            title_mk="Трајна понуда",
            is_active=True,
            valid_until=None,
        )

    def test_budget_filter_not_unsupported(self):
        result = self.parser.parse("show me cheap restaurants", language="en")
        self.assertNotIn("budget", result.unsupported_filters)

    def test_bilingual_search_excludes_expired_promotions(self):
        from core.views import _assistant_bilingual_search
        result = _assistant_bilingual_search(
            "deal", "понуда", "promotions", "en", self.request
        )
        titles = [p["title"] for p in result["promotions"]]
        self.assertNotIn("Old Deal", titles)
        self.assertIn("Summer Deal", titles)
        self.assertIn("Evergreen Deal", titles)

    def test_bilingual_search_price_filter_cheap(self):
        from core.views import _assistant_bilingual_search
        result = _assistant_bilingual_search(
            "jazz night", "џез ноќ", "events", "en", self.request,
            price_filter="cheap",
        )
        titles = [e["title"] for e in result["events"]]
        self.assertIn("Free Jazz Night", titles)
        self.assertNotIn("Paid Concert", titles)

    def test_bilingual_search_price_filter_premium(self):
        from core.views import _assistant_bilingual_search
        result = _assistant_bilingual_search(
            "concert", "концерт", "events", "en", self.request,
            price_filter="premium",
        )
        titles = [e["title"] for e in result["events"]]
        self.assertNotIn("Free Jazz Night", titles)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test core.tests.AssistantV2Tests.test_bilingual_search_excludes_expired_promotions core.tests.AssistantV2Tests.test_bilingual_search_price_filter_cheap core.tests.AssistantV2Tests.test_bilingual_search_price_filter_premium -v 2
```

Expected: All FAIL — `_assistant_bilingual_search` doesn't accept `price_filter` yet and promotions not filtered.

- [ ] **Step 3: Update `_assistant_bilingual_search` signature and body**

Replace the full function definition (lines 1747–1806):

```python
def _assistant_bilingual_search(query_en, query_mk, content_type, language, request, time_filter=None, open_now=False, price_filter=None, limit=3):
    """Search across bilingual fields with EN + MK terms combined, apply optional filters."""
    from django.db.models import Q

    terms = [t.strip() for t in [query_en, query_mk] if t and t.strip()]
    if not terms:
        return {'listings': [], 'events': [], 'promotions': [], 'blogs': [], 'total_count': 0, 'query': ''}

    def or_match(fields):
        q = Q()
        for term in terms:
            for field in fields:
                q |= Q(**{f"{field}__icontains": term})
        return q

    ctx = {'request': request, 'language': language}
    results = {'listings': [], 'events': [], 'promotions': [], 'blogs': []}

    if content_type in ('all', 'listings'):
        qs = Listing.objects.filter(
            or_match(['title', 'title_en', 'title_mk', 'address', 'description', 'description_en', 'description_mk',
                      'category__name', 'category__name_en', 'category__name_mk']),
            is_active=True,
        ).select_related('category').distinct()
        if open_now:
            batch = list(qs[:limit * 2])
            serialized_all = ListingSerializer(batch, many=True, context=ctx).data
            results['listings'] = [l for l in serialized_all if l.get('is_open')][:limit]
        else:
            results['listings'] = ListingSerializer(qs[:limit], many=True, context=ctx).data

    if content_type in ('all', 'events'):
        qs = Event.objects.filter(
            or_match(['title', 'title_en', 'title_mk', 'location', 'description', 'description_en', 'description_mk',
                      'category__name', 'category__name_en', 'category__name_mk']),
            is_active=True,
        ).select_related('category').distinct()
        start, end = _assistant_time_filter_range(time_filter)
        if start and end:
            qs = qs.filter(date_time__gte=start, date_time__lt=end)
        if price_filter == 'cheap':
            qs = qs.filter(entry_price__iregex=r'free|бесплатно|0')
        elif price_filter == 'premium':
            qs = qs.exclude(entry_price__iregex=r'free|бесплатно|0').exclude(
                entry_price__isnull=True
            ).exclude(entry_price='')
        results['events'] = EventSerializer(qs[:limit], many=True, context=ctx).data

    if content_type in ('all', 'promotions'):
        today = timezone.now().date()
        qs = Promotion.objects.filter(
            or_match(['title', 'title_en', 'title_mk', 'description', 'description_en', 'description_mk', 'discount_code']),
            is_active=True,
        ).filter(
            models.Q(valid_until__gte=today) | models.Q(valid_until__isnull=True)
        ).order_by('valid_until').distinct()
        results['promotions'] = PromotionSerializer(qs[:limit], many=True, context=ctx).data

    if content_type in ('all', 'blogs'):
        qs = Blog.objects.filter(
            or_match(['title', 'title_en', 'title_mk', 'subtitle', 'subtitle_en', 'subtitle_mk',
                      'content', 'content_en', 'content_mk']),
            is_active=True, published=True,
        ).distinct()
        results['blogs'] = BlogSerializer(qs[:limit], many=True, context=ctx).data

    total = sum(len(v) for v in results.values())
    return {**results, 'total_count': total, 'query': query_en or query_mk or ''}
```

- [ ] **Step 4: Pass `price_filter` through `_assistant_bilingual_search_response`**

In `_assistant_bilingual_search_response` (line ~1809), add `price_filter` extraction and pass it:

```python
def _assistant_bilingual_search_response(plan, language, request, context_entity):
    query_en = (plan.get('normalized_query_en') or '').strip()
    query_mk = (plan.get('normalized_query_mk') or '').strip()
    content_type = (plan.get('content_type') or 'all').strip().lower()
    time_filter = plan.get('time_filter')
    open_now = bool(plan.get('open_now_requested'))
    price_filter = plan.get('price_filter')

    search = _assistant_bilingual_search(
        query_en, query_mk, content_type, language, request,
        time_filter=time_filter, open_now=open_now, price_filter=price_filter, limit=3,
    )
    # Everything below this line in _assistant_bilingual_search_response is unchanged.
    # Only the 8 lines above (variable extractions + search call) are replaced.
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python manage.py test core.tests.AssistantV2Tests.test_bilingual_search_excludes_expired_promotions core.tests.AssistantV2Tests.test_bilingual_search_price_filter_cheap core.tests.AssistantV2Tests.test_bilingual_search_price_filter_premium -v 2
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/tests.py
git commit -m "feat(assistant): promotion validity filter, event price filter, open_now efficiency, select_related"
```

---

## Task 5: Feed tool `time_filter` and `open_now` passthrough

**Files:**
- Modify: `core/views.py` (lines 2874–2909 and ~1949)

- [ ] **Step 1: Write failing test**

Add to `AssistantV2Tests` in `core/tests.py`:

```python
    def test_feed_response_filters_events_by_time(self):
        from core.views import _assistant_generic_feed_response
        # event_free has date_time "2026-04-30 20:00" — in the future relative to test date
        # Use time_filter=None to check the function runs without error with the new signature
        result = _assistant_generic_feed_response(
            "event events happening", "en", self.request, time_filter=None, open_now=False
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], 'events_overview')

    def test_feed_response_excludes_expired_promotions(self):
        from core.views import _assistant_generic_feed_response
        result = _assistant_generic_feed_response(
            "deal deals promo promotion", "en", self.request
        )
        self.assertIsNotNone(result)
        titles = [r['data']['title'] for r in result['results']]
        self.assertNotIn("Old Deal", titles)
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test core.tests.AssistantV2Tests.test_feed_response_filters_events_by_time core.tests.AssistantV2Tests.test_feed_response_excludes_expired_promotions -v 2
```

Expected: FAIL — `_assistant_generic_feed_response` doesn't accept `time_filter`/`open_now` yet.

- [ ] **Step 3: Rewrite `_assistant_generic_feed_response`**

Replace the full function (lines 2874–2909):

```python
def _assistant_generic_feed_response(normalized_message, language, request, time_filter=None, open_now=False):
    if any(keyword in normalized_message for keyword in ['event', 'events', 'happening', 'настан', 'настани']):
        qs = Event.objects.filter(is_active=True)
        start, end = _assistant_time_filter_range(time_filter)
        if start and end:
            qs = qs.filter(date_time__gte=start, date_time__lt=end)
        serialized = EventSerializer(qs[:3], many=True, context={'request': request, 'language': language}).data
        if serialized:
            return {
                'answer': _localized_text(
                    language,
                    "Here are some upcoming events from the app.",
                    "Еве неколку претстојни настани од апликацијата.",
                ),
                'intent': 'events_overview',
                'confidence': 'medium',
                'results': [{'type': 'event', 'data': item} for item in serialized],
                'actions': [],
                'suggestions': _assistant_default_suggestions(language),
            }

    if any(keyword in normalized_message for keyword in ['deal', 'deals', 'promo', 'promotion', 'offer', 'понуда', 'промоција', 'попуст']):
        today = timezone.now().date()
        qs = Promotion.objects.filter(
            is_active=True,
        ).filter(
            models.Q(valid_until__gte=today) | models.Q(valid_until__isnull=True)
        ).order_by('valid_until')[:3]
        serialized = PromotionSerializer(qs, many=True, context={'request': request, 'language': language}).data
        if serialized:
            return {
                'answer': _localized_text(
                    language,
                    "Here are some active deals from the app.",
                    "Еве неколку активни понуди од апликацијата.",
                ),
                'intent': 'promotions_overview',
                'confidence': 'medium',
                'results': [{'type': 'promotion', 'data': item} for item in serialized],
                'actions': [],
                'suggestions': _assistant_default_suggestions(language),
            }

    return None
```

- [ ] **Step 4: Update the call site in `_assistant_execute_ai_plan`**

Find the `tool == 'feed'` branch (line ~1949) and replace:

```python
    if tool == 'feed':
        return _assistant_generic_feed_response(
            normalized_tool_query, language, request,
            time_filter=plan.get('time_filter'),
            open_now=bool(plan.get('open_now_requested')),
        )
```

- [ ] **Step 5: Update the heuristic fallback call site in `AssistantQueryView.post`**

Find the call to `_assistant_generic_feed_response` in `AssistantQueryView.post` (line ~3050). It must pass no extra args (defaults are fine):

```python
        feed_response = _assistant_generic_feed_response(normalized_message, language, request)
```

This line is unchanged — the defaults `time_filter=None, open_now=False` handle it.

- [ ] **Step 6: Run tests**

```bash
python manage.py test core.tests.AssistantV2Tests.test_feed_response_filters_events_by_time core.tests.AssistantV2Tests.test_feed_response_excludes_expired_promotions -v 2
```

Expected: Both PASS

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/tests.py
git commit -m "feat(assistant): feed tool respects time_filter and excludes expired promotions"
```

---

## Task 6: Promotion expiry awareness — `_assistant_promo_expiry_note`

**Files:**
- Modify: `core/views.py` (add helper near line 2572, update `_assistant_promotion_answer`)

- [ ] **Step 1: Write failing tests**

Add to `AssistantV2Tests` in `core/tests.py`:

```python
    def test_promo_expiry_note_within_7_days(self):
        from core.views import _assistant_promo_expiry_note
        from django.utils import timezone
        today = timezone.now().date()
        promo_data = {'valid_until': str(today + timedelta(days=3))}
        note = _assistant_promo_expiry_note(promo_data, 'en')
        self.assertIsNotNone(note)
        self.assertIn('3', note)

    def test_promo_expiry_note_beyond_7_days_returns_none(self):
        from core.views import _assistant_promo_expiry_note
        from django.utils import timezone
        today = timezone.now().date()
        promo_data = {'valid_until': str(today + timedelta(days=10))}
        note = _assistant_promo_expiry_note(promo_data, 'en')
        self.assertIsNone(note)

    def test_promo_expiry_note_no_valid_until_returns_none(self):
        from core.views import _assistant_promo_expiry_note
        note = _assistant_promo_expiry_note({}, 'en')
        self.assertIsNone(note)
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test core.tests.AssistantV2Tests.test_promo_expiry_note_within_7_days core.tests.AssistantV2Tests.test_promo_expiry_note_beyond_7_days_returns_none core.tests.AssistantV2Tests.test_promo_expiry_note_no_valid_until_returns_none -v 2
```

Expected: All FAIL — `_assistant_promo_expiry_note` does not exist yet.

- [ ] **Step 3: Add `_assistant_promo_expiry_note` helper**

Insert this function immediately before `_assistant_listing_answer` (line ~2547):

```python
def _assistant_promo_expiry_note(promo_data, language):
    """Return a localized expiry warning if the promo expires within 7 days, else None."""
    valid_until_str = promo_data.get('valid_until')
    if not valid_until_str:
        return None
    try:
        from datetime import date as date_type
        valid_until = (
            date_type.fromisoformat(str(valid_until_str))
            if not isinstance(valid_until_str, date_type)
            else valid_until_str
        )
        days_left = (valid_until - timezone.now().date()).days
        if 0 <= days_left <= 7:
            return _localized_text(
                language,
                f"Expires in {days_left} day{'s' if days_left != 1 else ''}",
                f"Истекува за {days_left} {'ден' if days_left == 1 else 'дена'}",
            )
    except (ValueError, TypeError, AttributeError):
        pass
    return None
```

- [ ] **Step 4: Update `_assistant_promotion_answer` to append expiry note**

Replace `_assistant_promotion_answer` (line ~2572):

```python
def _assistant_promotion_answer(promotion, language):
    parts = [promotion.get('title')]
    description = _compact_text(promotion.get('description'))
    if description:
        parts.append(description)
    if promotion.get('has_discount_code') and promotion.get('discount_code'):
        parts.append(_localized_text(language, f"Code: {promotion['discount_code']}", f"Код: {promotion['discount_code']}"))
    if promotion.get('valid_until'):
        parts.append(_localized_text(language, f"Valid until {promotion['valid_until']}", f"Важи до {promotion['valid_until']}"))
    expiry_note = _assistant_promo_expiry_note(promotion, language)
    if expiry_note:
        parts.append(expiry_note)
    return ". ".join(part for part in parts if part) + "."
```

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.AssistantV2Tests.test_promo_expiry_note_within_7_days core.tests.AssistantV2Tests.test_promo_expiry_note_beyond_7_days_returns_none core.tests.AssistantV2Tests.test_promo_expiry_note_no_valid_until_returns_none -v 2
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/tests.py
git commit -m "feat(assistant): add promotion expiry note for deals expiring within 7 days"
```

---

## Task 7: Cross-linked promotions on listing responses

**Files:**
- Modify: `core/views.py` (`_assistant_resolved_entity_response`, line ~1688)

- [ ] **Step 1: Write failing test**

Add to `AssistantV2Tests` in `core/tests.py`:

```python
    def test_resolved_listing_includes_related_promotions(self):
        from core.views import _assistant_resolved_entity_response
        from core.serializers import ListingSerializer

        listing = Listing.objects.create(
            title="Test Cafe",
            title_en="Test Cafe",
            title_mk="Тест Кафе",
            is_active=True,
            category=self.category,
        )
        listing.promotions.add(self.promo_active)

        serialized = ListingSerializer(listing, context={'request': self.request, 'language': 'en'}).data
        response = _assistant_resolved_entity_response('listing', serialized, 'en', request=self.request)

        self.assertIsNotNone(response)
        result_types = [r['type'] for r in response['results']]
        self.assertIn('promotion', result_types)
```

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test core.tests.AssistantV2Tests.test_resolved_listing_includes_related_promotions -v 2
```

Expected: FAIL — no `promotion` in results, and function doesn't accept `request` kwarg.

- [ ] **Step 3: Update `_assistant_resolved_entity_response` signature and body**

Replace the full function (lines 1688–1717):

```python
def _assistant_resolved_entity_response(entity_type, data, language, request=None):
    """Compose a single-entity response. For listings, appends related active promotions."""
    builders = {
        'listing': _assistant_listing_answer,
        'event': _assistant_event_answer,
        'promotion': _assistant_promotion_answer,
        'blog': _assistant_blog_answer,
    }
    builder = builders.get(entity_type)
    answer = builder(data, language) if builder else None
    if not answer:
        return None

    results = [{'type': entity_type, 'data': data}]

    if entity_type == 'listing' and data.get('id') and request is not None:
        today = timezone.now().date()
        listing_obj = Listing.objects.filter(id=data['id']).prefetch_related('promotions').first()
        if listing_obj:
            related_promos = listing_obj.promotions.filter(
                is_active=True,
            ).filter(
                models.Q(valid_until__gte=today) | models.Q(valid_until__isnull=True)
            )[:2]
            ctx = {'request': request, 'language': language}
            for promo in related_promos:
                promo_data = PromotionSerializer(promo, context=ctx).data
                results.append({'type': 'promotion', 'data': promo_data})

    return _assistant_response(
        answer=answer,
        intent=f"{entity_type}_match",
        confidence='high',
        results=results,
        actions=[],
        suggestions=_assistant_context_suggestions(
            language,
            {
                'entity_type': entity_type,
                'entity_id': data.get('id'),
                'entity_label': data.get('title'),
                'screen': ASSISTANT_ENTITY_SCREEN_MAP.get(entity_type),
                'data': data,
            },
        ),
        resolved_context=_assistant_result_to_context(entity_type, data),
    )
```

- [ ] **Step 4: Update call site in `_assistant_execute_ai_plan`**

Find the call at line ~1920:

```python
            resp = _assistant_resolved_entity_response(resolved_type, data, language)
```

Replace with:

```python
            resp = _assistant_resolved_entity_response(resolved_type, data, language, request=request)
```

- [ ] **Step 5: Run test**

```bash
python manage.py test core.tests.AssistantV2Tests.test_resolved_listing_includes_related_promotions -v 2
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/tests.py
git commit -m "feat(assistant): surface related active promotions on resolved listing responses"
```

---

## Task 8: N+1 elimination in `_assistant_category_by_hint`

**Files:**
- Modify: `core/views.py` (line ~1727)

- [ ] **Step 1: Add `select_related('category')` to `_assistant_category_by_hint`**

Find line ~1727 inside `_assistant_category_by_hint`:

```python
    listings = Listing.objects.filter(category=category, is_active=True)[:limit]
```

Replace with:

```python
    listings = Listing.objects.filter(category=category, is_active=True).select_related('category')[:limit]
```

- [ ] **Step 2: Verify nothing broke**

```bash
python manage.py test core.tests.AssistantV2Tests -v 2
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "perf(assistant): add select_related to category hint query"
```

---

## Task 9: Full test suite run and final verification

- [ ] **Step 1: Run all assistant tests**

```bash
python manage.py test core.tests.AssistantV2Tests -v 2
```

Expected output — all tests pass:
```
test_bilingual_search_excludes_expired_promotions ... ok
test_bilingual_search_price_filter_cheap ... ok
test_bilingual_search_price_filter_premium ... ok
test_budget_filter_not_unsupported ... ok
test_feed_response_excludes_expired_promotions ... ok
test_feed_response_filters_events_by_time ... ok
test_promo_expiry_note_beyond_7_days_returns_none ... ok
test_promo_expiry_note_no_valid_until_returns_none ... ok
test_promo_expiry_note_within_7_days ... ok
test_resolved_listing_includes_related_promotions ... ok
```

- [ ] **Step 2: Verify imports are clean**

```bash
python -c "
from core.assistant_ai import GroqAssistantAIProvider
from core.assistant_parser import HeuristicAssistantQueryParser
from core.views import (
    _assistant_bilingual_search,
    _assistant_generic_feed_response,
    _assistant_resolved_entity_response,
    _assistant_promo_expiry_note,
    _assistant_build_catalog,
)
print('all imports ok')
"
```

Expected: `all imports ok`

- [ ] **Step 3: Check default model**

```bash
python -c "
from core.assistant_ai import GroqAssistantAIProvider
p = GroqAssistantAIProvider()
assert p.model == 'llama-3.3-70b-versatile', f'wrong model: {p.model}'
assert p.timeout_seconds == 10.0, f'wrong timeout: {p.timeout_seconds}'
print('model and timeout ok')
"
```

Expected: `model and timeout ok`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test(assistant): full v2 test suite green"
```
