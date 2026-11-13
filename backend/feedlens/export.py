from __future__ import annotations

import csv
import io
import json

from .models import CATEGORIES, AnalyzedPost


def to_markdown(run: dict, posts: list[AnalyzedPost]) -> str:
    req, d = run["request"], run["digest"]
    lines = [f"# FeedLens — Lượt #{run['id']} ({req['platform']} · {req['source_type']})",
             f"_{run['created_at']} · {len(posts)} bài_", ""]
    if d:
        lines += ["## Tổng hợp", d["overall"], ""]
        if d["action_items"]:
            lines += ["### Nên làm"] + [f"- [ ] {a}" for a in d["action_items"]] + [""]
        for c in d["categories"]:
            lines += [f"## {CATEGORIES.get(c['category'], c['category'])} ({c['count']})", c["summary"]]
            lines += [f"- {h}" for h in c["highlights"]] + [""]
    jobs = sorted((p for p in posts if p.job), key=lambda p: -p.job.match_score)
    if jobs:
        lines += ["## Việc làm", "| Điểm | Vị trí | Công ty | Nơi làm | Lương | Liên hệ | Link |",
                  "|---|---|---|---|---|---|---|"]
        for p in jobs:
            j = p.job
            lines.append(f"| {j.match_score} | {j.title} | {j.company} | {j.location} {j.work_mode} | "
                         f"{j.salary} | {j.contact} | {p.url} |")
    return "\n".join(lines)


def to_csv(posts: list[AnalyzedPost]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category", "source", "author", "summary", "url", "job_title", "company",
                "location", "salary", "work_mode", "contact", "match_score", "text"])
    for p in posts:
        j = p.job
        w.writerow([p.category, p.source, p.author, p.summary, p.url,
                    j.title if j else "", j.company if j else "", j.location if j else "",
                    j.salary if j else "", j.work_mode if j else "", j.contact if j else "",
                    j.match_score if j else "", p.text])
    return "﻿" + buf.getvalue()  # BOM để Excel đọc đúng tiếng Việt


def to_json(run: dict, posts: list[AnalyzedPost]) -> str:
    return json.dumps({**run, "posts": [p.model_dump() for p in posts]}, ensure_ascii=False, indent=2)
