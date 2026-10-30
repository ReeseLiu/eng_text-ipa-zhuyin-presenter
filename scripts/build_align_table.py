#!/usr/bin/env python3
"""Build the grapheme–phoneme alignment table used by syllable-split suggestions.

The aligner is constrained (ADR 0002): every letter belongs to exactly one chunk
and each chunk maps to phonemes with one of these shapes only:

    1 letter  -> no phoneme   (silent letter)
    1 letter  -> 1 phoneme
    1 letter  -> 2 phonemes   (small whitelist, e.g. x -> k s, u -> j u)
    2 letters -> 1 phoneme    (digraph whitelist or doubled consonant)
    3 letters -> 1 phoneme    (small trigraph whitelist)

2 -> 2 chunks and phonemes without letters are impossible by construction. A
doubled consonant letter may not be silent on its own, so "mm" -> /m/ is always
one 2-letter chunk.

Chunk scores come from a few rounds of hard (Viterbi) EM over CMUdict; rare
mappings are then pruned so words that need them fail instead of aligning badly.
For every phoneme position we also record whether a competing alignment would
put the chunk boundary somewhere else with a score within LOW_CONFIDENCE_GAP of
the best one; runtime refuses to cut at those positions.

Outputs:
    data/syllable_align_table.json
    app/browser_align.js   (same payload, loaded lazily by the browser app)

Usage:
    python scripts/build_align_table.py           # rebuild both files
    python scripts/build_align_table.py --check   # verify files match cmudict + aligner version
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.phoneme_core.g2p import SimpleG2P  # noqa: E402
from backend.phoneme_core.rules_conservative import is_vowel  # noqa: E402

CMUDICT_PATH = ROOT / "data" / "cmudict.dict"
TABLE_PATH = ROOT / "data" / "syllable_align_table.json"
BROWSER_ALIGN_PATH = ROOT / "app" / "browser_align.js"

# Bump whenever the inventory, scoring, pruning or output format changes.
ALIGNER_VERSION = "1.0.1"
TABLE_FORMAT = "syllable_align_table/1"

EM_ITERATIONS = 4
PRUNE_MIN_COUNT = 3
SMOOTHING = 0.1
LOW_CONFIDENCE_GAP = 2.0

# (letters, phonemes) per chunk code; order is part of the format.
CHUNK_CODES = {"a": (1, 0), "b": (1, 1), "c": (1, 2), "d": (2, 1), "e": (3, 1)}
CODE_FOR_SHAPE = {shape: code for code, shape in CHUNK_CODES.items()}

VOWEL_LETTERS = set("aeiouy")
SILENT_ONLY = set("'-")

VOWEL_PHONES = ["i", "ɪ", "eɪ", "ɛ", "æ", "ə", "ʌ", "ɑ", "ɔ", "ʊ", "u", "aɪ", "aʊ", "oʊ", "ɔɪ", "ɚ"]

CONSONANT_1TO1 = {
    "b": ["b", "p"],
    "c": ["k", "s", "ʃ", "tʃ", "z"],
    "d": ["d", "dʒ", "t"],
    "f": ["f", "v"],
    "g": ["ɡ", "dʒ", "ʒ", "k"],
    "h": ["h"],
    "j": ["dʒ", "j", "h", "ʒ"],
    "k": ["k"],
    "l": ["l"],
    "m": ["m"],
    "n": ["n", "ŋ"],
    "p": ["p", "f"],
    "q": ["k"],
    "r": ["ɹ", "ɚ"],
    "s": ["s", "z", "ʃ", "ʒ"],
    "t": ["t", "ʃ", "tʃ", "θ", "d", "ð"],
    "v": ["v", "f"],
    "w": ["w", "v", "h"],
    "x": ["z", "ʃ", "s", "k", "ɡ"],
    "z": ["z", "s", "ʒ", "t"],
}

ONE_TO_TWO = {
    "x": [("k", "s"), ("ɡ", "z"), ("k", "ʃ"), ("ɡ", "ʒ")],
    "u": [("j", "u"), ("j", "ʊ"), ("j", "ə"), ("j", "ɚ")],
    "e": [("j", "u")],
    "o": [("w", "ʌ"), ("w", "ɑ")],
    "l": [("ə", "l")],
    "m": [("ə", "m")],
    "n": [("ə", "n")],
}

CONSONANT_DIGRAPHS = {
    "th": ["θ", "ð", "t"],
    "sh": ["ʃ"],
    "ch": ["tʃ", "k", "ʃ"],
    "ph": ["f", "v", "p"],
    "gh": ["ɡ", "f"],
    "ck": ["k"],
    "ng": ["ŋ"],
    "wh": ["w", "h"],
    "wr": ["ɹ"],
    "kn": ["n"],
    "gn": ["n"],
    "mb": ["m"],
    "sc": ["s", "ʃ"],
    "gu": ["ɡ"],
    "qu": ["k"],
    "ti": ["ʃ", "tʃ"],
    "ci": ["ʃ"],
    "si": ["ʒ", "ʃ"],
    "ce": ["ʃ"],
    "cq": ["k"],
}

VOWEL_DIGRAPHS = [
    "aa", "ae", "ai", "ao", "au", "aw", "ay",
    "ea", "ee", "ei", "eo", "eu", "ew", "ey",
    "ie", "oa", "oe", "oi", "oo", "ou", "ow", "oy",
    "ue", "ui", "uy", "ye",
]

R_COLORED_DIGRAPHS = ["ar", "er", "ir", "or", "ur", "yr", "re"]

TRIGRAPHS = {
    "tch": ["tʃ"],
    "dge": ["dʒ"],
    "igh": ["aɪ"],
    "sch": ["ʃ", "s"],
    "eau": ["oʊ", "u"],
    "ear": ["ɚ"],
    "our": ["ɚ"],
    "ssi": ["ʃ"],
}


def build_inventory() -> dict[str, set[tuple[str, ...]]]:
    """Map each grapheme chunk to the phoneme tuples it may produce."""
    inv: dict[str, set[tuple[str, ...]]] = {}

    def add(grapheme: str, phones: tuple[str, ...]) -> None:
        inv.setdefault(grapheme, set()).add(phones)

    for letter in "abcdefghijklmnopqrstuvwxyz":
        add(letter, ())
        if letter in VOWEL_LETTERS:
            for phone in VOWEL_PHONES + ["j", "w"]:
                add(letter, (phone,))
        else:
            for phone in CONSONANT_1TO1[letter]:
                add(letter, (phone,))
    for ch in SILENT_ONLY:
        add(ch, ())
    for letter, outs in ONE_TO_TWO.items():
        for out in outs:
            add(letter, out)
    for grapheme, phones in CONSONANT_DIGRAPHS.items():
        for phone in phones:
            add(grapheme, (phone,))
    for grapheme in VOWEL_DIGRAPHS:
        for phone in VOWEL_PHONES + (["j"] if grapheme == "ye" else []):
            add(grapheme, (phone,))
    for grapheme in R_COLORED_DIGRAPHS:
        add(grapheme, ("ɚ",))
    for letter in "bcdfgklmnprstvz":
        for phone in CONSONANT_1TO1[letter]:
            add(letter * 2, (phone,))
    for grapheme, phones in TRIGRAPHS.items():
        for phone in phones:
            add(grapheme, (phone,))
    return inv


INVENTORY = build_inventory()
NEG_INF = float("-inf")


def _silent_forbidden(letters: str, idx: int) -> bool:
    ch = letters[idx]
    if ch in VOWEL_LETTERS or ch in SILENT_ONLY:
        return False
    return (idx > 0 and letters[idx - 1] == ch) or (idx + 1 < len(letters) and letters[idx + 1] == ch)


def _edges(letters: str, phones: tuple[str, ...], scores: dict) -> list[list[tuple[int, int, float, tuple]]]:
    """edges[i] = list of (letter_len, phone_len, score, key) usable at letter i."""
    out: list[list[tuple[int, int, float, tuple]]] = []
    for i in range(len(letters)):
        cands = []
        for glen in (1, 2, 3):
            grapheme = letters[i : i + glen]
            if len(grapheme) < glen:
                break
            outs = INVENTORY.get(grapheme)
            if not outs:
                continue
            for ph in outs:
                if glen == 1 and not ph and _silent_forbidden(letters, i):
                    continue
                key = (grapheme, ph)
                score = scores.get(key)
                if score is None:
                    continue
                cands.append((glen, len(ph), score, key))
        out.append(cands)
    return out


def _viterbi(letters: str, phones: tuple[str, ...], scores: dict):
    n_l, n_p = len(letters), len(phones)
    edges = _edges(letters, phones, scores)

    def ok(i: int, j: int, glen: int, plen: int, key: tuple) -> bool:
        return j + plen <= n_p and phones[j : j + plen] == key[1]

    fwd = [[NEG_INF] * (n_p + 1) for _ in range(n_l + 1)]
    back: list[list[tuple | None]] = [[None] * (n_p + 1) for _ in range(n_l + 1)]
    fwd[0][0] = 0.0
    for i in range(n_l):
        row = fwd[i]
        for j in range(n_p + 1):
            base = row[j]
            if base == NEG_INF:
                continue
            for glen, plen, score, key in edges[i]:
                if not ok(i, j, glen, plen, key):
                    continue
                cand = base + score
                ti, tj = i + glen, j + plen
                if cand > fwd[ti][tj]:
                    fwd[ti][tj] = cand
                    back[ti][tj] = (i, j, glen, plen, key)
    if fwd[n_l][n_p] == NEG_INF:
        return None

    bwd = [[NEG_INF] * (n_p + 1) for _ in range(n_l + 1)]
    bwd[n_l][n_p] = 0.0
    for i in range(n_l - 1, -1, -1):
        for j in range(n_p, -1, -1):
            best = NEG_INF
            for glen, plen, score, key in edges[i]:
                if not ok(i, j, glen, plen, key):
                    continue
                cand = bwd[i + glen][j + plen]
                if cand == NEG_INF:
                    continue
                cand += score
                if cand > best:
                    best = cand
            bwd[i][j] = best

    path = []
    i, j = n_l, n_p
    while (i, j) != (0, 0):
        step = back[i][j]
        path.append(step)
        i, j = step[0], step[1]
    path.reverse()
    return fwd[n_l][n_p], path, fwd, bwd, edges


def _low_confidence_positions(letters: str, phones: tuple[str, ...], best: float, path, fwd, bwd, edges) -> list[int]:
    """Phoneme indices whose chunk start letter is not clearly determined."""
    n_p = len(phones)
    starts: dict[int, int] = {}
    for i, j, glen, plen, key in path:
        if plen:
            starts[j] = i

    low: list[int] = []
    for j in range(1, n_p):
        if j not in starts:
            continue
        chosen = starts[j]
        # A rival is any complete path where phoneme j does not open a chunk at
        # letter `chosen`. Chunks carry at most 2 phonemes, so that means either
        # (a) j opens a chunk at another letter, or (b) j is the second phoneme of
        # a 1->2 chunk at any letter, `chosen` included. The two cases need
        # independent reachability checks: skipping (b) whenever (a) is
        # unreachable, or at l == chosen, hides real rivals (e.g. "lone" /ə n/).
        rival = NEG_INF
        for l in range(len(letters)):
            if l != chosen and fwd[l][j] != NEG_INF:
                for glen, plen, score, key in edges[l]:
                    if not plen or j + plen > n_p or phones[j : j + plen] != key[1]:
                        continue
                    tail = bwd[l + glen][j + plen]
                    if tail == NEG_INF:
                        continue
                    rival = max(rival, fwd[l][j] + score + tail)
            if fwd[l][j - 1] != NEG_INF:
                for glen, plen, score, key in edges[l]:
                    if plen != 2 or j + 1 > n_p or phones[j - 1 : j + 1] != key[1]:
                        continue
                    tail = bwd[l + glen][j + 1]
                    if tail != NEG_INF:
                        rival = max(rival, fwd[l][j - 1] + score + tail)
        if best - rival < LOW_CONFIDENCE_GAP:
            low.append(j)
    return low


def _syllable_count(phones: tuple[str, ...]) -> int:
    return sum(1 for p in phones if is_vowel(p))


def load_items() -> tuple[list[tuple[str, list[tuple[str, ...]]]], str]:
    raw = CMUDICT_PATH.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    g2p = SimpleG2P(CMUDICT_PATH)
    items = []
    for word in sorted(g2p._dict):
        if not all(ch.isascii() and (ch.isalpha() or ch in SILENT_ONLY) for ch in word):
            continue
        prons = [tuple(g2p._arpabet_to_ipa_with_stress(p)[0]) for p in g2p._dict[word]]
        items.append((word, prons))
    return items, sha


# ---- worker helpers (module-level so multiprocessing can pickle them) ----
_WORKER_SCORES: dict = {}


def _init_worker(scores: dict) -> None:
    global _WORKER_SCORES
    _WORKER_SCORES = scores


def _count_batch(batch) -> Counter:
    counts: Counter = Counter()
    for word, prons in batch:
        for phones in prons:
            if _syllable_count(phones) < 1:
                continue
            res = _viterbi(word, phones, _WORKER_SCORES)
            if res is None:
                continue
            for _i, _j, _gl, _pl, key in res[1]:
                counts[key] += 1
    return counts


def _encode_batch(batch) -> list[tuple[str, str, int, int, int]]:
    out = []
    for word, prons in batch:
        codes = []
        aligned = failed = low_n = 0
        for phones in prons:
            if _syllable_count(phones) < 2:
                codes.append(".")
                continue
            res = _viterbi(word, phones, _WORKER_SCORES)
            if res is None:
                codes.append("-")
                failed += 1
                continue
            best, path, fwd, bwd, edges = res
            chunk = "".join(CODE_FOR_SHAPE[(gl, pl)] for _i, _j, gl, pl, _k in path)
            low = _low_confidence_positions(word, phones, best, path, fwd, bwd, edges)
            if low:
                low_n += 1
                chunk += "~" + ",".join(str(j) for j in low)
            codes.append(chunk)
            aligned += 1
        out.append((word, "|".join(codes), aligned, failed, low_n))
    return out


def _scores_from_counts(counts: Counter, allowed: set) -> dict:
    total = sum(counts.get(k, 0) for k in allowed) + SMOOTHING * len(allowed)
    return {k: math.log((counts.get(k, 0) + SMOOTHING) / total) for k in allowed}


def _batches(items, size: int = 2000):
    return [items[i : i + size] for i in range(0, len(items), size)]


def build(jobs: int) -> dict:
    items, sha = load_items()
    allowed = {(g, ph) for g, outs in INVENTORY.items() for ph in outs}
    scores = {k: 0.0 for k in allowed}
    batches = _batches(items)

    def run(fn, scores_now):
        if jobs <= 1:
            _init_worker(scores_now)
            return [fn(b) for b in batches]
        with Pool(jobs, initializer=_init_worker, initargs=(scores_now,)) as pool:
            return pool.map(fn, batches)

    counts: Counter = Counter()
    for it in range(EM_ITERATIONS):
        counts = Counter()
        for part in run(_count_batch, scores):
            counts.update(part)
        scores = _scores_from_counts(counts, allowed)
        print(f"[em] iteration {it + 1}: {sum(counts.values())} chunks", file=sys.stderr)

    kept = {k for k in allowed if counts.get(k, 0) >= PRUNE_MIN_COUNT}
    counts = Counter()
    for part in run(_count_batch, {k: v for k, v in scores.items() if k in kept}):
        counts.update(part)
    kept = {k for k in kept if counts.get(k, 0) >= PRUNE_MIN_COUNT}
    scores = _scores_from_counts(counts, kept)
    print(f"[prune] kept {len(kept)} of {len(allowed)} mappings", file=sys.stderr)

    entries: dict[str, str] = {}
    aligned = failed = low_n = 0
    for part in run(_encode_batch, scores):
        for word, code, a, f, low in part:
            entries[word] = code
            aligned += a
            failed += f
            low_n += low

    return {
        "format": TABLE_FORMAT,
        "aligner_version": ALIGNER_VERSION,
        "cmudict_sha256": sha,
        "low_confidence_gap": LOW_CONFIDENCE_GAP,
        "chunk_codes": {code: list(shape) for code, shape in CHUNK_CODES.items()},
        "entry_syntax": "per word: prons joined by '|' in CMUdict order; '.' = fewer than 2 syllables (not aligned), "
        "'-' = no alignment, else chunk codes optionally followed by '~' and comma-separated low-confidence phoneme indices",
        "stats": {
            "words": len(entries),
            "aligned_prons": aligned,
            "failed_prons": failed,
            "prons_with_low_confidence_positions": low_n,
            "mappings": len(kept),
        },
        "entries": entries,
    }


def table_json(table: dict) -> str:
    return json.dumps(table, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def browser_js(table: dict) -> str:
    return "window.BROWSER_ALIGN_TABLE = " + table_json(table) + ";\n"


def check() -> int:
    problems = []
    sha = hashlib.sha256(CMUDICT_PATH.read_bytes()).hexdigest()
    if not TABLE_PATH.exists():
        problems.append(f"missing {TABLE_PATH.relative_to(ROOT)}")
    else:
        table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        if table.get("cmudict_sha256") != sha:
            problems.append("cmudict_sha256 mismatch: rebuild the table")
        if table.get("aligner_version") != ALIGNER_VERSION:
            problems.append("aligner_version mismatch: rebuild the table")
        if not BROWSER_ALIGN_PATH.exists():
            problems.append(f"missing {BROWSER_ALIGN_PATH.relative_to(ROOT)}")
        elif BROWSER_ALIGN_PATH.read_text(encoding="utf-8") != browser_js(table):
            problems.append("app/browser_align.js does not match data/syllable_align_table.json")
    for problem in problems:
        print(f"[check] {problem}", file=sys.stderr)
    if not problems:
        print("[check] alignment table is up to date")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify outputs instead of rebuilding")
    parser.add_argument("--jobs", type=int, default=0, help="worker processes (default: CPU count)")
    args = parser.parse_args()
    if args.check:
        return check()

    import os

    jobs = args.jobs or (os.cpu_count() or 1)
    table = build(jobs)
    TABLE_PATH.write_text(table_json(table), encoding="utf-8")
    BROWSER_ALIGN_PATH.write_text(browser_js(table), encoding="utf-8")
    print(json.dumps(table["stats"]))
    print(TABLE_PATH)
    print(BROWSER_ALIGN_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
