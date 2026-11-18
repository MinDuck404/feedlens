import { Briefcase, Check, CheckCircle2, Copy, ExternalLink, FileSearch, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { formatNumber, serverMessage, useI18n, type Key } from "../i18n";
import { routeHref, type RunTab } from "../router";
import type { AIProviderInfo, Meta, Post, Run, RunRequest, ScrapeReport, Topic } from "../types";
import { filterTopicPosts, topicColor } from "../topics";
import { ModelPicker } from "./Composer";

import { canContinueAnalysis, defaultRunTab, describeRunSource, formatDuration, isRemoteText, jobPresentation, matchesJobType, parseTimestamp, runTimingSummary, type TimingKey } from "../logic";

import { Button, IconButton, Skeleton, SkeletonCard, EmptyState, Select } from "./ui";

const CATEGORY_INK: Record<string, string> = Object.fromEntries(
  ["job", "news", "tech", "marketplace", "question", "event", "promotion", "personal", "entertainment", "other"].map((c) => [c, `var(--cat-${c})`]),
);
const categoryTone = (category: string) => CATEGORY_INK[category] ?? CATEGORY_INK.other;

type Tab = RunTab;

interface Props {
  runId: number;
  meta: Meta;
  tab: Tab;               // tab nằm trong URL (#/runs/12/jobs) nên tải lại trang vẫn giữ
  onTab: (t: Tab) => void;
  onDeleted: () => void;
  onAnalysisStarted?: () => void;
  onRerun?: (request: RunRequest) => void;
}

export default function RunView({ runId, meta, tab, onTab, onDeleted, onAnalysisStarted, onRerun }: Props) {
  const [run, setRun] = useState<Run | null>(null);
  const [missing, setMissing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const setTab = (next: Tab) => {
    if (next === "digest" && run?.request.platform === "linkedin" && run.request.mode === "jobs") window.location.hash = `#/runs/${run.id}/digest`;
    else onTab(next);
  };
  const { t, locale, cat } = useI18n();
  const defaulted = useRef<number | null>(null);
  useEffect(() => {
    if (!run || run.id !== runId || defaulted.current === runId) return;
    defaulted.current = runId;
    if (defaultRunTab(run.request, window.location?.hash ?? "") === "jobs") onTab("jobs");
  }, [run, runId, onTab]);

  useEffect(() => { const reload = () => setRetry((value) => value + 1); window.addEventListener("feedlens:topicsChanged", reload); return () => window.removeEventListener("feedlens:topicsChanged", reload); }, []);

  useEffect(() => {
    let alive = true;
    let timer: number;
    let failures = 0;
    let current: Run | null = null;
    let loadedVersion = -1;
    let lastFullLoad = -Infinity;
    setMissing(false);
    setLoadError(false);
    const load = async () => {
      try {
        let r = await api.run(runId, false);
        if (!alive) return;
        const active = !["done", "error", "analysis_failed"].includes(r.status);
        const changed = current?.status !== r.status;
        const newerPosts = r.posts_version !== undefined && r.posts_version > loadedVersion;
        if (!r.posts && (!current || changed || !active || newerPosts && Date.now() - lastFullLoad >= 10000)) {
          r = await api.run(runId);
          if (!alive) return;
          loadedVersion = r.posts_version ?? loadedVersion;
          lastFullLoad = Date.now();
        } else if (!r.posts && current?.posts) {
          r = { ...r, posts: current.posts };
        }
        current = r;
        setRun(r);
        setLoadError(false);
        failures = 0;
        if (!["done", "error", "analysis_failed"].includes(r.status)) timer = window.setTimeout(load, document.hidden ? 10000 : 1500);
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) { setMissing(true); return; }
        if (e instanceof ApiError && e.status === 401) return;
        setLoadError(true);
        timer = window.setTimeout(load, Math.max(document.hidden ? 10000 : 0, Math.min(30000, 1500 * 2 ** Math.min(failures++, 5))));
      }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [runId, retry]);

  if (missing) {
    return (
      <div className="mx-auto max-w-xl px-6 py-24">
        <h1 className="text-2xl font-semibold tracking-tight">{t("run.notFound", { id: runId })}</h1>
        <p className="mt-2 text-ink-soft">{t("run.maybeDeleted")}</p>
        <a href={routeHref({ page: "history" })} className="mt-6 inline-block rounded-full border border-line px-5 py-2 font-medium hover:border-ink">
          {t("run.viewHistory")}
        </a>
      </div>
    );
  }
  if (!run) return loadError ? <p role="alert" className="m-5 text-sm text-danger">{t("run.retrying")} <Button variant="ghost" onClick={() => setRetry((n) => n + 1)}>{t("act.retry")}</Button></p> : (
    <div className="mx-auto max-w-5xl space-y-6 px-5 py-8 md:px-10" role="status" aria-label={t("act.loading")}>
      <div aria-hidden="true" className="space-y-6"><Skeleton height={18} className="w-40" /><Skeleton height={36} className="w-3/4" /><Skeleton height={44} rounded="full" /><SkeletonCard /><SkeletonCard /></div>
    </div>
  );
  const q = run.request;
  const title = describeRunSource(q, t);
  const when = parseTimestamp(run.created_at);
  const canContinue = canContinueAnalysis(run);
  const failed = run.status === "error" || run.status === "analysis_failed";

  const remove = async () => {
    if (!confirm(t("run.confirmDelete"))) return;
    if (deleting) return;
    setDeleting(true);
    try { await api.deleteRun(run.id); onDeleted(); }
    catch (e) { alert((e as Error).message); }
    finally { setDeleting(false); }
  };

  return (
    <div className="page-enter mx-auto max-w-5xl px-5 py-8 md:px-10 md:py-10">
      {loadError && <p role="alert" className="mt-3 text-sm text-danger">{t("run.retrying")} <button onClick={() => setRetry((n) => n + 1)}>{t("act.retry")}</button></p>}
      <header className="text-center">
        <h1 className="mx-auto max-w-[32ch] font-headline text-2xl leading-tight font-semibold text-balance [overflow-wrap:anywhere] sm:text-3xl md:text-4xl">{title}</h1>
        <p className="mt-4 text-xs leading-relaxed text-ink-soft [overflow-wrap:anywhere]">
          {when.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}
          {run.ai_label && t("run.readBy", { ai: run.ai_label })}
        </p>
        {run.request?.scrape_report && <ScrapeReportLine report={run.request.scrape_report} />}
        <div className="mt-2 flex items-center justify-center gap-1 text-ink-soft">
          {!!run.posts?.length && (["md", "csv", "json"] as const).map((f) => (
            <Button key={f} variant="ghost" size="sm" onClick={() => api.download(run.id, f).catch((e) => alert(e.message))} className="font-mono text-xs hover:bg-sunken hover:text-ink hover:underline underline-offset-4">
              .{f}
            </Button>
          ))}
          {onRerun && run.request && (
            <IconButton onClick={() => onRerun(run.request)} aria-label={t("run.rerun")} title={t("run.rerun")} variant="ghost" size="sm" className="hover:text-ink">
              <RotateCcw className="size-3.5" />
            </IconButton>
          )}
          <IconButton onClick={remove} busy={deleting} aria-label={t("run.delete")} variant="ghost" size="sm" className="hover:text-danger">
            <Trash2 className="size-3.5" />
          </IconButton>
        </div>
      </header>
      <hr className="rule-double mt-4" />
      {(q.platform === "reddit" || q.platform === "x") && <p className="mt-3 text-xs leading-relaxed text-ink-soft" role="note">{t(q.platform === "reddit" ? "cmp.warning.redditPolicy" : "cmp.warning.xPolicy")}</p>}

      {failed || canContinue ? (
        <>
        {failed && <div className="paper-card mt-8 rounded-2xl border-danger/40 p-5">
          <p className="font-semibold text-danger">{t(run.status === "analysis_failed" ? "run.analysisFailed" : "run.stopped")}</p>
          <p className="mt-2 text-sm whitespace-pre-wrap [overflow-wrap:anywhere]" title={run.error ?? undefined}>{serverMessage(run.error_code, run.error ?? "")}</p>
        </div>}
        {canContinue && <section className="paper-card mt-5 rounded-2xl p-5"><h2 className="font-headline text-xl">{t("run.continueAnalysis")}</h2><RetryAnalysis key={run.id} run={run} onStarted={() => { setRetry((n) => n + 1); onAnalysisStarted?.(); }} /></section>}
        {!!run.posts?.length && <section className="mt-8"><h2 className="mb-5 font-headline text-2xl">{t("run.savedPosts")}</h2><PostList posts={run.posts} filter={null} setFilter={() => {}} name={cat} /></section>}
        </>
      ) : run.status !== "done" || !run.digest ? (
        <InProgress run={run} />
      ) : (
        <Done run={run} meta={meta} tab={tab} setTab={setTab} />
      )}
    </div>
  );
}

function ScrapeReportLine({ report }: { report: ScrapeReport }) {
  const { t, lang } = useI18n();
  const reason = report.stop_reason && report.stop_reason !== "target_reached" ? t(`run.stop.${report.stop_reason}` as Key) : "";
  const timing = runTimingSummary(report.timings);
  const label = (key: TimingKey, seconds: number) => `${t(`run.timing.${key}` as Key)} ${formatDuration(seconds, lang)}`;
  return (
    <>
      {report.target !== undefined && (
        <p className="mt-1 text-xs leading-relaxed text-ink-soft">
          {t("run.scrapeReport", { got: report.collected ?? 0, target: report.target, old: report.skipped_old ?? 0 })}
          {!!report.skipped_ads && ` · ${t("run.scrapeAds", { n: report.skipped_ads })}`}
          {reason && ` · ${reason}`}
        </p>
      )}
      {timing && (
        <details className="mx-auto mt-1 max-w-prose text-xs leading-relaxed text-ink-soft">
          <summary className="interactive-tap cursor-pointer [overflow-wrap:anywhere]">
            {t("run.timing.title")}: {timing.main.map((p) => label(p.key, p.seconds)).join(" · ")}
          </summary>
          {(timing.detail.length > 0 || !!report.full_text_from_story) && (
            <p className="mt-1 [overflow-wrap:anywhere]">
              {timing.detail.length > 0 && `${t("run.timing.details")}: ${timing.detail.map((p) => label(p.key, p.seconds)).join(" · ")}`}
              {!!report.full_text_from_story && <span className="block">{t("run.timing.fullText", { n: report.full_text_from_story })}</span>}
            </p>
          )}
        </details>
      )}
    </>
  );
}

function RetryAnalysis({ run, onStarted }: { run: Run; onStarted: () => void }) {
  const { t } = useI18n();
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [provider, setProvider] = useState(run.request.ai_provider || "auto");
  const [model, setModel] = useState(run.request.ai_model || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let alive = true; api.providers().then((p) => { if (alive) setProviders(p); }).catch((e) => { if (alive) setError(e.message); }); return () => { alive = false; }; }, []);
  const submit = async () => {
    setBusy(true); setError("");
    try { await api.retryAnalysis(run.id, provider, model); onStarted(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="mt-4 border-t border-line pt-4">
    <p className="text-sm text-ink-soft">{t("run.retryAnalysisHint")}</p>
    <fieldset disabled={busy} className="mt-3 min-w-0 space-y-3">
      <label className="block text-sm">{t("cmp.ai")}<Select aria-label={t("cmp.ai")} className="mt-2" value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); }}>
        <option value="auto">{t("profile.auto")}</option>
        {providers.filter((p) => p.configured && p.key !== "offline").map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
        {provider !== "auto" && provider !== "offline" && !providers.some((p) => p.key === provider && p.configured) && <option value={provider}>{provider}</option>}
        <option value="offline">{t("profile.offlineOption")}</option>
      </Select></label>
      {provider !== "auto" && provider !== "offline" && <ModelPicker provider={provider} value={model} onChange={setModel} />}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <Button busy={busy} onClick={submit}>{t("run.continueAnalysis")}</Button>
    </fieldset>
  </div>;
}

function InProgress({ run }: { run: Run }) {
  const p = run.progress;
  const { t } = useI18n();
  const pct = p?.target ? Math.min(100, Math.round((p.done / p.target) * 100)) : 0;
  const phase = run.status === "pending" ? t("run.phase.pending")
    : run.status === "scraping" ? t("run.phase.scraping") : run.status === "analyzing" ? t("run.phase.analyzing") : t("run.phase.preparing");
  return (
    <div className="mt-10 max-w-lg">
      <p role="status" className="font-semibold">{phase}</p>
      <div role="progressbar" aria-label={phase} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="mt-4 h-1.5 overflow-hidden rounded-full bg-sunken">
        <div className="h-full w-full origin-left rounded-full bg-accent transition-transform duration-[var(--duration-normal)] ease-[var(--ease-micro)] motion-reduce:transition-none" style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
      <p className="mt-2 text-sm text-ink-soft">{p ? serverMessage(p.message_code ?? `progress.${p.phase}`, p.message, { ...p.message_vars, done: p.done, target: p.target }) : (run.status === "pending" ? t("run.pendingHint") : t("run.openingBrowser"))}</p>
    </div>
  );
}

type RunPostFilters = { category: string | null; topicId: number | null };

export function runPostFiltersFromHash(hash: string): RunPostFilters {
  const [path, query = ""] = hash.split("?");
  if (!/^#\/runs\/\d+\/posts$/.test(path)) return { category: null, topicId: null };
  const params = new URLSearchParams(query);
  const category = params.get("category");
  const value = Number(params.get("topic"));
  return {
    category: category && Object.prototype.hasOwnProperty.call(CATEGORY_INK, category) ? category : null,
    topicId: Number.isSafeInteger(value) && value > 0 ? value : null,
  };
}

export function runPostsHref(runId: number, filters: RunPostFilters): string {
  const params = new URLSearchParams();
  if (filters.category && Object.prototype.hasOwnProperty.call(CATEGORY_INK, filters.category)) params.set("category", filters.category);
  if (filters.topicId !== null && Number.isSafeInteger(filters.topicId) && filters.topicId > 0) params.set("topic", String(filters.topicId));
  return routeHref({ page: "run", id: runId, tab: "posts" }) + (params.size ? `?${params}` : "");
}

function Done({ run, meta, tab: requested, setTab }: {
  run: Run; meta: Meta; tab: Tab; setTab: (t: Tab) => void;
}) {
  const posts = run.posts ?? [];
  const d = run.digest!;
  const [filters, setFilters] = useState(() => runPostFiltersFromHash(window.location?.hash ?? ""));
  const { category: filter, topicId } = filters;
  const panel = useRef<HTMLDivElement>(null);
  const jumpToPosts = useRef(filter !== null || topicId !== null);
  useEffect(() => {
    const sync = () => {
      jumpToPosts.current = true;
      setFilters(runPostFiltersFromHash(window.location.hash));
    };
    sync();
    window.addEventListener("hashchange", sync); return () => window.removeEventListener("hashchange", sync);
  }, [run.id]);
  useEffect(() => {
    if (requested !== "posts" || !jumpToPosts.current) return;
    jumpToPosts.current = false;
    panel.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    panel.current?.focus({ preventScroll: true });
  }, [requested, filters]);
  const selectPosts = (next: RunPostFilters) => {
    jumpToPosts.current = true; setFilters(next);
    const href = runPostsHref(run.id, next);
    if (window.location.hash !== href) window.location.hash = href;
    else { panel.current?.scrollIntoView({ block: "start" }); panel.current?.focus({ preventScroll: true }); }
  };
  const selectTopic = (id: number | null) => selectPosts({ ...filters, topicId: id });
  const selectCategory = (category: string | null) => selectPosts({ ...filters, category });
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicError, setTopicError] = useState("");
  useEffect(() => {
    let alive = true;
    api.topics().then((data) => { if (alive) setTopics(data.topics); }).catch((e) => { if (alive) setTopicError(e.message); });
    return () => { alive = false; };
  }, [run.id, run.digest]);
  const jobs = useMemo(
    () => posts.filter((p) => p.job || p.job_seed).map((p) => ({ ...p, ...jobPresentation(p) })).sort((a, b) => b.job!.match_score - a.job!.match_score),
    [posts],
  );
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    posts.forEach((p) => m.set(p.category, (m.get(p.category) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [posts]);
  const { t, cat, lang } = useI18n();
  void meta;  // tên loại bài lấy theo ngôn ngữ giao diện thay vì meta.categories (tiếng Việt)
  const name = cat;
  const tab: Tab = requested === "jobs" && !jobs.length && run.request.mode !== "jobs" ? "digest" : requested;

  const categoryBar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const bar = categoryBar.current;
    if (!bar || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const tokens = getComputedStyle(bar);
    bar.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], {
      duration: parseFloat(tokens.getPropertyValue("--duration-normal")),
      easing: tokens.getPropertyValue("--ease-micro").trim(),
    });
  }, [run.id]);

  const pick = selectCategory;

  return (
    <>
      {/* Thanh phân loại: điểm nhấn của trang, đồng thời là bộ lọc */}
      <section className="mt-4 min-w-0" aria-label={t("run.composition")}>
        <p className="mb-2 text-xs text-ink-soft">{t("run.postsCount", { n: posts.length })}</p>
        <div ref={categoryBar} className="flex h-1.5 w-full origin-left gap-0.5">
          {counts.map(([c, n]) => (
            <button key={c} onClick={() => pick(c)} title={t("run.catCount", { name: name(c), n })}
              aria-label={t("run.catCount", { name: name(c), n })} aria-pressed={filter === c}
              className="relative h-full rounded-full transition-opacity before:absolute before:inset-x-0 before:-inset-y-3 hover:opacity-80 focus-visible:z-10 focus-visible:outline-offset-2"
              style={{ flexGrow: n, flexBasis: 0, minWidth: 6, background: categoryTone(c), opacity: filter && filter !== c ? 0.3 : 1 }} />
          ))}
        </div>
        <ul className="mt-2 flex max-w-full gap-1 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:pr-0 sm:[mask-image:none]">
          {counts.map(([c, n]) => (
            <li key={c} className="shrink-0">
              <button onClick={() => pick(c)} aria-pressed={filter === c} aria-label={t("run.viewCategory", { name: name(c), n })} className="interactive-tap flex min-h-10 items-center gap-1.5 rounded-sm px-2 py-1 text-xs hover:bg-sunken focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2 aria-pressed:bg-sunken aria-pressed:font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: categoryTone(c) }} />
                {name(c)} <span className="font-mono text-xs text-ink-soft">{formatNumber(n, lang)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {topics.length > 0 && <section aria-label={t("topics.yours")} className="mt-3 min-w-0"><h2 className="text-xs text-ink-soft">{t("topics.yours")}</h2><div className="mt-1 flex gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:flex-wrap sm:pr-0 sm:[mask-image:none]">
        {topics.map((topic) => <button key={topic.id} type="button" onClick={() => selectTopic(topic.id)} aria-label={t("run.catCount", { name: topic.name, n: filterTopicPosts(posts, topic.id).length })} aria-pressed={topicId === topic.id && tab === "posts"} className="flex min-h-10 shrink-0 items-center gap-2 rounded-full border border-line px-3 text-xs hover:bg-sunken aria-pressed:bg-sunken aria-pressed:font-semibold"><span className="size-2 rounded-full" style={{ background: topicColor(topic.color) }} />{topic.name}<span className="font-mono text-ink-soft">{formatNumber(filterTopicPosts(posts, topic.id).length, lang)}</span></button>)}
      </div></section>}

      <nav data-run-tabs className="mt-3 flex gap-1 border-b border-line" role="tablist" aria-label={t("run.composition")}>
        {([["digest", t("tab.digest")], ...(jobs.length ? [["jobs", t("tab.jobs", { n: jobs.length })]] : []), ["posts", t("tab.posts")]] as [Tab, string][])
          .map(([k, l], index, tabs) => (
            <button key={k} id={`run-${run.id}-tab-${k}`} role="tab" aria-selected={tab === k}
              aria-controls={`run-${run.id}-panel`} tabIndex={tab === k ? 0 : -1} onClick={() => setTab(k)}
              onKeyDown={(e) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                e.preventDefault();
                const next = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                setTab(tabs[next][0]);
                e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
              }}
              className="interactive-tap -mb-px min-h-12 flex-1 border-b-2 border-transparent px-2 py-3 text-sm text-ink-soft transition-colors duration-[var(--duration-fast)] hover:text-ink focus:outline-none! focus-visible:outline-solid! focus-visible:outline-1! focus-visible:outline-ink/35! focus-visible:-outline-offset-4! focus-visible:rounded-lg! aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink sm:flex-none sm:px-5">
              {l}
            </button>
          ))}
      </nav>

      <div ref={panel} key={tab} role="tabpanel" id={`run-${run.id}-panel`} aria-labelledby={`run-${run.id}-tab-${tab}`} tabIndex={0} className="page-enter min-w-0 scroll-mt-20 py-7">
        {topicError && <p role="alert" className="mb-4 text-sm text-danger">{topicError}</p>}
        {tab === "digest" && <DigestView d={d} name={name} posts={posts} topics={topics} onTopic={selectTopic} onCategory={selectCategory} />}
        {tab === "jobs" && <JobsBoard jobs={jobs} runId={run.id} />}
        {tab === "posts" && <PostList posts={posts} filter={filter} setFilter={selectCategory} name={name} topics={topics} topicId={topicId} onTopicChange={selectTopic} />}
      </div>
    </>
  );
}

function DigestView({ d, name, posts, topics, onTopic, onCategory }: { d: NonNullable<Run["digest"]>; name: (c: string) => string; posts: Post[]; topics: Topic[]; onTopic: (id: number) => void; onCategory: (category: string) => void }) {
  const { t, locale } = useI18n();
  const byId = new Map(posts.map((post) => [post.id, post]));
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_240px]">
      <div className="min-w-0">
        {!!d.topics?.length && <section className="mb-8 border-b border-line pb-7" aria-label={t("topics.yours")}>
          <h2 className="mb-5 font-headline text-3xl font-semibold">{t("topics.yours")}</h2>
          <div className="divide-y divide-line">{d.topics.map((topic) => {
            const featured = topic.post_ids.map((id) => byId.get(id)).filter((post): post is Post => !!post).slice(0, 3);
            const remaining = Math.max(0, topic.count - featured.length);
            const summary = [...new Intl.Segmenter(locale, { granularity: "sentence" }).segment(topic.summary)].slice(0, 2).map((part) => part.segment).join("");
            return <section key={topic.topic_id} className="py-4 first:pt-0">
              <h3 className="flex flex-wrap items-baseline gap-2 font-headline text-xl"><span className="size-2.5 shrink-0 rounded-full" style={{ background: topicColor(topics.find((item) => item.id === topic.topic_id)?.color ?? "red") }} /><button onClick={() => onTopic(topic.topic_id)} className="min-h-10 text-left hover:text-link">{topic.name}</button><span className="font-sans text-xs text-ink-soft">{t("run.nPosts", { n: topic.count })}</span></h3>
              {topic.count === 0 ? <p className="mt-2 text-sm text-ink-soft">{t("topics.noMatch")}</p> : <>
                {summary && <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-soft [overflow-wrap:anywhere]">{summary}</p>}
                <ul className="mt-3 space-y-1">{featured.map((post) => <li key={post.id} className="flex items-start gap-2 text-sm [overflow-wrap:anywhere]"><span className="min-w-0 flex-1 py-1.5">{post.summary || post.text.slice(0, 160)}</span>{post.url && <a href={post.url} target="_blank" rel="noopener noreferrer" title={t("posts.openOriginal")} aria-label={`${t("posts.openOriginal")}: ${post.summary || post.text.slice(0, 80)}`} className="grid size-9 shrink-0 place-items-center text-ink-soft hover:text-link"><ExternalLink aria-hidden="true" className="size-3.5" /></a>}</li>)}</ul>
              </>}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">{remaining > 0 && <span className="text-ink-soft">{t(remaining === 1 ? "topics.moreOne" : "topics.more", { n: remaining })} ·</span>}<button onClick={() => onTopic(topic.topic_id)} className="min-h-10 font-medium text-link hover:underline">{t("topics.viewAll")}</button></div>
            </section>;
          })}</div>
        </section>}
        <p className="prose-reading text-xl! leading-relaxed! [overflow-wrap:anywhere] sm:text-2xl!">{d.overall}</p>
        <div className="mt-8 space-y-7">
          {d.categories.map((c) => (
            <section key={c.category} className="border-t border-line pt-5">
              <h3 className="flex flex-wrap items-baseline gap-2 font-headline text-2xl font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: categoryTone(c.category) }} />
                <button type="button" onClick={() => onCategory(c.category)} aria-label={t("run.viewCategory", { name: name(c.category), n: c.count })} className="group flex min-h-11 flex-wrap items-baseline gap-x-3 gap-y-1 rounded-sm text-left transition-colors hover:text-link focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-4">
                  <span>{name(c.category)}</span><span className="font-sans text-xs font-normal text-ink-soft group-hover:text-link">{t("run.viewCategoryCount", { n: c.count })}</span>
                </button>
              </h3>
              <p className="prose-reading mt-3 [overflow-wrap:anywhere]">{c.summary}</p>
              {c.highlights.length > 0 && (
                <ul className="prose-reading mt-3 list-disc space-y-2 pl-5 [overflow-wrap:anywhere]">
                  {c.highlights.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              )}
            </section>
          ))}
        </div>
      </div>
      {d.action_items.length > 0 && (
        <aside className="h-fit border border-[var(--field-line)] bg-sunken p-4 lg:sticky lg:top-6">
          <h3 className="font-headline text-xl font-semibold">{t("run.nextSteps")}</h3>
          <ul className="mt-3 space-y-2.5">
            {d.action_items.map((a, i) => (
              <li key={i}>
                <label className="flex min-h-10 gap-3 py-1 text-sm [overflow-wrap:anywhere]">
                  <input type="checkbox" className="peer sr-only" />
                  <span aria-hidden="true" className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-[4px] border border-ink-faint bg-surface text-transparent transition-colors duration-[var(--duration-fast)] peer-checked:border-primary peer-checked:bg-primary peer-checked:text-primary-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent peer-focus-visible:outline-offset-2">
                    <Check className="size-3" strokeWidth={2.5} />
                  </span>
                  <span className="min-w-0 flex-1 leading-relaxed">{a}</span>
                </label>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}

const tierOf = (v: number): { key: Key; color: string } =>
  v >= 70 ? { key: "tier.good", color: "var(--ok)" } : v >= 40 ? { key: "tier.maybe", color: "var(--warning)" } : { key: "tier.low", color: "var(--ink-soft)" };

/** Vòng điểm phù hợp 0–100 */
function ScoreRing({ v }: { v: number }) {
  const tier = tierOf(v);
  const { t } = useI18n();
  const r = 22, c = 2 * Math.PI * r;
  return (
    <div role="img" className="relative grid size-12 shrink-0 place-items-center sm:size-14" aria-label={t("job.scoreAria", { v, tier: t(tier.key) })}>
      <svg aria-hidden="true" viewBox="0 0 56 56" className="absolute inset-0 -rotate-90">
        <circle cx="28" cy="28" r={r} fill="none" stroke="var(--line)" strokeWidth="4" />
        <circle cx="28" cy="28" r={r} fill="none" stroke={tier.color} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} />
      </svg>
      <span className="font-mono text-sm font-medium">{v}</span>
    </div>
  );
}

type JobFilter = "all" | "good" | "remote";
type JobSort = "score" | "salary" | "source";
const isRemote = (p: Post) => isRemoteText(`${p.job?.work_mode} ${p.job?.location} ${p.text}`);

/** Nhớ việc đã ứng tuyển theo từng lượt, chỉ trên trình duyệt này */
function useApplied(runId: number) {
  const key = `feedlens.applied.${runId}`;
  const [set, setSet] = useState<Set<number>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem(key) ?? "[]")); } catch { return new Set(); }
  });
  const toggle = (id: number) => setSet((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    try { localStorage.setItem(key, JSON.stringify([...n])); } catch { /* chế độ riêng tư */ }
    return n;
  });
  return [set, toggle] as const;
}

function JobsBoard({ jobs, runId }: { jobs: Post[]; runId: number }) {
  const [filter, setFilter] = useState<JobFilter>("all");
  const [sort, setSort] = useState<JobSort>("score");
  const [matchType, setMatchType] = useState("all");
  const [q, setQ] = useState("");
  const [applied, toggleApplied] = useApplied(runId);
  const { t, locale, lang } = useI18n();
  const good = jobs.filter((p) => p.job!.match_score >= 70).length;
  const remote = jobs.filter(isRemote).length;

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let list = jobs.filter((p) =>
      matchesJobType(p.job?.match_type, matchType) &&
      (filter === "all" || (filter === "good" ? p.job!.match_score >= 70 : isRemote(p))) &&
      (!needle || `${p.job!.title} ${p.job!.company} ${p.job!.location} ${p.summary}`.toLowerCase().includes(needle)));
    if (sort === "salary") list = [...list].sort((a, b) => Number(!!b.job!.salary) - Number(!!a.job!.salary) || b.job!.match_score - a.job!.match_score);
    if (sort === "source") list = [...list].sort((a, b) => a.source.localeCompare(b.source, locale) || b.job!.match_score - a.job!.match_score);
    return list;
  }, [jobs, filter, sort, q, locale, matchType]);

  const chips: [JobFilter, string, number][] = [["all", t("job.filterAll"), jobs.length], ["good", t("job.filterGood"), good], ["remote", t("job.filterRemote"), remote]];

  return (
    <div>
      <div className="grid grid-cols-3 divide-x divide-line border-b border-line pb-6">
        {([[t("job.statFound"), jobs.length], [t("job.statGood"), good], [t("job.statApplied"), applied.size]] as [string, number][]).map(([l, n]) => (
          <div key={l} className="min-w-0 px-3 first:pl-0 last:pr-0 sm:px-6">
            <div className="font-mono text-2xl font-medium">{formatNumber(n, lang)}</div>
            <div className="mt-1 text-xs leading-relaxed text-ink-soft">{l}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 space-y-2 sm:flex sm:flex-wrap sm:items-center sm:gap-2 sm:space-y-0">
        <div className="flex min-w-0 gap-2 overflow-x-auto pr-5 pb-1 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:pr-0 sm:pb-0 sm:[mask-image:none]">
        {chips.map(([k, l, n]) => (
          <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}
            className="interactive-tap min-h-11 shrink-0 whitespace-nowrap rounded-full border border-line px-3.5 py-2 text-sm hover:border-ink aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-ink">
            {l} <span className="font-mono text-xs opacity-70">{formatNumber(n, lang)}</span>
          </button>
        ))}
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-2 sm:flex sm:flex-1 sm:flex-wrap">
        <div className="col-span-2 flex min-h-11 min-w-0 items-center rounded-full border border-[var(--field-line)] bg-[var(--field-bg)] px-4 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-glow)] sm:ml-auto sm:w-56">
          <input className="min-w-0 w-full bg-transparent py-2 text-sm text-ink border-0! outline-none! ring-0! [box-shadow:none]! focus-visible:outline-none! placeholder:text-ink-soft" placeholder={t("job.search")}
            value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("job.searchAria")} />
        </div>
        <select className="field min-h-11 min-w-0 w-full rounded-full sm:w-auto" value={matchType} onChange={(e) => setMatchType(e.target.value)} aria-label={t("profile.matchFilter")}>
          {["all", "primary", "adjacent", "stretch", "none"].map((type) => <option key={type} value={type}>{t(`profile.match.${type}` as Key)}</option>)}
        </select>
        <select className="field min-h-11 min-w-0 w-full rounded-full sm:w-auto" value={sort} onChange={(e) => setSort(e.target.value as JobSort)} aria-label={t("job.sort")}>
          <option value="score">{t("job.sortScore")}</option>
          <option value="salary">{t("job.sortSalary")}</option>
          <option value="source">{t("job.sortSource")}</option>
        </select>
        </div>
      </div>

      {shown.length === 0 ? (
        <EmptyState className="mt-6" icon={<Briefcase className="size-6" />} title={t("job.none")}
          action={{ label: t("act.seeAll"), onClick: () => { setFilter("all"); setMatchType("all"); setQ(""); } }} />
      ) : (
        <ul className="mt-5 space-y-3">
          {shown.map((p) => <JobCard key={p.id} p={p} applied={applied.has(p.id)} onApplied={() => toggleApplied(p.id)} />)}
        </ul>
      )}
    </div>
  );
}

function JobCard({ p, applied, onApplied }: { p: Post; applied: boolean; onApplied: () => void }) {
  const presentation = jobPresentation(p);
  const j = presentation.job!;
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const workMode = j.work_mode?.trim().toLowerCase();
  const tags = [
    j.location && { label: j.location },
    j.work_mode && { label: workMode && ["remote", "hybrid", "onsite"].includes(workMode) ? t(`profile.mode.${workMode}` as Key) : j.work_mode },
    j.salary && { label: j.salary },
  ].filter(Boolean) as { label: string; mono?: boolean }[];
  const copy = async () => {
    try { await navigator.clipboard.writeText(j.contact); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { alert(t("act.copyFailed")); }
  };

  return (
    <li className={`stagger-item border-b border-line py-6 [overflow-wrap:anywhere] ${applied ? "bg-ok/5" : ""}`}>
      <div className="flex gap-3 sm:gap-4">
        <ScoreRing v={j.match_score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-col items-start gap-x-2 gap-y-1 sm:flex-row sm:flex-wrap sm:items-baseline">
            <h3 className="min-w-0 font-headline text-xl leading-snug font-semibold text-balance [overflow-wrap:anywhere]">{j.title || p.summary}</h3>
            {j.match_type && j.match_type !== "none" && <span className="order-first text-xs font-medium text-link sm:order-last">{t(`profile.match.${j.match_type}` as Key)}</span>}
          </div>
          <p className="mt-0.5 text-sm text-ink-soft">
            {j.company || t("job.unknownCompany")}<span className="mx-1.5">/</span>{p.source}
          </p>
          {tags.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {tags.map((tg) => (
                <span key={tg.label} className={`max-w-full rounded-tag bg-sunken px-2.5 py-1 text-xs [overflow-wrap:anywhere] ${tg.mono ? "font-mono" : ""}`}>{tg.label}</span>
              ))}
            </div>
          )}
          {!!j.gaps?.length && <p className="mt-2 text-sm text-ink-soft">{t("profile.gaps")} {j.gaps.join(" · ")}</p>}
          {!!j.constraint_flags?.length && <ul className="mt-2 border border-warning/50 bg-warning/10 p-3 text-sm text-ink">{j.constraint_flags.map((flag) => <li key={flag}>{t(`profile.flag.${flag}` as Key)}</li>)}</ul>}
          {j.match_reason && <p className="mt-3 max-w-[70ch] text-sm leading-relaxed text-ink-soft [overflow-wrap:anywhere]">{j.match_reason}</p>}
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            {j.contact && (
              <button onClick={copy} title={j.contact}
                className="interactive-tap flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:border-ink">
                {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />}
                <span className="truncate text-xs">{copied ? t("act.copied") : j.contact}</span>
              </button>
            )}
            {presentation.url && <a href={presentation.url} target="_blank" rel="noopener noreferrer" aria-label={t("job.openOriginalAria", { title: j.title || p.summary })} className="interactive-tap inline-flex min-h-11 items-center gap-1.5 rounded-full border border-line px-3 py-2 text-sm text-link hover:border-ink"><span>{t("job.openOriginal")}</span><ExternalLink aria-hidden="true" className="size-3.5" /></a>}
            <button onClick={onApplied} aria-pressed={applied}
              className="interactive-tap flex min-h-11 items-center gap-2 rounded-full border border-line px-3 py-2 text-sm text-ink-soft hover:text-ink aria-pressed:border-ok/30 aria-pressed:bg-ok/5 aria-pressed:text-ok sm:ml-auto">
              <CheckCircle2 className="size-4" /> {applied ? t("job.applied") : t("job.markApplied")}
            </button>
          </div>
        </div>
      </div>
    </li>
  );
}

function PostList({ posts, filter, setFilter, name, topics = [], topicId = null, onTopicChange = () => {} }: {
  posts: Post[]; filter: string | null; setFilter: (c: string | null) => void; name: (c: string) => string; topics?: Topic[]; topicId?: number | null; onTopicChange?: (id: number | null) => void;
}) {
  const shown = filterTopicPosts(filter ? posts.filter((p) => p.category === filter) : posts, topicId);
  const { t } = useI18n();
  const [categoryBefore, categoryAfter] = t("posts.viewingCategory", { n: shown.length, category: "{category}" }).split("{category}");
  return (
    <>
      {!!(topics.length || topicId !== null) && <div className="mb-5 flex gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)]" role="group" aria-label={t("topics.title")}>
        <button type="button" aria-pressed={topicId === null} onClick={() => onTopicChange(null)} className="min-h-11 shrink-0 rounded-full border border-line px-3 text-sm aria-pressed:bg-sunken aria-pressed:font-semibold">{t("topics.all")}</button>
        {topics.map((topic) => <button key={topic.id} type="button" aria-pressed={topicId === topic.id} onClick={() => onTopicChange(topicId === topic.id ? null : topic.id)} className="flex min-h-11 shrink-0 items-center gap-2 rounded-full border border-line px-3 text-sm aria-pressed:bg-sunken aria-pressed:font-semibold"><span className="size-2 rounded-full" style={{ background: topicColor(topic.color) }} />{topic.name}</button>)}
      </div>}
      {filter && (
        <p className="mb-4 text-sm">
          {categoryBefore}<b>{name(filter)}</b>{categoryAfter}{" "}
          <button onClick={() => setFilter(null)} className="text-link hover:underline">{t("act.seeAll")}</button>
        </p>
      )}
      {shown.length === 0 && <EmptyState icon={<FileSearch className="size-6" />} title={t("hist.empty")} />}
      <ul className="divide-y divide-line-strong">
        {shown.map((p) => <ReadingPost key={p.id} p={p} name={name} topics={topics} />)}
      </ul>
    </>
  );
}


function ReadingPost({ p, name, topics }: { p: Post; name: (c: string) => string; topics: Topic[] }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="stagger-item min-w-0 py-7 first:pt-0 [overflow-wrap:anywhere]">
      <article>
        <h3 className="max-w-[38ch] font-headline text-2xl leading-snug font-semibold sm:text-3xl">{p.summary || p.text.slice(0, 100)}</h3>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs leading-relaxed text-ink-soft">
          <span className="font-medium" style={{ color: categoryTone(p.category) }}>{p.analyzed === false ? t("run.rawPost") : name(p.category)}</span>
          <span>{p.source}</span>
          <span>{p.author || t("posts.unknownAuthor")}</span>
          {p.sponsored && <span className="rounded-full border border-line px-2 py-0.5 text-xs text-ink-soft">{t("posts.sponsored")}</span>}
        </div>
        {!!p.topic_ids?.length && <ul className="mt-3 flex flex-wrap gap-2" aria-label={t("topics.title")}>{p.topic_ids.map((id) => topics.find((topic) => topic.id === id)).filter((topic): topic is Topic => !!topic).map((topic) => <li key={topic.id}><span tabIndex={p.topic_reason ? 0 : undefined} title={p.topic_reason} aria-label={p.topic_reason ? `${topic.name}: ${p.topic_reason}` : topic.name} className="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs" style={{ color: topicColor(topic.color), borderColor: topicColor(topic.color) }}><span className="size-1.5 shrink-0 rounded-full bg-current" />{topic.name}</span></li>)}</ul>}
        <p id={`post-${p.id}-text`} className={`prose-reading mt-4 whitespace-pre-wrap [overflow-wrap:anywhere] ${expanded ? "" : "line-clamp-3"}`}>{p.text}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
          <button type="button" aria-expanded={expanded} aria-controls={`post-${p.id}-text`} onClick={() => setExpanded((v) => !v)}
            className="min-h-10 text-ink-soft underline decoration-line underline-offset-4 hover:text-ink">
            {t(expanded ? "posts.readLess" : "posts.readMore")}
          </button>
          {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-10 items-center gap-1.5 font-medium text-link underline underline-offset-4 hover:decoration-2">
            {t("posts.openOriginal")} <ExternalLink aria-hidden="true" className="size-3.5" />
          </a>}
        </div>
      </article>
    </li>
  );
}
