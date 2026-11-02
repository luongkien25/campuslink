# H1 – Shlink: digest, cấu hình container, readiness, migration, drain (TV3 → TV2, TV4)

Ngày (UTC): 2026-11-02 · Gate: G3 · Commit: (điền sau khi merge) · Issue: #11
Không ghi secret. Secret thật do TV3 tạo trên DB VM và cấp theo ADR-10 (mục 6), không qua Zalo, issue hay Git.

**Phạm vi bản này:** mọi số liệu đo trên **Compose local** của TV3 (2 replica dùng chung PostgreSQL 16 + Redis 7.0), chưa đo trên cụm. Phần cần đo lại trên guest 1 vCPU/2 GiB ghi ở mục 8. Evidence: `evidence/G3/20261102-H1-shlink-smoke-local.txt`.

## 1. Đã sẵn sàng

| Thứ | Giá trị | Kiểm bằng lệnh |
| --- | --- | --- |
| Image | `shlinkio/shlink@sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee` (OCI index của tag `5.1.8`; manifest amd64 `sha256:9083dc4b…a973`), ghi trong `docs/versions.lock` | `docker buildx imagetools inspect shlinkio/shlink:5.1.8` ra đúng `Digest` trên |
| Hợp đồng env | `app/shlink.env.example` (SRS 4.3, domain thật từ inventory, không secret). Trên app VM chép thành `/opt/campuslink/shlink.env` | `grep -c REPLACE app/shlink.env.example` ra `0` |
| Secret app cần | 2 file: `/run/secrets/db_password` (1 dòng mật khẩu), `/run/secrets/redis_servers` (1 dòng `tcp://default:<mật-khẩu>@10.20.0.10:6379`) | mục 6 |
| Smoke | `app/smoke/h1-smoke.sh` (28 phép thử FR-APP-01–05, 07, 08, 10–12, NFR-12, Redis PING); chạy được cho cụm bằng biến `A`, `B`, `SHORT_BASE` | 28/28 PASS local |
| Compose local | `app/compose/` để thử nhanh hợp đồng mà không cần cloud | mục 3 |
| Runtime | RoadRunner 3.0.1, `WEB_WORKER_NUM=1` + `TASK_WORKER_NUM=1` → 2 tiến trình worker; khởi động lại replica khi DB đã migrate: khoảng 2,3 s tới `/rest/health` 200 (local) | `docker exec shlink sh -c 'ps aux \| grep -c "[r]oadrunner-worker"'` ra `2` |

### 1.1 Chạy container trên app VM (đề xuất, **chưa kiểm trên cụm**)

```
docker run -d --name shlink --restart unless-stopped \
  --env-file /opt/campuslink/shlink.env \
  -v /run/secrets/db_password:/run/secrets/db_password:ro \
  -v /run/secrets/redis_servers:/run/secrets/redis_servers:ro \
  -p 8080:8080 --stop-timeout 30 \
  shlinkio/shlink@sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee
```

- Image phải được nạp sẵn trong Glance image (FR-INF-22), lúc boot không `pull`. Kiểm: `docker image inspect shlinkio/shlink@sha256:68a7…85ee` có kết quả khi VM không ra Internet.
- **Không** đặt `DB_PASSWORD` hay `REDIS_SERVERS` dạng biến thường ở bất kỳ đâu: Shlink đọc biến thường **trước** `*_FILE` (`EnvVars::loadFromEnv`, v5.1.8), nên biến thường sẽ đè lên secret.
- Mount **từng file** như trên, không mount cả thư mục: container chạy uid 1001, còn thư mục `/run/secrets` trên host để 0700/root.
- `--stop-timeout 30`: dừng mềm đo được khoảng 1,3 s (mục 5), 30 s là dư.
- Không ghi đè `--entrypoint` (mục 4).

## 2. Người nhận làm được gì / không được làm gì

- Được: dùng digest, file env và lệnh chạy ở trên để dựng image và app unit; đổi `WEB_WORKER_NUM`/`TASK_WORKER_NUM`/`MEMORY_LIMIT` khi đo (báo TV3 để cập nhật ngân sách kết nối ở mục 5.2); dùng `app/smoke/h1-smoke.sh` trong kiểm thử.
- Không được (hỏi TV3 trước): đổi `CACHE_NAMESPACE`, `DEFAULT_DOMAIN`, `REDIRECT_STATUS_CODE`, `REDIS_PUB_SUB_ENABLED` (portal/stats phụ thuộc); bỏ migration trong entrypoint; đưa secret vào image, user-data, Heat output; tạo API key Shlink (TV3 giữ key admin, SRS 4.2).

## 3. Cách tự kiểm tra (người nhận chạy, đều PASS mới coi là nhận xong)

Trên máy có Docker, trong repo:

```
cd app/compose
./gen-secrets.sh                                  # secret ngau nhien, chi local
docker compose --profile hai-replica up -d        # A :18080, B :18081 (B chi len sau khi A healthy)
curl -sS http://127.0.0.1:18080/rest/health       # {"status":"pass","version":"5.1.8",...}
for n in tv3-admin:"" tv3-donvi-a:--author-only tv3-donvi-b:--author-only; do   # 3 key cho smoke
  docker compose exec -T shlink shlink api-key:generate --name="${n%%:*}" ${n#*:} --no-ansi \
  | grep -oE '[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}' | head -1 > "secrets/api_key_${n%%:*}"; done
cd .. && DB_STOP_CMD='cd compose && docker compose stop postgres' DB_START_CMD='cd compose && docker compose start postgres' ./smoke/h1-smoke.sh
# mong doi dong cuoi: "== ket qua: 0 FAIL"
cd compose && docker compose --profile hai-replica down -v        # don sach
```

Trên cụm (sau FR-INF-12 và app unit đầu tiên), mục 3 của readiness:

```
curl -sS -m 5 http://<ip-app>:8080/rest/health        # 200 va "status":"pass"
# Redis PING: xem muc 3.1
```

### 3.1 Readiness (FR-INF-09): cả hai phải đạt, rồi mới signal WaitCondition và thêm PoolMember

1. `curl -sS -m 5 -o /tmp/h -w '%{http_code}' http://127.0.0.1:8080/rest/health` ra `200` **và** body có `"status":"pass"`. Health chỉ kiểm DB, **không kiểm Redis** (SRS 4.1).
2. Redis PING có xác thực, chỉ dùng file `redis_servers` (đã chạy thật từ một container riêng trong mạng Compose):

   ```
   u=$(cat /run/secrets/redis_servers); hp=${u##*@}; pw=${u#tcp://*:}; pw=${pw%@*}
   [ "$(REDISCLI_AUTH="$pw" redis-cli -h "${hp%:*}" -p "${hp##*:}" --no-auth-warning ping)" = PONG ]
   ```

   - **So output bằng `PONG`, không dùng exit code**: `redis-cli` 7.0 trả exit 0 cả khi sai mật khẩu (in `AUTH failed: WRONGPASS…` rồi `NOAUTH…`).
   - App VM cần `redis-cli` (gói `redis-tools` của Ubuntu 24.04), cài sẵn trong image (chưa kiểm tên gói trên guest).
   - Mật khẩu chỉ gồm ký tự hex (mục 6), nên phần cắt chuỗi ở trên không cần urldecode.
3. Timeout khởi động: 180 s (SRS 4.3). Local, DB đã migrate: khoảng 2,3 s (3 lần đo). Lần đầu trên DB rỗng chưa đo chính xác.

Kết quả mong đợi khi lỗi (đã thấy local): dừng PostgreSQL → health `503` + `"status":"fail"`; Redis sai mật khẩu → không có `PONG`. Cả hai đều phải làm stack fail, không thêm member.

## 4. Migration và thứ tự khởi động

- Entrypoint của image (`docker-entrypoint.sh`) **mỗi lần khởi động** đều chạy `shlink-installer init --no-interaction --clear-db-cache --skip-download-geolite`: tạo schema nếu DB rỗng, chạy migration, sinh proxy Doctrine, xóa cache entity. Sau đó mới `exec rr serve`. Log mong đợi:

  ```
  Initializing database if needed... Success!
  Updating database... Success!
  Generating proxies... Success!
  Clearing entities cache... Success!
  ```

- Thứ tự bắt buộc: **app A (cố định, AZ-A) healthy trước**, rồi mới tạo ASG-B. Trong Heat: `depends_on` của ASG trỏ tới WaitCondition của app A. Replica sau gặp DB đã migrate thì bước "Updating database" không làm gì (đã thấy với replica B local).
- Chưa thử: hai instance cùng khởi động lần đầu trên DB rỗng. Không dựa vào việc này; giữ đúng thứ tự trên.
- DB `shlink` và user `shlink` phải có sẵn trên DB VM (TV3 tạo khi làm FR-INF-12); installer không tạo database.

## 5. Drain visit (O-07) và kết nối DB (O-08)

### 5.1 Drain

Đo bằng `app/smoke/drain-measure.sh`: 300 GET (20 song song) vào replica A, rồi dừng A ngay; đếm visit qua B. Thêm một lượt giới hạn A còn 0,25 CPU để giả lập guest yếu.

| Cách dừng A | Visit mất | Sự kiện Redis pub/sub mất | Thời gian |
| --- | --- | --- | --- |
| Không dừng | 0/300 | 0/300 | visit đủ sau ~0,03 s |
| `docker stop` (SIGTERM) | 0/300 | 0/300 | dừng mất ~1,3 s |
| `docker kill` (SIGKILL) | 0/300 (4 lượt) | 0 và **4/300** (lượt 0,25 CPU) | — |

Vì sao (mã nguồn v5.1.8, `VisitsTracker::trackVisit`): **visit được ghi vào PostgreSQL trong transaction của chính request**, rồi mới phát `UrlVisited`. Hàng đợi bộ nhớ của RoadRunner chỉ chứa listener async: `NotifyVisitToRedis` (pub/sub cho `campus-stats`), Mercure, RabbitMQ, GeoLite (ba cái sau đang tắt).

Thủ tục trước khi dừng một replica (scale-in, bảo trì):

1. Gỡ PoolMember (Heat đã làm trước khi xóa VM, FR-INF-09).
2. Đợi 5 s cho request đang chạy xong (Nginx dùng `Connection close`, request ngắn).
3. `docker stop shlink` (SIGTERM, `--stop-timeout 30`), rồi mới xóa VM.

Nếu VM bị xóa thẳng (Nova delete, không qua bước 3) thì visit vẫn còn, chỉ có thể mất vài sự kiện pub/sub; FR-APP-18 bù bằng đối soát với API visits. Backup (FR-INF-15) không cần drain, vì visit đã nằm trong DB.

**Lệch với SRS mục 2** ("không hứa exactly-once cho visit khi kill/scale-in"): theo đo đạc và mã nguồn, thứ không được hứa là **sự kiện pub/sub**, còn visit thì bền. Đã báo TV1 trong PR để sửa câu đó; H1 không tự sửa SRS.

### 5.2 Kết nối PostgreSQL

Đo `pg_stat_activity` (DB `shlink`): mỗi tiến trình worker PHP giữ tối đa **1** kết nối, Shlink không có pool riêng. Rảnh lâu: 0; đang tải: replica B 2 (1 active + 1 idle), A 1; sau tải: mỗi replica 1.

Ngân sách đề xuất cho DB VM (2 GiB RAM; **đề xuất, chưa áp dụng**):

| Ai | Tính | Số kết nối |
| --- | --- | --- |
| Shlink, tối đa 3 app | 3 × (1 web + 1 task) + 3 × 1 tạm khi entrypoint/CLI chạy | 9 |
| Dự phòng nếu tăng `WEB_WORKER_NUM` lên 2 | +3 | 12 → giới hạn role `shlink` **15** |
| `campus-portal` + `campus-worker` (1.3), `campus-stats` | ước lượng, chốt trong H1b | 20 |
| Backup `pg_dump`, restore test, `psql` quản trị | | 5 |
| `superuser_reserved_connections` | mặc định | 3 |
| **`max_connections`** | | **50** (thay mặc định 100 để tiết kiệm RAM) |

Áp dụng trên DB VM khi làm FR-INF-12: `max_connections = 50` trong `postgresql.conf`; `ALTER ROLE shlink CONNECTION LIMIT 15;`.

## 6. Secret: phần ứng dụng cần từ cơ chế cấp tự động (O-03, ADR-10 trong PR #15)

Ứng dụng cần, **trước khi `docker run`**:

| File trên app VM | Nội dung | Quyền |
| --- | --- | --- |
| `/run/secrets/db_password` | mật khẩu user `shlink`, 1 dòng | 0444, root, thư mục 0700/root |
| `/run/secrets/redis_servers` | `tcp://default:<mật-khẩu>@10.20.0.10:6379`, 1 dòng | như trên |

- Mật khẩu sinh bằng `openssl rand -hex 24` (chỉ ký tự hex): không cần urlencode trong URI và không vỡ khi cắt chuỗi ở readiness. Shlink có urldecode (`shlink-common` `RedisFactory`), nhưng nhóm không dựa vào việc đó.
- Shlink tự cắt khoảng trắng và xuống dòng ở cuối file (`parseEnvVar` có `trim`), nên file kết thúc bằng `\n` không sao.
- `/run` là tmpfs, mất khi reboot: script lấy secret phải chạy **mỗi lần boot**, trước container (systemd: `Before=` unit chạy Shlink).
- Theo ADR-10: TV3 ghi 2 object `campus-secrets/app/db_password` và `campus-secrets/app/redis_servers` sau khi tạo mật khẩu thật trên DB VM (FR-INF-12). Tên object là đề xuất; chốt cùng TV2 trong PR #15.
- Container Shlink **không cần** API key. Key do TV3 tạo bằng CLI (SRS 4.2), không nằm trong VM.

**Chưa chốt, cần phối hợp:**

| Việc | Ai | Hạn đề xuất |
| --- | --- | --- |
| Merge ADR-10, tạo `campus-secrets` và `campus-boot` | TV1 | trước 06/11 |
| Script boot lấy secret vào `/run/secrets`, unit systemd đúng thứ tự | TV2 | cùng image app (G4) |
| Tạo DB VM, mật khẩu thật, ghi 2 object | TV3 | 05–06/11 |
| Thử quyền 0444/uid 1001 trên app VM thật (local là Docker Desktop, tự đổi chủ sở hữu file nên chưa chứng minh được) | TV2 + TV3 | phiên cụm đầu tiên |

## 7. Đã biết còn thiếu hoặc lỗi

- Toàn bộ chạy trên Compose local, chưa qua Nginx/TLS/Octavia. `TRUSTED_PROXIES=1` đúng với chuỗi Nginx → OVN LB (L4, không thêm hop) → app, nhưng chưa kiểm IP thật trong visit.
- NFR-15 (guest UUID/IP trong log) chưa làm: log Shlink là JSON nhưng không có thông tin VM; đề xuất TV2 gắn qua log driver/tag của Docker trên VM.
- `REDIS_PUB_SUB_ENABLED=true`: topic thấy được là `https://shlink.io/new-visit`, `https://shlink.io/new-visit/{shortCode}`, `https://shlink.io/new-short-url`; payload JSON có `shortUrl.shortCode`, `tags`. Đây chỉ là quan sát, O-12 vẫn do TV4 chốt.
- Phiên bản Redis/PostgreSQL local (7.0.15, 16.15) gần với apt Ubuntu 24.04 nhưng chưa đối chiếu bản patch trên DB VM.

## 8. Đo lại trên cụm (bổ sung vào H1 khi có)

- Smoke `h1-smoke.sh` qua `https://s.44-198-215-187.sslip.io` (`SHORT_BASE`), A và B là IP app thật.
- Drain và pub/sub trên guest 1 vCPU/2 GiB; số kết nối thật trên DB VM.
- Thời gian khởi động tới ready (đầu vào NFR-06).

## 9. Lỗi đã gặp khi làm (đã thêm vào `docs/troubleshooting.md`)

- `redis-cli` exit 0 khi sai mật khẩu → readiness phải so output `PONG`.
- Docker Desktop đổi chủ sở hữu file bind-mount (thấy uid 1001 thay vì uid của người dùng) → phép thử quyền file secret trên Compose local không có giá trị chứng minh.
