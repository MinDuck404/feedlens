"""/api/search & /api/ask: Tìm kiếm nhanh (FTS5 / LIKE) và Hỏi đáp có trích dẫn."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .ai import resolve_provider_key, user_keys
from .ai.registry import preferred_provider
from .analyzer import LANGUAGE_NAMES, get_analyzer
from .auth import CurrentUser, current_user
from .models import CATEGORIES

ASK_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "query_terms": {"type": "array", "items": {"type": "string"}},
        "date_from": {"type": ["string", "null"]},
        "date_to": {"type": ["string", "null"]},
        "categories": {"type": "array", "items": {"type": "string"}},
        "topics": {"type": "array", "items": {"type": "string"}},
        "job": {
            "type": ["object", "null"],
            "properties": {
                "work_modes": {"type": "array", "items": {"type": "string"}},
                "min_salary_vnd": {"type": ["integer", "null"]},
                "locations": {"type": "array", "items": {"type": "string"}},
                "min_score": {"type": ["integer", "null"]},
                "match_type": {"type": ["string", "null"]},
            },
            "required": ["work_modes", "min_salary_vnd", "locations", "min_score", "match_type"],
            "additionalProperties": False,
        },
        "has_link": {"type": ["boolean", "null"]},
        "has_github": {"type": ["boolean", "null"]},
        "limit": {"type": "integer"},
    },
    "required": ["query_terms", "date_from", "date_to", "categories", "topics", "job", "has_link", "has_github", "limit"],
    "additionalProperties": False,
}

ASK_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Câu trả lời ngắn gọn, có trích dẫn [#id] dựa trên các bài viết được cung cấp",
        },
    },
    "required": ["answer"],
    "additionalProperties": False,
}

NO_MATCH_MESSAGES = {
    "vi": "Không tìm thấy bài viết nào khớp trong dữ liệu của bạn.",
    "en": "No matching posts found in your data.",
    "zh": "在您的数据中未找到匹配的帖子。",
}


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    language: Literal["vi", "en", "zh"] = "vi"


def search_router(db):
    router = APIRouter(prefix="/api")

    @router.get("/search")
    def search(
        q: str = Query(""),
        platform: str | None = Query(None),
        categories: list[str] = Query(default=[]),
        topic_ids: list[int] = Query(default=[]),
        date_from: str | None = Query(None),
        date_to: str | None = Query(None),
        job_only: bool = Query(False),
        work_modes: list[str] = Query(default=[]),
        min_score: int | None = Query(None),
        has_link: bool | None = Query(None),
        has_github: bool | None = Query(None),
        limit: int = Query(default=40, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        user: CurrentUser = Depends(current_user),
    ):
        posts, total = db().search_posts(
            user_id=user.id,
            q=q,
            platform=platform,
            categories=categories if categories else None,
            topic_ids=topic_ids if topic_ids else None,
            date_from=date_from,
            date_to=date_to,
            job_only=job_only,
            work_modes=work_modes if work_modes else None,
            min_score=min_score,
            has_link=has_link,
            has_github=has_github,
            limit=limit,
            offset=offset,
        )
        return {
            "total": total,
            "posts": posts,
            "limit": limit,
            "offset": offset,
        }

    @router.post("/ask")
    def ask(body: AskBody, user: CurrentUser = Depends(current_user)):
        # Kiểm tra key AI của người dùng
        keys = user_keys(db(), user.id)
        provider = preferred_provider(db(), user.id, "auto")
        if resolve_provider_key(provider, keys) == "offline":
            return JSONResponse({"code": "error.ask_needs_key", "detail": "error.ask_needs_key"}, status_code=400)

        analyzer = get_analyzer(provider, None, keys, user.id)

        # Bước 1: Hiểu câu hỏi -> bộ lọc JSON
        today_str = datetime.now(timezone.utc).date().isoformat()
        user_topics = db().list_topics(user.id, enabled_only=True)
        topic_names = [t.name for t in user_topics]
        valid_cats = list(CATEGORIES.keys())

        sys_step1 = (
            "Bạn là trợ lý phân tích câu hỏi người dùng thành bộ lọc tìm kiếm có cấu trúc. "
            "Trích xuất các từ khóa (query_terms), khoảng ngày (date_from, date_to), "
            "danh mục (categories), chủ đề (topics) và tiêu chí việc làm nếu có theo schema."
        )
        prompt_step1 = (
            f"Ngày hôm nay: {today_str}\n"
            f"Các danh mục hợp lệ: {', '.join(valid_cats)}\n"
            f"Các chủ đề người dùng đang theo dõi: {', '.join(topic_names) if topic_names else '(chưa có)'}\n\n"
            f'Câu hỏi: "{body.question}"'
        )

        filter_json = analyzer.provider.complete_json(sys_step1, prompt_step1, ASK_FILTER_SCHEMA, effort="low")

        # Bước 2: Chạy search với bộ lọc vừa trích xuất (tối đa 40 bài)
        q_terms = filter_json.get("query_terms") or []
        q_str = " ".join(q_terms)
        cat_filter = filter_json.get("categories") or []
        t_filter = filter_json.get("topics") or []
        matched_topic_ids = [t.id for t in user_topics if t.name in t_filter]

        job_data = filter_json.get("job")
        job_only = bool(cat_filter == ["job"] or job_data)
        work_modes = job_data.get("work_modes") if job_data else None
        min_score = job_data.get("min_score") if job_data else None

        posts, _ = db().search_posts(
            user_id=user.id,
            q=q_str,
            categories=cat_filter if cat_filter else None,
            topic_ids=matched_topic_ids if matched_topic_ids else None,
            date_from=filter_json.get("date_from"),
            date_to=filter_json.get("date_to"),
            job_only=job_only,
            work_modes=work_modes if work_modes else None,
            min_score=min_score,
            has_link=filter_json.get("has_link"),
            has_github=filter_json.get("has_github"),
            limit=40,
            offset=0,
        )

        # Không có bài: trả lời không tìm thấy, tuyệt đối KHÔNG gọi bước 3
        if not posts:
            no_match = NO_MATCH_MESSAGES.get(body.language, NO_MATCH_MESSAGES["vi"])
            return {
                "filters": filter_json,
                "answer": no_match,
                "citations": [],
                "posts": [],
            }

        # Bước 3: Gọi AI trả lời ngắn gọn có trích dẫn [#id]
        posts_text_list = []
        for p in posts:
            text_snippet = (p.get("summary") or p.get("text") or "")[:400]
            posts_text_list.append(
                f"[#{p['id']}] [{p.get('date', '')}] [{p.get('source', '')} - {p.get('author', '')}]:\n{text_snippet}"
            )
        posts_block = "\n\n".join(posts_text_list)

        lang_name = LANGUAGE_NAMES.get(body.language, "tiếng Việt")
        sys_step3 = (
            "Bạn là trợ lý tổng hợp thông tin từ các bài viết đã lưu trong kho dữ liệu của người dùng. "
            "Nhiệm vụ: Trả lời câu hỏi ngắn gọn, trung thực, chỉ dựa trên các bài viết được cung cấp. "
            "BẮT BUỘC: Mọi khẳng định hoặc chi tiết phải trích dẫn ID bài viết tương ứng dưới dạng [#id], ví dụ: [#142]. "
            f"Viết câu trả lời bằng {lang_name}. "
            "TUYỆT ĐỐI KHÔNG bịa thông tin và KHÔNG trích dẫn bất kỳ ID nào không có trong danh sách được cấp."
        )
        prompt_step3 = (
            f'Câu hỏi của người dùng: "{body.question}"\n\n'
            f"Các bài viết liên quan được cung cấp:\n<posts>\n{posts_block}\n</posts>"
        )

        answer_obj = analyzer.provider.complete_json(sys_step3, prompt_step3, ASK_ANSWER_SCHEMA, effort="low")
        raw_answer = answer_obj.get("answer", "")

        # Xóa mọi id bịa (không có thật trong danh sách posts)
        valid_ids = {p["id"] for p in posts}
        cited_ids = [int(x) for x in re.findall(r"\[#(\d+)\]", raw_answer)]

        def fix_citation(match: re.Match) -> str:
            cid = int(match.group(1))
            return match.group(0) if cid in valid_ids else ""

        clean_answer = re.sub(r"\[#(\d+)\]", fix_citation, raw_answer).strip()
        citations = sorted(list(set(cid for cid in cited_ids if cid in valid_ids)))

        return {
            "filters": filter_json,
            "answer": clean_answer,
            "citations": citations,
            "posts": posts,
        }

    return router
