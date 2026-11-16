# Test FeedLens / Hướng dẫn test FeedLens

[Tiếng Việt](#tiếng-việt) · [English](#english) · [Roadmap](../ROADMAP.md) · [Contributing](../CONTRIBUTING.md)

## Tiếng Việt

Bạn không cần biết code. Mục tiêu là thử một luồng nhỏ và báo chính xác điều xảy ra, kể cả khi mọi thứ hoạt động tốt.

### Cài từ Releases

1. Cài Google Chrome, mở [Releases](https://github.com/MinDuck404/feedlens/releases/latest), tải **FeedLens-<version>.zip** trong Assets và giải nén. Không chọn “Source code” nếu bạn không muốn cài Node.js/build giao diện.
2. Windows: bấm đúp `start.bat`. macOS/Linux: mở Terminal tại thư mục giải nén và chạy `bash start.sh`. Đây là bản chạy từ mã nguồn, chưa phải app macOS được ký. Lần đầu cần mạng để tải Python/thư viện; có thể mất vài phút.
3. Giữ cửa sổ terminal mở. Trình duyệt sẽ mở `http://127.0.0.1:8765`; nếu không, tự mở địa chỉ đó. Dừng bằng Ctrl+C trong terminal. Khi nâng cấp, giải nén vào thư mục mới; đừng xoá/ghi đè thư mục dữ liệu cũ hoặc chuyển dữ liệu khi app đang chạy. Nhờ maintainer hướng dẫn nếu cần giữ lịch sử.

**Rủi ro:** tự động lướt có thể vi phạm điều khoản Facebook và các nền tảng, dẫn đến checkpoint hoặc khoá tài khoản. Nên dùng tài khoản phụ bạn có quyền sử dụng, chạy ít bài và dừng nếu được yêu cầu xác minh. Không vượt checkpoint hoặc giới hạn nền tảng. Bài viết/câu hỏi và nội dung CV được xử lý có thể gửi tới nhà cung cấp AI bạn chọn; dùng dữ liệu mẫu không nhạy cảm. AI có thể tính phí; không có key vẫn thử được phân loại offline và Tìm nhanh, nhưng không đánh giá chất lượng tóm tắt AI.

### Kịch bản 14 bước

Ghi phiên bản từ tên ZIP/tag, Windows/macOS/Linux, phiên bản Chrome, ngôn ngữ và sáng/tối. Đánh dấu từng bước: đạt / lỗi / bỏ qua (kèm lý do).

1. Mở app; đổi vi → en → zh và quay lại. Kiểm tra chữ không bị cắt; đổi sáng/tối.
2. Bấm Đăng nhập cạnh Facebook; trên màn hình nhỏ mở menu ☰. Tự đăng nhập trong Chrome, không gửi mật khẩu/cookie cho ai. Kiểm tra trạng thái phiên sau đó.
3. Mở Cài đặt → API key. Nếu muốn test AI, thêm key của bạn, chọn model và Kiểm tra. Không chụp key. Không có key thì ghi “offline”.
4. Tuỳ chọn: mở Hồ sơ tìm việc, dán hồ sơ giả không có thông tin liên hệ. Chọn vai trò/địa điểm, lưu, đóng rồi mở lại. Không cần tải CV thật.
5. Mở Chủ đề, tạo hai chủ đề với tên/từ khoá dễ phân biệt và màu khác nhau; thử bật/tắt rồi bật lại.
6. Mở Lướt mới → Facebook → Bảng tin, chọn **20 bài** và ghi rõ “chỉ bài mới” bật hay tắt. Bấm Bắt đầu một lần. Nếu bị yêu cầu xác minh, dừng và ghi nhận.
7. Theo dõi tiến độ: lướt → phân tích → tóm tắt. Ghi số bài thực nhận, số bài cũ/quảng cáo bỏ qua và lý do dừng nếu có. 20 là mục tiêu, không bảo đảm khi hết nội dung/ngân sách.
8. Đọc Tóm tắt; kiểm tra Chủ đề của bạn, kể cả chủ đề không khớp. Bấm tên loại/chủ đề và xem bộ lọc Bài viết có đúng không.
9. Mở vài bài gốc: có vào đúng bài, thay vì ảnh/trang chủ không? Ghi tác giả giả danh hoặc đoạn mô tả đã che dữ liệu nếu sai, không gửi nội dung riêng tư.
10. Mở Việc làm; thử lọc loại khớp/điểm, xem tiêu chí và link gốc. Không có việc làm là kết quả hợp lệ, ghi “không có dữ liệu để kiểm tra”.
11. Mở Lịch sử, xem lại lượt vừa chạy; tải JSON/Markdown và mở trên máy. Không đính kèm bản xuất thật vào issue vì chứa nội dung bài viết.
12. Trong Chủ đề, sửa một chủ đề rồi gắn lại cho lượt cũ, chờ hoàn tất; mở lại lượt xem số bài và tóm tắt đã cập nhật.
13. Mở Xu hướng, đổi loại/chủ đề và khoảng ngày; bấm một điểm để mở Hỏi & tìm. Thử Tìm nhanh, chỉnh/bỏ chip lọc; có key thì hỏi một câu đơn giản và bấm nguồn trích dẫn. Ít lịch sử có thể cho biểu đồ rỗng/phẳng.
14. Tuỳ chọn: chạy thêm một lượt nhỏ với **offline** hoặc model/key không dùng được (không cố gây quota); kiểm tra thông báo, bài đã lấy và Phân tích tiếp nếu xuất hiện. Sửa cấu hình rồi thử lại. Đóng/mở app, kiểm tra lịch sử còn nguyên. Ghi bỏ qua nếu không muốn chạy thêm.

### Lấy log và gửi báo cáo an toàn

- Log chính nằm trong cửa sổ terminal đã mở bởi `start.bat` / `start.sh`; hiện chưa có tệp log cố định tự xuất. Chọn và sao chép đoạn quanh thời điểm lỗi sang **một tệp mới**, không gửi toàn bộ terminal. Nếu cửa sổ đóng ngay, mở PowerShell tại thư mục app rồi chạy `./start.bat` để thấy lỗi.
- Ghi giờ lỗi và múi giờ, số lượt, bước tái hiện, mong đợi và thực tế. Gửi bằng [Issues](https://github.com/MinDuck404/feedlens/issues/new/choose) → Bug report hoặc Test report. Một lỗi riêng biệt nên có một issue. Không cần gọi lại AI hay chạy nhiều lần chỉ để lấy log.
- **Không gửi** thư mục `backend/data/`, `profiles/`, database, `secret.key`, `.env`, file cookie, token agent, API key, CV thật, HAR/network dump hoặc header Authorization. Không dùng “Copy as cURL” từ trình duyệt để báo lỗi.
- Với lỗi link Facebook, mẫu thường ở `backend/data/debug/missing-links/run-<id>.html` và `.json` (nếu có). Nếu đã đổi FEEDLENS_DATA_DIR thì tìm trong thư mục dữ liệu tương ứng. Không có file cũng bình thường; không tự lướt thêm để tạo file nếu chưa được yêu cầu.
- Tạo **bản sao** của riêng mẫu cần gửi. Mở bằng trình soạn thảo văn bản, không mở HTML như trang web. Dù app đã rút gọn và loại một số token, mẫu vẫn có thể chứa tên, ID tài khoản/bài/nhóm, URL và nội dung riêng tư. Thay bằng `AUTHOR_A`, `PAGE_ID`, `POST_ID`, `REDACTED`; giữ cùng ký hiệu cho cùng ID, giữ cấu trúc thuộc tính và dạng URL khi có thể. Xoá email, số điện thoại, địa chỉ, tên thật, token/cookie và tham số URL nhạy cảm. Che thông tin tương tự trên ảnh.
- Đọc lại toàn bộ bản sao; tìm `cookie`, `token`, `authorization`, `fb_dtsg`, `c_user`, `xs`, `__user` và chuỗi key. Tìm kiếm này **không bảo đảm** đã sạch. Nếu không chắc, chỉ gửi mô tả/fixture giả và hỏi maintainer cách chia sẻ riêng; đừng tải file lên issue công khai. Checkbox trong form chỉ xác nhận bạn đã kiểm tra, không thay việc kiểm tra.

## English

No coding is needed. Try a small workflow and report exactly what happened, including successful results.

### Install from Releases

1. Install Google Chrome. Open [Releases](https://github.com/MinDuck404/feedlens/releases/latest), download **FeedLens-<version>.zip** under Assets and extract it. Avoid “Source code” unless you intend to install Node.js and build the UI.
2. Windows: double-click `start.bat`. macOS/Linux: open a terminal in the extracted directory and run `bash start.sh`. This is a source-based launcher, not a signed macOS app. First launch needs internet to download Python/dependencies and can take several minutes.
3. Leave the terminal open; visit `http://127.0.0.1:8765` if the browser does not open. Stop with Ctrl+C. Extract upgrades into a new directory; do not delete/overwrite old data or move it while the app is running. Ask a maintainer before migrating history.

**Risk:** automated browsing may violate Facebook and other platforms' terms and cause checkpoints or account restrictions. Prefer a secondary account you are authorized to use, keep runs small, and stop if verification is requested. Do not bypass checks or platform limits. Post/question and processed CV content may be sent to your selected AI provider; use non-sensitive sample data. AI can incur charges. Without a key you can test offline classification and Quick search, but not AI summary quality.

### 14-step test

Record the ZIP/tag version, OS, Chrome version, language and light/dark setting. Mark each step pass / fail / skipped, with a reason.

1. Launch; switch vi → en → zh and back. Check clipping and switch light/dark.
2. Sign in beside Facebook (open ☰ on small screens). Sign in yourself in Chrome; never share credentials/cookies. Check the resulting session status.
3. Open Settings → API keys. Optionally add your own key, choose a model and Check it. Do not capture the key in screenshots. Otherwise record “offline”.
4. Optionally paste a fictional Job profile without contact details, set roles/locations, save and reopen. Do not upload a real CV for testing.
5. Create two Topics with distinct keywords/colors; disable and enable one.
6. New run → Facebook → Feed → **20 posts**. Record whether “only new” is enabled. Click Start once. Stop and report if verification is requested.
7. Observe scraping → analysis → digest. Record collected/skipped counts and the stop reason if available. Twenty is a target, not guaranteed when content/budget runs out.
8. Read Digest and Your topics, including zero-match topics. Click a category/topic and verify the Posts filter.
9. Open several original posts. Do they open the post rather than a photo/homepage? Describe mismatches using pseudonyms and redacted excerpts.
10. Open Jobs, try match/score filters, constraints and original links. No jobs is valid; record “no data to test”.
11. Open History and revisit this run. Download JSON/Markdown and inspect locally; do not attach real exports to an issue.
12. Edit a Topic, re-apply to past runs, wait for completion and reopen the run to check counts/summaries.
13. Open Trends, switch category/topic and date range, click a point into Ask & search. Try Quick search and editable filter chips. With a key, ask a simple question and follow citations. Little history may yield an empty/flat chart.
14. Optionally try another small run with offline or an unavailable model/key; do not deliberately exhaust quota. Check errors, retained scraped posts and Continue analysis if offered. Fix configuration and retry. Restart the app and check history persists. Skip extra runs if preferred.

### Logs and safe reports

- Logs appear in the launch terminal; there is no fixed automatically exported log file. Copy only the relevant time window into a **new file**. If the window closes immediately, open PowerShell in the app folder and run `./start.bat` to see the error.
- Record time/timezone, run number, steps, expected and actual behavior. Use [Issues](https://github.com/MinDuck404/feedlens/issues/new/choose) → Bug report or Test report. Separate unrelated bugs. Do not repeatedly call AI just to capture logs.
- **Never upload** `backend/data/`, profiles, databases, `secret.key`, `.env`, cookie files, agent tokens, API keys, real CVs, HAR/network dumps or Authorization headers. Avoid “Copy as cURL”.
- Missing-link samples may be at `backend/data/debug/missing-links/run-<id>.html` and `.json`; with a custom FEEDLENS_DATA_DIR, use its debug directory instead. Files may legitimately be absent; do not run more scans just to create them without being asked.
- Copy only the needed sample. Open the copy in a text editor, not as a web page. Automatic truncation/token removal is **not a privacy guarantee**: names, account/post/group IDs, URLs and private excerpts can remain. Replace them consistently with `AUTHOR_A`, `PAGE_ID`, `POST_ID`, `REDACTED`, preserving attribute structure and URL shapes where possible. Remove contacts, addresses, credentials and sensitive URL parameters; redact screenshots too.
- Review the entire copy and search for `cookie`, `token`, `authorization`, `fb_dtsg`, `c_user`, `xs`, `__user` and key strings. Searches do not prove safety. If uncertain, submit only a description/synthetic fixture and ask the maintainer about private sharing; do not upload to a public issue. The form checkbox does not replace inspection.
