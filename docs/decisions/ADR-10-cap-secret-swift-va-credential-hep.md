# ADR-10: Cấp secret qua Swift `campus-secrets`; VM do ASG tạo lấy bằng application credential chỉ-đọc

- Ngày: 02/11/2026, sửa 07/11/2026 theo review của TV2 trên PR #15 (giới hạn cấp container, rủi ro khi lộ credential) · Người quyết: TV1 (Kenn), cho D3 và D4 (biên bản họp 25/10; SRS O-02, O-03) · Trạng thái: chấp nhận, **chưa thử trên cụm** (mục "Phải kiểm trên cụm"). D4 do TV2 + TV3 làm chủ nên cần hai bạn xem lại khi review PR.

## Bối cảnh

- **D3** (kênh trao secret giữa người, hạn 26/10) và **D4** (secret cho VM do ASG tạo, hạn 27/10) chưa có quyết định, trong khi H1 của TV3 cần "cách cấp secret" (SRS 4.5) và TV2 chưa ghép app vào ASG được nếu thiếu D4.
- Mật khẩu Keystone đã không đi qua kênh nào: nằm trong `~/.config/openstack/clouds.yaml` của từng người trên A (H2).
- App/DB VM không có floating IP và VM của ASG-B (min 1, max 2) không có người nhập tay, nên không đẩy secret từ ngoài vào được. VM mới cần một thứ để chứng minh nó được phép lấy secret. NFR-08 cấm secret trong user-data, nhưng không thể thỏa hoàn toàn chữ đó mà vẫn tự scale-out.

## Quyết định

**D3 (người với người)**

1. Không có kênh trao secret giữa người. Keystone: `clouds.yaml` trên A (đã chốt, H2).
2. Secret ứng dụng do người sở hữu sinh ngay trên cụm và ghi vào Swift container private `campus-secrets`, prefix `app/`, bằng `openstack object create` trên A. TV3: mật khẩu DB `shlink` và `campus_portal`, `redis_servers`, `PORTAL_SECRET_KEY`, key `campus-stats`. TV1: application credential `campus-svc` (file `swift_app_cred`).
3. Cấm Zalo, issue, PR, Git, evidence, file H. Các nơi này chỉ ghi **tên object**, không ghi giá trị.
4. Người đọc được container: `member` (TV2, TV3) và admin (TV1). `reader` (TV4) không (chưa kiểm).

**D4 (VM do ASG tạo)**

5. User Keystone `campus-boot`, role `reader` trong project `campuslink`. Container `campus-secrets` có ACL đọc cho user này (cú pháp ACL chưa kiểm). `reader` không thuộc `operator_roles` của Swift (`Member, admin`) nên **chỉ đọc được nhờ ACL**; ACL sai thì VM bị từ chối, không mở rộng quyền.
   - **Giới hạn là cấp container, không phải cấp prefix.** ACL đọc của Swift áp cho cả container: `campus-boot` đọc được **mọi object** trong `campus-secrets`, không chỉ `app/*`. Prefix `app/` chỉ là quy ước đặt tên.
   - Vì vậy `campus-secrets` **chỉ chứa secret mà VM app cần lúc boot** (danh sách ở mục 2). Secret VM không cần (credential admin, khóa backup, secret của người) không được đặt trong container này; cần thì dùng container khác không có ACL cho `campus-boot`.
   - ACL không cho ghi: `campus-boot` không `PUT`/`DELETE` được object (kiểm ở mục "Phải kiểm" 1).
6. Application credential `campus-boot` do user đó tạo (TV1 đăng nhập tạm, tạo xong đặt lại mật khẩu ngẫu nhiên và không lưu). Access rules (O-14) là cách **duy nhất** giới hạn tới prefix `campus-secrets/app/*`; thêm làm lớp thứ hai nếu thử được. Chưa kiểm nên thiết kế **không dựa vào** lớp này: mục 5 phải đúng kể cả khi không có access rules.
7. ID và secret của credential vào stack qua hai tham số Heat `hidden: true`, giá trị lấy từ `env.yaml` cục bộ (bị `.gitignore` chặn), không nằm trong Git hay Heat output. Chúng nằm trong user-data của VM.
8. Script boot (TV2, `SOFTWARE_CONFIG`): lấy token bằng application credential, `GET` từng object `app/*`, ghi `/run/secrets/<tên>` mode 0444 trong thư mục cha 0700 root (SRS 4.3), rồi mới chạy container. Thiếu object hoặc 401/403 thì không chạy app và báo lỗi (không in giá trị ra log).
9. Sửa chữ SRS: NFR-08 và mục 4.6 thêm ngoại lệ duy nhất "application credential bootstrap `campus-boot`, chỉ-đọc, theo ADR-10". Mọi secret khác vẫn cấm trong user-data. Credential này vẫn **cấm trong Git và evidence**.
10. Lộ credential `campus-boot` (hoặc nghi lộ): **coi như mọi secret trong `campus-secrets` đã lộ**, vì người có credential đã đọc được chúng. Làm theo thứ tự: (a) xóa application credential, tạo cái mới; (b) đổi từng secret trong container (mật khẩu DB `shlink`, `campus_portal` trên DB VM; mật khẩu Redis; `PORTAL_SECRET_KEY`; key `campus-stats`; xóa và tạo lại credential `campus-svc`), ghi bản mới vào `campus-secrets`; (c) `stack update` với tham số mới và thay VM app để chúng lấy secret mới. Chỉ xóa credential mà không đổi secret là **chưa đủ**. Thay người (không lộ): chỉ cần (a) và (c).

## Phương án đã loại

- **Kéo từ DB VM qua mạng nội bộ (phương án B):** giữ nguyên chữ NFR-08, nhưng thêm dịch vụ tự viết trên DB VM (1 vCPU/2 GiB), mọi VM trong `campus-app-sg` đọc được, tin theo vị trí mạng.
- **Secret thẳng trong user-data hoặc Heat parameter thường:** lộ qua `stack show` và metadata; đi ngược NFR-08.
- **Bake vào image Glance:** ngược FR-INF-22.
- **Barbican:** không nằm trong thành phần đã chốt của cụm; thêm dịch vụ chỉ để cấp secret là không đáng.
- **Tin nhắn tự hủy hoặc trình quản lý mật khẩu chung (gợi ý gốc của D3):** thêm công cụ ngoài và không giải được D4.

## Hệ quả

- **Lộ credential `campus-boot` không chỉ là lộ quyền đọc Swift.** Người có nó đọc được mọi object trong `campus-secrets` (mục 5), rồi dùng các secret đó:

  | Secret lộ | Người có nó làm được gì | Điều kiện / giới hạn |
  | --- | --- | --- |
  | Mật khẩu DB `shlink`, `campus_portal` | Đọc, sửa, xóa dữ liệu link, lượt truy cập, tài khoản portal | Phải tới được PostgreSQL trên DB VM 10.20.0.10: DB không có FIP, cần đứng trong `campus-net` (vd đã chiếm một VM app) |
  | `redis_servers` (có mật khẩu) | Đọc, xóa cache và khóa; làm app chạy sai | Như trên, Redis chỉ trong `campus-net` |
  | `PORTAL_SECRET_KEY` | Giải mã API key Shlink của mọi đơn vị mà portal lưu trong DB `campus_portal` (SRS mục 4.2), rồi tạo/sửa/xóa link nhân danh đơn vị đó | Cần thêm dữ liệu DB (dòng trên); key giải mã ra thì dùng được **từ Internet** qua REST của `s.` |
  | Key `campus-stats` | Key **admin** của Shlink (SRS mục 4.2: Shlink không có role chỉ-đọc): đọc mọi visit, tạo/sửa/xóa mọi link, đổi đích chuyển hướng | Dùng được **từ Internet**: REST ra ngoài qua `s.` (FR-INF-06), không cần vào mạng riêng |
  | Credential `campus-svc` (`swift_app_cred`) | Ghi, ghi đè, xóa object trong `campus-qr`, `campus-reports` (vd thay ảnh QR) | Qua endpoint Swift trên A; giới hạn theo access rules của `campus-svc` (O-14, chưa kiểm) |

  Credential `campus-boot` lại nằm trong user-data: **mọi tiến trình trong VM app** đọc được qua `169.254.169.254`, nên chiếm được một VM app là có cả hai lớp trên. Ai xem được `user_data` bằng `server show` thì chưa kiểm (mục "Phải kiểm" 4). Thu hồi phải đổi cả secret, không chỉ credential (mục 10).
- Rủi ro được chấp nhận vì: secret nào VM app cũng phải có để chạy, nên VM app bị chiếm thì đằng nào cũng lộ chúng; `campus-boot` không thêm quyền ghi, không thêm secret nào ngoài những gì VM đã cần (nhờ luật ở mục 5).
- Scale-out phụ thuộc Swift trên A đang `up`. Swift hỏng thì VM mới không chạy app (an toàn nhưng scale-out thất bại): đưa vào kiểm FR-INF-11 và fault run.
- Quét secret (NFR-18) vẫn phải sạch trong Git và image; chỉ user-data của VM chạy được chứa credential này.
- Cập nhật `infra/heat/env.example.yaml` (TV2): ghi hai tham số `hidden` và bỏ câu "O-03 còn mở".

## Phải kiểm trên cụm (gom vào phiên bật cloud sau 05/11)

Dùng giá trị giả, không đặt secret thật khi thử.

1. Tạo `campus-secrets`, user `campus-boot` (reader), ACL đọc; thêm 2 object giả `app/<x>` và `test/<y>` (ngoài `app/`). Bằng credential của `campus-boot` **chưa có access rules**:
   - `GET app/<x>`: 200.
   - `GET test/<y>`: **200 là kết quả đúng của thiết kế** (xác nhận giới hạn cấp container, mục 5); ghi lại như vậy, không coi là FAIL.
   - `PUT` và `DELETE` object trong `campus-secrets`: 403.
   - `GET` và `PUT` container khác (`campus-backups`): 403.
   - Liệt kê container (`GET campus-secrets`): ghi lại 200 hay 403 (ACL `.rlistings` có hay không, chưa kiểm).
2. `campus-tv4` (reader) `GET campus-secrets/app/<x>`: 403.
3. Access rules (O-14), trên một credential thử thứ hai của `campus-boot` có rule `GET` tới `campus-secrets/app/*`: kiểm cú pháp path, wildcard; kỳ vọng `GET app/<x>` = 200, `GET test/<y>` = 403, `PUT`/`DELETE` = 403. Đạt thì dùng credential có access rules (giới hạn thành cấp prefix) và ghi vào mục 6; không đạt thì giữ thiết kế cấp container ở mục 5, ghi lý do.
4. `server show` bằng `campus-tv4` có hiện `user_data` không.
5. Một VM thử lấy token bằng application credential từ trong guest rồi `GET` object, qua endpoint Swift trên A.

Phân việc: TV1 container, user, credential (mục 1, 5, 6); TV3 ghi object (mục 2); TV2 script boot và tham số Heat (mục 7, 8).
