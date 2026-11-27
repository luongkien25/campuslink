# Script để từng thành viên tự tập demo CampusLink

**Chốt kịch bản phần mình trước trong [issue 104](https://github.com/luongkien25/campuslink/issues/104), sau đó mới tự thử và gửi kết quả.** Mỗi người dùng laptop riêng tối nay. Khi bảo vệ dùng một laptop chung, đến phần ai thì người đó tự bấm và tự nói. [Kịch bản chung](kich-ban-demo-bao-ve-10-phut.md) là khung ghép các phần.

## Lấy bản script trên laptop

PR 103 chưa merge thì clone riêng nhánh demo để không ảnh hưởng nhánh đang làm:

```powershell
git clone --branch tv1/kich-ban-demo-bao-ve-20261127 --single-branch https://github.com/luongkien25/campuslink.git campuslink-demo
Set-Location campuslink-demo
.\ops\demo\demo-laptop.ps1 help
```

Nếu đã clone thư mục demo này, cập nhật bằng `git pull --ff-only` trong chính thư mục đó. Khi PR đã merge, dùng main mới nhất theo quy trình nhóm.

Script laptop suy ra repo từ vị trí file, không buộc dùng ổ D. Chạy trong Windows PowerShell 5.1 hoặc mới hơn, có `curl.exe`. Nếu PowerShell đang chặn `.ps1`, mở một phiên riêng bằng lệnh dưới; tùy chọn chỉ áp dụng phiên đó, không đổi policy hệ thống:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass
```

Trong thư mục repo:

```powershell
.\ops\demo\demo-laptop.ps1 pre
.\ops\demo\demo-laptop.ps1 app <slug-mau>
.\ops\demo\demo-laptop.ps1 failover <slug-mau> 90
.\ops\demo\demo-laptop.ps1 hm8
```

Thay `<slug-mau>` bằng mã thật, không chép nguyên dấu ngoặc. `pre` kiểm HTTPS Shlink, Web Client và portal health; `app` thêm redirect 302/API thiếu key 401. `failover` quan sát trong khung thời gian bằng request HTTPS, bất kỳ mẫu lỗi nào đều trả mã lỗi và được in ra. `hm8` đọc các dòng chi phí gần nhất và chỉ vị trí ảnh có ngày; không coi chúng là bảng actual đã hoàn chỉnh. TV4 đối chiếu trước khi nói. Tham số `-Domain` và `-RepoRoot` dùng khi cần đổi domain/vị trí repo.

## Lệnh cloud theo từng tài khoản

Sau khi TV1 đã cài bộ dùng chung vào Host A:

```powershell
ssh tv2@campus-a
```

Thay `tv2` bằng tài khoản của mình. Alias SSH `campus-a` và key phải được cấu hình sẵn theo CONTRIBUTING. Trong SSH:

```bash
alias d='bash /opt/campuslink-demo/demo-host-a.sh'
d help
```

| Người | Thao tác tự thử sau khi chốt kịch bản | Ghi chú |
| --- | --- | --- |
| TV1, user `ubuntu` | `d hm1`, `d hm2`, `d hm5`; kiểm nền và giữ phiên | Các lệnh admin chỉ dùng quyền sẵn có của TV1; không chia quyền này cho thành viên |
| TV2, user `tv2` | `d pre`, `d lb`, `d hm7`, `d watch 10`; alarm/load/failover theo lượt riêng | Dùng `OS_CLOUD=campus-tv2`, không mượn credential TV1 |
| TV3, user `tv3` | `d hm34`; portal trên trình duyệt; script laptop `pre` | Volume/Swift dùng `campus-tv3`; dữ liệu mẫu và GUI do TV3 tự chuẩn bị |
| TV4, user `tv4` nếu cần SSH | Script laptop `pre`, `app`, `failover`, `hm8`; video/evidence | Read-only API còn tùy policy; quyền bị từ chối phải báo lại, không đổi role để tập |

TV2 đăng ký lượt tải/failover, không chạy chồng với người khác:

```bash
d pre
d alarm-on /duong/dan/env-private-da-xac-nhan
d load-start <slug-moi> 420
d watch 10
# Ctrl+C chi thoat monitor, chua dung tai
d load-stop
d hm7
d alarm-off
# Chi tiep tuc khi alarm da tat va action trong
d fail-stop
d fail-start
d cleanup
```

Đây là trình tự để chủ phần chốt, không phải lệnh chạy toàn bộ ngay sau khi clone. File env riêng giữ mode 600, không tải lên repo/issue. ID tài nguyên mặc định lấy từ inventory hiện có, TV2 phải đối chiếu trước khi đổi trạng thái. Nếu còn 3 member, đưa về baseline theo quy trình Heat đã thống nhất rồi kiểm lại; `cleanup` chỉ kiểm, không tự scale-in/tắt alarm/bật VM.

`load-start` và `load-stop` phải dùng cùng user. Tải chạy trên Host A, log/PID riêng tại `~/.local/state/campus-demo/`; không tự dừng tiến trình của người khác. Giữ log làm bằng chứng. Không phát tải vào fixture cũ `tv4fix1`.

## Cài bộ dùng chung khi cloud bật

**Trạng thái lúc chuẩn bị:** cụm đang tắt theo TV1, chưa cài/kiểm quyền thực tế trên Host A. Cần bật theo runbook trước khi SCP; việc cài dưới đây chỉ thêm file, không bật alarm, phát tải hoặc dừng VM.

TV1 thực hiện từ repo trên laptop:

```powershell
ssh campus-a 'mkdir -p ~/campus-demo-stage-20261127'
scp .\ops\demo\demo-host-a.sh .\ops\demo\demo-json.py .\ops\demo\install-demo.sh campus-a:~/campus-demo-stage-20261127/
ssh campus-a 'sudo bash ~/campus-demo-stage-20261127/install-demo.sh'
```

Installer chỉ chép hai file vào `/opt/campuslink-demo`, root sở hữu, thành viên đọc được; không sửa sudoers, OpenStack role, credential, dịch vụ hoặc stack. Nó kiểm các user đọc được file và in SHA256 để đối chiếu. Sau cài, TV1 kiểm `d help` bằng tài khoản thành viên; từng người kiểm API phần mình sau khi chốt kịch bản và đăng ký lượt.

Hôm bảo vệ, TV1 mở trước cửa sổ SSH `ubuntu`, `tv2`, `tv3` bằng quyền đã có. Từ phiên quản trị có thể dùng `sudo -iu tv2`/`sudo -iu tv3` để chuẩn bị đúng tài khoản, đặt alias `d` trong từng phiên; không sao chép private key hay mật khẩu lên máy chung. Thành viên tiếp quản đúng cửa sổ khi đến phần mình.

## Kiểm thử offline và giới hạn

```powershell
python -I tests/demo/test_demo_host.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/demo/test_demo_laptop.ps1
```

Các test dùng dữ liệu/CLI giả: đọc JSON LB, không lộ action URL, chặn failover khi trạng thái alarm chưa rõ, dùng đúng tài khoản, so toàn bộ SHA256, mã HTTP/exit code, đường dẫn portable và thời gian quan sát failover. Không kiểm credential, API policy hay autoscaling thật. Trạng thái thực tế phải do từng chủ phần báo sau lượt tự tập.

Tham khảo cú pháp CLI: [Octavia 2026.1](https://docs.openstack.org/python-octaviaclient/2026.1/cli/index.html) cho `loadbalancer status show` vốn trả JSON, [Heat stack event](https://docs.openstack.org/python-heatclient/2026.2/cli/stack.html) cho giới hạn số event. Đối chiếu `--help` của bản cài trên cụm khi gặp khác biệt.
