import json
import os
import re
from functools import lru_cache

_WIKI_PATH = os.path.join(os.path.dirname(__file__), 'data', 'gevgelija_wiki.json')


@lru_cache(maxsize=1)
def _load_articles() -> tuple:
    try:
        with open(_WIKI_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return tuple(data.get('articles') or [])
    except (OSError, json.JSONDecodeError):
        return ()


def _normalize(text: str) -> str:
    return re.sub(r'[^\w\s]', ' ', (text or '').lower()).strip()


def _score_article(article: dict, terms: list[str]) -> int:
    score = 0
    slug = _normalize(article.get('slug') or '')
    tags = ' '.join(article.get('tags') or [])
    title_en = _normalize(article.get('title_en') or '')
    title_mk = _normalize(article.get('title_mk') or '')
    short_en = _normalize(article.get('short_description_en') or '')
    short_mk = _normalize(article.get('short_description_mk') or '')

    for term in terms:
        if not term:
            continue
        if term in slug:
            score += 5
        if term in tags:
            score += 4
        if term in title_en or term in title_mk:
            score += 3
        if term in short_en or term in short_mk:
            score += 2
        for section in article.get('sections') or []:
            if term in _normalize(section.get('content_en') or ''):
                score += 1
            if term in _normalize(section.get('content_mk') or ''):
                score += 1

    return score


def _is_cyrillic(text: str) -> bool:
    return any('Ѐ' <= c <= 'ӿ' for c in (text or ''))


def search_wiki(query_en: str, query_mk: str, top_n: int = 2) -> str:
    """Return a formatted block of the most relevant wiki sections for GoAI context."""
    articles = _load_articles()
    if not articles:
        return ''

    terms: list[str] = []
    for q in [query_en, query_mk]:
        if q:
            terms.extend(t for t in _normalize(q).split() if len(t) >= 3)
    terms = list(dict.fromkeys(terms))

    if not terms:
        return ''

    scored = sorted(
        ((a, _score_article(a, terms)) for a in articles),
        key=lambda x: x[1],
        reverse=True,
    )
    top = [(a, s) for a, s in scored if s >= 3][:top_n]

    if not top:
        return ''

    lang = 'mk' if _is_cyrillic(query_mk) else 'en'
    lines: list[str] = []

    for article, _ in top:
        title = article.get(f'title_{lang}') or article.get('title_en') or ''
        lines.append(f"[{title}]")
        for section in (article.get('sections') or [])[:3]:
            sec_title = section.get(f'title_{lang}') or section.get('title_en') or ''
            content = section.get(f'content_{lang}') or section.get('content_en') or ''
            if content:
                lines.append(f"{sec_title}: {content}")

    return '\n'.join(lines)
