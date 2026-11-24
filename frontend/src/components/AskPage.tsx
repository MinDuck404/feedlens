import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, Search, X } from "lucide-react";
import { api } from "../api/client";
import { formatNumber, useI18n, type Key } from "../i18n";
import { questionHistory, textParts } from "../lib/search";
import { routeHref } from "../router";
import { topicColor } from "../lib/topics";
import type { AskResponse, SearchFilters, SearchPost, SearchResponse, Topic } from "../api/types";
import { Button, Dialog, EmptyState, SegmentedControl, Select, SkeletonCard, TextField } from "./ui";

interface Props { initialFilters?: SearchFilters; account: string; onNewRun: () => void; onSettings: () => void }
const categoryKeys = ["job", "news", "tech", "question", "marketplace", "event", "promotion", "personal", "entertainment", "other"];
const activeEntries = (filters: SearchFilters) => Object.entries(filters).filter(([key, value]) => value != null && value !== "" && !(key === "job_only" && value === false) && (!Array.isArray(value) || value.length));

export default function AskPage({ initialFilters = {}, account, onNewRun, onSettings }: Props) {
  const { t, cat, lang } = useI18n();
  const tabsId = useId();
  const input = useRef<HTMLInputElement>(null);
  const sequence = useRef(0), aiSequence = useRef(0), flashTimer = useRef<number>();
  const [mode, setMode] = useState("quick");
  const [filters, setFilters] = useState<SearchFilters>(initialFilters);
  const [question, setQuestion] = useState("");
  const [topics, setTopics] = useState<Topic[]>([]);
  const [canAsk, setCanAsk] = useState(false), [providersLoaded, setProvidersLoaded] = useState(false);
  const [result, setResult] = useState<SearchResponse | null>(null), [answer, setAnswer] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(true), [asking, setAsking] = useState(false), [more, setMore] = useState(false);
  const [error, setError] = useState(""), [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0), [editing, setEditing] = useState(false);
  const [manual, setManual] = useState(activeEntries(initialFilters).length > 0), [changed, setChanged] = useState(false);
  const [flash, setFlash] = useState<number | null>(null), [history, setHistory] = useState<string[]>([]);
  const historyKey = `feedlens.ask.history.${encodeURIComponent(account)}`;
  useEffect(() => { if (!account) { setHistory([]); return; } try { setHistory(questionHistory(JSON.parse(localStorage.getItem(historyKey) ?? "[]"))); } catch { setHistory([]); } }, [historyKey, account]);
  useEffect(() => {
    let alive = true;
    const loadTopics = () => api.topics().then((value) => { if (alive) setTopics(value.topics); }).catch((e) => { if (alive) setLoadError(e.message); });
    const loadProviders = () => api.providers().then((value) => { if (alive) { setCanAsk(value.some((provider) => provider.configured && provider.key !== "offline")); setProvidersLoaded(true); } }).catch((e) => { if (alive) setLoadError(e.message); });
    loadTopics(); loadProviders();
    window.addEventListener("feedlens:aiChanged", loadProviders); window.addEventListener("feedlens:topicsChanged", loadTopics);
    return () => { alive = false; aiSequence.current++; clearTimeout(flashTimer.current); window.removeEventListener("feedlens:aiChanged", loadProviders); window.removeEventListener("feedlens:topicsChanged", loadTopics); };
  }, []);
  useEffect(() => {
    const request = ++sequence.current; setLoading(true); setError(""); setMore(false);
    const timer = window.setTimeout(() => { api.search(filters).then((value) => { if (request === sequence.current) setResult(value); }).catch((e) => { if (request === sequence.current) setError(e.message); }).finally(() => { if (request === sequence.current) setLoading(false); }); }, 250);
    return () => { window.clearTimeout(timer); sequence.current++; };
  }, [filters, retry]);
  useEffect(() => { input.current?.focus(); }, [mode]);
  const update = (next: SearchFilters) => { aiSequence.current++; setFilters(next); setAnswer(null); setManual(true); setChanged(true); setAsking(false); };
  const remove = (key: string) => { const next = { ...filters }; delete next[key as keyof SearchFilters]; update(next); };
  const ask = async (text = question, useFilters = manual) => {
    if (!canAsk || !text.trim() || asking) return;
    const request = ++aiSequence.current; setQuestion(text); setAsking(true); setError(""); setAnswer(null);
    const nextHistory = questionHistory(history, text); setHistory(nextHistory); try { if (account) localStorage.setItem(historyKey, JSON.stringify(nextHistory)); } catch { /* Questions remain available in memory. */ }
    try { const value = await api.ask(text.trim(), lang, useFilters ? filters : undefined); if (request !== aiSequence.current) return;
      setAnswer(value); setFilters(value.applied_filters); setManual(true); setChanged(false); setResult({ posts: value.posts, total: value.total, limit: 40, offset: 0 });
    } catch (e) { if (request === aiSequence.current) setError((e as Error).message); }
    finally { if (request === aiSequence.current) setAsking(false); }
  };
  const goTo = (id: number) => {
    const target = document.getElementById(`ask-post-${id}`); if (!target) return;
    target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }); target.focus({ preventScroll: true });
    clearTimeout(flashTimer.current); setFlash(id); flashTimer.current = window.setTimeout(() => setFlash(null), 1200);
  };
  const entries = activeEntries(filters);
  const label = (key: string): string => t(({ q: "ask.query", platform: "ask.platform", categories: "ask.category", topic_ids: "topics.title", date_from: "ask.from", date_to: "ask.to", job_only: "ask.jobs", work_modes: "ask.modes", min_salary_vnd: "ask.salary", locations: "ask.locations", min_score: "ask.score", match_type: "ask.match", has_link: "ask.link", has_github: "ask.github" } as Record<string, Key>)[key]);
  const display = (key: string, value: unknown) => {
    if (key === "categories") return (value as string[]).map(cat).join(", ");
    if (key === "topic_ids") return (value as number[]).map((id) => topics.find((topic) => topic.id === id)?.name ?? `#${id}`).join(", ");
    if (key === "work_modes") return (value as string[]).map((mode) => t(`profile.mode.${mode}` as Key)).join(", ");
    if (key === "match_type") return t(`profile.match.${value}` as Key);
    if (typeof value === "boolean") return t(value ? "ask.yes" : "ask.no");
    return Array.isArray(value) ? value.join(", ") : typeof value === "number" ? formatNumber(value, lang) : String(value);
  };
  return <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 md:py-12">
    <header><h1 className="font-headline text-3xl sm:text-4xl">{t("ask.title")}</h1><p className="mt-3 max-w-prose leading-relaxed text-ink-soft">{t("ask.subtitle")}</p><div className="rule-double my-6" /></header>
    <SegmentedControl id={tabsId} mode="tabs" label={t("ask.title")} value={mode} onChange={(value) => { aiSequence.current++; setAsking(false); setManual(false); setMode(value); }} options={[{ value: "quick", label: t("ask.quick") }, { value: "ai", label: t("ask.ai") }]} />
    <section role="tabpanel" id={`${tabsId}-panel-${mode}`} aria-labelledby={`${tabsId}-tab-${mode}`} className="mt-5">
      {loadError && <p role="alert" className="mb-3 text-sm text-danger">{loadError} <button className="min-h-11 underline" onClick={() => { setLoadError(""); window.dispatchEvent(new Event("feedlens:aiChanged")); window.dispatchEvent(new Event("feedlens:topicsChanged")); }}>{t("act.retry")}</button></p>}
      {mode === "ai" && providersLoaded && !canAsk && <p className="mb-4 rounded-xl border border-line bg-sunken p-4 text-sm leading-relaxed">{t("ask.noKey")} <button onClick={onSettings} className="min-h-11 text-link underline">{t("act.settings")}</button></p>}
      <form onSubmit={(event) => { event.preventDefault(); if (mode === "ai") void ask(); else setRetry((value) => value + 1); }}>
        <label className="sr-only" htmlFor={`${tabsId}-input`}>{t(mode === "quick" ? "ask.query" : "ask.question")}</label>
        <div className="flex min-w-0 items-center gap-2 rounded-xl border border-[var(--field-line)] bg-[var(--field-bg)] px-3 focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-tint)]">
          <Search aria-hidden="true" className="size-4 shrink-0 text-ink-soft" /><input id={`${tabsId}-input`} data-ask-input ref={input} type="search" maxLength={1000} disabled={asking} className="min-h-12 min-w-0 flex-1 border-0 bg-transparent py-2 text-sm outline-none! ring-0!" value={mode === "quick" ? filters.q ?? "" : question} onChange={(e) => mode === "quick" ? update({ ...filters, q: e.target.value }) : (setQuestion(e.target.value), setManual(false), setAnswer(null))} onKeyDown={(e) => { if (e.key === "Escape") { if (mode === "quick") update({ ...filters, q: "" }); else setQuestion(""); } if (e.key === "Enter" && e.nativeEvent.isComposing) e.preventDefault(); }} />
          <Button type="submit" size="sm" busy={asking} disabled={mode === "ai" && (!canAsk || !question.trim())} className="min-h-11 shrink-0">{t(mode === "quick" ? "ask.search" : "ask.ai")}</Button>
        </div>
      </form>
      {mode === "ai" && canAsk && !question && <div className="mt-4"><p className="text-xs text-ink-soft">{t("ask.examples")}</p><div className="mt-2 flex flex-col items-start gap-1">{(["ask.exampleJobs", "ask.exampleGithub"] as Key[]).map((key) => <button key={key} className="min-h-11 text-left text-sm text-link hover:underline" onClick={() => void ask(t(key), false)}>{t(key)}</button>)}</div></div>}
      {mode === "ai" && history.length > 0 && <details className="mt-4 text-sm"><summary className="min-h-11 cursor-pointer py-3 text-ink-soft">{t("ask.history")}</summary><ul className="space-y-1">{history.map((item) => <li key={item}><button className="min-h-11 text-left text-link [overflow-wrap:anywhere] hover:underline" onClick={() => { setQuestion(item); setManual(false); setAnswer(null); }}>{item}</button></li>)}</ul><button className="min-h-11 text-xs text-ink-soft underline" onClick={() => { setHistory([]); try { localStorage.removeItem(historyKey); } catch { /* In-memory history is cleared. */ } }}>{t("ask.clearHistory")}</button></details>}
    </section>
    <section aria-label={t("ask.filters")} className="my-5 border-y border-line py-2"><div className="flex flex-wrap items-center justify-between gap-1"><span className="text-xs text-ink-soft">{t("ask.filters")}</span><div className="flex gap-1"><Button size="sm" variant="ghost" className="min-h-11" onClick={() => setEditing(true)}>{t("ask.addFilter")}</Button>{entries.length > 0 && <Button size="sm" variant="ghost" className="min-h-11" onClick={() => update({})}>{t("ask.clear")}</Button>}</div></div><div className="flex max-w-full items-center gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:flex-wrap sm:overflow-visible sm:pr-0 sm:[mask-image:none]">
      {entries.map(([key, value]) => <div key={key} className="flex max-w-[85vw] shrink-0 items-center rounded-full border border-line bg-sunken text-xs sm:max-w-full"><button type="button" onClick={() => setEditing(true)} title={`${label(key)}: ${display(key, value)}`} className="min-h-11 min-w-0 truncate rounded-l-full px-3 text-left">{label(key)}: {display(key, value)}</button><button type="button" aria-label={t("ask.remove", { name: label(key) })} className="grid min-h-11 w-11 shrink-0 place-items-center rounded-r-full hover:bg-sunken-hover" onClick={() => remove(key)}><X className="size-3.5" /></button></div>)}
    </div></section>
    {changed && mode === "ai" && <p className="mb-4 text-sm text-ink-soft">{t("ask.updatedFilters")}</p>}
    {error && <div role="alert" className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger"><span>{error}</span><Button variant="outline" size="sm" onClick={() => mode === "ai" ? void ask() : setRetry((value) => value + 1)}>{t("act.retry")}</Button></div>}
    {answer && <section aria-label={t("ask.answer")} className="mb-7 border-b border-line pb-6"><div className="flex flex-wrap items-baseline justify-between gap-2"><h2 id="ask-answer" tabIndex={-1} className="font-headline text-2xl">{t("ask.answer")}</h2><span className="text-xs text-ink-soft">{answer.ai_label}</span></div><p className="prose-reading mt-4 whitespace-pre-wrap [overflow-wrap:anywhere]">{textParts(answer.answer, "citation", answer.citations.filter((id) => answer.posts.some((post) => post.id === id))).map((part, i) => part.id ? <Citation key={i} post={answer.posts.find((post) => post.id === part.id)!} onGo={() => goTo(part.id!)} /> : <span key={i}>{part.text}</span>)}</p></section>}
    {asking ? <div role="status" aria-label={t("act.loading")}><SkeletonCard /></div> : loading && !answer ? <div role="status" aria-label={t("act.loading")}><SkeletonCard /></div> : !error && result && <>
      <h2 className="mb-5 font-headline text-2xl">{t("ask.results", { n: result.total })}</h2>
      {!result.total ? <><EmptyState icon={<Search className="size-6" />} title={t(entries.length ? "ask.noMatch" : "ask.empty")} description={t(entries.length ? "ask.loosen" : "ask.emptyHint")} action={{ label: t(entries.length ? "ask.clear" : "act.newRun"), onClick: entries.length ? () => update({}) : onNewRun }} />{entries.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{filters.min_salary_vnd != null && <Button variant="ghost" onClick={() => remove("min_salary_vnd")}>{t("ask.dropSalary")}</Button>}{!!filters.locations?.length && <Button variant="ghost" onClick={() => remove("locations")}>{t("ask.dropLocation")}</Button>}{(filters.date_from || filters.date_to) && <Button variant="ghost" onClick={() => { const end = new Date(), start = new Date(); start.setUTCDate(end.getUTCDate() - 29); update({ ...filters, date_from: start.toISOString().slice(0, 10), date_to: end.toISOString().slice(0, 10) }); }}>{t("ask.expandDates")}</Button>}</div>}</> : <ul className="divide-y divide-line-strong">{result.posts.map((post) => <SearchCard key={post.id} post={post} flash={flash === post.id} hasAnswer={!!answer} />)}</ul>}
      {result.posts.length < result.total && <Button className="mt-5" variant="outline" busy={more} onClick={async () => { const request = sequence.current; setMore(true); try { const value = await api.search(filters, result.posts.length); if (request === sequence.current) setResult({ ...value, posts: [...result.posts, ...value.posts] }); } catch (e) { if (request === sequence.current) setError((e as Error).message); } finally { if (request === sequence.current) setMore(false); } }}>{t("ask.more")}</Button>}
    </>}
    {editing && <FilterEditor initial={filters} topics={topics} onClose={() => setEditing(false)} onApply={(next) => { update(next); setEditing(false); }} />}
  </div>;
}

function Citation({ post, onGo }: { post: SearchPost; onGo: () => void }) {
  const { t } = useI18n(); const id = useId(); const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const preview = (element: HTMLElement) => { const rect = element.getBoundingClientRect(); setPosition({ left: Math.max(12, Math.min(innerWidth - 300, rect.left)), top: Math.max(12, rect.top - 130) }); };
  return <><a href={`#ask-post-${post.id}`} aria-label={t("ask.citation", { id: post.id, title: post.summary })} aria-describedby={position ? id : undefined} onMouseEnter={(e) => preview(e.currentTarget)} onMouseLeave={() => setPosition(null)} onFocus={(e) => preview(e.currentTarget)} onBlur={() => setPosition(null)} onClick={(e) => { e.preventDefault(); setPosition(null); onGo(); }} className="inline-flex min-h-8 items-center rounded border border-accent/30 bg-accent/10 px-1.5 font-mono text-xs text-link underline-offset-2 hover:underline">[#{post.id}]</a>
    {position && createPortal(<span id={id} role="tooltip" className="pointer-events-none fixed z-[70] block w-72 max-w-[calc(100vw-24px)] rounded-xl border border-line bg-surface p-3 font-sans text-sm text-ink shadow-lg [overflow-wrap:anywhere]" style={position}><span className="block text-xs text-ink-soft">{post.source} · {post.author}</span><span className="mt-1 block line-clamp-2">{post.summary || post.text.slice(0, 160)}</span><span className="mt-1 block text-xs text-ink-soft">{post.date}{post.job ? ` · ${post.job.match_score}/100` : ""}</span></span>, document.body)}
  </>;
}

function SearchCard({ post, flash, hasAnswer }: { post: SearchPost; flash: boolean; hasAnswer: boolean }) {
  const { t, cat, locale } = useI18n();
  return <li id={`ask-post-${post.id}`} tabIndex={-1} className={`min-w-0 scroll-mt-20 py-6 outline-none transition-colors duration-200 motion-reduce:transition-none [overflow-wrap:anywhere] ${flash ? "rounded-lg bg-accent/5 ring-2 ring-accent" : ""}`}>
    <div className="mb-2 flex flex-wrap items-baseline gap-3 text-xs text-ink-soft">{hasAnswer ? <a href="#ask-answer" onClick={(e) => { e.preventDefault(); document.getElementById("ask-answer")?.focus(); }} title={t("ask.backAnswer")} className="min-h-8 font-mono text-link">[#{post.id}]</a> : <span className="font-mono">[#{post.id}]</span>}<span>{cat(post.category)}</span><span>{post.platform} · {post.source}</span><span>{post.author || t("posts.unknownAuthor")}</span><time dateTime={post.date}>{new Date(`${post.date}T00:00:00Z`).toLocaleDateString(locale, { timeZone: "UTC" })}</time></div>
    <h3 className="max-w-[40ch] font-headline text-2xl leading-snug font-semibold">{post.job?.title || post.summary || post.text.slice(0, 120)}</h3>
    {post.job && <p className="mt-2 text-sm text-ink-soft">{[post.job.company, post.job.salary, post.job.location].filter(Boolean).join(" · ")}</p>}
    <p className="prose-reading mt-3 [overflow-wrap:anywhere]">{textParts(post.snippet, "snippet").map((part, i) => part.highlight ? <mark key={i} className="rounded bg-accent/15 px-0.5 text-ink">{part.text}</mark> : <span key={i}>{part.text}</span>)}</p>
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">{post.url && /^https?:\/\//i.test(post.url) && <a href={post.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 text-link underline underline-offset-4">{t("posts.openOriginal")}<ExternalLink className="size-3" /></a>}<a href={routeHref({ page: "run", id: post.run_id, tab: "posts" })} className="inline-flex min-h-11 items-center text-link underline underline-offset-4">{t("ask.openRun")}</a></div>
  </li>;
}

function FilterEditor({ initial, topics, onApply, onClose }: { initial: SearchFilters; topics: Topic[]; onApply: (filters: SearchFilters) => void; onClose: () => void }) {
  const { t, cat } = useI18n(); const [draft, setDraft] = useState<SearchFilters>(initial);
  const [locationText, setLocationText] = useState(initial.locations?.join(", ") ?? "");
  const set = <K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const toggle = (key: "categories" | "work_modes", value: string) => set(key, draft[key]?.includes(value) ? draft[key]!.filter((item) => item !== value) : [...draft[key] ?? [], value]);
  return <Dialog open title={t("ask.editFilters")} side="center" maxWidth="max-w-xl" className="max-h-[calc(100dvh-2rem)] [&_h2]:font-headline [&>header>button]:size-11" onClose={onClose} closeAriaLabel={t("act.close")} onSubmit={(e) => { e.preventDefault(); onApply({ ...draft, locations: locationText.split(",").map((value) => value.trim()).filter(Boolean).slice(0, 20) }); }} footer={<div className="flex justify-end gap-2"><Button className="min-h-11" variant="ghost" onClick={onClose}>{t("act.cancel")}</Button><Button className="min-h-11" type="submit">{t("ask.apply")}</Button></div>}>
    <label className="block text-sm">{t("ask.query")}<TextField autoFocus className="mt-2" onKeyDown={(e) => { if (e.key === "Enter" && e.nativeEvent.isComposing) e.preventDefault(); }} maxLength={1000} value={draft.q ?? ""} onChange={(e) => set("q", e.target.value)} /></label>
    <label className="block text-sm">{t("ask.platform")}<Select className="mt-2" value={draft.platform ?? ""} onChange={(e) => set("platform", e.target.value as SearchFilters["platform"] || null)}><option value="">{t("ask.any")}</option>{["Facebook", "LinkedIn", "X", "Reddit"].map((platform) => <option key={platform} value={platform.toLowerCase()}>{platform}</option>)}</Select></label>
    <div className="grid grid-cols-2 gap-3"><label className="text-sm">{t("ask.from")}<TextField type="date" className="mt-2" max={draft.date_to ?? undefined} value={draft.date_from ?? ""} onChange={(e) => set("date_from", e.target.value || null)} /></label><label className="text-sm">{t("ask.to")}<TextField type="date" className="mt-2" min={draft.date_from ?? undefined} value={draft.date_to ?? ""} onChange={(e) => set("date_to", e.target.value || null)} /></label></div>
    <fieldset><legend className="text-sm font-medium">{t("ask.category")}</legend><div className="mt-2 grid grid-cols-2 gap-x-3">{categoryKeys.map((value) => <label key={value} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" className="size-4 shrink-0 accent-accent" checked={draft.categories?.includes(value) ?? false} onChange={() => toggle("categories", value)} />{cat(value)}</label>)}</div></fieldset>
    {!!topics.length && <fieldset><legend className="text-sm font-medium">{t("topics.title")}</legend>{topics.map((topic) => <label key={topic.id} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-accent" checked={draft.topic_ids?.includes(topic.id) ?? false} onChange={() => set("topic_ids", draft.topic_ids?.includes(topic.id) ? draft.topic_ids.filter((id) => id !== topic.id) : [...draft.topic_ids ?? [], topic.id])} /><span className="size-2 rounded-full" style={{ background: topicColor(topic.color) }} />{topic.name}</label>)}</fieldset>}
    <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-accent" checked={draft.job_only ?? false} onChange={(e) => set("job_only", e.target.checked)} />{t("ask.jobs")}</label>
    <fieldset><legend className="text-sm font-medium">{t("ask.modes")}</legend><div className="flex flex-wrap gap-x-4">{["remote", "hybrid", "onsite"].map((mode) => <label key={mode} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-accent" checked={draft.work_modes?.includes(mode) ?? false} onChange={() => toggle("work_modes", mode)} />{t(`profile.mode.${mode}` as Key)}</label>)}</div></fieldset>
    <label className="block text-sm">{t("ask.salary")}<TextField className="mt-2" type="number" min="0" max="1000000000000" value={draft.min_salary_vnd ?? ""} onChange={(e) => set("min_salary_vnd", e.target.value ? Number(e.target.value) : null)} /><span className="mt-1 block text-xs leading-relaxed text-ink-soft">{t("ask.salaryHint")}</span></label>
    <label className="block text-sm">{t("ask.locations")}<TextField className="mt-2" onKeyDown={(e) => { if (e.key === "Enter" && e.nativeEvent.isComposing) e.preventDefault(); }} value={locationText} onChange={(e) => setLocationText(e.target.value)} /></label>
    <div className="grid grid-cols-2 gap-3"><label className="text-sm">{t("ask.score")}<TextField type="number" min="0" max="100" className="mt-2" value={draft.min_score ?? ""} onChange={(e) => set("min_score", e.target.value ? Number(e.target.value) : null)} /></label><label className="text-sm">{t("ask.match")}<Select className="mt-2" value={draft.match_type ?? ""} onChange={(e) => set("match_type", e.target.value as SearchFilters["match_type"] || null)}><option value="">{t("ask.any")}</option>{["primary", "adjacent", "stretch", "none"].map((type) => <option key={type} value={type}>{t(`profile.match.${type}` as Key)}</option>)}</Select></label></div>
    <div className="grid grid-cols-2 gap-3">{(["has_link", "has_github"] as const).map((key) => <label key={key} className="text-sm">{t(key === "has_link" ? "ask.link" : "ask.github")}<Select className="mt-2" value={draft[key] == null ? "" : String(draft[key])} onChange={(e) => set(key, e.target.value === "" ? null : e.target.value === "true")}><option value="">{t("ask.any")}</option><option value="true">{t("ask.yes")}</option><option value="false">{t("ask.no")}</option></Select></label>)}</div>
  </Dialog>;
}
