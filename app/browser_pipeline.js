/* eslint-disable no-continue */
(() => {
  const SCHEMA_VERSION = "0.1.0";

  const ARPABET_TO_IPA = {
    AA: "ɑ",
    AE: "æ",
    AH: "ʌ",
    AO: "ɔ",
    EH: "ɛ",
    ER: "ɚ",
    IH: "ɪ",
    IY: "i",
    UH: "ʊ",
    UW: "u",
    AW: "aʊ",
    AY: "aɪ",
    EY: "eɪ",
    OW: "oʊ",
    OY: "ɔɪ",
    B: "b",
    CH: "tʃ",
    D: "d",
    DH: "ð",
    F: "f",
    G: "ɡ",
    HH: "h",
    JH: "dʒ",
    K: "k",
    L: "l",
    M: "m",
    N: "n",
    NG: "ŋ",
    P: "p",
    R: "ɹ",
    S: "s",
    SH: "ʃ",
    T: "t",
    TH: "θ",
    V: "v",
    W: "w",
    Y: "j",
    Z: "z",
    ZH: "ʒ",
  };

  const MULTI_PHONEME_UNITS = [
    "ɑːɹ",
    "ɔːɹ",
    "aɪ",
    "aʊ",
    "eɪ",
    "oʊ",
    "ɔɪ",
    "iː",
    "uː",
    "ɑː",
    "ɔː",
    "ɜː",
    "oː",
    "ɪɹ",
    "tʃ",
    "dʒ",
    "əl",
    "ɚ",
    "ɝ",
  ];

  const READ_PRESENT_PREV_CUES = new Set([
    "will",
    "can",
    "could",
    "may",
    "might",
    "must",
    "should",
    "shall",
    "would",
    "to",
    "please",
    "lets",
    "let's",
    "do",
    "does",
    "don't",
    "doesn't",
  ]);
  const READ_PAST_PREV_CUES = new Set(["have", "has", "had", "did", "already", "just", "previously", "earlier", "before"]);
  const READ_PAST_TIME_CUES = new Set(["yesterday", "ago", "last", "earlier", "previously", "before", "tonight"]);
  const READ_PRESENT_HABITUAL_CUES = new Set([
    "often",
    "usually",
    "always",
    "daily",
    "every",
    "each",
    "sometimes",
    "rarely",
    "seldom",
    "generally",
    "typically",
    "normally",
  ]);
  const LEAD_VERB_PREV_CUES = READ_PRESENT_PREV_CUES;
  const LEAD_VERB_NEXT_CUES = new Set([
    "to",
    "the",
    "a",
    "an",
    "my",
    "your",
    "our",
    "their",
    "his",
    "her",
    "its",
    "us",
    "them",
    "me",
    "him",
    "role",
    "team",
    "way",
    "project",
    "group",
    "effort",
    "meeting",
  ]);
  const LEAD_METAL_CUES = new Set([
    "pipe",
    "paint",
    "poisoning",
    "metal",
    "ore",
    "pencil",
    "bullet",
    "bullets",
    "solder",
    "toxicity",
    "exposure",
    "battery",
    "batteries",
  ]);

  const VOWELS = new Set([
    "i",
    "ɪ",
    "eɪ",
    "ɛ",
    "æ",
    "ə",
    "ʌ",
    "ɑ",
    "ɔ",
    "ʊ",
    "u",
    "aɪ",
    "aʊ",
    "oʊ",
    "ɔɪ",
    "iː",
    "uː",
    "ɑː",
    "ɔː",
    "ɜː",
    "ɐ",
    "ɚ",
    "ɝ",
    "ɔːɹ",
    "ɑːɹ",
    "ɪɹ",
  ]);

  const LEGAL_ONSET_CLUSTERS_2 = new Set([
    "p ɹ",
    "b ɹ",
    "t ɹ",
    "d ɹ",
    "k ɹ",
    "ɡ ɹ",
    "f ɹ",
    "θ ɹ",
    "p l",
    "b l",
    "k l",
    "ɡ l",
    "f l",
    "s p",
    "s t",
    "s k",
    "s m",
    "s n",
    "s f",
    "s w",
    "s j",
    "s l",
    "s ɹ",
  ]);

  const LEGAL_ONSET_CLUSTERS_3 = new Set([
    "s p ɹ",
    "s t ɹ",
    "s k ɹ",
    "s p l",
    "s k l",
    "s k w",
    "s t j",
  ]);

  const FALLBACK_BASE_MAP = {
    "iː": "ee",
    "uː": "oo",
    "ɜː": "er",
    a: "ah",
    "ɲ": "n",
    "ʉ": "oo",
  };

  const PUNCT_STRIP_RE = /[.,!?;:…]+$/;

  function escapeRegex(text) {
    return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function normalizeText(text) {
    let normalized = String(text || "").toLowerCase().replaceAll("’", "'");
    normalized = normalized.replace(/[^a-z0-9'\s]+/g, " ");
    normalized = normalized.replace(/\s+/g, " ").trim();
    return normalized;
  }

  function normalizeWordToken(token) {
    let normalized = String(token || "").toLowerCase().replaceAll("’", "'");
    normalized = normalized.replace(/[^a-z0-9']+/g, "");
    return normalized.trim();
  }

  function parseCleanLineWords(line) {
    const lineNorm = String(line || "").replaceAll("’", "'");
    const words = [];
    const re = /[A-Za-z0-9']+(?:[.,!?;:…]+)?/g;
    const matches = lineNorm.matchAll(re);
    for (const match of matches) {
      const token = String(match[0] || "");
      const tokenBase = token.replace(PUNCT_STRIP_RE, "");
      const tokenNorm = normalizeWordToken(tokenBase);
      if (tokenNorm) {
        words.push({ word: tokenBase, norm: tokenNorm });
      }
    }
    return words;
  }

  function cleanContextTokens(rawTokens) {
    const output = [];
    for (const token of rawTokens || []) {
      const normalized = normalizeWordToken(String(token || ""));
      if (normalized) {
        output.push(normalized);
      }
    }
    return output;
  }

  function contextBundle(context) {
    if (!context || typeof context !== "object" || Array.isArray(context)) {
      return { tokens: [], idx: -1 };
    }
    const rawTokens = Array.isArray(context.tokens) ? context.tokens : [];
    const tokens = cleanContextTokens(rawTokens);
    const idx = Number(context.index);
    if (!Number.isFinite(idx) || idx < 0 || idx >= tokens.length) {
      return { tokens, idx: -1 };
    }
    return { tokens, idx: Math.trunc(idx) };
  }

  class BrowserG2P {
    constructor(cmudictRaw) {
      this.dict = {};
      this.loadCmudict(cmudictRaw);
    }

    loadCmudict(rawText) {
      const lines = String(rawText || "").split(/\r?\n/);
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line || line.startsWith(";;;")) {
          continue;
        }
        const parts = line.split(/\s+/);
        if (parts.length < 2) {
          continue;
        }
        const word = String(parts[0]).replace(/\(\d+\)$/g, "").toLowerCase();
        const phones = parts.slice(1);
        if (!this.dict[word]) {
          this.dict[word] = [];
        }
        const bucket = this.dict[word];
        const key = phones.join(" ");
        if (!bucket.some((candidate) => candidate.join(" ") === key)) {
          bucket.push(phones);
        }
      }
    }

    findPronunciationIndex(pronunciations, targetIpa) {
      for (let idx = 0; idx < pronunciations.length; idx += 1) {
        const [ipaTokens] = this.arpabetToIpaWithStress(pronunciations[idx]);
        if (ipaTokens.join(" ") === targetIpa.join(" ")) {
          return idx;
        }
      }
      return null;
    }

    pickPronunciation(pronunciations, targetIpa, fallbackIdx) {
      const found = this.findPronunciationIndex(pronunciations, targetIpa);
      const idx = found === null
        ? Math.max(0, Math.min(pronunciations.length - 1, fallbackIdx))
        : found;
      return pronunciations[idx];
    }

    selectReadPronunciation(pronunciations, context) {
      const { tokens, idx } = contextBundle(context);
      if (idx < 0) {
        return [this.pickPronunciation(pronunciations, ["r", "i", "d"], 1), "cmudict_context:read_present_default"];
      }

      const prev1 = idx - 1 >= 0 ? tokens[idx - 1] : "";
      const prev2 = idx - 2 >= 0 ? tokens[idx - 2] : "";
      const next1 = idx + 1 < tokens.length ? tokens[idx + 1] : "";
      const nearby = new Set(tokens.slice(Math.max(0, idx - 3), idx).concat(tokens.slice(idx + 1, idx + 4)));

      if (READ_PAST_PREV_CUES.has(prev1) || prev1.endsWith("'ve") || prev1.endsWith("'d")) {
        return [this.pickPronunciation(pronunciations, ["r", "ɛ", "d"], 0), "cmudict_context:read_past_cue"];
      }
      if (Array.from(nearby).some((token) => READ_PAST_TIME_CUES.has(token))) {
        return [this.pickPronunciation(pronunciations, ["r", "ɛ", "d"], 0), "cmudict_context:read_past_time"];
      }
      if (prev1 === "last" || prev2 === "last") {
        return [this.pickPronunciation(pronunciations, ["r", "ɛ", "d"], 0), "cmudict_context:read_past_time"];
      }
      if (next1 === "aloud") {
        return [this.pickPronunciation(pronunciations, ["r", "i", "d"], 1), "cmudict_context:read_present_aloud"];
      }
      if (READ_PRESENT_PREV_CUES.has(prev1) || READ_PRESENT_PREV_CUES.has(prev2)) {
        return [this.pickPronunciation(pronunciations, ["r", "i", "d"], 1), "cmudict_context:read_present_cue"];
      }
      if (Array.from(nearby).some((token) => READ_PRESENT_HABITUAL_CUES.has(token))) {
        return [this.pickPronunciation(pronunciations, ["r", "i", "d"], 1), "cmudict_context:read_present_habitual"];
      }
      return [this.pickPronunciation(pronunciations, ["r", "i", "d"], 1), "cmudict_context:read_present_default"];
    }

    selectLeadPronunciation(pronunciations, context) {
      const { tokens, idx } = contextBundle(context);
      if (idx < 0) {
        return [this.pickPronunciation(pronunciations, ["l", "i", "d"], 1), "cmudict_context:lead_verb_default"];
      }

      const prev1 = idx - 1 >= 0 ? tokens[idx - 1] : "";
      const prev2 = idx - 2 >= 0 ? tokens[idx - 2] : "";
      const next1 = idx + 1 < tokens.length ? tokens[idx + 1] : "";
      const next2 = idx + 2 < tokens.length ? tokens[idx + 2] : "";
      const nearby = new Set(tokens.slice(Math.max(0, idx - 3), idx).concat(tokens.slice(idx + 1, idx + 4)));

      if (LEAD_METAL_CUES.has(next1) || LEAD_METAL_CUES.has(next2) || Array.from(nearby).some((token) => LEAD_METAL_CUES.has(token))) {
        return [this.pickPronunciation(pronunciations, ["l", "ɛ", "d"], 0), "cmudict_context:lead_metal"];
      }
      if (LEAD_VERB_PREV_CUES.has(prev1) || LEAD_VERB_PREV_CUES.has(prev2)) {
        return [this.pickPronunciation(pronunciations, ["l", "i", "d"], 1), "cmudict_context:lead_verb_cue"];
      }
      if (LEAD_VERB_NEXT_CUES.has(next1)) {
        return [this.pickPronunciation(pronunciations, ["l", "i", "d"], 1), "cmudict_context:lead_verb_object"];
      }
      if (prev1 === "the" && prev2 === "in") {
        return [this.pickPronunciation(pronunciations, ["l", "i", "d"], 1), "cmudict_context:lead_nominal"];
      }
      return [this.pickPronunciation(pronunciations, ["l", "i", "d"], 1), "cmudict_context:lead_verb_default"];
    }

    selectCmudictPronunciation(normalizedWord, pronunciations, context) {
      if (!Array.isArray(pronunciations) || pronunciations.length === 0) {
        return [[], "cmudict"];
      }
      if (normalizedWord === "read") {
        return this.selectReadPronunciation(pronunciations, context);
      }
      if (normalizedWord === "lead") {
        return this.selectLeadPronunciation(pronunciations, context);
      }
      return [pronunciations[0], "cmudict"];
    }

    arpabetToIpaWithStress(phones) {
      const tokens = [];
      const stressLevels = [];
      for (const phone of phones || []) {
        const base = String(phone || "").replace(/[012]+$/g, "");
        const stress = String(phone || "").slice(base.length);
        if (!ARPABET_TO_IPA[base]) {
          continue;
        }
        let ipa = ARPABET_TO_IPA[base];
        if (base === "AH" && stress === "0") {
          ipa = "ə";
        }
        tokens.push(ipa);
        stressLevels.push(/^\d+$/.test(stress) ? Number(stress) : null);
      }
      return [tokens, stressLevels];
    }

    wordToIpaWithStress(word, context = null) {
      const normalized = normalizeText(word);
      if (!normalized) {
        return [[], "empty", []];
      }

      if (this.dict[normalized]) {
        const [selected, source] = this.selectCmudictPronunciation(normalized, this.dict[normalized], context);
        const [ipaTokens, stressLevels] = this.arpabetToIpaWithStress(selected);
        return [ipaTokens, source, stressLevels];
      }

      if (normalized.endsWith("'s") && this.dict[normalized.slice(0, -2)]) {
        const [selected] = this.selectCmudictPronunciation(normalized.slice(0, -2), this.dict[normalized.slice(0, -2)], context);
        const [base, stressLevels] = this.arpabetToIpaWithStress(selected);
        const last = base.length > 0 ? base[base.length - 1] : "";
        if (["s", "z", "ʃ", "ʒ", "tʃ", "dʒ"].includes(last)) {
          base.push("ɪ", "z");
          stressLevels.push(null, null);
        } else if (["p", "t", "k", "f", "θ"].includes(last)) {
          base.push("s");
          stressLevels.push(null);
        } else {
          base.push("z");
          stressLevels.push(null);
        }
        return [base, "cmudict", stressLevels];
      }

      return [[], "missing", []];
    }
  }

  function sentenceToCanonicalWords(sentenceText, g2p) {
    const records = [];
    const words = parseCleanLineWords(sentenceText);
    const contextTokens = words.map((item) => item.norm || "");
    words.forEach((wordInfo, idx) => {
      const [canonicalIpa, source, stressLevels] = g2p.wordToIpaWithStress(
        wordInfo.word,
        { tokens: contextTokens, index: idx },
      );
      records.push({
        word: wordInfo.word,
        word_norm: wordInfo.norm,
        canonical_ipa: canonicalIpa,
        canonical_stress_levels: stressLevels,
        g2p_source: source,
      });
    });
    return records;
  }

  function stripDiacritics(token) {
    return String(token || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").normalize("NFC");
  }

  function isVowel(token) {
    return VOWELS.has(token);
  }

  function maxOnsetSize(cluster) {
    if (!Array.isArray(cluster) || cluster.length === 0) {
      return 0;
    }
    const maxSize = Math.min(3, cluster.length);
    for (let size = maxSize; size >= 1; size -= 1) {
      const tail = cluster.slice(cluster.length - size).join(" ");
      if (size === 1) {
        return 1;
      }
      if (size === 2 && LEGAL_ONSET_CLUSTERS_2.has(tail)) {
        return 2;
      }
      if (size === 3 && LEGAL_ONSET_CLUSTERS_3.has(tail)) {
        return 3;
      }
    }
    return 1;
  }

  function analyzeSyllableTokens(baseTokens) {
    if (!Array.isArray(baseTokens) || baseTokens.length === 0) {
      return [];
    }

    const baseNorm = baseTokens.map((token) => stripDiacritics(token));
    const vowelIndices = [];
    baseNorm.forEach((token, idx) => {
      if (isVowel(token)) {
        vowelIndices.push(idx);
      }
    });

    const annotations = baseTokens.map((_, idx) => ({
      index: idx,
      syllable_index: 0,
      syllable_slot: "C1",
      slot_index: idx,
      position: idx === 0 ? "onset" : "coda",
    }));

    if (vowelIndices.length === 0) {
      return annotations;
    }

    const syllableCount = vowelIndices.length;
    const firstVowel = vowelIndices[0];
    const lastVowel = vowelIndices[vowelIndices.length - 1];

    for (let idx = 0; idx < firstVowel; idx += 1) {
      annotations[idx] = {
        index: idx,
        syllable_index: 0,
        syllable_slot: "C1",
        slot_index: idx,
        position: "onset",
      };
    }

    vowelIndices.forEach((vowelIdx, syllableIndex) => {
      annotations[vowelIdx] = {
        index: vowelIdx,
        syllable_index: syllableIndex,
        syllable_slot: "V",
        slot_index: 0,
        position: "nucleus",
      };
    });

    const tail = [];
    for (let idx = lastVowel + 1; idx < baseTokens.length; idx += 1) {
      tail.push(idx);
    }
    tail.forEach((idx, slotIndex) => {
      annotations[idx] = {
        index: idx,
        syllable_index: syllableCount - 1,
        syllable_slot: "C2",
        slot_index: slotIndex,
        position: "coda",
      };
    });

    for (let leftSylIdx = 0; leftSylIdx < syllableCount - 1; leftSylIdx += 1) {
      const leftVowel = vowelIndices[leftSylIdx];
      const rightVowel = vowelIndices[leftSylIdx + 1];
      const middle = [];
      for (let idx = leftVowel + 1; idx < rightVowel; idx += 1) {
        middle.push(idx);
      }
      if (middle.length === 0) {
        continue;
      }

      const clusterNorm = middle.map((idx) => baseNorm[idx]);
      const onsetCount = maxOnsetSize(clusterNorm);
      const codaCount = Math.max(0, middle.length - onsetCount);
      const codaIndices = middle.slice(0, codaCount);
      const onsetIndices = middle.slice(codaCount);

      codaIndices.forEach((idx, slotIndex) => {
        annotations[idx] = {
          index: idx,
          syllable_index: leftSylIdx,
          syllable_slot: "C2",
          slot_index: slotIndex,
          position: "intervocalic",
        };
      });

      onsetIndices.forEach((idx, slotIndex) => {
        annotations[idx] = {
          index: idx,
          syllable_index: leftSylIdx + 1,
          syllable_slot: "C1",
          slot_index: slotIndex,
          position: "intervocalic",
        };
      });
    }

    return annotations;
  }

  function normalizeStressLevel(value) {
    if (Number.isInteger(value) && [0, 1, 2].includes(value)) {
      return value;
    }
    if (typeof value === "string" && /^\d+$/.test(value)) {
      const parsed = Number(value);
      return [0, 1, 2].includes(parsed) ? parsed : null;
    }
    return null;
  }

  function detailDict(tokenDetails, idx) {
    if (!Array.isArray(tokenDetails) || idx < 0 || idx >= tokenDetails.length) {
      return {};
    }
    const detail = tokenDetails[idx];
    return detail && typeof detail === "object" ? detail : {};
  }

  function detailSlot(tokenDetails, idx) {
    return String(detailDict(tokenDetails, idx).syllable_slot || "");
  }

  function detailPosition(tokenDetails, idx) {
    return String(detailDict(tokenDetails, idx).position || "");
  }

  function detailSyllableIndex(tokenDetails, idx) {
    const raw = detailDict(tokenDetails, idx).syllable_index;
    if (Number.isInteger(raw)) {
      return raw;
    }
    if (typeof raw === "string" && /^\d+$/.test(raw)) {
      return Number(raw);
    }
    return null;
  }

  function detailSlotIndex(tokenDetails, idx) {
    const raw = detailDict(tokenDetails, idx).slot_index;
    if (Number.isInteger(raw)) {
      return raw;
    }
    if (typeof raw === "string" && /^\d+$/.test(raw)) {
      return Number(raw);
    }
    return null;
  }

  function sameSyllable(tokenDetails, leftIdx, rightIdx) {
    const left = detailSyllableIndex(tokenDetails, leftIdx);
    const right = detailSyllableIndex(tokenDetails, rightIdx);
    if (left === null || right === null) {
      return true;
    }
    return left === right;
  }

  function adjacentOnsetSlots(tokenDetails, leftIdx, rightIdx) {
    if (detailSlot(tokenDetails, leftIdx) !== "C1") {
      return false;
    }
    if (detailSlot(tokenDetails, rightIdx) !== "C1") {
      return false;
    }
    if (!sameSyllable(tokenDetails, leftIdx, rightIdx)) {
      return false;
    }
    const leftSlot = detailSlotIndex(tokenDetails, leftIdx);
    const rightSlot = detailSlotIndex(tokenDetails, rightIdx);
    if (leftSlot === null || rightSlot === null) {
      return false;
    }
    return rightSlot === leftSlot + 1;
  }

  function shouldMergeReducedSchwaL(ipaTokens, tokenDetails, idx) {
    if (idx + 1 >= ipaTokens.length) {
      return false;
    }
    if (ipaTokens[idx] !== "ə" || ipaTokens[idx + 1] !== "l") {
      return false;
    }
    if (idx + 1 !== ipaTokens.length - 1) {
      return false;
    }
    if (idx + 1 >= tokenDetails.length) {
      return false;
    }

    const current = detailDict(tokenDetails, idx);
    const next = detailDict(tokenDetails, idx + 1);
    if (normalizeStressLevel(current.stress_level) !== 0) {
      return false;
    }
    if (String(next.syllable_slot || "") !== "C2") {
      return false;
    }
    const currentSyllable = current.syllable_index;
    const nextSyllable = next.syllable_index;
    if (Number.isInteger(currentSyllable) && Number.isInteger(nextSyllable) && currentSyllable !== nextSyllable) {
      return false;
    }
    return true;
  }

  function slotAwareZhuyin(row, token, slot) {
    if (slot === "C1") {
      return row.zhuyin_plus_C1 || row.zhuyin_plus || token;
    }
    if (slot === "V") {
      return row.zhuyin_plus_V || row.zhuyin_plus || token;
    }
    if (slot === "C2") {
      return row.zhuyin_plus_C2 || row.zhuyin_plus || token;
    }
    return row.zhuyin_plus || token;
  }

  function contextualZhuyinOverride(ipaTokens, tokenDetails, idx, reducedSchwaL) {
    const token = ipaTokens[idx];
    const slot = detailSlot(tokenDetails, idx);

    if (shouldMergeReducedSchwaL(ipaTokens, tokenDetails, idx)) {
      return { text: reducedSchwaL, mergeNext: true };
    }

    if (idx + 1 < ipaTokens.length) {
      const nextToken = ipaTokens[idx + 1];
      const nextSlot = detailSlot(tokenDetails, idx + 1);
      const same = sameSyllable(tokenDetails, idx, idx + 1);

      if (token === "ɔ" && nextToken === "ɹ" && nextSlot === "C2" && same) return { text: "ㄛㄦ", mergeNext: true };
      if (["ɑ", "ɑː", "a"].includes(token) && nextToken === "ɹ" && nextSlot === "C2" && same) return { text: "ㄚ(喉)ㄦ", mergeNext: true };
      if (token === "ɛ" && nextToken === "ɹ" && nextSlot === "C2" && same) return { text: "ㄝㄦ", mergeNext: true };
      if (["ɪ", "i"].includes(token) && nextToken === "ɹ" && nextSlot === "C2" && same) return { text: "ㄧㄦ", mergeNext: true };
      if (token === "ɔ" && nextToken === "l" && nextSlot === "C2" && same) return { text: "ㄛ", mergeNext: true };
      if (token === "d" && nextToken === "z" && slot === "C2" && nextSlot === "C2" && idx + 1 === ipaTokens.length - 1 && same) return { text: "ㄗ", mergeNext: true };
      if (token === "t" && nextToken === "s" && slot === "C2" && nextSlot === "C2" && idx + 1 === ipaTokens.length - 1 && same) return { text: "ㄘ", mergeNext: true };
      if (token === "t" && nextToken === "ɹ" && adjacentOnsetSlots(tokenDetails, idx, idx + 1)) return { text: "ㄔㄨ", mergeNext: true };
      if (token === "d" && nextToken === "ɹ" && adjacentOnsetSlots(tokenDetails, idx, idx + 1)) return { text: "ㄓㄨ", mergeNext: true };
    }

    if (token === "k" && idx > 0 && ipaTokens[idx - 1] === "s" && adjacentOnsetSlots(tokenDetails, idx - 1, idx)) {
      return { text: "ㄍ", mergeNext: false };
    }
    if (token === "p" && slot === "C1" && detailPosition(tokenDetails, idx) === "intervocalic") {
      return { text: "ㄅ", mergeNext: false };
    }
    if (token === "l" && slot === "C2") {
      return { text: "ㄛ", mergeNext: false };
    }
    return null;
  }

  function ipaKey(tokens) {
    return (tokens || []).filter((token) => token).join(" ");
  }

  function normalizeOverrideTokens(tokens, targetLen) {
    const normalized = (tokens || []).map((token) => String(token || ""));
    if (normalized.length < targetLen) {
      normalized.push(...new Array(targetLen - normalized.length).fill(""));
    }
    if (normalized.length > targetLen) {
      return normalized.slice(0, targetLen);
    }
    return normalized;
  }

  function normalizeExceptionWord(raw) {
    return normalizeWordToken(String(raw || "").replaceAll("’", "'"));
  }

  function loadDisplayExceptionsJson(payload) {
    const output = {};
    const entries = Array.isArray(payload?.word_ipa_overrides) ? payload.word_ipa_overrides : [];
    entries.forEach((item) => {
      if (!item || typeof item !== "object") {
        return;
      }
      const wordNorm = normalizeExceptionWord(item.word_norm || "");
      const ipaRaw = Array.isArray(item.ipa) ? item.ipa : [];
      const zhuyinRaw = Array.isArray(item.zhuyin_plus) ? item.zhuyin_plus : [];
      if (!wordNorm) {
        return;
      }
      const ipaTokens = ipaRaw.map((token) => String(token || "").trim()).filter((token) => token);
      if (ipaTokens.length === 0) {
        return;
      }
      if (!output[wordNorm]) {
        output[wordNorm] = {};
      }
      output[wordNorm][ipaKey(ipaTokens)] = normalizeOverrideTokens(zhuyinRaw, ipaTokens.length);
    });
    return output;
  }

  function resolveDisplayExceptionZhuyin(displayExceptions, wordText, ipaTokens) {
    if (!displayExceptions || typeof displayExceptions !== "object") {
      return null;
    }
    const wordNorm = normalizeExceptionWord(wordText || "");
    if (!wordNorm) {
      return null;
    }
    const wordRules = displayExceptions[wordNorm];
    if (!wordRules || typeof wordRules !== "object") {
      return null;
    }
    const candidate = wordRules[ipaKey(ipaTokens)];
    if (!Array.isArray(candidate)) {
      return null;
    }
    return normalizeOverrideTokens(candidate, ipaTokens.length);
  }

  function buildDisplayBundle(tokens, table, tokenDetails = [], wordText = "", displayExceptions = null) {
    const ipaTokens = (tokens || []).filter((token) => token);
    const kkTokens = [];
    const zhuyinTokens = [];
    const symbolIds = [];
    const details = Array.isArray(tokenDetails) ? tokenDetails : [];
    const reducedSchwaL = (table?.["əl"]?.zhuyin_plus) || "ㄛ";
    const mergedNextIndices = new Set();
    const exceptionZhuyin = resolveDisplayExceptionZhuyin(displayExceptions, wordText, ipaTokens);

    ipaTokens.forEach((token, idx) => {
      const row = table?.[token] && typeof table[token] === "object" ? table[token] : {};
      kkTokens.push(row.kk || token);
      symbolIds.push(row.symbol_id || "");

      if (exceptionZhuyin) {
        zhuyinTokens.push(idx < exceptionZhuyin.length ? exceptionZhuyin[idx] : "");
        return;
      }
      if (mergedNextIndices.has(idx)) {
        zhuyinTokens.push("");
        return;
      }

      const override = contextualZhuyinOverride(ipaTokens, details, idx, reducedSchwaL);
      if (override) {
        zhuyinTokens.push(override.text);
        if (override.mergeNext && idx + 1 < ipaTokens.length) {
          mergedNextIndices.add(idx + 1);
        }
        return;
      }

      zhuyinTokens.push(slotAwareZhuyin(row, token, detailSlot(details, idx)));
    });

    return {
      ipa: ipaTokens,
      kk: kkTokens,
      zhuyin_plus: zhuyinTokens,
      symbol_ids: symbolIds,
    };
  }

  function normalizeIpaTokens(value) {
    if (typeof value === "string") {
      const raw = value.trim();
      if (!raw) {
        return [];
      }
      if (raw.includes(" ")) {
        return raw.split(/\s+/).filter((token) => token);
      }
      const pattern = MULTI_PHONEME_UNITS
        .slice()
        .sort((a, b) => b.length - a.length)
        .map((unit) => escapeRegex(unit))
        .join("|");
      const re = new RegExp(`(${pattern}|[^\\s])`, "gu");
      return Array.from(raw.matchAll(re)).map((match) => match[1]).filter((token) => token && token.trim());
    }
    if (Array.isArray(value)) {
      return value.map((token) => String(token || "").trim()).filter((token) => token);
    }
    return [];
  }

  class BrowserPipeline {
    constructor(data) {
      const safeData = data && typeof data === "object" ? data : {};
      this.g2p = new BrowserG2P(safeData.cmudict_raw || "");
      this.displayTable = safeData.display_table && typeof safeData.display_table === "object"
        ? safeData.display_table
        : {};
      this.displayExceptions = loadDisplayExceptionsJson(safeData.display_exceptions || {});
    }

    splitSentences(text) {
      let normalized = String(text || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n");
      normalized = normalized.replace(/[ \t]+/g, " ");
      normalized = normalized.replace(/\n{2,}/g, "\n").trim();
      if (!normalized) {
        return [];
      }
      const parts = normalized.match(/[^.!?。！？\n]+(?:[.!?。！？]+|$)/g) || [];
      return parts.map((part) => String(part || "").replace(/\s+/g, " ").trim()).filter((part) => part);
    }

    processText(text, source = "inline") {
      const sentences = this.splitSentences(text).map((sentence, idx) => this.processSentence(sentence, idx + 1));
      return {
        schema_version: SCHEMA_VERSION,
        source: {
          type: "text",
          name: source || "inline",
        },
        sentences,
      };
    }

    processSentence(sentenceText, sentenceId = 1) {
      const words = sentenceToCanonicalWords(sentenceText, this.g2p).map((record, idx) => this.recordToWord(record, idx + 1));
      return {
        sentence_id: String(sentenceId),
        text: String(sentenceText || "").trim(),
        words,
      };
    }

    processWord(wordText, context = null) {
      const contextTokens = [];
      let contextIndex = -1;
      if (context && typeof context === "object" && !Array.isArray(context)) {
        const rawTokens = Array.isArray(context.tokens) ? context.tokens : [];
        rawTokens.forEach((token) => {
          contextTokens.push(normalizeWordToken(String(token || "")));
        });
        const idx = Number(context.index);
        if (Number.isFinite(idx)) {
          contextIndex = Math.trunc(idx);
        }
      }
      const [ipaTokens, source, stressLevels] = this.g2p.wordToIpaWithStress(
        String(wordText || ""),
        contextTokens.length > 0 ? { tokens: contextTokens, index: contextIndex } : null,
      );
      const record = {
        word: String(wordText || "").trim(),
        word_norm: normalizeWordToken(String(wordText || "")),
        canonical_ipa: ipaTokens,
        canonical_stress_levels: stressLevels,
        g2p_source: source,
      };
      return this.recordToWord(record, 1);
    }

    displayForIpa(ipaTokens, wordText = "", stressLevels = []) {
      const tokens = normalizeIpaTokens(ipaTokens);
      const tokenDetails = analyzeSyllableTokens(tokens);
      if (Array.isArray(stressLevels) && stressLevels.length > 0) {
        tokenDetails.forEach((detail, idx) => {
          detail.stress_level = idx < stressLevels.length ? stressLevels[idx] : null;
        });
      }
      const display = buildDisplayBundle(tokens, this.displayTable, tokenDetails, wordText, this.displayExceptions);
      return {
        ipa: tokens,
        display,
        token_details: tokenDetails,
      };
    }

    exportJson(payload) {
      const output = payload && typeof payload === "object" ? payload : {};
      if (!output.schema_version) {
        output.schema_version = SCHEMA_VERSION;
      }
      if (!output.export) {
        output.export = {
          status: "draft",
          format: "text-ipa-zhuyin-presenter",
        };
      }
      return output;
    }

    getDisplayTable() {
      return this.displayTable;
    }

    recordToWord(record, wordIndex) {
      const ipaTokens = normalizeIpaTokens(record.canonical_ipa || []);
      const stressLevels = Array.isArray(record.canonical_stress_levels) ? record.canonical_stress_levels : [];
      const tokenDetails = analyzeSyllableTokens(ipaTokens);
      tokenDetails.forEach((detail, idx) => {
        detail.stress_level = idx < stressLevels.length ? stressLevels[idx] : null;
      });
      const display = buildDisplayBundle(
        ipaTokens,
        this.displayTable,
        tokenDetails,
        record.word || "",
        this.displayExceptions,
      );
      return {
        word_id: String(wordIndex),
        word: record.word || "",
        word_norm: record.word_norm || "",
        g2p_source: record.g2p_source || "",
        ipa: ipaTokens,
        display,
        token_details: tokenDetails,
        edited: false,
      };
    }
  }

  function createBrowserPipeline(data = null) {
    return new BrowserPipeline(data || window.BROWSER_DATA || {});
  }

  window.BrowserPipeline = BrowserPipeline;
  window.createBrowserPipeline = createBrowserPipeline;
})();
