"""Dữ liệu giả để xem thử giao diện mà không cần đăng nhập."""
from .models import RawPost

_G = "Việc làm IT (dữ liệu mẫu)"
_RAW = [
    ("HR Nova Tech", "[HN/Remote] Tuyển Python Backend Developer (2+ năm). FastAPI, PostgreSQL. Lương 25-35tr. "
                     "Làm remote 100%. Gửi CV: jobs@novatech.example"),
    ("Linh Recruiter", "We're hiring Senior React Engineer — HCM, hybrid, up to $2500. DM hoặc email hr@acme.example"),
    ("Minh Trần", "Cho em hỏi mới ra trường nên học Java hay Python để dễ xin việc ạ?"),
    ("Shop Laptop Cũ", "Thanh lý MacBook Air M1 8/256, giá 11tr, ship toàn quốc, inbox mình nhé"),
    ("GDG Hanoi", "Sự kiện: Workshop 'Build AI agents' tối thứ 6 này, đăng ký tham gia tại link bên dưới"),
    ("Startup ABC", "Tuyển thực tập sinh Data (Python, SQL), part-time, có trợ cấp. Liên hệ 0912345678"),
    ("Tuấn Dev", "Chia sẻ: mình vừa migrate hệ thống từ Django sang FastAPI, throughput tăng gấp 3 lần. API design là chìa khóa."),
    ("Ưu đãi Cloud", "Khuyến mãi giảm giá 50% VPS cloud cho dev, voucher có hạn đến cuối tháng"),
    ("FinCorp", "Tuyển Java Developer onsite Đà Nẵng, 3 năm kinh nghiệm Spring Boot, lương thỏa thuận."),
    ("Hà Phương", "Hôm nay team mình đi team building ở Ba Vì, vui quá haha 😂"),
]
DEMO_POSTS = [RawPost(platform="facebook", source=_G, author=a, text=t,
                      url=f"https://www.facebook.com/groups/demo/posts/{i}") for i, (a, t) in enumerate(_RAW)]
