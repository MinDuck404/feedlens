const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

// Compile the existing TS modules without a second build or a test dependency.
for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (module, filename) => {
    let source = fs.readFileSync(filename, "utf8").replace("import.meta.env", "({})");
    if (filename.endsWith("Composer.tsx")) source += "\nexport { ModelPicker };";
    if (filename.endsWith("Sidebar.tsx")) source += "\nexport { PlatformRow };";
    module._compile(ts.transpileModule(source, { fileName: filename, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText, filename);
  };
}

const memory = new Map([["feedlens.lang", "en"]]);
global.localStorage = {
  getItem: (key) => memory.get(key) ?? null,
  setItem: (key, value) => memory.set(key, value),
  removeItem: (key) => memory.delete(key),
};
Object.defineProperty(global, "navigator", { configurable: true, value: { languages: ["en-US"] } });
global.window = new EventTarget();
global.document = { documentElement: {} };

const { groupName, parseTimestamp, serialWriter, isRemoteText } = require("../src/logic.ts");
const i18n = require("../src/i18n.tsx");
const { api, ApiError } = require("../src/api.ts");
const React = require("react");

// Exercise hook-based async logic through render/effect/cleanup without browser layout.
function hooks(component) {
  const original = { useState: React.useState, useRef: React.useRef, useEffect: React.useEffect, useMemo: React.useMemo, useCallback: React.useCallback };
  const cells = [];
  let index = 0, pending = [];
  React.useState = (initial) => {
    const at = index++;
    if (!cells[at]) cells[at] = { value: typeof initial === "function" ? initial() : initial };
    return [cells[at].value, (v) => { cells[at].value = typeof v === "function" ? v(cells[at].value) : v; }];
  };
  React.useRef = (initial) => {
    const at = index++;
    return cells[at] ??= { current: initial };
  };
  React.useEffect = (effect, deps) => {
    const at = index++, previous = cells[at];
    if (!previous || deps.some((v, i) => v !== previous.deps[i])) {
      pending.push(() => { previous?.cleanup?.(); cells[at] = { deps, cleanup: effect() }; });
    }
  };
  React.useMemo = (fn) => fn();
  React.useCallback = (fn) => fn;
  return {
    render(props) { index = 0; const result = component(props); const effects = pending; pending = []; effects.forEach((effect) => effect()); return result; },
    close() { cells.forEach((cell) => cell?.cleanup?.()); Object.assign(React, original); },
  };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

test("malformed and Unicode saved group names render without crashing", () => {
  assert.equal(groupName("https://facebook.com/groups/bad%"), "bad%");
  assert.equal(groupName("https://facebook.com/groups/%E4%B8%AD%E6%96%87"), "中文");
  assert.equal(groupName("https://facebook.com/groups/viec-lam/"), "viec lam");
});

test("UTC-naive and signed-offset timestamps refer to the same instant", () => {
  assert.equal(parseTimestamp("2026-11-14T12:00:00").toISOString(), "2026-11-14T12:00:00.000Z");
  assert.equal(parseTimestamp("2026-11-14T07:00:00-05:00").toISOString(), "2026-11-14T12:00:00.000Z");
  assert.equal(parseTimestamp("2026-11-14T19:00:00+07:00").toISOString(), "2026-11-14T12:00:00.000Z");
});

test("remote filter recognizes Vietnamese, English and Chinese", () => {
  for (const text of ["từ xa", "remote", "WFH", "远程工程师", "遠程", "居家办公"]) assert.ok(isRemoteText(text), text);
  assert.equal(isRemoteText("onsite only"), false);
});

test("preference writes remain ordered and recover after a rejected write", async () => {
  const gate = deferred(), calls = [];
  const save = serialWriter(async (value) => { calls.push(value); if (value === 1) await gate.promise; });
  const first = save(1), second = save(2);
  const rejected = assert.rejects(first, /offline/);
  await tick(); assert.deepEqual(calls, [1]);
  gate.reject(new Error("offline"));
  await rejected; await second; assert.deepEqual(calls, [1, 2]);
});

test("locale messages pluralize and external translations follow React without storage", () => {
  assert.equal(i18n.translate("hist.summary", { n: 1, j: 1 }), "1 run, 1 job search");
  assert.equal(i18n.translate("run.nPosts", { n: 1 }), "1 post");
  assert.equal(i18n.translate("run.nPosts", { n: 10000 }), "10,000 posts");
  assert.equal(i18n.translate("cmp.total", { total: 40, n: 1 }), "Up to 40 posts from 1 source");
  assert.equal(i18n.serverMessage("error.request_failed"), "Could not complete the request. Please try again.");
  assert.equal(i18n.serverMessage(undefined, "Could not save cookie preferences", { status: 500 }), "Request failed (500).");
  assert.equal(i18n.serverMessage(undefined, "Cookie facebook đã hết hiệu lực", { status: 400 }), i18n.translate("error.cookie_invalid"));
  const harness = hooks(i18n.I18nProvider);
  const original = localStorage.setItem;
  try {
    localStorage.setItem = () => { throw new Error("storage blocked"); };
    harness.render({ children: null }).props.value.setLang("zh");
    assert.equal(i18n.translate("error.invalid_credentials"), "邮箱或密码错误。");
    assert.equal(i18n.translate("run.andMore", { first: "A", n: 1 }), "A，另有 1 个来源");
    memory.set("feedlens.lang", "vi");
    const event = new Event("storage");
    Object.defineProperty(event, "key", { value: "feedlens.lang" });
    window.dispatchEvent(event);
    assert.equal(harness.render({ children: null }).props.value.lang, "vi");
    assert.equal(i18n.translate("error.invalid_credentials"), "Sai email hoặc mật khẩu.");
    harness.render({ children: null }).props.value.setLang("en");
  } finally { localStorage.setItem = original; harness.close(); }
});

test("large count captions render each localized count once in every locale", () => {
  const harness = hooks(i18n.I18nProvider);
  try {
    for (const [lang, posts, groups, city] of [
      ["vi", "1.234 bài, chia theo loại", "Chọn 1.234/1.234 nhóm sẽ lướt", "Hà Nội"],
      ["en", "1,234 posts, by type", "1,234/1,234 groups selected", "Hanoi"],
      ["zh", "1,234 条帖子，按类型", "已选择 1,234/1,234 个群组", "河内"],
    ]) {
      harness.render({ children: null }).props.value.setLang(lang);
      assert.equal(i18n.translate("run.postsCount", { n: 1234 }), posts);
      assert.equal(i18n.translate("cmp.groupsSelectedCount", { selected: 1234, total: 1234 }), groups);
      assert.equal(i18n.translate("kw.hanoi"), city);
    }
    harness.render({ children: null }).props.value.setLang("en");
    assert.equal(i18n.translate("run.postsCount", { n: 1 }), "1 post, by type");
  } finally {
    harness.render({ children: null }).props.value.setLang("en");
    harness.close();
  }
});

test("all locales have identical keys and interpolation variables", () => {
  const source = fs.readFileSync(require.resolve("../src/i18n.tsx"), "utf8");
  const ast = ts.createSourceFile("i18n.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const dictionaries = {};
  function visit(node) {
    if (ts.isVariableDeclaration(node) && ["vi", "en", "zh"].includes(node.name.getText(ast))) {
      const entries = node.initializer.properties.map((p) => [p.name.text, p.initializer.text]);
      dictionaries[node.name.getText(ast)] = new Map(entries);
      assert.equal(entries.length, dictionaries[node.name.getText(ast)].size, "duplicate dictionary key");
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
  for (const lang of ["en", "zh"]) {
    assert.deepEqual([...dictionaries[lang].keys()].sort(), [...dictionaries.vi.keys()].sort());
    for (const [key, value] of dictionaries.vi) {
      const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
      assert.deepEqual(placeholders(dictionaries[lang].get(key)), placeholders(value), `${lang}: ${key}`);
    }
  }
});

test("login 401 keeps credentials error; protected 401 logs out; 404 keeps status", async () => {
  const original = global.fetch;
  let logouts = 0;
  const onLogout = () => { logouts++; };
  window.addEventListener("feedlens:logout", onLogout);
  try {
    memory.set("feedlens.token", "existing");
    global.fetch = async () => new Response(JSON.stringify({ detail: "Sai email hoặc mật khẩu.", code: "error.invalid_credentials" }), { status: 401 });
    await assert.rejects(api.login("a@b.c", "wrong"), (e) => e.status === 401 && e.message === "Incorrect email or password.");
    assert.equal(logouts, 0); assert.equal(memory.get("feedlens.token"), "existing");
    await assert.rejects(api.me(), (e) => e.status === 401);
    assert.equal(logouts, 1); assert.equal(memory.has("feedlens.token"), false);
    global.fetch = async () => new Response(JSON.stringify({ detail: "not found", code: "error.run_missing" }), { status: 404 });
    await assert.rejects(api.run(4), (e) => e instanceof ApiError && e.status === 404 && e.message === "Run not found.");
    global.fetch = async () => { throw new TypeError("Failed to fetch"); };
    await assert.rejects(api.run(4), (e) => e.status === 0 && e.message.includes("Cannot reach"));
  } finally { global.fetch = original; window.removeEventListener("feedlens:logout", onLogout); }
});

test("queued preferences never cross into the next logged-in account", async () => {
  const original = global.fetch, gate = deferred();
  let calls = 0;
  try {
    memory.set("feedlens.token", "account-a");
    global.fetch = async () => { calls++; await gate.promise; return new Response("{}"); };
    const first = api.savePreferences({}), second = api.savePreferences({});
    const rejected = assert.rejects(second, (e) => e.status === 401);
    await tick(); memory.set("feedlens.token", "account-b"); gate.resolve();
    await first; await rejected; assert.equal(calls, 1);
  } finally { global.fetch = original; memory.delete("feedlens.token"); }
});

test("late model responses cannot replace the current provider or latest refresh", async () => {
  const { ModelPicker } = require("../src/components/Composer.tsx");
  const original = api.models, requests = [];
  const originalContext = React.useContext;
  React.useContext = () => ({ t: i18n.translate });
  api.models = () => { const request = deferred(); requests.push(request); return request.promise; };
  const harness = hooks(ModelPicker);
  try {
    harness.render({ provider: "gemini", value: "", onChange() {} });
    harness.render({ provider: "openai", value: "", onChange() {} });
    requests[1].resolve({ models: ["new-model"], default: "new-model" }); await tick();
    requests[0].resolve({ models: ["stale-model"], default: "stale-model" }); await tick();
    const result = harness.render({ provider: "openai", value: "", onChange() {} });
    assert.ok(JSON.stringify(result).includes("new-model"));
    assert.ok(!JSON.stringify(result).includes("stale-model"));
    result.props.children[1].props.onClick();
    result.props.children[1].props.onClick();
    requests[3].resolve({ models: ["latest-refresh"], default: "latest-refresh" }); await tick();
    requests[2].resolve({ models: ["old-refresh"], default: "old-refresh" }); await tick();
    assert.ok(JSON.stringify(harness.render({ provider: "openai", value: "", onChange() {} })).includes("latest-refresh"));
  } finally { harness.close(); api.models = original; React.useContext = originalContext; }
});

test("run polling backs off after transient errors, recovers, and only 404 means missing", async () => {
  const RunView = require("../src/components/RunView.tsx").default;
  const original = api.run, timers = [], oldTimer = window.setTimeout, oldClear = global.clearTimeout;
  window.setTimeout = (callback, delay) => { timers.push({ callback, delay }); return timers.length; };
  global.clearTimeout = () => {};
  const context = hooks(i18n.I18nProvider);
  const value = context.render({ children: null }).props.value;
  context.close();
  const originalContext = React.useContext; React.useContext = () => value;
  let attempt = 0;
  api.run = async () => { if (++attempt < 3) throw new ApiError(0, undefined, "", "offline"); return { id: 1, status: "scraping", request: { platform: "facebook", source_type: "feed" }, created_at: "2026-11-14T12:00:00" }; };
  const harness = hooks(RunView);
  const props = { runId: 1, tab: "digest", meta: {}, onTab() {}, onDeleted() {} };
  try {
    harness.render(props); await tick();
    assert.ok(JSON.stringify(harness.render(props)).includes("Retrying")); assert.equal(timers[0].delay, 1500);
    await timers[0].callback(); await tick(); assert.equal(timers[1].delay, 3000);
    await timers[1].callback(); await tick(); assert.equal(timers[2].delay, 1500);
    assert.ok(!JSON.stringify(harness.render(props)).includes("Retrying"));
    api.run = async () => { throw new ApiError(404, "error.run_missing", "", "missing"); };
    await timers[2].callback(); await tick();
    assert.ok(JSON.stringify(harness.render(props)).includes("not found")); assert.equal(timers.length, 3);
  } finally { harness.close(); React.useContext = originalContext; api.run = original; window.setTimeout = oldTimer; global.clearTimeout = oldClear; }
});


test("saved sessions remain unchecked until verification and offer login only when needed", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { PlatformRow } = require("../src/components/Sidebar.tsx");
  for (const [has_profile, logged_in, login_state, buttons, login] of [
    [true, null, "idle", 1, null],
    [true, false, "idle", 3, "plat.relogin"],
    [true, true, "idle", 2, null],
    [false, null, "idle", 1, "plat.login"],
    [true, null, "waiting", 1, null],
  ]) {
    const html = renderToStaticMarkup(React.createElement(i18n.I18nProvider, null,
      React.createElement(PlatformRow, { p: { key: "facebook", name: "Facebook", has_profile, logged_in, login_state }, onChanged() {}, onLogin() {} })));
    assert.equal((html.match(/<button\b/g) || []).length, buttons);
    if (login) assert.ok(html.includes(i18n.translate(login)));
    else assert.ok(!html.includes(i18n.translate("plat.relogin")));
    if (has_profile && logged_in === null && login_state === "idle") assert.ok(html.includes(i18n.translate("plat.saved")));
  }
});


test("match type filtering preserves legacy jobs and isolates primary, adjacent and stretch", () => {
  const { matchesJobType } = require("../src/logic.ts");
  const types = ["primary", "adjacent", "stretch", "none", null, undefined];
  assert.equal(types.filter((type) => matchesJobType(type, "all")).length, 6);
  assert.deepEqual(types.filter((type) => matchesJobType(type, "primary")), ["primary"]);
  assert.deepEqual(types.filter((type) => matchesJobType(type, "adjacent")), ["adjacent"]);
  assert.deepEqual(types.filter((type) => matchesJobType(type, "stretch")), ["stretch"]);
  assert.deepEqual(types.filter((type) => matchesJobType(type, "none")), ["none", null, undefined]);
});
