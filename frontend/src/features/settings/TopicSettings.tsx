import { useEffect, useId, useRef, useState } from "react";
import { api } from "../../api/client";
import { useI18n, type Key } from "../../i18n";
import { TOPIC_INKS, topicColor } from "../../lib/topics";
import type { Topic, TopicApplyStatus, TopicColor } from "../../api/types";
import { Button, EmptyState, SkeletonCard, TextField } from "../../components/ui";

const blank = (): Omit<Topic, "id"> & { id?: number } => ({ name: "", description: "", include_keywords: [], exclude_keywords: [], enabled: true, color: "red" });
const keywords = (text: string) => [...new Set(text.split(/[,，\n]/).map((k) => k.trim()).filter(Boolean))].slice(0, 20);

function pickUnusedColor(existingTopics: Topic[]): TopicColor {
  const allColors = Object.keys(TOPIC_INKS) as TopicColor[];
  const used = new Set(existingTopics.map((t) => t.color));
  const unused = allColors.find((c) => !used.has(c));
  if (unused) return unused;
  return allColors[existingTopics.length % allColors.length];
}

export default function TopicSettings() {
  const { t } = useI18n();
  const id = useId();
  const mounted = useRef(true);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [limit, setLimit] = useState(12);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<ReturnType<typeof blank> | null>(null);
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [text, setText] = useState("");
  const [testing, setTesting] = useState(false);
  const [matches, setMatches] = useState<{ topic_id: number; reason: string }[] | null>(null);
  const [job, setJob] = useState<TopicApplyStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const reload = async () => {
    const result = await api.topics();
    if (mounted.current) { setTopics(result.topics); setLimit(result.max); }
  };
  useEffect(() => {
    mounted.current = true;
    reload().catch((e) => { if (mounted.current) setError(e.message); }).finally(() => { if (mounted.current) setLoading(false); });
    api.topicsProgress().then((value) => { if (mounted.current) setJob(value); }).catch((e) => { if (mounted.current) setError(e.message); });
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (job?.state !== "running") return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try { const value = await api.topicsProgress(); if (!cancelled) { setError(""); setJob(value); } }
      catch (e) { if (!cancelled) { setError((e as Error).message); setJob((current) => current && { ...current }); } }
    }, 1500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [job]);
  useEffect(() => { if (job?.state === "done") window.dispatchEvent(new Event("feedlens:topicsChanged")); }, [job?.state]);
  const edit = (topic?: Topic | (Omit<Topic, "id"> & { id?: number })) => {
    const item = topic ?? { ...blank(), color: pickUnusedColor(topics) };
    setDraft({ ...item });
    setInclude(item.include_keywords.join(", "));
    setExclude(item.exclude_keywords.join(", "));
    setError("");
  };
  const mutate = async (action: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await action(); await reload(); setMatches(null); window.dispatchEvent(new Event("feedlens:topicsChanged")); return true; }
    catch (e) { if (mounted.current) setError((e as Error).message); return false; }
    finally { if (mounted.current) setBusy(false); }
  };
  const save = async () => {
    if (!draft || busy) return;
    const ok = await mutate(() => api.saveTopic({ ...draft, name: draft.name.trim(), description: draft.description.trim(), include_keywords: keywords(include), exclude_keywords: keywords(exclude) }));
    if (ok && mounted.current) setDraft(null);
  };
  return <section className="min-w-0">
    <h3 className="font-headline text-2xl font-semibold">{t("topics.title")}</h3>
    <p className="mt-2 text-sm leading-relaxed text-ink-soft">{t("topics.hint")}</p>
    {error && <p role="alert" className="mt-3 text-sm text-danger">{error} <button type="button" className="underline" onClick={() => reload().then(() => setError("")).catch((e) => setError(e.message))}>{t("act.retry")}</button></p>}
    {loading ? <div className="mt-4"><SkeletonCard /></div> : <>
      <div className="my-4 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-ink-soft">{t("topics.limit", { n: topics.length, max: limit })}</span><Button disabled={busy || topics.length >= limit || !!draft || job?.state === "running"} variant="outline" className="min-h-11" onClick={() => edit()}>{t("topics.add")}</Button></div>
      {!topics.length && !draft && <EmptyState title={t("topics.empty")} />}
      <ul className="divide-y divide-line">
        {topics.map((topic) => <li key={topic.id} className="py-4">
          <div className="flex items-start gap-3"><input type="checkbox" className="mt-1 size-5 shrink-0 accent-accent" aria-label={`${t("topics.enabled")}: ${topic.name}`} checked={topic.enabled} disabled={busy || job?.state === "running"} onChange={async (e) => { const enabled = e.target.checked; setTopics((current) => current.map((item) => item.id === topic.id ? { ...item, enabled } : item)); if (!await mutate(() => api.saveTopic({ ...topic, enabled }))) setTopics((current) => current.map((item) => item.id === topic.id ? topic : item)); }} />
            <div className="min-w-0 flex-1"><h4 className="flex items-center gap-2 font-medium [overflow-wrap:anywhere]"><span className="size-2.5 shrink-0 rounded-full" style={{ background: topicColor(topic.color) }} />{topic.name}</h4><p className="mt-1 text-sm text-ink-soft [overflow-wrap:anywhere]">{topic.description}</p>
              <div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="ghost" className="min-h-11" disabled={busy || !!draft || job?.state === "running"} onClick={() => edit(topic)}>{t("topics.edit")}</Button><Button size="sm" variant="ghost" className="min-h-11 text-danger" disabled={busy || job?.state === "running"} onClick={() => { if (confirm(t("topics.deleteConfirm", { name: topic.name }))) void mutate(() => api.deleteTopic(topic.id)); }}>{t("act.delete")}</Button></div>
            </div>
          </div>
        </li>)}
      </ul>
    </>}
    {draft && <form className="page-enter my-5 space-y-4 border-y border-line py-5" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <h4 className="font-headline text-xl">{t(draft.id == null ? "topics.add" : "topics.edit")}</h4>
      <label className="block text-sm">{t("topics.name")}<TextField autoFocus required maxLength={80} className="mt-2" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
      <label className="block text-sm">{t("topics.description")}<TextField as="textarea" maxLength={400} rows={3} className="mt-2 resize-y" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
      <label className="block text-sm">{t("topics.include")}<TextField className="mt-2" value={include} onChange={(e) => setInclude(e.target.value)} /></label>
      <label className="block text-sm">{t("topics.exclude")}<TextField className="mt-2" value={exclude} onChange={(e) => setExclude(e.target.value)} /></label>
      <fieldset><legend className="text-sm">{t("topics.color")}</legend><div className="mt-2 flex flex-wrap gap-1">{(Object.keys(TOPIC_INKS) as TopicColor[]).map((color) => {
        const usedBy = topics.find((t) => t.id !== draft.id && t.color === color);
        return <label key={color} title={usedBy ? usedBy.name : undefined} className="relative grid size-11 cursor-pointer place-items-center"><input type="radio" name={`${id}-color`} value={color} checked={draft.color === color} onChange={() => setDraft({ ...draft, color })} className="peer sr-only" /><span className={`relative grid size-7 place-items-center rounded-full border-2 border-transparent ring-offset-2 ring-offset-sheet peer-checked:ring-2 peer-checked:ring-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent ${usedBy ? "opacity-60 hover:opacity-100" : ""}`} style={{ background: topicColor(color) }}>{usedBy && <span aria-hidden="true" className="size-1.5 rounded-full bg-paper shadow-xs" />}</span><span className="sr-only">{t(`topics.color.${color}` as Key)}</span></label>;
      })}</div></fieldset>
      <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="size-5 accent-accent" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />{t("topics.enabled")}</label>
      <div className="flex justify-end gap-2"><Button variant="ghost" disabled={busy} onClick={() => setDraft(null)}>{t("act.cancel")}</Button><Button type="submit" busy={busy} disabled={!draft.name.trim()}>{t("topics.save")}</Button></div>
    </form>}
    <section className="mt-6 border-t border-line pt-5">
      <h4 className="font-headline text-xl">{t("topics.test")}</h4><p className="mt-2 text-sm text-ink-soft">{t("topics.testHint")}</p>
      <label className="sr-only" htmlFor={`${id}-test`}>{t("topics.testText")}</label><TextField as="textarea" id={`${id}-test`} maxLength={4000} rows={3} className="mt-3 resize-y" value={text} onChange={(e) => { setText(e.target.value); setMatches(null); }} />
      <Button className="mt-3 min-h-11" variant="outline" busy={testing} disabled={!text.trim() || !topics.some((topic) => topic.enabled) || busy || !!draft} onClick={async () => { setTesting(true); setMatches(null); setError(""); try { const result = await api.testTopics(text.trim()); if (mounted.current) setMatches(result.matches); } catch (e) { if (mounted.current) setError((e as Error).message); } finally { if (mounted.current) setTesting(false); } }}>{t("topics.test")}</Button>
      {matches && <div role="status" className="mt-3 text-sm">{!matches.length ? t("topics.noneTest") : <ul className="space-y-2">{matches.map((match) => <li key={match.topic_id} className="[overflow-wrap:anywhere]"><b>{topics.find((topic) => topic.id === match.topic_id)?.name}</b>{match.reason && <p className="mt-1 text-ink-soft">{match.reason}</p>}</li>)}</ul>}</div>}
    </section>
    <section className="mt-6 border-t border-line pt-5"><p className="text-sm text-ink-soft">{t("topics.applyHint")}</p>
      <Button className="mt-3 min-h-11 max-w-full [&>span]:whitespace-normal [&>span]:text-left" variant="outline" busy={starting || job?.state === "running"} disabled={busy || !!draft || loading} onClick={async () => { setStarting(true); setError(""); try { const value = await api.applyTopics(); if (mounted.current) setJob(value); } catch (e) { if (mounted.current) setError((e as Error).message); } finally { if (mounted.current) setStarting(false); } }}>{t("topics.apply")}</Button>
      {job && job.state !== "idle" && <div role="status" className="mt-3 text-sm">{job.state === "error" ? t("topics.applyError") : job.state === "done" ? t("topics.applied") : t("topics.progress", { done: job.done, total: job.total })}{job.state === "running" && <progress className="mt-2 block h-2 w-full accent-accent" max={Math.max(1, job.total)} value={job.done} aria-label={t("topics.progress", { done: job.done, total: job.total })} />}</div>}
    </section>
  </section>;
}
