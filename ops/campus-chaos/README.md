# campus-chaos v0 (FR-INF-24)

Dịch vụ thí nghiệm lỗi có kiểm soát cho app VM của nhóm (SRS 1.4, ADR-11). Chạy trên host A bằng Python 3 và thư viện chuẩn, gọi CLI `openstack`.

**Trạng thái (12/11/2026):** v0, **chưa chạy trên cụm**. Logic (xác thực, rào an toàn, dừng sớm, hoàn tác, phân tích số liệu) đã có 18 test chạy không cần cụm. Ba lệnh gây lỗi và hoàn tác (`server stop/start`, `loadbalancer member set --disable/--enable`, `port set --disable/--enable`) đã chạy thật bằng `member` trong `chaos-lab.sh` (evidence `evidence/G3/20261112-FR-INF-24-O-20-chaos-lab-hanh-dong-loi-bang-member.txt`). **Chưa kiểm trên cụm:** dạng cột `properties` của `server show -f json`, `object create --name` lên Swift `campus-reports`, và việc đọc kịch bản `.yaml` (cần PyYAML; dùng `.json` nếu thiếu).

## Rào an toàn

- Chỉ nhận đích có metadata `campus_role=app`. DB VM, host và mọi VM khác bị từ chối trước khi làm gì.
- Mỗi lúc một thí nghiệm: file `state.json` được ghi **trước** khi gây lỗi; còn file thì từ chối chạy tiếp.
- `duration_s` từ 1 đến 300; hành động chỉ là một trong `vm-stop`, `member-disable`, `port-disable`.
- Dừng sớm và hoàn tác ngay khi tỉ lệ lỗi trong cửa sổ vượt ngưỡng hoặc không còn member `ONLINE`.
- Luôn hoàn tác trong `finally`, kể cả khi có ngoại lệ hoặc lệnh gây lỗi thất bại. Hoàn tác thất bại thì **giữ** `state.json` để `revert` thử lại.
- Kiểm "đã hoàn tác" bằng lưu lượng thật (đích trả lời lại) chứ không chỉ `operating_status`: ở thí nghiệm O-20, lưu lượng quay lại trước khi trạng thái LB về `ONLINE` (0,3–5,6 s).

## Cách dùng

Chép `campus_chaos.py` và một kịch bản (từ `scenarios/*.example.yaml`) lên A. Tạm thời chạy bằng quyền `member` của TV2 (chưa có credential riêng cho `campus-chaos`):

```
sudo -u tv2 -H env CHAOS_CLOUD=campus-tv2 CHAOS_STATE_DIR=/tmp/campus-chaos \
  python3 /tmp/campus_chaos.py run /tmp/kich-ban.yaml --dry-run     # kiểm và in kế hoạch, không gây lỗi
sudo -u tv2 -H env CHAOS_CLOUD=campus-tv2 CHAOS_STATE_DIR=/tmp/campus-chaos \
  python3 /tmp/campus_chaos.py run /tmp/kich-ban.yaml
```

Nếu tiến trình bị ngắt: `campus_chaos.py revert` (đọc `state.json`) rồi `status`. Báo cáo JSON nằm ở `<state-dir>/reports/` và được đưa lên Swift `campus-reports` (`chaos/<giờ>-<tên>.json`); đưa lên thất bại chỉ cảnh báo.

## Đối chiếu FR-INF-24

| Yêu cầu | v0 |
| --- | --- |
| Nhận kịch bản | Có (`.yaml` hoặc `.json`) |
| Gây đúng một lỗi: tắt VM, tắt member LB, tắt port | Có |
| Dừng sớm khi tỉ lệ lỗi vượt ngưỡng hoặc hết member `ONLINE` | Có |
| Tự hoàn tác sau thời lượng (tối đa 300 s) | Có |
| Báo cáo vào Swift `campus-reports` | Có, **chưa kiểm** |
| Chỉ nhận đích `campus_role=app`; mỗi lúc một thí nghiệm | Có |
| Application credential có access rules, không dùng admin | **Chưa**: tạm dùng user `member` |

## Chưa làm

- Credential riêng `campus-chaos` với access rules (phần còn lại của O-20) và thử trên stack thật của TV2.
- Tự ghi số đo NFR-21 và kết luận giả thuyết NFR-01/02; SLI từ log Nginx (NFR-22). Log `$request_time` đã bật trên A ngày 12/11 (`/var/log/nginx/campus-rt.log`).
- Kịch bản nhiều bước; probe từ nhiều nguồn.
