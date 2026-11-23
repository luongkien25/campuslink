# campus-portal (TV3)

Cổng chiến dịch cho đơn vị, bao quanh Shlink 5.1.8 qua REST v3 (ADR-08, SRS 3.3, 4.6). Bản hiện tại là **MVP phương án B** đã chốt ở issue #40:

| Mã | Có trong MVP | Ghi chú |
| --- | --- | --- |
| FR-APP-13 | Tối thiểu | Đăng nhập, 3 vai trò (`admin`, `unit`, `viewer`). Mỗi đơn vị một API key Shlink `--author-only`, mã hóa Fernet trong DB `campus_portal` |
| FR-APP-14 | Có | Chiến dịch tạo, sửa, đóng. Link mang tag `campaign-<id>`, có `validUntil` = hạn chiến dịch. Đóng thì `validUntil` = lúc đóng |
| FR-APP-16 | Đường lùi | 1 lô, chạy đồng bộ, tối đa 300 người. Mỗi người một short link riêng; PDF A4 8 thẻ/trang; lưu `<campaign_id>/v<n>/lo-1.pdf` |
| FR-APP-17 | Có | Luật chuyển hướng theo thiết bị (android/ios/desktop), ngôn ngữ, trước/sau một mốc giờ. Admin và đơn vị đặt được, người xem thì không. Luật lưu trong Shlink, trang `/campaigns/<id>/links/<mã>/rules` |
| FR-APP-15 | Có, chạy đồng bộ | Nhập link từ CSV (cột `long_url`, `custom_slug`, `label`; ≤ 1 MB, ≤ 1000 dòng) ngay trong request, không qua hàng đợi (FR-APP-21 chưa có). Báo kết quả từng dòng; nhập lại cùng file không tạo link trùng |
| FR-APP-20 | Có | Nhật ký thao tác (ai, làm gì, đối tượng, lúc nào) ở bảng `audit_log`, admin xem tại `/admin/audit` (mới nhất trước, 200 dòng). Không ghi API key, mật khẩu |
| FR-APP-21 | Không | Bỏ theo #40. `ROLE=worker` thoát mã 2 |

## Chạy trên Compose local

```
cd app/compose
./gen-secrets.sh            # lần đầu (H1)
./gen-portal-secrets.sh     # chỉ tạo file secret portal còn thiếu
docker compose --profile portal up -d --build --wait
```

Mở `http://127.0.0.1:18090`. Admin đầu tiên: `admin`, mật khẩu trong `secrets/portal_admin_password` (smoke tự tạo; tạo tay bằng `docker compose exec -T portal python -m portal.cli create-admin admin < secrets/portal_admin_password`).

API key cho đơn vị: `docker compose exec shlink shlink api-key:generate --author-only --name=<đơn vị>`, rồi dán vào trang Quản trị.

Smoke theo cột "Kiểm bằng" của SRS: `app/portal/smoke/portal-smoke.sh` (tự tạo admin, 2 đơn vị, 3 tài khoản nếu chưa có).

## Cấu hình (SRS 4.6)

Secret chỉ đọc qua `*_FILE`: `PORTAL_DB_URL_FILE`, `PORTAL_SECRET_KEY_FILE`, `REDIS_SERVERS_FILE`, `SWIFT_APP_CRED_FILE` (khi `QR_STORAGE=swift`).
Không secret: `ROLE`, `PORTAL_PORT` (8081), `SHLINK_API_URL`, `QR_STORAGE` (`local`|`swift`), `QR_LOCAL_DIR`, `OS_AUTH_URL`, `SWIFT_URL`, `SWIFT_CONTAINER_QR`, `TIMEZONE`.

- `GET /healthz`: 200 `{"status":"pass"}` khi DB `campus_portal` và Redis trả lời, ngược lại 503.
- Migration chạy lúc khởi động, khóa `pg_advisory_xact_lock` nên nhiều replica khởi động cùng lúc vẫn an toàn.
- Cookie phiên ký bằng khóa suy từ `PORTAL_SECRET_KEY`. Mọi form POST có CSRF token. Mật khẩu băm `scrypt`.
- Chiến dịch của đơn vị khác luôn trả 404. Cách ly ở cả hai lớp: portal lọc theo `unit_id`, và Shlink chỉ cho key `--author-only` thấy link của chính key đó.

## Chưa làm (H1b, 17/11 nếu đạt mốc 16/11)

Image có digest, DB `campus_portal` trên DB VM, secret vào `campus-secrets/app/`, `QR_STORAGE=swift` thử với `campus-svc`. Nhánh Swift (`portal/storage.py`) **chưa chạy thử**.
