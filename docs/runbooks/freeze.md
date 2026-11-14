# Runbook freeze 19–22/11/2026 (TV1 chốt)

Nguồn: SRS 6.3 (Freeze, 19/11), ADR-07, `infra/aws/README.md` (SG `campus-ingress-admin`), `start-stop.md` mục 6. Soạn 14/11/2026, **chưa chạy lần nào** ❓. Lệnh có nhãn **[THAY ĐỔI]** chỉ TV1 chạy.

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

Kiểm: người đó `ssh campus-a hostname` được. Chỉ khi **ít nhất TV1 vào được qua rule /32** mới xóa rule mở:

```bash
# [THAY ĐỔI]
aws ec2 revoke-security-group-ingress --region us-east-1 --group-id sg-0bf8503bfeee5a3c0 --security-group-rule-ids <sgr-id-cua-rule-22-0.0.0.0/0>
```

Kiểm lại bằng lệnh `describe` ở trên: không còn dòng `22 … 0.0.0.0/0`; `443 0.0.0.0/0` vẫn còn; **không có** rule cổng 80.

Lỡ tự khóa: Console AWS vẫn sửa SG được (không đi qua SSH). Không tắt fail2ban, không đổi `sshd`.

## 3. Quét lại từ ngoài (FR-INF-05)

Từ một mạng **không** nằm trong danh sách /32 (ví dụ 4G), PowerShell:

```powershell
22,80,443,5432,6379,8080,8774,9696 | % { "{0} {1}" -f $_, (Test-NetConnection 44.198.215.187 -Port $_ -WarningAction SilentlyContinue).TcpTestSucceeded }
```

PASS: chỉ `443 True`, còn lại `False`. Từ mạng có trong /32: thêm `22 True`. Đồng thời chạy `after-start.md` 1.10, 1.11 từ laptop (đi đường ngoài, không `--resolve` trên A).

## 4. Evidence

`evidence/G5/<yyyymmdd>-FR-INF-05-ADR-07-thu-ssh-32.txt`: giờ UTC, ai chạy, output `describe` (**che IP**: thay bằng `x.x.x.x/32 (tv1-nha)`), kết quả quét mục 3, giới hạn (quét từ mạng nào). Ảnh Console SG phải che account ID.

## 5. Trong freeze (19–29/11)

- Không nâng phiên bản, không `stack.sh`, không đổi `local.conf`, không tạo lại Heat stack `campus-app` (tạo lại thì FIP của VIP đổi và `s.` trả 502: xem `after-start.md` 2.6b).
- Chỉ sửa lỗi chặn demo; mỗi lần sửa ghi issue #4 (giờ UTC, việc, ai).
- Giữ EIP tới 30/11; không mở cổng 80 (cert `campus` hết hạn 05/02/2027, không cần gia hạn).
