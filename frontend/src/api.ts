import type { Meta, PlatformState, Run, RunRequest } from "./types";

// Khi deploy riêng, VITE_API_URL là URL backend (vd https://feedlens-api.up.railway.app).
// Khi chạy local qua Vite proxy hoặc backend phục vụ luôn frontend thì để trống.
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const TOKEN_KEY = "feedlens.token";
export const auth = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* chế độ riêng tư */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* bỏ qua */ } },
};

export class UnauthorizedError extends Error {}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const token = auth.get();
  const r = await fetch(API_BASE + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (r.status === 401) {
    auth.clear();
    window.dispatchEvent(new Event("feedlens:logout"));
    throw new UnauthorizedError("Phiên đăng nhập đã hết hạn.");
  }
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Lỗi ${r.status}: ${r.statusText}`);
  }
  return r;
}

const call = async <T>(path: string, init?: RequestInit): Promise<T> => (await raw(path, init)).json();

export const api = {
  meta: () => call<Meta>("/api/meta"),
  login: (password: string) => call<{ token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  platforms: () => call<PlatformState[]>("/api/platforms"),
  platformAction: (p: string, act: "login" | "check" | "logout") =>
    call(`/api/platforms/${p}/${act}`, { method: "POST" }),
  runs: () => call<Run[]>("/api/runs"),
  run: (id: number) => call<Run>(`/api/runs/${id}`),
  createRun: (req: RunRequest) => call<{ id: number }>("/api/runs", { method: "POST", body: JSON.stringify(req) }),
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
