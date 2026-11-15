import { useId, useState } from "react";
import type { TrendsResponse } from "../types";
import { useI18n, formatNumber } from "../i18n";
import { routeHref, navigate } from "../router";
import { trendSearchFilters } from "../search";
import { trendColor, trendPath, trendPoints } from "../trends";

interface Props {
  data: TrendsResponse;
  viewMode: "overview" | "grid";
  className?: string;
}

export function TrendsChart({ data, viewMode, className = "" }: Props) {
  const { t, locale, lang } = useI18n();
  const clipId = useId().replace(/:/g, "");
  const [index, setIndex] = useState<number | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const { timeline, series } = data;
  const focal = hovered ?? series.find((item) => item.total > 0)?.id;
  const max = Math.max(4, Math.ceil(Math.max(0, ...series.flatMap((item) => item.counts)) / 4) * 4);
  const width = 730, height = 280;
  const date = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString(locale, { month: "short", day: "numeric", timeZone: "UTC" });
  const growth = (value: number | null) => value === null ? t("trends.newPeriod") : `${value > 0 ? "+" : ""}${formatNumber(value, lang)}%`;
  const explore = (id: string, date?: string) => routeHref({ page: "ask", filters: trendSearchFilters(data, id, date) });
  const current = index !== null && index < timeline.length ? index : null;
  if (viewMode === "grid") return <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 ${className}`}>
    {series.map((item) => {
      const points = trendPoints(item.counts, 180, 50, max);
      const line = trendPath(points);
      const color = trendColor(item.color);
      return <a key={item.id} href={explore(item.id)} className="paper-card min-w-0 p-4 text-left transition-colors hover:border-ink-soft">
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
      <p id={`${clipId}-hint`} className="mb-3 text-xs text-ink-soft">{t("trends.chartHint")}</p>
      <svg viewBox="0 0 800 340" className="h-auto w-full overflow-hidden" tabIndex={0} role="img" aria-label={t("trends.title")} aria-describedby={`${clipId}-hint`}
        onPointerMove={(event) => { if (event.pointerType === "mouse") { const rect = event.currentTarget.getBoundingClientRect(); setIndex(Math.max(0, Math.min(timeline.length - 1, Math.round(((event.clientX - rect.left) / rect.width * 800 - 46) / width * (timeline.length - 1))))); } }}
        onPointerDown={(event) => { const rect = event.currentTarget.getBoundingClientRect(); setIndex(Math.max(0, Math.min(timeline.length - 1, Math.round(((event.clientX - rect.left) / rect.width * 800 - 46) / width * (timeline.length - 1))))); }}
        onPointerLeave={(event) => { if (event.pointerType === "mouse") setIndex(null); }} onKeyDown={(event) => {
          if (event.key === "Enter" && focal) { event.preventDefault(); navigate({ page: "ask", filters: trendSearchFilters(data, focal, current !== null ? timeline[current] : undefined) }); }
          if (["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) { event.preventDefault(); setIndex((value) => event.key === "Escape" ? null : event.key === "Home" ? 0 : event.key === "End" ? timeline.length - 1 : Math.max(0, Math.min(timeline.length - 1, (value ?? 0) + (event.key === "ArrowRight" ? 1 : -1)))); }
        }}>
        <defs><clipPath id={clipId}><rect x="46" y="24" width={width} height={height} /></clipPath></defs>
        {[0, 1, 2, 3, 4].map((tick) => <g key={tick}><line x1="46" x2="776" y1={24 + height - tick * height / 4} y2={24 + height - tick * height / 4} stroke="var(--line-strong)" strokeDasharray={tick ? "3,3" : undefined} /><text x="36" y={28 + height - tick * height / 4} textAnchor="end" className="fill-ink-soft font-mono text-[11px]">{formatNumber(max * tick / 4, lang)}</text></g>)}
        {ticks.map((tick) => <text key={tick} x={46 + (timeline.length <= 1 ? width / 2 : tick / (timeline.length - 1) * width)} y="328" textAnchor="middle" className="fill-ink-soft text-[11px]">{date(timeline[tick])}</text>)}
        <g clipPath={`url(#${clipId})`} data-trend-plot>
          {series.map((item) => {
            const points = trendPoints(item.counts.slice(0, timeline.length), width, height, max);
            const line = trendPath(points);
            const color = trendColor(item.color), focus = focal === item.id;
            return <g key={item.id} transform="translate(46 24)" opacity={focus ? 1 : hovered ? 0.25 : 0.65}>
              {focus && points.length > 0 && <path d={`${line} L ${points.at(-1)!.x} ${height} L ${points[0].x} ${height} Z`} fill={color} fillOpacity="0.14" />}
              <path d={line} stroke={color} strokeWidth={focus ? 2.4 : 1.3} fill="none" strokeLinejoin="round" />
              {focus && points.map((point, i) => <a key={i} href={explore(item.id, timeline[i])} tabIndex={-1} aria-label={`${t("trends.exploreDate")}: ${item.name}`}><circle cx={point.x} cy={point.y} r={i === current ? 4 : 2.5} fill={color} stroke="var(--paper)" /></a>)}
            </g>;
          })}
          {current !== null && <line x1={46 + (timeline.length <= 1 ? width / 2 : current / (timeline.length - 1) * width)} x2={46 + (timeline.length <= 1 ? width / 2 : current / (timeline.length - 1) * width)} y1="24" y2="304" stroke="var(--ink)" strokeDasharray="3,3" />}
        </g>
      </svg>
      {current !== null && <div role="status" aria-live="polite" className="mt-3 border-t border-line pt-3 text-sm"><p className="font-medium">{date(timeline[current])}</p><ul className="mt-2 grid gap-x-5 gap-y-1 sm:grid-cols-2">{series.map((item) => <li key={item.id} className="flex min-w-0 items-baseline justify-between gap-3"><span className="min-w-0 [overflow-wrap:anywhere]">{item.name}</span><span className="shrink-0 font-mono">{formatNumber(item.counts[current] ?? 0, lang)}</span></li>)}</ul>{focal && <a href={explore(focal, timeline[current])} className="mt-2 inline-flex min-h-11 items-center text-link underline">{t("trends.exploreDate")}</a>}</div>}
    </div>
    <div role="group" aria-label={t("trends.focalSeries")} className="flex max-w-full gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:flex-wrap sm:pr-0 sm:[mask-image:none]">
      {series.map((item) => <a key={item.id} href={explore(item.id)} onPointerEnter={() => setHovered(item.id)} onPointerLeave={() => setHovered(null)} onFocus={() => setHovered(item.id)} onBlur={() => setHovered(null)} className="flex min-h-11 shrink-0 items-center gap-2 rounded-full border border-line px-3 text-sm hover:bg-sunken"><span className="size-2.5 rounded-full" style={{ background: trendColor(item.color) }} /><span>{item.name}</span><span className="font-mono text-xs text-ink-soft">{formatNumber(item.total, lang)}</span></a>)}
    </div>
  </div>;
}
