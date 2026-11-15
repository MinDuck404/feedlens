import { useEffect, useState, useMemo } from "react";
import { TrendingUp, Layers, Sparkles, FilterX, AlertCircle } from "lucide-react";
import { api } from "../api";
import { formatNumber, useI18n } from "../i18n";
import type { TrendsResponse } from "../types";
import { TrendsChart } from "./TrendsChart";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";
import { SegmentedControl } from "./ui/SegmentedControl";
import { Skeleton } from "./ui/Skeleton";

interface Props {
  onNewRun: () => void;
}

export default function TrendsPage({ onNewRun }: Props) {
  const { t, cat, lang } = useI18n();

  const [group, setGroup] = useState<"category" | "topic">("category");
  const [bucket, setBucket] = useState<"day" | "week">("day");
  const [days, setDays] = useState<number>(30);
  const [viewMode, setViewMode] = useState<"overview" | "grid">(() => window.matchMedia?.("(max-width: 639px)").matches ? "grid" : "overview");
  const [activeSeriesId, setActiveSeriesId] = useState<string | null>(null);

  const [rawData, setData] = useState<TrendsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [retry, setRetry] = useState(0);
  const loadTrends = () => setRetry((value) => value + 1);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null);
    api.trends({ group, bucket, days }).then((result) => {
      if (!alive) return;
      setData(result);
      setActiveSeriesId((current) => result.series.some((item) => item.id === current) ? current : null);
    }).catch((err) => { if (alive) setError(err.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [group, bucket, days, retry]);
  const data = useMemo(() => rawData ? {
    ...rawData,
    series: rawData.series.map((item) => ({ ...item, name: rawData.range.group === "category" ? cat(item.id) : item.name })),
    summary: {
      ...rawData.summary,
      top_gainer: rawData.summary.top_gainer ? { ...rawData.summary.top_gainer, name: rawData.range.group === "category" ? cat(rawData.summary.top_gainer.id) : rawData.summary.top_gainer.name } : null,
      new_emerging: rawData.summary.new_emerging ? { ...rawData.summary.new_emerging, name: rawData.range.group === "category" ? cat(rawData.summary.new_emerging.id) : rawData.summary.new_emerging.name } : null,
    },
  } : null, [rawData, cat]);

  const activeSeries = useMemo(() => {
    if (!data || !activeSeriesId) return null;
    return data.series.find((s) => s.id === activeSeriesId) ?? null;
  }, [data, activeSeriesId]);

  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-start px-4 py-8 sm:px-6 md:py-12">
      {/* Header phong cách báo in Fiorinda */}
      <header className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft mb-2">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-accent" />
            <span className="font-semibold text-ink">{t("trends.eyebrow")}</span>
            <span className="hidden sm:inline text-line">•</span>
            <span className="hidden sm:inline font-mono">{data?.range.start_date} → {data?.range.end_date}</span>
          </div>
        </div>

        <h1 className="font-headline text-3xl font-normal tracking-tight text-ink sm:text-4xl md:text-5xl leading-[1.15]">
          <span>{t("trends.title")}</span>
        </h1>
        <p className="mt-2 text-base text-ink-soft leading-relaxed max-w-2xl">
          {t("trends.subtitle")}
        </p>
      </header>

      <div className="rule-double mb-6" />

      {/* Toolbar / Controls */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-line pb-5">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Nhóm theo (Group By) */}
          <SegmentedControl
            label={t("trends.group")}
            value={group}
            onChange={(v) => {
              setGroup(v as "category" | "topic");
              setActiveSeriesId(null);
            }}
            options={[
              { value: "category", label: t("trends.groupCategory") },
              { value: "topic", label: t("trends.groupTopic") },
            ]}
            compact
          />

          {/* Chu kỳ (Bucket) */}
          <SegmentedControl
            label={t("trends.bucket")}
            value={bucket}
            onChange={(v) => setBucket(v as "day" | "week")}
            options={[
              { value: "day", label: t("trends.bucketDay") },
              { value: "week", label: t("trends.bucketWeek") },
            ]}
            compact
          />

          {/* Khoảng thời gian (Range) */}
          <SegmentedControl
            label={t("trends.range")}
            value={String(days)}
            onChange={(v) => setDays(Number(v))}
            options={[
              { value: "7", label: t("trends.days7") },
              { value: "30", label: t("trends.days30") },
              { value: "90", label: t("trends.days90") },
            ]}
            compact
          />
        </div>

        {/* Chế độ xem: Biểu đồ tổng quan vs Lưới từng chủ đề */}
        <div className="flex items-center gap-2">
          <SegmentedControl
            label={t("trends.view")}
            value={viewMode}
            onChange={(v) => setViewMode(v as "overview" | "grid")}
            options={[
              { value: "overview", label: t("trends.viewOverview") },
              { value: "grid", label: t("trends.viewGrid") },
            ]}
            compact
          />
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div
          role="alert"
          className="mb-6 flex items-center justify-between gap-3 border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger rounded-xl"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0" />
            <span className="font-medium">{error}</span>
          </div>
          <Button size="sm" variant="outline" onClick={loadTrends}>
            {t("act.retry")}
          </Button>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Skeleton height="86px" rounded="xl" />
            <Skeleton height="86px" rounded="xl" />
            <Skeleton height="86px" rounded="xl" />
          </div>
          <Skeleton height="360px" rounded="2xl" />
        </div>
      ) : data && !error && (data.summary.total_posts === 0 || !data.series.some((item) => item.total > 0)) ? (
        /* Empty State */
        <EmptyState
          icon={<TrendingUp className="size-6 text-accent" />}
          title={group === "topic" && data.series.length === 0 ? t("trends.noTopics") : t("trends.noData")}
          description={
            group === "topic" && data.series.length === 0
              ? t("trends.noTopicsHint")
              : t("trends.noDataHint")
          }
          action={{
            label: t("act.newRun"),
            onClick: onNewRun,
          }}
          className="my-8"
        />
      ) : data && !error ? (
        /* Data Content */
        <div className="space-y-6">
          <p className="text-xs leading-relaxed text-ink-soft">{t("trends.comparison", { days })}</p>
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Thẻ 1: Tổng số bài */}
            <div className="paper-card p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-ink-soft mb-1">
                <span className="font-medium uppercase tracking-wider text-[11px]">{t("trends.totalVolume")}</span>
                <Layers className="size-4 text-ink-soft opacity-70" />
              </div>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-headline text-3xl sm:text-4xl font-semibold text-ink tabular-nums">
                  {formatNumber(data.summary.total_posts, lang)}
                </span>
                <span className="text-xs text-ink-soft">{t("trends.unit")}</span>
              </div>
            </div>

            {/* Thẻ 2: Tăng mạnh nhất */}
            <div className="paper-card p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-ink-soft mb-1">
                <span className="font-medium uppercase tracking-wider text-[11px]">{t("trends.topGainer")}</span>
                <TrendingUp className="size-4 text-ok" />
              </div>
              <div>
                {data.summary.top_gainer ? (
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-semibold text-base sm:text-lg text-ink truncate max-w-[160px]">
                      {data.summary.top_gainer.name}
                    </span>
                    <span className="font-mono text-xs font-semibold text-ok bg-ok/10 px-2 py-0.5 rounded-full">
                      +{formatNumber(data.summary.top_gainer.growth, lang)}%
                    </span>
                  </div>
                ) : (
                  <span className="text-sm text-ink-soft italic">{t("trends.noGainer")}</span>
                )}
              </div>
            </div>

            {/* Thẻ 3: Mới xuất hiện */}
            <div className="paper-card p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-ink-soft mb-1">
                <span className="font-medium uppercase tracking-wider text-[11px]">{t("trends.newEmerging")}</span>
                <Sparkles className="size-4 text-accent" />
              </div>
              <div>
                {data.summary.new_emerging ? (
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-semibold text-base sm:text-lg text-ink truncate max-w-[160px]">
                      {data.summary.new_emerging.name}
                    </span>
                    <span className="font-mono text-xs text-ink-soft">
                      {t("trends.articles", { n: data.summary.new_emerging.count })}
                    </span>
                  </div>
                ) : (
                  <span className="text-sm text-ink-soft italic">{t("trends.noEmerging")}</span>
                )}
              </div>
            </div>
          </div>

          {/* Active Filter Indicator */}
          {activeSeries && (
            <div className="flex flex-wrap items-center justify-between gap-3 bg-sunken border border-line px-4 py-2.5 rounded-xl text-xs">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="size-2.5 rounded-full shrink-0" style={{ backgroundColor: activeSeries.color }} />
                <span className="text-ink-soft">
                  {t("trends.focalSeries")}: {activeSeries.name}
                </span>
                <b className="text-ink font-semibold">
                  {t("trends.articles", { n: activeSeries.total })}
                </b>
              </div>
              <button
                type="button"
                onClick={() => setActiveSeriesId(null)}
                className="flex items-center gap-1 font-medium text-accent hover:underline cursor-pointer"
              >
                <FilterX className="size-3.5" />
                <span>{t("trends.clearFilter")}</span>
              </button>
            </div>
          )}

          {/* Biểu đồ chính */}
          <TrendsChart
            key={`${group}-${bucket}-${days}`}
            data={data}
            activeSeriesId={activeSeriesId}
            onSelectSeries={setActiveSeriesId}
            viewMode={viewMode}
          />

          {/* Chú thích nguồn ngày tháng */}
          <footer className="mt-8 border-t border-line/70 pt-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs text-ink-soft">
            <div className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-accent" />
              <span>{t("trends.footnote")}</span>
            </div>
            {data.fallback_count > 0 && (
              <span className="font-mono opacity-80">
                {t("trends.fallback", { n: data.fallback_count })}
              </span>
            )}
          </footer>
        </div>
      ) : null}
    </div>
  );
}
