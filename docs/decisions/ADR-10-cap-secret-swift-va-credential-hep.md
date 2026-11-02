# ADR-10: Cấp secret qua Swift `campus-secrets`; VM do ASG tạo lấy bằng application credential chỉ-đọc

- Ngày: 02/11/2026 · Người quyết: TV1 (Kenn), cho D3 và D4 (biên bản họp 25/10; SRS O-02, O-03) · Trạng thái: chấp nhận, **chưa thử trên cụm** (mục "Phải kiểm trên cụm"). D4 do TV2 + TV3 làm chủ nên cần hai bạn xem lại khi review PR.

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
6. Application credential `campus-boot` do user đó tạo (TV1 đăng nhập tạm, tạo xong đặt lại mật khẩu ngẫu nhiên và không lưu). Thêm access rules giới hạn `GET` tới `campus-secrets/app/*` làm lớp thứ hai nếu thử được (O-14).
7. ID và secret của credential vào stack qua hai tham số Heat `hidden: true`, giá trị lấy từ `env.yaml` cục bộ (bị `.gitignore` chặn), không nằm trong Git hay Heat output. Chúng nằm trong user-data của VM.
8. Script boot (TV2, `SOFTWARE_CONFIG`): lấy token bằng application credential, `GET` từng object `app/*`, ghi `/run/secrets/<tên>` mode 0444 trong thư mục cha 0700 root (SRS 4.3), rồi mới chạy container. Thiếu object hoặc 401/403 thì không chạy app và báo lỗi (không in giá trị ra log).
9. Sửa chữ SRS: NFR-08 và mục 4.6 thêm ngoại lệ duy nhất "application credential bootstrap `campus-boot`, chỉ-đọc, theo ADR-10". Mọi secret khác vẫn cấm trong user-data. Credential này vẫn **cấm trong Git và evidence**.
10. Lộ hoặc thay người: xóa credential, tạo lại, `stack update` với tham số mới. VM đang chạy đã lấy secret rồi; nếu secret ứng dụng lộ thì đổi cả secret trong `campus-secrets`.

## Phương án đã loại

- **Kéo từ DB VM qua mạng nội bộ (phương án B):** giữ nguyên chữ NFR-08, nhưng thêm dịch vụ tự viết trên DB VM (1 vCPU/2 GiB), mọi VM trong `campus-app-sg` đọc được, tin theo vị trí mạng.
- **Secret thẳng trong user-data hoặc Heat parameter thường:** lộ qua `stack show` và metadata; đi ngược NFR-08.
- **Bake vào image Glance:** ngược FR-INF-22.
- **Barbican:** không nằm trong thành phần đã chốt của cụm; thêm dịch vụ chỉ để cấp secret là không đáng.
- **Tin nhắn tự hủy hoặc trình quản lý mật khẩu chung (gợi ý gốc của D3):** thêm công cụ ngoài và không giải được D4.

## Hệ quả

- Thiệt hại tối đa nếu lộ credential `campus-boot` là đọc `campus-secrets/app/*`, đúng các secret app đã giữ; thu hồi được (mục 10). Mọi tiến trình trong VM app đọc được nó qua `169.254.169.254`; ai xem được `user_data` bằng `server show` thì chưa kiểm.
- Scale-out phụ thuộc Swift trên A đang `up`. Swift hỏng thì VM mới không chạy app (an toàn nhưng scale-out thất bại): đưa vào kiểm FR-INF-11 và fault run.
- Quét secret (NFR-18) vẫn phải sạch trong Git và image; chỉ user-data của VM chạy được chứa credential này.
- Cập nhật `infra/heat/env.example.yaml` (TV2): ghi hai tham số `hidden` và bỏ câu "O-03 còn mở".

## Phải kiểm trên cụm (gom vào phiên bật cloud sau 05/11)

1. Tạo `campus-secrets`, user `campus-boot` (reader), ACL đọc; `GET app/<x>` bằng credential của `campus-boot`: 200; `PUT` và `GET` container khác (`campus-backups`): 403.
2. `campus-tv4` (reader) `GET campus-secrets/app/<x>`: 403.
3. Access rules (O-14): cú pháp path, wildcard, và có chặn `PUT`/`DELETE` thật không.
4. `server show` bằng `campus-tv4` có hiện `user_data` không.
5. Một VM thử lấy token bằng application credential từ trong guest rồi `GET` object, qua endpoint Swift trên A.

Phân việc: TV1 container, user, credential (mục 1, 5, 6); TV3 ghi object (mục 2); TV2 script boot và tham số Heat (mục 7, 8).
