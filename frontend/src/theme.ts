export type ThemePreference = "system" | "light" | "dark";
let transitionTimer: ReturnType<typeof setTimeout> | undefined;
let colorsRegistered = false;

export function getThemePreference(): ThemePreference {
  const value = document.documentElement.dataset?.themePreference;
  return value === "light" || value === "dark" ? value : "system";
}

export function setThemePreference(value: ThemePreference) {
  const root = document.documentElement;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (!colorsRegistered && typeof CSS !== "undefined" && CSS.registerProperty) {
    const colors = ["paper", "sheet", "sunken", "sunken-hover", "field-bg", "field-line", "reading-panel", "ink", "ink-soft", "ink-faint", "line", "line-strong", "primary", "primary-ink", "accent", "accent-fill", "accent-ink", "accent-glow", "link", "danger", "ok", "warning", ...["tech", "marketplace", "question", "event", "promotion", "entertainment", "news", "job", "personal", "other"].map((c) => `cat-${c}`)].map((c) => `--${c}`);
    colors.forEach((name) => { try { CSS.registerProperty({ name, syntax: "<color>", inherits: true, initialValue: "transparent" }); } catch { /* A property may already be registered. */ } });
    root.style.setProperty("--theme-transition-properties", colors.join(","));
    colorsRegistered = true;
  }
  clearTimeout(transitionTimer);
  if (!reduced && colorsRegistered) {
    root.classList.add("theme-changing");
    void root.offsetWidth; // Establish the old palette before changing its target colors.
    transitionTimer = setTimeout(() => root.classList.remove("theme-changing"), 280);
  } else root.classList.remove("theme-changing");
  root.dataset.themePreference = value;
  if (value === "system") delete root.dataset.theme; else root.dataset.theme = value;
  root.classList.toggle("dark", value === "dark");
  root.classList.toggle("light", value === "light");
  try { localStorage.setItem("feedlens.theme", value); } catch { /* Private mode still applies the current choice. */ }
  window.dispatchEvent(new Event("feedlens:theme"));
}

export function isDarkTheme(): boolean {
  const preference = getThemePreference();
  return preference === "dark" || (preference === "system" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches);
}
