import logging
import os
import re
from dataclasses import asdict, dataclass, field
from difflib import get_close_matches
from typing import Any


logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", (value or "").lower())).strip()


def _tokenize(value: str) -> list[str]:
    return [token for token in _normalize_text(value).split() if token]


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _keyword_match(normalized_message: str, tokens: list[str], keywords: list[str], fuzzy_cutoff: float = 0.82) -> tuple[bool, list[str], bool]:
    matched = []
    exact = False

    normalized_keywords = [_normalize_text(keyword) for keyword in keywords if keyword]
    for keyword in normalized_keywords:
        if not keyword:
            continue

        if " " in keyword:
            if keyword in normalized_message:
                matched.append(keyword)
                exact = True
            continue

        if keyword in tokens:
            matched.append(keyword)
            exact = True
            continue

        if len(keyword) < 4:
            continue

        close = get_close_matches(keyword, tokens, n=1, cutoff=fuzzy_cutoff)
        if close and close[0] and close[0][0] == keyword[0] and abs(len(close[0]) - len(keyword)) <= 2:
            matched.append(keyword)

    matched = _dedupe_preserving_order(matched)
    return bool(matched), matched, exact


STOPWORDS = {
    'a', 'an', 'and', 'any', 'about', 'around', 'at', 'be', 'can', 'for', 'from',
    'get', 'give', 'have', 'help', 'i', 'im', 'in', 'info', 'information', 'is',
    'it', 'me', 'need', 'on', 'or', 'please', 'show', 'some', 'tell', 'that',
    'the', 'there', 'this', 'to', 'what', 'where', 'which', 'with', 'you',
    'дали', 'има', 'ми', 'ме', 'на', 'за', 'каде', 'кое', 'кој', 'која', 'ова',
    'овој', 'оваа', 'тоа', 'тие', 'сакам', 'треба', 'покажи', 'кажи', 'дали',
}


FAQ_RULES = [
    {
        'intent': 'language_help',
        'keywords': ['language', 'change language', 'lang', 'јазик', 'смени јазик'],
        'canonical_terms': ['language'],
    },
    {
        'intent': 'wishlist_help',
        'keywords': ['wishlist', 'favorite', 'favourite', 'favorites', 'омилени', 'листа на желби'],
        'canonical_terms': ['wishlist'],
    },
    {
        'intent': 'support_help',
        'keywords': ['support', 'help support', 'problem', 'issue', 'bug', 'поддршка', 'помош', 'проблем'],
        'canonical_terms': ['support'],
    },
    {
        'intent': 'collaboration_help',
        'keywords': ['collaboration', 'partner', 'partnership', 'business', 'соработка', 'партнерство'],
        'canonical_terms': ['collaboration'],
    },
    {
        'intent': 'currency_help',
        'keywords': ['currency', 'exchange', 'rate', 'rates', 'валута', 'курс', 'курсеви', 'менувачница'],
        'canonical_terms': ['currency'],
    },
    {
        'intent': 'border_help',
        'keywords': ['border', 'camera', 'cameras', 'граница', 'камери'],
        'canonical_terms': ['border camera'],
    },
    {
        'intent': 'account_help',
        'keywords': ['guest', 'register', 'sign up', 'signup', 'login', 'account', 'гостин', 'регистрација', 'најава'],
        'canonical_terms': ['guest register login'],
    },
]


LISTING_CATEGORY_RULES = [
    {
        'intent': 'listing_search',
        'entity_type': 'listing',
        'category_key': 'accommodation',
        'keywords': ['hotel', 'hotels', 'accommodation', 'sleep', 'stay', 'motel', 'hostel', 'апартман', 'сместување', 'хотел'],
        'category_terms': ['Sleep & Rest', 'Accommodation', 'Hotel'],
        'canonical_terms': ['hotel accommodation'],
        'search_query': 'hotel accommodation',
    },
    {
        'intent': 'listing_search',
        'entity_type': 'listing',
        'category_key': 'food',
        'keywords': ['food', 'eat', 'restaurant', 'restaurants', 'cafe', 'coffee', 'breakfast', 'lunch', 'dinner', 'храна', 'ресторан', 'кафе'],
        'category_terms': ['Food', 'Restaurant', 'Cafe'],
        'canonical_terms': ['restaurant food cafe'],
        'search_query': 'restaurant food',
    },
    {
        'intent': 'listing_search',
        'entity_type': 'listing',
        'category_key': 'dental',
        'keywords': ['dentist', 'dental', 'teeth', 'tooth', 'стоматолог', 'забар'],
        'category_terms': ['Dental Clinic', 'Dentist'],
        'canonical_terms': ['dentist dental'],
        'search_query': 'dentist',
    },
    {
        'intent': 'listing_search',
        'entity_type': 'listing',
        'category_key': 'fuel',
        'keywords': ['gas', 'petrol', 'fuel', 'station', 'pump', 'бензин', 'пумпа'],
        'category_terms': ['Petrol Station'],
        'canonical_terms': ['petrol station fuel'],
        'search_query': 'petrol station',
    },
    {
        'intent': 'listing_search',
        'entity_type': 'listing',
        'category_key': 'services',
        'keywords': ['service', 'services', 'mechanic', 'auto', 'repair', 'сервис', 'авто'],
        'category_terms': ['Auto services', 'Services'],
        'canonical_terms': ['services auto'],
        'search_query': 'services',
    },
]


FEED_RULES = [
    {
        'intent': 'event_search',
        'entity_type': 'event',
        'content_type': 'events',
        'keywords': ['event', 'events', 'happening', 'concert', 'party', 'festival', 'настан', 'настани', 'концерт'],
        'canonical_terms': ['events'],
        'search_query': 'events',
    },
    {
        'intent': 'promotion_search',
        'entity_type': 'promotion',
        'content_type': 'promotions',
        'keywords': ['deal', 'deals', 'promo', 'promotion', 'promotions', 'offer', 'discount', 'понуда', 'промоција', 'попуст'],
        'canonical_terms': ['promotion deal'],
        'search_query': 'promotion',
    },
    {
        'intent': 'blog_search',
        'entity_type': 'blog',
        'content_type': 'blogs',
        'keywords': ['blog', 'article', 'guide', 'story', 'blog post', 'статија', 'водич'],
        'canonical_terms': ['blog article'],
        'search_query': 'blog',
    },
]


CONTEXT_SIGNAL_RULES = [
    {
        'slot': 'contact',
        'keywords': ['call', 'phone', 'contact', 'number', 'ring', 'јави', 'телефон', 'контакт', 'број'],
        'canonical_terms': ['call phone contact'],
    },
    {
        'slot': 'directions',
        'keywords': ['map', 'direction', 'directions', 'where', 'address', 'route', 'мапа', 'насока', 'адреса', 'локација'],
        'canonical_terms': ['map direction address'],
    },
    {
        'slot': 'open_now',
        'keywords': ['open', 'opened', 'hours', 'working', 'available now', 'отворено', 'отворен', 'работно време'],
        'canonical_terms': ['open hours'],
        'filter_key': 'open_now',
        'filter_value': True,
    },
    {
        'slot': 'price',
        'keywords': ['price', 'ticket', 'entry', 'cost', 'цена', 'влез', 'билет'],
        'canonical_terms': ['price entry'],
    },
    {
        'slot': 'age_limit',
        'keywords': ['age', 'limit', 'adult', 'child', 'возраст', 'ограничување'],
        'canonical_terms': ['age limit'],
    },
    {
        'slot': 'promo_code',
        'keywords': ['code', 'discount code', 'coupon', 'код', 'код за попуст', 'купон'],
        'canonical_terms': ['discount code'],
    },
    {
        'slot': 'expiry',
        'keywords': ['expire', 'expiry', 'valid until', 'end', 'истек', 'истекува', 'важи до'],
        'canonical_terms': ['expire valid until'],
    },
    {
        'slot': 'summary',
        'keywords': ['summary', 'summarize', 'about', 'details', 'info', 'information', 'сумирај', 'за што', 'инфо'],
        'canonical_terms': ['summary info'],
    },
    {
        'slot': 'related_promotions',
        'keywords': ['promotion', 'deal', 'offer', 'discount', 'промоција', 'понуда', 'попуст'],
        'canonical_terms': ['promotion deal'],
    },
    {
        'slot': 'related_events',
        'keywords': ['event', 'events', 'happening', 'настан', 'настани'],
        'canonical_terms': ['events'],
    },
]


SOFT_FILTER_RULES = [
    {
        'filter_key': 'budget',
        'keywords': ['cheap', 'affordable', 'budget', 'low cost', 'евтин', 'евтино', 'пристапно'],
        'unsupported': True,
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


@dataclass
class AssistantQueryUnderstanding:
    provider: str
    confidence: str = 'low'
    intent: str = 'unknown'
    entity_type: str | None = None
    content_type: str = 'all'
    faq_intent: str | None = None
    category_key: str | None = None
    category_terms: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    unsupported_filters: list[str] = field(default_factory=list)
    canonical_terms: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    search_query: str = ''

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['canonical_terms'] = _dedupe_preserving_order(payload['canonical_terms'])
        payload['matched_terms'] = _dedupe_preserving_order(payload['matched_terms'])
        payload['category_terms'] = _dedupe_preserving_order(payload['category_terms'])
        payload['unsupported_filters'] = _dedupe_preserving_order(payload['unsupported_filters'])
        payload['filters'] = {key: value for key, value in payload['filters'].items() if value not in (None, '', [], {})}
        return payload


class BaseAssistantQueryParser:
    provider_name = 'base'

    def parse(self, message: str, language: str = 'en', context: dict[str, Any] | None = None, history: list[dict[str, Any]] | None = None) -> AssistantQueryUnderstanding:
        raise NotImplementedError


class HeuristicAssistantQueryParser(BaseAssistantQueryParser):
    provider_name = 'heuristic'

    def parse(self, message: str, language: str = 'en', context: dict[str, Any] | None = None, history: list[dict[str, Any]] | None = None) -> AssistantQueryUnderstanding:
        normalized_message = _normalize_text(message)
        tokens = _tokenize(message)
        understanding = AssistantQueryUnderstanding(provider=self.provider_name, search_query=message.strip())
        confidence_score = 0

        for rule in FAQ_RULES:
            matched, matched_terms, exact = _keyword_match(normalized_message, tokens, rule['keywords'])
            if not matched:
                continue
            understanding.intent = 'app_help'
            understanding.faq_intent = rule['intent']
            understanding.canonical_terms.extend(rule['canonical_terms'])
            understanding.matched_terms.extend(matched_terms)
            confidence_score = max(confidence_score, 4 if exact else 3)
            break

        if understanding.intent == 'unknown':
            for rule in LISTING_CATEGORY_RULES:
                matched, matched_terms, exact = _keyword_match(normalized_message, tokens, rule['keywords'])
                if not matched:
                    continue
                understanding.intent = rule['intent']
                understanding.entity_type = rule['entity_type']
                understanding.category_key = rule['category_key']
                understanding.category_terms.extend(rule['category_terms'])
                understanding.canonical_terms.extend(rule['canonical_terms'])
                understanding.matched_terms.extend(matched_terms)
                understanding.search_query = rule['search_query']
                confidence_score = max(confidence_score, 4 if exact else 3)
                break

        if understanding.intent == 'unknown':
            for rule in FEED_RULES:
                matched, matched_terms, exact = _keyword_match(normalized_message, tokens, rule['keywords'])
                if not matched:
                    continue
                understanding.intent = rule['intent']
                understanding.entity_type = rule['entity_type']
                understanding.content_type = rule['content_type']
                understanding.canonical_terms.extend(rule['canonical_terms'])
                understanding.matched_terms.extend(matched_terms)
                understanding.search_query = rule['search_query']
                confidence_score = max(confidence_score, 4 if exact else 3)
                break

        for rule in CONTEXT_SIGNAL_RULES:
            matched, matched_terms, exact = _keyword_match(normalized_message, tokens, rule['keywords'])
            if not matched:
                continue
            understanding.canonical_terms.extend(rule['canonical_terms'])
            understanding.matched_terms.extend(matched_terms)
            if rule.get('filter_key'):
                understanding.filters[rule['filter_key']] = rule.get('filter_value', True)
            confidence_score = max(confidence_score, 3 if exact else 2)

        for rule in SOFT_FILTER_RULES:
            matched, matched_terms, exact = _keyword_match(normalized_message, tokens, rule['keywords'])
            if not matched:
                continue
            understanding.filters[rule['filter_key']] = True
            if rule.get('unsupported'):
                understanding.unsupported_filters.append(rule['filter_key'])
            understanding.matched_terms.extend(matched_terms)
            confidence_score = max(confidence_score, 2 if exact else 1)

        if context and context.get('entity_type'):
            if any(token in tokens for token in ['this', 'it', 'them', 'that', 'ова', 'овој', 'оваа', 'тоа', 'тие']):
                understanding.entity_type = context['entity_type']
                understanding.intent = 'contextual_followup' if understanding.intent == 'unknown' else understanding.intent
                confidence_score = max(confidence_score, 3)

        if history and understanding.intent == 'unknown':
            if any(token in tokens for token in ['first', 'second', 'last', 'прво', 'второ', 'последно']):
                understanding.intent = 'followup_reference'
                confidence_score = max(confidence_score, 2)

        if not understanding.search_query.strip():
            core_tokens = [token for token in tokens if token not in STOPWORDS]
            understanding.search_query = " ".join(core_tokens[:6]) or message.strip()

        understanding.canonical_terms = _dedupe_preserving_order(understanding.canonical_terms)
        understanding.matched_terms = _dedupe_preserving_order(understanding.matched_terms)

        if confidence_score >= 4:
            understanding.confidence = 'high'
        elif confidence_score >= 2:
            understanding.confidence = 'medium'
        else:
            understanding.confidence = 'low'

        return understanding


def get_assistant_query_parser() -> BaseAssistantQueryParser:
    provider = (os.getenv('ASSISTANT_QUERY_PARSER_PROVIDER') or 'heuristic').strip().lower()
    if provider == 'heuristic':
        return HeuristicAssistantQueryParser()

    logger.warning("Unsupported assistant query parser provider '%s'; falling back to heuristic parser", provider)
    return HeuristicAssistantQueryParser()
