# Lời thoại video: Phân đoạn 8 (Dự toán, Chi phí & Ma trận nghiệm thu) và Câu hỏi bảo vệ – TV4

> **Chủ trì:** TV4 – Cao Song Toàn (`@toancst`) · **Tham chiếu:** #80 (`T4-8`), #74 (khung video ≤ 10 phút, phân đoạn 8 khoảng **50 giây**).
> **Lưu ý bảo mật khi quay (`NFR-08`, `T4-6`):** Phân đoạn 8 quay hoàn toàn trên máy cá nhân với các tệp và ảnh đã che trong repo (`evidence/G0/20261119-FR-INF-21-aws-budgets.png`, `evidence/G0/20261118-FR-INF-21-aws-credits.png`, `cost.csv`, `evidence/G5/20261121-FR-INF-21-NFR-16-aws-pricing-calculator.txt`, `docs/acceptance.md`). **Không cần SSH vào `campus-a` và không mở trực tiếp AWS Console chưa che Account ID.**

---

## 1. Kịch bản thao tác & Lời thoại Phân đoạn 8 (Thời lượng: ~50 giây)

| Mốc giờ | Thao tác trên màn hình | Lời thoại của TV4 (khoảng 115–125 chữ, đọc trong ~50 giây) |
| --- | --- | --- |
| **0:00 – 0:12** | Mở song song 2 ảnh đã che trong repo:<br>1. `evidence/G0/20261119-FR-INF-21-aws-budgets.png`<br>2. `evidence/G0/20261118-FR-INF-21-aws-credits.png` | *"Hạng mục 8 là dự toán và kiểm soát chi phí. Ngay từ Gate 0, nhóm đã đặt 3 ngưỡng cảnh báo AWS Budgets ở mức 30, 50 và 65 đô la. Tài khoản có tổng cộng 140 đô la AWS Credit; tính đến ngày 18–19 tháng 11, chi phí tháng 11 mới dùng 27,34 đô la, số dư credit còn 93,96 đô la và dự báo cuối tháng của AWS là 53,65 đô la, đạt mục tiêu ngân sách dưới 70 đô la."* |
| **0:12 – 0:26** | Chuyển sang tab `cost.csv` (cuộn từ đầu xuống dòng cuối ngày 21/11) và ảnh `20261023-NFR-16-campus-a-idle-timer-active.png` | *"Để tiết kiệm, nhóm chỉ bật 2 EC2 theo phiên và ghi nhật ký từng phiên vào `cost.csv` với tổng thời gian chạy khoảng 37 giờ trên Host A và 27 giờ trên Host B. Cụm có 3 lớp bảo vệ tự động: Shutdown behavior là Stop, systemd timer tự tắt sau 60 phút rảnh và EventBridge Scheduler tắt máy lúc 2 giờ sáng mỗi ngày."* |
| **0:26 – 0:40** | Mở file `evidence/G5/20261121-FR-INF-21-NFR-16-aws-pricing-calculator.txt` (mục 2 & mục 3) hoặc Bảng 2.3 trong `docs/acceptance.md` | *"Theo bảng giá AWS Pricing Calculator tại `us-east-1`, nếu vận hành liên tục 730 giờ mỗi tháng, cụm OpenStack trên 2 EC2 `m7i` tốn 561,01 đô la đã gồm 20% dự phòng. Khi đặt cạnh kiến trúc AWS Managed tương đương gồm ALB, EC2 Auto Scaling, RDS PostgreSQL, ElastiCache và NAT Gateway tốn khoảng 162 đến 193 đô la mỗi tháng, mô hình 2 EC2 đắt hơn khi chạy 24/7 vì phải gánh control plane, nhưng lại rẻ hơn và dễ đóng băng nguyên trạng khi bật tắt theo phiên lab."* |
| **0:40 – 0:50** | Mở `docs/acceptance.md` (bảng 8 hạng mục bắt buộc ở Mục 1 và terminal chạy `python3 -m unittest discover -s tests -v` ra `OK 7 tests`) | *"Toàn bộ bằng chứng của 8 hạng mục bắt buộc và các chỉ số hiệu năng, chịu lỗi, chi phí đều đã được kiểm chứng tự động và tổng hợp đầy đủ trong ma trận nghiệm thu `docs/acceptance.md`."* |

---

## 2. Ba câu hỏi & trả lời bảo vệ cá nhân ngắn gọn – TV4 (`CLO2` & `CLO4`)

### Câu 1: Vì sao `NFR-01` (`p95 redirect ≤ 500 ms` ở ~30 RPS) không đạt khi đo qua Internet, và nhóm đã phân tách nguyên nhân như thế nào?
- Theo đúng định nghĩa SRS, `NFR-01` đo từ máy phát qua Internet (từ Việt Nam tới `us-east-1`), mỗi request mở kết nối HTTPS mới nên `p95` thực tế là **`1.081–1.200 ms`** (16–17/11), không đạt ngưỡng `≤ 500 ms`; nhóm giữ nguyên ngưỡng và báo cáo trung thực.
- Để chẩn đoán, nhóm bật `$request_time` (`rt`) và `$upstream_response_time` (`urt`) trên Nginx Host A (`NFR-22`): ở 10 RPS `p95` phía server chỉ **`74–117 ms`**, ở 30 RPS ngày 16–17/11 là **`238–256 ms`** (trong đó khi scale từ 2 lên 3 app VM ngày 17/11 thì `p95` phía server giảm từ `313 ms` xuống `189 ms`), nhưng ở lượt đối chứng 18/11 là **`596 ms`**.
- Phép đo ramp `ab` nội bộ từ Host A qua VIP ngày 20/11 (PR #88) và kiểm chỉ-đọc DB VM (PR #84) cho thấy thông lượng redirect chạm trần ở **~32,5 RPS** đúng lúc CPU `campus-db` (1 vCPU) đạt **`96–98%`** (tương quan với việc Shlink mở ~50 kết nối PostgreSQL TLS + SCRAM mới mỗi giây).
- **Evidence:** `evidence/G5/20261121-NFR-01-03-tong-hop.txt`, `evidence/G4/20261118-NFR-01-tv1-nginx-request-time-p95.txt` (PR #68), `evidence/G4/20261120-FR-INF-11-ramp-redirect-ab-cpu-gnocchi.txt` (PR #88), `evidence/G5/20261120-FR-INF-12-NFR-01-db-vm-cpu-kiem-chi-doc.txt` (PR #84).

### Câu 2: Khi tắt nóng App VM A để thử chịu lỗi (`FR-INF-20`, `NFR-07`), dịch vụ bị ảnh hưởng ra sao và tiêu tốn bao nhiêu Error Budget (`NFR-22`)?
- Trong lượt đo steady 10 RPS ngày 18/11 (10.200 request), khi dừng Nova VM app A (`10.20.0.195`), Octavia OVN health monitor phát hiện và chuyển member A sang `ERROR` sau **`9,47 giây`**; trong 9,5 giây chuyển tiếp đó chỉ có **1 request bị timeout phía client (`599`)** ở giây `+1,5`.
- Suốt **`301,4 giây`** A tắt, app VM B (`10.20.0.196` ở AZ-B) gánh toàn bộ lưu lượng với **0 HTTP `5xx`** và chỉ **2/3.015 request timeout (`0,066%`)**, tiêu thụ vỏn vẹn **6,63% quỹ lỗi (error budget 1%)** của `NFR-02`.
- Sau khi bật lại A, cả 2 member trở về `ONLINE` sau **`51,00 giây`** với **0 lỗi** trong cửa sổ hồi phục.
- **Evidence:** `evidence/G5/20261118-FR-INF-20-NFR-07-tv2-app-a-failover.txt` (PR #69), `evidence/G4/20261118-FR-INF-20-NFR-07-tv1-failover-analysis.txt` (PR #68).

### Câu 3: So sánh chi phí vận hành CampusLink trên 2 EC2 với kiến trúc AWS Managed tương đương (`NFR-16`)?
- Nếu chạy **24/7 (730 giờ/tháng)**: CampusLink tốn **`561,01 USD/tháng`** ($(0{,}615 \times 730 + 18{,}56) \times 1{,}2$), cao hơn khoảng **2,9–3,5 lần** so với kiến trúc AWS Managed tương đương (`ALB` + 2–3 `t3.small` + `RDS db.t4g.small` + `ElastiCache cache.t4g.small` + `S3` + `NAT Gateway`, khoảng **`162,44–193,24 USD/tháng`**), vì phải thuê 2 máy `m7i` (12 vCPU, 48 GiB RAM) có nested KVM để nuôi toàn bộ control plane của OpenStack.
- Nếu chạy theo **mô hình Lab bật/tắt theo phiên (~40–60 giờ)**: Gom toàn bộ đám mây vào 2 EC2 và dùng `campus-nat` trên Host A giúp nhóm `Stop/Start` nguyên trạng mà không mất phí giữ `ALB`, `NAT Gateway` hay `ElastiCache` 24/7; nhờ đó chi phí thực tế cả học kỳ chỉ khoảng **`51,50 USD`** (dự báo AWS Budgets tháng 11 là `53,65 USD`), nằm gọn trong ngân sách `≤ 70 USD` và được chi trả hoàn toàn bằng `140 USD` AWS Credit.
- **Evidence:** `evidence/G5/20261121-FR-INF-21-NFR-16-aws-pricing-calculator.txt`, `cost.csv`, `evidence/G0/20261118-FR-INF-21-aws-credits.png`, `evidence/G0/20261119-FR-INF-21-aws-budgets.png`.
