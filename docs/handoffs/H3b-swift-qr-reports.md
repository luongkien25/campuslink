# H3b – Swift `campus-qr`, `campus-reports` và credential `campus-svc` (TV1 → TV3, TV4)

Ngày (UTC): 2026-11-07 · Gate: mở rộng lên cụm (SRS 6.3, 10–14/11) · Commit: (điền sau khi merge)
**Mới xong phần Swift.** Phần ingress của H3b (cert có `app.`, vhost `app.`) chưa làm, xem mục 4.
Không ghi secret. Secret của credential nằm trong Swift `campus-secrets/app/swift_app_cred` (ADR-10), không qua chat.

## 1. Đã sẵn sàng

| Thứ | Giá trị | Kiểm bằng lệnh (sau `export OS_CLOUD=campus-tv3`, TV4 chỉ chạy được dòng đầu nếu có quyền xem) |
| --- | --- | --- |
| Container | `campus-qr`, `campus-reports`, private, đã tạo 07/11 | `openstack container list -f value` |
| Endpoint Swift | `http://10.11.0.10:8080/v1/AUTH_07af3a3dd4c24d1ba028efcb6d28ef84` | `openstack catalog show object-store` (cần quyền; giá trị cũng ở `inventory.yaml`) |
| Keystone (lấy token) | `http://10.11.0.10/identity` (biến `OS_AUTH_URL`) | — |
| User | `campus-svc`, role `reader` trong `campuslink`; ACL đọc+ghi của **hai container trên**, không container nào khác | — (chỉ TV1 xem được bằng admin) |
| Application credential | tên `campus-svc`, **10 rule** (xem mục 2); secret không ghi ở đây | — |
| File secret | object `campus-secrets/app/swift_app_cred`, 2 dòng: `id=<id credential>` và `secret=<secret>`. VM lấy lúc boot cùng các secret khác (ADR-10, script boot của TV2), mặc định chép thành `/run/secrets/swift_app_cred` | `openstack object show campus-secrets app/swift_app_cred -c name -c content-length` (`member` xem được; `reader` TV4 không) |

Giá trị lâu dài đã chép vào `docs/inventory.yaml`.

## 2. Người nhận làm được gì / không được làm gì

Credential `campus-svc` được phép (đã kiểm 07/11, `evidence/G3/20261107-H3b-campus-svc-access-rules.txt`):

- `GET` và `HEAD` container `campus-qr`, `campus-reports` (liệt kê, kiểm tra tồn tại).
- `PUT` object dưới `campus-qr/**` và `campus-reports/**`, kể cả ghi đè cùng tên; `GET`, `HEAD` object đó. Wildcard `**` đã thử với tên 3 cấp (`campus-qr/probe/v1/lo-1.pdf`) và 2 cấp (`campus-reports/probe/…csv`).

Quy ước tên (SRS 4.6): `campus-qr/<campaign_id>/v<phiên bản>/lo-<n>.pdf`, `campus-qr/<campaign_id>/v<phiên bản>/tong.pdf`, `campus-reports/<campaign_id>/<yyyymmddThhmmZ>.csv`. Tên có ký tự đặc biệt (khoảng trắng, dấu, `%`, `?`) **chưa thử**: dùng ASCII, chữ số, `-`.

Không được (bị Swift từ chối bằng **HTTP 401**, không phải 403):

- `DELETE` object, `POST` (đổi metadata), tạo hoặc xóa container.
- Mọi thao tác trên container khác (`campus-secrets`, `campus-backups`) và trên account.
- Muốn thay object: ghi đè cùng tên. Muốn xóa hẳn: nhờ TV1 (admin).

Lưu ý khi viết code: 401 cũng là lỗi khi token hết hạn. Xử lý: lấy token mới rồi thử lại **một lần**; vẫn 401 thì coi là vượt quyền (sai tên container, sai phương thức), không thử lại mù quáng.

Lấy token (application credential, Keystone v3): `POST $OS_AUTH_URL/v3/auth/tokens` với `{"auth":{"identity":{"methods":["application_credential"],"application_credential":{"id":"<id>","secret":"<secret>"}}}}`; token ở header `X-Subject-Token` của phản hồi, dùng làm `X-Auth-Token` khi gọi Swift. Đã thử từ một VM guest ở host A (ADR-10).

Dung lượng: đĩa loopback của Swift chỉ 5 GiB, dùng chung với `campus-backups` (H3 mục 4). Tính kích thước PDF thẻ và retention báo cáo cho vừa mức này.

## 3. Cách tự kiểm tra (người nhận chạy trên VM app khi có image, đều PASS mới coi là nhận xong)

Chưa chạy được ở thời điểm viết (chưa có VM app thật). Trên VM app sau khi script boot chép secret:

```
. /run/secrets/swift_app_cred          # đặt biến id, secret (file dạng key=value)
AUTH=http://10.11.0.10/identity
SW=http://10.11.0.10:8080/v1/AUTH_07af3a3dd4c24d1ba028efcb6d28ef84
BODY="{\"auth\":{\"identity\":{\"methods\":[\"application_credential\"],\"application_credential\":{\"id\":\"$id\",\"secret\":\"$secret\"}}}}"
TOKEN=$(curl -s -i -X POST "$AUTH/v3/auth/tokens" -H "Content-Type: application/json" -d "$BODY" | grep -i "^x-subject-token:" | cut -d" " -f2 | tr -d "\r")
curl -s -o /dev/null -w "%{http_code}\n" -X PUT -d probe -H "X-Auth-Token: $TOKEN" "$SW/campus-reports/probe/test.csv"   # 201
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Auth-Token: $TOKEN" "$SW/campus-reports/probe/test.csv"                  # 200
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "X-Auth-Token: $TOKEN" "$SW/campus-reports/probe/test.csv"        # 401
```

Không in `$TOKEN`, `$secret` ra log hay chat. Object `probe/test.csv` để lại (không xóa được bằng credential này): báo TV1 xóa.

## 4. Đã biết còn thiếu hoặc lỗi

- **Ingress `app.` chưa làm** (TV1, 10–14/11): cert Let's Encrypt thêm `app.` (mở SG 80 vài phút), vhost `app.` có SSE, thử với backend giả. Đây vẫn là một phần của H3b.
- Đã thử từ VM ở host B (`campus-az-b`) bằng credential tạm có 1 access rule (09/11/2026, `evidence/G3/20261109-ADR-10-vm-o-B-toi-keystone-swift.txt`): token Keystone, `GET` đúng object 200, `PUT`, `DELETE`, object khác và không token đều 401. Chưa thử từ portal/worker thật và bằng credential `campus-svc` thật từ VM ở B.
- Credential `campus-svc` **không đặt hạn** (`--expiration`). Thu hồi (lộ hoặc đổi người): TV1 xóa credential, tạo lại và ghi đè `swift_app_cred`, rồi VM app lấy lại lúc boot (ADR-10 mục 10).
- Định dạng `swift_app_cred` (`id=` và `secret=`) do TV1 chọn vì SRS chỉ ghi "id + secret". TV3 và TV4 chưa viết code đọc nên còn đổi được; muốn đổi thì báo TV1 trước 14/11.
- Access rules chỉ chạy nhờ 2 dòng cấu hình Swift trên A (ADR-10 mục 6, `docs/troubleshooting.md` 07/11).

## 5. Lỗi đã gặp khi làm (đã thêm vào `docs/troubleshooting.md`: có)

- Dán khối lệnh dài vào SSH bị cắt và dính dòng; dùng `scp` + script (xem evidence, mục 0).
- Access rules ra 401 rồi 500 khi chưa sửa cấu hình Swift (đã ghi ở troubleshooting khi làm ADR-10).
