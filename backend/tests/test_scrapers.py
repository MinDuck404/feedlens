from types import SimpleNamespace

import pytest

from feedlens import scrapers
from feedlens.scrapers import FacebookScraper, select_facebook_link


@pytest.mark.parametrize("links,expected", [
    ([("https://www.facebook.com/photo/123/", False), ("https://www.facebook.com/acme/posts/456", False)], "https://www.facebook.com/acme/posts/456"),
    ([("/videos/123/", False), ("/groups/community/posts/456/", False)], "https://www.facebook.com/groups/community/posts/456/"),
    ([("/photo.php?fbid=1", False), ("/permalink/456/", False)], "https://www.facebook.com/permalink/456/"),
    ([("/photo/123/", False), ("/story.php?__tn__=R&story_fbid=456&id=789&__cft__[0]=track", False)], "https://www.facebook.com/story.php?story_fbid=456&id=789"),
    ([("/photo/123/", False), ("/some-post-reference", True)], "https://www.facebook.com/some-post-reference"),
    ([("/photo/123/", True), ("/acme/posts/456", False)], "https://www.facebook.com/acme/posts/456"),
    ([("/shared/posts/1", False), ("/acme/posts/2", True)], "https://www.facebook.com/acme/posts/2"),
    ([("/photo.php?fbid=123&__tn__=R&__cft__=x&fbclid=track", False)], "https://www.facebook.com/photo.php?fbid=123"),
    ([("https://fb.watch/abc/?__tn__=track", False)], "https://fb.watch/abc/"),
    ([("https://example.com/posts/1", False), ("/photos/123/", False)], "https://www.facebook.com/photos/123/"),
    ([("https://facebook.com.evil.example/posts/1", True), ("javascript:alert(1)", True), ("https://[invalid", False)], ""),
    ([("https://www.facebook.com/acme", False)], ""),
    ([], ""),
])
def test_facebook_link_priority_and_tracking(links, expected):
    assert select_facebook_link(links) == expected


def test_collector_applies_facebook_link_selection_before_creating_post(monkeypatch):
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    page = SimpleNamespace(
        goto=lambda *args, **kwargs: None,
        evaluate=lambda script: None if script == scraper.expand_js else [{
            "text": "A community post with a photo and a timestamp.", "author": "Author", "posted_at": "", "url": "",
            "links": [["https://www.facebook.com/photo/1", False], ["https://www.facebook.com/user/posts/2?__tn__=track", True]],
        }],
        mouse=SimpleNamespace(wheel=lambda *args: None),
    )
    posts = scraper.collect(page, "https://www.facebook.com/", "feed", 1, set(), lambda *args: None)
    assert len(posts) == 1
    assert posts[0].url == "https://www.facebook.com/user/posts/2"
