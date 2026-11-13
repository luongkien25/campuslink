# Runbook: backup DB lên Swift và restore thử (FR-INF-15, FR-INF-16, O-19, issue #38)

Người làm: TV3. Đầu vào: H2 mục 4.1 (VM nhảy), H3 (`campus-backups`), H1 mục 10 và `docs/runbooks/db-vm.md` (DB VM).
Không ghi secret vào repo, evidence, issue hay Zalo. Lệnh đánh dấu ⚠️ thay đổi trạng thái dùng chung (AGENTS.md mục 6).

## Thiết kế

| Thứ | Giá trị | Vì sao |
| --- | --- | --- |
| Chạy ở đâu | Trên DB VM `campus-db`, `pg_dump -Fc shlink` bằng user `postgres` (peer auth) | A không có route tới `10.20.0.0/24`; không cần mật khẩu DB |
| Đích | Swift `campus-backups/db/shlink-<UTC>.dump` và `...dump.sha256`; object dump có metadata `X-Object-Meta-Sha256`; PUT kèm `ETag` (md5) để Swift từ chối nếu hỏng đường truyền | FR-INF-15 "có checksum" |
| Quyền | Application credential `campus-db-backup` do `campus-tv3` tạo, hết hạn 31/12/2026, access rules chỉ `PUT/GET/HEAD/DELETE` trên `campus-backups/db/*` và `GET` liệt kê `campus-backups` | O-14: access rules đã chạy trên cụm; không thêm user Keystone |
| Đưa credential vào VM | Qua SSH, VM nhảy tạm (H2 mục 4.1), file `/root/campus-backup/cred` (0600, 2 dòng `id=`, `secret=`) | Không qua user-data nên không cần ngoại lệ NFR-08 mới |
| Chu kỳ (O-19, **chốt 13/11** ở #38) | systemd timer: 10 phút sau boot, rồi mỗi giờ (`RandomizedDelaySec=120`); `Persistent=true` chạy bù lượt lỡ khi máy tắt | RPO ≤ 1 giờ 02 phút khi cụm chạy; lúc cụm tắt không có ghi mới |
| Retention | 48 bản trong Swift (khoảng 2 ngày chạy), 2 bản trên đĩa DB VM | Dump khoảng vài chục KB; Swift 5 GiB (H3 mục 4) |
| Bản ngoài A | `pull-latest.sh` chép bản mới nhất về laptop và kiểm sha256 | FR-INF-15 "1 bản về máy nhóm", NFR-11 |
| Restore | `campus-db-restore-test`: tải dump, kiểm sha256, `DROP/CREATE campus_restore_test`, `pg_restore --no-owner`; tên DB đích cố định, **không bao giờ** là `shlink` | FR-INF-16, FR-INF-25 tầng 2 |

Script: `app/db/backup/`. Đã thử local (container Ubuntu 24.04 + PostgreSQL 16.15 + Shlink 5.1.8 + Keystone/Swift giả): `evidence/G3/20261112-FR-INF-15-backup-thu-local.txt`. **Đã chạy trên cụm 12/11:** `evidence/G3/20261112-FR-INF-15-16-backup-restore-cum.txt` (access rules thật: 4 thao tác trong `db/` được phép, ngoài `db/` và `campus-secrets` bị 401).

## 0. Trước phiên

Tích Zalo, bật A (B không cần), ghi issue #4, after-start phần 1.

## 1. Kiểm đầu vào (chỉ đọc, trên A)

```
export OS_CLOUD=campus-tv3
openstack server list -c Name -c Status                     # campus-db ACTIVE; chua co campus-jump
openstack console log show campus-db | grep campus-db-check | tail -8
openstack container show campus-backups -c object_count
openstack floating ip list -c "Floating IP Address" -c Port   # con cho cho 1 FIP (quota 3)
openstack application credential create --help | grep -A2 access-rules
openstack image list -c Name | grep -i cirros; openstack flavor list -c Name | grep cirros
```

## 2. Credential (trên A)

```
mkdir -p ~/campus-backup && cd ~/campus-backup        # chep app/db/backup/* vao day bang scp tu laptop
OS_CLOUD=campus-tv3 ./make-backup-cred.sh             # ⚠️ tao credential; ghi ~/campus-backup-cred 0600, khong in secret
```

## 3. VM nhảy và SSH tới DB VM (H2 mục 4.1)

Trên A, ⚠️ cả khối:

```
openstack security group show campus-jump-sg >/dev/null 2>&1 || { openstack security group create campus-jump-sg --description "vm nhay tam"; \
  openstack security group rule create --protocol tcp --dst-port 22 --remote-ip 172.24.4.0/24 --ingress campus-jump-sg; }
openstack server create --flavor cirros256 --image cirros-0.6.3-x86_64-disk --network campus-net --security-group campus-jump-sg \
  --key-name tv3 --availability-zone campus-az-a --wait campus-jump
FIP=$(openstack floating ip create public -f value -c floating_ip_address); openstack server add floating ip campus-jump $FIP; echo $FIP
openstack security group create ssh-from-jump-tv3 --description "ssh tu vm nhay, tam"
openstack security group rule create --protocol tcp --dst-port 22 --remote-group campus-jump-sg --ingress ssh-from-jump-tv3
openstack port set --security-group ssh-from-jump-tv3 campus-db-port
```

Trên laptop, thêm vào `~/.ssh/config` (thay `<FIP>`):

```
Host campus-jump
    HostName <FIP>
    User cirros
    ProxyJump campus-a
    IdentityFile ~/.ssh/campuslink_tv3
    IdentitiesOnly yes
Host campus-db
    HostName 10.20.0.10
    User ubuntu
    ProxyJump campus-jump
    IdentityFile ~/.ssh/campuslink_tv3
    IdentitiesOnly yes
```

Đối chiếu host key lần đầu với console log: `campus-jump` (Cirros) in khóa đầy đủ giữa `BEGIN SSH HOST KEY KEYS` và `END`, chép thẳng vào `~/.ssh/known_hosts`. `campus-db` chỉ in host key ở lần boot đầu (cloud-init `keys_to_console` chạy một lần), nên sau reboot không còn trong console: chấp nhận lần đầu (`StrictHostKeyChecking=accept-new`) vì đường đi nằm trọn sau A. ED25519 của `campus-db`: `SHA256:ADcHyo0E7RMz+FVGzHSD6f1omo4EjuUNlWmmlE8Oixo`.

## 4. Cài và chạy lần đầu

Từ laptop:

```
scp -r app/db/backup campus-db:
ssh campus-a 'cat ~/campus-backup-cred' | ssh campus-db 'cd ~/backup && sudo ./install.sh --cred-stdin'    # ⚠️
ssh campus-db 'sudo systemctl start campus-db-backup.service; sudo journalctl -u campus-db-backup -n 8 --no-pager -o cat'
ssh campus-db 'sudo systemctl enable --now campus-db-backup.timer; systemctl list-timers campus-db-backup.timer --no-pager'   # ⚠️
```

Đạt khi journal có `OK campus-backups/db/shlink-<UTC>.dump etag khop md5, meta sha256 khop` và trên A:

```
openstack object list campus-backups --prefix db/
openstack object show campus-backups db/shlink-<UTC>.dump -c etag -c content-length -c properties
```

## 5. Restore thử và bản ngoài A

```
ssh campus-db 'sudo SLUGS="tv2g4-20261111" campus-db-restore-test latest'   # ⚠️ tao lai DB campus_restore_test
./app/db/backup/pull-latest.sh                                              # laptop: tai ban moi nhat, sha256sum -c
```

Đạt khi `shlink` và `campus_restore_test` cùng `short_urls`, `visits`, `migration` (trừ khi có ghi mới sau lúc dump), slug thử trỏ đúng đích.

Restore ở chỗ khác (ví dụ TV1 trên Compose local), từ file đã kiểm sha256:

```
docker run -d --name pgr -e POSTGRES_PASSWORD=x postgres:16 && sleep 5
docker exec pgr createdb -U postgres campus_restore_test
docker exec -i pgr pg_restore -U postgres --no-owner --no-acl -d campus_restore_test < shlink-<UTC>.dump
docker exec pgr psql -U postgres -d campus_restore_test -Atc 'select count(*) from short_urls'
```

## 6. Dọn (⚠️, trên A)

```
openstack port unset --security-group ssh-from-jump-tv3 campus-db-port
openstack security group delete ssh-from-jump-tv3
openstack server delete --wait campus-jump && openstack floating ip delete $FIP
openstack security group delete campus-jump-sg          # neu khong ai khac dang dung
rm -f ~/campus-backup-cred
```

Kiểm: `openstack port show campus-db-port -c security_group_ids` chỉ còn `campus-db-sg`.

## Vận hành

- Trạng thái lượt gần nhất: `/var/lib/campus-backup/last` trên DB VM (`OK <UTC> <object> <byte> <sha256>` hoặc `FAIL <UTC> <lý do>`).
- Đổi credential (hết hạn 31/12/2026 hoặc nghi lộ): tạo cái mới bằng `make-backup-cred.sh`, ghi lại `/root/campus-backup/cred` qua SSH, xóa cái cũ (`openstack application credential delete`). Credential chỉ ghi/xóa được `campus-backups/db/*`, không đọc được `campus-secrets`.
- Credential `campus-db-backup` thuộc user `campus-tv3` (giữ đến 30/11, TV1 chốt ở #38): đổi role, khóa hoặc xóa `campus-tv3` thì backup hỏng ngay (lượt sau báo `FAIL Keystone tra 401`, xem `/var/lib/campus-backup/last`).
- Giới hạn: credential có quyền `DELETE` trong `db/*` (để chạy retention), và Swift nằm trên chính host A. Bản trong Swift chỉ chống mất DB VM hoặc volume, **không** chống mất host A hay xóa nhầm. Bản về laptop (`pull-latest.sh`) và tầng 3 của FR-INF-25 (S3 Object Lock, O-22) bù phần này.
- Chưa có: DB `campus_portal` (thêm vào dump khi portal có DB, H1b); Redis không backup (cache + hàng đợi, ADR-09).
