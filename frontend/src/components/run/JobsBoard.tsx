import { Briefcase, Check, CheckCircle2, Copy, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { formatNumber, useI18n, type Key } from "../../i18n";
import { isRemoteText, jobPresentation, matchesJobType } from "../../lib/logic";
import type { Post } from "../../api/types";
import { EmptyState, Select } from "../ui";
import { PostSources } from "./PostList";

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

export function JobsBoard({ jobs, runId }: { jobs: Post[]; runId: number }) {
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
        <Select shape="pill" value={matchType} onChange={(e) => setMatchType(e.target.value)} aria-label={t("profile.matchFilter")}>
          {["all", "primary", "adjacent", "stretch", "none"].map((type) => <option key={type} value={type}>{t(`profile.match.${type}` as Key)}</option>)}
        </Select>
        <Select shape="pill" value={sort} onChange={(e) => setSort(e.target.value as JobSort)} aria-label={t("job.sort")}>
          <option value="score">{t("job.sortScore")}</option>
          <option value="salary">{t("job.sortSalary")}</option>
          <option value="source">{t("job.sortSource")}</option>
        </Select>
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
          <PostSources p={p} />
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
