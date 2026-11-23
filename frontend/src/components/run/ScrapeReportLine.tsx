import { ChevronDown, History, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { useI18n, type Key } from "../../i18n";
import { formatDuration, runTimingSummary, scrapeSourceRows, type TimingKey } from "../../logic";
import type { Preferences, RunRequest, SavedGroup, ScrapeReport } from "../../types";

export function savedGroupsFor(prefs: Preferences | null | undefined, request: RunRequest): SavedGroup[] {
  const stored = (prefs as { saved_sources?: Record<string, SavedGroup[]> } | null | undefined)?.saved_sources ?? {};
  return [...(stored[`${request.platform}:${request.mode ?? "group"}`] ?? []), ...Object.values(stored).flat(), ...(prefs?.groups?.[request.platform] ?? [])];
}

export function ScrapeReportLine({ report, groups }: { report: ScrapeReport; groups: SavedGroup[] }) {
  const { t, lang } = useI18n();
  const reason = report.stop_reason && report.stop_reason !== "target_reached" ? t(`run.stop.${report.stop_reason}` as Key) : "";
  const timing = runTimingSummary(report.timings);
  const sources = scrapeSourceRows(report.sources, groups, report.sources?.some((source) => source.status === "running" || source.status === "pending"));
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const detailsOpen = expanded ?? sources.length <= 5;
  const withPosts = sources.filter((source) => source.collected > 0).length;
  const empty = sources.filter((source) => source.collected === 0).length;
  const label = (key: TimingKey, seconds: number) => `${t(`run.timing.${key}` as Key)} ${formatDuration(seconds, lang)}`;
  return (
    <>
      {report.target !== undefined && (
        <p className="mt-1 text-xs leading-relaxed text-ink-soft">
          {t("run.scrapeReport", { got: report.collected ?? 0, target: report.target, old: report.skipped_old ?? 0 })}
          {!!report.skipped_ads && ` · ${t("run.scrapeAds", { n: report.skipped_ads })}`}
          {reason && ` · ${reason}`}
        </p>
      )}
      {sources.length > 0 && <section aria-label={t("run.sources.details", { n: sources.length })} className="mx-auto mt-3 max-w-3xl text-left">
        <details open={detailsOpen} onToggle={(event) => setExpanded(event.currentTarget.open)}>
          <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-3 text-sm text-ink-soft [&::-webkit-details-marker]:hidden">
            <span>{t("run.sources.summary", { total: sources.length, withPosts, empty })}</span>
            <ChevronDown aria-hidden="true" className={`size-4 shrink-0 transition-transform ${detailsOpen ? "rotate-180" : ""}`} />
            <span className="sr-only">{t("run.sources.details", { n: sources.length })}</span>
          </summary>
          <div className="mt-2 overflow-hidden rounded-xl border border-line bg-surface">
            <div className="hidden grid-cols-[minmax(0,1fr)_200px_100px_128px] gap-x-4 border-b border-line px-3 py-1.5 text-xs text-ink-faint sm:grid">
              <span>{t("run.sources.group")}</span><span>{t("run.sources.posts")}</span><span className="text-right">{t("run.sources.skippedOld")}</span><span>{t("run.sources.status")}</span>
            </div>
            <ul className="divide-y divide-line">
              {sources.map((source, index) => {
                const statusKey = source.status === "running" ? "run.source.running"
                  : source.status === "pending" ? "run.source.pending"
                    : source.status === "error" || source.stop_reason === "interrupted" ? "run.source.error"
                      : source.stop_reason === "target_reached" ? "run.source.reached"
                        : source.stop_reason === "caught_up" ? "run.source.caughtUp"
                          : source.stop_reason === "budget_exhausted" ? "run.source.budget"
                            : source.stop_reason === "no_more_posts" ? "run.source.noMorePosts" : "run.source.done";
                const status = t(statusKey);
                const detail = source.stop_reason ? t(`run.stop.${source.stop_reason}` as Key) : status;
                const progress = source.target && source.target > 0 ? Math.min(100, source.collected / source.target * 100) : 0;
                const max = Math.max(source.target ?? 0, source.collected, 1);
                const tone = statusKey === "run.source.running" ? "border-accent/30 bg-accent/10 text-link"
                  : statusKey === "run.source.error" ? "border-danger/30 bg-danger/5 text-danger"
                    : source.collected === 0 && source.status === "done" ? "border-warning/30 bg-warning/10 text-warning"
                      : "border-line bg-sunken text-ink-soft";
                const skippedLabel = t("run.sources.skippedOldCount", { n: source.skipped_old });
                const duplicatesLabel = t("run.sources.skippedDupCount", { n: source.skipped_dup });
                return <li key={`${source.name}-${index}`} className="grid min-w-0 grid-cols-[minmax(0,1fr)_112px_56px_88px] items-center gap-x-1 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_200px_100px_128px] sm:gap-x-4">
                  <span className="min-w-0 truncate text-sm font-medium text-ink" title={source.name}>{source.name}</span>
                  <span className="grid min-w-0 grid-cols-[9ch_minmax(0,1fr)] items-center gap-1.5 font-mono text-xs tabular-nums text-ink">
                    <span className={`whitespace-nowrap ${source.collected === 0 && source.status === "done" ? "text-warning" : ""}`}>{String(source.collected).padStart(3, " ")} / {source.target == null ? "—" : String(source.target).padStart(3, " ")}</span>
                    {source.target != null && <span role="progressbar" aria-label={t("run.sources.progress", { name: source.name, got: source.collected, target: source.target })} aria-valuemin={0} aria-valuemax={max} aria-valuenow={source.collected} className="h-1 w-7 shrink-0 overflow-hidden rounded-full bg-line sm:w-16">
                      <span className="block h-full rounded-full bg-accent" style={{ width: `${progress}%` }} />
                    </span>}
                  </span>
                  <span aria-label={`${skippedLabel}${source.skipped_dup ? `; ${duplicatesLabel}` : ""}`} title={`${skippedLabel}${source.skipped_dup ? ` · ${duplicatesLabel}` : ""}`} className="inline-flex min-w-0 items-center justify-end gap-1 text-xs tabular-nums text-ink-soft">
                    <History aria-hidden="true" className="size-3.5 shrink-0" /><span>{String(source.skipped_old).padStart(3, " ")}</span>{!!source.skipped_dup && <span className="sr-only">, {duplicatesLabel}</span>}
                  </span>
                  <span title={detail} aria-label={`${status}: ${detail}`} className={`inline-flex w-full items-center justify-center gap-1 rounded-full border px-1.5 py-0.5 text-center text-xs leading-tight ${tone}`}>
                    {source.status === "running" && <LoaderCircle aria-hidden="true" className="size-3 shrink-0 animate-spin motion-reduce:animate-none" />}
                    <span className="truncate">{status}</span>
                  </span>
                </li>;
              })}
            </ul>
          </div>
        </details>
      </section>}
      {timing && (
        <details className="mx-auto mt-1 max-w-prose text-xs leading-relaxed text-ink-soft">
          <summary className="interactive-tap cursor-pointer [overflow-wrap:anywhere]">
            {t("run.timing.title")}: {timing.main.map((p) => label(p.key, p.seconds)).join(" · ")}
          </summary>
          {(timing.detail.length > 0 || !!report.full_text_from_story) && (
            <p className="mt-1 [overflow-wrap:anywhere]">
              {timing.detail.length > 0 && `${t("run.timing.details")}: ${timing.detail.map((p) => label(p.key, p.seconds)).join(" · ")}`}
              {!!report.full_text_from_story && <span className="block">{t("run.timing.fullText", { n: report.full_text_from_story })}</span>}
            </p>
          )}
        </details>
      )}
    </>
  );
}
