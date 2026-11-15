export type ThemePreference = "system" | "light" | "dark";

export function getThemePreference(): ThemePreference {
  const value = document.documentElement.dataset?.themePreference;
  return value === "light" || value === "dark" ? value : "system";
}

export function setThemePreference(value: ThemePreference) {
  const root = document.documentElement;
  root.dataset.themePreference = value;
  if (value === "system") delete root.dataset.theme; else root.dataset.theme = value;
  root.classList.toggle("dark", value === "dark");
  root.classList.toggle("light", value === "light");
  try { localStorage.setItem("feedlens.theme", value); } catch { /* Private mode still applies the current choice. */ }
  window.dispatchEvent(new Event("feedlens:theme"));
}
