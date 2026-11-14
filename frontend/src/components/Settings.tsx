import { Check, Copy, ExternalLink, Loader2, X as XIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { API_BASE, api } from "../api";
import type { AIProviderInfo, Me, Meta } from "../types";
import CookieSessions from "./CookieSessions";
import { useI18n } from "../i18n";

interface Props {
  meta: Meta;
  me: Me | null;
  onClose: () => void;
  onChanged: () => void;
}

export default function Settings({ meta, me, onClose, onChanged }: Props) {
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const { t } = useI18n();
  const reload = () => api.providers().then(setProviders);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    reload();  // một lần khi mở, không chạy lại mỗi lần App cập nhật
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-ink/30" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section role="dialog" aria-label={t("set.title")} className="sheet flex h-full w-full max-w-md flex-col bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-lg font-semibold">{t("set.title")}</h2>
          <button onClick={onClose} aria-label={t("act.close")} className="rounded-md p-1 text-ink-soft hover:bg-sunken">
            <XIcon className="size-5" />
          </button>
        </header>
        <div className="flex-1 space-y-8 overflow-x-hidden overflow-y-auto px-6 py-5">
          <div>
            <h3 className="font-semibold">{t("set.keys")}</h3>
            <p className="mt-1 text-sm text-ink-soft">{t("set.keysHint")}</p>
            <ul className="mt-4 space-y-3">
              {providers.filter((p) => p.key !== "offline").map((p) => (
                <KeyRow key={p.key} p={p} onChanged={() => { reload(); onChanged(); }} />
              ))}
            </ul>
          </div>
          {meta.mode === "cloud" && me && <AgentSection me={me} onChanged={onChanged} />}
          {meta.server_scrape && <CookieSessions />}
        </div>
      </section>
    </div>
  );
}

function KeyRow({ p, onChanged }: { p: AIProviderInfo; onChanged: () => void }) {
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
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!confirm(t("set.confirmDeleteKey", { name: p.name }))) return;
    await api.deleteKey(p.key);
    onChanged();
  };

  return (
    <li className="paper-card rounded-xl p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-medium">{p.name}</div>
          <div className="text-xs text-ink-soft">
            {p.configured
              ? p.source === "env" ? t("set.envKey") : t("set.savedKey", { hint: p.hint })
              : t("set.noKey")}
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          {!editing && (
            <button onClick={() => setEditing(true)} className="font-medium text-link hover:underline">
              {p.source === "db" ? t("set.changeKey") : t("set.addKey")}
            </button>
          )}
          {p.source === "db" && !editing && (
            <button onClick={remove} className="text-ink-soft hover:text-danger">{t("act.delete")}</button>
          )}
        </div>
      </div>
      {editing && (
        <div className="mt-3">
          <input type="password" className="field" autoFocus placeholder={t("set.pasteKey", { name: p.name })}
            value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" />
          {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
          <div className="mt-2 flex items-center justify-between gap-2">
            <a href={p.key_url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-link hover:underline">
              {t("set.whereKey")} <ExternalLink className="size-3" />
            </a>
            <div className="flex gap-2">
              <button onClick={() => { setEditing(false); setError(""); setValue(""); }}
                className="rounded-md px-3 py-1.5 text-sm text-ink-soft hover:bg-surface">{t("act.cancel")}</button>
              <button onClick={save} disabled={busy || value.trim().length < 8}
                className="flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-ink disabled:opacity-50">
                {busy && <Loader2 className="size-3.5 animate-spin" />} {busy ? t("set.checking") : t("set.saveKey")}
              </button>
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
  const { t, locale } = useI18n();
  const server = API_BASE || window.location.origin;
  const command = `.venv\\Scripts\\feedlens agent --server ${server} --token ${token}`;

  const create = async () => {
    if (me.agent.has_token && !confirm(t("set.newTokenConfirm"))) return;
    setToken((await api.newAgentToken()).token);
    setCopied(false);
    onChanged();
  };

  return (
    <div>
      <h3 className="font-semibold">{t("set.agent")}</h3>
      <p className="mt-1 text-sm text-ink-soft">{t("set.agentHint")}</p>
      <p className="mt-3 flex items-center gap-2 text-sm">
        <span className={`size-2 rounded-full ${me.agent.online ? "bg-ok" : "bg-line"}`} />
        {me.agent.online ? t("set.agentOn")
          : me.agent.last_seen ? t("set.agentLast", { when: new Date(me.agent.last_seen).toLocaleString(locale) })
          : t("set.agentNever")}
      </p>

      {token ? (
        <div className="mt-4">
          <p className="text-sm font-medium">{t("set.runThis")}</p>
          <pre className="mt-2 rounded-lg bg-sunken p-3 text-xs break-all whitespace-pre-wrap">{command}</pre>
          <button onClick={() => navigator.clipboard.writeText(command).then(() => setCopied(true))}
            className="mt-2 flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-ink">
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? t("act.copied") : t("set.copyCmd")}
          </button>
          <p className="mt-2 text-xs text-ink-soft">{t("set.tokenOnce")}</p>
        </div>
      ) : (
        <button onClick={create} className="mt-4 rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-ink">
          {me.agent.has_token ? t("set.newToken") : t("set.connect")}
        </button>
      )}
    </div>
  );
}
