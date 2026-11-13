from __future__ import annotations

import hashlib
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

Platform = Literal["facebook", "linkedin", "x", "reddit"]
SourceType = Literal["feed", "group", "search"]

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

    @property
    def fingerprint(self) -> str:
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


class AnalyzedPost(RawPost):
    id: Optional[int] = None
    category: str = "other"
    summary: str = ""
    job: Optional[JobInfo] = None


class CategoryDigest(BaseModel):
    category: str
    count: int
    summary: str
    highlights: list[str] = Field(default_factory=list)


class Digest(BaseModel):
    overall: str
    categories: list[CategoryDigest]
    action_items: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    platform: Platform
    source_type: SourceType = "feed"
    sources: list[str] = Field(default_factory=list, description="Group URL/ID, subreddit, từ khóa tìm kiếm...")
    count: int = Field(50, ge=1, le=1000, description="Số bài cho MỖI nguồn (bảng tin / group / từ khóa)")
    speed: Literal["fast", "careful"] = "fast"
    job_mode: bool = False
    keywords: list[str] = Field(default_factory=list)
    profile: str = Field("", description="Mô tả ngắn về bạn/CV để chấm điểm mức phù hợp việc làm")
    ai_provider: str = Field("auto", description="auto | anthropic | openai | gemini | offline")
    ai_model: str = Field("", description="Bỏ trống => model mặc định của nhà cung cấp")
    only_new: bool = Field(False, description="Bỏ qua bài đã thấy ở các lượt trước")
    headless: bool = False  # mặc định hiện cửa sổ để bạn thấy bot đang làm gì
