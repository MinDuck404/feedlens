import { Globe, Loader2, LogIn, Plus, RefreshCw, Search, Settings as SettingsIcon, X as XIcon } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { LANGS, useI18n, type Key, type Lang } from "../i18n";
import type { PlatformState, Run } from "../types";

export const STATUS_CLS: Record<string, string> = {
  pending: "text-ink-soft", queued: "text-ink-soft", scraping: "text-link",
  analyzing: "text-link", done: "text-ok", error: "text-danger",
};

interface Props {
  cloud: boolean;
  email?: string;
  agentOnline?: boolean;
  onOpenSettings: () => void;
  platforms: PlatformState[];
  runs: Run[];
  selected: number | null;
  page: "home" | "history" | "run";
  onSelect: (id: number) => void;
  onGoHome: () => void;
  onGoHistory: () => void;
  onNewRun: () => void;
  onPlatformChanged: () => void;
  onLogout?: () => void;
}

export default function Sidebar({ cloud, email, agentOnline, onOpenSettings, platforms, runs, selected, page, onSelect, onGoHome, onGoHistory, onNewRun, onPlatformChanged, onLogout }: Props) {
  const { t, lang, setLang } = useI18n();
  const navCls = "rounded-full px-3 py-1 text-sm text-ink-soft hover:text-ink aria-[current=page]:bg-primary aria-[current=page]:text-primary-ink";
  return (
    <aside className="flex w-full shrink-0 flex-col border-line md:h-full md:w-72 md:border-r">
      <div className="flex items-center justify-between px-5 pt-5 pb-4">
        <a href="#/" onClick={(e) => { e.preventDefault(); onGoHome(); }} className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <span aria-hidden className="relative grid size-6 place-items-center rounded-full bg-primary">
            <Search className="size-3.5 text-primary-ink" strokeWidth={3} />
            <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-accent ring-2 ring-[var(--paper)]" />
          </span>
          FeedLens
        </a>
        <button
          onClick={onNewRun}
          className="flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-ink hover:opacity-90"
        >
          <Plus className="size-4" /> {t("act.newRun")}
        </button>
      </div>

      <nav className="flex gap-1 px-4 pb-4" aria-label={t("nav.label")}>
        <a href="#/" aria-current={page === "home" ? "page" : undefined} className={navCls}
          onClick={(e) => { e.preventDefault(); onGoHome(); }}>{t("nav.home")}</a>
        <a href="#/history" aria-current={page === "history" ? "page" : undefined} className={navCls}
          onClick={(e) => { e.preventDefault(); onGoHistory(); }}>{t("nav.history")}</a>
      </nav>

      {cloud ? (
        <button onClick={onOpenSettings} className="paper-card mx-5 mb-4 flex items-center gap-2 rounded-xl px-3 py-2 text-left text-sm">
          <span className={`size-2 shrink-0 rounded-full ${agentOnline ? "bg-ok" : "bg-line"}`} />
          <span className="flex-1">{agentOnline ? t("sb.agentOn") : t("sb.agentOff")}</span>
        </button>
      ) : (
        <section className="px-5 pb-4">
          <h2 className="mb-1 font-mono text-xs text-ink-soft">{t("sb.accounts")}</h2>
          <ul className="divide-y divide-line">
            {platforms.map((p) => <PlatformRow key={p.key} p={p} onChanged={onPlatformChanged} onLogin={onGoHome} />)}
          </ul>
        </section>
      )}

      <section className="flex min-h-0 flex-1 flex-col border-t border-line px-3 pt-4">
        <h2 className="mb-2 flex items-center justify-between px-2 font-mono text-xs text-ink-soft">
          <span>{t("sb.prevRuns", { n: runs.length })}</span>
          {runs.length > 0 && (
            <button onClick={onGoHistory} className="font-sans text-xs text-link hover:underline">{t("sb.seeAll")}</button>
          )}
        </h2>
        {runs.length === 0 ? (
          <p className="px-2 text-sm text-ink-soft">{t("sb.noRuns")}</p>
        ) : (
          <ul className="-mx-1 max-h-40 overflow-y-auto pb-4 md:max-h-none">
            {runs.map((r) => {
              const q = r.request;
              const src = q.source_type === "feed" ? t("sb.feed") : q.sources[0] ?? "";
              return (
                <li key={r.id}>
                  <button
                    onClick={() => onSelect(r.id)}
                    aria-current={page === "run" && selected === r.id}
                    className="w-full rounded-xl border border-transparent px-3 py-2 text-left hover:bg-surface aria-[current=true]:border-line aria-[current=true]:bg-surface aria-[current=true]:shadow-sm"
                  >
                    <span className="block truncate text-sm font-medium">{src}</span>
                    <span className="flex justify-between gap-2 text-xs text-ink-soft">
                      <span>{PLATFORM_LABEL[q.platform]}{q.job_mode ? t("sb.jobTag") : ""}</span>
                      <span className={`font-mono ${STATUS_CLS[r.status] ?? ""}`}>{t(`status.${r.status}` as Key)}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <div className="flex items-center gap-2 border-t border-line px-5 py-3 text-sm">
        <span className="min-w-0 flex-1 truncate text-ink-soft">{email ?? t("sb.thisMachine")}</span>
        <label className="relative grid size-8 place-items-center rounded-md text-ink-soft hover:bg-sunken hover:text-ink" title={t("lang.label")}>
          <Globe className="size-4" />
          <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label={t("lang.label")}
            className="absolute inset-0 cursor-pointer opacity-0">
            {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </label>
        <span aria-hidden className="-ml-1 font-mono text-xs text-ink-soft uppercase">{lang}</span>
        <button onClick={onOpenSettings} aria-label={t("act.settings")} title={t("act.settings")}
          className="grid size-8 place-items-center rounded-md text-ink-soft hover:bg-sunken hover:text-ink">
          <SettingsIcon className="size-4" />
        </button>
        {onLogout && (
          <button onClick={onLogout} className="rounded-md px-2 py-1 text-ink-soft hover:bg-sunken hover:text-ink">{t("act.logout")}</button>
        )}
      </div>
    </aside>
  );
}

function PlatformRow({ p, onChanged, onLogin }: { p: PlatformState; onChanged: () => void; onLogin: () => void }) {
  const [busy, setBusy] = useState(false);
  const { t } = useI18n();
  const act = async (a: "login" | "check" | "logout") => {
    if (a === "logout" && !confirm(t("plat.confirmRemove", { name: p.name }))) return;
    if (a === "login") onLogin();  // về trang chủ, nơi có hướng dẫn trong lúc cửa sổ đăng nhập mở
    setBusy(true);
    try { await api.platformAction(p.key, a); } catch (e) { alert((e as Error).message); }
    setBusy(false);
    onChanged();
  };
  const waiting = p.login_state === "waiting";
  const status = waiting ? t("plat.waiting")
    : p.logged_in === true ? t("plat.loggedIn")
    : p.logged_in === false ? t("plat.notLoggedIn")
    : p.has_profile ? t("plat.saved") : t("plat.notConnected");
  const dot = waiting ? "bg-accent animate-pulse" : p.logged_in ? "bg-ok" : p.has_profile ? "bg-ink-soft" : "bg-line";

  return (
    <li className="flex items-center justify-between gap-2 py-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-sm font-medium">
          <span className={`size-2 rounded-full ${dot}`} />
          {p.name}
        </div>
        <div className="truncate pl-4 text-xs text-ink-soft">{status}</div>
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        {busy ? (
          <Loader2 className="size-4 animate-spin text-ink-soft" />
        ) : (
          <>
            {p.has_profile && (
              <IconBtn label={t("plat.check")} onClick={() => act("check")}><RefreshCw className="size-3.5" /></IconBtn>
            )}
            {!p.logged_in && !waiting && (
              <button onClick={() => act("login")} title={t("plat.openLogin", { name: p.name })}
                className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-medium hover:border-ink hover:text-link">
                <LogIn className="size-3.5" /> {p.has_profile ? t("plat.relogin") : t("plat.login")}
              </button>
            )}
            {p.has_profile && (
              <IconBtn label={t("plat.remove")} onClick={() => act("logout")}><XIcon className="size-3.5" /></IconBtn>
            )}
          </>
        )}
      </div>
    </li>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button aria-label={label} title={label} onClick={onClick}
      className="grid size-7 place-items-center rounded-md text-ink-soft hover:bg-sunken hover:text-ink">
      {children}
    </button>
  );
}
