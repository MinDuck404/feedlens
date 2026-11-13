import { useCallback, useEffect, useState } from "react";
import { api, auth } from "./api";
import Composer from "./components/Composer";
import Login from "./components/Login";
import RunView from "./components/RunView";
import Sidebar from "./components/Sidebar";
import type { Meta, PlatformState, Run } from "./types";

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
    return <Login configError={meta.config_error} onDone={() => setAuthed(true)} />;
  }
  return <Workspace meta={meta} onLogout={meta.auth_required ? () => { auth.clear(); setAuthed(false); } : undefined} />;
}

function Workspace({ meta, onLogout }: { meta: Meta; onLogout?: () => void }) {
  const [platforms, setPlatforms] = useState<PlatformState[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);

  const refreshPlatforms = useCallback(() => api.platforms().then(setPlatforms).catch(() => {}), []);
  const refreshRuns = useCallback(() => api.runs().then(setRuns).catch(() => {}), []);

  useEffect(() => { refreshPlatforms(); refreshRuns(); }, [refreshPlatforms, refreshRuns]);

  // Cập nhật định kỳ khi có lượt đang chạy, đang chờ đăng nhập, hoặc ở cloud (bot ở máy có thể đẩy lượt mới bất cứ lúc nào)
  const busy = runs.some((r) => !["done", "error"].includes(r.status));
  const waitingLogin = platforms.some((p) => p.login_state === "waiting");
  const cloud = meta.mode === "cloud";
  useEffect(() => {
    if (!busy && !waitingLogin && !cloud) return;
    const t = setInterval(() => {
      if (busy || cloud) refreshRuns();
      if (waitingLogin) refreshPlatforms();
    }, busy || waitingLogin ? 2000 : 15000);
    return () => clearInterval(t);
  }, [busy, waitingLogin, cloud, refreshRuns, refreshPlatforms]);

  return (
    <div className="flex h-full flex-col md:flex-row">
      <Sidebar
        cloud={cloud}
        platforms={platforms}
        runs={runs}
        selected={selected}
        onSelect={setSelected}
        onNewRun={() => setComposerOpen(true)}
        onPlatformChanged={refreshPlatforms}
        onLogout={onLogout}
      />
      <main className="min-w-0 flex-1 overflow-y-auto">
        {selected ? (
          <RunView key={selected} runId={selected} meta={meta}
            onDeleted={() => { setSelected(null); refreshRuns(); }} />
        ) : (
          <EmptyState cloud={cloud} hasRuns={runs.length > 0} onNewRun={() => setComposerOpen(true)} />
        )}
      </main>
      {composerOpen && (
        <Composer
          meta={meta}
          platforms={platforms}
          onClose={() => setComposerOpen(false)}
          onCreated={(id) => { setComposerOpen(false); setSelected(id); refreshRuns(); }}
        />
      )}
    </div>
  );
}

function EmptyState({ cloud, hasRuns, onNewRun }: { cloud: boolean; hasRuns: boolean; onNewRun: () => void }) {
  return (
    <div className="mx-auto flex h-full max-w-xl flex-col justify-center px-6 py-16">
      <h1 className="font-serif text-4xl leading-tight font-medium tracking-tight text-ink md:text-5xl">
        Để bot lướt thay bạn, rồi đọc bản tóm tắt trong năm phút.
      </h1>
      <p className="mt-5 max-w-prose text-ink-soft">
        {cloud
          ? "Bot chạy trên máy bạn, dùng Chrome và phiên đăng nhập của bạn, rồi gửi bài lên đây. Server chia bài theo loại, tóm tắt và lọc việc làm hợp với bạn."
          : "Đăng nhập một nền tảng ở cột bên trái, chọn bảng tin hoặc group, và FeedLens sẽ gom bài, chia theo loại, lọc ra việc làm hợp với bạn."}
      </p>
      <div className="mt-8 flex gap-3">
        <button onClick={onNewRun}
          className="rounded-lg bg-cobalt px-5 py-2.5 font-semibold text-cobalt-ink hover:opacity-90">
          Lướt mới
        </button>
        {hasRuns && <span className="self-center text-sm text-ink-soft">hoặc mở một lượt trong lịch sử</span>}
      </div>
    </div>
  );
}
