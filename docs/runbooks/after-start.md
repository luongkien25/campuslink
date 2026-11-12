# Runbook: kiểm sau khi bật máy (FR-INF-19)

Chạy sau bước "Bật" của [start-stop.md](start-stop.md). Mục đích: biết cụm đã dùng được chưa, **không sửa gì khi chưa biết lỗi là gì**. Không chạy lại `stack.sh`, không `unstack.sh`/`clean.sh`, không restart hàng loạt `devstack@*`.

Nguồn: 09 M.6 (ghi chú TV1), Lab TV1 v1.2 mục 12.3–12.4 (bỏ bước 5–6 in lẫn của 12.2), evidence `evidence/G1/20261025-FR-INF-19-*`, `evidence/G2/20261027-FR-INF-19-*`, `evidence/G3/20261027-*`.

Ai làm phần nào:

- **Phần 1: ai bật máy cũng làm** (user `tv2`/`tv3`/`tv4`, không cần `sudo`, dùng `OS_CLOUD` của mình). 5 phút.
- **Phần 2: chỉ TV1** (cần `sudo` và quyền admin OpenStack). Làm khi Phần 1 có dòng FAIL, sau thay đổi lớn, và trước mỗi buổi đo/demo.
- **Phần 3: bảng trước/sau** cho FR-INF-19 (khi đã có app và dữ liệu thật).

Gặp FAIL: tra [troubleshooting.md](../troubleshooting.md) theo triệu chứng, ghi vào issue "Nhật ký cloud", báo TV1. Không tự sửa cấu hình host.

## 0. Thứ tự bật

1. Console EC2 (us-east-1): Start **A**, đợi `2/2 checks passed`. Chưa SSH được thì xem *Actions → Monitor and troubleshoot → Get system log*.
2. Start **B** sau khi A đã lên (B ra Internet và nói chuyện với OpenStack qua A).
3. Đợi khoảng **5 phút** sau khi B lên rồi mới kết luận các dòng OpenStack (dịch vụ báo `up` chậm vài phút sau boot).

## 1. Phần 1: kiểm nhanh (mọi thành viên)

Từ laptop: `ssh campus-a`, rồi dán từng dòng. Thay `tv2` bằng tên của bạn.

```bash
export OS_CLOUD=campus-tv2
```

| # | Lệnh | PASS khi | FAIL thì |
|---|---|---|---|
| 1.1 | `hostnamectl --static; uptime` | `campus-a`; uptime đúng lúc bạn bật | Sai tên host: dừng, báo TV1 |
| 1.2 | `ip -br addr show br-ex` | có `172.24.4.1/24` | Báo TV1 (2.3). Không tự `ip address` |
| 1.3 | `systemctl list-units --type=service --state=failed --no-legend; echo rc=$?` | không in dòng unit nào, `rc=0` | Chép tên unit vào issue, báo TV1 |
| 1.4 | `systemctl is-active campus-nat nginx apache2` | 3 dòng `active` | `nginx` `inactive`: báo TV1 (2.6) |
| 1.5 | `openstack loadbalancer provider list -f value -c name` | có dòng `ovn` | Báo TV1 (2.5). Không tạo LB khi thiếu `ovn` (sẽ ra amphora, không chạy được) |
| 1.6 | `openstack server list -c Name -c Status` | VM của nhóm `ACTIVE` | `SHUTOFF`: xem 1.8. `ERROR`: báo TV1 |
| 1.7 | `openstack volume list -c Name -c Status` | `campus-db-data` là `in-use` (khi đã gắn DB VM) | `error`/`available` sai dự kiến: báo TV3 + TV1 |
| 1.8 | Chỉ khi có VM `SHUTOFF`: bật **DB VM trước**, đợi `ACTIVE`, rồi mới bật app: `openstack server start <UUID>` | VM lên `ACTIVE` | Dùng UUID, không dùng tên (dễ trùng) |

Từ **laptop** (PowerShell hoặc Git Bash), không dùng `-k`:

| # | Lệnh | PASS khi |
|---|---|---|
| 1.9 | `curl.exe -sS -o NUL -w "%{http_code}\n" https://admin.44-198-215-187.sslip.io/` | `200` |
| 1.10 | `curl.exe -sS -o NUL -w "%{http_code}\n" https://s.44-198-215-187.sslip.io/rest/health` | `200` khi đã có app (trước đó là `503`, đúng thiết kế) |
| 1.11 | `curl.exe -sS -o NUL -w "%{http_code} %{redirect_url}\n" https://s.44-198-215-187.sslip.io/<slug-mau>` | `302` và đúng đích |

Windows báo lỗi thu hồi chứng chỉ (`CRYPT_E_NO_REVOCATION_CHECK`): thêm `--ssl-revoke-best-effort`, **không** thêm `-k`.

Đủ PASS thì ghi một dòng vào issue "Nhật ký cloud": giờ UTC, "after-start Phần 1 PASS" (hoặc số dòng FAIL).

## 2. Phần 2: kiểm đầy đủ (TV1)

Trong shell `ubuntu@campus-a`, định nghĩa một lần (giống evidence G2):

```bash
a() { sudo -u stack -H bash -c "source /opt/stack/devstack/openrc admin admin >/dev/null 2>&1; $*"; }
```

### 2.1 Host A

```bash
hostnamectl --static; chronyc tracking | grep -E 'System time|Leap'; df -h / | tail -1
findmnt /opt/stack/data/swift/drives/sdb1; sudo vgs stack-volumes-lvmdriver-1; lsblk -o NAME,SERIAL
```

PASS: Leap `Normal`; `/` còn ≥ 10 GiB; `sdb1` mount từ `/dev/loopN`; VG có mặt (VFree ghi lại); ghi tên NVMe nếu đổi (đã đảo chỗ 27/10, VG vẫn lên nhờ filter regex). Swift chưa mount: **không** `mkfs`, đối chiếu file `swift.img` cũ rồi mới mount (Lab 12.3 bước 3).

### 2.2 NAT và mạng host

```bash
systemctl status campus-nat --no-pager | head -5; sudo iptables -t nat -L POSTROUTING -n -v | grep -E '10.11.11.0/24|172.24.4.0/24'
```

PASS: `active (exited)`, có drop-in `br-ex.conf`; 2 dòng MASQUERADE.

### 2.3 Nếu `br-ex` mất IP

Sửa bền đã cài 25/10 (`ops/campus-br-ex` + drop-in). Nếu vẫn mất: `sudo systemctl restart campus-nat`, rồi `ip -br addr show br-ex`. Chỉ khi vẫn không có: `sudo ip address replace 172.24.4.1/24 dev br-ex && sudo ip link set br-ex up`. Ghi vào troubleshooting vì sửa bền đã không chạy.

### 2.4 OpenStack (admin)

```bash
a openstack compute service list -c Binary -c Host -c State -f value
a "openstack network agent list -c 'Agent Type' -c Host -c Alive -f value"
a openstack volume service list -c Binary -c Host -c State -f value
```

PASS: `nova-compute` của `campus-a` **và** `campus-b` `up`; network agent có **4** dòng OVN (đã thấy 24/10, 25/10), tất cả `:-)`/`True`; `cinder-volume` `up`.

Hàm `a` nối đối số bằng `$*` nên làm mất dấu nháy: đối số có khoảng trắng (`-c 'Agent Type'`) phải nằm trong một chuỗi bọc cả lệnh như dòng 2 (HANDOFF phiên 19, cạm bẫy 2).

### 2.5 Octavia provider `ovn`

```bash
ls -ld /run/octavia; a openstack loadbalancer provider list
```

PASS: thư mục có, chủ `stack`; có `ovn`. Thiếu thư mục: `sudo systemd-tmpfiles --create /etc/tmpfiles.d/octavia.conf`, rồi `sudo systemctl restart devstack@o-api`, đợi 10 giây, kiểm lại. (`devstack@o-da` báo `active` cả khi lỗi bind socket, nên `--state=failed` không bắt được lỗi này.)

### 2.5b Swift: cấu hình cho access rules (từ 07/11/2026)

```bash
sudo grep -nE '^(service_type|include_service_catalog)' /etc/swift/proxy-server.conf; systemctl is-active devstack@s-proxy
```

PASS: có `service_type = object-store` **và** `include_service_catalog = True` (hai dòng sửa tay 07/11, ngoài repo, ADR-10 mục 6), `s-proxy` `active`. Thiếu một trong hai thì credential có access rules (`campus-svc`, `campus-boot`) bị 401 hoặc 500 dù mọi thứ khác đúng: báo TV1, không tự sửa.

### 2.6 Nginx và Apache `Alias`

```bash
systemctl is-enabled nginx; systemctl is-active nginx; sudo nginx -t 2>&1 | tail -1; sudo ss -lntp | grep -E ':(80|443) '
```

PASS: `enabled`, `active`, `syntax is ok`; `:443` là `nginx`, `:80` là `apache2`. Nginx `inactive`: `sudo systemctl enable --now nginx`. **Không bao giờ** để Nginx nghe 80 (chiếm cổng của Keystone/Placement).

### 2.7 B

**Chạy từ laptop**, không chạy từ A: `ssh campus-b` (ProxyJump qua A). Khóa SSH vào B chỉ nằm trên laptop, trên A không có khóa nên `ssh campus-b` từ A báo `Host key verification failed` (`BatchMode`). Vào shell B rồi dán lệnh dưới, hoặc `ssh campus-b '<lệnh>'`.

```bash
hostnamectl --static; chronyc tracking | grep -E 'System time|Leap'; systemctl list-units 'devstack@*' --state=failed --no-legend; echo rc=$?
systemctl show devstack@ceilometer-acompute -p ActiveState -p NRestarts
```

PASS: `campus-b`; không unit lỗi; `ceilometer-acompute` `active`, `NRestarts=0` (khác 0 là lỗi Redis coordination, troubleshooting mục "Đã biết trước").

### 2.8 Guest, LB, telemetry (khi đã có app)

```bash
a openstack server list --all-projects --long -c Name -c Status -c Host
a openstack loadbalancer status show <LB_ID>
a openstack metric measures show -r <VM_UUID> cpu --granularity 60 | tail -3
a openstack alarm list
```

PASS: DB VM và app `ACTIVE` đúng host; member `ONLINE`; metric có điểm mới trong 5 phút; alarm không kẹt `insufficient data`. Rồi mới bật lại alarm/scaling (TV2) và cho TV4 chạy tải (Lab 12.3 bước 9).

## 3. Phần 3: bảng trước/sau (FR-INF-19, Lab 12.4)

Ghi cột "Trước" **trước khi Stop**, cột "Sau" sau Phần 1 và 2. Lưu thành `evidence/<gate>/<yyyymmdd>-FR-INF-19-truoc-sau.txt`, che secret.

| Mục | Trước tắt (lệnh) | Sau bật: PASS khi |
|---|---|---|
| Link mẫu | slug + URL đích trong DB | `curl` slug ra `302`, đúng `Location` |
| Swift | `openstack object save campus-backups <obj> --file - \| sha256sum` | checksum giống |
| Cinder | `sha256sum` file test trên volume DB | file còn, mount đúng UUID |
| Guest | `server list` UUID + port + volume attachment | UUID không đổi, không bị tạo lại |
| App | digest Shlink, `/rest/health` | cùng digest, `200`, Redis PING có auth PASS (TV3) |
| Mạng, IAM | B `apt-get update` được; trên A `aws sts get-caller-identity` ra role `CampusLinkBackup` | giống trước; quét cổng từ ngoài chỉ 22 và 443 |

PASS G2/FR-INF-19: ít nhất một lần Stop/Start thật **cả A và B** với đủ bảng. Phải khôi phục bằng snapshot/rebuild thì ghi là restore, không gọi là stop/start bình thường.
