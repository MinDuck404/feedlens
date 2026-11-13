import { Loader2, RefreshCw, X as XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import type { AIProviderInfo, Me, Meta, Platform, PlatformState, RunRequest, SourceType } from "../types";

const SOURCE_HINT: Record<Platform, Record<Exclude<SourceType, "feed">, { label: string; ph: string }>> = {
  facebook: {
    group: { label: "Group cần lướt", ph: "https://www.facebook.com/groups/vieclamit\n123456789" },
    search: { label: "Từ khóa", ph: "tuyển python\nvieclamit | remote react" },
  },
  linkedin: {
    group: { label: "Group cần lướt", ph: "https://www.linkedin.com/groups/123456/" },
    search: { label: "Từ khóa", ph: "hiring python vietnam" },
  },
  x: {
    group: { label: "Tài khoản hoặc list", ph: "@vercel\nhttps://x.com/i/lists/123" },
    search: { label: "Từ khóa hoặc hashtag", ph: "#hiring remote" },
  },
  reddit: {
    group: { label: "Subreddit", ph: "forhire\nvietnam" },
    search: { label: "Từ khóa", ph: "python job remote" },
  },
};

interface Props {
  meta: Meta;
  me: Me | null;
  platforms: PlatformState[];
  onClose: () => void;
  onCreated: (id: number) => void;
  onOpenSettings: () => void;
}

export default function Composer({ meta, me, platforms, onClose, onCreated, onOpenSettings }: Props) {
  const [providers, setProviders] = useState<AIProviderInfo[] | null>(null);
  const [f, setF] = useState<RunRequest>({
    platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false,
    keywords: [], profile: "", ai_provider: "offline", ai_model: "", only_new: false, headless: false,
  });
  const [sourcesText, setSourcesText] = useState("");
  const [keywordsText, setKeywordsText] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const set = <K extends keyof RunRequest>(k: K, v: RunRequest[K]) => setF((s) => ({ ...s, [k]: v }));

  const cloud = meta.mode === "cloud";
  const platformOptions = platforms.length
    ? platforms.map((p) => ({ value: p.key, label: p.name.replace(" (Twitter)", "") }))
    : Object.entries(PLATFORM_LABEL).map(([value, label]) => ({ value, label }));
  const platformState = platforms.find((p) => p.key === f.platform);
  const hint = f.source_type !== "feed" ? SOURCE_HINT[f.platform][f.source_type] : null;
  const usable = (providers ?? []).filter((p) => p.configured);

  useEffect(() => {
    api.providers().then((list) => {
      setProviders(list);
      const first = list.find((p) => p.configured && p.key !== "offline");
      if (first) set("ai_provider", first.key);
    });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSending(true);
    try {
      const { id } = await api.createRun({
        ...f,
        sources: sourcesText.split("\n").map((s) => s.trim()).filter(Boolean),
        keywords: keywordsText.split(",").map((s) => s.trim()).filter(Boolean),
      });
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

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
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
              options={[{ value: "feed", label: "Bảng tin" }, { value: "group", label: "Group" }, { value: "search", label: "Tìm kiếm" }]} />
            {hint && (
              <label className="mt-3 block">
                <span className="mb-1 block text-sm">{hint.label}, mỗi dòng một mục</span>
                <textarea className="field" rows={3} placeholder={hint.ph} value={sourcesText}
                  onChange={(e) => setSourcesText(e.target.value)} />
              </label>
            )}
          </Group>

          <Group label={`Số bài: ${f.count}`}>
            <input type="range" min={10} max={meta.max_posts} step={10} value={f.count}
              onChange={(e) => set("count", Number(e.target.value))}
              className="w-full accent-[var(--cobalt)]" aria-label="Số bài" />
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
                    <button type="button" onClick={onOpenSettings} className="font-medium text-cobalt hover:underline">
                      Thêm key Gemini, ChatGPT hoặc Claude
                    </button>
                  </p>
                )}
              </>
            )}
          </Group>

          <Group label="Tìm việc">
            <Toggle checked={f.job_mode} onChange={(v) => set("job_mode", v)}>
              Trích việc làm và chấm điểm độ phù hợp
            </Toggle>
            {f.job_mode && (
              <div className="mt-3 space-y-3">
                <label className="block">
                  <span className="mb-1 block text-sm">Từ khóa, ngăn cách bằng dấu phẩy</span>
                  <input className="field" placeholder="python, remote, junior" value={keywordsText}
                    onChange={(e) => setKeywordsText(e.target.value)} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm">Vài dòng về bạn</span>
                  <textarea className="field" rows={3} value={f.profile} onChange={(e) => set("profile", e.target.value)}
                    placeholder="2 năm Python/Django, muốn làm remote, kỳ vọng 20–30 triệu, ở Hà Nội" />
                </label>
              </div>
            )}
          </Group>

          <Group label="Tùy chọn">
            <Toggle checked={f.only_new} onChange={(v) => set("only_new", v)}>Bỏ qua bài đã thấy ở lượt trước</Toggle>
            <Toggle checked={!f.headless} onChange={(v) => set("headless", !v)}>Hiện cửa sổ trình duyệt khi lướt</Toggle>
          </Group>
        </div>

        <footer className="border-t border-line px-6 py-4">
          {cloud && me && !me.agent.online && (
            <p className="mb-3 text-sm text-ink-soft">
              Agent trên máy bạn đang tắt. Lượt sẽ chờ và tự chạy khi agent bật.{" "}
              <button type="button" onClick={onOpenSettings} className="font-medium text-cobalt hover:underline">
                {me.agent.has_token ? "Xem cách bật" : "Kết nối agent"}
              </button>
            </p>
          )}
          {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
          <button disabled={sending}
            className="w-full rounded-lg bg-cobalt py-2.5 font-semibold text-cobalt-ink hover:opacity-90 disabled:opacity-50">
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
    <div className="flex rounded-lg bg-sunken p-1" role="radiogroup">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className="flex-1 rounded-md px-2 py-1.5 text-sm text-ink-soft aria-checked:bg-surface aria-checked:font-semibold aria-checked:text-ink aria-checked:shadow-sm">
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
      <span aria-hidden className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-cobalt peer-focus-visible:outline-2 peer-focus-visible:outline-cobalt
        after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition-transform peer-checked:after:translate-x-4" />
    </label>
  );
}
