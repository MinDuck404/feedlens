from __future__ import annotations

import csv
import io
import json

from .models import CATEGORIES, AnalyzedPost

SEED_FIELDS = ("title", "company", "location", "work_mode", "salary_text", "url", "job_id", "posted_at")


def to_markdown(run: dict, posts: list[AnalyzedPost]) -> str:
    req, d = run["request"], run["digest"]
    lines = [f"# FeedLens — Lượt #{run['id']} ({req['platform']} · {req.get('mode') or req['source_type']})",
             f"_{run['created_at']} · {len(posts)} bài_", ""]
    if req.get("mode"):
        lines += [f"- Mode: {req['mode']}", f"- Options: {json.dumps(req.get('options') or {}, ensure_ascii=False, sort_keys=True)}", ""]
    if d:
        lines += ["## Tổng hợp", d["overall"], ""]
        if d["action_items"]:
            lines += ["### Nên làm"] + [f"- [ ] {a}" for a in d["action_items"]] + [""]
        for c in d["categories"]:
            lines += [f"## {CATEGORIES.get(c['category'], c['category'])} ({c['count']})", c["summary"]]
            lines += [f"- {h}" for h in c["highlights"]] + [""]
    jobs = sorted((p for p in posts if p.job), key=lambda p: -p.job.match_score)
    if not d:
        for p in posts:
            lines += [f"## {p.source}", p.author, "", p.text, "", p.url, ""]
    if jobs:
        lines += ["## Việc làm", "| Điểm | Vị trí | Công ty | Nơi làm | Lương | Liên hệ | Link |",
                  "|---|---|---|---|---|---|---|"]
        for p in jobs:
            j = p.job
            lines.append(f"| {j.match_score} | {j.title} | {j.company} | {j.location} {j.work_mode} | "
                         f"{j.salary} | {j.contact} | {p.url} |")
    seeds = [p for p in posts if p.job_seed]
    if seeds:
        lines += ["", "## Job source data", "| " + " | ".join(SEED_FIELDS) + " |",
                  "| " + " | ".join("---" for _ in SEED_FIELDS) + " |"]
        for p in seeds:
            values = [str(getattr(p.job_seed, key)).replace("|", "\\|").replace("\r", " ").replace("\n", " ") for key in SEED_FIELDS]
            lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def to_csv(posts: list[AnalyzedPost], run: dict | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    req = (run or {}).get("request", {})
    extended = bool(req.get("mode") or any(p.job_seed for p in posts))
    headers = ["category", "source", "author", "summary", "url", "job_title", "company",
               "location", "salary", "work_mode", "contact", "match_score", "text"]
    if extended:
        headers += ["mode", "options"] + [f"job_seed_{key}" for key in SEED_FIELDS]
    w.writerow(headers)
    for p in posts:
        j = p.job
        row = [p.category, p.source, p.author, p.summary, p.url,
                    j.title if j else "", j.company if j else "", j.location if j else "",
                    j.salary if j else "", j.work_mode if j else "", j.contact if j else "",
                    j.match_score if j else "", p.text]
        if extended:
            row += [req.get("mode") or "", json.dumps(req.get("options") or {}, ensure_ascii=False, sort_keys=True)]
            row += [getattr(p.job_seed, key) if p.job_seed else "" for key in SEED_FIELDS]
        w.writerow(row)
    return "﻿" + buf.getvalue()  # BOM để Excel đọc đúng tiếng Việt


def to_json(run: dict, posts: list[AnalyzedPost]) -> str:
    return json.dumps({**run, "posts": [p.model_dump() for p in posts]}, ensure_ascii=False, indent=2)
