import { Briefcase, X } from "lucide-react";
import { useI18n, type Key } from "../../i18n";
import type { JobProfile, Mode, RunRequest } from "../../types";
import { TextField } from "../ui";

const KEYWORD_SUGGESTIONS = ["remote", "junior", "senior", "intern", "part-time", "Hà Nội", "HCM", "Đà Nẵng"];
const KEYWORD_LABELS: Record<string, Key> = {
  remote: "kw.remote", junior: "kw.junior", senior: "kw.senior", intern: "kw.intern", "part-time": "kw.partTime",
  "Hà Nội": "kw.hanoi", HCM: "kw.hcm", "Đà Nẵng": "kw.danang",
};

interface Props {
  mode: Mode;
  f: Pick<RunRequest, "job_mode" | "profile">;
  set: <K extends "job_mode" | "profile">(key: K, value: RunRequest[K]) => void;
  keywords: string[];
  setKeywords: (list: string[]) => void;
  kwDraft: string;
  setKwDraft: (value: string) => void;
  addKeyword: (raw: string) => void;
  jobProfile: JobProfile | null;
  onOpenSettings: (tab?: string) => void;
}

export function JobCriteria({ mode, f, set, keywords, setKeywords, kwDraft, setKwDraft, addKeyword, jobProfile, onOpenSettings }: Props) {
  const { t } = useI18n();
  return (
    <>
          {mode !== "jobs" && <section className={`rounded-card border p-4 transition-colors duration-[var(--duration-fast)] ${f.job_mode ? "border-ink bg-surface" : "border-line"}`}>
            <label className="flex cursor-pointer items-start gap-3">
              <span className={`grid size-9 shrink-0 place-items-center rounded-full ${f.job_mode ? "bg-primary text-primary-ink" : "bg-sunken text-ink-soft"}`}>
                <Briefcase className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{t("cmp.jobs")}</span>
                <span className="block text-sm text-ink-soft">{t("cmp.jobsHint")}</span>
              </span>
              <input type="checkbox" className="peer sr-only" checked={f.job_mode} onChange={(e) => set("job_mode", e.target.checked)} />
              <span aria-hidden className="relative mt-1 h-5 w-9 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-primary peer-focus-visible:outline-2 peer-focus-visible:outline-accent
                after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition-transform after:duration-[var(--duration-fast)] motion-reduce:after:transition-none peer-checked:after:translate-x-4" />
            </label>
            {f.job_mode && (
              <div className="page-enter mt-5 space-y-5">
                <div>
                  <span className="mb-1.5 block text-sm font-medium">{t("cmp.keywords")}</span>
                  <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-[var(--field-line)] bg-[var(--field-bg)] p-2 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-glow)]">
                    {keywords.map((k) => (
                      <span key={k} className="page-enter flex max-w-full items-center gap-1 rounded-full bg-primary py-0.5 pr-1 pl-3 text-xs text-primary-ink">
                        <span className="min-w-0 truncate" title={k}>{k}</span>
                        <button type="button" aria-label={t("cmp.kwRemove", { k })} onClick={() => setKeywords(keywords.filter((x) => x !== k))}
                          className="interactive-tap grid size-9 shrink-0 place-items-center rounded-full hover:bg-primary-ink/20"><X className="size-3" /></button>
                      </span>
                    ))}
                    <input className="min-w-24 flex-1 bg-transparent px-1 py-1 text-sm border-0! outline-none! ring-0! [box-shadow:none]! focus-visible:outline-none! placeholder:text-ink-soft/70"
                      placeholder={keywords.length ? t("cmp.kwAdd") : t("cmp.kwPlaceholder")} value={kwDraft}
                      onChange={(e) => setKwDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.nativeEvent.isComposing) return;
                        if ((e.key === "Enter" || e.key === ",") && kwDraft.trim()) { e.preventDefault(); addKeyword(kwDraft); }
                        if (e.key === "Backspace" && !kwDraft && keywords.length) setKeywords(keywords.slice(0, -1));
                      }}
                      onBlur={() => kwDraft.trim() && addKeyword(kwDraft)} aria-label={t("cmp.kwAria")} />
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {KEYWORD_SUGGESTIONS.filter((s) => !keywords.includes(s) && !keywords.includes(t(KEYWORD_LABELS[s]))).map((s) => (
                      <button key={s} type="button" onClick={() => addKeyword(t(KEYWORD_LABELS[s]))}
                        className="interactive-tap min-h-10 rounded-full border border-line px-3 py-1 text-xs text-ink-soft hover:border-ink hover:bg-surface hover:text-ink">
                        + {t(KEYWORD_LABELS[s])}
                      </button>
                    ))}
                  </div>
                </div>
                {jobProfile && <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-y border-line py-3 text-sm"><span>{t("profile.using", { role: jobProfile.primary_roles.join(", ") || t("profile.title") })}</span><button type="button" onClick={() => onOpenSettings()} className="shrink-0 text-link underline underline-offset-4">{t("profile.edit")}</button></p>}
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium">{t(jobProfile ? "profile.notes" : "cmp.profile")}</span>
                  <TextField as="textarea" aria-label={t(jobProfile ? "profile.notes" : "cmp.profile")} className="resize-y" rows={3} value={f.profile} onChange={(e) => set("profile", e.target.value)}
                    placeholder={t(jobProfile ? "profile.notesPh" : "cmp.profilePh")} />
                  <span className="mt-1 block text-xs text-ink-soft">{t(jobProfile ? "profile.notesHint" : "cmp.profileHint")}</span>
                </label>
              </div>
            )}
          </section>}
          {mode === "jobs" && <section className="rounded-card border border-line p-4">
            {jobProfile ? <p className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-3 text-sm">
              <span>{t("profile.using", { role: jobProfile.primary_roles.join(", ") || t("profile.title") })}</span>
              <button type="button" onClick={() => onOpenSettings("profile")} className="shrink-0 text-link underline underline-offset-4">{t("profile.edit")}</button>
            </p> : <p className="mb-4 flex flex-wrap items-center gap-2 border-b border-line pb-3 text-sm text-ink-soft">
              <span>{t("cmp.jobsProfileHint")}</span>
              <button type="button" onClick={() => onOpenSettings("profile")} className="font-medium text-link underline underline-offset-4">{t("profile.upload")}</button>
            </p>}
            <label className="block"><span className="mb-1.5 block text-sm font-medium">{t(jobProfile ? "profile.notes" : "cmp.profile")}</span>
              <TextField as="textarea" aria-label={t(jobProfile ? "profile.notes" : "cmp.profile")} className="resize-y" rows={2} value={f.profile} onChange={(e) => set("profile", e.target.value)}
                placeholder={t(jobProfile ? "profile.notesPh" : "cmp.profilePh")} />
              <span className="mt-1 block text-xs text-ink-soft">{t(jobProfile ? "profile.notesHint" : "cmp.profileHint")}</span>
            </label>
          </section>}
    </>
  );
}
