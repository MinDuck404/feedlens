import csv
import io
import json

from feedlens.runs.export import to_csv
from feedlens.runs.export import to_json
from feedlens.runs.export import to_markdown
from feedlens.models import AnalyzedPost, JobInfo, JobSeed


def sample(mode=True):
    request = {"platform": "linkedin", "source_type": "search", "sources": ["Python"]}
    if mode:
        request.update(mode="jobs", options={"keywords": "Python", "location": "Hà Nội"})
    return {"id": 1, "created_at": "2026-11-17", "request": request, "digest": None}


def test_new_mode_exports_preserve_request_and_observed_seed():
    seed = JobSeed(title="Python | Developer", company="Acme", location="Hà Nội", work_mode="remote",
                   salary_text="30–40M", url="https://www.linkedin.com/jobs/view/123/", job_id="123", posted_at="Today")
    posts = [AnalyzedPost(platform="linkedin", source="Python", text="Original description", category="job",
                          job_seed=seed, job=JobInfo(title="Python", match_score=80))]
    run = sample()
    raw_json = json.loads(to_json(run, posts))
    assert raw_json["request"]["mode"] == "jobs" and raw_json["request"]["options"]["location"] == "Hà Nội"
    assert raw_json["posts"][0]["job_seed"] == seed.model_dump()
    rows = list(csv.DictReader(io.StringIO(to_csv(posts, run).lstrip("\ufeff"))))
    assert rows[0]["mode"] == "jobs" and json.loads(rows[0]["options"]) == run["request"]["options"]
    assert rows[0]["job_seed_company"] == "Acme" and rows[0]["job_seed_url"] == seed.url
    assert rows[0]["job_seed_salary_text"] == "30–40M" and rows[0]["match_score"] == "80"
    md = to_markdown(run, posts)
    assert "linkedin · jobs" in md and "- Mode: jobs" in md and '"location": "Hà Nội"' in md
    assert "Python \\| Developer" in md and seed.url in md and "Job source data" in md


def test_legacy_csv_and_markdown_format_is_unchanged():
    p = AnalyzedPost(platform="linkedin", source="s", author="A", text="Original", summary="Summary")
    expected_csv = "\ufeffcategory,source,author,summary,url,job_title,company,location,salary,work_mode,contact,match_score,text\r\nother,s,A,Summary,,,,,,,,,Original\r\n"
    assert to_csv([p]) == expected_csv
    assert to_csv([p], sample(False)) == expected_csv
    assert to_markdown(sample(False), [p]) == "# FeedLens — Lượt #1 (linkedin · search)\n_2026-11-17 · 1 bài_\n\n## s\nA\n\nOriginal\n\n\n"
    assert "mode" not in json.loads(to_json(sample(False), [p]))["request"]


def test_seed_columns_are_available_without_ai_and_rows_without_seed_stay_aligned():
    seed = JobSeed(title="Original role", job_id="42")
    posts = [AnalyzedPost(platform="linkedin", source="s", text="Card", job_seed=seed),
             AnalyzedPost(platform="linkedin", source="s", text="Another card")]
    rows = list(csv.DictReader(io.StringIO(to_csv(posts, sample()).lstrip("\ufeff"))))
    assert rows[0]["job_seed_title"] == "Original role" and rows[1]["job_seed_title"] == ""
    assert all(None not in row for row in rows)
    assert "Original role" in to_markdown(sample(), posts)
