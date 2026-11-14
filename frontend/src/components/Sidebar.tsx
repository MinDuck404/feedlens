import {
  Globe,
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
import { api } from "../api";
import { PLATFORM_LABEL } from "../categories";
import { LANGS, useI18n, type Key, type Lang } from "../i18n";
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
          onSelect={(id) => handleMobileNav(() => props.onSelect(id))}
          onNewRun={() => handleMobileNav(props.onNewRun)}
          onOpenSettings={() => handleMobileNav(props.onOpenSettings)}
        />
      </Sheet>

      {/* Desktop Sidebar (>= 768px): cố định thanh bên trái */}
      <aside className="hidden h-full w-72 shrink-0 flex-col border-r border-line bg-bg/50 md:flex">
        <div className="flex items-center justify-between px-5 pt-5 pb-4">
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
  onPlatformChanged,
  onLogout,
}: Props) {
  const { t, lang, setLang } = useI18n();

  const navCls =
    "rounded-full px-3.5 py-1.5 text-sm font-medium transition-all interactive-tap text-ink-soft hover:text-ink hover:bg-sunken/60 aria-[current=page]:bg-primary aria-[current=page]:text-primary-ink aria-[current=page]:shadow-xs";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Navigation Pills */}
      <nav className="flex gap-1.5 px-4 pb-4" aria-label={t("nav.label")}>
        <a
          href="#/"
          aria-current={page === "home" ? "page" : undefined}
          className={navCls}
          onClick={(e) => {
            e.preventDefault();
            onGoHome();
          }}
        >
          {t("nav.home")}
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
          {t("nav.history")}
        </a>
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
        <section className="px-4 pb-4">
          <h2 className="mb-2 font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {t("sb.accounts")}
          </h2>
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
      <section className="flex min-h-0 flex-1 flex-col border-t border-line px-3 pt-4">
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
          <ul className="-mx-1 flex-1 space-y-1 overflow-y-auto px-1 pb-4">
            {runs.map((r) => {
              const q = r.request;
              const src =
                q.source_type === "feed" ? t("sb.feed") : q.sources[0] ?? "";
              const isSelected = page === "run" && selected === r.id;

              return (
                <li key={r.id}>
                  <button
                    onClick={() => onSelect(r.id)}
                    aria-current={isSelected}
                    className={`group relative w-full rounded-xl border px-3 py-2.5 text-left transition-all interactive-tap ${
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
      <div className="flex items-center gap-2 border-t border-line px-4 py-3 text-sm bg-bg/60">
        <span
          className="min-w-0 flex-1 truncate text-xs font-medium text-ink-soft"
          title={email ?? t("sb.thisMachine")}
        >
          {email ?? t("sb.thisMachine")}
        </span>

        {/* Language Picker với Focus Ring hoàn chỉnh (code-audit #15) */}
        <label
          className="relative grid size-8 place-items-center rounded-lg text-ink-soft transition-colors hover:bg-sunken hover:text-ink focus-within:ring-2 focus-within:ring-accent focus-within:ring-offset-2 outline-none cursor-pointer"
          title={t("lang.label")}
        >
          <Globe className="size-4" />
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as Lang)}
            aria-label={t("lang.label")}
            className="absolute inset-0 cursor-pointer opacity-0"
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <span
          aria-hidden
          className="-ml-1 font-mono text-[11px] font-semibold text-ink-soft uppercase"
        >
          {lang}
        </span>

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
  );
}

/** Hàng tài khoản nền tảng với bố cục 2 hàng: Tên và Trạng thái không bao giờ bị cắt xén */
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
  const { t } = useI18n();

  const platformName = PLATFORM_LABEL[p.key] || p.name?.trim() || p.key;

  const act = async (a: "login" | "check" | "logout") => {
    if (a === "logout" && !confirm(t("plat.confirmRemove", { name: platformName })))
      return;
    if (a === "login") onLogin();
    setBusy(true);
    try {
      await api.platformAction(p.key, a);
    } catch (e) {
      alert((e as Error).message);
    }
    setBusy(false);
    onChanged();
  };

  const waiting = p.login_state === "waiting";
  const status = waiting
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

  return (
    <li className="py-2.5">
      {/* Hàng 1: Dot + Tên nền tảng (không bị truncate/che khuất) + Tối đa IconButton nhỏ (refresh, remove) */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`size-2 shrink-0 rounded-full ${dot}`} />
          <span className="text-sm font-semibold text-ink">{platformName}</span>
        </div>

        <div className="flex shrink-0 items-center gap-0.5">
          {busy ? (
            <Loader2 className="size-4 animate-spin text-ink-soft" />
          ) : (
            <>
              {p.has_profile && (
                <IconButton
                  icon={<RefreshCw className="size-3.5" />}
                  label={t("plat.check")}
                  variant="ghost"
                  size="sm"
                  className="size-7 p-0 outline-none focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  onClick={() => act("check")}
                />
              )}

              {p.has_profile && (
                <IconButton
                  icon={<XIcon className="size-3.5" />}
                  label={t("plat.remove")}
                  variant="ghost"
                  size="sm"
                  className="size-7 p-0 outline-none focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  onClick={() => act("logout")}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Hàng 2: Trạng thái kết nối + Nút có chữ (Đăng nhập lại / Đăng nhập) chuyển xuống đây */}
      <div className="mt-1 flex flex-wrap items-center justify-between gap-1.5 pl-4">
        <span className="font-sans text-xs text-ink-soft">{status}</span>

        {!p.logged_in && !waiting && !busy && (
          <button
            type="button"
            onClick={() => act("login")}
            title={t("plat.openLogin", { name: platformName })}
            className="flex shrink-0 items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs font-medium text-ink transition-colors hover:border-ink hover:text-link interactive-tap shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <LogIn className="size-3 text-accent" />
            <span>{p.has_profile ? t("plat.relogin") : t("plat.login")}</span>
          </button>
        )}
      </div>
    </li>
  );
}
