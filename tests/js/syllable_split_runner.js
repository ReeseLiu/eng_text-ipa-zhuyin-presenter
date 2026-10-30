#!/usr/bin/env node
// Runs the browser pipeline under Node for tests/test_syllable_split.py.
// stdin: JSON array of {word, ipa} or {body}; stdout: JSON array of
// {suggestion, syllable_indices} in the same order, or {error: code} when
// suggestSyllableSplit throws (e.g. "bad_request" for invalid input types).
// A {body} item goes through suggestSyllableSplitRequest, the browser-mode
// route for /api/suggest_syllable_split, and yields {suggestion} or {error}.
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appDir = path.resolve(__dirname, "..", "..", "app");
const context = { console };
context.window = context;
vm.createContext(context);
for (const name of ["browser_data.js", "browser_pipeline.js", "browser_align.js"]) {
  vm.runInContext(fs.readFileSync(path.join(appDir, name), "utf8"), context, { filename: name });
}

const pipeline = context.createBrowserPipeline(context.BROWSER_DATA);
const items = JSON.parse(fs.readFileSync(0, "utf8"));
const results = items.map((item) => {
  if (Object.prototype.hasOwnProperty.call(item, "body")) {
    try {
      return { suggestion: JSON.parse(JSON.stringify(pipeline.suggestSyllableSplitRequest(item.body))) };
    } catch (error) {
      return { error: error.code || "error" };
    }
  }
  let suggestion;
  try {
    suggestion = pipeline.suggestSyllableSplit(item.word, item.ipa);
  } catch (error) {
    return { error: error.code || "error" };
  }
  const details = pipeline.displayForIpa(item.ipa, item.word).token_details;
  return {
    suggestion: JSON.parse(JSON.stringify(suggestion)),
    syllable_indices: details.map((detail) => detail.syllable_index),
  };
});
process.stdout.write(JSON.stringify(results));
