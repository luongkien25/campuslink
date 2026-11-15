# H5 – Fixture, bản backup và thủ tục restore (TV3 → TV4)

Ngày (UTC): 2026-11-15 (bản nháp, chưa có số liệu cụm) · Gate: G4, G5 · Commit: `REPLACE_SAU_MERGE` · Yêu cầu: #50
Không ghi secret. API key Shlink và credential backup **không** nằm trong file này (SRS O-02, ADR-10).

## 1. Đã sẵn sàng

### 1.1. 5 slug fixture chuẩn (cố định cho NFR-03, NFR-04, FR-INF-16)

Lấy đúng 5 slug đã có trong `tests/fixtures/fixture-slugs.example.json` và `tests/load/setup-fixture.sh` (PR #48 của TV4), để TV4 không phải đổi code. Ví dụ `cl-fix-01..05` trong #50 **không** dùng.

| Slug | Đích (`longUrl`) | Tag |
| --- | --- | --- |
| `tv4fix1` | `https://example.org/campuslink-fixture-1` | `campus-open-day`, `load-test` |
| `tv4fix2` | `https://example.org/campuslink-fixture-2` | như trên |
| `tv4fix3` | `https://example.org/campuslink-fixture-3` | như trên |
| `tv4fix4` | `https://example.org/campuslink-fixture-4` | như trên |
| `tv4fix5` | `https://example.org/campuslink-fixture-5` | như trên |

- Tạo bằng key **admin** do TV3 giữ (SRS 4.2, dòng "TV3 giữ 1 key admin để chuẩn bị fixture chung"). Key `--author-only` chỉ thấy link do chính nó tạo, nên **không** thấy fixture. TV4 đọc thống kê fixture (`GET .../visits`) bằng key admin hoặc key không giới hạn của TV4, không dùng key đơn vị.
- Không đặt `validUntil`, `maxVisits`: fixture không bao giờ hết hạn.
- Trên cụm: **chưa tạo** (phiên cloud trước 16/11 19:30). Số liệu ở 1.2 điền sau phiên đó.

### 1.2. Bản backup dùng cho kiểm restore

| Thứ | Giá trị | Kiểm bằng |
| --- | --- | --- |
| Container Swift | `campus-backups`, object `db/shlink-<UTC>.dump` + `db/shlink-<UTC>.dump.sha256` | `openstack object list campus-backups --prefix db/` (TV3, `OS_CLOUD=campus-tv3`) |
| Bản đã kiểm có đủ 5 fixture | `REPLACE_SAU_PHIEN_CLOUD` (vd `db/shlink-20261116T...Z.dump`) | dòng `OK tai ...` của `campus-db-restore-test` |
| sha256 của bản đó | `REPLACE_SAU_PHIEN_CLOUD` | như trên |
| Phiên bản migration Shlink | `ShlinkMigrations\Version20260607082210` (Shlink 5.1.8; local 15/11, cụm điền sau) | dòng `migration=` |
| Lịch backup | 10 phút sau boot DB VM, rồi mỗi giờ (`Persistent`), giữ 48 bản trong Swift; RPO ≤ 1 giờ 02 phút | `docs/runbooks/db-backup.md` |
| Snapshot EBS (FR-INF-17, TV1) | `snap-03f8a6038bec5b942` (lab IAM 26/10, không chứa fixture) | `docs/inventory.yaml` dòng `iam_lab_snapshot` |

"Backup snapshot ID" của H5 là **tên object dump trong Swift** ở trên. Snapshot EBS là của TV1, chỉ để chứng minh quyền IAM, không dùng để restore DB.

## 2. Người nhận làm được gì / không được làm gì

- Được:
  - Gọi `GET /tv4fixN` và `GET /rest/v3/short-urls/tv4fixN/visits` không giới hạn trong phiên đo.
  - Chạy `tests/load/setup-fixture.sh`: an toàn khi fixture đã có (Shlink trả 400 `non-unique-slug`, không ghi đè).
  - Xin TV3 chạy restore thử (mục 3.2) bất cứ lúc nào ngoài cửa sổ đo tải.
- Không được (hỏi TV3 trước):
  - Xóa, sửa đích hay đặt hạn cho 5 fixture. Đổi 1 fixture là phải đo lại mọi lượt NFR-04 (SRS: "cùng fixture").
  - Restore vào DB `shlink` thật. Restore chỉ vào `campus_restore_test` (FR-INF-16).
  - Chạy restore thử **trong** cửa sổ đo tải: `pg_restore` dùng CPU/IO của chính DB VM.

## 3. Cách tự kiểm tra

### 3.1. TV4 kiểm fixture trên cụm (không cần quyền đặc biệt ngoài API key)

`setup-fixture.sh` coi mọi mã 400 là "đã có", nhưng Shlink trả 400 cả khi slug đã có **với đích khác** và khi body sai. Vì vậy sau khi chạy, kiểm lại đích và tag của từng slug:

```bash
# key doc tu file, khong dua len argv (cung cach setup-fixture.sh)
for i in 1 2 3 4 5; do
  curl -sS "https://s.44-198-215-187.sslip.io/rest/v3/short-urls/tv4fix$i" \
    --config <(printf 'header = "X-Api-Key: %s"\n' "$SHLINK_API_KEY") \
  | jq -r '[.shortCode, .longUrl, (.tags|join(",")), .visitsSummary.total] | @tsv'
done
```

Mong đợi: 5 dòng, cột 2 đúng bảng 1.1, cột 3 `campus-open-day,load-test`. `curl -sSI https://s.44-198-215-187.sslip.io/tv4fix1` trả `302` + `Location` đúng đích.

### 3.2. Restore thử (TV3 chạy trên DB VM, ⚠️ tạo lại DB `campus_restore_test`)

Đường vào DB VM theo `docs/runbooks/db-backup.md` mục 3 (VM nhảy).

```bash
ssh campus-db 'sudo systemctl start campus-db-backup.service && sudo journalctl -u campus-db-backup -n 4 --no-pager -o cat'   # dump moi co du 5 fixture
ssh campus-db 'sudo DROP_AFTER=1 SLUGS="tv4fix1 tv4fix2 tv4fix3 tv4fix4 tv4fix5" campus-db-restore-test latest'
```

Mong đợi (đủ các dòng, nếu không là FAIL):

| Dòng | Điều kiện PASS |
| --- | --- |
| `OK tai campus-backups/db/shlink-<UTC>.dump ... sha256 khop` | sha256 khớp |
| `OK pg_restore vao campus_restore_test trong <n> ms` | không lỗi |
| `shlink: ... migration=X` và `campus_restore_test: ... migration=X` | cùng `X` (cùng phiên bản Shlink) |
| `campus_restore_test: short_urls=a visits=b` | `a`, `b` ≤ số của `shlink` (DB thật có thể đã ghi thêm sau dump) |
| `OK slug tv4fixN: campus_restore_test -> <đích> visits=v | shlink -> <đích> visits=w` (5 dòng) | đích trùng bảng 1.1 ở cả hai bên, `v ≤ w` |
| `OK da DROP campus_restore_test (DROP_AFTER=1)` | DB tạm đã xóa (#50) |
| `PASS restore db/shlink-<UTC>.dump` | exit 0 |

Script tự FAIL (exit 1) nếu một slug thiếu trong bản khôi phục hoặc khác đích so với DB thật. Đã thử cả 2 trường hợp FAIL: `evidence/G3/20261115-FR-INF-16-H5-fixture-restore-thu-local.txt`.

### 3.3. NFR-04 (visit không mất khi restart Shlink)

Chạy 3.1 trước và sau `docker restart` Shlink (TV2 làm trên app VM). Mong đợi: cột 4 (`visitsSummary.total`) sau ≥ trước, cộng thêm đúng số `GET /tv4fixN` gửi giữa hai lần.

## 4. Đã biết còn thiếu hoặc lỗi

- Mục 1.2 chưa có số liệu cụm: điền sau phiên cloud (trước 16/11 19:30), cùng evidence `evidence/G3/<ngay>-FR-INF-16-H5-...-cum.txt`.
- Chưa chạy Shlink trỏ vào `campus_restore_test` (Redis namespace khác) để thử redirect từ bản khôi phục. Script hiện kiểm ở mức dữ liệu (schema version, số bản ghi, 5 slug/đích). Diễn tập tầng 2 FR-INF-25 của TV1 (`ops/dr/dr-tier2.sh`, PR #37) restore dump vào PostgreSQL tạm trên A, cũng ở mức dữ liệu.
- DB VM đang chạy bản `campus-db-restore-test` cũ (chưa có kiểm visit, FAIL theo slug, `DROP_AFTER`): cài lại bằng `install.sh` trong phiên cloud trước khi chạy 3.2.
- `campus_restore_test` có tên cố định: hai người chạy restore thử cùng lúc sẽ ghi đè nhau. Chỉ TV3 chạy.

## 5. Lỗi đã gặp khi làm

- Shlink trả 400 cho cả slug trùng (`non-unique-slug`) và body sai, nên "400 = đã có" không đủ: phải đọc lại đích (mục 3.1).
