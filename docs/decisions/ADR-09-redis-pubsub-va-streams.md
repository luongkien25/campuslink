# ADR-09: Redis pub/sub cho thống kê, Redis Streams cho hàng đợi job; không thêm RabbitMQ

- Ngày: 02/11/2026 · Người quyết: TV1 (Kenn) · Trạng thái: chấp nhận

## Bối cảnh

Phần mở rộng (ADR-08) cần hai thứ: nhận sự kiện visit gần thời gian thực (FR-APP-18) và một hàng đợi job bền cho nhiều worker (FR-APP-16, FR-APP-21). Shlink 5.1.8 phát sự kiện qua Mercure, RabbitMQ hoặc Redis pub/sub. DB VM chỉ có 1 vCPU/2 GiB và đã chạy PostgreSQL + Redis.

## Quyết định

1. **Sự kiện visit:** bật `REDIS_PUB_SUB_ENABLED=true` cho Shlink (SRS 4.3), dùng lại Redis ứng dụng. `campus-stats` subscribe, chạy **đúng một bản** (mọi subscriber đều nhận mọi sự kiện, hai bản sẽ đếm gấp đôi). Pub/sub không lưu tin nên `campus-stats` đối soát định kỳ với `GET /rest/v3/tags/{tag}/visits`.
2. **Hàng đợi job:** Redis Stream `campus:jobs`, consumer group `campus-workers`. Worker đọc bằng `XREADGROUP`, xong thì `XACK`; lúc khởi động và định kỳ thì `XAUTOCLAIM` job treo quá 60 s của worker đã chết. Job idempotent (tên object Swift cố định), tối đa 3 lần thử rồi chuyển `failed`. Trạng thái job và số lô còn lại nằm trong DB `campus_portal`.
3. Redis phải từ 6.2 (có `XAUTOCLAIM`) và bật AOF (O-17).

## Phương án đã loại

- **RabbitMQ:** có hàng đợi bền và ack, nhưng thêm một dịch vụ và RAM trên DB VM 2 GiB. Giữ làm phương án so sánh trong báo cáo.
- **Mercure:** thêm hub và JWT riêng; hợp với đẩy cập nhật lên trình duyệt hơn là server-to-server.
- **Dùng pub/sub cho job:** không lưu tin, không ack, worker tắt là mất job.
- **Hàng đợi trong PostgreSQL (`SELECT … FOR UPDATE SKIP LOCKED`):** làm được, nhưng thêm truy vấn polling lên PostgreSQL, nơi đã là điểm nghẽn khi tải redirect cao.

## Hệ quả

- Redis thành điểm lỗi đơn của cache Shlink, sự kiện và hàng đợi job; mất Redis thì portal báo job tạm dừng, redirect vẫn chạy nếu Shlink chịu được mất cache (kiểm khi fault run).
- AOF tăng ghi đĩa trên DB VM; đo cùng O-15.
- Pub/sub của Shlink chỉ chạy với RoadRunner (runtime của image Docker). Tên topic và payload phải đối chiếu Async API spec trước khi code (O-12).
