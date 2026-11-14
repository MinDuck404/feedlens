import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import type { Platform, PlatformSession } from "../types";

const PLATFORMS: Platform[] = ["facebook", "linkedin", "x", "reddit"];

const STATUS: Record<PlatformSession["status"], { label: string; cls: string }> = {
  unchecked: { label: "Chưa kiểm tra", cls: "text-ink-soft" },
  ok: { label: "Dùng được", cls: "text-ok" },
  invalid: { label: "Hết hiệu lực", cls: "text-danger" },
};

/** Cài đặt → Lướt trên server: lưu cookie (mã hóa) để server lướt thay, không cần agent trên máy. */
export default function CookieSessions() {
  const [sessions, setSessions] = useState<PlatformSession[] | null>(null);
  const reload = () => api.sessions().then(setSessions);
  useEffect(() => { reload(); }, []);

  return (
    <div>
      <h3 className="font-semibold">Lướt trên server (cookie)</h3>
      <p className="mt-1 text-sm text-ink-soft">
        Server dùng cookie đăng nhập của bạn để tự lướt, không cần bật agent. Cookie được mã hóa khi lưu và không bao giờ hiện lại trên web.
      </p>
      <div className="mt-3 flex gap-2 rounded-lg border border-danger/40 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" />
        <p>
          Cookie sẽ được dùng từ IP của server, khác máy bạn hay dùng. Facebook/LinkedIn có thể bắt xác minh,
          đăng xuất hoặc <b>khóa tài khoản</b>. Nên dùng tài khoản phụ. Cookie có quyền như mật khẩu: chỉ lưu trên server bạn tin tưởng.
        </p>
      </div>
      <p className="mt-3 text-sm">
        Cách dễ nhất: đăng nhập trên máy bằng <code>feedlens login facebook</code> (qua xác minh 2 bước), rồi chạy{" "}
        <code>feedlens cookies push facebook</code> trong thư mục <code>backend</code>. Hoặc dán cookie xuất từ extension Cookie-Editor ở dưới.
      </p>
      {sessions === null ? (
        <p className="mt-3 text-sm text-ink-soft">Đang tải…</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {PLATFORMS.map((p) => (
            <SessionRow key={p} platform={p} s={sessions.find((x) => x.platform === p)} onChanged={reload} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SessionRow({ platform, s, onChanged }: { platform: Platform; s?: PlatformSession; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "check">("");
  const [error, setError] = useState("");
  const name = PLATFORM_LABEL[platform];

  const run = async (kind: "save" | "check", fn: () => Promise<unknown>) => {
    setBusy(kind);
    setError("");
    try {
      await fn();
      if (kind === "save") { setEditing(false); setValue(""); }
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const remove = async () => {
    if (!confirm(`Xóa cookie ${name} khỏi server?`)) return;
    await api.deleteSession(platform);
    onChanged();
  };

  return (
    <li className="paper-card rounded-xl p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">{name}</div>
          {s ? (
            <div className="text-xs">
              <span className={STATUS[s.status].cls}>{STATUS[s.status].label}</span>
              <span className="text-ink-soft"> · tài khoản {s.hint}, lưu {new Date(s.saved_at).toLocaleDateString("vi-VN")}</span>
              {s.status_message && <p className="mt-0.5 text-ink-soft">{s.status_message}</p>}
            </div>
          ) : (
            <div className="text-xs text-ink-soft">Chưa có cookie</div>
          )}
        </div>
        {!editing && (
          <div className="flex shrink-0 items-center gap-2 text-sm">
            {s && (
              <button onClick={() => run("check", () => api.checkSession(platform))} disabled={!!busy}
                className="flex items-center gap-1 font-medium text-link hover:underline disabled:opacity-50">
                {busy === "check" && <Loader2 className="size-3.5 animate-spin" />} Kiểm tra
              </button>
            )}
            <button onClick={() => setEditing(true)} className="font-medium text-link hover:underline">
              {s ? "Thay" : "Dán cookie"}
            </button>
            {s && <button onClick={remove} className="text-ink-soft hover:text-danger">Xóa</button>}
          </div>
        )}
      </div>
      {busy === "check" && <p className="mt-2 text-xs text-ink-soft">Server đang mở trang chủ {name} bằng cookie, khoảng 10–30 giây…</p>}
      {editing && (
        <div className="mt-3">
          <textarea className="field font-mono text-xs" rows={4} autoFocus value={value} onChange={(e) => setValue(e.target.value)}
            placeholder={'[{"name":"c_user","value":"…","domain":".facebook.com"}, …]\nhoặc: c_user=…; xs=…'} />
          <div className="mt-2 flex justify-end gap-2">
            <button onClick={() => { setEditing(false); setValue(""); setError(""); }}
              className="rounded-md px-3 py-1.5 text-sm text-ink-soft hover:bg-surface">Hủy</button>
            <button onClick={() => run("save", () => api.saveSession(platform, value))} disabled={!!busy || value.trim().length < 10}
              className="flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-ink disabled:opacity-50">
              {busy === "save" && <Loader2 className="size-3.5 animate-spin" />} Lưu cookie
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </li>
  );
}
