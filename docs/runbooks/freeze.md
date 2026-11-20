# Runbook freeze 19–22/11/2026 (TV1 chốt)

Nguồn: SRS 6.3 (Freeze, 19/11), ADR-07, `infra/aws/README.md` (SG `campus-ingress-admin`), `start-stop.md` mục 6. Soạn 14/11/2026. **Lần chạy thực tế đầu tiên: tối 19/11/2026** (thêm hai rule SSH `/32` của TV1 và TV2, xóa rule 22 `0.0.0.0/0`, SSH mới của TV1 và TV2 với `ControlMaster=no`, quét ngoài do TV4 chạy từ mạng khác); giờ chính xác và **trạng thái SG sau lần chạy đó** ghi ở issue #4 (nhật ký cloud), không ghi lại ở đây để khỏi lệch. Lệnh có nhãn **[THAY ĐỔI]** chỉ TV1 chạy.

**Hai khoảng ngày khác nhau trong file này:** **19–22/11** là freeze của SRS 6.3 (diễn tập, video, kiểm 8 tiêu chí, thu SSH về `/32`), nộp 23/11; **19–29/11** (mục 5) là khoảng **giữ hạn chế vận hành** kéo dài tới trước buổi bảo vệ 30/11.

## 0. Trước 19/11 (không cần cloud)

1. Mỗi thành viên cần SSH gửi TV1 qua Zalo (không ghi vào repo hay issue: IP nhà là thông tin cá nhân) IP công khai hiện tại: `curl.exe -s https://checkip.amazonaws.com`. Ghi rõ mạng gì (nhà, trường, 4G). IP 4G đổi liên tục: không dùng được với /32.
2. Thành viên **không** tự sửa SG được (IAM `iam-member-startstop.json` chỉ Start/Stop). Đổi IP thì báo TV1, TV1 thêm rule mới rồi xóa rule cũ (mục 2).
3. Ngày bảo vệ 30/11: demo đi qua 443, không cần SSH. Nếu cần SSH lúc demo (bật tải, `campus-chaos`), sáng 30/11 TV1 thêm IP mạng đang dùng ở trường hoặc dùng một điểm phát cố định đã thêm trước.

## 1. Snapshot tay trước khi đổi gì

Theo `start-stop.md` mục 6: tắt B rồi A, *Create snapshot* theo Instance, tag `Name=freeze-<yyyymmdd>`. Snapshot tay không bị DLM xoay vòng (DLM chỉ giữ 3 bản của nó).

## 2. Thu cổng 22 về /32 (ADR-07)

Chạy từ máy TV1 có AWS CLI (`--region us-east-1`) hoặc làm tương đương trên Console. **Thêm /32 trước, xóa 0.0.0.0/0 sau**, để không tự khóa mình.

```bash
# Chỉ đọc: liệt kê rule vào hiện có, lấy ID rule 22 0.0.0.0/0 (README ghi sgr-08ba369199877dc42 từ 27/10, kiểm lại)
aws ec2 describe-security-group-rules --region us-east-1 --filters Name=group-id,Values=sg-0bf8503bfeee5a3c0 --query "SecurityGroupRules[?!IsEgress].[SecurityGroupRuleId,IpProtocol,FromPort,CidrIpv4,Description]" --output table
```

```bash
# [THAY ĐỔI] lặp cho từng người; Description không chứa IP, chỉ tv1..tv4 + nơi
aws ec2 authorize-security-group-ingress --region us-east-1 --group-id sg-0bf8503bfeee5a3c0 --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=<IP>/32,Description=tv1-nha}]"
```

**Trước khi xóa rule mở, việc `ssh` thành công không chứng minh rule /32 đúng**, vì `0.0.0.0/0` vẫn cho vào (review TV2, PR #46). Đối chiếu bằng hai việc: (a) trên đúng máy và mạng đang dùng, chạy `curl.exe -s https://checkip.amazonaws.com` rồi so với `<IP>/32` vừa thêm (khác nhau nghĩa là rule sai hoặc mạng đã đổi); (b) chạy lại lệnh `describe` ở trên, thấy rule /32 mới với Description đúng. Mở sẵn AWS Console (SG `campus-ingress-admin`) để khôi phục. Chỉ khi **cả hai khớp, cho ít nhất TV1**, mới xóa rule mở:

```bash
# [THAY ĐỔI]
aws ec2 revoke-security-group-ingress --region us-east-1 --group-id sg-0bf8503bfeee5a3c0 --security-group-rule-ids <sgr-id-cua-rule-22-0.0.0.0/0>
```

Kiểm lại bằng lệnh `describe` ở trên: không còn dòng `22 … 0.0.0.0/0`; `443 0.0.0.0/0` vẫn còn; **không có** rule cổng 80.

**Sau khi xóa, bắt buộc mở kết nối SSH mới** từ máy TV1 và từng người có rule /32: không dùng phiên SSH đang mở và không dùng ControlMaster/ControlPath cũ, ví dụ `ssh -o ControlMaster=no -o ControlPath=none campus-a hostname`. Chỉ khi kết nối mới thành công mới coi là xong; phiên đang mở hoặc lệnh `describe` không thay được phép kiểm này.

Lỡ tự khóa: Console AWS vẫn sửa SG được (không đi qua SSH): thêm lại rule cổng 22 từ `0.0.0.0/0` hoặc sửa rule /32 trên Console, rồi tìm nguyên nhân. Không tắt fail2ban, không đổi `sshd`.

## 3. Quét lại từ ngoài (FR-INF-05)

Từ một mạng **không** nằm trong danh sách /32 (ví dụ 4G), PowerShell:

```powershell
22,80,443,5432,6379,8080,8774,9696 | % { "{0} {1}" -f $_, (Test-NetConnection 44.198.215.187 -Port $_ -WarningAction SilentlyContinue).TcpTestSucceeded }
```

PASS: chỉ `443 True`, còn lại `False`. Từ mạng có trong /32: thêm `22 True`. Đồng thời chạy `after-start.md` 1.10, 1.11 từ laptop (đi đường ngoài, không `--resolve` trên A).

## 4. Evidence

`evidence/G5/<yyyymmdd>-FR-INF-05-ADR-07-thu-ssh-32.txt`: giờ UTC, ai chạy, output `describe` (**che IP**: thay bằng `x.x.x.x/32 (tv1-nha)`), kết quả quét mục 3, giới hạn (quét từ mạng nào). Ảnh Console SG phải che account ID.

## 5. Giữ hạn chế vận hành (19–29/11, tới trước bảo vệ 30/11)

- Không nâng phiên bản, không `stack.sh`, không đổi `local.conf`, không tạo lại Heat stack `campus-app` (tạo lại thì FIP của VIP đổi và `s.` trả 502: xem `after-start.md` 2.6b).
- Chỉ sửa lỗi chặn demo; mỗi lần sửa ghi issue #4 (giờ UTC, việc, ai).
- Giữ EIP tới 30/11; không mở cổng 80 (cert `campus` hết hạn 05/02/2027, không cần gia hạn).
