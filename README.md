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
