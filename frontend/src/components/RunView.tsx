import { RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { serverMessage, useI18n } from "../i18n";
import { routeHref, type RunTab } from "../router";
import type { Meta, Preferences, Run, RunRequest } from "../types";
import { canContinueAnalysis, canReanalyzeOffline, defaultRunTab, describeRunSource, parseTimestamp } from "../logic";
import { Button, IconButton, Skeleton, SkeletonCard } from "./ui";
import { Done } from "./run/Done";
import { InProgress } from "./run/InProgress";
import { JobsBoard } from "./run/JobsBoard";
import { PostList, PostSources, ReadingPost } from "./run/PostList";
import { QuotaDiagnostics, RetryAnalysis } from "./run/RetryAnalysis";
import { savedGroupsFor, ScrapeReportLine } from "./run/ScrapeReportLine";

export { Done, InProgress, JobsBoard, PostSources, ReadingPost, QuotaDiagnostics };
export { runPostFiltersFromHash, runPostsHref } from "./run/runPostFilters";

type Tab = RunTab;

interface Props {
  runId: number;
  meta: Meta;
  prefs?: Preferences | null;
  tab: Tab;               // tab nằm trong URL (#/runs/12/jobs) nên tải lại trang vẫn giữ
  onTab: (t: Tab) => void;
  onDeleted: () => void;
  onAnalysisStarted?: () => void;
  onRerun?: (request: RunRequest) => void;
}

export default function RunView({ runId, meta, prefs, tab, onTab, onDeleted, onAnalysisStarted, onRerun }: Props) {
  const [run, setRun] = useState<Run | null>(null);
  const [missing, setMissing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const setTab = (next: Tab) => {
    if (next === "digest" && run?.request.platform === "linkedin" && run.request.mode === "jobs") window.location.hash = `#/runs/${run.id}/digest`;
    else onTab(next);
  };
  const { t, locale, cat } = useI18n();
  const defaulted = useRef<number | null>(null);
  useEffect(() => {
    if (!run || run.id !== runId || defaulted.current === runId) return;
    defaulted.current = runId;
    if (defaultRunTab(run.request, window.location?.hash ?? "") === "jobs") onTab("jobs");
  }, [run, runId, onTab]);

  useEffect(() => { const reload = () => setRetry((value) => value + 1); window.addEventListener("feedlens:topicsChanged", reload); return () => window.removeEventListener("feedlens:topicsChanged", reload); }, []);

  useEffect(() => {
    let alive = true;
    let timer: number;
    let failures = 0;
    let current: Run | null = null;
    let loadedVersion = -1;
    let lastFullLoad = -Infinity;
    setMissing(false);
    setLoadError(false);
    const load = async () => {
      try {
        let r = await api.run(runId, false);
        if (!alive) return;
        const active = !["done", "error", "analysis_failed"].includes(r.status);
        const changed = current?.status !== r.status;
        const newerPosts = r.posts_version !== undefined && r.posts_version > loadedVersion;
        if (!r.posts && (!current || changed || !active || newerPosts && Date.now() - lastFullLoad >= 10000)) {
          r = await api.run(runId);
          if (!alive) return;
          loadedVersion = r.posts_version ?? loadedVersion;
          lastFullLoad = Date.now();
        } else if (!r.posts && current?.posts) {
          r = { ...r, posts: current.posts };
        }
        current = r;
        setRun(r);
        setLoadError(false);
        failures = 0;
        if (!["done", "error", "analysis_failed"].includes(r.status)) timer = window.setTimeout(load, document.hidden ? 10000 : 1500);
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) { setMissing(true); return; }
        if (e instanceof ApiError && e.status === 401) return;
        setLoadError(true);
        timer = window.setTimeout(load, Math.max(document.hidden ? 10000 : 0, Math.min(30000, 1500 * 2 ** Math.min(failures++, 5))));
      }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [runId, retry]);

  if (missing) {
    return (
      <div className="mx-auto max-w-xl px-6 py-24">
        <h1 className="text-2xl font-semibold tracking-tight">{t("run.notFound", { id: runId })}</h1>
        <p className="mt-2 text-ink-soft">{t("run.maybeDeleted")}</p>
        <a href={routeHref({ page: "history" })} className="mt-6 inline-block rounded-full border border-line px-5 py-2 font-medium hover:border-ink">
          {t("run.viewHistory")}
        </a>
      </div>
    );
  }
  if (!run) return loadError ? <p role="alert" className="m-5 text-sm text-danger">{t("run.retrying")} <Button variant="ghost" onClick={() => setRetry((n) => n + 1)}>{t("act.retry")}</Button></p> : (
    <div className="mx-auto max-w-5xl space-y-6 px-5 py-8 md:px-10" role="status" aria-label={t("act.loading")}>
      <div aria-hidden="true" className="space-y-6"><Skeleton height={18} className="w-40" /><Skeleton height={36} className="w-3/4" /><Skeleton height={44} rounded="full" /><SkeletonCard /><SkeletonCard /></div>
    </div>
  );
  const q = run.request;
  const title = describeRunSource(q, t);
  const when = parseTimestamp(run.created_at);
  const canContinue = canContinueAnalysis(run);
  const canReanalyze = canReanalyzeOffline(run);
  const canReprocess = !!run.can_reprocess_ai;
  const failed = run.status === "error" || run.status === "analysis_failed";
  const counts = run.analysis_counts;
  const activeAI = run.status === "analyzing" ? run.progress?.ai : undefined;
  const readBy = activeAI?.model ? `${activeAI.provider} (${activeAI.model})` : run.ai_label;

  const remove = async () => {
    if (!confirm(t("run.confirmDelete"))) return;
    if (deleting) return;
    setDeleting(true);
    try { await api.deleteRun(run.id); onDeleted(); }
    catch (e) { alert((e as Error).message); }
    finally { setDeleting(false); }
  };

  return (
    <div className="page-enter mx-auto max-w-5xl px-5 py-8 md:px-10 md:py-10">
      {loadError && <p role="alert" className="mt-3 text-sm text-danger">{t("run.retrying")} <button onClick={() => setRetry((n) => n + 1)}>{t("act.retry")}</button></p>}
      <header className="text-center">
        <h1 className="mx-auto max-w-[32ch] font-headline text-2xl leading-tight font-semibold text-balance [overflow-wrap:anywhere] sm:text-3xl md:text-4xl">{title}</h1>
        <p className="mt-4 text-xs leading-relaxed text-ink-soft [overflow-wrap:anywhere]">
          {when.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}
          {readBy && t("run.readBy", { ai: readBy })}
        </p>
        {!!counts?.total && <p role="status" className="mt-2 text-sm text-ink-soft">{t("run.analysisCounts", counts)}{counts.pending > 0 && ` ${t("run.analysisPending", { n: counts.pending })}`}</p>}
        {run.request?.scrape_report && <ScrapeReportLine report={run.request.scrape_report} groups={savedGroupsFor(prefs, run.request)} />}
        <div className="mt-2 flex items-center justify-center gap-1 text-ink-soft">
          {!!run.posts?.length && (["md", "csv", "json"] as const).map((f) => (
            <Button key={f} variant="ghost" size="sm" onClick={() => api.download(run.id, f).catch((e) => alert(e.message))} className="font-mono text-xs hover:bg-sunken hover:text-ink hover:underline underline-offset-4">
              .{f}
            </Button>
          ))}
          {onRerun && run.request && (
            <IconButton onClick={() => onRerun(run.request)} aria-label={t("run.rerun")} title={t("run.rerun")} variant="ghost" size="sm" className="hover:text-ink">
              <RotateCcw className="size-3.5" />
            </IconButton>
          )}
          <IconButton onClick={remove} busy={deleting} aria-label={t("run.delete")} variant="ghost" size="sm" className="hover:text-danger">
            <Trash2 className="size-3.5" />
          </IconButton>
        </div>
      </header>
      <hr className="rule-double mt-4" />
      {(q.platform === "reddit" || q.platform === "x") && <p className="mt-3 text-xs leading-relaxed text-ink-soft" role="note">{t(q.platform === "reddit" ? "cmp.warning.redditPolicy" : "cmp.warning.xPolicy")}</p>}

      {failed || canContinue || canReanalyze || canReprocess ? (
        <>
        {failed && <div className="paper-card mt-8 rounded-2xl border-danger/40 p-5">
          <p className="font-semibold text-danger">{t(run.error_code === "error.ai_service_paused" ? "run.servicePaused" : run.error_code === "error.analysis_stopped" ? "run.aiPaused" : run.status === "analysis_failed" ? "run.analysisFailed" : "run.stopped")}</p>
          <p className="mt-2 text-sm whitespace-pre-wrap [overflow-wrap:anywhere]" title={run.error ?? undefined}>{serverMessage(run.error_code, run.error ?? "")}</p>
          {run.error_code === "error.browser_missing" && <a href="https://www.google.com/chrome/" target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex min-h-10 items-center text-sm text-link underline">{t("plat.downloadChrome")}</a>}
          {run.error_code === "error.ai_quota" && counts && <p className="mt-2 text-sm">{t("run.aiQuotaSaved", { total: counts.total, ai: counts.ai })}</p>}
          {run.progress?.ai?.state === "exhausted" && run.progress.ai.daily && <p className="mt-2 text-sm">{t("run.dailyQuotaExhausted")}</p>}
          {run.error_code === "error.ai_quota" && run.progress?.ai?.provider_id === "gemini" && <p className="mt-2 text-sm">{t(run.progress.ai.project_shared ? "run.sharedProjectDetected" : "run.projectQuotaHint")}</p>}
          <QuotaDiagnostics run={run} />
        </div>}
        {canContinue && <section className="paper-card mt-5 rounded-2xl p-5"><h2 className="font-headline text-xl">{t("run.continueAnalysis")}</h2><RetryAnalysis key={run.id} run={run} onStarted={() => { setRetry((n) => n + 1); onAnalysisStarted?.(); }} /></section>}
        {canReanalyze && <section className="paper-card mt-5 rounded-2xl p-5"><h2 className="font-headline text-xl">{t("run.reanalyzeAI")}</h2><p className="mt-2 text-sm text-ink-soft">{t("run.reanalyzeAIHint", { n: run.posts?.length ?? run.collected, requests: run.reanalyze_requests_estimate ?? 1 })}</p><RetryAnalysis key={`reanalyze-${run.id}`} run={run} reanalyzeAll onStarted={() => { setRetry((n) => n + 1); onAnalysisStarted?.(); }} /></section>}
        {canReprocess && <details className="paper-card mt-5 rounded-2xl border border-accent/30 p-5 text-left"><summary className="interactive-tap cursor-pointer font-headline text-xl">{t("run.reprocessAI")}</summary><p className="mt-2 text-sm text-ink-soft">{t("run.reanalyzeAIHint", { n: run.analysis_counts?.total ?? run.collected, requests: run.reanalyze_requests_estimate ?? 1 })}</p>{run.reanalysis_active && counts?.pending ? <p role="status" className="mt-2 text-sm text-warning">{t("run.reanalysisPending", { n: counts.pending })}</p> : null}<RetryAnalysis key={`reprocess-${run.id}`} run={run} reanalyzeAll onStarted={() => { setRetry((n) => n + 1); onAnalysisStarted?.(); }} /></details>}
        {run.status === "done" && run.digest ? <Done run={run} meta={meta} tab={tab} setTab={setTab} /> : !!run.posts?.length && <section className="mt-8"><h2 className="mb-5 font-headline text-2xl">{t("run.savedPosts")}</h2><PostList posts={run.posts} filter={null} setFilter={() => {}} name={cat} /></section>}
        </>
      ) : run.status !== "done" || !run.digest ? (
        <><InProgress run={run} onStarted={() => { setRetry((n) => n + 1); onAnalysisStarted?.(); }} />
        {run.status === "analyzing" && !!run.posts?.length && <Done run={run} meta={meta} tab={tab} setTab={setTab} />}</>
      ) : (
        <Done run={run} meta={meta} tab={tab} setTab={setTab} />
      )}
    </div>
  );
}
