"""Map IPA tokens to display-friendly labels for the UI."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .text_utils import normalize_word_token


FALLBACK_BASE_MAP = {
    "iː": "ee",
    "uː": "oo",
    "ɜː": "er",
    "a": "ah",
    "ɲ": "n",
    "ʉ": "oo",
}


def display_token(ipa_map: dict[str, str], raw_token: str) -> str:
    if not raw_token:
        return ""
    if raw_token in ipa_map:
        return ipa_map[raw_token]
    if raw_token in FALLBACK_BASE_MAP:
        return FALLBACK_BASE_MAP[raw_token]
    normalized = raw_token.replace("ː", "")
    if normalized in ipa_map:
        return ipa_map[normalized]
    return raw_token


def map_tokens(ipa_map: dict[str, str], tokens: list[str]) -> list[str]:
    return [display_token(ipa_map, token) for token in tokens]


def _normalize_stress_level(value) -> int | None:
    if isinstance(value, int):
        return value if value in {0, 1, 2} else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed in {0, 1, 2} else None
    return None


def _detail_dict(token_details: list[dict], idx: int) -> dict:
    if idx < 0 or idx >= len(token_details):
        return {}
    detail = token_details[idx]
    return detail if isinstance(detail, dict) else {}


def _detail_slot(token_details: list[dict], idx: int) -> str:
    return str(_detail_dict(token_details, idx).get("syllable_slot") or "")


def _detail_position(token_details: list[dict], idx: int) -> str:
    return str(_detail_dict(token_details, idx).get("position") or "")


def _detail_syllable_index(token_details: list[dict], idx: int) -> int | None:
    raw = _detail_dict(token_details, idx).get("syllable_index")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _detail_slot_index(token_details: list[dict], idx: int) -> int | None:
    raw = _detail_dict(token_details, idx).get("slot_index")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _same_syllable(token_details: list[dict], left_idx: int, right_idx: int) -> bool:
    left = _detail_syllable_index(token_details, left_idx)
    right = _detail_syllable_index(token_details, right_idx)
    if left is None or right is None:
        return True
    return left == right


def _adjacent_onset_slots(token_details: list[dict], left_idx: int, right_idx: int) -> bool:
    if _detail_slot(token_details, left_idx) != "C1":
        return False
    if _detail_slot(token_details, right_idx) != "C1":
        return False
    if not _same_syllable(token_details, left_idx, right_idx):
        return False
    left_slot = _detail_slot_index(token_details, left_idx)
    right_slot = _detail_slot_index(token_details, right_idx)
    if left_slot is None or right_slot is None:
        return False
    return right_slot == left_slot + 1


def _should_merge_reduced_schwa_l(ipa_tokens: list[str], token_details: list[dict], idx: int) -> bool:
    if idx + 1 >= len(ipa_tokens):
        return False
    if ipa_tokens[idx] != "ə" or ipa_tokens[idx + 1] != "l":
        return False
    if idx + 1 != len(ipa_tokens) - 1:
        return False
    if idx + 1 >= len(token_details):
        return False

    current = token_details[idx] if isinstance(token_details[idx], dict) else {}
    nxt = token_details[idx + 1] if isinstance(token_details[idx + 1], dict) else {}
    if _normalize_stress_level(current.get("stress_level")) != 0:
        return False
    if str(nxt.get("syllable_slot") or "") != "C2":
        return False

    cur_syl = current.get("syllable_index")
    next_syl = nxt.get("syllable_index")
    if isinstance(cur_syl, int) and isinstance(next_syl, int) and cur_syl != next_syl:
        return False
    return True


def _slot_aware_zhuyin(row: dict[str, str], token: str, slot: str) -> str:
    if slot == "C1":
        return row.get("zhuyin_plus_C1") or row.get("zhuyin_plus") or token
    if slot == "V":
        return row.get("zhuyin_plus_V") or row.get("zhuyin_plus") or token
    if slot == "C2":
        return row.get("zhuyin_plus_C2") or row.get("zhuyin_plus") or token
    return row.get("zhuyin_plus") or token


def _contextual_zhuyin_override(ipa_tokens: list[str], token_details: list[dict], idx: int, reduced_schwa_l: str) -> tuple[str, bool] | None:
    token = ipa_tokens[idx]
    slot = _detail_slot(token_details, idx)

    if _should_merge_reduced_schwa_l(ipa_tokens, token_details, idx):
        return reduced_schwa_l, True

    has_next = idx + 1 < len(ipa_tokens)
    if has_next:
        next_token = ipa_tokens[idx + 1]
        next_slot = _detail_slot(token_details, idx + 1)
        same_syllable = _same_syllable(token_details, idx, idx + 1)

        if token == "ɔ" and next_token == "ɹ" and next_slot == "C2" and same_syllable:
            return "ㄛㄦ", True
        if token in {"ɑ", "ɑː", "a"} and next_token == "ɹ" and next_slot == "C2" and same_syllable:
            return "ㄚ(喉)ㄦ", True
        if token == "ɛ" and next_token == "ɹ" and next_slot == "C2" and same_syllable:
            return "ㄝㄦ", True
        if token in {"ɪ", "i"} and next_token == "ɹ" and next_slot == "C2" and same_syllable:
            return "ㄧㄦ", True
        if token == "ɔ" and next_token == "l" and next_slot == "C2" and same_syllable:
            return "ㄛ", True
        if token == "d" and next_token == "z" and slot == "C2" and next_slot == "C2" and idx + 1 == len(ipa_tokens) - 1 and same_syllable:
            return "ㄗ", True
        if token == "t" and next_token == "s" and slot == "C2" and next_slot == "C2" and idx + 1 == len(ipa_tokens) - 1 and same_syllable:
            return "ㄘ", True
        if token == "t" and next_token == "ɹ" and _adjacent_onset_slots(token_details, idx, idx + 1):
            return "ㄔㄨ", True
        if token == "d" and next_token == "ɹ" and _adjacent_onset_slots(token_details, idx, idx + 1):
            return "ㄓㄨ", True

    if token == "k" and idx > 0 and ipa_tokens[idx - 1] == "s" and _adjacent_onset_slots(token_details, idx - 1, idx):
        return "ㄍ", False
    if token == "p" and slot == "C1" and _detail_position(token_details, idx) == "intervocalic":
        return "ㄅ", False
    if token == "l" and slot == "C2":
        return "ㄛ", False
    return None


def _ipa_key(tokens: list[str]) -> str:
    return " ".join(token for token in tokens if token)


def _normalize_exception_word(raw: str) -> str:
    cleaned = str(raw or "").replace("’", "'")
    return normalize_word_token(cleaned)


def _normalize_override_tokens(tokens: list[str], target_len: int) -> list[str]:
    normalized = [str(token) for token in tokens]
    if len(normalized) < target_len:
        normalized.extend([""] * (target_len - len(normalized)))
    if len(normalized) > target_len:
        normalized = normalized[:target_len]
    return normalized


def load_display_exceptions_json(path: Path) -> dict[str, dict[str, list[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, dict[str, list[str]]] = {}
    entries = payload.get("word_ipa_overrides", [])
    if not isinstance(entries, list):
        return output

    for item in entries:
        if not isinstance(item, dict):
            continue
        word_norm = _normalize_exception_word(str(item.get("word_norm", "")))
        ipa_raw = item.get("ipa", [])
        zhuyin_raw = item.get("zhuyin_plus", [])
        if not word_norm or not isinstance(ipa_raw, list) or not isinstance(zhuyin_raw, list):
            continue
        ipa_tokens = [str(token).strip() for token in ipa_raw if str(token).strip()]
        if not ipa_tokens:
            continue
        output.setdefault(word_norm, {})[_ipa_key(ipa_tokens)] = _normalize_override_tokens(zhuyin_raw, len(ipa_tokens))
    return output


def resolve_display_exception_zhuyin(display_exceptions: dict[str, dict[str, list[str]]] | None, word_text: str | None, ipa_tokens: list[str]) -> list[str] | None:
    if not display_exceptions or not isinstance(display_exceptions, dict):
        return None
    word_norm = _normalize_exception_word(str(word_text or ""))
    if not word_norm:
        return None
    word_rules = display_exceptions.get(word_norm)
    if not isinstance(word_rules, dict):
        return None
    candidate = word_rules.get(_ipa_key(ipa_tokens))
    if not isinstance(candidate, list):
        return None
    return _normalize_override_tokens(candidate, len(ipa_tokens))


def load_display_table_csv(path: Path) -> dict[str, dict[str, str]]:
    """Load BOM-friendly display table CSV keyed by IPA token."""
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"symbol_id", "ipa", "kk", "zhuyin_plus"}
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        missing_cols = sorted(required - set(reader.fieldnames))
        if missing_cols:
            raise ValueError(f"CSV missing required columns: {', '.join(missing_cols)}")

        for line_idx, row in enumerate(reader, start=2):
            ipa = (row.get("ipa") or "").strip()
            if not ipa:
                continue
            if ipa in rows:
                raise ValueError(f"Duplicate ipa token '{ipa}' in CSV line {line_idx}")
            rows[ipa] = {
                "symbol_id": (row.get("symbol_id") or "").strip(),
                "kk": (row.get("kk") or "").strip(),
                "zhuyin_plus": (row.get("zhuyin_plus") or "").strip(),
                "zhuyin_plus_C1": (row.get("zhuyin_plus_C1") or "").strip(),
                "zhuyin_plus_V": (row.get("zhuyin_plus_V") or "").strip(),
                "zhuyin_plus_C2": (row.get("zhuyin_plus_C2") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }
    return rows


def build_display_bundle(
    tokens: list[str],
    table: dict[str, dict[str, str]],
    token_details: list[dict] | None = None,
    word_text: str | None = None,
    display_exceptions: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, list[str]]:
    ipa_tokens = [token for token in tokens if token]
    kk_tokens: list[str] = []
    zhuyin_tokens: list[str] = []
    symbol_ids: list[str] = []
    details = token_details if isinstance(token_details, list) else []
    reduced_schwa_l = (table.get("əl", {}).get("zhuyin_plus") or "ㄛ")
    merged_next_indices: set[int] = set()
    exception_zhuyin = resolve_display_exception_zhuyin(display_exceptions, word_text, ipa_tokens)

    for idx, token in enumerate(ipa_tokens):
        row = table.get(token, {})
        kk_tokens.append(row.get("kk") or token)
        symbol_ids.append(row.get("symbol_id") or "")

        if exception_zhuyin is not None:
            zhuyin_tokens.append(exception_zhuyin[idx] if idx < len(exception_zhuyin) else "")
            continue
        if idx in merged_next_indices:
            zhuyin_tokens.append("")
            continue

        context_override = _contextual_zhuyin_override(ipa_tokens, details, idx, reduced_schwa_l)
        if context_override is not None:
            override_text, merge_next = context_override
            zhuyin_tokens.append(override_text)
            if merge_next and idx + 1 < len(ipa_tokens):
                merged_next_indices.add(idx + 1)
            continue

        zhuyin_tokens.append(_slot_aware_zhuyin(row, token, _detail_slot(details, idx)))

    return {
        "ipa": ipa_tokens,
        "kk": kk_tokens,
        "zhuyin_plus": zhuyin_tokens,
        "symbol_ids": symbol_ids,
    }


def display_tokens_for_system(display_value, tokens: list[str], system: str) -> list[str]:
    """Read display tokens from either legacy list or bundle object."""
    if isinstance(display_value, list):
        return display_value
    if isinstance(display_value, dict):
        candidate = display_value.get(system)
        if isinstance(candidate, list):
            return candidate
        fallback = display_value.get("ipa")
        if isinstance(fallback, list):
            return fallback
    return tokens
