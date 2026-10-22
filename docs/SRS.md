# SRS – CampusLink (Nhóm 11)

> Bản Markdown xuất ngày 22/10/2026 từ Claude Doc "SRS – CampusLink (Nhóm 11)". Khi sửa yêu cầu, giữ nguyên mã FR/NFR/O để các issue, PR và prompt cho AI agent tham chiếu đúng.

**Có cần SRS không?** Có, nhưng là bản gọn để làm việc. Đề xuất nói *làm gì*, bản phân công nói *ai làm khi nào*, Lab TV1 nói *làm thế nào*; còn thiếu một chỗ đánh mã từng yêu cầu và ghi rõ phép thử PASS, để mỗi người (và AI agent khi "vibe code") nhìn một bảng là biết việc của mình xong hay chưa. SRS này chỉ tổng hợp từ 3 tài liệu nhóm, không thêm phạm vi mới; điểm chưa chốt nằm ở mục 7.

## 1. Giới thiệu

**Mục đích.** SRS này gom các yêu cầu đã rải trong đề xuất và bản phân công v1.1 thành một nơi duy nhất, có mã yêu cầu (FR/NFR) để mỗi thành viên biết mình phải làm gì, nhận gì từ ai và thế nào là PASS. SRS không thay thế bản phân công: phân công nói *ai làm, khi nào*; SRS nói *hệ thống phải làm được gì và đo thế nào*.

**Phạm vi.** CampusLink là dịch vụ rút gọn link cho trường, dùng Shlink v5.1.8 (backend) và Shlink Web Client v4.8.1 (UI) chạy trong Nova VM trên OpenStack DevStack stable/2026.1, lồng trong 2 EC2 AWS ở 2 AZ. Phạm vi gồm: tạo/sửa/chuyển hướng link, thống kê visit, QR, gắn tag theo chiến dịch, cân bằng tải, tự động mở rộng, lưu trữ block/object, sao lưu/khôi phục, phân quyền và đo hiệu năng. Ngoài phạm vi: viết lại backend/schema, Kubernetes/Magnum, chịu lỗi mất cả một AZ, bản đồ địa lý GeoLite, real-time Mercure.

**Thuật ngữ.**

| Thuật ngữ | Nghĩa trong SRS |
| --- | --- |
| Host A / Host B | EC2 A (controller + compute + gateway + storage, AZ-A) / EC2 B (compute, AZ-B) |
| App A / App B | Nova VM chạy container Shlink, đặt ở host A / host B |
| DB VM | VM 10.20.0.10 chứa PostgreSQL và Redis ứng dụng |
| VIP | Địa chỉ Octavia OVN LB trong mạng nội bộ OpenStack |
| short domain / admin domain | `s.CAMPUS_DOMAIN` (redirect) / `admin.CAMPUS_DOMAIN` (Web Client); `CAMPUS_DOMAIN` = `<EIP-gạch-ngang>.sslip.io`, xem mục 2 |
| Gate G0–G5 | Cổng nghiệm thu theo lịch trong bản phân công |
| H0–H6 | Mốc bàn giao giữa các thành viên |
| PASS | Điều kiện cần đạt, chưa phải kết quả đã có |

**Tài liệu tham chiếu.**

- Đề xuất dự án CampusLink (4 trang) của Nhóm 11.
- CampusLink – Phân công chi tiết & kế hoạch phối hợp, bản 1.1 - Shlink, 22/10/2026 (`docs/references/`).
- CampusLink – Lab TV1, bản 1.1, 22/10/2026.
- OpenAPI và HealthAction của Shlink v5.1.8 (nguồn S28–S29 trong bản phân công).

## 2. Mô tả tổng quan

**Bối cảnh.** Câu lạc bộ và đơn vị trong trường cần link ngắn/QR cho sự kiện, tài liệu và chiến dịch, cần đổi đích đến và xem lượt truy cập. Khi tải tăng hoặc một VM ứng dụng lỗi, dịch vụ vẫn phải chuyển hướng đúng và mở rộng được. Trọng tâm đánh giá là hạ tầng cloud, không phải viết ứng dụng mới.

**Luồng chính.** Người dùng → EIP AWS → Nginx trên host A:443 (TLS) → floating IP nội bộ của VIP (172.24.4.x) → Octavia OVN TCP LB → App A / App B :8080 → PostgreSQL + Redis trên DB VM 10.20.0.10. Backup: `pg_dump` → Swift private → restore vào DB tách biệt.

**Tác nhân.**

| Tác nhân | Vai trò | Kênh truy cập |
| --- | --- | --- |
| Người truy cập link | Mở link ngắn/QR, được chuyển hướng | `https://s.CAMPUS_DOMAIN/{shortCode}` |
| Quản trị nội dung (CLB/đơn vị) | Tạo/sửa link, gắn tag, xem thống kê, tạo QR | Web Client tại `https://admin.CAMPUS_DOMAIN`, nhập API key riêng |
| Client API / script kiểm thử | Gọi REST v3 bằng `X-Api-Key` | Locust, smoke test, fixture |
| Quản trị cloud (TV1) | Quản trị AWS và OpenStack admin | SSH tới A, ProxyJump tới B |
| Thành viên dự án (TV2/TV3 member, TV4 reader) | Vận hành trong project `campuslink` | OpenStack CLI qua SSH, không public API |

**Ràng buộc.**

| Mã | Ràng buộc |
| --- | --- |
| C-01 | AWS us-east-1, 2 EC2 ở 2 AZ: A m7i.2xlarge (8 vCPU/32 GiB, public-A 10.11.0.10), B m7i.xlarge (4 vCPU/16 GiB, private-B 10.11.11.10, không public IPv4). Không thêm EC2. |
| C-02 | Ubuntu 24.04 LTS x86_64, DevStack stable/2026.1, khóa SHA từng repo sau smoke. Nested KVM bắt buộc; không benchmark trên QEMU. |
| C-03 | Neutron ML2/OVN, Octavia provider `ovn` (TCP, không Amphora), Heat + Ceilometer + Gnocchi + Aodh. |
| C-04 | Shlink v5.1.8 + Web Client v4.8.1, khóa image digest; không dùng `develop` hay `latest`. Không sửa backend/schema upstream. |
| C-05 | PostgreSQL 16 trên Cinder volume; Redis ứng dụng dùng chung, riêng với Redis của Gnocchi. Không SQLite khi có nhiều replica. |
| C-06 | Flavor: app 1 vCPU/2 GiB/10 GiB; DB 1 vCPU/2 GiB/10 GiB + Cinder 10 GiB; builder 2 vCPU/4 GiB tạm. Tổng app 2–3 VM. |
| C-07 | Quota project `campuslink`: 6 instance, 8 vCPU, 12 GiB RAM, 5 volume/30 GiB, 3 floating IP. |
| C-08 | Ngân sách lab mục tiêu 70 USD (kế hoạch 52–67 USD cho 40–60 giờ/EC2); EC2 chỉ bật theo phiên. |
| C-09 | Nộp 09/11/2026, bảo vệ 16/11/2026. Không nâng phiên bản sau freeze. |

**Giả định và giới hạn đã chấp nhận.**

- Host A là điểm lỗi đơn của ingress, controller, gateway, Cinder/Swift và DB. Hệ thống không chịu được mất cả AZ-A (ADR-05).
- Octavia OVN chỉ có TCP monitor, không phát hiện API trả 500; HTTP readiness được kiểm trước khi đăng ký member.
- Autoscaling không được hứa là cải thiện hiệu năng; kết quả đo thật được báo cáo kể cả khi không cải thiện (ADR-06).
- Queue background của RoadRunner nằm trong bộ nhớ; không hứa exactly-once cho visit khi kill/scale-in.
- "Campaign" được ánh xạ thành tag Shlink (ví dụ `campus-open-day`).

**Domain (chốt 22/10/2026, cập nhật cùng ngày).** Nhóm không mua domain. `CAMPUS_DOMAIN` = `<EIP-gạch-ngang>.sslip.io`, ví dụ EIP 3.91.10.20 → `3-91-10-20.sslip.io`. sslip.io là DNS công khai miễn phí, tự phân giải mọi tên dạng này về đúng IP, không cần đăng ký. Vì vậy `s.CAMPUS_DOMAIN` (link ngắn) và `admin.CAMPUS_DOMAIN` (Web Client) cùng trỏ về EIP của host A, và mọi máy trên Internet, kể cả điện thoại quét QR, phân giải được mà không sửa hosts. Chứng thư TLS lấy từ Let's Encrypt bằng certbot (HTTP-01, SAN chứa cả 2 tên, tự gia hạn). Không dùng `curl -k` hay tắt TLS verification để báo PASS. EIP phải giữ cố định tới hết buổi bảo vệ: đổi EIP là đổi domain và mọi QR đã phát hành mất hiệu lực.

**Sơ đồ kiến trúc.** Host A gánh ingress, LB, DB và storage; host B chỉ chạy app.

![Sơ đồ kiến trúc CampusLink · 2 EC2, 2 AZ](images/kien-truc.png)

*Nguồn sơ đồ (Mermaid, để sửa): `docs/images/kien-truc.mmd`.*

Mọi request đi qua Nginx và VIP trên host A rồi mới tới app; vì vậy tắt app A chỉ là lỗi app, còn tắt EC2 A làm mất cả hệ thống. Guest dùng `campus-net` 10.20.0.0/24, Geneve nối A↔B.

## 3. Yêu cầu chức năng

Có 34 yêu cầu, chia 2 nhóm: chức năng ứng dụng mà người dùng thấy (FR-APP) và chức năng hạ tầng mà môn học chấm (FR-INF, bám 8 hạng mục bắt buộc). Mức ưu tiên: **P0** = thiếu thì trượt tiêu chí; **P1** = cần cho demo; **P2** = chưa dùng trong bản này. Cột "Kiểm bằng" là phép thử tối thiểu để ghi PASS.

### 3.1 Chức năng ứng dụng (Shlink + Web Client)

| Mã | Yêu cầu | Ưu tiên | Chủ trì | Kiểm bằng |
| --- | --- | --- | --- | --- |
| FR-APP-01 | Tạo link ngắn từ `longUrl`, cho phép `customSlug` và `tags`; trả `shortUrl` dạng `https://s.CAMPUS_DOMAIN/...` | P0 | TV3 | `POST /rest/v3/short-urls` → 200, `shortUrl` đúng domain HTTPS |
| FR-APP-02 | Chuyển hướng `GET /{shortCode}` bằng HTTP 302 với `Location` = `longUrl` | P0 | TV3 | curl không follow → 302 + Location đúng |
| FR-APP-03 | Sửa đích đến của link đã có; thay đổi có hiệu lực trên mọi replica | P0 | TV3 | `PATCH` rồi GET qua cả app A và app B → Location mới |
| FR-APP-04 | Ghi nhận visit cho mỗi lượt GET redirect và xem danh sách visit có phân trang | P0 | TV3 | `GET .../visits` sau khi đợi task nền, đếm khớp số GET (cùng bộ lọc bot/UA) |
| FR-APP-05 | Gắn tag chiến dịch và xem thống kê theo tag | P1 | TV3 | `GET /rest/v3/tags/stats` có tag `campus-open-day` với số link/visit |
| FR-APP-06 | Tạo QR cho short URL ngay trong Web Client (Shlink 5 không còn endpoint QR backend) | P1 | TV3 | Quét QR bằng điện thoại → mở đúng `shortUrl` |
| FR-APP-07 | Mọi API quản trị yêu cầu header `X-Api-Key`; thiếu/sai key bị từ chối | P0 | TV3 | Không key hoặc key sai → 401 |
| FR-APP-08 | Mỗi thành viên có API key riêng có tên; key `--author-only` chỉ thấy link do chính key tạo | P0 | TV3 | Key A không đọc được link riêng của key B |
| FR-APP-09 | Web Client chạy dạng SPA tĩnh tại admin domain; refresh route không 404; người dùng tự nhập server URL + key | P0 | TV3 (build), TV1 (Nginx) | Mở `https://admin.../` → thêm server → liệt kê link; F5 ở route con không 404 |
| FR-APP-10 | CORS chỉ cho phép origin admin domain gọi API với `X-Api-Key`, `Content-Type` | P0 | TV3 | Preflight `OPTIONS` từ origin admin → allow-origin đúng |
| FR-APP-11 | Endpoint health `GET /rest/health` trả 200/`pass` khi truy vấn DB được, 503/`fail` khi DB lỗi | P0 | TV3 | Dừng PostgreSQL → 503; bật lại → 200 |
| FR-APP-12 | Tài nguyên không tồn tại trả 404; tạo trùng slug trả 400 `non-unique-slug` | P1 | TV3 | Gọi slug không có; tạo 2 lần cùng slug |

### 3.2 Chức năng hạ tầng

| Mã | Yêu cầu | Ưu tiên | Chủ trì | Kiểm bằng |
| --- | --- | --- | --- | --- |
| FR-INF-01 | 2 EC2 ở 2 AWS AZ; VPC 10.11.0.0/16 với 4 subnet; B không public IPv4, ra Internet qua NAT trên A | P0 | TV1 | Ảnh EC2 AZ ID + route table; B `apt update` được |
| FR-INF-02 | Nested KVM hoạt động trên cả A và B | P0 | TV1 | `/dev/kvm`, `kvm-ok` trên 2 host |
| FR-INF-03 | 2 nova-compute up; 2 Nova AZ `campus-az-a`/`campus-az-b` ánh xạ đúng host A/B | P0 | TV1 | `openstack aggregate show`, VM tạo ở đúng host |
| FR-INF-04 | Mạng tenant `campus-net` 10.20.0.0/24 (MTU 1400) nối guest xuyên host qua Geneve; guest ra Internet qua SNAT router | P0 | TV1 | Ping DF 1372 byte + HTTP A↔B; curl ra ngoài từ guest |
| FR-INF-05 | App/DB VM không có floating IP; cổng 8080/5432/6379/API quản trị không truy cập được từ Internet | P0 | TV1/TV3 | Quét cổng từ máy ngoài VPC: chỉ 80, 443 (và 22 từ /32 cho phép) mở |
| FR-INF-06 | Ingress: EIP → Nginx A:443 (TLS) → FIP nội bộ của VIP:8080; admin domain phục vụ Web Client tĩnh | P0 | TV1 (+TV3 cert) | `curl https://s.../rest/health` từ Internet → 200 với cert hợp lệ, không `-k` |
| FR-INF-07 | Octavia provider `ovn`: listener TCP 8080, pool `SOURCE_IP_PORT`, TCP health monitor | P0 | TV2 | Nhiều kết nối mới đi tới cả 2 backend (log/capture từng guest) |
| FR-INF-08 | Heat giữ 1 app cố định ở AZ-A và ASG-B min 1/max 2 ở AZ-B (tổng 2–3 app) | P0 | TV2 | `templates/root.yaml`; manual policy 1→2→1 ở B |
| FR-INF-09 | Mỗi app unit: VM → readiness (health 200 + Redis PING có auth) → WaitCondition → PoolMember; xóa thì gỡ member trước VM | P0 | TV2 | Cố ý làm DB unreachable → stack fail, không thêm member |
| FR-INF-10 | Ceilometer thu metric CPU của VM app ở cả 2 host; Gnocchi lưu granularity 60 s; Aodh đánh giá ngưỡng và gọi scaling policy | P0 | TV2 | Có metric có đơn vị/timestamp cho VM A và B; alarm history có chuyển ALARM |
| FR-INF-11 | Tải thật kích hoạt scale-out 2→3 và scale-in 3→2 tự động | P0 | TV2 + TV4 | Timeline: load → ALARM → Heat event → VM ready → request đầu trên VM mới |
| FR-INF-12 | PostgreSQL 16 + Redis ứng dụng trên DB VM 10.20.0.10, dữ liệu PostgreSQL nằm trên Cinder volume 10 GiB | P0 | TV3 (TV1 cấp port/volume) | Reboot DB VM: link còn; thiếu mount thì PostgreSQL không chạy |
| FR-INF-13 | Cinder LVM backend trên EBS 30 GiB riêng, attach/detach giữ dữ liệu | P0 | TV1 | File test có checksum khớp sau detach/attach |
| FR-INF-14 | Swift container `campus-backups` private, upload/download đúng checksum | P0 | TV1 | Request không token bị từ chối (không phải timeout) |
| FR-INF-15 | Backup `pg_dump -Fc` → Swift theo lịch, có checksum/retention, thêm 1 bản về máy nhóm | P0 | TV3 | Object có trong Swift + checksum khớp bản local |
| FR-INF-16 | Restore vào DB tách biệt `campus_restore_test` (Redis namespace khác), cùng phiên bản Shlink | P0 | TV3 | Kiểm schema version, số bản ghi fixture và 5 slug/target đã chốt |
| FR-INF-17 | IAM role `CampusLinkBackup` gắn EC2 A, chỉ được `CreateSnapshot` volume đã duyệt với tag `Project=CampusLink` | P0 | TV1 | Dry-run: volume đúng → `DryRunOperation`; volume B → `UnauthorizedOperation`; 1 snapshot completed |
| FR-INF-18 | Keystone: project `campuslink`; TV2/TV3 `member`, TV4 `reader`; không có admin credential trong guest/app | P0 | TV1 | Reader tạo VM → 403; member tạo project → 403 |
| FR-INF-19 | Stop/start cả 2 EC2 theo runbook và khôi phục đủ dịch vụ mà không chạy lại `stack.sh` | P0 | TV1 | Bảng trước/sau: slug redirect, Swift checksum, Cinder file, UUID, digest, STS |
| FR-INF-20 | Khi tắt app VM A, LB loại backend lỗi và app B tiếp tục phục vụ | P1 | TV2 + TV4 | Fault run: thời gian phát hiện, 5xx/timeout, thời gian hồi phục |
| FR-INF-21 | Giám sát chi phí: budget cảnh báo 30/50/65 USD, ghi giờ chạy từng host | P1 | TV4 | `cost.csv` + ảnh budget |
| FR-INF-22 | Image app trên Glance có Docker + Shlink digest nạp sẵn, không chứa secret; scale-out không build/pull | P0 | TV2 | `image-manifest.json`; clone boot độc lập |

## 4. Hợp đồng giao diện (API, cấu hình, bàn giao)

Hợp đồng này chốt trước 23/10 và là thứ TV2 (readiness, image), TV4 (smoke, Locust) và Web Client cùng dựa vào. Nguồn gốc là OpenAPI và HealthAction của Shlink **v5.1.8**; khi SRS và OpenAPI khác nhau, OpenAPI thắng và SRS phải sửa. Không tự suy endpoint từ tên dự án.

### 4.1 REST API dùng trong dự án

| API | Auth | Kết quả đúng | Bên dùng |
| --- | --- | --- | --- |
| `GET /rest/health` | Không | 200 + JSON `status=pass` khi truy vấn DB được; 503/`fail` khi DB lỗi. **Không kiểm Redis** | TV2 readiness, TV4 synthetic check |
| `GET /{shortCode}` | Không | 302 + `Location` (vì `REDIRECT_STATUS_CODE=302`); client test không follow | Locust, trình duyệt |
| `POST /rest/v3/short-urls` | `X-Api-Key` | 200 theo spec; body chứa `shortUrl` | Web Client, fixture, TV4 |
| `PATCH /rest/v3/short-urls/{shortCode}` | `X-Api-Key` | Đổi `longUrl`; kiểm qua cả 2 backend | Web Client, TV4 |
| `GET /rest/v3/short-urls/{shortCode}/visits` | `X-Api-Key` | Danh sách visit phân trang; mọi lượt đo dùng cùng bộ lọc bot/thời gian/domain | Web Client, tải đọc |
| `GET /rest/v3/tags/stats` | `X-Api-Key` | Thống kê link/visit theo tag | Demo chiến dịch |
| `OPTIONS /rest/v3/...` | Không | Preflight cho origin `https://admin.CAMPUS_DOMAIN`, cho phép `X-Api-Key`, `Content-Type` | Web Client |

Mã lỗi cần xử lý: 401 (thiếu/sai key), 400 `non-unique-slug` (trùng slug), 404 (slug không có; `/` cũng có thể 404 vì chưa cấu hình base redirect), 503 (health khi DB lỗi). Trong benchmark: 302 và create 200 là thành công, 5xx/timeout là lỗi, 4xx ghi riêng.

Ví dụ gọi (đã dùng trong smoke Lab 9.8; key nhập bằng `read -rsp`, không in ra log):

```bash
curl --fail-with-body -sS "$CAMPUS_SHORT/rest/v3/short-urls" \
  -H "X-Api-Key: $CAMPUS_API_KEY" -H 'Content-Type: application/json' \
  --data '{"longUrl":"https://example.org/","customSlug":"tv1-20261025T0900","tags":["campus-smoke"]}'
curl -sS -D - -o /dev/null "$CAMPUS_SHORT/tv1-20261025T0900"   # mong đợi 302
curl --fail-with-body -sS -X PATCH "$CAMPUS_SHORT/rest/v3/short-urls/tv1-20261025T0900" \
  -H "X-Api-Key: $CAMPUS_API_KEY" -H 'Content-Type: application/json' \
  --data '{"longUrl":"https://example.org/?campus=updated"}'
```

### 4.2 Quy tắc về API key

- Key tạo bằng `shlink api-key:generate --name=<tên> [--author-only]` trong container đang chạy; key lưu trong DB nên dùng được trên mọi replica. Chỉ thấy plaintext một lần lúc tạo.
- Key không có role = quyền admin ứng dụng. Shlink **không có** cặp role read/write; `--author-only` dùng cho phép thử phân tách dữ liệu, `--domain-only` chỉ khi đủ điều kiện domain của upstream.
- TV3 giữ 1 key admin để chuẩn bị fixture chung. Nếu fixture tạo bằng key hạn chế, TV4 phải dùng chính key đó khi đo thống kê.
- Web Client lưu server/key trong local storage của trình duyệt: không đặt key thật vào `servers.json` hay `SHLINK_SERVER_API_KEY` của UI public. CORS không phải cơ chế phân quyền.

### 4.3 Hợp đồng cấu hình container (TV3 → TV2)

Container `shlinkio/shlink:5.1.8` (sau smoke khóa bằng RepoDigest thật), nghe cổng 8080, chạy cả web và background worker. File `/opt/campuslink/shlink.env` baseline:

```
DEFAULT_DOMAIN=s.CAMPUS_DOMAIN
IS_HTTPS_ENABLED=true
PORT=8080
DB_DRIVER=postgres
DB_HOST=10.20.0.10
DB_PORT=5432
DB_NAME=shlink
DB_USER=shlink
DB_PASSWORD_FILE=/run/secrets/db_password
REDIS_SERVERS_FILE=/run/secrets/redis_servers
CACHE_NAMESPACE=campuslink-v5
REDIS_PUB_SUB_ENABLED=false
MERCURE_ENABLED=false
RABBITMQ_ENABLED=false
AUTO_RESOLVE_TITLES=false
SKIP_INITIAL_GEOLITE_DOWNLOAD=true
REDIRECT_STATUS_CODE=302
WEB_WORKER_NUM=1
TASK_WORKER_NUM=1
MEMORY_LIMIT=256M
TIMEZONE=UTC
LOGS_FORMAT=json
CORS_ALLOW_ORIGIN=https://admin.CAMPUS_DOMAIN
TRUSTED_PROXIES=1
```

- Secret chỉ đi qua file `_FILE` (bind-mount read-only, mode 0444, thư mục cha 0700/root); không đặt thêm biến thường chứa secret vì biến thường được ưu tiên. `redis_servers` có dạng `tcp://default:<password-urlencoded>@10.20.0.10:6379`.
- Entrypoint chạy installer/migration mỗi lần khởi động: instance đầu tiên phải xong trước khi thêm replica; không sửa entrypoint để bỏ migration. Timeout khởi động pilot 180 s.
- Worker/memory là điểm xuất phát để đo trên guest 1 vCPU/2 GiB, không phải cấu hình hiệu năng đã chứng nhận.

### 4.4 Ingress và cổng mạng

| Đường | Nguồn → đích | Cổng | Ghi chú |
| --- | --- | --- | --- |
| Người dùng → Nginx | Internet → EIP A | TCP 80, 443 | 2 virtual host theo SNI/Host; cổng 80 chỉ phục vụ ACME HTTP-01 của Let's Encrypt và chuyển hướng sang 443 |
| Nginx → VIP | A → FIP nội bộ 172.24.4.x | TCP 8080 | `Connection close`, `proxy_next_upstream off` (không retry POST), ghi đè `X-Forwarded-For` |
| VIP → app | OVN LB → guest | TCP 8080 | SG `campus-app-sg` nhận từ 10.20.0.0/24 và 172.24.4.0/24 |
| App → DB | `campus-app-sg` → `campus-db-sg` | TCP 5432, 6379 | Chỉ từ app SG |
| Quản trị | IP /32 của thành viên → A | TCP 22 | B qua ProxyJump; guest qua diag jump tạm |
| Overlay | A ↔ B | UDP 6081 Geneve, TCP 6641/6642 OVN, 5672 Rabbit, 3306 SQL | Chỉ trong SG `campus-hosts` |

### 4.5 Các mốc bàn giao H0–H6

| Mốc | Giao → nhận | Nội dung phải có (không chỉ "đã xong") |
| --- | --- | --- |
| H0 | TV1 → cả nhóm | inventory, kiến trúc mạng, phiên bản, lịch sử dụng cloud, SSH cá nhân |
| H1 | TV3 → TV2, TV4 | Shlink digest, API v3, `/rest/health` + Redis probe, cách cấp secret, worker config, migration/drain |
| H2 | TV1 → TV2, TV3 | project, network/subnet/router UUID, AZ, flavor, keypair, quota, SG, endpoint private |
| H3 | TV1 → TV3 | Cinder service/backend, volume type/AZ, Swift auth endpoint, DB port 10.20.0.10; smoke attach/upload |
| H4 | TV2 → TV3, TV4 | VIP port/UUID, pool, image UUID, Heat params, thủ tục scale/disable alarm |
| H5 | TV3 → TV4 | fixture, backup snapshot ID, restore checklist, expected outputs |
| H6 | TV4 → cả nhóm | raw metrics, lỗi tái lập được, chênh lệch so với mục tiêu |

## 5. Yêu cầu phi chức năng

Mọi con số dưới đây là **mục tiêu cần đo**, không phải kết quả đã có. Nếu không đạt, nhóm công bố số đo và phân tích; không đổi ngưỡng sau khi xem kết quả.

| Mã | Loại | Yêu cầu đo được | Chủ trì |
| --- | --- | --- | --- |
| NFR-01 | Hiệu năng | p95 redirect ≤ 500 ms ở mức thực đạt khoảng 30 RPS (đo qua Internet, đã gồm network latency) | TV4 |
| NFR-02 | Tin cậy | Tỷ lệ 5xx/timeout < 1% trong lượt không gây lỗi | TV4 |
| NFR-03 | Workload | Profile 80% `GET /{shortCode}`, 15% `GET .../visits`, 5% `POST /rest/v3/short-urls`; mức 10/30/60 RPS mục tiêu; warm-up 2 phút, steady 5 phút mỗi mức | TV4 |
| NFR-04 | Thực nghiệm | So static (2 app, 1/AZ) với auto (1 app AZ-A + ASG-B 1–2); mỗi cấu hình ≥ 3 lượt, đảo thứ tự; cùng digest, image UUID, fixture, config | TV4 |
| NFR-05 | Co giãn | Scale-out khi CPU > 60% qua 2 cửa sổ 60 s; scale-in khi < 25% qua 3 cửa sổ 60 s; cooldown ≥ 180 s. CPU phải quy đổi từ ns: % = Δcpu_ns / (Δt × 10^9 × N vCPU) × 100 | TV2 |
| NFR-06 | Co giãn | Đo và báo cáo riêng: thời điểm ALARM, VM ACTIVE, app ready, request đầu tiên tới VM mới | TV2 + TV4 |
| NFR-07 | Sẵn sàng | Mất app VM A không làm mất dịch vụ; đo thời gian phát hiện, lỗi trong lúc chuyển và thời gian hồi phục. Không cam kết chịu mất EC2 A/AZ-A | TV2 |
| NFR-08 | Bảo mật | Không secret trong Git, Glance image, Heat output, evidence, user-data; `.gitignore` chặn `.env`, `*.pem`, `local.conf`, `clouds.yaml`, `*.dump`, `*.sql` | Cả nhóm |
| NFR-09 | Bảo mật | Ba lớp quyền tách biệt: AWS IAM (EC2 A gọi AWS API), Keystone (người/dịch vụ trong OpenStack), Shlink API key (người dùng app). IMDSv2 bắt buộc, hop limit 1; guest không lấy được credential IAM của host | TV1 |
| NFR-10 | Bảo mật | Chứng thư Let's Encrypt hợp lệ cho cả 2 tên, còn hạn; không dùng `curl -k` để báo PASS | TV1 + TV3 |
| NFR-11 | Bền dữ liệu | Dữ liệu link còn nguyên sau reboot DB VM và sau stop/start cả 2 EC2; luôn có ít nhất 1 bản dump ngoài host A | TV3 |
| NFR-12 | Nhất quán | Link tạo/sửa qua app A đọc được qua app B; tất cả replica dùng cùng DB, cùng Redis, cùng `CACHE_NAMESPACE` | TV3 |
| NFR-13 | Tài nguyên | Không OOM/swap kéo dài khi chạy 3 app + DB; reserve A 16 GiB/4 vCPU, B 8 GiB/1 vCPU; allocation ratio 1.0 | TV1 + TV2 |
| NFR-14 | Tái lập | Khóa SHA mọi repo OpenStack, Gnocchi commit, Shlink digest, Web Client checksum, image UUID trong `versions.lock`; một người khác đọc runbook chạy lại được smoke | TV4 |
| NFR-15 | Quan sát | Log JSON, UTC, Request ID Shlink, guest UUID/IP trên mỗi replica; metric có đơn vị, timestamp, resource | TV2 + TV3 |
| NFR-16 | Chi phí | Lab ≤ 70 USD mục tiêu (công thức: (0,615 × H + 18,56) × 1,2, H = giờ mỗi EC2); báo cáo thêm kịch bản 730 giờ/tháng (562,32 USD gồm dự phòng 20%) | TV4 |

**Không được làm để đạt số:** chèn tác vụ CPU giả vào endpoint, gửi Heat signal SUCCESS thủ công rồi gọi là autoscaling tự động, hạ threshold để chữa thiếu metric, benchmark trên QEMU như KVM, đếm visit bằng HEAD, chạy đo đồng thời với build/backup lớn.

## 6. Tiêu chí nghiệm thu theo thành viên

Mỗi thành viên "xong" khi mọi mã yêu cầu mình chủ trì có bằng chứng trong `evidence/` và người review chéo đã **chạy hoặc quan sát** phép thử, không chỉ đọc ảnh. Bảng dưới gộp yêu cầu ở mục 3–5 theo người; task chi tiết (T1.xx…T4.xx) vẫn nằm trong bản phân công.

### 6.1 Phạm vi và định nghĩa hoàn thành

| Thành viên | Yêu cầu chủ trì | Nhận đầu vào | Hoàn thành khi | Review chéo bởi |
| --- | --- | --- | --- | --- |
| TV1 – Lương Đức Kiên (nền, mạng) | FR-INF-01–06, 13, 14, 17–19; NFR-09, 10, 13 | — (bắt đầu chuỗi) | G0–G2 PASS; TV2/TV3 tự dùng project mà không cần TV1 đăng nhập admin hộ; stop/start thật giữ link/object/volume | TV4 |
| TV2 – Nguyễn Công Huy Hoàng (LB, image, scaling) | FR-INF-07–11, 20, 22; NFR-05–07 | H2 từ TV1, H1 từ TV3 (trước đó dùng HTTP stub) | 2→3→2 bằng tải thật có alarm history, Heat events, member lifecycle, request tới app mới; fault run có số đo | TV1 (quyền, Heat scope) |
| TV3 – Đinh Quang Huy (ứng dụng, dữ liệu) | FR-APP-01–12, FR-INF-12, 15, 16; NFR-11, 12 | H2, H3 từ TV1 (trước đó chạy Compose local) | Create → QR → 302 → edit → visits chạy qua 2 replica; backup/restore tách biệt PASS; manifest giao TV2 không chứa secret | TV2 (image, readiness) |
| TV4 – Cao Song Toàn (kiểm thử, chi phí) | FR-INF-21; NFR-01–04, 14, 16; phối hợp NFR-06, 07 | H4 từ TV2, H5 từ TV3 | Acceptance matrix đủ 8 tiêu chí; raw CSV + metadata mỗi lượt; `cost.csv`; người ngoài đọc runbook chạy lại được smoke | TV3 (dữ liệu, workload) |

### 6.2 Ma trận 8 hạng mục bắt buộc

| Hạng mục | Yêu cầu liên quan | Chủ trì | Bằng chứng bắt buộc |
| --- | --- | --- | --- |
| 1. Mạng, 2 AZ | FR-INF-01–04 | TV1 | EC2 AZ ID + Nova host/AZ mapping; route table; VM A/B; overlay test |
| 2. Ứng dụng private | FR-INF-05, 06 | TV1/TV3 | Không FIP cho app/DB; B không public IPv4; SG; thử TCP public bị chặn |
| 3. Hai loại storage | FR-INF-13, 14 | TV3/TV1 | Cinder mount; Swift private put/get; dữ liệu còn sau reboot |
| 4. Cơ sở dữ liệu | FR-INF-12, 15, 16; NFR-12 | TV3 | 2 app nhất quán; giới hạn pool; dump và restore tách biệt |
| 5. IAM / quyền | FR-INF-17, 18; FR-APP-07, 08 | TV1 | Instance profile; STS role; allow/deny; Keystone reader/member |
| 6. LB + autoscaling | FR-INF-07–09, 11 | TV2 | 2→3→2; alarm, Heat events, member lifecycle, request tới app mới |
| 7. Monitoring + alarm | FR-INF-10; NFR-15 | TV2/TV4 | Metric có đơn vị/timestamp/resource; alarm transition; host metrics |
| 8. Dự toán | FR-INF-21; NFR-16 | TV4 | Giá nguồn + ngày; actual usage; lab và 730 giờ; credit tách biệt |

### 6.3 Cổng nghiệm thu theo lịch

| Ngày | Gate | Phải có | Người dẫn |
| --- | --- | --- | --- |
| 21–22/10 | G0 | Account/quota/credit, KVM cả 2 host, B ra Internet | TV1 + TV4 |
| 22–23/10 | G1 | 2 nova-compute; guest A↔B; smoke OVN LB; 1 metric/Heat resource | TV1 + TV2 |
| 24–25/10 | G2 | Network/role/storage smoke; chạy lại được sau stop/start | TV1 + TV3 + TV4 |
| 26–28/10 | G3 | App thật 2 replica, backup/restore, TLS, manual scaling | TV2 + TV3 |
| 29/10–01/11 | G4 | Tải thật → alarm → VM ready → traffic → scale-in | TV2 + TV4 |
| 02–05/11 | G5 | Benchmark 3 lượt, fault run, giới hạn, chi phí | TV4 |
| 06–08/11 | Freeze | Diễn tập, video, kiểm đủ 8 tiêu chí | TV1 chốt |
| 09/11 | Nộp | Mã nguồn/cấu hình, báo cáo, video | Cả nhóm |
| 16/11 | Bảo vệ | Không nâng phiên bản phút cuối | Cả nhóm |

### 6.4 Dùng SRS khi làm việc với AI agent

Nhóm dự định dùng AI hỗ trợ viết code/cấu hình, nên mỗi issue/prompt nên kèm: mã yêu cầu (ví dụ FR-INF-09), đoạn hợp đồng liên quan ở mục 4, cột "Kiểm bằng" làm tiêu chí dừng, và danh sách "Không được làm" ở mục 5. Không cho agent tự chạy `clean.sh`/`unstack.sh`, xóa stack/volume, mở SG, hoặc nhận secret thật; agent gọi `ssh campus-a '<lệnh>'` từ máy cá nhân thay vì cài lên controller.

## 7. Vấn đề mở

Các điểm dưới đây chưa được chốt trong tài liệu nhóm; SRS giữ placeholder và cập nhật khi có quyết định.

| # | Vấn đề | Ảnh hưởng tới | Người chốt |
| --- | --- | --- | --- |
| O-01 | Domain thật cho `CAMPUS_DOMAIN`: đã chốt 22/10 không mua domain, dùng `<EIP-gạch-ngang>.sslip.io` + Let's Encrypt. Còn mở: điền EIP thật vào inventory; nếu Let's Encrypt từ chối do giới hạn tần suất của sslip.io thì chuyển sang DuckDNS (chỉ đổi `CAMPUS_DOMAIN`); có giới hạn IP cho trang admin hay không | FR-APP-01, 09; FR-INF-06; NFR-10; SG mở 80/443 ra Internet khi cấp cert và khi demo | TV1 + TV3 |
| O-02 | Kênh trao đổi secret riêng của nhóm (DB password, Redis URI, API key) | H1, FR-INF-09, NFR-08 | Cả nhóm |
| O-03 | Cơ chế cấp secret tự động cho VM do ASG tạo (nhập tay chỉ đủ cho instance đầu tiên) | FR-INF-08, 09, 11 | TV2 + TV3 |
| O-04 | Rubric chính thức của giảng viên; SRS đang hiểu 8 hạng mục theo bảng trong đề xuất. Nếu rubric đòi entity "campaign" riêng thì ghi thiếu tính năng | Mục 6.2, FR-APP-05 | TV1 |
| O-05 | Số dư và hạn thật của 200 USD credit; giá 0,410/0,205 USD/giờ chưa kiểm bằng Calculator | NFR-16 | TV4 |
| O-06 | Gnocchi commit cụ thể (không có nhánh stable/2026.1) | NFR-14, FR-INF-10 | TV2 |
| O-07 | Thời gian drain visit trước scale-in/backup (queue RoadRunner trong bộ nhớ) | FR-INF-11, 15 | TV3 đo |
| O-08 | `max_connections` PostgreSQL theo tổng worker của tối đa 3 app + dự phòng quản trị | FR-INF-12 | TV3 |
| O-09 | Người chịu trách nhiệm tắt cloud mỗi phiên, và lịch phiên cài chung đầu tiên | NFR-16, FR-INF-19 | Cả nhóm |
| O-10 | Ngưỡng scaling thật sau khi đo (60%/25% chỉ là khởi đầu); nếu Shlink quá nhẹ để kích alarm ở 60 RPS | NFR-05, FR-INF-11 | TV2 + TV4 |
| O-11 | Thông báo của giảng viên tuần tới có thay đổi yêu cầu/lịch nộp hay không | Toàn bộ SRS | TV1 |
