import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { AIKey, AIProviderInfo } from "../../api/types";
import { SegmentedControl, Select } from "../../components/ui";
import { useI18n } from "../../i18n";
import { ModelPicker } from "./Controls";

export function AIKeyPicker({ provider, providerInfo, keyId, model, onChange }: {
  provider: string; providerInfo?: AIProviderInfo; keyId: number | null; model: string;
  onChange: (keyId: number | null, model: string) => void;
}) {
  const { t } = useI18n();
  const [keys, setKeys] = useState<AIKey[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setKeys(null); setError("");
    api.listKeys().then((list) => {
      if (alive) setKeys(list.filter((key) => key.provider === provider).sort((a, b) => a.priority - b.priority || a.id - b.id));
    }).catch((e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [provider]);
  useEffect(() => {
    if (keys && keyId !== null && !keys.some((key) => key.id === keyId && key.enabled && key.status !== "invalid")) onChange(null, "");
  }, [keys, keyId, onChange]);
  const reason = (key: AIKey) => !key.enabled ? t("cmp.keyDisabled") : key.status === "invalid" ? t("set.keyInvalid")
    : model && key.usage_today[model]?.limit_rpd != null && key.usage_today[model].requests >= key.usage_today[model].limit_rpd! ? t("cmp.keyQuota") : "";
  const name = (key: AIKey) => `${key.label.trim() || key.base_url || t("set.keyName", { hint: key.hint })}${key.label.trim() && key.hint ? ` · …${key.hint.slice(-4)}` : ""}`;
  const first = keys?.find((key) => key.enabled && key.status !== "invalid");
  const firstAuto = keys?.find((key) => key.enabled);
  const firstName = firstAuto ? name(firstAuto) : providerInfo?.source === "env" ? t("run.environmentKey") : t("cmp.noSelectableKey");
  return <div className="mt-3 space-y-2">
    <fieldset disabled={!keys || !first} className="min-w-0"><SegmentedControl compact label={t("cmp.keyMode")} value={keyId === null ? "auto" : "key"}
      onChange={(mode) => {
        if (mode === (keyId === null ? "auto" : "key")) return;
        onChange(mode === "key" && first ? first.id : null, "");
      }}
      options={[{ value: "auto", label: t("cmp.keyAuto") }, { value: "key", label: t("cmp.keyChoose") }]} /></fieldset>
    {keyId === null ? <p className="text-xs text-ink-soft">{keys === null && !error ? t("act.loading") : t("cmp.keyAutoHint", { name: firstName })}</p>
      : <label className="block text-sm">{t("cmp.keyLabel")}<Select aria-label={t("cmp.keyLabel")} className="mt-1" value={String(keyId)} onChange={(e) => onChange(Number(e.target.value), "")}>
        {keys === null && <option value={keyId}>{t("act.loading")}</option>}
        {keys?.map((key) => <option key={key.id} value={key.id} disabled={!!reason(key)} className={reason(key) ? "text-ink-soft" : ""}>
          {name(key)}{reason(key) ? ` · ${reason(key)}` : ""}
        </option>)}
      </Select></label>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <ModelPicker key={`${provider}-${keyId}`} provider={provider} keyId={keyId} value={model} onChange={(next) => onChange(keyId, next)} />
  </div>;
}
