# Runbook: dựng DB VM 10.20.0.10 (FR-INF-12, issue #27)

Người làm: TV3 (`tv3` trên A, `OS_CLOUD=campus-tv3`). Đầu vào: H2, H3, H1 mục 5.2 và 6, ADR-10.
Không ghi secret vào repo, evidence, issue hay Zalo. Lệnh đánh dấu ⚠️ thay đổi trạng thái dùng chung: đọc lại rồi mới chạy (AGENTS.md mục 6).

## Thiết kế

| Thứ | Giá trị | Vì sao |
| --- | --- | --- |
| VM | `campus-db`, flavor `campus.db`, image `ubuntu-noble-base`, `--port campus-db-port` (10.20.0.10, chỉ `campus-db-sg`), AZ `campus-az-a` | SRS C-06; Cinder LVM/iSCSI chạy trên A |
| Volume | `campus-db-data` gắn sau khi tạo VM, ext4 nhãn `campus-db-data`, mount `/var/lib/postgresql` bằng UUID, `nofail` | Cluster PostgreSQL nằm trên volume; tên thiết bị trong guest có thể đổi (H3 mục 4) |
| PostgreSQL | gói `postgresql-16` của Ubuntu 24.04; `max_connections = 50`; role `shlink` `CONNECTION LIMIT 15`; DB `shlink` owner `shlink`; `pg_hba`: chỉ `shlink`→`shlink` từ `10.20.0.0/24`, `scram-sha-256` | H1 mục 5.2 (O-08) |
| Thiếu mount | drop-in `RequiresMountsFor=/var/lib/postgresql` cho `postgresql@16-main` | Kiểm bằng của FR-INF-12 |
| Redis | gói `redis-server` 7.0 của Ubuntu; `requirepass`, `appendonly yes`, `maxmemory 256mb`, `noeviction`; dữ liệu trên đĩa gốc | Redis là cache + hàng đợi (ADR-09); `noeviction` để không mất job, **đề xuất, chốt cùng TV4** |
| Secret | `openssl rand -hex 24` trên A; đưa vào VM qua user-data; ghi Swift `campus-secrets/app/db_password`, `app/redis_servers` | ADR-10 mục 2, H1 mục 6 |
| Tự kiểm | `campus-db-check.service` chạy mỗi lần boot, in `OK`/`FAIL` ra console (không in secret) | Không cần SSH hay VM nhảy để kiểm |

**Rủi ro chấp nhận:** user-data của DB VM chứa 2 mật khẩu. Giống ADR-10 với credential `campus-boot` trên VM app. Giảm thiểu: `bootcmd` chặn tiến trình không phải root gọi `169.254.169.254` mỗi lần boot; DB VM không chạy container hay dịch vụ nhận URL từ người dùng; đổi mật khẩu về sau làm bằng `ALTER ROLE`/sửa `campus.conf`, không qua user-data. Đã kiểm 08/11: `member` không đọc được `user_data` qua Nova API (bước 6).

Script: `app/db/user-data.tmpl.yaml`, `app/db/render-user-data.sh`, `app/db/put-secrets.sh`. Đã chạy thử trong container Ubuntu 24.04 (evidence `evidence/G3/20261107-FR-INF-12-db-vm-thu-local.txt`) và **chạy trên cụm 08/11** (evidence `evidence/G3/20261108-FR-INF-12-db-vm.txt`, H1 mục 10).

## 0. Trước phiên

Tích Zalo "Đang dùng 2 EC2", ghi issue #4 nếu bạn là người bật (`docs/runbooks/start-stop.md`). Chỉ cần A; B không bắt buộc.

## 1. Kiểm đầu vào (chỉ đọc)

```
export OS_CLOUD=campus-tv3
openstack server list -c Name -c Status                                  # chua co campus-db
openstack volume show campus-db-data -c status -c attachments            # available, []
openstack port show campus-db-port -c fixed_ips -c device_id -c security_group_ids   # 10.20.0.10, device_id rong
openstack quota show -c instances -c cores -c ram                        # con du 1 vCPU / 2048 MiB
openstack keypair list                                                   # co tv3 chua
```

Có gì khác (volume `in-use`, port đã gắn VM) thì **dừng**, hỏi TV1/TV2, không tạo lại.

## 2. Đưa script lên A, thử quyền ghi Swift

Từ máy cá nhân:

```
ssh campus-a 'mkdir -p ~/campus-db'
scp app/db/user-data.tmpl.yaml app/db/render-user-data.sh app/db/put-secrets.sh campus-a:campus-db/
```

Trên A:

```
cd ~/campus-db && chmod +x *.sh
OS_CLOUD=campus-tv3 ./put-secrets.sh probe          # ⚠️ tao roi xoa object app/_probe-tv3 (khong co secret)
```

Kết quả `OK member ghi/xoa duoc` thì đi tiếp. `403` thì báo TV1 (comment issue #27), dừng ở đây. (TV1 đã kiểm `member` ghi được ngày 08/11, PR #28; lần chạy 08/11 bỏ bước này.)

## 3. Sinh mật khẩu, tạo VM

```
./render-user-data.sh                               # ~/campus-db-secrets/, mode 700/600; "con REPLACE_: 0"
openstack keypair create --public-key ~/.ssh/<khoa .pub cua ban> tv3   # ⚠️ neu buoc 1 chua co; de go loi sau nay
openstack server create --flavor campus.db --image ubuntu-noble-base \
  --port campus-db-port --availability-zone campus-az-a --key-name tv3 \
  --user-data ~/campus-db-secrets/user-data.yaml --wait campus-db      # ⚠️
openstack server add volume campus-db campus-db-data                    # ⚠️
rm ~/campus-db-secrets/user-data.yaml
```

Gắn volume AZ `nova` vào VM AZ `campus-az-a` đã chạy (08/11). Lỗi thì báo TV1, đừng thử tạo volume mới.

## 4. Theo dõi cài đặt (5–10 phút)

```
openstack console log show campus-db | grep -E 'campus-db-(setup|check)'
```

Đạt khi có đủ các dòng sau, không có dòng `FAIL`:

```
campus-db-setup: volume trong, tao ext4
campus-db-check: OK mount /var/lib/postgresql /dev/vdb ext4
campus-db-check: OK postgresql 16.x ... max_connections=50 data=/var/lib/postgresql/16/main
campus-db-check: role shlink connlimit=15 db_shlink=1
campus-db-check: listen 0.0.0.0:5432 0.0.0.0:6379 ...
campus-db-check: OK redis v=7.0.x PING=PONG
campus-db-check: OK redis khong mat khau bi tu choi
campus-db-check: OK chan metadata cho non-root
```

Treo ở `cho volume` → chưa chạy `server add volume`. Không có dòng nào sau 15 phút → xem toàn bộ console log, tìm lỗi apt/cloud-init.

## 5. Ghi secret vào Swift

```
OS_CLOUD=campus-tv3 ./put-secrets.sh                # ⚠️ ghi app/db_password, app/redis_servers; "etag khop"
```

Kiểm tên object (không in nội dung): `openstack object list campus-secrets --prefix app/`.

## 6. Kiểm (chỉ đọc, trừ reboot)

```
openstack --os-compute-api-version 2.3 server show campus-db -c OS-EXT-SRV-ATTR:user_data   # mong doi: khong co truong / rong voi member
openstack server reboot --wait campus-db            # ⚠️ roi xem lai console log nhu buoc 4 (lan boot 2 khong co dong campus-db-setup)
```

Phần "link còn sau reboot" của FR-INF-12 làm sau khi TV2 chạy Shlink trên clone (dòng `short_urls=` trong console phải giữ nguyên số trước/sau reboot).

Console log của Nova chỉ giữ lần boot gần nhất: chép output lần boot đầu vào evidence trước khi reboot.

Thử thiếu mount (FR-INF-12), làm khi chưa có dữ liệu thật hoặc báo nhóm trước (đã làm 08/11, VM boot chậm khoảng 30 s do `x-systemd.device-timeout`):

```
openstack server stop campus-db && openstack server remove volume campus-db campus-db-data   # ⚠️
openstack server start campus-db                    # console: "FAIL chua mount", "FAIL postgresql@16-main khong chay"
openstack server stop campus-db && openstack server add volume campus-db campus-db-data && openstack server start campus-db   # ⚠️ ve lai OK
```

## 7. Dọn và bàn giao

- Sau bước 5 đạt: `rm -rf ~/campus-db-secrets` trên A (bản gốc nằm trong Swift; DB VM có bản riêng ở `/root/campus-secrets`, mode 600).
- Evidence (đã che): output bước 1, `probe`, dòng `campus-db-*` của console log, `put-secrets.sh`, `object list` → `evidence/G3/<yyyymmdd>-FR-INF-12-db-vm.txt`.
- Ghi trạng thái thực tế vào H1 (mục mới về DB VM) và `docs/inventory.yaml` (`campus-db` UUID, volume đã gắn: nhờ TV1 vì CODEOWNERS), comment issue #27.
- TV2 kiểm từ VM app: `/rest/health` 200 với DB thật, `redis-probe.sh` ra `PONG`.

## 8. Volume đã có dữ liệu PostgreSQL

`campus-db-setup` dừng với `FAIL volume da co du lieu PostgreSQL` khi VM mới gặp volume cũ (ví dụ tạo lại VM). Script không format, không cài đè. Không xóa dữ liệu; hỏi nhóm, rồi làm tay: cài gói với `create_main_cluster = false` trong `/etc/postgresql-common/createcluster.conf`, dựng lại cấu hình `/etc/postgresql/16/main` trỏ vào dữ liệu cũ. Chưa thử.
