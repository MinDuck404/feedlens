import { useEffect, useState, useMemo } from "react";
import { TrendingUp, Layers, Sparkles, AlertCircle } from "lucide-react";
import { api } from "../api";
import { formatNumber, useI18n } from "../i18n";
import type { TrendsResponse } from "../types";
import { TrendsChart } from "./TrendsChart";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";
import { SegmentedControl } from "./ui/SegmentedControl";
import { Skeleton } from "./ui/Skeleton";

export const TRENDS_FILTERS_KEY = "feedlens.trendsFilters";

export type TrendGroup = "category" | "topic";
export type TrendBucket = "day" | "week";
export type TrendDays = 7 | 30 | 90;
export type TrendViewMode = "overview" | "grid";

export interface TrendsFiltersState {
  group: TrendGroup;
  bucket: TrendBucket;
  days: TrendDays;
  viewMode: TrendViewMode;
}

export const VALID_GROUPS: readonly TrendGroup[] = ["category", "topic"] as const;
export const VALID_BUCKETS: readonly TrendBucket[] = ["day", "week"] as const;
export const VALID_DAYS: readonly TrendDays[] = [7, 30, 90] as const;
export const VALID_VIEW_MODES: readonly TrendViewMode[] = ["overview", "grid"] as const;

export function parseTrendsFilters(
  rawQuery?: string | URLSearchParams | null,
  rawStored?: string | null,
  isMobile = false
): TrendsFiltersState {
  const defaults: TrendsFiltersState = {
    group: "category",
    bucket: "day",
    days: 30,
    viewMode: isMobile ? "grid" : "overview",
  };

  let stored: Record<string, unknown> = {};
  if (rawStored) {
    try {
      const parsed = JSON.parse(rawStored);
      if (parsed && typeof parsed === "object") stored = parsed as Record<string, unknown>;
    } catch {
      // Ignored
    }
  }

  let params: URLSearchParams | null = null;
  if (rawQuery instanceof URLSearchParams) {
    params = rawQuery;
  } else if (typeof rawQuery === "string") {
    const qIdx = rawQuery.indexOf("?");
    const qStr = qIdx >= 0 ? rawQuery.slice(qIdx + 1) : rawQuery;
    params = new URLSearchParams(qStr);
  }

  // Priority order: URL > localStorage > defaults
  let group: TrendGroup = defaults.group;
  const sGroup = stored.group;
  if (sGroup === "category" || sGroup === "topic") group = sGroup;
  const qGroup = params?.get("group");
  if (qGroup === "category" || qGroup === "topic") group = qGroup;

  let bucket: TrendBucket = defaults.bucket;
  const sBucket = stored.bucket;
  if (sBucket === "day" || sBucket === "week") bucket = sBucket;
  const qBucket = params?.get("bucket");
  if (qBucket === "day" || qBucket === "week") bucket = qBucket;

  let days: TrendDays = defaults.days;
  const sDays = Number(stored.days ?? stored.range);
  if (sDays === 7 || sDays === 30 || sDays === 90) days = sDays as TrendDays;
  const qRange = params?.get("range") ?? params?.get("days");
  if (qRange) {
    const num = Number(qRange);
    if (num === 7 || num === 30 || num === 90) days = num as TrendDays;
  }

  let viewMode: TrendViewMode = defaults.viewMode;
  const sView = stored.viewMode ?? stored.view;
  if (sView === "overview" || sView === "grid") viewMode = sView as TrendViewMode;
  const qView = params?.get("view") ?? params?.get("viewMode");
  if (qView === "overview" || qView === "grid") viewMode = qView as TrendViewMode;

  return { group, bucket, days, viewMode };
}

export function serializeTrendsFilters(filters: TrendsFiltersState): string {
  const params = new URLSearchParams();
  params.set("group", filters.group);
  params.set("bucket", filters.bucket);
  params.set("range", String(filters.days));
  params.set("view", filters.viewMode);
  return params.toString();
}

interface Props {
  onNewRun: () => void;
}

export default function TrendsPage({ onNewRun }: Props) {
  const { t, cat, lang } = useI18n();

  const isMobile = typeof window !== "undefined" && typeof window.matchMedia === "function" && !!window.matchMedia("(max-width: 639px)").matches;
  const readInitial = () => {
    let stored: string | null = null;
    if (typeof localStorage !== "undefined") {
      try {
        stored = localStorage.getItem(TRENDS_FILTERS_KEY);
      } catch {
        // Ignored
      }
    }
    const hash = typeof window !== "undefined" && window.location ? window.location.hash : "";
    return parseTrendsFilters(hash, stored, isMobile);
  };

  const initial = useMemo(readInitial, []);
  const [group, setGroup] = useState<TrendGroup>(initial.group);
  const [bucket, setBucket] = useState<TrendBucket>(initial.bucket);
  const [days, setDays] = useState<TrendDays>(initial.days);
  const [viewMode, setViewMode] = useState<TrendViewMode>(initial.viewMode);

  // Sync state to localStorage and URL query params
  useEffect(() => {
    const currentFilters: TrendsFiltersState = { group, bucket, days, viewMode };
    if (typeof localStorage !== "undefined") {
      try {
        localStorage.setItem(TRENDS_FILTERS_KEY, JSON.stringify(currentFilters));
      } catch {
        // Ignored
      }
    }
    const query = serializeTrendsFilters(currentFilters);
    const targetHash = `#/trends?${query}`;
    if (typeof window !== "undefined" && window.location && window.location.hash !== targetHash && window.location.hash.startsWith("#/trends")) {
      if (typeof history !== "undefined" && history.replaceState) {
        history.replaceState(null, "", targetHash);
      }
    }
  }, [group, bucket, days, viewMode]);

  // Synchronize on browser history navigation (back/forward)
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onHashChange = () => {
      if (!window.location?.hash?.startsWith("#/trends")) return;
      let stored: string | null = null;
      if (typeof localStorage !== "undefined") {
        try {
          stored = localStorage.getItem(TRENDS_FILTERS_KEY);
        } catch {
          // Ignored
        }
      }
      const next = parseTrendsFilters(window.location.hash, stored, !!window.matchMedia?.("(max-width: 639px)").matches);
      setGroup((prev) => prev !== next.group ? next.group : prev);
      setBucket((prev) => prev !== next.bucket ? next.bucket : prev);
      setDays((prev) => prev !== next.days ? next.days : prev);
      setViewMode((prev) => prev !== next.viewMode ? next.viewMode : prev);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

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
    }
  } : null, [rawData, cat]);

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
            onChange={(v) => setDays(Number(v) as TrendDays)}
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
            <span>{error}</span>
          </div>
          <Button size="sm" variant="secondary" onClick={loadTrends}>
            {t("act.retry")}
          </Button>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !rawData ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Skeleton className="h-24 w-full rounded-2xl" />
            <Skeleton className="h-24 w-full rounded-2xl" />
            <Skeleton className="h-24 w-full rounded-2xl" />
          </div>
          <Skeleton className="h-[360px] w-full rounded-2xl" />
        </div>
      ) : data && (!data.series.length || !data.series.some((item) => item.total > 0)) ? (
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

          {/* Biểu đồ chính */}
          <TrendsChart
            key={`${group}-${bucket}-${days}`}
            data={data}
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
