const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

// Compile the existing TS modules without a second build or a test dependency.
for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (module, filename) => {
    let source = fs.readFileSync(filename, "utf8").replace("import.meta.env", "({})");
    if (filename.endsWith("Sidebar.tsx")) source += "\nexport { PlatformRow, SidebarBody };";
    if (filename.endsWith("RunView.tsx")) source += "\nexport { PostSources, JobsBoard, ReadingPost, InProgress, Done };";
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

test("analyzing view exposes actual model, quota retry time and stop/change controls", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { InProgress, Done } = require("../src/components/RunView.tsx");
  const run = { id: 9, status: "analyzing", request: { platform: "facebook" }, digest: null,
    progress: { phase: "analyzing", done: 1, target: 2, ai: { state: "quota_wait", provider: "Gemini", model: "actual", key_label: "Work key", retry_at: 2000000000 } },
    posts: [{ id: 1, fingerprint: "a", category: "news", summary: "Read", text: "Read text", analyzed: true, source: "Feed", platform: "facebook", topic_ids: [] },
      { id: -2, fingerprint: "b", category: "other", text: "Raw waiting text", analyzed: false, source: "Feed", platform: "facebook", topic_ids: [] }] };
  const render = (element) => renderToStaticMarkup(React.createElement(i18n.I18nProvider, null, element));
  const progress = render(React.createElement(InProgress, { run, onStarted() {} }));
  assert.ok(progress.includes("actual") && progress.includes("Work key"));
  assert.ok(progress.includes(i18n.translate("run.stopAI")));
  assert.ok(progress.includes(i18n.translate("run.changeModel")));
  assert.ok(progress.includes("<time"));
  const posts = render(React.createElement(Done, { run, meta: {}, tab: "digest", setTab() {} }));
  assert.ok(posts.includes("Raw waiting text"));
  assert.ok(posts.includes(i18n.translate("run.aiUnread").replaceAll("'", "&#x27;")));
  assert.ok(!posts.includes('id="run-9-tab-digest"'));
});

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

test("grouped posts show every original source on job and reading cards without increasing job counts", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { JobsBoard, ReadingPost, PostSources } = require("../src/components/RunView.tsx");
  const p = { id: 8, text: "Job text", summary: "Python developer", category: "job", source: "Group A", author: "Recruiter", url: "https://example.test/1",
    job: { title: "Python developer", company: "Acme", match_score: 90, work_mode: "remote" },
    sources: [{ source: "Group A", url: "https://example.test/1" }, { source: "Group B", url: "https://example.test/2" }] };
  const render = (element) => renderToStaticMarkup(React.createElement(i18n.I18nProvider, null, element));
  for (const element of [React.createElement(JobsBoard, { jobs: [p], runId: 1 }), React.createElement(ReadingPost, { p, name: () => "Jobs", topics: [] })]) {
    const html = render(element);
    assert.ok(html.includes(i18n.translate("posts.postedInGroups", { n: 2 })));
    assert.ok(html.includes('href="https://example.test/1"'));
    assert.ok(html.includes('href="https://example.test/2"'));
    assert.equal((html.match(/<li\b/g) || []).length, 1);
  }
  assert.equal(render(React.createElement(PostSources, { p: { ...p, sources: undefined } })), "");
  const sameGroup = render(React.createElement(PostSources, { p: { ...p, sources: p.sources.map((s) => ({ ...s, source: "Group A" })) } }));
  assert.ok(sameGroup.includes(i18n.translate("posts.postedInSameGroup", { n: 2 })));
  assert.ok(sameGroup.includes("size-3 shrink-0"));
  const unsafe = render(React.createElement(PostSources, { p: { ...p, sources: [p.sources[0], { source: "Unsafe", url: "javascript:alert(1)" }] } }));
  assert.ok(!unsafe.includes('href="javascript:'));
});

test("malformed and Unicode saved group names render without crashing", () => {
  assert.equal(groupName("https://facebook.com/groups/bad%"), "bad%");
  assert.equal(groupName("https://facebook.com/groups/%E4%B8%AD%E6%96%87"), "中文");
  assert.equal(groupName("https://facebook.com/groups/viec-lam/"), "viec lam");
});

test("source scrape rows use saved names and treat missing status as complete", () => {
  const { scrapeSourceRows } = require("../src/logic.ts");
  const rows = scrapeSourceRows([
    { label: "https://facebook.com/groups/tech/", target: 5, collected: 4, skipped_old: 0, stop_reason: "target_reached" },
    { label: "https://facebook.com/groups/123/", target: 20, collected: 0, skipped_old: 7, stop_reason: "caught_up", status: "running" },
    { label: "https://facebook.com/groups/viec-lam/", target: 10, collected: 10, skipped_old: 0, stop_reason: "target_reached", status: "pending" },
  ], [{ url: "https://facebook.com/groups/123", name: "Engineering jobs" }]);

  assert.deepEqual(rows, [
    { name: "Engineering jobs", target: 20, collected: 0, skipped_old: 7, skipped_dup: 0, stop_reason: "caught_up", status: "running" },
    { name: "viec lam", target: 10, collected: 10, skipped_old: 0, skipped_dup: 0, stop_reason: "target_reached", status: "pending" },
    { name: "tech", target: 5, collected: 4, skipped_old: 0, skipped_dup: 0, stop_reason: "target_reached", status: "done" },
  ]);
});

test("offline completed run can offer full AI reanalysis", () => {
  const { canReanalyzeOffline } = require("../src/logic.ts");
  assert.equal(canReanalyzeOffline({ status: "done", ai_label: "bộ lọc từ khóa offline", posts: [{}] }), true);
  assert.equal(canReanalyzeOffline({ status: "analyzing", ai_label: "bộ lọc từ khóa offline", posts: [{}] }), false);
  assert.equal(canReanalyzeOffline({ status: "done", ai_label: "OpenAI", posts: [{}] }), false);
  assert.equal(canReanalyzeOffline({ status: "done", ai_label: "offline", can_reanalyze_ai: true }), true);
});

test("run source descriptions localize new modes and retain legacy surface labels", () => {
  const { describeRunSource } = require("../src/logic.ts");
  const context = hooks(i18n.I18nProvider);
  try {
    for (const lang of ["vi", "en", "zh"]) {
      context.render({ children: null }).props.value.setLang(lang);
      const translate = (key, vars) => i18n.translate(key, vars);
      const jobs = describeRunSource({ platform: "linkedin", source_type: "search", sources: ["Python"], mode: "jobs",
        options: { keywords: "Python", location: "Hà Nội", work_modes: ["remote"], posted_within: "week" } }, translate);
      assert.ok(jobs.includes("LinkedIn") && jobs.includes("Python") && jobs.includes("Hà Nội"));
      assert.ok(jobs.includes(translate("profile.mode.remote")) && jobs.includes(translate("source.period.week")));
      const pages = describeRunSource({ platform: "facebook", source_type: "group", sources: ["a", "b", "c"], mode: "page" }, translate);
      assert.ok(pages.includes(translate("source.pages", { n: 3 })));
      const reddit = describeRunSource({ platform: "reddit", source_type: "group", sources: ["https://reddit.com/r/forhire/new/"], mode: "subreddit", options: { sort: "new" } }, translate);
      assert.ok(reddit.includes("r/forhire") && reddit.includes(translate("source.sort.new")));
      const legacy = { platform: "facebook", source_type: "group", sources: ["https://www.facebook.com/groups/a/"] };
      assert.equal(describeRunSource(legacy, translate), legacy.sources[0]);
      assert.equal(describeRunSource(legacy, translate, "history"), "facebook.com/groups/a");
      assert.equal(describeRunSource({ ...legacy, source_type: "feed" }, translate, "sidebar"), translate("sb.feed"));
    }
  } finally { context.render({ children: null }).props.value.setLang("en"); context.close(); }
});

test("Jobs default only applies to bare LinkedIn Jobs URLs", () => {
  const { defaultRunTab } = require("../src/logic.ts");
  const req = { platform: "linkedin", mode: "jobs" };
  assert.equal(defaultRunTab(req, "#/runs/12"), "jobs");
  assert.equal(defaultRunTab(req, "#/runs/12?foo=bar"), "jobs");
  for (const url of ["#/runs/12/digest", "#/runs/12/posts", "#/runs/12/jobs"]) assert.equal(defaultRunTab(req, url), null);
  assert.equal(defaultRunTab({ platform: "linkedin" }, "#/runs/12"), null);
  assert.equal(defaultRunTab({ platform: "facebook", mode: "jobs" }, "#/runs/12"), null);
});

test("observed job seed takes precedence without changing AI assessment or original data", () => {
  const { jobPresentation } = require("../src/logic.ts");
  const post = { url: "https://example.com/wrong", job: { title: "AI title", company: "AI company", location: "AI location", salary: "AI salary", work_mode: "onsite", match_score: 88, contact: "hr@example.test", match_reason: "CV fits" },
    job_seed: { title: "Python", company: "Observed company", location: "Hà Nội", salary_text: "30M", work_mode: "remote", url: "https://www.linkedin.com/jobs/view/123/" } };
  const result = jobPresentation(post);
  assert.equal(result.job.company, "Observed company"); assert.equal(result.job.salary, "30M");
  assert.equal(result.job.work_mode, "remote"); assert.equal(result.job.match_score, 88);
  assert.equal(result.url, post.job_seed.url); assert.equal(post.job.company, "AI company");
  assert.equal(jobPresentation({ ...post, job: null }).job.title, "Python");
  assert.equal(jobPresentation({ ...post, job_seed: null }).url, post.url);
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

test("API run detail supports metadata polling without changing default requests", async () => {
  const original = global.fetch, requests = [];
  global.fetch = async (url) => { requests.push(url); return new Response("{}"); };
  try {
    await api.run(42); await api.run(42, false);
    assert.deepEqual(requests, ["/api/runs/42", "/api/runs/42?posts=0"]);
  } finally { global.fetch = original; }
});

test("active run polling keeps posts, throttles full refreshes, and loads final results", async () => {
  const RunView = require("../src/components/RunView.tsx").default;
  const original = api.run, originalContext = React.useContext, oldTimer = window.setTimeout, oldClear = global.clearTimeout, oldNow = Date.now;
  const context = hooks(i18n.I18nProvider), value = context.render({ children: null }).props.value; context.close();
  const timers = [], calls = []; let now = 0, version = 0, status = "scraping";
  const oldHidden = document.hidden;
  Date.now = () => now; document.hidden = false;
  React.useContext = () => value;
  window.setTimeout = (callback, delay) => { timers.push({ callback, delay }); return timers.length; };
  global.clearTimeout = () => {};
  const post = { id: 1, category: "news", analyzed: true, text: "Previously loaded post", source: "feed", platform: "facebook", posted_at: "", url: "", summary: "News", author: "Author", job: null };
  api.run = async (id, posts = true) => {
    calls.push({ posts, now });
    return { id, status, posts_version: version, request: { platform: "facebook", source_type: "feed", ai_provider: "offline", ai_model: "" },
      created_at: "2026-11-14T12:00:00Z", ...(posts ? { posts: [post] } : {}) };
  };
  const harness = hooks(RunView), props = { runId: 1, tab: "posts", meta: {}, onTab() {}, onDeleted() {} };
  const poll = async (time) => { now = time; await timers.shift().callback(); await tick(); };
  try {
    harness.render(props); await tick();
    assert.deepEqual(calls.map((call) => call.posts), [false, true]);
    await poll(1500); assert.equal(calls.at(-1).posts, false);
    status = "analyzing"; version = 20; await poll(3000);
    assert.deepEqual(calls.slice(-2).map((call) => call.posts), [false, true]);
    version = 40; await poll(4500);
    assert.equal(calls.at(-1).posts, false);
    assert.ok(JSON.stringify(harness.render(props)).includes("Previously loaded post"));
    await poll(13000); assert.equal(calls.at(-1).posts, true);
    document.hidden = true; await poll(14500); assert.equal(timers.at(-1).delay, 10000);
    status = "done"; version = 500; await poll(24500);
    assert.deepEqual(calls.slice(-2).map((call) => call.posts), [false, true]);
    assert.equal(timers.length, 0);
  } finally {
    harness.close(); api.run = original; React.useContext = originalContext; window.setTimeout = oldTimer;
    global.clearTimeout = oldClear; Date.now = oldNow; document.hidden = oldHidden;
  }
});

test("workspace polling uses 5s active, 15s hidden, and 2s login checks", () => {
  const { workspacePollDelay } = require("../src/App.tsx");
  assert.equal(workspacePollDelay(true, false, false), 5000);
  assert.equal(workspacePollDelay(true, false, true), 15000);
  assert.equal(workspacePollDelay(false, false, false), 15000);
  assert.equal(workspacePollDelay(true, true, false), 2000);
  assert.equal(workspacePollDelay(true, true, true), 2000);
});


test("saved sessions remain unchecked until verification and offer login only when needed", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { PlatformRow } = require("../src/components/Sidebar.tsx");
  for (const [has_profile, logged_in, login_state, buttons, login] of [
    [true, null, "idle", 3, "plat.relogin"],
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

test("browser notices appear once above all account rows while platform errors stay local", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { SidebarBody } = require("../src/components/Sidebar.tsx");
  const base = ["facebook", "linkedin", "x", "reddit"].map((key) => ({ key, name: key, logged_in: null, has_profile: false, login_state: "idle" }));
  const render = (change) => renderToStaticMarkup(React.createElement(i18n.I18nProvider, null,
    React.createElement(SidebarBody, { cloud: false, platforms: base.map((p) => ({ ...p, ...change })), runs: [], page: "home", onOpenSettings() {}, onPlatformChanged() {} })));
  for (const state of [{ missing: true }, { browser: "msedge" }, { browser: "chromium", oauth_limited: true }]) {
    const html = render(state);
    assert.equal((html.match(/href="https:\/\/www.google.com\/chrome\/"/g) || []).length, state.browser === "msedge" ? 0 : 1);
    assert.equal((html.match(/<button\b[^>]*aria-label="Sign in:/g) || []).length, 4);
  }
  assert.ok(render({ missing: true }).includes(i18n.translate("plat.browserMissing")));
});

test("waiting platform exposes a manual finish action", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { PlatformRow } = require("../src/components/Sidebar.tsx");
  const html = renderToStaticMarkup(React.createElement(i18n.I18nProvider, null,
    React.createElement(PlatformRow, { p: { key: "facebook", name: "Facebook", has_profile: true, logged_in: null, login_state: "waiting" }, onChanged() {}, onLogin() {} })));
  assert.ok(html.includes(i18n.translate("plat.finishLogin")));
});

test("manual sign-in finish uses the dedicated platform endpoint", async () => {
  const original = global.fetch, requests = [];
  global.fetch = async (url, init) => { requests.push([url, init.method]); return new Response("{}"); };
  try {
    await api.platformAction("facebook", "login/finish");
    assert.deepEqual(requests, [["/api/platforms/facebook/login/finish", "POST"]]);
  } finally { global.fetch = original; }
});

test("browser login errors, download links and Edge/Chromium notes remain visible with recovery actions", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { PlatformRow } = require("../src/components/Sidebar.tsx");
  const base = { key: "facebook", name: "Facebook", has_profile: true, logged_in: null, login_state: "idle" };
  const render = (p) => renderToStaticMarkup(React.createElement(i18n.I18nProvider, null,
    React.createElement(PlatformRow, { p: { ...base, ...p }, onChanged() {}, onLogin() {} })));
  const missing = render({ missing: true });
  assert.ok(!missing.includes('href="https://www.google.com/chrome/"'));
  assert.equal((missing.match(/<button\b/g) || []).length, 3);
  const failed = render({ login_error: "profile locked", login_error_code: "error.browser_failed" });
  assert.ok(failed.includes('title="profile locked"'));
  assert.ok(failed.includes(i18n.translate("error.browser_failed")));
  const edge = render({ browser: "msedge" });
  assert.ok(!edge.includes(i18n.translate("plat.edgeNote")));
  const chromium = render({ browser: "chromium", oauth_limited: true });
  assert.ok(!chromium.includes(i18n.translate("plat.chromiumNote")));
});

test("background session checks show a spinner and suppress reconnect until complete", () => {
  const { renderToStaticMarkup } = require("react-dom/server");
  const { PlatformRow } = require("../src/components/Sidebar.tsx");
  const html = renderToStaticMarkup(React.createElement(i18n.I18nProvider, null,
    React.createElement(PlatformRow, { p: { key: "facebook", name: "Facebook", has_profile: true, logged_in: false, login_state: "idle", checking: true }, onChanged() {}, onLogin() {} })));
  assert.ok(html.includes(i18n.translate("plat.checking")));
  assert.ok(html.includes("animate-spin"));
  assert.equal((html.match(/<button\b/g) || []).length, 0);
});

test("analysis failures stop polling and keep saved posts available", async () => {
  const RunView = require("../src/components/RunView.tsx").default;
  const original = api.run, oldTimer = window.setTimeout;
  const timers = [];
  window.setTimeout = (...args) => timers.push(args);
  const context = hooks(i18n.I18nProvider);
  const value = context.render({ children: null }).props.value; context.close();
  const originalContext = React.useContext; React.useContext = () => value;
  api.run = async () => ({ id: 1, status: "analysis_failed", request: { platform: "facebook", source_type: "feed", ai_provider: "offline", ai_model: "" }, created_at: "2026-11-14T12:00:00Z", posts: [{ id: -1, analyzed: false, text: "Saved post" }], error_code: "error.ai_quota" });
  const harness = hooks(RunView);
  const props = { runId: 1, tab: "posts", meta: {}, onTab() {}, onDeleted() {} };
  try {
    harness.render(props); await tick();
    const result = JSON.stringify(harness.render(props));
    assert.ok(result.includes("quota") && result.includes("Saved post"));
    assert.ok(result.includes("Saved posts"));
    assert.equal(timers.length, 0);
  } finally { harness.close(); React.useContext = originalContext; api.run = original; window.setTimeout = oldTimer; }
});

test("interrupted AI upgrades show real coverage and offer only remaining posts", async () => {
  const RunView = require("../src/components/RunView.tsx").default;
  const originalRun = api.run, originalProviders = api.providers, originalContext = React.useContext;
  const context = hooks(i18n.I18nProvider), value = context.render({ children: null }).props.value;
  context.close(); React.useContext = () => value;
  api.providers = async () => [];
  api.run = async () => ({ id: 14, status: "analysis_failed", can_continue_analysis: true,
    request: { platform: "facebook", source_type: "feed", ai_provider: "openai", ai_model: "fake" },
    analysis_counts: { ai: 20, offline: 1180, pending: 0, total: 1200 },
    created_at: "2026-11-14T12:00:00Z", error_code: "error.ai_quota", posts: [] });
  const harness = hooks(RunView), props = { runId: 14, tab: "posts", meta: {}, onTab() {}, onDeleted() {} };
  try {
    harness.render(props); await tick();
    const result = harness.render(props), rendered = JSON.stringify(result);
    assert.ok(rendered.includes(i18n.translate("run.analysisCounts", { ai: 20, offline: 1180, total: 1200 })));
    assert.ok(rendered.includes(i18n.translate("run.aiQuotaSaved", { total: 1200, ai: 20 })));
    let retry;
    const visit = (node) => {
      if (!React.isValidElement(node)) return;
      if (node.type.name === "RetryAnalysis") retry = node;
      React.Children.forEach(node.props.children, visit);
    };
    visit(result); assert.ok(retry);
    const retryHarness = hooks(retry.type);
    try {
      const content = JSON.stringify(retryHarness.render(retry.props));
      assert.ok(content.includes(i18n.translate("run.retryAIHint", { n: 1180 })));
      assert.ok(content.includes(i18n.translate("run.sendRemainingAI")));
      await tick();
    } finally { retryHarness.close(); }
  } finally { harness.close(); React.useContext = originalContext; api.run = originalRun; api.providers = originalProviders; }
});

test("completed AI runs offer confirmed reanalysis with an estimated request count", async () => {
  const RunView = require("../src/components/RunView.tsx").default;
  const originalRun = api.run, originalProviders = api.providers, originalRetry = api.retryAnalysis;
  const originalContext = React.useContext, originalConfirm = window.confirm;
  const context = hooks(i18n.I18nProvider), value = context.render({ children: null }).props.value;
  context.close(); React.useContext = () => value;
  const prompts = [], requests = [];
  let allowed = false;
  window.confirm = (message) => { prompts.push(message); return allowed; };
  api.providers = async () => [];
  api.run = async () => ({ id: 14, status: "done", ai_label: "Gemini", can_continue_analysis: false,
    can_reanalyze_ai: false, can_reprocess_ai: true, reanalyze_requests_estimate: 28,
    analysis_counts: { ai: 1200, offline: 0, pending: 0, total: 1200 },
    request: { platform: "facebook", source_type: "group", ai_provider: "gemini", ai_model: "gemini-3.5-flash-lite" },
    created_at: "2026-11-14T12:00:00Z", digest: { overall: "Done", categories: [], action_items: [] }, posts: [] });
  api.retryAnalysis = async (...args) => requests.push(args);
  const harness = hooks(RunView), props = { runId: 14, tab: "digest", meta: {}, onTab() {}, onDeleted() {} };
  try {
    harness.render(props); await tick();
    const tree = harness.render(props);
    let retryNode;
    const visit = (node) => {
      if (!React.isValidElement(node)) return;
      if (node.type.name === "RetryAnalysis" && node.props.reanalyzeAll) retryNode = node;
      React.Children.forEach(node.props.children, visit);
    };
    visit(tree); assert.ok(retryNode);
    const retryHarness = hooks(retryNode.type);
    try {
      const retryTree = retryHarness.render(retryNode.props);
      await tick();
      let button;
      const findButton = (node) => {
        if (!React.isValidElement(node)) return;
        if (typeof node.props.onClick === "function") button = node;
        React.Children.forEach(node.props.children, findButton);
      };
      findButton(retryHarness.render(retryNode.props)); assert.ok(button);
      await button.props.onClick();
      assert.equal(requests.length, 0);
      assert.ok(prompts[0].includes("1,200") && prompts[0].includes("28"));
      allowed = true;
      await button.props.onClick();
      assert.deepEqual(requests, [[14, "auto", "gemini-3.5-flash-lite", "reanalyze_all"]]);
    } finally { retryHarness.close(); }
  } finally {
    harness.close(); React.useContext = originalContext; window.confirm = originalConfirm;
    api.run = originalRun; api.providers = originalProviders; api.retryAnalysis = originalRetry;
  }
});

test("theme preference applies explicit overrides and restores system styling before render", () => {
  const vm = require("node:vm");
  const html = fs.readFileSync(require.resolve("../index.html"), "utf8");
  const bootstrap = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const classes = new Set();
  const root = { dataset: {}, classList: { add: (value) => classes.add(value), remove: (value) => classes.delete(value), toggle: (value, on) => on ? classes.add(value) : classes.delete(value) } };
  vm.runInNewContext(bootstrap, { localStorage: { getItem: () => "dark" }, document: { documentElement: root } });
  assert.equal(root.dataset.theme, "dark");
  assert.ok(classes.has("dark"));
  const original = global.document;
  global.document = { documentElement: root };
  try {
    const { getThemePreference, setThemePreference } = require("../src/theme.ts");
    assert.equal(getThemePreference(), "dark");
    setThemePreference("light");
    assert.equal(root.dataset.theme, "light"); assert.ok(classes.has("light") && !classes.has("dark"));
    setThemePreference("system");
    assert.equal(root.dataset.theme, undefined); assert.equal(classes.size, 0);
    assert.equal(memory.get("feedlens.theme"), "system");
  } finally { global.document = original; }
});

test("continue analysis depends on saved content, not the failure status name", () => {
  const { canContinueAnalysis } = require("../src/logic.ts");
  for (const status of ["error", "analysis_failed", "done"]) {
    assert.equal(canContinueAnalysis({ status, posts: [{ analyzed: true }], digest: null }), true);
    assert.equal(canContinueAnalysis({ status, posts: [{ analyzed: false }], digest: {} }), true);
    assert.equal(canContinueAnalysis({ status, posts: [{ analyzed: true }], digest: {} }), false);
    assert.equal(canContinueAnalysis({ status, posts: [] }), false);
  }
  assert.equal(canContinueAnalysis({ status: "error", posts: [{ summary: "legacy" }] }), true);
  for (const status of ["pending", "queued", "scraping", "analyzing"]) {
    assert.equal(canContinueAnalysis({ status, posts: [{ analyzed: false }], can_continue_analysis: true }), false);
  }
});


test("topic filters combine safely with category filters and support multiple tags", () => {
  const { filterTopicPosts, TOPIC_INKS, topicColor } = require("../src/topics.ts");
  const posts = [{ id: 1, category: "tech", topic_ids: [4, 7] }, { id: 2, category: "job", topic_ids: [7] }, { id: 3, category: "tech" }];
  assert.equal(filterTopicPosts(posts, null), posts);
  assert.deepEqual(filterTopicPosts(posts, 4).map((p) => p.id), [1]);
  assert.deepEqual(filterTopicPosts(posts, 7).map((p) => p.id), [1, 2]);
  assert.deepEqual(filterTopicPosts(posts.filter((p) => p.category === "tech"), 7).map((p) => p.id), [1]);
  assert.deepEqual(filterTopicPosts(posts, 99), []);
  assert.equal(Object.keys(TOPIC_INKS).length, 16);
  assert.equal(topicColor("unknown"), topicColor("red"));
});

test("topics CRUD, quick test and background progress use the backend contract", async () => {
  const original = global.fetch;
  const requests = [];
  global.fetch = async (url, init) => { requests.push([url, init.method ?? "GET", init.body ? JSON.parse(init.body) : null]); return new Response(JSON.stringify({ topics: [], state: "idle" })); };
  try {
    const topic = { name: "React", description: "React work", enabled: true, color: "navy", include_keywords: ["react"], exclude_keywords: [] };
    await api.topics(); await api.saveTopic(topic); await api.saveTopic({ ...topic, id: 12 });
    await api.deleteTopic(12); await api.testTopics("React post"); await api.applyTopics(); await api.topicsProgress();
    assert.deepEqual(requests.map(([url, method]) => [url, method]), [
      ["/api/topics", "GET"], ["/api/topics", "POST"], ["/api/topics/12", "PUT"], ["/api/topics/12", "DELETE"],
      ["/api/topics/test", "POST"], ["/api/topics/apply", "POST"], ["/api/topics/apply", "GET"],
    ]);
    assert.deepEqual(requests[1][2], topic);
    assert.deepEqual(requests[4][2], { text: "React post" });
  } finally { global.fetch = original; }
});


test("trend paths stay within a zero-based plot and handle one point", () => {
  const { trendPoints, trendPath, trendColor } = require("../src/trends.ts");
  const points = trendPoints([0, 4, 0, 2], 730, 280, 4);
  assert.deepEqual(points.map((p) => p.y), [280, 0, 280, 140]);
  assert.ok(points.every((p) => p.x >= 0 && p.x <= 730 && p.y >= 0 && p.y <= 280));
  assert.deepEqual(trendPoints([0], 100, 40, 4), [{ x: 50, y: 40 }]);
  assert.ok(trendPoints([-1, 8], 100, 40, 4).every((p) => p.y >= 0 && p.y <= 40));
  assert.equal(trendPath(points).includes("C"), false);
  assert.match(trendColor("#2B5C8F"), /#6D9ECE/);
});

test("changing trend filters cannot be overwritten by an older response", async () => {
  const TrendsPage = require("../src/components/TrendsPage.tsx").default;
  const original = api.trends, originalContext = React.useContext;
  const context = hooks(i18n.I18nProvider);
  const value = context.render({ children: null }).props.value; context.close(); React.useContext = () => value;
  const requests = [];
  api.trends = (params) => { const gate = deferred(); requests.push({ params, ...gate }); return gate.promise; };
  const harness = hooks(TrendsPage);
  const props = { onNewRun() {} };
  const find = (node, label) => {
    if (!node || typeof node !== "object") return null;
    if (node.props?.label === label) return node;
    for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, label); if (found) return found; }
    return null;
  };
  const response = (group, title) => ({ range: { group, days: 30, bucket: "day", start_date: "2026-11-01", end_date: "2026-11-30" }, timeline: ["2026-11-01"], series: [{ id: "1", name: title, color: "#AE3824", counts: [1], total: 1, growth: null }], summary: { total_posts: 1, top_gainer: null, new_emerging: null }, fallback_count: 0 });
  try {
    const tree = harness.render(props);
    find(tree, i18n.translate("trends.group")).props.onChange("topic");
    harness.render(props);
    assert.equal(requests.length, 2);
    requests[1].resolve(response("topic", "Latest topic")); await tick();
    requests[0].resolve(response("category", "Old category")); await tick();
    const rendered = JSON.stringify(harness.render(props));
    assert.ok(rendered.includes("Latest topic")); assert.ok(!rendered.includes("Old category"));
  } finally { harness.close(); api.trends = original; React.useContext = originalContext; }
});


test("search links preserve repeated filters and explicit false without accepting unknown keys", () => {
  const { searchParams, readSearchParams, trendSearchFilters } = require("../src/search.ts");
  const { parseRoute, routeHref } = require("../src/router.ts");
  const filters = { q: "React & 中文", categories: ["job", "tech"], topic_ids: [3, 5], has_link: false, min_score: 0 };
  assert.deepEqual(readSearchParams(searchParams(filters)), filters);
  assert.deepEqual(parseRoute(routeHref({ page: "ask", filters })), { page: "ask", filters });
  assert.deepEqual(readSearchParams(new URLSearchParams("unknown=x&topic_ids=bad&has_link=oops")), { topic_ids: [] });
  const weekly = { range: { group: "topic", bucket: "week", start_date: "2026-11-12", end_date: "2026-11-18" } };
  assert.deepEqual(trendSearchFilters(weekly, "3", "2026-11-09"), { topic_ids: [3], date_from: "2026-11-12", date_to: "2026-11-15" });
});

test("snippet and citation tokens keep markup inert and link only returned post IDs", () => {
  const { textParts, questionHistory } = require("../src/search.ts");
  assert.deepEqual(textParts('<img src=x onerror=alert(1)> «React»', "snippet"), [{ text: '<img src=x onerror=alert(1)> ' }, { text: "React", highlight: true }]);
  assert.deepEqual(textParts("See [#12] and [#999]", "citation", [12]), [{ text: "See " }, { text: "[#12]", id: 12 }, { text: " and " }, { text: "[#999]" }]);
  const history = questionHistory(Array.from({ length: 30 }, (_, i) => `Question ${i}`), "Question 5");
  assert.equal(history.length, 20); assert.equal(history[0], "Question 5"); assert.equal(history.filter((value) => value === "Question 5").length, 1);
  assert.deepEqual(questionHistory({ unexpected: true }), []);
});


test("run category and topic filters round-trip through post URLs", () => {
  const { runPostFiltersFromHash, runPostsHref } = require("../src/components/RunView.tsx");
  for (const category of ["job", "news", "tech", "marketplace", "question", "event", "promotion", "personal", "entertainment", "other", null]) {
    for (const topicId of [null, 12]) {
      const filters = { category, topicId };
      const href = runPostsHref(42, filters);
      assert.deepEqual(runPostFiltersFromHash(href), filters);
      assert.ok(href.startsWith("#/runs/42/posts"));
    }
  }
  assert.equal(runPostsHref(42, { category: "news", topicId: 12 }), "#/runs/42/posts?category=news&topic=12");
  assert.equal(runPostsHref(42, { category: null, topicId: null }), "#/runs/42/posts");
  assert.deepEqual(runPostFiltersFromHash("#/runs/42/posts?topic=12&category=promotion"), { category: "promotion", topicId: 12 });
});

test("run post filters ignore invalid categories, topics and non-post routes", () => {
  const { runPostFiltersFromHash, runPostsHref } = require("../src/components/RunView.tsx");
  for (const category of ["unknown", "__proto__", "constructor", "toString", "NEWS", "<script>"]) {
    assert.deepEqual(runPostFiltersFromHash(`#/runs/42/posts?category=${encodeURIComponent(category)}&topic=3`), { category: null, topicId: 3 });
    assert.equal(runPostsHref(42, { category, topicId: 3 }), "#/runs/42/posts?topic=3");
  }
  for (const topic of ["-1", "NaN", "1.5", "0", "9007199254740992"]) {
    assert.deepEqual(runPostFiltersFromHash(`#/runs/42/posts?category=job&topic=${topic}`), { category: "job", topicId: null });
  }
  for (const hash of ["#/runs/42/digest?category=news&topic=2", "#/ask?category=job", "#/runs/42?category=news"]) {
    assert.deepEqual(runPostFiltersFromHash(hash), { category: null, topicId: null });
  }
});

test("trends filters parse, validate, and serialize with priority URL > storage > defaults", () => {
  const { parseTrendsFilters, serializeTrendsFilters, DEFAULT_TRENDS_FILTERS } = require("../src/components/TrendsPage.tsx");

  // 1. Defaults when empty
  const def = parseTrendsFilters("", null, false);
  assert.deepEqual(def, { group: "category", bucket: "day", days: 30, viewMode: "overview" });
  assert.equal(parseTrendsFilters(null, null, true).viewMode, "grid");

  // 2. LocalStorage persistence format
  const storedJson = JSON.stringify({ group: "topic", bucket: "week", days: 90, viewMode: "grid" });
  assert.deepEqual(parseTrendsFilters("", storedJson, false), { group: "topic", bucket: "week", days: 90, viewMode: "grid" });

  // 3. Fallback on invalid or malformed stored values
  assert.deepEqual(
    parseTrendsFilters("", "{ invalid-json }", false),
    { group: "category", bucket: "day", days: 30, viewMode: "overview" }
  );
  assert.deepEqual(
    parseTrendsFilters("", JSON.stringify({ group: "bad_group", bucket: "yearly", days: 999, viewMode: "cards" }), false),
    { group: "category", bucket: "day", days: 30, viewMode: "overview" }
  );

  // 4. URL query overrides stored values
  const urlWithOverrides = "#/trends?group=category&bucket=day&range=7&view=overview";
  assert.deepEqual(
    parseTrendsFilters(urlWithOverrides, storedJson, false),
    { group: "category", bucket: "day", days: 7, viewMode: "overview" }
  );

  // 5. URL query partial override (group overridden, other from storage)
  assert.deepEqual(
    parseTrendsFilters("#/trends?group=category", storedJson, false),
    { group: "category", bucket: "week", days: 90, viewMode: "grid" }
  );

  // 6. Support synonyms: range / days, view / viewMode
  assert.deepEqual(
    parseTrendsFilters("#/trends?days=7&viewMode=grid", null, false),
    { group: "category", bucket: "day", days: 7, viewMode: "grid" }
  );

  // 7. Serialization to query string
  assert.equal(
    serializeTrendsFilters({ group: "topic", bucket: "week", days: 90, viewMode: "grid" }),
    "group=topic&bucket=week&range=90&view=grid"
  );
});
