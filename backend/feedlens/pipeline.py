from __future__ import annotations

import threading
import traceback
from typing import Callable

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

    scraper = SCRAPERS[req.platform]()
    targets = scraper.urls(req.source_type, req.sources)
    target_total = min(req.count, settings.max_posts)
    per_source = max(1, target_total // len(targets))
    posts: list[RawPost] = []
    with open_context(req.platform, headless=req.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for i, (label, url) in enumerate(targets):
            remaining = target_total - len(posts)
            if remaining <= 0:
                break
            quota = remaining if i == len(targets) - 1 else min(per_source, remaining)
            base = len(posts)
            posts += scraper.collect(page, url, label, quota, seen,
                                     lambda n, msg: on_progress(base + n, msg))
    return posts


def execute_run(db: Database, run_id: int, req: RunRequest) -> None:
    prog = PROGRESS.setdefault(run_id, {})
    target = min(req.count, settings.max_posts)

    def report(phase: str):
        def _fn(n: int, msg: str):
            prog.update(phase=phase, done=n, target=target, message=msg)
        return _fn

    lock = _platform_locks[req.platform]  # 1 trình duyệt / profile tại một thời điểm
    try:
        # Kiểm tra AI trước khi lướt, để không lướt xong mới báo thiếu API key
        analyzer = get_analyzer(req.ai_provider, req.ai_model or None)
        db.update_run(run_id, ai_label=analyzer.label)
        with lock:
            db.update_run(run_id, status="scraping")
            seen = db.known_fingerprints(req.platform) if req.only_new else set()
            raw = scrape(req, seen, report("scraping"))
        _analyze(db, run_id, req, raw, analyzer, report)
    except Exception as e:  # noqa: BLE001 — lỗi được ghi lại cho UI
        _fail(db, run_id, e)


def _analyze(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], analyzer, report) -> None:
    prog = PROGRESS.setdefault(run_id, {})
    db.update_run(run_id, status="analyzing", collected=len(raw))
    if not raw:
        raise RuntimeError("Không lấy được bài nào — kiểm tra đăng nhập hoặc selector của nền tảng.")
    analyzed = analyzer.classify(raw, req.job_mode, req.keywords, req.profile, report("analyzing"))
    db.save_posts(run_id, analyzed)
    prog.update(phase="summarizing", message="Đang viết tóm tắt…")
    digest = analyzer.digest(analyzed, req.job_mode)
    db.update_run(run_id, status="done", digest=digest)
    prog.update(phase="done", message="Hoàn tất")


def _fail(db: Database, run_id: int, e: Exception) -> None:
    traceback.print_exc()
    db.update_run(run_id, status="error", error=str(e)[:2000])
    PROGRESS.setdefault(run_id, {}).update(phase="error", message=str(e)[:300])


def execute_ingest(db: Database, run_id: int, req: RunRequest, raw: list[RawPost]) -> None:
    """Chế độ cloud: bài đã được bot ở máy người dùng lướt sẵn, server chỉ phân tích."""
    prog = PROGRESS.setdefault(run_id, {})

    def report(phase: str):
        def _fn(n: int, msg: str):
            prog.update(phase=phase, done=n, target=len(raw), message=msg)
        return _fn

    try:
        analyzer = get_analyzer(req.ai_provider, req.ai_model or None)
        db.update_run(run_id, ai_label=analyzer.label)
        if req.only_new:
            known = db.known_fingerprints(req.platform)
            raw = [p for p in raw if p.fingerprint not in known]
        _analyze(db, run_id, req, raw, analyzer, report)
    except Exception as e:  # noqa: BLE001
        _fail(db, run_id, e)


def _spawn(target, run_id: int, *args) -> None:
    PROGRESS[run_id] = {"phase": "queued", "done": 0, "target": 0, "message": "Đang chờ…"}
    threading.Thread(target=target, args=(*args,), daemon=True).start()


def start_run(db: Database, req: RunRequest) -> int:
    run_id = db.create_run(req)
    _spawn(execute_run, run_id, db, run_id, req)
    return run_id


def start_ingest(db: Database, req: RunRequest, raw: list[RawPost]) -> int:
    run_id = db.create_run(req)
    db.update_run(run_id, collected=len(raw))
    _spawn(execute_ingest, run_id, db, run_id, req, raw)
    return run_id
