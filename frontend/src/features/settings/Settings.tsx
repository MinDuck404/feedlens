import { Check, Copy } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { parseTimestamp } from "../../lib/logic";
import { API_BASE, api } from "../../api/client";
import type { AIKey, AIProviderInfo, Me, Meta, Preferences } from "../../api/types";
import AIProviderKeys from "./AIProviderKeys";
import CookieSessions from "./CookieSessions";
import TopicSettings from "./TopicSettings";
import JobProfileSettings from "./JobProfileSettings";
import { formatNumber, useI18n } from "../../i18n";
import { Sheet, Button, SkeletonCard, SegmentedControl, Select } from "../../components/ui";

interface Props {
  initialTab?: string;
  meta: Meta;
  me: Me | null;
  prefs?: Preferences | null;
  onPrefsChange?: (p: Preferences) => void;
  onClose: () => void;
  onChanged: () => void;
}

function settingsTab(value: string | null | undefined, cloud: boolean): string {
  if (["agent", "cookies"].includes(value ?? "")) return cloud ? "scrape" : "keys";
  return ["keys", "profile", "topics", "general", ...(cloud ? ["scrape"] : [])].includes(value ?? "") ? value! : "keys";
}

export default function Settings({ meta, me, prefs, onPrefsChange, onClose, onChanged, initialTab }: Props) {
  const [open, setOpen] = useState(true);
  const id = useId();
  const body = useRef<HTMLDivElement>(null);
  const cloud = meta.mode === "cloud";
  const [selectedTab, setTab] = useState(() => {
    if (initialTab !== undefined) return settingsTab(initialTab, cloud);
    try { return settingsTab(localStorage.getItem("feedlens.settingsTab"), cloud); } catch { return "keys"; }
  });
  const tab = settingsTab(selectedTab, cloud);
  useEffect(() => { try { localStorage.setItem("feedlens.settingsTab", tab); } catch { /* Keep the current tab in memory. */ } }, [tab]);
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [keys, setKeys] = useState<AIKey[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const { t, lang } = useI18n();
  const reload = () => Promise.all([api.providers(), api.listKeys()]).then(([providers, keys]) => {
    setProviders(providers); setKeys(keys); setLoadError("");
  }).finally(() => setLoading(false));

  const tabs = [{ value: "keys", label: t("set.tab.keys") }, { value: "profile", label: t("profile.title") }, { value: "topics", label: t("topics.title") }, { value: "general", label: t("set.tab.general") }, ...(cloud ? [{ value: "scrape", label: t("set.tab.scrape") }] : [])];
  const changeTab = (value: string) => {
    setTab(value); if (body.current) body.current.scrollTop = 0;
    try { localStorage.setItem("feedlens.settingsTab", value); } catch { /* Keep the current tab in memory. */ }
  };
  const rows = [
    { key: "anthropic", name: "Claude" }, { key: "openai", name: "OpenAI" }, { key: "gemini", name: "Gemini" },
    { key: "custom", name: t("set.customProvider") },
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
            {rows.map((p) => <AIProviderKeys key={p.key} provider={p} keys={keys.filter((key) => key.provider === p.key)}
              available={!loadError} onChanged={async () => { await reload(); onChanged(); }} />)}
          </ul>}
        </div>
        <div hidden={tab !== "profile"} role="tabpanel" id={`${id}-panel-profile`} aria-labelledby={`${id}-tab-profile`} tabIndex={0}><JobProfileSettings providers={providers} /></div>
        <div hidden={tab !== "topics"} role="tabpanel" id={`${id}-panel-topics`} aria-labelledby={`${id}-tab-topics`} tabIndex={0}><TopicSettings /></div>
        <div hidden={tab !== "general"} role="tabpanel" id={`${id}-panel-general`} aria-labelledby={`${id}-tab-general`} tabIndex={0}>
          <h3 className="font-headline text-2xl font-semibold">{t("set.tab.general")}</h3>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium">{t("set.maxPosts")}</span>
            <Select
              aria-label={t("set.maxPosts")}
              value={String(prefs?.max_posts ?? (meta.max_posts === 1000 || meta.max_posts === 2000 ? meta.max_posts : 500))}
              onChange={(event) => {
                const max_posts = Number(event.target.value) as 500 | 1000 | 2000;
                onPrefsChange?.({ ...(prefs ?? {}), max_posts });
              }}
            >
              {[500, 1000, 2000].map((n) => (
                <option key={n} value={String(n)}>{formatNumber(n, lang)}</option>
              ))}
            </Select>
          </label>
          <p className="mt-2 text-sm leading-relaxed text-pretty text-ink-soft">{t("set.maxPostsHint")}</p>
        </div>
        {cloud && <div hidden={tab !== "scrape"} role="tabpanel" id={`${id}-panel-scrape`} aria-labelledby={`${id}-tab-scrape`} tabIndex={0}>
          {me ? <AgentSection me={me} onChanged={onChanged} /> : <div role="status" aria-label={t("act.loading")}><SkeletonCard /></div>}
          {meta.server_scrape && <div className="mt-6"><CookieSessions /></div>}
        </div>}
      </div>
    </Sheet>
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
    <section>
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
