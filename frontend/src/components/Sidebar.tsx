import {
  House, History, TrendingUp,
  Loader2,
  LogIn,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  X as XIcon,
} from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { describeRunSource } from "../logic";
import { serverMessage, useI18n, type Key } from "../i18n";
import { LanguageMenu, ThemeSwitch } from "./PreferenceMenus";
import type { PlatformState, Run } from "../types";
import { Button, IconButton } from "./ui/Button";
import { Sheet } from "./ui/Dialog";

const FALLBACK_PLATFORMS: PlatformState[] = [
  { key: "facebook", name: "Facebook", logged_in: false, has_profile: false, login_state: "idle" },
  { key: "linkedin", name: "LinkedIn", logged_in: false, has_profile: false, login_state: "idle" },
  { key: "x", name: "X", logged_in: false, has_profile: false, login_state: "idle" },
  { key: "reddit", name: "Reddit", logged_in: false, has_profile: false, login_state: "idle" },
];

export const STATUS_CLS: Record<string, string> = {
  pending: "text-ink-soft",
  queued: "text-ink-soft",
  scraping: "text-link",
  analyzing: "text-link",
  done: "text-ok",
  error: "text-danger",
  analysis_failed: "text-danger",
};

interface Props {
  cloud: boolean;
  email?: string;
  agentOnline?: boolean;
  onOpenSettings: () => void;
  platforms: PlatformState[];
  runs: Run[];
  selected: number | null;
  page: "home" | "history" | "trends" | "ask" | "run";
  onSelect: (id: number) => void;
  onGoHome: () => void;
  onGoHistory: () => void;
  onGoTrends?: () => void;
  onGoAsk?: () => void;
  onNewRun: () => void;
  onPlatformChanged: () => void;
  onLogout?: () => void;
}

export default function Sidebar(props: Props) {
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const { t } = useI18n();

  const handleMobileNav = (action: () => void) => {
    setMobileDrawerOpen(false);
    action();
  };

  return (
    <>
      {/* Mobile Top Header (h-14 / 56px) - chỉ hiện trên màn hình < 768px, loại bỏ nút New Run trùng lặp */}
      <header className="sticky top-0 z-30 flex h-14 w-full shrink-0 items-center justify-between border-b border-line bg-bg/90 px-4 backdrop-blur-md md:hidden">
        <a
          href="#/"
          onClick={(e) => {
            e.preventDefault();
            props.onGoHome();
          }}
          className="flex items-center gap-2 text-lg font-headline font-semibold tracking-tight text-ink interactive-tap"
        >
          <span
            aria-hidden
            className="relative grid size-6 place-items-center rounded-full bg-primary"
          >
            <Search className="size-3.5 text-primary-ink" strokeWidth={3} />
            <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-accent ring-2 ring-[var(--paper)]" />
          </span>
          <span>FeedLens</span>
        </a>

        <div className="flex items-center gap-1">
          <ThemeSwitch />
          <IconButton
            icon={<Plus className="size-4" />}
            label={t("act.newRun")}
            variant="ghost"
            size="sm"
            className="size-11! outline-none focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            onClick={props.onNewRun}
          />
          <IconButton
            icon={<Menu className="size-5" />}
            label={t("nav.menu")}
            variant="ghost"
            size="sm"
            className="size-11! outline-none focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            onClick={() => setMobileDrawerOpen(true)}
          />
        </div>
      </header>

      {/* Mobile Drawer (trượt từ bên trái với Sheet chung) */}
      <Sheet
        open={mobileDrawerOpen}
        onClose={() => setMobileDrawerOpen(false)}
        side="left"
        maxWidth="max-w-xs"
        ariaLabel="FeedLens"
        title={
          <div className="flex items-center gap-2 text-base font-semibold tracking-tight">
            <span
              aria-hidden
              className="relative grid size-6 place-items-center rounded-full bg-primary"
            >
              <Search className="size-3.5 text-primary-ink" strokeWidth={3} />
              <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-accent ring-2 ring-[var(--paper)]" />
            </span>
            <span>FeedLens</span>
          </div>
        }
        closeAriaLabel={t("act.close")}
        contentClassName="flex-1 flex flex-col min-h-0 overflow-y-auto px-4 py-3"
      >
        <div className="mb-3 px-1 pt-1">
          <Button
            size="sm"
            variant="primary"
            pill
            icon={<Plus className="size-3.5" />}
            onClick={() => handleMobileNav(props.onNewRun)}
            className="w-full justify-center shadow-xs"
          >
            {t("act.newRun")}
          </Button>
        </div>
        <SidebarBody
          {...props}
          onGoHome={() => handleMobileNav(props.onGoHome)}
          onGoHistory={() => handleMobileNav(props.onGoHistory)}
          onGoTrends={() => handleMobileNav(() => props.onGoTrends?.())}
          onGoAsk={() => handleMobileNav(() => props.onGoAsk?.())}
          onSelect={(id) => handleMobileNav(() => props.onSelect(id))}
          onNewRun={() => handleMobileNav(props.onNewRun)}
          onOpenSettings={() => handleMobileNav(props.onOpenSettings)}
        />
      </Sheet>

      {/* Desktop Sidebar (>= 768px): cố định thanh bên trái */}
      <aside className="hidden h-full w-72 shrink-0 flex-col border-r border-line bg-bg/50 md:flex">
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <a
            href="#/"
            onClick={(e) => {
              e.preventDefault();
              props.onGoHome();
            }}
            className="flex items-center gap-2.5 text-xl font-headline font-semibold tracking-tight text-ink interactive-tap"
          >
            <span
              aria-hidden
              className="relative grid size-6 place-items-center rounded-full bg-primary"
            >
              <Search className="size-3.5 text-primary-ink" strokeWidth={3} />
              <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-accent ring-2 ring-[var(--paper)]" />
            </span>
            <span>FeedLens</span>
          </a>
          <Button
            size="sm"
            variant="primary"
            pill
            icon={<Plus className="size-3.5" />}
            onClick={props.onNewRun}
          >
            {t("act.newRun")}
          </Button>
        </div>

        <SidebarBody {...props} />
      </aside>
    </>
  );
}

/** Thân nội dung dùng chung giữa Mobile Drawer và Desktop Sidebar */
function SidebarBody({
  cloud,
  email,
  agentOnline,
  onOpenSettings,
  platforms,
  runs,
  selected,
  page,
  onSelect,
  onGoHome,
  onGoHistory,
  onGoTrends,
  onGoAsk,
  onPlatformChanged,
  onLogout,
}: Props) {
  const { t } = useI18n();

  const navCls =
    "flex min-h-11 items-center gap-3 rounded-xl px-3.5 py-2 text-sm font-medium transition-colors interactive-tap text-ink-soft hover:text-ink hover:bg-sunken/60 aria-[current=page]:bg-primary aria-[current=page]:text-primary-ink aria-[current=page]:shadow-xs";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Navigation Pills */}
      <nav className="flex flex-col gap-0 px-4 pb-2" aria-label={t("nav.label")}>
        <a
          href="#/"
          aria-current={page === "home" ? "page" : undefined}
          className={navCls}
          onClick={(e) => {
            e.preventDefault();
            onGoHome();
          }}
        >
          <House aria-hidden="true" className="size-4 shrink-0" /><span className="whitespace-nowrap">{t("nav.home")}</span>
        </a>
        <a
          href="#/history"
          aria-current={page === "history" ? "page" : undefined}
          className={navCls}
          onClick={(e) => {
            e.preventDefault();
            onGoHistory();
          }}
        >
          <History aria-hidden="true" className="size-4 shrink-0" /><span className="whitespace-nowrap">{t("nav.history")}</span>
        </a>
        <a
          href="#/trends"
          aria-current={page === "trends" ? "page" : undefined}
          className={navCls}
          onClick={(e) => {
            e.preventDefault();
            onGoTrends?.();
          }}
        >
          <TrendingUp aria-hidden="true" className="size-4 shrink-0" /><span className="whitespace-nowrap">{t("nav.trends")}</span>
        </a>
        <a href="#/ask" aria-current={page === "ask" ? "page" : undefined} className={navCls} onClick={(event) => { event.preventDefault(); onGoAsk?.(); }}><Search aria-hidden="true" className="size-4 shrink-0" /><span className="whitespace-nowrap">{t("ask.title")}</span></a>
      </nav>

      {/* Cloud Agent / Platform Accounts */}
      {cloud ? (
        <button
          onClick={onOpenSettings}
          className="paper-card paper-card-interactive mx-4 mb-4 flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm"
        >
          <span
            className={`size-2 shrink-0 rounded-full ${
              agentOnline ? "bg-ok animate-pulse" : "bg-line"
            }`}
          />
          <span className="flex-1 font-medium">
            {agentOnline ? t("sb.agentOn") : t("sb.agentOff")}
          </span>
        </button>
      ) : (
        <section className="px-4 pb-2">
          <h2 className="mb-1 font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {t("sb.accounts")}
          </h2>
          <BrowserNotice platforms={platforms} />
          <ul className="divide-y divide-line rounded-xl border border-line bg-surface/50 px-3">
            {FALLBACK_PLATFORMS.map((fallback) => platforms.find((p) => p.key === fallback.key) ?? fallback).map((p) => (
              <PlatformRow
                key={p.key}
                p={p}
                onChanged={onPlatformChanged}
                onLogin={onGoHome}
              />
            ))}
          </ul>
        </section>
      )}

      {/* Recent Runs List - Tương phản cao hơn, hover rõ nét, chỉ báo item đang chọn */}
      <section className="flex min-h-0 flex-1 flex-col border-t border-line px-3 pt-3">
        <h2 className="mb-2 flex items-center justify-between px-2 font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
          <span className="flex items-center gap-1.5">
            <span>{t("sb.prevRunsTitle")}</span>
            <span className="font-mono text-[11px] tracking-normal">({runs.length})</span>
          </span>
          {runs.length > 0 && (
            <button
              onClick={onGoHistory}
              className="text-xs font-medium text-link hover:underline lowercase tracking-normal"
            >
              {t("sb.seeAll")}
            </button>
          )}
        </h2>

        {runs.length === 0 ? (
          <p className="px-2 py-4 text-center text-sm text-ink-soft">
            {t("sb.noRuns")}
          </p>
        ) : (
          <ul className="-mx-1 flex-1 space-y-0.5 overflow-y-auto px-1 pb-4">
            {runs.map((r) => {
              const q = r.request;
              const src = describeRunSource(q, t, "sidebar");
              const isSelected = page === "run" && selected === r.id;

              return (
                <li key={r.id}>
                  <button
                    onClick={() => onSelect(r.id)}
                    title={src}
                    aria-current={isSelected}
                    className={`group relative w-full rounded-xl border px-3 py-1.5 text-left transition-all interactive-tap ${
                      isSelected
                        ? "border-line bg-surface font-semibold text-ink shadow-xs"
                        : "border-transparent text-ink hover:bg-surface/90 hover:text-ink"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      {isSelected && (
                        <span className="size-1.5 rounded-full bg-accent shrink-0 animate-pulse" />
                      )}
                      <span className="truncate text-sm font-medium">{src}</span>
                    </div>
                    <div className="flex items-center justify-between gap-2 pt-1 text-xs">
                      <span className="truncate text-ink-soft">
                        {PLATFORM_LABEL[q.platform]}
                        {q.job_mode ? t("sb.jobTag") : ""}
                      </span>
                      {/* Bỏ font-mono cho chữ trạng thái để hiển thị tiếng Việt/Trung không bị lệch */}
                      <span
                        className={`font-sans text-[11px] font-medium shrink-0 ${
                          STATUS_CLS[r.status] ?? ""
                        }`}
                      >
                        {t(`status.${r.status}` as Key)}
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Bottom Bar: Account & Settings */}
      <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2 text-sm bg-bg/60">
        {email ? (
          <span
            className="min-w-0 flex-1 truncate text-xs font-medium text-ink-soft"
            title={email}
          >
            {email}
          </span>
        ) : null}

        <div className="flex items-center gap-1 ml-auto">
          <LanguageMenu />

          {/* Settings Button */}
          <IconButton
            icon={<SettingsIcon className="size-4" />}
            label={t("act.settings")}
            variant="ghost"
            size="sm"
            className="outline-none focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            onClick={onOpenSettings}
          />

          {/* Logout Button */}
          {onLogout && (
            <button
              onClick={onLogout}
              className="rounded-lg px-2 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-sunken hover:text-danger outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {t("act.logout")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function BrowserNotice({ platforms }: { platforms: PlatformState[] }) {
  const { t } = useI18n();
  const missing = platforms.some((p) => p.missing || p.login_error_code === "error.browser_missing");
  const limited = platforms.some((p) => p.oauth_limited);
  const edge = platforms.some((p) => p.browser === "msedge");
  if (!missing && !limited && !edge) return null;
  const message = missing ? (platforms.some((p) => p.has_profile) ? "plat.browserSessionMissing" : "plat.browserMissing")
    : limited ? "plat.chromiumNote" : "plat.edgeNote";
  return <p role={missing ? "alert" : "note"} className={`mb-2 text-xs leading-relaxed ${missing ? "text-danger" : "text-ink-soft"}`}>
    {t(message)}{(missing || limited) && <> <a href="https://www.google.com/chrome/" target="_blank" rel="noopener noreferrer" className="inline-flex min-h-10 items-center text-link underline">{t("plat.downloadChrome")}</a></>}
  </p>;
}

/** Compact account row; invalid sessions remain visible below the actions. */
function PlatformRow({
  p,
  onChanged,
  onLogin,
}: {
  p: PlatformState;
  onChanged: () => void;
  onLogin: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const { t } = useI18n();

  const platformName = PLATFORM_LABEL[p.key] || p.name?.trim() || p.key;

  const act = async (a: "login" | "check" | "logout" | "login/finish") => {
    if (a === "logout" && !confirm(t("plat.confirmRemove", { name: platformName })))
      return;
    if (a === "login") onLogin();
    setBusy(true);
    setActionError(null);
    try {
      await api.platformAction(p.key, a);
    } catch (e) {
      setActionError(e instanceof ApiError && e.code === "error.browser_missing" ? null : (e as Error).message);
    }
    setBusy(false);
    onChanged();
  };

  const waiting = p.login_state === "waiting";
  const checking = !!p.checking;
  const status = checking ? t("plat.checking") : waiting
    ? t("plat.waiting")
    : p.logged_in === true
    ? t("plat.loggedIn")
    : p.logged_in === false
    ? t("plat.notLoggedIn")
    : p.has_profile
    ? t("plat.saved")
    : t("plat.notConnected");

  const dot = waiting
    ? "bg-accent animate-pulse"
    : p.logged_in
    ? "bg-ok"
    : p.has_profile
    ? "bg-ink-soft"
    : "bg-line";

  const invalid = p.has_profile && p.logged_in === false && !waiting && !checking;
  const loginLabel = `${t(p.has_profile ? "plat.relogin" : "plat.login")}: ${platformName}`;
  const checkLabel = `${t("plat.check")}: ${platformName}`;
  const removeLabel = `${t("plat.remove")}: ${platformName}`;
  return (
    <li>
      <div className="flex min-h-9 items-center justify-between gap-2" title={`${platformName}: ${status}`}>
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${invalid ? "bg-danger" : dot}`} />
          <span className="text-sm font-medium text-ink">{platformName}</span>
          <span className="sr-only">{status}</span>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          {busy || checking ? <span role="status" aria-label={status} title={status} className="grid size-8 place-items-center"><Loader2 aria-hidden="true" className="size-3.5 animate-spin text-ink-soft" /></span> : <>
            {waiting && <Button size="sm" variant="outline" className="min-h-10" aria-label={`${t("plat.finishLogin")}: ${platformName}`} onClick={() => act("login/finish")}>{t("plat.finishLogin")}</Button>}
            {p.has_profile && !waiting && <IconButton icon={<RefreshCw className="size-3.5" />} label={checkLabel} title={checkLabel} variant="ghost" size="sm" className="size-8 p-0" onClick={() => act("check")} />}
            {p.has_profile && !waiting && <IconButton icon={<XIcon className="size-3.5" />} label={removeLabel} title={removeLabel} variant="ghost" size="sm" className="size-8 p-0" onClick={() => act("logout")} />}
            {p.logged_in !== true && !waiting && <IconButton icon={<LogIn className="size-3.5" />} label={loginLabel} title={`${loginLabel} · ${t("plat.openLogin", { name: platformName })}`} variant="ghost" size="sm" className="size-8 p-0 text-link" onClick={() => act("login")} />}
          </>}
        </div>
      </div>
      {invalid && <p className="pb-2 pl-4 text-xs leading-relaxed text-danger">{t("plat.sessionInvalid")}</p>}
      {(actionError || (p.login_error && p.login_error_code !== "error.browser_missing")) && <p role="alert" title={p.login_error ?? undefined} className="pb-2 pl-4 text-xs leading-relaxed text-danger">{actionError || serverMessage(p.login_error_code ?? undefined, p.login_error ?? "")}</p>}
    </li>
  );
}
