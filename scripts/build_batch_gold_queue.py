#!/usr/bin/env python3
"""Build the batch gold labeling queue (ADR 0003, docs/specs/batch-gold-labeling-v1.md).

Every (word, IPA) in the align table goes through Pipeline.suggest_syllable_split,
the same path the product uses. The IPA rows are the word's CMUdict
pronunciations as the product converts them (all variants, not only the
product default). Then:

    fail-all   every failed row (not_applicable excluded), partitioned by
               failure code and word initial, sorted by (word, ipa), chunked
               into batches; batch_id = "{code}|{initial}|{chunk_index}"
    ok_global  uniform sample without replacement of the ok rows
               (sample_n=30, sample_seed=0 by default)

Outputs a JSONL queue and a JSON report (population counts, population
suggestion_rate, sampling record, batch sizes). Optionally writes unreviewed
gold skeletons for the sampled rows. Never sets reviewed and never writes
manual_syllables.

Usage:
    python scripts/build_batch_gold_queue.py
    python scripts/build_batch_gold_queue.py --batch-size 50 --sample-n 30 --sample-seed 0
    python scripts/build_batch_gold_queue.py --limit 2000 --out /tmp/queue.jsonl --report /tmp/queue_report.json
    python scripts/build_batch_gold_queue.py --gold-template /tmp/gold_template.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import batch_gold  # noqa: E402
from backend.pipeline import ALIGN_TABLE_PATH, Pipeline  # noqa: E402
from backend.phoneme_core.syllable_split import load_align_table  # noqa: E402

DEFAULT_QUEUE_PATH = ROOT / "reports" / "batch_gold_queue.jsonl"
DEFAULT_REPORT_PATH = ROOT / "reports" / "batch_gold_queue_report.json"
QUEUE_REPORT_VERSION = 1


def evaluate_table(pipe: Pipeline, table: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    """One row ``{word, ipa, code, suggested_segments}`` per distinct (word, CMUdict IPA) in the table."""
    # suggest_syllable_split reads this lazily; pin it to the table being queued.
    pipe._align_table = table
    words = sorted((table.get("entries") or {}), key=batch_gold.nfc)
    if limit is not None:
        words = words[:limit]
    rows: list[dict[str, Any]] = []
    for word in words:
        seen: set[tuple[str, ...]] = set()
        for ipa in pipe._cmudict_ipa_pronunciations(word) or []:
            ipa = [batch_gold.nfc(phone) for phone in ipa]
            if tuple(ipa) in seen:
                continue
            seen.add(tuple(ipa))
            suggestion = pipe.suggest_syllable_split(word, ipa)
            code = suggestion["code"] if suggestion["status"] == "failed" else suggestion["status"]
            rows.append({"word": batch_gold.nfc(word), "ipa": ipa, "code": code, "suggested_segments": suggestion["segments"] or None})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--align-table", type=Path, default=ALIGN_TABLE_PATH, help="align table JSON (default: data/syllable_align_table.json)")
    parser.add_argument("--out", type=Path, default=DEFAULT_QUEUE_PATH, help=f"queue JSONL (default: {DEFAULT_QUEUE_PATH.relative_to(ROOT)})")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help=f"report JSON (default: {DEFAULT_REPORT_PATH.relative_to(ROOT)})")
    parser.add_argument("--gold-template", type=Path, help="also write unreviewed gold skeletons for the sampled rows")
    parser.add_argument("--batch-size", type=int, default=batch_gold.DEFAULT_BATCH_SIZE, help="rows per batch, 50-200 (default: 100)")
    parser.add_argument("--sample-n", type=int, default=batch_gold.DEFAULT_SAMPLE_N, help="ok rows to sample globally (default: 30)")
    parser.add_argument("--sample-seed", type=int, default=batch_gold.DEFAULT_SAMPLE_SEED, help="sampling seed (default: 0)")
    parser.add_argument("--limit", type=int, help="development only: first N words in sorted order (default: all)")
    args = parser.parse_args(argv)
    if not batch_gold.MIN_BATCH_SIZE <= args.batch_size <= batch_gold.MAX_BATCH_SIZE:
        parser.error(f"--batch-size must be {batch_gold.MIN_BATCH_SIZE}-{batch_gold.MAX_BATCH_SIZE}")
    if args.sample_n < 0:
        parser.error("--sample-n must be >= 0")

    table = load_align_table(args.align_table)
    rows = evaluate_table(Pipeline(), table, args.limit)
    queue, report = batch_gold.build_queue(rows, args.batch_size, args.sample_n, args.sample_seed)
    report = {
        "report_version": QUEUE_REPORT_VERSION,
        "align_table": {key: table.get(key) for key in ("aligner_version", "cmudict_sha256")},
        "limit": args.limit,
        **report,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in queue:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.gold_template:
        entries = [batch_gold.gold_template_entry(row) for row in queue if row["sampling_stratum"]]
        template = {
            "version": 1,
            "description": "Unreviewed gold skeletons from scripts/build_batch_gold_queue.py (ADR 0003). Fill segments, then set reviewed only through an explicit review that writes reviewed_fingerprint.",
            "sampling": report["sampling"],
            "entries": entries,
        }
        args.gold_template.parent.mkdir(parents=True, exist_ok=True)
        args.gold_template.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sampling = report["sampling"]
    print(
        f"evaluated {report['evaluated_rows']} (word, ipa) rows; counts {report['counts_by_code']}\n"
        f"population suggestion_rate {report['population']['suggestion_rate']} over {report['population']['denominator_value']}\n"
        f"fail-all rows {report['fail_all_rows']} in {sum(1 for b in report['batches'] if not b.startswith('ok|'))} batches;"
        f" ok sample {sampling['sample_n_actual']}/{sampling['frame_size']} (seed {sampling['sample_seed']})\n"
        f"queue: {args.out}\nreport: {args.report}" + (f"\ngold template: {args.gold_template}" if args.gold_template else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
