# Chương: Ứng dụng, cơ sở dữ liệu, sao lưu và khôi phục (TV3)

> Bản nháp của TV3 cho báo cáo cuối (#79, T3-5). TV1 ghép vào khung báo cáo. Mọi số liệu đều trỏ tới evidence trong repo. PR chưa merge ghi kèm số PR.

## 1. Ứng dụng

### 1.1. Thành phần

- **Shlink 5.1.8** (`shlinkio/shlink`, khóa digest trong `docs/versions.lock`): backend rút gọn link chạy trên app VM, không sửa mã hay schema.
- **Shlink Web Client 4.8.1**: SPA tĩnh ở admin domain, người dùng tự nhập server URL và API key.
- **campus-portal** (nhóm tự viết, FastAPI): cổng chiến dịch nhiều đơn vị. Theo điều kiện lùi cứng ở #40, portal **dừng ở MVP trên Compose** (SRS 6.3, bản 20/11).

### 1.2. Bảng yêu cầu FR-APP-01..21

Trạng thái: **Cụm** = đạt trên cụm OpenStack; **Compose** = đạt trên Compose local; **Bỏ** = bỏ khỏi MVP theo #40 (14–15/11).

| Mã | Nội dung ngắn | Trạng thái | Evidence |
| --- | --- | --- | --- |
| FR-APP-01 | Tạo link, `customSlug`, tag, `shortUrl` đúng domain | Cụm | `evidence/G3/20261118-FR-APP-01-12-h1-smoke-cum.txt` (PR #62) |
| FR-APP-02 | Redirect 302 đúng `Location` | Cụm | như trên |
| FR-APP-03 | Sửa đích, hiệu lực trên mọi replica | Cụm | như trên (PATCH qua A, đọc qua B) |
| FR-APP-04 | Ghi visit, xem có phân trang | Cụm | như trên (24/24 visit) |
| FR-APP-05 | Tag chiến dịch, thống kê theo tag | Cụm | như trên |
| FR-APP-06 | QR trong Web Client | Cụm | như trên; `evidence/G3/20261118-FR-APP-06-quet-qr-iphone.png` (PR #62) |
| FR-APP-07 | API cần `X-Api-Key` | Cụm | như trên (401 khi thiếu hoặc sai key) |
| FR-APP-08 | Key `--author-only` chỉ thấy link của mình | Cụm | như trên (key B: đọc 404, sửa 404, danh sách 0) |
| FR-APP-09 | Web Client SPA, F5 không 404 | Cụm | như trên; `evidence/G3/20261118-FR-APP-09-web-client-key-donvi-a.png` (PR #62) |
| FR-APP-10 | CORS chỉ cho admin origin | Cụm | như trên |
| FR-APP-11 | Health 200/503 theo DB | Cụm | như trên (dừng PostgreSQL thì 503, bật lại thì 200) |
| FR-APP-12 | 404 và 400 `non-unique-slug` | Cụm | như trên |
| FR-APP-13 | Portal: tài khoản, 3 vai trò, key riêng mỗi đơn vị | Compose; cụm dừng ở DB, secret, Swift | `evidence/G3/20261114-FR-APP-13-14-16-portal-mvp-compose.txt` (31 PASS); `evidence/G3/20261115-H1b-FR-APP-13-16-portal-db-swift-cum.txt`; `evidence/G3/20261118-H1b-FR-APP-13-portal-image-build.txt` |
| FR-APP-14 | Chiến dịch: tạo, sửa, đóng, hạn | Compose | `evidence/G3/20261114-FR-APP-13-14-16-portal-mvp-compose.txt` |
| FR-APP-15 | Nhập CSV hàng loạt | Bỏ (#40) | — |
| FR-APP-16 | Thẻ QR cá nhân hóa | Compose (1 lô đồng bộ); cụm chỉ thử `campus-svc` ghi `campus-qr` | như FR-APP-13 |
| FR-APP-17 | Luật chuyển hướng từ portal | Bỏ (#40) | — |
| FR-APP-18 | `campus-stats` thời gian thực | Không làm: không có mã trong repo, không build (`docs/versions.lock`) | #40 |
| FR-APP-19 | Báo cáo CSV vào `campus-reports` | Không làm | #40 |
| FR-APP-20 | Nhật ký thao tác portal | Bỏ (#40) | — |
| FR-APP-21 | Hàng đợi job bền (`campus-worker`) | Không làm: worker không build | #40 |

Smoke H1 trên cụm chạy ngày 18/11 từ DB VM, gọi thẳng 2 app VM; 27 PASS, 0 FAIL. Key đi qua file, không lên argv (PR #59).

### 1.3. Vì sao portal dừng ở Compose

Mốc lùi cứng ghi ở #40: nếu đến 18/11 23:59 image portal chưa phát hành có digest và chưa lên cụm ổn định, thì demo portal trên Compose. Đến mốc đó, TV3 đã build được image từ commit sạch (base khóa digest, smoke 31 PASS trên chính image, #63) nhưng **chưa push GHCR**. Vì vậy portal dừng ở Compose, không thêm listener 8081 vào Heat, không đụng cụm trong freeze. Mục đích là giữ ổn định cho phần lõi (Shlink, LB, scaling) đang đo G5. Phần đã làm trên cụm chỉ gồm DB `campus_portal`, 2 secret trong Swift, và `campus-svc` ghi được vào `campus-qr`.

## 2. Cơ sở dữ liệu

### 2.1. Thiết kế

- DB VM `campus-db` (flavor `campus.db`: 1 vCPU, 2 GiB, theo SRS C-06), **không có floating IP**, chỉ nhận kết nối từ `campus-net`.
- **PostgreSQL 16.15** (apt Ubuntu 24.04). Dữ liệu nằm trên **Cinder volume `campus-db-data` 10 GiB**; thiếu mount thì PostgreSQL không chạy, để tránh ghi nhầm lên đĩa gốc. `max_connections=50`, xác thực `scram-sha-256`, TLS bật.
- **Redis 7.0.15**: cache, khóa và pub/sub dùng chung cho mọi replica Shlink. Bật AOF, `maxmemory 256mb`, `noeviction` (ADR-09, O-17).
- Mọi replica dùng cùng DB, cùng Redis, cùng `CACHE_NAMESPACE` (NFR-12). Mật khẩu DB và Redis cấp qua Swift `campus-secrets` (ADR-10), không nằm trong image hay Git.

### 2.2. Lý do chọn

- **PostgreSQL:** Shlink hỗ trợ chính thức. SQLite bị loại vì nhiều replica phải dùng chung một DB (ràng buộc ở AGENTS.md mục 3). Bản 16 có sẵn trong apt Ubuntu 24.04, không phải thêm repo ngoài.
- **Redis:** tài liệu Shlink yêu cầu Redis khi chạy nhiều instance, để các replica dùng chung cache và khóa. Phép kiểm NFR-12 (sửa qua A, đọc ngay qua B) chạy trên cấu hình này.
- **Tự dựng trên VM thay vì dịch vụ quản trị sẵn:** DevStack của nhóm không cài Trove, vì bật thêm dịch vụ phải chạy lại `stack.sh` và xóa toàn bộ tài nguyên cụm (ADR-11, `docs/decisions/ADR-11-van-hanh-nang-cao.md`). Đây là phần tương đương **Amazon RDS** (PostgreSQL) và **ElastiCache** (Redis), nhóm tự vận hành: tự backup, tự vá, tự giám sát.
- **Cinder cho dữ liệu DB:** volume tách khỏi vòng đời VM (tương đương **EBS**). Dựng lại VM thì gắn lại volume, dữ liệu còn; chụp snapshot được (tầng 1 DR).

### 2.3. Kết quả

| Yêu cầu | Kết quả | Evidence |
| --- | --- | --- |
| FR-INF-12 | PASS: thiếu mount thì PostgreSQL không chạy; reboot DB VM thì link còn | `evidence/G3/20261108-FR-INF-12-db-vm.txt`, `evidence/G3/20261112-FR-INF-15-16-backup-restore-cum.txt` |
| NFR-11 | PASS: link còn sau reboot DB VM và stop/start 2 EC2; luôn có dump ngoài host A | `evidence/G3/20261112-FR-INF-15-16-backup-restore-cum.txt` |
| NFR-12 | PASS trên cụm: sửa qua A, đọc qua B thấy đích mới ngay | PR #62 |

### 2.4. Giới hạn đã đo

- DB VM chỉ 1 vCPU. Trong lượt đo 18/11, CPU DB lên khoảng 94–96%, cùng lúc p95 phía server tăng.
- Kiểm chỉ đọc ngày 20/11 (#76, PR #84) thấy **Shlink mở kết nối PostgreSQL mới cho từng request**, khoảng 50 kết nối mỗi giây ở 25 visit/s, mỗi kết nối có bắt tay TLS và xác thực SCRAM. Đây là **tương quan, chưa chứng minh nhân quả**. Phép thử xác nhận (giữ kết nối lâu dài, pgbouncer) để sau bản nộp.
- Ứng viên thứ hai, đọc từ mã Shlink v5.1.8 (PR #89): mỗi visit chạy 4 lệnh `COUNT(*)` trên toàn bộ visit của slug để gửi sự kiện pub/sub, nên chi phí DB tăng theo số visit slug đã có. Lượt đo tối 21/11 (PR #91, #77) cùng chiều với dự đoán: slug mới `tv3dc-20261121` tốn khoảng **25 ms** CPU DB mỗi visit, đạt 39,54 RPS, đuôi 1–2 phút; slug `tv4fix1` (khoảng 124 nghìn visit) tốn khoảng **148 ms**, 23,49 RPS, đuôi khoảng 26 phút (CPU DB tính tay từ Gnocchi). Đây mới là một cặp lượt đo, vẫn là **tương quan, chưa đối chứng lặp lại**.
- Bộ đếm `pg_stat_user_tables` bị xóa mỗi lần VM boot, vì VM tắt theo host nên PostgreSQL khởi động lại sau lần tắt không sạch. Không dùng được để xem lịch sử autovacuum.

## 3. Sao lưu (FR-INF-15)

- **Cách làm:** `pg_dump -Fc` trên DB VM, đẩy vào Swift `campus-backups/db/` kèm sha256. Script so etag (md5) và meta sha256 sau khi đẩy. Giữ 48 bản trong Swift và 2 bản trên đĩa VM.
- **Lịch:** systemd timer `OnBootSec=10min`, `OnCalendar=hourly`, `RandomizedDelaySec=120`, `Persistent=true`. Từ đó **RPO ≤ 1 giờ 02 phút khi cụm chạy** (O-19).
- **Quyền:** application credential của `campus-tv3`, chỉ ghi và xóa được `campus-backups/db/*`, không đọc được `campus-secrets` (ADR-10).
- **Bản ngoài host A:** `app/db/backup/pull-latest.sh` kéo bản mới nhất về máy nhóm, kiểm sha256 (20/11: 1,2 MB, 11,8 s).
- **Lý do chọn Swift** (tương đương **S3**): lưu đối tượng, private, có checksum; tách khỏi DB VM và volume. Giới hạn: Swift nằm trên chính host A, nên không chống được mất host A; phần này do bản về máy nhóm bù.
- Evidence: `evidence/G3/20261112-FR-INF-15-16-backup-restore-cum.txt`, `evidence/G3/20261112-FR-INF-15-backup-thu-local.txt`.

## 4. Khôi phục (FR-INF-16, FR-INF-25, NFR-20)

- **Restore thử (FR-INF-16):** `campus-db-restore-test` restore dump vào DB tách biệt `campus_restore_test`, không bao giờ vào DB `shlink`. Script so migration, số bản ghi và 5 slug fixture `tv4fix1..5` (đích và số visit), rồi xóa DB thử khi đặt `DROP_AFTER=1`. Trên cụm 16/11: PASS (`evidence/G3/20261116-FR-INF-16-H5-fixture-restore-cum.txt`, H5).
- **Khôi phục thảm họa 3 tầng:**

| Tầng | Kịch bản | RPO | RTO đo được | Ngưỡng NFR-20 | Evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | Cinder snapshot → volume mới → DB VM thử (cả AZ-A và AZ-B) | Thời điểm snapshot (crash-consistent) | 124–158 s | ≤ 300 s | `evidence/G3/20261112-FR-INF-25-tang-1-snapshot-volume-db-vm-thu-hai-host.txt` |
| 2 | Dump trong Swift → PostgreSQL sạch tạm trên A | ≤ 1 giờ 02 phút | 5,8 s (dữ liệu nhỏ, chỉ phần restore) | ≤ 60 s | `evidence/G3/20261113-FR-INF-25-tang-2-dump-swift-restore-cum-tam.txt` |
| 3 (thay thế) | Dump kéo về máy nhóm → Compose mới tinh → Shlink → smoke H1 | ≤ 1 giờ 02 phút, cộng thời gian từ lần kéo gần nhất | 18,2 s từ lúc có dump; 30,0 s tính cả kéo từ Swift; dữ liệu thật (7.141 link, 164.496 visit) | chưa chốt (tầng 3 chờ O-22) | `evidence/G5/20261120-FR-INF-25-tang-3-thay-the-local.txt` (PR #86) |

- **Không có S3/Object Lock:** tầng 3 theo SRS cần bucket S3 bật Object Lock, đổi ràng buộc ngân sách, nên phải nhóm duyệt ADR-11/O-22. O-22 chưa duyệt, vì vậy tầng 3 dùng bản thay thế trên máy nhóm. Bản này không bất biến và không nằm ở tài khoản hay region khác. RTO tầng 3 chưa tính thời gian cài Docker và kéo image trên máy mới.
