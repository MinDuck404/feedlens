"""Offline classification and job matching."""
from __future__ import annotations

import re
from collections import Counter
from .models import CATEGORIES, AnalyzedPost, CategoryDigest, Digest, JobInfo, TopicDigest
from . import analyzer as facade
from .analysis_prompts import (
    _seeded_job,
)
from .analysis_topics import (
    _topic_groups,
    heuristic_topics,
)
from .job_scoring import (
    MATCH_STOPWORDS,
    _LEVELS,
    _cv_skills,
    _job_salary,
    _location_conflict,
    _match_terms,
    _normalize_level,
    _profile_level,
    _role_terms,
    _role_text,
    _work_mode_conflict,
)


KEYWORDS: dict[str, list[str]] = {
    "job": ["tuyển", "tuyen dung", "hiring", "we're hiring", "job", "vị trí", "ứng tuyển", "jd", "lương",
            "salary", "cv", "intern", "thực tập", "full-time", "part-time", "remote", "việc làm", "cần người"],
    "marketplace": ["bán", "pass lại", "thanh lý", "giá", "ship", "order", "inbox", "for sale", "cho thuê"],
    "question": ["?", "cho em hỏi", "cho mình hỏi", "xin ý kiến", "có ai", "help", "giúp"],
    "event": ["sự kiện", "event", "workshop", "webinar", "meetup", "đăng ký tham gia", "hội thảo"],
    "promotion": ["khuyến mãi", "giảm giá", "sale off", "voucher", "ưu đãi", "discount"],
    "tech": ["ai", "python", "javascript", "react", "llm", "cloud", "api", "github", "devops", "data"],
    "news": ["tin tức", "breaking", "báo", "chính phủ", "thị trường", "news", "cập nhật"],
    "entertainment": ["haha", "meme", "phim", "nhạc", "game", "😂", "🤣"],
}


def _first_sentence(text: str, limit: int = 160) -> str:
    s = re.split(r"(?<=[.!?\n])\s", text.strip(), maxsplit=1)[0]
    return (s[:limit] + "…") if len(s) > limit else s


def heuristic_category(text: str) -> str:
    t = text.lower()
    scores = {c: sum(t.count(k) for k in kws) for c, kws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "personal" if len(t) < 280 else "other"


class HeuristicAnalyzer:
    label = "bộ lọc từ khóa offline"

    def classify(self, posts, job_mode, keywords, profile, progress):
        out = []
        topics = list(getattr(self, "topics", None) or [])
        cv_profile = getattr(self, "job_profile", None)
        kws = [k.casefold() for k in keywords]
        primary_roles, adjacent_roles = [], []
        if cv_profile:
            primary_roles = _role_terms(cv_profile.primary_roles)
            adjacent_roles = _role_terms([r.role for r in cv_profile.adjacent_roles
                                          if cv_profile.allow_adjacent and r.enabled and r.role.strip()])
        elif profile:
            kws += re.findall(r"[\w+#.]+", profile.casefold())
        kws = sorted({k.strip() for k in kws if len(k.strip()) > 2 and k.strip() not in MATCH_STOPWORDS})
        skills = sorted(set(kws + _cv_skills(cv_profile)) - set(primary_roles + adjacent_roles)) if cv_profile else kws
        for p in posts:
            match_text = p.text
            if p.job_seed is not None:
                match_text += "\n" + "\n".join([p.job_seed.title, p.job_seed.company, p.job_seed.location,
                                              p.job_seed.work_mode, p.job_seed.salary_text])
            cat = "job" if p.job_seed is not None else heuristic_category(p.text)
            job = None
            if cat == "job":
                hits = _match_terms(skills, match_text.casefold())
                match_type = None
                if cv_profile:
                    role_text = _role_text("\n".join([p.job_seed.title, p.text]) if p.job_seed else p.text)
                    primary = _match_terms(primary_roles, role_text.casefold())
                    if (not primary and _normalize_level(role_text) == "fresher"
                            and re.search(r"(?i)\bdeveloper\b", role_text)
                            and any(re.search(r"(?i)\bdeveloper\b|\bdev\b", role) for role in cv_profile.primary_roles)):
                        primary = ["developer"]
                    adjacent = [] if primary else _match_terms(adjacent_roles, role_text.casefold())
                    match_type = "primary" if primary else "adjacent" if adjacent else "none"
                    score = {"primary": 70, "adjacent": 50, "none": 0}[match_type]
                    score += min(30, 10 * len(hits))
                    user_level, user_years = _profile_level(cv_profile)
                    job_level = _normalize_level(role_text)
                    level_gap = _LEVELS.get(job_level, -1) - _LEVELS.get(user_level, -1) if job_level and user_level else 0
                    years = re.search(r"(?i)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?|năm)\b", role_text)
                    years_gap = bool(years and user_years is not None and float(years[1]) >= user_years + 2)
                    flags = ["level"] if level_gap >= 2 or years_gap else []
                    if flags:
                        score = min(35, score)
                        if match_type in {"primary", "adjacent"}:
                            match_type = "stretch"
                    elif level_gap == 1:
                        score = min(65, score)
                    location = p.job_seed.location if p.job_seed else ""
                    work_mode = p.job_seed.work_mode if p.job_seed else ""
                    preferences = " ".join(cv_profile.criteria.locations) + " " + profile
                    if _location_conflict(preferences, location, work_mode):
                        flags.append("location")
                        score -= 35
                    if _work_mode_conflict(cv_profile.criteria.work_modes, work_mode):
                        flags.append("work_mode")
                        score -= 25
                    score = max(0, score)
                    hits = primary + adjacent + hits
                else:
                    score = int(100 * len(hits) / len(kws)) if kws else 50
                    flags = []
                contact = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|0\d{9,10}", p.text)
                job = JobInfo(title=_first_sentence(p.text, 80), match_score=score,
                               salary=_job_salary(p.text),
                               contact=contact.group(0) if contact else "",
                               match_reason=(f"Khớp từ khóa: {', '.join(hits)}" if hits else "")[:140],
                               match_type=match_type)
                if cv_profile:
                    job.constraint_flags = flags
                    job.match_reason = (f"Vai trò {match_type}: {', '.join(primary or adjacent) or 'khác ngành'}"
                                        + (f"; kỹ năng: {', '.join(hits[:5])}" if hits else "")
                                        + ("; cấp bậc chưa phù hợp" if "level" in flags else ""))[:140]
                if p.job_seed is not None:
                    job = _seeded_job(p, job.model_dump())
            tids = heuristic_topics(match_text, topics)
            out.append(AnalyzedPost(**p.model_dump(), category=cat, summary=_first_sentence(p.text), job=job,
                                    analyzed_by="offline" if self.label == HeuristicAnalyzer.label else self.label,
                                    topic_ids=tids))
        progress(len(out), f"Đã phân loại {len(out)}/{len(posts)} (offline)")
        return out

    def tag_topics(self, posts, topics, progress=lambda n, m: None):
        out = {p.id: (heuristic_topics(f"{p.summary}\n{p.text}", topics), "") for p in posts}
        progress(len(posts), "")
        return out

    def topic_digest(self, posts):
        topics = list(getattr(self, "topics", None) or [])
        groups = _topic_groups(posts, topics)
        return [TopicDigest(topic_id=t.id, name=t.name, count=len(groups[t.id]),
                            post_ids=[p.id for p in groups[t.id] if p.id]) for t in topics]

    def digest(self, posts, job_mode):
        counts = Counter(p.category for p in posts)
        cats = []
        for c, n in counts.most_common():
            items = [p for p in posts if p.category == c]
            cats.append(CategoryDigest(category=c, count=n,
                                       summary=f"{n} bài thuộc nhóm {CATEGORIES[c]}.",
                                       highlights=[p.summary for p in items[:3]]))
        top = ", ".join(f"{CATEGORIES[c]} ({n})" for c, n in counts.most_common(3))
        jobs = sorted((p for p in posts if p.job), key=lambda p: -p.job.match_score)
        return Digest(
            overall=f"Đã đọc {len(posts)} bài. Nhiều nhất: {top}. "
                    "(Chế độ offline — thêm API key Claude/OpenAI/Gemini để có tóm tắt bằng AI.)",
            categories=cats,
            action_items=[f"Xem job: {p.job.title}" for p in jobs[:5]] if job_mode else [],
            topics=self.topic_digest(posts),
        )
