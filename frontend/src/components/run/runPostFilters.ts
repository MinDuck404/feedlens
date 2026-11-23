import { routeHref } from "../../router";

const CATEGORY_INK: Record<string, string> = Object.fromEntries(
  ["job", "news", "tech", "marketplace", "question", "event", "promotion", "personal", "entertainment", "other"].map((c) => [c, `var(--cat-${c})`]),
);
export const categoryTone = (category: string) => CATEGORY_INK[category] ?? CATEGORY_INK.other;

export type RunPostFilters = { category: string | null; topicId: number | null };

export function runPostFiltersFromHash(hash: string): RunPostFilters {
  const [path, query = ""] = hash.split("?");
  if (!/^#\/runs\/\d+\/posts$/.test(path)) return { category: null, topicId: null };
  const params = new URLSearchParams(query);
  const category = params.get("category");
  const value = Number(params.get("topic"));
  return {
    category: category && Object.prototype.hasOwnProperty.call(CATEGORY_INK, category) ? category : null,
    topicId: Number.isSafeInteger(value) && value > 0 ? value : null,
  };
}

export function runPostsHref(runId: number, filters: RunPostFilters): string {
  const params = new URLSearchParams();
  if (filters.category && Object.prototype.hasOwnProperty.call(CATEGORY_INK, filters.category)) params.set("category", filters.category);
  if (filters.topicId !== null && Number.isSafeInteger(filters.topicId) && filters.topicId > 0) params.set("topic", String(filters.topicId));
  return routeHref({ page: "run", id: runId, tab: "posts" }) + (params.size ? `?${params}` : "");
}
