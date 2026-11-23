"""Chế độ 'Server': lướt ngay trên server bằng cookie người dùng đã lưu, không cần agent trên máy.

Đánh đổi (đã ghi trong README và hiện trên web):
- Cookie được dùng từ IP datacenter, khác IP/trình duyệt quen của tài khoản -> nền tảng có thể bắt xác minh,
  đăng xuất hoặc khóa tài khoản. Khi bị đòi xác minh, lượt dừng và cookie bị đánh dấu hết hiệu lực;
  server không cố vượt qua.
- Server chỉ chạy một trình duyệt mỗi lúc (RAM gói free có hạn); các lượt khác xếp hàng.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Callable, Iterator

from .models import RawPost, RunRequest

# Một Chromium mỗi lúc trên toàn server
SERVER_SLOT = threading.Semaphore(1)
# Không tải ảnh/video/font: nhanh hơn nhiều và đỡ RAM (bài viết chỉ cần chữ)
_BLOCKED_RESOURCES = {"image", "media", "font"}
_HOME = {"facebook": "https://www.facebook.com/", "linkedin": "https://www.linkedin.com/feed/",
         "x": "https://x.com/home", "reddit": "https://www.reddit.com/"}


class CookieInvalid(RuntimeError):
    pass


@contextmanager
def cookie_page(cookies: list[dict]) -> Iterator:
    from playwright.sync_api import sync_playwright

    from .browser import detect_browser

    with sync_playwright() as pw:
        opts = dict(headless=True, args=["--disable-dev-shm-usage", "--disable-gpu", "--mute-audio"])
        selected = detect_browser(playwright=pw)
        browser = pw.chromium.launch(executable_path=selected.executable_path, **opts)
        try:
            ctx = browser.new_context(locale="vi-VN", viewport={"width": 1280, "height": 900})
            ctx.add_cookies(cookies)
            ctx.route("**/*", lambda route: route.abort()
                      if route.request.resource_type in _BLOCKED_RESOURCES else route.continue_())
            page = ctx.new_page()
            page.set_default_timeout(45_000)
            yield page
        finally:
            browser.close()


def scrape_with_cookies(req: RunRequest, cookies: list[dict], seen: set[str],
                        on_progress: Callable[[int, str], None], report: dict | None = None) -> list[RawPost]:
    from .pipeline import collect_all
    from .scrapers import NeedsVerification
    from .source_modes import normalize

    normalize(req)  # Validate before launching a cookie browser too.
    with cookie_page(cookies) as page:
        try:
            return collect_all(page, req, seen, on_progress, interactive=False, report=report)
        except NeedsVerification as e:
            raise CookieInvalid(
                f"{req.platform} yêu cầu đăng nhập/xác minh khi lướt từ server, nên cookie không còn dùng được. "
                "Đăng nhập lại trên máy (feedlens login) rồi gửi cookie mới, hoặc chuyển sang chạy bằng agent."
            ) from e


def check_cookies(platform: str, cookies: list[dict]) -> tuple[bool, str]:
    """Mở trang chủ bằng cookie; ok nếu không bị chuyển sang trang đăng nhập/xác minh."""
    from .cookies import SESSION_COOKIE
    from .scrapers import has_login_form, is_blocked_url

    with SERVER_SLOT, cookie_page(cookies) as page:
        page.goto(_HOME[platform], wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if is_blocked_url(platform, page.url):
            return False, f"Bị chuyển tới {page.url.split('?')[0]}: cookie hết hạn hoặc cần xác minh."
        if has_login_form(page):
            return False, "Trang hiện form đăng nhập: cookie không hợp lệ hoặc đã hết hạn."
        if not any(c["name"] == SESSION_COOKIE[platform] for c in page.context.cookies()):
            return False, "Nền tảng đã xóa cookie phiên: cookie không còn hợp lệ."
        return True, "Đăng nhập được từ server."
