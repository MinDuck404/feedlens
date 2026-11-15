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
        evaluate=lambda script, *args: None if script == scraper.expand_js or args or "scroll" in script else [{
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



def fake_collect(monkeypatch, rounds, seen=(), target=2, url="https://www.facebook.com/"):
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    batches = iter(rounds)
    monkeypatch.setattr(scrapers, "_facebook_items", lambda page: next(batches, []))
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    page = SimpleNamespace(goto=lambda *args, **kwargs: None, evaluate=lambda *args: None,
                           mouse=SimpleNamespace(wheel=lambda *args: None))
    progress=[]
    posts=scraper.collect(page, url, "feed", target, set(seen), lambda n,msg:progress.append((n,msg)))
    return posts, scraper, progress


def item(text):
    return dict(text=text, author="Author", posted_at="", url="")


def fingerprint(text):
    return scrapers.RawPost(platform="facebook", source="feed", text=text).fingerprint


def test_old_posts_are_not_a_stuck_feed(monkeypatch):
    old=[item(f"Old feed post number {i}") for i in range(7)]
    posts,scraper,_=fake_collect(monkeypatch, [[p] for p in old]+[[item("New feed post one"),item("New feed post two")]],
        seen=[fingerprint(p['text']) for p in old])
    assert len(posts)==2
    assert scraper.last_report['skipped_old']==7
    assert scraper.last_report['stop_reason']=='target_reached'


def test_total_examined_budget_bounds_nonchronological_feed(monkeypatch):
    old=[item(f"Old feed post number {i}") for i in range(30)]
    posts,scraper,_=fake_collect(monkeypatch, [[p] for p in old],seen=[fingerprint(p['text']) for p in old])
    assert posts==[]
    assert scraper.last_report['stop_reason']=='budget_exhausted'
    assert scraper.last_report['examined']==max(4*2,20)


def test_chronological_group_catches_up_after_eight_distinct_old_posts(monkeypatch):
    old=[item(f"Old group post number {i}") for i in range(12)]
    _,scraper,_=fake_collect(monkeypatch, [[p] for p in old],seen=[fingerprint(p['text']) for p in old],
        target=20,url="https://www.facebook.com/groups/demo/?sorting_setting=CHRONOLOGICAL")
    assert scraper.last_report['skipped_old']==8
    assert scraper.last_report['stop_reason']=='caught_up'


def test_facebook_sponsored_post_is_flagged_without_wasting_snapshot_quota(facebook_page):
    facebook_page.set_content('''<div role="feed"><div role="article"><h3><a href="/elevenlabs">ElevenLabs</a></h3>
      <a href="#"><span>Được tài trợ</span></a>
      <div data-ad-preview="message">Now available in Claude, ChatGPT, Cursor and more tools today.</div>
      <a href="/elevenlabs?__cft__[0]=SECRETTOKEN&amp;__tn__=R"><img src="x.png"></a></div></div>''')
    item = scrapers._facebook_items(facebook_page)[0]
    assert item["sponsored"] is True
    assert "_missing_header" not in item  # Ads do not consume the diagnostic sample quota.


def test_facebook_regular_post_with_permalink_has_no_snapshot(facebook_page):
    facebook_page.set_content('''<div role="feed"><div role="article"><h3>Author</h3>
      <div data-ad-preview="message">A normal post that has a real permalink.</div>
      <a href="/author/posts/pfbidOK/">2 h</a></div></div>''')
    item = scrapers._facebook_items(facebook_page)[0]
    assert item["sponsored"] is False and "_missing_header" not in item


def test_collect_all_records_report_per_source(monkeypatch):
    from feedlens import pipeline
    from feedlens.models import RunRequest

    class Fake:
        def urls(self, source_type, sources):
            return [("Feed", "https://www.facebook.com/")]

        def collect(self, page, url, label, quota, seen, progress, speed, interactive):
            self.last_report = dict(target=quota, collected=1, skipped_old=3, examined=4, stop_reason="no_more_posts")
            self.missing_headers = ["<div>x</div>"]
            return [scrapers.RawPost(platform="facebook", source=label, text="Some new post body text")]

    monkeypatch.setitem(pipeline.SCRAPERS, "facebook", Fake)
    report: dict = {}
    pipeline.collect_all(None, RunRequest(platform="facebook", count=5), set(), lambda *a: None, False, report)
    assert report["sources"][0]["skipped_old"] == 3 and report["missing_link_samples"] == ["<div>x</div>"]


def test_facebook_query_only_timestamp_is_hovered_and_scroll_is_restored(facebook_page):
    # Shape seen in a real feed sample: obfuscated timestamp with aria-labelledby and href="?__cft__…".
    facebook_page.set_content('''<div style="height:3000px"></div><div role="feed"><div role="article"><h3><a href="/page">Page</a></h3>
      <a aria-labelledby="_r_v_" href="?__cft__[0]=TOKEN&amp;__tn__=R" role="link"
         onmouseover="this.href='/page/posts/pfbidREAL/?__cft__[0]=TOKEN'"><span id="_r_v_">x</span></a>
      <div data-ad-preview="message">A page post whose timestamp only resolves on hover.</div>
      <a href="/photo/?fbid=1&amp;set=a.2" role="link"><img src="x.png"></a></div></div>''')
    facebook_page.evaluate("() => window.scrollTo(0, 0)")
    item = scrapers._facebook_items(facebook_page)[0]
    assert item["url"] == "https://www.facebook.com/page/posts/pfbidREAL/"
    assert "_missing_header" not in item
    assert facebook_page.evaluate("() => window.scrollY") == 0


@pytest.mark.parametrize("href", ["/ads/about/?id=123", "https://l.facebook.com/l.php?u=https%3A%2F%2Fexample.test", "/page/posts/123?ad_id=777"])
def test_facebook_ad_or_redirect_is_never_a_post_link(href):
    assert select_facebook_link([(href,True)]) == ""


def test_ads_do_not_count_towards_quota_or_known_posts(monkeypatch):
    batches=[[dict(item('Advertisement number one'),sponsored=True),
              dict(item('Advertisement number two'),url='https://www.facebook.com/ads/about/')],
             [item('First organic post body'),item('Second organic post body')]]
    posts,scraper,progress=fake_collect(monkeypatch,batches,target=2)
    assert [p.text for p in posts]==['First organic post body','Second organic post body']
    assert scraper.last_report['skipped_ads']==2
    assert scraper.last_report['stop_reason']=='target_reached'


@pytest.mark.parametrize("body,expected", [
    ('<h3><a href="/groups/demo/">Group</a></h3><a href="/photo/?fbid=999&amp;set=gm.12345">Photo</a>',
     'https://www.facebook.com/groups/demo/posts/12345/'),
    ('<h3><a href="/author.page">Page</a></h3><a href="/photo/?fbid=999&amp;set=pcb.12345">Photo</a>',
     'https://www.facebook.com/author.page/posts/12345/'),
    ('<h3><a href="/groups/demo/">Group</a></h3><a aria-labelledby="time" href="/groups/demo/?multi_permalinks=12345&amp;hoisted_section_header_type=recently_seen">x</a>',
     'https://www.facebook.com/groups/demo/posts/12345/'),
])
def test_facebook_real_header_shapes_recover_post_not_photo(facebook_page,body,expected):
    facebook_page.set_content('<div role="feed"><div role="article">'+body+
        '<div data-ad-preview="message">An organic article body with enough text.</div></div></div>')
    assert scrapers._facebook_items(facebook_page)[0]['url']==expected


def test_facebook_graphql_story_recovers_post_url_from_feedback():
    import base64
    story={'__typename':'Story','message':{'text':'A story body from a network response.'},
           'actors':[{'id':'1234','name':'Author'}],
           'feedback':{'id':base64.b64encode(b'feedback:9876543210').decode()}}
    records=scrapers.facebook_stories({'data':{'node':story}})
    assert len(records)==1
    assert records[0]['url']=='https://www.facebook.com/1234/posts/9876543210/'
    assert records[0]['text']==story['message']['text']


@pytest.mark.parametrize('marker', ['<a href="/ads/about/">x</a>',
    '<a href="/page/posts/1?ad_id=777">x</a>', '<span>Sponsored</span>', '<span>赞助内容</span>'])
def test_ads_are_detected_anywhere_in_the_article(facebook_page,marker):
    facebook_page.set_content('<div role="article"><h3>Advertiser</h3>'+('<span>x</span>'*65)+marker+
        '<div data-ad-preview="message">An advertisement body with enough text.</div></div>')
    assert scrapers._facebook_items(facebook_page)[0]['sponsored'] is True


def test_media_album_and_photo_ids_are_not_guessed_as_post_ids():
    link='https://www.facebook.com/photo/?fbid=999&set=a.12345'
    assert scrapers.facebook_dom_permalink([(link,False)],'/author')==link
    link='https://www.facebook.com/photo/?fbid=999&set=gm.12345'
    assert scrapers.facebook_dom_permalink([(link,False)])==link  # No group identity available.


def test_ads_are_counted_once_even_when_repeated_and_never_become_known(monkeypatch):
    ad=dict(item('Repeated sponsored post body'),sponsored=True)
    posts,scraper,_=fake_collect(monkeypatch,[[ad.copy(),ad.copy()],[ad.copy(),item('Organic post after advertisement')]],target=1)
    assert len(posts)==1 and not posts[0].sponsored
    assert scraper.last_report['skipped_ads']==1 and scraper.last_report['skipped_old']==0


def test_graphql_cache_accepts_ndjson_but_ignores_media_and_comment_ids():
    import json,base64
    story={'__typename':'Story','post_id':'pfbidABC123','message':{'text':'A story with a group destination.'},
           'to':{'__typename':'Group','id':'555'},'actors':[{'id':'123','name':'Author'}],'creation_time':1794760000}
    invalid={'__typename':'Story','message':{'text':'No post identity can be inferred safely.'},
             'feedback':{'id':base64.b64encode(b'comment:9876543210').decode()},
             'attachments':[{'media':{'__typename':'Photo','id':'444','url':'https://www.facebook.com/photo/?fbid=444'}}]}
    cache={};scrapers.cache_facebook_stories('for (;;);'+json.dumps({'data':story})+'\ninvalid JSON\n'+json.dumps(invalid),cache)
    assert len(cache)==2
    record=cache[fingerprint(story['message']['text'])]
    assert record['url']=='https://www.facebook.com/groups/555/posts/pfbidABC123/'
    assert record['posted_at'].endswith('+00:00')
    assert cache[fingerprint(invalid['message']['text'])]['url']==''
    for payload in [{'__typename':'Story','comet_sections':{'content':['invalid']}}, {'__typename':'Story','message':5}, []]:
        scrapers.cache_facebook_stories(json.dumps(payload),cache)


@pytest.mark.parametrize('url,status', [('https://facebook.com.evil.test/api/graphql/',200),
                                      ('https://www.facebook.com/api/other/',200),
                                      ('https://www.facebook.com/api/graphql/',500)])
def test_graphql_listener_ignores_non_feed_responses(url,status):
    cache={}
    scrapers.capture_facebook_response(SimpleNamespace(url=url,status=status,text=lambda: (_ for _ in ()).throw(AssertionError('must not read body'))),cache)
    assert cache=={}


def test_graphql_listener_enriches_dom_and_is_removed_after_collection(monkeypatch):
    import json
    organic=dict(item('Organic post with missing DOM link.'),_missing_header='<div>unresolved DOM header</div>')
    ad=item('Obfuscated sponsored post body.')
    payload={'data':{'nodes':[{'__typename':'Story','message':{'text':p['text']},'post_id':str(i+100),
        'actors':[{'id':'123','name':'Author'}], 'sponsored_data':{'ad_id':'777'} if p is ad else None} for i,p in enumerate([ad,organic])]}}
    callbacks={}
    page=SimpleNamespace(on=lambda event,fn:callbacks.update({event:fn}),
        remove_listener=lambda event,fn:callbacks.pop(event),
        goto=lambda *a,**k:callbacks['response'](SimpleNamespace(url='https://www.facebook.com/api/graphql/',status=200,text=lambda:json.dumps(payload))),
        evaluate=lambda *a:[],mouse=SimpleNamespace(wheel=lambda *a:None))
    monkeypatch.setattr(scrapers,'_human_pause',lambda *a:None)
    monkeypatch.setattr(scrapers,'_facebook_items',lambda page:[ad.copy(),organic.copy()])
    scraper=FacebookScraper();monkeypatch.setattr(scraper,'ensure_access',lambda *a:False)
    posts=scraper.collect(page,'https://www.facebook.com/','feed',1,set(),lambda *a:None)
    assert len(posts)==1 and posts[0].url=='https://www.facebook.com/123/posts/101/'
    assert scraper.last_report['skipped_ads']==1 and callbacks=={}
    assert scraper.missing_headers==[]


def test_graphql_listener_cleanup_on_navigation_failure(monkeypatch):
    callbacks={}
    page=SimpleNamespace(on=lambda event,fn:callbacks.update({event:fn}),remove_listener=lambda event,fn:callbacks.pop(event),
        goto=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Navigation failed')))
    with pytest.raises(RuntimeError,match='Navigation failed'):
        FacebookScraper().collect(page,'https://www.facebook.com/','feed',1,set(),lambda *a:None)
    assert callbacks=={}


def test_network_match_accepts_a_unique_long_excerpt_but_rejects_ambiguity():
    import json
    prefix='This is a sufficiently long introduction to an organic community post with meaningful details. '
    cache={}
    def story(suffix,id):
        return {'__typename':'Story','message':{'text':prefix+suffix},'url':f'https://www.facebook.com/page/posts/{id}/'}
    scrapers.cache_facebook_stories(json.dumps(story('The rest of the full article.',123)),cache)
    post=scrapers.RawPost(platform='facebook',source='feed',text=prefix+'… Xem thêm')
    assert scrapers.match_facebook_story(post,cache)['url'].endswith('/posts/123/')
    scrapers.cache_facebook_stories(json.dumps(story('Another article with the same introduction.',456)),cache)
    assert scrapers.match_facebook_story(post,cache) is None
    short=scrapers.RawPost(platform='facebook',source='feed',text='This is a short excerpt')
    assert scrapers.match_facebook_story(short,cache) is None


def test_group_pcb_photo_uses_the_group_header_not_a_photo_id(facebook_page):
    facebook_page.set_content('<div role="feed"><div><h3><a href="/groups/demo/">Group</a></h3>'
        '<div data-ad-preview="message">Group photo post with a pcb parent story identifier.</div>'
        '<a href="/photo/?fbid=999&amp;set=pcb.12345">Photo</a></div></div>')
    assert scrapers._facebook_items(facebook_page)[0]['url']=='https://www.facebook.com/groups/demo/posts/12345/'


def test_initial_json_enriches_a_visible_post_without_extra_requests(facebook_page,monkeypatch):
    import json
    text='Visible organic post whose header contains no permalink anchor.'
    payload={'data':{'node':{'__typename':'Story','post_id':'pfbidINITIAL','actors':[{'id':'123','name':'Author'}],
        'comet_sections':{'content':{'story':{'message':{'text':text}}}}}}}
    facebook_page.set_content('<script type="application/json" data-sjs>'+json.dumps(payload)+'</script>'
        '<div role="feed"><div><h3>Author</h3><div data-ad-preview="message">'+text+'</div></div></div>')
    monkeypatch.setattr(scrapers,'_human_pause',lambda *a:None)
    monkeypatch.setattr(facebook_page,'goto',lambda *a,**k:None)
    scraper=FacebookScraper();monkeypatch.setattr(scraper,'ensure_access',lambda *a:False)
    posts=scraper.collect(facebook_page,'https://www.facebook.com/','feed',1,set(),lambda *a:None)
    assert posts[0].url=='https://www.facebook.com/123/posts/pfbidINITIAL/'
    assert scraper.missing_headers==[]


def test_malformed_author_url_does_not_break_photo_fallback():
    url='https://www.facebook.com/photo/?fbid=999&set=pcb.12345'
    assert scrapers.facebook_dom_permalink([(url,False)],'https://[invalid')==url


@pytest.mark.parametrize('raw,expected', [
 ('Hiệp Đông Anh - Tin nhanh hóng hớt\xa0Tài khoản đã xác minh\xa0 · Theo dõi','Hiệp Đông Anh - Tin nhanh hóng hớt'),
 ('Example\xa0Verified account · Follow','Example'),
 ('张三 已验证账户 · 关注','张三'),
 ('ÆRJUN ÆRJUN và SUMANTA DAS','ÆRJUN ÆRJUN và SUMANTA DAS'),
 ('Follow Your Dreams','Follow Your Dreams'),
 ('A\n và B\xa0 · Theo dõi','A và B'),
])
def test_facebook_author_removes_ui_badges_but_preserves_collaborators(raw,expected):
    assert scrapers.clean_facebook_author(raw)==expected


def test_snapshot_keeps_late_permalink_and_referenced_ids_without_tokens(facebook_page):
    facebook_page.set_content('<div role="article"><h4><a href="/page">Suggested page</a> · Theo dõi</h4>'
      '<a href="?__cft__[0]=SECRET" aria-labelledby="time-ref">x</a><span id="time-ref">1 ngày trước</span>'
      '<div data-ad-preview="message">A sufficiently long article body for snapshot testing.</div>'
      + ('<div><span>Facebook</span></div>'*500)
      + '<a id="late-link" href="/page/posts/pfbidLATE/?access_token=SECRET&amp;cookie=PRIVATE&amp;story_fbid=pfbidLATE">Open post</a></div>')
    snapshot=facebook_page.locator('[role=article]').evaluate(scrapers.FB_HEADER_SNAPSHOT_JS)
    assert 'pfbidLATE' in snapshot and 'late-link' in snapshot and 'time-ref' in snapshot
    assert 'SECRET' not in snapshot and 'PRIVATE' not in snapshot
    assert snapshot.endswith('</section>')


def test_suggested_page_header_keeps_coauthor_name_and_unknown_link_empty(facebook_page):
    facebook_page.set_content('<div role="article"><h4><a href="/page-a">A và B</a>'
      '<span>Tài khoản đã xác minh</span> · Theo dõi</h4>'
      '<a role="link" aria-labelledby="time">x</a><span id="time">1 ngày trước</span>'
      '<div data-ad-preview="message">A visible post without a trustworthy story identifier.</div></div>')
    item=scrapers._facebook_items(facebook_page)[0]
    assert item['author']=='A và B' and item['url']==''
    assert 'time' in item['_missing_header']


def test_run8_long_obfuscated_timestamp_uses_referenced_date_and_hover(facebook_page):
    facebook_page.set_content('<div role="feed"><div><h4><a href="/profile.php?id=123">Suggested page</a> · Theo dõi</h4>'
      '<a role="link" aria-labelledby="date-ref" href="?__cft__[0]=TRACK" onmouseover="this.href=\'/page/posts/pfbidREAL/\'">'
      +('<span>x</span>'*120)+'</a><span id="date-ref">1 ngày trước</span>'
      '<div data-ad-preview="message">A page video post with a long obfuscated timestamp.</div></div></div>')
    item=scrapers._facebook_items(facebook_page)[0]
    assert item['author']=='Suggested page'
    assert item['url']=='https://www.facebook.com/page/posts/pfbidREAL/'


def test_ad_headers_do_not_consume_the_runs_missing_link_samples(monkeypatch):
    ad=dict(item('Advertisement with no URL'),sponsored=True,_missing_header='<div>advertisement</div>')
    organic=dict(item('Organic post without a link'),_missing_header='<div>organic</div>')
    _,scraper,_=fake_collect(monkeypatch,[[ad,organic]],target=1)
    assert scraper.missing_headers==['<div>organic</div>']
