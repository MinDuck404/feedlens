import { Check, ChevronDown, Globe, Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { LANGS, useI18n } from "../i18n";
import { getThemePreference, isDarkTheme, setThemePreference, type ThemePreference } from "../theme";

function ChoiceMenu({ label, icon, caption, value, options, onChange, above = true }: {
  label: string; icon: ReactNode; caption?: string; value: string;
  options: { value: string; label: string }[]; onChange: (value: string) => void; above?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const close = () => { setOpen(false); trigger.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return <div ref={root} className="relative shrink-0">
    <button ref={trigger} type="button" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen((v) => !v)} onKeyDown={(event) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); } }}
      className="flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-full px-2 text-ink-soft hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2">
      {icon}{caption && <span className="font-mono text-xs uppercase">{caption}</span>}{caption && <ChevronDown aria-hidden="true" className="size-3" />}
    </button>
    {open && <div ref={menu} id={id} role="menu" aria-label={label}
      className={`absolute right-0 z-50 min-w-40 rounded-xl border border-[var(--field-line)] bg-surface p-1 shadow-lg ${above ? "bottom-full mb-2" : "top-full mt-2"}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); return; }
        if (event.key === "Tab") { setOpen(false); trigger.current?.focus(); return; }
        const buttons = [...(menu.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
        const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
        let next = index;
        if (event.key === "ArrowDown") next = (index + 1) % buttons.length;
        else if (event.key === "ArrowUp") next = (index + buttons.length - 1) % buttons.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = buttons.length - 1;
        else return;
        event.preventDefault(); buttons[next]?.focus();
      }}>
      {options.map((option) => <button key={option.value} type="button" role="menuitemradio" aria-checked={value === option.value} tabIndex={-1}
        onClick={() => { onChange(option.value); close(); }}
        className="flex min-h-11 w-full items-center justify-between gap-4 rounded-lg px-3 text-left text-sm text-ink hover:bg-sunken focus:bg-sunken focus:outline-none">
        {option.label}{value === option.value && <Check aria-hidden="true" className="size-4 text-link" />}
      </button>)}
    </div>}
  </div>;
}

export function LanguageMenu({ above = true }: { above?: boolean }) {
  const { t, lang, setLang } = useI18n();
  return <ChoiceMenu label={t("lang.label")} icon={<Globe aria-hidden="true" className="size-4" />} caption={lang} value={lang} above={above}
    options={LANGS.map((l) => ({ value: l.code, label: l.label }))} onChange={(value) => setLang(value as typeof lang)} />;
}

export function ThemeMenu({ above = true }: { above?: boolean }) {
  const { t } = useI18n();
  const [theme, setTheme] = useState(getThemePreference);
  useEffect(() => { const update = () => setTheme(getThemePreference()); window.addEventListener("feedlens:theme", update); return () => window.removeEventListener("feedlens:theme", update); }, []);
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return <ChoiceMenu label={t("theme.label")} icon={<Icon aria-hidden="true" className="size-4" />} value={theme} above={above}
    options={(["light", "dark", "system"] as const).map((value) => ({ value, label: t(`theme.${value}`) }))}
    onChange={(value) => setThemePreference(value as ThemePreference)} />;
}

export function ThemeSwitch() {
  const { t } = useI18n();
  const [dark, setDark] = useState(isDarkTheme);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setDark(isDarkTheme());
    window.addEventListener("feedlens:theme", update); media.addEventListener("change", update);
    return () => { window.removeEventListener("feedlens:theme", update); media.removeEventListener("change", update); };
  }, []);
  return <button type="button" role="switch" aria-checked={dark} aria-label={t("theme.dark")} title={t("theme.toggle")}
    onClick={() => setThemePreference(dark ? "light" : "dark")}
    className="inline-flex h-11 w-[72px] shrink-0 items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2">
    <span aria-hidden="true" className="relative block h-8 w-16 rounded-full border border-[var(--field-line)] bg-[var(--field-bg)]">
      <Sun className="absolute top-2 left-2 size-3.5 text-ink-faint" /><Moon className="absolute top-2 right-2 size-3.5 text-ink-faint" />
      <span data-theme-knob className={`absolute top-[3px] left-[3px] grid size-6 place-items-center rounded-full bg-primary text-primary-ink shadow-sm transition-transform duration-[var(--duration-normal)] ease-[var(--ease-spring)] motion-reduce:transition-none ${dark ? "translate-x-8" : "translate-x-0"}`}>
        <Sun className={`absolute size-3.5 transition-[transform,opacity] duration-[var(--duration-normal)] motion-reduce:transition-none ${dark ? "rotate-90 opacity-0" : "rotate-0 opacity-100"}`} />
        <Moon className={`absolute size-3.5 transition-[transform,opacity] duration-[var(--duration-normal)] motion-reduce:transition-none ${dark ? "rotate-0 opacity-100" : "-rotate-90 opacity-0"}`} />
      </span>
    </span>
  </button>;
}
