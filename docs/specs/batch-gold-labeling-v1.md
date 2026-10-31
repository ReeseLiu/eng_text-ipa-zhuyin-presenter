# Spec: 分批金標 v1（ADR 0003 accepted 2026-10-31；實作依本 spec）

## Goal
Batch-label CMUdict **(word, IPA)** rows: all no-suggestion rows; sampled successful suggestions as `reviewed` gold in an eval gold file. Never auto-write `manual_syllables`. Reserve assistive-evidence audit fields.

## Non-goals (v1)
- Auto-import gold into product `manual_syllables`
- Full-dict human review of every successful suggestion
- Required DGX / Jev runtime (schema only)
- Changing the online aligner / product apply rules

## Terms: "selected IPA" vs the `ipa` field
Two different things; this spec, ADR 0003 and GLOSSARY use them consistently:
- **Selected IPA / pronunciation (目前選用的 IPA／發音)**: the one pronunciation the queue row and the aligner were working with at that moment (one CMUdict variant). Every queue row has exactly one.
- **`ipa` field (IPA 欄位)**: the stored value in a gold entry.
  - Candidate entries (`reviewed` not literal `true`) **may omit** it; eval then uses the product default pronunciation (`Pipeline.process_word`).
  - Reviewed entries **must** carry it (see Reviewed binding). The product default must never fill the gap, neither for scoring nor for the fingerprint.

## Unit & filters
- **Row key**: `(word, ipa)` where `ipa` is the selected pronunciation in the **canonical form locked for v1: a JSON array of phone strings, phone order preserved** (the form the gold fixture already uses). No string-joined form.
- Multi-pronunciation words: one queue row per pronunciation that was evaluated.
- Exclude `not_applicable` from labeling queues.
- Gold JSON top-level keeps the existing fields: `version`, `description`, `entries` (matches eval loader expectations).

## Normalization (shared by sort key and fingerprint)
- Every string (`word`, each phone, each segment) is Unicode **NFC**-normalized. No case folding, no trimming beyond what the source already has.
- `ipa` is the canonical array above; `segments` is an array of strings in order.

## Batches
1. No-suggestion: partition by fail `code`, then by word initial (`A–Z` / `other`).
2. Within a partition, rows are sorted stably by `(word, ipa)`: lexicographic by Unicode codepoint on `word`, then element-wise on the normalized `ipa` array (Python tuple order). Then split into chunks of size `batch_size` (default **100**, configurable 50–200). Oversized partitions (observed: some buckets >1000) must chunk; do not emit a single mega-batch.
3. `batch_id` = stable string `"{code}|{initial}|{chunk_index}"` (0-based), reproducible from the same align table + suggest path + config.
   - Expected, not a bug: adding or removing words in the word table / align table shifts rows between chunks, so `chunk_index` of later chunks moves. `batch_id` is a work-queue address, not a gold identity; gold identity is `(word, ipa)`.
4. Successful suggestions (sampling, **locked for v1**):
   - **Sampling frame**: global — every queue row with `code=ok`, one row per evaluated pronunciation (= all CMUdict variants covered by that evaluation run, not only the product default).
   - `sample_n` default **30** = 30 rows drawn from that global frame (not 30 per initial).
   - `sample_seed` default **0**.
   - `sampling_stratum` = `"ok_global"`; `sampling_rate` = `sample_n_actual / frame_size`.
   - Report and sampling record store: `frame_size`, `sample_n` requested, `sample_n_actual`, `sample_seed`, and the denominators used.
   - **Sampling algorithm (locked for v1)**: uniform, without replacement. Before drawing, sort the frame by the `(word, ipa)` key above. Draw with `random.Random(sample_seed).sample(frame, min(sample_n, frame_size))` (Python's `random` module; the seed is the integer `sample_seed`). `sample_n_actual = min(sample_n, frame_size)`: when `frame_size < sample_n` every frame row is drawn. When `frame_size == 0` nothing is drawn, `sampling_rate = null` (never divide by zero) and the report records `frame_size=0`. The drawn rows are emitted in `(word, ipa)` order.
   - Sampled rows go to the queue file with `batch_id = "ok|ok_global|{chunk_index}"`, chunked by `batch_size` in `(word, ipa)` order (same shape as the fail batches, with the stratum in the initial slot). Non-sampled `ok` rows are counted in the report but not written to the queue.
5. Population counts: the report also records, over every evaluated `(word, ipa)`, the count per code (`ok`, each fail code, `not_applicable`) and the population `suggestion_rate = ok / (ok + failed)` (`not_applicable` excluded; `null` when the denominator is 0).

## Legality contract (segments)
Valid iff all hold:
1. Every segment is a non-empty string
2. Concatenation equals `word`
3. Cuts only on character boundaries (no splitting a codepoint)
4. `len(segments)` equals syllable count of the entry's IPA (project's existing syllable count for that IPA; for candidates without `ipa`, the product default IPA). An IPA with no vowel counts as 1 syllable here, since a non-empty word always has at least one segment.

Implementation scope: the eval applies these rules to every gold source it merges (curated gold file, known word table, contract fixtures), as it already did for rule 2. Strings are compared after NFC, so a split that separates a base letter from a combining mark fails rule 2/3; a lone surrogate in a segment fails rule 3. Entries whose fields have the wrong type (e.g. `segments` not a list of strings, `ipa` present but not a list of strings) are also `invalid_gold`.

**IPA phones (accepted 2026-10-31):** when `ipa` is present and is a list of strings, every phone must be free of Unicode lone surrogates (code points U+D800–U+DFFF). A phone that contains any fails as `invalid_gold` with reason `ipa_lone_surrogate` (same classification order as other legality failures: before fingerprint / `stale_reviewed`). Rationale: a lone surrogate is not a phone, and the fingerprint path must UTF-8-encode the IPA array.

Illegal candidates must not enter Jev scoring pools or be written as `reviewed` without human repair that restores legality.

**Invalid gold**: a gold entry (any tier) that violates any rule above is classified `invalid_gold` and is **not scored** (not in any rate, not counted as reviewed or candidate). Report the count and ids.

**Teacher split vs IPA syllable count**: if the teacher's intended split conflicts with the syllable count of the selected IPA, the labeler must either choose / add an IPA whose syllable count matches, or mark the row as not labelable with a `note`. It must **not** be written as `reviewed: true` as is.

**Teacher-added IPA (not from CMUdict)**: an entry whose `ipa` was added by a human (not a CMUdict variant) sets `ipa_source: "human"` (entry field, nullable; `null`/absent = taken from the queue, i.e. CMUdict). Such a pronunciation is not in the align table or the queue, so it is outside population coverage. The eval report counts these entries separately (`ipa_source_human`, with ids); the population `suggestion_rate` still comes only from the full-dictionary / align table run. `ipa_source` is not part of the fingerprint.

## Reviewed binding & revocation (Codex P1, B1)
### Fingerprint
- Field `reviewed_fingerprint`: `string | null`.
- Algorithm:
  1. Take the normalized triple as a JSON array `[word, ipa, segments]` (`ipa` = canonical phone array).
  2. Serialize as canonical JSON: UTF-8 bytes, keys sorted (relevant only if objects ever appear), no insignificant whitespace, non-ASCII not escaped. Python reference: `json.dumps(triple, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")`.
  3. `reviewed_fingerprint` = SHA-256 of those bytes, lowercase hex (64 chars).
- Test vector: `["badger",["b","æ","dʒ","ɚ"],["bad","ger"]]` → `50da880ad28212fb6900b790c70e8a5cf16d8fe865f0c5ed1d69daccd17bb38e`.

### Writing rules
- Setting `reviewed: true` must write the correct `reviewed_fingerprint` in the same write. `ipa` is **required** for reviewed entries.
- `reviewed: false` (or absent): `reviewed_fingerprint` may be `null`.
- Machines may update `audit` freely; `audit` is not part of the fingerprint.
- If `word` / `ipa` / `segments` change, the writer **must** either clear `reviewed` (→ `false`) and `reviewed_fingerprint` (→ `null`), or require an explicit re-review that recomputes the fingerprint. Stale `true` must not carry over.
- Optional provenance: `reviewer`, `reviewed_at` (ISO-8601) when setting reviewed.

### Load rules
- `reviewed: true` and fingerprint present and equal to the recomputed value → reviewed.
- `reviewed: true` but `ipa` missing, fingerprint missing, or fingerprint mismatch → **downgraded to candidate** and counted in report field `stale_reviewed` (with ids). Never silently treated as reviewed. (If the entry has no `ipa`, eval scores the candidate against the product default as for any candidate.)
- Anything other than literal `true` → candidate.
- **Classification order (each entry lands in exactly one class)**:
  1. Legality (rules above, against the entry's `ipa`, or the product default IPA when `ipa` is absent) → fails: `invalid_gold`; stop. An invalid entry is never also counted as `stale_reviewed`.
  2. Otherwise, if `reviewed is True`: check `ipa` present and fingerprint equal to the recomputed value → fails: candidate, `stale_reviewed` +1; passes: reviewed.
  3. Then merge / conflict handling below.
- Eval merge: exactly one reviewed answer for a key → use it; multiple conflicting reviewed → `unresolved` (excluded from reviewed rates).

## Artifacts
### Queue export (JSONL or JSON list)
Each row: `word`, `ipa`, `code` (`ok` or fail code), `batch_id`, `suggested_segments` (nullable), `sampling_stratum` (nullable), `sampling_rate` (nullable).

### Gold file
Field types below are **type annotations**, not literal values: e.g. `"score": "number|null"` means the JSON value is a number or `null`, never the string `"number|null"`.
```json
{
  "version": 1,
  "description": "string",
  "entries": [
    {
      "id": "string (unique)",
      "word": "string",
      "ipa": ["phone", "..."],
      "segments": ["..."],
      "reviewed": false,
      "reviewed_fingerprint": "string|null",
      "reviewer": "string|null",
      "reviewed_at": "string|null",
      "suggestion_shown": "boolean|null",
      "sampling_stratum": "string|null",
      "sampling_rate": "number|null",
      "ipa_source": "\"human\"|null",
      "note": "string|null",
      "audit": [
        {
          "segments": ["..."],
          "source": "aligner|local_model|human_draft",
          "model_id": "string|null",
          "score": "number|null",
          "abstained": false
        }
      ]
    }
  ]
}
```
- Existing fields are kept: top-level `version`, `description`; per entry `id`, `note` (nullable).
- `ipa` may be omitted only on candidates; required when `reviewed: true`.
- Only literal `reviewed: true` with a valid fingerprint enters reviewed-tier metrics.
- `sampling_stratum` / `sampling_rate` live **in gold entries** (v1 choice), copied from the queue row when the entry is created; `null` for non-sampled rows and fail-all rows. The queue file alone is not the record.
- `suggestion_shown`: whether the labeler saw a suggested split while labeling (anchoring bias). `null` = not recorded (legacy entries).
- `audit[].score` = model score / estimated probability (not claimed calibrated unless separately validated).

## Assistive evidence (optional later; offline labeling only)
- Local model: 1–3 legal candidates or abstain.
- Decision model (e.g. Jev): score **legal** candidates only; never set `reviewed`.
- Human chooses/edits → gold entry; product apply rules unchanged (aligner failure still no one-click apply of model output).

## Reporting & metric meaning
- Candidate vs reviewed tiers as today, plus `stale_reviewed` and `invalid_gold` counts.
- **Population `suggestion_rate`** comes from full-dictionary coverage (align table / suggest path over every evaluated `(word, ipa)`), **not** inferred from the gold file.
- **Success sample stratum** (`ok_global`) is used only to estimate `exact_rate_when_suggested` (weight by `sampling_rate` if strata are ever combined).
- **Fail-all strata** show the failure-code distribution and what the correct split would have been; their suggestion_rate is 0 by construction and must not be reported as product coverage.
- Report rates **by sampling_stratum** so the reviewed tier is not naively mixed (fail-all + success-sample).
- Report records: `frame_size`, `sample_n`, `sample_n_actual`, `sample_seed`, and each rate's denominator. Document denominators in eval README / report JSON.

## Queue builder & gold template (implementation notes)
- `scripts/build_batch_gold_queue.py` reads the align table, lists each word's CMUdict pronunciations (as the product converts them to IPA; duplicate IPA within one word collapses to one row), and runs `Pipeline.suggest_syllable_split` on every `(word, ipa)`. `--limit N` (first N words in sorted order) is for development only; the default is the full table, and the report records the limit.
- Initial for batching: first character of `word` upper-cased if `A–Z`, else `other`.
- Optional `--gold-template PATH` writes gold entry skeletons for the sampled rows only: `reviewed: false`, `reviewed_fingerprint: null`, `segments: []` (to be filled by the labeler; until then the entry is `invalid_gold` and never scored), `sampling_stratum` / `sampling_rate` copied from the queue, `suggestion_shown: null`, and the aligner suggestion kept in `audit` (`source: "aligner"`). It never sets `reviewed` and never touches `manual_syllables`.

## Acceptance (docs stage)
- ADR 0003 relation-to-0002, legality, binding/revocation, batch unit, audit shape, glossary updates pass Claude + Codex read-only review.

## Acceptance (implementation stage — only after docs accepted)
- Queue builder from align table / suggest path with stable `batch_id` and `(word, ipa)` sort.
- Global ok-frame sampling with defaults `sample_n=30`, `sample_seed=0`; sampling fields written into gold entries and the report.
- Eval: fingerprint binding and downgrade; conflict → unresolved; stratum reporting; `invalid_gold` excluded from scoring.
- No silent `manual_syllables` write from gold import.
- Unit tests:
  - Legality: empty segment, concatenation ≠ word, codepoint split, syllable-count mismatch → `invalid_gold`, not scored.
  - Fingerprint test vector above.
  - `reviewed: true` with hand-edited `segments` (fingerprint left as is) → loads as candidate, `stale_reviewed` +1.
  - Same for hand-edited `word`, and for hand-edited `ipa`.
  - `reviewed: true` with `ipa` omitted, or fingerprint `null`/missing → candidate, `stale_reviewed` +1.
  - Only `audit` changed → still reviewed.
  - Edit the gold file directly on disk, then reload → same results as above (no cached reviewed state).
  - Writer API: changing `word`/`ipa`/`segments` clears `reviewed` and fingerprint unless re-review recomputes it.
  - `batch_id` stability for the same inputs; documented shift when rows are added/removed.
