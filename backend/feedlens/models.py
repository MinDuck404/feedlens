from __future__ import annotations

import hashlib
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Platform = Literal["facebook", "linkedin", "x", "reddit"]
SourceType = Literal["feed", "group", "search"]
Mode = Literal["feed", "group", "search", "page", "jobs", "recruiting_posts", "legacy_group",
               "subreddit", "home", "account", "list"]


class EmptyOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class FacebookGroupOptions(EmptyOptions):
    latest: bool = Field(True, strict=True)
    old_streak: int = Field(5, ge=1, le=50, strict=True, description="Gặp N bài cũ liên tiếp thì bỏ qua nhóm (khi bỏ qua bài cũ)")


class LinkedInJobsOptions(EmptyOptions):
    keywords: str = Field(..., min_length=1, max_length=500)
    location: str = Field("", max_length=300)
    work_modes: list[Literal["remote", "hybrid", "onsite"]] = Field(default_factory=list, max_length=3)
    posted_within: Literal["day", "week", "month"] = "week"


class LinkedInPostsOptions(EmptyOptions):
    posted_within: Literal["day", "week"] | None = "week"
    hiring: bool = Field(True, strict=True)


class RedditSubredditOptions(EmptyOptions):
    sort: Literal["new", "top_day", "top_week"] = "new"


class RedditSearchOptions(EmptyOptions):
    sort: Literal["new", "top"] = "new"


ModeOptions = (EmptyOptions | FacebookGroupOptions | LinkedInJobsOptions | LinkedInPostsOptions
               | RedditSubredditOptions | RedditSearchOptions)


class JobSeed(BaseModel):
    """Observed job facts, kept separately from the AI's JobInfo assessment."""
    model_config = ConfigDict(extra="forbid")
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""
    job_id: str = ""
    posted_at: str = ""
    work_mode: Literal["", "remote", "hybrid", "onsite"] = ""
    salary_text: str = ""

CATEGORIES: dict[str, str] = {
    "job": "Việc làm / Tuyển dụng",
    "news": "Tin tức / Thời sự",
    "tech": "Công nghệ / Kiến thức",
    "marketplace": "Mua bán / Rao vặt",
    "question": "Hỏi đáp / Xin ý kiến",
    "event": "Sự kiện",
    "promotion": "Quảng cáo / Khuyến mãi",
    "personal": "Đời sống / Chia sẻ cá nhân",
    "entertainment": "Giải trí / Meme",
    "other": "Khác",
}


class RawPost(BaseModel):
    platform: str
    source: str
    author: str = ""
    text: str
    url: str = ""
    posted_at: str = ""
    sponsored: bool = False
    job_seed: JobSeed | None = None

    @property
    def fingerprint(self) -> str:
        if self.platform == "linkedin" and self.job_seed and self.job_seed.job_id:
            return hashlib.sha1(f"linkedin|job|{self.job_seed.job_id}".encode()).hexdigest()
        norm = re.sub(r"\s+", " ", self.text.lower()).strip()[:500]
        return hashlib.sha1(f"{self.platform}|{norm}".encode()).hexdigest()


class JobInfo(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    work_mode: str = ""  # onsite / remote / hybrid
    contact: str = ""
    match_score: int = 0  # 0-100 vs user's keywords/profile
    match_reason: str = ""
    match_type: Literal["primary", "adjacent", "stretch", "none"] | None = None
    gaps: list[str] = Field(default_factory=list, max_length=3)
    constraint_flags: list[Literal["work_mode", "location", "salary", "level"]] = Field(default_factory=list, max_length=4)


class AnalyzedPost(RawPost):
    id: Optional[int] = None
    analyzed: bool = True
    analyzed_by: str = ""
    category: str = "other"
    summary: str = ""
    job: Optional[JobInfo] = None
    topic_ids: list[int] = Field(default_factory=list)
    topic_reason: str = ""


TOPIC_COLORS = (
    "red", "navy", "amber", "teal", "purple", "rose", "slate", "brown",
    "emerald", "indigo", "coral", "olive", "cyan", "wine", "ochre", "rust",
)
MAX_TOPICS = 12


class Topic(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=400)
    include_keywords: list[str] = Field(default_factory=list, max_length=20)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=20)
    enabled: bool = True
    color: str = "red"


class TopicDigest(BaseModel):
    topic_id: int
    name: str
    count: int
    summary: str = ""
    post_ids: list[int] = Field(default_factory=list)


class CategoryDigest(BaseModel):
    category: str
    count: int
    summary: str
    highlights: list[str] = Field(default_factory=list)


class Digest(BaseModel):
    overall: str
    categories: list[CategoryDigest]
    action_items: list[str] = Field(default_factory=list)
    topics: list[TopicDigest] = Field(default_factory=list)  # "Chủ đề của bạn", kể cả chủ đề 0 bài


class RunRequest(BaseModel):
    platform: Platform
    source_type: SourceType = "feed"
    mode: Mode | None = None
    options: ModeOptions = Field(default_factory=EmptyOptions)
    sources: list[str] = Field(default_factory=list, description="Group URL/ID, subreddit, từ khóa tìm kiếm...")
    count: int = Field(50, ge=1, le=1000, description="Số bài cho MỖI nguồn (bảng tin / group / từ khóa)")
    speed: Literal["fast", "careful"] = "fast"
    language: Literal["vi", "en", "zh"] = Field("vi", description="Ngôn ngữ AI viết tóm tắt (theo giao diện)")
    runner: Literal["agent", "server"] = Field("agent", description="cloud: agent trên máy user hay server dùng cookie")
    job_mode: bool = False
    keywords: list[str] = Field(default_factory=list)
    profile: str = Field("", description="Mô tả ngắn về bạn/CV để chấm điểm mức phù hợp việc làm")
    ai_provider: str = Field("auto", description="auto | anthropic | openai | gemini | offline")
    ai_model: str = Field("", description="Bỏ trống => model mặc định của nhà cung cấp")
    only_new: bool = Field(False, description="Bỏ qua bài đã thấy ở các lượt trước")
    headless: bool = False  # mặc định hiện cửa sổ để bạn thấy bot đang làm gì
    max_posts: Literal[500, 1000, 2000] | None = Field(None, description="Trần bài mỗi lượt chọn trong Cài đặt; None = mặc định của server")

    @model_validator(mode="before")
    @classmethod
    def source_mode(cls, value):
        if isinstance(value, dict):
            from .source_modes import prepare_request
            return prepare_request(value)
        return value
