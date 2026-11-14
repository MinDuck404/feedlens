import { Briefcase, ChevronRight } from "lucide-react";
import { PLATFORM_LABEL } from "../categories";
import { useI18n, type Key } from "../i18n";
import { routeHref } from "../router";
import type { Run } from "../types";
import { STATUS_CLS } from "./Sidebar";

export default function HistoryPage({ runs, onOpen, onNewRun }: {
  runs: Run[]; onOpen: (id: number) => void; onNewRun: () => void;
}) {
  const { t, locale } = useI18n();
  const jobsRuns = runs.filter((r) => r.request.job_mode).length;

  const when = (iso: string) =>
    new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z")
      .toLocaleString(locale, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

  const sourceLabel = (r: Run): string => {
    const q = r.request;
    if (q.source_type === "feed") return t("run.feedOf", { platform: PLATFORM_LABEL[q.platform] });
    const short = (s: string) => s.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
    const first = short(q.sources[0] ?? "");
    return q.sources.length > 1 ? t("run.andMore", { first, n: q.sources.length - 1 }) : first;
  };

  return (
    <div className="mx-auto max-w-4xl px-5 py-10 md:px-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold tracking-[-0.03em]">{t("hist.title")}</h1>
          <p className="mt-1 font-mono text-xs text-ink-soft">{t("hist.summary", { n: runs.length, j: jobsRuns })}</p>
        </div>
        <button onClick={onNewRun} className="rounded-full bg-primary px-5 py-2.5 font-semibold text-primary-ink hover:opacity-90">
          {t("act.newRun")}
        </button>
      </header>

      {runs.length === 0 ? (
        <p className="paper-card mt-8 rounded-2xl px-6 py-10 text-center text-ink-soft">{t("hist.empty")}</p>
      ) : (
        <ul className="paper-card mt-8 divide-y divide-line overflow-hidden rounded-2xl">
          {runs.map((r) => (
            <li key={r.id}>
              <a href={routeHref({ page: "run", id: r.id, tab: "digest" })}
                onClick={(e) => { e.preventDefault(); onOpen(r.id); }}
                className="group flex items-center gap-4 px-5 py-4 hover:bg-sunken/60">
                <span className="w-24 shrink-0 font-mono text-xs text-ink-soft">{when(r.created_at)}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate font-medium">{sourceLabel(r)}</span>
                    {r.request.job_mode && (
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-sunken px-2 py-0.5 text-xs">
                        <Briefcase className="size-3" /> {t("hist.jobTag")}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-ink-soft">
                    {PLATFORM_LABEL[r.request.platform]}
                    {r.ai_label && <>, {r.ai_label}</>}
                  </span>
                </span>
                <span className="hidden w-16 text-right font-mono text-sm sm:block">{r.collected || "–"}</span>
                <span className={`w-24 text-right font-mono text-xs ${STATUS_CLS[r.status] ?? ""}`}>{t(`status.${r.status}` as Key)}</span>
                <ChevronRight className="size-4 text-ink-soft transition-transform group-hover:translate-x-0.5" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
