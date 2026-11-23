import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { formatNumber, useI18n } from "../../i18n";
import { jobPresentation } from "../../logic";
import type { RunTab } from "../../router";
import { filterTopicPosts, topicColor } from "../../topics";
import type { Meta, Run, Topic } from "../../types";
import { DigestView } from "./DigestView";
import { JobsBoard } from "./JobsBoard";
import { PostList } from "./PostList";
import { categoryTone, runPostFiltersFromHash, runPostsHref, type RunPostFilters } from "./runPostFilters";

type Tab = RunTab;

export function Done({ run, meta, tab: requested, setTab }: {
  run: Run; meta: Meta; tab: Tab; setTab: (t: Tab) => void;
}) {
  const posts = run.posts ?? [];
  const d = run.digest!;
  const partial = run.status !== "done" || !d;
  const [filters, setFilters] = useState(() => runPostFiltersFromHash(window.location?.hash ?? ""));
  const { category: filter, topicId } = filters;
  const panel = useRef<HTMLDivElement>(null);
  const jumpToPosts = useRef(filter !== null || topicId !== null);
  useEffect(() => {
    const sync = () => {
      jumpToPosts.current = true;
      setFilters(runPostFiltersFromHash(window.location.hash));
    };
    sync();
    window.addEventListener("hashchange", sync); return () => window.removeEventListener("hashchange", sync);
  }, [run.id]);
  useEffect(() => {
    if (requested !== "posts" || !jumpToPosts.current) return;
    jumpToPosts.current = false;
    panel.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    panel.current?.focus({ preventScroll: true });
  }, [requested, filters]);
  const selectPosts = (next: RunPostFilters) => {
    jumpToPosts.current = true; setFilters(next);
    const href = runPostsHref(run.id, next);
    if (window.location.hash !== href) window.location.hash = href;
    else { panel.current?.scrollIntoView({ block: "start" }); panel.current?.focus({ preventScroll: true }); }
  };
  const selectTopic = (id: number | null) => selectPosts({ ...filters, topicId: id });
  const selectCategory = (category: string | null) => selectPosts({ ...filters, category });
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicError, setTopicError] = useState("");
  useEffect(() => {
    let alive = true;
    api.topics().then((data) => { if (alive) setTopics(Array.isArray(data?.topics) ? data.topics : []); }).catch((e) => { if (alive) setTopicError(e.message); });
    return () => { alive = false; };
  }, [run.id, run.digest]);
  const jobs = useMemo(
    () => posts.filter((p) => (!partial || p.analyzed !== false) && (p.job || p.job_seed)).map((p) => ({ ...p, ...jobPresentation(p) })).sort((a, b) => b.job!.match_score - a.job!.match_score),
    [posts, partial],
  );
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    posts.filter((p) => p.analyzed !== false).forEach((p) => m.set(p.category, (m.get(p.category) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [posts]);
  const { t, cat, lang } = useI18n();
  void meta;  // tên loại bài lấy theo ngôn ngữ giao diện thay vì meta.categories (tiếng Việt)
  const name = cat;
  const tab: Tab = partial && (requested === "digest" || requested === "jobs" && !jobs.length) ? "posts" : requested === "jobs" && !jobs.length && run.request.mode !== "jobs" ? "digest" : requested;

  const categoryBar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const bar = categoryBar.current;
    if (!bar || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const tokens = getComputedStyle(bar);
    bar.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], {
      duration: parseFloat(tokens.getPropertyValue("--duration-normal")),
      easing: tokens.getPropertyValue("--ease-micro").trim(),
    });
  }, [run.id]);

  const pick = selectCategory;

  return (
    <>
      {/* Thanh phân loại: điểm nhấn của trang, đồng thời là bộ lọc */}
      <section className="mt-4 min-w-0" aria-label={t("run.composition")}>
        <p className="mb-2 text-xs text-ink-soft">{t("run.postsCount", { n: posts.length })}</p>
        <div ref={categoryBar} className="flex h-1.5 w-full origin-left gap-0.5">
          {counts.map(([c, n]) => (
            <button key={c} onClick={() => pick(c)} title={t("run.catCount", { name: name(c), n })}
              aria-label={t("run.catCount", { name: name(c), n })} aria-pressed={filter === c}
              className="relative h-full rounded-full transition-opacity before:absolute before:inset-x-0 before:-inset-y-3 hover:opacity-80 focus-visible:z-10 focus-visible:outline-offset-2"
              style={{ flexGrow: n, flexBasis: 0, minWidth: 6, background: categoryTone(c), opacity: filter && filter !== c ? 0.3 : 1 }} />
          ))}
        </div>
        <ul className="mt-2 flex max-w-full gap-1 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:pr-0 sm:[mask-image:none]">
          {counts.map(([c, n]) => (
            <li key={c} className="shrink-0">
              <button onClick={() => pick(c)} aria-pressed={filter === c} aria-label={t("run.viewCategory", { name: name(c), n })} className="interactive-tap flex min-h-10 items-center gap-1.5 rounded-sm px-2 py-1 text-xs hover:bg-sunken focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2 aria-pressed:bg-sunken aria-pressed:font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: categoryTone(c) }} />
                {name(c)} <span className="font-mono text-xs text-ink-soft">{formatNumber(n, lang)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {topics.length > 0 && <section aria-label={t("topics.yours")} className="mt-3 min-w-0"><h2 className="text-xs text-ink-soft">{t("topics.yours")}</h2><div className="mt-1 flex gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)] sm:flex-wrap sm:pr-0 sm:[mask-image:none]">
        {topics.map((topic) => <button key={topic.id} type="button" onClick={() => selectTopic(topic.id)} aria-label={t("run.catCount", { name: topic.name, n: filterTopicPosts(posts, topic.id).length })} aria-pressed={topicId === topic.id && tab === "posts"} className="flex min-h-10 shrink-0 items-center gap-2 rounded-full border border-line px-3 text-xs hover:bg-sunken aria-pressed:bg-sunken aria-pressed:font-semibold"><span className="size-2 rounded-full" style={{ background: topicColor(topic.color) }} />{topic.name}<span className="font-mono text-ink-soft">{formatNumber(filterTopicPosts(posts, topic.id).length, lang)}</span></button>)}
      </div></section>}

      <nav data-run-tabs className="mt-3 flex gap-1 border-b border-line" role="tablist" aria-label={t("run.composition")}>
        {([...(partial ? [] : [["digest", t("tab.digest")]]), ...(jobs.length ? [["jobs", t("tab.jobs", { n: jobs.length })]] : []), ["posts", t("tab.posts")]] as [Tab, string][])
          .map(([k, l], index, tabs) => (
            <button key={k} id={`run-${run.id}-tab-${k}`} role="tab" aria-selected={tab === k}
              aria-controls={`run-${run.id}-panel`} tabIndex={tab === k ? 0 : -1} onClick={() => setTab(k)}
              onKeyDown={(e) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                e.preventDefault();
                const next = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                setTab(tabs[next][0]);
                e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
              }}
              className="interactive-tap -mb-px min-h-12 flex-1 border-b-2 border-transparent px-2 py-3 text-sm text-ink-soft transition-colors duration-[var(--duration-fast)] hover:text-ink focus:outline-none! focus-visible:outline-solid! focus-visible:outline-1! focus-visible:outline-ink/35! focus-visible:-outline-offset-4! focus-visible:rounded-lg! aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink sm:flex-none sm:px-5">
              {l}
            </button>
          ))}
      </nav>

      <div ref={panel} key={tab} role="tabpanel" id={`run-${run.id}-panel`} aria-labelledby={`run-${run.id}-tab-${tab}`} tabIndex={0} className="page-enter min-w-0 scroll-mt-20 py-7">
        {topicError && <p role="alert" className="mb-4 text-sm text-danger">{topicError}</p>}
        {tab === "digest" && <DigestView d={d} name={name} posts={posts} topics={topics} onTopic={selectTopic} onCategory={selectCategory} />}
        {tab === "jobs" && <JobsBoard jobs={jobs} runId={run.id} />}
        {tab === "posts" && <PostList posts={posts} filter={filter} setFilter={selectCategory} name={name} topics={topics} topicId={topicId} onTopicChange={selectTopic} />}
      </div>
    </>
  );
}
