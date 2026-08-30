"""Text normalisation helpers shared by parsing, dedupe and matching."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9+#. ]+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&rsquo;": "'",
    "&ldquo;": '"',
    "&rdquo;": '"',
}

#: Seniority and employment-type words that carry no matching signal in a title.
TITLE_NOISE_WORDS = frozenset(
    {
        "i", "ii", "iii", "iv", "v",
        "1", "2", "3", "4", "5",
        "sr", "senior", "jr", "junior", "staff", "principal", "lead",
        "entry", "level", "mid", "associate", "intern", "internship",
        "full", "part", "time", "fulltime", "parttime", "contract", "contractor",
        "remote", "hybrid", "onsite", "us", "usa", "the", "a", "an", "of", "and",
    }
)

STOP_WORDS = TITLE_NOISE_WORDS | frozenset(
    {
        "to", "in", "for", "with", "on", "at", "by", "or", "is", "are", "be",
        "we", "you", "our", "your", "as", "that", "this", "it", "will", "have",
    }
)


def strip_html(value: str | None) -> str:
    """Turn an HTML job description into readable plain text."""
    if not value:
        return ""
    text = value
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = _HTML_TAG_RE.sub(" ", text)
    for entity, replacement in _HTML_ENTITIES.items():
        text = text.replace(entity, replacement)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def normalize(value: str | None) -> str:
    """Lowercase, strip accents and collapse punctuation/whitespace."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def slugify(value: str | None) -> str:
    text = normalize(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def tokenize(value: str | None, *, drop_stop_words: bool = True) -> set[str]:
    tokens = {token for token in normalize(value).split() if len(token) > 1 or token in {"c", "r"}}
    if drop_stop_words:
        tokens -= STOP_WORDS
    return tokens


def normalize_title(title: str | None) -> str:
    """Title reduced to its meaningful words, for dedupe and title matching."""
    tokens = [token for token in normalize(title).split() if token not in TITLE_NOISE_WORDS]
    return " ".join(tokens)


def normalize_domain(value: str | None) -> str | None:
    """Extract the bare registrable-ish domain from a URL or host string."""
    if not value:
        return None
    text = value.strip().lower()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/")[0].split("?")[0].split("#")[0]
    text = text.split("@")[-1].split(":")[0]
    if text.startswith("www."):
        text = text[4:]
    return text or None


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def overlap_ratio(needed: set[str], available: set[str]) -> float:
    """Share of ``needed`` covered by ``available``; 1.0 when nothing is needed."""
    if not needed:
        return 1.0
    return len(needed & available) / len(needed)


def content_hash(*parts: str | None) -> str:
    joined = "|".join(normalize(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[: limit - 1] + "…"
