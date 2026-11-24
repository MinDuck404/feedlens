"""Trình duyệt dùng profile riêng cho từng nền tảng.

Người dùng tự đăng nhập trong cửa sổ Chrome thật; cookie phiên được lưu trong
`data/profiles/<platform>`. FeedLens không bao giờ nhận hay lưu mật khẩu.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time
from contextlib import closing, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from .config import settings
from feedlens.scrapers.base import is_blocked_url


@dataclass(frozen=True)
class PlatformInfo:
    key: str
    name: str
    login_url: str
    home_url: str
    session_cookie: str  # cookie chứng tỏ đã đăng nhập
    cookie_domain: str


PLATFORMS: dict[str, PlatformInfo] = {
    "facebook": PlatformInfo("facebook", "Facebook", "https://www.facebook.com/login",
                             "https://www.facebook.com/", "c_user", "facebook.com"),
    "linkedin": PlatformInfo("linkedin", "LinkedIn", "https://www.linkedin.com/login",
                             "https://www.linkedin.com/feed/", "li_at", "linkedin.com"),
    "x": PlatformInfo("x", "X (Twitter)", "https://x.com/i/flow/login",
                      "https://x.com/home", "auth_token", "x.com"),
    "reddit": PlatformInfo("reddit", "Reddit", "https://www.reddit.com/login/",
                           "https://www.reddit.com/", "reddit_session", "reddit.com"),
}


class BrowserNotFoundError(RuntimeError):
    def __init__(self, name: str = "Chrome/Edge/Chromium"):
        super().__init__(f"Browser not found: {name}. Install Chrome: https://www.google.com/chrome/; or clear the saved session to use another browser.")


@dataclass(frozen=True)
class BrowserInfo:
    name: str
    executable_path: str
    oauth_limited: bool = False


def _profile_browser(platform: str) -> str | None:
    pdir = profile_dir(platform)
    marker = pdir / ".browser"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()
    # Empty folders left by failed launches contain no session to preserve.
    return "chrome" if pdir.exists() and any(pdir.iterdir()) else None


def detect_browser(platform: str | None = None, *, native_only: bool = False, playwright=None,
                   headless: bool = False, native_paths: dict | None = None) -> BrowserInfo:
    """Choose an installed browser while keeping existing profiles on their original browser."""
    affinity = _profile_browser(platform) if platform else None
    channel = getattr(settings, "browser_channel", "chrome")
    wanted = affinity or (channel if not native_only and channel in {"msedge", "chromium"} else None)
    for name, finder in (("chrome", find_chrome), ("msedge", find_edge)):
        if wanted and wanted != name:
            continue
        path = native_paths.get(name) if native_paths is not None else finder()
        if path:
            return BrowserInfo(name, path)
    if not native_only and wanted in {None, "chromium"}:
        if playwright is None:
            with sync_playwright() as pw:
                return _playwright_browser(pw, headless=headless)
        return _playwright_browser(playwright, headless=headless)
    raise BrowserNotFoundError(wanted or "Chrome/Edge")


def _playwright_browser(pw, *, headless: bool = False) -> BrowserInfo:
    path = pw.chromium.executable_path
    if Path(path).is_file():
        return BrowserInfo("chromium", path, oauth_limited=True)
    if headless:
        # --only-shell installs a sibling of Chromium at the same Playwright revision.
        for parent in Path(path).parents:
            if parent.name.startswith("chromium-"):
                shell = parent.with_name(parent.name.replace("chromium-", "chromium_headless_shell-", 1))
                for candidate in shell.glob("*/*"):
                    if candidate.name in {"chrome-headless-shell", "chrome-headless-shell.exe", "headless_shell", "headless_shell.exe"} and candidate.is_file():
                        return BrowserInfo("chromium", str(candidate), oauth_limited=True)
                break
    raise BrowserNotFoundError()


def browser_status(platform: str | None = None, *, headless: bool = False, playwright=None, native_paths: dict | None = None) -> dict:
    try:
        info = detect_browser(platform, headless=headless, playwright=playwright, native_paths=native_paths)
        return {"browser": info.name, "oauth_limited": info.oauth_limited, "missing": False}
    except BrowserNotFoundError:
        return {"browser": None, "oauth_limited": False, "missing": True}


_STATUS_TTL = 15
_status_cache = None
_status_lock = threading.Lock()


def clear_browser_status_cache() -> None:
    global _status_cache
    with _status_lock:
        _status_cache = None


def browser_statuses() -> dict[str, dict]:
    """Share discovery across all account rows and polling requests; manual actions refresh it."""
    global _status_cache
    affinities = tuple(_profile_browser(p) for p in PLATFORMS)
    channel = getattr(settings, "browser_channel", "chrome")
    key = (str(settings.profiles_dir), channel, affinities,
           *(os.getenv(k) for k in ("FEEDLENS_CHROME_PATH", "PLAYWRIGHT_BROWSERS_PATH", "PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")))
    with _status_lock:
        if _status_cache and _status_cache[0] == key and time.monotonic() < _status_cache[1]:
            return _status_cache[2]
        native = {"chrome": find_chrome(), "msedge": find_edge()}
        needs_playwright = not any(native.values()) or channel == "chromium" or "chromium" in affinities
        with sync_playwright() if needs_playwright else nullcontext(None) as pw:
            statuses = {p: browser_status(p, playwright=pw, native_paths=native) for p in PLATFORMS}
        _status_cache = (key, time.monotonic() + _STATUS_TTL, statuses)
        return statuses


def warn_if_no_native_browser() -> None:
    try:
        detect_browser(native_only=True)
    except BrowserNotFoundError:
        print("Warning: Chrome/Edge not found. Install Chrome: https://www.google.com/chrome/. FeedLens will still start; Playwright Chromium has limited Google/Apple login support.")
        print("Chưa tìm thấy Chrome/Edge. Bạn vẫn có thể mở FeedLens; tải Chrome tại https://www.google.com/chrome/ để đăng nhập.")


def _remember_browser(pdir: Path, info: BrowserInfo) -> None:
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / ".browser").write_text(info.name, encoding="utf-8")


def _discard_failed_profile(pdir: Path, existed: bool) -> None:
    if not existed and _is_inside(settings.profiles_dir.resolve(), pdir.resolve()):
        shutil.rmtree(pdir, ignore_errors=True)


def profile_dir(platform: str) -> Path:
    return settings.profiles_dir / platform


# Giới hạn dung lượng cache trên đĩa của Chrome (64MB). Chrome ghi cache ảnh/video/JS vào
# Default/Cache và phình mãi; cờ này chặn nó ở mức nhỏ.
DISK_CACHE_BYTES = 64 * 1024 * 1024

# Thư mục cache có thể tạo lại được. TUYỆT ĐỐI không đụng Cookies, Local Storage, IndexedDB,
# Session Storage, Login Data, Preferences, Network, Service Worker — chúng giữ phiên đăng nhập.
CACHE_DIRS: tuple[str, ...] = (
    "Default/Cache",
    "Default/Code Cache",
    "Default/GPUCache",
    "Default/DawnWebGPUCache",
    "Default/DawnGraphiteCache",
    "GrShaderCache",
    "ShaderCache",
    "GraphiteDawnCache",
)


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:  # file bị Chrome khoá / vừa bị xoá
                continue
    return total


def profile_size(platform: str) -> int:
    return _dir_size(profile_dir(platform))


def _is_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def clean_cache(platform: str) -> tuple[int, int]:
    """Xoá cache trong profile của một nền tảng, giữ nguyên phiên đăng nhập.

    Trả về (dung lượng trước, dung lượng sau) tính bằng byte.
    """
    pdir = profile_dir(platform)
    before = _dir_size(pdir)
    if not pdir.exists():
        return 0, 0
    base = pdir.resolve()
    for rel in CACHE_DIRS:
        target = (pdir / rel).resolve()
        # Chỉ xoá thư mục nằm trong profile (chặn symlink trỏ ra ngoài)
        if target == base or not _is_inside(base, target):
            continue
        try:
            shutil.rmtree(target, ignore_errors=True)
        except OSError:
            pass  # Chrome còn khoá file trên Windows: bỏ qua, không làm lỗi lượt lướt
    return before, _dir_size(pdir)


def clean_all_caches() -> list[tuple[str, int, int]]:
    """Dọn cache cho mọi profile đang có. Trả về [(platform, trước, sau)]."""
    results = []
    for platform in PLATFORMS:
        if not profile_dir(platform).exists():
            continue
        before, after = clean_cache(platform)
        results.append((platform, before, after))
    return results


@contextmanager
def open_context(platform: str, headless: bool = True) -> Iterator[BrowserContext]:
    pdir = profile_dir(platform)
    existed = pdir.exists()
    with sync_playwright() as pw:
        selected = detect_browser(platform, playwright=pw, headless=headless)
        kwargs = dict(
            user_data_dir=str(pdir),
            headless=headless,
            viewport=None if not headless else {"width": 1280, "height": 900},
            locale="vi-VN",
            chromium_sandbox=True,  # giữ sandbox của Chrome (Playwright mặc định thêm --no-sandbox)
            args=[f"--disk-cache-size={DISK_CACHE_BYTES}"],
            timeout=20_000,
        )
        try:
            ctx = pw.chromium.launch_persistent_context(executable_path=selected.executable_path, **kwargs)
        except Exception:
            _discard_failed_profile(pdir, existed)
            raise
        try:
            _remember_browser(pdir, selected)
            yield ctx
        finally:
            try:
                ctx.close()
            finally:
                # Dọn cache sau khi đóng Chrome: giữ profile nhỏ, giữ nguyên phiên đăng nhập.
                # Không bao giờ để việc dọn cache làm hỏng lượt lướt.
                try:
                    clean_cache(platform)
                except Exception:  # noqa: BLE001
                    pass


def _has_session(ctx: BrowserContext, info: PlatformInfo) -> bool:
    return any(c["name"] == info.session_cookie and info.cookie_domain in c["domain"]
               for c in ctx.cookies())


def _verification_pending(ctx: BrowserContext, platform: str) -> bool:
    """Còn tab nào đang ở trang đăng nhập / xác minh 2 bước / checkpoint không."""
    return any(is_blocked_url(platform, p.url) for p in ctx.pages)


def find_chrome() -> str | None:
    """Đường dẫn Chrome cài trên máy (FEEDLENS_CHROME_PATH ghi đè), hoặc None."""
    override = os.getenv("FEEDLENS_CHROME_PATH")
    if override and Path(override).is_file():
        return override
    if sys.platform == "win32":
        roots = [os.getenv(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [Path(r) / "Google/Chrome/Application/chrome.exe" for r in roots if r]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                      Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        candidates = [Path(p) for p in map(shutil.which, ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")) if p]
    return next((str(p) for p in candidates if p.is_file()), None)


def find_edge() -> str | None:
    if sys.platform == "win32":
        roots = [os.getenv(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [Path(r) / "Microsoft/Edge/Application/msedge.exe" for r in roots if r]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                      Path.home() / "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    else:
        candidates = [Path(p) for p in map(shutil.which, ("microsoft-edge", "microsoft-edge-stable", "msedge")) if p]
    return next((str(p) for p in candidates if p.is_file()), None)


def profile_has_session_cookie(platform: str) -> bool | None:
    """Read name/domain metadata from a temporary SQLite copy, never cookie values."""
    info = PLATFORMS[platform]
    pdir = profile_dir(platform) / "Default"
    try:
        source = next((path for path in (pdir / "Network/Cookies", pdir / "Cookies") if path.is_file()), None)
        if source is None:
            return False
        with tempfile.TemporaryDirectory(prefix="feedlens-cookie-check-") as temporary:
            snapshot = Path(temporary) / "Cookies"
            shutil.copyfile(source, snapshot)
            wal = source.with_name(source.name + "-wal")
            if wal.is_file():
                shutil.copyfile(wal, snapshot.with_name(snapshot.name + "-wal"))
            with closing(sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True, timeout=0.1)) as conn:
                return conn.execute("SELECT 1 FROM cookies WHERE name = ? AND (host_key = ? OR host_key LIKE ?) LIMIT 1",
                                    (info.session_cookie, info.cookie_domain, "%." + info.cookie_domain)).fetchone() is not None
    except (OSError, sqlite3.Error):
        return None


def _stop_login_process(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)


def interactive_login(platform: str, timeout_s: int = 600,
                      on_window_closed: Callable[[], None] | None = None,
                      finish_event: threading.Event | None = None) -> bool:
    """Cho người dùng tự đăng nhập vào profile của FeedLens.

    Ưu tiên mở Chrome của máy như một cửa sổ bình thường, KHÔNG gắn Playwright: Google, Apple,
    Microsoft từ chối "Đăng nhập bằng ..." trong trình duyệt đang bị điều khiển tự động.
    Cookie mới ổn định hoặc tín hiệu kết thúc sẽ đóng cửa sổ; sau đó vẫn kiểm tra phiên trực tiếp.
    Chrome và Edge dùng cửa sổ thường; Chromium Playwright có giới hạn OAuth.
    Trình duyệt được ghi lại theo profile để không trộn cookie giữa các ứng dụng."""
    selected = detect_browser(platform)
    if selected.oauth_limited:
        return (_playwright_login(platform, timeout_s, finish_event=finish_event) if finish_event is not None
                else _playwright_login(platform, timeout_s))
    pdir = profile_dir(platform)
    # An old cookie must not close the window before the user can renew an expired session.
    auto_finish = profile_has_session_cookie(platform) is False
    pdir.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen([
            selected.executable_path, f"--user-data-dir={pdir}", "--no-first-run", "--no-default-browser-check",
            f"--disk-cache-size={DISK_CACHE_BYTES}", "--new-window", PLATFORMS[platform].login_url,
        ])
    except FileNotFoundError as e:
        raise BrowserNotFoundError(selected.name) from e
    _remember_browser(pdir, selected)
    deadline = time.monotonic() + timeout_s
    cookie_since = None
    while True:
        now = time.monotonic()
        if (finish_event is not None and finish_event.is_set()) or now >= deadline:
            _stop_login_process(proc)
            break
        if auto_finish:
            present = profile_has_session_cookie(platform)
            if present is None:
                auto_finish = False  # Locked/unknown schema: keep the window until manual finish or exit.
            elif present:
                cookie_since = now if cookie_since is None else cookie_since
                if now - cookie_since >= 6:
                    _stop_login_process(proc)
                    break
            else:
                cookie_since = None
        try:
            result = proc.wait(timeout=min(2, max(0.01, deadline - now)))
        except subprocess.TimeoutExpired:
            continue
        if result:
            # The window may already contain a user's new session; preserve it on process errors.
            raise RuntimeError(f"{selected.name} exited with code {result}")
        break
    if on_window_closed:
        on_window_closed()  # để giao diện báo "Đang kiểm tra…" thay vì vẫn "Đăng nhập trong cửa sổ…"
    try:
        clean_cache(platform)
    except Exception:  # noqa: BLE001
        pass
    ok = check_session(platform)
    for _ in range(2):  # None = chưa mở được profile (Chrome chưa kịp nhả khoá): thử lại
        if ok is not None:
            break
        time.sleep(2)
        ok = check_session(platform)
    return bool(ok)


def _playwright_login(platform: str, timeout_s: int = 600,
                      finish_event: threading.Event | None = None) -> bool:
    """Mở cửa sổ Chrome để người dùng tự đăng nhập (và tự hoàn tất xác minh 2 bước nếu có).

    Chỉ coi là xong khi đã có cookie phiên VÀ không còn tab nào ở trang xác minh: Facebook đặt
    cookie c_user ngay trước bước 2FA, nên chỉ nhìn cookie sẽ đóng cửa sổ quá sớm."""
    info = PLATFORMS[platform]
    with open_context(platform, headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(info.home_url if _has_session(ctx, info) else info.login_url)
        deadline = time.time() + timeout_s
        stable = 0
        while time.time() < deadline:
            if finish_event is not None and finish_event.is_set():
                break
            if not ctx.pages:  # người dùng đóng cửa sổ
                break
            if _has_session(ctx, info) and not _verification_pending(ctx, platform):
                stable += 1
                if stable >= 3:  # ổn định ~3 giây, tránh bắt nhầm lúc đang chuyển trang
                    return True
            else:
                stable = 0
            time.sleep(1)
        return _has_session(ctx, info) and not (ctx.pages and _verification_pending(ctx, platform))


def check_session(platform: str) -> bool | None:
    info = PLATFORMS[platform]
    if not profile_dir(platform).exists():
        return False
    try:
        with open_context(platform, headless=True) as ctx:
            if not _has_session(ctx, info):
                return False
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(info.home_url, wait_until="domcontentloaded", timeout=15_000)
            return _has_session(ctx, info) and not _verification_pending(ctx, platform)
    except Exception:
        return None


def logout(platform: str) -> None:
    shutil.rmtree(profile_dir(platform), ignore_errors=True)
