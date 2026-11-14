import { Search } from "lucide-react";
import { useState } from "react";
import { api, auth } from "../api";
import { useI18n } from "../i18n";

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
  const { t } = useI18n();

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
          <Search className="size-6 text-link" strokeWidth={2.75} /> FeedLens
        </div>
        <h1 className="mt-8 font-serif text-3xl font-medium">
          {registering ? t("login.registerTitle") : t("login.loginTitle")}
        </h1>
        <p className="mt-2 text-ink-soft">
          {registering ? t("login.registerHint") : t("login.loginHint")}
        </p>
        {configError ? (
          <p role="alert" className="mt-6 rounded-lg bg-surface p-4 text-sm text-danger">{configError}</p>
        ) : (
          <>
            <label className="mt-6 block">
              <span className="mb-1 block text-sm font-medium">{t("login.email")}</span>
              <input type="email" className="field" autoFocus autoComplete="email" required
                value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="mt-4 block">
              <span className="mb-1 block text-sm font-medium">{registering ? t("login.passwordMin") : t("login.password")}</span>
              <input type="password" className="field" required minLength={registering ? 8 : undefined}
                autoComplete={registering ? "new-password" : "current-password"}
                value={pw} onChange={(e) => setPw(e.target.value)} />
            </label>
            {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
            <button disabled={busy || !email || !pw}
              className="mt-5 w-full rounded-full bg-primary py-2.5 font-semibold text-primary-ink hover:opacity-90 disabled:opacity-50">
              {busy ? t("login.busy") : registering ? t("login.register") : t("login.login")}
            </button>
            {signupOpen && (
              <p className="mt-4 text-center text-sm text-ink-soft">
                {registering ? t("login.haveAccount") : t("login.noAccount")}{" "}
                <button type="button" onClick={() => { setMode(registering ? "login" : "register"); setError(""); }}
                  className="font-medium text-link hover:underline">
                  {registering ? t("login.login") : t("login.register")}
                </button>
              </p>
            )}
          </>
        )}
      </form>
    </main>
  );
}
