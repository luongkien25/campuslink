# Hướng dẫn: tạo SSH key và gửi cho TV1

Dành cho TV2, TV3, TV4. Làm một lần, mất khoảng 5 phút. Kết quả: TV1 thêm key của bạn vào máy A, bạn đăng nhập bằng user riêng (`tv2`, `tv3` hoặc `tv4`) mà không cần mật khẩu máy chủ.

## Cần nhớ trước khi làm

- Mỗi người có **một cặp key riêng**. Không dùng chung key của người khác, không dùng chung file `.pem` của TV1.
- Cặp key gồm hai file:
  - **Private key** (không có đuôi, ví dụ `campuslink_tv2`): **không bao giờ gửi cho ai**, kể cả TV1.
  - **Public key** (đuôi `.pub`, ví dụ `campuslink_tv2.pub`): đây là file **duy nhất** bạn gửi cho TV1. Public key không phải bí mật.
- **Passphrase** là mật khẩu bảo vệ private key. Bạn **tự đặt** lúc tạo key. Nó chỉ nằm trên máy bạn và trong đầu bạn:
  - Không gửi passphrase cho TV1 hay ai khác, không ghi vào nhóm chat, issue hay repo.
  - TV1 không đọc được và không đặt lại được. Quên passphrase thì phải tạo key mới và gửi lại `.pub`.
  - Nên đặt (đừng để trống): máy bị mất hoặc bị xem trộm thì kẻ lấy được file key vẫn chưa dùng được. Dài từ 12 ký tự, dễ nhớ với bạn.
- Khi gõ passphrase, màn hình **không hiện gì** (kể cả dấu `*`). Đó là bình thường, cứ gõ rồi Enter.

Thay `tv2` bên dưới bằng user của bạn: `tv2`, `tv3` hoặc `tv4`.

## Bước 1. Kiểm tra máy có `ssh-keygen`

**Windows 10/11:** mở **PowerShell** (không cần chạy bằng quyền Administrator).

```powershell
ssh -V
```

Ra dòng bắt đầu bằng `OpenSSH_` là được. Nếu báo không tìm thấy lệnh: Settings → Apps → Optional features → thêm **OpenSSH Client**.

**macOS / Linux:** mở Terminal, gõ `ssh -V`, thường có sẵn.

## Bước 2. Tạo cặp key

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh"
ssh-keygen -t ed25519 -C "tv2-campuslink" -f "$env:USERPROFILE\.ssh\campuslink_tv2"
```

**macOS / Linux:**

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "tv2-campuslink" -f ~/.ssh/campuslink_tv2
```

Máy sẽ hỏi hai lần:

```
Enter passphrase (empty for no passphrase):
Enter same passphrase again:
```

Gõ passphrase của bạn, Enter, gõ lại lần nữa, Enter. Hai lần phải giống nhau.

Nếu máy hỏi `... already exists. Overwrite (y/n)?` nghĩa là bạn đã có file tên đó: bấm **n**, rồi đổi tên sau `-f` thành tên khác (ví dụ `campuslink_tv2b`). Không ghi đè key cũ nếu bạn đang dùng nó cho việc khác.

Xong sẽ in ra dòng `Your public key has been saved in ...campuslink_tv2.pub` và vài dòng vân tay (fingerprint). Bạn có hai file trong thư mục `.ssh`.

## Bước 3. Lấy nội dung public key

**Windows (PowerShell):**

```powershell
Get-Content "$env:USERPROFILE\.ssh\campuslink_tv2.pub"
```

Muốn chép thẳng vào clipboard:

```powershell
Get-Content "$env:USERPROFILE\.ssh\campuslink_tv2.pub" | Set-Clipboard
```

**macOS:** `cat ~/.ssh/campuslink_tv2.pub` hoặc `pbcopy < ~/.ssh/campuslink_tv2.pub`. **Linux:** `cat ~/.ssh/campuslink_tv2.pub`.

Kết quả đúng là **một dòng duy nhất**, dạng:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI................ tv2-campuslink
```

- Bắt đầu bằng `ssh-ed25519`, kết thúc bằng `tv2-campuslink` (phần comment bạn đặt ở `-C`).
- Dài khoảng 100 ký tự, **không bị ngắt xuống dòng** giữa chừng.

## Bước 4. Gửi cho TV1

Gửi **riêng** cho TV1 (nhắn tin riêng hoặc email), bằng một trong hai cách:

1. Dán nguyên dòng ở bước 3 vào tin nhắn, kèm tên user của bạn. Ví dụ:
   ```
   User: tv2
   Key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI................ tv2-campuslink
   ```
2. Hoặc đính kèm file `campuslink_tv2.pub`.

**Không gửi:** file không có đuôi `.pub`, nội dung file nào bắt đầu bằng `-----BEGIN OPENSSH PRIVATE KEY-----`, passphrase, ảnh chụp màn hình có private key.

## Bước 5. Tự kiểm tra trước khi gửi (1 phút)

- [ ] File gửi có đuôi `.pub`, hoặc dòng dán bắt đầu bằng `ssh-ed25519`.
- [ ] Chỉ có **một dòng**, không có `BEGIN` hay `PRIVATE` trong nội dung.
- [ ] Bạn nhớ passphrase vừa đặt (thử `ssh-keygen -y -f` bằng đường dẫn private key: nó hỏi passphrase và in ra public key nếu nhập đúng).

Kiểm passphrase (không bắt buộc, không gửi đi đâu):

```powershell
ssh-keygen -y -f "$env:USERPROFILE\.ssh\campuslink_tv2"
```

Nhập đúng passphrase thì in ra một dòng `ssh-ed25519 ...`. Nhập sai thì báo `incorrect passphrase`.

## Bước 6. Sau khi TV1 báo "đã thêm key"

TV1 sẽ nhắn bạn khi đã thêm key vào máy A. Lúc đó máy có thể đang **tắt** (xem `docs/runbooks/start-stop.md`): TV1 hoặc bạn bật máy theo runbook, và nhớ ghi giờ vào issue "Nhật ký cloud".

Đăng nhập (thay `tv2` bằng user của bạn):

**Windows (PowerShell):**

```powershell
ssh -i "$env:USERPROFILE\.ssh\campuslink_tv2" tv2@44.198.215.187
```

**macOS / Linux:**

```bash
ssh -i ~/.ssh/campuslink_tv2 tv2@44.198.215.187
```

- Lần đầu máy hỏi `Are you sure you want to continue connecting (yes/no/[fingerprint])?`: nếu TV1 đã gửi dấu vân tay của máy thì đối chiếu, khớp thì gõ `yes`.
- Sau đó máy hỏi **passphrase** của bạn (không phải mật khẩu máy chủ). Đó là bình thường: mỗi lần SSH đều hỏi.
- Vào được thì dấu nhắc đổi thành `tv2@campus-a`.

Muốn gõ ngắn hơn, thêm vào file `~/.ssh/config` (Windows: `C:\Users\<tên bạn>\.ssh\config`):

```
Host campus-a
    HostName 44.198.215.187
    User tv2
    IdentityFile ~/.ssh/campuslink_tv2
    IdentitiesOnly yes
```

Rồi dùng `ssh campus-a`.

Tài khoản `tv2`/`tv3`/`tv4` **không có sudo**: bạn xem được log và dùng OpenStack bằng credential Keystone riêng của mình, không đổi được cấu hình máy. Cần quyền cao hơn thì nhờ TV1.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Permission denied (publickey)` | Sai user (đang dùng `ubuntu` thay vì `tv2`); dùng sai file key; TV1 chưa thêm key; key bị dán thành nhiều dòng | Kiểm lệnh có `-i <private key>` và `tv2@...`; hỏi TV1 đã thêm key chưa; gửi lại dòng `.pub` nguyên vẹn |
| `Connection timed out` | Máy A đang tắt, hoặc mạng nhà bạn chặn cổng 22 | Xem issue "Nhật ký cloud", bật máy theo runbook; thử mạng khác |
| `Connection refused` ngay lập tức | Máy A vừa bật chưa xong | Đợi khoảng 2–3 phút (đến khi AWS báo `2/2 checks passed`) |
| `WARNING: UNPROTECTED PRIVATE KEY FILE!` | File private key bị chia sẻ cho người khác đọc | macOS/Linux: `chmod 600 ~/.ssh/campuslink_tv2`. Windows: chuột phải file → Properties → Security, chỉ để user của bạn |
| `incorrect passphrase` / hỏi passphrase hoài | Nhập sai passphrase (lưu ý bàn phím gõ tiếng Việt, Caps Lock) | Gõ lại; quên hẳn thì tạo key mới (bước 2 với tên khác) và gửi lại `.pub` |
| Bị chặn sau nhiều lần sai | `fail2ban` trên A chặn IP của bạn | Nhắn TV1 gỡ chặn, kèm IP công cộng của bạn |

## Bảo mật

- Mất máy hoặc nghi lộ private key: **báo TV1 ngay** để gỡ key của bạn khỏi máy A.
- Cổng 22 của máy A đang mở cho mọi IP đến hết 06/11/2026 (ADR-07), nên key và passphrase là lớp bảo vệ chính.
- Không dán private key, passphrase hay mật khẩu tạm AWS vào nhóm chat, issue GitHub hay repo.
