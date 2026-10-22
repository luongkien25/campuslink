# Runbook: bật/tắt 2 host theo phiên

Mục tiêu: không host nào chạy khi không ai dùng (SRS NFR-16, O-09). Ai cần làm thì tự bật; quên tắt thì máy tự tắt.

Chi phí tham khảo (us-east-1, chưa kiểm lại bằng Calculator): bật cả A + B khoảng **0,6 USD/giờ**; tắt vẫn tốn đĩa EBS (~150 GiB gp3) + EIP, khoảng **0,5 USD/ngày**.

## 1. Quyền bật/tắt cho thành viên (TV1 làm 1 lần)

1. Gắn tag `Project=CampusLink` cho instance A và B (policy dựa vào tag này).
2. IAM → Policies → Create → JSON: dán `infra/aws/iam-member-startstop.json`, đặt tên `CampusLinkStartStop`.
3. IAM → User groups → `campuslink-members`, gắn policy trên.
4. Tạo IAM user `tv2`, `tv3`, `tv4` (chỉ console access, bắt đổi mật khẩu lần đầu, nên bật MFA), cho vào group.
5. Gửi riêng cho từng người: link đăng nhập `https://<account-alias>.signin.aws.amazon.com/console` + mật khẩu tạm.

Thành viên chỉ thấy và bật/tắt được 2 instance có tag đó; không tạo, xóa, sửa gì khác. Nếu EBS mã hóa bằng KMS key tự tạo (không phải `aws/ebs`) thì Start sẽ lỗi quyền KMS: báo TV1.

## 2. Bật (người vào làm)

1. Comment vào issue **"Nhật ký cloud"**: tên, giờ UTC, định làm gì.
2. Console EC2 (us-east-1) → bật **A trước**, chờ `2/2 checks passed`, rồi bật **B** (B ra Internet qua NAT trên A).
3. `ssh campus-a` → chạy kiểm tra sau khi bật: `docs/runbooks/after-start.md` (TV1 viết ở G2, FR-INF-19). Không chạy lại `stack.sh`.
4. Việc dài mà không giữ SSH (đo tải từ laptop, demo): `ssh campus-a 'campus-keepalive 180'` (giữ máy 180 phút).

## 3. Tắt

- Tắt tay: **B trước, A sau** (Console → Stop). Ghi giờ tắt vào issue.
- Không tắt tay cũng được: host tự tắt (mục 4). Người bật cuối cùng vẫn chịu trách nhiệm kiểm tra cuối ngày.

## 4. Tự tắt khi không ai dùng (TV1 cài trên A và B)

Quy tắc trong `ops/idle-shutdown.sh`, kiểm mỗi 5 phút:

- **A** tắt sau **60 phút** không có: phiên SSH, tiến trình dài (`stack.sh`, `pg_dump`, `locust`, `apt-get`...), hoặc `campus-keepalive` còn hạn. 20 phút đầu sau boot không tính.
- **B** tắt sau **15 phút** kể từ khi A tắt và không ai SSH vào B.

```
# tren A (va lam tuong tu tren B)
sudo install -m 755 ops/idle-shutdown.sh /usr/local/sbin/
sudo install -m 755 ops/campus-keepalive /usr/local/bin/
sudo install -m 644 ops/campus-idle-shutdown.service ops/campus-idle-shutdown.timer /etc/systemd/system/
# chi tren B: doi MODE=a thanh MODE=b
sudo sed -i 's/MODE=a/MODE=b/' /etc/systemd/system/campus-idle-shutdown.service
sudo systemctl daemon-reload && sudo systemctl enable --now campus-idle-shutdown.timer
systemctl list-timers campus-idle-shutdown.timer
journalctl -t campus-idle            # xem lan tat gan nhat
```

EC2 phải để **Shutdown behavior = Stop** (mặc định), nếu là Terminate thì mất máy.

## 5. Chốt chặn cuối: tắt lúc 2 giờ sáng (miễn phí)

EventBridge → Scheduler → Create schedule: `cron(0 19 * * ? *)` (19:00 UTC = 02:00 giờ Việt Nam), target **EC2 StopInstances** với ID của A và B, để console tự tạo execution role. Phòng trường hợp script tự tắt bị lỗi hoặc ai đó để keepalive quá dài.

## 6. Snapshot EBS tự động (TV1 làm 1 lần, ~5 phút)

Mục tiêu: hỏng DevStack thì quay về bản tốt gần nhất trong ~15 phút thay vì dựng lại 2–3 ngày. Chi phí ước tính 2–4 USD cả đợt (0,05 USD/GB-tháng, chỉ tính block đã ghi, bản sau chỉ lưu phần thay đổi; chưa kiểm bằng Calculator).

**Tự động hằng ngày (Data Lifecycle Manager, không tốn phí dịch vụ):**
EC2 → Lifecycle Manager → Create policy → *EBS snapshot policy*:
- Target: **Instance**, tag `Project=CampusLink` (lấy cả root + đĩa Cinder 30 GiB của A, root của B).
- Schedule: hằng ngày lúc **20:00 UTC** (03:00 giờ VN, sau mốc tắt 02:00 nên đĩa đang đứng yên, snapshot nhất quán).
- Retain: **3** bản. Copy tags from source: bật. IAM role: để console dùng role mặc định.
- Máy tắt cả ngày thì snapshot gần như không tốn thêm (không có block mới).

**Chụp tay ở mốc quan trọng** (giữ lâu, DLM không xóa vì không phải bản của nó):
- Ngay khi `stack.sh` xong + G1 PASS; trước thay đổi lớn (`local.conf`, `stack.sh` lại); trước freeze 06/11.
- Tắt B rồi A trước khi chụp. EC2 → Elastic Block Store → Snapshots → *Create snapshot* → Resource type **Instance** → chọn A (làm lại với B). Tag `Name=G1-ok-<ngày>`.
- Chỉ giữ 1–2 bản chụp tay mới nhất; xóa bản cũ.

**Khôi phục:**
- Root: EC2 → chọn instance (đang chạy) → Actions → Monitor and troubleshoot → **Replace root volume** → chọn snapshot. Giữ nguyên Instance ID, ENI, IP riêng, EIP → domain sslip và QR không đổi.
- Đĩa Cinder (A): tắt A → detach đĩa 30 GiB → Create volume từ snapshot (cùng AZ, gp3) → attach đúng device cũ → bật A → kiểm `sudo vgs` thấy `stack-volumes-lvmdriver-1`.
- Sau khi khôi phục: chạy `after-start.md`, ghi vào issue "Nhật ký cloud" và `docs/troubleshooting.md` nguyên nhân hỏng.
