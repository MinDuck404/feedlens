import { Briefcase, Check, Loader2, RefreshCw, Trash2, X as XIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import type {
  AIProviderInfo, Me, Meta, Platform, PlatformSession, PlatformState, Preferences, RunRequest, SavedGroup, SourceType,
} from "../types";

const SOURCE_HINT: Record<Platform, Record<Exclude<SourceType, "feed">, { label: string; ph: string }>> = {
  facebook: {
    group: { label: "Thêm nhóm", ph: "https://www.facebook.com/groups/vieclamit\nhttps://www.facebook.com/groups/123456789" },
    search: { label: "Từ khóa", ph: "tuyển python\nvieclamit | remote react" },
  },
  linkedin: {
    group: { label: "Thêm nhóm", ph: "https://www.linkedin.com/groups/123456/" },
    search: { label: "Từ khóa", ph: "hiring python vietnam" },
  },
  x: {
    group: { label: "Thêm tài khoản hoặc list", ph: "@vercel\nhttps://x.com/i/lists/123" },
    search: { label: "Từ khóa hoặc hashtag", ph: "#hiring remote" },
  },
  reddit: {
    group: { label: "Thêm subreddit", ph: "forhire\nvietnam" },
    search: { label: "Từ khóa", ph: "python job remote" },
  },
};

const DEFAULTS: RunRequest = {
  platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false, keywords: [], profile: "",
  ai_provider: "offline", ai_model: "", only_new: false, headless: false, speed: "fast", runner: "agent",
};

const lines = (t: string) => t.split("\n").map((s) => s.trim()).filter(Boolean);
/** Link dán vào ô một dòng: tách theo dấu cách, xuống dòng hoặc dấu phẩy */
const links = (t: string) => t.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);

/** Tên dễ đọc từ link nhóm: facebook.com/groups/viec-lam-it -> "viec lam it" */
function groupName(url: string): string {
  const slug = url.replace(/\/$/, "").split(/groups\/|\/r\/|x\.com\//).pop() ?? url;
  return decodeURIComponent(slug.split(/[/?#]/)[0]).replace(/[-_.]+/g, " ").trim() || url;
}

const KEYWORD_SUGGESTIONS = ["remote", "junior", "senior", "intern", "part-time", "Hà Nội", "HCM", "Đà Nẵng"];

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
  const saved = prefs.composer ?? {};
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

  // Tải một lần khi mở form (không chạy lại khi App cập nhật, để không ghi đè lựa chọn đang chỉnh)
  useEffect(() => {
    if (cloud && meta.server_scrape) api.sessions().then(setSessions).catch(() => {});
    api.providers().then((list) => {
      setProviders(list);
      const ok = (k?: string) => !!k && list.some((p) => p.key === k && p.configured);
      const first = list.find((p) => p.configured && p.key !== "offline")?.key ?? "offline";
      setF((s) => ({ ...s, ai_provider: ok(saved.ai_provider) ? saved.ai_provider! : first,
                     ai_model: ok(saved.ai_provider) ? saved.ai_model ?? "" : "" }));
    });
  }, []);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const snapshot = (next: Partial<Preferences> = {}): Preferences => ({
    composer: { ...f, sources: undefined, keywords: undefined, keywords_text: keywordsText },
    groups, searches, ...next,
  });

  /** Lưu cài đặt vào tài khoản (không chặn giao diện nếu lỗi mạng). */
  const persist = (next: Partial<Preferences>) => {
    const p = snapshot(next);
    lastSaved.current = JSON.stringify(p);
    onPrefsChange(p);
    api.savePreferences(p).catch(() => {});
  };

  // Đóng form (nút X, Esc, bấm ra ngoài) cũng lưu lại những gì vừa chỉnh
  const latest = useRef(snapshot());
  latest.current = snapshot();
  const lastSaved = useRef(JSON.stringify(prefs));
  useEffect(() => () => {
    const json = JSON.stringify(latest.current);
    if (json !== lastSaved.current) {
      onPrefsChange(latest.current);
      api.savePreferences(latest.current).catch(() => {});
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
      setError(myGroups.length ? "Chọn ít nhất một nhóm để lướt." : "Thêm ít nhất một link nhóm.");
      return;
    }
    setSending(true);
    try {
      const { id } = await api.createRun({ ...f, sources, keywords: keywordsText.split(",").map((s) => s.trim()).filter(Boolean) });
      persist({});
      onCreated(id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-ink/30" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} role="dialog" aria-label="Lướt mới"
        className="sheet flex h-full w-full max-w-md flex-col bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-lg font-semibold">Lướt mới</h2>
          <button type="button" onClick={onClose} aria-label="Đóng" className="rounded-md p-1 text-ink-soft hover:bg-sunken">
            <XIcon className="size-5" />
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-x-hidden overflow-y-auto px-6 py-5">
          {cloud && meta.server_scrape && (
            <Group label="Chạy bằng">
              <Segmented value={f.runner} onChange={(v) => set("runner", v as RunRequest["runner"])}
                options={[{ value: "agent", label: "Agent trên máy" }, { value: "server", label: "Server (cookie)" }]} />
              <p className="mt-2 text-sm text-ink-soft">
                {f.runner === "agent"
                  ? "Agent mở Chrome trên máy bạn bằng phiên đăng nhập và IP nhà. An toàn nhất cho tài khoản."
                  : "Server tự lướt bằng cookie đã lưu, không cần bật agent. Dễ bị nền tảng bắt xác minh hoặc khóa tài khoản."}
              </p>
            </Group>
          )}

          <Group label="Nền tảng">
            <Segmented value={f.platform} onChange={(v) => set("platform", v as Platform)} options={platformOptions} />
            {!cloud && platformState && !platformState.has_profile && (
              <p className="mt-2 text-sm text-ink-soft">
                Bạn chưa đăng nhập {platformState.name}. Đăng nhập ở cột bên trái trước, nếu không bot chỉ thấy nội dung công khai.
              </p>
            )}
          </Group>

          <Group label="Lướt ở đâu">
            <Segmented value={f.source_type} onChange={(v) => set("source_type", v as SourceType)}
              options={[{ value: "feed", label: "Bảng tin" }, { value: "group", label: "Nhóm" }, { value: "search", label: "Tìm kiếm" }]} />

            {f.source_type === "group" && hint && (
              <div className="mt-3">
                {myGroups.length > 0 && (
                  <>
                    <div className="mb-2 flex items-center justify-between text-sm">
                      <span><span className="font-mono">{sources.length}/{myGroups.length}</span> nhóm sẽ lướt</span>
                      <button type="button" className="text-link hover:underline"
                        onClick={() => updateGroups(myGroups.map((g) => ({ ...g, enabled: sources.length < myGroups.length })))}>
                        {sources.length < myGroups.length ? "Chọn tất cả" : "Bỏ chọn tất cả"}
                      </button>
                    </div>
                    <ul className="paper-card max-h-60 divide-y divide-line overflow-y-auto rounded-2xl">
                      {myGroups.map((g, i) => {
                        const name = groupName(g.url);
                        return (
                          <li key={g.url} className="group/row flex items-center">
                            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 py-2.5">
                              <input type="checkbox" className="peer sr-only" checked={g.enabled}
                                onChange={(e) => updateGroups(myGroups.map((x, j) => j === i ? { ...x, enabled: e.target.checked } : x))} />
                              <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-sunken font-mono text-xs uppercase text-ink-soft
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
                            <button type="button" aria-label={`Xóa ${name} khỏi danh sách`} title="Xóa khỏi danh sách"
                              onClick={() => updateGroups(myGroups.filter((_, j) => j !== i))}
                              className="mr-2 grid size-7 place-items-center rounded-full text-ink-soft opacity-0 hover:bg-sunken hover:text-danger focus:opacity-100 group-hover/row:opacity-100">
                              <Trash2 className="size-3.5" />
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}
                <div className="mt-3 flex items-center gap-2 rounded-full border border-line bg-surface py-1 pr-1 pl-4 focus-within:outline-2 focus-within:outline-accent">
                  <input className="min-w-0 flex-1 bg-transparent py-1.5 text-sm outline-none placeholder:text-ink-soft/70"
                    placeholder={myGroups.length ? "Dán thêm link nhóm…" : hint.ph.split("\n")[0]}
                    value={newGroups} onChange={(e) => setNewGroups(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addGroups(); } }}
                    aria-label={hint.label} />
                  <button type="button" onClick={addGroups} disabled={!links(newGroups).length}
                    className="rounded-full bg-primary px-4 py-1.5 text-sm font-medium text-primary-ink disabled:opacity-40">
                    Thêm
                  </button>
                </div>
                <p className="mt-1.5 px-1 text-xs text-ink-soft">Dán một hoặc nhiều link (cách nhau bằng dấu cách) rồi Enter. Danh sách được lưu cho lần sau.</p>
              </div>
            )}

            {f.source_type === "search" && hint && (
              <label className="mt-3 block">
                <span className="mb-1 block text-sm">{hint.label}, mỗi dòng một mục</span>
                <textarea className="field" rows={3} placeholder={hint.ph} value={searchText}
                  onChange={(e) => setSearches({ ...searches, [f.platform]: e.target.value })} />
              </label>
            )}
          </Group>

          <Group label={f.source_type === "feed" ? `Số bài: ${f.count}` : `Số bài mỗi ${f.source_type === "group" ? "nhóm" : "từ khóa"}: ${f.count}`}>
            <input type="range" min={10} max={Math.min(200, meta.max_posts)} step={10} value={f.count}
              onChange={(e) => set("count", Number(e.target.value))}
              className="w-full accent-[var(--accent)]" aria-label="Số bài" />
            {nSources > 1 && (
              <p className="mt-1 text-sm text-ink-soft">
                Tổng tối đa {total} bài từ {nSources} {f.source_type === "group" ? "nhóm" : "từ khóa"}
                {f.count * nSources > meta.max_posts && ` (giới hạn ${meta.max_posts} bài mỗi lượt)`}.
              </p>
            )}
          </Group>

          <Group label="Tốc độ lướt">
            <Segmented value={f.speed} onChange={(v) => set("speed", v as RunRequest["speed"])}
              options={[{ value: "fast", label: "Nhanh" }, { value: "careful", label: "Cẩn thận" }]} />
            <p className="mt-2 text-sm text-ink-soft">
              {f.speed === "fast" ? "Cuộn nhanh, nghỉ ngắn. Lướt nhiều mỗi ngày thì nên chọn Cẩn thận."
                : "Cuộn chậm và nghỉ lâu như người thật đọc, ít bị nền tảng nghi ngờ hơn."}
            </p>
          </Group>

          <Group label="AI đọc bài">
            {providers === null ? (
              <p className="text-sm text-ink-soft">Đang tải…</p>
            ) : (
              <>
                <select className="field" value={f.ai_provider}
                  onChange={(e) => { set("ai_provider", e.target.value); set("ai_model", ""); }}>
                  {usable.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                </select>
                {f.ai_provider !== "offline" && (
                  <ModelPicker provider={f.ai_provider} value={f.ai_model} onChange={(m) => set("ai_model", m)} />
                )}
                {usable.length === 1 && (
                  <p className="mt-2 text-sm text-ink-soft">
                    Chưa có API key nào nên chỉ dùng được bộ lọc từ khóa.{" "}
                    <button type="button" onClick={onOpenSettings} className="font-medium text-link hover:underline">
                      Thêm key Gemini, ChatGPT hoặc Claude
                    </button>
                  </p>
                )}
              </>
            )}
          </Group>

          <section className={`rounded-2xl border p-4 transition-colors ${f.job_mode ? "border-ink bg-surface" : "border-line"}`}>
            <label className="flex cursor-pointer items-start gap-3">
              <span className={`grid size-9 shrink-0 place-items-center rounded-full ${f.job_mode ? "bg-primary text-primary-ink" : "bg-sunken text-ink-soft"}`}>
                <Briefcase className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">Tìm việc</span>
                <span className="block text-sm text-ink-soft">Trích vị trí, lương, liên hệ và chấm điểm độ hợp với bạn.</span>
              </span>
              <input type="checkbox" className="peer sr-only" checked={f.job_mode} onChange={(e) => set("job_mode", e.target.checked)} />
              <span aria-hidden className="relative mt-1 h-5 w-9 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-primary peer-focus-visible:outline-2 peer-focus-visible:outline-accent
                after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition-transform peer-checked:after:translate-x-4" />
            </label>
            {f.job_mode && (
              <div className="mt-4 space-y-4">
                <div>
                  <span className="mb-1.5 block text-sm font-medium">Từ khóa</span>
                  <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-line bg-surface p-2 focus-within:outline-2 focus-within:outline-accent">
                    {keywords.map((k) => (
                      <span key={k} className="flex items-center gap-1 rounded-full bg-primary py-1 pr-1 pl-3 text-xs text-primary-ink">
                        {k}
                        <button type="button" aria-label={`Bỏ từ khóa ${k}`} onClick={() => setKeywords(keywords.filter((x) => x !== k))}
                          className="grid size-4 place-items-center rounded-full hover:bg-primary-ink/20"><XIcon className="size-3" /></button>
                      </span>
                    ))}
                    <input className="min-w-24 flex-1 bg-transparent px-1 py-1 text-sm outline-none placeholder:text-ink-soft/70"
                      placeholder={keywords.length ? "Thêm…" : "python, react, kế toán…"} value={kwDraft}
                      onChange={(e) => setKwDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if ((e.key === "Enter" || e.key === ",") && kwDraft.trim()) { e.preventDefault(); addKeyword(kwDraft); }
                        if (e.key === "Backspace" && !kwDraft && keywords.length) setKeywords(keywords.slice(0, -1));
                      }}
                      onBlur={() => kwDraft.trim() && addKeyword(kwDraft)} aria-label="Thêm từ khóa" />
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {KEYWORD_SUGGESTIONS.filter((s) => !keywords.includes(s)).map((s) => (
                      <button key={s} type="button" onClick={() => addKeyword(s)}
                        className="rounded-full border border-dashed border-line px-2.5 py-0.5 text-xs text-ink-soft hover:border-ink hover:text-ink">
                        + {s}
                      </button>
                    ))}
                  </div>
                </div>
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium">Vài dòng về bạn</span>
                  <textarea className="field" rows={3} value={f.profile} onChange={(e) => set("profile", e.target.value)}
                    placeholder="2 năm Python/Django, muốn làm remote, kỳ vọng 20–30 triệu, ở Hà Nội" />
                  <span className="mt-1 block text-xs text-ink-soft">AI dùng đoạn này để chấm điểm từng việc từ 0 đến 100.</span>
                </label>
              </div>
            )}
          </section>

          <Group label="Tùy chọn">
            <Toggle checked={f.only_new} onChange={(v) => set("only_new", v)}>Bỏ qua bài đã thấy ở lượt trước</Toggle>
            {!serverMode && <Toggle checked={!f.headless} onChange={(v) => set("headless", !v)}>Hiện cửa sổ trình duyệt khi lướt</Toggle>}
            {!serverMode && f.headless && (
              <p className="text-sm text-ink-soft">Chạy ẩn thì không xác minh 2 bước được; nếu nền tảng hỏi xác minh, lượt sẽ dừng và báo lỗi.</p>
            )}
          </Group>
        </div>

        <footer className="border-t border-line px-6 py-4">
          {serverMode && (!session || session.status === "invalid") && (
            <p className="mb-3 text-sm text-danger">
              {session ? `Cookie ${PLATFORM_LABEL[f.platform]} đã hết hiệu lực. ` : `Chưa có cookie ${PLATFORM_LABEL[f.platform]} trên server. `}
              <button type="button" onClick={onOpenSettings} className="font-medium text-link hover:underline">
                {session ? "Gửi cookie mới" : "Thêm cookie"}
              </button>
            </p>
          )}
          {!serverMode && cloud && me && !me.agent.online && (
            <p className="mb-3 text-sm text-ink-soft">
              Agent trên máy bạn đang tắt. Lượt sẽ chờ và tự chạy khi agent bật.{" "}
              <button type="button" onClick={onOpenSettings} className="font-medium text-link hover:underline">
                {me.agent.has_token ? "Xem cách bật" : "Kết nối agent"}
              </button>
            </p>
          )}
          {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
          <button disabled={sending}
            className="w-full rounded-full bg-primary py-2.5 font-semibold text-primary-ink hover:opacity-90 disabled:opacity-50">
            {sending ? "Đang bắt đầu…" : "Bắt đầu lướt"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function ModelPicker({ provider, value, onChange }: { provider: string; value: string; onChange: (m: string) => void }) {
  const [models, setModels] = useState<string[]>([]);
  const [def, setDef] = useState("");
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");

  const load = (refresh = false) => {
    setState("loading");
    api.models(provider, refresh)
      .then((r) => { setModels(r.models); setDef(r.default); setState("ok"); })
      .catch((e) => { setError((e as Error).message); setState("error"); });
  };
  useEffect(() => { load(); }, [provider]);

  return (
    <div className="mt-2 flex gap-2">
      <select className="field" value={value} onChange={(e) => onChange(e.target.value)}
        disabled={state !== "ok"} aria-label="Model">
        <option value="">
          {state === "loading" ? "Đang lấy danh sách model…" : state === "error" ? error : `Mặc định (${def})`}
        </option>
        {value && !models.includes(value) && <option value={value}>{value}</option>}
        {models.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
      <button type="button" onClick={() => load(true)} title="Tải lại danh sách model" aria-label="Tải lại danh sách model"
        className="grid w-10 shrink-0 place-items-center rounded-lg border border-line text-ink-soft hover:text-ink">
        {state === "loading" ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
      </button>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold">{label}</legend>
      {children}
    </fieldset>
  );
}

function Segmented({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <div className="flex rounded-full border border-line bg-sunken p-1" role="radiogroup">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className="flex-1 rounded-full px-2 py-1.5 text-sm text-ink-soft aria-checked:bg-surface aria-checked:font-semibold aria-checked:text-ink aria-checked:shadow-sm">
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 py-1 text-sm">
      <span>{children}</span>
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span aria-hidden className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-primary peer-focus-visible:outline-2 peer-focus-visible:outline-accent
        after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition-transform peer-checked:after:translate-x-4" />
    </label>
  );
}
