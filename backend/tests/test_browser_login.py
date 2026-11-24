"""Đăng nhập bằng Chrome thường (không gắn Playwright), để Google/Apple không chặn đăng nhập."""
import subprocess
from types import SimpleNamespace

from feedlens.browser import profiles as browser


class FakeProc:
    def __init__(self, args, wait_raises=False):
        self.args = args
        self.wait_raises = wait_raises
        self.terminated = False

    def wait(self, timeout=None):
        if self.wait_raises and not self.terminated:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return 0

    def terminate(self):
        self.terminated = True


def setup(monkeypatch, tmp_path, *, chrome="C:/Chrome/chrome.exe", channel="chrome", session=True, wait_raises=False):
    monkeypatch.setattr(browser, "settings", SimpleNamespace(profiles_dir=tmp_path, browser_channel=channel))
    monkeypatch.setattr(browser, "find_chrome", lambda: chrome)
    monkeypatch.setattr(browser, "find_edge", lambda: None)
    if chrome is None or channel == "chromium":
        from contextlib import contextmanager
        executable = tmp_path / "bundled-chromium"
        executable.touch()

        @contextmanager
        def playwright():
            yield SimpleNamespace(chromium=SimpleNamespace(executable_path=str(executable)))

        monkeypatch.setattr(browser, "sync_playwright", playwright)
    monkeypatch.setattr(browser, "check_session", lambda platform: session)
    monkeypatch.setattr(browser, "clean_cache", lambda platform: (0, 0))
    launched = []

    def popen(args, **kwargs):
        proc = FakeProc(args, wait_raises)
        launched.append(proc)
        return proc

    monkeypatch.setattr(browser.subprocess, "Popen", popen)
    return launched


def test_login_opens_plain_chrome_with_feedlens_profile(tmp_path, monkeypatch):
    launched = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "_playwright_login", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no playwright")))

    assert browser.interactive_login("linkedin") is True

    args = launched[0].args
    assert args[0] == "C:/Chrome/chrome.exe"
    assert f"--user-data-dir={tmp_path / 'linkedin'}" in args
    assert args[-1] == "https://www.linkedin.com/login"
    assert not any("remote-debugging" in a or "enable-automation" in a for a in args)


def test_login_reports_missing_session_after_window_closes(tmp_path, monkeypatch):
    setup(monkeypatch, tmp_path, session=False)
    assert browser.interactive_login("facebook") is False


def test_login_timeout_closes_chrome_then_checks_session(tmp_path, monkeypatch):
    launched = setup(monkeypatch, tmp_path, wait_raises=True)
    assert browser.interactive_login("x", timeout_s=1) is True
    assert launched[0].terminated


def test_login_falls_back_to_playwright_without_chrome(tmp_path, monkeypatch):
    launched = setup(monkeypatch, tmp_path, chrome=None)
    monkeypatch.setattr(browser, "_playwright_login", lambda platform, timeout_s: "playwright")
    assert browser.interactive_login("reddit") == "playwright"
    assert launched == []


def test_login_uses_playwright_when_channel_is_not_chrome(tmp_path, monkeypatch):
    # Profile do Chromium của Playwright tạo ra không dùng chung được với Chrome của máy.
    launched = setup(monkeypatch, tmp_path, channel="chromium")
    monkeypatch.setattr(browser, "_playwright_login", lambda platform, timeout_s: "playwright")
    assert browser.interactive_login("reddit") == "playwright"
    assert launched == []


def test_login_signals_window_closed_before_checking(tmp_path, monkeypatch):
    setup(monkeypatch, tmp_path)
    events = []
    monkeypatch.setattr(browser, "check_session", lambda platform: events.append("check") or True)
    assert browser.interactive_login("linkedin", on_window_closed=lambda: events.append("closed")) is True
    assert events == ["closed", "check"]


def test_login_retries_session_check_while_profile_is_busy(tmp_path, monkeypatch):
    setup(monkeypatch, tmp_path)
    monkeypatch.setattr(browser.time, "sleep", lambda s: None)
    results = iter([None, None, True])
    monkeypatch.setattr(browser, "check_session", lambda platform: next(results))
    assert browser.interactive_login("linkedin") is True


def test_find_chrome_prefers_env_override(tmp_path, monkeypatch):
    exe = tmp_path / "chrome.exe"
    exe.write_text("")
    monkeypatch.setenv("FEEDLENS_CHROME_PATH", str(exe))
    assert browser.find_chrome() == str(exe)
    monkeypatch.setenv("FEEDLENS_CHROME_PATH", str(tmp_path / "missing.exe"))
    assert browser.find_chrome() != str(tmp_path / "missing.exe")
