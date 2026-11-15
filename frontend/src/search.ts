import type { SearchFilters, TrendsResponse } from "./types";

const arrays = ["categories", "topic_ids", "work_modes", "locations"];
const singles = ["q", "platform", "date_from", "date_to", "job_only", "min_salary_vnd", "min_score", "match_type", "has_link", "has_github"];
export function searchParams(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (arrays.includes(key) && Array.isArray(value)) value.forEach((item) => params.append(key, String(item)));
    else if (singles.includes(key) && value != null && value !== "") params.set(key, String(value));
  }
  return params;
}
export function readSearchParams(params: URLSearchParams): SearchFilters {
  const filters: Record<string, unknown> = {};
  for (const key of arrays) {
    const values = params.getAll(key).slice(0, key === "topic_ids" ? 12 : 20);
    if (values.length) filters[key] = key === "topic_ids" ? values.map(Number).filter((n) => Number.isSafeInteger(n) && n > 0) : values;
  }
  for (const key of singles) {
    const value = params.get(key); if (value === null || value === "") continue;
    if (["job_only", "has_link", "has_github"].includes(key)) { if (["true", "false"].includes(value)) filters[key] = value === "true"; }
    else if (["min_score", "min_salary_vnd"].includes(key)) { const n = Number(value); if (Number.isFinite(n) && n >= 0) filters[key] = n; }
    else filters[key] = value.slice(0, 1000);
  }
  return filters as SearchFilters;
}
export function textParts(text: string, mode: "snippet" | "citation", validIds: number[] = []): { text: string; highlight?: boolean; id?: number }[] {
  const pattern = mode === "snippet" ? /«([^»]*)»/g : /\[#(\d+)\]/g;
  const parts: { text: string; highlight?: boolean; id?: number }[] = []; let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index! > cursor) parts.push({ text: text.slice(cursor, match.index) });
    parts.push(mode === "snippet" ? { text: match[1], highlight: true } : { text: match[0], ...(validIds.includes(Number(match[1])) ? { id: Number(match[1]) } : {}) });
    cursor = match.index! + match[0].length;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) });
  return parts;
}
export function questionHistory(items: unknown, question?: string): string[] {
  const values = Array.isArray(items) ? items.filter((value): value is string => typeof value === "string" && !!value.trim() && value.length <= 1000) : [];
  return [...new Set([...(question?.trim() ? [question.trim()] : []), ...values])].slice(0, 20);
}
export function trendSearchFilters(data: TrendsResponse, id: string, date?: string): SearchFilters {
  let end = data.range.end_date;
  if (date) {
    const day = new Date(`${date}T00:00:00Z`); day.setUTCDate(day.getUTCDate() + (data.range.bucket === "week" ? 6 : 0));
    end = [day.toISOString().slice(0, 10), end].sort()[0];
  }
  return { ...(data.range.group === "topic" ? { topic_ids: [Number(id)] } : { categories: [id] }), date_from: date ? [date, data.range.start_date].sort().at(-1)! : data.range.start_date, date_to: end };
}
