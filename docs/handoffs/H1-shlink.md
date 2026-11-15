# H1 – Shlink: digest, cấu hình container, readiness, migration, drain (TV3 → TV2, TV4)

Ngày (UTC): 2026-11-02 · Gate: G3 · Commit: (điền sau khi merge) · Issue: #11
Không ghi secret. Secret thật do TV3 tạo trên DB VM và cấp theo ADR-10 (mục 6), không qua Zalo, issue hay Git.

**Phạm vi bản này:** mọi số liệu đo trên **Compose local** của TV3 (2 replica dùng chung PostgreSQL 16 + Redis 7.0), chưa đo trên cụm. Phần cần đo lại trên guest 1 vCPU/2 GiB ghi ở mục 8. Evidence: `evidence/G3/20261102-H1-shlink-smoke-local.txt` (02/11) và `evidence/G3/20261105-H1-shlink-smoke-local-lan2.txt` (05/11, chạy lại mục 3, Redis probe, dấu hiệu lỗi).

## 1. Đã sẵn sàng

| Thứ | Giá trị | Kiểm bằng lệnh |
| --- | --- | --- |
| Image | `shlinkio/shlink@sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee` (OCI index của tag `5.1.8`; manifest amd64 `sha256:9083dc4b…a973`), ghi trong `docs/versions.lock` | `docker buildx imagetools inspect shlinkio/shlink:5.1.8` ra đúng `Digest` trên |
| Hợp đồng env | `app/shlink.env.example` (SRS 4.3, domain thật từ inventory, không secret). Trên app VM chép thành `/opt/campuslink/shlink.env` | `grep -c REPLACE app/shlink.env.example` ra `0` |
| Secret app cần | 2 file: `/run/secrets/db_password` (1 dòng mật khẩu), `/run/secrets/redis_servers` (1 dòng `tcp://default:<mật-khẩu>@10.20.0.10:6379`) | mục 6 |
| Smoke | `app/smoke/h1-smoke.sh` (27 phép thử FR-APP-01–05, 07, 08, 10–12, NFR-12, Redis PING); chạy được cho cụm bằng biến `A`, `B`, `SHORT_BASE` | 27/27 PASS local (02/11 và 05/11) |
| Probe Redis | `app/smoke/redis-probe.sh`: PING có xác thực, chỉ đọc file `redis_servers`, exit code đúng | mục 3.1 |
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

Trên máy có Docker, trong repo (đã chạy nguyên khối này từ Compose rỗng ngày 05/11, kết quả 27 PASS, 0 FAIL; evidence `20261105-H1-shlink-smoke-local-lan2.txt`):

```
cd app/compose
./gen-secrets.sh                                  # secret ngau nhien, chi local
docker compose --profile hai-replica up -d --wait # A :18080, B :18081; --wait cho ca 2 healthy (thieu --wait thi health B co the FAIL)
curl -sS http://127.0.0.1:18080/rest/health       # {"status":"pass","version":"5.1.8",...}
for n in tv3-admin:"" tv3-donvi-a:--author-only tv3-donvi-b:--author-only; do   # 3 key cho smoke
  docker compose exec -T shlink shlink api-key:generate --name="${n%%:*}" ${n#*:} --no-ansi \
  | grep -oE '[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}' | head -1 > "secrets/api_key_${n%%:*}"; done
cd ..
REDIS_PING_CMD='cd compose && docker compose run --rm --no-deps -T -v "$PWD/secrets/redis_servers:/run/secrets/redis_servers:ro" -v "$PWD/../smoke/redis-probe.sh:/probe.sh:ro" --entrypoint sh redis /probe.sh 2>/dev/null' \
DB_STOP_CMD='cd compose && docker compose stop postgres' \
DB_START_CMD='cd compose && docker compose start postgres' \
./smoke/h1-smoke.sh
# mong doi: 27 dong PASS (co "FR-INF-09 Redis PING co xac thuc (=PONG)"), dong cuoi "== ket qua: 0 FAIL"
cd compose && docker compose --profile hai-replica down -v        # don sach
```

- `REDIS_PING_CMD` chạy **đúng** `redis-probe.sh` của mục 3.1 trong một container riêng chỉ được mount file `redis_servers`, giống app VM. Không đặt biến này thì smoke bỏ qua Redis probe và chỉ còn 26 phép thử.
- `2>/dev/null` để bỏ dòng "Container … Creating" mà `docker compose run` in ra stderr; smoke so stdout đúng bằng `PONG`.
- Docker Desktop không mount được file trong `/tmp`; để file thử trong `app/compose/secrets/`.

Trên cụm (sau FR-INF-12 và app unit đầu tiên), mục 3 của readiness:

```
curl -sS -m 5 http://<ip-app>:8080/rest/health        # 200 va "status":"pass"
# Redis PING: xem muc 3.1
```

### 3.1 Readiness (FR-INF-09): cả hai phải đạt, rồi mới signal WaitCondition và thêm PoolMember

1. `curl -sS -m 5 -o /tmp/h -w '%{http_code}' http://127.0.0.1:8080/rest/health` ra `200` **và** body có `"status":"pass"`. Health chỉ kiểm DB, **không kiểm Redis** (SRS 4.1).
2. Redis PING có xác thực: `app/smoke/redis-probe.sh [/run/secrets/redis_servers]`. Script chỉ đọc file, không in mật khẩu; in `PONG` + exit 0 khi đúng, `FAIL` + exit 1 khi khác. Đã chạy từ container riêng trong mạng Compose (05/11): đúng mật khẩu → `PONG`, exit 0; file chứa mật khẩu sai → `FAIL`, exit 1.

   - Script tự so output với `PONG` vì `redis-cli` 7.0 trả **exit 0 cả khi sai mật khẩu** (in `AUTH failed: WRONGPASS…` rồi `NOAUTH…`). Nếu tự viết probe, đừng dựa vào exit code của `redis-cli`.
   - App VM cần `redis-cli` (gói `redis-tools` của Ubuntu 24.04), cài sẵn trong image (chưa kiểm tên gói trên guest) và `timeout` (coreutils).
   - Mật khẩu chỉ gồm ký tự hex (mục 6), nên phần cắt chuỗi trong script không cần urldecode.
3. Timeout khởi động: 180 s (SRS 4.3).

### 3.2 Dấu hiệu xong, dấu hiệu lỗi và thời gian (đo local, Docker Desktop, 05/11)

| Tình huống | Thấy gì | Thời gian | Readiness làm gì |
| --- | --- | --- | --- |
| Bình thường, DB rỗng (instance đầu) | Log 4 dòng `... Success!` rồi `RoadRunner server started`; `/rest/health` 200 `pass`; probe `PONG` | container start → RoadRunner: **1,1 s** | Đạt cả 2 điều kiện ở 3.1 → signal |
| Bình thường, DB đã migrate (replica sau) | Như trên, "Updating database" không làm gì | khởi động lại → health 200: **~2,3 s** (3 lần, đo 02/11) | Như trên |
| Mật khẩu DB sai | Container **thoát exit 1**; log `[ERROR] Error generating database..` và `[ERROR] Error updating database..`; RoadRunner không chạy | thoát sau **~1,2 s** | `docker inspect -f '{{.State.Status}}' shlink` khác `running` (hoặc `RestartCount` > 0 khi có `--restart`) → fail ngay, không đợi hết 180 s |
| **Redis sai mật khẩu/không tới được** | **Giống hệt dòng trên**: exit 1, log vẫn ghi "Error … database" (nguyên nhân thật là `Predis\Connection\ConnectionException`, xem bằng `-e SHELL_VERBOSITY=3`) | thoát sau **~1,2 s**, cả với DB rỗng lẫn DB đã migrate | Như trên; đọc log đừng chỉ đi sửa DB |
| PostgreSQL dừng sau khi app đã chạy | `/rest/health` **503** `"status":"fail"`; container vẫn `running`; bật DB lại → 200 trong vài giây | — | Không đạt điều kiện 1 → không signal |

- **Dấu hiệu migration xong:** `/rest/health` trả 200. Entrypoint chạy `set -e`, nên RoadRunner (và cổng 8080) chỉ chạy khi installer thoát 0. Đừng dựa vào chữ `Success!` trong log: khi lỗi, hai dòng `Generating proxies… Success!` và `Clearing entities cache… Success!` vẫn xuất hiện.
- **Điều kiện khởi động replica tiếp theo:** app A đạt cả 2 điều kiện ở 3.1.
- Chưa thử: Redis mất **sau khi** app đã chạy (health vẫn chỉ kiểm DB).

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

Đo bằng `app/smoke/drain-measure.sh`: 300 GET (20 song song) vào replica A, **đợi cả 300 GET trả 302 xong**, rồi mới dừng A; đếm visit qua B. Thêm một lượt giới hạn A còn 0,25 CPU để giả lập guest yếu.

**Phạm vi của kết quả này:** chỉ nói về visit và sự kiện của các request **đã trả lời xong** lúc replica bị dừng (hàng đợi task nền còn việc). Phép đo **không** có request đang xử lý giữa chừng, nên chưa kết luận được gì về request đang chạy khi replica bị dừng (client có nhận lỗi không, visit của request đó có ghi không). Phần này cần đo riêng trên cụm (mục 8).

| Cách dừng A | Visit mất | Sự kiện Redis pub/sub mất | Thời gian |
| --- | --- | --- | --- |
| Không dừng | 0/300 | 0/300 | visit đủ sau ~0,03 s |
| `docker stop` (SIGTERM) | 0/300 | 0/300 | dừng mất ~1,3 s |
| `docker kill` (SIGKILL) | 0/300 (4 lượt) | 0 và **4/300** (lượt 0,25 CPU) | — |

Vì sao (mã nguồn v5.1.8, `VisitsTracker::trackVisit`): **visit được ghi vào PostgreSQL trong transaction của chính request**, rồi mới phát `UrlVisited`. Hàng đợi bộ nhớ của RoadRunner chỉ chứa listener async: `NotifyVisitToRedis` (pub/sub cho `campus-stats`), Mercure, RabbitMQ, GeoLite (ba cái sau đang tắt).

Thủ tục trước khi dừng một replica (scale-in, bảo trì):

1. Gỡ PoolMember (Heat đã làm trước khi xóa VM, FR-INF-09).
2. Đợi 5 s cho request đang chạy xong. **Đây là đề xuất, chưa đo**: dựa trên việc Nginx dùng `Connection close` và request redirect ngắn; phải kiểm lại trên cụm cùng phép đo request đang xử lý (mục 8).
3. `docker stop shlink` (SIGTERM, `--stop-timeout 30`), rồi mới xóa VM.

Nếu VM bị xóa thẳng (Nova delete, không qua bước 3) thì visit của request **đã trả lời** vẫn còn, chỉ có thể mất vài sự kiện pub/sub; FR-APP-18 bù bằng đối soát với API visits. Backup (FR-INF-15) không cần drain, vì visit của request đã trả lời nằm sẵn trong DB.

**Lệch với SRS mục 2** ("không hứa exactly-once cho visit khi kill/scale-in"): với request đã trả lời, đo đạc và mã nguồn cho thấy thứ có thể mất là **sự kiện pub/sub**, không phải visit. Với request đang xử lý thì chưa đo, nên câu trong SRS vẫn đúng cho trường hợp đó. Đề nghị TV1 làm rõ câu này; H1 không tự sửa SRS.

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
| Tạo DB VM, mật khẩu thật, ghi 2 object | TV3 | **xong 08/11** (mục 10) |
| Thử quyền 0444/uid 1001 trên app VM thật (local là Docker Desktop, tự đổi chủ sở hữu file nên chưa chứng minh được) | TV2 + TV3 | phiên cụm đầu tiên |

## 7. Đã biết còn thiếu hoặc lỗi

- Toàn bộ chạy trên Compose local, chưa qua Nginx/TLS/Octavia. `TRUSTED_PROXIES=1` đúng với chuỗi Nginx → OVN LB (L4, không thêm hop) → app, nhưng chưa kiểm IP thật trong visit.
- NFR-15 (guest UUID/IP trong log) chưa làm: log Shlink là JSON nhưng không có thông tin VM; đề xuất TV2 gắn qua log driver/tag của Docker trên VM.
- `REDIS_PUB_SUB_ENABLED=true`: topic thấy được là `https://shlink.io/new-visit`, `https://shlink.io/new-visit/{shortCode}`, `https://shlink.io/new-short-url`; payload JSON có `shortUrl.shortCode`, `tags`. Đây chỉ là quan sát, O-12 vẫn do TV4 chốt.
- Phiên bản Redis/PostgreSQL local (7.0.15, 16.15) **khớp** bản apt trên DB VM (đối chiếu 08/11, mục 10).

## 8. Đo lại trên cụm (bổ sung vào H1 khi có)

- Smoke `h1-smoke.sh` qua `https://s.44-198-215-187.sslip.io` (`SHORT_BASE`), A và B là IP app thật.
- Drain và pub/sub trên guest 1 vCPU/2 GiB; số kết nối thật trên DB VM.
- **Request đang xử lý khi dừng replica:** bắn tải liên tục qua VIP, gỡ member, đợi N giây, `docker stop`; đếm lỗi phía client và so số visit với số 302 nhận được. Từ đó chốt thời gian chờ ở bước 2 mục 5.1 (hiện là đề xuất 5 s). Làm chung với fault run FR-INF-20 (TV2 + TV4).
- Thời gian khởi động tới ready (đầu vào NFR-06).

## 9. Lỗi đã gặp khi làm (đã thêm vào `docs/troubleshooting.md`)

- `redis-cli` exit 0 khi sai mật khẩu → readiness phải so output `PONG`.
- `docker compose up -d` trả về khi replica B mới được tạo, chưa phục vụ → smoke ngay sau đó FAIL health B (`curl: (52) Empty reply from server`). Dùng `up -d --wait`.
- Redis sai mật khẩu làm container thoát với log "Error generating database" → dễ sửa nhầm DB (mục 3.2).
- Docker Desktop đổi chủ sở hữu file bind-mount (thấy uid 1001 thay vì uid của người dùng) → phép thử quyền file secret trên Compose local không có giá trị chứng minh.

## 10. DB VM trên cụm (FR-INF-12, O-08, issue #27; 08/11/2026)

Làm theo `docs/runbooks/db-vm.md`. Evidence: `evidence/G3/20261108-FR-INF-12-db-vm.txt`.

| Thứ | Giá trị | Kiểm bằng (`OS_CLOUD=campus-tvN` trên A) |
| --- | --- | --- |
| VM | `campus-db` `6d17a9e8-4975-4c46-afd6-be1017e2a251`, `campus.db`, `campus-az-a`, `ubuntu-noble-base`, port `campus-db-port` 10.20.0.10, chỉ `campus-db-sg`, không FIP | `openstack server show campus-db -c status -c addresses` |
| Volume | `campus-db-data` gắn `/dev/vdb`, ext4, mount `/var/lib/postgresql` theo UUID, `nofail` | `openstack volume show campus-db-data -c status` → `in-use` |
| PostgreSQL | 16.15 (apt), `max_connections=50`, DB `shlink` owner role `shlink` `CONNECTION LIMIT 15`, `pg_hba`: chỉ `shlink`→`shlink` từ `10.20.0.0/24`, `scram-sha-256` | console: dòng `campus-db-check: OK postgresql ...` |
| Redis | 7.0.15 (apt), `10.20.0.10:6379`, có mật khẩu, AOF, `maxmemory 256mb` `noeviction` (đề xuất, chốt cùng TV4), dữ liệu trên đĩa gốc | console: `OK redis ... PING=PONG`, `OK redis khong mat khau bi tu choi` |
| Secret | `campus-secrets/app/db_password` (49 byte), `campus-secrets/app/redis_servers` (79 byte), đúng định dạng mục 6; etag khớp lúc ghi | `openstack object list campus-secrets --prefix app/` |
| Tự kiểm | `campus-db-check.service` mỗi lần boot in `OK`/`FAIL` ra console, không in secret | `openstack console log show campus-db \| grep campus-db-check` |

Đã kiểm trên cụm: reboot giữ nguyên cấu hình, PG và Redis tự lên; tháo volume rồi boot thì PostgreSQL **không chạy** (`FAIL chua mount`, `postgresql@16-main inactive`), gắn lại thì về `OK`; `member` không đọc được `user_data` của VM qua Nova API; gắn volume AZ `nova` vào VM `campus-az-a` chạy được.

Chưa kiểm, người nhận (TV2) làm khi chạy clone:
- Kết nối 5432/6379 từ VM có `campus-app-sg` (SG `campus-db-sg` chỉ nhận từ SG này; VM ngoài SG sẽ timeout, không phải lỗi mật khẩu).
- Shlink chạy migration trên DB thật (local đã chạy được với cùng cấu hình, `evidence/G3/20261107-FR-INF-12-db-vm-thu-local.txt`).
- ~~"Reboot: link còn" của FR-INF-12~~: **đã kiểm 12/11** với link `tv2g4-20261111` của TV2, `short_urls=1 visits=2` trước và sau reboot (`evidence/G3/20261112-FR-INF-15-16-backup-restore-cum.txt`).

Backup (FR-INF-15, 12/11): timer trên `campus-db` dump `shlink` mỗi giờ lên `campus-backups/db/`, giữ 48 bản; restore thử vào `campus_restore_test` bằng `campus-db-restore-test`. Thủ tục: `docs/runbooks/db-backup.md`.

Lưu ý vận hành:
- Mật khẩu đưa vào VM qua user-data (rủi ro chấp nhận như ADR-10, runbook mục "Thiết kế"); đổi mật khẩu về sau bằng `ALTER ROLE` trên VM rồi ghi lại object Swift, không qua user-data.
- Không tạo lại `campus-db` trên volume đã có dữ liệu bằng user-data này: script sẽ dừng (`FAIL volume da co du lieu PostgreSQL`), xem runbook mục 8.
- Port 22 của DB VM đóng (SG); gỡ lỗi bằng console log, cần vào máy thì dùng VM nhảy theo H2 mục 4.1 (keypair `tv3`).

