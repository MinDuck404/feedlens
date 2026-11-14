import { Briefcase, Check, CheckCircle2, ChevronDown, Copy, ExternalLink, FileSearch, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { formatNumber, serverMessage, useI18n, type Key } from "../i18n";
import { routeHref, type RunTab } from "../router";
import type { Meta, Post, Run } from "../types";

import { isRemoteText, parseTimestamp } from "../logic";

import { Button, IconButton, Skeleton, SkeletonCard, EmptyState } from "./ui";

// Equal lightness/chroma keeps categories quiet beside the coral action color.
const CATEGORY_HUE: Record<string, number> = { job: 155, news: 250, tech: 300, marketplace: 350, question: 195, event: 85, promotion: 35, personal: 100, entertainment: 120, other: 80 };
const categoryTone = (category: string) => `oklch(70% 0.045 ${CATEGORY_HUE[category] ?? 80})`;

type Tab = RunTab;

interface Props {
  runId: number;
  meta: Meta;
  tab: Tab;               // tab nằm trong URL (#/runs/12/jobs) nên tải lại trang vẫn giữ
  onTab: (t: Tab) => void;
  onDeleted: () => void;
}

export default function RunView({ runId, meta, tab, onTab, onDeleted }: Props) {
  const [run, setRun] = useState<Run | null>(null);
  const [missing, setMissing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const setTab = onTab;
  const { t, locale } = useI18n();

  useEffect(() => {
    let alive = true;
    let timer: number;
    let failures = 0;
    setMissing(false);
    setLoadError(false);
    const load = async () => {
      try {
        const r = await api.run(runId);
        if (!alive) return;
        setRun(r);
        setLoadError(false);
        failures = 0;
        if (!["done", "error"].includes(r.status)) timer = window.setTimeout(load, 1500);
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) { setMissing(true); return; }
        if (e instanceof ApiError && e.status === 401) return;
        setLoadError(true);
        timer = window.setTimeout(load, Math.min(30000, 1500 * 2 ** Math.min(failures++, 5)));
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
  const title = q.source_type === "feed" ? t("run.feedOf", { platform: PLATFORM_LABEL[q.platform] })
    : q.sources.length > 1 ? t("run.andMore", { first: q.sources[0], n: q.sources.length - 1 }) : q.sources[0];
  const when = parseTimestamp(run.created_at);

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
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 basis-full sm:flex-1">
          <p className="text-xs leading-relaxed text-ink-soft [overflow-wrap:anywhere]">
            {when.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}
            {run.ai_label && t("run.readBy", { ai: run.ai_label })}
          </p>
          <h1 className="mt-2 text-2xl leading-tight font-semibold tracking-tight text-balance [overflow-wrap:anywhere] md:text-3xl">{title}</h1>
        </div>
        <div className="flex items-center gap-1">
          {run.status === "done" && (["md", "csv", "json"] as const).map((f) => (
            <Button key={f} variant="outline" size="sm" onClick={() => api.download(run.id, f).catch((e) => alert(e.message))} className="min-h-10 font-mono">
              .{f}
            </Button>
          ))}
          <IconButton onClick={remove} busy={deleting} aria-label={t("run.delete")} variant="outline" className="ml-1 size-10 hover:border-danger hover:text-danger">
            <Trash2 className="size-4" />
          </IconButton>
        </div>
      </header>

      {run.status === "error" ? (
        <div className="paper-card mt-8 rounded-2xl border-danger/40 p-5">
          <p className="font-semibold text-danger">{t("run.stopped")}</p>
          <p className="mt-2 text-sm whitespace-pre-wrap [overflow-wrap:anywhere]" title={run.error ?? undefined}>{serverMessage(run.error_code, run.error ?? "")}</p>
        </div>
      ) : run.status !== "done" || !run.digest ? (
        <InProgress run={run} />
      ) : (
        <Done run={run} meta={meta} tab={tab} setTab={setTab} filter={filter} setFilter={setFilter} />
      )}
    </div>
  );
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
      <p className="mt-2 text-sm text-ink-soft">{p ? serverMessage(p.message_code ?? `progress.${p.phase}`, p.message, { done: p.done, target: p.target }) : (run.status === "pending" ? t("run.pendingHint") : t("run.openingBrowser"))}</p>
    </div>
  );
}

function Done({ run, meta, tab: requested, setTab, filter, setFilter }: {
  run: Run; meta: Meta; tab: Tab; setTab: (t: Tab) => void; filter: string | null; setFilter: (c: string | null) => void;
}) {
  const posts = run.posts ?? [];
  const d = run.digest!;
  const jobs = useMemo(
    () => posts.filter((p) => p.job).sort((a, b) => b.job!.match_score - a.job!.match_score),
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
  const tab: Tab = requested === "jobs" && !jobs.length ? "digest" : requested;  // URL cũ trỏ vào tab không còn

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

  const pick = (c: string) => { setFilter(filter === c ? null : c); setTab("posts"); };

  return (
    <>
      {/* Thanh phân loại: điểm nhấn của trang, đồng thời là bộ lọc */}
      <section className="mt-8 border-t border-line pt-6" aria-label={t("run.composition")}>
        <p className="mb-2 text-sm text-ink-soft">{t("run.postsCount", { n: posts.length })}</p>
        <div ref={categoryBar} className="flex h-2.5 w-full origin-left gap-0.5">
          {counts.map(([c, n]) => (
            <button key={c} onClick={() => pick(c)} title={t("run.catCount", { name: name(c), n })}
              aria-label={t("run.catCount", { name: name(c), n })} aria-pressed={filter === c}
              className="relative h-full rounded-full transition-opacity before:absolute before:inset-x-0 before:-inset-y-3 hover:opacity-80 focus-visible:z-10 focus-visible:outline-offset-2"
              style={{ flexGrow: n, flexBasis: 0, minWidth: 6, background: categoryTone(c), opacity: filter && filter !== c ? 0.3 : 1 }} />
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-1">
          {counts.map(([c, n]) => (
            <li key={c}>
              <button onClick={() => pick(c)} aria-pressed={filter === c} className="interactive-tap flex min-h-10 items-center gap-2 rounded-full px-3 py-1 text-sm hover:bg-sunken aria-pressed:bg-sunken aria-pressed:font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: categoryTone(c) }} />
                {name(c)} <span className="font-mono text-xs text-ink-soft">{formatNumber(n, lang)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <nav data-run-tabs className="mt-7 flex gap-1 border-b border-line" role="tablist" aria-label={t("run.composition")}>
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

      <div key={tab} role="tabpanel" id={`run-${run.id}-panel`} aria-labelledby={`run-${run.id}-tab-${tab}`} tabIndex={0} className="page-enter min-w-0 py-7">
        {tab === "digest" && <DigestView d={d} name={name} />}
        {tab === "jobs" && <JobsBoard jobs={jobs} runId={run.id} />}
        {tab === "posts" && <PostList posts={posts} filter={filter} setFilter={setFilter} name={name} />}
      </div>
    </>
  );
}

function DigestView({ d, name }: { d: NonNullable<Run["digest"]>; name: (c: string) => string }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0">
        <p className="max-w-[68ch] font-serif text-xl leading-[1.75] [overflow-wrap:anywhere] sm:text-2xl">{d.overall}</p>
        <div className="mt-10 space-y-8">
          {d.categories.map((c) => (
            <section key={c.category}>
              <h3 className="flex flex-wrap items-center gap-2 text-lg font-semibold tracking-tight">
                <span className="size-2.5 rounded-full" style={{ background: categoryTone(c.category) }} />
                {name(c.category)} <span className="text-xs font-normal text-ink-soft">{t("run.nPosts", { n: c.count })}</span>
              </h3>
              <p className="mt-2 max-w-[68ch] leading-relaxed text-ink-soft [overflow-wrap:anywhere]">{c.summary}</p>
              {c.highlights.length > 0 && (
                <ul className="mt-3 max-w-[68ch] list-disc space-y-2 pl-5 text-sm [overflow-wrap:anywhere]">
                  {c.highlights.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              )}
            </section>
          ))}
        </div>
      </div>
      {d.action_items.length > 0 && (
        <aside className="paper-card h-fit rounded-2xl p-5 lg:sticky lg:top-6">
          <h3 className="font-semibold">{t("run.nextSteps")}</h3>
          <ul className="mt-3 space-y-2.5">
            {d.action_items.map((a, i) => (
              <li key={i}>
                <label className="flex min-h-10 gap-3 py-1 text-sm [overflow-wrap:anywhere]">
                  <input type="checkbox" className="peer sr-only" />
                  <span aria-hidden="true" className="mt-0.5 grid size-4.5 shrink-0 place-items-center rounded-[4px] border border-line bg-surface text-transparent transition-colors duration-[var(--duration-fast)] peer-checked:border-primary peer-checked:bg-primary peer-checked:text-primary-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent peer-focus-visible:outline-offset-2">
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
  const [q, setQ] = useState("");
  const [applied, toggleApplied] = useApplied(runId);
  const { t, locale, lang } = useI18n();
  const good = jobs.filter((p) => p.job!.match_score >= 70).length;
  const remote = jobs.filter(isRemote).length;

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let list = jobs.filter((p) =>
      (filter === "all" || (filter === "good" ? p.job!.match_score >= 70 : isRemote(p))) &&
      (!needle || `${p.job!.title} ${p.job!.company} ${p.job!.location} ${p.summary}`.toLowerCase().includes(needle)));
    if (sort === "salary") list = [...list].sort((a, b) => Number(!!b.job!.salary) - Number(!!a.job!.salary) || b.job!.match_score - a.job!.match_score);
    if (sort === "source") list = [...list].sort((a, b) => a.source.localeCompare(b.source, locale) || b.job!.match_score - a.job!.match_score);
    return list;
  }, [jobs, filter, sort, q, locale]);

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

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {chips.map(([k, l, n]) => (
          <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}
            className="interactive-tap min-h-11 rounded-full border border-line px-3.5 py-2 text-sm hover:border-ink aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-ink">
            {l} <span className="font-mono text-xs opacity-70">{formatNumber(n, lang)}</span>
          </button>
        ))}
        <input className="field ml-auto min-h-11 w-full rounded-full sm:w-56" placeholder={t("job.search")}
          value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("job.searchAria")} />
        <select className="field min-h-11 w-full rounded-full sm:w-auto" value={sort} onChange={(e) => setSort(e.target.value as JobSort)} aria-label={t("job.sort")}>
          <option value="score">{t("job.sortScore")}</option>
          <option value="salary">{t("job.sortSalary")}</option>
          <option value="source">{t("job.sortSource")}</option>
        </select>
      </div>

      {shown.length === 0 ? (
        <EmptyState className="mt-6" icon={<Briefcase className="size-6" />} title={t("job.none")}
          action={{ label: t("act.seeAll"), onClick: () => { setFilter("all"); setQ(""); } }} />
      ) : (
        <ul className="mt-5 space-y-3">
          {shown.map((p) => <JobCard key={p.id} p={p} applied={applied.has(p.id)} onApplied={() => toggleApplied(p.id)} />)}
        </ul>
      )}
    </div>
  );
}

function JobCard({ p, applied, onApplied }: { p: Post; applied: boolean; onApplied: () => void }) {
  const j = p.job!;
  const tier = tierOf(j.match_score);
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const tags = [
    j.location && { label: j.location },
    j.work_mode && { label: j.work_mode },
    j.salary && { label: j.salary },
  ].filter(Boolean) as { label: string; mono?: boolean }[];
  const copy = async () => {
    try { await navigator.clipboard.writeText(j.contact); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { alert(t("act.copyFailed")); }
  };

  return (
    <li className={`stagger-item paper-card p-4 [overflow-wrap:anywhere] sm:p-5 ${applied ? "border-ok/40" : ""}`}>
      <div className="flex gap-3 sm:gap-4">
        <ScoreRing v={j.match_score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="min-w-0 text-lg leading-snug font-semibold text-balance [overflow-wrap:anywhere]">{j.title || p.summary}</h3>
            <span className="text-xs font-medium" style={{ color: tier.color }}>{t(tier.key)}</span>
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
          {j.match_reason && <p className="mt-3 max-w-[70ch] text-sm leading-relaxed text-ink-soft [overflow-wrap:anywhere]">{j.match_reason}</p>}
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            {p.url && (
              <a href={p.url} target="_blank" rel="noopener noreferrer"
                className="interactive-tap inline-flex min-h-11 max-w-full items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-ink hover:opacity-90">
                {t("job.open")} <ExternalLink className="size-3.5" />
              </a>
            )}
            {j.contact && (
              <button onClick={copy} title={j.contact}
                className="interactive-tap flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:border-ink">
                {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />}
                <span className="truncate text-xs">{copied ? t("act.copied") : j.contact}</span>
              </button>
            )}
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

function PostList({ posts, filter, setFilter, name }: {
  posts: Post[]; filter: string | null; setFilter: (c: string | null) => void; name: (c: string) => string;
}) {
  const shown = filter ? posts.filter((p) => p.category === filter) : posts;
  const { t } = useI18n();
  const [categoryBefore, categoryAfter] = t("posts.viewingCategory", { n: shown.length, category: "{category}" }).split("{category}");
  return (
    <>
      {filter && (
        <p className="mb-4 text-sm">
          {categoryBefore}<b>{name(filter)}</b>{categoryAfter}{" "}
          <button onClick={() => setFilter(null)} className="text-link hover:underline">{t("act.seeAll")}</button>
        </p>
      )}
      {shown.length === 0 && <EmptyState icon={<FileSearch className="size-6" />} title={t("hist.empty")} />}
      <ul className="space-y-3">
        {shown.map((p) => (
          <li key={p.id} className="stagger-item paper-card min-w-0 px-4 py-4 [overflow-wrap:anywhere] sm:px-5">
            <details className="group/post">
              <summary className="cursor-pointer list-none rounded-field">
                <span className="flex items-start justify-between gap-3"><span className="min-w-0 text-base leading-relaxed font-medium">{p.summary}</span><ChevronDown aria-hidden="true" className="mt-1 size-4 shrink-0 text-ink-soft transition-transform duration-[var(--duration-fast)] group-open/post:rotate-180 motion-reduce:transition-none" /></span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-ink-soft">
                  <span className="flex items-center gap-1.5 text-ink">
                    <span className="size-2 rounded-full" style={{ background: categoryTone(p.category) }} />
                    {name(p.category)}
                  </span>
                  <span>{p.author || t("posts.unknownAuthor")}</span>
                  <span>{p.source}</span>
                  {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-link hover:underline"
                    onClick={(e) => e.stopPropagation()}>{t("posts.openOriginal")}</a>}
                </span>
              </summary>
              <p className="mt-4 max-w-[72ch] border-t border-line pt-4 text-sm leading-relaxed whitespace-pre-wrap text-ink-soft [overflow-wrap:anywhere]">{p.text}</p>
            </details>
          </li>
        ))}
      </ul>
    </>
  );
}
