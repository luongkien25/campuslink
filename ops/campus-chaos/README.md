# campus-chaos v0 (FR-INF-24)

Dịch vụ thí nghiệm lỗi có kiểm soát cho app VM của nhóm (SRS 1.4, ADR-11). Chạy trên host A bằng Python 3 và thư viện chuẩn, gọi CLI `openstack`.

**Trạng thái (13/11/2026):** v0, **đã chạy trên cụm** trên stack lab 2 VM sau LB `ovn` (evidence `evidence/G3/20261113-FR-INF-24-campus-chaos-chay-tren-cum.txt`): rào an toàn, dry-run, 3 thí nghiệm thật (`vm-stop`, `member-disable`, `port-disable`: LB phát hiện 1,4–3,6 s, 0/181 probe lỗi mỗi lần, đích trả lời lại sau 1,4–30,5 s) và một lần thử dừng sớm đều đạt (26 PASS, 0 FAIL). Báo cáo lên Swift `campus-reports` và đọc lại được; kịch bản `.yaml` đọc được (cần PyYAML, A có; dùng `.json` nếu thiếu); dạng cột `properties` của `server show -f json` đọc đúng. Logic có 18 test chạy không cần cụm. Ba lệnh gây lỗi và hoàn tác đã chạy bằng `member` từ 12/11 (`evidence/G3/20261112-FR-INF-24-O-20-chaos-lab-hanh-dong-loi-bang-member.txt`). Cùng ngày đã kiểm: kill -9 tiến trình giữa chừng rồi `campus_chaos.py revert` hoàn tác được (`vm-stop`: đích trả lời lại sau 33,4 s; `member-disable`: 2,9 s), và một lượt `vm-stop` 120 s ở 30 req/s đạt, 0 lỗi (evidence `evidence/G3/20261113-FR-INF-24-kill-giua-chung-revert-chay-120s-30rps.txt`). **Chưa:** credential riêng `campus-chaos`, chạy ở B với k6 như SRS ghi (lần này lab ở AZ-A, probe bằng Python), thử trên stack app thật của TV2, thử ngưỡng tỉ lệ lỗi thật của dừng sớm (13/11 mới thử bằng `online_members_lt: 3` để dừng ngay).

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

## Chạy cả chuỗi trên lab

Bộ lab tự dựng và chạy cả chuỗi nằm ở `lab/`: `chaos-lab.sh` dựng stack 2 VM `campus_role=app` sau LB `ovn`; `chaos-run.sh` chạy kiểm rào an toàn, dry-run, 3 thí nghiệm thật, thử dừng sớm, kiểm báo cáo trên Swift rồi dọn lab. Chép `lab/chaos-lab.sh`, `lab/chaos-run.sh` và `campus_chaos.py` vào **cùng một thư mục** trên A, rồi `sudo bash chaos-run.sh run` (khoảng 6 phút; bị ngắt thì `sudo bash chaos-run.sh down`). `lab/chaos-kill.sh` (cùng thư mục) thử kill -9 giữa chừng rồi `revert` và một lượt 120 s ở 30 req/s (`sudo bash chaos-kill.sh run`, khoảng 6 phút). Chạy bằng quyền `member` `campus-tv2`, không dùng admin. Nếu `down` của `chaos-lab.sh` báo còn 1 tài nguyên (đã gặp 2 lần, nghi xóa LB trễ), chạy lại `sudo bash chaos-lab.sh down` sau khoảng 1 phút.

## Đối chiếu FR-INF-24

| Yêu cầu | v0 |
| --- | --- |
| Nhận kịch bản | Có (`.yaml` hoặc `.json`) |
| Gây đúng một lỗi: tắt VM, tắt member LB, tắt port | Có |
| Dừng sớm khi tỉ lệ lỗi vượt ngưỡng hoặc hết member `ONLINE` | Có |
| Tự hoàn tác sau thời lượng (tối đa 300 s) | Có |
| Báo cáo vào Swift `campus-reports` | Có, đã kiểm trên cụm 13/11 (4 báo cáo, đọc lại được) |
| Chỉ nhận đích `campus_role=app`; mỗi lúc một thí nghiệm | Có, đã kiểm 13/11 (`campus-db` bị từ chối) |
| Kill tiến trình giữa chừng rồi `revert` hoàn tác được | Có, đã kiểm 13/11 (`vm-stop` và `member-disable`) |
| Application credential có access rules, không dùng admin | **Chưa**: tạm dùng user `member` |

## Chưa làm

- Credential riêng `campus-chaos` với access rules (phần còn lại của O-20) và thử trên stack thật của TV2.
- Tự ghi số đo NFR-21 và kết luận giả thuyết NFR-01/02; SLI từ log Nginx (NFR-22). Log `$request_time` đã bật trên A ngày 12/11 (`/var/log/nginx/campus-rt.log`).
- Thử ngưỡng tỉ lệ lỗi thật của dừng sớm (13/11 mới thử bằng `online_members_lt: 3`).
- Kịch bản nhiều bước; probe từ nhiều nguồn.
