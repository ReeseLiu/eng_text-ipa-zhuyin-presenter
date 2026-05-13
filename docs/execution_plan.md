# Text IPA Zhuyin Presenter - Execution Plan

## 1) Scope (MVP)

This tool is a standalone text-to-phonetics utility.

In scope:
- Import `.txt` file content.
- Split text into sentences.
- Lookup per-word canonical IPA.
- Convert IPA to Improved Zhuyin (`zhuyin_plus`).
- Provide a simple edit mode:
  - edit sentence text
  - edit word text
  - edit IPA tokens
  - trigger dependent recomputation
- Provide presentation mode:
  - show one sentence at a time
  - show word + phonetic rows
  - left/right arrow switches previous/next sentence
- Reserve JSON export API and UI entry point.

Out of scope (explicit):
- No audio playback.
- No timeline or sentence audio slicing.

## 2) Project Folders

Local project root:
- `/home/reeseliu/text-ipa-zhuyin-presenter`

NAS mirror root:
- `/mnt/reesenas/text-ipa-zhuyin-presenter`

Local structure:
- `app/` static frontend (`index.html`, `app.js`, `styles.css`)
- `backend/` API server and text processing
- `backend/phoneme_core/` vendored/adapted core logic
- `data/` local runtime resources
- `docs/` planning and handoff
- `samples/` sample text files
- `scripts/` packaging helpers
- `tests/` unit tests

NAS structure:
- `docs/`
- `samples/`
- `exports/`
- `offline_packages/`

## 3) Borrowed Logic and Sources

Reference project:
- `/home/reeseliu/phoneme-surface-lattice`

Primary logic to borrow/adapt:
- `src/phoneme_surface_lattice/g2p.py`
- `src/phoneme_surface_lattice/text_utils.py`
- `src/phoneme_surface_lattice/display_mapping.py`
- `src/phoneme_surface_lattice/syllable_structure.py`

Data resources:
- `configs/display_mapping_table_syllable.csv`
- `configs/display_mapping_exceptions.json`
- CMUdict cache file (`~/.cache/cmudict/cmudict.dict`) copied into this project for offline use.

Important:
- Avoid hard runtime dependency on `phoneme-surface-lattice` code path in final offline bundle.
- Vendor the minimal required modules into `backend/phoneme_core/`.

## 4) Architecture

Backend:
- Python HTTP server (simple non-framework API is acceptable for MVP).
- Endpoints:
  - `POST /api/process_text`
  - `POST /api/reprocess_sentence`
  - `POST /api/reprocess_word`
  - `POST /api/display_for_ipa`
  - `POST /api/export_json` (reserved, MVP returns current payload)

Frontend:
- Single-page static UI.
- Modes:
  - edit mode
  - presentation mode
- Presentation layout should match current visual language in `phoneme-surface-lattice/web` presentation section.

## 5) Data Model (Draft)

Top-level payload:
- `schema_version`
- `source`
- `sentences[]`

Sentence item:
- `sentence_id`
- `text`
- `words[]`

Word item:
- `word`
- `word_norm`
- `g2p_source`
- `ipa[]`
- `display.ipa[]`
- `display.kk[]`
- `display.zhuyin_plus[]`
- `display.symbol_ids[]`
- `edited` (boolean)

## 6) Implementation Milestones

M1 - Core processing
- Sentence splitting utility.
- Word token parsing.
- G2P lookup path and fallback behavior.
- IPA-to-display bundle generation.

M2 - API
- Implement all MVP endpoints.
- Stable JSON response shape.
- Error format consistency.

M3 - Edit UI
- Text import and render sentence list.
- Editable sentence text and word text.
- Editable IPA tokens.
- Recompute behavior wiring.

M4 - Presentation UI
- Single-sentence focused view.
- Display switch (`IPA` / `Improved Zhuyin`).
- Left/right keyboard navigation.
- Layout parity with current project style.

M5 - Offline packaging
- Build a distributable folder with backend + frontend + data resources.
- Add README with run instructions.

M6 - Tests and verification
- Unit tests for sentence split and conversion.
- Manual checklist pass.

## 7) Validation Checklist

Functional:
- Import `.txt` succeeds.
- Sentence split deterministic and stable.
- IPA generated for common words.
- Improved Zhuyin generated from IPA.
- Editing sentence text triggers recompute.
- Editing IPA triggers display recompute.
- Presentation mode renders target sentence and supports left/right switch.

Layout:
- Presentation text and phonetic rows align similarly to existing project.
- Desktop and mobile basic readability pass.

Offline:
- Tool runs without internet when bundled resources exist.
- No audio dependencies required.

## 8) Risks and Mitigation

Risk: Missing CMUdict on target machine.
- Mitigation: bundle `data/cmudict.dict` and read locally first.

Risk: `espeak-ng` unavailable.
- Mitigation: expose clear fallback status and allow manual IPA editing.

Risk: Layout drift vs existing project presentation style.
- Mitigation: copy core presentation structure/classes and adjust minimally.

## 9) Done Definition for MVP

MVP is done when:
- Core flow (import -> split -> IPA -> zhuyin -> edit -> presentation) works end-to-end.
- No audio feature is implemented.
- Offline package can be run locally by another user with documented steps.
- JSON export endpoint placeholder exists and returns structured payload.
