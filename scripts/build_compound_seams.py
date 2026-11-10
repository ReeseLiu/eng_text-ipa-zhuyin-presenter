#!/usr/bin/env python3
"""Build data/compound_seams.json from the reviewed compound-seam CSV.

Usage:
    python3 scripts/build_compound_seams.py path/to/A2_compound_seam_review.csv
    python3 scripts/build_compound_seams.py path/to/A2_compound_seam_review.csv --check

Only rows whose ``keep`` column is exactly ``Y`` are kept; ``N`` and ``?`` rows are
left out. The CSV columns used are ``word``, ``seam`` (spelling split such as
``net·work``) and ``ipa`` (space-separated tokens of the whole word).

A compound seam is stored as the number of IPA tokens in the left half. It is found
by looking the left spelling half up in CMUdict and keeping the pronunciations that
are a prefix of the whole word's IPA. The build fails, and writes nothing, when a row
has no such prefix, several prefixes of different lengths, or a seam that does not
split the consonants between two vowels (the only place a seam takes effect), so a
reviewed list never loses an entry silently.

Rerun after the review list changes, then ``python3 scripts/build_browser_assets.py``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.phoneme_core.g2p import SimpleG2P  # noqa: E402
from backend.phoneme_core.rules_conservative import is_vowel  # noqa: E402
from backend.phoneme_core.syllable_structure import _strip_diacritics  # noqa: E402
from backend.phoneme_core.text_utils import normalize_word_token  # noqa: E402

OUTPUT_PATH = ROOT / "data" / "compound_seams.json"
CMUDICT_PATH = ROOT / "data" / "cmudict.dict"
SEAM_MARK = "·"


def _left_ipa_lengths(g2p: SimpleG2P, left: str, ipa: list[str]) -> set[int]:
    lengths: set[int] = set()
    for phones in g2p._dict.get(left, []):
        left_ipa, _ = g2p._arpabet_to_ipa_with_stress(phones)
        if left_ipa and ipa[: len(left_ipa)] == left_ipa:
            lengths.add(len(left_ipa))
    return lengths


def _seam_inside_cluster(ipa: list[str], seam: int) -> bool:
    """True when the seam splits the consonants between two vowels (the only case the seam changes)."""
    vowels = [idx for idx, token in enumerate(ipa) if is_vowel(_strip_diacritics(token))]
    return (
        any(idx < seam - 1 for idx in vowels)
        and any(idx > seam for idx in vowels)
        and seam - 1 not in vowels
        and seam not in vowels
    )


def build(source: Path) -> tuple[dict, list[str]]:
    g2p = SimpleG2P(CMUDICT_PATH)
    raw = source.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    entries: list[dict] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    for line_no, row in enumerate(rows, start=2):
        if (row.get("keep") or "").strip() != "Y":
            continue
        word = (row.get("word") or "").strip()
        spelling = (row.get("seam") or "").strip()
        ipa = (row.get("ipa") or "").split()
        word_norm = normalize_word_token(word)
        parts = spelling.split(SEAM_MARK)
        if not word_norm or not ipa or len(parts) != 2 or "".join(parts).lower() != word.lower():
            problems.append(f"line {line_no}: {word!r}: malformed row (seam={spelling!r})")
            continue
        key = (word_norm, " ".join(ipa))
        if key in seen:
            problems.append(f"line {line_no}: {word!r}: duplicate word and IPA")
            continue
        lengths = _left_ipa_lengths(g2p, normalize_word_token(parts[0]), ipa)
        if len(lengths) != 1:
            reason = "left half has no CMUdict pronunciation that prefixes the IPA" if not lengths else f"ambiguous left IPA lengths {sorted(lengths)}"
            problems.append(f"line {line_no}: {word!r} /{' '.join(ipa)}/: {reason}")
            continue
        seam = lengths.pop()
        if not _seam_inside_cluster(ipa, seam):
            problems.append(f"line {line_no}: {word!r} /{' '.join(ipa)}/: seam {seam} does not split the consonants between two vowels")
            continue
        seen.add(key)
        entries.append({"word_norm": word_norm, "spelling": spelling, "ipa": " ".join(ipa), "seam": seam})

    entries.sort(key=lambda item: (item["word_norm"], item["ipa"]))
    payload = {
        "version": 1,
        "description": (
            "Compound seams: when the consonants between two vowels cross the seam, the syllable "
            "boundary is fixed at the seam instead of the maximal onset. seam = IPA tokens in the left half. "
            "Built by scripts/build_compound_seams.py; edit the review CSV and rebuild, not this file."
        ),
        "source": {"file": source.name, "sha256": hashlib.sha256(raw).hexdigest(), "keep": "Y"},
        "entries": entries,
    }
    return payload, problems


def render(payload: dict) -> str:
    head = {key: value for key, value in payload.items() if key != "entries"}
    lines = json.dumps(head, ensure_ascii=False, indent=2)[:-2].rstrip()
    body = ",\n".join("    " + json.dumps(entry, ensure_ascii=False) for entry in payload["entries"])
    return f"{lines},\n  \"entries\": [\n{body}\n  ]\n}}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="review CSV with keep/word/seam/ipa columns")
    parser.add_argument("--check", action="store_true", help="verify data/compound_seams.json is up to date; write nothing")
    args = parser.parse_args()

    payload, problems = build(args.source)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} row(s) could not be resolved; nothing written", file=sys.stderr)
        return 1

    text = render(payload)
    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != text:
            print(f"{OUTPUT_PATH} is stale; rerun without --check", file=sys.stderr)
            return 1
        print(f"{OUTPUT_PATH} is up to date ({len(payload['entries'])} entries)")
        return 0

    OUTPUT_PATH.write_text(text, encoding="utf-8")
    print(f"{OUTPUT_PATH}: {len(payload['entries'])} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
