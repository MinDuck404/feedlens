import { Check, CheckCircle2, Copy, ExternalLink, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { colorOf, PLATFORM_LABEL } from "../categories";
import { useI18n, type Key } from "../i18n";
import { routeHref, type RunTab } from "../router";
import type { Meta, Post, Run } from "../types";

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
  const [filter, setFilter] = useState<string | null>(null);
  const setTab = onTab;
  const { t, locale } = useI18n();

  useEffect(() => {
    let alive = true;
    let timer: number;
    const load = async () => {
      try {
        const r = await api.run(runId);
        if (!alive) return;
        setRun(r);
        if (!["done", "error"].includes(r.status)) timer = window.setTimeout(load, 1500);
      } catch {
        if (alive) setMissing(true);
      }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [runId]);

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
  if (!run) return null;
  const q = run.request;
  const title = q.source_type === "feed" ? t("run.feedOf", { platform: PLATFORM_LABEL[q.platform] })
    : q.sources.length > 1 ? t("run.andMore", { first: q.sources[0], n: q.sources.length - 1 }) : q.sources[0];
  const when = new Date(run.created_at.endsWith("Z") || run.created_at.includes("+") ? run.created_at : run.created_at + "Z");

  const remove = async () => {
    if (!confirm(t("run.confirmDelete"))) return;
    await api.deleteRun(run.id);
    onDeleted();
  };

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 md:px-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs text-ink-soft">
            {when.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}
            {run.ai_label && t("run.readBy", { ai: run.ai_label })}
          </p>
          <h1 className="mt-1 truncate text-2xl font-bold tracking-tight md:text-3xl">{title}</h1>
        </div>
        <div className="flex items-center gap-1">
          {run.status === "done" && (["md", "csv", "json"] as const).map((f) => (
            <button key={f} onClick={() => api.download(run.id, f).catch((e) => alert(e.message))}
              className="rounded-full border border-line px-3 py-1 font-mono text-xs text-ink-soft hover:border-ink hover:text-ink">
              .{f}
            </button>
          ))}
          <button onClick={remove} aria-label={t("run.delete")} title={t("run.delete")}
            className="ml-1 grid size-8 place-items-center rounded-full border border-line text-ink-soft hover:border-danger hover:text-danger">
            <Trash2 className="size-4" />
          </button>
        </div>
      </header>

      {run.status === "error" ? (
        <div className="paper-card mt-8 rounded-2xl border-danger/40 p-5">
          <p className="font-semibold text-danger">{t("run.stopped")}</p>
          <p className="mt-2 whitespace-pre-wrap text-sm">{run.error}</p>
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
      <p className="font-semibold">{phase}</p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-sunken">
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-sm text-ink-soft">{p?.message || (run.status === "pending" ? t("run.pendingHint") : t("run.openingBrowser"))}</p>
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
  const { t, cat } = useI18n();
  void meta;  // tên loại bài lấy theo ngôn ngữ giao diện thay vì meta.categories (tiếng Việt)
  const name = cat;
  const tab: Tab = requested === "jobs" && !jobs.length ? "digest" : requested;  // URL cũ trỏ vào tab không còn

  const pick = (c: string) => { setFilter(filter === c ? null : c); setTab("posts"); };

  return (
    <>
      {/* Thanh phân loại: điểm nhấn của trang, đồng thời là bộ lọc */}
      <section className="mt-8" aria-label={t("run.composition")}>
        <p className="mb-2 text-sm text-ink-soft"><span className="font-mono text-ink">{posts.length}</span> {t("run.postsByCategory")}</p>
        {/* Một dải liền: chỉ bo hai đầu, các loại nối nhau bằng vạch mảnh màu giấy */}
        <div className="flex h-9 w-full overflow-hidden rounded-full">
          {counts.map(([c, n]) => (
            <button key={c} onClick={() => pick(c)} title={t("run.catCount", { name: name(c), n })}
              aria-label={t("run.catCount", { name: name(c), n })}
              className="h-full transition-opacity not-first:border-l-2 not-first:border-[var(--paper)] hover:opacity-80 focus-visible:z-10 focus-visible:outline-offset-[-2px]"
              style={{ flexGrow: n, flexBasis: 0, minWidth: 6, background: colorOf(c), opacity: filter && filter !== c ? 0.3 : 1 }} />
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
          {counts.map(([c, n]) => (
            <li key={c}>
              <button onClick={() => pick(c)} className="flex items-center gap-2 text-sm hover:underline">
                <span className="size-2.5 rounded-full" style={{ background: colorOf(c) }} />
                {name(c)} <span className="font-mono text-xs text-ink-soft">{n}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <nav className="mt-8 flex gap-6 border-b border-line" role="tablist">
        {([["digest", t("tab.digest")], ...(jobs.length ? [["jobs", t("tab.jobs", { n: jobs.length })]] : []), ["posts", t("tab.posts")]] as [Tab, string][])
          .map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className="-mb-px border-b-2 border-transparent pb-2.5 text-sm text-ink-soft aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink">
              {l}
            </button>
          ))}
      </nav>

      <div className="py-6">
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
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_260px]">
      <div className="min-w-0">
        <p className="max-w-[68ch] font-serif text-xl leading-[1.75]">{d.overall}</p>
        <div className="mt-10 space-y-8">
          {d.categories.map((c) => (
            <section key={c.category}>
              <h3 className="flex items-center gap-2 font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: colorOf(c.category) }} />
                {name(c.category)} <span className="font-mono text-xs font-normal text-ink-soft">{t("run.nPosts", { n: c.count })}</span>
              </h3>
              <p className="mt-1 max-w-[68ch] text-ink-soft">{c.summary}</p>
              {c.highlights.length > 0 && (
                <ul className="mt-2 max-w-[68ch] list-disc space-y-1 pl-5 text-sm">
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
                <label className="flex gap-2.5 text-sm">
                  <input type="checkbox" className="mt-1 accent-[var(--accent)]" />
                  <span>{a}</span>
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
  v >= 70 ? { key: "tier.good", color: "var(--ok)" } : v >= 40 ? { key: "tier.maybe", color: "#b7851a" } : { key: "tier.low", color: "var(--ink-soft)" };

/** Vòng điểm phù hợp 0–100 */
function ScoreRing({ v }: { v: number }) {
  const tier = tierOf(v);
  const { t } = useI18n();
  const r = 22, c = 2 * Math.PI * r;
  return (
    <div className="relative grid size-14 shrink-0 place-items-center" aria-label={t("job.scoreAria", { v, tier: t(tier.key) })}>
      <svg viewBox="0 0 56 56" className="absolute inset-0 -rotate-90">
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
const isRemote = (p: Post) => /remote|từ xa|wfh|work from home/i.test(`${p.job?.work_mode} ${p.job?.location} ${p.text}`);

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
  const { t } = useI18n();
  const good = jobs.filter((p) => p.job!.match_score >= 70).length;
  const remote = jobs.filter(isRemote).length;

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let list = jobs.filter((p) =>
      (filter === "all" || (filter === "good" ? p.job!.match_score >= 70 : isRemote(p))) &&
      (!needle || `${p.job!.title} ${p.job!.company} ${p.job!.location} ${p.summary}`.toLowerCase().includes(needle)));
    if (sort === "salary") list = [...list].sort((a, b) => Number(!!b.job!.salary) - Number(!!a.job!.salary) || b.job!.match_score - a.job!.match_score);
    if (sort === "source") list = [...list].sort((a, b) => a.source.localeCompare(b.source) || b.job!.match_score - a.job!.match_score);
    return list;
  }, [jobs, filter, sort, q]);

  const chips: [JobFilter, string, number][] = [["all", t("job.filterAll"), jobs.length], ["good", t("job.filterGood"), good], ["remote", t("job.filterRemote"), remote]];

  return (
    <div>
      <div className="grid grid-cols-3 gap-3">
        {([[t("job.statFound"), jobs.length], [t("job.statGood"), good], [t("job.statApplied"), applied.size]] as [string, number][]).map(([l, n]) => (
          <div key={l} className="paper-card rounded-2xl px-4 py-3">
            <div className="font-mono text-2xl font-medium">{n}</div>
            <div className="font-mono text-xs text-ink-soft">{l}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {chips.map(([k, l, n]) => (
          <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}
            className="rounded-full border border-line px-3.5 py-1.5 text-sm hover:border-ink aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-ink">
            {l} <span className="font-mono text-xs opacity-70">{n}</span>
          </button>
        ))}
        <input className="field ml-auto !w-full !rounded-full sm:!w-56" placeholder={t("job.search")}
          value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("job.searchAria")} />
        <select className="field !w-auto !rounded-full" value={sort} onChange={(e) => setSort(e.target.value as JobSort)} aria-label={t("job.sort")}>
          <option value="score">{t("job.sortScore")}</option>
          <option value="salary">{t("job.sortSalary")}</option>
          <option value="source">{t("job.sortSource")}</option>
        </select>
      </div>

      {shown.length === 0 ? (
        <p className="paper-card mt-5 rounded-2xl px-5 py-8 text-center text-sm text-ink-soft">
          {t("job.none")} <button onClick={() => { setFilter("all"); setQ(""); }} className="text-link hover:underline">{t("act.seeAll")}</button>
        </p>
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
    j.salary && { label: j.salary, mono: true },
  ].filter(Boolean) as { label: string; mono?: boolean }[];
  const copy = () => navigator.clipboard.writeText(j.contact).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });

  return (
    <li className={`paper-card rounded-2xl p-5 transition-opacity ${applied ? "opacity-60" : ""}`}>
      <div className="flex gap-4">
        <ScoreRing v={j.match_score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="text-[17px] leading-snug font-semibold">{j.title || p.summary}</h3>
            <span className="font-mono text-xs" style={{ color: tier.color }}>{t(tier.key)}</span>
          </div>
          <p className="mt-0.5 text-sm text-ink-soft">
            {j.company || t("job.unknownCompany")}<span className="mx-1.5">/</span>{p.source}
          </p>
          {tags.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {tags.map((tg) => (
                <span key={tg.label} className={`rounded-full bg-sunken px-2.5 py-0.5 text-xs ${tg.mono ? "font-mono" : ""}`}>{tg.label}</span>
              ))}
            </div>
          )}
          {j.match_reason && <p className="mt-2.5 max-w-[70ch] text-sm text-ink-soft">{j.match_reason}</p>}
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            {p.url && (
              <a href={p.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-ink hover:opacity-90">
                {t("job.open")} <ExternalLink className="size-3.5" />
              </a>
            )}
            {j.contact && (
              <button onClick={copy} title={j.contact}
                className="flex max-w-full items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-sm hover:border-ink">
                {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />}
                <span className="truncate font-mono text-xs">{copied ? t("act.copied") : j.contact}</span>
              </button>
            )}
            <button onClick={onApplied} aria-pressed={applied}
              className="ml-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm text-ink-soft hover:text-ink aria-pressed:text-ok">
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
  return (
    <>
      {filter && (
        <p className="mb-4 text-sm">
          {t("posts.viewing", { n: shown.length })} <b>{name(filter)}</b>.{" "}
          <button onClick={() => setFilter(null)} className="text-link hover:underline">{t("act.seeAll")}</button>
        </p>
      )}
      <ul className="space-y-2">
        {shown.map((p) => (
          <li key={p.id} className="paper-card rounded-xl px-4 py-3">
            <details>
              <summary className="cursor-pointer list-none">
                <span className="block font-medium">{p.summary}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-ink-soft">
                  <span className="flex items-center gap-1.5 text-ink">
                    <span className="size-2 rounded-full" style={{ background: colorOf(p.category) }} />
                    {name(p.category)}
                  </span>
                  <span>{p.author || t("posts.unknownAuthor")}</span>
                  <span>{p.source}</span>
                  {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-link hover:underline"
                    onClick={(e) => e.stopPropagation()}>{t("posts.openOriginal")}</a>}
                </span>
              </summary>
              <p className="mt-3 max-w-[72ch] whitespace-pre-wrap text-sm text-ink-soft">{p.text}</p>
            </details>
          </li>
        ))}
      </ul>
    </>
  );
}
