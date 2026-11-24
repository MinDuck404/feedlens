import { ExternalLink, FileSearch } from "lucide-react";
import { useState } from "react";
import { useI18n } from "../../i18n";
import { filterTopicPosts, topicColor } from "../../lib/topics";
import type { Post, Topic } from "../../api/types";
import { EmptyState } from "../ui";
import { categoryTone } from "./runPostFilters";

export function PostSources({ p }: { p: Post }) {
  const { t } = useI18n();
  const sources = p.sources ?? [];
  if (sources.length < 2) return null;
  const groups = new Set(sources.map((source) => source.source));
  return <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
    <span>{t(groups.size === 1 ? "posts.postedInSameGroup" : "posts.postedInGroups", { n: groups.size === 1 ? sources.length : groups.size })}</span>
    {sources.map((source, index) => /^https?:\/\//i.test(source.url)
      ? <a key={`${source.source}-${source.url}`} href={source.url} target="_blank" rel="noopener noreferrer" aria-label={`${source.source || t("posts.openOriginal")} · ${index + 1}`} className="inline-flex min-h-10 items-center gap-1 text-link underline underline-offset-4">{source.source || t("posts.openOriginal")}<ExternalLink aria-hidden="true" className="size-3 shrink-0" /></a>
      : <span key={`${source.source}-${index}`}>{source.source}</span>)}
  </div>;
}

export function PostList({ posts, filter, setFilter, name, topics = [], topicId = null, onTopicChange = () => {} }: {
  posts: Post[]; filter: string | null; setFilter: (c: string | null) => void; name: (c: string) => string; topics?: Topic[]; topicId?: number | null; onTopicChange?: (id: number | null) => void;
}) {
  const shown = filterTopicPosts(filter ? posts.filter((p) => p.category === filter) : posts, topicId);
  const { t } = useI18n();
  const [categoryBefore, categoryAfter] = t("posts.viewingCategory", { n: shown.length, category: "{category}" }).split("{category}");
  return (
    <>
      {!!(topics.length || topicId !== null) && <div className="mb-5 flex gap-2 overflow-x-auto pb-1 pr-5 [mask-image:linear-gradient(to_right,black_calc(100%_-_20px),transparent)]" role="group" aria-label={t("topics.title")}>
        <button type="button" aria-pressed={topicId === null} onClick={() => onTopicChange(null)} className="min-h-11 shrink-0 rounded-full border border-line px-3 text-sm aria-pressed:bg-sunken aria-pressed:font-semibold">{t("topics.all")}</button>
        {topics.map((topic) => <button key={topic.id} type="button" aria-pressed={topicId === topic.id} onClick={() => onTopicChange(topicId === topic.id ? null : topic.id)} className="flex min-h-11 shrink-0 items-center gap-2 rounded-full border border-line px-3 text-sm aria-pressed:bg-sunken aria-pressed:font-semibold"><span className="size-2 rounded-full" style={{ background: topicColor(topic.color) }} />{topic.name}</button>)}
      </div>}
      {filter && (
        <p className="mb-4 text-sm">
          {categoryBefore}<b>{name(filter)}</b>{categoryAfter}{" "}
          <button onClick={() => setFilter(null)} className="text-link hover:underline">{t("act.seeAll")}</button>
        </p>
      )}
      {shown.length === 0 && <EmptyState icon={<FileSearch className="size-6" />} title={t("hist.empty")} />}
      <ul className="divide-y divide-line-strong">
        {shown.map((p) => <ReadingPost key={p.id} p={p} name={name} topics={topics} />)}
      </ul>
    </>
  );
}


export function ReadingPost({ p, name, topics }: { p: Post; name: (c: string) => string; topics: Topic[] }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="stagger-item min-w-0 py-7 first:pt-0 [overflow-wrap:anywhere]">
      <article>
        <h3 className="max-w-[38ch] font-headline text-2xl leading-snug font-semibold sm:text-3xl">{p.summary || p.text.slice(0, 100)}</h3>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs leading-relaxed text-ink-soft">
          <span className="font-medium" style={{ color: categoryTone(p.category) }}>{p.analyzed === false ? t("run.aiUnread") : name(p.category)}</span>
          <span>{p.source}</span>
          <span>{p.author || t("posts.unknownAuthor")}</span>
          {p.sponsored && <span className="rounded-full border border-line px-2 py-0.5 text-xs text-ink-soft">{t("posts.sponsored")}</span>}
        </div>
        {!!p.topic_ids?.length && <ul className="mt-3 flex flex-wrap gap-2" aria-label={t("topics.title")}>{p.topic_ids.map((id) => topics.find((topic) => topic.id === id)).filter((topic): topic is Topic => !!topic).map((topic) => <li key={topic.id}><span tabIndex={p.topic_reason ? 0 : undefined} title={p.topic_reason} aria-label={p.topic_reason ? `${topic.name}: ${p.topic_reason}` : topic.name} className="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs" style={{ color: topicColor(topic.color), borderColor: topicColor(topic.color) }}><span className="size-1.5 shrink-0 rounded-full bg-current" />{topic.name}</span></li>)}</ul>}
        <PostSources p={p} />
        <p id={`post-${p.id}-text`} className={`prose-reading mt-4 whitespace-pre-wrap [overflow-wrap:anywhere] ${expanded ? "" : "line-clamp-3"}`}>{p.text}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
          <button type="button" aria-expanded={expanded} aria-controls={`post-${p.id}-text`} onClick={() => setExpanded((v) => !v)}
            className="min-h-10 text-ink-soft underline decoration-line underline-offset-4 hover:text-ink">
            {t(expanded ? "posts.readLess" : "posts.readMore")}
          </button>
          {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-10 items-center gap-1.5 font-medium text-link underline underline-offset-4 hover:decoration-2">
            {t("posts.openOriginal")} <ExternalLink aria-hidden="true" className="size-3.5" />
          </a>}
        </div>
      </article>
    </li>
  );
}
