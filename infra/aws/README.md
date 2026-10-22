# AWS network – CampusLink (Lab 2–3, TV1)

VPC `campus-vpc` = `vpc-0730a24c74eb94b62`. Điền ID thật sau khi tạo. Chụp ảnh console đã che thông tin thanh toán, lưu vào `evidence/G0/`.

## Subnet

| Tên | CIDR | AZ (name / ID) | Route table | Auto-assign public IPv4 | Subnet ID |
|---|---|---|---|---|---|
| public-A | 10.11.0.0/24 | us-east-1a / use1-az1 | campus-public-rt | tắt (dùng EIP thủ công) | subnet-00c7d6d73205f3cae |
| private-A (dự phòng) | 10.11.10.0/24 | us-east-1a / use1-az1 | campus-private-rt | tắt | subnet-0402e50e0be29f05a |
| public-B (dự phòng) | 10.11.1.0/24 | us-east-1b / use1-az2 | campus-public-rt | tắt | subnet-0b9c94d9e201710f0 |
| private-B | 10.11.11.0/24 | us-east-1b / use1-az2 | campus-private-rt | tắt | subnet-06036244a1d16cab1 |

## Route table

| Route table | Đích | Target | Ghi chú |
|---|---|---|---|
| campus-public-rt (`rtb-082ab7fbd85ef92be`) | 10.11.0.0/16 | local | |
| campus-public-rt | 0.0.0.0/0 | campus-igw (`igw-0ceda12a7ab10f8da`) | |
| campus-private-rt (`rtb-07baedadc611749be`) | 10.11.0.0/16 | local | |
| campus-private-rt | 0.0.0.0/0 | **ENI của A** (REPLACE_ENI_A) | Chỉ thêm sau khi A chạy và đã tắt source/dest check. Không trỏ tới IGW |

**Không** thêm route tới 10.20.0.0/24 hay 172.24.4.0/24 (mạng ảo của OpenStack, AWS không biết đến).

## Security group

| SG | Gắn vào | Chiều | Cổng | Nguồn | Mục đích |
|---|---|---|---|---|---|
| campus-ingress-admin (`sg-0bf8503bfeee5a3c0`) | A | in | TCP 22 | **0.0.0.0/0 trong giai đoạn phát triển** (ADR-07), thu về /32 từng người trước freeze 06/11 | SSH, chỉ key, user riêng mỗi người |
| campus-ingress-admin | A | in | TCP 443 | 0.0.0.0/0 khi demo (ngoài lúc demo thì /32) | Nginx `s.` + `admin.` (SNI) |
| campus-ingress-admin | A | in | TCP 80 | 0.0.0.0/0 khi cấp/gia hạn cert và khi demo | Let's Encrypt HTTP-01 + chuyển hướng sang 443 |
| campus-hosts (`sg-096f3c77665c4e038`) | A, B | in | all | chính SG campus-hosts | Control plane + Geneve UDP 6081 |
| campus-hosts (hoặc SG riêng của A) | A | in | TCP 80, 443 | 10.11.11.0/24 | B ra Internet qua NAT A |
| (mặc định) | A, B | out | all | 0.0.0.0/0 | Cài đặt |

**Không mở ra Internet:** 5000, 6080, 8000, 8004, 8080, 9292, 3306, 5432, 5672, 6379, 6641/6642, 9696.

Khi thu hẹp SG self (lúc freeze): kiểm thực tế bằng `ss -lntup`, catalog, transport URL. Các cổng thường gặp: UDP 6081, TCP 6641/6642, 5672, 3306, API HTTP, iSCSI 3260 (theo `cinder.conf`).

## Instance

| | A | B |
|---|---|---|
| Type | m7i.2xlarge | m7i.xlarge |
| Subnet / IP | public-A / 10.11.0.10 | private-B / 10.11.11.10 |
| Public IP | EIP (REPLACE) | **không có** |
| Nested virtualization | Enable | Enable |
| IMDS | v2 required, hop 1 | v2 required, hop 1 |
| Source/dest check | **disabled** | giữ mặc định |
| EBS | root 60 gp3 + data 30 gp3 (Cinder) | root 60 gp3 |
| SG | campus-hosts + campus-ingress-admin | campus-hosts |
