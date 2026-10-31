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

**目前選用的 IPA（selected IPA／發音）**：
佇列與對齊當下選中的那一組發音（CMUdict 的某一個變體）；每個佇列列恰有一組。與金標條目裡存的「IPA 欄位」不同：IPA 欄位可能省略（僅限候選金標），選用的 IPA 永遠存在。
_Avoid_: 預設發音（指產品 `Pipeline.process_word` 給的那組時請明說）

**金標切分（gold syllable split）**：
評估用的「詞＋IPA → grapheme 片段列表」，鍵為 `(word, ipa)`，存於評估金標檔。分為候選金標與已審金標；違反合法性契約者歸 `invalid_gold`，不計分。產品裡寫入 `manual_syllables` 是手填／已套用建議，不自動等同已審金標（ADR 0003；產品語意仍依 ADR 0002）。
_Avoid_: 標準答案（語意過寬）、ground truth（未指明單位時）

**候選金標（candidate gold）**：
有 grapheme 片段列表、但尚未人工確認的評估用標註（例如契約案例或字表匯入），或 `reviewed: true` 但 IPA 欄位缺漏、指紋缺漏或不符而被降級的條目；IPA 欄位可省略，省略時 eval 用產品預設發音。可計分，不得計入 `gold_reviewed`。
_Avoid_: 偽金標、自動金標

**已審金標（reviewed gold）**：
人工確認後、`reviewed: true` 且 `reviewed_fingerprint` 與 `[word, ipa, segments]` 重算值相符的金標條目；IPA 欄位必填。唯有此層代表教師認可的切分監督訊號。IPA 欄位缺漏、指紋缺漏或不符者，載入時降為候選並計入 `stale_reviewed`。
_Avoid_: 已套用建議（那是產品 `manual_syllables`，未必已進評估金標檔）

**無法建議佇列（no-suggestion queue）**：
對齊器對某詞／發音回傳失敗碼而不給建議時，排入分批人工標記的待辦集合。
_Avoid_: 錯誤清單、bug list

**輔助證據（assistive evidence）**：
離線標記時，本地模型提出的合法切分候選，以及決策模型（如 Jev）對候選的**模型評分／估計機率**；供人工裁決參考，本身不是金標，也不得自動設 `reviewed`。
_Avoid_: 自動標註、模型金標、校準機率（未經校準驗證時）
