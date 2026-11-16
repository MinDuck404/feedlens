# Lộ trình FeedLens

[English](ROADMAP.md) · [Đóng góp](CONTRIBUTING.md) · [Hướng dẫn test](docs/TESTING.md)

Bản nháp để thảo luận, không cam kết ngày phát hành. Độ khó: **S** = nhỏ, **M** = thay đổi vài phần liên quan, **L** = cần thiết kế và kiểm chứng đáng kể. Tính năng đã có nằm trong [README](README.vi.md).

## Now — Ưu tiên hiện tại

| Hạng mục | Vấn đề của người dùng | Tiêu chí hoàn thành | Độ khó |
|---|---|---|---|
| Hướng dẫn người test | Chưa biết cài, thử gì và báo lỗi an toàn. | Cài được trên Windows sạch theo hướng dẫn Releases; gửi báo cáo đã che dữ liệu, có bước tái hiện bằng form issue. | S |
| Test tự động trên PR | Lỗi hồi quy có thể lọt vào bản phát hành. | Mỗi PR chạy pytest, test logic frontend và build, không dùng tài khoản thật hoặc gọi AI trả phí. | M |
| Báo cáo lướt cho agent | Bản cloud thiếu số bài bỏ qua và lý do dừng như bản local. | Agent gửi và lưu scrape_report tương thích ngược; UI vẫn dùng được với agent cũ; có test cho cả hai. | M |
| Kiểm chứng thêm nền tảng | Có bộ lấy bài LinkedIn/X/Reddit, nhưng fixture không chứng minh trang thật hiện tại hoạt động tốt. | Có ma trận test thủ công với sự đồng ý của người test: đăng nhập, bảng tin/tìm kiếm, link gốc, kết quả rỗng và hết phiên; thêm fixture đã làm sạch cho lỗi tìm được. | M |

## Next — Tiếp theo

| Hạng mục | Vấn đề của người dùng | Tiêu chí hoàn thành | Độ khó |
|---|---|---|---|
| AI local / tương thích đầy đủ | Muốn dùng model riêng tư hoặc rẻ hơn mà không sửa code. | Ollama và một server tương thích OpenAI qua test phân loại, tóm tắt và Hỏi AI; cấu hình endpoint/model và lỗi rõ ràng; model local không cần key cloud. | L |
| Lịch lướt | Phải tự bấm chạy mỗi lần. | Bật/tắt lịch, xem lần chạy; có quy tắc múi giờ, chạy trễ, chạy trùng, hết phiên và máy local ngủ/tắt. | L |
| Thông báo hữu ích | Có thể bỏ lỡ việc phù hợp khi chưa mở app. | Telegram hoặc email có bật/tắt, ngưỡng điểm/chủ đề, chống gửi trùng, xem trước nội dung, báo lỗi và bảo vệ token. Bắt đầu bằng một kênh. | M |

## Later — Về sau

| Hạng mục | Vấn đề của người dùng | Tiêu chí hoàn thành | Độ khó |
|---|---|---|---|
| App desktop, gồm macOS | ZIP mã nguồn vẫn cần tải môi trường và mở terminal. | Cài, mở, cập nhật và giữ dữ liệu được; ghi rõ và kiểm thử ký app/notarization, Intel/Apple Silicon trên macOS. | L |
| Nguồn bổ sung | Tin và việc phù hợp còn ở ngoài bốn nền tảng hiện có. | Chọn theo nhu cầu người test; ghi rõ giới hạn truy cập, link gốc, fixture trước khi tuyên bố hỗ trợ. Threads và trang việc làm mới là ứng viên. | L |

## Đối chiếu code

- SDK OpenAI đã đọc được `OPENAI_BASE_URL`, nhưng code dùng Responses API và lọc tên model kiểu OpenAI. Không ghi là hoàn toàn thiếu base URL; hỗ trợ Ollama đầy đủ vẫn cần kiểm chứng và hoàn thiện.
- Workflow release đã build/test frontend, chưa có workflow PR chạy cả pytest lẫn frontend.
- Agent mới gửi bài và tiến độ, chưa gửi scrape_report; local/server-cookie đã có.
- Chưa tìm thấy scheduler hay module gửi Telegram/email trong backend/feedlens.
- Đã có start.sh và ZIP mã nguồn dùng trên macOS; app macOS đóng gói/ký là mục tiêu khác.
- Không thể suy ra mức độ test tài khoản thật của LinkedIn/X/Reddit chỉ từ source.

Các công cụ CLI và dịch vụ scraper là nguồn tham khảo ưu tiên, không phải căn cứ khẳng định hơn thua chưa kiểm chứng. Hãy gửi nhu cầu cụ thể bằng form đề xuất tính năng.
