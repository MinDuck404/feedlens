import { Check, Copy, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { parseTimestamp } from "../logic";
import { API_BASE, api } from "../api";
import type { AIProviderInfo, Me, Meta } from "../types";
import CookieSessions from "./CookieSessions";
import { useI18n } from "../i18n";
import { Sheet, Button, SkeletonCard } from "./ui";

interface Props {
  meta: Meta;
  me: Me | null;
  onClose: () => void;
  onChanged: () => void;
}

export default function Settings({ meta, me, onClose, onChanged }: Props) {
  const [open, setOpen] = useState(true);
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const { t } = useI18n();
  const reload = () => api.providers().then((p) => { setProviders(p); setLoadError(""); }).finally(() => setLoading(false));

  const handleClose = useCallback(() => {
    setOpen(false);
    setTimeout(() => {
      onClose();
    }, 200);
  }, [onClose]);

  useEffect(() => {
    reload().catch((e) => setLoadError(e.message));  // một lần khi mở, không chạy lại mỗi lần App cập nhật
  }, []);

  return (
    <Sheet
      open={open}
      onClose={handleClose}
      title={t("set.title")}
      closeAriaLabel={t("act.close")}
      maxWidth="max-w-lg"
      className="[&_h2]:font-headline"
    >
      <div>
        <h3 className="font-headline text-2xl font-semibold">{t("set.keys")}</h3>
        <p className="mt-2 text-sm leading-relaxed text-pretty text-ink-soft">{t("set.keysHint")}</p>
        <ul className="mt-4 space-y-3">
          {loadError && <li role="alert" className="mt-2 text-sm text-danger">{loadError} <button onClick={() => reload().catch((e) => setLoadError(e.message))}>{t("act.retry")}</button></li>}
          {loading && <li role="status" aria-label={t("act.loading")}><div aria-hidden="true"><SkeletonCard /></div></li>}
          {providers.filter((p) => p.key !== "offline").map((p) => (
            <KeyRow key={p.key} p={p} onChanged={async () => { await reload(); onChanged(); }} />
          ))}
        </ul>
      </div>
      {meta.mode === "cloud" && me && <AgentSection me={me} onChanged={onChanged} />}
      {meta.server_scrape && <CookieSessions />}
    </Sheet>
  );
}

function KeyRow({ p, onChanged }: { p: AIProviderInfo; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { t } = useI18n();

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await api.saveKey(p.key, value);
      setValue("");
      setEditing(false);
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!confirm(t("set.confirmDeleteKey", { name: p.name }))) return;
    if (busy) return;
    setBusy(true); setError("");
    try { await api.deleteKey(p.key); await onChanged(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <li className="border-b border-line py-4">
      <div className="flex min-w-0 flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0 [overflow-wrap:anywhere]">
          <div className="font-medium">{p.name}</div>
          <div className="text-xs text-ink-soft">
            {p.configured
              ? p.source === "env" ? t("set.envKey") : t("set.savedKey", { hint: p.hint })
              : t("set.noKey")}
          </div>
        </div>
        <div className="flex max-w-full flex-wrap items-center gap-2 text-sm">
          {!editing && (
            <Button onClick={() => setEditing(true)} variant="outline" className="min-h-10">
              {p.source === "db" ? t("set.changeKey") : t("set.addKey")}
            </Button>
          )}
          {p.source === "db" && !editing && (
            <Button onClick={remove} busy={busy} variant="ghost" className="min-h-10 hover:text-danger">{t("act.delete")}</Button>
          )}
        </div>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {editing && (
        <div className="page-enter mt-4 border-t border-line pt-4">
          <label className="mb-2 block text-sm font-medium" htmlFor={`api-key-${p.key}`}>{t("set.pasteKey", { name: p.name })}</label>
          <input id={`api-key-${p.key}`} type="password" className="field" autoFocus placeholder={t("set.pasteKey", { name: p.name })}
            value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <a href={p.key_url} target="_blank" rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center gap-1 text-sm text-link underline-offset-4 hover:underline">
              {t("set.whereKey")} <ExternalLink className="size-3" />
            </a>
            <div className="flex gap-2">
              <Button onClick={() => { setEditing(false); setError(""); setValue(""); }} disabled={busy} variant="ghost">{t("act.cancel")}</Button>
              <Button onClick={save} busy={busy} disabled={value.trim().length < 8}>
                {busy ? t("set.checking") : t("set.saveKey")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </li>
  );
}

function AgentSection({ me, onChanged }: { me: Me; onChanged: () => void }) {
  const [token, setToken] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { t, locale } = useI18n();
  const server = API_BASE || window.location.origin;
  const command = `.venv\\Scripts\\feedlens agent --server ${server} --token ${token}`;
  const copy = async () => {
    try { await navigator.clipboard.writeText(command); setCopied(true); }
    catch { setError(t("act.copyFailed")); }
  };

  const create = async () => {
    if (me.agent.has_token && !confirm(t("set.newTokenConfirm"))) return;
    if (busy) return;
    setBusy(true); setError("");
    try {
      setToken((await api.newAgentToken()).token);
      setCopied(false);
      onChanged();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <section className="border-t border-line pt-6">
      <h3 className="font-headline text-2xl font-semibold">{t("set.agent")}</h3>
      <p className="mt-2 text-sm leading-relaxed text-pretty text-ink-soft">{t("set.agentHint")}</p>
      <p className="mt-4 flex items-start gap-2 text-sm [overflow-wrap:anywhere]">
        <span className={`mt-1.5 size-2 shrink-0 rounded-full ${me.agent.online ? "bg-ok" : "bg-line"}`} />
        {me.agent.online ? t("set.agentOn")
          : me.agent.last_seen ? t("set.agentLast", { when: parseTimestamp(me.agent.last_seen).toLocaleString(locale) })
          : t("set.agentNever")}
      </p>

      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {token ? (
        <div className="mt-4">
          <p className="text-sm font-medium">{t("set.runThis")}</p>
          <pre className="mt-2 rounded-lg bg-sunken p-3 text-xs break-all whitespace-pre-wrap">{command}</pre>
          <Button onClick={copy} className="mt-3 gap-2" icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />}>
            {copied ? t("act.copied") : t("set.copyCmd")}
          </Button>
          <p className="mt-2 text-xs text-ink-soft">{t("set.tokenOnce")}</p>
        </div>
      ) : (
        <Button onClick={create} busy={busy} variant="outline" className="mt-4">
          {me.agent.has_token ? t("set.newToken") : t("set.connect")}
        </Button>
      )}
    </section>
  );
}
