#!/usr/bin/env python3
"""Build browser data bundle for file:// offline mode."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_DIR = ROOT / "app"


def load_display_table(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ipa = (row.get("ipa") or "").strip()
            if not ipa:
                continue
            rows[ipa] = {
                "ipa": ipa,
                "symbol_id": (row.get("symbol_id") or "").strip(),
                "kk": (row.get("kk") or "").strip(),
                "zhuyin_plus": (row.get("zhuyin_plus") or "").strip(),
                "zhuyin_plus_C1": (row.get("zhuyin_plus_C1") or "").strip(),
                "zhuyin_plus_V": (row.get("zhuyin_plus_V") or "").strip(),
                "zhuyin_plus_C2": (row.get("zhuyin_plus_C2") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }
    return rows


def build_browser_data() -> dict:
    cmudict_raw = (DATA_DIR / "cmudict.dict").read_text(encoding="latin-1")
    display_table = load_display_table(DATA_DIR / "display_mapping_table_syllable.csv")
    display_exceptions = json.loads((DATA_DIR / "display_mapping_exceptions.json").read_text(encoding="utf-8"))
    return {
        "cmudict_raw": cmudict_raw,
        "display_table": display_table,
        "display_exceptions": display_exceptions,
    }


def main() -> None:
    payload = build_browser_data()
    out_path = APP_DIR / "browser_data.js"
    out_path.write_text(
        "window.BROWSER_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(out_path)


if __name__ == "__main__":
    main()
