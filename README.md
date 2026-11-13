# FeedLens

Lướt bảng tin, group và kết quả tìm kiếm trên mạng xã hội bằng **phiên đăng nhập của chính bạn**, rồi để AI **phân loại, tóm tắt theo loại, tóm tắt tổng hợp** và **lọc việc làm hợp với bạn**.

Nền tảng: Facebook, LinkedIn, X (Twitter), Reddit. AI: **Claude, ChatGPT, Gemini**, hoặc bộ lọc từ khóa offline.

## Cấu trúc

```
backend/            Python, FastAPI: API, bot lướt (Playwright), lớp AI, DB
  feedlens/
    api.py          REST API (/api/...), phục vụ luôn frontend/dist nếu đã build
    auth.py         mật khẩu + token phiên, API token cho bot (chế độ cloud)
    ai/             anthropic_provider · openai_provider · gemini_provider · registry
    db/             SQLAlchemy: tables.py (schema) + repository.py (truy vấn)
    browser.py      Chrome profile riêng cho từng nền tảng, đăng nhập tương tác
    scrapers.py     URL + JS trích bài cho từng nền tảng, vòng cuộn giống người
    analyzer.py     phân loại, trích job, tóm tắt (dùng chung cho mọi AI)
    pipeline.py     lướt → phân loại → tóm tắt, chạy nền, báo tiến độ
  tests/
frontend/           React + Vite + TypeScript + Tailwind
docker-compose.yml  Postgres (tùy chọn)
```

## Cài đặt

Yêu cầu: Python ≥ 3.10, Node ≥ 20, Google Chrome (hoặc Edge).

**Backend**

```bash
cd backend && uv venv && uv pip install -e ".[dev]"
```

```bash
copy backend\.env.example backend\.env
```

Mở `backend/.env`, điền ít nhất một key: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` hoặc `GEMINI_API_KEY`. Không điền gì thì app chạy chế độ offline.

**Frontend**

```bash
cd frontend && npm install
```

## Chạy

Cách đơn giản nhất: build frontend một lần, backend sẽ phục vụ cả giao diện tại http://127.0.0.1:8765

```bash
cd frontend && npm run build
```

```bash
cd backend && .venv\Scripts\feedlens serve --open
```

Khi sửa giao diện, chạy thêm Vite dev server (http://localhost:5173, tự proxy `/api` sang backend):

```bash
cd frontend && npm run dev
```

Xem thử giao diện với dữ liệu mẫu, không cần đăng nhập:

```bash
cd backend && .venv\Scripts\feedlens demo
```

Dòng lệnh, ví dụ quét 2 group việc làm bằng ChatGPT:

```bash
cd backend && .venv\Scripts\feedlens run facebook --type group --source https://www.facebook.com/groups/aaa --source bbb -n 60 --jobs -k python -k remote --ai openai
```

## Deploy lên cloud (Railway)

```
 Máy bạn                                   Railway
┌──────────────────────────┐   HTTPS   ┌─────────────────────────┐   ┌──────────┐
│ feedlens push            │ ────────▶ │ backend (FastAPI)        │──▶│ Postgres │
│ Chrome + phiên đăng nhập │  API token│ FEEDLENS_MODE=cloud      │   └──────────┘
└──────────────────────────┘           │ AI: phân loại + tóm tắt  │
                                       └────────────▲────────────┘
                                                    │ mật khẩu
                                       ┌────────────┴────────────┐
                                       │ frontend (nginx, tĩnh)   │
                                       └─────────────────────────┘
```

Bot lướt **luôn chạy trên máy bạn**, vì nó cần Chrome thật, phiên đăng nhập của bạn và IP nhà (IP datacenter rất dễ bị Facebook/LinkedIn checkpoint). Server cloud không giữ cookie mạng xã hội nào; nó nhận bài, chạy AI, lưu vào Postgres và hiển thị qua web.

Biến môi trường của service **backend**:

| Biến | Giá trị |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (tham chiếu tới service Postgres) |
| `FEEDLENS_PASSWORD` | mật khẩu đăng nhập web |
| `FEEDLENS_SECRET` | chuỗi ngẫu nhiên ≥ 32 ký tự, dùng để ký phiên |
| `FEEDLENS_API_TOKEN` | chuỗi ngẫu nhiên, cho `feedlens push` |
| `FEEDLENS_CORS` | URL của frontend, vd `https://feedlens-web.up.railway.app` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | ít nhất một key |

Service **frontend** chỉ cần `VITE_API_URL` = URL của backend. Biến này được đưa vào lúc build, nên đổi xong phải deploy lại.

Thiếu `FEEDLENS_PASSWORD` hoặc `FEEDLENS_SECRET` thì backend khóa toàn bộ API. Đăng nhập sai quá 10 lần trong 15 phút sẽ bị chặn tạm thời.

Lướt từ máy rồi gửi lên cloud:

```bash
cd backend && .venv\Scripts\feedlens login facebook
```

```bash
$env:FEEDLENS_SERVER="https://<backend>.up.railway.app"; $env:FEEDLENS_API_TOKEN="<token>"
```

```bash
.venv\Scripts\feedlens push facebook --type group --source https://www.facebook.com/groups/aaa -n 60 --jobs -k python
```

Nút "Lướt mới" trên web bản cloud tạo sẵn lệnh này để bạn copy.

## Chọn AI

| Nhà cung cấp | Biến key | Model mặc định | Đổi model |
|---|---|---|---|
| Claude | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | `ANTHROPIC_MODEL` |
| ChatGPT | `OPENAI_API_KEY` | `gpt-5-mini` | `OPENAI_MODEL` |
| Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` | `GEMINI_MODEL` |

- `FEEDLENS_AI_PROVIDER=auto` chọn nhà cung cấp đầu tiên có key (Claude → OpenAI → Gemini). Trong form "Lướt mới" bạn đổi được AI và model cho từng lượt.
- Server tương thích OpenAI (OpenRouter, LM Studio…): đặt `OPENAI_BASE_URL`. Server đó phải hỗ trợ Responses API và JSON schema.
- Mọi nhà cung cấp đều dùng **structured output** theo cùng một JSON schema, nên kết quả có cùng định dạng.
- Thêm nhà cung cấp mới: viết một lớp kế thừa `AIProvider` với hàm `complete_json()` rồi đăng ký trong `ai/registry.py`.

## Database

Mặc định là SQLite tại `backend/data/feedlens.db`. Muốn dùng Postgres:

```bash
docker compose up -d
```

```bash
cd backend && uv pip install -e ".[postgres]"
```

Rồi đặt `DATABASE_URL=postgresql+psycopg://feedlens:feedlens@localhost:5432/feedlens` trong `backend/.env`. Bảng được tạo tự động khi khởi động.

## Lưu ý

- Tự động lướt **vi phạm điều khoản** của Facebook, LinkedIn và X; tài khoản có thể bị checkpoint. Hãy dùng cho cá nhân, số lượng nhỏ, và cân nhắc dùng tài khoản phụ.
- Bot chạy trong cửa sổ Chrome hiển thị theo mặc định. Chế độ ẩn thường bị chặn (Reddit chặn trình duyệt ẩn khi chưa đăng nhập). FeedLens không cố vượt cơ chế chống bot.
- FeedLens **chỉ đọc**: không đăng, không bình luận, không nhắn tin. Mật khẩu không bao giờ đi qua app.
- Nội dung bài viết được gửi tới nhà cung cấp AI bạn chọn. `backend/data/` chứa cookie phiên, **không chia sẻ hay commit**.
- Selector của mạng xã hội thay đổi thường xuyên. Nếu một nền tảng trả về 0 bài, sửa đoạn JS tương ứng trong `backend/feedlens/scrapers.py`.

## Lộ trình

- [ ] Lịch chạy tự động mỗi sáng + báo Telegram/email khi có job điểm ≥ 80
- [ ] Upload CV (PDF) để chấm độ phù hợp chính xác hơn
- [ ] Hỏi đáp trên dữ liệu đã thu ("tuần này có job React remote nào lương > 30 triệu?")
- [ ] Biểu đồ xu hướng chủ đề theo thời gian
- [ ] Thêm Ollama (chạy AI hoàn toàn trên máy), Threads, TopCV/ITviec
- [ ] Đóng gói desktop (Tauri) để dùng không cần terminal
