import { Briefcase, ChevronRight, Inbox, Plus } from "lucide-react";
import { describeRunSource, parseTimestamp } from "../lib/logic";
import { PLATFORM_LABEL } from "../lib/categories";
import { formatNumber, useI18n, type Key } from "../i18n";
import { routeHref } from "../router";
import type { Run } from "../api/types";
import { STATUS_CLS } from "./Sidebar";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";

interface Props {
  runs: Run[];
  onOpen: (id: number) => void;
  onNewRun: () => void;
}

export default function HistoryPage({ runs, onOpen, onNewRun }: Props) {
  const { t, locale, lang } = useI18n();
  const jobsRuns = runs.filter((r) => r.request.job_mode).length;

  const when = (iso: string) =>
    parseTimestamp(iso).toLocaleString(locale, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });

  const sourceLabel = (r: Run): string => {
    return describeRunSource(r.request, t, "history");
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-10 md:px-10">
      {/* Newspaper Masthead Header */}
      <header className="masthead mb-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 font-sans text-xs text-ink-soft mb-1">
              <span className="size-2 rounded-full bg-accent" />
              <span>{t("hist.archiveSubtitle")}</span>
            </div>
            <h1 className="font-headline text-3xl sm:text-4xl font-normal tracking-tight text-ink">
              {t("hist.title")}
            </h1>
            <p className="mt-1 font-sans text-xs text-ink-soft">
              {t("hist.summary", { n: runs.length, j: jobsRuns })}
            </p>
          </div>
          <Button
            onClick={onNewRun}
            variant="primary"
            pill
            icon={<Plus className="size-4" />}
          >
            {t("act.newRun")}
          </Button>
        </div>
      </header>

      {/* Empty State vs List */}
      {runs.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            icon={<Inbox className="size-8" />}
            title={t("hist.empty")}
            action={{
              label: t("act.newRun"),
              onClick: onNewRun,
              icon: <Plus className="size-4" />,
            }}
          />
        </div>
      ) : (
        <div className="mt-8 border-t border-line">
          <ul className="divide-y divide-line">
            {runs.map((r, i) => (
              <li
                key={r.id}
                className="stagger-item"
                style={{ animationDelay: `${Math.min(i * 35, 350)}ms` }}
              >
                <a
                  href={routeHref({ page: "run", id: r.id, tab: "digest" })}
                  onClick={(e) => {
                    e.preventDefault();
                    onOpen(r.id);
                  }}
                  className="group block py-5 transition-colors hover:bg-sunken/40 active:bg-sunken"
                >
                  {/* Mobile Layout (<640px) */}
                  <div className="flex flex-col gap-1.5 lg:hidden">
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0 flex-1 line-clamp-2 font-headline text-lg font-medium text-ink group-hover:text-link transition-colors">
                        {sourceLabel(r)}
                      </span>
                      <span
                        className={`shrink-0 font-sans text-xs font-medium ${
                          STATUS_CLS[r.status] ?? ""
                        }`}
                      >
                        {t(`status.${r.status}` as Key)}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-ink-soft">
                      <div className="flex min-w-0 items-center gap-1.5 truncate">
                        <span className="font-sans text-[11px]">{when(r.created_at)}</span>
                        <span>•</span>
                        <span className="truncate">{PLATFORM_LABEL[r.request.platform]}</span>
                        {r.request.job_mode && (
                          <span className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-sunken px-1.5 py-0.5 text-[10px] font-medium text-ink">
                            <Briefcase className="size-2.5" /> {t("hist.jobTag")}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0 pl-2 font-mono tabular-nums text-ink">
                        <span>{r.collected ? formatNumber(r.collected, lang) : "–"}</span>
                        <ChevronRight className="size-3.5 text-ink-soft transition-transform group-hover:translate-x-0.5" />
                      </div>
                    </div>
                  </div>

                  {/* Desktop Layout (>=640px) */}
                  <div className="hidden lg:flex lg:items-center lg:gap-4">
                    <span className="w-28 shrink-0 font-sans text-xs text-ink-soft">
                      {when(r.created_at)}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="line-clamp-2 font-headline text-lg font-medium text-ink group-hover:text-link transition-colors">
                          {sourceLabel(r)}
                        </span>
                        {r.request.job_mode && (
                          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-sunken px-2 py-0.5 text-xs font-medium text-ink">
                            <Briefcase className="size-3" /> {t("hist.jobTag")}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 truncate text-xs text-ink-soft">
                        {PLATFORM_LABEL[r.request.platform]}
                        {r.ai_label && <>, {r.ai_label}</>}
                      </div>
                    </div>

                    <span className="w-20 text-right font-mono tabular-nums text-sm text-ink font-medium">
                      {r.collected ? formatNumber(r.collected, lang) : "–"}
                    </span>

                    <span
                      className={`w-28 text-right font-sans text-xs font-medium ${
                        STATUS_CLS[r.status] ?? ""
                      }`}
                    >
                      {t(`status.${r.status}` as Key)}
                    </span>

                    <ChevronRight className="size-4 shrink-0 text-ink-soft transition-transform group-hover:translate-x-0.5" />
                  </div>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
