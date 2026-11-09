# H3 – Cinder, Swift, volume và port cho DB VM (TV1 → TV3)

Ngày (UTC): 2026-10-25 · Gate: G1 → G2 · Commit: (điền sau khi merge)
Không ghi secret. Mật khẩu Keystone của bạn nằm trong `~/.config/openstack/clouds.yaml` trên A (xem H2).

## 1. Đã sẵn sàng

| Thứ | Giá trị (UUID/IP/tên) | Kiểm bằng lệnh (sau `export OS_CLOUD=campus-tv3`) |
| --- | --- | --- |
| Backend Cinder | `lvmdriver-1`: LVM trên đĩa EBS 30 GiB riêng (VG `stack-volumes-lvmdriver-1`, thin pool khoảng 28,5 GiB), iSCSI `lioadm`, cổng 3260 | `openstack volume type list -c Name` |
| Volume type | `lvmdriver-1` | như trên |
| AZ của volume | `nova` (chỉ có một); AZ của Nova là `campus-az-a`/`campus-az-b` | `openstack availability zone list --volume -c "Zone Name"` |
| Volume DB | `campus-db-data` `f43fbbd2-b85f-4bb1-b403-ba54a2f84189`, 10 GiB, `lvmdriver-1`, `available`, **chưa gắn VM nào** | `openstack volume show campus-db-data -c status -c size -c type` |
| Port DB | `campus-db-port` `7df6ea1d-2e8c-46d5-99b9-e121855d81b5`, IP **10.20.0.10**, chỉ gắn `campus-db-sg` | `openstack port show campus-db-port -c fixed_ips -c security_group_ids` |
| SG DB | `campus-db-sg` `15d5d84d-f71a-4595-a5b2-ac75f818c040`: TCP 5432 và 6379 chỉ từ `campus-app-sg` | `openstack security group rule list --ingress campus-db-sg` |
| Swift endpoint | `http://10.11.0.10:8080/v1/AUTH_07af3a3dd4c24d1ba028efcb6d28ef84` (public, từ A) | `openstack endpoint list --service object-store` (cần quyền admin) hoặc `openstack object store account show` |
| Container | `campus-backups`, private, hiện trống; bạn (`campus-tv3`, `member`) đã tạo, ghi, đọc, xóa object thử được | `openstack container list` |

Giá trị lâu dài đã nằm trong `docs/inventory.yaml` (`storage.*`).

## 2. Người nhận làm được gì / không được làm gì

- Được: tạo DB VM với `--port campus-db-port` (IP cố định 10.20.0.10) và gắn volume `campus-db-data` vào; mount, format, dùng làm thư mục dữ liệu PostgreSQL; upload, đọc, xóa object trong `campus-backups` (FR-INF-15); tạo snapshot volume nếu cần (quota 10).
- Không được (hỏi TV1 trước): đổi `campus-db-sg` hay đổi IP của port; xóa `campus-db-data` hoặc `campus-db-port` khi đã có dữ liệu; tạo volume khiến vượt quota 5 volume/30 GiB (hiện đã dùng 10 GiB); cho container `campus-backups` quyền đọc công khai.

## 3. Cách tự kiểm tra (người nhận chạy trên A, đều PASS mới coi là nhận xong)

```
export OS_CLOUD=campus-tv3
openstack volume show campus-db-data -c status -c size -c type          # available, 10, lvmdriver-1
openstack port show campus-db-port -c fixed_ips -c security_group_ids   # 10.20.0.10, chỉ 15d5d84d-...
openstack container list                                                # có campus-backups
cd /tmp && echo "kiem tra $(date -u +%FT%TZ)" > h3.txt && sha256sum h3.txt
openstack object create campus-backups h3.txt
openstack object save --file h3.dl campus-backups h3.txt && sha256sum h3.dl    # hai checksum phải giống nhau
curl -s -o /dev/null -w '%{http_code}\n' http://10.11.0.10:8080/v1/AUTH_07af3a3dd4c24d1ba028efcb6d28ef84/campus-backups   # 401
openstack object delete campus-backups h3.txt; rm -f h3.txt h3.dl
```

## 4. Đã biết còn thiếu hoặc lỗi

- **Dung lượng Swift rất nhỏ:** đĩa loopback của Swift là 5 GiB (`inventory.yaml`: `storage.swift.loopback_size`). Tính retention của `pg_dump` (FR-INF-15) cho vừa mức này, và mỗi bản chép về máy nhóm không thay được bản trong Swift.
- **Gắn volume AZ `nova` vào VM ở `campus-az-a` chạy được** (TV3 gắn `campus-db-data` vào `campus-db`, 08/11/2026, `evidence/G3/20261108-FR-INF-12-db-vm.txt`; `cross_az_attach` giữ mặc định). Gắn vào VM ở `campus-az-b` cũng chạy được (09/11/2026: volume `in-use`, attachment đúng VM; chưa kiểm `lsblk` trong guest, `evidence/G3/20261109-ADR-10-vm-o-B-toi-keystone-swift.txt`). Nếu gắn lỗi, báo TV1.
- Chưa thử mount thật: `nofail` và `RequiresMountsFor=` cho PostgreSQL trong DB VM là việc của bạn (09 mục G). Tên thiết bị trong guest có thể đổi, dùng UUID của filesystem hoặc `/dev/disk/by-id`.
- Thin pool 28,5 GiB nhỏ hơn quota 30 GiB (cấp phát mỏng). Đừng ghi đầy volume rồi tạo thêm snapshot lớn.
- Chưa thử snapshot hay restore volume. Chưa kiểm Swift với object lớn.
- `campus-db-data` do user `campus-tv3` tạo (vì `volume create` không có `--project`), nên mọi thao tác hằng ngày dùng được `campus-tv3`. `campus-tv2` cũng thấy volume này vì cùng project.
- Swift ghi `operator_roles = Member, admin` (chữ **M** hoa) nhưng role `member` của bạn vẫn dùng được; không cần can thiệp.

## 5. Lỗi đã gặp khi làm (đã thêm vào `docs/troubleshooting.md`? chưa, sẽ thêm cùng PR này)

- `openstack volume create` không có cờ `--project`; tạo bằng shell admin thì volume nằm ở project `admin` và DB VM không gắn được.
- Dán nguyên khối `curl`/`nc` vào Cirros cần `echo -e`; không liên quan DB nhưng nếu tự dựng web thử thì nhớ.
- Sau Stop/Start, `/run/octavia` biến mất và `br-ex` mất IP; đã sửa bền trên A, xem evidence `20261025-FR-INF-19-…` (không ảnh hưởng DB VM).
