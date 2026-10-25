# H2 – Project, mạng, flavor, SG, image (TV1 → TV2, TV3)

Ngày (UTC): 2026-10-25 · Gate: G1 · Commit: (điền sau khi merge)
Không ghi secret. Mật khẩu Keystone chỉ nằm trong `~/.config/openstack/clouds.yaml` của từng người trên host A, không gửi qua Zalo (SRS O-02).
TV4 (`reader`) đọc được mọi thứ dưới đây nhưng không tạo được VM.

## 1. Đã sẵn sàng

| Thứ | Giá trị (UUID/IP/tên) | Kiểm bằng lệnh (sau `export OS_CLOUD=campus-tvN`) |
| --- | --- | --- |
| Project | `campuslink` `07af3a3dd4c24d1ba028efcb6d28ef84` | `openstack token issue -c project_id` |
| User Keystone | `campus-tv2`, `campus-tv3` (`member`), `campus-tv4` (`reader`) | `openstack token issue -c expires` |
| Đăng nhập | SSH vào A bằng user Linux `tv2`/`tv3`/`tv4`, file `~/.config/openstack/clouds.yaml` có sẵn; auth_url `http://10.11.0.10/identity` | `OS_CLOUD=campus-tv2 openstack server list` |
| AZ | `campus-az-a` (host `campus-a`), `campus-az-b` (host `campus-b`) | `openstack availability zone list --compute -c "Zone Name"` |
| Mạng | `campus-net` `18ecc898-663f-4440-9782-bdf1675ba5c9`, MTU **1400** | `openstack network show campus-net -c id -c mtu` |
| Subnet | `campus-subnet` `59399337-e22b-4237-87dd-bf4ac035bcfa`, 10.20.0.0/24, gateway 10.20.0.1, pool 10.20.0.100–220 | `openstack subnet show campus-subnet -c cidr -c gateway_ip` |
| Router | `campus-router` `971a03cd-406c-41ca-a395-a7637cc0f1f2` (gateway ngoài 172.24.4.128) | `openstack router show campus-router -c id` |
| Mạng ngoài | `public` 172.24.4.0/24, pool FIP 172.24.4.100–200 | `openstack network show public -c id` |
| Flavor | `campus.app` `a9083cf8-24ab-4a7a-8b5c-6ba44ed1b6de` (1 vCPU/2 GiB/10 GiB), `campus.db` `9ae2d463-8202-4575-a4f3-e32c4800d02c` (1/2 GiB/10 GiB), `campus.builder` `ee0a0c60-54c7-4488-896d-5081c1b098cf` (2/4 GiB/20 GiB, tạm) | `openstack flavor list -c Name -c VCPUs -c RAM -c Disk` |
| Quota project | 6 instance, 8 vCPU, 12288 MiB RAM, 5 volume/30 GiB, 3 floating IP | `openstack quota show` |
| SG app | `campus-app-sg` `b3eb3225-3e50-4c38-b43f-3823b6022d05`: TCP 8080 từ 10.20.0.0/24 và 172.24.4.0/24 | `openstack security group rule list --ingress campus-app-sg` |
| SG DB | `campus-db-sg` `15d5d84d-f71a-4595-a5b2-ac75f818c040`: TCP 5432 và 6379 chỉ từ `campus-app-sg` | `openstack security group rule list --ingress campus-db-sg` |
| Image guest | `ubuntu-noble-base` `b915f809-b352-4d03-a14a-ec9c294e85d8`, public; Ubuntu 24.04 `release-20261017`, qcow2 3,5 GiB, sha256 `04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94` | `openstack image show ubuntu-noble-base -c status -c visibility -c size` |
| Octavia | provider **`ovn`** (listener TCP, pool `SOURCE_IP_PORT`, health monitor TCP); mặc định cũng là `ovn` nhưng vẫn ghi `--provider ovn` khi tạo LB | `openstack loadbalancer provider list` |
| Endpoint private (từ A) | Keystone `http://10.11.0.10/identity/v3`, Nova `http://10.11.0.10/compute/v2.1`, Neutron `http://10.11.0.10/networking`, Octavia `http://10.11.0.10/load-balancer`; còn lại xem `openstack catalog list` | `openstack catalog list` |

Giá trị lâu dài đã nằm trong `docs/inventory.yaml` và `docs/versions.lock`.

## 2. Người nhận làm được gì / không được làm gì

- Được: tạo VM, port, volume, Heat stack, load balancer trong project `campuslink` trong hạn quota; gắn `campus-app-sg`/`campus-db-sg`; dùng flavor `campus.*` và image `ubuntu-noble-base`; tự `openstack keypair create --public-key <file .pub của bạn> <tên>`.
- Không được (hỏi TV1 trước): `stack.sh`/`unstack.sh`/`clean.sh`; đổi mạng, subnet, router, quota, role; tạo thêm user Keystone; sửa SG `campus-app-sg`/`campus-db-sg` của người khác; xóa `campus-db-port`, `campus-db-data` (xem H3); vượt 3 floating IP; dùng `sudo` hay credential `admin`.
- Keypair của Nova thuộc từng user Keystone, nên **không có keypair chung**. Mỗi người tự import khóa công khai của mình.

## 3. Cách tự kiểm tra (người nhận chạy trên A, đều PASS mới coi là nhận xong)

```
export OS_CLOUD=campus-tv2        # hoặc campus-tv3, campus-tv4
openstack token issue -c project_id                       # 07af3a3dd4c24d1ba028efcb6d28ef84
openstack availability zone list --compute -c "Zone Name" # có campus-az-a và campus-az-b
openstack flavor list -c Name | grep campus               # campus.app, campus.db, campus.builder
openstack image show ubuntu-noble-base -c status -c visibility   # active, public
openstack security group list -c Name                     # campus-app-sg, campus-db-sg, default
openstack network show campus-net -c mtu                  # 1400
openstack loadbalancer provider list                      # có ovn
```
TV2: thử thêm một LB nhỏ bằng quyền `member` của bạn (xem mục 4, chưa kiểm).

## 4. Đã biết còn thiếu hoặc lỗi

- **Chưa thử bằng quyền `member`:** Octavia (tạo LB), Heat, Gnocchi/Aodh, tạo floating IP. Smoke LB và metric của TV1 chạy bằng quyền admin. Gặp `403` thì báo TV1 (có thể cần gán role hoặc sửa policy), đừng tìm cách vượt quyền.
- **Chưa chốt cách vào VM không có floating IP để gỡ lỗi.** Host A chưa có route tới 10.20.0.0/24 (chưa thử thêm route qua gateway router 172.24.4.128). SG app/db cũng chưa mở SSH hay ICMP (SRS không quy định). Cần thì xin TV1.
- Gnocchi đang ghim commit **tạm** `4a41c1d…` (SRS O-06), chờ TV2 xác nhận (D1, D2). Metric `cpu` của VM đã có điểm mỗi 60 giây ở cả A và B, nhưng chưa kiểm archive policy, `rate:mean` và alarm Aodh (xem `docs/troubleshooting.md`, mục "insufficient data").
- Image Ubuntu chỉ đối chiếu SHA256SUMS qua HTTPS, chưa kiểm chữ ký GPG. Chưa cài Docker hay Shlink vào image (FR-INF-22 là việc của TV2).
- Quota 6 instance và 3 FIP tính cho cả project. VIP của LB sẽ cần một FIP (TV1 gắn cho Nginx, FR-INF-06).
- Cổng 22 của A mở 0.0.0.0/0 đến freeze 06/11 (ADR-07). Máy tự tắt khi không có phiên SSH (A 60 phút, B 15 phút sau A).

## 5. Lỗi đã gặp khi làm (đã thêm vào `docs/troubleshooting.md`? chưa, sẽ thêm cùng PR này)

- Shell `openrc admin admin` là project `admin`: không thấy server, volume, SG của `campuslink` theo tên (dùng UUID, hoặc dùng `OS_CLOUD=campus-tvN`).
- `openstack server add security group` bằng quyền admin báo "Security group … not found for project <admin>". Dùng `openstack port set --security-group <sg> <port>`. Lệnh `port set --security-group` **cộng dồn**; ghi trùng một SG thì Neutron trả 400.
- `openstack volume create` không có `--project`: tạo volume bằng `OS_CLOUD` của người dùng thật (xem H3).
- LB OVN quên `--provider ovn` sẽ kẹt `PENDING_CREATE`; mỗi lệnh sau khi tạo phải chờ LB về `ACTIVE`, nếu không bị 409.
