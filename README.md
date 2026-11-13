# FeedLens

Lướt bảng tin, group và kết quả tìm kiếm trên mạng xã hội bằng **phiên đăng nhập của chính bạn**, rồi để AI **phân loại, tóm tắt theo loại, tóm tắt tổng hợp** và **lọc việc làm hợp với bạn**.

Nền tảng: Facebook, LinkedIn, X (Twitter), Reddit. AI: **Claude, ChatGPT, Gemini**, hoặc bộ lọc từ khóa offline.

## Cấu trúc

```
backend/            Python, FastAPI: API, bot lướt (Playwright), lớp AI, DB
  feedlens/
    api.py          REST API (/api/...), phục vụ luôn frontend/dist nếu đã build
    auth.py         tài khoản, token phiên, token agent (chế độ cloud)
    crypto.py       băm mật khẩu (scrypt), mã hóa API key (Fernet)
    agent.py        `feedlens agent`: nhận việc từ cloud, lướt trên máy người dùng
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

Chạy local thì có thể điền key AI vào `backend/.env` hoặc nhập trên web (Cài đặt → API key AI). Không có key nào thì app dùng bộ lọc từ khóa offline.

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

## Deploy lên cloud

Bản đang chạy dùng gói miễn phí:

| Phần | Nơi chạy | Cấu hình |
|---|---|---|
| Frontend | GitHub Pages: https://minduck404.github.io/feedlens/ | `.github/workflows/pages.yml`, biến repo `VITE_API_URL` |
| Backend | Render (free, ngủ sau 15 phút không dùng) | `render.yaml` (Blueprint) |
| Database | Neon Postgres (free) | `DATABASE_URL` trên Render |

Muốn dùng Railway thay thế thì `backend/railway.json`, `frontend/railway.json` và hai Dockerfile đã có sẵn.

```
 Máy bạn                                     Cloud
┌───────────────────────────┐  hỏi việc  ┌──────────────────────────┐   ┌──────────┐
│ feedlens agent (chạy nền)  │ ◀────────▶ │ backend (FastAPI)         │──▶│ Postgres │
│ Chrome + phiên đăng nhập   │  gửi bài   │ tài khoản, key mã hóa,    │   └──────────┘
└───────────────────────────┘ token fla_ │ hàng đợi, AI tóm tắt      │
                                          └─────────────▲────────────┘
                                                        │ email + mật khẩu
                                          ┌─────────────┴────────────┐
                                          │ frontend (GitHub Pages)   │
                                          └──────────────────────────┘
```

Việc lướt **luôn chạy trên máy người dùng**, vì cần Chrome thật, phiên đăng nhập của họ và IP nhà (IP datacenter rất dễ bị Facebook/LinkedIn checkpoint). Server không giữ cookie mạng xã hội nào.

Luồng sử dụng trên bản cloud:

1. Đăng ký tài khoản trên web.
2. **Cài đặt → API key AI:** dán key Gemini, ChatGPT hoặc Claude. Server kiểm tra key bằng cách lấy danh sách model, mã hóa key (Fernet, khóa suy ra từ `FEEDLENS_SECRET`) rồi lưu vào DB. Web chỉ hiện 4 ký tự cuối.
3. **Cài đặt → Kết nối agent:** tạo token `fla_…` (chỉ hiện một lần; DB chỉ lưu hash) và copy lệnh chạy agent:

```bash
cd backend && .venv\Scripts\feedlens agent --server https://feedlens-api.onrender.com --token fla_xxx
```

4. Lần đầu, đăng nhập mạng xã hội cho agent: `.venv\Scripts\feedlens login facebook`.
5. Bấm **Lướt mới → Bắt đầu lướt** trên web. Lượt được xếp vào hàng đợi; agent hỏi việc mỗi 2 giây, mở Chrome lướt, báo tiến độ, gửi bài lên; server phân tích bằng key của bạn. Lần sau chỉ cần chạy `feedlens agent`.

Mỗi tài khoản chỉ thấy lượt, bài viết và key của chính mình. `feedlens push` (lướt một lần rồi gửi, không qua hàng đợi) vẫn dùng được với cùng token.

Một số hành vi đáng biết:

- **Lướt nhiều nhóm:** chế độ *Nhóm* có danh sách nhóm đã lưu (thêm nhiều link một lúc, tick chọn nhóm cần lướt). "Số bài" là số bài **mỗi nhóm**; tổng một lượt tối đa `FEEDLENS_MAX_POSTS` (mặc định 500). Nhóm nào lỗi (link sai, không có quyền xem) thì bỏ qua và lướt tiếp nhóm khác.
- **Lưu cài đặt:** form "Lướt mới" và danh sách nhóm được lưu vào tài khoản (`/api/preferences`), mở lại trang hay đổi máy vẫn giữ nguyên.
- **Xác minh 2 bước / checkpoint:** nếu nền tảng chuyển sang trang đăng nhập hoặc xác minh, bot dừng lại và chờ bạn tự hoàn tất trong cửa sổ Chrome (tối đa 10 phút), rồi lướt tiếp. Chạy ẩn thì không xác minh được nên lượt báo lỗi rõ ràng. `feedlens login` chỉ coi là xong khi đã qua hết bước xác minh.
- **Tốc độ:** *Nhanh* (mặc định) cuộn mạnh, nghỉ ~1 giây; *Cẩn thận* cuộn chậm, nghỉ lâu như người đọc thật. AI đọc tối đa 4 lô (20 bài/lô) song song.

### Chế độ "Server (cookie)": lướt không cần agent

Server tự mở Chromium ẩn bằng cookie đăng nhập bạn đã lưu, nên không cần bật agent trên máy.

> ⚠️ Cookie được dùng từ IP datacenter, khác máy bạn hay dùng. Facebook/LinkedIn có thể bắt xác minh, đăng xuất hoặc **khóa tài khoản**. Nên dùng tài khoản phụ. Cookie có quyền như mật khẩu.

1. Trên máy: `feedlens login facebook` (tự qua xác minh 2 bước), rồi gửi cookie lên server:

```bash
cd backend && .venv\Scripts\feedlens cookies push facebook
```

   Lệnh đọc cookie từ profile Chrome riêng của FeedLens (không phải Chrome chính của bạn) và dùng server/token đã lưu của agent. Cách khác: **Cài đặt → Lướt trên server → Dán cookie** (JSON của extension Cookie-Editor, `cookies.txt`, hoặc `c_user=…; xs=…`).
2. **Cài đặt → Kiểm tra:** server thử mở trang chủ bằng cookie (khoảng 10–30 giây).
3. **Lướt mới → Chạy bằng: Server (cookie) → Bắt đầu lướt.**

Chi tiết:

- Cookie được mã hóa (Fernet) khi lưu, không bao giờ trả về web; chỉ hiện 4 số cuối ID tài khoản.
- Server chặn tải ảnh/video/font để nhanh và nhẹ RAM, và chỉ chạy **một** trình duyệt mỗi lúc (các lượt khác xếp hàng).
- Nếu nền tảng đòi đăng nhập/xác minh (URL checkpoint hoặc trang hiện form mật khẩu), lượt dừng và cookie bị đánh dấu **Hết hiệu lực**. Server không cố vượt; hãy đăng nhập lại trên máy rồi gửi cookie mới.
- Chủ server tắt chế độ này bằng `FEEDLENS_SERVER_SCRAPE=false`. Image Docker có Chromium headless shell (Playwright), nên `/api/health` có thêm `"browser": true`.

Biến môi trường của service **backend**:

| Biến | Giá trị |
|---|---|
| `FEEDLENS_MODE` | `cloud` |
| `DATABASE_URL` | chuỗi kết nối Postgres (Neon: `postgresql://…?sslmode=require`) |
| `FEEDLENS_SECRET` | chuỗi ngẫu nhiên ≥ 32 ký tự; ký phiên đăng nhập và mã hóa API key. **Đừng đổi** sau khi đã có user |
| `FEEDLENS_ALLOW_SIGNUP` | `true` (mở đăng ký) hoặc `false` |
| `FEEDLENS_CORS` | origin của frontend, vd `https://minduck404.github.io` |

Ở chế độ cloud, server **không** dùng API key trong biến môi trường, để người dùng khác không tiêu quota của chủ server. Thiếu `FEEDLENS_SECRET` thì backend khóa toàn bộ API. Sai mật khẩu 10 lần trong 15 phút (theo IP hoặc theo email) sẽ bị chặn tạm thời.

Frontend chỉ cần `VITE_API_URL` = URL của backend (đưa vào lúc build).

## Chọn AI

| Nhà cung cấp | Lấy key ở | Ép model (local) |
|---|---|---|
| Claude | console.anthropic.com | `ANTHROPIC_MODEL` |
| ChatGPT | platform.openai.com | `OPENAI_MODEL` |
| Gemini | aistudio.google.com | `GEMINI_MODEL` |

- Danh sách model trong form "Lướt mới" lấy trực tiếp từ API của nhà cung cấp bằng key của bạn (cache 10 phút, có nút tải lại).
- Để "Mặc định" thì app dùng `gemini-3.5-flash-lite` / `gpt-5-mini` / `claude-opus-5-5` nếu key của bạn có model đó, nếu không thì model mới nhất thuộc dòng nhanh (Gemini *flash*, OpenAI *mini*, Claude *opus*). Nếu model đó quá tải (429/5xx), app thử lại 3 lần (3s, 6s, 12s) rồi tự chuyển sang model kế tiếp; trạng thái hiện trên web.
- Mọi nhà cung cấp dùng **structured output** theo cùng một JSON schema, nên kết quả có cùng định dạng.
- Server tương thích OpenAI (OpenRouter, LM Studio…): đặt `OPENAI_BASE_URL` (chỉ local).
- Thêm nhà cung cấp: viết lớp kế thừa `AIProvider` với `complete_json()` và `list_models()`, đăng ký trong `ai/registry.py`.

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
