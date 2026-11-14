import { Globe, Search } from "lucide-react";
import { useId, useState } from "react";
import { api, auth, ApiError } from "../api";
import { LANGS, serverMessage, useI18n, type Lang } from "../i18n";
import { Button } from "./ui/Button";

interface Props {
  configError: string | null;
  signupOpen: boolean;
  onDone: () => void;
}

interface LoginError {
  code?: string;
  fallback: string;
  status?: number;
}

export default function Login({ configError, signupOpen, onDone }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [error, setError] = useState<LoginError | null>(null);
  const [busy, setBusy] = useState(false);
  const registering = mode === "register";
  const { t, lang, setLang } = useI18n();

  const loginTabId = useId();
  const registerTabId = useId();
  const panelId = useId();
  const emailId = useId();
  const passwordId = useId();

  const tabs: { id: string; key: "login" | "register"; label: string }[] = [
    { id: loginTabId, key: "login", label: t("login.login") },
    { id: registerTabId, key: "register", label: t("login.register") },
  ];

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token } = await (registering ? api.register(email, pw) : api.login(email, pw));
      auth.set(token);
      onDone();
    } catch (err) {
      if (err instanceof ApiError) {
        setError({
          code: err.code || (err.status === 0 ? "api.network" : undefined),
          fallback: typeof err.detail === "string" ? err.detail : err.message,
          status: err.status,
        });
      } else {
        setError({
          fallback: (err as Error).message || "",
        });
      }
    } finally {
      setBusy(false);
    }
  };

  const errorMessage = error
    ? serverMessage(error.code, error.fallback, error.status ? { status: error.status } : undefined)
    : "";

  return (
    <main className="relative flex min-h-full flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
      {/* Top Language Picker */}
      <div className="absolute top-4 right-4 sm:top-6 sm:right-6 flex items-center gap-2">
        <label
          className="relative flex items-center gap-1.5 rounded-full border border-line bg-surface/80 px-3 py-1.5 text-xs font-medium text-ink-soft shadow-xs transition-colors hover:bg-surface hover:text-ink focus-within:ring-2 focus-within:ring-accent focus-within:ring-offset-2 cursor-pointer"
          title={t("lang.label")}
        >
          <Globe className="size-3.5" />
          <span className="font-mono uppercase">{lang}</span>
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
      </div>

      <div className="mx-auto w-full max-w-md">
        {/* Paper Card Form Container */}
        <div className="border-y border-line py-8 sm:py-10">
          {/* Brand Header */}
          <div className="flex flex-col items-center text-center">
            <div className="relative mb-3 grid size-10 place-items-center rounded-full bg-primary shadow-sm">
              <Search className="size-5 text-primary-ink" strokeWidth={2.5} />
              <span className="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full bg-accent ring-2 ring-[var(--sheet)]" />
            </div>
            <h1 className="font-headline text-3xl font-normal tracking-tight text-ink sm:text-4xl">
              FeedLens
            </h1>
            <div className="rule-double my-4 w-full" />
            <p className="text-sm text-ink-soft">
              {registering ? t("login.registerHint") : t("login.loginHint")}
            </p>
          </div>

          {/* Mode Switcher Pills (khi signup được mở) */}
          {signupOpen && (
            <div
              className="mt-6 flex rounded-full border border-line bg-sunken p-1"
              role="tablist"
              aria-label={t("login.login")}
            >
              {tabs.map((tabItem, index) => {
                const isSelected = mode === tabItem.key;
                return (
                  <button
                    key={tabItem.key}
                    id={tabItem.id}
                    type="button"
                    role="tab"
                    aria-selected={isSelected}
                    aria-controls={panelId}
                    tabIndex={isSelected ? 0 : -1}
                    onClick={() => {
                      setMode(tabItem.key);
                      setError(null);
                    }}
                    onKeyDown={(e) => {
                      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                      e.preventDefault();
                      const next =
                        e.key === "Home"
                          ? 0
                          : e.key === "End"
                          ? tabs.length - 1
                          : (index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                      setMode(tabs[next].key);
                      setError(null);
                      e.currentTarget.parentElement
                        ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
                        [next]?.focus();
                    }}
                    className={`flex-1 rounded-full py-1.5 text-xs font-semibold transition-all interactive-tap ${
                      isSelected
                        ? "bg-surface text-ink shadow-xs"
                        : "text-ink-soft hover:text-ink"
                    }`}
                  >
                    {tabItem.label}
                  </button>
                );
              })}
            </div>
          )}

          {configError ? (
            <div role="alert" className="mt-6 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
              {serverMessage("error.config", configError)}
            </div>
          ) : (
            <form
              id={panelId}
              role="tabpanel"
              aria-labelledby={signupOpen ? (registering ? registerTabId : loginTabId) : undefined}
              onSubmit={submit}
              className="mt-6 space-y-4"
            >
              <div>
                <label
                  htmlFor={emailId}
                  className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-ink-soft cursor-pointer"
                >
                  {t("login.email")}
                </label>
                <input
                  id={emailId}
                  type="email"
                  className="field"
                  autoComplete="email"
                  required
                  placeholder="name@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div>
                <label
                  htmlFor={passwordId}
                  className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-ink-soft cursor-pointer"
                >
                  {registering ? t("login.passwordMin") : t("login.password")}
                </label>
                <input
                  id={passwordId}
                  type="password"
                  className="field"
                  required
                  minLength={registering ? 8 : undefined}
                  autoComplete={registering ? "new-password" : "current-password"}
                  placeholder="••••••••"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                />
              </div>

              {errorMessage && (
                <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-2.5 text-sm text-danger">
                  {errorMessage}
                </div>
              )}

              <Button
                type="submit"
                variant="primary"
                pill
                busy={busy}
                disabled={busy || !email || !pw}
                className="mt-6 w-full py-2.5 text-sm font-semibold"
              >
                {busy ? t("login.busy") : registering ? t("login.register") : t("login.login")}
              </Button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
