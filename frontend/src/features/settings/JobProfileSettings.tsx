import { X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { api } from "../../api/client";
import { useI18n, type Key } from "../../i18n";
import type { AIProviderInfo, JobProfile } from "../../api/types";
import { Button, Select, SkeletonCard, TextField } from "../../components/ui";

const EMPTY: JobProfile = { markdown: "", criteria: { work_modes: [], locations: [], min_salary: null, currency: "VND", level: "" }, primary_roles: [], adjacent_roles: [], allow_adjacent: true };

export default function JobProfileSettings({ providers }: { providers: AIProviderInfo[] }) {
  const { t, lang } = useI18n();
  const fileInput = useRef<HTMLInputElement>(null);
  const [profile, setProfile] = useState<JobProfile>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [provider, setProvider] = useState("auto");
  const [busy, setBusy] = useState("load");
  const [error, setError] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [notice, setNotice] = useState<Key | null>(null);
  const load = async () => {
    setBusy("load"); setError(""); setLoadFailed(false);
    try { setProfile(await api.profile() ?? EMPTY); }
    catch (e) { setError((e as Error).message); setLoadFailed(true); }
    finally { setBusy(""); }
  };
  useEffect(() => { void load(); }, []);
  const set = <K extends keyof JobProfile>(key: K, value: JobProfile[K]) => { setProfile((p) => ({ ...p, [key]: value })); setNotice(null); };
  const criterion = <K extends keyof JobProfile["criteria"]>(key: K, value: JobProfile["criteria"][K]) => {
    setProfile((p) => ({ ...p, criteria: { ...p.criteria, [key]: value } })); setNotice(null);
  };
  const selectFile = (next?: File) => {
    setError("");
    if (next && next.size > 5 * 1024 * 1024) { setFile(null); if (fileInput.current) fileInput.current.value = ""; setError(t("error.cv_too_large")); return; }
    setFile(next ?? null); setNotice(null);
  };
  const analyze = async () => {
    setBusy("analyze"); setError(""); setNotice(null);
    try {
      const form = new FormData();
      if (file) form.set("file", file); else form.set("text", text);
      form.set("language", lang); form.set("ai_provider", provider);
      const result = await api.analyzeCV(form);
      setProfile((p) => ({ ...p, markdown: result.markdown, primary_roles: result.suggested_roles, adjacent_roles: result.adjacent_roles.map((r) => ({ ...r, enabled: r.enabled ?? true })) }));
      if (result.ai_status === "unavailable") setNotice("profile.aiUnavailable");
      else { setFile(null); if (fileInput.current) fileInput.current.value = ""; setText(""); setNotice(result.offline ? "profile.offline" : "profile.review"); }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  };
  const save = async () => {
    setBusy("save"); setError(""); setNotice(null);
    try { setProfile(await api.saveProfile(profile)); setNotice("profile.saved"); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  };
  const remove = async () => {
    if (!confirm(t("profile.deleteConfirm"))) return;
    setBusy("delete"); setError(""); setNotice(null);
    try { await api.deleteProfile(); setProfile(EMPTY); setText(""); setFile(null); if (fileInput.current) fileInput.current.value = ""; setNotice("profile.deleted"); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  };
  return (
    <section className="border-b border-line pb-6">
      <h3 className="font-headline text-2xl font-semibold">{t("profile.title")}</h3>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">{t("profile.hint")}</p>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error} {loadFailed && <Button variant="ghost" onClick={load}>{t("act.retry")}</Button>}</p>}
      {busy === "load" ? <div className="mt-4"><SkeletonCard /></div> : !loadFailed && (
        <fieldset disabled={!!busy} className="mt-5 min-w-0 space-y-5 disabled:opacity-75">
          <div onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (!busy) selectFile(e.dataTransfer.files[0]); }} className="border border-dashed border-[var(--field-line)] bg-[var(--field-bg)] p-4">
            <label className="block cursor-pointer text-sm font-medium">
              <input ref={fileInput} type="file" accept=".pdf,application/pdf" onChange={(e) => selectFile(e.target.files?.[0])} className="peer sr-only" />
              <span className="inline-flex min-h-11 items-center rounded-full bg-primary px-4 py-2 text-primary-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent peer-focus-visible:outline-offset-2">{t("profile.upload")}</span>
            </label>
            <p className="mt-2 break-words text-xs text-ink-soft">{file?.name ?? t("profile.noFile")}</p>
          </div>
          <label className="block text-sm">{t("profile.paste")}
            <TextField as="textarea" aria-label={t("profile.paste")} className="mt-2" rows={4} value={text} onChange={(e) => { setText(e.target.value); setNotice(null); }} disabled={!!file || !!busy} />
          </label>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-0 flex-1 text-sm">{t("profile.provider")}
              <Select aria-label={t("profile.provider")} className="mt-2" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="auto">{t("profile.auto")}</option>
                {providers.filter((p) => p.key !== "offline" && p.configured).map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                <option value="offline">{t("profile.offlineOption")}</option>
              </Select>
            </label>
            <Button onClick={analyze} busy={busy === "analyze"} disabled={!!busy || (!file && text.trim().length < 20)}>{t("profile.analyze")}</Button>
          </div>
          {notice && <p role="status" className="border-y border-line py-3 text-sm text-ink-soft">{t(notice)}{notice === "profile.aiUnavailable" && <> <Button variant="ghost" onClick={analyze} busy={busy === "analyze"} disabled={!!busy || (!file && text.trim().length < 20)}>{t("act.retry")}</Button></>}</p>}
          <label className="block text-sm font-medium">{t("profile.markdown")}
            <TextField as="textarea" aria-label={t("profile.markdown")} className="mt-2 font-mono text-xs" rows={8} maxLength={8000} value={profile.markdown} onChange={(e) => set("markdown", e.target.value)} />
          </label>
          <details className="border-y border-line py-3">
            <summary className="min-h-10 cursor-pointer text-sm font-medium">{t("profile.preview")}</summary>
            <div className="prose-reading mt-3 [overflow-wrap:anywhere]">{profile.markdown.split("\n").map((line, i) => line.startsWith("#") ? <h4 key={i} className="mt-4 font-headline text-xl">{line.replace(/^#+\s*/, "")}</h4> : line.startsWith("- ") ? <p key={i}>• {line.slice(2)}</p> : <p key={i}>{line || "\u00a0"}</p>)}</div>
          </details>
          <ListEditor label={t("profile.primary")} values={profile.primary_roles} onChange={(v) => set("primary_roles", v.slice(0, 3))} max={3} />
          <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" checked={profile.allow_adjacent} onChange={(e) => set("allow_adjacent", e.target.checked)} className="size-5 accent-[var(--accent)]" />{t("profile.allowAdjacent")}</label>
          <div>
            <h4 className="text-sm font-medium">{t("profile.adjacent")}</h4>
            {!profile.adjacent_roles.length && <p className="mt-2 text-xs text-ink-soft">{t("profile.adjacentHint")}</p>}
            {profile.adjacent_roles.map((role, i) => <label key={i} className="mt-3 flex items-start gap-3 text-sm">
              <input type="checkbox" className="mt-1 size-5 shrink-0 accent-[var(--accent)]" checked={role.enabled} onChange={(e) => set("adjacent_roles", profile.adjacent_roles.map((r, index) => index === i ? { ...r, enabled: e.target.checked } : r))} />
              <span className="min-w-0 [overflow-wrap:anywhere]"><b>{role.role}</b><span className="mt-1 block text-xs leading-relaxed text-ink-soft">{role.reason}</span></span>
            </label>)}
          </div>
          <h4 className="border-t border-line pt-4 font-headline text-xl">{t("profile.criteria")}</h4>
          <fieldset><legend className="text-sm">{t("profile.workModes")}</legend><div className="mt-2 flex flex-wrap gap-4">
            {(["remote", "hybrid", "onsite"] as const).map((mode) => <label key={mode} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" className="size-5 accent-[var(--accent)]" checked={profile.criteria.work_modes.includes(mode)} onChange={(e) => criterion("work_modes", e.target.checked ? [...profile.criteria.work_modes, mode] : profile.criteria.work_modes.filter((m) => m !== mode))} />{t(`profile.mode.${mode}`)}</label>)}
          </div></fieldset>
          <ListEditor label={t("profile.locations")} values={profile.criteria.locations} onChange={(v) => criterion("locations", v)} max={20} />
          <div className="grid grid-cols-[minmax(0,1fr)_90px] gap-3">
            <label className="text-sm">{t("profile.salary")}<TextField className="mt-2" type="number" min={0} value={profile.criteria.min_salary ?? ""} onChange={(e) => criterion("min_salary", e.target.value === "" ? null : Number(e.target.value))} /></label>
            <label className="text-sm">{t("profile.currency")}<Select aria-label={t("profile.currency")} className="mt-2" value={profile.criteria.currency} onChange={(e) => criterion("currency", e.target.value as "VND" | "USD")}><option>VND</option><option>USD</option></Select></label>
          </div>
          <label className="block text-sm">{t("profile.level")}<Select aria-label={t("profile.level")} className="mt-2" value={profile.criteria.level} onChange={(e) => criterion("level", e.target.value)}>{["", "intern", "fresher", "junior", "mid", "senior", "lead"].map((level) => <option key={level} value={level}>{t(`profile.level.${level || "any"}` as Key)}</option>)}</Select></label>
          <div className="flex flex-wrap gap-3 border-t border-line pt-4"><Button onClick={save} busy={busy === "save"} disabled={!!busy || !profile.markdown.trim()}>{t("profile.save")}</Button><Button variant="ghost" onClick={remove} busy={busy === "delete"} disabled={!!busy} className="hover:text-danger">{t("profile.delete")}</Button></div>
        </fieldset>
      )}
    </section>
  );
}

function ListEditor({ label, values, onChange, max }: { label: string; values: string[]; onChange: (values: string[]) => void; max: number }) {
  const { t } = useI18n();
  const inputId = useId();
  const [draft, setDraft] = useState("");
  const add = () => { const value = draft.trim(); if (value && !values.includes(value) && values.length < max) onChange([...values, value]); setDraft(""); };
  return <div><label htmlFor={inputId} className="block text-sm">{label}</label>
    <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-2xl border border-[var(--field-line)] bg-[var(--field-bg)] p-2 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-glow)]">
      {values.map((value) => <button key={value} type="button" onClick={() => onChange(values.filter((v) => v !== value))} aria-label={t("profile.removeItem", { value })} className="inline-flex min-h-11 max-w-full items-center gap-2 rounded-full bg-sunken px-3 py-1 text-sm [overflow-wrap:anywhere]"><span className="min-w-0">{value}</span><X aria-hidden="true" className="size-3.5 shrink-0" /></button>)}
      <input id={inputId} className="min-h-11 min-w-16 flex-1 bg-transparent px-2 text-sm text-ink border-0! outline-none! ring-0! [box-shadow:none]! focus-visible:outline-none!" maxLength={120} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); add(); } }} />
      <button type="button" disabled={!draft.trim() || values.length >= max} onClick={add} className="interactive-tap ml-auto min-h-11 shrink-0 rounded-full px-3 text-xs font-medium text-link hover:bg-sunken disabled:text-ink-faint disabled:cursor-not-allowed">{t("cmp.add")}</button>
    </div>
  </div>;
}
