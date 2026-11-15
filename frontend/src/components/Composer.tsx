import { Briefcase, Check, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { groupName } from "../logic";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { formatNumber, useI18n, type Key } from "../i18n";
import { Sheet, Button, IconButton, Skeleton, Select, SegmentedControl } from "./ui";
import type {
  AIProviderInfo, JobProfile, Me, Meta, Platform, PlatformSession, PlatformState, Preferences, RunRequest, SavedGroup, SourceType,
} from "../types";

const SOURCE_HINT: Record<Platform, Record<Exclude<SourceType, "feed">, { label: Key; ph: string; phKey?: Key }>> = {
  facebook: {
    group: { label: "cmp.addGroup", ph: "https://www.facebook.com/groups/vieclamit\nhttps://www.facebook.com/groups/123456789" },
    search: { label: "cmp.keywords", ph: "", phKey: "cmp.searchFacebook" },
  },
  linkedin: {
    group: { label: "cmp.addGroup", ph: "https://www.linkedin.com/groups/123456/" },
    search: { label: "cmp.keywords", ph: "", phKey: "cmp.searchLinkedin" },
  },
  x: {
    group: { label: "cmp.addAccount", ph: "@vercel\nhttps://x.com/i/lists/123" },
    search: { label: "cmp.keywordsOrTags", ph: "", phKey: "cmp.searchX" },
  },
  reddit: {
    group: { label: "cmp.addSubreddit", ph: "forhire\nvietnam" },
    search: { label: "cmp.keywords", ph: "", phKey: "cmp.searchReddit" },
  },
};

const DEFAULTS: RunRequest = {
  platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false, keywords: [], profile: "",
  ai_provider: "offline", ai_model: "", only_new: false, headless: false, speed: "fast", runner: "agent",
};

const lines = (t: string) => t.split("\n").map((s) => s.trim()).filter(Boolean);
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
  onOpenSettings: () => void;
}

export default function Composer({ meta, me, platforms, prefs, onPrefsChange, onClose, onCreated, onOpenSettings }: Props) {
  const [open, setOpen] = useState(true);
  const handleClose = useCallback(() => {
    setOpen(false);
    setTimeout(onClose, 200);
  }, [onClose]);

  const saved = prefs.composer ?? {};
  const { t, lang } = useI18n();
  const [jobProfile, setJobProfile] = useState<JobProfile | null>(null);
  const [providers, setProviders] = useState<AIProviderInfo[] | null>(null);
  const [sessions, setSessions] = useState<PlatformSession[]>([]);
  const [f, setF] = useState<RunRequest>({ ...DEFAULTS, ...saved, sources: [], keywords: [] });
  const [groups, setGroups] = useState(prefs.groups ?? {});
  const [searches, setSearches] = useState(prefs.searches ?? {});
  const [newGroups, setNewGroups] = useState("");
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
  const hint = f.source_type !== "feed" ? SOURCE_HINT[f.platform][f.source_type] : null;
  const usable = (providers ?? []).filter((p) => p.configured);
  const myGroups: SavedGroup[] = groups[f.platform] ?? [];
  const searchText = searches[f.platform] ?? "";
  const sources = f.source_type === "group" ? myGroups.filter((g) => g.enabled).map((g) => g.url)
    : f.source_type === "search" ? lines(searchText) : [];
  const nSources = f.source_type === "feed" ? 1 : Math.max(1, sources.length);
  const total = Math.min(f.count * nSources, meta.max_posts);

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
  useEffect(() => { loadProviders(); api.profile().then(setJobProfile).catch((e) => setLoadError(e.message)); }, []);

  const snapshot = (next: Partial<Preferences> = {}): Preferences => ({
    composer: { ...f, sources: undefined, keywords: undefined, keywords_text: keywordsText },
    groups, searches, ...next,
  });

  /** Lưu cài đặt vào tài khoản (không chặn giao diện nếu lỗi mạng). */
  const persist = (next: Partial<Preferences>) => {
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
    const next = { ...groups, [f.platform]: list };
    setGroups(next);
    persist({ groups: next });
  };
  const addGroups = () => {
    const known = new Set(myGroups.map((g) => g.url.replace(/\/$/, "")));
    const added: SavedGroup[] = [];
    for (const raw of links(newGroups)) {
      const url = raw.replace(/\/$/, "");
      if (!known.has(url)) { known.add(url); added.push({ url, enabled: true }); }
    }
    if (added.length) updateGroups([...myGroups, ...added]);
    setNewGroups("");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (f.source_type === "group" && !sources.length) {
      setError(myGroups.length ? t("cmp.pickGroup") : t("cmp.addGroupFirst"));
      return;
    }
    setSending(true);
    try {
      const { id } = await api.createRun({ ...f, sources, language: lang, keywords: keywordsText.split(",").map((s) => s.trim()).filter(Boolean) });
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
          <button type="button" onClick={onOpenSettings} className="font-medium text-link hover:underline">
            {session ? t("cmp.sendCookie") : t("cmp.addCookie")}
          </button>
        </p>
      )}
      {!serverMode && cloud && me && !me.agent.online && (
        <p className="mb-3 text-sm text-ink-soft">
          {t("cmp.agentOff")}{" "}
          <button type="button" onClick={onOpenSettings} className="font-medium text-link hover:underline">
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
            <SegmentedControl compact label={t("cmp.platform")} value={f.platform} onChange={(v) => set("platform", v as Platform)} options={platformOptions} />
            {!cloud && platformState && !platformState.has_profile && (
              <p className="mt-2 text-sm text-ink-soft">
                {t("cmp.notLoggedIn", { name: platformState.name })}
              </p>
            )}
          </Group>

          <Group label={t("cmp.where")}>
            <SegmentedControl compact label={t("cmp.where")} value={f.source_type} onChange={(v) => set("source_type", v as SourceType)}
              options={[{ value: "feed", label: t("cmp.feed") }, { value: "group", label: t("cmp.groups") }, { value: "search", label: t("cmp.search") }]} />

            {f.source_type === "group" && hint && (
              <div className="mt-3">
                {myGroups.length > 0 && (
                  <>
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span>{t("cmp.groupsSelectedCount", { selected: sources.length, total: myGroups.length })}</span>
                      <button type="button" className="interactive-tap min-h-10 text-link underline-offset-4 hover:underline"
                        onClick={() => updateGroups(myGroups.map((g) => ({ ...g, enabled: sources.length < myGroups.length })))}>
                        {sources.length < myGroups.length ? t("cmp.selectAll") : t("cmp.selectNone")}
                      </button>
                    </div>
                    <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded-card border border-line">
                      {myGroups.map((g, i) => {
                        const name = groupName(g.url);
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
                <div className="mt-3 flex items-center gap-2 rounded-full border border-[var(--field-line)] bg-[var(--field-bg)] py-1 pr-1 pl-4 transition-[border-color,box-shadow] duration-[var(--duration-fast)] focus-within:border-accent focus-within:shadow-[0_0_0_2px_var(--accent-glow)]">
                  <input className="min-w-0 flex-1 bg-transparent py-1.5 text-sm border-0! outline-none! ring-0! [box-shadow:none]! focus-visible:outline-none! placeholder:text-ink-soft/70"
                    placeholder={myGroups.length ? t("cmp.pasteMore") : hint.ph.split("\n")[0]}
                    value={newGroups} onChange={(e) => setNewGroups(e.target.value)}
                    onKeyDown={(e) => { if (!e.nativeEvent.isComposing && e.key === "Enter") { e.preventDefault(); addGroups(); } }}
                    aria-label={t(hint.label)} />
                  <Button onClick={addGroups} disabled={!links(newGroups).length} variant="secondary" className="shrink-0 border-0! shadow-none! focus-visible:outline-none!">
                    {t("cmp.add")}
                  </Button>
                </div>
                <p className="mt-1.5 px-1 text-xs text-ink-soft">{t("cmp.addHint")}</p>
              </div>
            )}

            {f.source_type === "search" && hint && (
              <label className="mt-3 block">
                <span className="mb-1 block text-sm">{t("cmp.onePerLine", { label: t(hint.label) })}</span>
                <textarea className="field resize-y" rows={3} placeholder={hint.phKey ? t(hint.phKey) : hint.ph} value={searchText}
                  onChange={(e) => setSearches({ ...searches, [f.platform]: e.target.value })} />
              </label>
            )}
          </Group>

          <Group label={t(f.source_type === "feed" ? "cmp.countLabel" : f.source_type === "group" ? "cmp.countPerGroupLabel" : "cmp.countPerKeywordLabel")}>
            <div className="flex items-center gap-4">
            <output className="min-w-12 text-right font-mono text-3xl font-medium tabular-nums" aria-hidden="true">{formatNumber(f.count, lang)}</output>
            <input type="range" min={10} max={Math.min(200, meta.max_posts)} step={10} value={f.count}
              onChange={(e) => set("count", Number(e.target.value))}
              style={{ backgroundImage: `linear-gradient(to right, var(--accent) ${100 * (f.count - 10) / Math.max(1, Math.min(200, meta.max_posts) - 10)}%, color-mix(in srgb, var(--ink) 35%, var(--sheet)) ${100 * (f.count - 10) / Math.max(1, Math.min(200, meta.max_posts) - 10)}%)`, backgroundSize: "100% 6px", backgroundPosition: "center", backgroundRepeat: "no-repeat" }}
              className="h-11 min-w-0 flex-1 cursor-pointer appearance-none bg-transparent
                [&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-transparent
                [&::-webkit-slider-thumb]:-mt-[7px] [&::-webkit-slider-thumb]:size-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-accent [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-sm [&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:duration-[var(--duration-fast)] hover:[&::-webkit-slider-thumb]:scale-110 active:[&::-webkit-slider-thumb]:scale-125
                [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:bg-transparent [&::-moz-range-thumb]:size-5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border [&::-moz-range-thumb]:border-accent [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:shadow-sm [&::-moz-range-thumb]:transition-transform [&::-moz-range-thumb]:duration-[var(--duration-fast)] hover:[&::-moz-range-thumb]:scale-110 active:[&::-moz-range-thumb]:scale-125 motion-reduce:[&::-webkit-slider-thumb]:transition-none motion-reduce:[&::-moz-range-thumb]:transition-none"
              aria-label={t("cmp.countAria")} />
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {[20, 40, 80, 120].filter((n) => n <= Math.min(200, meta.max_posts)).map((n) => (
                <button key={n} type="button" onClick={() => set("count", n)} aria-pressed={f.count === n}
                  className="interactive-tap relative isolate min-h-11 min-w-11 rounded-full px-2 py-1 font-mono text-xs text-ink-soft hover:text-ink aria-pressed:text-primary-ink before:absolute before:inset-x-1 before:inset-y-1.5 before:-z-10 before:rounded-full hover:before:bg-sunken aria-pressed:before:bg-primary">
                  {formatNumber(n, lang)}
                </button>
              ))}
            </div>
            {nSources > 1 && (
              <p className="mt-1 text-sm text-ink-soft">
                {t("cmp.total", { total, n: nSources })}
                {f.count * nSources > meta.max_posts && t("cmp.cap", { max: meta.max_posts })}.
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
                    <button type="button" onClick={onOpenSettings} className="font-medium text-link hover:underline">
                      {t("cmp.addKey")}
                    </button>
                  </p>
                )}
              </>
            )}
          </Group>

          <section className={`rounded-card border p-4 transition-colors duration-[var(--duration-fast)] ${f.job_mode ? "border-ink bg-surface" : "border-line"}`}>
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
                {jobProfile && <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-y border-line py-3 text-sm"><span>{t("profile.using", { role: jobProfile.primary_roles.join(", ") || t("profile.title") })}</span><button type="button" onClick={onOpenSettings} className="shrink-0 text-link underline underline-offset-4">{t("profile.edit")}</button></p>}
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium">{t(jobProfile ? "profile.notes" : "cmp.profile")}</span>
                  <textarea aria-label={t(jobProfile ? "profile.notes" : "cmp.profile")} className="field resize-y" rows={3} value={f.profile} onChange={(e) => set("profile", e.target.value)}
                    placeholder={t(jobProfile ? "profile.notesPh" : "cmp.profilePh")} />
                  <span className="mt-1 block text-xs text-ink-soft">{t(jobProfile ? "profile.notesHint" : "cmp.profileHint")}</span>
                </label>
              </div>
            )}
          </section>

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
