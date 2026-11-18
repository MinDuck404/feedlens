import { Briefcase, Check, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { groupName } from "../logic";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { formatNumber, useI18n, type Key } from "../i18n";
import { Sheet, Button, IconButton, Skeleton, Select, SegmentedControl } from "./ui";
import { PLATFORM_MODES, applyJobProfileDefaults, countPlan, defaultDraft, defaultMode, draftFromRequest, draftKey, inferMode, jobProfileSuggestions,
  migratePreferences, modeDefinition, serializeDraft, sourceLines, validateDraft, type ModeDraft, type ModePreferences } from "../platformModes";
import type {
  AIProviderInfo, JobProfile, Me, Meta, Mode, ModeOptions, Platform, PlatformSession, PlatformState, Preferences, RunRequest, SavedGroup,
} from "../types";

const DEFAULTS: RunRequest = {
  platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false, keywords: [], profile: "",
  ai_provider: "offline", ai_model: "", only_new: false, headless: false, speed: "fast", runner: "agent",
};

/** Link dán vào ô một dòng: tách theo dấu cách, xuống dòng hoặc dấu phẩy */
const links = (t: string) => t.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);

const KEYWORD_SUGGESTIONS = ["remote", "junior", "senior", "intern", "part-time", "Hà Nội", "HCM", "Đà Nẵng"];
const KEYWORD_LABELS: Record<string, Key> = {
  remote: "kw.remote", junior: "kw.junior", senior: "kw.senior", intern: "kw.intern", "part-time": "kw.partTime",
  "Hà Nội": "kw.hanoi", HCM: "kw.hcm", "Đà Nẵng": "kw.danang",
};

/** Rút gọn link nhóm để dễ đọc: facebook.com/groups/vieclamit */
const shortUrl = (u: string) => u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");

interface Props {
  meta: Meta;
  me: Me | null;
  platforms: PlatformState[];
  prefs: Preferences;
  onPrefsChange: (p: Preferences) => void;
  onClose: () => void;
  onCreated: (id: number) => void;
  onOpenSettings: (tab?: string) => void;
  initialRequest?: RunRequest;
}

export default function Composer({ meta, me, platforms, prefs, onPrefsChange, onClose, onCreated, onOpenSettings, initialRequest }: Props) {
  const [open, setOpen] = useState(true);
  const handleClose = useCallback(() => {
    setOpen(false);
    setTimeout(onClose, 200);
  }, [onClose]);

  const [stored] = useState(() => migratePreferences(prefs));
  const saved = initialRequest ? { ...prefs.composer, ...initialRequest, keywords_text: (initialRequest.keywords ?? []).join(", ") } : prefs.composer ?? {};
  const initialPlatform = saved.platform ?? "facebook", initialMode = inferMode(saved);
  const initialDraft = initialRequest ? draftFromRequest(initialRequest) : stored.drafts[draftKey(initialPlatform, initialMode)] ?? draftFromRequest(saved);
  const { t, lang } = useI18n();
  const [topicCount, setTopicCount] = useState<number | null>(null);
  const [jobProfile, setJobProfile] = useState<JobProfile | null>(null);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [providers, setProviders] = useState<AIProviderInfo[] | null>(null);
  const [sessions, setSessions] = useState<PlatformSession[]>([]);
  const [f, setF] = useState<RunRequest>({ ...DEFAULTS, ...saved, platform: initialPlatform, mode: initialMode,
    source_type: modeDefinition(initialPlatform, initialMode).sourceType, options: initialDraft.options as ModeOptions,
    count: initialDraft.count, sources: [], keywords: [], job_mode: initialMode === "jobs" || saved.job_mode || false });
  const [drafts, setDrafts] = useState(stored.drafts);
  const [savedSources, setSavedSources] = useState(() => {
    if (!initialRequest) return stored.saved_sources;
    const key = draftKey(initialPlatform, initialMode), selected = new Set(initialRequest.sources);
    const previous = stored.saved_sources[key] ?? [];
    return { ...stored.saved_sources, [key]: [...previous.map((source) => ({ ...source, enabled: selected.has(source.url) })),
      ...initialRequest.sources.filter((url) => !previous.some((source) => source.url === url)).map((url) => ({ url, enabled: true }))] };
  });
  const [sourceText, setSourceText] = useState(initialDraft.sourceText);
  const selectedModes = useRef<Partial<Record<Platform, Mode>>>({ [initialPlatform]: initialMode });
  const [newGroups, setNewGroups] = useState(initialDraft.sourceEntry ?? "");
  const [keywordsText, setKeywordsText] = useState(saved.keywords_text ?? "");
  const [kwDraft, setKwDraft] = useState("");
  const keywords = keywordsText.split(",").map((s) => s.trim()).filter(Boolean);
  const setKeywords = (list: string[]) => setKeywordsText(list.join(", "));
  const addKeyword = (raw: string) => {
    // cập nhật theo giá trị mới nhất, để bấm nhanh nhiều gợi ý liên tiếp không bị mất từ nào
    setKeywordsText((prev) => {
      const cur = prev.split(",").map((s) => s.trim()).filter(Boolean);
      const add = raw.split(",").map((s) => s.trim()).filter((s) => s && !cur.includes(s));
      return [...cur, ...add].join(", ");
    });
    setKwDraft("");
  };
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState("");
  const set = <K extends keyof RunRequest>(k: K, v: RunRequest[K]) => setF((s) => ({ ...s, [k]: v }));

  const cloud = meta.mode === "cloud";
  const serverMode = cloud && meta.server_scrape && f.runner === "server";
  const session = sessions.find((x) => x.platform === f.platform);
  const platformOptions = platforms.length
    ? platforms.map((p) => ({ value: p.key, label: p.name.replace(" (Twitter)", "") }))
    : Object.entries(PLATFORM_LABEL).map(([value, label]) => ({ value, label }));
  const platformState = platforms.find((p) => p.key === f.platform);
  const mode = f.mode ?? defaultMode(f.platform);
  const definition = modeDefinition(f.platform, mode);
  const hint = definition.fields.find((field) => field.name === "sources");
  const usesSaved = definition.sourceType === "group";
  const key = draftKey(f.platform, mode);
  const usable = (providers ?? []).filter((p) => p.configured);
  const myGroups: SavedGroup[] = savedSources[key] ?? [];
  const sources = usesSaved ? myGroups.filter((g) => g.enabled).map((g) => g.url) : sourceLines(sourceText);
  const draft: ModeDraft = { count: f.count, sourceText: sources.join("\n"), ...(newGroups ? { sourceEntry: newGroups } : {}), options: (f.options ?? {}) as ModeDraft["options"] };
  const effectiveMaxPosts = prefs.max_posts ?? meta.max_posts;
  const plan = countPlan(f.platform, mode, draft, effectiveMaxPosts);
  const nSources = plan.sources, total = plan.total;
  const changeMode = (platform: Platform, nextMode = selectedModes.current[platform] ?? defaultMode(platform)) => {
    if (platform === f.platform && nextMode === mode) return;
    setDrafts((old) => ({ ...old, [key]: draft }));
    const next = drafts[draftKey(platform, nextMode)] ?? defaultDraft(platform, nextMode);
    if (modeDefinition(platform, nextMode).sourceType === "group" && !savedSources[draftKey(platform, nextMode)]) {
      setSavedSources((old) => ({ ...old, [draftKey(platform, nextMode)]: sourceLines(next.sourceText).map((url) => ({ url, enabled: true })) }));
    }
    selectedModes.current[platform] = nextMode;
    setF((old) => ({ ...old, platform, mode: nextMode, source_type: modeDefinition(platform, nextMode).sourceType,
      options: next.options as ModeOptions, count: next.count, job_mode: nextMode === "jobs" || (old.mode !== "jobs" && old.job_mode) }));
    setSourceText(next.sourceText);
    setNewGroups(next.sourceEntry ?? "");
    setError("");
  };
  const setOption = (name: string, value: ModeDraft["options"][string]) =>
    setF((old) => ({ ...old, options: { ...old.options, [name]: value } as ModeOptions }));

  const loadProviders = () => {
    setLoadError("");
    if (cloud && meta.server_scrape) api.sessions().then(setSessions).catch((e) => setLoadError(e.message));
    api.providers().then((list) => {
      setProviders(list);
      const ok = (k?: string) => !!k && list.some((p) => p.key === k && p.configured);
      const first = list.find((p) => p.configured && p.key !== "offline")?.key ?? "offline";
      const preferred = list.find((p) => p.configured && p.is_default)?.key;
      const selected = preferred ?? (ok(saved.ai_provider) ? saved.ai_provider! : first);
      setF((s) => ({ ...s, ai_provider: selected,
                     ai_model: selected === saved.ai_provider ? saved.ai_model ?? "" : "" }));
    }).catch((e) => { setProviders([]); setLoadError(e.message); });
  };
  useEffect(() => { api.topics().then((data) => setTopicCount(data.topics.filter((topic) => topic.enabled).length)).catch((e) => setLoadError(e.message)); loadProviders();
    api.profile().then(setJobProfile).catch((e) => setLoadError(e.message)).finally(() => setProfileLoaded(true)); }, []);
  const autoFilledProfile = useRef(false);
  useEffect(() => {
    if (!profileLoaded || !jobProfile || initialRequest || mode !== "jobs" || autoFilledProfile.current) return;
    autoFilledProfile.current = true;
    const next = applyJobProfileDefaults({ count: f.count, sourceText, options: (f.options ?? {}) as ModeDraft["options"] }, jobProfile);
    const currentOptions = (f.options ?? {}) as ModeDraft["options"];
    if (next.options.keywords !== currentOptions.keywords || next.options.location !== currentOptions.location
        || next.options.work_modes !== currentOptions.work_modes) {
      setF((current) => ({ ...current, options: next.options as ModeOptions }));
      setDrafts((old) => ({ ...old, [key]: next }));
    }
  }, [profileLoaded, jobProfile, initialRequest, mode, key, f.count, f.options, sourceText]);

  const snapshot = (next: Partial<ModePreferences> = {}): ModePreferences => ({
    ...stored,
    composer: { ...f, sources: undefined, keywords: undefined, keywords_text: keywordsText },
    drafts: { ...drafts, [key]: { ...draft, sourceText: usesSaved
      ? ((next.saved_sources ?? savedSources)[key] ?? []).filter((source) => source.enabled).map((source) => source.url).join("\n") : draft.sourceText } },
    saved_sources: savedSources, ...next,
  });

  /** Lưu cài đặt vào tài khoản (không chặn giao diện nếu lỗi mạng). */
  const persist = (next: Partial<ModePreferences>) => {
    const p = snapshot(next);
    lastSaved.current = JSON.stringify(p);
    onPrefsChange(p);
  };

  // Đóng form (nút X, Esc, bấm ra ngoài) cũng lưu lại những gì vừa chỉnh
  const latest = useRef(snapshot());
  latest.current = snapshot();
  const lastSaved = useRef(JSON.stringify(snapshot()));
  useEffect(() => () => {
    const json = JSON.stringify(latest.current);
    if (json !== lastSaved.current) {
      onPrefsChange(latest.current);
    }
  }, []);

  const updateGroups = (list: SavedGroup[]) => {
    const next = { ...savedSources, [key]: list };
    setSavedSources(next);
    persist({ saved_sources: next });
  };
  const addGroups = () => {
    const known = new Set(myGroups.map((g) => g.url.replace(/\/$/, "")));
    const added: SavedGroup[] = [];
    for (const raw of (hint?.type === "saved" ? links(newGroups) : sourceLines(newGroups))) {
      const url = raw.replace(/\/$/, "");
      if (!known.has(url)) { known.add(url); added.push({ url, enabled: true }); }
    }
    if (added.length) updateGroups([...myGroups, ...added]);
    setNewGroups("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const invalid = validateDraft(f.platform, mode, draft);
    if (invalid) {
      setError(hint?.type === "saved" && !sources.length ? t(myGroups.length ? "cmp.pickGroup" : "cmp.addGroupFirst") : t(invalid));
      return;
    }
    setSending(true);
    try {
      const { id } = await api.createRun(serializeDraft({ ...f, ...(prefs.max_posts ? { max_posts: prefs.max_posts } : {}), language: lang, keywords }, mode, draft));
      persist({});
      onCreated(id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  };

  const footerNode = (
    <>
      {serverMode && (!session || session.status === "invalid") && (
        <p className="mb-3 text-sm text-danger">
          {session ? t("cmp.cookieExpired", { name: PLATFORM_LABEL[f.platform] }) : t("cmp.noCookie", { name: PLATFORM_LABEL[f.platform] })}{" "}
          <button type="button" onClick={() => onOpenSettings()} className="font-medium text-link hover:underline">
            {session ? t("cmp.sendCookie") : t("cmp.addCookie")}
          </button>
        </p>
      )}
      {!serverMode && cloud && me && !me.agent.online && (
        <p className="mb-3 text-sm text-ink-soft">
          {t("cmp.agentOff")}{" "}
          <button type="button" onClick={() => onOpenSettings()} className="font-medium text-link hover:underline">
            {me.agent.has_token ? t("cmp.howToStart") : t("cmp.connectAgent")}
          </button>
        </p>
      )}
      {loadError && <p role="alert" className="mb-3 text-sm text-danger">{loadError} <button type="button" onClick={loadProviders}>{t("act.retry")}</button></p>}
      {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
      <Button type="submit" busy={sending} size="md" className="h-11! min-h-11! w-full text-sm!">
        {sending ? t("cmp.starting") : t("cmp.start")}
      </Button>
    </>
  );

  return (
    <Sheet
      open={open}
      onClose={handleClose}
      title={t("cmp.title")}
      closeAriaLabel={t("act.close")}
      onSubmit={submit}
      footer={footerNode}
      className="[&_h2]:font-headline [&_footer]:bg-surface [&_footer]:shadow-[0_-8px_16px_-12px_rgba(0,0,0,0.18)]"
    >
      {topicCount !== null && <p className="mb-5 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-3 text-sm text-ink-soft"><span>{t(topicCount === 1 ? "topics.followingOne" : "topics.following", { n: topicCount })}</span><button type="button" className="min-h-11 text-link underline underline-offset-4" onClick={() => onOpenSettings("topics")}>{t("topics.manage")}</button></p>}
      {cloud && meta.server_scrape && (
            <Group label={t("cmp.runner")}>
              <SegmentedControl compact label={t("cmp.runner")} value={f.runner} onChange={(v) => set("runner", v as RunRequest["runner"])}
                options={[{ value: "agent", label: t("cmp.runnerAgent") }, { value: "server", label: t("cmp.runnerServer") }]} />
              <p className="mt-2 text-sm text-ink-soft">
                {f.runner === "agent"
                  ? t("cmp.runnerAgentHint")
                  : t("cmp.runnerServerHint")}
              </p>
            </Group>
          )}

          <Group label={t("cmp.platform")}>
            <SegmentedControl compact label={t("cmp.platform")} value={f.platform} onChange={(v) => changeMode(v as Platform)} options={platformOptions} />
            {!cloud && platformState && !platformState.has_profile && (
              <p className="mt-2 text-sm text-ink-soft">
                {t("cmp.notLoggedIn", { name: platformState.name })}
              </p>
            )}
          </Group>

          <Group label={t("cmp.where")}>
            <SegmentedControl compact label={t("cmp.where")} value={mode} onChange={(v) => changeMode(f.platform, v as Mode)}
              options={[...PLATFORM_MODES[f.platform], ...(mode === "legacy_group" ? [definition] : [])].map((item) => ({ value: item.mode, label: t(item.label) }))} />
            <p className="mt-2 text-sm text-ink-soft">{t(definition.description)}</p>
            {f.platform === "facebook" && mode === "search" && <p className="mt-2 text-sm text-ink-soft">{t("cmp.notice.fbSearchLowResults")}</p>}
            {(f.platform === "reddit" || f.platform === "x") && <p role="note" className="mt-3 rounded-card bg-sunken p-3 text-xs text-ink-soft">{t(f.platform === "reddit" ? "cmp.warning.redditPolicy" : "cmp.warning.xPolicy")}</p>}

            {usesSaved && hint && (
              <div className="mt-3">
                {myGroups.length > 0 && (
                  <>
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span>{t(hint.type === "saved" ? "cmp.groupsSelectedCount" : "cmp.sourcesSelectedCount", { selected: sources.length, total: myGroups.length })}</span>
                      <button type="button" className="interactive-tap min-h-10 text-link underline-offset-4 hover:underline"
                        onClick={() => updateGroups(myGroups.map((g) => ({ ...g, enabled: sources.length < myGroups.length })))}>
                        {sources.length < myGroups.length ? t("cmp.selectAll") : t("cmp.selectNone")}
                      </button>
                    </div>
                    <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded-card border border-line">
                      {myGroups.map((g, i) => {
                        const name = mode === "list" ? g.url.replace(/\/$/, "").split("/").pop()! : groupName(g.url);
                        return (
                          <li key={g.url} className="group/row flex items-center transition-colors duration-[var(--duration-fast)] hover:bg-sunken/60">
                            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 py-2.5">
                              <input type="checkbox" className="peer sr-only" checked={g.enabled}
                                onChange={(e) => updateGroups(myGroups.map((x, j) => j === i ? { ...x, enabled: e.target.checked } : x))} />
                              <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-sunken text-xs uppercase text-ink-soft
                                peer-checked:bg-primary peer-checked:text-primary-ink">
                                {name.slice(0, 2)}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-medium">{name}</span>
                                <span className="block truncate font-mono text-[11px] text-ink-soft" title={g.url}>{shortUrl(g.url)}</span>
                              </span>
                              <span aria-hidden className="grid size-5 shrink-0 place-items-center rounded-full border border-line text-transparent
                                peer-checked:border-primary peer-checked:bg-primary peer-checked:text-primary-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent">
                                <Check className="size-3" strokeWidth={3} />
                              </span>
                            </label>
                            <IconButton aria-label={t("cmp.removeGroup", { name })} title={t("cmp.removeFromList")}
                              onClick={() => updateGroups(myGroups.filter((_, j) => j !== i))}
                              className="mr-1 size-10 shrink-0 hover:text-danger">
                              <Trash2 className="size-4" />
                            </IconButton>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}
                {hint.type === "saved" ? <div className="mt-3 flex items-center gap-2 rounded-full border border-[var(--field-line)] bg-[var(--field-bg)] py-1 pr-1 pl-4 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-glow)]">
                  <input className="min-w-0 flex-1 bg-transparent py-1.5 text-sm border-0! outline-none! ring-0! [box-shadow:none]! focus-visible:outline-none! placeholder:text-ink-soft/70"
                    placeholder={myGroups.length ? t("cmp.pasteMore") : hint.example}
                    value={newGroups} onChange={(e) => setNewGroups(e.target.value)}
                    onKeyDown={(e) => { if (!e.nativeEvent.isComposing && e.key === "Enter") { e.preventDefault(); addGroups(); } }}
                    aria-label={t(hint.label)} />
                  <Button onClick={addGroups} disabled={!links(newGroups).length} variant="secondary" className="shrink-0 border-0! shadow-none! focus-visible:outline-none!">
                    {t("cmp.add")}
                  </Button>
                </div>
                : <div className="mt-3"><label className="block"><span className="mb-1.5 block text-sm">{t("cmp.onePerLine", { label: t(hint.label) })}</span>
                    <textarea className="field resize-y" rows={3} value={newGroups} aria-label={t(hint.label)} placeholder={hint.placeholder ? t(hint.placeholder) : hint.example}
                      onChange={(event) => setNewGroups(event.target.value)} /></label><Button className="mt-2" variant="secondary" disabled={!sourceLines(newGroups).length} onClick={addGroups}>{t("cmp.add")}</Button></div>}
                {hint.type === "saved" && <p className="mt-1.5 px-1 text-xs text-ink-soft">{t("cmp.addHint")}</p>}
              </div>
            )}

            {hint?.type === "sources" && !usesSaved && (
              <label className="mt-3 block">
                <span className="mb-1 block text-sm">{t("cmp.onePerLine", { label: t(hint.label) })}</span>
                <textarea className="field resize-y" rows={3} placeholder={hint.placeholder ? t(hint.placeholder) : hint.example} value={sourceText}
                  onChange={(e) => setSourceText(e.target.value)} aria-label={t(hint.label)} required={hint.required} />
              </label>
            )}
            {f.platform === "reddit" && mode === "subreddit" && <div className="mt-2 flex flex-wrap gap-2">
              {["r/forhire", "r/remotejs", "r/jobbit", "r/hiring"].map((sub) => <button key={sub} type="button"
                className="min-h-11 rounded-full border border-line px-3 text-xs text-ink-soft hover:border-ink"
                onClick={() => {
                  if (myGroups.some((source) => source.url === sub)) updateGroups(myGroups.map((source) => source.url === sub ? { ...source, enabled: true } : source));
                  else updateGroups([...myGroups, { url: sub, enabled: true }]);
                }}>+ {sub}</button>)}
            </div>}
            {definition.fields.filter((field) => field.name !== "sources").map((field) => {
              const value = draft.options[field.name];
              if (field.type === "toggle") return <div key={field.name} className="mt-3"><Toggle checked={value === true} onChange={(checked) => setOption(field.name, checked)}>{t(field.label)}</Toggle><p className="text-xs text-ink-soft">{t("cmp.input.groupChronologicalHint")}</p></div>;
              if (field.type === "multi") return <fieldset key={field.name} className="mt-4"><legend className="mb-2 text-sm">{t(field.label)}</legend><div className="flex flex-wrap gap-2">{field.choices?.map((choice) => {
                const checked = Array.isArray(value) && value.includes(choice.value);
                return <label key={choice.value} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line px-3 text-sm"><input type="checkbox" checked={checked}
                  onChange={() => setOption(field.name, checked ? (value as string[]).filter((item) => item !== choice.value) : [...(Array.isArray(value) ? value : []), choice.value])} />{t(choice.label)}</label>;
              })}</div></fieldset>;
              return <div key={field.name} className="mt-4"><label className="block"><span className="mb-1.5 block text-sm">{t(field.label)}</span>
                {field.type === "select" ? <Select aria-label={t(field.label)} value={value === null ? "" : String(value ?? "")} onChange={(event) => setOption(field.name, event.target.value || null)}>
                  {value === null && <option value="">{t("cmp.input.time.any")}</option>}{field.choices?.map((choice) => <option key={choice.value} value={choice.value}>{t(choice.label)}</option>)}
                </Select> : field.type === "number" ? <input type="number" className="field" min={field.min} max={field.max} step={1}
                  value={value === undefined || value === null ? "" : String(value)}
                  onChange={(event) => {
                    const raw = event.target.value;
                    setOption(field.name, raw === "" ? null : Number(raw));
                  }} /> : <input className="field" value={String(value ?? "")} required={field.required} maxLength={field.name === "keywords" ? 500 : 300}
                  placeholder={field.placeholder ? t(field.placeholder) : undefined} onChange={(event) => setOption(field.name, event.target.value)} />}</label>
                {field.hint && <p className="mt-1.5 text-xs text-ink-soft">{t(field.hint)}</p>}
                {mode === "jobs" && field.name === "keywords" && jobProfile && <div className="mt-2 flex flex-wrap gap-2">
                  {jobProfileSuggestions(jobProfile).map((role) => <button key={role} type="button"
                    className="min-h-10 max-w-full truncate rounded-full border border-line px-3 text-xs text-ink-soft hover:border-ink hover:text-ink"
                    title={role} onClick={() => setOption("keywords", role)}>{role}</button>)}
                </div>}
              </div>;
            })}
          </Group>

          <Group label={t(plan.label)}>
            <div className="flex items-center gap-4">
            <output className="min-w-12 text-right font-mono text-3xl font-medium tabular-nums" aria-hidden="true">{formatNumber(f.count, lang)}</output>
            <input type="range" min={1} max={Math.min(200, effectiveMaxPosts)} step={1} value={f.count}
              onChange={(e) => set("count", Number(e.target.value))}
              style={{ backgroundImage: `linear-gradient(to right, var(--accent) ${100 * (f.count - 1) / Math.max(1, Math.min(200, effectiveMaxPosts) - 1)}%, color-mix(in srgb, var(--ink) 35%, var(--sheet)) ${100 * (f.count - 1) / Math.max(1, Math.min(200, effectiveMaxPosts) - 1)}%)`, backgroundSize: "100% 6px", backgroundPosition: "center", backgroundRepeat: "no-repeat" }}
              className="h-11 min-w-0 flex-1 cursor-pointer appearance-none bg-transparent
                [&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-transparent
                [&::-webkit-slider-thumb]:-mt-[7px] [&::-webkit-slider-thumb]:size-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-accent [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-sm [&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:duration-[var(--duration-fast)] hover:[&::-webkit-slider-thumb]:scale-110 active:[&::-webkit-slider-thumb]:scale-125
                [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:bg-transparent [&::-moz-range-thumb]:size-5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border [&::-moz-range-thumb]:border-accent [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:shadow-sm [&::-moz-range-thumb]:transition-transform [&::-moz-range-thumb]:duration-[var(--duration-fast)] hover:[&::-moz-range-thumb]:scale-110 active:[&::-moz-range-thumb]:scale-125 motion-reduce:[&::-webkit-slider-thumb]:transition-none motion-reduce:[&::-moz-range-thumb]:transition-none"
              aria-label={t(plan.label)} />
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {[20, 25, 40, 80, 120].filter((n) => n <= Math.min(200, effectiveMaxPosts)).map((n) => (
                <button key={n} type="button" onClick={() => set("count", n)} aria-pressed={f.count === n}
                  className="interactive-tap relative isolate min-h-11 min-w-11 rounded-full px-2 py-1 font-mono text-xs text-ink-soft hover:text-ink aria-pressed:text-primary-ink before:absolute before:inset-x-1 before:inset-y-1.5 before:-z-10 before:rounded-full hover:before:bg-sunken aria-pressed:before:bg-primary">
                  {formatNumber(n, lang)}
                </button>
              ))}
            </div>
            {(nSources > 1 || f.count * nSources > plan.cap) && (
              <p className="mt-1 text-sm text-ink-soft">
                {t("cmp.total", { total, n: nSources })}
                {f.count * nSources > plan.cap && t("cmp.cap", { max: plan.cap })}.
                {f.count * nSources > plan.cap && <span className="mt-1 block">{t("cmp.effectivePerSource", {
                  max: plan.cap, range: plan.minPerSource === plan.maxPerSource ? formatNumber(plan.minPerSource, lang)
                    : `${formatNumber(plan.minPerSource, lang)}–${formatNumber(plan.maxPerSource, lang)}`,
                })}</span>}
              </p>
            )}
          </Group>

          <Group label={t("cmp.speed")}>
            <SegmentedControl compact label={t("cmp.speed")} value={f.speed} onChange={(v) => set("speed", v as RunRequest["speed"])}
              options={[{ value: "fast", label: t("cmp.fast") }, { value: "careful", label: t("cmp.careful") }]} />
            <p className="mt-2 text-sm text-ink-soft">
              {f.speed === "fast" ? t("cmp.fastHint") : t("cmp.carefulHint")}
            </p>
          </Group>

          <Group label={t("cmp.ai")}>
            {providers === null ? (
              <div role="status" aria-label={t("act.loading")}><div aria-hidden="true"><Skeleton height={40} /></div></div>
            ) : (
              <>
                <Select aria-label={t("cmp.ai")} value={f.ai_provider}
                  onChange={(e) => { set("ai_provider", e.target.value); set("ai_model", ""); }}>
                  {usable.map((p) => <option key={p.key} value={p.key}>{p.key === "offline" ? t("cmp.offline") : p.name}</option>)}
                </Select>
                {f.ai_provider !== "offline" && (
                  <ModelPicker key={f.ai_provider} provider={f.ai_provider} value={f.ai_model} onChange={(m) => set("ai_model", m)} />
                )}
                {usable.length === 1 && (
                  <p className="mt-2 text-sm text-ink-soft">
                    {t("cmp.noKeys")}{" "}
                    <button type="button" onClick={() => onOpenSettings()} className="font-medium text-link hover:underline">
                      {t("cmp.addKey")}
                    </button>
                  </p>
                )}
              </>
            )}
          </Group>

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
                  <textarea aria-label={t(jobProfile ? "profile.notes" : "cmp.profile")} className="field resize-y" rows={3} value={f.profile} onChange={(e) => set("profile", e.target.value)}
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
              <textarea aria-label={t(jobProfile ? "profile.notes" : "cmp.profile")} className="field resize-y" rows={2} value={f.profile} onChange={(e) => set("profile", e.target.value)}
                placeholder={t(jobProfile ? "profile.notesPh" : "cmp.profilePh")} />
              <span className="mt-1 block text-xs text-ink-soft">{t(jobProfile ? "profile.notesHint" : "cmp.profileHint")}</span>
            </label>
          </section>}

          <Group label={t("cmp.options")}>
            <Toggle checked={f.only_new} onChange={(v) => set("only_new", v)}>{t("cmp.onlyNew")}</Toggle>
            {!serverMode && <Toggle checked={!f.headless} onChange={(v) => set("headless", !v)}>{t("cmp.showBrowser")}</Toggle>}
            {!serverMode && f.headless && (
              <p className="text-sm text-ink-soft">{t("cmp.headlessHint")}</p>
            )}
          </Group>
    </Sheet>
  );
}

export function ModelPicker({ provider, value, onChange }: { provider: string; value: string; onChange: (m: string) => void }) {
  const [models, setModels] = useState<string[]>([]);
  const [def, setDef] = useState("");
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");
  const { t } = useI18n();
  const requestId = useRef(0);

  const load = (refresh = false) => {
    const id = ++requestId.current;
    setState("loading");
    api.models(provider, refresh)
      .then((r) => { if (id !== requestId.current) return; setModels(r.models); setDef(r.default); setState("ok"); })
      .catch((e) => { if (id !== requestId.current) return; setError((e as Error).message); setState("error"); });
  };
  useEffect(() => { load(); return () => { ++requestId.current; }; }, [provider]);

  return (
    <div className="mt-2 flex gap-2">
      <Select value={value} onChange={(e) => onChange(e.target.value)}
        disabled={state !== "ok"} aria-label={t("cmp.modelAria")}>
        <option value="">
          {state === "loading" ? t("cmp.modelsLoading") : state === "error" ? error : t("cmp.modelDefault", { m: def })}
        </option>
        {value && !models.includes(value) && <option value={value}>{value}</option>}
        {models.map((m) => <option key={m} value={m}>{m}</option>)}
      </Select>
      <IconButton onClick={() => load(true)} aria-label={t("cmp.reloadModels")} variant="outline" busy={state === "loading"} className="size-11 shrink-0">
        <RefreshCw className="size-4" />
      </IconButton>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-3 text-sm font-semibold tracking-tight">{label}</legend>
      {children}
    </fieldset>
  );
}

function Toggle({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-4 py-2 text-sm">
      <span>{children}</span>
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span aria-hidden className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-primary peer-focus-visible:outline-2 peer-focus-visible:outline-accent
        after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition-transform after:duration-[var(--duration-fast)] motion-reduce:after:transition-none peer-checked:after:translate-x-4" />
    </label>
  );
}
