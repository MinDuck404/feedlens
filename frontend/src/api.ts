import { serverMessage, translate } from "./i18n";
import { serialWriter } from "./logic";
import type { AgentInfo, AIProviderInfo, JobProfile, CVAnalysis, Me, Meta, PlatformSession, PlatformState, Preferences, Run, RunRequest } from "./types";

// Khi deploy riêng, VITE_API_URL là URL backend (vd https://feedlens-api.up.railway.app).
// Khi chạy local qua Vite proxy hoặc backend phục vụ luôn frontend thì để trống.
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const TOKEN_KEY = "feedlens.token";
export const auth = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* chế độ riêng tư */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* bỏ qua */ } },
};

export class ApiError extends Error {
  constructor(public status: number, public code: string | undefined, public detail: unknown, message: string) {
    super(message);
  }
}
export class UnauthorizedError extends ApiError {}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const token = auth.get();
  let r: Response;
  try { r = await fetch(API_BASE + path, {
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  }); } catch { throw new ApiError(0, undefined, "", translate("api.network")); }
  if (r.status === 401 && path !== "/api/auth/login" && path !== "/api/auth/register") {
    auth.clear();
    window.dispatchEvent(new Event("feedlens:logout"));
    throw new UnauthorizedError(401, "error.session_expired", "", translate("api.sessionExpired"));
  }
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const code = body.code ?? (path === "/api/auth/login" && r.status === 401 ? "error.invalid_credentials" : undefined);
    const message = code || typeof body.detail === "string"
      ? serverMessage(code, body.detail, { status: r.status })
      : translate("api.requestFailed", { status: r.status });
    throw new ApiError(r.status, code, body.detail, message);
  }
  return r;
}

const call = async <T>(path: string, init?: RequestInit): Promise<T> => (await raw(path, init)).json();

const savePreferences = serialWriter<{ body: string; token: string }>(({ body, token }) => {
  // A queued write from a previous account must never use the next account's token.
  if (auth.get() !== token) throw new UnauthorizedError(401, "error.session_expired", "", translate("api.sessionExpired"));
  return call("/api/preferences", { method: "PUT", body });
});

export const api = {
  meta: () => call<Meta>("/api/meta"),
  login: (email: string, password: string) =>
    call<{ token: string; email: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) =>
    call<{ token: string; email: string }>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => call<Me>("/api/auth/me"),
  profile: () => call<JobProfile | null>("/api/profile"),
  saveProfile: (profile: JobProfile) => call<JobProfile>("/api/profile", { method: "PUT", body: JSON.stringify(profile) }),
  deleteProfile: () => call("/api/profile", { method: "DELETE" }),
  analyzeCV: (form: FormData) => call<CVAnalysis>("/api/profile/cv", { method: "POST", body: form }),
  preferences: () => call<Preferences>("/api/preferences"),
  savePreferences: (p: Preferences) => savePreferences({ body: JSON.stringify(p), token: auth.get() }),
  sessions: () => call<PlatformSession[]>("/api/sessions"),
  saveSession: (p: string, cookies: string) =>
    call<PlatformSession>(`/api/sessions/${p}`, { method: "PUT", body: JSON.stringify({ cookies }) }),
  deleteSession: (p: string) => call(`/api/sessions/${p}`, { method: "DELETE" }),
  checkSession: (p: string) => call<PlatformSession>(`/api/sessions/${p}/check`, { method: "POST" }),
  newAgentToken: () => call<{ token: string }>("/api/agent/token", { method: "POST" }),
  providers: () => call<AIProviderInfo[]>("/api/ai/providers"),
  saveKey: (p: string, apiKey: string) =>
    call<{ models: string[] }>(`/api/ai/keys/${p}`, { method: "PUT", body: JSON.stringify({ api_key: apiKey }) }),
  deleteKey: (p: string) => call(`/api/ai/keys/${p}`, { method: "DELETE" }),
  models: (p: string, refresh = false) =>
    call<{ models: string[]; default: string }>(`/api/ai/models/${p}${refresh ? "?refresh=true" : ""}`),
  platforms: () => call<PlatformState[]>("/api/platforms"),
  platformAction: (p: string, act: "login" | "check" | "logout") =>
    call(`/api/platforms/${p}/${act}`, { method: "POST" }),
  runs: () => call<Run[]>("/api/runs"),
  run: (id: number) => call<Run>(`/api/runs/${id}`),
  createRun: (req: RunRequest) =>
    call<{ id: number; agent?: AgentInfo }>("/api/runs", { method: "POST", body: JSON.stringify(req) }),
  deleteRun: (id: number) => call(`/api/runs/${id}`, { method: "DELETE" }),
  /** Tải file xuất kèm token (thẻ <a href> thường không gửi được header Authorization). */
  download: async (id: number, fmt: "md" | "csv" | "json") => {
    const r = await raw(`/api/runs/${id}/export?fmt=${fmt}`);
    const url = URL.createObjectURL(await r.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `feedlens-${id}.${fmt}` });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
