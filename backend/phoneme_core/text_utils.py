"""Text normalization helpers for the standalone presenter."""

from __future__ import annotations

import re


PUNCT_STRIP_RE = re.compile(r"[.,!?;:…]+$")


def normalize_text(text: str) -> str:
    """Normalize text for matching and tokenization."""
    normalized = text.lower().replace("’", "'")
    normalized = re.sub(r"[^a-z0-9'\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_word_token(token: str) -> str:
    """Normalize a single token while keeping apostrophes."""
    normalized = token.lower().replace("’", "'")
    normalized = re.sub(r"[^a-z0-9']+", "", normalized)
    return normalized.strip()


def tokenize_words(text: str) -> list[str]:
    """Tokenize normalized words."""
    return re.findall(r"[a-z0-9']+", normalize_text(text))


def parse_clean_line_words(line: str) -> list[dict]:
    """Parse text line into word dicts with original and normalized forms."""
    line_norm = line.replace("’", "'")
    words = []
    for match in re.finditer(r"[A-Za-z0-9']+(?:[.,!?;:…]+)?", line_norm):
        token = match.group(0)
        token_base = PUNCT_STRIP_RE.sub("", token)
        token_norm = normalize_word_token(token_base)
        if token_norm:
            words.append({"word": token_base, "norm": token_norm})
    return words
