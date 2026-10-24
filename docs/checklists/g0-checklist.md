# Checklist G0 – Lab 0–4 (TV1, có TV4 thu evidence)

Ghi giờ **UTC** cho mỗi bước. Lưu output đã che vào `evidence/G0/`. Mỗi ô ✔ chỉ đánh khi có bằng chứng.

## Phần 1 – Trước khi thuê máy (không tốn tiền)

| # | Việc | Lệnh / nơi kiểm | PASS khi | Evidence | ✔ |
|---|---|---|---|---|---|
| 1.1 | Đúng tài khoản/Region | `aws sts get-caller-identity` (CloudShell us-east-1) | ARN đúng tài khoản nhóm | ARN đã che account ID | ✔ |
| 1.2 | Type hỗ trợ nested | `aws ec2 describe-instance-types --region us-east-1 --instance-types m7i.2xlarge m7i.xlarge --query 'InstanceTypes[].{Type:InstanceType,Features:ProcessorInfo.SupportedFeatures}'` | Cả hai có `nested-virtualization` | output | ✔ |
| 1.3 | AZ name + ID | `aws ec2 describe-availability-zones --region us-east-1 --query 'AvailabilityZones[].{Name:ZoneName,ID:ZoneId,State:State}'` | Chọn được 2 AZ; ghi ID vào inventory | output | ✔ |
| 1.4 | m7i có ở cả 2 AZ đã chọn | `aws ec2 describe-instance-type-offerings --region us-east-1 --location-type availability-zone --filters Name=instance-type,Values=m7i.2xlarge,m7i.xlarge` | Cả 2 type xuất hiện ở AZ đã chọn | output | ✔ |
| 1.5 | Quota vCPU | Console → Service Quotas → EC2 → Running On-Demand Standard instances | ≥ 12 vCPU khả dụng (cộng phần đang dùng) | ảnh | ✔ |
| 1.6 | Quota EIP | Service Quotas → EC2-VPC Elastic IPs | còn ≥ 1 | ảnh | ✔ |
| 1.7 | Quyền IAM | Console → IAM → Roles → Create role (thử tới bước review, chưa cần tạo) | Không bị deny; hoặc có admin cấp sẵn role | ảnh/ghi chú | ✔ |
| 1.8 | Credit/Billing | Billing → Credits | Ghi số dư thật, hạn, phạm vi áp dụng | ảnh đã che | ✔ |
| 1.9 | Budget cảnh báo | Billing → Budgets | Có cảnh báo 30/50/65 USD | ảnh | ✔ |
| 1.10 | CIDR không trùng | So 10.11/16, 10.20/24, 10.21/24, 172.24.4/24 với VPN/WSL/Docker máy cá nhân | Không trùng | ghi chú | ✔ |

**Kết quả ngày 22/10/2026 (TV1):** cả 10 mục PASS. Số liệu: tài khoản thường (root, Paid plan), quota vCPU 16 (đang dùng 0), EIP 5, credit 131,38 USD hạn khoảng 1 năm, budget 30/50/65, m7i hai type đều có nested. AZ chọn: A = `us-east-1a` (use1-az1), B = `us-east-1b` (use1-az2); dự phòng `c`/`d`.
- 1.7 và 1.8 do TV1 tự xác nhận, chưa có ảnh. Còn phải lưu output/ảnh đã che vào `evidence/G0/`.
- Mở: đã có chi phí 3,92 USD trong tháng (dự báo 6 USD) dù chưa chạy máy nào. Cần xem Billing → Bills theo Service trước khi tạo thêm tài nguyên.

**Dừng lại nếu** 1.2, 1.5 hoặc 1.7 fail: ghi lỗi nguyên văn (che ID), báo nhóm, đổi tài khoản hoặc hỏi giảng viên. Không xin quyền rộng bừa bãi (Lab 1.1).

## Phần 2 – Mạng AWS (Lab 2) → điền `infra/aws/README.md`

| # | Việc | PASS khi | ✔ |
|---|---|---|---|
| 2.1 | VPC 10.11.0.0/16, bật DNS resolution + hostnames, không dùng wizard NAT Gateway | VPC ID ghi inventory | ✔ |
| 2.2 | 4 subnet đúng AZ | public-A/private-A ở AZ-A; public-B/private-B ở AZ-B | ✔ |
| 2.3 | IGW attach + public RT 0.0.0.0/0 → IGW | public-A/B associate | ✔ |
| 2.4 | private RT (chỉ local lúc này) | private-A/B associate | ✔ |
| 2.5 | SG `campus-hosts` (self all) + `campus-ingress-admin` (22) | Lúc làm: 22 chỉ từ /32. Từ 22/10 đổi theo ADR-07: 22 mở 0.0.0.0/0 tới freeze 06/11, bù bằng chỉ key + fail2ban + user riêng | ✔ (đổi theo ADR-07) |

## Phần 3 – A, NAT, B (Lab 3) – bắt đầu tốn tiền

| # | Việc | Kiểm | PASS khi | ✔ |
|---|---|---|---|---|
| 3.1 | Launch A: m7i.2xlarge, 10.11.0.10, root 60 + data 30 (data `DeleteOnTermination=No`), **Nested = Enable**, IMDSv2 hop 1, Shutdown behavior = Stop, tag `Project=CampusLink` (instance + volume), không gắn IAM role | console | ACTIVE, đúng AZ (ảnh AZ ID, FR-INF-01) | ✔ |
| 3.2 | EIP gắn A (tag `Project=CampusLink`, **không release**: đổi EIP = đổi domain sslip); **tắt source/dest check** trên A; ghi EIP dạng gạch ngang vào inventory | console | – | ✔ |
| 3.3 | SSH `campus-a` | `hostname; ip -br addr; ip route` | vào đúng máy | ✔ |
| 3.3b | Cứng hóa SSH (ADR-07): chỉ key + fail2ban | `sudo sshd -T \| grep -E 'passwordauthentication\|permitrootlogin'`; `sudo fail2ban-client status sshd` | `passwordauthentication no`, `permitrootlogin no`/`without-password`; jail sshd chạy | ✔ |
| 3.4 | Cài NAT: sysctl + `ops/campus-nat` + unit | `sudo iptables -t nat -L POSTROUTING -n -v` | Có 2 rule MASQUERADE | ✔ |
| 3.4b | Tự tắt trên A (`start-stop.md` §4) | `systemctl list-timers campus-idle-shutdown.timer` | Timer active | ✔ |
| 3.5 | private RT 0.0.0.0/0 → ENI A; SG A cho 80/443 từ 10.11.11.0/24 | console | – | ✔ |
| 3.6 | Launch B: m7i.xlarge, 10.11.11.10, **không public IP**, chỉ SG `campus-hosts`, Nested = Enable, IMDSv2 hop 1, Shutdown behavior = Stop, tag `Project=CampusLink`, AZ khác A | console | Ảnh AZ ID + không có public IPv4 | ✔ |
| 3.7 | SSH `campus-b` qua ProxyJump | `ssh campus-b hostname` | OK, không chép private key lên A | ✔ |
| 3.7b | Tự tắt trên B (`MODE=b`) | `systemctl list-timers campus-idle-shutdown.timer` | Timer active | ✔ |
| 3.8 | B ra Internet | `getent hosts opendev.org; curl -I --connect-timeout 10 https://opendev.org; sudo apt-get update` | DNS ok, HTTP 200/301/302, apt không timeout; counters NAT trên A tăng | ✔ |

Nếu 3.8 fail: DNS → private RT target → source/dest check → `ip_forward` → NAT counters → SG transit → NTP (Lab 3.3). **Không** gán public IP cho B để che lỗi.

## Phần 4 – OS, KVM, storage (Lab 4)

| # | Việc | Kiểm | PASS khi | ✔ |
|---|---|---|---|---|
| 4.1 | Gói nền (A/B) | Trước: `systemctl is-active apt-daily.service apt-daily-upgrade.service` ra 2 dòng `inactive` (máy mới bật thì unattended-upgrades đang giữ khóa dpkg, chờ xong). Rồi `sudo apt-get install -y git curl jq tmux chrony cpu-checker qemu-kvm libvirt-daemon-system libvirt-clients lvm2 python3-venv python3-pip sysstat tcpdump` | thành công | ✔ |
| 4.1b | Cập nhật tự động không tự restart service lõi (A/B) | Khối lệnh 4.1b dưới bảng | `apt-config dump Unattended-Upgrade::Package-Blacklist` in đủ 6 dòng (openvswitch-, ovn-, mysql-, rabbitmq-server, qemu-, libvirt); file needrestart có `'l'` | ✔ |
| 4.2 | Hostname bền | `hostnamectl`; `/etc/cloud/cloud.cfg.d/99-campus-hostname.cfg` có `preserve_hostname: true`; `/etc/hosts` có 2 dòng. Làm **trước** `stack.sh`, rồi Stop/Start máy một lần và kiểm lại (node RabbitMQ gắn với hostname: đổi tên sau khi cài là mất user `stackrabbit`) | campus-a / campus-b, giữ nguyên sau stop/start. **Đã kiểm sau Stop/Start 24/10/2026** (hostname, hosts, ping, by-id + VG, chrony, NAT, timer): `evidence/G1/20261024-FR-INF-02-sau-stop-start.txt` | ✔ |
| 4.3 | Giờ (Amazon Time Sync) | Ubuntu cloud image đã có sẵn `server 169.254.169.123 prefer iburst minpoll 4 maxpoll 4` trong `/etc/chrony/conf.d/00-cpc.conf` (nạp trước các dòng `pool` qua `confdir`), nên **không cần sửa** `chrony.conf` (thêm nữa chỉ bị trùng). Chỉ kiểm: `chronyc sources -v`, `chronyc tracking` | dòng `^*` là 169.254.169.123; đồng bộ. B dùng được cả khi NAT chưa xong (địa chỉ link-local) | ✔ |
| 4.4 | **KVM** (A và B) | `ls -l /dev/kvm; sudo kvm-ok; sudo virt-host-validate qemu` | `/dev/kvm` có, kvm-ok "can be used" | ✔ |
| 4.5 | CpuOptions thật | `aws ec2 describe-instances … --query '…CPU:CpuOptions…'` | nested enabled. **Chưa chạy 23/10** (cần AWS CLI); thay bằng `/dev/kvm` + `kvm-ok` trên A và B (4.4) và ảnh launch FR-INF-02 | — |
| 4.6 | Đĩa Cinder | `lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,SERIAL` → so SERIAL với volume ID (`vol0875752f0e893ca17`); `ls -l /dev/disk/by-id/*vol0875752f0e893ca17*`; `sudo wipefs -n /dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_vol0875752f0e893ca17` | đúng đĩa 30 GiB trống; ghi `nvme_serial` vào inventory. Tên `nvmeXn1` có thể đổi sau stop/start, nên DEV dùng đường by-id | ✔ |
| 4.7 | VG | `DEV=/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_vol0875752f0e893ca17` (link không có đuôi `-part`/`_1`, đúng tên in ra ở 4.6); `sudo pvcreate $DEV; sudo vgcreate stack-volumes-lvmdriver-1 $DEV; sudo vgs` | VG ~30 GiB, **không** mkfs | ✔ |
| 4.8 | User stack (A/B) | `id stack; sudo visudo -cf /etc/sudoers.d/stack` | OK | ✔ |

**Lệnh cho 4.1b** (A và B, chốt 23/10/2026): needrestart chỉ báo, không tự restart; unattended-upgrades không tự nâng gói lõi của DevStack, các gói khác vẫn tự vá bảo mật. Gói lõi chỉ nâng tay, có kế hoạch, ghi vào nhật ký cloud. Bỏ được bất cứ lúc nào bằng cách xóa `/etc/needrestart/conf.d/50-campuslink.conf` và `/etc/apt/apt.conf.d/51campuslink-unattended`.

```bash
echo "\$nrconf{restart} = 'l';" | sudo tee /etc/needrestart/conf.d/50-campuslink.conf
sudo tee /etc/apt/apt.conf.d/51campuslink-unattended >/dev/null <<'EOF'
// CampusLink: khong tu nang goi loi DevStack (regex khop dau ten goi)
Unattended-Upgrade::Package-Blacklist {
    "openvswitch-";
    "ovn-";
    "mysql-";
    "rabbitmq-server";
    "qemu-";
    "libvirt";
};
EOF
echo 'DPkg::Lock::Timeout "600";' | sudo tee /etc/apt/apt.conf.d/90campuslink-lock
# kiem
cat /etc/needrestart/conf.d/50-campuslink.conf
apt-config dump Unattended-Upgrade::Package-Blacklist
apt-config dump DPkg::Lock::Timeout
```

**PASS G0** = Phần 1 + 4.4 trên cả hai host + 3.8, có bảng chi phí tạm. Sau đó stop B rồi A (Stop, không Terminate). Ghi cloud = OFF.

## Bảng chi phí tạm G0 (23/10/2026)

Cloud = **OFF từ 23:05 giờ VN (16:05 UTC) ngày 23/10/2026**: B rồi A đã Stop, không Terminate. Giờ chạy lấy từ `last -x` trên A và `uptime -s` trên B (UTC); giờ Stop do TV1 báo, tính chung 16:05 cho cả hai. Sai số khoảng ±1–2 phút, vì AWS tính từ lúc instance vào trạng thái `running`, sớm hơn lúc boot chừng chục giây.

| Host | Lần chạy (UTC) | Thời lượng | Đơn giá (USD/giờ) | Ước tính (USD) |
|---|---|---|---|---|
| A `m7i.2xlarge` | 07:44:01 → 08:35:20 | 0:51:19 | 0,4032 | 0,34 |
| A | 14:29:18 → 16:05 | 1:35:42 | 0,4032 | 0,64 |
| B `m7i.xlarge` | 14:24:43 → 16:05 | 1:40:17 | 0,2016 ⚠️ | 0,34 |
| **Tổng tiền máy** | | A 2,45 giờ + B 1,67 giờ | | **≈ 1,32** (làm tròn từng dòng) |

Khi máy tắt vẫn tốn (ước tính, ⚠️ chưa kiểm bằng AWS Pricing Calculator):

| Khoản | Cách tính | Ước tính |
|---|---|---|
| EBS 150 GiB gp3 mã hóa (60 + 30 + 60) | 0,08 USD/GiB-tháng | ≈ 12 USD/tháng ≈ 0,40 USD/ngày |
| EIP `44.198.215.187` (public IPv4, gắn A) | 0,005 USD/giờ | ≈ 0,12 USD/ngày |
| Snapshot DLM | chưa tạo | 0 |
| **Tắt hẳn** | | **≈ 0,5 USD/ngày** |

Chạy cả A và B khoảng 0,6 USD/giờ. Đơn giá B (0,2016) suy ra bằng nửa giá A, chưa thấy trực tiếp trong console.

Credit còn lại: **129,57 USD** (TV1 đọc ở Billing → Credits ngày 24/10/2026; 22/10 là 131,38 USD, giảm 1,81 USD). ⚠️ Billing có thể trễ đến 24 giờ nên số này chưa chắc đã tính đủ các lần chạy máy.

Còn thiếu (điền tay, không suy ra): số liệu thực tế từ Cost Explorer sau khoảng 24 giờ để đối chiếu bảng này.

## Phần 5 – Việc thêm của TV1 trong G0–G1 (SRS 6.3, `docs/runbooks/start-stop.md`)

Làm trên console AWS ngày 23–24/10/2026 khi máy đang tắt. Ảnh trong `evidence/G0/` đã che account ID (ảnh có ARN chưa lưu).

| # | Việc | Kiểm | PASS khi | ✔ |
|---|---|---|---|---|
| 5.1 | Tag `Project=CampusLink` | Console: EC2 → Instances/Volumes/Elastic IPs, tìm `CampusLink` | A, B, 3 volume, EIP đều có tag | EIP ✔ (`20261023-G0-eip-tags-project.png`); instance và volume mang tag từ lúc launch (ảnh launch), chờ kiểm lại bằng snapshot DLM 5.4 |
| 5.2 | IAM: group `campuslink-members`, policy `CampusLinkStartStop`, user `tv2`–`tv4` | IAM → Groups/Policies/Users | Policy đúng file `infra/aws/iam-member-startstop.json` (có Condition tag); 3 user thuộc group, bắt đổi mật khẩu lần đầu | ✔ (`20261023-NFR-16-iam-campuslink-startstop-policy.png`, `-iam-users-tv2-tv4.png`). Còn mở: account alias để có URL đăng nhập; bật MFA cho tv2–tv4; `luongkien25` cũng nằm trong group |
| 5.3 | Lịch tắt 02:00 (EventBridge Scheduler) | Schedule `campuslink-stop-0200`, cron `0 19 * * ? *`, UTC, target EC2 `StopInstances`, role `CampusLinkSchedulerStopEc2Role` (trust `scheduler.amazonaws.com`, policy `CampusLinkSchedulerStopEc2`), retry 1 giờ và 10 lần | Enabled, đúng input 2 instance ID | ✔ cấu hình (`20261023-NFR-16-scheduler-*.png`). **Chạy thật chưa kiểm:** sáng 24/10 vào CloudTrail → Event history, lọc `StopInstances`, phải có sự kiện khoảng 19:00 UTC của role trên, không có `errorCode` |
| 5.4 | Snapshot hằng ngày (DLM) | Policy `policy-03e03380fa1963144`: target Instance, tag `Project=CampusLink`, mỗi 24 giờ lúc 20:00 UTC, giữ 3 bản, Copy tags | Enabled | ✔ cấu hình (`20261024-G0-dlm-policy-detail.png`, `-dlm-policy-settings.png`). **Chạy thật chưa kiểm:** sau 20:00 UTC phải có 3 snapshot (root A, Cinder A, root B) |
| 5.5 | User Linux `tv2`–`tv4` + fail2ban | `ops/add-member.sh` trên A, cần public key từng người | `id tv2`..., đăng nhập bằng key, không sudo | ☐ làm ở phiên G1 (cần A đang bật). `fail2ban` trên A đã chạy từ 3.3b |
| 5.6 | Chứng thư Let's Encrypt cho `44-198-215-187.sslip.io` | sổ tay TV1 v1.2 mục 16.3 | cert hợp lệ, không dùng `curl -k` | ☐ làm ở G3 (khoảng 27/10), cần Nginx/Apache trên A và mở SG 80 vài phút |
