# ADR-08: Mở rộng ứng dụng bằng dịch vụ bao quanh Shlink, không fork

- Ngày: 02/11/2026 · Người quyết: TV1 (Kenn) chốt sau khi so bảng duyệt đề tài · Trạng thái: chấp nhận

## Bối cảnh

Ngày 02/11/2026 giảng viên duyệt đề tài **Đạt** kèm nhận xét "Ứng dụng có vẻ quá đơn giản" và "Cần đánh giá thêm khi demo trình bày trực tiếp" (SRS O-04). So với bảng duyệt đủ 13 đề tài: nhận xét về CampusLink chỉ nhắm vào app, không có nhận xét về kiến trúc cloud; bốn đề tài không bị nhận xét gì đều có phần xử lý nặng chạy nền. SRS C-04 khóa digest Shlink 5.1.8 và Web Client 4.8.1, cấm sửa backend/schema. Lịch mới: nộp 23/11, bảo vệ 30/11 (C-09).

## Quyết định

1. Giữ Shlink 5.1.8 và Web Client 4.8.1 nguyên digest. Shlink vẫn là lõi redirect, visit, luật chuyển hướng; Web Client là giao diện quản trị kỹ thuật.
2. Thêm ba dịch vụ nhóm tự viết (SRS mục 3.3, 4.6):
   - `campus-portal`: giao diện nghiệp vụ cho đơn vị (tài khoản, chiến dịch, nhập CSV, phát hành thẻ QR, luật chuyển hướng, bảng SSE), cổng 8081, chạy trong mỗi app VM.
   - `campus-worker`: cùng image với portal, khác entrypoint, chạy trong mỗi app VM nên co giãn cùng ASG; xử lý job từ hàng đợi (ADR-09).
   - `campus-stats`: một bản trên DB VM, nhận visit qua Redis pub/sub, đếm theo phút và check-in, đối soát với API visits.
3. Ba dịch vụ chỉ nói chuyện với Shlink qua REST v3 (key `--author-only` theo đơn vị) và Redis. Dữ liệu nghiệp vụ nằm trong DB riêng `campus_portal`; file nằm trong Swift `campus-qr`, `campus-reports`, ghi bằng application credential của user `campus-svc`.
4. Không thêm EC2, không thêm VM.

## Phương án đã loại

- **Fork Shlink, thêm bảng chiến dịch vào schema:** vi phạm C-04, phải tự build image PHP, mất câu "cùng digest" khi so static với auto (NFR-04).
- **Fork Web Client, thêm trang chiến dịch:** phải nắm React/TypeScript và bộ giao diện riêng của Shlink; vẫn cần backend giữ key của đơn vị, nên không bớt được portal.
- **Viết lại app riêng:** bỏ phần Shlink đã làm tốt (redirect, visit, luật), rủi ro thời gian cao nhất.
- **VM riêng cho portal:** đụng trần RAM 12 GiB của quota khi cần builder; chạy trong app VM thì portal được LB và autoscale cùng Shlink.

## Hệ quả

- Image app có thêm container portal và worker; readiness chờ cả `/rest/health` và `/healthz` (H1b, H4b). LB thêm listener 8081 (O-13). Nginx thêm vhost `app.`, cert `campus` cấp lại với `--expand`.
- Thêm secret: mật khẩu DB `campus_portal`, `PORTAL_SECRET_KEY`, application credential `campus-svc`, key `campus-stats` (NFR-08, NFR-18).
- CPU của portal và worker cộng vào tín hiệu alarm CPU: benchmark redirect (G5) chạy khi không có job; "phát hành thẻ kích scale-out" là kịch bản riêng (NFR-19).
- Hai mốc cắt 10/11 và 14/11 (SRS 6.3) chặn phần mở rộng lấn sang benchmark. Đường lùi của FR-APP-16: một lô, không cá nhân hóa.
