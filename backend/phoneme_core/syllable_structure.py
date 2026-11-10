"""Heuristic syllable-slot analysis for IPA token sequences."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from .rules_conservative import is_vowel
from .text_utils import normalize_word_token


LEGAL_ONSET_CLUSTERS_2 = {
    ("p", "ɹ"),
    ("b", "ɹ"),
    ("t", "ɹ"),
    ("d", "ɹ"),
    ("k", "ɹ"),
    ("ɡ", "ɹ"),
    ("f", "ɹ"),
    ("θ", "ɹ"),
    ("p", "l"),
    ("b", "l"),
    ("k", "l"),
    ("ɡ", "l"),
    ("f", "l"),
    ("s", "p"),
    ("s", "t"),
    ("s", "k"),
    ("s", "m"),
    ("s", "n"),
    ("s", "f"),
    ("s", "w"),
    ("s", "j"),
    ("s", "l"),
    ("s", "ɹ"),
    ("ʃ", "ɹ"),
    ("k", "w"),
    ("t", "w"),
    ("d", "w"),
    ("ɡ", "w"),
    ("θ", "w"),
    # Coronal + /j/ (tj, dj, nj, lj) is deliberately excluded: US English drops
    # yod after coronals, so those clusters are not treated as onsets.
    ("p", "j"),
    ("b", "j"),
    ("k", "j"),
    ("ɡ", "j"),
    ("f", "j"),
    ("v", "j"),
    ("m", "j"),
    ("h", "j"),
}

LEGAL_ONSET_CLUSTERS_3 = {
    ("s", "p", "ɹ"),
    ("s", "t", "ɹ"),
    ("s", "k", "ɹ"),
    ("s", "p", "l"),
    ("s", "k", "l"),
    ("s", "k", "w"),
    ("s", "t", "j"),
    ("s", "k", "j"),
    ("s", "p", "j"),
}


def _strip_diacritics(token: str) -> str:
    decomposed = unicodedata.normalize("NFD", token)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def _max_onset_size(cluster: list[str]) -> int:
    if not cluster:
        return 0

    max_size = min(3, len(cluster))
    for size in range(max_size, 0, -1):
        tail = tuple(cluster[-size:])
        if size == 1:
            return 1
        if size == 2 and tail in LEGAL_ONSET_CLUSTERS_2:
            return 2
        if size == 3 and tail in LEGAL_ONSET_CLUSTERS_3:
            return 3
    return 1


def _normalize_seam_word(raw: str) -> str:
    return normalize_word_token(str(raw or "").replace("\u2019", "'"))


def load_compound_seams_json(path: Path) -> dict[str, dict[str, int]]:
    """Load ``data/compound_seams.json`` as ``{word_norm: {"ipa tokens": seam}}``."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, dict[str, int]] = {}
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return output
    for item in entries:
        if not isinstance(item, dict):
            continue
        word_norm = _normalize_seam_word(str(item.get("word_norm", "")))
        ipa_key = " ".join(str(item.get("ipa", "")).split())
        seam = item.get("seam")
        if not word_norm or not ipa_key or isinstance(seam, bool) or not isinstance(seam, int) or seam <= 0:
            continue
        output.setdefault(word_norm, {})[ipa_key] = seam
    return output


def resolve_compound_seam(compound_seams: dict[str, dict[str, int]] | None, word_text: str | None, ipa_tokens: list[str]) -> int | None:
    """Return the left-half IPA token count when (word, IPA) is a listed compound."""
    if not compound_seams or not isinstance(compound_seams, dict):
        return None
    word_rules = compound_seams.get(_normalize_seam_word(str(word_text or "")))
    if not isinstance(word_rules, dict):
        return None
    seam = word_rules.get(" ".join(token for token in ipa_tokens if token))
    return seam if isinstance(seam, int) else None


def analyze_syllable_tokens(base_tokens: list[str], seam: int | None = None) -> list[dict]:
    """Annotate each token with heuristic syllable C1/V/C2 information.

    ``seam`` is the number of tokens in the left half of a listed compound (see
    ``resolve_compound_seam``). When the consonants between two vowels have tokens on
    both sides of it, the boundary is fixed at the seam instead of the maximal onset.
    """
    if not base_tokens:
        return []

    base_norm = [_strip_diacritics(token) for token in base_tokens]
    vowel_indices = [idx for idx, token in enumerate(base_norm) if is_vowel(token)]

    annotations = [
        {
            "index": idx,
            "syllable_index": 0,
            "syllable_slot": "C1",
            "slot_index": idx,
            "position": "onset" if idx == 0 else "coda",
        }
        for idx in range(len(base_tokens))
    ]

    if not vowel_indices:
        return annotations

    syllable_count = len(vowel_indices)
    first_vowel = vowel_indices[0]
    last_vowel = vowel_indices[-1]

    for idx in range(first_vowel):
        annotations[idx] = {
            "index": idx,
            "syllable_index": 0,
            "syllable_slot": "C1",
            "slot_index": idx,
            "position": "onset",
        }

    for syllable_index, vowel_idx in enumerate(vowel_indices):
        annotations[vowel_idx] = {
            "index": vowel_idx,
            "syllable_index": syllable_index,
            "syllable_slot": "V",
            "slot_index": 0,
            "position": "nucleus",
        }

    tail = list(range(last_vowel + 1, len(base_tokens)))
    for slot_index, idx in enumerate(tail):
        annotations[idx] = {
            "index": idx,
            "syllable_index": syllable_count - 1,
            "syllable_slot": "C2",
            "slot_index": slot_index,
            "position": "coda",
        }

    for left_syl_idx in range(syllable_count - 1):
        left_vowel = vowel_indices[left_syl_idx]
        right_vowel = vowel_indices[left_syl_idx + 1]
        middle = list(range(left_vowel + 1, right_vowel))
        if not middle:
            continue

        if isinstance(seam, int) and not isinstance(seam, bool) and middle[0] < seam <= middle[-1]:
            coda_count = seam - middle[0]
        else:
            cluster_norm = [base_norm[idx] for idx in middle]
            onset_count = _max_onset_size(cluster_norm)
            coda_count = max(0, len(middle) - onset_count)

        coda_indices = middle[:coda_count]
        onset_indices = middle[coda_count:]

        for slot_index, idx in enumerate(coda_indices):
            annotations[idx] = {
                "index": idx,
                "syllable_index": left_syl_idx,
                "syllable_slot": "C2",
                "slot_index": slot_index,
                "position": "intervocalic",
            }

        for slot_index, idx in enumerate(onset_indices):
            annotations[idx] = {
                "index": idx,
                "syllable_index": left_syl_idx + 1,
                "syllable_slot": "C1",
                "slot_index": slot_index,
                "position": "intervocalic",
            }

    return annotations
