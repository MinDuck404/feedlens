const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (module, filename) => {
    const source = fs.readFileSync(filename, "utf8").replace("import.meta.env", "({})");
    module._compile(ts.transpileModule(source, { fileName: filename, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText, filename);
  };
}
global.localStorage = { getItem: () => null, setItem: () => {} };
const { formatDuration, runTimingSummary } = require("../src/logic.ts");

test("formatDuration uses minutes and seconds per language", () => {
  assert.equal(formatDuration(192.4, "vi"), "3 phút 12 giây");
  assert.equal(formatDuration(192.4, "en"), "3m 12s");
  assert.equal(formatDuration(192.4, "zh"), "3分12秒");
  assert.equal(formatDuration(20, "vi"), "20 giây");
  assert.equal(formatDuration(0.4, "en"), "<1s");
  assert.equal(formatDuration(3725, "en"), "1h 2m");
});

test("runTimingSummary keeps only phases that were measured, in display order", () => {
  assert.deepEqual(runTimingSummary({ analysis: 340, scrape_total: 192, navigation: 3 }).main.map((p) => p.key), ["scrape_total", "analysis"]);
  assert.deepEqual(runTimingSummary({ scrape_total: 10, expand: 1, navigation: 2 }).detail.map((p) => p.key), ["navigation", "expand"]);
  assert.equal(runTimingSummary(undefined), null);
  assert.equal(runTimingSummary({}), null);
});
