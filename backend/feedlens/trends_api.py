"""/api/trends: gom số liệu xu hướng bài viết theo danh mục hoặc chủ đề người dùng."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from .auth import CurrentUser, current_user
from .db.tables import PostRow, RunRow
from .models import CATEGORIES

TOPIC_PALETTE: dict[str, str] = {
    "red": "#AE3824",
    "navy": "#2B5C8F",
    "amber": "#8C5A24",
    "teal": "#28666E",
    "purple": "#6B4D82",
    "rose": "#A04462",
    "slate": "#54626F",
    "brown": "#70665C",
    "emerald": "#2D6A4F",
    "indigo": "#3F4E8C",
    "coral": "#C8553D",
    "olive": "#58641D",
    "cyan": "#1D6F8A",
    "wine": "#7A2038",
    "ochre": "#996B1F",
    "rust": "#9E4324",
}

CATEGORY_COLORS: dict[str, str] = {
    "job": "#AE3824",
    "tech": "#2B5C8F",
    "news": "#8C5A24",
    "question": "#28666E",
    "marketplace": "#6B4D82",
    "event": "#A04462",
    "personal": "#54626F",
    "entertainment": "#70665C",
    "promotion": "#8A7F73",
    "other": "#9E9488",
}


def parse_post_date(posted_at: str | None, run_created_at: Any) -> tuple[date, bool]:
    """Use UTC calendar dates; unreadable social timestamps fall back to the run date."""
    if posted_at:
        try:
            parsed = datetime.fromisoformat(posted_at.strip().replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.date(), False
        except (ValueError, TypeError):
            pass
    if isinstance(run_created_at, date):
        return date(run_created_at.year, run_created_at.month, run_created_at.day), True
    return datetime.now(timezone.utc).date(), True


def trends_router(db):
    router = APIRouter(prefix="/api/trends")

    @router.get("")
    def get_trends(
        group: Literal["category", "topic"] = Query("category"),
        bucket: Literal["day", "week"] = Query("day"),
        days: int = Query(30, ge=1, le=365),
        user: CurrentUser = Depends(current_user),
    ):
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days - 1)
        previous_start = start - timedelta(days=days)
        step = timedelta(days=7 if bucket == "week" else 1)
        first_bucket = start - timedelta(days=start.weekday()) if bucket == "week" else start
        timeline = []
        cursor = first_bucket
        while cursor <= today:
            timeline.append(cursor.isoformat())
            cursor += step
        bucket_index = {key: index for index, key in enumerate(timeline)}
        if group == "category":
            series = [{"id": key, "name": label, "color": CATEGORY_COLORS[key]} for key, label in CATEGORIES.items()]
        else:
            series = [{"id": str(topic.id), "name": topic.name, "color": TOPIC_PALETTE.get(topic.color, TOPIC_PALETTE["red"])}
                      for topic in db().list_topics(user.id)]
        by_id = {item["id"]: item for item in series}
        for item in series:
            item.update(counts=[0] * len(timeline), total=0, previous_total=0)
        total_posts = fallback_count = 0
        query = (select(PostRow.category, PostRow.topic_ids, PostRow.posted_at, RunRow.created_at)
                 .join(RunRow, PostRow.run_id == RunRow.id).where(RunRow.user_id == user.id)
                 .execution_options(yield_per=1000))
        # shortcut: free-form social timestamps require scanning metadata; normalize/index dates when history queries become slow.
        with db().Session() as session:
            for row in session.execute(query):
                posted, fallback = parse_post_date(row.posted_at, row.created_at)
                if not previous_start <= posted <= today:
                    continue
                current = posted >= start
                if current:
                    total_posts += 1
                    fallback_count += int(fallback)
                if group == "category":
                    ids = [row.category if row.category in by_id else "other"]
                else:
                    ids = {str(value) for value in (row.topic_ids or [])} & by_id.keys()
                for key in ids:
                    item = by_id[key]
                    if current:
                        period = posted - timedelta(days=posted.weekday()) if bucket == "week" else posted
                        item["counts"][bucket_index[period.isoformat()]] += 1
                        item["total"] += 1
                    else:
                        item["previous_total"] += 1
        for item in series:
            current, previous = item["total"], item["previous_total"]
            item["is_new"] = previous == 0 and current > 0
            item["growth"] = round((current - previous) / previous * 100, 1) if previous else (None if current else 0)
        gainers = [item for item in series if item["growth"] is not None and item["growth"] > 0]
        new = [item for item in series if item["is_new"]]
        top = max(gainers, key=lambda item: (item["growth"], item["total"], item["id"]), default=None)
        emerging = max(new, key=lambda item: (item["total"], item["id"]), default=None)
        series.sort(key=lambda item: (-item["total"], item["id"]))
        return {
            "range": {"group": group, "bucket": bucket, "days": days, "start_date": start.isoformat(), "end_date": today.isoformat(),
                      "previous_start_date": previous_start.isoformat(), "previous_end_date": (start - timedelta(days=1)).isoformat()},
            "timeline": timeline, "series": series,
            "summary": {"total_posts": total_posts,
                        "top_gainer": {key: top[key] for key in ("id", "name", "growth")} if top else None,
                        "new_emerging": {"id": emerging["id"], "name": emerging["name"], "count": emerging["total"]} if emerging else None},
            "fallback_count": fallback_count,
        }

    return router
