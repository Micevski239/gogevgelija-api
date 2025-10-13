from __future__ import annotations

from typing import Optional

from django.conf import settings


_SUPPORTED_LANG_CODES = {code for code, _ in settings.LANGUAGES}


def _normalize_language(code: Optional[str]) -> str:
    """Collapse a raw language value to a supported language code."""
    if not code:
        return settings.LANGUAGE_CODE

    # Split Accept-Language style values "mk,en;q=0.8"
    primary = code.split(',')[0].strip()
    if not primary:
        return settings.LANGUAGE_CODE

    # Extract base language (ignore regional subtags)
    base = primary.split('-')[0].lower()
    return base if base in _SUPPORTED_LANG_CODES else settings.LANGUAGE_CODE


def get_preferred_language(request) -> str:
    """Resolve the language that should drive localized responses."""
    # LocaleMiddleware sets LANGUAGE_CODE using Accept-Language headers
    lang_from_request = getattr(request, "LANGUAGE_CODE", None)
    if lang_from_request:
        lang = _normalize_language(lang_from_request)
        if lang:
            return lang

    # Fall back to the user's persisted preference
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False) and hasattr(user, "profile"):
        profile_lang = _normalize_language(user.profile.language_preference)
        if profile_lang:
            return profile_lang

    # Finally honour the raw header if middleware did not run
    header_lang = _normalize_language(request.headers.get("Accept-Language"))
    if header_lang:
        return header_lang

    return settings.LANGUAGE_CODE
