#!/usr/bin/env node
// Loads the real app/app.js into a minimal fake DOM (Node built-ins only, no jsdom)
// and drives the syllable-split suggestion flow through postJson and the rendered
// buttons. Exits non-zero on the first failed assertion; run by
// tests/test_syllable_split.py::AppFlowTest.
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appDir = path.resolve(__dirname, "..", "..", "app");

class FakeElement {
  constructor(document, tagName) {
    this.ownerDocument = document;
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.listeners = {};
    this.className = "";
    this.dataset = {};
    this.attributes = {};
    this.style = { setProperty() {} };
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.scrollWidth = 0;
    this.clientWidth = 0;
    this._text = "";
    const self = this;
    this.classList = {
      _list: () => self.className.split(/\s+/).filter(Boolean),
      add(...names) {
        self.className = [...new Set([...this._list(), ...names])].join(" ");
      },
      remove(...names) {
        self.className = this._list().filter((n) => !names.includes(n)).join(" ");
      },
      toggle(name, force) {
        const on = force === undefined ? !this.contains(name) : Boolean(force);
        on ? this.add(name) : this.remove(name);
        return on;
      },
      contains(name) {
        return this._list().includes(name);
      },
    };
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this.children = [];
    this._text = String(value ?? "");
  }

  set innerHTML(value) {
    this.textContent = value;
  }

  appendChild(child) {
    if (child.parentNode) {
      child.remove();
    }
    child.parentNode = this;
    this.children.push(child);
    if (this.onChildAppended) {
      this.onChildAppended(child);
    }
    return child;
  }

  append(...nodes) {
    nodes.forEach((node) => this.appendChild(node));
  }

  remove() {
    if (this.parentNode) {
      this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
      this.parentNode = null;
    }
  }

  contains(node) {
    return node === this || this.children.some((child) => child.contains(node));
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
  }

  addEventListener(type, handler) {
    (this.listeners[type] = this.listeners[type] || []).push(handler);
  }

  dispatchEvent(event) {
    (this.listeners[event.type] || []).forEach((handler) => handler(event));
    return true;
  }

  click() {
    this.dispatchEvent({ type: "click", target: this, preventDefault() {} });
  }

  focus() {}

  setSelectionRange() {}

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  // Compound selectors only: tag, .class and [attr='value'] (data-* reads dataset).
  matches(selector) {
    const tag = selector.match(/^[a-z]+/i);
    if (tag && tag[0].toUpperCase() !== this.tagName) {
      return false;
    }
    for (const [, cls] of selector.matchAll(/\.([\w-]+)/g)) {
      if (!this.classList.contains(cls)) {
        return false;
      }
    }
    for (const [, name, value] of selector.matchAll(/\[([\w-]+)='([^']*)'\]/g)) {
      const actual = name.startsWith("data-")
        ? this.dataset[name.slice(5).replace(/-(\w)/g, (_m, c) => c.toUpperCase())]
        : this.getAttribute(name);
      if (actual !== value) {
        return false;
      }
    }
    return true;
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => node.matches(selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

function createApp({ staticOnly }) {
  const fetchCalls = [];
  const document = {
    _byId: {},
    createElement(tag) {
      return new FakeElement(document, tag);
    },
    getElementById(id) {
      if (!document._byId[id]) {
        document._byId[id] = document.body.appendChild(new FakeElement(document, "div"));
        document._byId[id].id = id;
      }
      return document._byId[id];
    },
    querySelector(selector) {
      if (selector === "meta[name='app-static-only']") {
        return { content: staticOnly ? "on" : "off" };
      }
      return document.body.querySelector(selector);
    },
    addEventListener() {},
  };
  document.body = new FakeElement(document, "body");
  document.head = new FakeElement(document, "head");

  const context = {
    console,
    document,
    Event: class {
      constructor(type) {
        this.type = type;
      }
    },
    location: { protocol: "http:", hostname: "localhost" },
    fetch: async (url, options) => {
      fetchCalls.push({ url, options });
      throw new Error(`unexpected fetch ${url}`);
    },
    setTimeout,
    clearTimeout,
  };
  context.window = context;
  vm.createContext(context);

  // ensureAlignTableLoaded injects <script src="browser_align.js">; emulate the browser loading it.
  const scriptLoads = [];
  document.head.onChildAppended = (child) => {
    if (child.tagName !== "SCRIPT") {
      return;
    }
    scriptLoads.push(child.src);
    setImmediate(() => {
      vm.runInContext(fs.readFileSync(path.join(appDir, child.src), "utf8"), context, { filename: child.src });
      child.onload();
    });
  };

  for (const name of ["browser_data.js", "browser_pipeline.js", "app.js"]) {
    vm.runInContext(fs.readFileSync(path.join(appDir, name), "utf8"), context, { filename: name });
  }
  // Top-level const/let in app.js live in the context's global lexical scope.
  const run = (code) => vm.runInContext(code, context);
  return { context, document, run, fetchCalls, scriptLoads };
}

function settle() {
  return new Promise((resolve) => setImmediate(resolve));
}

async function settleUntil(predicate, label) {
  for (let i = 0; i < 50; i += 1) {
    if (predicate()) {
      return;
    }
    await settle();
  }
  assert.fail(`timed out waiting for ${label}`);
}

function findButton(root, text) {
  return root.querySelectorAll("button").find((btn) => btn.textContent === text) || null;
}

function previewText(app) {
  const box = app.document.getElementById("sentenceEditor").querySelector(".syllable-suggestion");
  return box ? box.textContent : null;
}

async function loadSentence(app, text) {
  app.document.getElementById("textInput").value = text;
  app.document.getElementById("processBtn").click();
  await settleUntil(() => app.run("state.payload") !== null, "process_text");
}

const tests = [];
function test(name, fn) {
  tests.push({ name, fn });
}

for (const staticOnly of [true, false]) {
  const mode = staticOnly ? "static-only" : "server-allowed";

  test(`${mode}: postJson rejects invalid suggest bodies as bad_request and keeps browser mode`, async () => {
    const app = createApp({ staticOnly });
    assert.strictEqual(app.run("browserPipeline !== null"), true);
    const bodies = [[], null, 5, "communication", {}, { word: "communication" }, { word: 5, ipa: [] }, { word: "x", ipa: [null] }];
    for (const body of bodies) {
      app.context.__body = body;
      await assert.rejects(
        app.run("postJson('/api/suggest_syllable_split', window.__body)"),
        (error) => error.code === "bad_request",
        `body ${JSON.stringify(body)}`,
      );
      assert.strictEqual(app.run("browserPipeline !== null"), true, `browser mode dropped after ${JSON.stringify(body)}`);
    }
    assert.deepStrictEqual(app.fetchCalls, []);
  });

  test(`${mode}: preview -> apply writes manual_syllables via the rendered buttons`, async () => {
    const app = createApp({ staticOnly });
    await loadSentence(app, "communication.");
    const editor = app.document.getElementById("sentenceEditor");
    assert.strictEqual(app.run("browserPipeline.hasAlignTable()"), false);

    findButton(editor, "建議切分").click();
    await settleUntil(() => previewText(app) !== null, "suggestion preview");
    assert.deepStrictEqual(app.scriptLoads, ["browser_align.js"]);
    assert.match(previewText(app), /建議（未套用）：co · mmu · ni · ca · tion/);
    // Preview only: payload is untouched until applied.
    assert.strictEqual(app.run("state.payload.sentences[0].words[0].manual_syllables"), undefined);

    findButton(editor, "套用建議").click();
    const word = JSON.parse(app.run("JSON.stringify(state.payload.sentences[0].words[0])"));
    assert.deepStrictEqual(word.manual_syllables.map((row) => row.text), ["co", "mmu", "ni", "ca", "tion"]);
    assert.strictEqual(word.edited, true);
    assert.strictEqual(app.run("state.syllableSuggestion"), null);
    assert.strictEqual(previewText(app), null);
    assert.match(app.document.getElementById("statusLine").textContent, /已套用音節切分建議/);
    assert.deepStrictEqual(app.fetchCalls, []);
  });

  test(`${mode}: apply on a stale preview refuses and writes nothing`, async () => {
    const app = createApp({ staticOnly });
    await loadSentence(app, "communication.");
    const editor = app.document.getElementById("sentenceEditor");
    findButton(editor, "建議切分").click();
    await settleUntil(() => previewText(app) !== null, "suggestion preview");
    const applyBtn = findButton(editor, "套用建議");
    assert.ok(applyBtn);

    // Edit the word's syllable slots after the preview was rendered (no re-render),
    // so the still-visible apply button now belongs to a stale suggestion.
    app.run(`
      const w = state.payload.sentences[0].words[0];
      state.payload.sentences[0].words[0] = {
        ...w,
        token_details: w.token_details.map((d, i) => (i === 0 ? { ...d, syllable_slot: "V" } : d)),
      };
    `);
    applyBtn.click();
    assert.strictEqual(app.run("state.payload.sentences[0].words[0].manual_syllables"), undefined);
    assert.strictEqual(app.run("state.syllableSuggestion"), null);
    assert.strictEqual(previewText(app), null);
    assert.match(app.document.getElementById("statusLine").textContent, /單字資料已變更/);
  });

  test(`${mode}: re-render hides a preview whose word changed`, async () => {
    const app = createApp({ staticOnly });
    await loadSentence(app, "communication.");
    findButton(app.document.getElementById("sentenceEditor"), "建議切分").click();
    await settleUntil(() => previewText(app) !== null, "suggestion preview");
    app.run(`
      const w = state.payload.sentences[0].words[0];
      state.payload.sentences[0].words[0] = { ...w, ipa: w.ipa.slice(0, -1) };
      renderAll();
    `);
    assert.strictEqual(previewText(app), null);
    assert.strictEqual(findButton(app.document.getElementById("sentenceEditor"), "套用建議"), null);
  });
}

(async () => {
  let failed = 0;
  for (const { name, fn } of tests) {
    try {
      await fn();
      process.stdout.write(`ok - ${name}\n`);
    } catch (error) {
      failed += 1;
      process.stdout.write(`not ok - ${name}\n${error.stack}\n`);
    }
  }
  process.stdout.write(`${tests.length - failed}/${tests.length} passed\n`);
  process.exitCode = failed ? 1 : 0;
})();
