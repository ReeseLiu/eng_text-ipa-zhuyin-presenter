# JSON Schema Draft

This schema is reserved for the MVP JSON export. It is intentionally stable enough for handoff but not final.

```json
{
  "schema_version": "0.1.0",
  "source": {
    "type": "text",
    "name": "inline or filename"
  },
  "sentences": [
    {
      "sentence_id": "1",
      "text": "We read the text.",
      "words": [
        {
          "word_id": "1",
          "word": "We",
          "word_norm": "we",
          "g2p_source": "cmudict",
          "ipa": ["w", "i"],
          "display": {
            "ipa": ["w", "i"],
            "kk": ["w", "i"],
            "zhuyin_plus": ["ㄨ", "ㄧ(微)"],
            "symbol_ids": ["025", "028"]
          },
          "token_details": [
            {
              "index": 0,
              "syllable_index": 0,
              "syllable_slot": "C1",
              "slot_index": 0,
              "position": "onset",
              "stress_level": null
            }
          ],
          "edited": false
        }
      ]
    }
  ],
  "export": {
    "status": "draft",
    "format": "text-ipa-zhuyin-presenter"
  }
}
```

Notes:
- No audio, timeline, clip, or playback fields are part of this MVP schema.
- `display.zhuyin_plus` is the Improved Zhuyin row used by presentation mode.
- `token_details` is included so future exports can preserve syllable-slot layout information.
- `POST /api/export_json` currently returns the current payload with draft export metadata.
