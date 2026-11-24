import { useId, useState, type PointerEvent, type KeyboardEvent } from "react";
import type { SearchFilters, TrendsResponse } from "../api/types";
import { useI18n, formatNumber } from "../i18n";
import { routeHref } from "../router";
import { trendSearchFilters } from "../lib/search";
import { trendColor, trendPath, trendPoints } from "../lib/trends";

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

  // Date navigation: hovered date previews temporarily; leaving chart retains last viewed date; starts at latest date
  const [viewedIndex, setViewedIndex] = useState<number | null>(() => latestIndex);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const safeViewed = viewedIndex !== null && timeline.length ? Math.max(0, Math.min(timeline.length - 1, viewedIndex)) : latestIndex;
  const safeHover = hoverIndex !== null && timeline.length ? Math.max(0, Math.min(timeline.length - 1, hoverIndex)) : null;
  const current = safeHover ?? safeViewed;

  // Series highlight on hover/focus: default has no highlight (all lines equal opacity 0.75)
  const [hoveredSeries, setHoveredSeries] = useState<string | null>(null);
  const activeSeries = hoveredSeries;

  const max = Math.max(4, Math.ceil(Math.max(0, ...series.flatMap((item) => item.counts)) / 4) * 4);
  const width = 730, height = 280;

  const date = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString(locale, { month: "short", day: "numeric", timeZone: "UTC" });
  const growth = (value: number | null) => value === null ? t("trends.newPeriod") : `${value > 0 ? "+" : ""}${formatNumber(value, lang)}%`;

  const pointerIndex = (event: PointerEvent<SVGRectElement>) => {
    const rect = event.currentTarget.ownerSVGElement!.getBoundingClientRect();
    return snapTrendIndex((event.clientX - rect.left) / rect.width * 800 - 46, timeline.length, width);
  };

  // Date range for search links
  const currentDateStr = current !== null ? timeline[current] : undefined;
  let end = data.range.end_date;
  if (currentDateStr) {
    const day = new Date(`${currentDateStr}T00:00:00Z`);
    day.setUTCDate(day.getUTCDate() + (data.range.bucket === "week" ? 6 : 0));
    end = [day.toISOString().slice(0, 10), end].sort()[0];
  }
  const dateFrom = currentDateStr ? [currentDateStr, data.range.start_date].sort().at(-1)! : data.range.start_date;

  // Explore date link finds all posts for that day/week
  const exploreFilters: SearchFilters = {
    date_from: dateFrom,
    date_to: end,
  };
  const exploreDateHref = routeHref({ page: "ask", filters: exploreFilters });

  const seriesAriaLabel = ({ name, count }: { name: string; count: number }) => {
    const formattedCount = formatNumber(count, lang);
    const dateStr = current !== null ? date(timeline[current]) : "";
    if (lang === "vi") {
      return dateStr
        ? `Xem ${formattedCount} bài ${name} ngày ${dateStr}`
        : `Xem ${formattedCount} bài ${name}`;
    }
    if (lang === "zh") {
      return dateStr
        ? `查看 ${dateStr} ${name} 的 ${formattedCount} 篇`
        : `查看 ${name} 的 ${formattedCount} 篇`;
    }
    return dateStr
      ? `View ${formattedCount} ${name} posts on ${dateStr}`
      : `View ${formattedCount} ${name} posts`;
  };

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

  return <div className={`space-y-4 ${className}`}>
    <div className="paper-card p-4 sm:p-5">
      <svg
        viewBox="-4 -4 808 338"
        className="w-full overflow-visible select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-lg"
        tabIndex={0}
        role="region"
        aria-label={t("trends.chartHint")}
        onKeyDown={(event: KeyboardEvent<SVGSVGElement>) => {
          if (!timeline.length) return;
          const base = safeViewed ?? 0;
          let target = base;
          if (event.key === "ArrowLeft") target = Math.max(0, base - 1);
          else if (event.key === "ArrowRight") target = Math.min(timeline.length - 1, base + 1);
          else if (event.key === "Home") target = 0;
          else if (event.key === "End") target = timeline.length - 1;
          else return;
          event.preventDefault();
          setViewedIndex(target);
        }}
      >
        <defs><clipPath id={clipId}><rect x="46" y="24" width={width} height={height} /></clipPath></defs>
        <g stroke="var(--line)" strokeDasharray="2,3" opacity="0.8">
          {[0, 1, 2, 3, 4].map((step) => {
            const y = 24 + step * (height / 4);
            const value = Math.round(max * (1 - step / 4));
            return <g key={step}><line x1="46" x2="776" y1={y} y2={y} /><text x="40" y={y + 4} textAnchor="end" fontSize="11" fill="var(--ink-soft)" stroke="none">{formatNumber(value, lang)}</text></g>;
          })}
        </g>
        <g fill="var(--ink-soft)" fontSize="11" textAnchor="middle">
          {timeline.map((point, index) => {
            if (timeline.length > 10 && index % Math.ceil(timeline.length / 8) !== 0 && index !== timeline.length - 1) return null;
            const x = 46 + (timeline.length <= 1 ? width / 2 : index / (timeline.length - 1) * width);
            return <text key={point} x={x} y="324">{date(point)}</text>;
          })}
        </g>
        <g clipPath={`url(#${clipId})`}>
          {series.map((item) => {
            const points = trendPoints(item.counts, width, height, max);
            const line = trendPath(points);
            const color = trendColor(item.color);
            const isHighlighted = activeSeries === item.id;
            const lineOpacity = activeSeries === null ? 0.75 : isHighlighted ? 1 : 0.25;
            const strokeWidth = isHighlighted ? 2.5 : 1.4;

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
        />
      </svg>
      <div data-trend-details role="status" aria-live="polite" className="mt-3 border-t border-line pt-3 text-sm">
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

        <ul className="mt-2 grid gap-x-5 gap-y-1 sm:grid-cols-2">
          {series.map((item) => {
            const count = current === null ? item.total : item.counts[current] ?? 0;
            const isHovered = hoveredSeries === item.id;
            const seriesFilters: SearchFilters = {
              ...(data.range.group === "topic" ? { topic_ids: [Number(item.id)] } : { categories: [item.id] }),
              date_from: dateFrom,
              date_to: end,
            };
            const seriesHref = routeHref({ page: "ask", filters: seriesFilters });
            const ariaLabel = seriesAriaLabel({ name: item.name, count });

            return (
              <li key={item.id}>
                <a
                  href={seriesHref}
                  aria-label={ariaLabel}
                  onPointerEnter={() => setHoveredSeries(item.id)}
                  onPointerLeave={() => setHoveredSeries(null)}
                  onFocus={() => setHoveredSeries(item.id)}
                  onBlur={() => setHoveredSeries(null)}
                  className={`flex w-full min-h-10 min-w-0 items-center gap-2 rounded-lg px-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    isHovered
                      ? "bg-sunken font-semibold ring-1 ring-accent text-ink"
                      : "hover:bg-sunken text-ink"
                  }`}
                >
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: trendColor(item.color) }} />
                  <span className="min-w-0 flex-1 truncate" title={item.name}>{item.name}</span>
                  <span className="shrink-0 font-mono text-ink">
                    {formatNumber(count, lang)}
                  </span>
                </a>
              </li>
            );
          })}
        </ul>

        {current !== null && (
          <div className="mt-2">
            <a
              href={exploreDateHref}
              className="inline-flex min-h-11 items-center text-link underline hover:text-link-hover text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
            >
              {t("trends.exploreDate")}
            </a>
          </div>
        )}
      </div>
    </div>
  </div>;
}
