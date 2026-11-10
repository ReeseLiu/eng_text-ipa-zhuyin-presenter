"""Syllable-split suggestions: map IPA syllable boundaries back onto spelling.

Mirrors ``suggestSyllableSplit`` in ``app/browser_pipeline.js``; both are locked
by ``tests/fixtures/syllable_split_cases.json``. See ADR 0001/0002.

The grapheme–phoneme chunks come from ``data/syllable_align_table.json`` (built
offline by ``scripts/build_align_table.py``). At runtime we only:

1. syllabify the word's *current* IPA with ``analyze_syllable_tokens``, at the
   compound seam the caller passes for listed compounds;
2. find the CMUdict pronunciation identical to that IPA;
3. cut before the chunk holding each syllable's first phoneme (so silent
   letters stay with the left syllable).

Any doubt yields a failure code and no segments; there is no best guess.

ADR 0002 asks for the alignment core to live in one place. The aligner itself
does (the offline table); only this small cut step is duplicated in Python and
JS, because the static/offline build has no server. The fixture contract tests
and the CMUdict parity sample in ``tests/test_syllable_split.py`` keep the two
copies in lockstep.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .syllable_structure import analyze_syllable_tokens

FAILURE_CODES = (
    "oov",
    "pron_mismatch",
    "no_alignment",
    "cut_inside_chunk",
    "low_confidence",
    "reconstruct",
)

SURFACE_RE = re.compile(r"^([A-Za-z'\-]+)([.,!?;:…]*)$")


def load_align_table(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _syllable_starts(ipa_tokens: list[str], seam: int | None = None) -> list[int]:
    """Phoneme index of the first token of each syllable after the first."""
    details = analyze_syllable_tokens(ipa_tokens, seam)
    starts: list[int] = []
    previous = 0
    for detail in details:
        syllable_index = int(detail.get("syllable_index") or 0)
        if syllable_index != previous:
            starts.append(int(detail["index"]))
            previous = syllable_index
    return starts


def _syllable_count(ipa_tokens: list[str]) -> int:
    details = analyze_syllable_tokens(ipa_tokens)
    has_vowel = any(detail.get("syllable_slot") == "V" for detail in details)
    if not has_vowel:
        return 0
    return len({int(detail.get("syllable_index") or 0) for detail in details})


def _parse_entry(raw: str, chunk_codes: dict[str, list[int]]) -> tuple[list[tuple[int, int]], set[int]] | None:
    body, _, low_raw = raw.partition("~")
    chunks: list[tuple[int, int]] = []
    for code in body:
        shape = chunk_codes.get(code)
        if not shape:
            return None
        chunks.append((int(shape[0]), int(shape[1])))
    low = {int(part) for part in low_raw.split(",") if part.strip().isdigit()}
    return chunks, low


def _failure(code: str) -> dict[str, Any]:
    return {"status": "failed", "code": code, "segments": []}


def suggest_syllable_split(
    word_text: str,
    ipa_tokens: list[str],
    pronunciations: Callable[[str], list[list[str]] | None],
    table: dict[str, Any],
    seam: int | None = None,
) -> dict[str, Any]:
    """Return ``{"status": "ok"|"not_applicable"|"failed", "code", "segments"}``.

    ``pronunciations(word)`` returns the CMUdict pronunciations of a lowercase
    word as IPA token lists in CMUdict order, or ``None`` when absent. ``seam`` is
    the word's compound seam (``resolve_compound_seam``), if it has one.
    """
    tokens = [str(token).strip() for token in ipa_tokens or [] if str(token).strip()]
    if _syllable_count(tokens) < 2:
        return {"status": "not_applicable", "code": None, "segments": []}

    matched = SURFACE_RE.match(str(word_text or "").strip())
    if not matched:
        return _failure("oov")
    core, punct = matched.groups()
    key = core.lower()

    prons = pronunciations(key)
    if not prons:
        return _failure("oov")

    pron_index = next((idx for idx, pron in enumerate(prons) if list(pron) == tokens), None)
    if pron_index is None:
        return _failure("pron_mismatch")

    raw_entry = (table.get("entries") or {}).get(key)
    codes = raw_entry.split("|") if isinstance(raw_entry, str) else []
    if pron_index >= len(codes) or codes[pron_index] in ("", ".", "-"):
        return _failure("no_alignment")
    parsed = _parse_entry(codes[pron_index], table.get("chunk_codes") or {})
    if parsed is None:
        return _failure("no_alignment")
    chunks, low = parsed
    if sum(n for n, _ in chunks) != len(core) or sum(p for _, p in chunks) != len(tokens):
        return _failure("no_alignment")

    # phoneme index -> letter offset of the chunk that starts with it
    chunk_start_at: dict[int, int] = {}
    inside: set[int] = set()
    letter = phone = 0
    for n_letters, n_phones in chunks:
        if n_phones:
            chunk_start_at[phone] = letter
            inside.update(range(phone + 1, phone + n_phones))
        letter += n_letters
        phone += n_phones

    cuts: list[int] = []
    for start in _syllable_starts(tokens, seam):
        if start in inside or start not in chunk_start_at:
            return _failure("cut_inside_chunk")
        if start in low:
            return _failure("low_confidence")
        cuts.append(chunk_start_at[start])

    bounds = [0, *cuts, len(core)]
    segments = [core[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]
    if any(not segment for segment in segments) or "".join(segments) != core or bounds != sorted(bounds):
        return _failure("reconstruct")
    if punct:
        segments[-1] = segments[-1] + punct
    return {"status": "ok", "code": None, "segments": segments}
