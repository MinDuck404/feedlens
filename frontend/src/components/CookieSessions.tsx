import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { useI18n, type Key } from "../i18n";
import type { Platform, PlatformSession } from "../types";

const PLATFORMS: Platform[] = ["facebook", "linkedin", "x", "reddit"];

const STATUS: Record<PlatformSession["status"], { label: Key; cls: string }> = {
  unchecked: { label: "ck.unchecked", cls: "text-ink-soft" },
  ok: { label: "ck.ok", cls: "text-ok" },
  invalid: { label: "ck.invalid", cls: "text-danger" },
};

/** Cài đặt → Lướt trên server: lưu cookie (mã hóa) để server lướt thay, không cần agent trên máy. */
export default function CookieSessions() {
  const [sessions, setSessions] = useState<PlatformSession[] | null>(null);
  const { t } = useI18n();
  const reload = () => api.sessions().then(setSessions);
  useEffect(() => { reload(); }, []);

  return (
    <div>
      <h3 className="font-semibold">{t("ck.title")}</h3>
      <p className="mt-1 text-sm text-ink-soft">{t("ck.hint")}</p>
      <div className="mt-3 flex gap-2 rounded-lg border border-danger/40 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" />
        <p>{t("ck.warn")}</p>
      </div>
      <p className="mt-3 text-sm">{t("ck.easiest")}</p>
      {sessions === null ? (
        <p className="mt-3 text-sm text-ink-soft">{t("act.loading")}</p>
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
  const { t, locale } = useI18n();

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
    if (!confirm(t("ck.confirmDelete", { name }))) return;
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
              <span className={STATUS[s.status].cls}>{t(STATUS[s.status].label)}</span>
              <span className="text-ink-soft">, {t("ck.account", { hint: s.hint, date: new Date(s.saved_at).toLocaleDateString(locale) })}</span>
              {s.status_message && <p className="mt-0.5 text-ink-soft">{s.status_message}</p>}
            </div>
          ) : (
            <div className="text-xs text-ink-soft">{t("ck.none")}</div>
          )}
        </div>
        {!editing && (
          <div className="flex shrink-0 items-center gap-2 text-sm">
            {s && (
              <button onClick={() => run("check", () => api.checkSession(platform))} disabled={!!busy}
                className="flex items-center gap-1 font-medium text-link hover:underline disabled:opacity-50">
                {busy === "check" && <Loader2 className="size-3.5 animate-spin" />} {t("ck.check")}
              </button>
            )}
            <button onClick={() => setEditing(true)} className="font-medium text-link hover:underline">
              {s ? t("ck.replace") : t("ck.paste")}
            </button>
            {s && <button onClick={remove} className="text-ink-soft hover:text-danger">{t("act.delete")}</button>}
          </div>
        )}
      </div>
      {busy === "check" && <p className="mt-2 text-xs text-ink-soft">{t("ck.checking", { name })}</p>}
      {editing && (
        <div className="mt-3">
          <textarea className="field font-mono text-xs" rows={4} autoFocus value={value} onChange={(e) => setValue(e.target.value)}
            placeholder={t("ck.placeholder")} />
          <div className="mt-2 flex justify-end gap-2">
            <button onClick={() => { setEditing(false); setValue(""); setError(""); }}
              className="rounded-md px-3 py-1.5 text-sm text-ink-soft hover:bg-surface">{t("act.cancel")}</button>
            <button onClick={() => run("save", () => api.saveSession(platform, value))} disabled={!!busy || value.trim().length < 10}
              className="flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-ink disabled:opacity-50">
              {busy === "save" && <Loader2 className="size-3.5 animate-spin" />} {t("ck.save")}
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </li>
  );
}
