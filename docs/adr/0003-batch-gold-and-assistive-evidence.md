# 分批金標：失敗全標、成功抽樣；輔助證據不自動成金標

全字典可跑覆蓋率，但 CMUdict 沒有 grapheme 切分答案；準確率只能靠人工金標。我們決定：佇列單位為 **(word, 目前選用的 IPA)**；無法建議者依失敗碼再依字首分批並**全數人工標**；有建議者只**抽樣**標成已審金標。評估用已審金標寫入金標檔（`reviewed: true` 須同時寫入 `reviewed_fingerprint`，綁定 word／IPA／segments 內容指紋），**不**自動寫入產品 `manual_syllables`。可選：本地模型在合法切分契約下提出候選，再交決策模型打分，僅為輔助證據。第一版先佇列＋人工；資料預留 audit 欄位。細節見 `docs/specs/batch-gold-labeling-v1.md`。

## Status

accepted（2026-10-31；Claude＋Codex 三審 PASS_WITH_NITS，剩餘 nits 已補進 spec；依「通過後才實作」順序，此後開始實作 v1）

## Relation to ADR 0002（取代／保留）

**取代（僅評估／金標管道）**
- ADR 0002「人工判定後寫入 `manual_syllables` 才視為金標」→ 改為：評估用**已審金標**寫入金標檔即可；寫入 `manual_syllables` 仍是產品套用／手填路徑，二者分離。
- ADR 0002「金標＝詞 → grapheme 片段列表」→ 收緊為：**詞＋IPA → 片段列表**，鍵為 `(word, ipa)`；已審條目的 IPA 欄位必填，並綁定內容指紋以防沿用過期 `reviewed`。

**保留**
- 產品對齊失敗不給建議、未套用不寫入、兩層優先序、片段非空／字元邊界／拼回原詞。
- 產品線上建議／排序：若日後加機率，仍只在**對齊器**產生的合法候選內排序（ADR 0002）。

**離線人工標記例外（不改變產品套用規則）**
- 僅在離線標記／評估管線，允許本地模型提出合法切分候選供人工參考；不得因此讓產品在對齊失敗時改為「可一鍵套用模型答案」。

## Considered Options

- 成功建議也全庫人工確認：否決為預設，改抽樣並記錄抽樣層／抽樣率。
- 金標同步自動進 `manual_syllables`：延後另 ADR。
- 模型／Jev 輸出直接 `reviewed`：否決。
- 第一版就接 DGX＋Jev：改資料預留、分階段。
- 抽樣欄位只放佇列檔：否決；佇列檔可重產、會位移，抽樣紀錄須跟著金標條目保存。
- 成功抽樣依字首分層：v1 不採用，鎖定全域抽樣框，避免分層權重與小層樣本不足。

## Consequences

- **兩種 IPA 說法**：「目前選用的 IPA／發音」指佇列與對齊當下選中的那一組發音；「IPA 欄位」指金標條目存的值。候選金標可省略 IPA 欄位（eval 改用產品預設發音）；已審金標不可省略，也不得靠產品預設發音補洞來算指紋。v1 的 IPA 正規表示鎖定為 phone 字串陣列，保留 phone 順序。
- **指紋**：新增 `reviewed_fingerprint`（string|null）。對 NFC 正規化後的 `[word, ipa, segments]` 做 canonical JSON（UTF-8、鍵排序、無多餘空白、不跳脫非 ASCII），取 SHA-256 小寫 hex。設 `reviewed: true` 必須同時寫入正確指紋；`reviewed: false` 時可為 null。
- **載入降級**：`reviewed` 僅 literal true 且指紋與重算值相符才算已審；`reviewed: true` 但 IPA 欄位缺漏、指紋缺漏或不符 → 降為候選，報表計 `stale_reviewed`，不得靜默當已審。
- **撤回**：機器可自由更新 audit（不在指紋內）；改 word／ipa／segments 必須清除 `reviewed` 與指紋，或要求明確重審並重算指紋。
- 多個 reviewed 衝突 → unresolved，不進 reviewed 計分（與現有 eval 合併規則一致，須寫進驗收）。
- **合法性契約**：字元邊界、片段非空、拼接＝原詞、片段數＝該 IPA 之音節數。違反者歸 `invalid_gold`，不計分。教師認定的切分與該 IPA 音節數衝突時，改選或新增 IPA，或標為不可標記並寫 `note`；不得硬寫 reviewed。
- **佇列與排序**：佇列以 (word, IPA) 為列；排除 not_applicable；分桶內穩定依 `(word, ipa)` 字典序排序（ipa 用與指紋相同的正規表示）；`batch_id` 由失敗碼＋字首＋序號穩定重現；大批次再切塊（預設 100，可設 50–200）。字表／對齊表增減會讓 `chunk_index` 位移，屬預期；金標身分以 `(word, ipa)` 為準，不以 `batch_id` 為準。
- **全域抽樣（v1 鎖定）**：成功建議抽樣框為全域所有 `code=ok` 的佇列列（每個已評估發音各一列，涵蓋該次評估的全部 CMUdict 變體，不限產品預設）；`sample_n` 預設 30（全域共 30 列，不是每字首 30），`sample_seed` 預設 0，兩者寫入報表與抽樣紀錄。
- **抽樣欄位進金標**：`sampling_stratum`、`sampling_rate` 寫進金標條目（非抽樣列與失敗全標列為 null）；報表記錄母體大小、實際抽樣數、seed 與分母。標記時記錄 `suggestion_shown`（是否顯示建議切分），以便日後評估錨定偏誤。
- **指標分母**：母體 `suggestion_rate` 取自全字典覆蓋率（align 表／suggest 路徑），不從金標檔反推；成功抽樣層只用來估 `exact_rate_when_suggested`（必要時以 `sampling_rate` 加權）；失敗全標層只看失敗碼分布，其 suggestion_rate 必為 0，不得當作產品覆蓋率。各層須分開回報。
- 金標檔保留既有欄位：頂層 `version`、`description`；每筆 `id`、`note`（可 null）。
- audit 為物件陣列，與金標欄位分開；決策模型分數稱「模型評分／估計機率」，不預設已校準。
- 產品批次匯入手填另開 ADR；本 ADR 通過前不實作功能碼（已於 accepted 後才開始實作）。
