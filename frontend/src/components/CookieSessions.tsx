import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { parseTimestamp } from "../logic";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { serverMessage, useI18n, type Key } from "../i18n";
import type { Platform, PlatformSession } from "../types";

import { Button, SkeletonCard } from "./ui";

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
  const [loadError, setLoadError] = useState("");
  const reload = () => api.sessions().then((s) => { setSessions(s); setLoadError(""); });
  useEffect(() => { reload().catch((e) => setLoadError(e.message)); }, []);

  return (
    <section className="border-t border-line pt-6">
      <h3 className="text-lg font-semibold tracking-tight">{t("ck.title")}</h3>
      <p className="mt-2 text-sm leading-relaxed text-pretty text-ink-soft">{t("ck.hint")}</p>
      <div className="mt-4 flex gap-3 rounded-card border border-warning/30 bg-warning/5 p-4 text-sm leading-relaxed">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
        <p>{t("ck.warn")}</p>
      </div>
      <p className="mt-3 text-sm">{t("ck.easiest")}</p>
      {loadError && <p role="alert" className="mt-2 text-sm text-danger">{loadError} <button onClick={() => reload().catch((e) => setLoadError(e.message))}>{t("act.retry")}</button></p>}
      {sessions === null && !loadError ? (
        <div role="status" aria-label={t("act.loading")} className="mt-4"><div aria-hidden="true"><SkeletonCard /></div></div>
      ) : (
        <ul className="mt-3 space-y-3">
          {(sessions ? PLATFORMS : []).map((p) => (
            <SessionRow key={p} platform={p} s={sessions?.find((x) => x.platform === p)} onChanged={reload} />
          ))}
        </ul>
      )}
    </section>
  );
}

function SessionRow({ platform, s, onChanged }: { platform: Platform; s?: PlatformSession; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "check" | "delete">("");
  const [error, setError] = useState("");
  const name = PLATFORM_LABEL[platform];
  const { t, locale } = useI18n();

  const run = async (kind: "save" | "check" | "delete", fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(kind);
    setError("");
    try {
      await fn();
      if (kind === "save") { setEditing(false); setValue(""); }
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const remove = async () => {
    if (!confirm(t("ck.confirmDelete", { name }))) return;
    await run("delete", () => api.deleteSession(platform));
  };

  return (
    <li className="paper-card p-4">
      <div className="flex flex-col items-start gap-3">
        <div className="min-w-0">
          <div className="font-medium">{name}</div>
          {s ? (
            <div className="mt-1 text-xs leading-relaxed [overflow-wrap:anywhere]">
              <span className={STATUS[s.status].cls}>{t(STATUS[s.status].label)}</span>
              <span className="text-ink-soft">, {t("ck.account", { hint: s.hint, date: parseTimestamp(s.saved_at).toLocaleDateString(locale) })}</span>
              {s.status_message && <p className="mt-0.5 text-ink-soft">{serverMessage(s.status_message_code ?? ({ ok: "ck.statusOk", invalid: "ck.statusInvalid", unchecked: "ck.statusUnchecked" }[s.status]), s.status_message)}</p>}
            </div>
          ) : (
            <div className="text-xs text-ink-soft">{t("ck.none")}</div>
          )}
        </div>
        {!editing && (
          <div className="flex w-full flex-wrap items-center gap-2 border-t border-line pt-3 text-sm">
            {s && (
              <Button onClick={() => run("check", () => api.checkSession(platform))} busy={busy === "check"} disabled={!!busy} variant="outline">
                {t("ck.check")}
              </Button>
            )}
            <Button onClick={() => setEditing(true)} disabled={!!busy} variant={s ? "ghost" : "outline"}>
              {s ? t("ck.replace") : t("ck.paste")}
            </Button>
            {s && <Button onClick={remove} busy={busy === "delete"} disabled={!!busy} variant="ghost" className="sm:ml-auto hover:text-danger">{t("act.delete")}</Button>}
          </div>
        )}
      </div>
      {busy === "check" && <p className="mt-2 text-xs text-ink-soft">{t("ck.checking", { name })}</p>}
      {editing && (
        <div className="page-enter mt-4">
          <label htmlFor={`cookie-${platform}`} className="mb-2 block text-sm font-medium">{t("ck.paste")}</label>
          <textarea id={`cookie-${platform}`} className="field font-mono text-xs" rows={4} autoFocus value={value} onChange={(e) => setValue(e.target.value)}
            placeholder={t("ck.placeholder")} />
          <div className="mt-2 flex justify-end gap-2">
            <Button onClick={() => { setEditing(false); setValue(""); setError(""); }} disabled={!!busy} variant="ghost">{t("act.cancel")}</Button>
            <Button onClick={() => run("save", () => api.saveSession(platform, value))} busy={busy === "save"} disabled={!!busy || value.trim().length < 10}>
              {t("ck.save")}
            </Button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </li>
  );
}
