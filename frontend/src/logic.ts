import type { Key } from "./i18n";
import type { Job, Post, RunRequest, SavedGroup, ScrapeSourceReport, StopReason } from "./types";
import { PLATFORM_LABEL } from "./categories";

type SourceRequest = Pick<RunRequest, "platform" | "source_type" | "sources"> & Partial<Pick<RunRequest, "mode" | "options">>;
type Translate = (key: Key, vars?: Record<string, string | number>) => string;

/** A mode-aware label; preserve each existing surface's legacy fallback. */
export function describeRunSource(req: SourceRequest | null | undefined, t: Translate, legacy: "run" | "history" | "sidebar" = "run"): string {
  if (!req) return t("run.unknownSource");
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

const DURATION_UNITS = {
  vi: { h: " giờ", m: " phút", s: " giây", sep: " " },
  en: { h: "h", m: "m", s: "s", sep: " " },
  zh: { h: "小时", m: "分", s: "秒", sep: "" },
} as const;

/** 192 → "3 phút 12 giây" / "3m 12s" / "3分12秒"; từ 1 giờ trở lên bỏ giây. */
export function formatDuration(seconds: number, lang: "vi" | "en" | "zh"): string {
  const u = DURATION_UNITS[lang] ?? DURATION_UNITS.en;
  const total = Math.round(seconds);
  if (total < 1) return `<1${u.s.trim()}`;
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const parts = h ? [`${h}${u.h}`, m ? `${m}${u.m}` : ""] : [m ? `${m}${u.m}` : "", s ? `${s}${u.s}` : ""];
  return parts.filter(Boolean).join(u.sep);
}

export function canReanalyzeOffline(run: { status: string; ai_label?: string; can_reanalyze_ai?: boolean; posts?: unknown[] }): boolean {
  return run.can_reanalyze_ai ?? (run.status === "done" && run.ai_label === "bộ lọc từ khóa offline" && !!run.posts?.length);
}

export function scrapeSourceRows(sources: ScrapeSourceReport[] = [], groups: SavedGroup[] = [], prioritizeActive = true) {
  const normalizeUrl = (url: string) => url.trim().replace(/^https?:\/\/(www\.)?/i, "").replace(/\/+$/, "").toLowerCase();
  return sources.map((source, order) => {
    const saved = groups.find((group) => normalizeUrl(group.url) === normalizeUrl(source.label));
    return {
      order,
      orderStatus: source.status === "running" ? 0 : source.status === "pending" ? 1 : 2,
      row: {
        name: saved?.name?.trim() || groupName(source.label),
        target: source.target ?? null,
        collected: source.collected ?? 0,
      skipped_old: source.skipped_old ?? 0,
      skipped_dup: source.skipped_dup ?? 0,
        stop_reason: source.stop_reason ?? null as StopReason | null,
        status: source.status === "pending" || source.status === "running" || source.status === "error" ? source.status : "done" as const,
      },
    };
  }).sort((left, right) => (prioritizeActive ? left.orderStatus - right.orderStatus : 0) || left.order - right.order)
    .map(({ row }) => row);
}

const MAIN_PHASES = ["scrape_total", "analysis", "summary"] as const;
const DETAIL_PHASES = ["navigation", "scroll_wait", "expand", "link_resolve", "extract"] as const;
export type TimingKey = (typeof MAIN_PHASES)[number] | (typeof DETAIL_PHASES)[number];

/** Chỉ giữ các giai đoạn có số đo (lượt cũ không có), theo thứ tự hiển thị. */
export function runTimingSummary(timings: Record<string, number> | undefined) {
  if (!timings) return null;
  const pick = (keys: readonly TimingKey[]) => keys.filter((key) => typeof timings[key] === "number").map((key) => ({ key, seconds: timings[key] }));
  const main = pick(MAIN_PHASES), detail = pick(DETAIL_PHASES);
  return main.length || detail.length ? { main, detail } : null;
}
