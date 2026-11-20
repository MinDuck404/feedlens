"""Capture localized README screenshots from an isolated, offline demo database.

Run after `npm run build` in frontend/:
    python .omc/scripts/capture_readme_assets.py
All names, posts, scores and profiles are fictional fixtures. No AI calls are made.
"""
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DOCS_SHOTS = ROOT / "docs" / "screenshots"
PORT = 8985
ORIGIN = f"http://127.0.0.1:{PORT}"

# Keep synthetic content in the same language as the interface, including job assessments.
COPY = {
    "en": {
        "lang": "en", "locale": "en-US", "new": "New run",
        "groups": ["Product Engineering", "Technology Careers", "Frontend Community"],
        "group_slugs": ["product-engineering", "technology-careers", "frontend-community"],
        "authors": ["Morgan Vale", "Avery Reed", "Robin Hart", "Taylor Brook", "Casey Rowan"],
        "keywords": ["distributed systems", "frontend", "remote", "senior"],
        "tech": "After six months running a news pipeline, our team found the main bottleneck in the processing queue. Separating collection from analysis tripled throughput and made retries predictable.\n\nWe now store each original post before analysis. Small batches and explicit checkpoints let us resume work without collecting the same posts again.",
        "tech_summary": "Separate collection from analysis, save original posts and resume safely with small batches.",
        "design": "Our engineering team replaced long coordination meetings with short design notes. Each note explains the problem, the smallest useful change and a way to check the result.\n\nA shared event log also helps us trace changes across services and recover from failed background tasks.",
        "design_summary": "Short design notes and an event log help teams coordinate asynchronous work.",
        "news": "A fictional survey of product teams explores how a single morning digest protects focus time. Engineers read a concise summary, save useful sources and return to detailed posts when needed.\n\nThe experiment combines technical discussions, career opportunities and practical next steps in one reading list.",
        "news_summary": "A morning digest brings technical discussions and career opportunities into one reading list.",
        "titles": ["Senior Distributed Systems Engineer", "Lead Frontend Engineer"],
        "locations": ["Hanoi · Remote", "Ho Chi Minh City · Hybrid"],
        "salaries": ["$2,400–3,400 / month", "$3,500–4,500 / month"],
        "job_texts": [
            "Nova Labs is hiring a senior distributed systems engineer. Build reliable data pipelines with Python, FastAPI and PostgreSQL. Five years of backend experience required. Fully remote, with equipment and learning support.",
            "Paper Kite Studio is hiring a lead frontend engineer. Shape accessible reading tools with React and TypeScript. Coach a small product team and improve performance. Hybrid schedule, with a learning budget.",
        ],
        "reasons": ["Primary role matches the CV; Python, FastAPI and data pipelines are strong fits.", "Adjacent role; React experience transfers, but team leadership needs more evidence."],
        "gap": "More experience leading a frontend team",
        "overall": "This edition connects practical engineering lessons with two career opportunities. Teams are making data pipelines easier to recover, replacing long meetings with clear design notes and protecting focus time with a daily digest. The job shortlist compares each role with the saved CV and highlights where more experience would help.",
        "category_summaries": ["Two roles with clear salary ranges and flexible work arrangements.", "Two practical notes on reliable data pipelines and asynchronous teamwork.", "One fictional report on a calmer way to follow community news."],
        "actions": ["Review the remote engineering role at Nova Labs.", "Read the guide to resumable data pipelines.", "Update your CV profile before rescoring the job shortlist."],
        "profile": "# Backend engineer\n\nFive years building reliable data pipelines.\n\n- Python, FastAPI, PostgreSQL\n- Distributed systems and automated testing\n- React and TypeScript for internal tools",
        "primary": "Backend Engineer", "adjacent": "Frontend Engineer",
        "adjacent_reason": "React experience can transfer to product interfaces.",
        "progress": "Collection and analysis complete.",
    },
    "vi": {
        "lang": "vi", "locale": "vi-VN", "new": "Lướt mới",
        "groups": ["Kỹ thuật Sản phẩm", "Việc làm Công nghệ", "Cộng đồng Giao diện"],
        "group_slugs": ["ky-thuat-san-pham", "viec-lam-cong-nghe", "cong-dong-giao-dien"],
        "authors": ["Minh An", "Hà Linh", "Thanh Vân", "Bảo Lam", "Khánh Vy"],
        "keywords": ["hệ thống phân tán", "giao diện", "từ xa", "cấp cao"],
        "tech": "Sau sáu tháng vận hành hệ thống đọc tin, nhóm nhận thấy nút thắt chính nằm ở hàng đợi xử lý. Tách việc thu thập khỏi phân tích giúp tăng thông lượng gấp ba và kiểm soát việc thử lại dễ hơn.\n\nNhóm lưu từng bài gốc trước khi phân tích. Chia lô nhỏ và ghi rõ tiến độ giúp tiếp tục công việc mà không phải thu thập lại những bài đã có.",
        "tech_summary": "Tách thu thập khỏi phân tích, lưu bài gốc và tiếp tục an toàn bằng các lô nhỏ.",
        "design": "Nhóm kỹ thuật thay những buổi họp dài bằng ghi chú thiết kế ngắn. Mỗi ghi chú nêu vấn đề, thay đổi nhỏ nhất có ích và cách kiểm tra kết quả.\n\nNhật ký sự kiện dùng chung cũng giúp theo dõi thay đổi giữa các dịch vụ và khôi phục tác vụ chạy nền khi có lỗi.",
        "design_summary": "Ghi chú thiết kế ngắn và nhật ký sự kiện giúp phối hợp công việc bất đồng bộ.",
        "news": "Một khảo sát giả lập về các nhóm sản phẩm tìm hiểu cách bản tin buổi sáng bảo vệ thời gian tập trung. Kỹ sư đọc tóm tắt ngắn, lưu nguồn hữu ích và quay lại bài chi tiết khi cần.\n\nThử nghiệm gộp thảo luận kỹ thuật, cơ hội nghề nghiệp và việc cần làm vào cùng một danh sách đọc.",
        "news_summary": "Bản tin buổi sáng gộp thảo luận kỹ thuật và cơ hội nghề nghiệp vào một danh sách đọc.",
        "titles": ["Kỹ sư Hệ thống Phân tán Cấp cao", "Trưởng nhóm Kỹ thuật Giao diện"],
        "locations": ["Hà Nội · Từ xa", "TP. Hồ Chí Minh · Kết hợp"],
        "salaries": ["60–85 triệu đồng / tháng", "85–110 triệu đồng / tháng"],
        "job_texts": [
            "Nova Labs tuyển kỹ sư hệ thống phân tán cấp cao. Xây dựng đường ống dữ liệu tin cậy bằng Python, FastAPI và PostgreSQL. Yêu cầu năm năm kinh nghiệm phát triển hệ thống. Làm việc từ xa hoàn toàn, hỗ trợ thiết bị và học tập.",
            "Paper Kite Studio tuyển trưởng nhóm kỹ thuật giao diện. Xây dựng công cụ đọc tin dễ tiếp cận bằng React và TypeScript. Hướng dẫn nhóm sản phẩm nhỏ, cải thiện hiệu năng. Làm việc kết hợp, có ngân sách học tập.",
        ],
        "reasons": ["Đúng vai trò trong CV; phù hợp kỹ năng Python, FastAPI và đường ống dữ liệu.", "Ngành gần; có thể chuyển kỹ năng React, cần thêm kinh nghiệm dẫn dắt nhóm."],
        "gap": "Kinh nghiệm dẫn dắt nhóm giao diện",
        "overall": "Bản tin kết nối bài học kỹ thuật thực tế với hai cơ hội nghề nghiệp. Các nhóm đang cải thiện khả năng khôi phục đường ống dữ liệu, thay họp dài bằng ghi chú thiết kế rõ ràng và bảo vệ thời gian tập trung bằng bản tin hằng ngày. Danh sách việc làm đối chiếu từng vai trò với CV đã lưu và chỉ ra kinh nghiệm cần bổ sung.",
        "category_summaries": ["Hai vị trí có khoảng lương rõ ràng và hình thức làm việc linh hoạt.", "Hai chia sẻ về đường ống dữ liệu tin cậy và phối hợp bất đồng bộ.", "Một báo cáo giả lập về cách theo dõi tin cộng đồng nhẹ nhàng hơn."],
        "actions": ["Xem vị trí kỹ sư làm việc từ xa tại Nova Labs.", "Đọc hướng dẫn xây dựng đường ống dữ liệu có thể tiếp tục.", "Cập nhật hồ sơ CV trước khi chấm lại danh sách việc làm."],
        "profile": "# Kỹ sư phát triển hệ thống\n\nNăm năm xây dựng đường ống dữ liệu tin cậy.\n\n- Python, FastAPI, PostgreSQL\n- Hệ thống phân tán và kiểm thử tự động\n- React và TypeScript cho công cụ nội bộ",
        "primary": "Kỹ sư phát triển hệ thống", "adjacent": "Kỹ sư giao diện",
        "adjacent_reason": "Kinh nghiệm React có thể áp dụng cho giao diện sản phẩm.",
        "progress": "Đã thu thập và phân tích xong.",
    },
    "zh-CN": {
        # The app's stored language code is zh, while the README directory is zh-CN.
        "lang": "zh", "locale": "zh-CN", "new": "新建浏览",
        "groups": ["产品工程社区", "科技职业机会", "前端技术社区"],
        "group_slugs": ["产品工程社区", "科技职业机会", "前端技术社区"],
        "authors": ["林知远", "陈若宁", "周书禾", "许安澜", "叶星言"],
        "keywords": ["分布式系统", "前端", "远程", "高级"],
        "tech": "新闻处理系统运行六个月后，团队发现主要瓶颈在任务队列。将内容采集与分析分开，吞吐量提高了三倍，失败后的重试也更加可控。\n\n现在，每条原始帖子都会先保存，再进入分析。通过小批量处理和明确的进度记录，任务可以从中断处继续，无需重复采集。",
        "tech_summary": "采集与分析分开，先保存原文，再通过小批量处理安全续跑。",
        "design": "工程团队用简短的设计说明代替漫长的协调会议。每份说明都写清问题、最小有效改动以及验证结果的方法。\n\n共享事件日志还帮助团队追踪服务之间的变化，并在后台任务失败后恢复工作。",
        "design_summary": "简短的设计说明和事件日志，让异步协作更清晰。",
        "news": "一项虚构的产品团队调查，探讨早间摘要如何保护专注时间。工程师先读简要总结，保存有用来源，需要时再回看详细帖子。\n\n这项演示将技术讨论、职业机会和下一步行动整合到同一份阅读清单中。",
        "news_summary": "早间摘要把技术讨论和职业机会整理到同一份阅读清单中。",
        "titles": ["高级分布式系统工程师", "前端技术负责人"],
        "locations": ["河内 · 远程", "胡志明市 · 混合办公"],
        "salaries": ["每月 2,400–3,400 美元", "每月 3,500–4,500 美元"],
        "job_texts": [
            "Nova Labs 招聘高级分布式系统工程师。使用 Python、FastAPI 和 PostgreSQL 构建可靠的数据流水线。要求五年后端经验。支持完全远程办公，并提供设备和学习补贴。",
            "Paper Kite Studio 招聘前端技术负责人。使用 React 和 TypeScript 构建无障碍阅读工具，指导小型产品团队并优化性能。采用混合办公，提供学习预算。",
        ],
        "reasons": ["符合简历中的主要方向；Python、FastAPI 和数据流水线经验匹配。", "属于相邻方向；React 经验可迁移，但还需补充团队带领经验。"],
        "gap": "带领前端团队的经验",
        "overall": "本期把实用的工程经验与两个职业机会联系起来。团队正在改进数据流水线的恢复能力，用清晰的设计说明代替长会议，并通过每日摘要保护专注时间。职位清单将每个岗位与已保存的简历档案进行比较，同时指出仍需补充的经验。",
        "category_summaries": ["两个薪资范围明确、办公方式灵活的职位。", "两篇关于可靠数据流水线与异步协作的实践分享。", "一份关于轻松关注社区资讯的虚构报告。"],
        "actions": ["查看 Nova Labs 的远程工程师职位。", "阅读可续跑数据流水线的实践指南。", "更新简历档案，再为职位清单重新评分。"],
        "profile": "# 后端工程师\n\n五年可靠数据流水线开发经验。\n\n- Python、FastAPI、PostgreSQL\n- 分布式系统与自动化测试\n- 使用 React 和 TypeScript 开发内部工具",
        "primary": "后端工程师", "adjacent": "前端工程师",
        "adjacent_reason": "React 经验可用于产品界面开发。",
        "progress": "采集与分析已完成。",
    },
}


def seed_demo(api, folder):
    from feedlens.job_profile import JobProfile, store_profile
    from feedlens.models import AnalyzedPost, CategoryDigest, Digest, JobInfo, RunRequest

    c = COPY[folder]
    db = api.app.state.db
    uid = db.local_user_id()
    for run in db.list_runs(uid):
        db.delete_run(run["id"], uid)
    posts = []
    for index, (category, text, summary) in enumerate([
        ("tech", c["tech"], c["tech_summary"]),
        ("job", c["job_texts"][0], c["titles"][0]),
        ("job", c["job_texts"][1], c["titles"][1]),
        ("tech", c["design"], c["design_summary"]),
        ("news", c["news"], c["news_summary"]),
    ]):
        job_index = index - 1
        job = JobInfo(
            title=c["titles"][job_index], company=["Nova Labs", "Paper Kite Studio"][job_index],
            location=c["locations"][job_index], salary=c["salaries"][job_index],
            work_mode=["remote", "hybrid"][job_index], contact="careers@example.com",
            match_score=[95, 76][job_index], match_reason=c["reasons"][job_index],
            match_type=["primary", "adjacent"][job_index],
            gaps=[] if job_index == 0 else [c["gap"]],
        ) if category == "job" else None
        posts.append(AnalyzedPost(
            platform="facebook", source=c["groups"][1 if category == "job" else 0],
            author=c["authors"][index], text=text, summary=summary, category=category,
            url=f"https://example.com/{folder}/posts/{index + 1}", job=job,
            posted_at="2026-11-20T08:00:00Z", analyzed_by="gemini",
        ))
    digest = Digest(overall=c["overall"], action_items=c["actions"], categories=[
        CategoryDigest(category=category, count=count, summary=c["category_summaries"][i], highlights=highlights)
        for i, (category, count, highlights) in enumerate([
            ("job", 2, [f"{c['titles'][j]} · {c['salaries'][j]}" for j in range(2)]),
            ("tech", 2, [c["tech_summary"], c["design_summary"]]),
            ("news", 1, [c["news_summary"]]),
        ])
    ])
    sources = [f"https://example.com/groups/{quote(slug)}" for slug in c["group_slugs"]]
    req = RunRequest(platform="facebook", mode="group", sources=sources[:2], count=40,
                     language=c["lang"], job_mode=True, keywords=c["keywords"], ai_provider="gemini")
    rid = db.create_run(req, uid, status="done")
    db.save_raw_posts(rid, posts)
    db.save_posts(rid, posts)
    db.update_run(rid, ai_label="Gemini", digest=digest, created_at=datetime(2026, 11, 20, 8, tzinfo=timezone.utc))
    api.PROGRESS.clear()
    api.PROGRESS[rid] = {"phase": "done", "message": c["progress"], "done": 5, "target": 5}
    store_profile(db, uid, JobProfile(
        markdown=c["profile"], primary_roles=[c["primary"]],
        adjacent_roles=[{"role": c["adjacent"], "reason": c["adjacent_reason"]}],
        criteria={"work_modes": ["remote", "hybrid"], "locations": [c["locations"][0].split(" · ")[0]],
                  "min_salary": 60_000_000 if folder == "vi" else 2000,
                  "currency": "VND" if folder == "vi" else "USD", "level": "senior"},
    ), encrypted=False)
    db.set_preferences(uid, {
        "composer": {"platform": "facebook", "mode": "group", "source_type": "group", "job_mode": True,
                     "keywords_text": ", ".join(c["keywords"]), "ai_provider": "offline"},
        "saved_sources": {"facebook:group": [{"url": url, "name": name, "enabled": True}
                                            for url, name in zip(sources, c["groups"])]},
    })
    # Platform profiles for sidebar (all 4 platforms connected cleanly).
    for platform in ["facebook", "linkedin", "x", "reddit"]:
        api.browser.profile_dir(platform).mkdir(parents=True, exist_ok=True)
        api._session_cache[platform] = True
    api._login_state.clear()
    assert db.analysis_counts(rid) == {"ai": 5, "offline": 0, "pending": 0, "total": 5}
    return rid


def compress_image(raw_bytes, target_viewport, target_kb=400):
    im = Image.open(io.BytesIO(raw_bytes))
    w, h = target_viewport
    if im.size != (w, h):
        im = im.resize((w, h), Image.Resampling.LANCZOS)

    if im.mode in ("RGBA", "P"):
        # Convert transparent background to RGB white or paper color.
        background = Image.new("RGB", im.size, (250, 247, 240))
        if im.mode == "RGBA":
            background.paste(im, mask=im.split()[3])
        else:
            background.paste(im)
        im = background

    # First attempt: standard PNG optimization.
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    if len(buf.getvalue()) <= target_kb * 1024:
        return buf.getvalue()
    # Adaptive quantization preserves crisp text edges.
    for colors in (256, 128):
        buf = io.BytesIO()
        im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).save(buf, format="PNG", optimize=True)
        if len(buf.getvalue()) <= target_kb * 1024:
            return buf.getvalue()
    raise AssertionError("Screenshot exceeds 400 KiB")


def capture(api, browser, folder):
    rid = seed_demo(api, folder)
    c = COPY[folder]
    targets = [
        ("hero-digest-light.png", "digest", "light", (1440, 1000)),
        ("posts-dark.png", "posts", "dark", (1440, 1000)),
        ("jobs-light.png", "jobs", "light", (1440, 1000)),
        ("composer-light.png", "composer", "light", (1440, 1000)),
        ("mobile-dark.png", "posts", "dark", (390, 1000)),
    ]
    output = DOCS_SHOTS / folder
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name, tab, theme, viewport in targets:
        with browser.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                                 device_scale_factor=2, locale=c["locale"], timezone_id="Asia/Ho_Chi_Minh",
                                 color_scheme=theme, reduced_motion="reduce", service_workers="block") as context:
            # No fixture can navigate to a live platform, load remote assets or call a paid AI.
            context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(ORIGIN + "/") else route.abort())
            context.add_init_script(f"localStorage.setItem('feedlens.lang', {json.dumps(c['lang'])}); localStorage.setItem('feedlens.theme', {json.dumps(theme)});")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
            page.goto(f"{ORIGIN}/#/runs/{rid}/{tab if tab != 'composer' else 'digest'}", wait_until="networkidle")
            page.locator("main h1").wait_for()
            if tab == "composer":
                page.get_by_role("button", name=c["new"], exact=True).first.click()
                page.get_by_role("dialog").wait_for()
                page.wait_for_load_state("networkidle")
            elif tab in ("jobs", "posts"):
                page.locator("main li" if tab == "jobs" else "main article").first.wait_for()
            else:
                page.get_by_text(c["overall"], exact=True).wait_for()
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(500)
            # Route effects can focus the posts panel and leave its focus ring in screenshots.
            # Reset viewport and focus after effects settle so mobile header remains clean.
            page.evaluate("""() => {
                document.activeElement?.blur();
                document.querySelectorAll('main, main *').forEach(el => { if (el.scrollTop) el.scrollTop = 0; });
                window.scrollTo(0, 0);
            }""")
            page.wait_for_timeout(100)
            assert page.locator("html").get_attribute("lang") == ("zh-CN" if folder == "zh-CN" else folder)
            busy = page.locator("[role=alert]:visible, .animate-spin:visible, [aria-busy=true]:visible, .skeleton:visible")
            assert not busy.count(), busy.evaluate_all("els => els.map(el => ({html: el.outerHTML, text: el.innerText}))")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Horizontal overflow: {folder}/{name}"
            assert not errors, errors
            text = page.locator("body").inner_text()
            if folder == "en":
                assert not re.search(r"[\u3400-\u9fff\u1ea0-\u1ef9đĐ]", text), text
            elif folder == "vi":
                assert not re.search(r"[\u3400-\u9fff]", text), text
            else:
                assert not re.search(r"[\u1ea0-\u1ef9đĐ]", text), text
            png = compress_image(page.screenshot(full_page=False), viewport)
            (output / name).write_bytes(png)
            inventory.append({"file": f"{folder}/{name}", "bytes": len(png), "width": viewport[0], "height": viewport[1]})
            print(f"{folder}/{name}: {len(png) / 1024:.1f} KiB", flush=True)
    return inventory


def main():
    assert (ROOT / "frontend/dist/index.html").is_file(), "Build frontend first"
    DOCS_SHOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="feedlens-readme-") as data_dir:
        # Set every sensitive setting before importing the app; never touch real data or profiles.
        os.environ.update(FEEDLENS_MODE="local", FEEDLENS_DATA_DIR=data_dir,
                          DATABASE_URL=f"sqlite:///{Path(data_dir).as_posix()}/feedlens.db",
                          FEEDLENS_SECRET="fictional-readme-fixture-only", FEEDLENS_AI_PROVIDER="offline")
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
            os.environ[key] = ""
        sys.path.insert(0, str(ROOT / "backend"))
        from feedlens import api
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=PORT, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.1)
            assert server.started, "Demo server did not start"
            inventory = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    for folder in COPY:
                        inventory.extend(capture(api, browser, folder))
                finally:
                    browser.close()
            assert len(inventory) == 15
            print("Captured 15 localized screenshots; layout, language and error checks passed.", flush=True)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            api.app.state.db.engine.dispose()


if __name__ == "__main__":
    main()
