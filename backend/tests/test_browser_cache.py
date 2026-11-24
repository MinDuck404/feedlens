from types import SimpleNamespace

from feedlens.browser import profiles as browser


def make_profile(root):
    profile = root / "facebook"
    for rel in ("Default/Cache/Cache_Data", "Default/Code Cache/js", "GrShaderCache", "Default/Local Storage/leveldb"):
        (profile / rel).mkdir(parents=True)
    (profile / "Default/Cache/Cache_Data/data_1").write_bytes(b"x" * 4096)
    (profile / "Default/Code Cache/js/a").write_bytes(b"x" * 2048)
    (profile / "Default/Cookies").write_bytes(b"session")
    (profile / "Default/Local Storage/leveldb/000003.log").write_bytes(b"ls")
    return profile


def test_clean_cache_keeps_login_state(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "settings", SimpleNamespace(profiles_dir=tmp_path))
    profile = make_profile(tmp_path)
    outside = tmp_path / "keep.txt"
    outside.write_text("untouched")

    before, after = browser.clean_cache("facebook")

    assert before > after
    assert not (profile / "Default/Cache").exists()
    assert not (profile / "Default/Code Cache").exists()
    assert not (profile / "GrShaderCache").exists()
    assert (profile / "Default/Cookies").read_bytes() == b"session"
    assert (profile / "Default/Local Storage/leveldb/000003.log").exists()
    assert outside.read_text() == "untouched"


def test_clean_cache_missing_profile_and_locked_files(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "settings", SimpleNamespace(profiles_dir=tmp_path))
    assert browser.clean_cache("reddit") == (0, 0)
    make_profile(tmp_path)

    def locked(*args, **kwargs):
        raise PermissionError("file in use")

    monkeypatch.setattr(browser.shutil, "rmtree", locked)
    browser.clean_cache("facebook")  # must not raise
    assert [r[0] for r in browser.clean_all_caches()] == ["facebook"]
