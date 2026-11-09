# 音節切分建議：可套用、CMUdict 反推 MVP、優先序寫死

編輯多音節字時需要可信的拼字切點，但又不能讓自動結果默默蓋掉教師手填。我們決定做「音節切分建議」：可一鍵套用進 `manual_syllables`；MVP 只依 CMUdict 音節界線反推 grapheme 切點（二元文法／小型語言模型機率列下一階段）；匯出與展示的優先序固定為手填 `manual_syllables`（含已套用的建議）＞ 系統自動切分（含已知字表與音節數猜測）。

## Status

accepted

## Considered Options

- 只顯示建議、不可一鍵寫入：較安全，但每次都要手抄，摩擦高；否決。
- MVP 就上 bigram／小型 LM：可能提高候選品質，但缺語料、評估與維護成本；延後。
- 建議可自動覆寫現況：省步驟，但易踩掉教師修正；否決。

## Consequences

- 前後端（`pipeline.py`／`browser_pipeline.js`／`app.js`）必須共用同一優先序語意，避免 Pages 靜態模式與 server 模式不一致。
- MVP 不引入 LM 相依；之後若加機率排序，不得改變「未套用就不寫入 `manual_syllables`」與既有優先序。
- 「已套用的建議」與手填同屬 `manual_syllables`，不另開持久層級。
- **第一版驗收優先**：先驗證 grapheme–phoneme 對齊準確度（音素對字母若錯位，所有切點建議會跟著歪）；以已知字表為測試集做自動化評估。
