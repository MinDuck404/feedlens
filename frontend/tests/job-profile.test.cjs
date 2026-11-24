const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");
for (const extension of [".ts", ".tsx"]) require.extensions[extension] = (module, filename) => {
  const source = fs.readFileSync(filename, "utf8").replace("import.meta.env", "({})");
  module._compile(ts.transpileModule(source, { fileName: filename, compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText, filename);
};
global.localStorage = { getItem: () => "en", setItem() {}, removeItem() {} };
global.window = new EventTarget(); global.document = { documentElement: {} };
const React = require("react"), { api } = require("../src/api/client.ts");
const JobProfileSettings = require("../src/features/settings/JobProfileSettings.tsx").default;
const { Button } = require("../src/components/ui/Button.tsx");

function hooks(component) {
  const original = { useState: React.useState, useContext: React.useContext, useEffect: React.useEffect, useRef: React.useRef };
  let index = 0, effects = []; const cells = [];
  React.useState = (initial) => {
    const at = index++; cells[at] ??= { value: typeof initial === "function" ? initial() : initial };
    return [cells[at].value, (value) => { cells[at].value = typeof value === "function" ? value(cells[at].value) : value; }];
  };
  React.useContext = () => ({ t: (key) => key, lang: "en" });
  React.useRef = (initial) => cells[index++] ??= { current: initial };
  React.useEffect = (effect, deps) => {
    const at = index++, previous = cells[at];
    if (!previous || deps.some((value, i) => value !== previous.deps[i])) effects.push(() => {
      previous?.cleanup?.(); cells[at] = { deps, cleanup: effect() };
    });
  };
  return {
    render(props) { index = 0; const tree = component(props); const pending = effects; effects = []; pending.forEach((fn) => fn()); return tree; },
    close() { cells.forEach((cell) => cell?.cleanup?.()); Object.assign(React, original); },
  };
}
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  return null;
}
const button = (tree, label) => find(tree, (node) => node.type === Button && node.props.children === label);
const field = (tree, label) => find(tree, (node) => node.props?.["aria-label"] === label);
const profile = {
  markdown: "Previous CV", primary_roles: ["Python Engineer"],
  adjacent_roles: [{ role: "QA Engineer", reason: "Testing", enabled: false }], allow_adjacent: false,
  criteria: { work_modes: ["remote"], locations: ["Hà Nội"], min_salary: 2000, currency: "USD", level: "senior" },
};
const preview = { markdown: "# Offline CV\nPython engineer with API experience", suggested_roles: profile.primary_roles, adjacent_roles: profile.adjacent_roles, offline: true };

for (const source of ["text", "file"]) test(`unavailable CV analysis shows a neutral saved notice and retries the original ${source}`, async () => {
  const original = { ...api }, requests = [], saved = [], props = { providers: [] };
  api.profile = async () => structuredClone(profile);
  api.analyzeCV = async (form) => {
    requests.push(form);
    return requests.length === 1 ? { ...preview, ai_status: "unavailable", code: "error.cv_ai_unavailable", saved: true }
      : { ...preview, markdown: "# AI CV", offline: false, ai_status: "ok" };
  };
  api.saveProfile = async (value) => { saved.push(value); return value; };
  const harness = hooks(JobProfileSettings);
  try {
    harness.render(props); await new Promise(setImmediate);
    let tree = harness.render(props);
    const text = "Python engineer with API experience and testing skills";
    const file = new File(["synthetic PDF"], "cv.pdf", { type: "application/pdf" });
    if (source === "file") find(tree, (node) => node.type === "input" && node.props.type === "file").props.onChange({ target: { files: [file] } });
    else field(tree, "profile.paste").props.onChange({ target: { value: text } });
    tree = harness.render(props); await button(tree, "profile.analyze").props.onClick(); tree = harness.render(props);
    const status = find(tree, (node) => node.props?.role === "status");
    assert.ok(status && JSON.stringify(status).includes("profile.aiUnavailable"));
    assert.ok(!status.props.className.includes("text-danger"));
    assert.equal(find(tree, (node) => node.props?.role === "alert"), null);
    assert.equal(field(tree, "profile.markdown").props.value, preview.markdown);
    if (source === "text") assert.equal(field(tree, "profile.paste").props.value, text);
    else assert.ok(JSON.stringify(tree).includes("cv.pdf"));
    await button(tree, "profile.save").props.onClick(); tree = harness.render(props);
    assert.deepEqual(saved[0], { ...profile, markdown: preview.markdown });
    // A new failed attempt restores the retry notice after an explicit save.
    api.analyzeCV = async (form) => { requests.push(form); return { ...preview, ai_status: "unavailable", saved: true }; };
    await button(tree, "profile.analyze").props.onClick(); tree = harness.render(props);
    const retry = button(tree, "act.retry"); assert.ok(retry && !retry.props.disabled);
    api.analyzeCV = async (form) => { requests.push(form); return { ...preview, offline: false, ai_status: "ok" }; };
    await retry.props.onClick(); tree = harness.render(props);
    for (const form of requests) {
      assert.equal(form.get("language"), "en"); assert.equal(form.get("ai_provider"), "auto");
      if (source === "file") { assert.equal(form.get("file").name, "cv.pdf"); assert.equal(await form.get("file").text(), await file.text()); }
      else assert.equal(form.get("text"), text);
    }
    assert.equal(button(tree, "act.retry"), null);
    assert.equal(field(tree, "profile.paste").props.value, "");
    assert.ok(JSON.stringify(tree).includes("profile.review"));
  } finally { harness.close(); Object.assign(api, original); }
});

test("legacy offline CV responses retain their review notice and clear upload input", async () => {
  const original = { ...api }, props = { providers: [] }, harness = hooks(JobProfileSettings);
  api.profile = async () => profile; api.analyzeCV = async () => preview;
  try {
    harness.render(props); await new Promise(setImmediate); let tree = harness.render(props);
    field(tree, "profile.paste").props.onChange({ target: { value: "Python engineer with API experience" } });
    tree = harness.render(props); await button(tree, "profile.analyze").props.onClick(); tree = harness.render(props);
    assert.ok(JSON.stringify(tree).includes("profile.offline"));
    assert.equal(button(tree, "act.retry"), null);
    assert.equal(field(tree, "profile.paste").props.value, "");
  } finally { harness.close(); Object.assign(api, original); }
});
