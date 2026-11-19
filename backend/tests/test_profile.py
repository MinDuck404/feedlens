import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from feedlens import api, pipeline
from feedlens.analyzer import CLASSIFY_SCHEMA, HeuristicAnalyzer, LLMAnalyzer
from feedlens.db import Database
from feedlens.job_profile import (MAX_CV_BYTES, CV_SCHEMA, JobProfile, ProfileError, analyze_cv, extract_cv_pdf,
                                  load_profile, redact_contacts, relevant_roles, store_profile)
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
    user = api.db().get_user_by_email("cv-a@example.test")
    payload = api.db().get_job_profile(user.id)
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
    assert result[0].job.match_type == "primary" and result[0].job.match_score == 50
    assert result[1].job.match_type == "none" and result[1].job.match_score == 0
    legacy = HeuristicAnalyzer().classify(posts, True, [], "Python", lambda *args: None)
    assert legacy[0].job.match_score == 100
    assert JobInfo().match_type is None and JobInfo().gaps == []


@pytest.mark.parametrize("allow,enabled,flags,score", [(False, True, [], 40), (True, False, [], 40), (True, True, [], 80), (True, True, ["work_mode"], 65)])
def test_profile_once_per_batch_and_adjacent_cap(allow, enabled, flags, score):
    prompts = []
    def complete(system, prompt, schema, effort):
        prompts.append(prompt)
        return {"items": [{"id": i, "category": "job", "summary": "Role", "is_job": True, "job": {"title": "QA", "match_score": 90, "match_type": "adjacent", "gaps": ["Testing experience", "Test plans", "Browser automation", "Extra detail"], "constraint_flags": flags, "match_reason": "Transferable programming"}} for i in range(prompt.count('<post id='))]}
    fake = SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake"))
    analyzer = LLMAnalyzer(fake)
    analyzer.job_profile = JobProfile(markdown="UNIQUE_CV_MARKER Python", allow_adjacent=allow, adjacent_roles=[{"role": "QA", "reason": "API skills", "enabled": enabled}])
    posts = [RawPost(platform="x", source="s", text=f"Hiring QA tester {i}") for i in range(61)]
    result = analyzer.classify(posts, True, [], "RUN_NOTE_MARKER", lambda *args: None)
    assert len(prompts) == 2
    assert all(p.count("UNIQUE_CV_MARKER") == 1 and p.count("RUN_NOTE_MARKER") == 1 for p in prompts)
    assert all(p.job.match_score == score and p.job.match_type == "adjacent" for p in result)
    assert all(p.job.gaps == ["Testing experience", "Test plans", "Browser automation"] for p in result)
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
        assert post.job.match_type == expected["match_type"]
        assert post.job.gaps == expected["gaps"]
        assert post.job.constraint_flags == expected["constraint_flags"]
        assert 0 <= post.job.match_score <= 100
        assert expected["score_range"][0] <= post.job.match_score <= expected["score_range"][1]
        if post.job.constraint_flags:
            assert post.job.match_score <= max(0, 100 - 35 * len(post.job.constraint_flags))


def test_redaction_removes_unlabelled_contact_lines_but_keeps_experience_dates():
    source = "Backend Developer\n2022 - 2024\n2025 - 2026\n090  123  4567\n123 Main Street\n12 đường Nguyễn Trãi, quận 1\n123 Nguyễn Văn Cừ, P.4, Q.5\n3 years experience\nname@example.test"
    cleaned = redact_contacts(source)
    assert "2022 - 2024" in cleaned and "2025 - 2026" in cleaned
    assert "4567" not in cleaned and "Main Street" not in cleaned and "Nguyễn Trãi" not in cleaned and "@" not in cleaned
    assert "Nguyễn Văn Cừ" not in cleaned and "3 years experience" in cleaned
