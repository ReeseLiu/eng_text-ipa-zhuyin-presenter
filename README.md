# text-ipa-zhuyin-presenter

Standalone text processing tool for:
- sentence splitting
- word-level IPA lookup
- IPA to Improved Zhuyin conversion
- simple edit mode and presentation mode

This project intentionally excludes audio playback in MVP.

## Run

```bash
python -m backend.server
```

Open `http://127.0.0.1:8000`.

## Browser-only Offline Mode (No Python runtime required)

You can run directly in a browser without starting any server:

1. Open `app/index.html` directly (double-click or `file://.../app/index.html`).
2. The app uses bundled browser assets:
   - `app/browser_data.js`
   - `app/browser_pipeline.js`

When data files are updated, rebuild browser assets:

```bash
python scripts/build_browser_assets.py
```

Notes:
- Browser-only mode does not use `espeak-ng` fallback.
- Unknown words (not found in CMUdict) can still be edited manually in IPA / Improved Zhuyin fields.
- Unknown words in browser mode now include a guessed syllable count, and you can override it with the `音節數` control in edit mode to keep presentation/export grouping stable.
- In static-only deployment mode (including GitHub Pages), the app does not call `/api/*`; all processing stays in browser runtime.

## Use

- Import a `.txt` file or paste text into the textarea.
- Click `處理文字`.
- Edit sentence text to recompute words, IPA, and Improved Zhuyin.
- Edit a word to recompute that word.
- Edit IPA tokens to recompute display values only.
- For words without usable syllable metadata (especially CMUdict-missing words), use `音節數` to override how manual tokens are grouped in presentation and JSON export.
- Switch between `文字 + IPA` and `文字 + 改良注音`.
- Enter presentation mode and use left/right arrow keys to change sentences.
- Use `匯出 JSON` for the draft JSON export payload.

## Syllable-Split Suggestions

In edit mode, `建議切分` previews spelling cut points for a multi-syllable word based on its current IPA (see `docs/adr/0001-*.md`, `docs/adr/0002-*.md`). Nothing is written until `套用建議` is clicked, which stores the segments in `manual_syllables`. When the aligner is unsure it reports a failure code (`oov`, `pron_mismatch`, `no_alignment`, `cut_inside_chunk`, `low_confidence`, `reconstruct`) instead of guessing.

The grapheme–phoneme chunks come from an offline, constrained aligner over CMUdict:

```bash
python scripts/build_align_table.py          # writes data/syllable_align_table.json + app/browser_align.js
python scripts/build_align_table.py --check  # verifies both match data/cmudict.dict and the aligner version
```

Rebuild after changing `data/cmudict.dict` or the aligner. The browser loads `app/browser_align.js` only on the first suggestion request.

Tests (Python + Node parity on the shared fixtures in `tests/fixtures/syllable_split_cases.json`, plus `tests/js/app_flow_test.js`, which loads `app/app.js` in a minimal fake DOM). Node must be on `PATH` (no npm packages needed); without it the JS contract tests fail rather than skip:

```bash
python3 -m unittest discover -s tests
```

CI runs the same command in `.github/workflows/tests.yml` (pushes and pull requests) and before the Pages build in `.github/workflows/pages.yml`.

### Accuracy evaluation

```bash
python3 scripts/eval_syllable_split.py             # prints a summary, writes reports/syllable_split_eval.json (gitignored)
python3 scripts/eval_syllable_split.py --no-write --text my_words.txt
```

Gold means "word → expected grapheme fragment list" for one IPA (ADR 0002), not "has a suggestion", and per ADR 0002 only a human-confirmed split is gold. The script merges three sources by (word, IPA) and labels each row:

| Source | Label | Tier |
| --- | --- | --- |
| known word table `WORD_SEGMENT_HINTS` in `backend/pipeline.py` (against the production default IPA) | `candidate` | candidate |
| `status: ok` cases in `tests/fixtures/syllable_split_cases.json` | `contract` (locks the aligner's own output) | candidate |
| `tests/fixtures/syllable_split_gold.json`, entry with `"reviewed": true` (literal `true` only) | `reviewed` | reviewed |
| `tests/fixtures/syllable_split_gold.json`, any other entry | `candidate` | candidate |

Only the reviewed tier counts toward `gold_reviewed`. Candidate and contract rows are still scored, but in their own tier, so they never inflate it. Words from `--text` files (default: the strict sample sentence and `samples/demo.txt`) are also run so uncovered words show up as `missing_gold`.

Source conflicts (same word and IPA, different splits): if exactly one distinct reviewed split exists, it wins, the pair is in the reviewed tier, and it is listed under `gold_conflicts.resolved_by_review`. Otherwise (only candidates disagree, or reviewed rows disagree) the pair is `unresolved`: its `gold` is null, its outcome is `gold_conflict`, and it is left out of every tier and rate until someone fixes a source. Source order never decides.

Each item goes through `Pipeline.suggest_syllable_split` and is counted as `exact`, `mismatch` (`segment_count_differs` / `boundary_differs`), `no_suggestion` (by failure code), `missing_gold`, `gold_conflict`, or `not_applicable` (`no_gold`, `gold_single_segment`, `gold_multi_segment`). The report gives `by_tier` (`reviewed`, `candidate`), `by_source` (overlapping when a pair has several sources), and `rates` for `reviewed`, `candidate`, and `all_gold`:

- `exact_rate_when_suggested = exact / (exact + mismatch)`
- `suggestion_rate_on_gold = (exact + mismatch) / (exact + mismatch + no_suggestion + gold_multi_segment)`

Rates are rounded to four places and are `null` when the denominator is zero (the reviewed tier today). A one-syllable `not_applicable` on a single-segment gold agrees with the gold and is left out of both rates; on a multi-segment gold it counts as a missed suggestion. `tests/test_syllable_split_eval.py` runs a fast subset plus these rules in CI.

To grow the gold set, add entries to `tests/fixtures/syllable_split_gold.json` (`id`, `word`, `segments`, optional `ipa`, `reviewed`, `note`); `segments` must join back to `word` (golds that do not are listed under `invalid_gold` and not scored). Set `reviewed: true` only after a teacher confirmed the split. Applied `manual_syllables` from real edits are the intended long-term source.

Limitations:
- No entry is teacher-reviewed yet, so the reviewed tier is empty and its rates are `null`; the candidate rates are smoke signals, not accuracy estimates.
- Several known-table entries are morpheme splits (`every|thing`, `how|ever`) rather than one segment per syllable, so they can never match exactly and show up as `segment_count_differs`.
- The contract fixtures lock the aligner's current output, so their 100% exact rate is expected and pulls the candidate rates up.
- Only the Python core is scored; JS parity is covered by the contract tests above.

## Offline Notes

The MVP bundles these runtime resources under `data/`:
- `cmudict.dict`
- `display_mapping_table_syllable.csv`
- `display_mapping_exceptions.json`

And browser bundle assets under `app/`:
- `browser_data.js`
- `browser_pipeline.js`

The backend reads bundled data first and does not download CMUdict at runtime. If a word is missing from CMUdict, it tries local `espeak-ng` as a fallback when installed; otherwise the word remains editable manually.

## GitHub Pages Deployment

This repo includes a GitHub Actions workflow (`.github/workflows/pages.yml`) for static-only deployment.

What it does:
- Rebuilds browser bundle data (`python scripts/build_browser_assets.py`)
- Builds a minimal publish directory (`python scripts/build_pages_dist.py`)
- Deploys only `dist-pages/` to GitHub Pages

`dist-pages/` only includes:
- `index.html`
- `app/index.html`
- `app/app.js`
- `app/browser_pipeline.js`
- `app/browser_data.js`
- `app/browser_align.js`
- `app/styles.css`

Security notes for Pages:
- `app/index.html` includes a CSP to restrict resource loading.
- When hosted on `*.github.io`, the app automatically runs in static-only mode and will not fallback to `/api/*`.

Offline verification:
- Disconnect network access.
- Run `python -m backend.server`.
- Open `http://127.0.0.1:8000` and process `samples/demo.txt`.
- Confirm IPA and Improved Zhuyin are generated without referencing any external local project path.

Planning docs:
- `docs/execution_plan.md`
- `docs/new_session_prompt.md`
- `docs/json_schema_draft.md`
