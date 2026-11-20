# Lời thoại video: phân đoạn 3 (storage) và 4 (CSDL) – TV3

> #79, T3-6. Mỗi phân đoạn khoảng 50 giây (#74). TV3 vắng buổi quay 21/11 19:30–22:30, nên viết để **TV1 thao tác trên host A**, người đọc là TV1, hoặc TV3 thu lời sau.
> Mọi lệnh đã chạy thử trên A ngày 20/11 bằng credential member (`OS_CLOUD=campus-tv3`). TV1 dùng credential của mình, kết quả tương tự.
> **Che khi quay:** không in IP (lệnh dưới đã thay IP bằng `<ip>` hoặc ẩn trong biến), không in token, không mở `openrc` hay `clouds.yaml`, che ô Owner/Account ID nếu mở Console.
> Trước khi quay: cụm bật **ít nhất 20 phút** để timer backup đã tạo dump sau boot.

## Phân đoạn 3: Hai loại storage (khoảng 50 s)

| # | Thao tác (terminal trên A) | Lời thoại |
| --- | --- | --- |
| 1 | `openstack volume show campus-db-data -f value -c status -c size -c availability_zone` → `in-use`, `10` | "Loại thứ nhất là **block storage** Cinder, tương đương EBS. Dữ liệu PostgreSQL nằm trên volume 10 GiB này, tách khỏi vòng đời VM: dựng lại VM thì gắn lại volume, dữ liệu vẫn còn." |
| 2 | `openstack server show campus-db -f value -c status -c addresses \| sed -E 's/[0-9]+(\.[0-9]+){3}/<ip>/g'` | "Volume đang gắn vào DB VM. VM này không có IP công khai." |
| 3 | `SW=$(openstack catalog show object-store -f json \| jq -r '.endpoints[] \| select(.interface=="public") \| .url' \| head -1); P=$(openstack token issue -f value -c project_id)` rồi `curl -s -o /dev/null -w '%{http_code}\n' "${SW%%AUTH_*}AUTH_$P/campus-backups"` → **401** | "Loại thứ hai là **object storage** Swift, tương đương S3. Container backup là private: gọi không có token thì bị từ chối 401, không phải timeout." |
| 4 | `n=$(openstack object list campus-backups --prefix db/shlink- -f value \| grep '\.dump$' \| sort \| tail -1); d=$(mktemp -d); openstack object save --file $d/x.dump campus-backups $n; openstack object save --file $d/x.sha campus-backups $n.sha256; echo "Swift: $(cut -c1-16 $d/x.sha)  tinh lai: $(sha256sum $d/x.dump \| cut -c1-16)"; rm -rf $d` → hai giá trị trùng nhau | "Có token thì tải được bản dump mới nhất. Checksum tính lại trùng với checksum lưu kèm trong Swift, nên bản backup còn nguyên vẹn." |
| 5 | (không gõ) | "Chọn Cinder cho dữ liệu cần ghi nhanh và bền theo VM; chọn Swift cho backup và file, vì truy cập qua HTTP có quyền theo token và có checksum." |

## Phân đoạn 4: Cơ sở dữ liệu (khoảng 50 s)

| # | Thao tác | Lời thoại |
| --- | --- | --- |
| 1 | Mở `evidence/G3/20261118-FR-APP-01-12-h1-smoke-cum.txt`, cuộn tới khối `== redirect, sua, nhat quan 2 replica` (dòng `NFR-12 GET qua B sau PATCH o A`) | "Cả hai app VM dùng chung một PostgreSQL 16 và một Redis trên DB VM. Smoke trên cụm 18/11: sửa link qua app A, đọc qua app B thấy đích mới ngay." (Gọi thẳng từng app chỉ làm được từ trong mạng ảo nên dùng kết quả đã chạy; muốn làm trực tiếp phải dựng VM nhảy, mất thêm vài phút.) |
| 2 | `cat app/db/backup/campus-db-backup.timer` (trong repo trên laptop, hoặc `git show main:app/db/backup/campus-db-backup.timer`) | "Backup chạy bằng systemd timer: 10 phút sau khi boot rồi mỗi giờ. Vì vậy dữ liệu mất tối đa khoảng 1 giờ." |
| 3 | `openstack object list campus-backups --prefix db/shlink- --long -f value -c Name -c Bytes -c "Last Modified" \| grep '\.dump ' \| tail -3` | "Đây là các bản dump trong Swift: một bản ngay khi boot, một bản sau 10 phút, rồi theo giờ. Giữ 48 bản." |
| 4 | Mở `evidence/G3/20261116-FR-INF-16-H5-fixture-restore-cum.txt`, chỉ các dòng `OK slug tv4fix…` và `PASS restore` | "Restore thử vào một DB tách riêng, không bao giờ vào DB thật. Script so migration, số bản ghi và 5 link chuẩn, rồi xóa DB thử." |
| 5 | Mở `evidence/G5/20261120-FR-INF-25-tang-3-thay-the-local.txt`, mục 5 | "Khôi phục từ bản dump về máy nhóm vào một môi trường mới: dịch vụ chạy lại sau 18 giây, smoke 27 PASS." |

Nếu thừa thời gian trong phân đoạn 4, có thể bỏ bước 5 vì bảng RPO/RTO nằm trong báo cáo.

## Cảnh thêm (tùy chọn): portal trên Compose

Không cần cụm, TV3 tự quay trên máy mình và gửi file trước 22/11 12:00 nếu nhóm muốn:

```
cd app/compose && ./gen-portal-secrets.sh && docker compose --profile portal up -d --build --wait
# Mở http://127.0.0.1:18090 → đăng nhập admin → tạo chiến dịch → phát hành thẻ QR 1 lô (PDF) → đăng nhập đơn vị B không thấy chiến dịch của A
```

Lời thoại: "Portal là phần mở rộng nhóm tự viết: mỗi đơn vị có API key Shlink riêng, chỉ thấy link của mình. Theo điều kiện lùi đã chốt, portal dừng ở bản chạy trên Compose."
