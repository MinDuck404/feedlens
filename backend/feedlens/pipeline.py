from __future__ import annotations

import threading
import traceback
from typing import Callable

from .ai import user_keys
from .analyzer import get_analyzer
from .config import settings
from .db import Database
from .models import RawPost, RunRequest
from .scrapers import SCRAPERS

# Tiến độ trực tiếp cho UI: run_id -> {"phase", "message", "done", "target"}
PROGRESS: dict[int, dict] = {}
_platform_locks: dict[str, threading.Lock] = {p: threading.Lock() for p in SCRAPERS}


def scrape(req: RunRequest, seen: set[str], on_progress: Callable[[int, str], None]) -> list[RawPost]:
    from .browser import open_context  # chỉ cần Playwright khi lướt trên máy

    from .scrapers import NeedsVerification

    scraper = SCRAPERS[req.platform]()
    targets = scraper.urls(req.source_type, req.sources)
    total_cap = total_target(req)
    posts: list[RawPost] = []
    skipped: list[str] = []
    with open_context(req.platform, headless=req.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for i, (label, url) in enumerate(targets):
            remaining = total_cap - len(posts)
            if remaining <= 0:
                break
            quota = min(req.count, remaining)  # số bài là "mỗi nguồn"
            base = len(posts)
            prefix = f"Nguồn {i + 1}/{len(targets)} · " if len(targets) > 1 else ""
            try:
                posts += scraper.collect(page, url, label, quota, seen,
                                         lambda n, msg: on_progress(base + n, prefix + msg),
                                         speed=req.speed, interactive=not req.headless)
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


def total_target(req: RunRequest) -> int:
    n = 1 if req.source_type == "feed" else max(1, len(req.sources))
    return min(req.count * n, settings.max_posts)


def _keys(db: Database, user_id: int | None):
    return user_keys(db, user_id) if user_id is not None else {}


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
        analyzer = get_analyzer(req.ai_provider, req.ai_model or None, _keys(db, user_id), user_id or 0)
        db.update_run(run_id, ai_label=analyzer.label)
        with lock:
            db.update_run(run_id, status="scraping")
            seen = db.known_fingerprints(req.platform, user_id) if req.only_new else set()
            raw = scrape(req, seen, report("scraping"))
        _analyze(db, run_id, req, raw, analyzer, report)
    except Exception as e:  # noqa: BLE001 — lỗi được ghi lại cho UI
        _fail(db, run_id, e)


def _analyze(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], analyzer, report) -> None:
    prog = PROGRESS.setdefault(run_id, {})
    db.update_run(run_id, status="analyzing", collected=len(raw))
    if not raw:
        raise RuntimeError("Không lấy được bài nào — kiểm tra đăng nhập hoặc selector của nền tảng.")
    if hasattr(analyzer, "notify"):
        analyzer.notify = lambda msg: prog.update(message=msg)
    prog.update(phase="analyzing", done=0, target=len(raw), message=f"{analyzer.label} đang đọc {len(raw)} bài…")
    analyzed = analyzer.classify(raw, req.job_mode, req.keywords, req.profile, report("analyzing"))
    db.save_posts(run_id, analyzed)
    prog.update(phase="summarizing", message="Đang viết tóm tắt…")
    digest = analyzer.digest(analyzed, req.job_mode)
    db.update_run(run_id, status="done", digest=digest, ai_label=analyzer.label)  # model có thể đã đổi
    prog.update(phase="done", message="Hoàn tất")


def _fail(db: Database, run_id: int, e: Exception) -> None:
    traceback.print_exc()
    fail_run(db, run_id, str(e))


def fail_run(db: Database, run_id: int, message: str) -> None:
    db.update_run(run_id, status="error", error=message[:2000])
    PROGRESS.setdefault(run_id, {}).update(phase="error", message=message[:300])


def execute_analysis(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], user_id: int | None) -> None:
    """Bài đã được agent trên máy người dùng lướt sẵn; server chỉ phân tích."""
    prog = PROGRESS.setdefault(run_id, {})

    def report(phase: str):
        def _fn(n: int, msg: str):
            prog.update(phase=phase, done=n, target=len(raw), message=msg)
        return _fn

    try:
        analyzer = get_analyzer(req.ai_provider, req.ai_model or None, _keys(db, user_id), user_id or 0)
        db.update_run(run_id, ai_label=analyzer.label)
        if req.only_new:
            known = db.known_fingerprints(req.platform, user_id)
            raw = [p for p in raw if p.fingerprint not in known]
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


def start_analysis(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], user_id: int | None) -> None:
    db.update_run(run_id, status="analyzing", collected=len(raw))
    _spawn(execute_analysis, run_id, db, run_id, req, raw, user_id)


def start_ingest(db: Database, req: RunRequest, raw: list[RawPost], user_id: int | None = None) -> int:
    run_id = db.create_run(req, user_id)
    start_analysis(db, run_id, req, raw, user_id)
    return run_id
