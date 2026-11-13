import { Search } from "lucide-react";
import { useState } from "react";
import { api, auth } from "../api";

export default function Login({ configError, onDone }: { configError: string | null; onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { token } = await api.login(pw);
      auth.set(token);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-full place-items-center px-4 py-16">
      <form onSubmit={submit} className="w-full max-w-sm">
        <div className="flex items-center gap-2 text-xl font-bold tracking-tight">
          <Search className="size-6 text-cobalt" strokeWidth={2.75} /> FeedLens
        </div>
        <h1 className="mt-8 font-serif text-3xl font-medium">Bản tóm tắt của bạn đang chờ.</h1>
        <p className="mt-2 text-ink-soft">Nhập mật khẩu đã đặt cho server này.</p>
        {configError ? (
          <p role="alert" className="mt-6 rounded-lg bg-surface p-4 text-sm text-danger">{configError}</p>
        ) : (
          <>
            <label className="mt-6 block">
              <span className="mb-1 block text-sm font-medium">Mật khẩu</span>
              <input type="password" className="field" autoFocus autoComplete="current-password"
                value={pw} onChange={(e) => setPw(e.target.value)} />
            </label>
            {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
            <button disabled={busy || !pw}
              className="mt-5 w-full rounded-lg bg-cobalt py-2.5 font-semibold text-cobalt-ink hover:opacity-90 disabled:opacity-50">
              {busy ? "Đang kiểm tra…" : "Đăng nhập"}
            </button>
          </>
        )}
      </form>
    </main>
  );
}
