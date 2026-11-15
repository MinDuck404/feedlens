from types import SimpleNamespace

from feedlens import pipeline
from feedlens.db import Database
from feedlens.models import AnalyzedPost, RawPost, RunRequest


def make_db(tmp_path):
    return Database(f"sqlite:///{(tmp_path / 't.db').as_posix()}")


def test_sponsored_flag_survives_analysis_and_old_runs_default_false(tmp_path):
    db = make_db(tmp_path)
    run = db.create_run(RunRequest(platform="facebook"))
    ad = RawPost(platform="facebook", source="Feed", text="Sponsored product launch post body", sponsored=True)
    normal = RawPost(platform="facebook", source="Feed", text="A friend shares a long story today")
    db.save_raw_posts(run, [ad, normal])
    db.save_batch(run, [AnalyzedPost(**p.model_dump(), category="other") for p in (ad, normal)])
    flags = {p.text: p.sponsored for p in db.get_posts(run)}
    assert flags == {ad.text: True, normal.text: False}

    legacy = db.create_run(RunRequest(platform="facebook"))
    db.update_run(legacy, raw_posts=[{"platform": "facebook", "source": "Feed", "text": normal.text}])
    db.save_batch(legacy, [AnalyzedPost(**normal.model_dump(exclude={"sponsored"}), category="other")])
    assert [p.sponsored for p in db.get_posts(legacy)] == [False]


def test_save_scrape_report_keeps_request_and_writes_local_samples(tmp_path, monkeypatch):
    db = make_db(tmp_path)
    req = RunRequest(platform="facebook", count=20)
    run = db.create_run(req)
    monkeypatch.setattr(pipeline, "settings", SimpleNamespace(data_dir=tmp_path))
    pipeline.save_scrape_report(db, run, req, {
        "sources": [{"label": "Feed", "target": 20, "collected": 14, "skipped_old": 23, "examined": 37,
                     "stop_reason": "budget_exhausted"}],
        "missing_link_samples": ["<div>a</div>", "<div>b</div>"]})
    saved = db.get_run(run)["request"]
    assert saved["count"] == 20
    assert saved["scrape_report"]["skipped_old"] == 23 and saved["scrape_report"]["stop_reason"] == "budget_exhausted"
    html = (tmp_path / "debug" / "missing-links" / f"run-{run}.html").read_text(encoding="utf-8")
    assert "<div>a</div>" in html and "<div>b</div>" in html
    assert RunRequest(**saved).count == 20  # extra key does not break re-reading the request


def test_empty_report_changes_nothing(tmp_path):
    db = make_db(tmp_path)
    req = RunRequest(platform="facebook")
    run = db.create_run(req)
    pipeline.save_scrape_report(db, run, req, {})
    assert "scrape_report" not in db.get_run(run)["request"]


def test_ad_skip_count_aggregates_and_legacy_sources_default_zero(tmp_path):
    db=make_db(tmp_path);req=RunRequest(platform="facebook");rid=db.create_run(req)
    pipeline.save_scrape_report(db,rid,req,{"sources":[
        dict(target=20,collected=20,skipped_old=2,skipped_ads=3,stop_reason="target_reached"),
        dict(target=20,collected=14,skipped_old=4,stop_reason="no_more_posts")
    ]})
    report=db.get_run(rid)["request"]["scrape_report"]
    assert report["skipped_ads"]==3 and report["collected"]==34 and report["skipped_old"]==6


def test_graphql_debug_file_is_sanitized_capped_and_not_stored_in_request(tmp_path,monkeypatch):
    import json
    db=make_db(tmp_path);req=RunRequest(platform='facebook');rid=db.create_run(req)
    monkeypatch.setattr(pipeline,'settings',SimpleNamespace(data_dir=tmp_path))
    raw={'author':'Page','text':'Long caption '*20,'story':{'__typename':'Story','post_id':'pfbidABC','token':'SECRET',
        'message':{'text':'Body '*100,'cookie':'PRIVATE'},'fb_dtsg':'DTSG','__user':'USER',
        'url':'https://www.facebook.com/page/posts/pfbidABC/?access_token=URLSECRET&story_fbid=pfbidABC'}}
    pipeline.save_scrape_report(db,rid,req,{'sources':[dict(target=20,collected=14,skipped_old=2,stop_reason='no_more_posts')],
        'missing_graphql_samples':[raw for _ in range(12)]})
    filename=tmp_path/'debug'/'missing-links'/f'run-{rid}.json';content=filename.read_text(encoding='utf-8');saved=json.loads(content)
    assert len(saved)==10
    assert len(saved[0]['text'])<=60 and len(saved[0]['story']['message']['text'])<=60
    for secret in ['SECRET','PRIVATE','DTSG','USER','access_token','fb_dtsg','__user']:assert secret not in content
    assert saved[0]['story']['post_id']=='pfbidABC'
    assert 'missing_graphql_samples' not in db.get_run(rid)['request']
    assert set(db.get_run(rid)['request']['scrape_report'])=={'target','collected','skipped_old','skipped_ads','stop_reason','sources'}


def test_collect_all_transfers_at_most_ten_graphql_debug_samples(monkeypatch):
    class Fake:
        def urls(self,*args):return [('source one','https://example.test/1'),('source two','https://example.test/2')]
        def collect(self,page,url,label,target,seen,progress,**kwargs):
            self.last_report=dict(target=target,collected=1,skipped_old=0,skipped_ads=0,stop_reason='target_reached')
            self.missing_headers=[]
            self.missing_graphql_samples=[{'author':label,'text':str(i)} for i in range(8)]
            return [RawPost(platform='facebook',source=label,text='A visible post from '+label)]
    monkeypatch.setitem(pipeline.SCRAPERS,'facebook',Fake)
    report={};req=RunRequest(platform='facebook',source_type='group',sources=['one','two'],count=1)
    pipeline.collect_all(None,req,set(),lambda *args:None,False,report)
    assert len(report['missing_graphql_samples'])==10
    assert report['missing_graphql_samples'][-1]['author']=='source two'
