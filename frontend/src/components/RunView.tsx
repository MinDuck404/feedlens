import { ExternalLink, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { colorOf, PLATFORM_LABEL } from "../categories";
import type { Meta, Post, Run } from "../types";

type Tab = "digest" | "jobs" | "posts";

export default function RunView({ runId, meta, onDeleted }: { runId: number; meta: Meta; onDeleted: () => void }) {
  const [run, setRun] = useState<Run | null>(null);
  const [tab, setTab] = useState<Tab>("digest");
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: number;
    const load = async () => {
      const r = await api.run(runId);
      if (!alive) return;
      setRun(r);
      if (!["done", "error"].includes(r.status)) timer = window.setTimeout(load, 1500);
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [runId]);

  if (!run) return null;
  const q = run.request;
  const title = q.source_type === "feed" ? `Bảng tin ${PLATFORM_LABEL[q.platform]}`
    : q.sources.length > 1 ? `${q.sources[0]} và ${q.sources.length - 1} nguồn khác` : q.sources[0];
  const when = new Date(run.created_at.endsWith("Z") || run.created_at.includes("+") ? run.created_at : run.created_at + "Z");

  const remove = async () => {
    if (!confirm("Xóa lượt này cùng toàn bộ bài đã thu?")) return;
    await api.deleteRun(run.id);
    onDeleted();
  };

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 md:px-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs text-ink-soft">
            {when.toLocaleString("vi-VN", { dateStyle: "medium", timeStyle: "short" })}
            {run.ai_label && <>, đọc bởi {run.ai_label}</>}
          </p>
          <h1 className="mt-1 truncate text-2xl font-bold tracking-tight md:text-3xl">{title}</h1>
        </div>
        <div className="flex items-center gap-1">
          {run.status === "done" && (["md", "csv", "json"] as const).map((f) => (
            <button key={f} onClick={() => api.download(run.id, f).catch((e) => alert(e.message))}
              className="rounded-full border border-line px-3 py-1 font-mono text-xs text-ink-soft hover:border-ink hover:text-ink">
              .{f}
            </button>
          ))}
          <button onClick={remove} aria-label="Xóa lượt" title="Xóa lượt"
            className="ml-1 grid size-8 place-items-center rounded-full border border-line text-ink-soft hover:border-danger hover:text-danger">
            <Trash2 className="size-4" />
          </button>
        </div>
      </header>

      {run.status === "error" ? (
        <div className="paper-card mt-8 rounded-2xl border-danger/40 p-5">
          <p className="font-semibold text-danger">Lượt này dừng giữa chừng</p>
          <p className="mt-2 whitespace-pre-wrap text-sm">{run.error}</p>
        </div>
      ) : run.status !== "done" || !run.digest ? (
        <InProgress run={run} />
      ) : (
        <Done run={run} meta={meta} tab={tab} setTab={setTab} filter={filter} setFilter={setFilter} />
      )}
    </div>
  );
}

function InProgress({ run }: { run: Run }) {
  const p = run.progress;
  const pct = p?.target ? Math.min(100, Math.round((p.done / p.target) * 100)) : 0;
  const phase = run.status === "pending" ? "Đang chờ agent trên máy bạn nhận việc"
    : run.status === "scraping" ? "Đang lướt và gom bài" : run.status === "analyzing" ? "AI đang đọc từng bài" : "Đang chuẩn bị";
  return (
    <div className="mt-10 max-w-lg">
      <p className="font-semibold">{phase}</p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-sunken">
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-sm text-ink-soft">{p?.message || (run.status === "pending" ? "Lượt sẽ tự chạy khi agent bật. Xem cách bật trong phần Cài đặt." : "Đang mở trình duyệt…")}</p>
    </div>
  );
}

function Done({ run, meta, tab, setTab, filter, setFilter }: {
  run: Run; meta: Meta; tab: Tab; setTab: (t: Tab) => void; filter: string | null; setFilter: (c: string | null) => void;
}) {
  const posts = run.posts ?? [];
  const d = run.digest!;
  const jobs = useMemo(
    () => posts.filter((p) => p.job).sort((a, b) => b.job!.match_score - a.job!.match_score),
    [posts],
  );
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    posts.forEach((p) => m.set(p.category, (m.get(p.category) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [posts]);
  const name = (c: string) => meta.categories[c] ?? c;

  const pick = (c: string) => { setFilter(filter === c ? null : c); setTab("posts"); };

  return (
    <>
      {/* Thanh phân loại: điểm nhấn của trang, đồng thời là bộ lọc */}
      <section className="mt-8" aria-label="Thành phần bảng tin">
        <p className="mb-2 text-sm text-ink-soft"><span className="font-mono text-ink">{posts.length}</span> bài, chia theo loại</p>
        <div className="flex h-12 w-full gap-1 overflow-hidden rounded-full border border-line bg-surface p-1">
          {counts.map(([c, n]) => (
            <button key={c} onClick={() => pick(c)} title={`${name(c)}: ${n} bài`}
              aria-label={`${name(c)}: ${n} bài`}
              className="h-full rounded-full transition-opacity hover:opacity-80 focus-visible:z-10"
              style={{ flexGrow: n, flexBasis: 0, minWidth: 6, background: colorOf(c), opacity: filter && filter !== c ? 0.3 : 1 }} />
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
          {counts.map(([c, n]) => (
            <li key={c}>
              <button onClick={() => pick(c)} className="flex items-center gap-2 text-sm hover:underline">
                <span className="size-2.5 rounded-full" style={{ background: colorOf(c) }} />
                {name(c)} <span className="font-mono text-xs text-ink-soft">{n}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <nav className="mt-8 flex gap-6 border-b border-line" role="tablist">
        {([["digest", "Tóm tắt"], ...(jobs.length ? [["jobs", `Việc làm (${jobs.length})`]] : []), ["posts", "Bài viết"]] as [Tab, string][])
          .map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className="-mb-px border-b-2 border-transparent pb-2.5 text-sm text-ink-soft aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink">
              {l}
            </button>
          ))}
      </nav>

      <div className="py-6">
        {tab === "digest" && <DigestView d={d} name={name} />}
        {tab === "jobs" && <JobsTable jobs={jobs} />}
        {tab === "posts" && <PostList posts={posts} filter={filter} setFilter={setFilter} name={name} />}
      </div>
    </>
  );
}

function DigestView({ d, name }: { d: NonNullable<Run["digest"]>; name: (c: string) => string }) {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_260px]">
      <div className="min-w-0">
        <p className="max-w-[68ch] font-serif text-xl leading-[1.75]">{d.overall}</p>
        <div className="mt-10 space-y-8">
          {d.categories.map((c) => (
            <section key={c.category}>
              <h3 className="flex items-center gap-2 font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: colorOf(c.category) }} />
                {name(c.category)} <span className="font-mono text-xs font-normal text-ink-soft">{c.count} bài</span>
              </h3>
              <p className="mt-1 max-w-[68ch] text-ink-soft">{c.summary}</p>
              {c.highlights.length > 0 && (
                <ul className="mt-2 max-w-[68ch] list-disc space-y-1 pl-5 text-sm">
                  {c.highlights.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              )}
            </section>
          ))}
        </div>
      </div>
      {d.action_items.length > 0 && (
        <aside className="paper-card h-fit rounded-2xl p-5 lg:sticky lg:top-6">
          <h3 className="font-semibold">Nên làm tiếp</h3>
          <ul className="mt-3 space-y-2.5">
            {d.action_items.map((a, i) => (
              <li key={i}>
                <label className="flex gap-2.5 text-sm">
                  <input type="checkbox" className="mt-1 accent-[var(--accent)]" />
                  <span>{a}</span>
                </label>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}

function Score({ v }: { v: number }) {
  const tone = v >= 70 ? "text-ok" : v >= 40 ? "text-[#b7851a]" : "text-ink-soft";
  return (
    <div className={`w-14 ${tone}`} aria-label={`Độ phù hợp ${v}/100`}>
      <span className="font-mono text-lg font-medium">{v}</span>
      <div className="mt-0.5 h-1 rounded-full bg-sunken">
        <div className="h-full rounded-full bg-current" style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function JobsTable({ jobs }: { jobs: Post[] }) {
  return (
    <ul className="paper-card divide-y divide-line overflow-hidden rounded-2xl">
      {jobs.map((p) => {
        const j = p.job!;
        const facts = [j.company, [j.location, j.work_mode].filter(Boolean).join(", "), j.salary].filter(Boolean);
        return (
          <li key={p.id} className="flex gap-5 p-5">
            <Score v={j.match_score} />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold">{j.title || p.summary}</h3>
                {p.url && (
                  <a href={p.url} target="_blank" rel="noopener noreferrer"
                    className="flex shrink-0 items-center gap-1 text-sm text-link hover:underline">
                    Mở bài <ExternalLink className="size-3.5" />
                  </a>
                )}
              </div>
              {facts.length > 0 && <p className="mt-0.5 text-sm">{facts.join(" / ")}</p>}
              {j.match_reason && <p className="mt-1 text-sm text-ink-soft">{j.match_reason}</p>}
              {j.contact && <p className="mt-1 text-sm">Liên hệ: <span className="font-medium">{j.contact}</span></p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function PostList({ posts, filter, setFilter, name }: {
  posts: Post[]; filter: string | null; setFilter: (c: string | null) => void; name: (c: string) => string;
}) {
  const shown = filter ? posts.filter((p) => p.category === filter) : posts;
  return (
    <>
      {filter && (
        <p className="mb-4 text-sm">
          Đang xem {shown.length} bài loại <b>{name(filter)}</b>.{" "}
          <button onClick={() => setFilter(null)} className="text-link hover:underline">Xem tất cả</button>
        </p>
      )}
      <ul className="space-y-2">
        {shown.map((p) => (
          <li key={p.id} className="paper-card rounded-xl px-4 py-3">
            <details>
              <summary className="cursor-pointer list-none">
                <span className="block font-medium">{p.summary}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-ink-soft">
                  <span className="flex items-center gap-1.5 text-ink">
                    <span className="size-2 rounded-full" style={{ background: colorOf(p.category) }} />
                    {name(p.category)}
                  </span>
                  <span>{p.author || "Không rõ tác giả"}</span>
                  <span>{p.source}</span>
                  {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-link hover:underline"
                    onClick={(e) => e.stopPropagation()}>Mở bài gốc</a>}
                </span>
              </summary>
              <p className="mt-3 max-w-[72ch] whitespace-pre-wrap text-sm text-ink-soft">{p.text}</p>
            </details>
          </li>
        ))}
      </ul>
    </>
  );
}
