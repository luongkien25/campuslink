# AGENTS.md – hướng dẫn cho AI agent trong repo CampusLink

File này dành cho mọi AI hỗ trợ nhóm (Claude Code, Codex, Copilot, Cursor, Gemini, hoặc chat web có upload file).
Người trong nhóm đọc `CONTRIBUTING.md`. Nhóm còn mới với OpenStack, nên **ưu tiên đúng và kiểm được hơn nhanh**.

## 1. Dự án

CampusLink: dịch vụ rút gọn link = Shlink 5.1.8 (backend, Docker image) + Shlink Web Client 4.8.1 (SPA tĩnh),
chạy trên OpenStack DevStack stable/2026.1 lồng trong 2 EC2 AWS us-east-1:

- Host A (`campus-a`, AZ-A, m7i.2xlarge, có EIP): controller + compute + Cinder/Swift + Nginx :443 (ingress) + NAT cho B.
- Host B (`campus-b`, AZ-B, m7i.xlarge, không public IPv4): compute.
- Luồng: Internet → EIP → Nginx A:443 → FIP nội bộ của VIP (172.24.4.x):8080 → Octavia OVN (TCP) → app VM :8080 → PostgreSQL 16 + Redis trên DB VM 10.20.0.10.
- Autoscaling: Heat (1 app cố định AZ-A + ASG-B min 1/max 2) + Ceilometer/Gnocchi/Aodh.

Repo này **không chứa mã Shlink**. Không fork, không sửa upstream.

## 2. Nguồn sự thật: đọc trước khi trả lời

| File | Dùng để |
| --- | --- |
| `docs/SRS.md` | Yêu cầu có mã (FR-APP, FR-INF, NFR, C-, O-). Cột "Kiểm bằng" = tiêu chí dừng. Mục 4 = hợp đồng API/env/cổng/bàn giao. |
| `docs/inventory.yaml` | Tên, ID, IP, CIDR thật. **Không bịa giá trị**; chưa có thì để `REPLACE_...` và nói rõ. |
| `docs/versions.lock` | Phiên bản và SHA đã khóa. |
| `docs/handoffs/` | Thông tin bàn giao H0–H6 giữa các thành viên (UUID, endpoint, thủ tục). |
| `docs/troubleshooting.md` | Lỗi nhóm đã gặp và cách sửa. **Tra ở đây trước khi đoán nguyên nhân.** |
| `docs/decisions/` | ADR: quyết định đã chốt, không đề xuất ngược lại nếu không có lý do mới. |

Mâu thuẫn giữa các nguồn: báo cho người dùng, không tự chọn.

## 3. Ràng buộc cứng (không đề xuất phương án vi phạm)

- Ubuntu 24.04, DevStack **stable/2026.1**; không nâng/hạ phiên bản, không dùng `master`.
- Neutron ML2/**OVN**. Octavia provider **`ovn`**: listener TCP, pool `SOURCE_IP_PORT`, health monitor TCP. **Không Amphora, không L7 policy, không HTTP health monitor, không TLS termination ở Octavia.**
- Scaling bằng Heat `OS::Heat::AutoScalingGroup` + Aodh + Gnocchi. Không Senlin, Kubernetes, Magnum.
- Shlink `shlinkio/shlink:5.1.8` khóa bằng digest; không `latest`/`develop`; không sửa schema. Không SQLite khi nhiều replica.
- App/DB VM **không có floating IP**. Chỉ Nginx trên A:443 ra Internet. Cổng 80 trên A là Apache của DevStack: không cho Nginx nghe 80, chỉ mở SG 80 vài phút khi cấp cert Let's Encrypt.
- 10.20.0.0/24 (campus-net) và 172.24.4.0/24 (public của OpenStack) là mạng ảo; AWS không route tới. MTU guest 1400 (Geneve).
- Domain: `CAMPUS_DOMAIN = <EIP-gạch-ngang>.sslip.io`; cert Let's Encrypt. Không dùng `curl -k`/tắt verify để báo PASS.
- Quota project `campuslink`: 6 instance, 8 vCPU, 12 GiB RAM, 5 volume/30 GiB, 3 FIP. Flavor theo SRS C-06.
- Ngân sách ~70 USD: không đề xuất thêm EC2, NAT Gateway, ELB, RDS hay dịch vụ AWS trả phí khác.

## 4. Kiến thức của bạn có thể đã cũ

OpenStack 2026.1 có thể khác dữ liệu huấn luyện. Trước khi dùng một tham số CLI, option cấu hình hay thuộc tính Heat:

1. Kiểm bằng `openstack <lệnh> --help`, `openstack orchestration resource type show <Type>`, hoặc mã nguồn trong `/opt/stack/<project>` trên host A.
2. Hoặc tài liệu đúng nhánh: `https://docs.openstack.org/<project>/2026.1/`.
3. Nếu chưa kiểm được: ghi rõ **"chưa kiểm"** cạnh lệnh đó.

Khi debug, xin output thật (chạy `ops/ai-snapshot.sh`, log `journalctl -u devstack@<svc>`) thay vì đoán.

## 5. Truy cập cloud

- Agent chạy trên **máy cá nhân**, không cài lên controller. Lệnh tới cloud đi qua `ssh campus-a '<lệnh>'` (B: `ssh campus-b`, đi qua A bằng ProxyJump).
- Mỗi người SSH bằng user Linux riêng trên A (`tv2`/`tv3`/`tv4`, không sudo) và dùng credential Keystone của mình (`OS_CLOUD=<tên>`, file `~/.config/openstack/clouds.yaml` **trên host A**, không trong repo). TV2/TV3 là `member`, TV4 `reader`; chỉ TV1 dùng admin, `ubuntu`, `stack`, sudo.
- Lệnh cần sudo hoặc quyền admin OpenStack: đưa lệnh cho TV1 chạy, không tìm cách vượt quyền.
- Lấy trạng thái nhanh: `ssh campus-a 'OS_CLOUD=<tên> bash -s -- <phần>' < ops/ai-snapshot.sh` (chỉ đọc; xem đầu script).

## 6. Phải hỏi người trước khi chạy

Đề xuất lệnh, giải thích tác dụng, và **chờ người xác nhận** với mọi lệnh thay đổi trạng thái dùng chung:

- DevStack: `stack.sh`, `unstack.sh`, `clean.sh`, sửa `local.conf`, `systemctl restart/stop devstack@*`, reboot host.
- OpenStack: mọi `delete`, `stack create/update/delete`, `server rebuild/resize`, đổi network/router/subnet/SG, `quota set`, `role add/remove`, detach volume.
- AWS: stop/terminate/modify instance, SG, route table, EIP (release/disassociate), IAM.
- Dữ liệu: `DROP`/`TRUNCATE`/restore vào DB thật, `swift delete`, `docker system prune`, xóa file trong `/opt/stack`.
- Host: `iptables`/`nft`, `sysctl`, `netplan`.

Lệnh chỉ đọc (`list`, `show`, `status`, `journalctl`, `ss`, `ip`) thì chạy được ngay.

## 7. Không bao giờ

- Đọc, in ra, hoặc commit secret: `*.pem`, `local.conf`, `clouds.yaml`, `/etc/letsencrypt`, file env có PASSWORD/KEY, API key Shlink, Redis URI có mật khẩu. Thấy secret trong output thì che lại khi trích.
- Bịa output, ID, evidence; sửa test hoặc nới tiêu chí để "PASS".
- Đổi ràng buộc ở mục 3 mà không có ADR mới được nhóm duyệt.

## 8. Cách làm một việc

1. Xác định mã yêu cầu (vd FR-INF-09) và cột "Kiểm bằng" → đó là tiêu chí xong.
2. Đọc hợp đồng liên quan (SRS mục 4), inventory, handoff, troubleshooting.
3. Đưa kế hoạch ngắn + lệnh; đánh dấu lệnh nào thay đổi trạng thái (mục 6).
4. Sau khi chạy: so output với tiêu chí; nói rõ PASS/FAIL và vì sao.
5. Evidence: lưu output **đã che** vào `evidence/<gate>/<yyyymmdd>-<mã>-<mô tả>.txt|png`.
6. Gỡ được một lỗi mới: thêm 1 dòng vào `docs/troubleshooting.md`.
7. Chốt một quyết định thiết kế: viết ADR trong `docs/decisions/`.

## 9. Quy ước

- File cấu hình thật không commit; chỉ `*.example` với giá trị `REPLACE_...`.
- Comment trong file cấu hình/script: tiếng Việt không dấu (như file hiện có). Tài liệu `.md`: tiếng Việt có dấu.
- Commit: `[FR-INF-09] mô tả ngắn`. Nhánh: `tv1/...`, `tv2/...`, `tv3/...`, `tv4/...`.
- Thư mục và chủ sở hữu: xem `README.md` và `.github/CODEOWNERS`.
