import { useEffect, useState } from "react";

/** Router dựa trên hash (#/...): chạy được với server local lẫn GitHub Pages mà không cần cấu hình,
 *  và tải lại trang vẫn giữ nguyên chỗ đang xem.
 *    #/                 trang chủ
 *    #/history          lịch sử các lượt
 *    #/runs/12          một lượt (tab Tóm tắt)
 *    #/runs/12/jobs     một lượt, tab Việc làm (digest | jobs | posts) */
export type RunTab = "digest" | "jobs" | "posts";
export type Route =
  | { page: "home" }
  | { page: "history" }
  | { page: "run"; id: number; tab: RunTab };

const TABS: RunTab[] = ["digest", "jobs", "posts"];

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "history") return { page: "history" };
  if (parts[0] === "runs" && /^\d+$/.test(parts[1] ?? "")) {
    const tab = TABS.includes(parts[2] as RunTab) ? (parts[2] as RunTab) : "digest";
    return { page: "run", id: Number(parts[1]), tab };
  }
  return { page: "home" };
}

export function routeHref(r: Route): string {
  if (r.page === "history") return "#/history";
  if (r.page === "run") return r.tab === "digest" ? `#/runs/${r.id}` : `#/runs/${r.id}/${r.tab}`;
  return "#/";
}

export function navigate(r: Route, opts: { replace?: boolean } = {}) {
  const href = routeHref(r);
  if (location.hash === href || (href === "#/" && !location.hash)) return;
  if (opts.replace) history.replaceState(null, "", href);
  else location.hash = href;
  if (opts.replace) window.dispatchEvent(new HashChangeEvent("hashchange"));
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(location.hash));
  useEffect(() => {
    const on = () => setRoute(parseRoute(location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
