# Quy trình làm việc chung trên repo CampusLink

Nguyên tắc chung: **repo là nguồn sự thật chung của cả nhóm.** Mọi cấu hình đã kiểm chứng, lỗi đã xử lý và giá trị tài nguyên thật đều được ghi lại trong repo để các thành viên bàn giao và tái lập thống nhất.

## 1. Vòng làm việc chuẩn

```
Issue (mã FR/NFR + tiêu chí dừng)
  → tạo nhánh riêng (tv1/... | tv2/... | tv3/... | tv4/...)
  → kiểm tra đầu vào từ docs/SRS.md, docs/inventory.yaml, docs/handoffs/
  → chạy kiểm chứng thực tế trên cụm hoặc local
  → PASS: lưu evidence đã che secret, mở PR   |   FAIL: tra docs/troubleshooting.md, ghi rõ lỗi vào issue
  → cần thành viên khác xử lý: mở issue yêu cầu [YC-TVx] (mục 7)
  → ghi lỗi đã gỡ vào docs/troubleshooting.md; đổi giá trị thật thì cập nhật inventory/handoff
  → review chéo (chạy lại hoặc kiểm chứng kết quả) rồi merge
```

## 2. Thiết lập lần đầu (mỗi thành viên)

1. Clone repo, đọc `README.md` và `docs/SRS.md` (mục 1–2 và 6).
2. Gửi TV1 **public key** SSH (không gửi private key) và địa chỉ IP `/32` để thêm vào AWS Security Group.
3. TV1 cấp cho mỗi người **một user Linux riêng trên host A** (`tv2`, `tv3`, `tv4`), không `sudo`, thuộc nhóm `systemd-journal` để đọc log. Chỉ TV1 dùng `ubuntu`/`stack`.
   Cấu hình `~/.ssh/config` trên máy cá nhân:

   ```
   Host campus-a
     HostName <EIP của A>
     User <tv2|tv3|tv4>
     IdentityFile ~/.ssh/<key-của-bạn>
     IdentitiesOnly yes
   # campus-b: chỉ khi cần, thường là TV1
   Host campus-b
     HostName 10.11.11.10
     User <user trên B>
     IdentityFile ~/.ssh/<key-của-bạn>
     IdentitiesOnly yes
     ProxyJump campus-a
   ```

   Giữ `IdentitiesOnly yes` để SSH chỉ thử đúng khóa này, tránh `fail2ban` chặn IP dùng chung khi có nhiều khóa trong `ssh-agent`.

4. TV1 tạo user Keystone cho từng người (TV2/TV3 `member`, TV4 `reader`). Mỗi người đặt `clouds.yaml` trong `~/.config/openstack/` của user mình trên host A (`chmod 600`) và chạy với `OS_CLOUD=<tên>`. Mật khẩu trao qua kênh riêng (SRS O-02), không đưa vào repo hay nhóm chat.
5. Bản đồ tài liệu theo mảng phụ trách:

| Thành viên | Phần SRS chính | Handoff nhận | Thư mục phụ trách |
| --- | --- | --- | --- |
| TV1 | 3.2 (FR-INF-01–06, 13, 14, 17–19), 4.4 | — | `infra/aws`, `infra/devstack`, `ops` |
| TV2 | 3.2 (FR-INF-07–11, 20, 22), 4.3, 4.5 | H1, H2 | `infra/heat` |
| TV3 | 3.1, 4.1–4.3, FR-INF-12, 15, 16 | H2, H3 | `app`, `ops` |
| TV4 | 5, 6, FR-INF-21 | H4, H5 | `tests`, `evidence` |

## 3. Chẩn đoán sự cố

- Lấy ảnh chụp trạng thái cụm chỉ-đọc bằng script:
  `ssh campus-a 'OS_CLOUD=<tên> bash -s -- lb' < ops/cluster-snapshot.sh > snap.txt`
  (hỗ trợ các phần: `base`, `net`, `lb`, `heat`, `telemetry`, `storage`, `logs`, `all`).
  Script tự che các chuỗi dạng mật khẩu/token, nhưng vẫn cần đọc lại trước khi chia sẻ.
- Tra `docs/troubleshooting.md` trước khi đổi cấu hình.
- Mỗi lần chỉ thay đổi một thành phần rồi kiểm chứng lại. Mọi lệnh thay đổi trạng thái dùng chung (stack Heat, mạng, SG, dịch vụ hệ thống, `stack.sh`) phải thống nhất trước với người phụ trách.

## 4. Dùng chung cụm cloud

Hai EC2 dùng chung và tính phí theo giờ:

- Bật/tắt máy, cơ chế tự tắt khi rảnh, giữ máy khi đo tải và chụp snapshot: tuân thủ `docs/runbooks/start-stop.md` và `docs/runbooks/after-start.md`.
- Ghi nhật ký bật/tắt vào issue ghim **"Nhật ký cloud"** (người bật, giờ UTC, mục đích, người tắt).
- Trước thay đổi ảnh hưởng người khác (stack Heat, mạng, SG, restart dịch vụ): báo nhóm và chờ phiên đang chạy hoàn tất.
- Cuối phiên cập nhật 4 dòng: bằng chứng đã có; vướng mắc; đầu việc cần người khác (`[YC-TVx]`); bước kế tiếp.
- Người bật cuối cùng chịu trách nhiệm đảm bảo cụm đã tắt (SRS O-09).

## 5. Quy ước Git và PR

- Nhánh: `tv1/...`, `tv2/...`, `tv3/...`, `tv4/...`, mỗi nhánh giải quyết một hạng mục nhỏ. Commit theo mẫu `[FR-INF-09] mô tả ngắn`.
- Mở PR theo `.github/pull_request_template.md`, review chéo: TV4 → TV1, TV1 → TV2, TV2 → TV3, TV3 → TV4. Người review chạy kiểm lại hoặc đối chiếu bằng chứng trước khi duyệt.
- `.github/CODEOWNERS` tự gắn reviewer theo thư mục phụ trách.
- Người merge tự kiểm trước khi gộp vào `main`: đã có review, checks xanh, `baseRefName` là `main`.

## 6. Ghi nhận tài liệu kỹ thuật

| Sự kiện | Nơi cập nhật |
| --- | --- |
| Lỗi đã xử lý | `docs/troubleshooting.md`: triệu chứng → nguyên nhân → cách sửa → nguồn |
| Tài nguyên mới (UUID, IP, tên) | `docs/inventory.yaml` |
| Bàn giao mốc giữa thành viên | `docs/handoffs/Hx-...md` theo `_TEMPLATE.md` |
| Quyết định kiến trúc | `docs/decisions/ADR-xx-...md` |
| Quy trình vận hành lặp lại | `docs/runbooks/` |

## 7. Secret, bằng chứng và phối hợp qua Issues

- **Secret:** Không commit mật khẩu, API key, `clouds.yaml`, `local.conf`, `*.pem`, `/etc/letsencrypt`, Redis URI. Chỉ commit `*.example` dùng placeholder `REPLACE_...`. Nếu lỡ commit secret, báo TV1 ngay để **đổi secret** (xóa lịch sử git không đủ).
- **Evidence:** Che Account ID, IP cá nhân và thông tin thanh toán trước khi commit; bản gốc để trong `evidence/**/raw/` (được `.gitignore` bỏ qua).
- **Yêu cầu chéo (`[YC-TVx]`):** Mở issue theo mẫu `.github/ISSUE_TEMPLATE/yeu-cau.md` với tiêu đề `[YC-TV?][FR-XXX-NN] <việc>`, gắn nhãn `yeu-cau` + `cho-tv?` (thêm `chan-gate` nếu chặn tiến độ) và gán Assignee cho người nhận. Khi hoàn thành, comment đường dẫn evidence/PR và đóng issue (`Closes #<số>`).
