# Hợp đồng tích hợp ứng dụng với image và Heat

Tài liệu xác định đầu vào và điều kiện tích hợp Shlink vào VM do Heat quản lý, theo [SRS](../../docs/SRS.md) mục 4.1–4.6, FR-INF-09/11/22, NFR-08/15; [H1](../../docs/handoffs/H1-shlink.md); [ADR-09](../../docs/decisions/ADR-09-redis-pubsub-va-streams.md) và [ADR-10](../../docs/decisions/ADR-10-cap-secret-swift-va-credential-hep.md). Giá trị môi trường lấy từ [inventory](../../docs/inventory.yaml), phiên bản/digest từ [versions.lock](../../docs/versions.lock).

Đây là hợp đồng cho bootstrap, image và template app. TV2 đã [tái lập 27 phép kiểm local ngày 07/11/2026](../../evidence/G3/20261107-H1-tv2-smoke-local.txt) và [kiểm image/clone thật tại hai AZ ngày 11/11/2026](../../evidence/G4/20261111-FR-INF-22-image-clone.txt): bootstrap, health/Redis, reboot, Docker restart và logging. Template Heat core và callback đã kiểm native validate, negative A/B, callback timeout và scale tay2→3→2 trên cụm ngày 13/11; [H4](../../docs/handoffs/H4-heat-lb-scaling.md) tách stack tích hợp đã dọn với deployment hai app đang giữ. Telemetry/alarm/tải tự động chưa nghiệm thu. Phải tách kết quả clone khỏi nghiệm thu scaling.

## 1. Đầu vào và điều kiện triển khai

| Đầu vào | Hợp đồng | Nguồn / giới hạn |
| --- | --- | --- |
| Image nền | Ubuntu 24.04 x86_64, UUID/checksum đúng nguồn bàn giao | H2, inventory, versions.lock |
| Shlink | 5.1.8, triển khai bằng RepoDigest khóa trong versions.lock | H1; không chỉ dùng tag |
| Cấu hình | Env không chứa secret, worker/memory theo H1 | [shlink.env.example](../../app/shlink.env.example); cấu hình guest còn cần đo |
| Dữ liệu | PostgreSQL 16 và Redis ứng dụng dùng chung tại 10.20.0.10; DB/user có sẵn | H1; không tạo DB bằng installer |
| Secret | Swift campus-secrets, credential campus-boot có access rules, tên object biết trước | ADR-10, #26/#27; file credential đã giao trên A, helper đọc nội bộ |
| Migration/readiness | App A hoàn tất migration, health và Redis trước ASG-B | H1 mục 3–4, FR-INF-09 |
| Bảo vệ metadata | Sau khi lấy đủ secret, trước khi app containers được phép chạy | [Evidence guest hai AZ](../../evidence/G4/20261111-NFR-08-chan-metadata.txt), #21 đã đóng; giữ kiểm trong stack mới |
| Drain/kết nối | Phạm vi đo và ngân sách có nguồn, phân biệt đề xuất với đã kiểm | H1 mục 5, O-07/O-08 |

Mỗi đầu vào dùng triển khai phải gắn với phiên bản cấu hình và evidence. Placeholder không phải giá trị thật. Nếu nguồn mâu thuẫn, giải quyết trước khi dùng, không sửa yêu cầu để khớp một phép thử.

## 2. Image, cấu hình và mạng

Image app trên Glance chứa Docker, image Shlink theo digest và công cụ probe cần thiết, không chứa secret hoặc credential builder. Khi scale-out không build/pull image. Manifest ghi image nền, package, digest và UUID image app. Image nền ubuntu-noble-base khác image app đã bake; app_image của stack thật phải dùng image app.

Digest Shlink và manifest amd64 lấy từ versions.lock; không dùng latest/develop. Candidate giai đoạn 4 đã kiểm Ubuntu24.04.5 amd64, Docker29.1.3 và redis-tools7.0.15; chi tiết trong evidence image/clone. Gói/lệnh mới vẫn phải kiểm trên guest hoặc nguồn đúng phiên bản trước khi ghi là chạy được.

| Nhóm | Giá trị / cách lấy |
| --- | --- |
| Domain | DEFAULT_DOMAIN theo shlink.short_domain trong inventory, không scheme; IS_HTTPS_ENABLED=true |
| HTTP | PORT=8080, REDIRECT_STATUS_CODE=302, TRUSTED_PROXIES=1 |
| CORS | CORS_ALLOW_ORIGIN=https:// cộng shlink.admin_domain trong inventory |
| PostgreSQL | DB_DRIVER=postgres, DB_HOST=10.20.0.10, DB_PORT=5432, DB_NAME=shlink, DB_USER=shlink |
| Redis | CACHE_NAMESPACE=campuslink-v5, **REDIS_PUB_SUB_ENABLED=true**; mọi replica dùng chung Redis/namespace |
| Worker | WEB_WORKER_NUM=1, TASK_WORKER_NUM=1, MEMORY_LIMIT=256M; điểm xuất phát, chưa phải số đo guest |
| Tích hợp | MERCURE_ENABLED=false, RABBITMQ_ENABLED=false, AUTO_RESOLVE_TITLES=false, SKIP_INITIAL_GEOLITE_DOWNLOAD=true |
| Log | TIMEZONE=UTC, LOGS_FORMAT=json; Request ID khớp log JSON/UTC và guest UUID/IP đã kiểm trên clone A/B giai đoạn 4; stack mới phải kiểm lại |

Env không chứa secret của container đặt tại /opt/campuslink/shlink.env theo H1. App/DB VM không có FIP; guest MTU1400. App nghe8080, dùng PostgreSQL5432/Redis6379 qua SG nền. Ingress: Nginx A:443 → FIP VIP:8080 → Octavia OVN TCP → guest:8080. TLS kết thúc tại Nginx; LB dùng pool SOURCE_IP_PORT và TCP monitor. TCP monitor không thay readiness HTTP/Redis.

Mẫu [Nginx](../nginx/campus.conf.example) có đường trả503 khi chưa nối VIP. Có app/LB không tự chứng minh ingress đã nối hoặc TLS đã PASS. UUID/IP và Request ID đã kiểm trên clone; đường client/proxy qua ingress thật vẫn cần kiểm sau khi TV1 nối VIP.

## 3. Secret và ngoại lệ bootstrap

### Nguồn, quyền và tên object

Theo ADR-10, chủ sở hữu tạo secret trên cụm, ghi Swift campus-secrets dưới app/. Không trao giá trị qua chat, issue, PR, Git, evidence hoặc handoff. Core Shlink chỉ GET đúng hai object:

| Object trong campus-secrets | File đích trong guest/container | Biến env chỉ chứa đường dẫn |
| --- | --- | --- |
| app/db_password | /run/secrets/db_password, mật khẩu PostgreSQL một dòng | DB_PASSWORD_FILE |
| app/redis_servers | /run/secrets/redis_servers, Redis URI có xác thực một dòng | REDIS_SERVERS_FILE |

H1 yêu cầu mật khẩu hex, Redis URI dạng tcp://default:<mật-khẩu>@10.20.0.10:6379; probe hiện dựa trên định dạng đó. Không đặt DB_PASSWORD hoặc REDIS_SERVERS thường vì chúng ưu tiên hơn _FILE.

campus-boot là reader có ACL đọc container. **ACL ở cấp container, không giới hạn prefix.** Credential thật phải có access rule GET, service object-store, path /v1/AUTH_<project_id>/campus-secrets/app/*. Không list/HEAD container hoặc tải toàn kho; allowlist của script không thay access rules. Không bỏ rules hoặc tăng quyền khi boot lỗi.

Keystone token endpoint: http://10.11.0.10/identity/v3/auth/tokens. Swift account endpoint lấy từ inventory. Host bootstrap lấy token rồi GET từng object đã biết; không cần container app lấy token bootstrap. Cấu hình Swift cần service_type=object-store và include_service_catalog=True theo ADR-10; đây là cấu hình ngoài repo do phần nền quản lý, không để guest sửa controller.

### Quyền file, reboot và lỗi

File guest 0444/root, thư mục cha0700/root; bind-mount read-only **từng file** vào container uid1001 theo H1. Không suy từ quyền Docker Desktop rằng guest chắc chắn đọc được. /run là tmpfs: cấp lại secret mỗi boot, kiểm đúng quyền và nội dung định dạng trước app start.

Thiếu object, xác thực thất bại, timeout, file sai định dạng/quyền đều phải ngăn app khởi động và không signal thành công. Object không tồn tại có thể404; request ngoài access rules có thể401, không nhất thiết403. Không suy mọi401 là sai mật khẩu; kiểm nguyên nhân bằng trạng thái đã che. Giới hạn timeout/retry phải nằm trong ngân sách boot/readiness đã xác định, không retry vô hạn.

Không in secret/token vào log, argv hoặc evidence; không đưa secret vào env thường. Evidence chỉ ghi mã lỗi, bước, trạng thái và tên object, không nội dung. Không bake credential hoặc cache user-data/secret vào image.

### Heat và giới hạn bảo mật

NFR-08 có **ba ngoại lệ hẹp** theo ADR-10: credential bootstrap campus-boot trong app VM; mật khẩu DB/Redis trong user-data của DB VM tạo tay; token TOKEN_SIGNAL của WaitConditionHandle trong app VM. Ngoại lệ DB không áp cho app VM. Credential campus-boot đi qua hai parameter HOT hidden:true, lấy từ env thật cục bộ mode0600; các secret ứng dụng vẫn được đọc từ Swift lúc boot. [Env mẫu](env.example.yaml) chỉ chứa placeholder; [root.yaml](root.yaml) và [app-unit.yaml](app-unit.yaml) khai báo hai parameter đồng bộ.

Handle TOKEN_SIGNAL nằm trong từng app unit, không ở root. Token của stack user có hạn3600s và có thể signal các handle trong cùng cây stack; reader/member đọc được attribute token là rủi ro đã được ADR-10 chấp nhận. Token không cho đọc secret app. VM lưu descriptor trong `/run/campuslink/signal.json` root0600/parent0700, dùng header file thay vì argv, xóa sau lượt gửi. Không đưa token hoặc endpoint vào Heat outputs. Readiness local vẫn180s; WaitCondition chờ300s để bao phần boot/delivery khác mốc thời gian. TV1 đã kiểm stack không VM ở issue #34; TV2 đã kiểm native SUCCESS/FAILURE từ app VM và timeout 300s trong giai đoạn 5, xem [evidence](../../evidence/G4/20261113-FR-INF-09-tv2-heat-core-cloud.txt).

hidden không che credential khỏi admin hoặc mọi đường metadata/software-config. ADR-10 đã kiểm API user_data: admin thấy, member/reader không; không được suy thành mọi tiến trình guest đều không đọc được. Khi nghi lộ campus-boot, làm thủ tục thu hồi/đổi secret và thay VM theo ADR-10. Nếu chỉ lộ token signal thì xử lý theo ngoại lệ riêng của token, không suy thành secret ứng dụng đã lộ.

TV1 đã giao credential thật qua #26: `/home/tv2/.config/openstack/campus-boot.cred` trên A, tv2:tv2 mode0600/parent0700. TV3 giao DB/Redis và hai object thật qua #27. Giai đoạn4 đã kiểm bootstrap dùng credential thật trên clone A/B; helper tạo env bằng đường dẫn file, không source shell và không in giá trị. Bootstrap trong app A/ASG-B, WaitCondition và gate member đã có phép thử riêng ngày 13/11; xem H4.

## 4. Thứ tự boot, metadata guard và readiness

Luồng bắt buộc của app unit:

```text
VM khởi động
  → host bootstrap nhận cấu hình và lấy đủ secret hợp lệ vào /run/secrets
  → thiết lập và kiểm metadata guard thành công
  → cho phép app containers khởi động từ image đã nạp sẵn
  → entrypoint/migration upstream hoàn tất
  → health HTTP 200/pass và Redis PONG trên chính VM
  → signal thành công / WaitCondition hoàn tất
  → thêm PoolMember
```

### Bảo vệ metadata theo yêu cầu #21

Guard thuộc **guest app VM**, không phải firewall EC2 A/B. Implementation trong bootstrap dùng DOCKER-USER chặn đích169.254.169.254 cho Docker bridge sau cấp secret và trước Shlink start. Đã kiểm traffic, positive control và counters trên clone A/B, lặp sau reboot và Docker restart; evidence giai đoạn 4 không tự bao phủ portal/worker hoặc stack ASG mới.

- Phải kiểm network mode, firewall backend và chain Docker thực tế trước khi chọn lệnh. Container network_mode:host không được bảo vệ bởi hướng DOCKER-USER; báo lại bên yêu cầu để thống nhất biện pháp, không nhận PASS bằng rule không đi qua traffic.
- App unit phải phụ thuộc **thành công** của secret/guard unit. After= chỉ đặt thứ tự; cần dependency và xử lý lỗi tương ứng, không để guard lỗi mà app vẫn chạy.
- Kiểm cả lần boot đầu và reboot. Docker daemon có thể tự khởi động lại container theo restart policy; implementation phải ngăn đường này chạy trước secret/guard, không chỉ sắp thứ tự lệnh docker run đầu tiên.
- Giữ AUTO_RESOLVE_TITLES=false. Guard chỉ giảm đường truy cập từ container; không biến credential trong user-data thành bí mật với host hoặc tiến trình có đặc quyền trong guest.
- Kiểm guard đúng chain/traffic, container thực sự thử metadata và bị chặn, secret vẫn đủ và app chỉ chạy sau guard; lặp sau reboot. Lệnh probe thiếu hoặc mạng hỏng sẵn không phải bằng chứng firewall. Không in body user-data/secret/token. Evidence đã có: [11/11 NFR-08](../../evidence/G4/20261111-NFR-08-chan-metadata.txt); cần lặp trên app unit mới.

### Migration và readiness cơ bản

Giữ entrypoint upstream: installer/migration chạy mỗi lần khởi động; DB/user phải có trước. Theo H1, RoadRunner chỉ lên sau installer thoát0, nên health 200 là dấu hiệu migration hoàn tất; chữ Success riêng trong log không đủ. App A cố định AZ-A phải đạt cả health và Redis trước khi tạo ASG-B. [Root template](root.yaml) nối ASG-B tới nested app A hoàn tất (gồm WaitCondition và member). Cấu trúc này có tests offline và Heat events thật ngày 13/11: app A ready/member hoàn tất trước khi ASG-B tạo; negative A chặn cả ASG-B.

Readiness kiểm **chính VM**, không qua VIP hoặc replica khác:

1. GET /rest/health tại127.0.0.1:8080 trả HTTP 200 và JSON status=pass; không dùng root / có thể404. Health chỉ kiểm DB, không kiểm Redis.
2. [redis-probe.sh](../../app/smoke/redis-probe.sh) đọc file redis_servers, PING có xác thực và chỉ báo PONG/exit0 khi thành công. redis-cli có thể exit0 dù AUTH lỗi; không kiểm bằng exit code redis-cli đơn lẻ.
3. Cả hai đạt trong deadline pilot180s. H1 dùng HTTP probe tối đa5s; mỗi probe/retry phải có giới hạn và không vượt deadline còn lại. Container exited hoặc restart-loop fail sớm, không chờ đủ180s. Log lỗi database có thể bắt nguồn Redis theo H1.

Không đạt thì không signal thành công hoặc thêm member; lỗi phải thể hiện qua fail/timeout của app unit. VM ACTIVE, app ready, member ONLINE và request đầu tiên tới replica là các mốc khác nhau, ghi UTC/UUID khi kiểm thật.

## 5. Drain, kết nối và phạm vi mở rộng

### Drain và ngân sách DB

Gỡ PoolMember trước xóa VM theo FR-INF-09; thực hiện drain có giới hạn rồi dừng container. H1 đo request **đã trả lời xong**: visit nằm trong DB, sự kiện Redis pub/sub có thể mất khi kill. Request đang xử lý chưa đo; không suy kết quả đó thành không downtime hoặc exactly-once.

Delay5s đã quan sát trong scale-in: member xóa xong13:55:15Z, VM bắt đầu xóa13:55:20Z; đây chưa phải bảo đảm giữ mọi request đang chạy. Stop-timeout30s vẫn theo cấu hình H1. Cần kiểm in-flight trong fault run trên guest trước khi chốt. Cooldown autoscaling không thay thời gian drain. Phần đối soát pub/sub thuộc FR-APP-18, không do template tự bảo đảm.

H1 mục10 ghi DB VM đã áp dụng max_connections50 và role shlink limit15 (PR #30). Mỗi tiến trình worker quan sát giữ tối đa một kết nối trên local; cần đo số kết nối thật khi stack có3 app. Với tối đa3app, giữ:

```text
3 × C_app + C_other + C_admin ≤ max_connections
```

C_other gồm portal/worker/stats, backup/CLI và dự phòng tương ứng H1; chốt số thật với bên dữ liệu. Không tự đổi PostgreSQL hoặc worker để làm kiểm tra đạt.

### Mở rộng theo SRS1.3

[ADR-08](../../docs/decisions/ADR-08-mo-rong-app-dich-vu-bao-quanh.md) xác định portal+worker trên mỗi app VM, cùng image/digest khác ROLE; campus-stats đúng một bản trên DB VM, không bake vào image app. H1b cần bàn giao digest/env/_FILE, healthz và migration campus_portal. Chưa có H1b được tiếp nhận trong hợp đồng này, không biến tên đề xuất thành config đã chạy.

LB thêm listener/pool8081 cùng VIP, backend guest:8081; portal healthz200 và worker running bổ sung cho readiness core khi triển khai mở rộng. [H3b phần Swift](../../docs/handoffs/H3b-swift-qr-reports.md) đã được bàn giao qua PR #18: file swift_app_cred dạng id=/secret=, quyền GET/HEAD/PUT theo access rules; DELETE bị chặn. Ingress/cert/vhost app., đường B và portal/worker thật chưa được nghiệm thu trong bàn giao đó. Core không tải thêm secret mở rộng chưa dùng.

[Lab O-13](lab/README.md) có cấu hình hai listener; SG8081 đã được bàn giao qua [PR #23](https://github.com/luongkien25/campuslink/pull/23), đóng #19. Nghiệm thu traffic hai cổng theo evidence riêng của O-13, không suy từ evidence8080 ngày27/10 hoặc từ Compose H1. Worker co giãn cùng app; timeline worker mới nhận lô thuộc phối hợp NFR-19, không chứng minh bằng HTTP stub.

## 6. Tình huống nghiệm thu implementation sau hợp đồng

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Boot hợp lệ / reboot | Cấp lại secret, guard thành công trước containers; không build/pull; readiness đạt rồi mới thêm member |
| Secret thiếu/sai quyền/sai xác thực | Không chạy app hoặc signal thành công; lỗi không chứa giá trị secret |
| Guard lỗi hoặc container tự restart sớm | Không cho app chạy trước guard; không dùng After= đơn lẻ để nhận đạt |
| Host-network container | Không dùng DOCKER-USER làm bằng chứng; thống nhất biện pháp trước triển khai |
| Metadata request từ container | Có công cụ probe và đường thử hợp lệ, bị chặn; không đọc/in user-data để chứng minh |
| DB unreachable hoặc HTTP503/fail | Không đạt readiness, app unit không được báo thành công |
| HTTP 200 thiếu status=pass hoặc Redis lỗi | Không signal/thêm member, dù probe còn lại đạt |
| Migration lỗi hoặc app A chưa ready | Không tạo ASG-B; không dựa log Success/VM ACTIVE |
| Hết deadline180s / container restart-loop | Fail/timeout có lý do đã che, không thêm member |
| Scale-in | Gỡ member trước xóa VM, drain theo thủ tục đã kiểm; giữ số đo in-flight riêng |
| Ngân sách DB không đủ | Không nhận cấu hình triển khai; đối chiếu worker và dự phòng với H1 |

Mỗi phép kiểm thật gắn commit, digest/image UUID, VM UUID, UTC và output đã che theo môi trường áp dụng. [Evidence tiếp nhận H1 của TV2](../../evidence/G3/20261107-H1-tv2-smoke-local.txt) ghi đủ27 kiểm tra, đúng digest, hai replica và cleanup project local riêng. Evidence local đó không có UUID VM; các phép kiểm guest và Heat thật có UUID/time riêng ở evidence G4 ngày11/11 và13/11. Không dùng evidence local thay phép kiểm guest hoặc dừng DB/Redis dùng chung khi chưa có phiên/phạm vi được duyệt.

Issue #11 theo dõi bàn giao H1; #21 và #27 đã đóng sau kiểm clone. PR #33 chứa image/bootstrap/metadata evidence; PR #35 chốt callback theo ADR-10. WaitCondition/member lifecycle và scale thủ công đã có evidence riêng ngày 13/11. Autoscaling bằng alarm/tải thật chưa nghiệm thu; việc đóng bàn giao không thay tiêu chí đó.
