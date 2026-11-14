import { Briefcase, ChevronRight } from "lucide-react";
import { PLATFORM_LABEL } from "../categories";
import { routeHref } from "../router";
import type { Run } from "../types";

const STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: "chờ agent", cls: "text-ink-soft" },
  queued: { label: "đang chờ", cls: "text-ink-soft" },
  scraping: { label: "đang lướt", cls: "text-link" },
  analyzing: { label: "đang đọc", cls: "text-link" },
  done: { label: "xong", cls: "text-ok" },
  error: { label: "lỗi", cls: "text-danger" },
};

const when = (iso: string) =>
  new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z")
    .toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

function sourceLabel(r: Run): string {
  const q = r.request;
  if (q.source_type === "feed") return `Bảng tin ${PLATFORM_LABEL[q.platform]}`;
  const short = (s: string) => s.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  const first = short(q.sources[0] ?? "");
  return q.sources.length > 1 ? `${first} và ${q.sources.length - 1} nguồn khác` : first;
}

export default function HistoryPage({ runs, onOpen, onNewRun }: {
  runs: Run[]; onOpen: (id: number) => void; onNewRun: () => void;
}) {
  const jobsRuns = runs.filter((r) => r.request.job_mode).length;
  return (
    <div className="mx-auto max-w-4xl px-5 py-10 md:px-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold tracking-[-0.03em]">lịch sử</h1>
          <p className="mt-1 font-mono text-xs text-ink-soft">
            {runs.length} lượt, {jobsRuns} lượt tìm việc
          </p>
        </div>
        <button onClick={onNewRun} className="rounded-full bg-primary px-5 py-2.5 font-semibold text-primary-ink hover:opacity-90">
          Lướt mới
        </button>
      </header>

      {runs.length === 0 ? (
        <p className="paper-card mt-8 rounded-2xl px-6 py-10 text-center text-ink-soft">
          Chưa có lượt nào. Bấm <b className="text-ink">Lướt mới</b> để bắt đầu.
        </p>
      ) : (
        <ul className="paper-card mt-8 divide-y divide-line overflow-hidden rounded-2xl">
          {runs.map((r) => {
            const s = STATUS[r.status] ?? STATUS.queued;
            return (
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
                          <Briefcase className="size-3" /> tìm việc
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-ink-soft">
                      {PLATFORM_LABEL[r.request.platform]}
                      {r.ai_label && <>, {r.ai_label}</>}
                    </span>
                  </span>
                  <span className="hidden w-16 text-right font-mono text-sm sm:block">{r.collected || "–"}</span>
                  <span className={`w-20 text-right font-mono text-xs ${s.cls}`}>{s.label}</span>
                  <ChevronRight className="size-4 text-ink-soft transition-transform group-hover:translate-x-0.5" />
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
