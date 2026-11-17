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
const React = require("react"), { api } = require("../src/api.ts");
const Component = require("../src/components/AIProviderKeys.tsx").default;
const tick = () => new Promise(setImmediate);
const provider = { key: "gemini", name: "Gemini", configured: true, source: "db", hint: "", default_model: "gemini-3.5-flash-lite", key_url: "https://example.test/keys" };
const rows = [
  { id: 1, provider: "gemini", label: "Main", hint: "abcd", priority: 1, enabled: true, tier: "free", status: "ok", usage_today: { "gemini-3.5-flash-lite": { requests: 14, limit_rpd: 500 } } },
  { id: 2, provider: "gemini", label: "", hint: "efgh", priority: 0, enabled: false, tier: "paid", status: "invalid", usage_today: { "custom-model": { requests: 2, limit_rpd: null } } },
];
function hooks(component) {
  const original = { useState: React.useState, useContext: React.useContext, useId: React.useId, useEffect: React.useEffect, useCallback: React.useCallback, useRef: React.useRef };
  let index = 0, effects = []; const cells = [];
  React.useState = (initial) => { const at = index++; cells[at] ??= { value: typeof initial === "function" ? initial() : initial }; return [cells[at].value, (value) => { cells[at].value = typeof value === "function" ? value(cells[at].value) : value; }]; };
  React.useContext = () => ({ t: (key, vars) => key + (vars ? JSON.stringify(vars) : ""), lang: "en" });
  React.useId = () => "test";
  React.useCallback = (fn) => fn;
  React.useRef = (initial) => cells[index++] ??= { current: initial };
  React.useEffect = (effect, deps) => {
    const at = index++, previous = cells[at];
    if (!previous || deps.some((value, i) => value !== previous.deps[i])) effects.push(() => {
      previous?.cleanup?.(); cells[at] = { deps, cleanup: effect() };
    });
  };
  return { render(props) { index = 0; const tree = component(props); const pending = effects; effects = []; pending.forEach((fn) => fn()); return tree; },
    close() { cells.forEach((cell) => cell?.cleanup?.()); Object.assign(React, original); } };
}
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  return null;
}
const byAria = (tree, prefix) => find(tree, (node) => node.props?.["aria-label"]?.startsWith(prefix));

test("AI key client uses exact new routes and retains legacy save/delete", async () => {
  const original = global.fetch, requests = [];
  global.fetch = async (url, init) => { requests.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body) : null }); return new Response("{}"); };
  try {
    await api.listKeys(); await api.addKey({ provider: "gemini", api_key: "fake-secret", label: "Test", tier: "paid" });
    await api.updateKey(7, { enabled: false }); await api.reorderKeys("gemini", [7, 8]); await api.deleteKey(7);
    await api.saveKey("gemini", "legacy-secret"); await api.deleteKey("gemini");
    assert.deepEqual(requests.map(({ url, method }) => [url, method]), [
      ["/api/ai/keys", "GET"], ["/api/ai/keys", "POST"], ["/api/ai/keys/7", "PATCH"], ["/api/ai/keys/order", "PUT"],
      ["/api/ai/keys/7", "DELETE"], ["/api/ai/keys/gemini", "PUT"], ["/api/ai/keys/gemini", "DELETE"],
    ]);
    assert.deepEqual(requests[3].body, { provider: "gemini", ids: [7, 8] });
    assert.deepEqual(requests[2].body, { enabled: false });
  } finally { global.fetch = original; }
});

test("provider lists sort priority, show plan/status/usage, and expose row controls", async () => {
  const original = { ...api }, changes = [], harness = hooks(Component);
  api.updateKey = async (...args) => changes.push(["patch", ...args]); api.reorderKeys = async (...args) => changes.push(["order", ...args]);
  const props = { provider, keys: rows, available: true, onChanged: async () => changes.push(["reload"]) };
  try {
    let tree = harness.render(props), list = find(tree, (node) => node.type === "ol");
    assert.deepEqual(list.props.children.map((node) => node.key), ["2", "1"]);
    const content = JSON.stringify(tree);
    for (const expected of ["set.keyPrimary", "set.keyBackup", "set.keyInvalid", "set.keyValid", "14", "500", "custom-model", "set.geminiProjectQuota"]) assert.ok(content.includes(expected), expected);
    assert.equal(byAria(tree, "set.keyMoveUp").props.disabled, true);
    await byAria(tree, "set.keyMoveDown").props.onClick(); tree = harness.render(props);
    assert.deepEqual(changes[0], ["order", "gemini", [1, 2]]);
    await byAria(tree, "set.keyEnabledFor").props.onChange({ target: { checked: true } }); tree = harness.render(props);
    await byAria(tree, "set.keyTierFor").props.onChange({ target: { value: "free" } });
    assert.ok(changes.some((change) => JSON.stringify(change) === JSON.stringify(["patch", 2, { enabled: true }])));
    assert.ok(changes.some((change) => JSON.stringify(change) === JSON.stringify(["patch", 2, { tier: "free" }])));
  } finally { harness.close(); Object.assign(api, original); }
});

test("add form sends label/password/plan, keeps errors inline, and clears secret after success", async () => {
  const original = { ...api }, calls = [], harness = hooks(Component); let fail = true;
  api.addKey = async (body) => { calls.push(body); if (fail) throw new Error("Invalid key"); return rows[0]; };
  const props = { provider, keys: [], available: true, onChanged: async () => {} };
  try {
    let tree = harness.render(props);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    find(tree, (node) => node.type === "input" && node.props.maxLength === 80).props.onChange({ target: { value: "  Backup  " } });
    find(tree, (node) => node.type === "input" && node.props.type === "password").props.onChange({ target: { value: "  fake-new-secret  " } });
    const plan = find(tree, (node) => node.props?.value === "free" && node.props.onChange && node.type !== "input");
    plan.props.onChange({ target: { value: "paid" } }); tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.ok(find(tree, (node) => node.props?.role === "alert" && node.props.children === "Invalid key"));
    assert.equal(find(tree, (node) => node.type === "input" && node.props.type === "password").props.value, "  fake-new-secret  ");
    fail = false; await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.deepEqual(calls[1], { provider: "gemini", api_key: "fake-new-secret", label: "Backup", tier: "paid" });
    assert.equal(find(tree, (node) => node.type === "input" && node.props.type === "password"), null);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.type === "input" && node.props.type === "password").props.value, "");
  } finally { harness.close(); Object.assign(api, original); }
});

test("delete requires confirmation and unavailable data disables mutations", async () => {
  const original = { ...api }, oldConfirm = global.confirm, calls = [], harness = hooks(Component);
  api.deleteKey = async (id) => calls.push(id);
  const props = { provider, keys: rows, available: true, onChanged: async () => {} };
  try {
    let tree = harness.render(props);
    global.confirm = () => false; await byAria(tree, "set.keyDelete").props.onClick(); assert.deepEqual(calls, []);
    global.confirm = () => true; await byAria(tree, "set.keyDelete").props.onClick(); assert.deepEqual(calls, [2]);
    tree = harness.render({ ...props, available: false });
    assert.equal(byAria(tree, "set.keyDelete").props.disabled, true);
    assert.equal(byAria(tree, "set.keyEnabledFor").props.disabled, true);
  } finally { harness.close(); Object.assign(api, original); global.confirm = oldConfirm; }
});

test("Settings loads and groups keys, then reloads metadata after mutations", async () => {
  const Settings = require("../src/components/Settings.tsx").default;
  const original = { ...api }, harness = hooks(Settings); let keyCalls = 0, providerCalls = 0, changed = 0;
  api.providers = async () => { providerCalls++; return [provider]; };
  api.listKeys = async () => { keyCalls++; return rows; };
  const props = { meta: { mode: "local" }, me: null, initialTab: "keys", onChanged() { changed++; }, onClose() {} };
  try {
    harness.render(props); await tick(); const tree = harness.render(props);
    const section = find(tree, (node) => node.type === Component && node.props.provider.key === "gemini");
    assert.deepEqual(section.props.keys, rows); assert.equal(section.props.available, true);
    assert.equal(keyCalls, 1); assert.equal(providerCalls, 1);
    await section.props.onChanged();
    assert.equal(keyCalls, 2); assert.equal(providerCalls, 2); assert.equal(changed, 1);
  } finally { harness.close(); Object.assign(api, original); }
});
