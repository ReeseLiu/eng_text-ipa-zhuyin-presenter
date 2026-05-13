"""Text-to-IPA/Improved-Zhuyin processing pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .phoneme_core.display_mapping import (
    build_display_bundle,
    load_display_exceptions_json,
    load_display_table_csv,
)
from .phoneme_core.g2p import MULTI_PHONEME_UNITS, SimpleG2P, sentence_to_canonical_words
from .phoneme_core.syllable_structure import analyze_syllable_tokens
from .phoneme_core.text_utils import normalize_word_token


SCHEMA_VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DISPLAY_TABLE_PATH = DATA_DIR / "display_mapping_table_syllable.csv"
DISPLAY_EXCEPTIONS_PATH = DATA_DIR / "display_mapping_exceptions.json"
CMUDICT_PATH = DATA_DIR / "cmudict.dict"


class Pipeline:
    def __init__(self) -> None:
        self.g2p = SimpleG2P(CMUDICT_PATH)
        self.display_table = load_display_table_csv(DISPLAY_TABLE_PATH)
        self.display_exceptions = load_display_exceptions_json(DISPLAY_EXCEPTIONS_PATH)

    def split_sentences(self, text: str) -> list[str]:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{2,}", "\n", normalized).strip()
        if not normalized:
            return []

        parts = re.findall(r"[^.!?。！？\n]+(?:[.!?。！？]+|$)", normalized)
        sentences = [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]
        return sentences

    def process_text(self, text: str, source: str | None = None) -> dict[str, Any]:
        sentences = [self.process_sentence(sentence, idx) for idx, sentence in enumerate(self.split_sentences(text), start=1)]
        return {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "type": "text",
                "name": source or "inline",
            },
            "sentences": sentences,
        }

    def process_sentence(self, sentence_text: str, sentence_id: int | str | None = None) -> dict[str, Any]:
        words = [self._record_to_word(record, idx) for idx, record in enumerate(sentence_to_canonical_words(sentence_text, self.g2p), start=1)]
        return {
            "sentence_id": str(sentence_id if sentence_id is not None else 1),
            "text": str(sentence_text or "").strip(),
            "words": words,
        }

    def process_word(self, word_text: str, context: dict | None = None) -> dict[str, Any]:
        context_tokens = []
        context_index = -1
        if isinstance(context, dict):
            raw_tokens = context.get("tokens", [])
            if isinstance(raw_tokens, list):
                context_tokens = [normalize_word_token(str(token or "")) for token in raw_tokens]
            try:
                context_index = int(context.get("index", -1))
            except (TypeError, ValueError):
                context_index = -1

        ipa_tokens, source, stress_levels = self.g2p.word_to_ipa_with_stress(
            str(word_text or ""),
            context={"tokens": context_tokens, "index": context_index} if context_tokens else None,
        )
        record = {
            "word": str(word_text or "").strip(),
            "word_norm": normalize_word_token(str(word_text or "")),
            "canonical_ipa": ipa_tokens,
            "canonical_stress_levels": stress_levels,
            "g2p_source": source,
        }
        return self._record_to_word(record, 1)

    def display_for_ipa(self, ipa_tokens: list[str], word_text: str | None = None, stress_levels: list[int | None] | None = None) -> dict[str, Any]:
        tokens = normalize_ipa_tokens(ipa_tokens)
        token_details = analyze_syllable_tokens(tokens)
        if stress_levels:
            for idx, detail in enumerate(token_details):
                detail["stress_level"] = stress_levels[idx] if idx < len(stress_levels) else None
        display = build_display_bundle(
            tokens,
            self.display_table,
            token_details=token_details,
            word_text=word_text,
            display_exceptions=self.display_exceptions,
        )
        return {
            "ipa": tokens,
            "display": display,
            "token_details": token_details,
        }

    def export_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        output = payload if isinstance(payload, dict) else {}
        if "schema_version" not in output:
            output = {"schema_version": SCHEMA_VERSION, **output}
        output.setdefault("export", {"status": "draft", "format": "text-ipa-zhuyin-presenter"})
        return output

    def get_display_table(self) -> dict[str, dict[str, str]]:
        output: dict[str, dict[str, str]] = {}
        for ipa, row in self.display_table.items():
            safe_row = row if isinstance(row, dict) else {}
            output[ipa] = {
                "ipa": ipa,
                "symbol_id": str(safe_row.get("symbol_id", "")),
                "kk": str(safe_row.get("kk", "")),
                "zhuyin_plus": str(safe_row.get("zhuyin_plus", "")),
                "zhuyin_plus_C1": str(safe_row.get("zhuyin_plus_C1", "")),
                "zhuyin_plus_V": str(safe_row.get("zhuyin_plus_V", "")),
                "zhuyin_plus_C2": str(safe_row.get("zhuyin_plus_C2", "")),
                "notes": str(safe_row.get("notes", "")),
            }
        return output

    def _record_to_word(self, record: dict[str, Any], word_index: int) -> dict[str, Any]:
        ipa_tokens = normalize_ipa_tokens(record.get("canonical_ipa", []))
        stress_levels = record.get("canonical_stress_levels", [])
        token_details = analyze_syllable_tokens(ipa_tokens)
        if isinstance(stress_levels, list):
            for idx, detail in enumerate(token_details):
                detail["stress_level"] = stress_levels[idx] if idx < len(stress_levels) else None
        display = build_display_bundle(
            ipa_tokens,
            self.display_table,
            token_details=token_details,
            word_text=record.get("word"),
            display_exceptions=self.display_exceptions,
        )
        return {
            "word_id": str(word_index),
            "word": record.get("word", ""),
            "word_norm": record.get("word_norm", ""),
            "g2p_source": record.get("g2p_source", ""),
            "ipa": ipa_tokens,
            "display": display,
            "token_details": token_details,
            "edited": False,
        }


def normalize_ipa_tokens(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if " " in raw:
            return [part for part in raw.split() if part]
        pattern = "|".join(re.escape(unit) for unit in sorted(MULTI_PHONEME_UNITS, key=len, reverse=True))
        return [token for token in re.findall(f"({pattern}|[^\\s])", raw) if token.strip()]
    if isinstance(value, list):
        return [str(token).strip() for token in value if str(token).strip()]
    return []


pipeline = Pipeline()
