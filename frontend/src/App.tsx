import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, auth } from "./api/client";
import Composer from "./features/composer/Composer";
import Login from "./features/auth/Login";
import Settings from "./features/settings/Settings";
import RunView from "./features/run/RunView";
import HistoryPage from "./features/history/HistoryPage";
import AskPage from "./features/ask/AskPage";
import TrendsPage from "./features/trends/TrendsPage";
import Sidebar from "./features/sidebar/Sidebar";
import { ThemeSwitch } from "./features/settings/PreferenceMenus";
import { Button } from "./components/ui/Button";
import { Skeleton, SkeletonCard } from "./components/ui/Skeleton";
import { useI18n } from "./i18n";
import { navigate, routeHref, useRoute } from "./router";
import type { Me, Meta, PlatformState, Preferences, Run, RunRequest } from "./api/types";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [authed, setAuthed] = useState(() => !!auth.get());
  const [bootError, setBootError] = useState(false);
  const { t } = useI18n();

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setBootError(true));
    const onLogout = () => setAuthed(false);
    window.addEventListener("feedlens:logout", onLogout);
    return () => window.removeEventListener("feedlens:logout", onLogout);
  }, []);

  if (bootError) {
    return (
      <main className="grid h-full place-items-center p-6">
        <div className="paper-card max-w-md rounded-2xl p-8 text-center">
          <p className="text-base text-ink-soft">{t("app.bootError")}</p>
          <div className="mt-6 flex justify-center">
            <Button
              variant="outline"
              onClick={() => {
                setBootError(false);
                api.meta().then(setMeta).catch(() => setBootError(true));
              }}
            >
              {t("act.retry")}
            </Button>
          </div>
        </div>
      </main>
    );
  }

  // Boot Loading State (Skeleton thay vì màn hình trắng, chuẩn brief & audit)
  if (!meta) {
    return (
      <div className="flex h-full w-full flex-col bg-bg md:flex-row">
        {/* Mobile Top Skeleton */}
        <div className="flex h-14 w-full items-center justify-between border-b border-line px-4 md:hidden">
          <Skeleton width="110px" height="24px" rounded="full" />
          <Skeleton width="80px" height="32px" rounded="full" />
        </div>
        {/* Desktop Sidebar Skeleton */}
        <div className="hidden h-full w-72 shrink-0 flex-col border-r border-line p-5 md:flex space-y-6">
          <div className="flex items-center justify-between">
            <Skeleton width="120px" height="28px" rounded="full" />
            <Skeleton width="80px" height="32px" rounded="full" />
          </div>
          <div className="flex gap-2">
            <Skeleton width="70px" height="28px" rounded="full" />
            <Skeleton width="70px" height="28px" rounded="full" />
          </div>
          <div className="space-y-3 pt-4">
            <Skeleton width="90px" height="14px" />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </div>
        {/* Main Content Skeleton */}
        <div className="flex-1 min-w-0 p-6 md:p-12 space-y-6">
          <Skeleton height="42px" rounded="lg" className="w-full max-w-[280px]" />
          <Skeleton height="20px" className="w-full max-w-[450px]" />
          <div className="pt-6 space-y-4 max-w-2xl w-full">
            <Skeleton height="72px" rounded="xl" className="w-full" />
            <Skeleton height="72px" rounded="xl" className="w-full" />
            <Skeleton height="72px" rounded="xl" className="w-full" />
          </div>
        </div>
      </div>
    );
  }

  if (meta.auth_required && !authed) {
    return (
      <Login
        configError={meta.config_error}
        signupOpen={meta.signup_open}
        onDone={() => setAuthed(true)}
      />
    );
  }

  return (
    <Workspace
      meta={meta}
      onLogout={
        meta.auth_required
          ? () => {
              auth.clear();
              setAuthed(false);
            }
          : undefined
      }
    />
  );
}

export function workspacePollDelay(busy: boolean, waitingLogin: boolean, hidden: boolean): number {
  return waitingLogin ? 2000 : hidden || !busy ? 15000 : 5000;
}

function Workspace({ meta, onLogout }: { meta: Meta; onLogout?: () => void }) {
  const [platforms, setPlatforms] = useState<PlatformState[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const route = useRoute();
  const selected = route.page === "run" ? route.id : null;
  const [composerOpen, setComposerOpen] = useState(false);
  const [rerunRequest, setRerunRequest] = useState<RunRequest | undefined>();
  // Mọi đường đóng form (huỷ, tạo xong, mở Cài đặt) đều bỏ cài đặt chạy lại, để lần mở sau là form mới.
  useEffect(() => { if (!composerOpen) setRerunRequest(undefined); }, [composerOpen]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<string>();
  const [me, setMe] = useState<Me | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [prefsError, setPrefsError] = useState("");
  const latestPrefs = useRef<Preferences | null>(null);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.isComposing || document.querySelector('[role="dialog"]')) return;
      const editable = (event.target as HTMLElement)?.closest("input,textarea,select,[contenteditable=true]");
      if ((event.key === "/" && !editable) || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k")) {
        event.preventDefault(); if (!location.hash.startsWith("#/ask")) navigate({ page: "ask" });
        window.setTimeout(() => document.querySelector<HTMLInputElement>("[data-ask-input]")?.focus(), 0);
      }
    };
    window.addEventListener("keydown", shortcut); return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const [workspaceErrors, setWorkspaceErrors] = useState<Record<string, string>>({});
  const { t } = useI18n();

  const savePrefs = useCallback((p: Preferences) => {
    latestPrefs.current = p;
    setPrefs(p);
    api
      .savePreferences(p)
      .then(() => {
        if (latestPrefs.current === p) setPrefsError("");
      })
      .catch(() => {
        if (latestPrefs.current === p) setPrefsError("save");
      });
  }, []);

  const loadPrefs = () =>
    api
      .preferences()
      .then((p) => {
        setPrefs(p);
        setPrefsError("");
      })
      .catch(() => setPrefsError("load"));

  const clearError = (source: string) =>
    setWorkspaceErrors((errors) => {
      if (!(source in errors)) return errors;
      const next = { ...errors };
      delete next[source];
      return next;
    });

  const refreshMe = useCallback(
    () =>
      api
        .me()
        .then((v) => {
          setMe(v);
          clearError("me");
        })
        .catch((e) => setWorkspaceErrors((s) => ({ ...s, me: e.message }))),
    []
  );

  const refreshPlatforms = useCallback(
    () =>
      api
        .platforms()
        .then((v) => {
          setPlatforms(v);
          clearError("platforms");
        })
        .catch((e) => setWorkspaceErrors((s) => ({ ...s, platforms: e.message }))),
    []
  );

  const refreshRuns = useCallback(
    () =>
      api
        .runs()
        .then((v) => {
          setRuns(v);
          clearError("runs");
        })
        .catch((e) => setWorkspaceErrors((s) => ({ ...s, runs: e.message }))),
    []
  );

  useEffect(() => {
    refreshPlatforms();
    refreshRuns();
    refreshMe();
    loadPrefs();
  }, [refreshPlatforms, refreshRuns, refreshMe]);

  const busy = runs.some((r) => !["done", "error", "analysis_failed"].includes(r.status));
  const waitingLogin = platforms.some((p) => p.login_state === "waiting" || p.checking);
  const cloud = meta.mode === "cloud";

  useEffect(() => {
    if (!busy && !waitingLogin && !cloud) return;
    let timer: ReturnType<typeof setInterval>;
    const schedule = () => {
      clearInterval(timer);
      timer = setInterval(() => {
        if (busy || cloud) refreshRuns();
        if (cloud) refreshMe();
        if (waitingLogin) refreshPlatforms();
      }, workspacePollDelay(busy, waitingLogin, document.hidden));
    };
    schedule();
    document.addEventListener("visibilitychange", schedule);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", schedule); };
  }, [busy, waitingLogin, cloud, refreshRuns, refreshPlatforms, refreshMe]);

  return (
    <div className="flex h-full flex-col md:flex-row">
      <Sidebar
        cloud={cloud}
        email={meta.auth_required ? me?.email : undefined}
        agentOnline={cloud ? !!me?.agent.online : undefined}
        onOpenSettings={() => setSettingsOpen(true)}
        platforms={platforms}
        runs={runs}
        selected={selected}
        page={route.page}
        onSelect={(id) => navigate({ page: "run", id, tab: "digest" })}
        onGoHome={() => navigate({ page: "home" })}
        onGoHistory={() => navigate({ page: "history" })}
        onGoTrends={() => navigate({ page: "trends" })}
        onGoAsk={() => navigate({ page: "ask" })}
        onNewRun={() => setComposerOpen(true)}
        onPlatformChanged={refreshPlatforms}
        onLogout={onLogout}
      />

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 z-20 hidden h-12 items-center justify-end bg-bg/90 px-5 backdrop-blur-sm md:flex"><ThemeSwitch /></div>
        {(Object.keys(workspaceErrors).length > 0 || prefsError) && (
          <div className={`mx-auto space-y-2 px-5 pt-4 md:px-10 ${route.page === "home" ? "max-w-2xl" : route.page === "history" ? "max-w-4xl" : "max-w-5xl"}`}>
        {Object.entries(workspaceErrors).map(([source, message]) => (
          <div
            key={source}
            role="alert"
            className="flex items-center justify-between gap-3 border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
          >
            <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{message}</span>
            <button
              onClick={() =>
                source === "me"
                  ? refreshMe()
                  : source === "platforms"
                  ? refreshPlatforms()
                  : refreshRuns()
              }
              className="shrink-0 rounded-full bg-danger/15 px-3 py-1 text-xs font-semibold hover:bg-danger/25 transition-colors"
            >
              {t("act.retry")}
            </button>
          </div>
        ))}

        {prefsError && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
          >
            <span className="font-medium">
              {t(prefsError === "save" ? "prefs.saveFailed" : "api.network")}
            </span>
            <button
              onClick={() =>
                prefsError === "save" && latestPrefs.current
                  ? savePrefs(latestPrefs.current)
                  : loadPrefs()
              }
              className="shrink-0 rounded-full bg-danger/15 px-3 py-1 text-xs font-semibold hover:bg-danger/25 transition-colors"
            >
              {t("act.retry")}
            </button>
          </div>
        )}

          </div>
        )}

        {/* Page Transition Wrapper */}
        <div
          key={route.page + (route.page === "run" ? `-${route.id}` : "")}
          className="page-enter min-h-full"
        >
          {route.page === "run" ? (
            <RunView
              key={route.id}
              runId={route.id}
              meta={meta}
              prefs={prefs}
              tab={route.tab}
              onAnalysisStarted={refreshRuns}
              onRerun={(request) => { setRerunRequest(request); setComposerOpen(true); }}
              onTab={(tab) =>
                navigate({ page: "run", id: route.id, tab }, { replace: true })
              }
              onDeleted={() => {
                navigate({ page: "history" }, { replace: true });
                refreshRuns();
              }}
            />
          ) : route.page === "history" ? (
            <HistoryPage
              runs={runs}
              onOpen={(id) => navigate({ page: "run", id, tab: "digest" })}
              onNewRun={() => setComposerOpen(true)}
            />
          ) : route.page === "ask" ? (
            <AskPage key={routeHref(route)} initialFilters={route.filters} account={cloud ? me?.email ?? "" : "local"} onNewRun={() => setComposerOpen(true)} onSettings={() => setSettingsOpen(true)} />
          ) : route.page === "trends" ? (
            <TrendsPage
              onNewRun={() => setComposerOpen(true)}
            />
          ) : (
            <HomeLanding
              cloud={cloud}
              onNewRun={() => setComposerOpen(true)}
              onOpenSettings={() => setSettingsOpen(true)}
              loggingIn={platforms.find((p) => p.login_state === "waiting")?.name}
            />
          )}
        </div>
      </main>

      {composerOpen && prefs && (
        <Composer
          meta={meta}
          me={me}
          platforms={platforms}
          prefs={prefs}
          onPrefsChange={savePrefs}
          initialRequest={rerunRequest}
          onClose={() => setComposerOpen(false)}
          onCreated={(id) => {
            setComposerOpen(false);
            navigate({ page: "run", id, tab: "digest" });
            refreshRuns();
          }}
          onOpenSettings={(tab) => {
            setSettingsTab(tab);
            setComposerOpen(false);
            setSettingsOpen(true);
          }}
        />
      )}

      {settingsOpen && (
        <Settings
          initialTab={settingsTab}
          meta={meta}
          me={me}
          prefs={prefs}
          onPrefsChange={savePrefs}
          onClose={() => { setSettingsOpen(false); setSettingsTab(undefined); }}
          onChanged={() => { refreshMe(); window.dispatchEvent(new Event("feedlens:aiChanged")); }}
        />
      )}
    </div>
  );
}

/** Màn hình chào Home Landing theo phong cách báo in Fiorinda */
function HomeLanding({
  cloud,
  onNewRun,
  onOpenSettings,
  loggingIn,
}: {
  cloud: boolean;
  onNewRun: () => void;
  onOpenSettings: () => void;
  loggingIn?: string;
}) {
  const { t, locale } = useI18n();
  const [loginBefore, loginAfter] = t("home.loggingInFull").split("{name}");
  const steps = cloud
    ? [t("home.cloud1"), t("home.cloud2"), t("home.cloud3")]
    : [t("home.local1"), t("home.local2"), t("home.local3")];

  const todayStr = useMemo(() => {
    return new Date().toLocaleDateString(locale, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }, [locale]);

  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-start px-6 py-10 md:py-16">
      {loggingIn && (
        <div
          role="status"
          className="paper-card mb-8 flex items-center gap-3 rounded-2xl px-5 py-4 border border-line"
        >
          <span className="size-2.5 shrink-0 animate-pulse rounded-full bg-accent" />
          <p className="text-sm">
            {loginBefore}
            <b>{loggingIn}</b>
            {loginAfter} {t("home.loggingInHint")}
          </p>
        </div>
      )}

      {/* Newspaper Masthead Eyebrow Header */}
      <header className="masthead mb-8">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-accent" />
            <span className="font-semibold text-ink">FeedLens</span>
            <span className="hidden sm:inline text-line">•</span>
            <span className="hidden sm:inline">{t("home.edition")}</span>
          </div>
          <time className="font-sans text-ink-soft">{todayStr}</time>
        </div>
      </header>

      {/* Main Newspaper Headline */}
      <h1 className="font-headline text-4xl font-normal tracking-tight text-ink sm:text-5xl md:text-6xl leading-[1.12]">
        <span className="block">{t("home.title1")}</span>
        <span className="block text-accent font-serif italic">{t("home.title2")}</span>
      </h1>

      <div className="rule-double my-6" />

      {/* Editorial Lead Paragraph */}
      <p className="prose-reading text-base md:text-lg text-ink-soft leading-relaxed">
        {t("home.lead")}
      </p>

      {/* Table of Contents / 3 Steps (mục lục báo in, bớt card) */}
      <section className="mt-8 border-t border-b border-line py-5">
        <h2 className="mb-3 text-xs font-semibold text-ink-soft">
          {t("home.index")}
        </h2>
        <ol className="divide-y divide-line/70">
          {steps.map((s, i) => (
            <li
              key={i}
              className="flex items-baseline gap-4 py-3 group transition-colors hover:bg-sunken/40 px-2 -mx-2 rounded-lg"
            >
              <span className="font-headline text-base font-semibold text-accent shrink-0 tabular-nums">
                0{i + 1}
              </span>
              <span className="text-sm font-normal text-ink leading-relaxed">
                {!cloud && i === 0 ? <><span className="md:hidden">{t("home.local1Mobile")}</span><span className="hidden md:inline">{s}</span></> : s}
              </span>
            </li>
          ))}
        </ol>
      </section>

      {/* Action Bar */}
      <div className="mt-8 flex flex-wrap items-center gap-3.5">
        <Button onClick={onNewRun} size="lg" variant="primary" pill>
          {t("act.newRun")}
        </Button>
        <Button onClick={onOpenSettings} size="lg" variant="outline" pill>
          {t("act.settings")}
        </Button>
      </div>
    </div>
  );
}
