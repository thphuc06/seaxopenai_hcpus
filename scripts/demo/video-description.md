# Product Truth Passport — demo LIVE,31/10/2026

Video90 giây: chọn sản phẩm REAL, đối chiếu LIVE, dùng OpenAI Web Search tìm thêm nguồn, xem audit và snapshot mới, rồi đọc Passport, bằng chứng, Why và trace. OpenAI trích xuất claim; code chuẩn hóa, so sánh và quyết định kết quả.

Kết quả thực tế được giữ nguyên, gồm cả trường cần người duyệt và trường thiếu bằng chứng. Lượt đầu4 model calls; lượt web thêm9 calls, gồm2 hosted web searches. Web đã fetch/lưu2 snapshot REAL từ CeraVe và Pharmacity; nguồn Pharmacity tăng số nhóm nguồn độc lập cho loại da từ2 lên3. Long Chau và Guardian trả403; run PARTIAL và lý do bị chặn được thể hiện. Tổng chi phí ước tính$0,216138, không phải hóa đơn nhà cung cấp. Không fallback/replay; gold vẫn DRAFT. Connector registry trong lượt đầu là MOCK và không cung cấp thêm tài liệu.

Quay ứng dụng Local với database demo riêng. Web Search được kích hoạt qua operator API có sẵn (chú thích trên màn hình), vì UI hiện chỉ có audit viewer; không dựng nút bấm giả. Dữ liệu nguồn REAL được chụp trong ngày; không tạo revoke cho sản phẩm thật, không sửa câu trả lời/kết quả. Đoạn chờ model được tua nhanh với nhãn trên màn hình; tải trang và thời gian chờ recorder đã được cắt. Các cảnh đọc sau đó dùng đúng kết quả đã lưu và không gọi model thêm. CSS riêng cho recording tăng cỡ chữ/khoảng cách và giấu khung ảnh/giá/shop chưa có metadata; không sửa bằng chứng hay trạng thái.

H.264/AAC1280x720,30fps,90.03s; âm thanh im lặng, không giọng/TTS/nhạc/slide pitch. Demo kit tại `_outside-repo/skills/mvp-demo` là công cụ chuẩn bị29–30/10, được khai báo tách khỏi application code viết trong ngày thi.

File local: `scripts/demo/out/live-p4-20261031/demo.mp4`. Bản đầu/raw/trace được giữ trong `take-b375bf49`; web run/audit/backup DB và bản ghép mới trong `web-first`. Chưa công khai video. Chi tiết kiểm chứng: `docs/results/live-demo.md`; lịch cảnh: `scripts/demo/storyboard.md`; recorders: `scripts/demo/record_live_demo.py` và `record_web_demo.py`.
