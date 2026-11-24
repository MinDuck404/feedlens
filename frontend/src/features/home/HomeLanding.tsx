import { useMemo } from "react";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n";

/** Màn hình chào Home Landing theo phong cách báo in Fiorinda */
export default function HomeLanding({
  cloud,
  onNewRun,
  onOpenSettings,
  loggingIn,
}: {
  cloud: boolean;
  onNewRun: () => void;
  onOpenSettings: () => void;
  loggingIn?: string;
}) {
  const { t, locale } = useI18n();
  const [loginBefore, loginAfter] = t("home.loggingInFull").split("{name}");
  const steps = cloud
    ? [t("home.cloud1"), t("home.cloud2"), t("home.cloud3")]
    : [t("home.local1"), t("home.local2"), t("home.local3")];

  const todayStr = useMemo(() => {
    return new Date().toLocaleDateString(locale, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }, [locale]);

  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-start px-6 py-10 md:py-16">
      {loggingIn && (
        <div
          role="status"
          className="paper-card mb-8 flex items-center gap-3 rounded-2xl px-5 py-4 border border-line"
        >
          <span className="size-2.5 shrink-0 animate-pulse rounded-full bg-accent" />
          <p className="text-sm">
            {loginBefore}
            <b>{loggingIn}</b>
            {loginAfter} {t("home.loggingInHint")}
          </p>
        </div>
      )}

      {/* Newspaper Masthead Eyebrow Header */}
      <header className="masthead mb-8">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-accent" />
            <span className="font-semibold text-ink">FeedLens</span>
            <span className="hidden sm:inline text-line">•</span>
            <span className="hidden sm:inline">{t("home.edition")}</span>
          </div>
          <time className="font-sans text-ink-soft">{todayStr}</time>
        </div>
      </header>

      {/* Main Newspaper Headline */}
      <h1 className="font-headline text-4xl font-normal tracking-tight text-ink sm:text-5xl md:text-6xl leading-[1.12]">
        <span className="block">{t("home.title1")}</span>
        <span className="block text-accent font-serif italic">{t("home.title2")}</span>
      </h1>

      <div className="rule-double my-6" />

      {/* Editorial Lead Paragraph */}
      <p className="prose-reading text-base md:text-lg text-ink-soft leading-relaxed">
        {t("home.lead")}
      </p>

      {/* Table of Contents / 3 Steps (mục lục báo in, bớt card) */}
      <section className="mt-8 border-t border-b border-line py-5">
        <h2 className="mb-3 text-xs font-semibold text-ink-soft">
          {t("home.index")}
        </h2>
        <ol className="divide-y divide-line/70">
          {steps.map((s, i) => (
            <li
              key={i}
              className="flex items-baseline gap-4 py-3 group transition-colors hover:bg-sunken/40 px-2 -mx-2 rounded-lg"
            >
              <span className="font-headline text-base font-semibold text-accent shrink-0 tabular-nums">
                0{i + 1}
              </span>
              <span className="text-sm font-normal text-ink leading-relaxed">
                {!cloud && i === 0 ? <><span className="md:hidden">{t("home.local1Mobile")}</span><span className="hidden md:inline">{s}</span></> : s}
              </span>
            </li>
          ))}
        </ol>
      </section>

      {/* Action Bar */}
      <div className="mt-8 flex flex-wrap items-center gap-3.5">
        <Button onClick={onNewRun} size="lg" variant="primary" pill>
          {t("act.newRun")}
        </Button>
        <Button onClick={onOpenSettings} size="lg" variant="outline" pill>
          {t("act.settings")}
        </Button>
      </div>
    </div>
  );
}
