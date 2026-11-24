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
const modes = require("../src/lib/platformModes.ts");
const { TextField } = require("../src/components/ui/TextField.tsx");
const base = { platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false, keywords: ["Python"],
  profile: "Existing notes", ai_provider: "offline", ai_model: "", only_new: true, headless: true, speed: "careful", runner: "agent" };

test("catalog has exactly the public modes and LinkedIn defaults to job search", () => {
  assert.deepEqual(Object.fromEntries(Object.entries(modes.PLATFORM_MODES).map(([p, list]) => [p, list.length])), { facebook: 4, linkedin: 3, reddit: 3, x: 4 });
  assert.equal(modes.defaultMode("linkedin"), "jobs");
  assert.equal(modes.defaultDraft("linkedin", "jobs").count, 25);
  assert.equal(modes.defaultDraft("facebook", "group").options.latest, true);
  assert.equal(Object.values(modes.PLATFORM_MODES).flat().some((mode) => mode.mode === "legacy_group"), false);
});

test("job profile suggestions prioritize primary roles and include only enabled adjacent roles", () => {
  const profile = { primary_roles: ["Python Engineer", "Data Engineer", "Python Engineer"],
    adjacent_roles: [{ role: "QA Engineer", enabled: true }, { role: "Product Manager", enabled: false }, { role: "Data Engineer", enabled: true }],
    criteria: { locations: ["Hà Nội"], work_modes: ["remote"], min_salary: null, currency: "VND", level: "" },
    markdown: "", allow_adjacent: true };
  assert.deepEqual(modes.jobProfileSuggestions(profile), ["Python Engineer", "Data Engineer", "QA Engineer"]);
});

test("job profile autofill fills only empty fields and preserves current choices", () => {
  const profile = { primary_roles: ["Python Engineer"], adjacent_roles: [{ role: "QA Engineer", enabled: true }],
    criteria: { locations: ["Hà Nội"], work_modes: ["remote", "hybrid"], min_salary: null, currency: "VND", level: "" },
    markdown: "", allow_adjacent: true };
  assert.deepEqual(modes.applyJobProfileDefaults({ count: 25, sourceText: "", options: { keywords: "", location: "", work_modes: [] } }, profile),
    { count: 25, sourceText: "", options: { keywords: "Python Engineer", location: "Hà Nội", work_modes: ["remote", "hybrid"] } });
  assert.deepEqual(modes.applyJobProfileDefaults({ count: 25, sourceText: "", options: { keywords: "Custom query", location: "Da Nang", work_modes: ["onsite"] } }, profile).options,
    { keywords: "Custom query", location: "Da Nang", work_modes: ["onsite"] });
  assert.deepEqual(modes.applyJobProfileDefaults({ count: 25, sourceText: "", options: { keywords: "", location: "", work_modes: [] } },
    { ...profile, primary_roles: [], criteria: { ...profile.criteria, locations: [], work_modes: [] } }).options,
    { keywords: "", location: "", work_modes: [] });
});

const cases = [
  ["facebook", "feed", "", {}, "feed", []],
  ["facebook", "group", "demo\nhttps://www.facebook.com/groups/demo/", { latest: true, old_streak: 5 }, "group", ["demo"]],
  ["facebook", "page", "NASA\nhttps://www.facebook.com/NASA/", {}, "group", ["NASA"]],
  ["facebook", "search", "python\nreact", {}, "search", ["python", "react"]],
  ["linkedin", "jobs", "", { keywords: "  Python & React  ", location: "Vietnam", work_modes: ["remote", "hybrid"], posted_within: "week" }, "search", ["Python & React"]],
  ["linkedin", "recruiting_posts", "python", { posted_within: "week", hiring: true }, "search", ["python"]],
  ["linkedin", "feed", "", {}, "feed", []],
  ["reddit", "subreddit", "r/forhire\nhttps://www.reddit.com/r/forhire/new/", { sort: "new" }, "group", ["r/forhire"]],
  ["reddit", "search", "hiring Python", { sort: "new" }, "search", ["hiring Python"]],
  ["reddit", "home", "", {}, "feed", []],
  ["x", "search", "hiring lang:en", {}, "search", ["hiring lang:en"]],
  ["x", "account", "@sama\nhttps://x.com/sama", {}, "group", ["@sama"]],
  ["x", "list", "123456\nhttps://x.com/i/lists/123456", {}, "group", ["123456"]],
  ["x", "feed", "", {}, "feed", []],
];
for (const [platform, mode, sourceText, options, source_type, sources] of cases) test(`serialize ${platform}/${mode}`, () => {
  const draft = { ...modes.defaultDraft(platform, mode), sourceText, options };
  const request = modes.serializeDraft({ ...base, platform }, mode, draft);
  assert.equal(request.platform, platform); assert.equal(request.mode, mode);
  assert.equal(request.source_type, source_type); assert.deepEqual(request.sources, sources);
  assert.deepEqual(request.options, { ...options, ...(mode === "jobs" ? { keywords: "Python & React" } : {}) });
  for (const field of ["profile", "ai_provider", "ai_model", "keywords", "only_new", "headless", "speed", "runner"]) assert.deepEqual(request[field], base[field]);
  assert.equal(request.job_mode, mode === "jobs");
});

test("every mode validates its required fields and rejects invalid option values", () => {
  for (const [platform, definitions] of Object.entries(modes.PLATFORM_MODES)) for (const definition of definitions) {
    const draft = modes.defaultDraft(platform, definition.mode);
    assert.equal(!!modes.validateDraft(platform, definition.mode, draft), definition.fields.some((field) => field.required), `${platform}/${definition.mode}`);
  }
  assert.ok(modes.validateDraft("linkedin", "jobs", { count: 25, sourceText: "", options: { keywords: "Python", location: "", work_modes: ["wrong"], posted_within: "week" } }));
  assert.ok(modes.validateDraft("linkedin", "jobs", { count: 25, sourceText: "", options: { keywords: "Python", location: "", work_modes: [], posted_within: null } }));
  assert.ok(modes.validateDraft("facebook", "group", { count: 20, sourceText: "123", options: { latest: "true" } }));
  assert.ok(modes.validateDraft("facebook", "jobs", modes.defaultDraft("linkedin", "jobs")));
});

test("source validation refuses foreign hosts, credentials, unsupported paths and blank scoped search", () => {
  for (const [platform, mode, source] of [
    ["facebook", "page", "https://facebook.com.evil.test/NASA"], ["facebook", "page", "https://user:password@www.facebook.com/NASA"],
    ["facebook", "page", "file:///etc/passwd"], ["facebook", "page", "groups/demo"], ["facebook", "search", "demo | "],
    ["reddit", "subreddit", "https://evil.test/r/forhire"], ["x", "account", "https://x.com/i/lists/123"],
    ["x", "account", "home"], ["x", "list", "@sama"], ["linkedin", "legacy_group", "https://evil.test/groups/1"],
  ]) assert.ok(modes.validateDraft(platform, mode, { ...modes.defaultDraft(platform, mode), sourceText: source }), `${platform}/${source}`);
});

test("counts dedupe canonical sources and follow platform and global caps", () => {
  const plan = (platform, mode, sourceText, count, max = 500, options) => modes.countPlan(platform, mode, { ...modes.defaultDraft(platform, mode), sourceText, count, ...(options ? { options } : {}) }, max);
  assert.deepEqual(plan("reddit", "subreddit", "r/a\nr/b\nr/c", 40), { label: "cmp.countPerSubredditLabel", sources: 3, total: 100, cap: 100, quotas: [34, 33, 33], minPerSource: 33, maxPerSource: 34 });
  assert.equal(plan("reddit", "home", "", 150).total, 100);
  assert.equal(plan("x", "search", "one\ntwo\nthree", 25).total, 60);
  assert.equal(plan("facebook", "page", "NASA\nhttps://www.facebook.com/NASA/", 40).total, 40);
  assert.equal(plan("facebook", "group", "a\nb", 40, 50).total, 50);
  assert.equal(plan("linkedin", "jobs", "many\nqueries", 25).sources, 1);
  assert.equal(plan("linkedin", "recruiting_posts", "Python\nPython hiring", 20).total, 20);
  assert.equal(plan("x", "account", "@sama", 20).label, "cmp.countPerAccountLabel");
  assert.equal(plan("x", "list", "123", 20).label, "cmp.countPerListLabel");
  assert.equal(plan("facebook", "feed", "", 40).label, "cmp.countLabel");
});

test("water filling saturates small sources and gives odd posts to earlier sources", () => {
  assert.deepEqual(modes.distributeQuotas(Array(13).fill(120), 500), [...Array(6).fill(39), ...Array(7).fill(38)]);
  assert.deepEqual(modes.distributeQuotas([10, 600], 500), [10, 490]);
  assert.deepEqual(modes.distributeQuotas([2, 100, 100], 10), [2, 4, 4]);
  assert.deepEqual(modes.distributeQuotas([0, 1, 120, 120], 100), [0, 1, 50, 49]);
  assert.deepEqual(modes.distributeQuotas([2, 3, 4], 100), [2, 3, 4]);
  assert.deepEqual(modes.distributeQuotas([10, 10, 10], 2), [1, 1, 0]);
  assert.deepEqual(modes.distributeQuotas([], 100), []);
  assert.deepEqual(modes.distributeQuotas([10, 10], 0), [0, 0]);
  const plan = modes.countPlan("facebook", "group", { ...modes.defaultDraft("facebook", "group"), count: 120,
    sourceText: Array.from({ length: 13 }, (_, i) => `group${i}`).join("\n") }, 500);
  assert.deepEqual(plan.quotas, [...Array(6).fill(39), ...Array(7).fill(38)]);
  assert.equal(plan.minPerSource, 38); assert.equal(plan.maxPerSource, 39);
});

test("migration preserves old data, disabled sources, and unknown legacy X groups, and is idempotent", () => {
  const legacy = { composer: { ...base, platform: "linkedin", source_type: "search", count: 80, keywords_text: "Python, Docker" },
    groups: { facebook: [{ url: "demo", enabled: true }], reddit: [{ url: "r/forhire", enabled: false }], linkedin: [{ url: "https://www.linkedin.com/groups/123/", enabled: true }],
      x: [{ url: "@sama", enabled: true }, { url: "https://x.com/i/lists/123", enabled: false }, { url: "https://x.com/i/communities/456", enabled: true }] },
    searches: { linkedin: "old query", facebook: "Python" }, unrelated: { keep: true } };
  const original = structuredClone(legacy), migrated = modes.migratePreferences(legacy);
  assert.deepEqual(legacy, original);
  assert.deepEqual(modes.migratePreferences(migrated), migrated);
  assert.deepEqual(migrated.groups, legacy.groups); assert.deepEqual(migrated.searches, legacy.searches);
  assert.deepEqual(migrated.unrelated, { keep: true });
  assert.deepEqual(migrated.saved_sources["x:list"], legacy.groups.x.slice(1, 2));
  assert.equal(migrated.saved_sources["reddit:subreddit"][0].enabled, false);
  assert.equal(migrated.drafts["linkedin:legacy_group"].sourceText, "https://www.linkedin.com/groups/123/");
  assert.equal(migrated.drafts["x:legacy_group"].sourceText, "https://x.com/i/communities/456");
  assert.equal(migrated.drafts["facebook:group"].options.latest, false);
  assert.deepEqual(migrated.drafts["facebook:search"].options, {});
  assert.deepEqual(migrated.drafts["linkedin:recruiting_posts"], { sourceText: "old query", count: 80, options: { hiring: false, posted_within: null } });
  migrated.saved_sources["facebook:group"] = []; migrated.drafts["facebook:group"].sourceText = "";
  assert.deepEqual(modes.migratePreferences(migrated).saved_sources["facebook:group"], []);
});

test("old requests reopen with their original semantics instead of new defaults", () => {
  for (const [platform, source_type, sources, expected] of [
    ["facebook", "group", ["demo"], "group"], ["linkedin", "group", ["123"], "legacy_group"],
    ["linkedin", "search", ["original query"], "recruiting_posts"], ["reddit", "feed", [], "home"],
    ["x", "group", ["@sama"], "account"], ["x", "group", ["123"], "list"],
    ["x", "group", ["@sama", "https://x.com/i/lists/123"], "legacy_group"],
  ]) {
    const request = { ...base, platform, source_type, sources }, mode = modes.inferMode(request), draft = modes.draftFromRequest(request);
    assert.equal(mode, expected); const rerun = modes.serializeDraft(request, mode, draft);
    assert.deepEqual(rerun.sources, sources);
    if (platform === "facebook") assert.equal(rerun.options.latest, false);
    if (platform === "linkedin" && source_type === "search") assert.deepEqual(rerun.options, { hiring: false, posted_within: null });
  }
});

// Drive the same hook/event interface used by Composer, without network or browser layout.
const { SourceMode } = require("../src/features/composer/SourceMode.tsx");
const { JobCriteria } = require("../src/features/composer/JobCriteria.tsx");
function expandComposerSections(node) {
  if (!node || typeof node !== "object") return node;
  if (Array.isArray(node)) return node.map(expandComposerSections);
  if (node.type === SourceMode || node.type === JobCriteria) return expandComposerSections(node.type(node.props));
  if (!node.props) return node;
  return { ...node, props: { ...node.props, children: expandComposerSections(node.props.children) } };
}

function hooks(component) {
  const React = require("react"), original = { useState: React.useState, useRef: React.useRef, useEffect: React.useEffect, useContext: React.useContext, useCallback: React.useCallback };
  let index = 0, effects = []; const cells = [];
  React.useState = (initial) => { const at = index++; cells[at] ??= { value: typeof initial === "function" ? initial() : initial }; return [cells[at].value, (value) => { cells[at].value = typeof value === "function" ? value(cells[at].value) : value; }]; };
  React.useRef = (initial) => cells[index++] ??= { current: initial };
  React.useEffect = (effect, deps) => { const at = index++, previous = cells[at]; if (!previous || deps.some((value, i) => value !== previous.deps[i])) {
    effects.push(() => { previous?.cleanup?.(); cells[at] = { deps, cleanup: effect() }; });
  } };
  React.useContext = () => ({ t: (key) => key, lang: "en" }); React.useCallback = (fn) => fn;
  return { render(props) { index = 0; const tree = expandComposerSections(component(props)); const pending = effects; effects = []; pending.forEach((fn) => fn()); return tree; }, close() { cells.forEach((cell) => cell.cleanup?.()); Object.assign(React, original); } };
}
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  return null;
}

test("Composer restores and persists the exact key/model, and sends null after returning to Auto", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const { AIKeyPicker } = require("../src/features/composer/AIKeyPicker.tsx");
  const original = { ...api }, requests = [], saved = [];
  api.providers = async () => [{ key: "openai", configured: true, is_default: true }, { key: "gemini", configured: true }];
  api.profile = async () => null; api.topics = async () => ({ topics: [] });
  api.createRun = async (req) => { requests.push(req); return { id: 1 }; };
  const harness = hooks(Composer), props = { meta: { mode: "cloud", max_posts: 500 }, me: null, platforms: [],
    prefs: { composer: { platform: "facebook", source_type: "feed", ai_provider: "gemini", ai_key_id: 7, ai_model: "lite" } },
    onPrefsChange: (p) => saved.push(p), onClose() {}, onCreated() {}, onOpenSettings() {} };
  try {
    harness.render(props); await new Promise(setImmediate);
    let tree = harness.render(props), picker = find(tree, (n) => n.type === AIKeyPicker);
    assert.equal(picker.props.provider, "gemini"); assert.equal(picker.props.keyId, 7); assert.equal(picker.props.model, "lite");
    picker.props.onChange(8, "flash"); tree = harness.render(props);
    await tree.props.onSubmit({ preventDefault() {} });
    assert.equal(requests.at(-1).ai_key_id, 8); assert.equal(requests.at(-1).ai_model, "flash");
    assert.equal(saved.at(-1).composer.ai_key_id, 8); assert.equal(saved.at(-1).composer.ai_model, "flash");
    picker = find(tree, (n) => n.type === AIKeyPicker); picker.props.onChange(null, "");
    tree = harness.render(props); await tree.props.onSubmit({ preventDefault() {} });
    assert.equal(requests.at(-1).ai_key_id, null); assert.equal(saved.at(-1).composer.ai_key_id, null);
  } finally { harness.close(); Object.assign(api, original); }
});

test("Composer switches platform drafts, serializes Jobs, and preserves old preferences on close", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const original = { ...api }, requests = [], saved = [];
  api.providers = async () => [{ key: "offline", configured: true }]; api.profile = async () => null; api.topics = async () => ({ topics: [] });
  api.createRun = async (req) => { requests.push(req); return { id: 1 }; };
  const harness = hooks(Composer), props = { meta: { mode: "cloud", max_posts: 500 }, me: null, platforms: [],
    prefs: { groups: { facebook: [{ url: "legacy", enabled: false }] } }, onPrefsChange: (p) => saved.push(p), onClose() {}, onCreated() {}, onOpenSettings() {} };
  try {
    let tree = harness.render(props); await new Promise(setImmediate);
    find(tree, (n) => n.props?.label === "cmp.platform" && n.props.onChange).props.onChange("linkedin"); tree = harness.render(props);
    assert.equal(find(tree, (n) => n.props?.label === "cmp.where" && n.props.onChange).props.value, "jobs");
    find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.onChange({ target: { value: "Python Developer" } });
    tree = harness.render(props);
    find(tree, (n) => n.props?.label === "cmp.platform" && n.props.onChange).props.onChange("reddit"); tree = harness.render(props);
    find(tree, (n) => n.props?.["aria-label"] === "cmp.input.sortLabel").props.onChange({ target: { value: "top_week" } });
    find(tree, (n) => n.type === "button" && n.props.children?.includes?.("r/forhire")).props.onClick(); tree = harness.render(props);
    find(tree, (n) => n.type === TextField && n.props.as === "textarea" && n.props["aria-label"] === "cmp.addSubreddit").props.onChange({ target: { value: "r/not-added-yet" } }); tree = harness.render(props);
    find(tree, (n) => n.props?.label === "cmp.platform" && n.props.onChange).props.onChange("linkedin"); tree = harness.render(props);
    assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.value, "Python Developer");
    await tree.props.onSubmit({ preventDefault() {} });
    assert.equal(requests[0].mode, "jobs"); assert.equal(requests[0].count, 25); assert.equal(requests[0].job_mode, true);
    assert.equal(requests[0].options.keywords, "Python Developer"); assert.equal(requests[0].options.sort, undefined);
    assert.deepEqual(requests[0].sources, ["Python Developer"]);
  } finally { harness.close(); Object.assign(api, original); }
  assert.equal(saved.at(-1).drafts["reddit:subreddit"].options.sort, "top_week");
  assert.equal(saved.at(-1).drafts["reddit:subreddit"].sourceEntry, "r/not-added-yet");
  assert.deepEqual(saved.at(-1).groups, props.prefs.groups);
  assert.equal(saved.at(-1).saved_sources["reddit:subreddit"][0].url, "r/forhire");
});

test("Composer can reopen a legacy request without deleting other saved sources", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const original = { ...api }, requests = [], saved = [];
  api.providers = async () => [{ key: "offline", configured: true }]; api.profile = async () => null; api.topics = async () => ({ topics: [] });
  api.createRun = async (request) => { requests.push(request); return { id: 1 }; };
  const harness = hooks(Composer), props = { meta: { mode: "cloud", max_posts: 500 }, me: null, platforms: [],
    prefs: { groups: { linkedin: [{ url: "old-group", enabled: true }] } }, initialRequest: { ...base, platform: "linkedin", source_type: "group", sources: ["rerun-group"] },
    onPrefsChange: (p) => saved.push(p), onClose() {}, onCreated() {}, onOpenSettings() {} };
  try {
    const tree = harness.render(props); await new Promise(setImmediate);
    const picker = find(tree, (n) => n.props?.label === "cmp.where" && n.props.onChange);
    assert.equal(picker.props.value, "legacy_group");
    assert.equal(picker.props.options.length, 4);
    await tree.props.onSubmit({ preventDefault() {} });
    assert.equal(requests[0].mode, "legacy_group"); assert.deepEqual(requests[0].sources, ["rerun-group"]);
  } finally { harness.close(); Object.assign(api, original); }
  assert.deepEqual(saved.at(-1).saved_sources["linkedin:legacy_group"], [{ url: "old-group", enabled: false }, { url: "rerun-group", enabled: true }]);
});

const sampleProfile = { primary_roles: ["Python Engineer", "Data Engineer"],
  adjacent_roles: [{ role: "QA Engineer", enabled: true }, { role: "Product Manager", enabled: false }],
  criteria: { locations: ["Hà Nội"], work_modes: ["remote", "hybrid"], min_salary: null, currency: "VND", level: "" },
  markdown: "Python and APIs", allow_adjacent: true };

test("Jobs hides the redundant toggle, autofills from CV and chip click replaces the query", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const original = { ...api }, settings = [];
  api.providers = async () => [{ key: "offline", configured: true }]; api.profile = async () => sampleProfile; api.topics = async () => ({ topics: [] });
  const harness = hooks(Composer), props = { meta: { mode: "cloud", max_posts: 500 }, me: null, platforms: [],
    prefs: { composer: { platform: "linkedin", mode: "jobs", options: { keywords: "" } } }, onPrefsChange() {}, onClose() {}, onCreated() {}, onOpenSettings: (tab) => settings.push(tab) };
  try {
    harness.render(props); await new Promise(setImmediate); harness.render(props);
    let tree = harness.render(props);
    assert.equal(find(tree, (n) => n.props?.children === "cmp.jobs"), null);
    assert.ok(find(tree, (n) => n.props?.children === "profile.using"));
    assert.ok(find(tree, (n) => n.type === TextField && n.props.as === "textarea" && n.props["aria-label"] === "profile.notes"));
    assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.value, "Python Engineer");
    assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.locationPh").props.value, "Hà Nội");
    find(tree, (n) => n.type === "button" && n.props.children === "QA Engineer").props.onClick(); tree = harness.render(props);
    assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.value, "QA Engineer");
    assert.equal(find(tree, (n) => n.type === "button" && n.props.children === "Product Manager"), null);
    find(tree, (n) => n.type === "button" && n.props.children === "profile.edit").props.onClick();
    assert.deepEqual(settings, ["profile"]);
    find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.onChange({ target: { value: "" } }); harness.render(props); tree = harness.render(props);
    assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.value, "");
  } finally { harness.close(); Object.assign(api, original); }
});

test("profile arriving late preserves user input, and rerun skips all CV autofill", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const original = { ...api };
  api.providers = async () => [{ key: "offline", configured: true }]; api.topics = async () => ({ topics: [] });
  try {
    for (const rerun of [false, true]) {
      let resolveProfile;
      api.profile = () => new Promise((resolve) => { resolveProfile = resolve; });
      const request = { ...base, platform: "linkedin", mode: "jobs", options: { keywords: "", location: "", work_modes: [], posted_within: "week" } };
      const harness = hooks(Composer), props = { meta: { mode: "cloud", max_posts: 500 }, me: null, platforms: [],
        prefs: { composer: request }, ...(rerun ? { initialRequest: request } : {}), onPrefsChange() {}, onClose() {}, onCreated() {}, onOpenSettings() {} };
      try {
        let tree = harness.render(props);
        if (!rerun) find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.onChange({ target: { value: "User query" } });
        resolveProfile(sampleProfile); await new Promise(setImmediate); harness.render(props); tree = harness.render(props);
        assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.keywordsPh").props.value, rerun ? "" : "User query");
        assert.equal(find(tree, (n) => n.props?.placeholder === "cmp.input.locationPh").props.value, rerun ? "" : "Hà Nội");
      } finally { harness.close(); }
    }
  } finally { Object.assign(api, original); }
});

test("Jobs without a CV links to profile settings and other modes retain the toggle", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const original = { ...api }, settings = [];
  api.providers = async () => [{ key: "offline", configured: true }]; api.profile = async () => null; api.topics = async () => ({ topics: [] });
  const harness = hooks(Composer), props = { meta: { mode: "cloud", max_posts: 500 }, me: null, platforms: [],
    prefs: { composer: { platform: "linkedin", mode: "jobs", options: { keywords: "Python" } } }, onPrefsChange() {}, onClose() {}, onCreated() {}, onOpenSettings: (tab) => settings.push(tab) };
  try {
    harness.render(props); await new Promise(setImmediate); let tree = harness.render(props);
    assert.ok(find(tree, (n) => n.props?.children === "cmp.jobsProfileHint"));
    find(tree, (n) => n.type === "button" && n.props.children === "profile.upload").props.onClick();
    assert.deepEqual(settings, ["profile"]);
    find(tree, (n) => n.props?.label === "cmp.where" && n.props.onChange).props.onChange("recruiting_posts"); tree = harness.render(props);
    assert.ok(find(tree, (n) => n.props?.children === "cmp.jobs"));
  } finally { harness.close(); Object.assign(api, original); }
});

test("countPlan and Composer use prefs.max_posts cap (13 groups x 100 with cap 2000 = 1300) and send max_posts", async () => {
  global.window ??= new EventTarget(); global.document ??= { documentElement: {} };
  const { api } = require("../src/api/client.ts"), Composer = require("../src/features/composer/Composer.tsx").default;
  const groups = Array.from({ length: 13 }, (_, i) => `https://www.facebook.com/groups/g${i + 1}`);
  const plan = modes.countPlan("facebook", "group", { sourceText: groups.join("\n"), count: 100, options: { latest: true, old_streak: 5 } }, 2000);
  assert.equal(plan.cap, 2000);
  assert.equal(plan.total, 1300);

  const original = { ...api }, created = [];
  api.providers = async () => [{ key: "offline", configured: true }]; api.profile = async () => null; api.topics = async () => ({ topics: [] });
  api.createRun = async (req) => { created.push(req); return { id: 99 }; };
  const harness = hooks(Composer), props = {
    meta: { mode: "local", max_posts: 500 }, me: null, platforms: [],
    prefs: { max_posts: 2000, composer: { platform: "facebook", mode: "group", count: 100, sources: groups },
      saved_sources: { "facebook:group": groups.map((url) => ({ url, enabled: true })) },
      drafts: { "facebook:group": { sourceText: groups.join("\n"), count: 100, options: { latest: true, old_streak: 5 } } } },
    onPrefsChange() {}, onClose() {}, onCreated() {}, onOpenSettings() {},
  };
  try {
    harness.render(props); await new Promise(setImmediate);
    const tree = harness.render(props);
    assert.ok(JSON.stringify(tree).includes('"cmp.total"'));
    assert.ok(!JSON.stringify(tree).includes('"cmp.cap"'));
    await find(tree, (n) => typeof n.props?.onSubmit === "function").props.onSubmit({ preventDefault() {} });
    assert.equal(created[0].max_posts, 2000);
    assert.equal(created[0].options.old_streak, 5);
  } finally { harness.close(); Object.assign(api, original); }
});

test("facebook group old_streak validates 1..50 and defaults to 5 for legacy drafts", () => {
  const valid = { sourceText: "g1", count: 20, options: { latest: true, old_streak: 5 } };
  assert.equal(modes.validateDraft("facebook", "group", valid), null);
  assert.equal(modes.validateDraft("facebook", "group", { ...valid, options: { latest: true, old_streak: 0 } }), "error.validation");
  assert.equal(modes.validateDraft("facebook", "group", { ...valid, options: { latest: true, old_streak: 51 } }), "error.validation");
  assert.equal(modes.validateDraft("facebook", "group", { ...valid, options: { latest: true, old_streak: 1.5 } }), "error.validation");
  const migrated = modes.migratePreferences({
    version: 2,
    drafts: { "facebook:group": { sourceText: "g1", count: 20, options: { latest: false } } },
    saved_sources: { "facebook:group": [{ url: "g1", enabled: true }] },
  });
  assert.equal(migrated.drafts["facebook:group"].options.old_streak, 5);
  assert.equal(migrated.drafts["facebook:group"].options.latest, false);
});
