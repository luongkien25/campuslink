Chào bạn! Theo quy định phối hợp nhóm trong [AGENTS.md](file:///d:/trg/cloud/prj/campuslink/AGENTS.md) (mục 10.1):

> **Kiểm tra đầu phiên:** Do máy hiện tại chưa có GitHub CLI (`gh`) để tự động kiểm tra hộp yêu cầu giữa các thành viên, và nhánh git hiện tại đang là `tv4/case1-scaling`.
> 👉 **Bạn có phải là TV4 (`toancst`) không?** (Nếu bạn là thành viên khác như TV1, TV2, TV3 thì cho mình biết nhé).
> Bạn có thể xem nhanh các việc người khác đang chờ bạn tại: [Hộp yêu cầu GitHub](https://github.com/luongkien25/campuslink/issues?q=is%3Aopen+label%3Ayeu-cau).

---

### Giải thích cách chạy và làm việc với repo CampusLink

Repo này **không chứa mã nguồn Shlink** và **không phải là ứng dụng web thông thường** để chạy `npm start` hay `python app.py` cục bộ. Đây là **repo hạ tầng và vận hành (IaC / DevOps / Cloud Operations)** để triển khai Shlink v5.1.8 + Shlink Web Client v4.8.1 trên cụm OpenStack DevStack lồng trong 2 máy ảo AWS EC2.

Cách "chạy" repo này được chia thành 2 mức độ:

---

### 1. Chạy & kiểm thử offline trên máy cá nhân (Local Test)

Nếu bạn muốn chạy thử nghiệm các kịch bản kiểm thử, cú pháp template hoặc HTTP stub độc lập (ví dụ bài lab cân bằng tải OVN trong [`infra/heat/lab`](file:///d:/trg/cloud/prj/campuslink/infra/heat/lab/README.md)):

1. **Khởi tạo môi trường Python và chạy unit test:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r infra/heat/lab/tests/requirements.txt
   python -B -m unittest discover -s infra/heat/lab/tests -v
   ```
2. **Chạy thử HTTP backend độc lập:**
   - Khởi động backend stub (Terminal 1):
     ```powershell
     python infra/heat/lab/stub.py --backend app-a --bind 127.0.0.1 --port 8080
     ```
   - Gửi request kiểm tra phân phối tải (Terminal 2):
     ```powershell
     python infra/heat/lab/sample_lb.py http://127.0.0.1:8080/ --expect app-a --requests 5
     ```

---

### 2. Triển khai & vận hành trên Cloud (AWS + OpenStack)

Hệ thống hoàn chỉnh chạy trên 2 máy chủ EC2 ở AWS us-east-1 (Host A: controller/storage/ingress, Host B: compute worker).

Quy trình chuẩn theo [start-stop.md](file:///d:/trg/cloud/prj/campuslink/docs/runbooks/start-stop.md) và [CONTRIBUTING.md](file:///d:/trg/cloud/prj/campuslink/CONTRIBUTING.md):

#### Bước 1: Thiết lập truy cập cá nhân (làm 1 lần)
- Bạn cần gửi SSH public key cho TV1 để tạo Linux user riêng (`tv2`, `tv3` hoặc `tv4`) trên host A.
- Cấu hình file `~/.ssh/config` trên máy cá nhân trỏ tới IP của Host A (`campus-a`).
- TV1 cấp tài khoản Keystone và file `clouds.yaml` đặt tại thư mục `~/.config/openstack/` trên Host A.

#### Bước 2: Bật máy theo phiên (tránh tốn chi phí AWS)
1. Tích bình chọn **"Đang dùng 2 EC2"** trên nhóm Zalo.
2. Đăng nhập AWS Console us-east-1: Bật **Host A trước**, chờ `2/2 checks passed` rồi bật **Host B**.
3. Ghi giờ bật vào issue **"Nhật ký cloud"**.

#### Bước 3: SSH vào cụm và thực thi công việc
- SSH vào host A:
  ```bash
  ssh campus-a
  ```
- Kích hoạt profile OpenStack của bạn:
  ```bash
  export OS_CLOUD=campus-tv4   # hoặc campus-tv1, campus-tv2, campus-tv3
  openstack server list
  ```
- *Lưu ý quan trọng:* **Tuyệt đối không chạy lại `stack.sh`** vì lệnh này sẽ xóa sạch cơ sở dữ liệu, mạng và volume đang có.
- Nếu làm việc dài hạn hoặc đo tải từ laptop: chạy `campus-keepalive 180` trên host A để tránh máy tự tắt sau 60 phút nhàn rỗi.

#### Bước 4: Triển khai theo phân công từng vai trò
- **TV1 (Hạ tầng, Mạng, Nginx):** Quản trị AWS, DevStack, Nginx Ingress :443, cấp cert Let's Encrypt ([`infra/nginx/`](file:///d:/trg/cloud/prj/campuslink/infra/nginx/)).
- **TV2 (Orchestration & Autoscaling):** Tạo và cập nhật Heat stack ([`infra/heat/`](file:///d:/trg/cloud/prj/campuslink/infra/heat/)), kết nối Octavia OVN Load Balancer, Aodh, Gnocchi.
- **TV3 (Ứng dụng & Dữ liệu):** Triển khai PostgreSQL 16 + Redis trên DB VM (10.20.0.10) kèm Cinder Volume, cấu hình Shlink container ([`ops/`](file:///d:/trg/cloud/prj/campuslink/ops/)).
- **TV4 (Kiểm thử & Đánh giá):** Chạy smoke test, đo tải bằng Locust, ghi nhận evidence vào thư mục `evidence/`.

#### Bước 5: Tắt máy sau phiên làm việc
1. Thoát phiên làm việc và kiểm tra an toàn:
   ```bash
   ssh campus-a campus-check
   ```
2. Nếu báo `OK`: Tắt **Host B trước, sau đó tắt Host A** trên AWS Console.
3. Bỏ tích trên bình chọn Zalo và ghi nhận giờ tắt vào issue "Nhật ký cloud".

---

### 3. Luồng truy cập khi dịch vụ đang chạy
Khi toàn bộ hệ thống đã hoạt động:
- **Người dùng rút gọn link:** Truy cập `https://s.<EIP-gạch-ngang>.sslip.io/{code}`
- **Quản trị viên CLB/Trường:** Truy cập Web Client tại `https://admin.<EIP-gạch-ngang>.sslip.io`
- **Luồng xử lý ngầm:** Internet → Nginx Host A (:443 TLS) → FIP nội bộ Octavia OVN LB (:8080) → App VM (A / B) → Database VM (PostgreSQL 16 + Redis).