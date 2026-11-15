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


@pytest.fixture(scope="module")
def facebook_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # Synthetic HTML only: never load Facebook or a saved user profile.
        page.route("**/*", lambda route: route.abort())
        yield page
        browser.close()


@pytest.mark.parametrize("body,expected", [
    ('<a href="/reel/123456/">Watch reel</a>', 'https://www.facebook.com/reel/123456/'),
    ('<a href="/share/p/abc123/">Shared post</a>', 'https://www.facebook.com/share/p/abc123/'),
    ('<a href="/share/1ABCdef/">Shared post</a>', 'https://www.facebook.com/share/1ABCdef/'),
    ('<a href="/share/r/abc123/">Shared reel</a>', 'https://www.facebook.com/share/r/abc123/'),
    ('<a href="/share/v/abc123/">Shared video</a>', 'https://www.facebook.com/share/v/abc123/'),
    ('<span role="link" data-url="/author/posts/pfbidROLE/">2 giờ</span>',
     'https://www.facebook.com/author/posts/pfbidROLE/'),
    ('<a href="/permalink.php?story_fbid=pfbidABC&id=123&amp;__tn__=R"><abbr>1 h</abbr></a>',
     'https://www.facebook.com/permalink.php?story_fbid=pfbidABC&id=123'),
    ('<a href="/groups/community/posts/pfbidABC/">2 h</a>', 'https://www.facebook.com/groups/community/posts/pfbidABC/'),
    ('<a href="/photo/123/">Photo</a><a href="/author/posts/pfbidABC/">Sponsored</a>',
     'https://www.facebook.com/author/posts/pfbidABC/'),
    ('<a href="/shared/posts/456/">Shared article</a><a href="/author/posts/pfbidABC/" aria-label="November 15, 2026">1 h</a>',
     'https://www.facebook.com/author/posts/pfbidABC/'),
    ('<a data-href="https://www.facebook.com/author/posts/pfbidDATA/">1 h</a>',
     'https://www.facebook.com/author/posts/pfbidDATA/'),
])
def test_facebook_html_permalink_variants(facebook_page, body, expected):
    facebook_page.set_content('<div role="feed"><div role="article"><h3>Author</h3>'
        '<div data-ad-preview="message">A long enough post for the feed extractor.</div>' + body + '</div></div>')
    item = facebook_page.evaluate(scrapers.FB_JS)[0]
    assert select_facebook_link(item['links']) == expected


def test_facebook_html_hover_resolves_timestamp_without_navigation(facebook_page, monkeypatch):
    facebook_page.set_content('''<div role="feed"><div role="article"><h3>Author</h3>
      <div data-ad-preview="message">A long enough post with a lazy timestamp permalink.</div>
      <a role="link" aria-label="November 15, 2026" onmouseover="this.href='/author/posts/pfbidHOVER/?__tn__=R'">1 h</a>
      <a href="/photo/456/">Photo</a>
    </div></div>''')
    monkeypatch.setattr(scrapers, '_human_pause', lambda *args: None)
    monkeypatch.setattr(scrapers.random, 'random', lambda: 1)
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, 'ensure_access', lambda *args: False)
    monkeypatch.setattr(facebook_page, 'goto', lambda *args, **kwargs: None)
    posts = scraper.collect(facebook_page, 'https://www.facebook.com/', 'feed', 1, set(), lambda *args: None)
    assert posts[0].url == 'https://www.facebook.com/author/posts/pfbidHOVER/'
    assert facebook_page.url == 'about:blank'


def test_facebook_html_multiple_articles_and_nested_share(facebook_page):
    facebook_page.set_content('''<div role="feed"><div>
      <div role="article"><h3>Outer author</h3><a href="/outer/posts/1/">1 h</a>
        <div data-ad-preview="message">Outer shared post commentary is long enough.</div>
        <div role="article"><a href="/inner/posts/2/">2 h</a>
          <div data-ad-preview="message">Inner shared post content is long enough.</div></div>
      </div>
      <div role="article"><h3>Second author</h3><a href="/second/posts/3/">3 h</a>
        <div data-ad-preview="message">Second independent post content is long enough.</div></div>
    </div></div>''')
    items = scrapers._facebook_items(facebook_page)
    assert len(items) == 2
    assert [p['url'] for p in items] == ['https://www.facebook.com/outer/posts/1/',
                                       'https://www.facebook.com/second/posts/3/']


@pytest.mark.parametrize('href', ['', '#', '#timestamp', '/', '/?__tn__=R'])
def test_facebook_placeholder_is_not_a_permalink(href):
    assert select_facebook_link([(href, True)]) == ''


def test_facebook_collect_backfills_missing_url_on_later_scroll(monkeypatch):
    monkeypatch.setattr(scrapers, '_human_pause', lambda *args: None)
    monkeypatch.setattr(scrapers.random, 'random', lambda: 1)
    original = dict(text='A long enough post with a late permalink.', author='Author', posted_at='')
    rounds = iter([[dict(original, url='')], [dict(original, url='https://www.facebook.com/author/posts/late/')]])
    monkeypatch.setattr(scrapers, '_facebook_items', lambda page: next(rounds, []))
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, 'ensure_access', lambda *args: False)
    page = SimpleNamespace(goto=lambda *args, **kwargs: None, evaluate=lambda *args: None,
                           mouse=SimpleNamespace(wheel=lambda *args: None))
    posts = scraper.collect(page, 'https://www.facebook.com/', 'feed', 2, set(), lambda *args: None)
    assert len(posts) == 1
    assert posts[0].url == 'https://www.facebook.com/author/posts/late/'


def test_facebook_hover_recycled_dom_does_not_attach_another_posts_link(facebook_page):
    facebook_page.set_content('''<div role="feed"><div role="article">
      <div data-ad-preview="message">Original post content that is long enough.</div>
      <a role="link" onmouseover="this.parentElement.querySelector('div').innerText='A different post replaced the original.'; this.href='/other/posts/1/'">1 h</a>
    </div></div>''')
    item = scrapers._facebook_items(facebook_page)[0]
    assert item['url'] == ''


def test_facebook_hover_hidden_timestamp_preserves_media_fallback(facebook_page):
    facebook_page.set_content('''<div role="feed"><div role="article">
      <div data-ad-preview="message">A long enough post with a hidden timestamp.</div>
      <a role="link" style="display:none" data-testid="timestamp">1 h</a>
      <a href="/photo/1/">Photo</a>
    </div></div>''')
    assert scrapers._facebook_items(facebook_page)[0]['url'] == 'https://www.facebook.com/photo/1/'


def test_facebook_standalone_article_without_posinset(facebook_page):
    facebook_page.set_content('''<article role="article"><h3>Author</h3>
      <div data-ad-preview="message">Post outside the old feed wrapper selector.</div>
      <a href="/author/posts/pfbidSTANDALONE/">1 h</a></article>''')
    assert scrapers._facebook_items(facebook_page)[0]['url'] == 'https://www.facebook.com/author/posts/pfbidSTANDALONE/'
