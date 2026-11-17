import type { Key } from "./i18n";
import type { Job, Post, RunRequest } from "./types";
import { PLATFORM_LABEL } from "./categories";

type SourceRequest = Pick<RunRequest, "platform" | "source_type" | "sources"> & Partial<Pick<RunRequest, "mode" | "options">>;
type Translate = (key: Key, vars?: Record<string, string | number>) => string;

/** A mode-aware label; preserve each existing surface's legacy fallback. */
export function describeRunSource(req: SourceRequest, t: Translate, legacy: "run" | "history" | "sidebar" = "run"): string {
  const sources = req.sources ?? [];
  const short = (s: string) => s.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  if (!req.mode) {
    if (legacy === "sidebar") return req.source_type === "feed" ? t("sb.feed") : sources[0] ?? "";
    if (req.source_type === "feed") return t("run.feedOf", { platform: PLATFORM_LABEL[req.platform] });
    const first = legacy === "history" ? short(sources[0] ?? "") : sources[0] ?? "";
    return sources.length > 1 ? t("run.andMore", { first, n: sources.length - 1 }) : first;
  }
  const labels: Record<string, Key> = {
    "facebook.feed": "cmp.mode.fb.feed", "facebook.group": "cmp.mode.fb.groups", "facebook.page": "cmp.mode.fb.pages", "facebook.search": "cmp.mode.fb.search",
    "linkedin.jobs": "cmp.mode.li.jobs", "linkedin.recruiting_posts": "cmp.mode.li.hiring", "linkedin.feed": "cmp.mode.li.feed", "linkedin.legacy_group": "cmp.groups",
    "reddit.home": "cmp.mode.reddit.home", "reddit.subreddit": "cmp.mode.reddit.subreddits", "reddit.search": "cmp.mode.reddit.search",
    "x.feed": "cmp.mode.x.feed", "x.account": "cmp.mode.x.accounts", "x.list": "cmp.mode.x.lists", "x.search": "cmp.mode.x.search", "x.legacy_group": "cmp.groups",
  };
  const opts = req.options ?? {};
  const mode = labels[`${req.platform}.${req.mode}`];
  const head = `${PLATFORM_LABEL[req.platform]} · ${mode ? t(mode) : req.mode}`;
  if (req.mode === "jobs") {
    const details = ["keywords" in opts ? opts.keywords : sources[0], "location" in opts ? opts.location : ""];
    if ("work_modes" in opts) details.push(...(opts.work_modes ?? []).map((m) => t(`profile.mode.${m}` as Key)));
    if ("posted_within" in opts && opts.posted_within) details.push(t(`source.period.${opts.posted_within}` as Key));
    return `${head}: ${details.filter(Boolean).join(" · ")}`;
  }
  if (req.mode === "feed" || req.mode === "home") return head;
  let detail = sources.length > 1 ? t(req.mode === "page" ? "source.pages" : "source.count", { n: sources.length }) : short(sources[0] ?? "");
  if (req.mode === "subreddit" && sources.length === 1) {
    const sub = sources[0].replace(/^https?:\/\/(?:www\.|old\.)?reddit\.com\//, "").replace(/^\/?r\//, "").split(/[/?#]/)[0];
    detail = `r/${sub}`;
  }
  const sort = "sort" in opts ? opts.sort : undefined;
  if (sort) detail += ` (${t(`source.sort.${sort}` as Key)})`;
  if ("latest" in opts && opts.latest) detail += ` (${t("source.sort.new")})`;
  return `${head}: ${detail}`;
}

/** Only a bare run URL gets the Jobs default; explicit tabs remain shareable. */
export function defaultRunTab(req: Pick<RunRequest, "platform" | "mode">, hash: string): "jobs" | null {
  return req.platform === "linkedin" && req.mode === "jobs" && /^#\/?runs\/\d+\/?(?:\?.*)?$/.test(hash) ? "jobs" : null;
}

/** Preserve observed job facts while retaining AI scores, reasons and contact. */
export function jobPresentation(post: Pick<Post, "job" | "job_seed" | "url">): { job: Job | null; url: string } {
  const seed = post.job_seed;
  const job: Job | null = post.job ? { ...post.job } : seed ? {
    title: "", company: "", location: "", salary: "", work_mode: "", contact: "", match_score: 0, match_reason: "",
  } : null;
  if (seed && job) {
    for (const key of ["title", "company", "location", "work_mode"] as const) job[key] = seed[key] || job[key];
    job.salary = seed.salary_text || job.salary;
  }
  return { job, url: seed?.url || post.url };
}

/** Backend timestamps without an offset are UTC, including SQLite timestamps. */
export function parseTimestamp(iso: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

export function groupName(url: string): string {
  const slug = (url.replace(/\/$/, "").split(/groups\/|\/r\/|x\.com\//).pop() ?? url).split(/[/?#]/)[0];
  let decoded = slug;
  try { decoded = decodeURIComponent(slug); } catch { /* A malformed saved URL must still render. */ }
  return decoded.replace(/[-_.]+/g, " ").trim() || url;
}

export const isRemoteText = (text: string): boolean => /remote|từ xa|wfh|work from home|远程|遠程|居家办公|居家辦公|在宅/i.test(text);

/** Serialize writes across form mounts; a rejected save must not block later saves. */
export function serialWriter<T>(write: (value: T) => Promise<unknown>) {
  let tail: Promise<unknown> = Promise.resolve();
  return (value: T) => {
    const next = tail.catch(() => {}).then(() => write(value));
    tail = next;
    return next;
  };
}


export function matchesJobType(type: string | null | undefined, filter: string): boolean {
  return filter === "all" || (type ?? "none") === filter;
}

export function canContinueAnalysis(run: { status: string; digest?: unknown; posts?: { analyzed?: boolean }[]; can_continue_analysis?: boolean }): boolean {
  if (["pending", "queued", "scraping", "analyzing"].includes(run.status)) return false;
  return run.can_continue_analysis ?? (!!run.posts?.length && (!run.digest || run.posts.some((post) => post.analyzed === false)));
}
