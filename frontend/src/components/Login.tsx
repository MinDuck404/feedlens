import { Search } from "lucide-react";
import { useState } from "react";
import { api, auth } from "../api";

interface Props {
  configError: string | null;
  signupOpen: boolean;
  onDone: () => void;
}

export default function Login({ configError, signupOpen, onDone }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const registering = mode === "register";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { token } = await (registering ? api.register(email, pw) : api.login(email, pw));
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
        <h1 className="mt-8 font-serif text-3xl font-medium">
          {registering ? "Tạo tài khoản để bắt đầu." : "Bản tóm tắt của bạn đang chờ."}
        </h1>
        <p className="mt-2 text-ink-soft">
          {registering
            ? "API key AI và lịch sử lướt được lưu riêng cho tài khoản của bạn."
            : "Đăng nhập bằng email đã đăng ký."}
        </p>
        {configError ? (
          <p role="alert" className="mt-6 rounded-lg bg-surface p-4 text-sm text-danger">{configError}</p>
        ) : (
          <>
            <label className="mt-6 block">
              <span className="mb-1 block text-sm font-medium">Email</span>
              <input type="email" className="field" autoFocus autoComplete="email" required
                value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="mt-4 block">
              <span className="mb-1 block text-sm font-medium">Mật khẩu{registering && ", ít nhất 8 ký tự"}</span>
              <input type="password" className="field" required minLength={registering ? 8 : undefined}
                autoComplete={registering ? "new-password" : "current-password"}
                value={pw} onChange={(e) => setPw(e.target.value)} />
            </label>
            {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
            <button disabled={busy || !email || !pw}
              className="mt-5 w-full rounded-lg bg-cobalt py-2.5 font-semibold text-cobalt-ink hover:opacity-90 disabled:opacity-50">
              {busy ? "Đang xử lý…" : registering ? "Tạo tài khoản" : "Đăng nhập"}
            </button>
            {signupOpen && (
              <p className="mt-4 text-center text-sm text-ink-soft">
                {registering ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
                <button type="button" onClick={() => { setMode(registering ? "login" : "register"); setError(""); }}
                  className="font-medium text-cobalt hover:underline">
                  {registering ? "Đăng nhập" : "Tạo tài khoản"}
                </button>
              </p>
            )}
          </>
        )}
      </form>
    </main>
  );
}
