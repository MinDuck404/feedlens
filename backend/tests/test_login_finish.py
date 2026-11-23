import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from feedlens import api, browser
from tests.test_browser_detection import cloud, local_state
from tests.test_browser_login import setup


class RunningBrowser:
    def __init__(self, clock, on_wait=lambda: None, stubborn=False):
        self.clock, self.on_wait, self.stubborn = clock, on_wait, stubborn
        self.terminated = self.killed = False
        self.waits = []

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.killed or (self.terminated and not self.stubborn):
            return 0
        if self.terminated:
            raise subprocess.TimeoutExpired("browser", timeout)
        self.clock[0] += min(timeout, 2)
        self.on_wait()
        if timeout > 5:
            raise AssertionError("Login must not wait for Cmd+Q")
        raise subprocess.TimeoutExpired("browser", timeout)

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def cookie_db(root, rows):
    path = root / "facebook/Default/Network/Cookies"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE cookies (name TEXT, host_key TEXT)")
        conn.executemany("INSERT INTO cookies VALUES (?, ?)", rows)
    return path


def test_cookie_presence_reads_only_a_copy_and_metadata(tmp_path, monkeypatch):
    local_state(monkeypatch, tmp_path)
    path = cookie_db(tmp_path, [("c_user", ".facebook.com")])
    before = path.read_bytes()
    assert browser.profile_has_session_cookie("facebook") is True
    assert path.read_bytes() == before
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM cookies")
        conn.execute("INSERT INTO cookies VALUES ('c_user', 'evilfacebook.com')")
    assert browser.profile_has_session_cookie("facebook") is False
    path.write_bytes(b"not a database")
    assert browser.profile_has_session_cookie("facebook") is None


def test_login_detects_cookie_then_closes_without_waiting_for_app_exit(tmp_path, monkeypatch):
    setup(monkeypatch, tmp_path)
    clock = [0.0]
    created = []
    def add_cookie():
        if not created:
            cookie_db(tmp_path, [("c_user", ".facebook.com")])
            created.append(True)
    proc = RunningBrowser(clock, add_cookie)
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(browser, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda _: None))
    assert browser.interactive_login("facebook", timeout_s=600)
    assert proc.terminated and clock[0] < 20


def test_manual_finish_works_when_cookie_read_fails_and_escalates_to_kill(tmp_path, monkeypatch):
    import threading
    setup(monkeypatch, tmp_path)
    clock = [0.0]
    finish = threading.Event()
    proc = RunningBrowser(clock, lambda: finish.set(), stubborn=True)
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(browser, "profile_has_session_cookie", lambda p: None)
    monkeypatch.setattr(browser, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda _: None))
    assert browser.interactive_login("facebook", finish_event=finish)
    assert proc.terminated and proc.killed


def test_existing_cookie_does_not_close_a_relogin_before_manual_finish(tmp_path, monkeypatch):
    import threading
    setup(monkeypatch, tmp_path)
    cookie_db(tmp_path, [("c_user", ".facebook.com")])
    clock = [0.0]
    finish = threading.Event()
    proc = RunningBrowser(clock, lambda: finish.set() if clock[0] >= 20 else None)
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(browser, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda _: None))
    assert browser.interactive_login("facebook", finish_event=finish)
    assert proc.terminated and clock[0] >= 20


def test_cookie_snapshot_reads_committed_wal_without_modifying_profile(tmp_path, monkeypatch):
    local_state(monkeypatch, tmp_path)
    path = tmp_path / "facebook/Default/Cookies"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE cookies(name TEXT, host_key TEXT)")
        conn.execute("INSERT INTO cookies VALUES ('c_user', '.facebook.com')")
        conn.commit()
        before = path.read_bytes()
        wal = path.with_name("Cookies-wal")
        wal_before = wal.read_bytes()
        assert browser.profile_has_session_cookie("facebook")
        assert path.read_bytes() == before and wal.read_bytes() == wal_before


def test_locked_cookie_file_falls_back_without_touching_it(tmp_path, monkeypatch):
    local_state(monkeypatch, tmp_path)
    path = cookie_db(tmp_path, [("c_user", ".facebook.com")])
    before = path.read_bytes()
    monkeypatch.setattr(browser.shutil, "copyfile", lambda *a, **k: (_ for _ in ()).throw(PermissionError("locked")))
    assert browser.profile_has_session_cookie("facebook") is None
    assert path.read_bytes() == before


def test_browser_error_after_user_login_keeps_the_new_profile(tmp_path, monkeypatch):
    setup(monkeypatch, tmp_path)
    def wait(**kwargs):
        cookie_db(tmp_path, [("c_user", ".facebook.com")])
        return 1
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: SimpleNamespace(wait=wait))
    with pytest.raises(RuntimeError, match="exited with code 1"):
        browser.interactive_login("facebook")
    assert (tmp_path / "facebook/Default/Network/Cookies").is_file()


def test_login_finish_round_trip_closes_process_and_checks_session(cloud, monkeypatch, tmp_path):
    import threading
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    setup(monkeypatch, tmp_path)
    entered, verified = threading.Event(), threading.Event()
    class Process:
        terminated = False
        def wait(self, timeout):
            if self.terminated:
                return 0
            entered.set()
            api._login_finish["facebook"].wait(timeout)
            raise subprocess.TimeoutExpired("browser", timeout)
        def terminate(self):
            self.terminated = True
    proc = Process()
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(browser, "check_session", lambda p: verified.set() or True)
    assert client.post("/api/platforms/facebook/login").status_code == 200
    assert entered.wait(2)
    assert client.post("/api/platforms/facebook/login/finish").status_code == 200
    assert verified.wait(2)
    state = client.get("/api/platforms").json()[0]
    assert state["logged_in"] is True and state["login_state"] == "idle"
    assert proc.terminated


def test_finish_endpoint_signals_active_login_and_keeps_cloud_isolated(cloud, monkeypatch, tmp_path):
    import threading
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    event = threading.Event()
    monkeypatch.setattr(api, "_login_finish", {"facebook": event}, raising=False)
    api._login_state["facebook"] = "waiting"
    response = client.post("/api/platforms/facebook/login/finish")
    assert response.status_code == 200 and event.is_set()
    assert api._session_checks["facebook"] == "checking"
    assert client.post("/api/platforms/x/login/finish").status_code == 409
    client = cloud()
    from tests.test_cloud import _signup
    assert client.post("/api/platforms/facebook/login/finish", headers=_signup(client)).status_code == 409


@pytest.mark.parametrize("pending", [False, True])
def test_manual_playwright_finish_closes_context_and_respects_verification(monkeypatch, pending):
    import threading
    from contextlib import contextmanager
    finish = threading.Event()
    finish.set()
    closed = []
    page = SimpleNamespace(url="https://www.facebook.com/checkpoint/" if pending else "https://www.facebook.com/", goto=lambda *a: None)
    ctx = SimpleNamespace(pages=[page], cookies=lambda: [{"name": "c_user", "domain": ".facebook.com"}])
    @contextmanager
    def context(*a, **k):
        try:
            yield ctx
        finally:
            closed.append(True)
    monkeypatch.setattr(browser, "detect_browser", lambda *a, **k: browser.BrowserInfo("chromium", "fake", True))
    monkeypatch.setattr(browser, "open_context", context)
    assert browser.interactive_login("facebook", finish_event=finish) is (not pending)
    assert closed == [True]


def test_topic_refresh_never_summarizes_unread_placeholders(tmp_path):
    from feedlens.db import Database
    from feedlens.models import AnalyzedPost, PostGroup, PostSource, RawPost, RunRequest
    from feedlens.topics_api import refresh_topic_digests
    db = Database(f"sqlite:///{tmp_path / 'topics.db'}")
    uid = db.local_user_id()
    rid = db.create_run(RunRequest(platform="facebook"), uid)
    raw = [RawPost(platform="facebook", source="feed", text=text) for text in ("Read post", "Unread post")]
    db.save_raw_posts(rid, raw)
    db.save_post_groups(rid, [PostGroup(fingerprint=p.fingerprint, fingerprints=[p.fingerprint], sources=[PostSource(source=p.source)]) for p in raw])
    db.save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), summary="Read", analyzed_by="Fake AI")])
    db.update_run(rid, digest={"overall": "Read", "categories": [], "action_items": []})
    captured = []
    analyzer = SimpleNamespace(topic_digest=lambda posts: captured.extend(posts) or [])
    refresh_topic_digests(db, uid, analyzer, [])
    assert [p.text for p in captured] == ["Read post"]


def test_cli_markdown_exports_only_analyzed_posts(monkeypatch, tmp_path, capsys):
    from feedlens import cli, config, pipeline
    from feedlens.db import Database
    from feedlens.models import AnalyzedPost, PostGroup, PostSource, RawPost
    monkeypatch.setattr(config, "settings", SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'cli.db'}"))
    def interrupted(db, rid, req, uid):
        raw = [RawPost(platform="facebook", source="feed", text=text) for text in ("Read post", "DO NOT EXPORT UNREAD")]
        db.save_raw_posts(rid, raw)
        db.save_post_groups(rid, [PostGroup(fingerprint=p.fingerprint, fingerprints=[p.fingerprint], sources=[PostSource(source=p.source)]) for p in raw])
        db.save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), summary="Read", analyzed_by="Fake AI")])
        db.update_run(rid, status="analysis_failed", error="quota")
    monkeypatch.setattr(pipeline, "execute_run", interrupted)
    cli.main(["run", "facebook", "--ai", "offline"])
    output = capsys.readouterr().out
    assert "Read post" in output and "DO NOT EXPORT UNREAD" not in output
