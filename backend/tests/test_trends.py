
import feedlens.routes.dependencies as dependencies
from datetime import datetime, timedelta, timezone

from feedlens import api
from feedlens.models import AnalyzedPost, RunRequest
from tests.test_cloud import _signup, cloud  # noqa: F401 — fixture


def test_trends_user_isolation(cloud):
    client = cloud()
    a, b = _signup(client, "user-a@example.test"), _signup(client, "user-b@example.test")
    db = dependencies.db()
    user_a = db.get_user_by_email("user-a@example.test")
    user_b = db.get_user_by_email("user-b@example.test")

    today = datetime.now(timezone.utc).date().isoformat()
    run_a = db.create_run(RunRequest(platform="facebook"), user_a.id, status="done")
    db.save_batch(run_a, [
        AnalyzedPost(platform="facebook", source="feed", text="React 19 tips", summary="React 19",
                     category="tech", posted_at=f"{today}T10:00:00Z"),
        AnalyzedPost(platform="facebook", source="feed", text="Tuyển dev", summary="Tuyển dev",
                     category="job", posted_at=f"{today}T11:00:00Z"),
    ])

    # User B should see 0 posts
    r_b = client.get("/api/trends?group=category&days=7", headers=b)
    assert r_b.status_code == 200
    data_b = r_b.json()
    assert data_b["summary"]["total_posts"] == 0
    assert all(s["total"] == 0 for s in data_b["series"])

    # User A sees 2 posts
    r_a = client.get("/api/trends?group=category&days=7", headers=a)
    assert r_a.status_code == 200
    data_a = r_a.json()
    assert data_a["summary"]["total_posts"] == 2
    by_cat = {s["id"]: s["total"] for s in data_a["series"]}
    assert by_cat["tech"] == 1
    assert by_cat["job"] == 1


def test_trends_day_and_week_bucketing(cloud):
    client = cloud()
    h = _signup(client, "buckets@example.test")
    db = dependencies.db()
    user = db.get_user_by_email("buckets@example.test")

    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [
        AnalyzedPost(platform="facebook", source="feed", text="P1", summary="P1", category="tech",
                     posted_at=f"{today.isoformat()}T08:00:00Z"),
        AnalyzedPost(platform="facebook", source="feed", text="P2", summary="P2", category="tech",
                     posted_at=f"{yesterday.isoformat()}T10:00:00Z"),
        AnalyzedPost(platform="facebook", source="feed", text="P3", summary="P3", category="news",
                     posted_at=f"{two_days_ago.isoformat()}T12:00:00Z"),
    ])

    # Test day bucketing for 7 days
    r_day = client.get("/api/trends?group=category&bucket=day&days=7", headers=h)
    assert r_day.status_code == 200
    d_day = r_day.json()
    assert len(d_day["timeline"]) == 7
    assert d_day["timeline"][-1] == today.isoformat()
    assert d_day["summary"]["total_posts"] == 3

    # Check that tech has 1 on today and 1 on yesterday
    tech_series = next(s for s in d_day["series"] if s["id"] == "tech")
    today_idx = d_day["timeline"].index(today.isoformat())
    yest_idx = d_day["timeline"].index(yesterday.isoformat())
    assert tech_series["counts"][today_idx] == 1
    assert tech_series["counts"][yest_idx] == 1

    # Test week bucketing for 30 days
    r_week = client.get("/api/trends?group=category&bucket=week&days=30", headers=h)
    assert r_week.status_code == 200
    d_week = r_week.json()
    assert len(d_week["timeline"]) >= 4
    # All 3 posts should be counted in week buckets
    total_week_posts = sum(s["total"] for s in d_week["series"])
    assert total_week_posts == 3


def test_trends_group_topics(cloud):
    client = cloud()
    h = _signup(client, "topics-trend@example.test")
    db = dependencies.db()
    user = db.get_user_by_email("topics-trend@example.test")

    # Create 2 topics
    t1 = client.post("/api/topics", headers=h, json={"name": "AI Models", "color": "red"}).json()
    t2 = client.post("/api/topics", headers=h, json={"name": "Rust Dev", "color": "teal"}).json()

    today = datetime.now(timezone.utc).date().isoformat()
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [
        AnalyzedPost(platform="facebook", source="feed", text="Claude 3.7", summary="Claude",
                     category="tech", topic_ids=[t1["id"]], posted_at=f"{today}T08:00:00Z"),
        AnalyzedPost(platform="facebook", source="feed", text="Rust tips", summary="Rust",
                     category="tech", topic_ids=[t2["id"]], posted_at=f"{today}T09:00:00Z"),
        AnalyzedPost(platform="facebook", source="feed", text="AI + Rust", summary="Both",
                     category="tech", topic_ids=[t1["id"], t2["id"]], posted_at=f"{today}T10:00:00Z"),
        AnalyzedPost(platform="facebook", source="feed", text="No topic", summary="None",
                     category="tech", topic_ids=[], posted_at=f"{today}T11:00:00Z"),
    ])

    r = client.get("/api/trends?group=topic&bucket=day&days=7", headers=h)
    assert r.status_code == 200
    data = r.json()
    by_topic = {s["name"]: s["total"] for s in data["series"]}
    # t1 (AI Models) matched in 2 posts
    assert by_topic["AI Models"] == 2
    # t2 (Rust Dev) matched in 2 posts
    assert by_topic["Rust Dev"] == 2
    assert data["series"][0]["color"].startswith("#")


def test_trends_date_fallback(cloud):
    client = cloud()
    h = _signup(client, "fallback@example.test")
    db = dependencies.db()
    user = db.get_user_by_email("fallback@example.test")

    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    # Post with empty posted_at and post with unparseable posted_at
    db.save_batch(run, [
        AnalyzedPost(platform="facebook", source="feed", text="Empty date", summary="S1",
                     category="job", posted_at=""),
        AnalyzedPost(platform="facebook", source="feed", text="Bad date", summary="S2",
                     category="job", posted_at="không rõ ngày đăng"),
        AnalyzedPost(platform="facebook", source="feed", text="Good date", summary="S3",
                     category="job", posted_at=f"{datetime.now(timezone.utc).date().isoformat()}T12:00:00Z"),
    ])

    r = client.get("/api/trends?group=category&days=7", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total_posts"] == 3
    # 2 posts fell back to run created_at
    assert data["fallback_count"] == 2


def test_week_buckets_obey_exact_date_window(cloud, monkeypatch):
    from feedlens.routes import trends as trends_api
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(trends_api, "datetime", Clock)
    client = cloud()
    headers = _signup(client, "exact-window@example.test")
    db = dependencies.db()
    user = db.get_user_by_email("exact-window@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text=f"p-{day}", category="tech", posted_at=f"2026-11-{day:02}T10:00:00Z") for day in [15, 16, 17]])
    data = client.get("/api/trends?bucket=week&days=1", headers=headers).json()
    assert data["summary"]["total_posts"] == 1
    assert data["range"]["start_date"] == "2026-11-16"
    assert data["range"]["end_date"] == "2026-11-16"


def test_growth_compares_equal_previous_period_and_zero_is_not_percent(cloud, monkeypatch):
    from feedlens.routes import trends as trends_api
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(trends_api, "datetime", Clock)
    client = cloud()
    headers = _signup(client, "growth@example.test")
    db = dependencies.db()
    user = db.get_user_by_email("growth@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text=f"stable-{day}", category="tech", posted_at=f"2026-11-{day:02}") for day in range(3, 17)] + [
        AnalyzedPost(platform="facebook", source="feed", text="new-topic", category="news", posted_at="2026-11-16"),
    ])
    for bucket in ["day", "week"]:
        data = client.get(f"/api/trends?days=7&bucket={bucket}", headers=headers).json()
        series = {item["id"]: item for item in data["series"]}
        assert series["tech"]["growth"] == 0
        assert series["tech"]["previous_total"] == 7
        assert series["news"]["growth"] is None
        assert series["news"]["is_new"] is True
        assert data["summary"]["top_gainer"] is None
        assert data["summary"]["new_emerging"]["id"] == "news"


def test_dates_normalize_utc_and_reject_invalid_suffix():
    from feedlens.routes.trends import parse_post_date
    fallback = datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert parse_post_date("2026-11-15T00:30:00+07:00", fallback) == ((fallback - timedelta(days=1)).date(), False)
    assert parse_post_date("2026-11-14 garbage", fallback) == (fallback.date(), True)


def test_growth_uses_real_positive_baseline_and_ignores_other_users_topic(cloud):
    client = cloud()
    headers = _signup(client, "positive-growth@example.test")
    other = _signup(client, "other-topic@example.test")
    topic = client.post("/api/topics", headers=headers, json={"name": "Mine"}).json()
    foreign = client.post("/api/topics", headers=other, json={"name": "Foreign"}).json()
    db = dependencies.db(); user = db.get_user_by_email("positive-growth@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    today = datetime.now(timezone.utc).date()
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", category="tech", text=f"growth-{i}", posted_at=(today - timedelta(days=8 if i == 0 else 0)).isoformat(), topic_ids=[topic["id"], foreign["id"]]) for i in range(3)])
    data = client.get("/api/trends?days=7&group=topic", headers=headers).json()
    assert len(data["series"]) == 1
    assert data["series"][0]["growth"] == 100
    assert data["summary"]["top_gainer"]["id"] == str(topic["id"])
    assert data["summary"]["new_emerging"] is None
