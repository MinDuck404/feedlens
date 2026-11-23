import { useEffect, useState } from "react";
import { api } from "../../api";
import { serverMessage, useI18n } from "../../i18n";
import { formatDuration } from "../../logic";
import type { Run } from "../../types";
import { Button } from "../ui";
import { QuotaDiagnostics, RetryAnalysis } from "./RetryAnalysis";

export function InProgress({ run, onStarted }: { run: Run; onStarted: () => void }) {
  const p = run.progress;
  const { t, locale, lang } = useI18n();
  const [changing, setChanging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ai = p?.ai;
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!["quota_wait", "service_wait"].includes(ai?.state ?? "") || !ai?.retry_at || p?.stop_requested) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ai?.state, ai?.retry_at, p?.stop_requested]);
  const retryIn = ai?.retry_at ? Math.max(0, Math.ceil(ai.retry_at - now / 1000)) : 0;
  const stop = async () => {
    setBusy(true); setError("");
    try { await api.stopAnalysis(run.id); onStarted(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const pct = p?.target ? Math.min(100, Math.round((p.done / p.target) * 100)) : 0;
  const phase = run.status === "pending" ? t("run.phase.pending")
    : run.status === "scraping" ? t("run.phase.scraping") : run.status === "analyzing" ? t("run.phase.analyzing") : t("run.phase.preparing");
  return (
    <div className="mt-10 max-w-lg">
      <p role="status" className="font-semibold">{phase}</p>
      <div role="progressbar" aria-label={phase} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="mt-4 h-1.5 overflow-hidden rounded-full bg-sunken">
        <div className="h-full w-full origin-left rounded-full bg-accent transition-transform duration-[var(--duration-normal)] ease-[var(--ease-micro)] motion-reduce:transition-none" style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
      {ai && <div className="mt-3 space-y-2 text-sm text-ink-soft" role="status">
        {ai.model && <p className="[overflow-wrap:anywhere]">{ai.provider} · {ai.model} · {ai.key_label || t("run.environmentKey")}</p>}
        {ai.requested_model && ai.requested_model !== ai.model && <p>{t("run.requestedModel", { model: ai.requested_model })}</p>}
        {ai.switched_key && <p>{t("run.sameModelKey", { key: ai.key_label ?? "", model: ai.model ?? "" })}</p>}
        {p?.stop_requested ? <p>{t("run.stoppingAI")}</p>
          : ai.state === "quota_wait" ? <p>{ai.retry_at && <>{t("run.quotaCountdown", { seconds: retryIn })} · </>}{t("run.quotaRetryAt")} {ai.retry_at && <time dateTime={new Date(ai.retry_at * 1000).toISOString()}>{new Date(ai.retry_at * 1000).toLocaleTimeString(locale)}</time>}</p>
          : ai.state === "service_wait" ? <p>{ai.retry_at && <>{t("run.quotaCountdown", { seconds: retryIn })} · </>}{t("run.serviceWaiting", { provider: ai.provider_id === "gemini" ? t("run.googleAI") : ai.provider ?? "", http: ai.status ? ` (HTTP ${ai.status})` : "" })} {ai.retry_at && <time dateTime={new Date(ai.retry_at * 1000).toISOString()}>{new Date(ai.retry_at * 1000).toLocaleTimeString(locale)}</time>}</p>
          : ai.state === "service_paused" ? <p>{t("error.ai_service_paused")}</p>
          : ai.state === "sending" ? <p>{ai.batch ? t("run.sendingBatch", { n: ai.batch, total: ai.batches ?? 1 }) : t("run.writingSummary")}</p>
          : ai.state === "output_retry" ? <p>{t("run.outputRetry")}</p>
          : ai.state === "switching" ? <p>{ai.next_model ? t("run.switchingTo", { model: ai.next_model }) : t("run.noFallback")}</p>
          : ai.state === "exhausted" ? <p>{t(ai.daily ? "run.dailyQuotaExhausted" : "error.ai_quota")}</p> : null}
        <p>{t("run.readCount", { done: p?.done ?? 0, target: p?.target ?? run.collected })}{!!p?.eta_seconds && ` · ${t("run.estimatedRemaining", { time: formatDuration(p.eta_seconds, lang) })}`}</p>
        {!!p?.ai_requests && <p>{t("run.requestUsage", { requests: p.ai_requests, saved: p.newly_read ?? 0 })}</p>}
        {ai.provider_id === "gemini" && ["quota_wait", "exhausted"].includes(ai.state) && <p>{t(ai.project_shared ? "run.sharedProjectDetected" : "run.projectQuotaHint")}</p>}
      </div>}
      {!ai && <p className="mt-2 text-sm text-ink-soft">{p?.stop_requested ? t("run.stoppingAI") : p ? serverMessage(p.message_code ?? `progress.${p.phase}`, p.message, { ...p.message_vars, done: p.done, target: p.target }) : (run.status === "pending" ? t("run.pendingHint") : t("run.openingBrowser"))}</p>}
      {(ai?.state === "exhausted" || ai?.state === "service_paused") && <QuotaDiagnostics run={run} />}
      {run.status === "analyzing" && <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="secondary" busy={busy} disabled={!!p?.stop_requested} onClick={stop}>{t("run.stopAI")}</Button>
        <Button variant="ghost" disabled={!!p?.stop_requested} onClick={() => setChanging(!changing)} aria-expanded={changing}>{t("run.changeModel")}</Button>
      </div>}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {changing && <RetryAnalysis run={run} switching onStarted={onStarted} />}
    </div>
  );
}
