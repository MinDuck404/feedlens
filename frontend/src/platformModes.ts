import type { Key } from "./i18n";
import type { Mode, ModeOptions, Platform, Preferences, RunRequest, SavedGroup, SourceType } from "./types";

type OptionValue = string | boolean | string[] | null;
export interface ModeDraft { sourceText: string; sourceEntry?: string; count: number; options: Record<string, OptionValue> }
export interface ModeField {
  name: string;
  type: "text" | "sources" | "saved" | "select" | "multi" | "toggle";
  label: Key;
  placeholder?: Key;
  example?: string;
  required?: boolean;
  choices?: { value: string; label: Key }[];
}
export interface PlatformMode {
  mode: Mode; label: Key; description: Key; sourceType: SourceType; countLabel: Key;
  count: number; fields: ModeField[]; defaults?: Record<string, OptionValue>;
}
export interface ModePreferences extends Preferences {
  version: 2;
  drafts: Record<string, ModeDraft>;
  saved_sources: Record<string, SavedGroup[]>;
}

const period = (month = true): ModeField => ({ name: "posted_within", type: "select", label: "cmp.input.timeLabel", choices: [
  { value: "day", label: "cmp.input.time.24h" }, { value: "week", label: "cmp.input.time.week" },
  ...(month ? [{ value: "month", label: "cmp.input.time.month" as Key }] : []),
] });
const query = (placeholder: Key): ModeField => ({ name: "sources", type: "sources", label: "cmp.input.keywordsLabel", placeholder, required: true });
export const PLATFORM_MODES: Record<Platform, PlatformMode[]> = {
  facebook: [
    { mode: "feed", label: "cmp.mode.fb.feed", description: "cmp.mode.fb.feedDesc", sourceType: "feed", countLabel: "cmp.countLabel", count: 40, fields: [] },
    { mode: "group", label: "cmp.mode.fb.groups", description: "cmp.mode.fb.groupsDesc", sourceType: "group", countLabel: "cmp.countPerGroupLabel", count: 20,
      defaults: { latest: true }, fields: [
        { name: "sources", type: "saved", label: "cmp.addGroup", example: "https://www.facebook.com/groups/vieclamit", required: true },
        { name: "latest", type: "toggle", label: "cmp.input.groupChronological" },
      ] },
    { mode: "page", label: "cmp.mode.fb.pages", description: "cmp.mode.fb.pagesDesc", sourceType: "group", countLabel: "cmp.countPerPageLabel", count: 20,
      fields: [{ name: "sources", type: "sources", label: "cmp.input.pageLabel", placeholder: "cmp.input.pagePh", required: true }] },
    { mode: "search", label: "cmp.mode.fb.search", description: "cmp.mode.fb.searchDesc", sourceType: "search", countLabel: "cmp.countPerKeywordLabel", count: 20, fields: [query("cmp.searchFacebook")] },
  ],
  linkedin: [
    { mode: "jobs", label: "cmp.mode.li.jobs", description: "cmp.mode.li.jobsDesc", sourceType: "search", countLabel: "cmp.countJobsLabel", count: 25,
      defaults: { keywords: "", location: "", work_modes: [], posted_within: "week" }, fields: [
        { name: "keywords", type: "text", label: "cmp.input.keywordsLabel", placeholder: "cmp.input.keywordsPh", required: true },
        { name: "location", type: "text", label: "cmp.input.locationLabel", placeholder: "cmp.input.locationPh" },
        { name: "work_modes", type: "multi", label: "cmp.input.workModeLabel", choices: [
          { value: "remote", label: "cmp.input.workMode.remote" }, { value: "hybrid", label: "cmp.input.workMode.hybrid" }, { value: "onsite", label: "cmp.input.workMode.onsite" },
        ] }, period(),
      ] },
    { mode: "recruiting_posts", label: "cmp.mode.li.hiring", description: "cmp.mode.li.hiringDesc", sourceType: "search", countLabel: "cmp.countPerKeywordLabel", count: 20,
      defaults: { posted_within: "week", hiring: true }, fields: [query("cmp.searchLinkedin"), period(false)] },
    { mode: "feed", label: "cmp.mode.li.feed", description: "cmp.mode.li.feedDesc", sourceType: "feed", countLabel: "cmp.countLabel", count: 40, fields: [] },
  ],
  reddit: [
    { mode: "subreddit", label: "cmp.mode.reddit.subreddits", description: "cmp.mode.reddit.subredditsDesc", sourceType: "group", countLabel: "cmp.countPerSubredditLabel", count: 25,
      defaults: { sort: "new" }, fields: [
        { name: "sources", type: "sources", label: "cmp.addSubreddit", example: "r/forhire\nr/remotejs", required: true },
        { name: "sort", type: "select", label: "cmp.input.sortLabel", choices: [
          { value: "new", label: "cmp.input.sort.new" }, { value: "top_day", label: "cmp.input.sort.topDay" }, { value: "top_week", label: "cmp.input.sort.topWeek" },
        ] },
      ] },
    { mode: "search", label: "cmp.mode.reddit.search", description: "cmp.mode.reddit.searchDesc", sourceType: "search", countLabel: "cmp.countPerKeywordLabel", count: 25,
      defaults: { sort: "new" }, fields: [query("cmp.searchReddit"), { name: "sort", type: "select", label: "cmp.input.sortLabel", choices: [
        { value: "new", label: "cmp.input.sort.new" }, { value: "top", label: "cmp.input.sort.top" },
      ] }] },
    { mode: "home", label: "cmp.mode.reddit.home", description: "cmp.mode.reddit.homeDesc", sourceType: "feed", countLabel: "cmp.countLabel", count: 40, fields: [] },
  ],
  x: [
    { mode: "search", label: "cmp.mode.x.search", description: "cmp.mode.x.searchDesc", sourceType: "search", countLabel: "cmp.countPerKeywordLabel", count: 20, fields: [query("cmp.searchX")] },
    { mode: "account", label: "cmp.mode.x.accounts", description: "cmp.mode.x.accountsDesc", sourceType: "group", countLabel: "cmp.countPerAccountLabel", count: 20,
      fields: [{ name: "sources", type: "sources", label: "cmp.input.handleLabel", placeholder: "cmp.input.handlePh", required: true }] },
    { mode: "list", label: "cmp.mode.x.lists", description: "cmp.mode.x.listsDesc", sourceType: "group", countLabel: "cmp.countPerListLabel", count: 20,
      fields: [{ name: "sources", type: "sources", label: "cmp.input.listLabel", placeholder: "cmp.input.listPh", required: true }] },
    { mode: "feed", label: "cmp.mode.x.feed", description: "cmp.mode.x.feedDesc", sourceType: "feed", countLabel: "cmp.countLabel", count: 40, fields: [] },
  ],
};

const legacyMode: PlatformMode = { mode: "legacy_group", label: "cmp.mode.legacyGroups", description: "cmp.mode.legacyGroupsDesc",
  sourceType: "group", countLabel: "cmp.countPerGroupLabel", count: 20,
  fields: [{ name: "sources", type: "sources", label: "cmp.addGroup", required: true }] };
export const draftKey = (platform: Platform, mode: Mode) => `${platform}:${mode}`;
export const modeDefinition = (platform: Platform, mode: Mode): PlatformMode =>
  PLATFORM_MODES[platform].find((item) => item.mode === mode) ?? legacyMode;
export const defaultMode = (platform: Platform): Mode => PLATFORM_MODES[platform][0].mode;
export function defaultDraft(platform: Platform, mode: Mode): ModeDraft {
  const definition = modeDefinition(platform, mode);
  return { sourceText: "", count: definition.count, options: structuredClone(definition.defaults ?? {}) };
}
export const sourceLines = (text: string): string[] => [...new Set(text.split("\n").map((v) => v.trim()).filter(Boolean))];

function sourcePath(value: string, platform: Platform): { path: string; query: URLSearchParams } {
  const hosts = { facebook: ["facebook.com", "www.facebook.com", "m.facebook.com"], linkedin: ["linkedin.com", "www.linkedin.com"],
    reddit: ["reddit.com", "www.reddit.com", "old.reddit.com"], x: ["x.com", "www.x.com", "twitter.com", "www.twitter.com"] };
  if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith("//")) {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || !hosts[platform].includes(url.hostname)
        || url.username || url.password || !["", "80", "443"].includes(url.port)) throw new Error("source");
    return { path: url.pathname.replace(/^\/+|\/+$/g, ""), query: url.searchParams };
  }
  if (/[:?#\\]/.test(value)) throw new Error("source");
  return { path: value.replace(/^\/+|\/+$/g, ""), query: new URLSearchParams() };
}

function sourceIdentity(platform: Platform, mode: Mode, source: string): string {
  if (mode === "search" || mode === "recruiting_posts") {
    if (platform === "facebook" && source.includes("|")) {
      const [group, ...words] = source.split("|");
      if (!words.join("|").trim()) throw new Error("source");
      return `${sourceIdentity(platform, "group", group.trim())}|${words.join("|").trim()}`;
    }
    return source;
  }
  const { path, query } = sourcePath(source, platform);
  const identifier = /^[A-Za-z0-9_.-]+$/;
  if (platform === "facebook") {
    if (mode === "page" && path === "profile.php" && /^\d+$/.test(query.get("id") ?? "") && query.getAll("id").length === 1) return `profile.php?id=${query.get("id")}`;
    const name = mode === "group" ? path.replace(/^groups\//, "") : path;
    if (!identifier.test(name) || [".", ".."].includes(name) || mode === "page" && ["groups", "search", "home.php", "login", "login.php", "watch", "ads", "reel", "photo.php", "profile.php"].includes(name.toLowerCase())) throw new Error("source");
    return name;
  }
  if (platform === "reddit") {
    const found = path.match(/^(?:r\/)?([A-Za-z0-9_]{1,21})(?:\/(?:new|top))?$/);
    if (!found) throw new Error("source");
    return found[1];
  }
  if (platform === "linkedin") {
    const name = path.replace(/^groups\//, "");
    if (!identifier.test(name) || [".", ".."].includes(name)) throw new Error("source");
    return name;
  }
  if ((mode === "list" || mode === "legacy_group") && /^(?:i\/lists\/)?\d+$/.test(path)) return `list:${path.replace(/^i\/lists\//, "")}`;
  if ((mode === "account" || mode === "legacy_group") && /^@?[A-Za-z0-9_]{1,15}$/.test(path)) {
    const handle = path.replace(/^@/, "");
    if (["home", "search", "login", "logout", "settings", "explore", "notifications", "messages", "i"].includes(handle.toLowerCase())) throw new Error("source");
    return handle;
  }
  if (mode === "legacy_group" && /^i\/communities\/\d+$/.test(path)) return path;
  throw new Error("source");
}

export function inferMode(request: Partial<RunRequest>): Mode {
  const platform = request.platform ?? "facebook";
  if (request.mode) return request.mode;
  if (!request.source_type) return defaultMode(platform);
  if (platform === "linkedin") return request.source_type === "group" ? "legacy_group" : request.source_type === "search" ? "recruiting_posts" : "feed";
  if (platform === "reddit") return request.source_type === "group" ? "subreddit" : request.source_type === "feed" ? "home" : "search";
  if (platform === "x" && request.source_type === "group") {
    const kinds = new Set((request.sources ?? []).map((source) => {
      try { const { path } = sourcePath(source, "x"); return /^(?:i\/lists\/)?\d+$/.test(path) ? "list" : /^@?[A-Za-z0-9_]{1,15}$/.test(path) ? "account" : "legacy_group"; }
      catch { return "legacy_group"; }
    }));
    return kinds.size === 1 ? [...kinds][0] as Mode : "legacy_group";
  }
  return request.source_type;
}

export function draftFromRequest(request: Partial<RunRequest>): ModeDraft {
  const platform = request.platform ?? "facebook", mode = inferMode(request);
  const draft = defaultDraft(platform, mode);
  const legacy = !request.mode;
  return { ...draft, sourceText: (request.sources ?? []).join("\n"), count: request.count ?? draft.count,
    options: { ...draft.options,
      ...(legacy && platform === "facebook" && mode === "group" ? { latest: false } : {}),
      ...(legacy && platform === "linkedin" && mode === "recruiting_posts" ? { hiring: false, posted_within: null } : {}),
      ...request.options } };
}

export function validateDraft(platform: Platform, mode: Mode, draft: ModeDraft): Key | null {
  if (!PLATFORM_MODES[platform].some((item) => item.mode === mode) && !(mode === "legacy_group" && ["linkedin", "x"].includes(platform))) return "error.validation";
  if (!Number.isInteger(draft.count) || draft.count < 1 || draft.count > 1000) return "error.validation";
  for (const field of modeDefinition(platform, mode).fields) {
    const value = field.name === "sources" ? draft.sourceText : draft.options[field.name];
    if (field.required && (typeof value !== "string" || !value.trim())) return field.name === "sources" ? "error.sources_missing" : "error.validation";
    if (field.type === "toggle" && typeof value !== "boolean") return "error.validation";
    if (field.type === "multi" && !Array.isArray(value)) return "error.validation";
    if (field.type === "text" && typeof value !== "string") return "error.validation";
    if (field.choices && !(mode === "recruiting_posts" && value === null)) {
      const values = Array.isArray(value) ? value : [value];
      if (values.some((entry) => !field.choices!.some((choice) => choice.value === entry))) return "error.validation";
    }
  }
  if (String(draft.options.keywords ?? "").length > 500 || String(draft.options.location ?? "").length > 300) return "error.validation";
  try {
    if (modeDefinition(platform, mode).sourceType !== "feed" && mode !== "jobs") {
      for (const source of sourceLines(draft.sourceText)) {
        if (source.length > 2000) return "error.validation";
        sourceIdentity(platform, mode, source);
      }
    }
  } catch { return "error.validation"; }
  return null;
}

function draftIdentity(platform: Platform, mode: Mode, draft: ModeDraft, source: string): string {
  const identity = sourceIdentity(platform, mode, source);
  if (platform === "linkedin" && mode === "recruiting_posts" && draft.options.hiring && !/\bhiring\b/i.test(identity)) return `${identity} hiring`;
  if (platform === "facebook" && mode === "group" && !draft.options.latest && sourcePath(source, platform).query.get("sorting_setting") === "CHRONOLOGICAL") return `${identity}?chronological`;
  return identity;
}

export function serializeDraft(base: RunRequest, mode: Mode, draft: ModeDraft): RunRequest {
  if (validateDraft(base.platform, mode, draft)) throw new Error("Invalid platform mode draft");
  const definition = modeDefinition(base.platform, mode), options: Record<string, OptionValue> = {};
  for (const key of Object.keys(definition.defaults ?? {})) options[key] = draft.options[key] ?? (key === "posted_within" && mode === "recruiting_posts" ? null : definition.defaults![key]);
  let sources = definition.sourceType === "feed" ? [] : sourceLines(draft.sourceText);
  if (mode === "jobs") { options.keywords = String(options.keywords).trim(); options.location = String(options.location).trim(); sources = [String(options.keywords)]; }
  else {
    const seen = new Set<string>();
    sources = sources.filter((source) => { const key = draftIdentity(base.platform, mode, draft, source); if (seen.has(key)) return false; seen.add(key); return true; });
  }
  const { scrape_report: _report, ...request } = base;
  return { ...request, mode, options: options as ModeOptions, source_type: definition.sourceType, sources,
    count: draft.count, job_mode: mode === "jobs" || base.job_mode };
}

export function countPlan(platform: Platform, mode: Mode, draft: ModeDraft, maxPosts: number) {
  const definition = modeDefinition(platform, mode), identities = new Set<string>();
  if (mode === "jobs" || definition.sourceType === "feed") identities.add("single");
  else for (const source of sourceLines(draft.sourceText)) {
    try { identities.add(draftIdentity(platform, mode, draft, source)); } catch { identities.add(source); }
  }
  const cap = Math.min(maxPosts, platform === "reddit" ? 100 : platform === "x" && mode === "search" ? 60 : maxPosts);
  return { label: definition.countLabel, sources: identities.size, total: Math.min(draft.count * identities.size, cap), cap };
}

/** Add the new draft format once, preserving old preference fields and unknown legacy sources. */
export function migratePreferences(input: Preferences): ModePreferences {
  const stored = input as Partial<ModePreferences>;
  const drafts = structuredClone(stored.drafts ?? {}), saved = structuredClone(stored.saved_sources ?? {});
  const seed = (platform: Platform, mode: Mode, sources: SavedGroup[], legacy = false) => {
    const key = draftKey(platform, mode);
    if (!saved[key]) saved[key] = structuredClone(sources);
    if (!drafts[key]) drafts[key] = { ...(legacy ? draftFromRequest({ platform, source_type: modeDefinition(platform, mode).sourceType, sources: sources.map((source) => source.url) }) : defaultDraft(platform, mode)),
      sourceText: sources.filter((source) => source.enabled).map((source) => source.url).join("\n") };
  };
  for (const platform of Object.keys(PLATFORM_MODES) as Platform[]) {
    const groups = input.groups?.[platform] ?? [];
    if (groups.length) {
      if (platform === "x") {
        const grouped: Partial<Record<Mode, SavedGroup[]>> = {};
        for (const group of groups) { const mode = inferMode({ platform, source_type: "group", sources: [group.url] }); (grouped[mode] ??= []).push(group); }
        for (const [mode, sources] of Object.entries(grouped)) seed(platform, mode as Mode, sources, true);
      } else seed(platform, platform === "facebook" ? "group" : platform === "reddit" ? "subreddit" : "legacy_group", groups, true);
    }
    if (input.searches?.[platform]) seed(platform, platform === "linkedin" ? "recruiting_posts" : "search",
      sourceLines(input.searches[platform]!).map((url) => ({ url, enabled: true })), true);
  }
  const request = input.composer;
  if (request) {
    const platform = request.platform ?? "facebook", mode = inferMode(request), key = draftKey(platform, mode);
    if (!drafts[key]) drafts[key] = draftFromRequest(request);
    else if (stored.version !== 2) drafts[key] = { ...draftFromRequest(request), sourceText: request.sources?.length ? request.sources.join("\n") : drafts[key].sourceText };
    if (modeDefinition(platform, mode).sourceType === "group" && !saved[key]) saved[key] = sourceLines(drafts[key].sourceText).map((url) => ({ url, enabled: true }));
  }
  return { ...input, version: 2, drafts, saved_sources: saved };
}
