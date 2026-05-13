# New Session Prompt - text-ipa-zhuyin-presenter

請延續以下專案目標，直接開始實作，不要先做大量提問。

## 專案根目錄

- Local: `/home/reeseliu/text-ipa-zhuyin-presenter`
- NAS mirror: `/mnt/reesenas/text-ipa-zhuyin-presenter`

## 目標（MVP）

建立一個文字轉 IPA/改良注音的小工具：

1. 匯入 `.txt`。
2. 依句子拆分。
3. 逐字查詢 IPA。
4. IPA 轉換改良注音。
5. 編輯模式：
   - 可編輯句子文字、單字文字、IPA
   - 文字改動時，重新查 IPA 與注音
   - IPA 改動時，重新轉注音
6. 展示模式：
   - 一次顯示一句
   - 顯示「文字 + IPA」或「文字 + 改良注音」
   - 左右鍵切換上下句
7. 預留 JSON 匯出功能（先做 endpoint + UI 入口，schema 可先 draft）

## 明確限制

- 完全不做音檔播放功能。
- 不依賴 timeline/sentence audio。

## UI/排版要求

展示模式請盡量對齊現有專案視覺語言：

- 參考：`/home/reeseliu/phoneme-surface-lattice/web/app.js`
- 參考：`/home/reeseliu/phoneme-surface-lattice/web/styles.css`

至少保留這些設計方向：
- 大字句子顯示
- 下方按單字分組的音標/注音 row
- 句子切換體驗流暢

## 可借鑑邏輯（請優先重用）

- `g2p.py`
- `text_utils.py`
- `display_mapping.py`
- `syllable_structure.py`
- `configs/display_mapping_table_syllable.csv`
- `configs/display_mapping_exceptions.json`

來源專案：`/home/reeseliu/phoneme-surface-lattice`

## 離線能力要求

請做成可離線使用的工具版本：

- 別人拿到工具後可匯入文字，自動轉 IPA/注音。
- 優先把必要資料與核心邏輯放進本專案，避免執行時硬依賴原專案路徑。

## 建議交付順序

1. 先完成 backend text pipeline（split -> g2p -> display）。
2. 再做簡易編輯模式。
3. 再做展示模式與鍵盤切句。
4. 最後做 JSON 匯出預留與離線打包。
5. 在 `docs/` 補上 `json_schema_draft.md` 與簡短操作說明。

## 本輪結尾請回報

1. 完成項目清單。
2. 尚未完成項目。
3. 執行與驗證方式（含離線驗證）。
4. 下一步建議（最多 3 點）。
