import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { vi, type Key } from "./locales/vi";
import { en } from "./locales/en";
import { zh } from "./locales/zh";

export type { Key } from "./locales/vi";

/** Đa ngôn ngữ: tự nhận theo trình duyệt (vi / en / zh), người dùng đổi được, lựa chọn lưu trên trình duyệt.
 *  Từ điển tiếng Việt là chuẩn; en và zh bắt buộc có đủ mọi khóa (TypeScript báo lỗi nếu thiếu). */
export type Lang = "vi" | "en" | "zh";
export const LANGS: { code: Lang; label: string }[] = [
  { code: "vi", label: "Tiếng Việt" },
  { code: "en", label: "English" },
  { code: "zh", label: "中文" },
];
const LOCALE: Record<Lang, string> = { vi: "vi-VN", en: "en-US", zh: "zh-CN" };
const STORE = "feedlens.lang";

const DICTS: Record<Lang, Record<Key, string>> = { vi, en, zh };

export function detectLang(): Lang {
  try {
    const saved = localStorage.getItem(STORE);
    if (saved === "vi" || saved === "en" || saved === "zh") return saved;
  } catch { /* chế độ riêng tư */ }
  for (const l of navigator.languages ?? [navigator.language]) {
    const code = l.toLowerCase();
    if (code.startsWith("vi")) return "vi";
    if (code.startsWith("zh")) return "zh";
    if (code.startsWith("en")) return "en";
  }
  return "en";
}

type Vars = Record<string, string | number>;
let currentLang: Lang = detectLang();
const listeners = new Set<(lang: Lang) => void>();

function setCurrentLang(lang: Lang) {
  currentLang = lang;
  listeners.forEach((listener) => listener(lang));
}

export function formatNumber(n: number, lang: Lang = currentLang): string {
  return new Intl.NumberFormat(LOCALE[lang]).format(n);
}

function renderMessage(lang: Lang, key: Key, vars?: Vars): string {
  let s = DICTS[lang][key] ?? vi[key] ?? key;
  if (lang === "en" && vars) {
    const singular: Record<string, string> = { runs: "run", "job searches": "job search", posts: "post", sources: "source", "groups selected": "group selected" };
    const plural = new Intl.PluralRules("en");
    s = s.replace(/\{(\w+)\} (runs|job searches|posts|sources|groups selected)\b/g, (match, name: string, noun: string) =>
      typeof vars[name] === "number" && plural.select(vars[name]) === "one" ? `{${name}} ${singular[noun]}` : match);
  }
  if (vars) for (const [k, v] of Object.entries(vars)) {
    s = s.split(`{${k}}`).join(typeof v === "number" && k !== "id" ? formatNumber(v, lang) : String(v));
  }
  return s;
}

/** Uses the same in-memory language as React, even when storage is unavailable. */
export function translate(key: Key, vars?: Vars): string {
  return renderMessage(currentLang, key, vars);
}

export function serverMessage(code: string | undefined, fallback = "", vars?: Vars): string {
  if (code && Object.hasOwn(vi, code)) return translate(code as Key, vars);
  // Compatibility with older servers that only return a detail string.
  if (/Sai email|incorrect.*password/i.test(fallback)) return translate("error.invalid_credentials");
  if (/FEEDLENS_SECRET/.test(fallback)) return translate("error.config");
  if (/\bcookies?(?:\s+(?:facebook|linkedin|x|reddit))?\s+(?:đã\s+)?(?:hết hạn|hết hiệu lực|không (?:còn )?(?:hợp lệ|dùng được)|(?:is |are )?(?:invalid|expired))|\b(?:invalid|expired)\s+cookies?\b/i.test(fallback)) return translate("error.cookie_invalid");
  return vars?.status ? translate("api.requestFailed", vars) : translate("error.run_failed");
}
interface I18n {
  lang: Lang;
  locale: string;
  setLang: (l: Lang) => void;
  t: (key: Key, vars?: Vars) => string;
  /** Tên loại bài theo ngôn ngữ đang chọn */
  cat: (category: string) => string;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => currentLang);
  const setLang = useCallback((l: Lang) => {
    setCurrentLang(l);
    try { localStorage.setItem(STORE, l); } catch { /* bỏ qua */ }
  }, []);
  useEffect(() => {
    listeners.add(setLangState);
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORE || e.key === null) setCurrentLang(detectLang());
    };
    window.addEventListener("storage", onStorage);
    return () => { listeners.delete(setLangState); window.removeEventListener("storage", onStorage); };
  }, []);
  useEffect(() => { document.documentElement.lang = lang === "zh" ? "zh-CN" : lang; }, [lang]);

  const value = useMemo<I18n>(() => {
    const dict = DICTS[lang];
    const t = (key: Key, vars?: Vars) => renderMessage(lang, key, vars);
    const cat = (c: string) => (`cat.${c}` in dict ? dict[`cat.${c}` as Key] : c);
    return { lang, locale: LOCALE[lang], setLang, t, cat };
  }, [lang, setLang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n phải nằm trong <I18nProvider>");
  return v;
}
