import { ArrowDown, ArrowUp, ExternalLink, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../../api/client";
import { formatNumber, useI18n } from "../../i18n";
import type { AIKey, AIProviderInfo } from "../../api/types";
import { Button, IconButton, Select, TextField } from "../../components/ui";

interface Props {
  provider: AIProviderInfo;
  keys: AIKey[];
  available: boolean;
  onChanged: () => Promise<void>;
}

export default function AIProviderKeys({ provider: p, keys, available, onChanged }: Props) {
  const { t, lang } = useI18n();
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState("");
  const [secret, setSecret] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [tier, setTier] = useState<AIKey["tier"]>("free");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [verified, setVerified] = useState(false);
  const [model, setModel] = useState("");
  const custom = p.key === "custom";
  const providerName = custom ? t("set.customProvider") : p.name;
  const ordered = [...keys].sort((a, b) => a.priority - b.priority || a.id - b.id);
  const name = (key: AIKey) => key.label.trim() || key.base_url || t("set.keyName", { hint: key.hint });

  const action = async (work: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError("");
    try { await work(); await onChanged(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const save = () => action(async () => {
    await api.addKey({ provider: p.key as AIKey["provider"], api_key: secret.trim(), label: label.trim(), tier,
      ...(custom ? { base_url: baseUrl.trim(), default_model: defaultModel.trim() } : {}) });
    setSecret(""); setLabel(""); setBaseUrl(""); setDefaultModel(""); setEditing(false); setTier("free");
  });
  const move = (index: number, direction: -1 | 1) => action(async () => {
    const ids = ordered.map((key) => key.id);
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    await api.reorderKeys(p.key as AIKey["provider"], ids);
  });
  const remove = (key: AIKey) => {
    if (busy || !confirm(t("set.confirmDeleteKey", { name: name(key) }))) return;
    return action(() => api.deleteKey(key.id));
  };
  const check = () => action(async () => {
    setVerified(false);
    const result = await api.models(p.key, true);
    setModel(result.default); setVerified(true);
  });

  return <li className="min-w-0 border-b border-line py-5">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2"><h4 className="font-semibold">{providerName}</h4>
          {p.is_default && <span className="rounded-full bg-sunken px-2 py-1 text-xs text-link">{t("set.defaultAI")}</span>}</div>
        <p className="mt-1 break-words text-xs text-ink-soft">{t("set.defaultModel", { model: model || p.default_model || "—" })}</p>
      </div>
      {!editing && <Button size="sm" variant="outline" disabled={busy || !available} onClick={() => { setEditing(true); setError(""); }}>{t("set.addKey")}</Button>}
    </div>
    <p className="mt-2 text-xs text-ink-soft">{t("set.keyPriorityHint")}</p>
    {!available && <p className="mt-2 text-sm text-ink-soft">{t("set.keyUnknown")}</p>}
    {p.source === "env" && <p className="mt-2 text-xs text-ink-soft">{t("set.envKey")}. {t("set.envHint")}</p>}
    {available && !ordered.length && p.source !== "env" && <p className="mt-3 text-sm text-ink-soft">{t("set.noKey")}</p>}
    {!!ordered.length && <ol className="mt-3 space-y-3">
      {ordered.map((key, index) => <li key={key.id} className="min-w-0 rounded-card border border-line p-3">
        <div className="flex min-w-0 flex-wrap items-baseline gap-2">
          <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{name(key)}</span>
          {key.label.trim() && key.hint && <span className="font-mono text-xs text-ink-soft">••••{key.hint}</span>}
          <span className="rounded-full bg-sunken px-2 py-1 text-xs text-ink-soft">{t(index === 0 ? "set.keyPrimary" : "set.keyBackup")}</span>
          <span className={`text-xs ${key.status === "invalid" ? "text-danger" : "text-ink-soft"}`}>
            {t(key.status === "ok" ? "set.keyValid" : key.status === "invalid" ? "set.keyInvalid" : "set.keyUnchecked")}
          </span>
        </div>
        {custom && <p className="mt-2 break-words text-xs text-ink-soft">{key.base_url}<span className="mt-1 block">{t("set.defaultModel", { model: key.default_model || "—" })}</span></p>}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <label className="min-w-28 flex-1 text-xs"><span className="mb-1 block">{t("set.keyTier")}</span>
            <Select value={key.tier} disabled={busy || !available} aria-label={t("set.keyTierFor", { name: name(key) })}
              onChange={(event) => action(() => api.updateKey(key.id, { tier: event.target.value as AIKey["tier"] }))}>
              <option value="free">{t("set.keyFree")}</option><option value="paid">{t("set.keyPaid")}</option>
            </Select>
          </label>
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" role="switch" checked={key.enabled} disabled={busy || !available} aria-label={t("set.keyEnabledFor", { name: name(key) })}
              onChange={(event) => action(() => api.updateKey(key.id, { enabled: event.target.checked }))} />{t("set.keyEnabled")}
          </label>
          <div className="flex flex-wrap gap-1">
            <IconButton variant="outline" disabled={busy || !available || index === 0} aria-label={t("set.keyMoveUp", { name: name(key) })} onClick={() => move(index, -1)}><ArrowUp className="size-4" /></IconButton>
            <IconButton variant="outline" disabled={busy || !available || index === ordered.length - 1} aria-label={t("set.keyMoveDown", { name: name(key) })} onClick={() => move(index, 1)}><ArrowDown className="size-4" /></IconButton>
            <IconButton variant="outline" disabled={busy || !available} aria-label={t("set.keyDelete", { name: name(key) })} className="hover:text-danger" onClick={() => remove(key)}><Trash2 className="size-4" /></IconButton>
          </div>
        </div>
        <div className="mt-3 border-t border-line pt-2 text-xs text-ink-soft">
          <span>{t("set.keyUsageToday")}</span>
          {!Object.keys(key.usage_today).length ? <span className="ml-2">{t("set.keyNoUsage")}</span> : <ul className="mt-1 space-y-1">
            {Object.entries(key.usage_today).map(([model, usage]) => <li key={model} className="flex flex-wrap justify-between gap-x-2">
              <span className="min-w-0 [overflow-wrap:anywhere]">{model}</span>
              <span className="font-mono tabular-nums">{formatNumber(usage.requests, lang)}/{usage.limit_rpd === null ? "—" : formatNumber(usage.limit_rpd, lang)}</span>
            </li>)}
          </ul>}
        </div>
      </li>)}
    </ol>}
    {p.key === "gemini" && <p className="mt-3 text-xs leading-relaxed text-ink-soft">{t("set.geminiProjectQuota")}</p>}
    <div className="mt-3 flex flex-wrap gap-2">
      {p.configured && <Button size="sm" variant="ghost" disabled={busy || !available} onClick={check}>{t("set.checkKey")}</Button>}
      {p.configured && !p.is_default && <Button size="sm" variant="ghost" disabled={busy || !available} onClick={() => action(() => api.setDefaultAI(p.key))}>{t("set.useDefault")}</Button>}
    </div>
    {verified && !error && <p role="status" className="mt-2 text-xs text-ok">{t("set.keyValid")}</p>}
    {error && <p role="alert" className="mt-3 text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
    {editing && <div className="mt-4 space-y-3 border-t border-line pt-4">
      {custom && <label className="block text-sm"><span className="mb-1.5 block">{t("set.customBaseUrl")}</span>
        <TextField type="url" required aria-label={t("set.customBaseUrl")} placeholder={t("set.customBaseUrlPlaceholder")} value={baseUrl} maxLength={2000} disabled={busy}
          onChange={(event) => setBaseUrl(event.target.value)} />
        <span className="mt-1.5 block text-xs text-ink-soft">{t("set.customBaseUrlHint")}</span>
      </label>}
      <label className="block text-sm"><span className="mb-1.5 block">{t("set.keyLabel")}</span>
        <TextField value={label} maxLength={80} onChange={(event) => setLabel(event.target.value)} disabled={busy} />
      </label>
      <label className="block text-sm"><span className="mb-1.5 block">{t("set.pasteKey", { name: providerName })}</span>
        <TextField type="password" autoFocus value={secret} maxLength={500} autoComplete="off" disabled={busy}
          onChange={(event) => setSecret(event.target.value)} />
        {custom && <span className="mt-1.5 block text-xs text-ink-soft">{t("set.customKeyOptional")}</span>}
      </label>
      {custom && <label className="block text-sm"><span className="mb-1.5 block">{t("set.customDefaultModel")}</span>
        <TextField required aria-label={t("set.customDefaultModel")} value={defaultModel} maxLength={200} disabled={busy}
          onChange={(event) => setDefaultModel(event.target.value)} />
      </label>}
      <label className="block text-sm"><span className="mb-1.5 block">{t("set.keyTier")}</span>
        <Select value={tier} disabled={busy} onChange={(event) => setTier(event.target.value as AIKey["tier"])}>
          <option value="free">{t("set.keyFree")}</option><option value="paid">{t("set.keyPaid")}</option>
        </Select>
      </label>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {p.key_url && <a href={p.key_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 text-sm text-link hover:underline">{t("set.whereKey")}<ExternalLink className="size-3" /></a>}
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => { setEditing(false); setSecret(""); setLabel(""); setBaseUrl(""); setDefaultModel(""); setError(""); }}>{t("act.cancel")}</Button>
          <Button busy={busy} disabled={busy || (custom ? !baseUrl.trim() || !defaultModel.trim() : secret.trim().length < 8)} onClick={save}>{t(busy ? "set.checking" : "set.saveKey")}</Button>
        </div>
      </div>
    </div>}
  </li>;
}
