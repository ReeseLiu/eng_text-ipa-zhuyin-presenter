/* eslint-disable no-continue */
(() => {
  const SCHEMA_VERSION = "0.1.0";
  const JASON_SLOT_ORDER = ["C1", "V", "C2"];

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
  const WORD_WITH_PUNCT_RE = /^([A-Za-z']+)([.,!?;:…]*)$/;
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
      this.dict = Object.create(null);
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
    const output = Object.create(null);
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

  function normalizeSyllableSlot(value) {
    const slot = String(value || "");
    return JASON_SLOT_ORDER.includes(slot) ? slot : "V";
  }

  function normalizeSyllableIndex(value) {
    if (Number.isInteger(value)) {
      return Math.max(0, value);
    }
    if (typeof value === "string" && /^\d+$/.test(value)) {
      return Math.max(0, Number(value));
    }
    return 0;
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

  function groupTokensBySyllable(tokens, syllableCount) {
    const compact = Array.isArray(tokens)
      ? tokens.map((token) => String(token || "").trim()).filter((token) => token)
      : [];
    if (compact.length === 0) {
      return [];
    }
    if (!Number.isInteger(syllableCount) || syllableCount <= 0) {
      return compact.map((token) => [token]);
    }

    const target = Math.max(1, Math.min(syllableCount, compact.length));
    const base = Math.floor(compact.length / target);
    const remainder = compact.length % target;
    const groups = [];
    let cursor = 0;

    for (let idx = 0; idx < target; idx += 1) {
      const size = base + (idx < remainder ? 1 : 0);
      if (size <= 0) {
        continue;
      }
      groups.push(compact.slice(cursor, cursor + size));
      cursor += size;
    }

    return groups;
  }

  function splitSurfaceTextForRows(surfaceText, rowCount) {
    const safeCount = Number.isInteger(rowCount) ? rowCount : 0;
    if (safeCount <= 0) {
      return [];
    }

    const trimmed = String(surfaceText || "").trim();
    if (safeCount === 1) {
      return [trimmed];
    }
    if (!trimmed) {
      return Array.from({ length: safeCount }, () => "");
    }

    const matched = trimmed.match(WORD_WITH_PUNCT_RE);
    if (!matched) {
      return [trimmed, ...Array.from({ length: safeCount - 1 }, () => "")];
    }

    const [, coreWord, punct] = matched;
    const hinted = WORD_SEGMENT_HINTS[String(coreWord || "").toLowerCase()];
    if (!Array.isArray(hinted) || hinted.length !== safeCount) {
      return [trimmed, ...Array.from({ length: safeCount - 1 }, () => "")];
    }

    const built = [];
    for (let idx = 0; idx < hinted.length; idx += 1) {
      const part = String(hinted[idx] || "").trim();
      if (!part) {
        return [trimmed, ...Array.from({ length: safeCount - 1 }, () => "")];
      }
      built.push(idx === hinted.length - 1 ? `${part}${punct || ""}` : part);
    }

    if (/^[A-Z]/.test(coreWord) && built.length > 0 && built[0]) {
      built[0] = built[0][0].toUpperCase() + built[0].slice(1);
    }

    return built;
  }

  function fallbackSyllableCountForWord(word, surfaceText = "") {
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
      return guessEnglishSyllableCount(String(word?.word || surfaceText || ""));
    }

    return null;
  }

  function parseZhuyinNumbers(token, phoneticNumberTable, sortedSymbols) {
    const text = String(token || "").trim();
    if (!text) {
      return [];
    }
    const direct = Number(phoneticNumberTable[text]);
    if (Number.isInteger(direct)) {
      return [direct];
    }

    const memo = {};
    const walk = (start) => {
      if (start === text.length) {
        return [];
      }
      if (Object.prototype.hasOwnProperty.call(memo, start)) {
        return memo[start];
      }

      for (const symbol of sortedSymbols) {
        if (!text.startsWith(symbol, start)) {
          continue;
        }
        const tail = walk(start + symbol.length);
        if (!Array.isArray(tail)) {
          continue;
        }
        const number = Number(phoneticNumberTable[symbol]);
        if (!Number.isInteger(number)) {
          continue;
        }
        const result = [number, ...tail];
        memo[start] = result;
        return result;
      }

      memo[start] = null;
      return null;
    };

    const segmented = walk(0);
    return Array.isArray(segmented) ? segmented : [];
  }

  function normalizeSlotTokens(value) {
    if (Array.isArray(value)) {
      return value.map((token) => String(token || "").trim()).filter((token) => token);
    }
    if (typeof value === "string") {
      return value.trim().split(/[\s,]+/).filter((part) => part);
    }
    return [];
  }

  function buildPhoneticRowFromSlots(slots, phoneticNumberTable, sortedSymbols) {
    const row = [];
    JASON_SLOT_ORDER.forEach((slot) => {
      const slotTokens = normalizeSlotTokens(slots?.[slot]);
      if (slotTokens.length === 0) {
        return;
      }

      const merged = [];
      let parsedTokenCount = 0;
      slotTokens.forEach((token) => {
        const numbers = parseZhuyinNumbers(token, phoneticNumberTable, sortedSymbols);
        if (numbers.length === 0) {
          return;
        }
        merged.push(...numbers);
        parsedTokenCount += 1;
      });

      if (merged.length === 0) {
        return;
      }
      if (merged.length > 1 || parsedTokenCount > 1) {
        row.push(merged);
      } else {
        row.push(merged[0]);
      }
    });
    return row;
  }

  function buildManualPhoneticRows(word, surfaceText, phoneticNumberTable, sortedSymbols) {
    const rawRows = Array.isArray(word?.manual_syllables) ? word.manual_syllables : [];
    const rows = [];
    rawRows.forEach((rowRaw) => {
      if (!rowRaw || typeof rowRaw !== "object" || Array.isArray(rowRaw)) {
        return;
      }
      const text = String(rowRaw.text || "");
      const slots = rowRaw.slots && typeof rowRaw.slots === "object" ? rowRaw.slots : {};
      const phonetic = buildPhoneticRowFromSlots(slots, phoneticNumberTable, sortedSymbols);
      if (phonetic.length === 0) {
        return;
      }
      rows.push({ text, phonetic });
    });

    if (rows.length > 0 && !rows.some((row) => String(row.text || "").trim())) {
      rows[0].text = surfaceText;
    }
    return rows;
  }

  function buildPhoneticRows(displayZhuyinTokens, tokenDetails, phoneticNumberTable, sortedSymbols, fallbackSyllableCount = null) {
    const tokens = Array.isArray(displayZhuyinTokens)
      ? displayZhuyinTokens.map((token) => String(token || "").trim())
      : [];
    if (tokens.length === 0) {
      return [];
    }

    if (!Array.isArray(tokenDetails) || tokenDetails.length !== tokens.length) {
      const fallbackRows = [];
      const grouped = groupTokensBySyllable(tokens, fallbackSyllableCount);
      grouped.forEach((group) => {
        const groupNumbers = [];
        group.forEach((token) => {
          const numbers = parseZhuyinNumbers(token, phoneticNumberTable, sortedSymbols);
          if (numbers.length === 0) {
            return;
          }
          groupNumbers.push(...numbers);
        });
        if (groupNumbers.length === 0) {
          return;
        }
        fallbackRows.push(groupNumbers);
      });
      return fallbackRows;
    }

    const syllableMap = new Map();
    const slotCounts = new Map();
    tokenDetails.forEach((detailRaw) => {
      const detail = detailRaw && typeof detailRaw === "object" ? detailRaw : {};
      const slot = normalizeSyllableSlot(detail.syllable_slot);
      const syllableIndex = normalizeSyllableIndex(detail.syllable_index);
      if (!slotCounts.has(syllableIndex)) {
        slotCounts.set(syllableIndex, { C1: 0, V: 0, C2: 0 });
      }
      const counts = slotCounts.get(syllableIndex);
      counts[slot] = Number(counts[slot] || 0) + 1;
    });

    tokens.forEach((token, idx) => {
      if (!token) {
        return;
      }
      const detail = tokenDetails[idx] && typeof tokenDetails[idx] === "object" ? tokenDetails[idx] : {};
      const slot = normalizeSyllableSlot(detail.syllable_slot);
      const syllableIndex = normalizeSyllableIndex(detail.syllable_index);
      const numbers = parseZhuyinNumbers(token, phoneticNumberTable, sortedSymbols);
      if (numbers.length === 0) {
        return;
      }

      if (!syllableMap.has(syllableIndex)) {
        syllableMap.set(syllableIndex, { C1: [], V: [], C2: [] });
      }
      const bucket = syllableMap.get(syllableIndex);
      bucket[slot].push(...numbers);
    });

    const outputRows = [];
    const indices = Array.from(syllableMap.keys()).sort((a, b) => a - b);
    indices.forEach((syllableIndex) => {
      const bucket = syllableMap.get(syllableIndex);
      const row = [];
      JASON_SLOT_ORDER.forEach((slot) => {
        const numbers = Array.isArray(bucket?.[slot]) ? bucket[slot] : [];
        if (numbers.length === 0) {
          return;
        }
        const compositeSlot = (slot === "C1" || slot === "C2")
          && Number(slotCounts.get(syllableIndex)?.[slot] || 0) > 1;
        row.push(numbers.length > 1 || compositeSlot ? numbers : numbers[0]);
      });

      if (row.length > 0) {
        outputRows.push(row);
      }
    });

    return outputRows;
  }

  function tokenKkPhonetic(word) {
    const display = word?.display && typeof word.display === "object" ? word.display : {};
    const kkTokens = Array.isArray(display.kk) ? display.kk : null;
    if (kkTokens) {
      return kkTokens.map((token) => String(token || "")).join("");
    }
    const ipaTokens = Array.isArray(word?.ipa) ? word.ipa : [];
    return ipaTokens.map((token) => String(token || "")).join("");
  }

  function stableHash16(value) {
    let h = 0xCBF29CE484222325n;
    const prime = 0x100000001B3n;
    const mask = (1n << 64n) - 1n;
    const bytes = new TextEncoder().encode(String(value || ""));
    bytes.forEach((byte) => {
      h ^= BigInt(byte);
      h = (h * prime) & mask;
    });
    return h.toString(16).padStart(16, "0");
  }

  function tokenIdFor(sentenceId, wordGroupIndex, tokenIndex, token) {
    const safeToken = token && typeof token === "object" ? token : {};
    const seed = {
      sentenceId: String(sentenceId || ""),
      wordGroupIndex: Number.isInteger(wordGroupIndex) ? wordGroupIndex : Number(wordGroupIndex) || 0,
      tokenIndex: Number.isInteger(tokenIndex) ? tokenIndex : Number(tokenIndex) || 0,
      text: String(safeToken.text || ""),
      phonetic: Array.isArray(safeToken.phonetic) ? safeToken.phonetic : [],
      kkPhonetic: String(safeToken.kkPhonetic || ""),
    };
    const encoded = JSON.stringify(seed);
    return `tok_${stableHash16(encoded)}`;
  }

  function finalizeJasonToken(sentenceId, wordGroupIndex, tokenIndex, token) {
    const safeToken = token && typeof token === "object" ? token : {};
    safeToken.text = String(safeToken.text || "");
    if (!Array.isArray(safeToken.phonetic)) {
      safeToken.phonetic = [];
    }
    safeToken.toneLevel = 0;
    safeToken.toneStyle = "solid-short";
    safeToken.importance = safeToken.phonetic.length > 0 ? "important" : "not-important";
    safeToken.tokenId = tokenIdFor(sentenceId, wordGroupIndex, tokenIndex, safeToken);
    return safeToken;
  }

  function blankJasonToken(text) {
    return {
      tokenId: "",
      text: String(text || ""),
      toneLevel: 0,
      toneStyle: "solid-short",
      phonetic: [],
      importance: "not-important",
      reason: "",
      kkPhonetic: "",
      partOfSpeech: null,
      transZh: "",
    };
  }

  function wordToJasonTokens(word, surfaceText, phoneticNumberTable, sortedSymbols) {
    const display = word?.display && typeof word.display === "object" ? word.display : {};
    const zhuyinTokens = Array.isArray(display.zhuyin_plus) ? display.zhuyin_plus : [];
    const details = Array.isArray(word?.token_details) ? word.token_details : [];
    const fallbackSyllableCount = fallbackSyllableCountForWord(word, surfaceText);
    const kkPhonetic = tokenKkPhonetic(word);

    const manualRows = buildManualPhoneticRows(word, surfaceText, phoneticNumberTable, sortedSymbols);
    if (manualRows.length > 0) {
      return manualRows.map((row, idx) => {
        const token = blankJasonToken(String(row.text || (idx === 0 ? surfaceText : "")));
        token.phonetic = Array.isArray(row.phonetic) ? row.phonetic : [];
        token.kkPhonetic = kkPhonetic;
        return token;
      });
    }

    const phoneticRows = buildPhoneticRows(
      zhuyinTokens,
      details,
      phoneticNumberTable,
      sortedSymbols,
      fallbackSyllableCount,
    );

    if (phoneticRows.length === 0) {
      const token = blankJasonToken(surfaceText);
      token.kkPhonetic = kkPhonetic;
      return [token];
    }

    const splitTexts = splitSurfaceTextForRows(surfaceText, phoneticRows.length);
    return phoneticRows.map((row, idx) => {
      const token = blankJasonToken(splitTexts[idx] || (idx === 0 ? surfaceText : ""));
      token.phonetic = row;
      token.kkPhonetic = kkPhonetic;
      return token;
    });
  }

  function sentenceSurfaceTokens(sentenceText) {
    const text = String(sentenceText || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n").trim();
    if (!text) {
      return [];
    }
    return text.match(/[A-Za-z0-9']+(?:[.,!?;:…]+)?|[^\s]/g) || [];
  }

  function sentenceWords(sentence) {
    const rawWords = Array.isArray(sentence?.words) ? sentence.words : [];
    return rawWords.filter((item) => item && typeof item === "object" && !Array.isArray(item));
  }

  function convertSentenceToJason(sentence, phoneticNumberTable, sortedSymbols) {
    const sentenceText = String(sentence?.text || sentence?.sentence || "");
    const sentenceId = String(sentence?.sentence_id || sentence?.sentenceId || "");
    const surfaceTokens = sentenceSurfaceTokens(sentenceText);
    const sourceWords = sentenceWords(sentence);
    const words = [];
    let sourceIdx = 0;

    surfaceTokens.forEach((rawToken) => {
      if (normalizeWordToken(rawToken) && sourceIdx < sourceWords.length) {
        words.push(wordToJasonTokens(sourceWords[sourceIdx], rawToken, phoneticNumberTable, sortedSymbols));
        sourceIdx += 1;
        return;
      }
      words.push([blankJasonToken(rawToken)]);
    });

    while (sourceIdx < sourceWords.length) {
      const fallbackWord = sourceWords[sourceIdx];
      sourceIdx += 1;
      words.push(
        wordToJasonTokens(
          fallbackWord,
          String(fallbackWord?.word || ""),
          phoneticNumberTable,
          sortedSymbols,
        ),
      );
    }

    words.forEach((wordGroup, wordGroupIndex) => {
      if (!Array.isArray(wordGroup)) {
        return;
      }
      wordGroup.forEach((token, tokenIndex) => {
        if (!token || typeof token !== "object") {
          return;
        }
        wordGroup[tokenIndex] = finalizeJasonToken(sentenceId, wordGroupIndex, tokenIndex, token);
      });
    });

    return {
      sentenceId,
      sentence: sentenceText,
      words,
      tags: Array.isArray(sentence?.tags) ? sentence.tags : [],
      name: String(sentence?.name || ""),
      notes: String(sentence?.notes || ""),
    };
  }

  function exportPayloadToJason(payload, phoneticNumberTable, sortedSymbols) {
    const sentences = Array.isArray(payload?.sentences) ? payload.sentences : [];
    return sentences
      .filter((sentence) => sentence && typeof sentence === "object")
      .map((sentence) => convertSentenceToJason(sentence, phoneticNumberTable, sortedSymbols));
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
      const rawPhoneticNumberTable = safeData.phonetic_number_table && typeof safeData.phonetic_number_table === "object"
        ? safeData.phonetic_number_table
        : {};
      this.phoneticNumberTable = {};
      Object.entries(rawPhoneticNumberTable).forEach(([zhuyin, rawNumber]) => {
        const number = Number(rawNumber);
        if (!zhuyin || !Number.isInteger(number)) {
          return;
        }
        this.phoneticNumberTable[zhuyin] = number;
      });
      this.phoneticNumberSymbols = Object.keys(this.phoneticNumberTable).sort((left, right) => {
        if (left.length !== right.length) {
          return right.length - left.length;
        }
        return left.localeCompare(right);
      });
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
      return exportPayloadToJason(output, this.phoneticNumberTable, this.phoneticNumberSymbols);
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
      const word = {
        word_id: String(wordIndex),
        word: record.word || "",
        word_norm: record.word_norm || "",
        g2p_source: record.g2p_source || "",
        ipa: ipaTokens,
        display,
        token_details: tokenDetails,
        edited: false,
      };

      if (ipaTokens.length === 0 || String(record.g2p_source || "") === "missing") {
        word.syllable_count_guess = guessEnglishSyllableCount(record.word || "");
      }

      return word;
    }
  }

  function createBrowserPipeline(data = null) {
    return new BrowserPipeline(data || window.BROWSER_DATA || {});
  }

  window.BrowserPipeline = BrowserPipeline;
  window.createBrowserPipeline = createBrowserPipeline;
})();
