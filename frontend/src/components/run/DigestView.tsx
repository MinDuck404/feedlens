import { Check, ExternalLink } from "lucide-react";
import { useI18n } from "../../i18n";
import { topicColor } from "../../topics";
import type { Post, Run, Topic } from "../../types";
import { categoryTone } from "./runPostFilters";

export function DigestView({ d, name, posts, topics, onTopic, onCategory }: { d: NonNullable<Run["digest"]>; name: (c: string) => string; posts: Post[]; topics: Topic[]; onTopic: (id: number) => void; onCategory: (category: string) => void }) {
  const { t, locale } = useI18n();
  const byId = new Map(posts.map((post) => [post.id, post]));
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_240px]">
      <div className="min-w-0">
        {!!d.topics?.length && <section className="mb-8 border-b border-line pb-7" aria-label={t("topics.yours")}>
          <h2 className="mb-5 font-headline text-3xl font-semibold">{t("topics.yours")}</h2>
          <div className="divide-y divide-line">{d.topics.map((topic) => {
            const featured = topic.post_ids.map((id) => byId.get(id)).filter((post): post is Post => !!post).slice(0, 3);
            const remaining = Math.max(0, topic.count - featured.length);
            const summary = [...new Intl.Segmenter(locale, { granularity: "sentence" }).segment(topic.summary)].slice(0, 2).map((part) => part.segment).join("");
            return <section key={topic.topic_id} className="py-4 first:pt-0">
              <h3 className="flex flex-wrap items-baseline gap-2 font-headline text-xl"><span className="size-2.5 shrink-0 rounded-full" style={{ background: topicColor(topics.find((item) => item.id === topic.topic_id)?.color ?? "red") }} /><button onClick={() => onTopic(topic.topic_id)} className="min-h-10 text-left hover:text-link">{topic.name}</button><span className="font-sans text-xs text-ink-soft">{t("run.nPosts", { n: topic.count })}</span></h3>
              {topic.count === 0 ? <p className="mt-2 text-sm text-ink-soft">{t("topics.noMatch")}</p> : <>
                {summary && <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-soft [overflow-wrap:anywhere]">{summary}</p>}
                <ul className="mt-3 space-y-1">{featured.map((post) => <li key={post.id} className="flex items-start gap-2 text-sm [overflow-wrap:anywhere]"><span className="min-w-0 flex-1 py-1.5">{post.summary || post.text.slice(0, 160)}</span>{post.url && <a href={post.url} target="_blank" rel="noopener noreferrer" title={t("posts.openOriginal")} aria-label={`${t("posts.openOriginal")}: ${post.summary || post.text.slice(0, 80)}`} className="grid size-9 shrink-0 place-items-center text-ink-soft hover:text-link"><ExternalLink aria-hidden="true" className="size-3.5" /></a>}</li>)}</ul>
              </>}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">{remaining > 0 && <span className="text-ink-soft">{t(remaining === 1 ? "topics.moreOne" : "topics.more", { n: remaining })} ·</span>}<button onClick={() => onTopic(topic.topic_id)} className="min-h-10 font-medium text-link hover:underline">{t("topics.viewAll")}</button></div>
            </section>;
          })}</div>
        </section>}
        <p className="prose-reading text-xl! leading-relaxed! [overflow-wrap:anywhere] sm:text-2xl!">{d.overall}</p>
        <div className="mt-8 space-y-7">
          {d.categories.map((c) => (
            <section key={c.category} className="border-t border-line pt-5">
              <h3 className="flex flex-wrap items-baseline gap-2 font-headline text-2xl font-semibold">
                <span className="size-2.5 rounded-full" style={{ background: categoryTone(c.category) }} />
                <button type="button" onClick={() => onCategory(c.category)} aria-label={t("run.viewCategory", { name: name(c.category), n: c.count })} className="group flex min-h-11 flex-wrap items-baseline gap-x-3 gap-y-1 rounded-sm text-left transition-colors hover:text-link focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-4">
                  <span>{name(c.category)}</span><span className="font-sans text-xs font-normal text-ink-soft group-hover:text-link">{t("run.viewCategoryCount", { n: c.count })}</span>
                </button>
              </h3>
              <p className="prose-reading mt-3 [overflow-wrap:anywhere]">{c.summary}</p>
              {c.highlights.length > 0 && (
                <ul className="prose-reading mt-3 list-disc space-y-2 pl-5 [overflow-wrap:anywhere]">
                  {c.highlights.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              )}
            </section>
          ))}
        </div>
      </div>
      {d.action_items.length > 0 && (
        <aside className="h-fit border border-[var(--field-line)] bg-sunken p-4 lg:sticky lg:top-6">
          <h3 className="font-headline text-xl font-semibold">{t("run.nextSteps")}</h3>
          <ul className="mt-3 space-y-2.5">
            {d.action_items.map((a, i) => (
              <li key={i}>
                <label className="flex min-h-10 gap-3 py-1 text-sm [overflow-wrap:anywhere]">
                  <input type="checkbox" className="peer sr-only" />
                  <span aria-hidden="true" className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-[4px] border border-ink-faint bg-surface text-transparent transition-colors duration-[var(--duration-fast)] peer-checked:border-primary peer-checked:bg-primary peer-checked:text-primary-ink peer-focus-visible:outline-2 peer-focus-visible:outline-accent peer-focus-visible:outline-offset-2">
                    <Check className="size-3" strokeWidth={2.5} />
                  </span>
                  <span className="min-w-0 flex-1 leading-relaxed">{a}</span>
                </label>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}
