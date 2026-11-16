"""Trình duyệt dùng profile riêng cho từng nền tảng.

Người dùng tự đăng nhập trong cửa sổ Chrome thật; cookie phiên được lưu trong
`data/profiles/<platform>`. FeedLens không bao giờ nhận hay lưu mật khẩu.
"""
from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from .config import settings
from .scrapers import is_blocked_url


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
    pdir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        kwargs = dict(
            user_data_dir=str(pdir),
            headless=headless,
            viewport=None if not headless else {"width": 1280, "height": 900},
            locale="vi-VN",
            chromium_sandbox=True,  # giữ sandbox của Chrome (Playwright mặc định thêm --no-sandbox)
            args=[f"--disk-cache-size={DISK_CACHE_BYTES}"],
            timeout=20_000,
        )
        channel = settings.browser_channel
        try:
            ctx = pw.chromium.launch_persistent_context(
                channel=None if channel == "chromium" else channel, **kwargs)
        except Exception:
            # Fallback sang Chromium của Playwright (cần `playwright install chromium`)
            ctx = pw.chromium.launch_persistent_context(**kwargs)
        try:
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


def interactive_login(platform: str, timeout_s: int = 600) -> bool:
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
