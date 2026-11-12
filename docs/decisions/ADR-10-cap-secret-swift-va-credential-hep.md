# ADR-10: Cấp secret qua Swift `campus-secrets`; VM do ASG tạo lấy bằng application credential chỉ-đọc

- Ngày: 02/11/2026, sửa 07/11/2026 theo review của TV2 trên PR #15 (giới hạn cấp container, rủi ro khi lộ credential) · Người quyết: TV1 (Kenn), cho D3 và D4 (biên bản họp 25/10; SRS O-02, O-03) · Trạng thái: chấp nhận; **đã kiểm trên cụm 07/11/2026** (mục "Đã kiểm trên cụm"), phép kiểm 3 (access rules) đạt sau khi sửa 2 dòng cấu hình Swift trên A. D4 do TV2 + TV3 làm chủ.

## Bối cảnh

- **D3** (kênh trao secret giữa người, hạn 26/10) và **D4** (secret cho VM do ASG tạo, hạn 27/10) chưa có quyết định, trong khi H1 của TV3 cần "cách cấp secret" (SRS 4.5) và TV2 chưa ghép app vào ASG được nếu thiếu D4.
- Mật khẩu Keystone đã không đi qua kênh nào: nằm trong `~/.config/openstack/clouds.yaml` của từng người trên A (H2).
- App/DB VM không có floating IP và VM của ASG-B (min 1, max 2) không có người nhập tay, nên không đẩy secret từ ngoài vào được. VM mới cần một thứ để chứng minh nó được phép lấy secret. NFR-08 cấm secret trong user-data, nhưng không thể thỏa hoàn toàn chữ đó mà vẫn tự scale-out.

## Quyết định

**D3 (người với người)**

1. Không có kênh trao secret giữa người. Keystone: `clouds.yaml` trên A (đã chốt, H2).
2. Secret ứng dụng do người sở hữu sinh ngay trên cụm và ghi vào Swift container private `campus-secrets`, prefix `app/`, bằng `openstack object create` trên A. TV3: mật khẩu DB `shlink` và `campus_portal`, `redis_servers`, `PORTAL_SECRET_KEY`, key `campus-stats`. TV1: application credential `campus-svc` (file `swift_app_cred`).
3. Cấm Zalo, issue, PR, Git, evidence, file H. Các nơi này chỉ ghi **tên object**, không ghi giá trị.
4. Người đọc được container: `member` (TV2, TV3) và admin (TV1). `reader` (TV4) không: đã kiểm 07/11, `GET` ra 403.

**D4 (VM do ASG tạo)**

5. User Keystone `campus-boot`, role `reader` trong project `campuslink`. Container `campus-secrets` có ACL đọc cho user này (`swift post -r '<project_id>:<user_id>' campus-secrets`, đã kiểm 07/11). `reader` không thuộc `operator_roles` của Swift (`Member, admin`) nên **chỉ đọc được nhờ ACL**; ACL sai thì VM bị từ chối, không mở rộng quyền.
   - **Giới hạn là cấp container, không phải cấp prefix.** ACL đọc của Swift áp cho cả container: `campus-boot` đọc được **mọi object** trong `campus-secrets`, không chỉ `app/*`. Prefix `app/` chỉ là quy ước đặt tên.
   - Vì vậy `campus-secrets` **chỉ chứa secret mà VM app cần lúc boot** (danh sách ở mục 2). Secret VM không cần (credential admin, khóa backup, secret của người) không được đặt trong container này; cần thì dùng container khác không có ACL cho `campus-boot`.
   - ACL không cho ghi: `campus-boot` không `PUT`/`DELETE` được object (đã kiểm 07/11: 403).
6. Application credential `campus-boot` do user đó tạo (TV1 đặt lại mật khẩu, tạo credential, rồi đặt lại mật khẩu ngẫu nhiên và không lưu; `reader` tự tạo được credential nên ai giữ mật khẩu đều tạo thêm được). **Credential thật tạo CÓ access rules** (O-14): một rule `GET`, service `object-store`, path `/v1/AUTH_<project_id>/campus-secrets/app/*`. Đã kiểm 07/11: `GET app/<x>` 200, `app/<không-có>` 404; `test/<y>`, liệt kê container, `PUT`, `DELETE` bị từ chối (401). Đây là lớp **duy nhất** giới hạn tới prefix `app/`.
   - Access rules chỉ chạy khi `/etc/swift/proxy-server.conf`, mục `[filter:authtoken]`, có `service_type = object-store` **và** `include_service_catalog = True`. DevStack mặc định thiếu cả hai: thiếu `service_type` thì mọi request ra 401, thiếu catalog thì 500. Hai dòng này đã sửa trên A (07/11) và **không nằm trong repo**.
   - Đóng an toàn: nếu mất hai dòng đó (chạy lại `stack.sh`), credential có rules bị từ chối hoàn toàn, VM boot lỗi nhưng không lộ thêm. Mục 5 vẫn đúng kể cả khi không có access rules (phương án dự phòng: credential không rules, giới hạn cấp container).
7. ID và secret của credential vào stack qua hai tham số Heat `hidden: true`, giá trị lấy từ `env.yaml` cục bộ (bị `.gitignore` chặn), không nằm trong Git hay Heat output. Chúng nằm trong user-data của VM.
8. Script boot (TV2, `SOFTWARE_CONFIG`): lấy token bằng application credential, `GET` từng object `app/*`, ghi `/run/secrets/<tên>` mode 0444 trong thư mục cha 0700 root (SRS 4.3), rồi mới chạy container. Thiếu object hoặc 401/403 thì không chạy app và báo lỗi (không in giá trị ra log). Script phải biết sẵn tên từng object (`GET app/<tên>`): liệt kê container bị từ chối khi credential có access rules. Token lấy từ `http://10.11.0.10/identity/v3/auth/tokens`, Swift ở `http://10.11.0.10:8080/v1/AUTH_<project_id>`; đường này đã thử thông từ một VM ở host A (07/11).
9. Sửa chữ SRS: NFR-08 và mục 4.6 thêm ngoại lệ duy nhất "application credential bootstrap `campus-boot`, chỉ-đọc, theo ADR-10". Mọi secret khác vẫn cấm trong user-data. Credential này vẫn **cấm trong Git và evidence**. **Bổ sung 10/11/2026 (PR #30):** ngoại lệ thứ hai, hẹp: mật khẩu DB `shlink` và Redis trong user-data của DB VM `campus-db` (xem Hệ quả). **Bổ sung 12/11/2026 (#34):** ngoại lệ thứ ba, hẹp: token signal của `OS::Heat::WaitConditionHandle` trong user-data của app VM (xem Hệ quả).
10. Lộ credential `campus-boot` (hoặc nghi lộ): **coi như mọi secret trong `campus-secrets` đã lộ**, vì người có credential đã đọc được chúng. Làm theo thứ tự: (a) xóa application credential, tạo cái mới; (b) đổi từng secret trong container (mật khẩu DB `shlink`, `campus_portal` trên DB VM; mật khẩu Redis; `PORTAL_SECRET_KEY`; key `campus-stats`; xóa và tạo lại credential `campus-svc`), ghi bản mới vào `campus-secrets`; (c) `stack update` với tham số mới và thay VM app để chúng lấy secret mới. Chỉ xóa credential mà không đổi secret là **chưa đủ**. Thay người (không lộ): chỉ cần (a) và (c).

## Phương án đã loại

- **Kéo từ DB VM qua mạng nội bộ (phương án B):** giữ nguyên chữ NFR-08, nhưng thêm dịch vụ tự viết trên DB VM (1 vCPU/2 GiB), mọi VM trong `campus-app-sg` đọc được, tin theo vị trí mạng.
- **Secret thẳng trong user-data hoặc Heat parameter thường:** lộ qua `stack show` và metadata; đi ngược NFR-08.
- **Bake vào image Glance:** ngược FR-INF-22.
- **Barbican:** không nằm trong thành phần đã chốt của cụm; thêm dịch vụ chỉ để cấp secret là không đáng.
- **Tin nhắn tự hủy hoặc trình quản lý mật khẩu chung (gợi ý gốc của D3):** thêm công cụ ngoài và không giải được D4.

## Hệ quả

- **Lộ credential `campus-boot` không chỉ là lộ quyền đọc Swift.** Người có nó đọc được các object dưới `app/` (credential có access rules, mục 6; không có rules thì mọi object trong `campus-secrets`, mục 5). Toàn bộ secret app nằm dưới `app/`, nên rủi ro vẫn là cả bảng sau:

  | Secret lộ | Người có nó làm được gì | Điều kiện / giới hạn |
  | --- | --- | --- |
  | Mật khẩu DB `shlink`, `campus_portal` | Đọc, sửa, xóa dữ liệu link, lượt truy cập, tài khoản portal | Phải tới được PostgreSQL trên DB VM 10.20.0.10: DB không có FIP, cần đứng trong `campus-net` (vd đã chiếm một VM app) |
  | `redis_servers` (có mật khẩu) | Đọc, xóa cache và khóa; làm app chạy sai | Như trên, Redis chỉ trong `campus-net` |
  | `PORTAL_SECRET_KEY` | Giải mã API key Shlink của mọi đơn vị mà portal lưu trong DB `campus_portal` (SRS mục 4.2), rồi tạo/sửa/xóa link nhân danh đơn vị đó | Cần thêm dữ liệu DB (dòng trên); key giải mã ra thì dùng được **từ Internet** qua REST của `s.` |
  | Key `campus-stats` | Key **admin** của Shlink (SRS mục 4.2: Shlink không có role chỉ-đọc): đọc mọi visit, tạo/sửa/xóa mọi link, đổi đích chuyển hướng | Dùng được **từ Internet**: REST ra ngoài qua `s.` (FR-INF-06), không cần vào mạng riêng |
  | Credential `campus-svc` (`swift_app_cred`) | Ghi, ghi đè, xóa object trong `campus-qr`, `campus-reports` (vd thay ảnh QR) | Qua endpoint Swift trên A; giới hạn theo access rules của `campus-svc` (O-14: cơ chế đã chạy, kiểm 07/11 với `campus-boot`; `campus-svc` chưa tạo) |

  Credential `campus-boot` lại nằm trong user-data: **mọi tiến trình trong VM app** đọc được qua `169.254.169.254`, nên chiếm được một VM app là có cả hai lớp trên. Qua `server show`, chỉ admin (TV1) thấy `user_data`; `member` (TV2, TV3) và `reader` (TV4) không thấy (đã kiểm 07/11). Thu hồi phải đổi cả secret, không chỉ credential (mục 10).
- Rủi ro được chấp nhận vì: secret nào VM app cũng phải có để chạy, nên VM app bị chiếm thì đằng nào cũng lộ chúng; `campus-boot` không thêm quyền ghi, không thêm secret nào ngoài những gì VM đã cần (nhờ luật ở mục 5).
- Scale-out phụ thuộc Swift trên A đang `up`. Swift hỏng thì VM mới không chạy app (an toàn nhưng scale-out thất bại): đưa vào kiểm FR-INF-11 và fault run.
- Quét secret (NFR-18) vẫn phải sạch trong Git và image; chỉ user-data của VM chạy được chứa credential này.
- Endpoint Swift là `http` (không TLS): secret đi dạng rõ từ Swift trên A tới VM trong mạng nội bộ của cụm. Chấp nhận trong phạm vi lab, không thêm TLS cho Swift.
- Cấu hình Swift (2 dòng ở mục 6) nằm ngoài repo; đã ghi vào `docs/troubleshooting.md`. File cấu hình bền qua Stop/Start, nên `after-start` không cần kiểm lại.
- `reader` tự tạo được application credential: mật khẩu `campus-boot` luôn đặt ngẫu nhiên rồi bỏ (mục 6).
- Cập nhật `infra/heat/env.example.yaml` (TV2): ghi hai tham số `hidden` và bỏ câu "O-03 còn mở".
- **DB VM `campus-db` (bổ sung 10/11/2026, PR #30):** mật khẩu DB `shlink` và Redis đi vào VM qua user-data (cloud-init `app/db/user-data.tmpl.yaml`), vì DB VM không có FIP, không SSH và chưa có credential để tự đọc Swift. Chấp nhận vì VM tạo tay một lần, không thuộc ASG; `bootcmd` chặn tiến trình không phải root gọi `169.254.169.254` mỗi lần boot; DB VM không chạy container hay dịch vụ nhận URL từ người dùng; `member` (`campus-tv3`) không thấy `user_data` qua Nova API (đã kiểm 08/11, `evidence/G3/20261108-FR-INF-12-db-vm.txt`). Bản gốc của hai mật khẩu vẫn là `campus-secrets/app/`. Đổi mật khẩu về sau làm trên VM (`ALTER ROLE`, `/etc/redis/campus.conf`) rồi ghi lại object, không qua user-data. Thủ tục: `docs/runbooks/db-vm.md`.
- **Token signal của WaitConditionHandle (bổ sung 12/11/2026, #34):** FR-INF-09 cần app VM báo cho Heat là đã sẵn sàng. TV2 dùng `OS::Heat::WaitConditionHandle` với `signal_transport: TOKEN_SIGNAL` (mặc định của resource này) cộng `OS::Heat::WaitCondition`; Heat tạo một user trong stack domain `heat` (role `heat_stack_user`) và token của user đó đi vào VM qua user-data, nên đây là ngoại lệ thứ ba của NFR-08. Chấp nhận vì token **chỉ signal được**: không đọc được secret nào và không mở thêm đường tới Swift, Keystone, Nova hay Heat (đã kiểm 12/11, xem "Chưa kiểm / chưa chốt").

  | Token lộ | Người có nó làm được gì | Điều kiện / giới hạn |
  | --- | --- | --- |
  | Token stack user của một handle | Signal `SUCCESS` hoặc `FAILURE` cho handle trong **cùng cây stack** (stack gốc và stack lồng, kể cả member của ASG): làm WaitCondition xong sớm, hoặc fail | Hạn 3600 s (mặc định Keystone). Không đọc hay ghi Swift `campus-secrets`, không gọi Keystone, Nova, Heat (403, đã kiểm). Phạm vi "cùng cây stack" là theo mã Heat, **chưa thử trên cụm** |
  | Cùng token, do `member` hoặc `reader` đọc qua `stack resource show --with-attr token` | Như trên | Chỉ khi stack còn tồn tại và token chưa hết hạn. Ghi nhận (evidence 5.1), không chặn: người đó trong nhóm và token không cho đọc secret |

  Điều kiện thiết kế cho TV2: (1) handle nằm trong template của từng app unit (app A và member ASG-B), không ở root, vì token cấp lúc handle `CREATE` và hết hạn sau 3600 s, nên member ASG tạo sau đó cần handle riêng; (2) token vào VM qua user-data, ghi file `/run/...` root 0600, xóa sau khi signal, gọi bằng `curl -H @file` hoặc `--config`, **không dùng attribute `curl_cli`** (token nằm trong argv); (3) không đưa `token` và `endpoint` vào `outputs` của stack; (4) `WaitCondition.timeout` lớn hơn 180 s (ví dụ 300 s) và nhỏ hơn hạn token. Thu hồi: xóa stack hoặc member. Lộ token không phải làm thủ tục mục 10, vì không có secret nào lộ theo.

## Đã kiểm trên cụm (07/11/2026)

Evidence: `evidence/G3/20261107-ADR-10-kiem-tren-cum.txt`. Dùng giá trị giả; credential thử đã xóa, mật khẩu `campus-boot` đã đặt lại ngẫu nhiên.

| # | Phép kiểm | Kết quả |
| --- | --- | --- |
| 1 | `campus-boot` (credential không rules): `GET app/<x>`; `GET test/<y>`; `PUT`/`DELETE` trong `campus-secrets`; `GET`/`PUT` `campus-backups` | 200; **200** (đúng thiết kế, giới hạn cấp container); 403/403; 403/403. Liệt kê container: 200. `HEAD` account: 403 |
| 2 | `campus-tv4` (reader): `GET app/<x>`, `test/<y>`, liệt kê | 403 cả ba |
| 3 | Access rules (credential thứ hai của `campus-boot`) | Cấu hình mặc định: mọi request 401 (thiếu `service_type`). Thêm `service_type = object-store`: 500 (thiếu catalog). Thêm `include_service_catalog = True`: `GET app/<x>` 200, `app/<không-có>` 404; `test/<y>`, liệt kê, `PUT`, `DELETE`, `campus-backups` bị chặn (401). Credential không rules, `tv4`, admin không đổi |
| 4 | `server show` có `user_data`? | admin có; `tv2` (member) và `tv4` (reader) không |
| 5 | VM thử (host A) lấy token bằng credential có rules rồi `GET` | có token; `app/<x>` 200; `app/<không-có>` 404; `test/<y>` 401; liệt kê 401 |

Request không khớp rule ra **401**, không phải 403 (middleware từ chối token, `delay_auth_decision = 1`); vẫn là từ chối.

## Chưa kiểm / chưa chốt

- **Đã kiểm 12/11/2026 (#34), token signal của `OS::Heat::WaitConditionHandle` (`TOKEN_SIGNAL`):** `campus-tv2` (member) tạo stack thử không VM; 26 PASS, 1 FAIL ghi nhận (5.1: `reader` đọc được token), 0 WARN. Token có role duy nhất `heat_stack_user`, user và project thuộc domain `heat`, hạn 3600 s; bị từ chối 403 ở danh sách stack Heat, stack của chính nó, Swift `campus-secrets`, Keystone `/v3/projects`, Nova `/servers`; signal `SUCCESS` ra 200, WaitCondition và stack `CREATE_COMPLETE`; xóa stack thì user stack bị xóa theo (domain `heat`: 2 → 1). Endpoint signal cùng host:port với Keystone (`10.11.0.10:80`). Evidence `evidence/G3/20261112-FR-INF-09-NFR-08-heat-token-signal-kiem-tren-cum.txt`. **Chưa thử:** (a) token của một handle signal handle khác cùng cây stack hoặc khác stack (theo mã Heat `stable/2026.1`: stack lồng kế thừa `stack_user_project_id` của stack cha và `_stack_get` chỉ lọc theo project, nên cùng cây thì được, khác cây thì 404); (b) VM thật tới endpoint signal (TV2 phủ khi chạy SUCCESS, FAILURE, timeout bằng VM thật); (c) token hết hạn giữa chừng.
- **Đã kiểm 09/11/2026:** VM ở host B (`campus-az-b`, tạo bằng `campus-tv2`) lấy token Keystone rồi `GET` đúng object giả bằng credential tạm có 1 access rule: Keystone 200, cấp được token, `GET` 200 (md5 khớp); `PUT`, `DELETE`, object khác và không token đều 401, nên access rules chạy đúng từ phía B. Evidence `evidence/G3/20261109-ADR-10-vm-o-B-toi-keystone-swift.txt`. Chưa thử `campus-boot` và `campus-svc` thật và script boot thật từ VM ở B.
- **Đã kiểm 08/11/2026:** `member` (`campus-tv2`, `campus-tv3`) tạo, đọc lại (etag khớp md5) và xóa object giả dưới `app/` trong `campus-secrets`; `reader` (`campus-tv4`) ghi bị từ chối. Evidence `evidence/G3/20261108-FR-INF-22-campus-boot-credential-giao-tv2.txt`. Chưa thử `member` ghi object thật (`db_password`, `redis_servers`): TV3 làm ở issue #27.
- Credential `campus-svc` và access rules cho `campus-qr`, `campus-reports` (O-14, H3b): cơ chế đã chạy với `campus-boot`.
- Script boot thật của TV2 và tham số Heat `hidden`: TV2 làm. **Đã chốt 08/11/2026 (issue #26):** credential `campus-boot` thật (`campus-boot-20261107`, 1 access rule `GET campus-secrets/app/*`, không đặt hạn) nằm trong file `/home/tv2/.config/openstack/campus-boot.cred` trên A (`tv2:tv2`, 0600, thư mục cha 0700, hai dòng `id=` và `secret=`); TV2 đọc từ đó vào `env.yaml` cục bộ, không qua chat, issue hay Git. Đã kiểm bằng `curl` từ A (8 phép, `tv3` và `tv4` không đọc được file); đường mạng từ VM ở B đã kiểm 09/11 bằng credential tạm (xem trên); **chưa kiểm** `campus-boot` thật từ VM ở B và bằng script boot thật.

Phân việc: TV1 container, user, credential (mục 5, 6; đã tạo container, user và credential thật 08/11); TV3 ghi object (mục 2); TV2 script boot và tham số Heat (mục 7, 8).
