from __future__ import annotations

import time
import threading
import traceback
from contextvars import ContextVar
from typing import Callable

from .ai.registry import preferred_provider, user_key_list
from .analyzer import HeuristicAnalyzer, get_analyzer
from .config import settings
from .db import Database
from .models import RawPost, RunRequest
from .job_profile import load_profile
from .scrapers import SCRAPERS, LinkedInJobsScraper
from .source_modes import allocate_targets, normalize, total_target as planned_total_target

# Tiến độ trực tiếp cho UI: run_id -> {"phase", "message", "done", "target"}
PROGRESS: dict[int, dict] = {}
_platform_locks: dict[str, threading.Lock] = {p: threading.Lock() for p in SCRAPERS}
_REPORT_FLUSH: ContextVar[Callable[[dict], None] | None] = ContextVar("_report_flush", default=None)


def scrape(req: RunRequest, seen: set[str], on_progress: Callable[[int, str], None],
           report: dict | None = None) -> list[RawPost]:
    """Lướt bằng profile Chrome riêng của FeedLens trên máy này (agent / chế độ local)."""
    from .browser import open_context  # chỉ cần Playwright khi thật sự lướt

    normalize(req, run_cap(req))  # Reject invalid sources before opening a profile.
    with open_context(req.platform, headless=req.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return collect_all(page, req, seen, on_progress, interactive=not req.headless, report=report)


def collect_all(page, req: RunRequest, seen: set[str], on_progress: Callable[[int, str], None],
                interactive: bool, report: dict | None = None,
                on_report: Callable[[dict], None] | None = None) -> list[RawPost]:
    """Lướt lần lượt mọi nguồn (bảng tin / từng nhóm / từng từ khóa) trên một tab đã mở."""
    from .scrapers import NeedsVerification

    targets = normalize(req, run_cap(req))
    scraper = LinkedInJobsScraper() if req.platform == "linkedin" and req.mode == "jobs" else SCRAPERS[req.platform]()
    total_cap = total_target(req)
    flush = on_report or _REPORT_FLUSH.get()
    if report is not None:
        report["sources"] = [
            {
                "label": t.label,
                "target": t.per_target_count,
                "collected": 0,
                "skipped_old": 0,
                "skipped_dup": 0,
                "skipped_ads": 0,
                "examined": 0,
                "stop_reason": None,
                "status": "pending",
            }
            for t in targets
        ]
    posts: list[RawPost] = []
    skipped: list[str] = []
    history = frozenset(seen)
    for i, (label, url, chronological, per_target_count) in enumerate(targets):
        remaining = total_cap - len(posts)
        if remaining <= 0:
            break
        # Chia lại phần còn lại cho các nguồn chưa lướt: nhóm trước hết bài mới sớm (caught_up)
        # thì phần dư chuyển sang nhóm sau, thay vì bỏ phí (lượt 15: 370/500 dù còn nhóm có bài mới).
        requested = [t._replace(per_target_count=req.count) for t in targets[i:]]
        quota = min(allocate_targets(requested, remaining)[0].per_target_count, remaining)
        base = len(posts)
        prefix = f"Nguồn {i + 1}/{len(targets)} · " if len(targets) > 1 else ""
        if report is not None:
            report["sources"][i].update(target=quota, stop_reason=None, status="running")
            if flush:
                flush(report)
        last_flushed = 0

        def group_progress(n: int, msg: str) -> None:
            nonlocal last_flushed
            on_progress(base + n, prefix + msg)
            if report is not None:
                last = getattr(scraper, "last_report", None)
                if last:
                    report["sources"][i] = {"label": label, **last, "stop_reason": None, "status": "running"}
                    cur = int(last.get("collected", 0))
                    if flush and cur - last_flushed >= 10:
                        last_flushed = cur
                        flush(report)

        try:
            try:
                posts += scraper.collect(page, url, label, quota, seen,
                                         group_progress,
                                         speed=req.speed, interactive=interactive, chronological=chronological,
                                         leading_old_grace=3 if req.platform == "facebook" and req.mode == "page" else 0,
                                         report=report,
                                         old_streak_limit=getattr(req.options, "old_streak", 8), history=history)
            finally:
                if report is not None:
                    last = getattr(scraper, "last_report", None)
                    if last:
                        report["sources"][i] = {"label": label, **last, "status": "done"}
                        report.setdefault("missing_link_samples", []).extend(getattr(scraper, "missing_headers", []))
                        samples = report.setdefault("missing_graphql_samples", [])
                        samples.extend(getattr(scraper, "missing_graphql_samples", [])[:max(0, 10 - len(samples))])
                    else:
                        report["sources"][i] = {**report["sources"][i], "status": "done"}
                    if flush:
                        flush(report)
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


def add_timings(db: Database, run_id: int, **seconds: float) -> None:
    """Cộng dồn số giây vào request.scrape_report.timings (Phân tích tiếp cộng thêm, không ghi đè khoá khác)."""
    run = db.get_run(run_id)
    if not run:
        return
    request = dict(run.get("request") or {})
    report = dict(request.get("scrape_report") or {})
    timings = dict(report.get("timings") or {})
    for key, value in seconds.items():
        timings[key] = round(timings.get(key, 0) + value, 3)
    db.update_run(run_id, request={**request, "scrape_report": {**report, "timings": timings}})


def save_scrape_report(db: Database, run_id: int, req: RunRequest, report: dict) -> None:
    """Keep why scraping stopped next to the run request (JSON, no migration); diagnostics stay local."""
    sources = report.get("sources") or []
    if sources:
        summary = {"target": min(sum(s.get("target", 0) for s in sources), total_target(req)),
                   "collected": sum(s.get("collected", 0) for s in sources),
                   "skipped_old": sum(s.get("skipped_old", 0) for s in sources),
                   "skipped_ads": sum(s.get("skipped_ads", 0) for s in sources),
                   "stop_reason": sources[-1].get("stop_reason") if len(sources) == 1 else None,
                    "sources": [dict(s) for s in sources]}
        if any("skipped_dup" in s for s in sources):
            summary["skipped_dup"] = sum(s.get("skipped_dup", 0) for s in sources)
    else:
        summary = {}
    # Số đo thời gian (giây) và số bài lấy được toàn văn từ Story: scrapers.py ghi, pipeline thêm scrape_total.
    if report.get("timings"):
        summary["timings"] = dict(report["timings"])
    if "full_text_from_story" in report:
        summary["full_text_from_story"] = report["full_text_from_story"]
    if "from_story" in report:
        summary["from_story"] = report["from_story"]
    if summary:
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


def run_cap(req: RunRequest) -> int:
    """Trần bài của lượt: lựa chọn trong Cài đặt (500/1000/2000), không có thì dùng FEEDLENS_MAX_POSTS."""
    return req.max_posts or getattr(settings, "max_posts", 500)


def total_target(req: RunRequest) -> int:
    return planned_total_target(req, run_cap(req))


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
            started = time.monotonic()
            flush_token = _REPORT_FLUSH.set(lambda r: save_scrape_report(db, run_id, req, r))
            try:
                raw = scrape(req, seen, report("scraping"), scrape_report)
            finally:
                _REPORT_FLUSH.reset(flush_token)
                scrape_report.setdefault("timings", {})["scrape_total"] = round(time.monotonic() - started, 3)
                save_scrape_report(db, run_id, req, scrape_report)
        _analyze(db, run_id, req, raw, analyzer, report)
    except Exception as e:  # noqa: BLE001 — lỗi được ghi lại cho UI
        _fail(db, run_id, e)


def _analyze(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], analyzer, report,
             reanalyze_all: bool = False) -> None:
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
    needs_ai = analyzer.label != HeuristicAnalyzer.label
    completed = [] if reanalyze_all else [p for p in db.get_posts(run_id)
                                         if not needs_ai or p.analyzed_by not in {"", "offline"}]
    known = {p.fingerprint for p in completed}
    pending = [p for p in raw if p.fingerprint not in known]
    analyzer.on_batch = lambda batch: db.save_batch(run_id, batch)
    if pending:
        started = time.monotonic()
        try:
            analyzed = analyzer.classify(pending, req.job_mode, req.keywords, req.profile, report("analyzing"))
            returned = {post.fingerprint for post in analyzed}
            if any(post.fingerprint not in returned for post in pending):
                raise RuntimeError("AI chưa đọc hết các bài đã lưu. Bấm gửi tiếp để chỉ gửi những bài AI chưa đọc.")
            db.save_batch(run_id, analyzed)
        finally:  # lượt hết hạn mức giữa chừng vẫn ghi thời gian AI đã chạy
            add_timings(db, run_id, analysis=time.monotonic() - started)
    analyzed = db.get_posts(run_id)
    prog.update(phase="summarizing", message="Đang viết tóm tắt…")
    started = time.monotonic()
    digest = analyzer.digest(analyzed, req.job_mode)
    add_timings(db, run_id, summary=time.monotonic() - started)
    request = db.get_run(run_id)["request"]
    db.update_run(run_id, status="done", error=None, digest=digest,
                  request={**request, "analysis_used_ai": needs_ai})
    prog.update(phase="done", message="Hoàn tất")


def _fail(db: Database, run_id: int, e: Exception) -> None:
    traceback.print_exc()
    fail_run(db, run_id, str(e))


def fail_run(db: Database, run_id: int, message: str) -> None:
    status = "analysis_failed" if db.get_raw_posts(run_id) else "error"
    db.update_run(run_id, status=status, error=message[:2000])
    PROGRESS.setdefault(run_id, {}).update(phase=status, message=message[:300])


def execute_analysis(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], user_id: int | None,
                     reanalyze_all: bool = False) -> None:
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
        _analyze(db, run_id, req, raw, analyzer, report, reanalyze_all=reanalyze_all)
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
            started = time.monotonic()
            flush_token = _REPORT_FLUSH.set(lambda r: save_scrape_report(db, run_id, req, r))
            try:
                raw = scrape_with_cookies(req, cookies, seen, report("scraping"), scrape_report)
            finally:
                _REPORT_FLUSH.reset(flush_token)
                scrape_report.setdefault("timings", {})["scrape_total"] = round(time.monotonic() - started, 3)
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


def start_analysis(db: Database, run_id: int, req: RunRequest, raw: list[RawPost], user_id: int | None,
                   reanalyze_all: bool = False) -> None:
    if not db.get_raw_posts(run_id):
        if req.only_new:
            known = db.known_fingerprints(req.platform, user_id)
            raw = [p for p in raw if p.fingerprint not in known]
        db.save_raw_posts(run_id, raw)
    db.update_run(run_id, status="analyzing", collected=len(raw))
    _spawn(execute_analysis, run_id, db, run_id, req, raw, user_id, reanalyze_all)


def start_ingest(db: Database, req: RunRequest, raw: list[RawPost], user_id: int | None = None) -> int:
    run_id = db.create_run(req, user_id)
    start_analysis(db, run_id, req, raw, user_id)
    return run_id
