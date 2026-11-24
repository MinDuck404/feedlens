
import feedlens.routes.dependencies as dependencies
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from feedlens import api
from feedlens.runs import pipeline
from feedlens.analysis.prompts import CLASSIFY_SCHEMA
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.analysis.llm import LLMAnalyzer
from feedlens.db import Database
from feedlens.jobs.profile import MAX_CV_BYTES
from feedlens.jobs.profile import CV_SCHEMA
from feedlens.jobs.profile import JobProfile
from feedlens.jobs.profile import ProfileError
from feedlens.jobs.profile import analyze_cv
from feedlens.jobs.profile import extract_cv_pdf
from feedlens.jobs.profile import load_profile
from feedlens.jobs.profile import redact_contacts
from feedlens.jobs.profile import relevant_roles
from feedlens.jobs.profile import store_profile
from feedlens.models import JobInfo, RawPost, RunRequest
from tests.test_cloud import cloud, _signup


def pdf_bytes(text="Junior Python Developer with FastAPI and Docker skills", encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(300, 200)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("password")
    output = BytesIO(); writer.write(output)
    return output.getvalue()


def test_pdf_text_and_invalid_inputs():
    assert "FastAPI" in extract_cv_pdf(pdf_bytes())
    for data, code in [(pdf_bytes(""), "error.cv_no_text"), (pdf_bytes(encrypted=True), "error.cv_invalid"),
                       (b"not a PDF", "error.cv_invalid"), (b"%PDF-invalid", "error.cv_invalid"),
                       (b"x" * (MAX_CV_BYTES + 1), "error.cv_too_large")]:
        with pytest.raises(ProfileError) as exc:
            extract_cv_pdf(data)
        assert exc.value.code == code


def test_profile_crud_isolation_encryption_and_cv_is_not_saved(cloud, tmp_path):
    client = cloud()
    a, b = _signup(client, "cv-a@example.test"), _signup(client, "cv-b@example.test")
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/profile", headers=a).json() is None
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    response = client.post("/api/profile/cv", headers=a, data={"ai_provider": "offline", "language": "en"}, files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")})
    assert response.status_code == 200, response.text
    assert response.json()["offline"] is True
    assert "FastAPI" in response.json()["markdown"]
    assert client.get("/api/profile", headers=a).json() is None  # analysis is a draft
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
    profile = JobProfile(markdown="# CV_PRIVATE_MARKER\nPython FastAPI\nmail@example.test\nPhone: 0901234567\nAddress: 123 Main Street", primary_roles=["Python Developer"])
    response = client.put("/api/profile", headers=a, json=profile.model_dump())
    assert response.status_code == 200, response.text
    stored = response.json()
    assert "mail@example.test" not in stored["markdown"] and "0901234567" not in stored["markdown"] and "Main Street" not in stored["markdown"]
    user = dependencies.db().get_user_by_email("cv-a@example.test")
    payload = dependencies.db().get_job_profile(user.id)
    assert payload.startswith("fernet:") and "CV_PRIVATE_MARKER" not in payload
    assert client.get("/api/profile", headers=b).json() is None
    assert client.delete("/api/profile", headers=b).status_code == 200
    assert client.get("/api/profile", headers=a).json()["primary_roles"] == ["Python Developer"]
    assert client.delete("/api/profile", headers=a).status_code == 200
    assert client.get("/api/profile", headers=a).json() is None


def test_cv_api_errors_and_pasted_text(cloud):
    client = cloud(); headers = _signup(client)
    for blob, code in [(pdf_bytes(""), "error.cv_no_text"), (b"invalid", "error.cv_invalid"), (b"x" * (MAX_CV_BYTES + 1), "error.cv_too_large")]:
        response = client.post("/api/profile/cv", headers=headers, files={"file": ("cv.pdf", blob, "application/pdf")})
        assert response.status_code == 400 and response.json()["code"] == code
    response = client.post("/api/profile/cv", headers=headers, data={"text": "Junior Backend Developer Python FastAPI Docker\nEmail: me@example.test", "ai_provider": "offline"})
    assert response.status_code == 200 and "me@example.test" not in response.json()["markdown"]
    assert client.put("/api/profile", headers=headers, json={"markdown": "x" * 8001}).status_code == 422


def test_ai_cv_is_redacted_and_uses_only_relevant_role_hints():
    prompts = []
    def call(system, prompt, schema, effort):
        assert "English" in system and schema is CV_SCHEMA
        prompts.append(prompt)
        return {"markdown": "# Profile\nPython FastAPI\nEmail: output@example.test", "suggested_roles": ["Backend Developer"], "adjacent_roles": [{"role": "QA Engineer", "reason": "API testing skills transfer"}]}
    result = analyze_cv("Junior Backend Developer Python FastAPI\nPhone: 0901234567\nEmail: secret@example.test\nAddress: 42 Main Street", LLMAnalyzer(SimpleNamespace(complete_json=call, model="fake", info=SimpleNamespace(name="Fake"))), "en")
    assert len(prompts) == 1
    assert "secret@example.test" not in prompts[0] and "0901234567" not in prompts[0] and "Main Street" not in prompts[0]
    assert "output@example.test" not in result["markdown"]
    assert result["adjacent_roles"][0]["enabled"] is True
    assert 0 < len(relevant_roles("Junior Backend Developer")) <= 2


def test_offline_profile_matching_and_legacy_notes():
    analyzer = HeuristicAnalyzer()
    analyzer.job_profile = JobProfile(markdown="Python Docker", primary_roles=["Python Developer"])
    posts = [RawPost(platform="facebook", source="s", text="Hiring Python Developer for remote software work"), RawPost(platform="facebook", source="s", text="Hiring QA tester for onsite product testing")]
    result = analyzer.classify(posts, True, [], "", lambda *args: None)
    assert result[0].job.match_type == "primary" and result[0].job.match_score == 70
    assert result[1].job.match_type == "none" and result[1].job.match_score == 0
    legacy = HeuristicAnalyzer().classify(posts, True, [], "Python", lambda *args: None)
    assert legacy[0].job.match_score == 100
    assert JobInfo().match_type is None and JobInfo().gaps == []


def test_profile_scoring_applies_to_news_runs_and_ignores_ai_score():
    prompts = []

    def complete(system, prompt, schema, effort):
        prompts.append(prompt)
        items = []
        for index in range(prompt.count('<post id=')):
            title = ("Senior Business Analyst" if index == 0 else "SOC Analyst" if index == 1
                     else "Fresher Developer")
            items.append({"id": index, "category": "job", "summary": "Job", "is_job": True,
                          "job": {"match_score": 100, "match_type": "primary", "match_reason": "Location fits",
                                  "title": title, "level": "senior" if index < 2 else "fresher",
                                  "location": "HCM", "years_experience": 4 if index < 2 else 0}})
        return {"items": items}

    analyzer = LLMAnalyzer(SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake")))
    analyzer.job_profile = JobProfile(
        markdown="## Level and years\nJunior developer with 1 year experience\n## Main skills\nPython, React",
        primary_roles=["Junior Full-Stack Developer", "Frontend Developer", "Backend Developer"],
        adjacent_roles=[{"role": "QA Engineer", "reason": "Testing", "enabled": True}],
    )
    posts = [RawPost(platform="facebook", source="s", text=text) for text in (
        "Hiring Senior Business Analyst with 4+ years experience in HCM",
        "Hiring SOC Analyst with senior experience in HCM",
        "Tuyển Fresher Developer tại TP.HCM, có Python",
    )]
    results = analyzer.classify(posts, False, [], "các vùng lân cận HCM, hoặc remote", lambda *a: None)
    assert '"primary_roles": ["Junior Full-Stack Developer", "Frontend Developer", "Backend Developer"]' in prompts[0]
    senior, unrelated, fresher = [post.job for post in results]
    assert senior.match_score < 70 and "level" in senior.constraint_flags
    assert unrelated.match_score < 40 and unrelated.match_type == "primary"
    assert fresher.match_type == "primary"
    assert all("location" not in job.constraint_flags for job in (senior, unrelated, fresher))
    assert senior.match_reason.startswith("Vai trò") and "cấp bậc" in senior.match_reason


def test_primary_role_with_location_conflict_keeps_role_score_and_senior_becomes_stretch():
    prompts = []

    def complete(system, prompt, schema, effort):
        prompts.append(prompt)
        return {"items": [
            {"id": 0, "category": "job", "summary": "Junior backend", "is_job": True,
             "job": {"title": "Junior Backend Developer", "level": "junior", "years_experience": 1,
                     "location": "Hà Nội", "match_type": "primary", "match_score": 100}},
            {"id": 1, "category": "job", "summary": "Senior backend", "is_job": True,
             "job": {"title": "Senior Backend Developer", "level": "senior", "years_experience": 4,
                     "location": "TP.HCM", "match_type": "primary", "match_score": 100}},
        ]}

    analyzer = LLMAnalyzer(SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake")))
    analyzer.job_profile = JobProfile(markdown="## Level and years\nJunior developer, 1 year", primary_roles=["Junior Backend Developer"])
    results = analyzer.classify([
        RawPost(platform="facebook", source="s", text="Hiring junior backend developer at Hanoi"),
        RawPost(platform="facebook", source="s", text="Hiring senior backend developer, 4+ years"),
    ], False, [], "HCM or remote", lambda *a: None)
    junior, senior = [p.job for p in results]
    assert "effective level is junior" in prompts[0]
    assert junior.match_type == "primary" and 20 <= junior.match_score <= 40
    assert "location" in junior.constraint_flags
    assert senior.match_type == "primary" and senior.match_score < 40
    assert "level" in senior.constraint_flags


def test_profile_location_conflict_is_not_applied_to_remote_jobs():
    from feedlens.jobs.scoring import _location_conflict

    assert _location_conflict("HCM or remote", "Hà Nội", "onsite") is True
    assert _location_conflict("HCM or remote", "Hà Nội", "remote") is False
    assert _location_conflict("HCM", "Chưa rõ", "onsite") is False
    assert _location_conflict("HCM", "Q.12, TP.HCM", "onsite") is False
    assert _location_conflict("các vùng lân cận HCM or remote", "Bình Dương", "onsite") is False
    assert _location_conflict("HCM", "Bình Dương", "onsite") is True


def test_score_drops_a_wrong_ai_location_flag_when_the_place_fits():
    from feedlens.jobs.scoring import _score_job

    profile = JobProfile(markdown="", primary_roles=["Backend Developer"])
    fits = JobInfo(title="IT Helpdesk", location="Q.12, TP.HCM", work_mode="onsite", match_type="primary",
                   constraint_flags=["location"])
    assert "location" not in _score_job(fits, profile, "junior", 1, "HCM").constraint_flags
    elsewhere = JobInfo(title="Dev", location="Hà Nội", work_mode="onsite", match_type="primary")
    assert "location" in _score_job(elsewhere, profile, "junior", 1, "HCM").constraint_flags
    unknown = JobInfo(title="Dev", location="Chưa rõ", work_mode="onsite", match_type="primary",
                      constraint_flags=["location"])
    assert "location" in _score_job(unknown, profile, "junior", 1, "HCM").constraint_flags  # code can't tell: keep AI flag


def test_location_extraction_requires_a_recognized_location():
    from feedlens.jobs.scoring import _extract_location

    assert _extract_location("làm việc tại một trong những công ty startup hàng đầu") == ""
    assert "hcm" in _extract_location("📍 Địa điểm: Q.12, TP.HCM")
    assert "ha noi" in _extract_location("Office: Cầu Giấy, Hà Nội")


def test_llm_trusts_semantic_primary_for_variant_role_titles():
    def complete(system, prompt, schema, effort):
        return {"items": [{"id": 0, "category": "job", "summary": "Role", "is_job": True,
                           "job": {"title": "Fullstack Dev (React, Node)", "match_type": "primary",
                                   "match_score": 3, "level": "junior", "years_experience": 1}}]}

    analyzer = LLMAnalyzer(SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake")))
    analyzer.job_profile = JobProfile(markdown="## Main skills\nReact, Node", primary_roles=["Frontend Developer"])
    result = analyzer.classify([RawPost(platform="facebook", source="s", text="Hiring Fullstack Dev (React, Node)")],
                               False, [], "", lambda *a: None)[0].job
    assert result.match_type == "primary" and result.match_score >= 70


def test_profile_level_uses_criteria_then_markdown():
    from feedlens.jobs.scoring import _profile_level

    profile = JobProfile(markdown="## Level and years\nJunior developer with 1 year experience")
    assert _profile_level(profile) == ("junior", 1.0)
    profile.criteria.level = "mid"
    assert _profile_level(profile) == ("mid", 1.0)


def test_heuristic_detects_fresher_as_primary_and_no_profile_has_no_match_label():
    analyzer = HeuristicAnalyzer()
    analyzer.job_profile = JobProfile(markdown="## Level and years\nJunior developer, 1 year", primary_roles=["Junior Backend Developer"])
    raw = [RawPost(platform="facebook", source="group", text="Tuyển Fresher Developer, Python")]
    assert analyzer.classify(raw, False, [], "", lambda *a: None)[0].job.match_type == "primary"
    result = HeuristicAnalyzer().classify(raw, False, [], "", lambda *a: None)[0]
    assert result.job.match_type is None


@pytest.mark.parametrize("allow,enabled,flags,match_type,score", [(False, True, [], "stretch", 20), (True, False, [], "stretch", 20), (True, True, [], "adjacent", 50), (True, True, ["work_mode"], "adjacent", 30)])
def test_profile_once_per_batch_and_code_scored_adjacent_roles(allow, enabled, flags, match_type, score):
    prompts = []
    def complete(system, prompt, schema, effort):
        prompts.append(prompt)
        return {"items": [{"id": i, "category": "job", "summary": "Role", "is_job": True, "job": {"title": "QA", "match_score": 90, "match_type": "adjacent", "gaps": ["Testing experience", "Test plans", "Browser automation", "Extra detail"], "constraint_flags": flags, "match_reason": "Transferable programming"}} for i in range(prompt.count('<post id='))]}
    fake = SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake"))
    analyzer = LLMAnalyzer(fake)
    analyzer.job_profile = JobProfile(markdown="UNIQUE_CV_MARKER Python", allow_adjacent=allow, adjacent_roles=[{"role": "QA", "reason": "API skills", "enabled": enabled}])
    posts = [RawPost(platform="x", source="s", text=f"Hiring QA tester {i}") for i in range(61)]
    result = analyzer.classify(posts, True, [], "RUN_NOTE_MARKER", lambda *args: None)
    assert len(prompts) == 4  # 61 jobs, with checkpoints at most 20 posts apart.
    assert all(p.count("UNIQUE_CV_MARKER") == 1 and p.count("RUN_NOTE_MARKER") == 1 for p in prompts)
    assert all(p.job.match_score == score and p.job.match_type == match_type for p in result)
    assert all(p.job.match_reason.startswith("Vai trò") for p in result)
    assert CLASSIFY_SCHEMA["properties"]["items"]["items"]["properties"]["job"]["properties"]["constraint_flags"]["items"]["enum"] == ["work_mode", "location", "salary", "level"]


@pytest.mark.parametrize("profile_id", ["profile_1", "profile_2"])
def test_job_fixtures_through_pipeline_with_fake_provider(tmp_path, profile_id):
    fixture = json.loads((Path(__file__).with_name("fixtures") / "job-fixtures.json").read_text(encoding="utf8"))
    rows = fixture["fixtures"]
    candidate = next(p for p in fixture["metadata"]["profiles"] if p["id"] == profile_id)
    db = Database(f"sqlite:///{(tmp_path / 'pipeline.db').as_posix()}");uid = db.local_user_id()
    profile = JobProfile(markdown="UNIQUE_PROFILE_" + " ".join(candidate["skills"]), primary_roles=[candidate["primary_role"]], criteria=candidate["criteria"],
                         adjacent_roles=[{"role": r["title"][:120], "reason": "Enabled fixture role", "enabled": True} for r in rows if r["expected_evaluations"][profile_id]["match_type"] == "adjacent"])
    store_profile(db, uid, profile, False)
    def complete(system, prompt, schema, effort):
        if schema is CLASSIFY_SCHEMA:
            assert prompt.count("UNIQUE_PROFILE_") == 1
            items = []
            for i, row in enumerate(rows):
                expected = row["expected_evaluations"][profile_id]
                items.append({"id": i, "category": "job", "summary": row["title"], "is_job": True, "job": {"title": row["title"], "company": row["company"], "match_score": sum(expected["score_range"]) // 2, "match_type": expected["match_type"], "gaps": expected["gaps"], "constraint_flags": expected["constraint_flags"], "match_reason": expected["match_reason"]}})
            return {"items": items}
        return {"overall": "Summary", "categories": [{"category": "job", "summary": "Jobs", "highlights": []}], "action_items": []}
    analyzer = LLMAnalyzer(SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake")))
    req = RunRequest(platform="facebook", job_mode=True, profile="Extra notes", ai_provider="offline")
    rid = db.create_run(req, uid)
    raw = [RawPost(platform="facebook", source=r["source_group"], text=r["raw_text"]) for r in rows]
    pipeline._analyze(db, rid, req, raw, analyzer)
    assert db.get_run(rid, uid)["status"] == "done"
    posts = db.get_posts(rid)
    assert len(posts) == 10
    for post, row in zip(posts, rows):
        expected = row["expected_evaluations"][profile_id]
        assert post.job.match_type in {"primary", "adjacent", "stretch", "none"}
        assert 0 <= post.job.match_score <= 100
        assert post.job.match_reason.startswith("Vai trò")
        if post.job.constraint_flags:
            if "level" in post.job.constraint_flags:
                assert post.job.match_score <= 35
            else:
                assert post.job.match_score <= 100 - sum({"location": 30, "work_mode": 20, "salary": 20}.get(flag, 0) for flag in post.job.constraint_flags)


def test_redaction_removes_unlabelled_contact_lines_but_keeps_experience_dates():
    source = "Backend Developer\n2022 - 2024\n2025 - 2026\n090  123  4567\n123 Main Street\n12 đường Nguyễn Trãi, quận 1\n123 Nguyễn Văn Cừ, P.4, Q.5\n3 years experience\nname@example.test"
    cleaned = redact_contacts(source)
    assert "2022 - 2024" in cleaned and "2025 - 2026" in cleaned
    assert "4567" not in cleaned and "Main Street" not in cleaned and "Nguyễn Trãi" not in cleaned and "@" not in cleaned
    assert "Nguyễn Văn Cừ" not in cleaned and "3 years experience" in cleaned
