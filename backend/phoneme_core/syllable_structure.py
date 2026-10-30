"""Heuristic syllable-slot analysis for IPA token sequences."""

from __future__ import annotations

import unicodedata

from .rules_conservative import is_vowel


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


def analyze_syllable_tokens(base_tokens: list[str]) -> list[dict]:
    """Annotate each token with heuristic syllable C1/V/C2 information."""
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
