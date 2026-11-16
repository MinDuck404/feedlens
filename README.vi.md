<div align="center">

[English](README.md) · **Tiếng Việt** · [简体中文](README.zh-CN.md)

# FeedLens

**Đọc ít hơn, biết nhiều hơn.**

FeedLens lướt bảng tin, group và kết quả tìm kiếm trên mạng xã hội bằng phiên đăng nhập của chính bạn.
Sau đó AI phân loại bài, tóm tắt theo chủ đề và lọc ra việc làm hợp với bạn, trình bày như một tờ báo để đọc.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![React + Vite](https://img.shields.io/badge/react-vite-61DAFB?logo=react&logoColor=black)](frontend/)
[![AI: Claude · ChatGPT · Gemini](https://img.shields.io/badge/AI-Claude%20·%20ChatGPT%20·%20Gemini-AE3824)](#chọn-ai)
[![License: MIT](https://img.shields.io/badge/license-MIT-16120E)](LICENSE)

[Bắt đầu nhanh](#bắt-đầu-nhanh) · [Tính năng](#tính-năng) · [Chọn AI](#chọn-ai) · [Tự host trên cloud](#tự-host-trên-cloud) · [Lưu ý](#lưu-ý)

<img src="docs/screenshots/hero-digest-light.png" alt="Trang tóm tắt của một lượt lướt, trình bày kiểu báo giấy" width="900">

</div>

## Vì sao có FeedLens

Group việc làm, group cộng đồng và bảng tin mỗi ngày có hàng trăm bài, phần lớn là quảng cáo, meme và bài lặp lại. FeedLens đọc hộ bạn rồi đưa ra một bản tin ngắn: cái gì đáng đọc, việc nào hợp với bạn, mở bài gốc khi cần. Mọi thứ chạy bằng tài khoản và trình duyệt của chính bạn, trên máy của bạn.

## Tính năng

| | |
|---|---|
| **4 nền tảng** | Facebook, LinkedIn, X (Twitter), Reddit: bảng tin, group, hoặc kết quả tìm kiếm |
| **Tóm tắt kiểu báo** | Bài được chia theo loại (việc làm, công nghệ, tin tức, mua bán…), mỗi loại có đoạn tóm tắt riêng và một bản tóm tắt chung |
| **Chủ đề của bạn** | Tự định nghĩa tối đa 12 chủ đề theo dõi riêng; AI chỉ gắn khi bài thật sự nói về chủ đề đó; mục "Chủ đề của bạn" nằm đầu bản tin (kể cả chủ đề 0 bài); gắn lại chủ đề cho các lượt cũ bất cứ lúc nào |
| **Hỏi & tìm** | Tìm toàn văn trên kho bài đã lưu kèm bộ lọc có cấu trúc (loại bài, chủ đề, ngày, việc làm: remote/lương/địa điểm/điểm, link GitHub); Hỏi AI trả lời kèm trích dẫn đã xác thực [#id] trỏ đúng bài thật, hoặc báo rõ khi không tìm thấy bài phù hợp |
| **Xu hướng** | Thống kê lượng bài theo danh mục hoặc chủ đề trong 7/30/90 ngày theo ngày hoặc tuần, so sánh với kỳ trước; bấm vào điểm dữ liệu để mở trang Hỏi & tìm xem các bài đó |
| **Lọc việc làm theo CV** | Tải CV PDF một lần; AI chấm từng tin 0–100 theo vai trò, cấp độ, hình thức (remote/hybrid/onsite), địa điểm, lương. Gợi ý cả việc ngành gần (vd junior dev → IT helpdesk) kèm kỹ năng còn thiếu |
| **Không mất bài khi AI lỗi** | Bài đã lướt được lưu trước khi AI đọc; sửa key xong bấm "Phân tích lại", không cần lướt lại |
| **Chọn AI** | Claude, ChatGPT, Gemini, hoặc bộ lọc từ khóa offline khi không có key |
| **Chạy trên máy bạn** | Phiên đăng nhập nằm trong profile Chrome riêng, dữ liệu trong SQLite; chỉ nội dung bài đi tới AI bạn chọn |
| **3 ngôn ngữ** | Giao diện và bản tóm tắt bằng tiếng Việt, English hoặc 中文 (tự theo ngôn ngữ trình duyệt) |
| **Sáng / tối** | Giấy kem khi sáng, gỗ trầm khi tối; theo hệ điều hành hoặc chọn bằng nút trên thanh bên |

<table>
  <tr>
    <td width="62%"><img src="docs/screenshots/posts-dark.png" alt="Danh sách bài viết, giao diện tối"></td>
    <td width="38%"><img src="docs/screenshots/mobile-dark.png" alt="Giao diện trên điện thoại"></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/jobs-light.png" alt="Tab việc làm có điểm phù hợp"></td>
    <td><img src="docs/screenshots/composer-light.png" alt="Ngăn tạo lượt lướt mới"></td>
  </tr>
</table>

## Bắt đầu nhanh

Chỉ cần có **Google Chrome**. Máy chưa có Python thì script khởi động tự cài [uv](https://docs.astral.sh/uv/), uv tự mang theo Python.

1. Tải `FeedLens-<phiên bản>.zip` ở [Releases](https://github.com/MinDuck404/feedlens/releases/latest) rồi giải nén. File này có sẵn giao diện đã build, nên không cần Node.js.
   (Nếu dùng `git clone` hoặc **Code → Download ZIP** thì cần thêm [Node.js LTS](https://nodejs.org) để build giao diện ở lần chạy đầu.)
2. **Windows:** bấm đúp `start.bat`. **macOS/Linux:** chạy `./start.sh`.
   Lần đầu mất vài phút để cài Python và thư viện. Trình duyệt tự mở http://127.0.0.1:8765.
3. Bấm **Đăng nhập** cạnh Facebook (trên điện thoại: mở menu ☰). Một cửa sổ Chrome hiện ra; đăng nhập như bình thường, kể cả xác minh 2 bước. Xong thì cửa sổ tự đóng.
4. **Cài đặt** (bánh răng) → tab **API key**: thêm key Gemini, ChatGPT hoặc Claude. Không có key thì app dùng bộ lọc từ khóa.
5. Tìm việc? Tab **Hồ sơ tìm việc**: tải CV PDF, kiểm tra bản tóm tắt, chọn tiêu chí và vai trò muốn chuyển sang.
6. (Tùy chọn) Tab **Chủ đề**: tạo tối đa 12 chủ đề theo dõi riêng với từ khóa và màu sắc tự chọn.
7. Bấm **Lướt mới**, chọn bảng tin hoặc các nhóm, rồi **Bắt đầu lướt**.

Tắt app bằng cách đóng cửa sổ terminal (hoặc Ctrl+C).

> Muốn xem giao diện với dữ liệu mẫu mà chưa đăng nhập gì: `cd backend && .venv\Scripts\feedlens demo`.

## Cách hoạt động

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/vi/how-it-works-dark.svg">
  <img src="docs/diagrams/vi/how-it-works.svg" alt="Chrome của bạn lướt bài, lưu bài thô vào SQLite, AI phân loại và tóm tắt, rồi hiện thành bản tin">
</picture>

- **Lướt:** bot mở Chrome thật với profile riêng của FeedLens và cuộn như người đọc. Chế độ *Nhanh* nghỉ khoảng 1 giây; *Cẩn thận* cuộn chậm hơn.
- **Nhiều nhóm:** lưu sẵn danh sách nhóm, tick nhóm cần lướt. "Số bài" tính **mỗi nhóm**; cả lượt tối đa `FEEDLENS_MAX_POSTS` (mặc định 500). Nhóm lỗi thì bỏ qua và lướt tiếp.
- **Xác minh / checkpoint:** nếu nền tảng đòi đăng nhập lại, bot dừng và chờ bạn tự hoàn tất trong cửa sổ Chrome (tối đa 10 phút) rồi lướt tiếp.
- **AI:** đọc tối đa 4 lô song song, 20 bài mỗi lô. Mọi nhà cung cấp dùng chung một JSON schema nên kết quả cùng định dạng.
- **AI lỗi giữa chừng:** bài thô đã nằm trong DB. Lượt hiện lý do lỗi, vẫn xem và tải được bài thô (.json/.md), và có nút **Phân tích lại** để chạy lại bằng key hoặc model khác.

### Chấm việc theo CV

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/vi/cv-matching-dark.svg">
  <img src="docs/diagrams/vi/cv-matching.svg" alt="CV PDF được tách chữ trên máy, AI tạo hồ sơ Markdown, rồi dùng để chấm từng tin tuyển dụng">
</picture>

- Chữ trong PDF được tách ngay trên máy (`pypdf`). AI chuyển thành hồ sơ Markdown và bỏ số điện thoại, email, địa chỉ. **File PDF không được lưu.**
- Bạn tự đặt tiêu chí (remote/hybrid/onsite, địa điểm, lương tối thiểu, cấp độ) và bật từng vai trò lân cận muốn thử.
- Mỗi tin có nhãn **Đúng ngành / Ngành gần / Thử sức**, lý do, kỹ năng còn thiếu và cảnh báo khi trái tiêu chí. Server tự giới hạn điểm: trái 1 tiêu chí tối đa 65, trái 2 tiêu chí tối đa 30; việc ngành gần tối đa 80, và tối đa 40 nếu bạn chưa cho phép.
- Hồ sơ chỉ gửi kèm một lần cho mỗi lô 20 bài.

### Hỏi AI trên kho tin đã lưu

- **Hiểu câu hỏi dưới dạng bộ lọc:** AI phân tích câu hỏi tự nhiên thành các bộ lọc có cấu trúc (khoảng ngày, nền tảng, danh mục, chủ đề, điều kiện việc làm).
- **Tìm kiếm cục bộ trước:** Backend truy vấn cơ sở dữ liệu SQLite trên máy (dùng tìm kiếm toàn văn FTS5) để chọn tối đa 40 bài viết phù hợp nhất.
- **Tổng hợp kèm trích dẫn xác thực:** Nếu có bài phù hợp, AI tổng hợp câu trả lời ngắn gọn và trích dẫn nguồn `[#id]` trỏ đúng ID bài thật. Mọi ID do AI bịa ra đều bị loại bỏ tự động.
- **Thoát sớm khi không có bài:** Khi không tìm thấy bài nào khớp điều kiện, hệ thống báo ngay mà không tốn thêm lượt gọi AI thứ hai.
- **Dữ liệu gửi đi tối giản:** Chỉ câu hỏi và trích đoạn ngắn của các bài khớp mới được gửi lên AI; toàn bộ cơ sở dữ liệu không bao giờ bị tải lên.

## Chọn AI

| Nhà cung cấp | Lấy key ở | Ép model (chạy local) |
|---|---|---|
| Claude | console.anthropic.com | `ANTHROPIC_MODEL` |
| ChatGPT | platform.openai.com | `OPENAI_MODEL` |
| Gemini | aistudio.google.com | `GEMINI_MODEL` |

- Danh sách model trong "Lướt mới" lấy trực tiếp từ API bằng key của bạn (cache 10 phút, có nút tải lại).
- Để "Mặc định" thì app dùng `gemini-3.5-flash-lite` / `gpt-5-mini` / `claude-opus-5-5` nếu key có model đó, không thì model mới nhất thuộc dòng nhanh. Model quá tải (429/5xx) thì app thử lại 3 lần (3s, 6s, 12s) rồi chuyển sang model kế tiếp.
- Server tương thích OpenAI (OpenRouter, LM Studio…): đặt `OPENAI_BASE_URL` (chỉ local).
- Thêm nhà cung cấp: viết lớp kế thừa `AIProvider` với `complete_json()` và `list_models()`, đăng ký trong `ai/registry.py`.

## Lưu ý

> [!WARNING]
> Tự động lướt **vi phạm điều khoản** của Facebook, LinkedIn và X; tài khoản có thể bị checkpoint. Dùng cho cá nhân, số lượng nhỏ, và cân nhắc dùng tài khoản phụ.

- FeedLens **chỉ đọc**: không đăng, không bình luận, không nhắn tin. Mật khẩu không bao giờ đi qua app.
- Bot chạy trong cửa sổ Chrome hiển thị theo mặc định. Chế độ ẩn thường bị chặn (Reddit chặn trình duyệt ẩn khi chưa đăng nhập). FeedLens không cố vượt cơ chế chống bot.
- Nội dung bài được gửi tới nhà cung cấp AI bạn chọn. `backend/data/` chứa cookie phiên: **không chia sẻ, không commit**.
- Selector của mạng xã hội thay đổi thường xuyên. Nếu một nền tảng trả về 0 bài, sửa đoạn JS tương ứng trong `backend/feedlens/scrapers.py`.

## Dành cho nhà phát triển

<details>
<summary><b>Cài đặt thủ công và dòng lệnh</b></summary>

Yêu cầu: Python ≥ 3.10, Node ≥ 20, Google Chrome (hoặc Edge).

```bash
cd backend && uv venv && uv pip install -e ".[dev]"
copy backend\.env.example backend\.env
cd frontend && npm install && npm run build
```

Có thể điền key AI vào `backend/.env` hoặc nhập trên web. Chạy backend (phục vụ luôn giao diện đã build tại http://127.0.0.1:8765):

```bash
cd backend && .venv\Scripts\feedlens serve --open
```

Khi sửa giao diện, chạy thêm Vite dev server (http://localhost:5173, tự proxy `/api` sang backend):

```bash
cd frontend && npm run dev
```

Lướt bằng dòng lệnh, ví dụ quét 2 group việc làm bằng ChatGPT:

```bash
cd backend && .venv\Scripts\feedlens run facebook --type group --source https://www.facebook.com/groups/aaa --source bbb -n 60 --jobs -k python -k remote --ai openai
```

Test:

```bash
cd backend && .venv\Scripts\python -m pytest -q
cd frontend && node --test tests/logic.test.cjs
```

</details>

<details>
<summary><b>Cấu trúc thư mục</b></summary>

```
backend/            Python, FastAPI: API, bot lướt (Playwright), lớp AI, DB
  feedlens/
    api.py          REST API (/api/...), phục vụ luôn frontend/dist nếu đã build
    messages.py     mã lỗi/tiến độ ổn định để giao diện dịch sang vi/en/zh
    auth.py         tài khoản, token phiên, token agent (chế độ cloud)
    crypto.py       băm mật khẩu (scrypt), mã hóa API key (Fernet)
    agent.py        `feedlens agent`: nhận việc từ cloud, lướt trên máy người dùng
    ai/             anthropic_provider · openai_provider · gemini_provider · registry
    db/             SQLAlchemy: tables.py (schema) + repository.py (truy vấn)
    browser.py      Chrome profile riêng cho từng nền tảng, đăng nhập tương tác
    scrapers.py     URL + JS trích bài cho từng nền tảng, vòng cuộn giống người
    analyzer.py     phân loại, trích job, tóm tắt (dùng chung cho mọi AI)
    pipeline.py     lướt → phân loại → tóm tắt, chạy nền, báo tiến độ
    job_profile.py  CV → hồ sơ Markdown, tiêu chí, vai trò lân cận (adjacent_roles.json)
    profile_api.py  /api/profile: lưu, đọc, xóa hồ sơ; phân tích CV
    topics_api.py   /api/topics: CRUD chủ đề riêng, gắn lại chủ đề cho lượt cũ
    trends_api.py   /api/trends: gom số liệu bài viết theo danh mục/chủ đề
    search_api.py   /api/search: tìm FTS5 & Hỏi AI có trích dẫn xác thực
  tests/
frontend/           React + Vite + TypeScript + Tailwind
  src/components/     AskPage.tsx · TrendsPage.tsx · RunView · Settings · TopicSettings
  src/components/ui/  Dialog/Sheet, Button, Skeleton, EmptyState dùng chung
  src/i18n.tsx        từ điển vi/en/zh
  tests/              test logic (node --test)
docker-compose.yml  Postgres (tùy chọn)
```

</details>

<details>
<summary><b>Database: SQLite hoặc Postgres</b></summary>

Mặc định là SQLite tại `backend/data/feedlens.db`. Muốn dùng Postgres:

```bash
docker compose up -d
cd backend && uv pip install -e ".[postgres]"
```

Rồi đặt `DATABASE_URL=postgresql+psycopg://feedlens:feedlens@localhost:5432/feedlens` trong `backend/.env`. Bảng được tạo tự động khi khởi động.

</details>

## Tự host trên cloud

Hiện không có bản online nào đang chạy; FeedLens được thiết kế để dùng trên máy. Phần này dành cho ai muốn tự host bản nhiều người dùng.

<details>
<summary><b>Kiến trúc và cách triển khai</b></summary>

| Phần | Nơi chạy | Cấu hình |
|---|---|---|
| Frontend | GitHub Pages | `.github/workflows/pages.yml` (bật lại trong tab Actions), biến repo `VITE_API_URL` |
| Backend | Render (free, ngủ sau 15 phút không dùng) | `render.yaml` (Blueprint) |
| Database | Neon Postgres (free) | `DATABASE_URL` trên Render |

Muốn dùng Railway thì `backend/railway.json`, `frontend/railway.json` và hai Dockerfile đã có sẵn.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/vi/cloud-architecture-dark.svg">
  <img src="docs/diagrams/vi/cloud-architecture.svg" alt="Agent trên máy người dùng nhận việc từ backend FastAPI qua token fla_, backend lưu vào Postgres, frontend trên GitHub Pages">
</picture>

Việc lướt **luôn chạy trên máy người dùng**, vì cần Chrome thật, phiên đăng nhập của họ và IP nhà (IP datacenter rất dễ bị checkpoint). Server không giữ cookie mạng xã hội nào, trừ khi bật chế độ Server (cookie) bên dưới.

Luồng sử dụng:

1. Đăng ký tài khoản trên web.
2. **Cài đặt → API key AI:** dán key. Server kiểm tra key bằng cách lấy danh sách model, mã hóa (Fernet, khóa suy ra từ `FEEDLENS_SECRET`) rồi lưu. Web chỉ hiện 4 ký tự cuối.
3. **Cài đặt → Kết nối agent:** tạo token `fla_…` (chỉ hiện một lần; DB chỉ lưu hash) và chạy agent:

   ```bash
   cd backend && .venv\Scripts\feedlens agent --server https://your-api.example.com --token fla_xxx
   ```

4. Lần đầu, đăng nhập mạng xã hội cho agent: `.venv\Scripts\feedlens login facebook`.
5. Bấm **Lướt mới → Bắt đầu lướt**. Agent hỏi việc mỗi 2 giây, mở Chrome lướt, gửi bài lên; server phân tích bằng key của bạn.

Mỗi tài khoản chỉ thấy lượt, bài và key của mình. Form "Lướt mới" và danh sách nhóm được lưu vào tài khoản (`/api/preferences`). `feedlens push` (lướt một lần rồi gửi, không qua hàng đợi) dùng cùng token.

Biến môi trường của backend:

| Biến | Giá trị |
|---|---|
| `FEEDLENS_MODE` | `cloud` |
| `DATABASE_URL` | chuỗi kết nối Postgres (Neon: `postgresql://…?sslmode=require`) |
| `FEEDLENS_SECRET` | chuỗi ngẫu nhiên ≥ 32 ký tự; ký phiên và mã hóa API key. **Đừng đổi** sau khi đã có user |
| `FEEDLENS_ALLOW_SIGNUP` | `true` hoặc `false` |
| `FEEDLENS_CORS` | origin của frontend, vd `https://you.github.io` |

Ở chế độ cloud, server **không** dùng API key trong biến môi trường, để người dùng khác không tiêu quota của chủ server. Thiếu `FEEDLENS_SECRET` thì backend khóa toàn bộ API. Sai mật khẩu 10 lần trong 15 phút (theo IP hoặc email) sẽ bị chặn tạm thời. Frontend chỉ cần `VITE_API_URL` lúc build.

</details>

<details>
<summary><b>Chế độ Server (cookie): lướt không cần agent</b></summary>

Server tự mở Chromium ẩn bằng cookie đăng nhập bạn đã lưu.

> [!CAUTION]
> Cookie được dùng từ IP datacenter, khác máy bạn hay dùng. Facebook/LinkedIn có thể bắt xác minh, đăng xuất hoặc **khóa tài khoản**. Nên dùng tài khoản phụ. Cookie có quyền như mật khẩu.

1. Trên máy: `feedlens login facebook`, rồi gửi cookie lên server:

   ```bash
   cd backend && .venv\Scripts\feedlens cookies push facebook
   ```

   Lệnh đọc cookie từ profile Chrome riêng của FeedLens (không phải Chrome chính của bạn). Cách khác: **Cài đặt → Lướt trên server → Dán cookie** (JSON của Cookie-Editor, `cookies.txt`, hoặc `c_user=…; xs=…`).
2. **Cài đặt → Kiểm tra:** server thử mở trang chủ bằng cookie (khoảng 10–30 giây).
3. **Lướt mới → Chạy bằng: Server (cookie) → Bắt đầu lướt.**

- Cookie được mã hóa khi lưu, không bao giờ trả về web; chỉ hiện 4 số cuối ID tài khoản.
- Server chặn tải ảnh/video/font và chỉ chạy **một** trình duyệt mỗi lúc (các lượt khác xếp hàng).
- Nếu nền tảng đòi đăng nhập/xác minh, lượt dừng và cookie bị đánh dấu **Hết hiệu lực**. Đăng nhập lại trên máy rồi gửi cookie mới.
- Tắt chế độ này bằng `FEEDLENS_SERVER_SCRAPE=false`. Image Docker có sẵn Chromium headless, `/api/health` trả thêm `"browser": true`.

</details>

## Câu hỏi thường gặp

**Không có API key AI thì có dùng được không?**
Có. App dùng bộ lọc từ khóa offline để chia loại bài. Khi đó không có bản tóm tắt AI, và điểm việc làm chỉ tính theo số từ khóa khớp.

**Lướt một lượt mất bao lâu?**
Tùy số bài và tốc độ chọn. Chế độ *Nhanh* nghỉ khoảng 1 giây mỗi lần cuộn; thêm thời gian AI đọc theo lô 20 bài.

**Một nền tảng trả về 0 bài?**
Thường do mạng xã hội đổi giao diện. Xem đoạn JS của nền tảng đó trong `backend/feedlens/scrapers.py`, hoặc mở issue.

**Dữ liệu của tôi nằm ở đâu?**
Trong `backend/data/`: phiên Chrome ở `profiles/`, bài viết, kết quả, hồ sơ CV và API key (đã mã hóa) ở `feedlens.db`, khóa mã hóa ở `secret.key`. Thư mục này không bao giờ được commit. Đừng gửi nó cho người khác. Xóa thư mục này là xóa sạch.

**CV của tôi có bị lưu lại không?**
Không lưu file PDF. Chỉ lưu bản hồ sơ Markdown bạn đã duyệt, sau khi bỏ thông tin liên hệ. Bạn xóa được bất cứ lúc nào trong tab Hồ sơ tìm việc.

**AI báo lỗi giữa chừng thì sao?**
Bài đã lướt vẫn còn. Sửa key hoặc đổi model trong Cài đặt, rồi mở lượt đó và bấm **Phân tích lại**.

**Hỏi AI có gửi toàn bộ dữ liệu của tôi cho AI không?**
Không. App chỉ gửi câu hỏi kèm trích đoạn ngắn của tối đa 40 bài viết khớp với bộ lọc và tìm kiếm FTS5 cục bộ (SQLite). Nếu không có bài nào khớp, app không gọi AI.

## Lộ trình

- [ ] Lịch chạy tự động mỗi sáng + báo Telegram/email khi có job điểm ≥ 80
- [x] Upload CV (PDF) để chấm độ phù hợp chính xác hơn
- [x] Hỏi đáp trên dữ liệu đã thu ("tuần này có job React remote nào lương > 30 triệu?")
- [x] Biểu đồ xu hướng chủ đề theo thời gian
- [ ] Thêm Ollama (chạy AI hoàn toàn trên máy), Threads, TopCV/ITviec
- [ ] Đóng gói desktop (Tauri) để dùng không cần terminal

## Giấy phép

[MIT](LICENSE)
