#!/usr/bin/env python3
"""Evaluate syllable-split suggestions against gold grapheme fragment lists.

ADR 0001 asks for automated accuracy evaluation on the known word table before
anything else. For this evaluation pipeline, ADR 0003 (accepted) defines gold
as "(word, IPA) -> expected grapheme fragment list",
with reviewed gold kept in a gold file rather than in the product's
manual_syllables. ADR 0002 still governs the product side: manual_syllables,
aligner failure, apply rules, and the two-level priority. Gold comes from three
sources, keyed by (word, IPA), each with a label:

    known_word_table  WORD_SEGMENT_HINTS in backend/pipeline.py, against the
                      production default IPA (Pipeline.process_word); label
                      "candidate"
    fixture           status=ok cases in tests/fixtures/syllable_split_cases.json;
                      label "contract" (they lock the aligner's own output)
    curated           tests/fixtures/syllable_split_gold.json; label "reviewed"
                      only for entries with "reviewed": true, else "candidate"

Only human-confirmed ("reviewed") rows feed the reviewed tier. A curated entry
is reviewed only when "reviewed" is literally true, it carries an explicit
"ipa", and its "reviewed_fingerprint" matches the recomputed
SHA-256 of NFC [word, ipa, segments] (scripts/batch_gold.py). Each gold row is
classified once, in this order (docs/specs/batch-gold-labeling-v1.md):

    invalid_gold    breaks the legality contract (empty segment, does not
                    rebuild the word, codepoint split, segment count != the
                    IPA's syllable count, wrong field types); checked for every
                    source and never scored
    stale_reviewed  otherwise, "reviewed": true without ipa, without a
                    fingerprint, or with a mismatching one; scored as candidate

Contract and candidate rows are still scored, in the candidate tier, and never
count toward gold_reviewed. Reviewed rates are also reported per
sampling_stratum. The population suggestion_rate is not inferred from gold; it
comes from scripts/build_batch_gold_queue.py over the whole align table.

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

sys.path.insert(0, str(ROOT / "scripts"))
import batch_gold  # noqa: E402

FIXTURE_CASES_PATH = ROOT / "tests" / "fixtures" / "syllable_split_cases.json"
CURATED_GOLD_PATH = ROOT / "tests" / "fixtures" / "syllable_split_gold.json"
DEFAULT_TEXT_PATHS = (ROOT / "samples" / "demo.txt",)
DEFAULT_REPORT_PATH = ROOT / "reports" / "syllable_split_eval.json"
REPORT_VERSION = 3
TIERS = ("reviewed", "candidate")
UNSTRATIFIED = "unstratified"


def _key(word: str, ipa: list[str]) -> tuple[str, tuple[str, ...]]:
    return (word, tuple(ipa))


def _nfc_list(value: Any) -> Any:
    return [batch_gold.nfc(item) for item in value] if batch_gold.is_str_list(value) else value


def load_raw_gold(curated_path: Path = CURATED_GOLD_PATH) -> list[dict[str, Any]]:
    """Per-source gold rows ``{word, ipa, ipa_given, gold, source, label, ...}``.

    ``ipa_given`` False (only when the field is truly absent) means the
    production default IPA; a present ``ipa`` is kept as is, even null or the
    wrong type, so merge_gold can report it as invalid. Curated rows also carry
    ``id``, ``reviewed_fingerprint``, ``sampling_stratum`` and ``ipa_source``.
    A curated ``label`` of "reviewed" is only the entry's claim: merge_gold
    checks legality first and only then the fingerprint binding, downgrading
    stale claims to candidate.
    """
    raw: list[dict[str, Any]] = []
    for word, segments in WORD_SEGMENT_HINTS.items():
        raw.append(
            {"word": word, "ipa": None, "ipa_given": False, "gold": list(segments), "source": "known_word_table", "label": "candidate"}
        )
    for case in json.loads(FIXTURE_CASES_PATH.read_text(encoding="utf-8"))["cases"]:
        if case["expected"]["status"] == "ok":
            raw.append(
                {"word": case["word"], "ipa": case["ipa"], "ipa_given": True, "gold": case["expected"]["segments"], "source": "fixture", "label": "contract"}
            )
    # Read from disk on every call: no reviewed state is cached between loads.
    for entry in json.loads(curated_path.read_text(encoding="utf-8"))["entries"]:
        word = batch_gold.nfc(entry["word"]) if isinstance(entry.get("word"), str) else entry.get("word")
        raw.append(
            {
                "word": word,
                "ipa": _nfc_list(entry.get("ipa")),
                "ipa_given": "ipa" in entry,
                "gold": _nfc_list(entry.get("segments")),
                "source": "curated",
                # Only a literal true counts; "yes", 1 and the like stay candidates.
                "label": "reviewed" if entry.get("reviewed") is True else "candidate",
                "id": entry.get("id"),
                "reviewed_fingerprint": entry.get("reviewed_fingerprint"),
                "sampling_stratum": entry.get("sampling_stratum"),
                "ipa_source": entry.get("ipa_source"),
            }
        )
    return raw


def _ipa_given(row: dict[str, Any]) -> bool:
    # Rows built without the flag (tests, older callers) fall back to "a non-null ipa was given".
    return row.get("ipa_given", row["ipa"] is not None)


def merge_gold(pipe: Pipeline, raw: list[dict[str, Any]], issues: dict[str, list[dict[str, Any]]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge raw rows by (word, IPA) into ``{word, ipa, gold, sources, labels, reviewed, conflict}``; also return invalid golds.

    Each row is classified once: a gold that breaks the legality contract is
    reported as invalid (with ``reason``) and left out rather than scored;
    otherwise a curated ``reviewed: true`` row whose fingerprint binding fails
    is recorded in ``issues["stale_reviewed"]`` and merged as a candidate. Curated rows marked
    ``ipa_source: "human"`` are listed in ``issues["ipa_source_human"]``.
    ``conflict`` is None when all sources agree, else
    ``{"resolution": "reviewed" | "unresolved", "golds": [{source, label, gold}, ...]}``;
    unresolved pairs get ``gold`` None so they are never scored against either side.
    """
    issues = issues if issues is not None else {}
    stale = issues.setdefault("stale_reviewed", [])
    human_ipa = issues.setdefault("ipa_source_human", [])
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row["word"], str) or not row["word"]:
            ipa, reason = None, "word_not_string"
        elif _ipa_given(row):
            # A present ipa is never replaced by the default, even when null or mistyped.
            ipa = row["ipa"]
            reason = batch_gold.legality_error(row["word"], row["gold"], ipa)
        else:
            ipa = pipe.process_word(row["word"])["ipa"]
            reason = batch_gold.legality_error(row["word"], row["gold"], ipa)
        if reason:
            invalid.append(
                {"id": row.get("id"), "word": row["word"], "gold": row["gold"], "source": row["source"], "label": row["label"], "reason": reason}
            )
            continue
        # The fingerprint is computed only now: legality has ruled out lone surrogates
        # and wrong types, which would break hashing or be misreported as stale.
        if row["label"] == "reviewed" and "reviewed_fingerprint" in row:
            binding = {"word": row["word"], "ipa": row["ipa"] if _ipa_given(row) else None, "segments": row["gold"],
                       "reviewed_fingerprint": row["reviewed_fingerprint"]}
            reason = batch_gold.stale_reason(binding)
            if reason:
                stale.append({"id": row.get("id"), "word": row["word"], "source": row["source"], "reason": reason})
                row = {**row, "label": "candidate"}
        if row.get("ipa_source") == "human":
            human_ipa.append({"id": row.get("id"), "word": row["word"], "ipa": list(ipa)})
        groups.setdefault(_key(row["word"], list(ipa)), []).append(row)

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
        gold_rows = [row for row in rows if row["label"] == "reviewed"] if reviewed else rows
        stratum = next((row["sampling_stratum"] for row in gold_rows if row.get("sampling_stratum")), None)
        merged.append(
            {
                "word": word,
                "ipa": list(ipa),
                "gold": gold,
                "sources": [row["source"] for row in rows],
                "labels": sorted({row["label"] for row in rows}),
                "reviewed": reviewed,
                "tier": "reviewed" if reviewed else "candidate",
                "sampling_stratum": stratum,
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


def collect_gold(
    pipe: Pipeline, curated_path: Path = CURATED_GOLD_PATH, issues: dict[str, list[dict[str, Any]]] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return merge_gold(pipe, load_raw_gold(curated_path), issues)


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
                        "sampling_stratum": None,
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
    issues: dict[str, list[dict[str, Any]]] = {}
    gold_rows, invalid_gold = collect_gold(pipe, curated_path, issues)
    gold_keys = {_key(row["word"], row["ipa"]) for row in gold_rows}
    unlabeled = collect_unlabeled(pipe, texts or [], gold_keys)

    overall = _empty_counts()
    by_tier = {tier: _empty_counts() for tier in TIERS}
    by_source: dict[str, dict[str, Any]] = {}
    by_stratum: dict[str, dict[str, Any]] = {}
    items = []
    for row in [*gold_rows, *unlabeled]:
        suggestion = pipe.suggest_syllable_split(row["word"], row["ipa"])
        unresolved = row["conflict"] is not None and row["conflict"]["resolution"] == "unresolved"
        outcome, detail = classify(suggestion, row["gold"], conflicted=unresolved)
        _bump(overall, outcome, detail)
        if row["tier"] in by_tier and not unresolved:
            _bump(by_tier[row["tier"]], outcome, detail)
            if row["tier"] == "reviewed":
                _bump(by_stratum.setdefault(row["sampling_stratum"] or UNSTRATIFIED, _empty_counts()), outcome, detail)
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
        "stale_reviewed": issues["stale_reviewed"],
        "ipa_source_human": issues["ipa_source_human"],
        "rates": {
            "reviewed": compute_rates(by_tier["reviewed"]),
            "candidate": compute_rates(by_tier["candidate"]),
            "all_gold": compute_rates(all_gold),
        },
        # Reviewed tier only, so fail-all and ok_global samples are not mixed; unsampled rows are "unstratified".
        "reviewed_rates_by_stratum": {stratum: compute_rates(counts) for stratum, counts in sorted(by_stratum.items())},
        "overall": overall,
        "by_tier": by_tier,
        "reviewed_by_stratum": by_stratum,
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
        f" invalid {len(report['invalid_gold'])}, stale_reviewed {len(report['stale_reviewed'])},"
        f" ipa_source_human {len(report['ipa_source_human'])})",
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
    for stratum, rates in report["reviewed_rates_by_stratum"].items():
        lines.append(
            f"  reviewed/{stratum:<14} {rates['exact_rate_when_suggested']} ({rates['compared']} compared)"
            f" / {rates['suggestion_rate_on_gold']} ({rates['with_gold']} with gold)"
        )
    lines.append("by source:")
    for source, counts in sorted(report["by_source"].items()):
        lines.append(f"  {source:<17} {_counts_line(counts)}")
    for bad in report["invalid_gold"]:
        gold = "|".join(bad["gold"]) if batch_gold.is_str_list(bad["gold"]) else repr(bad["gold"])
        lines.append(f"  invalid gold ({bad['source']}) {bad['word']}: {gold} ({bad['reason']})")
    for row in report["stale_reviewed"]:
        lines.append(f"  stale reviewed ({row['source']}) {row['id'] or row['word']}: {row['reason']}, scored as candidate")
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


def _safe_text(text: str) -> str:
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


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
    # Invalid gold may echo lone surrogates; escape them instead of crashing the output.
    print(_safe_text(format_summary(report)))
    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # backslashreplace turns a lone surrogate into a "\udXXX" JSON escape, so the file stays valid JSON.
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="backslashreplace")
        print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
