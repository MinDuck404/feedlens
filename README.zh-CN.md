<div align="center">

[English](README.md) · [Tiếng Việt](README.vi.md) · **简体中文**

# FeedLens

**少读一点，多知道一点。**

FeedLens 用你自己的登录会话浏览社交网络的动态、群组和搜索结果。
随后由 AI 对帖子分类、按主题生成摘要，并根据你的简历挑出合适的工作，以报纸的版式呈现，方便阅读。

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![React + Vite](https://img.shields.io/badge/react-vite-61DAFB?logo=react&logoColor=black)](frontend/)
[![AI: Claude · ChatGPT · Gemini](https://img.shields.io/badge/AI-Claude%20·%20ChatGPT%20·%20Gemini-AE3824)](#选择-ai)
[![License: MIT](https://img.shields.io/badge/license-MIT-16120E)](LICENSE)

[快速开始](#快速开始) · [功能](#功能) · [工作原理](#工作原理) · [选择 AI](#选择-ai) · [云端自建](#云端自建) · [注意事项](#注意事项)

<img src="docs/screenshots/zh-CN/hero-digest-light.png" alt="一次浏览的摘要页，采用报纸版式" width="900">

</div>

## 为什么做 FeedLens

[路线图（英文）](ROADMAP.md) · [贡献指南（英文）](CONTRIBUTING.md) · [测试指南（越南语 / 英语）](docs/TESTING.md#english)

招聘群、社区群和信息流每天有成百上千条帖子，大部分是广告、梗图和重复内容。FeedLens 替你读完，给你一份简短的报纸：哪些值得看、哪些工作适合你，需要时一键打开原帖。一切都在你自己的电脑上、用你自己的浏览器和账号运行。

## 功能

| | |
|---|---|
| **4 个平台** | Facebook、LinkedIn、X (Twitter)、Reddit：动态、群组或搜索结果 |
| **报纸式摘要** | 帖子按类型分组（招聘、科技、新闻、二手买卖……），每类有单独摘要，另有一版头版总结 |
| **我的主题** | 自定义最多 12 个专属追踪主题；AI 仅在帖子确切切题时打上标签；报纸顶部专设“我的主题”版块（即使 0 条帖子的主题也会展示）；可随时为历史浏览重新打标签 |
| **提问与搜索** | 对已保存帖子进行全文检索，支持结构化筛选（分类、主题、日期、招聘：远程/薪资/地点/分数、GitHub 链接）；向 AI 提问时给出附带核验引文 [#id] 的回答，精准指向真实帖子，无匹配时明确说明 |
| **内容趋势** | 按分类或主题统计 7/30/90 天的帖子量（按天或按周），并与上一周期对比；点击图表数据点可直接进入提问与搜索查看对应帖子 |
| **按简历匹配工作** | 上传一次 PDF 简历；AI 按职位、级别、工作方式（远程/混合/现场）、地点和薪资为每条招聘打 0–100 分，并推荐相近岗位（如初级开发 → IT 技术支持），列出欠缺的技能 |
| **AI 出错也不丢帖子** | 帖子在 AI 分析之前就已保存；修好 key 后点"重新分析"即可，无需重新浏览 |
| **自选 AI** | Claude、ChatGPT、Gemini；没有 key 时使用离线关键词分类 |
| **本地运行** | 会话保存在独立的 Chrome 配置中，数据存于 SQLite；只有帖子文本会发送给你选择的 AI |
| **3 种语言** | 界面和摘要支持 中文、English、Tiếng Việt（默认跟随浏览器） |
| **浅色 / 深色** | 白天是米色纸张，夜晚是深色木桌；跟随系统，或在侧栏切换 |

<table>
  <tr>
    <td width="62%"><img src="docs/screenshots/zh-CN/posts-dark.png" alt="深色模式下的帖子列表"></td>
    <td width="38%"><img src="docs/screenshots/zh-CN/mobile-dark.png" alt="手机界面"></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/zh-CN/jobs-light.png" alt="带匹配分数的工作标签页"></td>
    <td><img src="docs/screenshots/zh-CN/composer-light.png" alt="新建浏览面板"></td>
  </tr>
</table>

## 快速开始

只需要 **Google Chrome**。如果没有 Python，启动脚本会自动安装 [uv](https://docs.astral.sh/uv/)，uv 会自带 Python。

1. 从 [Releases](https://github.com/MinDuck404/feedlens/releases/latest) 下载 `FeedLens-<版本>.zip` 并解压。其中已包含构建好的界面，无需 Node.js。
   （如果使用 `git clone` 或 **Code → Download ZIP**，首次运行还需要 [Node.js LTS](https://nodejs.org) 来构建界面。）
2. **Windows：** 双击 `start.bat`。**macOS/Linux：** 运行 `./start.sh`。
   首次运行需要几分钟安装 Python 和依赖，之后浏览器会自动打开 http://127.0.0.1:8765。
3. 点击 Facebook 旁的**登录**（手机上先打开 ☰ 菜单）。会弹出一个 Chrome 窗口，照常登录（包括两步验证），完成后窗口自动关闭。
4. **设置**（齿轮）→ **API key** 标签：添加 Gemini、ChatGPT 或 Claude 的 key。没有 key 时使用关键词匹配。
5. 在找工作？打开**求职档案**标签：上传简历，检查摘要，选择求职条件和愿意尝试的岗位。
6. （可选）**主题**标签：创建最多 12 个个人追踪主题，自定义关键词与主题颜色。
7. 点击**新建浏览**，选择动态或群组，再点**开始浏览**。

关闭终端窗口（或按 Ctrl+C）即可停止。

> 想先用示例数据看看界面：`cd backend && .venv\Scripts\feedlens demo`。

## 工作原理

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/zh-CN/how-it-works-dark.svg">
  <img src="docs/diagrams/zh-CN/how-it-works.svg" alt="你的 Chrome 浏览帖子，原始帖子存入 SQLite，AI 分类并摘要，最后生成报纸">
</picture>

- **浏览：** 用 FeedLens 专属配置打开真实的 Chrome 窗口，像人一样滚动。*快速*模式每次停约 1 秒；*谨慎*模式更慢。
- **多个群组：** 保存群组列表，勾选要浏览的群。"帖子数"按**每个群**计算；单次上限为 `FEEDLENS_MAX_POSTS`（默认 500）。出错的群会被跳过。
- **验证 / 检查点：** 如果平台要求重新登录，程序会暂停，最多等待 10 分钟让你在 Chrome 窗口中完成。
- **AI：** 最多 4 批并行，每批 20 条。所有服务商使用同一个 JSON schema，结果格式一致。
- **AI 中途出错：** 原始帖子已在数据库中。该次浏览会显示错误原因，可查看和下载原始帖子（.json/.md），并可用其他 key 或模型**重新分析**。

### 按简历匹配工作

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/zh-CN/cv-matching-dark.svg">
  <img src="docs/diagrams/zh-CN/cv-matching.svg" alt="PDF 简历在本地提取文字，AI 生成 Markdown 档案，再用它为每条招聘打分">
</picture>

- PDF 文字在本机提取（`pypdf`）。AI 将其转为 Markdown 档案，并去掉电话、邮箱和住址。**PDF 文件本身不会被保存。**
- 求职条件由你自己设定（远程/混合/现场、地点、最低薪资、级别），相近岗位可逐个开启。
- 每条招聘都有 **专业匹配 / 相近岗位 / 挑战岗位** 标签、理由、欠缺技能，以及违反条件时的提醒。服务器会限制分数：违反 1 项条件最高 65 分，2 项最高 30 分；相近岗位最高 80 分，未开启时最高 40 分。
- 档案每批 20 条只发送一次，而不是每条都发。

### 询问 AI 与本地知识库检索

- **将自然语言理解为结构化筛选：** AI 将你的自然语言提问解析为精确的结构化筛选条件（日期范围、平台、分类、主题、求职约束）。
- **先在本地检索：** 后端在本地 SQLite 数据库中通过全文检索（FTS5）找出最多 40 条最相关的候选帖子。
- **依据真实帖子生成引文回答：** 若有匹配帖子，AI 结合帖子内容提炼简要回答，并使用 `[#id]` 严格标注真实来源。任何编造的 ID 都会被自动剔除。
- **零匹配直接返回：** 如果本地没有检索到匹配帖子，系统会立即返回未找到结果的提示，不进行二次无效 AI 调用。
- **精简数据传输：** 仅将问题和匹配帖子的精简摘要发送给 AI；你的整个数据库永远不会被完整上传。

## 选择 AI

| 服务商 | 获取 key | 指定模型（本地） |
|---|---|---|
| Claude | console.anthropic.com | `ANTHROPIC_MODEL` |
| ChatGPT | platform.openai.com | `OPENAI_MODEL` |
| Gemini | aistudio.google.com | `GEMINI_MODEL` |

- "新建浏览"中的模型列表直接用你的 key 从服务商 API 获取（缓存 10 分钟，可手动刷新）。
- 选"默认"时，若你的 key 可用，则使用 `gemini-3.5-flash-lite` / `gpt-5-mini` / `claude-opus-5-5`，否则使用最新的快速模型。遇到 429/5xx 会重试 3 次（3 秒、6 秒、12 秒），再切换到下一个模型。
- 兼容 OpenAI 的服务（OpenRouter、LM Studio……）：设置 `OPENAI_BASE_URL`（仅本地）。
- 新增服务商：继承 `AIProvider`，实现 `complete_json()` 和 `list_models()`，并在 `ai/registry.py` 中注册。

## 注意事项

> [!WARNING]
> 自动浏览**违反** Facebook、LinkedIn 和 X 的服务条款，账号可能被要求验证。请仅限个人、小规模使用，并考虑使用小号。

- FeedLens **只读**：不发帖、不评论、不私信。密码永远不经过本应用。
- 默认在可见的 Chrome 窗口中运行。无头模式常被拦截（Reddit 会拦截未登录的无头浏览器）。FeedLens 不会尝试绕过反爬机制。
- 帖子内容会发送给你选择的 AI 服务商。`backend/data/` 中有会话 cookie：**切勿分享或提交**。
- 社交网站经常改版。若某平台返回 0 条帖子，请修改 `backend/feedlens/scrapers.py` 中对应的 JS。

## 常见问题

**没有 AI key 能用吗？**
可以。帖子由离线关键词分类。此时没有 AI 摘要，工作分数只按匹配的关键词数计算。

**一次浏览要多久？**
取决于帖子数量和速度设置。*快速*模式每次滚动约停 1 秒，另加 AI 每批 20 条的处理时间。

**某个平台返回 0 条帖子？**
通常是网站改版了。检查 `backend/feedlens/scrapers.py` 中该平台的 JS，或提交 issue。

**我的数据存在哪里？**
在 `backend/data/`：Chrome 会话在 `profiles/`；帖子、结果、简历档案和加密后的 API key 在 `feedlens.db`；加密密钥在 `secret.key`。该目录已被 git 忽略，不要发给任何人。删除它即可清空所有数据。

**我的简历会被保存吗？**
PDF 不会。只保存你确认过、已去除联系方式的 Markdown 档案，可随时在求职档案标签中删除。

**AI 中途出错怎么办？**
已浏览的帖子仍会保留。在设置中修好 key 或更换模型，打开那次浏览，点**重新分析**。

**询问 AI 会把我的全部数据发送给 AI 吗？**
不会。系统仅发送你的提问以及通过本地 SQLite 全文检索（FTS5）和筛选条件初筛出的最多 40 条匹配帖子摘要。若没有任何帖子匹配，则完全不会调用 AI。

## 开发者

<details>
<summary><b>手动安装与命令行</b></summary>

要求：Python ≥ 3.10、Node ≥ 20、Google Chrome（或 Edge）。

```bash
cd backend && uv venv && uv pip install -e ".[dev]"
copy backend\.env.example backend\.env
cd frontend && npm install && npm run build
```

AI key 可写入 `backend/.env`，也可在网页中填写。启动后端（同时在 http://127.0.0.1:8765 提供已构建的界面）：

```bash
cd backend && .venv\Scripts\feedlens serve --open
```

修改界面时，再运行 Vite 开发服务器（http://localhost:5173，自动将 `/api` 代理到后端）：

```bash
cd frontend && npm run dev
```

命令行浏览，例如用 ChatGPT 扫描两个招聘群：

```bash
cd backend && .venv\Scripts\feedlens run facebook --type group --source https://www.facebook.com/groups/aaa --source bbb -n 60 --jobs -k python -k remote --ai openai
```

测试：

```bash
cd backend && .venv\Scripts\python -m pytest -q
cd frontend && node --test tests/logic.test.cjs
```

</details>

<details>
<summary><b>目录结构</b></summary>

```
backend/            Python、FastAPI：API、浏览器自动化（Playwright）、AI 层、数据库
  feedlens/
    api.py          REST API (/api/...)，构建后同时提供 frontend/dist
    messages.py     稳定的错误/进度代码，供界面翻译为 vi/en/zh
    auth.py         账号、会话 token、agent token（云端模式）
    crypto.py       密码哈希（scrypt）、API key 加密（Fernet）
    agent.py        `feedlens agent`：从云端接收任务，在用户电脑上浏览
    ai/             anthropic_provider · openai_provider · gemini_provider · registry
    db/             SQLAlchemy：tables.py（结构）+ repository.py（查询）
    browser.py      每个平台独立的 Chrome 配置，交互式登录
    scrapers.py     各平台的 URL 与 JS 提取器，仿人滚动
    analyzer.py     分类、提取工作、摘要（所有 AI 共用）
    pipeline.py     浏览 → 分类 → 摘要，后台运行并报告进度
    job_profile.py  简历 → Markdown 档案、求职条件、相近岗位（adjacent_roles.json）
    profile_api.py  /api/profile：保存、读取、删除档案；简历分析
    topics_api.py   /api/topics：自定义主题 CRUD、重打历史标签
    trends_api.py   /api/trends：按分类/主题汇总帖子数量趋势
    search_api.py   /api/search：FTS5 全文搜索与带引文核验的 AI 问答
  tests/
frontend/           React + Vite + TypeScript + Tailwind
  src/components/     AskPage.tsx · TrendsPage.tsx · RunView · Settings · TopicSettings
  src/components/ui/  共享的 Dialog/Sheet、Button、Skeleton、EmptyState
  src/i18n.tsx        vi/en/zh 词典
  tests/              逻辑测试（node --test）
docker-compose.yml  Postgres（可选）
```

</details>

<details>
<summary><b>数据库：SQLite 或 Postgres</b></summary>

默认使用 `backend/data/feedlens.db`（SQLite）。如需 Postgres：

```bash
docker compose up -d
cd backend && uv pip install -e ".[postgres]"
```

然后在 `backend/.env` 中设置 `DATABASE_URL=postgresql+psycopg://feedlens:feedlens@localhost:5432/feedlens`。启动时会自动建表。

</details>

## 云端自建

目前没有公开实例；FeedLens 设计为在你自己的电脑上运行。本节面向想自建多用户实例的人。

<details>
<summary><b>架构与部署</b></summary>

| 部分 | 运行位置 | 配置 |
|---|---|---|
| 前端 | GitHub Pages | `.github/workflows/pages.yml`（在 Actions 标签中重新启用），仓库变量 `VITE_API_URL` |
| 后端 | Render（免费，空闲 15 分钟后休眠） | `render.yaml`（Blueprint） |
| 数据库 | Neon Postgres（免费） | Render 上的 `DATABASE_URL` |

如需 Railway，`backend/railway.json`、`frontend/railway.json` 和两个 Dockerfile 都已就绪。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/zh-CN/cloud-architecture-dark.svg">
  <img src="docs/diagrams/zh-CN/cloud-architecture.svg" alt="用户电脑上的 agent 通过 fla_ token 从 FastAPI 后端接收任务，后端数据存于 Postgres，前端托管在 GitHub Pages">
</picture>

浏览**始终在用户电脑上运行**，因为需要真实的 Chrome、用户的会话和家庭 IP（数据中心 IP 很容易被要求验证）。除非开启下面的服务器（cookie）模式，服务器不保存任何社交网站 cookie。

使用流程：

1. 在网页上注册账号。
2. **设置 → API key：** 粘贴 key。服务器通过获取模型列表来验证 key，加密（Fernet，密钥由 `FEEDLENS_SECRET` 派生）后保存。界面只显示最后 4 位。
3. **设置 → Agent：** 创建 `fla_…` token（只显示一次；数据库只存哈希），然后运行 agent：

   ```bash
   cd backend && .venv\Scripts\feedlens agent --server https://your-api.example.com --token fla_xxx
   ```

4. 首次使用时，为 agent 登录社交网站：`.venv\Scripts\feedlens login facebook`。
5. 点击**新建浏览 → 开始浏览**。Agent 每 2 秒拉取一次任务，用 Chrome 浏览并上传帖子；服务器用你的 key 分析。

每个账号只能看到自己的浏览记录、帖子和 key。"新建浏览"表单和群组列表会保存到账号（`/api/preferences`）。`feedlens push`（浏览一次后上传，不经过队列）使用同一个 token。

后端环境变量：

| 变量 | 值 |
|---|---|
| `FEEDLENS_MODE` | `cloud` |
| `DATABASE_URL` | Postgres 连接串（Neon：`postgresql://…?sslmode=require`） |
| `FEEDLENS_SECRET` | ≥ 32 字符的随机串；用于签名会话和加密 API key。有用户后**不要更改** |
| `FEEDLENS_ALLOW_SIGNUP` | `true` 或 `false` |
| `FEEDLENS_CORS` | 前端来源，如 `https://you.github.io` |

云端模式下，服务器**不会**使用环境变量中的 API key，以免其他用户消耗站长的配额。缺少 `FEEDLENS_SECRET` 时后端会锁定全部 API。15 分钟内密码错误 10 次（按 IP 或邮箱）会被临时封禁。前端只需在构建时提供 `VITE_API_URL`。

</details>

<details>
<summary><b>服务器（cookie）模式：无需 agent</b></summary>

服务器使用你保存的登录 cookie 打开无头 Chromium。

> [!CAUTION]
> Cookie 会从数据中心 IP 使用，与你平时的电脑不同。Facebook/LinkedIn 可能要求验证、强制登出或**封禁账号**。请使用小号。Cookie 的权限等同于密码。

1. 在本机：`feedlens login facebook`，然后上传 cookie：

   ```bash
   cd backend && .venv\Scripts\feedlens cookies push facebook
   ```

   该命令读取 FeedLens 专属 Chrome 配置中的 cookie（不是你日常用的 Chrome）。也可以：**设置 → 服务器浏览 → 粘贴 cookie**（Cookie-Editor 的 JSON、`cookies.txt`，或 `c_user=…; xs=…`）。
2. **设置 → 检查：** 服务器尝试用 cookie 打开首页（约 10–30 秒）。
3. **新建浏览 → 运行方式：服务器（cookie）→ 开始浏览。**

- Cookie 加密存储，从不返回给界面；只显示账号 ID 的最后 4 位。
- 服务器屏蔽图片/视频/字体，并且同一时间只运行**一个**浏览器（其他任务排队）。
- 如果平台要求登录或验证，任务会停止，cookie 被标记为**已失效**。请在本机重新登录并上传新 cookie。
- 用 `FEEDLENS_SERVER_SCRAPE=false` 关闭此模式。Docker 镜像自带无头 Chromium，`/api/health` 会返回 `"browser": true`。

</details>

## 路线图

- [ ] 每天早上定时运行，并在出现 ≥ 80 分的工作时通过 Telegram/邮件提醒
- [x] 上传简历（PDF）以更准确地匹配工作
- [x] 基于已收集数据问答（"这周有薪资超过 3000 万越南盾的远程 React 工作吗？"）
- [x] 话题趋势图
- [ ] 支持 Ollama（完全本地 AI）、Threads、TopCV/ITviec
- [ ] 桌面打包（Tauri），无需终端

## 许可证

[MIT](LICENSE)
