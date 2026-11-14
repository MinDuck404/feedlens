import { useCallback, useEffect, useRef, useState } from "react";
import { api, auth } from "./api";
import Composer from "./components/Composer";
import Login from "./components/Login";
import Settings from "./components/Settings";
import RunView from "./components/RunView";
import HistoryPage from "./components/HistoryPage";
import Sidebar from "./components/Sidebar";
import { Button } from "./components/ui/Button";
import { Skeleton, SkeletonCard } from "./components/ui/Skeleton";
import { useI18n } from "./i18n";
import { navigate, useRoute } from "./router";
import type { Me, Meta, PlatformState, Preferences, Run } from "./types";

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
      <div className="flex h-full w-full flex-col bg-paper md:flex-row">
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

function Workspace({ meta, onLogout }: { meta: Meta; onLogout?: () => void }) {
  const [platforms, setPlatforms] = useState<PlatformState[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const route = useRoute();
  const selected = route.page === "run" ? route.id : null;
  const [composerOpen, setComposerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [prefsError, setPrefsError] = useState("");
  const latestPrefs = useRef<Preferences | null>(null);
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

  const busy = runs.some((r) => !["done", "error"].includes(r.status));
  const waitingLogin = platforms.some((p) => p.login_state === "waiting");
  const cloud = meta.mode === "cloud";

  useEffect(() => {
    if (!busy && !waitingLogin && !cloud) return;
    const t = setInterval(
      () => {
        if (busy || cloud) refreshRuns();
        if (cloud) refreshMe();
        if (waitingLogin) refreshPlatforms();
      },
      busy || waitingLogin ? 2000 : 15000
    );
    return () => clearInterval(t);
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
        onNewRun={() => setComposerOpen(true)}
        onPlatformChanged={refreshPlatforms}
        onLogout={onLogout}
      />

      <main className="min-w-0 flex-1 overflow-y-auto">
        {Object.entries(workspaceErrors).map(([source, message]) => (
          <p key={source} role="alert" className="mt-3 px-6 text-sm text-danger">
            {message}{" "}
            <button
              onClick={() =>
                source === "me"
                  ? refreshMe()
                  : source === "platforms"
                  ? refreshPlatforms()
                  : refreshRuns()
              }
              className="underline font-medium"
            >
              {t("act.retry")}
            </button>
          </p>
        ))}

        {prefsError && (
          <p role="alert" className="mt-3 px-6 text-sm text-danger">
            {t(prefsError === "save" ? "prefs.saveFailed" : "api.network")}{" "}
            <button
              onClick={() =>
                prefsError === "save" && latestPrefs.current
                  ? savePrefs(latestPrefs.current)
                  : loadPrefs()
              }
              className="underline font-medium"
            >
              {t("act.retry")}
            </button>
          </p>
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
              tab={route.tab}
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
          ) : (
            <HomeLanding
              cloud={cloud}
              hasRuns={runs.length > 0}
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
          onClose={() => setComposerOpen(false)}
          onCreated={(id) => {
            setComposerOpen(false);
            navigate({ page: "run", id, tab: "digest" });
            refreshRuns();
          }}
          onOpenSettings={() => {
            setComposerOpen(false);
            setSettingsOpen(true);
          }}
        />
      )}

      {settingsOpen && (
        <Settings
          meta={meta}
          me={me}
          onClose={() => setSettingsOpen(false)}
          onChanged={refreshMe}
        />
      )}
    </div>
  );
}

/** Màn hình chào Home Landing (sửa code-audit #18: layout cuộn tự nhiên, không cố định chiều cao) */
function HomeLanding({
  cloud,
  hasRuns,
  onNewRun,
  onOpenSettings,
  loggingIn,
}: {
  cloud: boolean;
  hasRuns: boolean;
  onNewRun: () => void;
  onOpenSettings: () => void;
  loggingIn?: string;
}) {
  const { t } = useI18n();
  const [loginBefore, loginAfter] = t("home.loggingInFull").split("{name}");
  const steps = cloud
    ? [t("home.cloud1"), t("home.cloud2"), t("home.cloud3")]
    : [t("home.local1"), t("home.local2"), t("home.local3")];

  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-start px-6 py-12 md:py-20">
      {loggingIn && (
        <div
          role="status"
          className="paper-card mb-8 flex items-center gap-3 rounded-2xl px-5 py-4"
        >
          <span className="size-2.5 shrink-0 animate-pulse rounded-full bg-accent" />
          <p className="text-sm">
            {loginBefore}
            <b>{loggingIn}</b>
            {loginAfter} {t("home.loggingInHint")}
          </p>
        </div>
      )}

      <div className="mb-4 inline-flex items-center gap-2">
        <span className="inline-block size-2 rounded-full bg-accent" />
        <span className="font-mono text-xs uppercase tracking-wider text-ink-soft">
          FeedLens Engine
        </span>
      </div>

      <h1 className="text-4xl font-semibold tracking-[-0.035em] text-ink sm:text-5xl md:text-6xl leading-[1.08]">
        {t("home.title1")}
        <br />
        {t("home.title2")}
      </h1>

      <p className="mt-5 max-w-[52ch] text-base md:text-lg text-ink-soft leading-relaxed">
        {t("home.lead")}
      </p>

      <ol className="paper-card mt-8 divide-y divide-line overflow-hidden rounded-2xl shadow-xs">
        {steps.map((s, i) => (
          <li
            key={i}
            className="flex items-start gap-4 px-5 py-4 text-sm transition-colors hover:bg-sunken/40"
          >
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-sunken font-mono text-xs font-semibold text-ink-soft">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="pt-0.5 text-ink leading-relaxed">{s}</span>
          </li>
        ))}
      </ol>

      <div className="mt-8 flex flex-wrap items-center gap-3.5">
        <Button onClick={onNewRun} size="lg" variant="primary" pill>
          {t("act.newRun")}
        </Button>
        <Button onClick={onOpenSettings} size="lg" variant="outline" pill>
          {t("act.settings")}
        </Button>
        {hasRuns && (
          <>
            <span className="hidden md:inline text-sm text-ink-soft pl-1">
              {t("home.orOpen")}
            </span>
            <span className="inline md:hidden text-sm text-ink-soft pl-1">
              {t("home.orOpenMobile")}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
