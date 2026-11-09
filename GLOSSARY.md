# 英文發音呈現（IPA → 改良注音）

把英文文字轉成 IPA 與改良注音，供編輯、逐句展示，並匯出給 intonation-tutor 使用的領域詞彙。

## Language

**改良注音（zhuyin_plus）**：
依音節位置把 IPA 轉成給華語使用者對照發音的注音式標示。
_Avoid_: 注音符號（單指華語注音本身）、KK 音標

**C1／V／C2（C1VC2）**：
一個音節內部的結構切分：節首輔音群（C1）、元音核（V）、節尾輔音群（C2）；對照與編輯都以這三欄為單位。
_Avoid_: onset／nucleus／coda（除非對照語言學文獻）、音素欄位

**音節切分（syllable split）**：
把一個英文書寫形式（grapheme 序列）切成對應多個音節的拼字片段，使每個片段能對上一個 C1VC2。
_Avoid_: 斷詞、分詞、token 切分（指 Jason 匯出的 token 單位時請明說）

**Grapheme–phoneme 對照**：
書寫片段與發音（IPA／音節結構）之間的對應關係；音節切分建議是在既有發音音節界線上反推合理的拼字切點。
_Avoid_: 對齊（alignment，易與強制字級對齊混淆）、翻譯

**manual_syllables（手填音節）**：
使用者在編輯模式為某字手填的音節切分與各音節 C1／V／C2；匯出與展示時優先於其他來源。
_Avoid_: 手動覆寫、custom syllables

**音節切分建議（syllable-split suggestion）**：
系統依規則算出、可一鍵寫入 `manual_syllables` 的候選切分；未套用前不視為手填。
_Avoid_: 自動切分（指未經過「建議→套用」的系統預設結果）、預測

**已套用的建議**：
使用者對「音節切分建議」執行一鍵套用後寫入 `manual_syllables` 的內容；套用後與手填同一優先層（皆屬 `manual_syllables`），後續再手改仍算手填。
_Avoid_: 暫存建議、預填

**系統自動切分**：
未手填、也未套用建議時，系統依已知字拆字表、CMUdict 音節結構與音節數猜測等既有邏輯產生的切分。
_Avoid_: 預設切分、fallback split

**對齊失敗（alignment failure）**：
對齊器無法在固定策略下產出合法 grapheme 切點（例如無法還原原詞、切點不在字元邊界、對不到目前選用的 IPA）；此時不給音節切分建議。
_Avoid_: 對齊錯誤（易與實作 bug 混淆）、缺字

**金標切分（gold syllable split）**：
經人工判定（手填或修正後寫入）的「詞 → grapheme 片段列表」；用作驗收與日後候選排序的監督訊號。未套用的建議不是金標。
_Avoid_: 標準答案（語意過寬）、ground truth（未指明單位時）
