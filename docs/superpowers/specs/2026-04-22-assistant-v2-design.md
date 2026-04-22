# GoGevgelija Assistant v2 — Design Spec

**Date:** 2026-04-22
**Scope:** Backend only (no frontend changes)
**Goal:** Bigger model, fix all known gaps, add new capabilities, improve performance

---

## Background

The current assistant (`v1`) uses a two-layer hybrid: Groq `llama-3.1-8b-instant` as the AI planner returning strict JSON, with a heuristic keyword parser as fallback. The backend handles all user-facing text generation.

Known gaps in v1:
- `price_filter` is extracted by AI but never applied to DB queries
- Promotions are not filtered by validity (`valid_until`)
- `feed` tool ignores `time_filter` and `open_now` from the AI plan
- `open_now` over-fetches records (limit * 3) and serializes all before filtering in Python
- `price_filter` is listed as "unsupported" in the heuristic parser even though we're now implementing it
- Catalog entity limits are low (40/15/10), titles are EN-only, so Groq misses Cyrillic-named entities
- Cache TTLs are short (10min) for data that rarely changes intraday

---

## 1. Model Upgrade

**File:** `core/assistant_ai.py`

- Default model: `llama-3.1-8b-instant` → `llama-3.3-70b-versatile`
- Default timeout: `8s` → `10s`
- System prompt: minor refinement to leverage stronger multilingual and multi-turn reasoning of the 70b model (better Cyrillic/Latin/English disambiguation, stronger follow-up chain resolution)
- No schema changes — same strict JSON output contract

Env var `ASSISTANT_GROQ_MODEL` still overrides the default.

---

## 2. Bug Fixes

### 2a. Price filter — `_assistant_bilingual_search`

**File:** `core/views.py`

Apply `price_filter` to event queries:
- `cheap` → filter `entry_price__iregex` for "Free|free|Бесплатно|бесплатно|0"
- `premium` → exclude the above (non-free events)
- `mid` → no filter (too ambiguous without a price range field)
- Listings: no `price` field exists — skip silently, do not error

### 2b. Promotion validity — `_assistant_bilingual_search`

**File:** `core/views.py`

Always filter promotions to active ones:
```
valid_until__gte=today OR valid_until__isnull=True
```
Sort by `valid_until` ascending (soonest-expiring first, null last).

### 2c. Feed tool time/open_now passthrough

**File:** `core/views.py`

`_assistant_generic_feed_response` currently ignores `time_filter` and `open_now`.
Pass both from the AI plan so "events this weekend" and "open now" work through the `feed` tool path, not just `search`.

Signature change:
```python
def _assistant_generic_feed_response(normalized_message, language, request, time_filter=None, open_now=False)
```

Update the call site in `_assistant_execute_ai_plan` to pass `plan.get('time_filter')` and `plan.get('open_now_requested')`.

### 2d. open_now over-fetch

**File:** `core/views.py`

Current: fetches `limit * 3` listings, serializes all, filters `is_open` in Python.
Fix: fetch `limit * 2`, serialize only that batch. The 2x multiplier gives enough headroom to find `limit` open listings without serializing unnecessary data.

### 2e. price_filter unsupported label

**File:** `core/assistant_parser.py`

Remove `price_filter` from `unsupported_filters` in `SOFT_FILTER_RULES`. It is now supported for events.

---

## 3. New Capabilities

### 3a. Promotion expiry awareness

**File:** `core/views.py`

When the response includes promotions, check each promo's `valid_until`. If a promo expires within 7 days, append "— expires in X days" to the answer text or include it in the result subtitle data.

Implementation: add a helper `_assistant_promo_expiry_note(promo_data, language)` that returns a localized string or `None`. Appended to the answer text inside `_assistant_promotion_answer` (not the subtitle — answer text is user-visible, subtitle is UI-only).

### 3b. Cross-linked promotions on listing responses

**File:** `core/views.py`

When the assistant returns a single resolved listing (via `resolved_entity_id`), check its `promotions` M2M for active promotions. If any exist, append up to 2 as additional results in the same response payload.

Implementation: `_assistant_resolved_entity_response` receives serialized `data` (dict), not a model instance. After building the listing result, do a targeted lookup: `Listing.objects.filter(id=data['id']).prefetch_related('promotions').first()` then serialize `listing_obj.promotions.filter(is_active=True)[:2]`. Extend `results` with the promotion entries.

### 3c. Free events price filtering (end-to-end)

Combined result of fixes 2a and 2e: the full query chain now works:

> "Show me free events tonight"
> → AI: `price_filter: cheap`, `time_filter: tonight`, `entity_type_hint: event`
> → backend: events filtered by entry_price + date_time range

---

## 4. Performance

### 4a. Cache TTL increases

**File:** `core/views.py`

| Constant | Before | After | Reason |
|---|---|---|---|
| `_ASSISTANT_CATALOG_TTL` | 600s (10min) | 3600s (60min) | Listings/categories change rarely intraday |
| `_ASSISTANT_PLAN_CACHE_TTL` | 600s (10min) | 1800s (30min) | Repeated queries benefit from longer cache |

### 4b. Bilingual catalog improvements

**File:** `core/views.py`

In `_assistant_build_catalog`:
- Increase limits: listings 40→60, events 15→20, promotions 10→15
- Add `title_mk` to each entity entry so Groq can match Cyrillic-written names
- Use `.only('id', 'title', 'title_mk')` to keep the DB query lean

### 4c. N+1 elimination

**File:** `core/views.py`

Add `.select_related('category')` to listing and event querysets in `_assistant_bilingual_search` and `_assistant_category_by_hint`. Eliminates per-row category lookups during serialization.

---

## Files Changed

| File | Changes |
|---|---|
| `core/assistant_ai.py` | Model default, timeout default, system prompt refinement |
| `core/assistant_parser.py` | Remove `price_filter` from unsupported_filters |
| `core/views.py` | Price filter, promotion validity, feed passthrough, open_now, catalog, cache TTLs, expiry notes, cross-linked promos, select_related |

**No migrations. No frontend changes. No new dependencies.**

---

## Success Criteria

- "Show me free events tonight" returns only free events filtered to tonight's time range
- "Any deals?" returns only promotions with valid_until >= today, sorted soonest-expiring first
- Promotions expiring within 7 days show an expiry note
- A listing response includes its related active promotions (if any)
- "Events this weekend" works via `feed` tool path (not just `search`)
- Catalog cache survives 60 minutes without a rebuild
- Common queries (e.g. "show me restaurants") served from plan cache for 30 minutes
- No regressions on existing context/faq/category/search flows
