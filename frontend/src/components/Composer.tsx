import { X as XIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { API_BASE, api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import type { Meta, Platform, PlatformState, RunRequest, SourceType } from "../types";

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
  platforms: PlatformState[];
  onClose: () => void;
  onCreated: (id: number) => void;
}

export default function Composer({ meta, platforms, onClose, onCreated }: Props) {
  const [f, setF] = useState<RunRequest>({
    platform: "facebook", source_type: "feed", sources: [], count: 40, job_mode: false,
    keywords: [], profile: "", ai_provider: meta.default_ai, ai_model: "", only_new: false, headless: false,
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
  const pushCommand = buildPushCommand(f, sourcesText, keywordsText, API_BASE || window.location.origin);
  const [copied, setCopied] = useState(false);
  const provider = meta.ai_providers.find((p) => p.key === f.ai_provider);
  const platformState = platforms.find((p) => p.key === f.platform);
  const hint = f.source_type !== "feed" ? SOURCE_HINT[f.platform][f.source_type] : null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const notLoggedIn = useMemo(
    () => platformState && !platformState.has_profile,
    [platformState],
  );

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (cloud) return;
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
      <form
        onSubmit={submit}
        role="dialog"
        aria-label="Lướt mới"
        className="sheet flex h-full w-full max-w-md flex-col bg-surface shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-lg font-semibold">Lướt mới</h2>
          <button type="button" onClick={onClose} aria-label="Đóng" className="rounded-md p-1 text-ink-soft hover:bg-sunken">
            <XIcon className="size-5" />
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          <Group label="Nền tảng">
            <Segmented
              value={f.platform}
              onChange={(v) => set("platform", v as Platform)}
              options={platformOptions}
            />
            {!cloud && notLoggedIn && (
              <p className="mt-2 text-sm text-ink-soft">
                Bạn chưa đăng nhập {platformState?.name}. Đăng nhập ở cột bên trái trước, nếu không bot chỉ thấy nội dung công khai.
              </p>
            )}
          </Group>

          <Group label="Lướt ở đâu">
            <Segmented
              value={f.source_type}
              onChange={(v) => set("source_type", v as SourceType)}
              options={[{ value: "feed", label: "Bảng tin" }, { value: "group", label: "Group" }, { value: "search", label: "Tìm kiếm" }]}
            />
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
            <select className="field" value={f.ai_provider}
              onChange={(e) => { set("ai_provider", e.target.value); set("ai_model", ""); }}>
              {meta.ai_providers.map((p) => (
                <option key={p.key} value={p.key} disabled={!p.configured}>
                  {p.name}{p.configured ? "" : ` (thiếu ${p.env_key})`}
                </option>
              ))}
            </select>
            {provider && provider.models.length > 0 && (
              <>
                <input className="field mt-2" list="models" placeholder={`Model: ${provider.default_model}`}
                  value={f.ai_model} onChange={(e) => set("ai_model", e.target.value)} aria-label="Model" />
                <datalist id="models">{provider.models.map((m) => <option key={m} value={m} />)}</datalist>
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
          {cloud ? (
            <>
              <p className="mb-2 text-sm">
                Chạy lệnh này trong thư mục <code>backend</code> trên máy bạn. Đặt biến <code>FEEDLENS_API_TOKEN</code> trước khi chạy.
              </p>
              <pre className="max-h-32 overflow-auto rounded-lg bg-sunken p-3 text-xs whitespace-pre-wrap break-all">{pushCommand}</pre>
              <button type="button"
                onClick={() => navigator.clipboard.writeText(pushCommand).then(() => setCopied(true))}
                className="mt-3 w-full rounded-lg bg-cobalt py-2.5 font-semibold text-cobalt-ink hover:opacity-90">
                {copied ? "Đã copy lệnh" : "Copy lệnh"}
              </button>
            </>
          ) : (
            <>
              {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
              <button disabled={sending}
                className="w-full rounded-lg bg-cobalt py-2.5 font-semibold text-cobalt-ink hover:opacity-90 disabled:opacity-50">
                {sending ? "Đang bắt đầu…" : "Bắt đầu lướt"}
              </button>
            </>
          )}
        </footer>
      </form>
    </div>
  );
}

/** Lệnh PowerShell/bash cho bot ở máy: lướt rồi đẩy bài lên server cloud. */
function buildPushCommand(f: RunRequest, sourcesText: string, keywordsText: string, server: string): string {
  const q = (s: string) => `"${s.replace(/"/g, '\\"')}"`;
  const parts = [".venv/Scripts/feedlens push", f.platform];
  if (f.source_type !== "feed") parts.push("--type", f.source_type);
  sourcesText.split("\n").map((s) => s.trim()).filter(Boolean).forEach((s) => parts.push("--source", q(s)));
  parts.push("-n", String(f.count));
  if (f.job_mode) {
    parts.push("--jobs");
    keywordsText.split(",").map((s) => s.trim()).filter(Boolean).forEach((k) => parts.push("-k", q(k)));
    if (f.profile.trim()) parts.push("--profile", q(f.profile.trim().replace(/\s+/g, " ")));
  }
  if (f.only_new) parts.push("--only-new");
  if (f.headless) parts.push("--headless");
  if (f.ai_provider !== "auto") parts.push("--ai", f.ai_provider);
  if (f.ai_model) parts.push("--model", f.ai_model);
  parts.push("--server", server);
  return parts.join(" ");
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
