"""Text-to-IPA/Improved-Zhuyin processing pipeline."""

from __future__ import annotations

import csv
import json
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
PHONETIC_NUMBER_TABLE_PATH = DATA_DIR / "display_mapping_table_phonetic_number.csv"
CMUDICT_PATH = DATA_DIR / "cmudict.dict"
JASON_SLOT_ORDER = ("C1", "V", "C2")
WORD_SEGMENT_HINTS: dict[str, list[str]] = {
    "sometimes": ["some", "times"],
    "someone": ["some", "one"],
    "somebody": ["some", "body"],
    "something": ["some", "thing"],
    "somewhere": ["some", "where"],
    "everyone": ["every", "one"],
    "everybody": ["every", "body"],
    "everything": ["every", "thing"],
    "however": ["how", "ever"],
    "whatever": ["what", "ever"],
    "whenever": ["when", "ever"],
    "wherever": ["where", "ever"],
    "headquarters": ["head", "quar", "ters"],
    "measurement": ["mea", "sure", "ment"],
    "membership": ["mem", "ber", "ship"],
    "temperature": ["tem", "pera", "ture"],
    "shareholder": ["share", "hol", "der"],
    "convention": ["con", "ven", "tion"],
    "independence": ["in", "de", "pen", "dence"],
    "theoretical": ["the", "o", "re", "ti", "cal"],
    "concentration": ["con", "cen", "tra", "tion"],
    "accommodation": ["a", "cco", "mmo", "da", "tion"],
    "communication": ["co", "mmu", "ni", "ca", "tion"],
    "revolutionary": ["re", "vo", "lu", "tio", "na", "ry"],
}
WORD_WITH_PUNCT_RE = re.compile(r"^([A-Za-z']+)([.,!?;:…]*)$")


def load_phonetic_number_table_csv(path: Path) -> tuple[dict[str, int], list[str]]:
    mapping: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"zhuyin_plus", "phonetic_Number"}
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        missing_cols = sorted(required - set(reader.fieldnames))
        if missing_cols:
            raise ValueError(f"CSV missing required columns: {', '.join(missing_cols)}")

        for line_idx, row in enumerate(reader, start=2):
            zhuyin = (row.get("zhuyin_plus") or "").strip()
            raw_number = (row.get("phonetic_Number") or "").strip()
            if not raw_number:
                continue
            if not raw_number.isdigit():
                raise ValueError(f"Invalid phonetic_Number '{raw_number}' in CSV line {line_idx}")
            if not zhuyin:
                continue
            number = int(raw_number)
            existing = mapping.get(zhuyin)
            if existing is not None and existing != number:
                raise ValueError(f"Duplicate zhuyin_plus token '{zhuyin}' with conflicting number in CSV line {line_idx}")
            mapping[zhuyin] = number

    symbols = sorted(mapping.keys(), key=lambda token: (-len(token), token))
    return mapping, symbols


def _normalize_syllable_slot(value: Any) -> str:
    slot = str(value or "")
    return slot if slot in JASON_SLOT_ORDER else "V"


def _normalize_syllable_index(value: Any) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str) and value.isdigit():
        return max(0, int(value))
    return 0


def _normalize_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        as_int = int(value)
        return as_int if as_int > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        as_int = int(value.strip())
        return as_int if as_int > 0 else None
    return None


def _guess_english_syllable_count(word_text: str) -> int:
    text = str(word_text or "").lower().replace("’", "'")
    text = re.sub(r"(?:'s|s')$", "", text)
    text = re.sub(r"[^a-z]", "", text)
    if not text:
        return 1
    if len(text) <= 3:
        return 1

    groups = re.findall(r"[aeiouy]+", text)
    count = len(groups)

    if text.endswith("e") and not re.search(r"[^aeiouy]le$", text):
        count -= 1

    return max(1, count)


def _group_tokens_by_syllable(tokens: list[str], syllable_count: int | None) -> list[list[str]]:
    compact = [token for token in tokens if token]
    if not compact:
        return []

    if syllable_count is None:
        return [[token] for token in compact]

    target = max(1, min(syllable_count, len(compact)))
    base = len(compact) // target
    remainder = len(compact) % target
    groups: list[list[str]] = []
    cursor = 0

    for idx in range(target):
        size = base + (1 if idx < remainder else 0)
        if size <= 0:
            continue
        groups.append(compact[cursor : cursor + size])
        cursor += size

    return groups


def _split_surface_text_for_rows(surface_text: str, row_count: int) -> list[str]:
    if row_count <= 0:
        return []

    trimmed = str(surface_text or "").strip()
    if row_count == 1:
        return [trimmed]
    if not trimmed:
        return ["" for _ in range(row_count)]

    matched = WORD_WITH_PUNCT_RE.match(trimmed)
    if not matched:
        return [trimmed, *([""] * (row_count - 1))]

    core_word, punct = matched.groups()
    hinted = WORD_SEGMENT_HINTS.get(core_word.lower())
    if not isinstance(hinted, list) or len(hinted) != row_count:
        return [trimmed, *([""] * (row_count - 1))]

    built: list[str] = []
    for idx, hint_raw in enumerate(hinted):
        hint = str(hint_raw or "").strip()
        if not hint:
            return [trimmed, *([""] * (row_count - 1))]
        if idx == len(hinted) - 1 and punct:
            hint = f"{hint}{punct}"
        built.append(hint)

    if core_word[:1].isupper() and built and built[0]:
        built[0] = built[0][:1].upper() + built[0][1:]

    return built


def _fallback_syllable_count_for_word(word: dict[str, Any], surface_text: str) -> int | None:
    manual = _normalize_positive_int(word.get("manual_syllable_count"))
    if manual is not None:
        return manual

    guessed = _normalize_positive_int(word.get("syllable_count_guess"))
    if guessed is not None:
        return guessed

    raw_ipa = word.get("ipa")
    has_ipa = isinstance(raw_ipa, list) and any(str(token or "").strip() for token in raw_ipa)
    source = str(word.get("g2p_source") or "")
    if source == "missing" or not has_ipa:
        return _guess_english_syllable_count(str(word.get("word") or surface_text or ""))

    return None


def _parse_zhuyin_numbers(token: str, phonetic_number_map: dict[str, int], sorted_symbols: list[str]) -> list[int]:
    text = str(token or "").strip()
    if not text:
        return []

    direct = phonetic_number_map.get(text)
    if direct is not None:
        return [direct]

    memo: dict[int, list[int] | None] = {}

    def walk(start: int) -> list[int] | None:
        if start == len(text):
            return []
        if start in memo:
            return memo[start]

        for symbol in sorted_symbols:
            if not text.startswith(symbol, start):
                continue
            tail = walk(start + len(symbol))
            if tail is None:
                continue
            result = [phonetic_number_map[symbol], *tail]
            memo[start] = result
            return result

        memo[start] = None
        return None

    segmented = walk(0)
    return segmented if segmented is not None else []


def _normalize_slot_tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(token or "").strip() for token in value if str(token or "").strip()]
    if isinstance(value, str):
        return [part for part in re.split(r"[\s,]+", value.strip()) if part]
    return []


def _build_phonetic_row_from_slots(
    slots: dict[str, Any],
    phonetic_number_map: dict[str, int],
    sorted_symbols: list[str],
) -> list[Any]:
    row: list[Any] = []
    for slot in JASON_SLOT_ORDER:
        slot_tokens = _normalize_slot_tokens(slots.get(slot))
        if not slot_tokens:
            continue

        merged_numbers: list[int] = []
        parsed_token_count = 0
        for token in slot_tokens:
            numbers = _parse_zhuyin_numbers(token, phonetic_number_map, sorted_symbols)
            if not numbers:
                continue
            merged_numbers.extend(numbers)
            parsed_token_count += 1

        if not merged_numbers:
            continue
        if len(merged_numbers) > 1 or parsed_token_count > 1:
            row.append(merged_numbers)
        else:
            row.append(merged_numbers[0])

    return row


def _build_manual_phonetic_rows(
    word: dict[str, Any],
    surface_text: str,
    phonetic_number_map: dict[str, int],
    sorted_symbols: list[str],
) -> list[dict[str, Any]]:
    raw_rows = word.get("manual_syllables") if isinstance(word, dict) else None
    if not isinstance(raw_rows, list):
        return []

    rows: list[dict[str, Any]] = []
    for row_raw in raw_rows:
        if not isinstance(row_raw, dict):
            continue
        text = str(row_raw.get("text") or "")
        slots = row_raw.get("slots") if isinstance(row_raw.get("slots"), dict) else {}
        phonetic = _build_phonetic_row_from_slots(slots, phonetic_number_map, sorted_symbols)
        if not phonetic:
            continue
        rows.append({
            "text": text,
            "phonetic": phonetic,
        })

    if rows and not any(str(row.get("text") or "").strip() for row in rows):
        rows[0]["text"] = surface_text

    return rows


def _build_phonetic_rows(
    display_zhuyin_tokens: list[str],
    token_details: list[dict],
    phonetic_number_map: dict[str, int],
    sorted_symbols: list[str],
    fallback_syllable_count: int | None = None,
) -> list[list[Any]]:
    tokens = [str(token or "").strip() for token in display_zhuyin_tokens]
    if not tokens:
        return []

    if len(tokens) != len(token_details):
        fallback_rows: list[list[Any]] = []
        for group in _group_tokens_by_syllable(tokens, fallback_syllable_count):
            group_numbers: list[int] = []
            for token in group:
                numbers = _parse_zhuyin_numbers(token, phonetic_number_map, sorted_symbols)
                if not numbers:
                    continue
                group_numbers.extend(numbers)
            if not group_numbers:
                continue
            fallback_rows.append(group_numbers)
        return fallback_rows

    syllable_map: dict[int, dict[str, list[int]]] = {}
    slot_counts: dict[int, dict[str, int]] = {}
    for detail in token_details:
        safe_detail = detail if isinstance(detail, dict) else {}
        slot = _normalize_syllable_slot(safe_detail.get("syllable_slot"))
        syllable_index = _normalize_syllable_index(safe_detail.get("syllable_index"))
        counts = slot_counts.setdefault(syllable_index, {"C1": 0, "V": 0, "C2": 0})
        counts[slot] = counts.get(slot, 0) + 1

    for idx, token in enumerate(tokens):
        if not token:
            continue
        detail = token_details[idx] if isinstance(token_details[idx], dict) else {}
        slot = _normalize_syllable_slot(detail.get("syllable_slot"))
        syllable_index = _normalize_syllable_index(detail.get("syllable_index"))
        numbers = _parse_zhuyin_numbers(token, phonetic_number_map, sorted_symbols)
        if not numbers:
            continue

        bucket = syllable_map.setdefault(syllable_index, {"C1": [], "V": [], "C2": []})
        bucket[slot].extend(numbers)

    output_rows: list[list[Any]] = []
    for syllable_index in sorted(syllable_map.keys()):
        bucket = syllable_map[syllable_index]
        row: list[Any] = []
        for slot in JASON_SLOT_ORDER:
            numbers = bucket[slot]
            if not numbers:
                continue
            is_composite_slot = slot in {"C1", "C2"} and slot_counts.get(syllable_index, {}).get(slot, 0) > 1
            if len(numbers) > 1 or is_composite_slot:
                row.append(numbers)
            else:
                row.append(numbers[0])

        if row:
            output_rows.append(row)

    return output_rows


def _token_kk_phonetic(word: dict[str, Any]) -> str:
    display = word.get("display") if isinstance(word, dict) else {}
    if isinstance(display, dict):
        kk_tokens = display.get("kk")
        if isinstance(kk_tokens, list):
            return "".join(str(token or "") for token in kk_tokens)

    ipa_tokens = word.get("ipa") if isinstance(word, dict) else None
    if isinstance(ipa_tokens, list):
        return "".join(str(token or "") for token in ipa_tokens)
    return ""


def _token_id_for(sentence_id: str, word_group_index: int, token_index: int, token: dict[str, Any]) -> str:
    seed = {
        "sentenceId": str(sentence_id or ""),
        "wordGroupIndex": int(word_group_index),
        "tokenIndex": int(token_index),
        "text": str(token.get("text") or ""),
        "phonetic": token.get("phonetic") if isinstance(token.get("phonetic"), list) else [],
        "kkPhonetic": str(token.get("kkPhonetic") or ""),
    }
    encoded = json.dumps(seed, ensure_ascii=False, separators=(",", ":"))
    digest = _stable_hash16(encoded)
    return f"tok_{digest}"


def _stable_hash16(value: str) -> str:
    h = 0xCBF29CE484222325
    prime = 0x100000001B3
    mask = (1 << 64) - 1
    for byte in value.encode("utf-8"):
        h ^= byte
        h = (h * prime) & mask
    return f"{h:016x}"


def _finalize_jason_token(sentence_id: str, word_group_index: int, token_index: int, token: dict[str, Any]) -> dict[str, Any]:
    safe_token = token if isinstance(token, dict) else {}
    safe_token["text"] = str(safe_token.get("text") or "")
    if not isinstance(safe_token.get("phonetic"), list):
        safe_token["phonetic"] = []
    safe_token["toneLevel"] = 0
    safe_token["toneStyle"] = "solid-short"
    safe_token["importance"] = "important" if safe_token["phonetic"] else "not-important"
    safe_token["tokenId"] = _token_id_for(sentence_id, word_group_index, token_index, safe_token)
    return safe_token


def _blank_jason_token(text: str) -> dict[str, Any]:
    return {
        "tokenId": "",
        "text": str(text or ""),
        "toneLevel": 0,
        "toneStyle": "solid-short",
        "phonetic": [],
        "importance": "not-important",
        "reason": "",
        "kkPhonetic": "",
        "partOfSpeech": None,
        "transZh": "",
    }


def _word_to_jason_tokens(
    word: dict[str, Any],
    surface_text: str,
    phonetic_number_map: dict[str, int],
    sorted_symbols: list[str],
) -> list[dict[str, Any]]:
    display = word.get("display") if isinstance(word, dict) else {}
    display_zhuyin = display.get("zhuyin_plus") if isinstance(display, dict) else []
    zhuyin_tokens = display_zhuyin if isinstance(display_zhuyin, list) else []
    token_details = word.get("token_details") if isinstance(word, dict) else []
    details = token_details if isinstance(token_details, list) else []
    fallback_syllable_count = _fallback_syllable_count_for_word(word, surface_text)
    kk_phonetic = _token_kk_phonetic(word)

    manual_rows = _build_manual_phonetic_rows(word, surface_text, phonetic_number_map, sorted_symbols)
    if manual_rows:
        tokens: list[dict[str, Any]] = []
        for idx, row in enumerate(manual_rows):
            token = _blank_jason_token(str(row.get("text") or (surface_text if idx == 0 else "")))
            token["phonetic"] = row.get("phonetic") if isinstance(row.get("phonetic"), list) else []
            token["kkPhonetic"] = kk_phonetic
            tokens.append(token)
        return tokens

    phonetic_rows = _build_phonetic_rows(
        zhuyin_tokens,
        details,
        phonetic_number_map,
        sorted_symbols,
        fallback_syllable_count=fallback_syllable_count,
    )

    if not phonetic_rows:
        token = _blank_jason_token(surface_text)
        token["kkPhonetic"] = kk_phonetic
        return [token]

    tokens: list[dict[str, Any]] = []
    split_texts = _split_surface_text_for_rows(surface_text, len(phonetic_rows))
    for idx, row in enumerate(phonetic_rows):
        token = _blank_jason_token(split_texts[idx] if idx < len(split_texts) else (surface_text if idx == 0 else ""))
        token["phonetic"] = row
        token["kkPhonetic"] = kk_phonetic
        tokens.append(token)
    return tokens


def _sentence_surface_tokens(sentence_text: str) -> list[str]:
    text = str(sentence_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9']+(?:[.,!?;:…]+)?|[^\s]", text)


def _sentence_words(sentence: dict[str, Any]) -> list[dict[str, Any]]:
    raw_words = sentence.get("words")
    if not isinstance(raw_words, list):
        return []
    return [item for item in raw_words if isinstance(item, dict)]


def _convert_sentence_to_jason(
    sentence: dict[str, Any],
    phonetic_number_map: dict[str, int],
    sorted_symbols: list[str],
) -> dict[str, Any]:
    sentence_text = str(sentence.get("text") or sentence.get("sentence") or "")
    sentence_id = str(sentence.get("sentence_id") or sentence.get("sentenceId") or "")
    surface_tokens = _sentence_surface_tokens(sentence_text)
    source_words = _sentence_words(sentence)
    source_idx = 0

    words_output: list[list[dict[str, Any]]] = []
    for raw_token in surface_tokens:
        if normalize_word_token(raw_token) and source_idx < len(source_words):
            words_output.append(_word_to_jason_tokens(source_words[source_idx], raw_token, phonetic_number_map, sorted_symbols))
            source_idx += 1
        else:
            words_output.append([_blank_jason_token(raw_token)])

    while source_idx < len(source_words):
        fallback_word = source_words[source_idx]
        source_idx += 1
        words_output.append(
            _word_to_jason_tokens(
                fallback_word,
                str(fallback_word.get("word") or ""),
                phonetic_number_map,
                sorted_symbols,
            )
        )

    for word_group_index, word_group in enumerate(words_output):
        if not isinstance(word_group, list):
            continue
        for token_index, token in enumerate(word_group):
            if not isinstance(token, dict):
                continue
            word_group[token_index] = _finalize_jason_token(sentence_id, word_group_index, token_index, token)

    tags = sentence.get("tags")
    return {
        "sentenceId": sentence_id,
        "sentence": sentence_text,
        "words": words_output,
        "tags": tags if isinstance(tags, list) else [],
        "name": str(sentence.get("name") or ""),
        "notes": str(sentence.get("notes") or ""),
    }


def export_payload_to_jason(
    payload: dict[str, Any],
    phonetic_number_map: dict[str, int],
    sorted_symbols: list[str],
) -> list[dict[str, Any]]:
    sentences = payload.get("sentences")
    if not isinstance(sentences, list):
        return []
    return [
        _convert_sentence_to_jason(sentence, phonetic_number_map, sorted_symbols)
        for sentence in sentences
        if isinstance(sentence, dict)
    ]


class Pipeline:
    def __init__(self) -> None:
        self.g2p = SimpleG2P(CMUDICT_PATH)
        self.display_table = load_display_table_csv(DISPLAY_TABLE_PATH)
        self.display_exceptions = load_display_exceptions_json(DISPLAY_EXCEPTIONS_PATH)
        self.phonetic_number_map, self.phonetic_number_symbols = load_phonetic_number_table_csv(PHONETIC_NUMBER_TABLE_PATH)

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

    def export_json(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        body = payload if isinstance(payload, dict) else {}
        return export_payload_to_jason(body, self.phonetic_number_map, self.phonetic_number_symbols)

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
        word_payload = {
            "word_id": str(word_index),
            "word": record.get("word", ""),
            "word_norm": record.get("word_norm", ""),
            "g2p_source": record.get("g2p_source", ""),
            "ipa": ipa_tokens,
            "display": display,
            "token_details": token_details,
            "edited": False,
        }

        if not ipa_tokens or str(record.get("g2p_source") or "") == "missing":
            word_payload["syllable_count_guess"] = _guess_english_syllable_count(str(record.get("word") or ""))

        return word_payload


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
