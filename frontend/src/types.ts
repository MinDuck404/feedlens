export type Platform = "facebook" | "linkedin" | "x" | "reddit";
export type SourceType = "feed" | "group" | "search";
export type RunStatus = "pending" | "queued" | "scraping" | "analyzing" | "done" | "error" | "analysis_failed";

export interface AIProviderInfo {
  is_default?: boolean;
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
  config_error_code?: string;
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
  checking?: boolean;
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
  match_type?: MatchType | null;
  gaps?: string[];
  constraint_flags?: ("work_mode" | "location" | "salary" | "level")[];
}

export interface Post {
  topic_ids?: number[];
  topic_reason?: string;
  analyzed?: boolean;
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
  topics?: TopicDigest[];
  overall: string;
  categories: { category: string; count: number; summary: string; highlights: string[] }[];
  action_items: string[];
}

export interface Progress {
  phase: string;
  done: number;
  target: number;
  message: string;
  message_code?: string;
}

export interface Run {
  can_continue_analysis?: boolean;
  id: number;
  created_at: string;
  request: RunRequest;
  status: RunStatus;
  collected: number;
  ai_label: string;
  error: string | null;
  error_code?: string;
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
  status_message_code?: string;
  checked_at: string | null;
}


export type MatchType = "primary" | "adjacent" | "stretch" | "none";
export interface JobProfile {
  markdown: string;
  criteria: { work_modes: ("remote" | "hybrid" | "onsite")[]; locations: string[]; min_salary: number | null; currency: "VND" | "USD"; level: string };
  primary_roles: string[];
  adjacent_roles: { role: string; reason: string; enabled: boolean }[];
  allow_adjacent: boolean;
}
export interface CVAnalysis {
  markdown: string;
  suggested_roles: string[];
  adjacent_roles: JobProfile["adjacent_roles"];
  offline: boolean;
}

export type TopicColor = "red" | "navy" | "amber" | "teal" | "purple" | "rose" | "slate" | "brown";
export interface Topic {
  id: number;
  name: string;
  description: string;
  include_keywords: string[];
  exclude_keywords: string[];
  enabled: boolean;
  color: TopicColor;
}
export interface TopicDigest { topic_id: number; name: string; count: number; summary: string; post_ids: number[] }
export interface TopicApplyStatus { state: "idle" | "running" | "done" | "error"; done: number; total: number; error: string }

export interface TrendSeries {
  id: string;
  name: string;
  color: string;
  total: number;
  counts: number[];
  growth: number | null;
  previous_total?: number;
  is_new?: boolean;
}

export interface TrendsResponse {
  range: {
    group: "category" | "topic";
    bucket: "day" | "week";
    days: number;
    start_date: string;
    end_date: string;
    previous_start_date?: string;
    previous_end_date?: string;
  };
  timeline: string[];
  series: TrendSeries[];
  summary: {
    total_posts: number;
    top_gainer: { id: string; name: string; growth: number } | null;
    new_emerging: { id: string; name: string; count: number } | null;
  };
  fallback_count: number;
}
