const state = {
  payload: null,
  sentenceIndex: 0,
  displaySystem: "ipa",
  viewMode: "edit",
  displayTable: {},
  activeEditInput: null,
  activeEditMeta: null,
};

const el = {
  txtInput: document.getElementById("txtInput"),
  textInput: document.getElementById("textInput"),
  processBtn: document.getElementById("processBtn"),
  statusLine: document.getElementById("statusLine"),
  displaySystemSelect: document.getElementById("displaySystemSelect"),
  keyboardLabel: document.getElementById("keyboardLabel"),
  phonemeKeyboard: document.getElementById("phonemeKeyboard"),
  keyboardHelp: document.getElementById("keyboardHelp"),
  sentenceSelect: document.getElementById("sentenceSelect"),
  prevSentenceBtn: document.getElementById("prevSentenceBtn"),
  nextSentenceBtn: document.getElementById("nextSentenceBtn"),
  editModeBtn: document.getElementById("editModeBtn"),
  presentationModeBtn: document.getElementById("presentationModeBtn"),
  exportJsonBtn: document.getElementById("exportJsonBtn"),
  editSection: document.getElementById("editSection"),
  sentenceEditor: document.getElementById("sentenceEditor"),
  presentationSection: document.getElementById("presentationSection"),
  presentationSentenceText: document.getElementById("presentationSentenceText"),
  presentationPhonemeLine: document.getElementById("presentationPhonemeLine"),
  presentationPrevSentenceBtn: document.getElementById("presentationPrevSentenceBtn"),
  presentationNextSentenceBtn: document.getElementById("presentationNextSentenceBtn"),
  presentationDisplaySystemSelect: document.getElementById("presentationDisplaySystemSelect"),
  presentationReturnBtn: document.getElementById("presentationReturnBtn"),
};

const DISPLAY_LABEL = {
  ipa: "IPA",
  zhuyin_plus: "改良注音",
};

const PRESENTATION_SLOT_ORDER = ["C1", "V", "C2"];

function resolveStaticOnlyMode() {
  const meta = document.querySelector("meta[name='app-static-only']");
  const raw = String(meta?.content || "").trim().toLowerCase();
  if (["on", "true", "1"].includes(raw)) {
    return true;
  }
  if (["off", "false", "0"].includes(raw)) {
    return false;
  }

  if (window.location.protocol === "file:") {
    return true;
  }

  const host = String(window.location.hostname || "").toLowerCase();
  if (host.endsWith(".github.io")) {
    return true;
  }

  return false;
}

const STATIC_ONLY_MODE = resolveStaticOnlyMode();
let browserPipeline = null;
let browserPipelineInitError = null;

function canUseServerApi() {
  return !STATIC_ONLY_MODE;
}

function offlinePipelineUnavailableMessage() {
  const diagnostics = [];
  if (typeof window.BROWSER_DATA === "undefined") {
    diagnostics.push("browser_data.js 未載入");
  }
  if (typeof window.createBrowserPipeline !== "function") {
    diagnostics.push("browser_pipeline.js 未載入");
  }
  if (browserPipelineInitError) {
    diagnostics.push(`初始化失敗：${browserPipelineInitError.message}`);
  }
  if (diagnostics.length === 0) {
    diagnostics.push("未知錯誤");
  }
  return `離線處理模組不可用（${diagnostics.join("；")}）。請確認已完整解壓縮後，再開啟 app/index.html。`;
}

function initBrowserPipeline() {
  if (typeof window.createBrowserPipeline !== "function") {
    return null;
  }
  try {
    return window.createBrowserPipeline(window.BROWSER_DATA || {});
  } catch (error) {
    browserPipelineInitError = error instanceof Error ? error : new Error(String(error || "unknown error"));
    console.error("Browser pipeline initialization failed:", browserPipelineInitError);
    return null;
  }
}

browserPipeline = initBrowserPipeline();

async function postJson(url, body) {
  if (browserPipeline) {
    try {
      if (url === "/api/process_text") {
        return browserPipeline.processText(body?.text || "", body?.source || "inline");
      }
      if (url === "/api/reprocess_sentence") {
        return { sentence: browserPipeline.processSentence(body?.text || "", body?.sentence_id || "1") };
      }
      if (url === "/api/reprocess_word") {
        return { word: browserPipeline.processWord(body?.word || "", body?.context || null) };
      }
      if (url === "/api/display_for_ipa") {
        return browserPipeline.displayForIpa(
          body?.ipa || [],
          body?.word || "",
          Array.isArray(body?.stress_levels) ? body.stress_levels : [],
        );
      }
      if (url === "/api/export_json") {
        return browserPipeline.exportJson(body?.payload && typeof body.payload === "object" ? body.payload : body || {});
      }
      throw new Error(`Unsupported route in browser mode: ${url}`);
    } catch (error) {
      browserPipelineInitError = error instanceof Error ? error : new Error(String(error || "unknown error"));
      console.error("Browser pipeline runtime failed:", browserPipelineInitError);
      if (!canUseServerApi()) {
        throw new Error(`瀏覽器離線模式錯誤：${browserPipelineInitError.message}`);
      }
      browserPipeline = null;
    }
  }

  if (!canUseServerApi()) {
    throw new Error(offlinePipelineUnavailableMessage());
  }

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.error?.message || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function setStatus(message, isError = false) {
  if (!el.statusLine) {
    return;
  }
  el.statusLine.textContent = message;
  el.statusLine.style.color = isError ? "var(--danger)" : "var(--text-muted)";
}

function keyboardHelpText() {
  return state.displaySystem === "ipa"
    ? "點選符號插入目前 IPA 編輯欄位。"
    : "點選符號插入目前改良注音編輯欄位。";
}

function bindElementEvent(target, eventName, handler) {
  if (!target || typeof target.addEventListener !== "function") {
    return false;
  }
  target.addEventListener(eventName, handler);
  return true;
}

function keyboardNoFocusText() {
  return state.displaySystem === "ipa"
    ? "請先點選一個 IPA 編輯欄位。"
    : "請先點選一個改良注音編輯欄位。";
}

function resetKeyboardHelp(isError = false, text = "") {
  if (!el.keyboardHelp) {
    return;
  }
  el.keyboardHelp.className = "";
  el.keyboardHelp.textContent = text || keyboardHelpText();
  if (isError) {
    el.keyboardHelp.classList.add("status-error");
  }
}

function sentences() {
  return Array.isArray(state.payload?.sentences) ? state.payload.sentences : [];
}

function activeSentence() {
  return sentences()[state.sentenceIndex] || null;
}

function clampSentenceIndex() {
  const count = sentences().length;
  if (count <= 0) {
    state.sentenceIndex = 0;
    return;
  }
  state.sentenceIndex = Math.max(0, Math.min(count - 1, state.sentenceIndex));
}

function escapeFilenamePart(value) {
  return String(value || "text-ipa-zhuyin").replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "") || "text-ipa-zhuyin";
}

async function processText(sourceName = "inline") {
  const text = el.textInput.value.trim();
  if (!text) {
    setStatus("請先輸入或匯入文字。", true);
    return;
  }
  setStatus("處理中...");
  try {
    state.payload = await postJson("/api/process_text", { text, source: sourceName });
    state.sentenceIndex = 0;
    renderAll();
    setStatus(`完成：${sentences().length} 句。`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadDisplayTable() {
  if (browserPipeline) {
    state.displayTable = browserPipeline.getDisplayTable() || {};
    renderKeyboard();
    return;
  }
  if (!canUseServerApi()) {
    state.displayTable = {};
    renderKeyboard();
    return;
  }
  try {
    const response = await fetch("/api/display_table", { method: "GET" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.error?.message || `Request failed: ${response.status}`);
    }
    state.displayTable = payload?.display_table && typeof payload.display_table === "object"
      ? payload.display_table
      : {};
  } catch (_error) {
    state.displayTable = {};
  }
  renderKeyboard();
}

function renderAll() {
  clampSentenceIndex();
  renderSentenceSelect();
  renderEditor();
  renderKeyboard();
  renderPresentation();
}

function keyboardEntries() {
  const rows = Object.entries(state.displayTable || {})
    .filter(([ipa]) => ipa)
    .map(([ipa, row]) => {
      const safeRow = row && typeof row === "object" ? row : {};
      const label = state.displaySystem === "zhuyin_plus"
        ? (safeRow.zhuyin_plus || safeRow.ipa || ipa)
        : (safeRow.ipa || ipa);
      const sortId = Number(safeRow.symbol_id || 0);
      return {
        ipa,
        label: String(label || ipa),
        insertToken: String(label || ipa),
        sortId,
      };
    });
  rows.sort((a, b) => {
    if (a.sortId !== b.sortId) {
      return a.sortId - b.sortId;
    }
    return a.ipa.localeCompare(b.ipa);
  });
  return rows;
}

function setActiveEditInput(input, meta) {
  state.activeEditInput = input;
  state.activeEditMeta = meta || null;
  resetKeyboardHelp();
}

function restoreActiveEditInput() {
  if (!state.activeEditMeta || !el.sentenceEditor) {
    return;
  }
  const targetSelector = `input[data-edit-input='1'][data-sentence-idx='${state.activeEditMeta.sentenceIdx}'][data-word-idx='${state.activeEditMeta.wordIdx}'][data-system='${state.activeEditMeta.system}']`;
  const target = el.sentenceEditor.querySelector(targetSelector);
  if (target) {
    state.activeEditInput = target;
  }
}

function insertTokenToActiveEditInput(insertToken) {
  const target = state.activeEditInput;
  if (!target || !document.body.contains(target)) {
    resetKeyboardHelp(true, keyboardNoFocusText());
    return;
  }

  target.focus();
  const currentValue = target.value || "";
  const start = typeof target.selectionStart === "number" ? target.selectionStart : currentValue.length;
  const end = typeof target.selectionEnd === "number" ? target.selectionEnd : currentValue.length;

  const before = currentValue.slice(0, start);
  const after = currentValue.slice(end);
  const needsLeading = before.length > 0 && !/\s$/.test(before);
  const needsTrailing = after.length > 0 && !/^\s/.test(after);
  const insertText = `${needsLeading ? " " : ""}${insertToken}${needsTrailing ? " " : ""}`;

  target.value = `${before}${insertText}${after}`;
  const cursor = before.length + insertText.length;
  if (typeof target.setSelectionRange === "function") {
    target.setSelectionRange(cursor, cursor);
  }
  target.dispatchEvent(new Event("change", { bubbles: true }));
}

function renderKeyboard() {
  if (!el.phonemeKeyboard) {
    return;
  }
  el.phonemeKeyboard.innerHTML = "";
  resetKeyboardHelp();
  const entries = keyboardEntries();
  entries.forEach((entry) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "key-chip";
    btn.textContent = entry.label;
    btn.title = `IPA: ${entry.ipa}`;
    btn.addEventListener("click", () => insertTokenToActiveEditInput(entry.insertToken));
    el.phonemeKeyboard.appendChild(btn);
  });
}

function renderSentenceSelect() {
  const items = sentences();
  el.sentenceSelect.innerHTML = "";
  if (items.length === 0) {
    const option = document.createElement("option");
    option.textContent = "尚無句子";
    option.value = "0";
    el.sentenceSelect.appendChild(option);
    return;
  }
  items.forEach((sentence, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${index + 1}. ${String(sentence.text || "").slice(0, 52)}`;
    el.sentenceSelect.appendChild(option);
  });
  el.sentenceSelect.value = String(state.sentenceIndex);
}

function renderEditor() {
  const items = sentences();
  el.sentenceEditor.innerHTML = "";
  if (items.length === 0) {
    state.activeEditInput = null;
    state.activeEditMeta = null;
    el.sentenceEditor.className = "sentence-editor empty-state";
    el.sentenceEditor.textContent = "請先匯入或貼上文字。";
    return;
  }

  el.sentenceEditor.className = "sentence-editor";
  items.forEach((sentence, sentenceIdx) => {
    el.sentenceEditor.appendChild(buildSentenceCard(sentence, sentenceIdx));
  });
  restoreActiveEditInput();
}

function buildSentenceCard(sentence, sentenceIdx) {
  const card = document.createElement("article");
  card.className = `sentence-card${sentenceIdx === state.sentenceIndex ? " active" : ""}`;

  const header = document.createElement("header");
  const title = document.createElement("h3");
  title.textContent = `句子 ${sentenceIdx + 1}`;
  const jumpBtn = document.createElement("button");
  jumpBtn.type = "button";
  jumpBtn.textContent = "選取此句";
  jumpBtn.addEventListener("click", () => {
    state.sentenceIndex = sentenceIdx;
    renderAll();
  });
  header.append(title, jumpBtn);
  card.appendChild(header);

  const sentenceText = document.createElement("textarea");
  sentenceText.className = "sentence-text-input";
  sentenceText.value = sentence.text || "";
  sentenceText.addEventListener("change", async () => {
    await reprocessSentence(sentenceIdx, sentenceText.value);
  });
  card.appendChild(sentenceText);

  const wordList = document.createElement("div");
  wordList.className = "word-list";
  (Array.isArray(sentence.words) ? sentence.words : []).forEach((word, wordIdx) => {
    wordList.appendChild(buildWordRow(sentenceIdx, wordIdx, word));
  });
  card.appendChild(wordList);
  return card;
}

function buildSyllableCountControl(sentenceIdx, wordIdx, word) {
  const manualCount = normalizePositiveInt(word?.manual_syllable_count);
  const fallbackCount = fallbackSyllableCountForWord(word);

  const wrap = document.createElement("div");
  wrap.className = "syllable-control";

  const label = document.createElement("span");
  label.className = "syllable-control-label";
  label.textContent = "音節數";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "syllable-count-input";
  input.min = "1";
  input.step = "1";
  input.inputMode = "numeric";
  if (manualCount !== null) {
    input.value = String(manualCount);
  }
  if (fallbackCount !== null) {
    input.placeholder = String(fallbackCount);
  }
  input.title = "留空可改回自動猜測音節數";
  input.addEventListener("change", () => {
    updateWordManualSyllableCount(sentenceIdx, wordIdx, input.value);
  });

  const hint = document.createElement("span");
  hint.className = "syllable-control-hint";
  if (manualCount !== null) {
    hint.textContent = `手動：${manualCount}`;
  } else if (fallbackCount !== null) {
    hint.textContent = `自動猜測：${fallbackCount}`;
  } else {
    hint.textContent = "留空使用自動";
  }

  wrap.append(label, input, hint);
  return wrap;
}

function normalizeSlotLabel(value) {
  const slot = String(value || "").toUpperCase();
  return PRESENTATION_SLOT_ORDER.includes(slot) ? slot : "V";
}

function stringifySlotTokens(value) {
  if (Array.isArray(value)) {
    return value.map((token) => String(token || "").trim()).filter((token) => token).join(" ");
  }
  if (typeof value === "string") {
    return value.trim();
  }
  return "";
}

function parseSlotText(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return [];
  }
  return raw.split(/[\s,]+/).filter((part) => part);
}

function firstNonEmpty(arr) {
  if (!Array.isArray(arr)) {
    return "";
  }
  for (const item of arr) {
    const text = String(item || "").trim();
    if (text) {
      return text;
    }
  }
  return "";
}

const WORD_SEGMENT_HINTS = {
  sometimes: ["some", "times"],
  someone: ["some", "one"],
  somebody: ["some", "body"],
  something: ["some", "thing"],
  somewhere: ["some", "where"],
  everyone: ["every", "one"],
  everybody: ["every", "body"],
  everything: ["every", "thing"],
  however: ["how", "ever"],
  whatever: ["what", "ever"],
  whenever: ["when", "ever"],
  wherever: ["where", "ever"],
  headquarters: ["head", "quar", "ters"],
  measurement: ["mea", "sure", "ment"],
  membership: ["mem", "ber", "ship"],
  temperature: ["tem", "pera", "ture"],
  shareholder: ["share", "hol", "der"],
  convention: ["con", "ven", "tion"],
  independence: ["in", "de", "pen", "dence"],
  theoretical: ["the", "o", "re", "ti", "cal"],
  concentration: ["con", "cen", "tra", "tion"],
  accommodation: ["a", "cco", "mmo", "da", "tion"],
  communication: ["co", "mmu", "ni", "ca", "tion"],
  revolutionary: ["re", "vo", "lu", "tio", "na", "ry"],
};

function splitWordWithHints(wordText, syllableCount) {
  const trimmed = String(wordText || "").trim();
  if (!trimmed) {
    return [];
  }

  const matched = trimmed.match(/^([A-Za-z']+)([.,!?;:…]*)$/);
  if (!matched) {
    return [trimmed];
  }

  const [, coreWord, punct] = matched;
  const normalized = coreWord.toLowerCase();
  const hinted = WORD_SEGMENT_HINTS[normalized];
  if (!Array.isArray(hinted) || hinted.length === 0) {
    return [trimmed];
  }

  const built = hinted.map((part, idx) => {
    if (idx === hinted.length - 1) {
      return `${part}${punct || ""}`;
    }
    return part;
  });

  if (Number.isInteger(syllableCount) && syllableCount > 0 && built.length !== syllableCount) {
    return [trimmed];
  }

  return built;
}

function phoneticRowsFromTokensAndDetails(word) {
  const zhuyinTokens = displayTokensRawForSystem(word, "zhuyin_plus");
  const details = Array.isArray(word?.token_details) ? word.token_details : [];

  if (zhuyinTokens.length === 0) {
    return [];
  }

  if (details.length === zhuyinTokens.length && details.length > 0) {
    const bySyllable = new Map();
    zhuyinTokens.forEach((tokenRaw, idx) => {
      const token = String(tokenRaw || "").trim();
      if (!token) {
        return;
      }
      const detail = details[idx] && typeof details[idx] === "object" ? details[idx] : {};
      const slot = normalizeSlotLabel(detail.syllable_slot);
      const rawSyllable = Number(detail.syllable_index);
      const syllableIndex = Number.isFinite(rawSyllable) ? Math.max(0, Math.trunc(rawSyllable)) : 0;
      if (!bySyllable.has(syllableIndex)) {
        bySyllable.set(syllableIndex, { C1: [], V: [], C2: [] });
      }
      bySyllable.get(syllableIndex)[slot].push(token);
    });

    const indices = Array.from(bySyllable.keys()).sort((a, b) => a - b);
    return indices
      .map((index) => bySyllable.get(index))
      .filter((slots) => firstNonEmpty(slots?.C1) || firstNonEmpty(slots?.V) || firstNonEmpty(slots?.C2));
  }

  const fallbackSyllableCount = fallbackSyllableCountForWord(word);
  const grouped = groupTokensBySyllable(zhuyinTokens, fallbackSyllableCount);
  return grouped.map((group) => ({
    C1: [],
    V: group,
    C2: [],
  }));
}

function normalizeManualSyllables(rawRows, wordText = "") {
  const sourceRows = Array.isArray(rawRows) ? rawRows : [];
  const rows = sourceRows
    .filter((row) => row && typeof row === "object")
    .map((row) => {
      const slotsRaw = row.slots && typeof row.slots === "object" ? row.slots : {};
      const slots = {
        C1: parseSlotText(slotsRaw.C1),
        V: parseSlotText(slotsRaw.V),
        C2: parseSlotText(slotsRaw.C2),
      };
      return {
        text: String(row.text || "").trim(),
        slots,
      };
    })
    .filter((row) => row.text || row.slots.C1.length > 0 || row.slots.V.length > 0 || row.slots.C2.length > 0);

  if (rows.length > 0 && !rows.some((row) => row.text)) {
    rows[0].text = String(wordText || "").trim();
  }

  return rows;
}

function buildAutoManualSyllables(word) {
  const rows = phoneticRowsFromTokensAndDetails(word);
  if (rows.length === 0) {
    return [];
  }

  const wordText = String(word?.word || "").trim();
  const splitHint = splitWordWithHints(wordText, rows.length);

  return rows.map((slots, idx) => {
    const hinted = splitHint[idx] || "";
    return {
      text: idx === 0
        ? (hinted || (splitHint.length > 0 ? "" : wordText))
        : hinted,
      slots: {
        C1: [...(Array.isArray(slots.C1) ? slots.C1 : [])],
        V: [...(Array.isArray(slots.V) ? slots.V : [])],
        C2: [...(Array.isArray(slots.C2) ? slots.C2 : [])],
      },
    };
  });
}

function resolveManualSyllables(word) {
  const normalized = normalizeManualSyllables(word?.manual_syllables, String(word?.word || ""));
  if (normalized.length > 0) {
    return normalized;
  }
  return buildAutoManualSyllables(word);
}

function shouldShowManualSyllableEditor(word) {
  const manual = normalizeManualSyllables(word?.manual_syllables, String(word?.word || ""));
  if (manual.length > 0) {
    return true;
  }
  const source = String(word?.g2p_source || "");
  return source === "missing" || hasUsableTokenDetails(word);
}

function saveWordManualSyllables(sentenceIdx, wordIdx, rows, options = {}) {
  const sentence = sentences()[sentenceIdx];
  const word = sentence?.words?.[wordIdx];
  if (!word) {
    return;
  }

  const normalizedRows = normalizeManualSyllables(rows, String(word.word || ""));
  const nextWord = {
    ...word,
    edited: true,
  };

  if (normalizedRows.length > 0) {
    nextWord.manual_syllables = normalizedRows;
    setStatus(options.message || `${word.word || "word"} 音節表已更新。`);
  } else {
    delete nextWord.manual_syllables;
    setStatus(options.message || `${word.word || "word"} 已改回自動音節表。`);
  }

  state.payload.sentences[sentenceIdx].words[wordIdx] = nextWord;
  state.sentenceIndex = sentenceIdx;
  renderAll();
}

function buildManualSyllableEditor(sentenceIdx, wordIdx, word) {
  const rows = resolveManualSyllables(word);

  const wrapper = document.createElement("div");
  wrapper.className = "manual-syllable-editor";

  const header = document.createElement("div");
  header.className = "manual-syllable-header";
  const title = document.createElement("p");
  title.className = "field-label";
  title.textContent = "拼字音節 / C1VC2";

  const controls = document.createElement("div");
  controls.className = "manual-syllable-actions";

  const autofillBtn = document.createElement("button");
  autofillBtn.type = "button";
  autofillBtn.className = "mini-action";
  autofillBtn.textContent = "自動帶入";
  autofillBtn.addEventListener("click", () => {
    const nextRows = buildAutoManualSyllables(word);
    if (nextRows.length === 0) {
      setStatus(`${word.word || "word"} 沒有可帶入的音節資料。`, true);
      return;
    }
    saveWordManualSyllables(sentenceIdx, wordIdx, nextRows, {
      message: `${word.word || "word"} 已自動帶入音節表。`,
    });
  });

  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "mini-action";
  resetBtn.textContent = "清除手動";
  resetBtn.addEventListener("click", () => {
    saveWordManualSyllables(sentenceIdx, wordIdx, [], {
      message: `${word.word || "word"} 已清除手動音節表。`,
    });
  });

  controls.append(autofillBtn, resetBtn);
  header.append(title, controls);
  wrapper.appendChild(header);

  const table = document.createElement("table");
  table.className = "manual-syllable-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["拼字音節", "C1", "V", "C2"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const inputRefs = [];

  rows.forEach((row, idx) => {
    const tr = document.createElement("tr");
    const cells = [
      row.text || "",
      stringifySlotTokens(row.slots?.C1),
      stringifySlotTokens(row.slots?.V),
      stringifySlotTokens(row.slots?.C2),
    ];
    cells.forEach((value) => {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.type = "text";
      input.className = "manual-syllable-input";
      input.value = value;
      input.placeholder = idx === 0 ? "可留空" : "可留空";
      inputRefs.push(input);
      td.appendChild(input);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  wrapper.appendChild(table);

  const footer = document.createElement("div");
  footer.className = "manual-syllable-footer";

  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "mini-action";
  addBtn.textContent = "+ 音節";
  addBtn.addEventListener("click", () => {
    const nextRows = rows.concat([{ text: "", slots: { C1: [], V: [], C2: [] } }]);
    saveWordManualSyllables(sentenceIdx, wordIdx, nextRows, {
      message: `${word.word || "word"} 已新增音節列。`,
    });
  });

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "mini-action primary";
  saveBtn.textContent = "套用音節表";
  saveBtn.addEventListener("click", () => {
    const nextRows = [];
    const trNodes = Array.from(tbody.querySelectorAll("tr"));
    trNodes.forEach((tr) => {
      const inputs = Array.from(tr.querySelectorAll("input"));
      nextRows.push({
        text: String(inputs[0]?.value || "").trim(),
        slots: {
          C1: parseSlotText(inputs[1]?.value),
          V: parseSlotText(inputs[2]?.value),
          C2: parseSlotText(inputs[3]?.value),
        },
      });
    });
    saveWordManualSyllables(sentenceIdx, wordIdx, nextRows, {
      message: `${word.word || "word"} 已套用音節表。`,
    });
  });

  footer.append(addBtn, saveBtn);
  wrapper.appendChild(footer);

  return wrapper;
}

function buildWordRow(sentenceIdx, wordIdx, word) {
  const row = document.createElement("div");
  row.className = "word-row";

  const wordCell = document.createElement("div");
  const wordLabel = document.createElement("p");
  wordLabel.className = "field-label";
  wordLabel.textContent = "Word";
  const wordInput = document.createElement("input");
  wordInput.type = "text";
  wordInput.value = word.word || "";
  wordInput.addEventListener("change", async () => {
    await reprocessWord(sentenceIdx, wordIdx, wordInput.value);
  });
  const source = document.createElement("span");
  source.className = "source-tag";
  source.textContent = word.g2p_source || "manual";

  const metaRow = document.createElement("div");
  metaRow.className = "word-meta-row";
  metaRow.appendChild(source);
  if (shouldShowSyllableControl(word)) {
    metaRow.appendChild(buildSyllableCountControl(sentenceIdx, wordIdx, word));
  }

  wordCell.append(wordLabel, wordInput, metaRow);
  if (shouldShowManualSyllableEditor(word)) {
    wordCell.appendChild(buildManualSyllableEditor(sentenceIdx, wordIdx, word));
  }

  const ipaCell = document.createElement("div");
  const editLabel = document.createElement("p");
  editLabel.className = "field-label";
  editLabel.textContent = state.displaySystem === "ipa" ? "IPA tokens" : "改良注音 tokens";
  const editInput = document.createElement("input");
  editInput.type = "text";
  editInput.className = "ipa-input editable-token-input";
  editInput.dataset.editInput = "1";
  editInput.dataset.sentenceIdx = String(sentenceIdx);
  editInput.dataset.wordIdx = String(wordIdx);
  editInput.dataset.system = state.displaySystem;
  editInput.value = editableTokens(word).join(" ");

  const isActiveInput = state.activeEditMeta
    && Number(state.activeEditMeta.sentenceIdx) === sentenceIdx
    && Number(state.activeEditMeta.wordIdx) === wordIdx
    && String(state.activeEditMeta.system || "") === state.displaySystem;
  if (isActiveInput) {
    editInput.classList.add("active");
  }

  editInput.addEventListener("focus", () => {
    setActiveEditInput(editInput, { sentenceIdx, wordIdx, system: state.displaySystem });
    editInput.classList.add("active");
  });
  editInput.addEventListener("click", () => {
    setActiveEditInput(editInput, { sentenceIdx, wordIdx, system: state.displaySystem });
    editInput.classList.add("active");
  });
  editInput.addEventListener("blur", () => {
    editInput.classList.remove("active");
  });
  editInput.addEventListener("change", async () => {
    if (state.displaySystem === "ipa") {
      await updateWordIpa(sentenceIdx, wordIdx, editInput.value);
      return;
    }
    await updateWordDisplayTokens(sentenceIdx, wordIdx, editInput.value, "zhuyin_plus");
  });
  ipaCell.append(editLabel, editInput);

  const displayCell = document.createElement("div");
  const displayLabel = document.createElement("p");
  displayLabel.className = "field-label";
  displayLabel.textContent = state.displaySystem === "ipa" ? "改良注音預覽" : "IPA 參考";
  const preview = document.createElement("div");
  preview.className = "display-preview";
  const previewSystem = state.displaySystem === "ipa" ? "zhuyin_plus" : "ipa";
  preview.textContent = displayTokensForSystem(word, previewSystem).join(" ") || "-";
  displayCell.append(displayLabel, preview);

  row.append(wordCell, ipaCell, displayCell);
  return row;
}

function displayTokensRawForSystem(word, system) {
  const display = word?.display && typeof word.display === "object" ? word.display : {};
  const candidate = display[system];
  if (Array.isArray(candidate)) {
    return candidate.map((token) => String(token || ""));
  }
  if (system === "ipa") {
    return Array.isArray(word?.ipa) ? word.ipa.map((token) => String(token || "")) : [];
  }
  return [];
}

function displayTokensRaw(word) {
  return displayTokensRawForSystem(word, state.displaySystem);
}

function displayTokensForSystem(word, system) {
  return displayTokensRawForSystem(word, system).map((token) => token.trim()).filter((token) => token);
}

function displayTokens(word) {
  return displayTokensForSystem(word, state.displaySystem);
}

function editableTokens(word) {
  if (state.displaySystem === "ipa") {
    return displayTokensForSystem(word, "ipa");
  }
  return displayTokensForSystem(word, "zhuyin_plus");
}

function normalizeEditableTokens(text) {
  const raw = String(text || "").trim();
  if (!raw) {
    return [];
  }
  return raw.split(/\s+/).filter((token) => token);
}

function normalizePositiveInt(value) {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) {
    return value;
  }
  if (typeof value === "string" && /^\d+$/.test(value.trim())) {
    const parsed = Number(value.trim());
    return parsed > 0 ? parsed : null;
  }
  return null;
}

function guessEnglishSyllableCount(wordText) {
  let text = String(wordText || "").toLowerCase().replaceAll("’", "'");
  text = text.replace(/(?:'s|s')$/g, "");
  text = text.replace(/[^a-z]/g, "");
  if (!text) {
    return 1;
  }
  if (text.length <= 3) {
    return 1;
  }

  let count = (text.match(/[aeiouy]+/g) || []).length;
  if (/e$/.test(text) && !/[^aeiouy]le$/.test(text)) {
    count -= 1;
  }
  return Math.max(1, count);
}

function fallbackSyllableCountForWord(word) {
  const manual = normalizePositiveInt(word?.manual_syllable_count);
  if (manual !== null) {
    return manual;
  }

  const guessed = normalizePositiveInt(word?.syllable_count_guess);
  if (guessed !== null) {
    return guessed;
  }

  const ipaTokens = Array.isArray(word?.ipa)
    ? word.ipa.map((token) => String(token || "").trim()).filter((token) => token)
    : [];
  const source = String(word?.g2p_source || "");
  if (source === "missing" || ipaTokens.length === 0) {
    return guessEnglishSyllableCount(String(word?.word || ""));
  }

  return null;
}

function hasUsableTokenDetails(word) {
  const details = Array.isArray(word?.token_details) ? word.token_details : [];
  const ipaTokens = Array.isArray(word?.ipa)
    ? word.ipa.map((token) => String(token || "").trim()).filter((token) => token)
    : [];
  return details.length > 0 && details.length === ipaTokens.length;
}

function shouldShowSyllableControl(word) {
  if (normalizePositiveInt(word?.manual_syllable_count) !== null) {
    return true;
  }
  if (String(word?.g2p_source || "") === "missing") {
    return true;
  }
  return !hasUsableTokenDetails(word);
}

function groupTokensBySyllable(tokens, syllableCount) {
  const safeTokens = Array.isArray(tokens)
    ? tokens.map((token) => String(token || "").trim()).filter((token) => token)
    : [];
  if (safeTokens.length === 0) {
    return [];
  }
  if (!Number.isInteger(syllableCount) || syllableCount <= 0) {
    return safeTokens.map((token) => [token]);
  }

  const target = Math.max(1, Math.min(syllableCount, safeTokens.length));
  const base = Math.floor(safeTokens.length / target);
  const remainder = safeTokens.length % target;
  const groups = [];
  let cursor = 0;

  for (let idx = 0; idx < target; idx += 1) {
    const size = base + (idx < remainder ? 1 : 0);
    if (size <= 0) {
      continue;
    }
    groups.push(safeTokens.slice(cursor, cursor + size));
    cursor += size;
  }

  return groups;
}

function updateWordManualSyllableCount(sentenceIdx, wordIdx, rawValue) {
  const sentence = sentences()[sentenceIdx];
  const word = sentence?.words?.[wordIdx];
  if (!word) {
    return;
  }

  const text = String(rawValue ?? "").trim();
  const parsed = normalizePositiveInt(text);
  if (text && parsed === null) {
    setStatus("音節數需為正整數。", true);
    renderAll();
    return;
  }

  const nextWord = {
    ...word,
    edited: true,
  };
  if (parsed === null) {
    delete nextWord.manual_syllable_count;
    setStatus(`${word.word || "word"} 已改回自動音節猜測。`);
  } else {
    nextWord.manual_syllable_count = parsed;
    setStatus(`${word.word || "word"} 音節數已設為 ${parsed}。`);
  }

  state.payload.sentences[sentenceIdx].words[wordIdx] = nextWord;
  state.sentenceIndex = sentenceIdx;
  renderAll();
}

async function reprocessSentence(sentenceIdx, text) {
  const sentence = sentences()[sentenceIdx];
  if (!sentence) {
    return;
  }
  setStatus(`重算句子 ${sentenceIdx + 1}...`);
  try {
    const result = await postJson("/api/reprocess_sentence", {
      sentence_id: sentence.sentence_id || String(sentenceIdx + 1),
      text,
    });
    state.payload.sentences[sentenceIdx] = result.sentence;
    state.sentenceIndex = sentenceIdx;
    renderAll();
    setStatus(`句子 ${sentenceIdx + 1} 已重算。`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function reprocessWord(sentenceIdx, wordIdx, wordText) {
  const sentence = sentences()[sentenceIdx];
  if (!sentence) {
    return;
  }
  const contextTokens = (sentence.words || []).map((word, idx) => (idx === wordIdx ? wordText : word.word));
  setStatus(`重算單字 ${wordText}...`);
  try {
    const result = await postJson("/api/reprocess_word", {
      word: wordText,
      context: { tokens: contextTokens, index: wordIdx },
    });
    const nextWord = { ...result.word, word_id: String(wordIdx + 1), edited: true };
    state.payload.sentences[sentenceIdx].words[wordIdx] = nextWord;
    state.sentenceIndex = sentenceIdx;
    renderAll();
    setStatus(`單字 ${wordText} 已重算。`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function updateWordIpa(sentenceIdx, wordIdx, ipaText) {
  const sentence = sentences()[sentenceIdx];
  const word = sentence?.words?.[wordIdx];
  if (!word) {
    return;
  }
  setStatus(`轉換 ${word.word || "word"} 的顯示...`);
  try {
    const tokens = ipaText.trim() ? ipaText.trim().split(/\s+/) : [];
    const result = await postJson("/api/display_for_ipa", { ipa: tokens, word: word.word });
    state.payload.sentences[sentenceIdx].words[wordIdx] = {
      ...word,
      ipa: result.ipa,
      display: result.display,
      token_details: result.token_details,
      g2p_source: "manual_ipa",
      edited: true,
      display_edited: false,
    };
    state.sentenceIndex = sentenceIdx;
    renderAll();
    setStatus(`${word.word || "word"} 已更新 IPA 顯示。`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function normalizeOverrideLength(tokens, targetLen) {
  const normalized = Array.isArray(tokens) ? tokens.map((token) => String(token || "")) : [];
  if (!Number.isFinite(targetLen) || targetLen <= 0) {
    return normalized;
  }
  if (normalized.length < targetLen) {
    normalized.push(...new Array(targetLen - normalized.length).fill(""));
  }
  if (normalized.length > targetLen) {
    return normalized.slice(0, targetLen);
  }
  return normalized;
}

async function updateWordDisplayTokens(sentenceIdx, wordIdx, displayText, system) {
  const sentence = sentences()[sentenceIdx];
  const word = sentence?.words?.[wordIdx];
  if (!word) {
    return;
  }

  const editable = normalizeEditableTokens(displayText);
  const baseLen = Array.isArray(word.ipa) ? word.ipa.length : 0;
  const normalized = normalizeOverrideLength(editable, baseLen);
  const nextDisplay = {
    ...(word.display && typeof word.display === "object" ? word.display : {}),
    [system]: normalized,
  };

  state.payload.sentences[sentenceIdx].words[wordIdx] = {
    ...word,
    display: nextDisplay,
    edited: true,
    display_edited: true,
  };
  state.sentenceIndex = sentenceIdx;
  renderAll();
  setStatus(`${word.word || "word"} 已更新${DISPLAY_LABEL[system] || system}。`);
}

function setDisplaySystem(system) {
  state.displaySystem = system === "zhuyin_plus" ? "zhuyin_plus" : "ipa";
  el.displaySystemSelect.value = state.displaySystem;
  el.presentationDisplaySystemSelect.value = state.displaySystem;
  state.activeEditInput = null;
  state.activeEditMeta = null;
  if (el.keyboardLabel) {
    el.keyboardLabel.textContent = state.displaySystem === "ipa" ? "音標小鍵盤" : "注音小鍵盤";
  }
  renderEditor();
  renderKeyboard();
  renderPresentation();
}

function jumpToSentence(delta) {
  const count = sentences().length;
  if (count <= 0) {
    return;
  }
  state.sentenceIndex = Math.max(0, Math.min(count - 1, state.sentenceIndex + delta));
  renderAll();
}

function setViewMode(mode) {
  state.viewMode = mode === "presentation" ? "presentation" : "edit";
  document.body.classList.toggle("presentation-mode", state.viewMode === "presentation");
  document.body.classList.toggle("edit-mode", state.viewMode !== "presentation");
  el.presentationSection.hidden = state.viewMode !== "presentation";
  el.editSection.hidden = state.viewMode === "presentation";
  renderPresentation();
}

function getPresentationTokensAndDetails(word) {
  const rawTokens = displayTokensRaw(word);
  const tokenDetails = Array.isArray(word?.token_details) ? word.token_details : [];
  if (rawTokens.length > 0 && rawTokens.length === tokenDetails.length) {
    return {
      tokens: rawTokens,
      tokenDetails,
    };
  }
  return {
    tokens: displayTokens(word),
    tokenDetails: [],
  };
}

function buildPresentationSyllableColumns(tokens, tokenDetails) {
  const safeTokens = Array.isArray(tokens) ? tokens.map((token) => String(token || "")) : [];
  const details = Array.isArray(tokenDetails) ? tokenDetails : [];
  if (safeTokens.length === 0 || safeTokens.length !== details.length) {
    return null;
  }

  const bySyllable = new Map();
  let invalidFound = false;
  let visibleAssignedCount = 0;

  safeTokens.forEach((token, idx) => {
    const detail = details[idx] && typeof details[idx] === "object" ? details[idx] : {};
    const slot = String(detail.syllable_slot || "");
    const rawSyllable = Number(detail.syllable_index);
    if (!PRESENTATION_SLOT_ORDER.includes(slot) || !Number.isFinite(rawSyllable)) {
      invalidFound = true;
      return;
    }

    const syllableIndex = Math.max(0, Math.trunc(rawSyllable));
    if (!bySyllable.has(syllableIndex)) {
      bySyllable.set(syllableIndex, { C1: [], V: [], C2: [] });
    }

    const shown = token.trim();
    if (!shown) {
      return;
    }

    bySyllable.get(syllableIndex)[slot].push(shown);
    visibleAssignedCount += 1;
  });

  if (invalidFound || visibleAssignedCount <= 0 || bySyllable.size === 0) {
    return null;
  }

  const indices = Array.from(bySyllable.keys()).sort((a, b) => a - b);
  return indices.map((index) => ({
    index,
    slots: bySyllable.get(index),
  }));
}

function buildPresentationFallbackColumns(tokens, syllableCount = null) {
  const grouped = groupTokensBySyllable(tokens, syllableCount);
  return grouped.map((group) => ({
    slots: {
      C1: [],
      V: group,
      C2: [],
    },
  }));
}

function normalizePresentationColumnSlots(column) {
  const safeColumn = column && typeof column === "object" ? column : {};
  const slots = {};
  PRESENTATION_SLOT_ORDER.forEach((slot) => {
    const raw = Array.isArray(safeColumn?.slots?.[slot]) ? safeColumn.slots[slot] : [];
    slots[slot] = raw.map((token) => String(token || "").trim()).filter((token) => token);
  });
  return { slots };
}

function buildPresentationWordLayout(word) {
  const manualSyllables = normalizeManualSyllables(word?.manual_syllables, String(word?.word || ""));
  if (manualSyllables.length > 0) {
    const columns = manualSyllables.map((row) => normalizePresentationColumnSlots({
      slots: {
        C1: row.slots.C1,
        V: row.slots.V,
        C2: row.slots.C2,
      },
    }));
    const wordText = manualSyllables.map((row) => String(row.text || "").trim()).filter((part) => part).join(" ")
      || String(word?.word || "").trim();
    const tokenCount = columns.reduce((count, column) => {
      return count + PRESENTATION_SLOT_ORDER.reduce((inner, slot) => inner + (column.slots[slot] || []).length, 0);
    }, 0);
    return {
      wordText,
      columns,
      tokenCount,
    };
  }

  const wordText = String(word?.word || "").trim();
  const { tokens, tokenDetails } = getPresentationTokensAndDetails(word);
  const fallbackSyllableCount = fallbackSyllableCountForWord(word);
  const bySyllable = buildPresentationSyllableColumns(tokens, tokenDetails);
  const rawColumns = Array.isArray(bySyllable) && bySyllable.length > 0
    ? bySyllable
    : buildPresentationFallbackColumns(tokens, fallbackSyllableCount);

  if (!Array.isArray(rawColumns) || rawColumns.length === 0) {
    return {
      wordText,
      columns: [],
      tokenCount: 0,
    };
  }

  const columns = rawColumns.map((column) => normalizePresentationColumnSlots(column));
  const tokenCount = columns.reduce((count, column) => {
    return count + PRESENTATION_SLOT_ORDER.reduce((inner, slot) => inner + (column.slots[slot] || []).length, 0);
  }, 0);

  return {
    wordText,
    columns,
    tokenCount,
  };
}

function estimatePresentationTokenTextWidth(tokenText, scale = 1) {
  const text = String(tokenText || "").trim();
  const safeScale = Number.isFinite(scale) ? Math.max(0.62, Math.min(1, scale)) : 1;
  if (!text) {
    return Math.max(12, Math.round(16 * safeScale));
  }

  let units = 0;
  for (const ch of text) {
    if (/\s/.test(ch)) {
      units += 0.42;
    } else if (/[\u3040-\u30ff\u4e00-\u9fff\u3100-\u312f]/.test(ch)) {
      units += 1.02;
    } else if (/[()\[\]{}]/.test(ch)) {
      units += 0.46;
    } else if (/[0-9]/.test(ch)) {
      units += 0.58;
    } else {
      units += 0.64;
    }
  }

  const unitWidth = Math.max(8, Math.round(24 * safeScale));
  return Math.max(Math.round(18 * safeScale), Math.round(units * unitWidth));
}

function estimatePresentationWordTextWidth(wordText, scale = 1) {
  const text = String(wordText || "").trim();
  const safeScale = Number.isFinite(scale) ? Math.max(0.62, Math.min(1, scale)) : 1;
  if (!text) {
    return Math.max(64, Math.round(72 * safeScale));
  }

  let unitCount = 0;
  for (const ch of text) {
    if (/\s/.test(ch)) {
      unitCount += 0.34;
    } else if (/[MWmw]/.test(ch)) {
      unitCount += 0.95;
    } else if (/[A-Z]/.test(ch)) {
      unitCount += 0.78;
    } else if (/[a-z]/.test(ch)) {
      unitCount += 0.66;
    } else if (/[0-9]/.test(ch)) {
      unitCount += 0.62;
    } else {
      unitCount += 1.02;
    }
  }

  const unitWidth = Math.max(12, Math.round(30 * safeScale));
  const estimated = Math.round(unitCount * unitWidth);
  return Math.max(Math.round(72 * safeScale), estimated);
}

function estimatePresentationColumnWidth(column, scale = 1) {
  const safeColumn = column && typeof column === "object" ? column : {};
  const slotTexts = PRESENTATION_SLOT_ORDER.map((slot) => {
    const tokens = Array.isArray(safeColumn?.slots?.[slot]) ? safeColumn.slots[slot] : [];
    if (tokens.length === 0) {
      return "-";
    }
    return tokens.map((token) => String(token || "")).join(" ");
  });
  const widest = slotTexts.reduce((maxWidth, text) => {
    return Math.max(maxWidth, estimatePresentationTokenTextWidth(text, scale));
  }, 0);
  return Math.max(52, widest + Math.round(16 * scale));
}

function splitPresentationWordLayouts(wordLayouts, maxColumnsPerLine = 14) {
  const lines = [];
  let current = [];
  let currentColumns = 0;

  wordLayouts.forEach((layout) => {
    const cols = Array.isArray(layout?.columns) ? layout.columns.length : 0;
    if (cols <= 0) {
      return;
    }
    if (current.length > 0 && currentColumns + cols > maxColumnsPerLine) {
      lines.push(current);
      current = [];
      currentColumns = 0;
    }
    current.push(layout);
    currentColumns += cols;
  });

  if (current.length > 0) {
    lines.push(current);
  }

  return lines;
}

function buildPresentationWordGroup(layout, scale = 1) {
  const columns = Array.isArray(layout?.columns) ? layout.columns : [];
  if (columns.length === 0) {
    return null;
  }

  const columnWidths = columns.map((column) => estimatePresentationColumnWidth(column, scale));
  const wordTextWidth = estimatePresentationWordTextWidth(layout.wordText, scale);
  const contentWidth = Math.max(
    wordTextWidth,
    columnWidths.reduce((sum, width) => sum + width, 0) + (Math.max(0, columns.length - 1) * Math.max(8, Math.round(14 * scale))),
  );
  const columnTemplate = columnWidths.map((width) => `minmax(${Math.max(24, Math.round(width))}px, 1fr)`).join(" ");

  const group = document.createElement("div");
  group.className = "presentation-word-group";
  group.style.setProperty("--presentation-word-syllables", String(Math.max(1, columns.length)));
  group.style.setProperty("--presentation-word-gap", `${Math.max(8, Math.round(14 * scale))}px`);
  group.style.setProperty("--presentation-word-min-width", `${Math.max(72, Math.round(contentWidth))}px`);
  group.style.setProperty("--presentation-word-columns-template", columnTemplate || "minmax(72px, 1fr)");

  const wordCell = document.createElement("span");
  wordCell.className = "presentation-word-cell presentation-word-span";
  wordCell.textContent = layout.wordText || "...";
  group.appendChild(wordCell);

  PRESENTATION_SLOT_ORDER.forEach((slot) => {
    const slotRow = document.createElement("div");
    slotRow.className = "presentation-word-slot-row";
    const slotCells = document.createElement("div");
    slotCells.className = "presentation-word-slot-cells";

    columns.forEach((column) => {
      const cell = document.createElement("span");
      cell.className = "presentation-slot-cell";
      const slotTokens = Array.isArray(column?.slots?.[slot]) ? column.slots[slot] : [];
      if (slotTokens.length === 0) {
        cell.classList.add("empty");
        cell.textContent = "-";
      } else {
        cell.textContent = slotTokens.join(" ");
      }
      slotCells.appendChild(cell);
    });

    slotRow.appendChild(slotCells);
    group.appendChild(slotRow);
  });

  return group;
}

function buildPresentationSentenceMatrix(wordLayouts, scale = 1) {
  const lines = splitPresentationWordLayouts(wordLayouts);
  if (!Array.isArray(lines) || lines.length === 0) {
    return {
      matrix: null,
      columnCount: 0,
      lineCount: 0,
    };
  }

  const matrix = document.createElement("div");
  matrix.className = "presentation-sentence-matrix";
  let maxLineColumns = 0;

  lines.forEach((lineLayouts, lineIdx) => {
    const lineNode = document.createElement("div");
    lineNode.className = "presentation-line-matrix";
    lineNode.setAttribute("data-line-index", String(lineIdx + 1));

    const groupsWrap = document.createElement("div");
    groupsWrap.className = "presentation-line-groups";
    let lineColumns = 0;

    lineLayouts.forEach((layout) => {
      lineColumns += Array.isArray(layout?.columns) ? layout.columns.length : 0;
      const groupNode = buildPresentationWordGroup(layout, scale);
      if (groupNode) {
        groupsWrap.appendChild(groupNode);
      }
    });

    maxLineColumns = Math.max(maxLineColumns, lineColumns);
    lineNode.appendChild(groupsWrap);
    matrix.appendChild(lineNode);
  });

  return {
    matrix,
    columnCount: maxLineColumns,
    lineCount: lines.length,
  };
}

function updatePresentationScrollState() {
  const row = el.presentationPhonemeLine?.querySelector(".presentation-phoneme-row");
  if (!row) {
    el.presentationPhonemeLine?.classList.remove("scrollable");
    return;
  }
  const hasOverflow = row.scrollWidth > (row.clientWidth + 2);
  el.presentationPhonemeLine.classList.toggle("scrollable", hasOverflow);
}

function renderPresentation() {
  const sentence = activeSentence();
  if (!sentence || !Array.isArray(sentence.words) || sentence.words.length === 0) {
    el.presentationSentenceText.hidden = false;
    el.presentationSentenceText.textContent = "請先匯入文字";
    el.presentationPhonemeLine.textContent = "";
    el.presentationPhonemeLine.classList.remove("scrollable");
    return;
  }

  el.presentationSentenceText.hidden = false;
  el.presentationSentenceText.textContent = sentence.text || "";
  el.presentationPhonemeLine.innerHTML = "";

  const label = document.createElement("div");
  label.className = "presentation-phoneme-label";
  label.textContent = DISPLAY_LABEL[state.displaySystem] || state.displaySystem;
  el.presentationPhonemeLine.appendChild(label);

  const row = document.createElement("div");
  row.className = "presentation-phoneme-row";
  const words = Array.isArray(sentence.words) ? sentence.words : [];
  const wordLayouts = words.map((word) => buildPresentationWordLayout(word)).filter((layout) => layout.columns.length > 0);
  const totalTokenCount = wordLayouts.reduce((sum, layout) => sum + Number(layout.tokenCount || 0), 0);
  const totalColumnCount = wordLayouts.reduce((sum, layout) => sum + Number(layout.columns.length || 0), 0);

  const scale = computePresentationScale(sentence.text || "", words.length, totalTokenCount, totalColumnCount);
  el.presentationSection.style.setProperty("--presentation-scale", scale.toFixed(3));

  const built = buildPresentationSentenceMatrix(wordLayouts, scale);
  const matrix = built.matrix || document.createElement("div");
  if (!built.matrix) {
    matrix.className = "presentation-sentence-matrix";
  }
  row.appendChild(matrix);
  el.presentationPhonemeLine.appendChild(row);
  updatePresentationScrollState();
}

function computePresentationScale(sentenceText, wordCount, tokenCount, columnCount) {
  const textLen = String(sentenceText || "").trim().length;
  let scale = 1;
  if (wordCount >= 8) scale -= 0.08;
  if (wordCount >= 12) scale -= 0.08;
  if (tokenCount >= 28) scale -= 0.08;
  if (tokenCount >= 38) scale -= 0.08;
  if (columnCount >= 14) scale -= 0.08;
  if (columnCount >= 20) scale -= 0.08;
  if (textLen >= 40) scale -= 0.06;
  if (textLen >= 60) scale -= 0.08;
  return Math.max(0.62, Math.min(1, scale));
}

async function exportJson() {
  if (!state.payload) {
    setStatus("尚無可匯出的資料。", true);
    return;
  }
  setStatus("準備 JSON 匯出...");
  try {
    const result = await postJson("/api/export_json", { payload: state.payload });
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const name = escapeFilenamePart(state.payload?.source?.name || "text-ipa-zhuyin");
    link.href = url;
    link.download = `${name}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus("JSON 匯出已產生（Jason 格式）。");
  } catch (error) {
    setStatus(error.message, true);
  }
}

function bindEvents() {
  const missingElements = [];
  if (!bindElementEvent(el.processBtn, "click", () => processText("inline"))) {
    missingElements.push("processBtn");
  }

  bindElementEvent(el.txtInput, "change", async () => {
    const file = el.txtInput.files?.[0];
    if (!file) {
      return;
    }
    const text = await file.text();
    el.textInput.value = text;
    await processText(file.name);
  });

  if (!bindElementEvent(el.displaySystemSelect, "change", () => setDisplaySystem(el.displaySystemSelect.value))) {
    missingElements.push("displaySystemSelect");
  }
  if (!bindElementEvent(el.presentationDisplaySystemSelect, "change", () => setDisplaySystem(el.presentationDisplaySystemSelect.value))) {
    missingElements.push("presentationDisplaySystemSelect");
  }

  bindElementEvent(el.sentenceSelect, "change", () => {
    state.sentenceIndex = Number(el.sentenceSelect.value) || 0;
    renderAll();
  });

  bindElementEvent(el.prevSentenceBtn, "click", () => jumpToSentence(-1));
  bindElementEvent(el.nextSentenceBtn, "click", () => jumpToSentence(1));
  bindElementEvent(el.presentationPrevSentenceBtn, "click", () => jumpToSentence(-1));
  bindElementEvent(el.presentationNextSentenceBtn, "click", () => jumpToSentence(1));
  bindElementEvent(el.editModeBtn, "click", () => setViewMode("edit"));
  bindElementEvent(el.presentationModeBtn, "click", () => setViewMode("presentation"));
  bindElementEvent(el.presentationReturnBtn, "click", () => setViewMode("edit"));
  bindElementEvent(el.exportJsonBtn, "click", exportJson);

  if (missingElements.length > 0) {
    console.error(`Missing required DOM elements: ${missingElements.join(", ")}`);
  }

  document.addEventListener("keydown", (event) => {
    if (state.viewMode !== "presentation") {
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) {
      return;
    }
    if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) {
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      jumpToSentence(1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      jumpToSentence(-1);
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setViewMode("edit");
    }
  });
}

bindEvents();
setDisplaySystem(state.displaySystem);
loadDisplayTable();
renderAll();

if (browserPipelineInitError && canUseServerApi()) {
  setStatus(`瀏覽器離線模式載入失敗，已改用伺服器 API：${browserPipelineInitError.message}`, true);
}

if (!browserPipeline && !canUseServerApi()) {
  setStatus(offlinePipelineUnavailableMessage(), true);
}
