"""Shared rules for batch gold labeling (ADR 0003, docs/specs/batch-gold-labeling-v1.md).

Used by scripts/eval_syllable_split.py (loading and scoring gold) and
scripts/build_batch_gold_queue.py (queues and sampling). Pure functions only;
nothing here writes product ``manual_syllables``.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.phoneme_core.syllable_split import _syllable_count  # noqa: E402

DEFAULT_BATCH_SIZE = 100
MIN_BATCH_SIZE = 50
MAX_BATCH_SIZE = 200
DEFAULT_SAMPLE_N = 30
DEFAULT_SAMPLE_SEED = 0
OK_STRATUM = "ok_global"
# Fields that bind a reviewed entry; everything else (audit, note, provenance) may change freely.
FINGERPRINTED_FIELDS = ("word", "ipa", "segments")


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def sort_key(word: str, ipa: Iterable[str]) -> tuple[str, tuple[str, ...]]:
    """Queue / sampling order: codepoint order on NFC word, then element-wise on the NFC phone array."""
    return (nfc(word), tuple(nfc(phone) for phone in ipa))


def reviewed_fingerprint(word: str, ipa: list[str], segments: list[str]) -> str:
    triple = [nfc(word), [nfc(phone) for phone in ipa], [nfc(segment) for segment in segments]]
    payload = json.dumps(triple, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def syllable_count(ipa: list[str]) -> int:
    # A vowel-less IPA still needs one segment for a non-empty word (spec, legality rule 4).
    return max(1, _syllable_count(list(ipa)))


def legality_error(word: Any, segments: Any, ipa: list[str] | None) -> str | None:
    """First violated legality rule, or None. ``ipa`` is the entry's IPA or the product default."""
    if not isinstance(word, str) or not word:
        return "word_not_string"
    if not is_str_list(segments):
        return "segments_not_string_list"
    if not segments or any(not segment for segment in segments):
        return "empty_segment"
    if any(0xD800 <= ord(ch) <= 0xDFFF for segment in segments for ch in segment):
        return "codepoint_split"
    if "".join(nfc(segment) for segment in segments) != nfc(word):
        return "concat_mismatch"
    if ipa is None or not is_str_list(ipa):
        return "ipa_not_string_list"
    # A lone surrogate is not a phone, and it cannot be UTF-8 encoded for the fingerprint.
    if any(0xD800 <= ord(ch) <= 0xDFFF for phone in ipa for ch in phone):
        return "ipa_lone_surrogate"
    if len(segments) != syllable_count(ipa):
        return "syllable_count_mismatch"
    return None


def stale_reason(entry: dict[str, Any]) -> str | None:
    """Why a ``reviewed: true`` entry is not (or no longer) reviewed gold; None when the binding holds."""
    ipa = entry.get("ipa")
    if ipa is None:
        return "ipa_missing"
    fingerprint = entry.get("reviewed_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return "fingerprint_missing"
    if fingerprint != reviewed_fingerprint(entry["word"], ipa, entry["segments"]):
        return "fingerprint_mismatch"
    return None


def update_entry(entry: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Return a copy with ``changes`` applied; a change to word/ipa/segments revokes ``reviewed``."""
    updated = {**entry, **changes}
    if any(field in changes and changes[field] != entry.get(field) for field in FINGERPRINTED_FIELDS):
        updated["reviewed"] = False
        updated["reviewed_fingerprint"] = None
    return updated


def mark_reviewed(entry: dict[str, Any], reviewer: str | None = None, reviewed_at: str | None = None) -> dict[str, Any]:
    """Explicit (re-)review: sets ``reviewed: true`` and the fingerprint in the same write. Requires ``ipa``."""
    if not is_str_list(entry.get("ipa")):
        raise ValueError("reviewed entries need an explicit ipa list")
    if legality_error(entry.get("word"), entry.get("segments"), entry["ipa"]):
        raise ValueError(f"illegal segments for {entry.get('word')!r}")
    return {
        **entry,
        "reviewed": True,
        "reviewed_fingerprint": reviewed_fingerprint(entry["word"], entry["ipa"], entry["segments"]),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
    }


def word_initial(word: str) -> str:
    first = word[:1].upper()
    return first if "A" <= first <= "Z" else "other"


def sample_frame(frame: list[dict[str, Any]], sample_n: int, sample_seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Uniform sample without replacement from the (word, ipa)-sorted frame; returns (rows, sampling record)."""
    ordered = sorted(frame, key=lambda row: sort_key(row["word"], row["ipa"]))
    frame_size = len(ordered)
    n_actual = min(max(sample_n, 0), frame_size)
    drawn = random.Random(sample_seed).sample(ordered, n_actual)
    drawn.sort(key=lambda row: sort_key(row["word"], row["ipa"]))
    record = {
        "sampling_stratum": OK_STRATUM,
        "frame_size": frame_size,
        "sample_n": sample_n,
        "sample_n_actual": n_actual,
        "sample_seed": sample_seed,
        "sampling_rate": n_actual / frame_size if frame_size else None,
        "denominator": "frame_size",
    }
    return drawn, record


def chunk_batches(rows: list[dict[str, Any]], code: str, initial: str, batch_size: int) -> list[dict[str, Any]]:
    """Sort a partition by (word, ipa) and stamp ``batch_id = "{code}|{initial}|{chunk_index}"``."""
    ordered = sorted(rows, key=lambda row: sort_key(row["word"], row["ipa"]))
    return [{**row, "batch_id": f"{code}|{initial}|{index // batch_size}"} for index, row in enumerate(ordered)]


def build_queue(
    rows: list[dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
    sample_n: int = DEFAULT_SAMPLE_N,
    sample_seed: int = DEFAULT_SAMPLE_SEED,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Queue rows and a report from evaluated rows ``{word, ipa, code, suggested_segments}``.

    ``code`` is ``"ok"``, a failure code, or ``"not_applicable"`` (excluded from the queue).
    Fail rows: every one, batched per (code, initial). ok rows: global sample.
    """
    if not MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be {MIN_BATCH_SIZE}-{MAX_BATCH_SIZE}")
    counts: dict[str, int] = {}
    partitions: dict[tuple[str, str], list[dict[str, Any]]] = {}
    ok_frame: list[dict[str, Any]] = []
    for row in rows:
        counts[row["code"]] = counts.get(row["code"], 0) + 1
        if row["code"] == "not_applicable":
            continue
        if row["code"] == "ok":
            ok_frame.append(row)
        else:
            partitions.setdefault((row["code"], word_initial(row["word"])), []).append(row)

    queue: list[dict[str, Any]] = []
    batches: dict[str, int] = {}
    for code, initial in sorted(partitions):
        for row in chunk_batches(partitions[(code, initial)], code, initial, batch_size):
            queue.append(_queue_row(row, None, None))
    sampled, sampling = sample_frame(ok_frame, sample_n, sample_seed)
    for row in chunk_batches(sampled, "ok", OK_STRATUM, batch_size):
        queue.append(_queue_row(row, OK_STRATUM, sampling["sampling_rate"]))
    for row in queue:
        batches[row["batch_id"]] = batches.get(row["batch_id"], 0) + 1

    failed = sum(n for code, n in counts.items() if code not in ("ok", "not_applicable"))
    applicable = counts.get("ok", 0) + failed
    report = {
        "evaluated_rows": len(rows),
        "counts_by_code": dict(sorted(counts.items())),
        "population": {
            "suggestion_rate": round(counts.get("ok", 0) / applicable, 6) if applicable else None,
            "numerator": "ok",
            "denominator": "ok + failed (not_applicable excluded)",
            "denominator_value": applicable,
        },
        "fail_all_rows": failed,
        "sampling": sampling,
        "batch_size": batch_size,
        "batches": batches,
        "queue_rows": len(queue),
    }
    return queue, report


def _queue_row(row: dict[str, Any], stratum: str | None, rate: float | None) -> dict[str, Any]:
    return {
        "word": row["word"],
        "ipa": list(row["ipa"]),
        "code": row["code"],
        "batch_id": row["batch_id"],
        "suggested_segments": list(row["suggested_segments"]) if row.get("suggested_segments") else None,
        "sampling_stratum": stratum,
        "sampling_rate": rate,
    }


def gold_template_entry(queue_row: dict[str, Any]) -> dict[str, Any]:
    """Unreviewed gold skeleton for a queue row; ``segments`` stays empty until a labeler fills it."""
    suggested = queue_row.get("suggested_segments")
    return {
        "id": f"{queue_row['word']}:{' '.join(queue_row['ipa'])}",
        "word": queue_row["word"],
        "ipa": list(queue_row["ipa"]),
        "segments": [],
        "reviewed": False,
        "reviewed_fingerprint": None,
        "reviewer": None,
        "reviewed_at": None,
        "suggestion_shown": None,
        "sampling_stratum": queue_row.get("sampling_stratum"),
        "sampling_rate": queue_row.get("sampling_rate"),
        "ipa_source": None,
        "note": None,
        "audit": (
            [{"segments": list(suggested), "source": "aligner", "model_id": None, "score": None, "abstained": False}]
            if suggested
            else []
        ),
    }
