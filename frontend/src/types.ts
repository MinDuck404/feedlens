export type Platform = "facebook" | "linkedin" | "x" | "reddit";
export type SourceType = "feed" | "group" | "search";
export type RunStatus = "pending" | "queued" | "scraping" | "analyzing" | "done" | "error";

export interface AIProviderInfo {
  key: string;
  name: string;
  configured: boolean;
  source: "db" | "env" | null;
  hint: string;
  default_model: string;
  key_url: string;
}

export interface AgentInfo {
  has_token: boolean;
  online: boolean;
  last_seen: string | null;
}

export interface Me {
  email: string;
  agent: AgentInfo;
}

export interface Meta {
  mode: "local" | "cloud";
  auth_required: boolean;
  config_error: string | null;
  signup_open: boolean;
  server_scrape: boolean;
  categories: Record<string, string>;
  max_posts: number;
}

export interface PlatformState {
  key: Platform;
  name: string;
  logged_in: boolean | null;
  has_profile: boolean;
  login_state: "idle" | "waiting";
}

export interface RunRequest {
  platform: Platform;
  source_type: SourceType;
  sources: string[];
  count: number;
  job_mode: boolean;
  keywords: string[];
  profile: string;
  ai_provider: string;
  ai_model: string;
  only_new: boolean;
  headless: boolean;
  speed: "fast" | "careful";
  runner: "agent" | "server";
  /** Ngôn ngữ AI dùng để viết tóm tắt (theo ngôn ngữ giao diện) */
  language?: "vi" | "en" | "zh";
}

export interface SavedGroup {
  url: string;
  enabled: boolean;
}

/** Cài đặt lưu theo tài khoản (server chỉ lưu nguyên JSON này). */
export interface Preferences {
  composer?: Partial<RunRequest> & { keywords_text?: string };
  groups?: Partial<Record<Platform, SavedGroup[]>>;
  searches?: Partial<Record<Platform, string>>;
}

export interface Job {
  title: string;
  company: string;
  location: string;
  salary: string;
  work_mode: string;
  contact: string;
  match_score: number;
  match_reason: string;
}

export interface Post {
  id: number;
  platform: string;
  source: string;
  author: string;
  text: string;
  url: string;
  posted_at: string;
  category: string;
  summary: string;
  job: Job | null;
}

export interface Digest {
  overall: string;
  categories: { category: string; count: number; summary: string; highlights: string[] }[];
  action_items: string[];
}

export interface Progress {
  phase: string;
  done: number;
  target: number;
  message: string;
}

export interface Run {
  id: number;
  created_at: string;
  request: RunRequest;
  status: RunStatus;
  collected: number;
  ai_label: string;
  error: string | null;
  digest: Digest | null;
  progress: Progress | null;
  posts?: Post[];
}

export interface PlatformSession {
  platform: Platform;
  hint: string;
  saved_at: string;
  status: "unchecked" | "ok" | "invalid";
  status_message: string;
  checked_at: string | null;
}
