#!/usr/bin/env python3
"""Evaluate syllable-split suggestions against gold grapheme fragment lists.

ADR 0001 asks for automated accuracy evaluation on the known word table before
anything else; ADR 0002 defines gold as "word -> expected grapheme fragment
list". Gold comes from three sources, keyed by (word, IPA), each with a label:

    known_word_table  WORD_SEGMENT_HINTS in backend/pipeline.py, against the
                      production default IPA (Pipeline.process_word); label
                      "candidate"
    fixture           status=ok cases in tests/fixtures/syllable_split_cases.json;
                      label "contract" (they lock the aligner's own output)
    curated           tests/fixtures/syllable_split_gold.json; label "reviewed"
                      only for entries with "reviewed": true, else "candidate"

ADR 0002 makes gold only what a human confirmed, so only "reviewed" rows feed
the reviewed tier. Contract and candidate rows are still scored, in the
candidate tier, and never count toward gold_reviewed.

When sources disagree on one (word, IPA): a single reviewed split wins and the
pair stays in the reviewed tier; otherwise (no reviewed row, or reviewed rows
that disagree) the pair is an unresolved conflict, scored as gold_conflict and
left out of every rate.

Words from --text files (default: the strict sample sentence and
samples/demo.txt) are also run; multi-syllable ones without gold count as
missing_gold, so the report shows how much of the input gold actually covers.

Every item goes through Pipeline.suggest_syllable_split, the same Python core
the server uses. Outcomes:

    exact          suggestion == gold
    mismatch       suggestion != gold (split into segment_count_differs and
                   boundary_differs)
    no_suggestion  the aligner failed, counted by failure code
    missing_gold   suggestion made but no gold to compare with
    gold_conflict  sources disagree and no single reviewed split settles it
    not_applicable fewer than two syllables; on gold it is split into
                   gold_single_segment (agrees, left out of rates) and
                   gold_multi_segment (gold expects a split, so it counts
                   against suggestion_rate_on_gold like no_suggestion)

Rates are computed per tier (reviewed, candidate, all_gold), rounded to four
places, and null when their denominator is zero:

    exact_rate_when_suggested = exact / (exact + mismatch)
    suggestion_rate_on_gold   = (exact + mismatch)
                                / (exact + mismatch + no_suggestion + gold_multi_segment)

Usage:
    python scripts/eval_syllable_split.py                 # summary + reports/syllable_split_eval.json
    python scripts/eval_syllable_split.py --out PATH
    python scripts/eval_syllable_split.py --no-write --text my_words.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.pipeline import STRICT_SAMPLE_SENTENCE, WORD_SEGMENT_HINTS, Pipeline, pipeline as default_pipeline  # noqa: E402
from backend.phoneme_core.syllable_split import FAILURE_CODES  # noqa: E402

FIXTURE_CASES_PATH = ROOT / "tests" / "fixtures" / "syllable_split_cases.json"
CURATED_GOLD_PATH = ROOT / "tests" / "fixtures" / "syllable_split_gold.json"
DEFAULT_TEXT_PATHS = (ROOT / "samples" / "demo.txt",)
DEFAULT_REPORT_PATH = ROOT / "reports" / "syllable_split_eval.json"
REPORT_VERSION = 2
TIERS = ("reviewed", "candidate")


def _key(word: str, ipa: list[str]) -> tuple[str, tuple[str, ...]]:
    return (word, tuple(ipa))


def load_raw_gold(curated_path: Path = CURATED_GOLD_PATH) -> list[dict[str, Any]]:
    """Per-source gold rows ``{word, ipa, gold, source, label}``; ``ipa`` None means the production default."""
    raw: list[dict[str, Any]] = []
    for word, segments in WORD_SEGMENT_HINTS.items():
        raw.append({"word": word, "ipa": None, "gold": list(segments), "source": "known_word_table", "label": "candidate"})
    for case in json.loads(FIXTURE_CASES_PATH.read_text(encoding="utf-8"))["cases"]:
        if case["expected"]["status"] == "ok":
            raw.append(
                {"word": case["word"], "ipa": case["ipa"], "gold": case["expected"]["segments"], "source": "fixture", "label": "contract"}
            )
    for entry in json.loads(curated_path.read_text(encoding="utf-8"))["entries"]:
        raw.append(
            {
                "word": entry["word"],
                "ipa": entry.get("ipa"),
                "gold": list(entry["segments"]),
                "source": "curated",
                # Only a literal true counts; "yes", 1 and the like stay candidates.
                "label": "reviewed" if entry.get("reviewed") is True else "candidate",
            }
        )
    return raw


def merge_gold(pipe: Pipeline, raw: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge raw rows by (word, IPA) into ``{word, ipa, gold, sources, labels, reviewed, conflict}``; also return invalid golds.

    A gold whose segments do not join back to the word cannot be a split of it;
    it is reported as invalid and left out rather than scored as a mismatch.
    ``conflict`` is None when all sources agree, else
    ``{"resolution": "reviewed" | "unresolved", "golds": [{source, label, gold}, ...]}``;
    unresolved pairs get ``gold`` None so they are never scored against either side.
    """
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    for row in raw:
        if "".join(row["gold"]) != row["word"]:
            invalid.append({"word": row["word"], "gold": row["gold"], "source": row["source"], "label": row["label"]})
            continue
        ipa = list(row["ipa"]) if row["ipa"] is not None else pipe.process_word(row["word"])["ipa"]
        groups.setdefault(_key(row["word"], ipa), []).append(row)

    merged: list[dict[str, Any]] = []
    for (word, ipa), rows in groups.items():
        reviewed_golds = _distinct(row["gold"] for row in rows if row["label"] == "reviewed")
        all_golds = _distinct(row["gold"] for row in rows)
        if len(all_golds) == 1:
            gold, reviewed, resolution = all_golds[0], bool(reviewed_golds), None
        elif len(reviewed_golds) == 1:
            gold, reviewed, resolution = reviewed_golds[0], True, "reviewed"
        else:
            gold, reviewed, resolution = None, False, "unresolved"
        merged.append(
            {
                "word": word,
                "ipa": list(ipa),
                "gold": gold,
                "sources": [row["source"] for row in rows],
                "labels": sorted({row["label"] for row in rows}),
                "reviewed": reviewed,
                "tier": "reviewed" if reviewed else "candidate",
                "conflict": None
                if resolution is None
                else {
                    "resolution": resolution,
                    "golds": [{"source": row["source"], "label": row["label"], "gold": row["gold"]} for row in rows],
                },
            }
        )
    return merged, invalid


def _distinct(golds: Any) -> list[list[str]]:
    out: list[list[str]] = []
    for gold in golds:
        if gold not in out:
            out.append(gold)
    return out


def collect_gold(pipe: Pipeline, curated_path: Path = CURATED_GOLD_PATH) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return merge_gold(pipe, load_raw_gold(curated_path))


def collect_unlabeled(pipe: Pipeline, texts: list[str], gold_keys: set[tuple[str, tuple[str, ...]]]) -> list[dict[str, Any]]:
    """Words from free text with their production default IPA, minus those already in gold."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    rows: list[dict[str, Any]] = []
    for text in texts:
        for sentence in pipe.process_text(text)["sentences"]:
            for word in sentence["words"]:
                surface = str(word.get("word") or "").strip()
                key = _key(surface, list(word.get("ipa") or []))
                lower_key = _key(surface.lower().rstrip(".,!?;:…"), key[1])
                if not surface or key in seen or key in gold_keys or lower_key in gold_keys:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "word": surface,
                        "ipa": list(key[1]),
                        "gold": None,
                        "sources": ["text"],
                        "labels": [],
                        "reviewed": False,
                        "tier": "no_gold",
                        "conflict": None,
                    }
                )
    return rows


def classify(suggestion: dict[str, Any], gold: list[str] | None, conflicted: bool = False) -> tuple[str, str | None]:
    if conflicted:
        return "gold_conflict", None
    status = suggestion["status"]
    if status == "not_applicable":
        if gold is None:
            return "not_applicable", "no_gold"
        return "not_applicable", "gold_single_segment" if len(gold) < 2 else "gold_multi_segment"
    if status == "failed":
        return "no_suggestion", suggestion["code"]
    if gold is None:
        return "missing_gold", None
    if suggestion["segments"] == gold:
        return "exact", None
    if len(suggestion["segments"]) != len(gold):
        return "mismatch", "segment_count_differs"
    return "mismatch", "boundary_differs"


def _empty_counts() -> dict[str, Any]:
    return {
        "items": 0,
        "exact": 0,
        "mismatch": {"total": 0, "segment_count_differs": 0, "boundary_differs": 0},
        "no_suggestion": {"total": 0, **{code: 0 for code in FAILURE_CODES}},
        "missing_gold": 0,
        "gold_conflict": 0,
        "not_applicable": {"total": 0, "no_gold": 0, "gold_single_segment": 0, "gold_multi_segment": 0},
    }


def _bump(counts: dict[str, Any], outcome: str, detail: str | None) -> None:
    counts["items"] += 1
    if outcome in ("mismatch", "no_suggestion", "not_applicable"):
        counts[outcome]["total"] += 1
        counts[outcome][detail] = counts[outcome].get(detail, 0) + 1
    else:
        counts[outcome] += 1


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def compute_rates(counts: dict[str, Any]) -> dict[str, Any]:
    """Rates over gold-bearing counts; see the module docstring for the formulas."""
    compared = counts["exact"] + counts["mismatch"]["total"]
    with_gold = compared + counts["no_suggestion"]["total"] + counts["not_applicable"]["gold_multi_segment"]
    return {
        "compared": compared,
        "with_gold": with_gold,
        "exact_rate_when_suggested": _rate(counts["exact"], compared),
        "suggestion_rate_on_gold": _rate(compared, with_gold),
    }


def evaluate(pipe: Pipeline = default_pipeline, texts: list[str] | None = None, curated_path: Path = CURATED_GOLD_PATH) -> dict[str, Any]:
    gold_rows, invalid_gold = collect_gold(pipe, curated_path)
    gold_keys = {_key(row["word"], row["ipa"]) for row in gold_rows}
    unlabeled = collect_unlabeled(pipe, texts or [], gold_keys)

    overall = _empty_counts()
    by_tier = {tier: _empty_counts() for tier in TIERS}
    by_source: dict[str, dict[str, Any]] = {}
    items = []
    for row in [*gold_rows, *unlabeled]:
        suggestion = pipe.suggest_syllable_split(row["word"], row["ipa"])
        unresolved = row["conflict"] is not None and row["conflict"]["resolution"] == "unresolved"
        outcome, detail = classify(suggestion, row["gold"], conflicted=unresolved)
        _bump(overall, outcome, detail)
        if row["tier"] in by_tier and not unresolved:
            _bump(by_tier[row["tier"]], outcome, detail)
        # A pair can carry several rows from one source; count it once per source.
        for source in dict.fromkeys(row["sources"]):
            _bump(by_source.setdefault(source, _empty_counts()), outcome, detail)
        items.append(
            {
                **row,
                "suggestion": suggestion["segments"],
                "status": suggestion["status"],
                "code": suggestion["code"],
                "outcome": outcome,
                "detail": detail,
            }
        )

    all_gold = _empty_counts()
    for item in items:
        if item["tier"] in by_tier and item["outcome"] != "gold_conflict":
            _bump(all_gold, item["outcome"], item["detail"])
    return {
        "report_version": REPORT_VERSION,
        "align_table": {
            key: (pipe._align_table or {}).get(key) for key in ("aligner_version", "cmudict_sha256")
        },
        "gold_items": len(gold_rows),
        "gold_reviewed": sum(1 for row in gold_rows if row["reviewed"]),
        "gold_candidate": sum(1 for row in gold_rows if not row["reviewed"] and row["gold"] is not None),
        "gold_conflicts": {
            "resolved_by_review": sum(1 for row in gold_rows if row["conflict"] and row["conflict"]["resolution"] == "reviewed"),
            "unresolved": sum(1 for row in gold_rows if row["conflict"] and row["conflict"]["resolution"] == "unresolved"),
        },
        "invalid_gold": invalid_gold,
        "rates": {
            "reviewed": compute_rates(by_tier["reviewed"]),
            "candidate": compute_rates(by_tier["candidate"]),
            "all_gold": compute_rates(all_gold),
        },
        "overall": overall,
        "by_tier": by_tier,
        "by_source": by_source,
        "items": items,
    }


def _counts_line(counts: dict[str, Any]) -> str:
    return (
        f"items={counts['items']} exact={counts['exact']} mismatch={counts['mismatch']['total']}"
        f" no_suggestion={counts['no_suggestion']['total']} missing_gold={counts['missing_gold']}"
        f" gold_conflict={counts['gold_conflict']} not_applicable={counts['not_applicable']['total']}"
    )


def format_summary(report: dict[str, Any]) -> str:
    overall = report["overall"]
    codes = ", ".join(f"{code}={n}" for code, n in overall["no_suggestion"].items() if code != "total" and n)
    na = overall["not_applicable"]
    conflicts = report["gold_conflicts"]
    lines = [
        f"gold items: {report['gold_items']} (reviewed {report['gold_reviewed']}, candidate {report['gold_candidate']},"
        f" conflicts resolved_by_review={conflicts['resolved_by_review']} unresolved={conflicts['unresolved']},"
        f" invalid {len(report['invalid_gold'])})",
        f"evaluated: {overall['items']}",
        f"  exact:          {overall['exact']}",
        f"  mismatch:       {overall['mismatch']['total']}"
        f" (segment_count_differs={overall['mismatch']['segment_count_differs']},"
        f" boundary_differs={overall['mismatch']['boundary_differs']})",
        f"  no_suggestion:  {overall['no_suggestion']['total']}" + (f" ({codes})" if codes else ""),
        f"  missing_gold:   {overall['missing_gold']}",
        f"  gold_conflict:  {overall['gold_conflict']}",
        f"  not_applicable: {na['total']} (no_gold={na['no_gold']}, gold_single_segment={na['gold_single_segment']},"
        f" gold_multi_segment={na['gold_multi_segment']})",
        "rates (exact when suggested / suggestion on gold):",
    ]
    for tier, rates in report["rates"].items():
        lines.append(
            f"  {tier:<10} {rates['exact_rate_when_suggested']} ({rates['compared']} compared)"
            f" / {rates['suggestion_rate_on_gold']} ({rates['with_gold']} with gold)"
        )
    lines.append("by tier:")
    for tier, counts in report["by_tier"].items():
        lines.append(f"  {tier:<17} {_counts_line(counts)}")
    lines.append("by source:")
    for source, counts in sorted(report["by_source"].items()):
        lines.append(f"  {source:<17} {_counts_line(counts)}")
    for bad in report["invalid_gold"]:
        lines.append(f"  invalid gold ({bad['source']}) {bad['word']}: {'|'.join(bad['gold'])} does not rebuild the word")
    for item in report["items"]:
        if item["conflict"]:
            golds = ", ".join(f"{g['source']}={'|'.join(g['gold'])}" for g in item["conflict"]["golds"])
            lines.append(f"  conflict ({item['conflict']['resolution']}) {item['word']}: {golds}")
    for item in report["items"]:
        if item["outcome"] == "mismatch":
            lines.append(
                f"  mismatch [{item['tier']}] {item['word']}: suggested {'|'.join(item['suggestion'])} vs gold {'|'.join(item['gold'])}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_PATH, help=f"JSON report path (default: {DEFAULT_REPORT_PATH.relative_to(ROOT)})")
    parser.add_argument("--no-write", action="store_true", help="print the summary only")
    parser.add_argument("--text", type=Path, action="append", help="extra text file(s) for missing_gold coverage (default: samples/demo.txt)")
    parser.add_argument("--gold", type=Path, default=CURATED_GOLD_PATH, help="curated gold JSON")
    args = parser.parse_args(argv)

    text_paths = args.text if args.text else list(DEFAULT_TEXT_PATHS)
    texts = [STRICT_SAMPLE_SENTENCE, *(path.read_text(encoding="utf-8") for path in text_paths)]
    report = evaluate(texts=texts, curated_path=args.gold)
    print(format_summary(report))
    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
