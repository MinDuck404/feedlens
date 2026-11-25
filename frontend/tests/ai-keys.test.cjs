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
const Component = require("../src/features/settings/AIProviderKeys.tsx").default;
const { TextField } = require("../src/components/ui/TextField.tsx");
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

test("unsaved custom model client sends credentials only in a POST body and localizes failures", async () => {
  const { ApiError } = require("../src/api/client.ts"), i18n = require("../src/i18n/index.tsx");
  const original = global.fetch, requests = [];
  global.fetch = async (url, init) => {
    requests.push({ url, method: init.method, body: JSON.parse(init.body) });
    return new Response(JSON.stringify({ models: ["a-model", "z-model"] }));
  };
  try {
    const body = { base_url: "https://models.example/v1", api_key: "synthetic-discovery-secret" };
    assert.deepEqual(await api.customModels(body), { models: ["a-model", "z-model"] });
    assert.deepEqual(requests, [{ url: "/api/ai/custom/models", method: "POST", body }]);
    for (const [code, status] of [["error.custom_endpoint", 422], ["error.custom_connection", 400]]) {
      global.fetch = async () => new Response(JSON.stringify({ code, detail: "backend diagnostic" }), { status });
      await assert.rejects(api.customModels(body), (error) => error instanceof ApiError && error.code === code && error.message === i18n.translate(code));
    }
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
    find(tree, (node) => node.type === TextField && node.props.maxLength === 80).props.onChange({ target: { value: "  Backup  " } });
    find(tree, (node) => node.type === TextField && node.props.type === "password").props.onChange({ target: { value: "  fake-new-secret  " } });
    const plan = find(tree, (node) => node.props?.value === "free" && node.props.onChange && node.type !== "input");
    plan.props.onChange({ target: { value: "paid" } }); tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.ok(find(tree, (node) => node.props?.role === "alert" && node.props.children === "Invalid key"));
    assert.equal(find(tree, (node) => node.type === TextField && node.props.type === "password").props.value, "  fake-new-secret  ");
    fail = false; await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.deepEqual(calls[1], { provider: "gemini", api_key: "fake-new-secret", label: "Backup", tier: "paid" });
    assert.equal(find(tree, (node) => node.type === TextField && node.props.type === "password"), null);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.type === TextField && node.props.type === "password").props.value, "");
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
  const Settings = require("../src/features/settings/Settings.tsx").default;
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

const customProvider = { key: "custom", name: "Custom (OpenAI-compatible)", configured: true, source: "db", hint: "", default_model: "local-model", key_url: "" };
const customKey = { id: 12, provider: "custom", label: "", hint: "", priority: 0, enabled: true, tier: "free", status: "ok", usage_today: {}, base_url: "http://localhost:11434/v1", default_model: "local-model" };

test("custom model discovery fills an empty model and keeps manual model input available", async () => {
  const original = { ...api }, calls = [], harness = hooks(Component); let changed = 0;
  api.customModels = async (body) => { calls.push(body); return { models: ["a-model", "z-model"] }; };
  api.addKey = async () => assert.fail("Model discovery must not save credentials");
  const props = { provider: customProvider, keys: [], available: true, onChanged: async () => { changed++; } };
  try {
    let tree = harness.render(props);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.children === "set.customLoadModels").props.disabled, true);
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "  https://models.example/v1  " } });
    find(tree, (node) => node.type === TextField && node.props.type === "password").props.onChange({ target: { value: "  synthetic-key  " } });
    tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    assert.deepEqual(calls, [{ base_url: "https://models.example/v1", api_key: "synthetic-key" }]);
    const model = byAria(tree, "set.customDefaultModel");
    assert.equal(model.props.value, "a-model");
    const list = find(tree, (node) => node.type === "datalist");
    assert.equal(model.props.list, list.props.id);
    assert.deepEqual(list.props.children.map((node) => node.props.value), ["a-model", "z-model"]);
    model.props.onChange({ target: { value: "manual-model" } }); tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    assert.equal(byAria(tree, "set.customDefaultModel").props.value, "manual-model");
    assert.equal(changed, 0);
  } finally { harness.close(); Object.assign(api, original); }
});

test("custom model discovery shows busy state and an accessible empty-list hint", async () => {
  const original = { ...api }, harness = hooks(Component); let resolve;
  api.customModels = () => new Promise((done) => { resolve = done; });
  const props = { provider: customProvider, keys: [], available: true, onChanged: async () => assert.fail("Discovery does not change saved keys") };
  try {
    let tree = harness.render(props);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "https://models.example/v1" } }); tree = harness.render(props);
    const loading = find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    const button = find(tree, (node) => node.props?.children === "set.customLoadingModels");
    assert.equal(button.props.busy, true); assert.equal(button.props.disabled, true);
    assert.equal(byAria(tree, "set.customBaseUrl").props.disabled, true);
    assert.equal(find(tree, (node) => node.props?.children === "set.saveKey").props.disabled, true);
    resolve({ models: [] }); await loading; tree = harness.render(props);
    const hint = find(tree, (node) => node.props?.children === "set.customModelsEmpty");
    assert.equal(hint.props.role, "status");
    assert.equal(byAria(tree, "set.customDefaultModel").props["aria-describedby"], hint.props.id);
    assert.equal(byAria(tree, "set.customDefaultModel").props.disabled, false);
    byAria(tree, "set.customDefaultModel").props.onChange({ target: { value: "manual-model" } }); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.children === "set.saveKey").props.disabled, false);
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "https://other.example/v1" } }); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.children === "set.customModelsEmpty"), null);
  } finally { harness.close(); Object.assign(api, original); }
});

test("custom model discovery errors are translated and preserve unsaved fields", async () => {
  const i18n = require("../src/i18n/index.tsx"), original = global.fetch;
  const props = { provider: customProvider, keys: [], available: true, onChanged: async () => {} };
  try {
    for (const [code, status] of [["error.custom_endpoint", 422], ["error.custom_connection", 400]]) {
      global.fetch = async () => new Response(JSON.stringify({ code, detail: "upstream diagnostic" }), { status });
      const harness = hooks(Component);
      try {
        let tree = harness.render(props);
        find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
        byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "https://models.example/v1" } });
        byAria(tree, "set.customDefaultModel").props.onChange({ target: { value: "manual-model" } });
        find(tree, (node) => node.type === TextField && node.props.type === "password").props.onChange({ target: { value: "synthetic-key" } });
        tree = harness.render(props);
        await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
        assert.equal(find(tree, (node) => node.props?.role === "alert").props.children, i18n.translate(code));
        assert.equal(byAria(tree, "set.customBaseUrl").props.value, "https://models.example/v1");
        assert.equal(byAria(tree, "set.customDefaultModel").props.value, "manual-model");
        assert.equal(find(tree, (node) => node.type === TextField && node.props.type === "password").props.value, "synthetic-key");
        assert.equal(find(tree, (node) => node.props?.children === "set.customLoadModels").props.disabled, false);
      } finally { harness.close(); }
    }
  } finally { global.fetch = original; }
});

test("custom model suggestions reset when credentials change or the form is cancelled", async () => {
  const original = { ...api }, harness = hooks(Component);
  api.customModels = async () => ({ models: ["a-model"] });
  const props = { provider: customProvider, keys: [], available: true, onChanged: async () => {} };
  try {
    let tree = harness.render(props);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "https://models.example/v1" } }); tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    assert.ok(find(tree, (node) => node.type === "datalist"));
    find(tree, (node) => node.type === TextField && node.props.type === "password").props.onChange({ target: { value: "replacement-key" } }); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.type === "datalist"), null);
    await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    find(tree, (node) => node.props?.children === "act.cancel").props.onClick(); tree = harness.render(props);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.equal(byAria(tree, "set.customDefaultModel").props.value, "");
    assert.equal(find(tree, (node) => node.type === "datalist"), null);
  } finally { harness.close(); Object.assign(api, original); }
});

test("custom model discovery shows the normalized URL and keeps its API style through save and reset", async () => {
  const original = { ...api }, harness = hooks(Component), loaded = [], saved = [];
  api.customModels = async (body) => { loaded.push(body); return { models: ["a-model"], base_url: "https://models.example/v1", api_style: "responses" }; };
  api.addKey = async (body) => { saved.push(body); return { ...customKey, ...body }; };
  const props = { provider: customProvider, keys: [], available: true, onChanged: async () => {} };
  try {
    let tree = harness.render(props);
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.ok(find(tree, (node) => node.props?.children === "set.customBaseUrlFullHint"));
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "https://models.example/v1/responses" } });
    tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    assert.equal(byAria(tree, "set.customBaseUrl").props.value, "https://models.example/v1");
    await find(tree, (node) => node.props?.children === "set.customLoadModels").props.onClick(); tree = harness.render(props);
    assert.equal(loaded[1].api_style, "responses");
    await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.deepEqual(saved[0], { provider: "custom", api_key: "", label: "", tier: "free", base_url: "https://models.example/v1", default_model: "a-model", api_style: "responses" });
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "https://another.example/v1" } });
    byAria(tree, "set.customDefaultModel").props.onChange({ target: { value: "manual-model" } }); tree = harness.render(props);
    await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick();
    assert.equal(saved[1].api_style ?? "auto", "auto");
  } finally { harness.close(); Object.assign(api, original); }
});

test("custom key rows show explicit API styles and omit the auto badge", () => {
  const harness = hooks(Component), props = { provider: customProvider, available: true, onChanged: async () => {} };
  try {
    let tree = harness.render({ ...props, keys: [{ ...customKey, api_style: "responses" }] });
    assert.ok(find(tree, (node) => node.type === "span" && node.props.children === "responses"));
    tree = harness.render({ ...props, keys: [{ ...customKey, api_style: "chat" }] });
    assert.ok(find(tree, (node) => node.type === "span" && node.props.children === "chat"));
    tree = harness.render({ ...props, keys: [{ ...customKey, api_style: "auto" }] });
    assert.equal(find(tree, (node) => node.type === "span" && node.props.children === "auto"), null);
  } finally { harness.close(); }
});

test("custom endpoint form requires URL/model, permits an empty key, and preserves fields after a failed save", async () => {
  const original = { ...api }, calls = [], harness = hooks(Component); let fail = true;
  api.addKey = async (body) => { calls.push(body); if (fail) throw new Error("Endpoint unreachable"); return customKey; };
  const props = { provider: customProvider, keys: [], available: true, onChanged: async () => {} };
  try {
    let tree = harness.render(props);
    assert.ok(JSON.stringify(tree).includes("set.customProvider"));
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.children === "set.saveKey").props.disabled, true);
    byAria(tree, "set.customBaseUrl").props.onChange({ target: { value: "  http://localhost:11434/v1  " } }); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.children === "set.saveKey").props.disabled, true);
    byAria(tree, "set.customDefaultModel").props.onChange({ target: { value: "  local-model  " } }); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.children === "set.saveKey").props.disabled, false);
    assert.ok(JSON.stringify(tree).includes("set.customKeyOptional"));
    await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.equal(find(tree, (node) => node.props?.role === "alert").props.children, "Endpoint unreachable");
    assert.equal(byAria(tree, "set.customBaseUrl").props.value, "  http://localhost:11434/v1  ");
    assert.equal(byAria(tree, "set.customDefaultModel").props.value, "  local-model  ");
    fail = false; await find(tree, (node) => node.props?.children === "set.saveKey").props.onClick(); tree = harness.render(props);
    assert.deepEqual(calls[1], { provider: "custom", api_key: "", label: "", tier: "free", base_url: customKey.base_url, default_model: customKey.default_model });
    find(tree, (node) => node.props?.children === "set.addKey").props.onClick(); tree = harness.render(props);
    assert.equal(byAria(tree, "set.customBaseUrl").props.value, "");
    assert.equal(byAria(tree, "set.customDefaultModel").props.value, "");
    assert.equal(find(tree, (node) => node.type === TextField && node.props.type === "password").props.value, "");
  } finally { harness.close(); Object.assign(api, original); }
});

test("custom keys display endpoint/model without a fake secret hint, and Settings offers custom before a key exists", async () => {
  const original = { ...api }, harness = hooks(Component);
  try {
    const tree = harness.render({ provider: customProvider, keys: [customKey], available: true, onChanged: async () => {} });
    const content = JSON.stringify(tree);
    assert.ok(content.includes(customKey.base_url) && content.includes(customKey.default_model));
    assert.ok(!content.includes("••••"));
  } finally { harness.close(); }
  const Settings = require("../src/features/settings/Settings.tsx").default, settingsHarness = hooks(Settings);
  api.providers = async () => []; api.listKeys = async () => [];
  try {
    const props = { meta: { mode: "local" }, me: null, initialTab: "keys", onChanged() {}, onClose() {} };
    settingsHarness.render(props); await tick();
    const tree = settingsHarness.render(props);
    const section = find(tree, (node) => node.type === Component && node.props.provider.key === "custom");
    assert.ok(section && section.props.available);
    assert.equal(section.props.provider.name, "set.customProvider");
  } finally { settingsHarness.close(); Object.assign(api, original); }
});

test("custom requests preserve endpoint metadata and localize backend errors", async () => {
  const { ApiError } = require("../src/api/client.ts"), i18n = require("../src/i18n/index.tsx");
  const original = global.fetch, requests = [];
  global.fetch = async (url, init) => { requests.push({ url, body: JSON.parse(init.body) }); return new Response(JSON.stringify(customKey)); };
  try {
    const body = { provider: "custom", base_url: customKey.base_url, default_model: customKey.default_model, api_key: "" };
    assert.deepEqual(await api.addKey(body), customKey);
    assert.deepEqual(requests, [{ url: "/api/ai/keys", body }]);
    for (const [code, status] of [["error.custom_endpoint", 422], ["error.custom_model", 422], ["error.custom_connection", 400]]) {
      global.fetch = async () => new Response(JSON.stringify({ code, detail: "backend diagnostic" }), { status });
      await assert.rejects(api.addKey(body), (error) => error instanceof ApiError && error.code === code && error.message === i18n.translate(code));
    }
  } finally { global.fetch = original; }
});

test("custom key picker tolerates empty hints and loads models for the selected endpoint", async () => {
  const { AIKeyPicker } = require("../src/features/composer/AIKeyPicker.tsx"), { ModelPicker } = require("../src/features/composer/Controls.tsx");
  const original = { ...api }, picker = hooks(AIKeyPicker), calls = [];
  api.listKeys = async () => [customKey];
  api.models = async (...args) => { calls.push(args); return { models: [customKey.default_model], default: customKey.default_model }; };
  let modelNode;
  try {
    const props = { provider: "custom", providerInfo: customProvider, keyId: customKey.id, model: "", onChange() {} };
    picker.render(props); await tick(); const tree = picker.render(props);
    const select = byAria(tree, "cmp.keyLabel");
    assert.ok(JSON.stringify(select).includes(customKey.base_url));
    assert.ok(!JSON.stringify(select).includes("••••"));
    assert.equal(select.props.children.flat(Infinity).find((node) => node?.props?.value === customKey.id).props.disabled, false);
    modelNode = find(tree, (node) => node.type === ModelPicker);
  } finally { picker.close(); }
  const modelHarness = hooks(ModelPicker);
  try {
    modelHarness.render(modelNode.props); await tick(); const tree = modelHarness.render(modelNode.props);
    assert.deepEqual(calls, [["custom", false, customKey.id]]);
    assert.ok(JSON.stringify(tree).includes(customKey.default_model));
  } finally { modelHarness.close(); Object.assign(api, original); }
});

test("Composer and RetryAnalysis expose the localized custom provider and existing key picker", async () => {
  const Composer = require("../src/features/composer/Composer.tsx").default, { RetryAnalysis } = require("../src/features/run/RetryAnalysis.tsx");
  const { AIKeyPicker } = require("../src/features/composer/AIKeyPicker.tsx"), original = { ...api };
  api.providers = async () => [customProvider]; api.profile = async () => null; api.topics = async () => ({ topics: [] });
  for (const [component, props] of [
    [Composer, { meta: { mode: "local", max_posts: 500 }, me: null, platforms: [], prefs: { composer: { ai_provider: "custom", ai_key_id: customKey.id } }, onPrefsChange() {}, onClose() {}, onCreated() {}, onOpenSettings() {} }],
    [RetryAnalysis, { run: { request: { ai_provider: "custom", ai_key_id: customKey.id }, collected: 0 }, onStarted() {} }],
  ]) {
    const harness = hooks(component);
    try {
      harness.render(props); await tick(); const tree = harness.render(props);
      const select = byAria(tree, "cmp.ai");
      assert.ok(JSON.stringify(select).includes("set.customProvider"));
      const picker = find(tree, (node) => node.type === AIKeyPicker);
      assert.equal(picker.props.provider, "custom"); assert.equal(picker.props.keyId, customKey.id);
    } finally { harness.close(); }
  }
  Object.assign(api, original);
});
