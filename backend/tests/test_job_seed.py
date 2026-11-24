import re
from types import SimpleNamespace

import pytest

from feedlens.runs import pipeline
from feedlens.analysis.prompts import CLASSIFY_SCHEMA
from feedlens.analysis.prompts import KNOWN_JOBS_SCHEMA
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.analysis.llm import LLMAnalyzer
from feedlens.db import Database
from feedlens.jobs.profile import JobProfile
from feedlens.models import JobSeed, RawPost, RunRequest, Topic


def seeded_post(job_id="4100000001", text="Python engineer at a technology company", **fields):
    seed = JobSeed(**{
        "title": "Python Engineer", "company": "Observed Company", "location": "Vietnam",
        "url": f"https://www.linkedin.com/jobs/view/{job_id}/", "job_id": job_id,
        "posted_at": "2026-11-17", "work_mode": "remote", "salary_text": "$4,000/month", **fields,
    })
    return RawPost(platform="linkedin", source="Jobs: Python", text=text, url=seed.url,
                   author=seed.company, posted_at=seed.posted_at, job_seed=seed)


def llm(complete):
    return LLMAnalyzer(SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake")))


def assert_observed(post, seed):
    assert post.category == "job"
    assert post.job_seed == seed
    assert post.job.title == seed.title and post.job.company == seed.company
    assert post.job.location == seed.location and post.job.contact == seed.url
    assert post.job.work_mode == seed.work_mode and post.job.salary == seed.salary_text


def test_seed_is_a_known_job_and_observed_facts_override_conflicting_ai():
    raw = seeded_post()
    prompts = []
    def complete(system, prompt, schema, effort):
        assert schema is KNOWN_JOBS_SCHEMA
        fields = schema["properties"]["items"]["items"]["properties"]
        assert "is_job" not in fields and "category" not in fields
        prompts.append(prompt)
        return {"items": [{"id": 0, "category": "tech", "is_job": False, "summary": "A suitable role",
                           "job": {"title": "AI invented title", "company": "Wrong company", "location": "Wrong city",
                                   "contact": "https://wrong.test/", "work_mode": "onsite", "salary": "Wrong salary",
                                   "match_score": 91, "match_reason": "Python skills match", "match_type": "primary"}}]}
    analyzer = llm(complete)
    analyzer.job_profile = JobProfile(markdown="UNIQUE_CV Python", primary_roles=["Python Engineer"])
    post = analyzer.classify([raw], True, ["Python"], "UNIQUE_NOTES", lambda *a: None)[0]
    assert_observed(post, raw.job_seed)
    assert post.job.match_score >= 70 and post.job.match_score != 91 and post.job.match_type == "primary"
    assert prompts[0].count("<job_seed>") == 1 and '"job_id": "4100000001"' in prompts[0]
    assert prompts[0].count("UNIQUE_CV") == prompts[0].count("UNIQUE_NOTES") == 1


@pytest.mark.parametrize("result", [
    {"items": [{"id": 0, "summary": "", "job": {}}]},
    {"items": [{"id": 0, "summary": "Empty extracted facts", "job": {
        "title": "", "company": "", "location": "", "salary": "", "work_mode": "", "contact": ""}}]},
    {"items": []}, {},
])
def test_empty_ai_output_never_discards_observed_seed(result):
    raw = seeded_post()
    post = llm(lambda *a: result).classify([raw], False, [], "", lambda *a: None)[0]
    assert_observed(post, raw.job_seed)


def test_ai_can_fill_facts_not_present_in_seed():
    raw = seeded_post(company="", location="", salary_text="", work_mode="")
    analyzer = llm(lambda *a: {"items": [{"id": 0, "summary": "Role", "job": {
        "company": "Company in description", "location": "Hanoi", "salary": "Negotiable", "work_mode": "hybrid"}}]})
    post = analyzer.classify([raw], True, [], "", lambda *a: None)[0]
    assert post.job.title == "Python Engineer" and post.job.contact == raw.url
    assert post.job.company == "Company in description" and post.job.location == "Hanoi"
    assert post.job.salary == "Negotiable" and post.job.work_mode == "hybrid"
    assert post.job_seed.company == ""  # AI enrichment never mutates the observed source.


def test_offline_seed_produces_jobinfo_and_matches_cv_and_topics_without_job_keywords():
    raw = seeded_post(text="A short card without recruitment keywords")
    analyzer = HeuristicAnalyzer()
    analyzer.job_profile = JobProfile(markdown="Python Docker", primary_roles=["Python Engineer"])
    analyzer.topics = [Topic(id=7, name="Python", include_keywords=["Python"])]
    post = analyzer.classify([raw], True, [], "", lambda *a: None)[0]
    assert_observed(post, raw.job_seed)
    assert post.job.match_score >= 70 and post.job.match_type == "primary"
    assert post.topic_ids == [7]


def test_offline_seed_can_be_viewed_without_cv_or_matching_keywords():
    raw = seeded_post(text="A concise card")
    post = HeuristicAnalyzer().classify([raw], False, [], "", lambda *a: None)[0]
    assert_observed(post, raw.job_seed)
    assert post.job.match_score == 50 and post.job.match_type is None


def test_mixed_jobs_and_ordinary_posts_keep_input_order_and_topic_scoring():
    calls = []
    def complete(system, prompt, schema, effort):
        calls.append(prompt)
        fields = schema["properties"]["items"]["items"]["properties"]
        known = "is_job" not in fields
        assert "topic_ids" in fields
        ids = [int(i) for i in re.findall(r'<post id="(\d+)"', prompt)]
        return {"items": [{"id": i, "summary": "Known role" if known else "Ordinary news", "job": {"match_score": 75},
                           "category": "news", "is_job": False, "topic_ids": [7, 7, 999],
                           "topic_reason": "Python topic"} for i in ids]}
    analyzer = llm(complete)
    analyzer.topics = [Topic(id=7, name="Python")]
    raw = [seeded_post("101"), RawPost(platform="x", source="search", text="Python release news"), seeded_post("102")]
    snapshots = []
    analyzer.on_batch = lambda batch: snapshots.extend(batch)
    result = analyzer.classify(raw, True, [], "", lambda *a: None)
    assert len(calls) == 2 and len(snapshots) == 3
    assert [p.fingerprint for p in result] == [p.fingerprint for p in raw]
    assert [p.category for p in result] == ["job", "news", "job"]
    assert result[1].job is None and result[1].job_seed is None
    assert all(p.topic_ids == [7] and p.topic_reason == "Python topic" for p in result)
    assert_observed(result[0], raw[0].job_seed)
    assert_observed(result[2], raw[2].job_seed)


def test_seeded_jobs_keep_existing_cv_score_caps():
    analyzer = llm(lambda *a: {"items": [{"id": 0, "summary": "Role", "job": {
        "match_score": 101, "match_type": "adjacent", "constraint_flags": ["location", "location"],
        "gaps": ["a", "b", "c", "d"], "match_reason": "x" * 200}}]})
    analyzer.job_profile = JobProfile(markdown="Python", allow_adjacent=False)
    post = analyzer.classify([seeded_post()], True, [], "", lambda *a: None)[0]
    assert post.job.match_score < 40 and post.job.match_type == "stretch" and post.job.constraint_flags == ["location"]
    assert post.job.gaps == ["a", "b", "c"] and post.job.match_reason.startswith("Vai trò stretch")


def test_checkpoint_retry_preserves_seed_and_does_not_reanalyze_successful_batches(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{(tmp_path / 'seed-recovery.db').as_posix()}")
    req = RunRequest(platform="linkedin", job_mode=True, ai_provider="offline")
    rid = db.create_run(req)
    raw = [seeded_post(str(100 + i), text=f"Card {i}" + (" FAIL_BATCH" if i == 2 else "")) for i in range(6)]
    calls, fail = [], [True]
    def complete(system, prompt, schema, effort):
        if schema is KNOWN_JOBS_SCHEMA:
            assert db.get_raw_posts(rid) == raw
            calls.append(prompt)
            if fail[0] and "FAIL_BATCH" in prompt:
                raise RuntimeError("Invalid structured output for this batch")
            return {"items": [{"id": int(i), "summary": "Role", "job": {"match_score": 80}}
                              for i in re.findall(r'<post id="(\d+)"', prompt)]}
        return {"overall": "Jobs summary", "categories": [{"category": "job", "summary": "Jobs", "highlights": []}], "action_items": []}
    analyzer = llm(complete)
    monkeypatch.setattr('feedlens.analysis.prompts.BATCH_SIZE', 2)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "analysis_failed"
    completed = {p.fingerprint: p.id for p in db.get_posts(rid) if p.analyzed}
    assert len(completed) == 4
    assert sum(p.analyzed for p in db.get_posts(rid, include_raw=True)) == 4
    assert all(p.job_seed is not None for p in db.get_posts(rid, include_raw=True))
    calls.clear()
    fail[0] = False
    pipeline.execute_analysis(db, rid, req, db.get_raw_posts(rid), None)
    assert len(calls) == 1 and "FAIL_BATCH" in calls[0]
    assert db.get_run(rid)["status"] == "done"
    posts = db.get_posts(rid)
    assert len(posts) == 6 and all(p.category == "job" and p.job_seed is not None for p in posts)
    assert all(p.id == completed[p.fingerprint] for p in posts if p.fingerprint in completed)
    assert {p.fingerprint for p in posts} == {p.fingerprint for p in raw}
    assert db.get_run(rid)["digest"]["categories"][0]["count"] == 6


def test_digest_only_retry_keeps_seed_and_skips_completed_ai_calls(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{(tmp_path / 'seed-digest.db').as_posix()}")
    req = RunRequest(platform="linkedin", ai_provider="offline")
    rid = db.create_run(req)
    raw = [seeded_post()]
    calls, fail_digest = [], [True]
    def complete(system, prompt, schema, effort):
        calls.append(schema)
        if schema is KNOWN_JOBS_SCHEMA:
            return {"items": [{"id": 0, "summary": "Role", "job": {"match_score": 72}}]}
        if fail_digest[0]:
            raise RuntimeError("digest failed")
        return {"overall": "Done", "categories": [], "action_items": []}
    analyzer = llm(complete)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "analysis_failed"
    assert_observed(db.get_posts(rid)[0], raw[0].job_seed)
    calls.clear()
    fail_digest[0] = False
    pipeline.execute_analysis(db, rid, req, db.get_raw_posts(rid), None)
    assert len(calls) == 1 and calls[0] is not KNOWN_JOBS_SCHEMA
    assert db.get_run(rid)["status"] == "done"
    assert_observed(db.get_posts(rid)[0], raw[0].job_seed)


def test_unseeded_provider_contract_and_offline_category_are_unchanged():
    raw = RawPost(platform="x", source="feed", text="Python release announcement")
    def complete(system, prompt, schema, effort):
        assert schema is CLASSIFY_SCHEMA and "<job_seed>" not in prompt
        return {"items": [{"id": 0, "category": "tech", "summary": "Python news", "is_job": False, "job": {}}]}
    post = llm(complete).classify([raw], False, [], "", lambda *a: None)[0]
    assert post.category == "tech" and post.job is None and post.job_seed is None
    assert HeuristicAnalyzer().classify([raw], False, [], "", lambda *a: None)[0].category == "tech"
