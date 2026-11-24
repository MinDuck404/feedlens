import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { PLATFORM_LABEL } from "../../lib/categories";
import { formatNumber, useI18n } from "../../i18n";
import { Sheet, Button, Skeleton, Select, SegmentedControl } from "../../components/ui";
import { Group, Toggle } from "./Controls";
import { AIKeyPicker } from "./AIKeyPicker";
import { JobCriteria } from "./JobCriteria";
import { links, SourceMode } from "./SourceMode";
import { applyJobProfileDefaults, countPlan, defaultDraft, defaultMode, draftFromRequest, draftKey, inferMode,
  migratePreferences, modeDefinition, serializeDraft, sourceLines, validateDraft, type ModeDraft, type ModePreferences } from "../../lib/platformModes";
import type {
  AIProviderInfo, JobProfile, Me, Meta, Mode, ModeOptions, Platform, PlatformSession, PlatformState, Preferences, RunRequest, SavedGroup,
} from "../../api/types";

const DEFAULTS: RunRequest = {
  platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false, keywords: [], profile: "",
  ai_provider: "offline", ai_model: "", ai_key_id: null, only_new: false, headless: false, speed: "fast", runner: "agent",
};

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
      const selected = (ok(saved.ai_provider) ? saved.ai_provider! : preferred) ?? first;
      setF((s) => ({ ...s, ai_provider: selected,
                     ai_model: selected === saved.ai_provider ? saved.ai_model ?? "" : "",
                     ai_key_id: selected === saved.ai_provider && selected !== "offline" ? saved.ai_key_id ?? null : null }));
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

          <SourceMode f={f} mode={mode} definition={definition} usesSaved={usesSaved} myGroups={myGroups} sources={sources}
            newGroups={newGroups} setNewGroups={setNewGroups} updateGroups={updateGroups} addGroups={addGroups}
            sourceText={sourceText} setSourceText={setSourceText} draft={draft} setOption={setOption} changeMode={changeMode} jobProfile={jobProfile} />

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
                  onChange={(e) => { set("ai_provider", e.target.value); set("ai_model", ""); set("ai_key_id", null); }}>
                  {usable.map((p) => <option key={p.key} value={p.key}>{p.key === "offline" ? t("cmp.offline") : p.key === "custom" ? t("set.customProvider") : p.name}</option>)}
                </Select>
                {f.ai_provider !== "offline" && (
                  <AIKeyPicker key={f.ai_provider} provider={f.ai_provider} providerInfo={providers.find((p) => p.key === f.ai_provider)} keyId={f.ai_key_id ?? null} model={f.ai_model}
                    onChange={(ai_key_id, ai_model) => setF((old) => ({ ...old, ai_key_id, ai_model }))} />
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

          <JobCriteria mode={mode} f={f} set={set} keywords={keywords} setKeywords={setKeywords} kwDraft={kwDraft}
            setKwDraft={setKwDraft} addKeyword={addKeyword} jobProfile={jobProfile} onOpenSettings={onOpenSettings} />

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
