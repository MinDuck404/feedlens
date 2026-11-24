import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useI18n, type Key } from "../../i18n";
import type { AIProviderInfo, Run } from "../../api/types";
import { ModelPicker } from "../Composer";
import { Button, Select } from "../ui";

export function RetryAnalysis({ run, onStarted, reanalyzeAll = false, switching = false }: { run: Run; onStarted: () => void; reanalyzeAll?: boolean; switching?: boolean }) {
  const { t } = useI18n();
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [provider, setProvider] = useState(reanalyzeAll ? "auto" : run.request.ai_provider || "auto");
  const [model, setModel] = useState(run.request.ai_model || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resumeAI = !reanalyzeAll && run.request.ai_provider !== "offline";
  useEffect(() => { let alive = true; api.providers().then((p) => { if (alive) setProviders(p); }).catch((e) => { if (alive) setError(e.message); }); return () => { alive = false; }; }, []);
  const submit = async () => {
    if (reanalyzeAll && !window.confirm(t("run.confirmReanalyzeAI", { n: run.analysis_counts?.total ?? run.collected, requests: run.reanalyze_requests_estimate ?? 1 }))) return;
    setBusy(true); setError("");
    try {
      if (switching) await api.stopAnalysis(run.id, { ai_provider: provider, ai_model: model });
      else await api.retryAnalysis(run.id, provider, model, reanalyzeAll ? "reanalyze_all" : "continue");
      onStarted();
    }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="mt-4 border-t border-line pt-4">
    <p className="text-sm text-ink-soft">{resumeAI && run.analysis_counts ? t("run.retryAIHint", { n: run.analysis_counts.total - run.analysis_counts.ai }) : t("run.retryAnalysisHint")}</p>
    <fieldset disabled={busy} className="mt-3 min-w-0 space-y-3">
      <label className="block text-sm">{t("cmp.ai")}<Select aria-label={t("cmp.ai")} className="mt-2" value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); }}>
        <option value="auto">{t("profile.auto")}</option>
        {providers.filter((p) => p.configured && p.key !== "offline").map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
        {provider !== "auto" && provider !== "offline" && !providers.some((p) => p.key === provider && p.configured) && <option value={provider}>{provider}</option>}
        <option value="offline">{t("profile.offlineOption")}</option>
      </Select></label>
      {provider !== "auto" && provider !== "offline" && <ModelPicker provider={provider} value={model} onChange={setModel} />}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <Button disabled={switching && run.progress?.stop_requested} busy={busy} onClick={submit}>{t(switching ? "run.switchAndContinue" : reanalyzeAll ? "run.sendToAI" : resumeAI ? "run.sendRemainingAI" : "run.continueAnalysis")}</Button>
    </fieldset>
  </div>;
}

export function QuotaDiagnostics({ run }: { run: Run }) {
  const { t } = useI18n();
  const candidates = run.progress?.ai?.candidates;
  if (!candidates?.length) return null;
  return <details open className="mt-3 text-sm">
    <summary className="interactive-tap cursor-pointer font-medium">{t("run.quotaDetails", { n: candidates.length })}</summary>
    <ul className="mt-2 divide-y divide-line">{candidates.map((item, index) => <li key={`${item.key_id}-${item.model}-${index}`} className="py-2 [overflow-wrap:anywhere]">
      <p className="font-medium">{item.key_label || t("run.environmentKey")} · {item.model}</p>
      <p className="text-ink-soft">{t(`run.quotaReason.${item.reason}` as Key, {
        tokens: item.estimated_tokens, limit: (item.reason === "daily_limit" ? item.limit_rpd : item.limit_tpm) ?? 0,
        used: item.requests_today, metric: item.metric ?? "",
        cause: t(item.kind === "service" ? "run.quotaFailure.service" : item.kind === "network" ? "run.quotaFailure.network" : item.kind === "rate_limit" ? "run.quotaFailure.rate_limit" : "run.quotaFailure.other"),
      })}{!!item.status && ` · HTTP ${item.status}`}{item.project_shared && item.reason !== "service_unavailable" && ` · ${t("run.projectQuotaShared")}`}</p>
    </li>)}</ul>
  </details>;
}
