import { Check, Copy, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { parseTimestamp } from "../logic";
import { API_BASE, api } from "../api";
import type { AIProviderInfo, Me, Meta } from "../types";
import CookieSessions from "./CookieSessions";
import JobProfileSettings from "./JobProfileSettings";
import { ThemeMenu } from "./PreferenceMenus";
import { useI18n } from "../i18n";
import { Sheet, Button, SkeletonCard, SegmentedControl } from "./ui";

interface Props {
  meta: Meta;
  me: Me | null;
  onClose: () => void;
  onChanged: () => void;
}

export default function Settings({ meta, me, onClose, onChanged }: Props) {
  const [open, setOpen] = useState(true);
  const id = useId();
  const body = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState(() => {
    try { const saved = localStorage.getItem("feedlens.settingsTab"); return ["keys", "profile", "agent", "cookies"].includes(saved ?? "") ? saved! : "keys"; } catch { return "keys"; }
  });
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const { t } = useI18n();
  const reload = () => api.providers().then((p) => { setProviders(p); setLoadError(""); }).finally(() => setLoading(false));

  const tabs = [{ value: "keys", label: t("set.tab.keys") }, { value: "profile", label: t("profile.title") }, { value: "agent", label: t("set.tab.agent") }, { value: "cookies", label: t("set.tab.cookies") }];
  const changeTab = (value: string) => {
    setTab(value); if (body.current) body.current.scrollTop = 0;
    try { localStorage.setItem("feedlens.settingsTab", value); } catch { /* Keep the current tab in memory. */ }
  };
  const rows = [
    { key: "anthropic", name: "Claude" }, { key: "openai", name: "OpenAI" }, { key: "gemini", name: "Gemini" },
  ].map((p) => providers.find((row) => row.key === p.key) ?? { ...p, configured: false, source: null, hint: "", default_model: "", key_url: "" } as AIProviderInfo);

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
      maxWidth="max-w-xl"
      className="[&_h2]:font-headline"
      contentClassName="flex min-h-0 flex-1 flex-col overflow-hidden"
    >
      <div className="shrink-0 border-b border-line px-6 py-3">
        <SegmentedControl id={id} mode="tabs" label={t("set.title")} value={tab} onChange={changeTab} options={tabs} />
      </div>
      <div ref={body} className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div hidden={tab !== "keys"} role="tabpanel" id={`${id}-panel-keys`} aria-labelledby={`${id}-tab-keys`} tabIndex={0}>
          <h3 className="font-headline text-2xl font-semibold">{t("set.keys")}</h3>
          <p className="mt-2 text-sm leading-relaxed text-pretty text-ink-soft">{t("set.keysHint")}</p>
          {loadError && <p role="alert" className="mt-3 text-sm text-danger">{loadError} <button onClick={() => reload().catch((e) => setLoadError(e.message))}>{t("act.retry")}</button></p>}
          {loading ? <div role="status" aria-label={t("act.loading")} className="mt-4"><SkeletonCard /></div> : <ul className="mt-2">
            {rows.map((p) => <KeyRow key={p.key} p={p} available={!loadError} onChanged={async () => { await reload(); onChanged(); }} />)}
          </ul>}
        </div>
        <div hidden={tab !== "profile"} role="tabpanel" id={`${id}-panel-profile`} aria-labelledby={`${id}-tab-profile`} tabIndex={0}><JobProfileSettings providers={providers} /></div>
        <div hidden={tab !== "agent"} role="tabpanel" id={`${id}-panel-agent`} aria-labelledby={`${id}-tab-agent`} tabIndex={0}>
          <div className="mb-5 flex items-center justify-between gap-3 border-b border-line pb-3"><span className="text-sm">{t("theme.label")}</span><ThemeMenu above={false} /></div>
          {meta.mode === "cloud" && me ? <AgentSection me={me} onChanged={onChanged} /> : <><h3 className="font-headline text-2xl">{t("set.tab.agent")}</h3><p className="mt-3 text-sm leading-relaxed text-ink-soft">{t("set.localAgent")}</p></>}
        </div>
        <div hidden={tab !== "cookies"} role="tabpanel" id={`${id}-panel-cookies`} aria-labelledby={`${id}-tab-cookies`} tabIndex={0}>
          {meta.server_scrape ? <CookieSessions /> : <p className="text-sm leading-relaxed text-ink-soft">{t("set.cookiesUnavailable")}</p>}
        </div>
      </div>
    </Sheet>
  );
}

function KeyRow({ p, available, onChanged }: { p: AIProviderInfo; available: boolean; onChanged: () => Promise<void> }) {
  const [verified, setVerified] = useState(false);
  const [model, setModel] = useState("");
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
      setVerified(true);
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
    try { await api.deleteKey(p.key); setVerified(false); setModel(""); await onChanged(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const check = async () => {
    setBusy(true); setError(""); setVerified(false);
    try { const result = await api.models(p.key, true); setModel(result.default); setVerified(true); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const makeDefault = async () => {
    setBusy(true); setError("");
    try { await api.setDefaultAI(p.key); await onChanged(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <li className="border-b border-line py-4">
      <div className="flex min-w-0 flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0 [overflow-wrap:anywhere]">
          <div className="flex flex-wrap items-center gap-2 font-medium"><h4>{p.name}</h4>{p.is_default && <span className="rounded-full bg-sunken px-2 py-1 text-xs text-link">{t("set.defaultAI")}</span>}</div>
          <div className="text-xs text-ink-soft">
            {!available ? t("set.keyUnknown") : error ? t("set.keyError") : p.configured
              ? p.source === "env" ? t("set.envKey") : t("set.savedKey", { hint: p.hint })
              : t("set.noKey")}
          </div>
          <p className="mt-1 break-words text-xs text-ink-soft">{t("set.defaultModel", { model: model || p.default_model || "—" })}</p>
          {p.source === "env" && <p className="mt-2 max-w-prose text-xs leading-relaxed text-ink-soft">{t("set.envHint")}</p>}
          {verified && !error && <p role="status" className="mt-1 text-xs text-ok">{t("set.keyValid")}</p>}
        </div>
        <div className="flex max-w-full flex-wrap items-center gap-2 text-sm">
          {!editing && (
            <Button onClick={() => setEditing(true)} disabled={busy || !available} variant="outline" className="min-h-11" size="sm">
              {p.configured ? t("set.changeKey") : t("set.addKey")}
            </Button>
          )}
          {p.configured && !editing && <Button onClick={check} busy={busy} variant="ghost" size="sm" className="min-h-11">{t("set.checkKey")}</Button>}
          {p.source === "db" && !editing && (
            <Button onClick={remove} disabled={busy} variant="ghost" size="sm" className="min-h-11 hover:text-danger">{t("act.delete")}</Button>
          )}
        </div>
      </div>
      {p.configured && !p.is_default && !editing && <Button onClick={makeDefault} disabled={busy} variant="ghost" size="sm" className="mt-2 min-h-11">{t("set.useDefault")}</Button>}
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
