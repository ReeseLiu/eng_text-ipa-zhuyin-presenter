"""Canonical word-level G2P with offline CMUdict and espeak fallback."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .text_utils import normalize_text, normalize_word_token


ARPABET_TO_IPA = {
    "AA": "ɑ",
    "AE": "æ",
    "AH": "ʌ",
    "AO": "ɔ",
    "EH": "ɛ",
    "ER": "ɚ",
    "IH": "ɪ",
    "IY": "i",
    "UH": "ʊ",
    "UW": "u",
    "AW": "aʊ",
    "AY": "aɪ",
    "EY": "eɪ",
    "OW": "oʊ",
    "OY": "ɔɪ",
    "B": "b",
    "CH": "tʃ",
    "D": "d",
    "DH": "ð",
    "F": "f",
    "G": "ɡ",
    "HH": "h",
    "JH": "dʒ",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ŋ",
    "P": "p",
    "R": "ɹ",
    "S": "s",
    "SH": "ʃ",
    "T": "t",
    "TH": "θ",
    "V": "v",
    "W": "w",
    "Y": "j",
    "Z": "z",
    "ZH": "ʒ",
}

MULTI_PHONEME_UNITS = [
    "ɑːɹ",
    "ɔːɹ",
    "aɪ",
    "aʊ",
    "eɪ",
    "oʊ",
    "ɔɪ",
    "iː",
    "uː",
    "ɑː",
    "ɔː",
    "ɜː",
    "oː",
    "ɪɹ",
    "tʃ",
    "dʒ",
    "əl",
    "ɚ",
    "ɝ",
]

READ_PRESENT_PREV_CUES = {
    "will",
    "can",
    "could",
    "may",
    "might",
    "must",
    "should",
    "shall",
    "would",
    "to",
    "please",
    "lets",
    "let's",
    "do",
    "does",
    "don't",
    "doesn't",
}
READ_PAST_PREV_CUES = {"have", "has", "had", "did", "already", "just", "previously", "earlier", "before"}
READ_PAST_TIME_CUES = {"yesterday", "ago", "last", "earlier", "previously", "before", "tonight"}
READ_PRESENT_HABITUAL_CUES = {
    "often",
    "usually",
    "always",
    "daily",
    "every",
    "each",
    "sometimes",
    "rarely",
    "seldom",
    "generally",
    "typically",
    "normally",
}
LEAD_VERB_PREV_CUES = READ_PRESENT_PREV_CUES
LEAD_VERB_NEXT_CUES = {
    "to",
    "the",
    "a",
    "an",
    "my",
    "your",
    "our",
    "their",
    "his",
    "her",
    "its",
    "us",
    "them",
    "me",
    "him",
    "role",
    "team",
    "way",
    "project",
    "group",
    "effort",
    "meeting",
}
LEAD_METAL_CUES = {
    "pipe",
    "paint",
    "poisoning",
    "metal",
    "ore",
    "pencil",
    "bullet",
    "bullets",
    "solder",
    "toxicity",
    "exposure",
    "battery",
    "batteries",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _clean_context_tokens(raw_tokens: list[str]) -> list[str]:
    output: list[str] = []
    for token in raw_tokens:
        normalized = normalize_word_token(str(token or ""))
        if normalized:
            output.append(normalized)
    return output


def _context_bundle(context: dict | None) -> tuple[list[str], int]:
    if not isinstance(context, dict):
        return [], -1

    raw_tokens = context.get("tokens", [])
    if not isinstance(raw_tokens, list):
        return [], -1

    tokens = _clean_context_tokens(raw_tokens)

    raw_index = context.get("index", -1)
    try:
        idx = int(raw_index)
    except (TypeError, ValueError):
        return tokens, -1

    if idx < 0 or idx >= len(tokens):
        return tokens, -1
    return tokens, idx


class SimpleG2P:
    """Simplified word-to-IPA converter.

    The converter is offline-first: it reads ``data/cmudict.dict`` bundled in
    this project and never downloads data at runtime.
    """

    def __init__(self, cmudict_path: Path | None = None) -> None:
        self._dict: dict[str, list[list[str]]] = {}
        self._load_cmudict(cmudict_path)

    def _candidate_cmudict_paths(self, explicit_path: Path | None) -> list[Path]:
        candidates: list[Path] = []
        if explicit_path is not None:
            candidates.append(explicit_path)
        candidates.append(_project_root() / "data" / "cmudict.dict")
        candidates.append(Path.home() / ".cache" / "cmudict" / "cmudict.dict")
        return candidates

    def _load_cmudict(self, explicit_path: Path | None = None) -> None:
        dict_path = next((path for path in self._candidate_cmudict_paths(explicit_path) if path.exists()), None)
        if dict_path is None:
            return

        with dict_path.open("r", encoding="latin-1") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(";;;"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                word = re.sub(r"\(\d+\)$", "", parts[0]).lower()
                phones = parts[1:]
                bucket = self._dict.setdefault(word, [])
                if phones not in bucket:
                    bucket.append(phones)

    def word_to_ipa(self, word: str) -> tuple[list[str], str]:
        ipa_tokens, source, _stress_levels = self.word_to_ipa_with_stress(word)
        return ipa_tokens, source

    def _find_pronunciation_index(self, pronunciations: list[list[str]], target_ipa: tuple[str, ...]) -> int | None:
        for idx, phones in enumerate(pronunciations):
            ipa_tokens, _ = self._arpabet_to_ipa_with_stress(phones)
            if tuple(ipa_tokens) == target_ipa:
                return idx
        return None

    def _pick_pronunciation(self, pronunciations: list[list[str]], target_ipa: tuple[str, ...], fallback_idx: int) -> list[str]:
        idx = self._find_pronunciation_index(pronunciations, target_ipa)
        if idx is None:
            idx = min(max(fallback_idx, 0), len(pronunciations) - 1)
        return pronunciations[idx]

    def _select_read_pronunciation(self, pronunciations: list[list[str]], context: dict | None) -> tuple[list[str], str]:
        tokens, idx = _context_bundle(context)

        if idx < 0:
            return self._pick_pronunciation(pronunciations, ("r", "i", "d"), fallback_idx=1), "cmudict_context:read_present_default"

        prev_1 = tokens[idx - 1] if idx - 1 >= 0 else ""
        prev_2 = tokens[idx - 2] if idx - 2 >= 0 else ""
        next_1 = tokens[idx + 1] if idx + 1 < len(tokens) else ""
        window_prev = tokens[max(0, idx - 3) : idx]
        window_next = tokens[idx + 1 : idx + 4]
        nearby = set(window_prev + window_next)

        if prev_1 in READ_PAST_PREV_CUES or prev_1.endswith("'ve") or prev_1.endswith("'d"):
            return self._pick_pronunciation(pronunciations, ("r", "ɛ", "d"), fallback_idx=0), "cmudict_context:read_past_cue"
        if any(token in READ_PAST_TIME_CUES for token in nearby):
            return self._pick_pronunciation(pronunciations, ("r", "ɛ", "d"), fallback_idx=0), "cmudict_context:read_past_time"
        if prev_1 == "last" or prev_2 == "last":
            return self._pick_pronunciation(pronunciations, ("r", "ɛ", "d"), fallback_idx=0), "cmudict_context:read_past_time"
        if next_1 == "aloud":
            return self._pick_pronunciation(pronunciations, ("r", "i", "d"), fallback_idx=1), "cmudict_context:read_present_aloud"
        if prev_1 in READ_PRESENT_PREV_CUES or prev_2 in READ_PRESENT_PREV_CUES:
            return self._pick_pronunciation(pronunciations, ("r", "i", "d"), fallback_idx=1), "cmudict_context:read_present_cue"
        if any(token in READ_PRESENT_HABITUAL_CUES for token in nearby):
            return self._pick_pronunciation(pronunciations, ("r", "i", "d"), fallback_idx=1), "cmudict_context:read_present_habitual"

        return self._pick_pronunciation(pronunciations, ("r", "i", "d"), fallback_idx=1), "cmudict_context:read_present_default"

    def _select_lead_pronunciation(self, pronunciations: list[list[str]], context: dict | None) -> tuple[list[str], str]:
        tokens, idx = _context_bundle(context)

        if idx < 0:
            return self._pick_pronunciation(pronunciations, ("l", "i", "d"), fallback_idx=1), "cmudict_context:lead_verb_default"

        prev_1 = tokens[idx - 1] if idx - 1 >= 0 else ""
        prev_2 = tokens[idx - 2] if idx - 2 >= 0 else ""
        next_1 = tokens[idx + 1] if idx + 1 < len(tokens) else ""
        next_2 = tokens[idx + 2] if idx + 2 < len(tokens) else ""
        nearby = set(tokens[max(0, idx - 3) : idx] + tokens[idx + 1 : idx + 4])

        if next_1 in LEAD_METAL_CUES or next_2 in LEAD_METAL_CUES or any(token in LEAD_METAL_CUES for token in nearby):
            return self._pick_pronunciation(pronunciations, ("l", "ɛ", "d"), fallback_idx=0), "cmudict_context:lead_metal"
        if prev_1 in LEAD_VERB_PREV_CUES or prev_2 in LEAD_VERB_PREV_CUES:
            return self._pick_pronunciation(pronunciations, ("l", "i", "d"), fallback_idx=1), "cmudict_context:lead_verb_cue"
        if next_1 in LEAD_VERB_NEXT_CUES:
            return self._pick_pronunciation(pronunciations, ("l", "i", "d"), fallback_idx=1), "cmudict_context:lead_verb_object"
        if prev_1 == "the" and prev_2 == "in":
            return self._pick_pronunciation(pronunciations, ("l", "i", "d"), fallback_idx=1), "cmudict_context:lead_nominal"

        return self._pick_pronunciation(pronunciations, ("l", "i", "d"), fallback_idx=1), "cmudict_context:lead_verb_default"

    def _select_cmudict_pronunciation(
        self,
        normalized_word: str,
        pronunciations: list[list[str]],
        context: dict | None,
    ) -> tuple[list[str], str]:
        if not pronunciations:
            return [], "cmudict"
        if normalized_word == "read":
            return self._select_read_pronunciation(pronunciations, context)
        if normalized_word == "lead":
            return self._select_lead_pronunciation(pronunciations, context)
        return pronunciations[0], "cmudict"

    def word_to_ipa_with_stress(self, word: str, context: dict | None = None) -> tuple[list[str], str, list[int | None]]:
        normalized = normalize_text(word)
        if not normalized:
            return [], "empty", []

        if normalized in self._dict:
            selected, source = self._select_cmudict_pronunciation(normalized, self._dict[normalized], context)
            ipa_tokens, stress_levels = self._arpabet_to_ipa_with_stress(selected)
            return ipa_tokens, source, stress_levels

        if normalized.endswith("'s") and normalized[:-2] in self._dict:
            selected, _source = self._select_cmudict_pronunciation(normalized[:-2], self._dict[normalized[:-2]], context)
            base, stress_levels = self._arpabet_to_ipa_with_stress(selected)
            last = base[-1] if base else ""
            if last in ("s", "z", "ʃ", "ʒ", "tʃ", "dʒ"):
                base.extend(["ɪ", "z"])
                stress_levels.extend([None, None])
            elif last in ("p", "t", "k", "f", "θ"):
                base.append("s")
                stress_levels.append(None)
            else:
                base.append("z")
                stress_levels.append(None)
            return base, "cmudict", stress_levels

        fallback_tokens, source = self._espeak_fallback(normalized)
        return fallback_tokens, source, [None] * len(fallback_tokens)

    def _arpabet_to_ipa_with_stress(self, phones: list[str]) -> tuple[list[str], list[int | None]]:
        tokens = []
        stress_levels: list[int | None] = []
        for phone in phones:
            base = phone.rstrip("012")
            stress = phone[len(base) :] if len(phone) > len(base) else None
            if base not in ARPABET_TO_IPA:
                continue
            ipa = ARPABET_TO_IPA[base]
            if base == "AH" and stress == "0":
                ipa = "ə"
            tokens.append(ipa)
            if stress is None or not stress.isdigit():
                stress_levels.append(None)
            else:
                stress_levels.append(int(stress))
        return tokens, stress_levels

    def _espeak_fallback(self, word: str) -> tuple[list[str], str]:
        try:
            result = subprocess.run(
                ["espeak-ng", "-v", "en-us", "--ipa", "-q", word],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            raw = result.stdout.strip()
            raw = raw.replace("ˈ", "").replace("ˌ", "").replace(",", "").replace(".", "")
            raw = re.sub(r"\([^)]*\)", "", raw).strip()
            if not raw:
                return [], "espeak"

            pattern = "|".join(re.escape(unit) for unit in sorted(MULTI_PHONEME_UNITS, key=len, reverse=True))
            token_re = f"({pattern}|[^\\s])"
            raw_tokens = re.findall(token_re, raw)
            tokens = [token for token in raw_tokens if token.strip() and token != "ː"]
            return tokens, "espeak"
        except Exception:
            return [], "error"


def sentence_to_canonical_words(sentence_text: str, g2p: SimpleG2P) -> list[dict]:
    """Convert sentence text into per-word canonical IPA records."""
    from .text_utils import parse_clean_line_words

    records = []
    words = parse_clean_line_words(sentence_text)
    context_tokens = [item.get("norm", "") for item in words]

    for idx, word_info in enumerate(words):
        canonical_ipa, source, canonical_stress_levels = g2p.word_to_ipa_with_stress(
            word_info["word"],
            context={"tokens": context_tokens, "index": idx},
        )
        records.append(
            {
                "word": word_info["word"],
                "word_norm": word_info["norm"],
                "canonical_ipa": canonical_ipa,
                "canonical_stress_levels": canonical_stress_levels,
                "g2p_source": source,
            }
        )
    return records
