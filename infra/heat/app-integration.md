# Hợp đồng tích hợp ứng dụng với image và Heat

Tài liệu mô tả đầu vào và điều kiện tích hợp Shlink vào VM ứng dụng do Heat quản lý. Các ràng buộc lấy từ [SRS](../../docs/SRS.md), mục 4.1–4.5, FR-INF-09/11/22 và NFR-08. Giá trị môi trường lấy từ [inventory](../../docs/inventory.yaml); phiên bản và digest lấy từ [versions.lock](../../docs/versions.lock).

Đây là khung hợp đồng theo yêu cầu dự án. Cấu hình baseline cần được đối chiếu với H1 và evidence ứng dụng trước khi dùng để đóng image hoặc triển khai. Tài liệu không chứng minh bootstrap, readiness hay cấp secret đã chạy trên VM thật.

## 1. Đầu vào tích hợp

| Đầu vào | Nội dung bắt buộc | Nguồn đối chiếu |
| --- | --- | --- |
| Image nền | Ubuntu 24.04 x86_64, image UUID và checksum | H2, inventory, versions.lock |
| Container ứng dụng | Shlink 5.1.8; RepoDigest thật sau smoke | H1, versions.lock |
| Cấu hình container | Env không chứa giá trị secret, worker config và evidence kiểm chứng | H1, SRS 4.3 |
| Dịch vụ dữ liệu | PostgreSQL 16 và Redis ứng dụng dùng chung tại 10.20.0.10 | H1, inventory |
| Cấp secret | Nguồn cấp, cách xác thực VM, file đích, quyền truy cập, xử lý lỗi và thu hồi nếu có | H1, cơ chế thống nhất theo O-03 |
| Migration | Điều kiện hoàn tất migration, thứ tự khởi động replica và dấu hiệu thất bại | H1, SRS 4.3 |
| Readiness | Cách gọi health và Redis probe có xác thực; kết quả thành công/thất bại | H1, FR-INF-09 |
| Drain | Cách ngừng nhận traffic, xử lý công việc còn lại và thời gian đã đo | H1, O-07 |
| Kết nối DB | Giới hạn pool mỗi app, tổng kết nối và phần dự phòng | H1, O-08 |

Mỗi giá trị được tiếp nhận phải có phiên bản cấu hình hoặc commit và evidence tương ứng. Nếu các nguồn khác nhau, phải giải quyết mâu thuẫn trước khi sử dụng. Placeholder không được coi là digest, image UUID hoặc đầu vào triển khai hợp lệ.

## 2. Image, cấu hình và mạng

### Image

- Container dùng `shlinkio/shlink:5.1.8` làm phiên bản tham chiếu; triển khai bằng RepoDigest thật đã khóa trong versions.lock.
- Image app trên Glance chứa Docker và container image đã nạp sẵn. Khi scale-out không build hoặc pull image ứng dụng.
- Image app không chứa secret hoặc credential của builder. Manifest ghi được image nền, phiên bản package, Shlink digest và image UUID.
- Image nền `ubuntu-noble-base` và image app đã bake là hai đầu vào khác nhau. Parameter `app_image` phải trỏ tới image app khi triển khai Shlink thật.

### Cấu hình không chứa secret

Các giá trị dưới đây là baseline của SRS 4.3, chưa thay thế evidence H1:

| Nhóm | Baseline / cách lấy giá trị |
| --- | --- |
| Domain | `DEFAULT_DOMAIN` = `shlink.short_domain` trong inventory, không có scheme; `IS_HTTPS_ENABLED=true` |
| HTTP | `PORT=8080`, `REDIRECT_STATUS_CODE=302`, `TRUSTED_PROXIES=1` |
| CORS | `CORS_ALLOW_ORIGIN=https://` + `shlink.admin_domain` trong inventory |
| PostgreSQL | `DB_DRIVER=postgres`, `DB_HOST=10.20.0.10`, `DB_PORT=5432`, `DB_NAME=shlink`, `DB_USER=shlink` |
| Redis | `CACHE_NAMESPACE=campuslink-v5`, `REDIS_PUB_SUB_ENABLED=false`; mọi replica dùng cùng Redis và namespace |
| Worker | `WEB_WORKER_NUM=1`, `TASK_WORKER_NUM=1`, `MEMORY_LIMIT=256M` |
| Tích hợp tùy chọn | `MERCURE_ENABLED=false`, `RABBITMQ_ENABLED=false`, `AUTO_RESOLVE_TITLES=false`, `SKIP_INITIAL_GEOLITE_DOWNLOAD=true` |
| Log | `TIMEZONE=UTC`, `LOGS_FORMAT=json` |

File cấu hình container theo SRS là `/opt/campuslink/shlink.env` trong guest. Giá trị thật được tạo khi triển khai, không commit file cấu hình thực tế. Cấu hình worker/memory phải được kiểm chứng trên flavor `campus.app` 1 vCPU/2 GiB RAM, không coi baseline là kết quả đo hiệu năng.

### Mạng và ingress

- App/DB VM không có FIP; guest dùng MTU 1400 trên campus-net.
- App lắng nghe 8080; truy cập PostgreSQL 5432 và Redis 6379 qua SG nền đã bàn giao.
- Luồng ingress: Nginx A:443 → FIP của VIP:8080 → Octavia OVN TCP → app VM:8080. TLS kết thúc ở Nginx.
- LB dùng listener TCP, pool `SOURCE_IP_PORT`, health monitor TCP. TCP monitor không thay thế HTTP readiness và Redis probe.
- Mẫu [Nginx](../nginx/campus.conf.example) có nhánh trả 503 khi chưa nối tới VIP. Việc tạo app/LB không tự làm ingress trỏ tới app; đường Nginx → VIP phải được tích hợp và kiểm chứng riêng.

## 3. Secret và giao diện cấp tự động

Theo SRS 4.3, container đọc secret qua hai biến chỉ chứa đường dẫn:

| Biến | File trong container | Nội dung file |
| --- | --- | --- |
| `DB_PASSWORD_FILE` | `/run/secrets/db_password` | Mật khẩu PostgreSQL |
| `REDIS_SERVERS_FILE` | `/run/secrets/redis_servers` | Redis URI có xác thực, password được URL-encode đúng |

File được bind-mount read-only, mode `0444`; thư mục cha theo SRS là `0700`, owner root. H1 phải xác định đường dẫn nguồn trong guest, UID/GID thực tế của tiến trình container và cách kiểm quyền đọc trong cấu hình mount đó. Không suy ra quyền đọc chỉ từ việc file đã tồn tại.

Không đặt thêm biến thường chứa giá trị secret bên cạnh `_FILE`, vì biến thường được ưu tiên theo hợp đồng SRS. Không đưa secret vào Git, Glance image, user-data, Heat parameters/output, command line hoặc log/evidence.

Cơ chế cấp tự động phải xác định đủ:

1. Dịch vụ hoặc kênh cấp và cách VM chứng minh quyền nhận secret.
2. Điều kiện mạng, file nguồn/đích và thời điểm secret sẵn sàng cho container.
3. Cách xử lý thiếu file, sai quyền, xác thực thất bại hoặc nguồn cấp không truy cập được.
4. Phạm vi truy cập, cách cấp lại/thu hồi hoặc thay thế credential nếu áp dụng.
5. Evidence VM mới nhận secret mà không cần nhập tay, đồng thời không rò rỉ giá trị qua log hoặc metadata.

O-03 là điều kiện phải chốt trước khi triển khai bootstrap thật. Tài liệu này không lựa chọn kênh cấp, cơ chế xác thực hoặc thời gian retry. Không dùng credential admin OpenStack hay credential IAM của EC2 host làm đầu vào mặc định cho guest.

## 4. Bootstrap, migration và readiness

Luồng yêu cầu của một app unit:

```text
VM khởi động
  → nhận cấu hình không chứa secret và nhận secret qua cơ chế đã chốt
  → khởi động container từ digest đã nạp sẵn, giữ entrypoint upstream
  → installer/migration hoàn tất theo thủ tục H1
  → HTTP health đạt và Redis PING có xác thực đạt
  → signal thành công, WaitCondition hoàn tất
  → Heat tạo PoolMember
```

Instance đầu tiên phải hoàn tất migration trước khi thêm replica. Entrypoint upstream vẫn chạy installer/migration khi container khởi động; không bỏ qua migration để làm readiness thành công. H1 phải mô tả cách quan sát hoàn tất, xử lý lỗi và bảo đảm thứ tự khi có nhiều VM.

Readiness của từng VM kiểm ứng dụng ngay trên VM đó, không gọi qua VIP rồi dùng kết quả của replica khác:

- HTTP: `GET /rest/health` tại app cục bộ cổng 8080 trả HTTP 200 và JSON có `status=pass`. Endpoint không yêu cầu API key.
- Redis: probe riêng tới Redis ứng dụng, có xác thực, nhận `PONG`. Health HTTP chỉ kiểm DB, không xác nhận Redis.
- Cả hai điều kiện phải đạt trong timeout pilot 180 giây theo SRS. Cách gọi Redis probe và tham số retry phải được xác nhận trước khi viết bootstrap.
- Secret lỗi, migration lỗi hoặc readiness không đạt không được tạo signal thành công hoặc thêm PoolMember. Thất bại phải được phản ánh qua đường báo lỗi/timeout để stack không báo thành công cho app unit đó.

`VM ACTIVE` chỉ là trạng thái compute. App ready, member được thêm và request đầu tiên tới replica là các mốc riêng, phải ghi UTC và nhận diện VM khi kiểm chứng.

## 5. Drain và ngân sách kết nối DB

### Drain

Trước khi xóa VM phải gỡ PoolMember theo FR-INF-09. Thủ tục drain phải nêu cách ngừng nhận traffic mới, xử lý kết nối/công việc còn lại, dấu hiệu hoàn tất và giới hạn chờ đã đo theo O-07. Không tự thay thời gian drain bằng cooldown của autoscaling.

Queue background của RoadRunner ở trong bộ nhớ. Dừng đột ngột hoặc hết hạn drain có thể làm mất công việc; không cam kết exactly-once cho visit. Thời gian và thao tác drain thực tế cần có evidence ứng dụng trước khi áp dụng vào scale-in hoặc backup.

### Ngân sách kết nối

Đặt `C_app` là số kết nối PostgreSQL tối đa của một app theo worker/pool thực tế, `C_other` là kết nối từ các thành phần khác và `C_admin` là phần dự phòng quản trị. Với tối đa ba app:

```text
3 × C_app + C_other + C_admin ≤ max_connections
```

Không suy ra `C_app` chỉ từ số worker. H1 cần cung cấp cách tính, giới hạn pool, giá trị `max_connections` và dự phòng thực tế. Nếu bất đẳng thức không đạt, phải thống nhất cấu hình điều chỉnh trước khi triển khai; không tự tăng giới hạn PostgreSQL hoặc giảm worker để làm phép kiểm đạt.

## 6. Các tình huống phải kiểm chứng

| Tình huống | Kết quả yêu cầu |
| --- | --- |
| VM mới, đầu vào hợp lệ | Nhận secret tự động; chạy đúng digest không build/pull; health và Redis đạt trước khi thêm member |
| Secret thiếu, không đọc được hoặc sai xác thực | Không thêm member; không signal thành công; lý do lỗi không chứa giá trị secret |
| DB không truy cập được hoặc health trả 503/fail | Readiness không đạt; app unit không được báo thành công |
| HTTP 200 nhưng JSON không có status=pass | Không coi HTTP readiness thành công |
| Redis lỗi trong khi HTTP health vẫn pass | Readiness không đạt, không thêm member |
| Migration thất bại hoặc instance đầu tiên chưa hoàn tất | Không vượt điều kiện cho phép thêm replica, không che lỗi bằng trạng thái VM ACTIVE |
| Readiness hết 180 giây | Báo lỗi/timeout; không thêm member |
| Scale-in | Gỡ member trước khi xóa VM; thực hiện drain theo thủ tục đã kiểm chứng |
| Tổng kết nối của ba app vượt ngân sách DB | Không chấp nhận cấu hình để triển khai; đối chiếu lại worker/pool và dự phòng |

Mỗi phép kiểm thực tế cần gắn với commit cấu hình, digest, image UUID, VM UUID, thời điểm UTC và output đã che. Không dùng phản hồi HTTP stub làm evidence của Shlink. Khi thử lỗi DB/Redis, dùng phạm vi thử đã được duyệt, không tự dừng dịch vụ dữ liệu dùng chung.

## 7. Giới hạn áp dụng

Khung này chưa cung cấp bootstrap script, cơ chế cấp secret, lệnh Redis probe hoặc cấu hình drain có thể chạy. Chỉ triển khai sau khi đầu vào H1 và O-03/O-07/O-08 đã được xác nhận; không suy ra các giá trị còn thiếu từ baseline.

Image bake/clone và việc kiểm không chứa secret thuộc bước xây dựng image. Heat app unit, WaitCondition, PoolMember và kiểm scale thủ công thuộc bước triển khai app. Tài liệu này xác định điều kiện tiếp nhận và kiểm chứng; các phép thử đó chưa được nghiệm thu bằng việc hoàn thành khung hợp đồng.
