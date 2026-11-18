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

        def collect(self, page, url, label, quota, seen, progress, speed, interactive, **kwargs):
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
    monkeypatch.setattr(scrapers,'_facebook_items',lambda page,*args:[ad.copy(),organic.copy()])
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


@pytest.mark.parametrize('url', ['https://www.facebook.com/watch/?v=12345','https://www.facebook.com/page/videos/12345/','https://www.facebook.com/reel/12345/'])
def test_graphql_keeps_explicit_video_links(url):
    story={'__typename':'Story','message':{'text':'A sufficiently long page video caption.'},'url':url}
    assert scrapers.facebook_stories(story)[0]['url']==url


def test_page_graphql_metadata_supplies_permalink_for_content_story():
    story={'__typename':'Story','comet_sections':{
        'content':{'story':{'message':{'text':'A page news caption with a preview description.'}}},
        'metadata':[{'story':{'url':'https://www.facebook.com/page/posts/pfbidPAGE/','actors':[{'id':'123','name':'Page'}]}}]}}
    record=scrapers.facebook_stories(story)[0]
    assert record['url']=='https://www.facebook.com/page/posts/pfbidPAGE/'
    assert record['author']=='Page'


def test_short_page_caption_matches_expanded_preview_only_with_unique_author():
    import json
    cache={}
    def story(author,id):return {'__typename':'Story','message':{'text':'Tạm biệt acc clone'},'actors':[{'name':author}], 'url':f'https://www.facebook.com/page/posts/{id}/'}
    scrapers.cache_facebook_stories(json.dumps(story('Schannel',123)),cache)
    post=scrapers.RawPost(platform='facebook',source='feed',author='Schannel',text='Tạm biệt acc clone\nFacebook thông báo xóa trang cá nhân phụ trong tháng tới.')
    assert scrapers.match_facebook_story(post,cache)['url'].endswith('/posts/123/')
    post.author='Different page'
    assert scrapers.match_facebook_story(post,cache) is None


def test_page_video_attachment_uses_explicit_link_never_media_id():
    story={'__typename':'Story','message':{},'comet_sections':{'content':{'story':{
        'message':{'text':'Page video with an embedded player and full caption.'},
        'attachments':[{'styles':{'attachment':{'media':{'__typename':'Video','id':'999',
            'url':'https://www.facebook.com/watch/?v=12345'}}}}]}}}}
    assert scrapers.facebook_stories(story)[0]['url']=='https://www.facebook.com/watch/?v=12345'
    story['comet_sections']['content']['story']['attachments'][0]['styles']['attachment']['media'].pop('url')
    assert scrapers.facebook_stories(story)[0]['url']==''


def test_stable_feed_marker_survives_removed_sibling(facebook_page):
    facebook_page.set_content('''<div role="feed">
      <div><h4>First page</h4><a aria-labelledby="time1" href="?__cft__=x"
        onmouseover="document.getElementById('dummy')?.remove();this.href='/first/posts/pfbidFIRST/'">x</a>
        <span id="time1">1 giờ trước</span><div data-ad-preview="message">First page post with enough unique text.</div></div>
      <div id="dummy" role="article"></div>
      <div><h4>Second page</h4><a aria-labelledby="time2" href="?__cft__=x"
        onmouseover="this.href='/second/posts/pfbidSECOND/'">x</a>
        <span id="time2">2 giờ trước</span><div data-ad-preview="message">Second page post with enough unique text.</div></div>
    </div>''')
    items=scrapers._facebook_items(facebook_page)
    assert [x['url'] for x in items]==['https://www.facebook.com/first/posts/pfbidFIRST/','https://www.facebook.com/second/posts/pfbidSECOND/']
    assert facebook_page.locator('[data-feedlens-node]').count()==0


def test_snapshot_captured_before_hover_virtualizes_next_post(facebook_page):
    facebook_page.set_content('''<div role="feed">
      <div><h4>First page</h4><a aria-labelledby="t1" href="?__cft__=x"
        onmouseover="document.getElementById('second').innerHTML='<div></div>';this.href='/first/posts/pfbidFIRST/'">x</a>
        <span id="t1">1 giờ trước</span><div data-ad-preview="message">First page post with enough unique text.</div></div>
      <div id="second"><h4>Second page</h4><a aria-labelledby="t2" href="?__cft__=x">x</a>
        <span id="t2">2 giờ trước</span><div data-ad-preview="message">Second page post with enough unique text.</div></div>
    </div>''')
    items=scrapers._facebook_items(facebook_page)
    assert items[1]['url']==''
    assert 'Second page' in items[1]['_missing_header']
    assert 'Second page post with enough' in items[1]['_missing_header']
    assert 'post_not_visible' in items[1]['_missing_header']


def test_known_network_permalink_spares_hover_budget(facebook_page):
    import json
    text='Page post whose network permalink is already known.'
    facebook_page.set_content('<div role="article"><h4>Page</h4><a aria-labelledby="date" href="?__cft__=x" onmouseover="window.hovered=true">x</a><span id="date">2 giờ trước</span><div data-ad-preview="message">'+text+'</div></div>')
    cache={};scrapers.cache_facebook_stories(json.dumps({'__typename':'Story','message':{'text':text},'url':'https://www.facebook.com/page/posts/pfbidKNOWN/'}),cache)
    facebook_page.mouse.move(1,1);facebook_page.evaluate('window.hovered=false')
    items=scrapers._facebook_items(facebook_page,cache)
    assert items[0]['url']=='https://www.facebook.com/page/posts/pfbidKNOWN/'
    assert facebook_page.evaluate('window.hovered===true') is False


def test_short_caption_with_multiple_story_urls_remains_unresolved():
    import json
    cache={}
    for id in [1,2]:
        scrapers.cache_facebook_stories(json.dumps({'__typename':'Story','message':{'text':'Tạm biệt acc clone'},
            'actors':[{'name':'Schannel'}],'url':f'https://www.facebook.com/page/posts/{id}/'}),cache)
    post=scrapers.RawPost(platform='facebook',source='feed',author='Schannel',text='Tạm biệt acc clone\nLonger link preview that is visible only in the DOM.')
    assert scrapers.match_facebook_story(post,cache) is None


def test_virtualized_page_is_restored_before_timestamp_hover(facebook_page):
    facebook_page.mouse.move(1,1)
    facebook_page.set_content('''<div role="feed">
      <div><h4>First page</h4><a aria-labelledby="t1" href="?__cft__=x"
        onmouseover="window.unmounted=true;document.getElementById('second').innerHTML='<div></div>';this.href='/first/posts/pfbidFIRST/'">x</a>
        <span id="t1">1 giờ trước</span><div data-ad-preview="message">First page post with enough unique text.</div></div>
      <div id="second" style="margin-top:2000px;height:300px"><h4>Second page</h4><a aria-labelledby="t2" href="?__cft__=x"
        onmouseover="this.href='/second/posts/pfbidSECOND/'">x</a>
        <span id="t2">2 giờ trước</span><div data-ad-preview="message">Second page post with enough unique text.</div></div>
    </div><script>
      window.markup=document.getElementById('second').innerHTML;
      window.addEventListener('scroll',()=>{const n=document.getElementById('second');const r=n.getBoundingClientRect();
        if(window.unmounted && r.top<innerHeight && r.bottom>0){window.unmounted=false;setTimeout(()=>{n.innerHTML=window.markup;window.restored=true;},180);}});
    </script>''')
    items=scrapers._facebook_items(facebook_page)
    assert facebook_page.evaluate('window.restored===true')
    assert items[1]['url']=='https://www.facebook.com/second/posts/pfbidSECOND/'
    assert facebook_page.evaluate('scrollY')==0


def test_duplicate_short_captions_in_one_payload_are_not_a_unique_match():
    import json
    stories=[{'__typename':'Story','message':{'text':'Tạm biệt acc clone'},'actors':[{'name':'Schannel'}],
              'url':f'https://www.facebook.com/page/posts/{id}/'} for id in [1,2]]
    cache={};scrapers.cache_facebook_stories(json.dumps({'data':stories}),cache)
    post=scrapers.RawPost(platform='facebook',source='feed',author='Schannel',text='Tạm biệt acc clone\nLonger preview description.')
    assert scrapers.match_facebook_story(post,cache) is None


@pytest.mark.parametrize('actor,post_id,expected', [
 ({'id':'123'},'456','https://www.facebook.com/123/posts/456/'),
 ({'url':'https://www.facebook.com/Page.Name/?__cft__=track'},'pfbidABC123','https://www.facebook.com/Page.Name/posts/pfbidABC123/'),
 ({'slug':'Page.Name'},'pfbidABC123','https://www.facebook.com/Page.Name/posts/pfbidABC123/'),
 ({'url':'https://evil.test/Page.Name'},'pfbidABC123',''),
 ({'url':'https://www.facebook.com/groups/123/'},'456',''),
 ({'name':'Only a Page name'},'456',''),
])
def test_page_story_builds_link_only_with_explicit_owner(actor,post_id,expected):
    story={'__typename':'Story','post_id':post_id,'actors':[actor],'message':{'text':'An actual Page caption with sufficient text.'}}
    assert scrapers.facebook_stories(story)[0]['url']==expected


def test_story_does_not_borrow_actor_from_another_metadata_story():
    story={'__typename':'Story','post_id':'456','message':{'text':'A story with an identity but no actor on this node.'},
        'comet_sections':{'metadata':[{'story':{'actors':[{'id':'999','url':'https://www.facebook.com/other/'}]}}]}}
    assert scrapers.facebook_stories(story)[0]['url']==''


@pytest.mark.parametrize('decoded,expected', [
 ('feedback:pfbidABC123','pfbidABC123'),('opaque; Feedback:12345; end','12345'),
 ('comment:12345',''),('feedback:123_456',''),('feedback:123 feedback:456',''),
])
def test_feedback_id_search_stays_story_scoped(decoded,expected):
    import base64
    story={'__typename':'Story','message':{'text':'A page story whose feedback identifies the post.'},
        'actors':[{'id':'777'}],'feedback':{'id':base64.b64encode(decoded.encode()).decode()}}
    result=scrapers.facebook_stories(story)[0]['url']
    assert result==(f'https://www.facebook.com/777/posts/{expected}/' if expected else '')


def test_hover_env_off_never_moves_to_unresolved_timestamps(facebook_page,monkeypatch):
    monkeypatch.setenv('FEEDLENS_FB_HOVER','0');facebook_page.mouse.move(1,1)
    facebook_page.set_content('<div role="article"><h4>Page</h4><a aria-labelledby="date" href="?__cft__=x" onmouseover="this.href=\'/page/posts/pfbidHOVER/\'">x</a><span id="date">1 giờ trước</span><div data-ad-preview="message">Page post that would require timestamp hovering.</div></div>')
    item=scrapers._facebook_items(facebook_page)[0]
    assert item['url']=='' and 'hover_disabled' in item['_missing_header']


def test_graphql_debug_keeps_matched_node_or_same_author_keys():
    import json
    cache=scrapers.FacebookStoryCache()
    story={'__typename':'Story','message':{'text':'A sufficiently long Page caption without a post identifier.'},
           'actors':[{'name':'Page'}],'new_field':{'unknown_text':'x'*200},'cookie':'SECRET'}
    scrapers.cache_facebook_stories(json.dumps({'data':story}),cache)
    post=scrapers.RawPost(platform='facebook',source='feed',author='Page',text=story['message']['text'])
    matched=scrapers.facebook_graphql_debug(post,cache)
    assert matched['match']=='matched' and matched['story']['__typename']=='Story'
    assert 'cookie' not in matched['story'] and len(matched['story']['new_field']['unknown_text'])==60
    post.text='A different caption that does not match the network Story.'
    missing=scrapers.facebook_graphql_debug(post,cache)
    assert missing['same_author_keys'][0]['keys']==['__typename','actors','message','new_field']


def test_unparsed_page_story_still_exposes_sanitized_shape_for_diagnostics():
    import json
    cache=scrapers.FacebookStoryCache()
    scrapers.cache_facebook_stories(json.dumps({'__typename':'Story','actors':[{'name':'Page'}],
        'unknown_caption_shape':{'value':'No supported message node'},'fb_dtsg':'SECRET','__user':'USER'}),cache)
    post=scrapers.RawPost(platform='facebook',source='feed',author='Page',text='A DOM post that cannot be joined to any parsed Story.')
    result=scrapers.facebook_graphql_debug(post,cache)
    assert result['match']=='none_or_ambiguous'
    assert result['same_author_keys'][0]['keys']==['__typename','actors','unknown_caption_shape']


def test_debug_samples_are_collected_even_without_any_html_header(monkeypatch):
    posts,scraper,_=fake_collect(monkeypatch,[[item('A Page post that has no DOM or network permalink.')]],target=1)
    assert len(scraper.missing_graphql_samples)==1
    assert scraper.missing_graphql_samples[0]['match']=='none_or_ambiguous'
    assert scraper.missing_graphql_samples[0]['same_author_keys']==[]


def test_hover_budget_is_at_most_three_for_a_snapshot(facebook_page):
    facebook_page.mouse.move(1,1)
    facebook_page.set_content(''.join('<div role="article"><h4>Page '+str(i)+'</h4>'
        '<a aria-labelledby="t'+str(i)+'" href="?__cft__=x" onmouseover="window.hovers=(window.hovers||0)+1">x</a>'
        '<span id="t'+str(i)+'">1 giờ trước</span><div data-ad-preview="message">Page caption number '+str(i)+' with enough text.</div></div>' for i in range(5)))
    facebook_page.evaluate('window.hovers=0');items=scrapers._facebook_items(facebook_page)
    assert len(items)==5 and facebook_page.evaluate('window.hovers')<=3


def test_available_native_url_takes_precedence_over_post_id_and_owner():
    story={'__typename':'Story','post_id':'123','actors':[{'id':'777','slug':'Page.Name'}],
        'message':{'text':'Page story with an explicit canonical permalink.'},
        'permalink_url':'https://www.facebook.com/Page.Name/posts/pfbidCANONICAL/'}
    assert scrapers.facebook_stories(story)[0]['url']==story['permalink_url']


def test_missing_graphql_debug_samples_are_capped_per_source(monkeypatch):
    _,scraper,_=fake_collect(monkeypatch,[[item(f'Unresolved Page caption number {i}.') for i in range(12)]],target=12)
    assert len(scraper.missing_graphql_samples)==10


def test_graphql_debug_preserves_identifier_and_removes_nested_url_credentials():
    raw={'post_id':'pfbid'+'A'*90,'actors':[{'url':'https://user:password@www.facebook.com/Page/?id=777&access_token=SECRET'}],
        'message':{'text':'x'*100},'nested':{'cookies':{'xs':'PRIVATE'},'__user':'USER','fb_dtsg':'DTSG'}}
    clean=scrapers.sanitize_facebook_debug(raw)
    assert clean['post_id']==raw['post_id']
    assert clean['actors'][0]['url']=='https://www.facebook.com/Page/?id=777'
    assert len(clean['message']['text'])==60 and clean['nested']=={}


def test_debug_json_uses_graphql_responses_that_arrive_after_first_dom_capture(monkeypatch):
    import json
    first=item('An unresolved Page post seen before its network response.');second=item('Another organic post completing the requested quota.')
    callbacks={};calls=[]
    payload={'__typename':'Story','actors':[{'name':'Author'}],'message':{'text':first['text']},'new_page_shape':{'field':'unknown'}}
    page=SimpleNamespace(on=lambda event,fn:callbacks.update({event:fn}),remove_listener=lambda event,fn:callbacks.pop(event),
        goto=lambda *args,**kwargs:None,evaluate=lambda *args:[],mouse=SimpleNamespace(wheel=lambda *args:None))
    def extract(page,*args):
        calls.append(1)
        if len(calls)==1:return [first.copy()]
        callbacks['response'](SimpleNamespace(url='https://www.facebook.com/api/graphql/',status=200,text=lambda:json.dumps(payload)))
        return [second.copy()]
    monkeypatch.setattr(scrapers,'_facebook_items',extract);monkeypatch.setattr(scrapers,'_human_pause',lambda *a:None)
    monkeypatch.setattr(scrapers.random,'random',lambda:1)
    scraper=FacebookScraper();monkeypatch.setattr(scraper,'ensure_access',lambda *a:False)
    scraper.collect(page,'https://www.facebook.com/','feed',2,set(),lambda *a:None)
    assert scraper.missing_graphql_samples[0]['match']=='matched'
    assert 'new_page_shape' in scraper.missing_graphql_samples[0]['story']


def test_facebook_word_joiner_header_link_marks_sponsored(facebook_page):
    # Shape from real runs 6–10: the obfuscated "Sponsored" label is a header link whose text is only U+2060.
    facebook_page.set_content('''<div role="feed"><div role="article">
      <h4><a href="/profile.php?id=1">Rourke Heath</a> và <a href="/elevenlabsio">ElevenLabs</a></h4>
      <div><a href="?__cft__[0]=x" role="link">⁠<span><span></span></span></a><span aria-hidden="true"> · </span></div>
      <div data-ad-preview="message">Ranked #1 by Artificial Analysis. Expressive, lifelike voices.</div>
      <a href="https://l.facebook.com/l.php?u=https%3A%2F%2Fjoin.elevenlabs.io" role="link">JOIN.ELEVENLABS.IO</a></div></div>''')
    assert scrapers._facebook_items(facebook_page)[0]["sponsored"] is True


def test_facebook_organic_labelled_timestamp_is_not_sponsored(facebook_page):
    facebook_page.set_content('''<div role="feed"><div role="article">
      <h4><a href="/page">Tú Uyên</a></h4>
      <div><a aria-labelledby="_r_1_" href="?__cft__[0]=x" role="link"><span id="_r_1_">1 giờ</span></a></div>
      <div data-ad-preview="message">An ordinary page post with a normal timestamp link.</div></div></div>''')
    assert scrapers._facebook_items(facebook_page)[0]["sponsored"] is False


def test_story_graphql_replaces_truncated_dom_with_full_text(facebook_page, monkeypatch):
    import json
    prefix = "Tuyển dụng kỹ sư Python Backend làm việc tại Hà Nội với mức lương hấp dẫn và chế độ đãi ngộ tốt cho ứng viên có kinh nghiệm"
    full_text = prefix + " trên 3 năm về FastAPI, PostgreSQL, Redis và hệ thống phân tán quy mô lớn. Quyền lợi bảo hiểm đầy đủ."
    story = {
        "__typename": "Story",
        "post_id": "101",
        "actors": [{"name": "HR Tech"}],
        "message": {"text": full_text},
    }
    facebook_page.set_content(f'''<div role="feed"><div role="article">
      <h3>HR Tech</h3>
      <div data-ad-preview="message">{prefix}… Xem thêm</div>
      <div role="button" onclick="window.expandClicks=(window.expandClicks||0)+1">Xem thêm</div>
      <a href="/hrtech/posts/101/">1 h</a>
      <script type="application/json">{json.dumps({"data": story})}</script>
    </div></div>''')
    facebook_page.evaluate("window.expandClicks = 0")
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(facebook_page, "goto", lambda *args, **kwargs: None)
    report = {}
    posts = scraper.collect(facebook_page, "https://www.facebook.com/", "feed", 1, set(), lambda *args: None, report=report)
    assert len(posts) == 1
    assert posts[0].text == full_text
    assert report["full_text_from_story"] == 1
    assert facebook_page.evaluate("window.expandClicks") == 0


def test_two_authors_same_short_caption_do_not_merge_wrong_story(facebook_page, monkeypatch):
    import json
    short_caption = "Tuyển dev Python gấp"
    stories = [
        {"__typename": "Story", "post_id": "1", "actors": [{"name": "Alice"}],
         "message": {"text": short_caption + " lương 3000 USD tại Quận 1."}},
        {"__typename": "Story", "post_id": "2", "actors": [{"name": "Bob"}],
         "message": {"text": short_caption + " làm remote toàn thời gian."}},
    ]
    facebook_page.set_content(f'''<div role="feed"><div role="article">
      <h3>Alice</h3>
      <div data-ad-preview="message">{short_caption}… Xem thêm</div>
      <a href="/groups/demo/posts/1/">1 h</a>
      <script type="application/json">{json.dumps({"data": stories})}</script>
    </div></div>''')
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(facebook_page, "goto", lambda *args, **kwargs: None)
    report = {}
    posts = scraper.collect(facebook_page, "https://www.facebook.com/groups/demo/", "demo", 1, set(), lambda *args: None, report=report)
    assert len(posts) == 1
    assert posts[0].text == f"{short_caption}… Xem thêm"
    assert report["full_text_from_story"] == 0


def test_shared_or_other_group_story_is_not_used_for_full_text(facebook_page, monkeypatch):
    import json
    shared_prefix = "Bài viết gốc rất dài về kinh nghiệm phỏng vấn kỹ sư phần mềm tại các công ty công nghệ lớn"
    shared_full = shared_prefix + " và cách chuẩn bị thuật toán, thiết kế hệ thống trong 3 tháng."
    other_group_prefix = "Thông báo tuyển dụng lập trình viên ReactJS và TypeScript cho dự án thương mại điện tử"
    other_group_full = other_group_prefix + " tại thành phố Hồ Chí Minh, phúc lợi đầy đủ và thưởng tháng 13."
    payload = {
        "data": [
            {
                "__typename": "Story",
                "post_id": "10",
                "actors": [{"name": "Sharer"}],
                "message": {"text": "Mọi người tham khảo bài viết hay này nhé!"},
                "attached_story": {
                    "__typename": "Story",
                    "post_id": "11",
                    "actors": [{"name": "Original Author"}],
                    "message": {"text": shared_full},
                },
            },
            {
                "__typename": "Story",
                "post_id": "20",
                "actors": [{"name": "Other Group Author"}],
                "to": {"__typename": "Group", "id": "999"},
                "permalink_url": "https://www.facebook.com/groups/999/posts/20/",
                "message": {"text": other_group_full},
            },
        ]
    }
    facebook_page.set_content(f'''<div role="feed">
      <div role="article">
        <h3>Sharer</h3>
        <div data-ad-preview="message">{shared_prefix}… Xem thêm</div>
        <a href="/groups/111/posts/10/">1 h</a>
      </div>
      <div role="article">
        <h3>Other Group Author</h3>
        <div data-ad-preview="message">{other_group_prefix}… Xem thêm</div>
        <a href="/groups/111/posts/20/">2 h</a>
      </div>
      <script type="application/json">{json.dumps(payload)}</script>
    </div>''')
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(facebook_page, "goto", lambda *args, **kwargs: None)
    report = {}
    posts = scraper.collect(facebook_page, "https://www.facebook.com/groups/111/", "111", 2, set(), lambda *args: None, report=report)
    assert len(posts) == 2
    assert posts[0].text == f"{shared_prefix}… Xem thêm"
    assert posts[1].text == f"{other_group_prefix}… Xem thêm"
    assert report["full_text_from_story"] == 0


def test_shorter_story_never_replaces_longer_dom_text(facebook_page, monkeypatch):
    import json
    short_story = "Tuyển kỹ sư phần mềm"
    dom_text = short_story + " làm việc tại Hà Nội với nhiều quyền lợi hấp dẫn, mô tả chi tiết công việc rất dài ở phần xem trước liên kết."
    story = {
        "__typename": "Story",
        "post_id": "30",
        "actors": [{"name": "Page Author"}],
        "message": {"text": short_story},
    }
    facebook_page.set_content(f'''<div role="feed"><div role="article">
      <h3>Page Author</h3>
      <div data-ad-preview="message">{dom_text}</div>
      <a href="/PageAuthor/posts/30/">1 h</a>
      <script type="application/json">{json.dumps({"data": story})}</script>
    </div></div>''')
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(facebook_page, "goto", lambda *args, **kwargs: None)
    report = {}
    posts = scraper.collect(facebook_page, "https://www.facebook.com/", "feed", 1, set(), lambda *args: None, report=report)
    assert len(posts) == 1
    assert posts[0].text == dom_text
    assert report["full_text_from_story"] == 0


def test_round_without_expand_button_skips_expand_wait_using_fake_clock(facebook_page, monkeypatch):
    now = [0.0]
    pauses = []
    def fake_monotonic():
        now[0] += 0.01
        return now[0]
    def fake_pause(lo, hi):
        pauses.append((lo, hi))
        now[0] += lo
    monkeypatch.setattr(scrapers.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(scrapers, "_human_pause", fake_pause)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)

    # Case 1: no "Xem thêm" / "See more" button -> no expand pause
    facebook_page.set_content('''<div role="feed"><div role="article">
      <h3>Author</h3>
      <div data-ad-preview="message">A normal post without any expand button on the page.</div>
      <a href="/groups/demo/posts/40/">1 h</a>
    </div></div>''')
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(facebook_page, "goto", lambda *args, **kwargs: None)
    report = {}
    scraper.collect(facebook_page, "https://www.facebook.com/groups/demo/", "demo", 1, set(), lambda *args: None, report=report)
    expand_range = scrapers.PACE["fast"]["expand"]
    assert expand_range not in pauses

    # Case 2: has "Xem thêm" button and NO Story -> clicks and waits expand pause
    pauses.clear()
    facebook_page.set_content('''<div role="feed"><div role="article">
      <h3>Author</h3>
      <div data-ad-preview="message">A post without Story that actually needs expand button click.</div>
      <div role="button" onclick="window.clicked=(window.clicked||0)+1">Xem thêm</div>
      <a href="/groups/demo/posts/41/">1 h</a>
    </div></div>''')
    facebook_page.evaluate("window.clicked = 0")
    scraper.collect(facebook_page, "https://www.facebook.com/groups/demo/", "demo", 1, set(), lambda *args: None, report={})
    assert facebook_page.evaluate("window.clicked") == 1
    assert expand_range in pauses


def test_report_contains_all_five_timing_keys_and_accumulates_without_secrets(facebook_page, monkeypatch):
    import json
    now = [100.0]
    def fake_monotonic():
        now[0] += 0.05
        return now[0]
    def fake_pause(lo, hi):
        now[0] += lo
    monkeypatch.setattr(scrapers.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(scrapers, "_human_pause", fake_pause)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)

    prefix = "Bài viết thứ nhất có nội dung đủ dài để khớp duy nhất với Story trong bộ nhớ đệm GraphQL"
    full_text = prefix + " và phần nội dung mở rộng đầy đủ phía sau không cần bấm nút xem thêm."
    story = {
        "__typename": "Story",
        "post_id": "50",
        "actors": [{"name": "Author"}],
        "message": {"text": full_text},
    }
    facebook_page.set_content(f'''<div role="feed"><div role="article">
      <h3>Author</h3>
      <div data-ad-preview="message">{prefix}… Xem thêm</div>
      <a href="/author/posts/50/">1 h</a>
      <script type="application/json">{json.dumps({"data": story})}</script>
    </div></div>''')
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(facebook_page, "goto", lambda *args, **kwargs: None)
    report = {}
    scraper.collect(facebook_page, "https://www.facebook.com/", "feed1", 1, set(), lambda *args: None, report=report)
    first_nav = report["timings"]["navigation"]
    assert set(report["timings"].keys()) == {"navigation", "scroll_wait", "expand", "link_resolve", "extract"}
    assert all(isinstance(v, float) and v >= 0.0 for v in report["timings"].values())
    assert report["full_text_from_story"] == 1

    # Second source accumulates on the same report dict
    scraper.collect(facebook_page, "https://www.facebook.com/", "feed2", 1, set(), lambda *args: None, report=report)
    assert report["timings"]["navigation"] > first_nav
    assert report["full_text_from_story"] == 2
    serialized = json.dumps(report, ensure_ascii=False)
    assert full_text not in serialized
    assert "cookie" not in serialized.lower()


@pytest.mark.parametrize("href,expected", [
    ("/groups/x/posts/4616939438573919/?comment_id=4616948331906363&__cft__[0]=abc&__tn__=R",
     "https://www.facebook.com/groups/x/posts/4616939438573919/"),
    ("/groups/x/posts/4616939438573919/?reply_comment_id=999&notif_id=123",
     "https://www.facebook.com/groups/x/posts/4616939438573919/"),
    ("/permalink/123456/?comment_id=777&fbclid=xyz",
     "https://www.facebook.com/permalink/123456/"),
    ("/permalink.php?story_fbid=111&id=222&comment_id=333&__cft__[0]=a",
     "https://www.facebook.com/permalink.php?story_fbid=111&id=222"),
])
def test_facebook_permalink_strips_comment_id_and_junk_query(href, expected):
    assert select_facebook_link([(href, True)]) == expected


def test_facebook_dom_prefers_post_anchor_over_earlier_comment_anchor(facebook_page):
    facebook_page.set_content('''<div role="feed"><div role="article">
      <h3>Author</h3>
      <div data-ad-preview="message">Post content long enough for extraction in group feed.</div>
      <a href="/groups/x/posts/999/?comment_id=111&__tn__=R">5 m</a>
      <a href="/groups/x/posts/4616939438573919/">2 h</a>
    </div></div>''')
    item = scrapers._facebook_items(facebook_page)[0]
    assert item["url"] == "https://www.facebook.com/groups/x/posts/4616939438573919/"


def _ndjson_page(monkeypatch, payloads, *, dom_items=None):
    callbacks = {}
    def goto(url, **kwargs):
        for body in payloads:
            callbacks["response"](SimpleNamespace(
                url="https://www.facebook.com/api/graphql/", status=200, text=lambda b=body: b
            ))
    page = SimpleNamespace(
        on=lambda event, fn: callbacks.update({event: fn}),
        remove_listener=lambda event, fn: callbacks.pop(event, None),
        goto=goto,
        evaluate=lambda *args: [],
        mouse=SimpleNamespace(wheel=lambda *args: None),
    )
    monkeypatch.setattr(scrapers, "_facebook_items", lambda *args: list(dom_items or []))
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    return page


def test_group_graphql_first_extracts_clean_story_without_dom_and_dedups_repeats(monkeypatch):
    import base64, json
    comment_fb = base64.b64encode(b"comment:9876543210").decode()
    good_story = {
        "__typename": "Story",
        "post_id": "1001",
        "creation_time": 1794900000,
        "actors": [{"name": "Minh Dev"}],
        "to": {"__typename": "Group", "id": "111"},
        "permalink_url": "https://www.facebook.com/groups/111/posts/1001/?comment_id=555&__cft__[0]=x",
        "message": {"text": "Tuyển kỹ sư Backend Python làm việc tại Hà Nội, toàn văn đầy đủ từ GraphQL."},
    }
    other_group = {
        "__typename": "Story",
        "post_id": "1002",
        "creation_time": 1794900100,
        "actors": [{"name": "Other"}],
        "to": {"__typename": "Group", "id": "999"},
        "message": {"text": "Bài viết từ nhóm khác không được phép lọt vào kết quả của nhóm 111."},
    }
    suggested_page = {
        "__typename": "Story",
        "post_id": "1003",
        "creation_time": 1794900200,
        "actors": [{"id": "777", "name": "Suggested Page"}],
        "message": {"text": "Bài gợi ý từ trang ngoài nhóm không thuộc nhóm 111."},
    }
    comment_node = {
        "__typename": "Comment",
        "feedback": {"id": comment_fb},
        "body": {"text": "Bình luận có feedback số nhưng không phải Story."},
    }
    ad_story = {
        "__typename": "Story",
        "post_id": "1004",
        "creation_time": 1794900300,
        "actors": [{"name": "Sponsor"}],
        "to": {"__typename": "Group", "id": "111"},
        "sponsored_data": {"ad_id": "888"},
        "message": {"text": "Quảng cáo tài trợ trong nhóm cần bị lọc khỏi target."},
    }
    ndjson = "\n".join([
        json.dumps({"data": good_story}),
        json.dumps({"data": other_group}),
        json.dumps({"data": suggested_page}),
        json.dumps({"data": comment_node}),
        json.dumps({"data": ad_story}),
    ])
    # Repeat the exact same NDJSON payload to verify duplicate responses do not duplicate posts.
    page = _ndjson_page(monkeypatch, [ndjson, ndjson])
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    report = {}
    posts = scraper.collect(page, "https://www.facebook.com/groups/111/", "111", 5, set(), lambda *a: None, report=report)
    assert len(posts) == 1
    assert posts[0].url == "https://www.facebook.com/groups/111/posts/1001/"
    assert posts[0].author == "Minh Dev"
    assert posts[0].posted_at.startswith("2026-") or "T" in posts[0].posted_at
    assert scraper.last_report["skipped_ads"] == 1
    assert report["from_story"] == 1


def test_group_graphql_first_keeps_photo_only_and_same_caption_different_post_id(monkeypatch):
    import json
    photo_story = {
        "__typename": "Story",
        "post_id": "2001",
        "creation_time": 1794900100,
        "actors": [{"name": "Photo Poster"}],
        "to": {"__typename": "Group", "id": "111"},
        "attachments": [{"media": {"__typename": "Photo", "id": "444", "accessibility_caption": "Ảnh tuyển dụng"}}],
    }
    dup_caption_1 = {
        "__typename": "Story",
        "post_id": "2002",
        "creation_time": 1794900200,
        "actors": [{"name": "User A"}],
        "to": {"__typename": "Group", "id": "111"},
        "message": {"text": "Tuyển lập trình viên Python gấp trong tuần này!"},
    }
    dup_caption_2 = {
        "__typename": "Story",
        "post_id": "2003",
        "creation_time": 1794900300,
        "actors": [{"name": "User B"}],
        "to": {"__typename": "Group", "id": "111"},
        "message": {"text": "Tuyển lập trình viên Python gấp trong tuần này!"},
    }
    payload = json.dumps({"data": [photo_story, dup_caption_1, dup_caption_2]})
    page = _ndjson_page(monkeypatch, [payload])
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    report = {}
    posts = scraper.collect(page, "https://www.facebook.com/groups/111/", "111", 5, set(), lambda *a: None, report=report)
    assert len(posts) == 3
    assert {p.url for p in posts} == {
        "https://www.facebook.com/groups/111/posts/2001/",
        "https://www.facebook.com/groups/111/posts/2002/",
        "https://www.facebook.com/groups/111/posts/2003/",
    }
    assert report["from_story"] == 3


def test_group_graphql_first_sorts_by_creation_time_for_caught_up_and_dedups_dom(monkeypatch):
    import json
    # 8 old stories (older creation_time) + 1 newest story (arrives LAST in cache!)
    old_stories = [{
        "__typename": "Story",
        "post_id": str(3000 + i),
        "creation_time": 1794800000 + i,
        "actors": [{"name": f"Old {i}"}],
        "to": {"__typename": "Group", "id": "111"},
        "message": {"text": f"Bài cũ số {i} đã đọc ở lượt trước đó rồi nhé."},
    } for i in range(8)]
    newest_story = {
        "__typename": "Story",
        "post_id": "3999",
        "creation_time": 1794999999,
        "actors": [{"name": "Newest"}],
        "to": {"__typename": "Group", "id": "111"},
        "message": {"text": "Bài mới nhất có creation_time lớn nhất nhưng về sau trong JSON."},
    }
    seen = {fingerprint(s["message"]["text"]) for s in old_stories}
    # DOM also renders newest_story with same post_id: must be deduplicated, not counted twice.
    dom_dup = {
        "author": "Newest",
        "text": newest_story["message"]["text"],
        "url": "https://www.facebook.com/groups/111/posts/3999/",
        "posted_at": "",
        "sponsored": False,
    }
    payload = json.dumps({"data": [*old_stories, newest_story]})
    page = _ndjson_page(monkeypatch, [payload], dom_items=[dom_dup])
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    report = {}
    posts = scraper.collect(
        page, "https://www.facebook.com/groups/111/?sorting_setting=CHRONOLOGICAL",
        "111", 10, seen, lambda *a: None, chronological=True, report=report,
    )
    assert len(posts) == 1
    assert posts[0].url == "https://www.facebook.com/groups/111/posts/3999/"
    assert scraper.last_report["skipped_old"] == 8
    assert scraper.last_report["stop_reason"] == "caught_up"
    assert report["from_story"] == 1


def test_collect_respects_custom_old_streak_limit(monkeypatch):
    old = [item(f"Old group post number {i}") for i in range(5)]
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    batches = iter([[p] for p in old])
    monkeypatch.setattr(scrapers, "_facebook_items", lambda page: next(batches, []))
    scraper = FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *args: False)
    page = SimpleNamespace(goto=lambda *args, **kwargs: None, evaluate=lambda *args: None,
                           mouse=SimpleNamespace(wheel=lambda *args: None))
    posts = scraper.collect(
        page, "https://www.facebook.com/groups/demo/?sorting_setting=CHRONOLOGICAL",
        "demo", 20, {fingerprint(p["text"]) for p in old}, lambda *a: None,
        old_streak_limit=3,
    )
    assert posts == []
    assert scraper.last_report["skipped_old"] == 3
    assert scraper.last_report["stop_reason"] == "caught_up"
