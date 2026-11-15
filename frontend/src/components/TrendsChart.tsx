import { useId, useState, type PointerEvent, type MouseEvent, type KeyboardEvent } from "react";
import type { SearchFilters, TrendsResponse } from "../types";
import { useI18n, formatNumber } from "../i18n";
import { routeHref } from "../router";
import { trendSearchFilters } from "../search";
import { trendColor, trendPath, trendPoints } from "../trends";

interface Props {
  data: TrendsResponse;
  viewMode: "overview" | "grid";
  className?: string;
}

function snapTrendIndex(x: number, count: number, plotWidth = 730): number | null {
  if (count <= 0) return null;
  if (count === 1) return 0;
  return Math.max(0, Math.min(count - 1, Math.round(Math.max(0, Math.min(plotWidth, x)) / plotWidth * (count - 1))));
}

export function TrendsChart({ data, viewMode, className = "" }: Props) {
  const { t, locale, lang } = useI18n();
  const clipId = useId().replace(/:/g, "");
  const { timeline, series } = data;
  const latestIndex = timeline.length ? timeline.length - 1 : null;

  // Date navigation and pinning state
  const [viewedIndex, setViewedIndex] = useState<number | null>(() => latestIndex);
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const safeViewed = viewedIndex !== null && timeline.length ? Math.max(0, Math.min(timeline.length - 1, viewedIndex)) : latestIndex;
  const safePinned = pinnedIndex !== null && timeline.length ? Math.max(0, Math.min(timeline.length - 1, pinnedIndex)) : null;
  const safeHover = hoverIndex !== null && timeline.length ? Math.max(0, Math.min(timeline.length - 1, hoverIndex)) : null;

  // Effective current index: hover takes precedence for temporary preview, then pinned, then last viewed
  const current = safeHover ?? safePinned ?? safeViewed;

  // Series highlight state
  const [selectedSeries, setSelectedSeries] = useState<string | null>(null);
  const [hoveredSeries, setHoveredSeries] = useState<string | null>(null);
  const activeSeries = hoveredSeries ?? selectedSeries;

  const max = Math.max(4, Math.ceil(Math.max(0, ...series.flatMap((item) => item.counts)) / 4) * 4);
  const width = 730, height = 280;

  const date = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString(locale, { month: "short", day: "numeric", timeZone: "UTC" });
  const growth = (value: number | null) => value === null ? t("trends.newPeriod") : `${value > 0 ? "+" : ""}${formatNumber(value, lang)}%`;

  const pointerIndex = (event: PointerEvent<SVGRectElement>) => {
    const rect = event.currentTarget.ownerSVGElement!.getBoundingClientRect();
    return snapTrendIndex((event.clientX - rect.left) / rect.width * 800 - 46, timeline.length, width);
  };

  // Build target filters for "Tìm bài trong ngày/tuần này" link
  const currentDateStr = current !== null ? timeline[current] : undefined;
  let end = data.range.end_date;
  if (currentDateStr) {
    const day = new Date(`${currentDateStr}T00:00:00Z`);
    day.setUTCDate(day.getUTCDate() + (data.range.bucket === "week" ? 6 : 0));
    end = [day.toISOString().slice(0, 10), end].sort()[0];
  }
  const dateFrom = currentDateStr ? [currentDateStr, data.range.start_date].sort().at(-1)! : data.range.start_date;
  const exploreFilters: SearchFilters = {
    ...(selectedSeries ? (data.range.group === "topic" ? { topic_ids: [Number(selectedSeries)] } : { categories: [selectedSeries] }) : {}),
    date_from: dateFrom,
    date_to: end,
  };
  const exploreDateHref = routeHref({ page: "ask", filters: exploreFilters });

  const pinnedLabel = t("trends.pinned");
  const unpinLabel = t("trends.unpin");

  if (viewMode === "grid") return <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 ${className}`}>
    {series.map((item) => {
      const points = trendPoints(item.counts, 180, 50, max);
      const line = trendPath(points);
      const color = trendColor(item.color);
      return <a key={item.id} href={routeHref({ page: "ask", filters: trendSearchFilters(data, item.id) })} className="paper-card min-w-0 p-4 text-left transition-colors hover:border-ink-soft">
        <span className="flex items-start gap-2 text-sm font-semibold"><span className="mt-1 size-2.5 shrink-0 rounded-full" style={{ background: color }} /><span className="min-w-0 [overflow-wrap:anywhere]">{item.name}</span></span>
        <span className="mt-2 block text-sm">{t("trends.articles", { n: item.total })} <span className="ml-2 text-xs text-ink-soft">{growth(item.growth)}</span></span>
        <svg viewBox="-4 -4 188 58" className="mt-3 h-16 w-full overflow-hidden" aria-hidden="true">
          <defs><clipPath id={`${clipId}-${item.id}`}><rect width="180" height="50" /></clipPath></defs>
          <g clipPath={`url(#${clipId}-${item.id})`}><path d={points.length ? `${line} L ${points.at(-1)!.x} 50 L ${points[0].x} 50 Z` : ""} fill={color} fillOpacity="0.14" /><path d={line} fill="none" stroke={color} strokeWidth="2" /></g>
        </svg>
      </a>;
    })}
  </div>;

  const step = Math.max(1, Math.ceil((timeline.length - 1) / 5));
  const ticks = [...new Set([0, ...timeline.map((_, i) => i).filter((i) => i % step === 0), timeline.length - 1])].filter((i) => i >= 0);

  return <div className={`space-y-4 ${className}`}>
    <div className="paper-card min-w-0 overflow-hidden p-3 sm:p-5">
      <p id={`${clipId}-hint`} className="mb-3 text-xs text-ink-soft">{t("trends.stableHint")}</p>
      <svg
        viewBox="0 0 800 340"
        className="h-auto w-full overflow-hidden outline-none"
        tabIndex={0}
        role="img"
        aria-label={t("trends.title")}
        aria-describedby={`${clipId}-hint`}
        onKeyDown={(event: KeyboardEvent<SVGSVGElement>) => {
          if (event.key === "Enter") {
            event.preventDefault();
            if (current !== null) {
              setPinnedIndex(current);
              setViewedIndex(current);
              setHoverIndex(null);
            }
          } else if (event.key === "Escape") {
            event.preventDefault();
            setPinnedIndex(null);
            setViewedIndex(latestIndex);
            setHoverIndex(null);
          } else if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            const target = event.key === "Home"
              ? 0
              : event.key === "End"
              ? (timeline.length - 1)
              : Math.max(0, Math.min(timeline.length - 1, (current ?? 0) + (event.key === "ArrowRight" ? 1 : -1)));
            setViewedIndex(target);
            if (pinnedIndex !== null) {
              setPinnedIndex(target);
            }
          }
        }}
      >
        <defs><clipPath id={clipId}><rect x="46" y="24" width={width} height={height} /></clipPath></defs>
        {[0, 1, 2, 3, 4].map((tick) => <g key={tick}><line x1="46" x2="776" y1={24 + height - tick * height / 4} y2={24 + height - tick * height / 4} stroke="var(--line-strong)" strokeDasharray={tick ? "3,3" : undefined} /><text x="36" y={28 + height - tick * height / 4} textAnchor="end" className="fill-ink-soft font-mono text-[11px]">{formatNumber(max * tick / 4, lang)}</text></g>)}
        {ticks.map((tick) => <text key={tick} x={46 + (timeline.length <= 1 ? width / 2 : tick / (timeline.length - 1) * width)} y="328" textAnchor="middle" className="fill-ink-soft text-[11px]">{date(timeline[tick])}</text>)}
        <g clipPath={`url(#${clipId})`} data-trend-plot>
          {series.map((item) => {
            const points = trendPoints(item.counts.slice(0, timeline.length), width, height, max);
            const line = trendPath(points);
            const color = trendColor(item.color);
            const isHighlighted = activeSeries === item.id;
            // When no series is active, all lines share the exact same opacity (0.75) and stroke (1.4)
            const lineOpacity = activeSeries ? (isHighlighted ? 1 : 0.25) : 0.75;
            const strokeWidth = isHighlighted ? 2.4 : 1.4;

            return <g key={item.id} data-series-id={item.id} transform="translate(46 24)" opacity={lineOpacity}>
              {isHighlighted && points.length > 0 && <path d={`${line} L ${points.at(-1)!.x} ${height} L ${points[0].x} ${height} Z`} fill={color} fillOpacity="0.14" />}
              <path d={line} stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinejoin="round" />
              {isHighlighted && points.map((point, i) => (
                <circle
                  key={i}
                  cx={point.x}
                  cy={point.y}
                  r={i === current ? 4.5 : 2.5}
                  fill={color}
                  stroke="var(--paper)"
                  strokeWidth={1.5}
                />
              ))}
            </g>;
          })}
          {current !== null && <line x1={46 + (timeline.length <= 1 ? width / 2 : current / (timeline.length - 1) * width)} x2={46 + (timeline.length <= 1 ? width / 2 : current / (timeline.length - 1) * width)} y1="24" y2="304" stroke="var(--ink)" strokeDasharray="3,3" />}
        </g>
        <rect
          data-trend-hover
          x="46"
          y="24"
          width={width}
          height={height}
          fill="transparent"
          pointerEvents="all"
          className="cursor-crosshair"
          onPointerMove={(event) => {
            const idx = pointerIndex(event);
            if (idx !== null) {
              setHoverIndex(idx);
              setViewedIndex(idx);
            }
          }}
          onPointerLeave={() => {
            setHoverIndex(null);
          }}
          onPointerDown={(event) => {
            const idx = pointerIndex(event);
            if (idx !== null) {
              setHoverIndex(idx);
              setViewedIndex(idx);
            }
          }}
          onClick={(event: MouseEvent<SVGRectElement>) => {
            const rect = event.currentTarget.ownerSVGElement!.getBoundingClientRect();
            const selected = snapTrendIndex((event.clientX - rect.left) / rect.width * 800 - 46, timeline.length, width);
            if (selected !== null) {
              setPinnedIndex(selected);
              setViewedIndex(selected);
              setHoverIndex(null);
            }
          }}
        />
      </svg>
      <div data-trend-details role="status" aria-live="polite" className="mt-3 h-64 overflow-y-auto border-t border-line pt-3 text-sm">
        {safePinned !== null ? (
          <div className="flex flex-wrap items-center gap-1.5 font-medium">
            <span className="font-semibold text-ink">
              {pinnedLabel} {date(timeline[safePinned])}
            </span>
            <span className="text-line">·</span>
            <button
              type="button"
              onClick={() => {
                setPinnedIndex(null);
                setViewedIndex(latestIndex);
              }}
              className="text-link underline hover:text-link-hover text-xs font-normal"
            >
              {unpinLabel}
            </button>
            {safeHover !== null && safeHover !== safePinned && (
              <span className="text-xs text-ink-soft ml-1">
                ({date(timeline[safeHover])})
              </span>
            )}
          </div>
        ) : (
          <p className="font-medium">
            {current !== null ? (
              current === latestIndex && viewedIndex === latestIndex ? (
                `${t("trends.latestDate")} · ${date(timeline[current])}`
              ) : (
                date(timeline[current])
              )
            ) : (
              t("trends.periodTotals")
            )}
          </p>
        )}

        <ul className="mt-2 grid gap-x-5 gap-y-1 sm:grid-cols-2">
          {series.map((item) => {
            const isSelected = selectedSeries === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setSelectedSeries((prev) => prev === item.id ? null : item.id)}
                  onPointerEnter={() => setHoveredSeries(item.id)}
                  onPointerLeave={() => setHoveredSeries(null)}
                  onFocus={() => setHoveredSeries(item.id)}
                  onBlur={() => setHoveredSeries(null)}
                  className={`flex w-full min-h-10 min-w-0 items-center gap-2 rounded-lg px-2 text-left transition-colors ${
                    isSelected
                      ? "bg-sunken font-semibold ring-1 ring-accent text-ink"
                      : "hover:bg-sunken focus-visible:bg-sunken text-ink"
                  }`}
                >
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: trendColor(item.color) }} />
                  <span className="min-w-0 flex-1 truncate" title={item.name}>{item.name}</span>
                  <span className="shrink-0 font-mono text-ink">
                    {formatNumber(current === null ? item.total : item.counts[current] ?? 0, lang)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        {current !== null && (
          <div className="mt-2">
            <a
              href={exploreDateHref}
              className="inline-flex min-h-11 items-center text-link underline hover:text-link-hover text-sm"
            >
              {t("trends.exploreDate")}
            </a>
          </div>
        )}
      </div>
    </div>
    <div role="group" aria-label={t("trends.focalSeries")} className="flex max-w-full gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:flex-wrap sm:pr-0 sm:[mask-image:none]">
      {series.map((item) => {
        const isSelected = selectedSeries === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setSelectedSeries((prev) => prev === item.id ? null : item.id)}
            onPointerEnter={() => setHoveredSeries(item.id)}
            onPointerLeave={() => setHoveredSeries(null)}
            onFocus={() => setHoveredSeries(item.id)}
            onBlur={() => setHoveredSeries(null)}
            className={`flex min-h-11 shrink-0 items-center gap-2 rounded-full border px-3 text-sm transition-colors ${
              isSelected
                ? "border-accent bg-sunken font-semibold text-ink ring-1 ring-accent"
                : "border-line hover:bg-sunken text-ink"
            }`}
          >
            <span className="size-2.5 rounded-full" style={{ background: trendColor(item.color) }} />
            <span>{item.name}</span>
            <span className="font-mono text-xs text-ink-soft">{formatNumber(item.total, lang)}</span>
          </button>
        );
      })}
    </div>
  </div>;
}
