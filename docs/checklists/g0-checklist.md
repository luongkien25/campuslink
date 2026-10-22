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
| 2.5 | SG `campus-hosts` (self all) + `campus-ingress-admin` (22 từ /32) | Không có 0.0.0.0/0 cho 22 | ✔ |

## Phần 3 – A, NAT, B (Lab 3) – bắt đầu tốn tiền

| # | Việc | Kiểm | PASS khi | ✔ |
|---|---|---|---|---|
| 3.1 | Launch A: m7i.2xlarge, 10.11.0.10, root 60 + data 30, **Nested = Enable**, IMDSv2 hop 1 | console | ACTIVE, đúng AZ | ☐ |
| 3.2 | EIP gắn A; **tắt source/dest check** trên A | console | – | ☐ |
| 3.3 | SSH `campus-a` | `hostname; ip -br addr; ip route` | vào đúng máy | ☐ |
| 3.4 | Cài NAT: sysctl + `ops/campus-nat` + unit | `sudo iptables -t nat -L POSTROUTING -n -v` | Có 2 rule MASQUERADE | ☐ |
| 3.5 | private RT 0.0.0.0/0 → ENI A; SG A cho 80/443 từ 10.11.11.0/24 | console | – | ☐ |
| 3.6 | Launch B: m7i.xlarge, 10.11.11.10, **không public IP**, Nested = Enable, AZ khác A | console | – | ☐ |
| 3.7 | SSH `campus-b` qua ProxyJump | `ssh campus-b hostname` | OK, không chép private key lên A | ☐ |
| 3.8 | B ra Internet | `getent hosts opendev.org; curl -I --connect-timeout 10 https://opendev.org; sudo apt-get update` | DNS ok, HTTP 200/301/302, apt không timeout; counters NAT trên A tăng | ☐ |

Nếu 3.8 fail: DNS → private RT target → source/dest check → `ip_forward` → NAT counters → SG transit → NTP (Lab 3.3). **Không** gán public IP cho B để che lỗi.

## Phần 4 – OS, KVM, storage (Lab 4)

| # | Việc | Kiểm | PASS khi | ✔ |
|---|---|---|---|---|
| 4.1 | Gói nền (A/B) | `sudo apt-get install -y git curl jq tmux chrony cpu-checker qemu-kvm libvirt-daemon-system libvirt-clients lvm2 python3-venv python3-pip sysstat tcpdump` | thành công | ☐ |
| 4.2 | Hostname bền | `hostnamectl`; `/etc/cloud/cloud.cfg.d/99-campus-hostname.cfg` có `preserve_hostname: true`; `/etc/hosts` có 2 dòng | campus-a / campus-b | ☐ |
| 4.3 | Giờ | `chronyc tracking` | đồng bộ | ☐ |
| 4.4 | **KVM** (A và B) | `ls -l /dev/kvm; sudo kvm-ok; sudo virt-host-validate qemu` | `/dev/kvm` có, kvm-ok "can be used" | ☐ |
| 4.5 | CpuOptions thật | `aws ec2 describe-instances … --query '…CPU:CpuOptions…'` | nested enabled | ☐ |
| 4.6 | Đĩa Cinder | `lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,SERIAL` → so SERIAL với volume ID; `sudo wipefs -n DEVICE` | đúng đĩa 30 GiB trống | ☐ |
| 4.7 | VG | `sudo pvcreate DEV; sudo vgcreate stack-volumes-lvmdriver-1 DEV; sudo vgs` | VG ~30 GiB, **không** mkfs | ☐ |
| 4.8 | User stack (A/B) | `id stack; sudo visudo -cf /etc/sudoers.d/stack` | OK | ☐ |

**PASS G0** = Phần 1 + 4.4 trên cả hai host + 3.8, có bảng chi phí tạm. Sau đó stop B rồi A (Stop, không Terminate). Ghi cloud = OFF.
