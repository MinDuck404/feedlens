import { useCallback, useEffect, useState } from "react";
import { api, auth } from "./api";
import Composer from "./components/Composer";
import Login from "./components/Login";
import Settings from "./components/Settings";
import RunView from "./components/RunView";
import HistoryPage from "./components/HistoryPage";
import Sidebar from "./components/Sidebar";
import { navigate, useRoute } from "./router";
import type { Me, Meta, PlatformState, Preferences, Run } from "./types";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [authed, setAuthed] = useState(() => !!auth.get());
  const [bootError, setBootError] = useState("");

  useEffect(() => {
    api.meta().then(setMeta).catch(() =>
      setBootError("Không kết nối được server FeedLens. Kiểm tra backend đang chạy rồi tải lại trang."),
    );
    const onLogout = () => setAuthed(false);
    window.addEventListener("feedlens:logout", onLogout);
    return () => window.removeEventListener("feedlens:logout", onLogout);
  }, []);

  if (bootError) {
    return (
      <main className="grid h-full place-items-center p-6">
        <p className="max-w-md text-center text-ink-soft">{bootError}</p>
      </main>
    );
  }
  if (!meta) return null;
  if (meta.auth_required && !authed) {
    return <Login configError={meta.config_error} signupOpen={meta.signup_open} onDone={() => setAuthed(true)} />;
  }
  return <Workspace meta={meta} onLogout={meta.auth_required ? () => { auth.clear(); setAuthed(false); } : undefined} />;
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

  const refreshMe = useCallback(() => api.me().then(setMe).catch(() => {}), []);
  const refreshPlatforms = useCallback(() => api.platforms().then(setPlatforms).catch(() => {}), []);
  const refreshRuns = useCallback(() => api.runs().then(setRuns).catch(() => {}), []);

  useEffect(() => {
    refreshPlatforms(); refreshRuns(); refreshMe();
    api.preferences().then(setPrefs).catch(() => setPrefs({}));
  }, [refreshPlatforms, refreshRuns, refreshMe]);

  // Cập nhật định kỳ khi có lượt đang chạy, đang chờ đăng nhập, hoặc ở cloud (bot ở máy có thể đẩy lượt mới bất cứ lúc nào)
  const busy = runs.some((r) => !["done", "error"].includes(r.status));
  const waitingLogin = platforms.some((p) => p.login_state === "waiting");
  const cloud = meta.mode === "cloud";
  useEffect(() => {
    if (!busy && !waitingLogin && !cloud) return;
    const t = setInterval(() => {
      if (busy || cloud) refreshRuns();
      if (cloud) refreshMe();
      if (waitingLogin) refreshPlatforms();
    }, busy || waitingLogin ? 2000 : 15000);
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
        {route.page === "run" ? (
          <RunView key={route.id} runId={route.id} meta={meta} tab={route.tab}
            onTab={(tab) => navigate({ page: "run", id: route.id, tab }, { replace: true })}
            onDeleted={() => { navigate({ page: "history" }, { replace: true }); refreshRuns(); }} />
        ) : route.page === "history" ? (
          <HistoryPage runs={runs} onOpen={(id) => navigate({ page: "run", id, tab: "digest" })}
            onNewRun={() => setComposerOpen(true)} />
        ) : (
          <EmptyState cloud={cloud} hasRuns={runs.length > 0} onNewRun={() => setComposerOpen(true)}
            onOpenSettings={() => setSettingsOpen(true)}
            loggingIn={platforms.find((p) => p.login_state === "waiting")?.name} />
        )}
      </main>
      {composerOpen && prefs && (
        <Composer
          meta={meta}
          me={me}
          platforms={platforms}
          prefs={prefs}
          onPrefsChange={setPrefs}
          onClose={() => setComposerOpen(false)}
          onCreated={(id) => { setComposerOpen(false); navigate({ page: "run", id, tab: "digest" }); refreshRuns(); }}
          onOpenSettings={() => { setComposerOpen(false); setSettingsOpen(true); }}
        />
      )}
      {settingsOpen && (
        <Settings meta={meta} me={me} onClose={() => setSettingsOpen(false)} onChanged={refreshMe} />
      )}
    </div>
  );
}

function EmptyState({ cloud, hasRuns, onNewRun, onOpenSettings, loggingIn }: {
  cloud: boolean; hasRuns: boolean; onNewRun: () => void; onOpenSettings: () => void; loggingIn?: string;
}) {
  const steps = cloud
    ? ["Thêm API key AI và kết nối agent trong Cài đặt.", "Bật agent trên máy (hoặc lưu cookie để lướt bằng server).", "Bấm Lướt mới, chọn bảng tin hoặc nhóm."]
    : ["Bấm Đăng nhập cạnh Facebook ở cột trái, đăng nhập trong cửa sổ hiện ra.", "Dán API key Gemini, ChatGPT hoặc Claude trong Cài đặt.", "Bấm Lướt mới, chọn bảng tin hoặc các nhóm cần lướt."];
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col justify-center px-6 py-16">
      {loggingIn && (
        <div role="status" className="paper-card mb-8 flex items-center gap-3 rounded-2xl px-5 py-4">
          <span className="size-2.5 shrink-0 animate-pulse rounded-full bg-accent" />
          <p className="text-sm">
            Đang mở cửa sổ đăng nhập <b>{loggingIn}</b>. Đăng nhập trong cửa sổ Chrome vừa hiện ra (kể cả xác minh 2 bước);
            xong thì cửa sổ tự đóng.
          </p>
        </div>
      )}
      <h1 className="text-5xl leading-[1.02] font-semibold tracking-[-0.035em] text-ink md:text-7xl">
        đọc ít hơn,<br />biết nhiều hơn.
      </h1>
      <p className="mt-6 max-w-[52ch] text-lg text-ink-soft">
        FeedLens lướt bảng tin và các nhóm thay bạn, chia bài theo loại, tóm tắt, và lọc ra việc làm hợp với bạn.
      </p>
      <ol className="paper-card mt-10 divide-y divide-line rounded-2xl">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-4 px-5 py-3.5 text-sm">
            <span className="font-mono text-ink-soft">{String(i + 1).padStart(2, "0")}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <button onClick={onNewRun}
          className="rounded-full bg-primary px-6 py-3 font-semibold text-primary-ink hover:opacity-90">
          Lướt mới
        </button>
        <button onClick={onOpenSettings}
          className="rounded-full border border-line px-5 py-3 font-medium hover:border-ink">
          Cài đặt
        </button>
        {hasRuns && <span className="text-sm text-ink-soft">hoặc mở một lượt ở cột trái</span>}
      </div>
    </div>
  );
}
