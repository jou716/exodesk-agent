from __future__ import annotations

import re

from langdetect import DetectorFactory, LangDetectException, detect


DetectorFactory.seed = 0


LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")

LANGUAGE_NAMES = {
    "zh": "Chinese (Simplified)",
    "en": "English",
    "tr": "Turkish",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ar": "Arabic",
    "fa": "Persian",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "he": "Hebrew",
    "el": "Greek",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "cs": "Czech",
    "ro": "Romanian",
    "hu": "Hungarian",
}


def normalize_language_code(value: str | None, default: str = "en") -> str:
    code = (value or "").strip().lower().replace("_", "-")
    if not code:
        return default
    if code.startswith("zh"):
        return "zh"
    return code


def language_display_name(code: str) -> str:
    normalized = normalize_language_code(code)
    primary = normalized.split("-", 1)[0]
    return LANGUAGE_NAMES.get(primary, f"the customer's original language (ISO code: {normalized})")


def detect_text_language(text: str, default: str = "en") -> str:
    value = text.strip()
    if not value:
        return default
    try:
        return normalize_language_code(detect(value), default=default)
    except LangDetectException:
        return "zh" if any("\u4e00" <= char <= "\u9fff" for char in value) else default
