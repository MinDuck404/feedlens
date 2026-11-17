from __future__ import annotations

import threading
import traceback
from typing import Callable

from .ai.registry import preferred_provider, user_key_list
from .analyzer import get_analyzer
from .config import settings
from .db import Database
from .models import RawPost, RunRequest
from .job_profile import load_profile
from .scrapers import SCRAPERS, LinkedInJobsScraper
from .source_modes import normalize, total_target as planned_total_target

# Tiến độ trực tiếp cho UI: run_id -> {"phase", "message", "done", "target"}
PROGRESS: dict[int, dict] = {}
_platform_locks: dict[str, threading.Lock] = {p: threading.Lock() for p in SCRAPERS}


def scrape(req: RunRequest, seen: set[str], on_progress: Callable[[int, str], None],
           report: dict | None = None) -> list[RawPost]:
    """Lướt bằng profile Chrome riêng của FeedLens trên máy này (agent / chế độ local)."""
    from .browser import open_context  # chỉ cần Playwright khi thật sự lướt

    normalize(req, settings.max_posts)  # Reject invalid sources before opening a profile.
    with open_context(req.platform, headless=req.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return collect_all(page, req, seen, on_progress, interactive=not req.headless, report=report)


def collect_all(page, req: RunRequest, seen: set[str], on_progress: Callable[[int, str], None],
                interactive: bool, report: dict | None = None) -> list[RawPost]:
    """Lướt lần lượt mọi nguồn (bảng tin / từng nhóm / từng từ khóa) trên một tab đã mở."""
    from .scrapers import NeedsVerification

    targets = normalize(req, settings.max_posts)
    scraper = LinkedInJobsScraper() if req.platform == "linkedin" and req.mode == "jobs" else SCRAPERS[req.platform]()
    total_cap = total_target(req)
    posts: list[RawPost] = []
    skipped: list[str] = []
    for i, (label, url, chronological, per_target_count) in enumerate(targets):
        remaining = total_cap - len(posts)
        if remaining <= 0:
            break
        quota = min(per_target_count, remaining)
        base = len(posts)
        prefix = f"Nguồn {i + 1}/{len(targets)} · " if len(targets) > 1 else ""
        try:
            try:
                posts += scraper.collect(page, url, label, quota, seen,
                                         lambda n, msg: on_progress(base + n, prefix + msg),
                                         speed=req.speed, interactive=interactive, chronological=chronological,
                                         leading_old_grace=3 if req.platform == "facebook" and req.mode == "page" else 0)
            finally:
                if report is not None and getattr(scraper, "last_report", None):
                    report.setdefault("sources", []).append({"label": label, **scraper.last_report})
                    report.setdefault("missing_link_samples", []).extend(getattr(scraper, "missing_headers", []))
                    samples = report.setdefault("missing_graphql_samples", [])
                    samples.extend(getattr(scraper, "missing_graphql_samples", [])[:max(0, 10 - len(samples))])
        except NeedsVerification:
            raise
        except Exception as e:  # noqa: BLE001 — một nhóm lỗi (link sai, bị chặn) không làm hỏng cả lượt
            if page.is_closed():
                raise RuntimeError("Cửa sổ Chrome đã bị đóng giữa chừng.") from e
            skipped.append(f"{label}: {str(e)[:120]}")
            on_progress(base, f"{prefix}Bỏ qua {label}: {str(e)[:120]}")
    if not posts and skipped:
        raise RuntimeError("Không lướt được nguồn nào. " + " | ".join(skipped))
    return posts


def save_scrape_report(db: Database, run_id: int, req: RunRequest, report: dict) -> None:
    """Keep why scraping stopped next to the run request (JSON, no migration); diagnostics stay local."""
    sources = report.get("sources") or []
    if sources:
        summary = {"target": sum(s.get("target", 0) for s in sources),
                   "collected": sum(s.get("collected", 0) for s in sources),
                   "skipped_old": sum(s.get("skipped_old", 0) for s in sources),
                   "skipped_ads": sum(s.get("skipped_ads", 0) for s in sources),
                   "stop_reason": sources[-1].get("stop_reason") if len(sources) == 1 else None,
                   "sources": sources}
        db.update_run(run_id, request={**req.model_dump(), "scrape_report": summary})
    samples = report.get("missing_link_samples") or []
    if samples:
        try:
            folder = settings.data_dir / "debug" / "missing-links"
            folder.mkdir(parents=True, exist_ok=True)
            body = "\n<hr>\n".join(samples[:10])
            (folder / f"run-{run_id}.html").write_text(
                f"<!-- FeedLens: posts whose permalink was not found (text shortened, tokens removed) -->\n{body}\n",
                encoding="utf-8")
        except OSError:
            pass

    graphql_samples = report.get("missing_graphql_samples") or []
    if graphql_samples:
        import json
        from .scrapers import sanitize_facebook_debug
        try:
            folder = settings.data_dir / "debug" / "missing-links"
            folder.mkdir(parents=True, exist_ok=True)
            safe = [sanitize_facebook_debug(sample) for sample in graphql_samples[:10]]
            (folder / f"run-{run_id}.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


def total_target(req: RunRequest) -> int:
    return planned_total_target(req, settings.max_posts)


def _keys(db: Database, user_id: int | None):
    return user_key_list(db, user_id) if user_id is not None else []


def execute_run(db: Database, run_id: int, req: RunRequest, user_id: int | None = None) -> None:
    """Chế độ local: lướt bằng trình duyệt trên chính máy này rồi phân tích."""
    prog = PROGRESS.setdefault(run_id, {})
    target = total_target(req)

    def report(phase: str):
        def _fn(n: int, msg: str):
            prog.update(phase=phase, done=n, target=target, message=msg)
        return _fn

    lock = _platform_locks[req.platform]  # 1 trình duyệt / profile tại một thời điểm
    try:
        # Kiểm tra AI trước khi lướt, để không lướt xong mới báo thiếu API key
        analyzer = get_analyzer(preferred_provider(db, user_id, req.ai_provider), req.ai_model or None, _keys(db, user_id), user_id or 0)
        db.update_run(run_id, ai_label=analyzer.label)
        with lock:
            db.update_run(run_id, status="scraping")
            seen = db.known_fingerprints(req.platform, user_id) if req.only_new else set()
            scrape_report: dict = {}
            try:
                raw = scrape(req, seen, report("scraping"), scrape_report)
            finally:
                save_scrape_report(db, run_id, req, scrape_report)
        _analyze(db, run_id, req, raw, analyzer, report)
    except Exception as e:  # noqa: BLE001 — lỗi được ghi lại cho UI
        _fail(db, run_id, e)


def _analyze(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], analyzer, report) -> None:
    prog = PROGRESS.setdefault(run_id, {})
    db.save_raw_posts(run_id, raw)
    db.update_run(run_id, status="analyzing", collected=len(raw))
    if not raw:
        raise RuntimeError("Không lấy được bài nào — kiểm tra đăng nhập hoặc selector của nền tảng.")
    if hasattr(analyzer, "notify"):
        analyzer.notify = lambda msg: prog.update(message=msg)
    if hasattr(analyzer, "language"):
        analyzer.language = req.language  # AI viết tóm tắt theo ngôn ngữ giao diện người dùng
    prog.update(phase="analyzing", done=0, target=len(raw), message=f"{analyzer.label} đang đọc {len(raw)} bài…")
    owner = (db.get_run(run_id) or {}).get("user_id")
    if req.job_mode:
        analyzer.job_profile = load_profile(db, owner)
    analyzer.topics = db.list_topics(owner, enabled_only=True) if owner is not None else []
    completed = db.get_posts(run_id)
    known = {p.fingerprint for p in completed}
    pending = [p for p in raw if p.fingerprint not in known]
    analyzer.on_batch = lambda batch: db.save_batch(run_id, batch)
    if pending:
        analyzed = analyzer.classify(pending, req.job_mode, req.keywords, req.profile, report("analyzing"))
        db.save_batch(run_id, analyzed)
    analyzed = db.get_posts(run_id)
    prog.update(phase="summarizing", message="Đang viết tóm tắt…")
    digest = analyzer.digest(analyzed, req.job_mode)
    db.update_run(run_id, status="done", error=None, digest=digest, ai_label=analyzer.label)  # model có thể đã đổi
    prog.update(phase="done", message="Hoàn tất")


def _fail(db: Database, run_id: int, e: Exception) -> None:
    traceback.print_exc()
    fail_run(db, run_id, str(e))


def fail_run(db: Database, run_id: int, message: str) -> None:
    status = "analysis_failed" if db.get_raw_posts(run_id) else "error"
    db.update_run(run_id, status=status, error=message[:2000])
    PROGRESS.setdefault(run_id, {}).update(phase=status, message=message[:300])


def execute_analysis(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], user_id: int | None) -> None:
    """Bài đã được agent trên máy người dùng lướt sẵn; server chỉ phân tích."""
    prog = PROGRESS.setdefault(run_id, {})

    def report(phase: str):
        def _fn(n: int, msg: str):
            prog.update(phase=phase, done=n, target=len(raw), message=msg)
        return _fn

    try:
        if not db.get_raw_posts(run_id):
            if req.only_new:
                known = db.known_fingerprints(req.platform, user_id)
                raw = [p for p in raw if p.fingerprint not in known]
            db.save_raw_posts(run_id, raw)
        analyzer = get_analyzer(preferred_provider(db, user_id, req.ai_provider), req.ai_model or None, _keys(db, user_id), user_id or 0)
        db.update_run(run_id, ai_label=analyzer.label)
        _analyze(db, run_id, req, raw, analyzer, report)
    except Exception as e:  # noqa: BLE001
        _fail(db, run_id, e)


def _spawn(target, run_id: int, *args) -> None:
    PROGRESS[run_id] = {"phase": "queued", "done": 0, "target": 0, "message": "Đang chờ…"}
    threading.Thread(target=target, args=(*args,), daemon=True).start()


def start_run(db: Database, req: RunRequest, user_id: int | None = None) -> int:
    run_id = db.create_run(req, user_id)
    _spawn(execute_run, run_id, db, run_id, req, user_id)
    return run_id


def execute_server_run(db: Database, run_id: int, req: RunRequest, user_id: int) -> None:
    """Chế độ 'Server': lướt trên server bằng cookie đã lưu của user, rồi phân tích."""
    import json

    from .crypto import decrypt
    from .server_runner import SERVER_SLOT, CookieInvalid, scrape_with_cookies

    prog = PROGRESS.setdefault(run_id, {})
    target = total_target(req)

    def report(phase: str):
        def _fn(n: int, msg: str):
            prog.update(phase=phase, done=n, target=target, message=msg)
        return _fn

    try:
        analyzer = get_analyzer(preferred_provider(db, user_id, req.ai_provider), req.ai_model or None, _keys(db, user_id), user_id)
        db.update_run(run_id, ai_label=analyzer.label)
        row = db.get_session(user_id, req.platform)
        cookies = json.loads(decrypt(row.ciphertext) or "null") if row else None
        if not cookies:
            raise RuntimeError(f"Chưa có cookie {req.platform} hợp lệ. Thêm cookie trong Cài đặt → Lướt trên server.")
        if not SERVER_SLOT.acquire(blocking=False):
            prog.update(phase="queued", message="Server đang lướt cho lượt khác, đang xếp hàng…")
            SERVER_SLOT.acquire()
        try:
            db.update_run(run_id, status="scraping")
            prog.update(phase="scraping", done=0, target=target, message="Server đang mở trình duyệt…")
            seen = db.known_fingerprints(req.platform, user_id) if req.only_new else set()
            scrape_report: dict = {}
            try:
                raw = scrape_with_cookies(req, cookies, seen, report("scraping"), scrape_report)
            finally:
                save_scrape_report(db, run_id, req, scrape_report)
        finally:
            SERVER_SLOT.release()
        db.set_session_status(user_id, req.platform, "ok", f"Lướt được {len(raw)} bài từ server.")
        _analyze(db, run_id, req, raw, analyzer, report)
    except CookieInvalid as e:
        db.set_session_status(user_id, req.platform, "invalid", str(e))
        _fail(db, run_id, e)
    except Exception as e:  # noqa: BLE001
        _fail(db, run_id, e)


def start_server_run(db: Database, req: RunRequest, user_id: int) -> int:
    run_id = db.create_run(req, user_id, status="queued")
    _spawn(execute_server_run, run_id, db, run_id, req, user_id)
    return run_id


def start_analysis(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], user_id: int | None) -> None:
    if not db.get_raw_posts(run_id):
        if req.only_new:
            known = db.known_fingerprints(req.platform, user_id)
            raw = [p for p in raw if p.fingerprint not in known]
        db.save_raw_posts(run_id, raw)
    db.update_run(run_id, status="analyzing", collected=len(raw))
    _spawn(execute_analysis, run_id, db, run_id, req, raw, user_id)


def start_ingest(db: Database, req: RunRequest, raw: list[RawPost], user_id: int | None = None) -> int:
    run_id = db.create_run(req, user_id)
    start_analysis(db, run_id, req, raw, user_id)
    return run_id
