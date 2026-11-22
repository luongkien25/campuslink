# Ba câu trả lời bảo vệ ngắn – TV3

> #79, T3-7. Mỗi câu 3–5 dòng, kèm evidence. Số liệu lấy từ evidence trong repo; PR chưa merge ghi kèm số.

## 1. RPO và RTO của từng tầng khôi phục là bao nhiêu?

Backup `pg_dump` lên Swift theo timer mỗi giờ (10 phút sau boot, rồi hourly), nên **RPO ≤ 1 giờ 02 phút** khi cụm chạy (O-19); riêng tầng 1 thì RPO là thời điểm chụp snapshot.
- **Tầng 1** (Cinder snapshot → volume mới → DB VM thử, thử ở cả 2 AZ): **RTO 124–158 s**, ngưỡng ≤ 300 s.
- **Tầng 2** (dump trong Swift → PostgreSQL tạm): phần restore **5,8 s**, dữ liệu nhỏ; ngưỡng ≤ 60 s.
- **Tầng 3 bản thay thế** (dump trên máy nhóm → Compose mới): **18,2 s** với dữ liệu thật (164 nghìn visit), 30 s tính cả bước kéo từ Swift.

Không có S3/Object Lock vì O-22 chưa duyệt.
Evidence: `evidence/G3/20261112-FR-INF-25-tang-1-…txt`, `evidence/G3/20261113-FR-INF-25-tang-2-…txt`, `evidence/G5/20261120-FR-INF-25-tang-3-thay-the-local.txt` (PR #86).

## 2. Vì sao portal chỉ chạy trên Compose?

Nhóm chốt trước một **điều kiện lùi cứng** ở #40: đến 18/11 23:59 mà image portal chưa phát hành có digest và chưa lên cụm ổn định thì demo trên Compose. Lý do là để không làm ảnh hưởng phần lõi (Shlink, LB, scaling) đang đo G5. Đến mốc đó, image đã build từ commit sạch và chạy smoke 31 PASS, nhưng chưa push lên registry. Vì vậy nhóm giữ đúng quyết định đã chốt, không cố đưa lên cụm sát freeze. Trên cụm đã có DB `campus_portal`, secret trong Swift, và quyền ghi `campus-qr`.
Evidence: #40, `evidence/G3/20261114-FR-APP-13-14-16-portal-mvp-compose.txt`, `evidence/G3/20261118-H1b-FR-APP-13-portal-image-build.txt`, SRS 6.3 (PR #73).

## 3. Vì sao DB VM chỉ 1 vCPU, và ảnh hưởng thế nào tới p95?

Quota project là 8 vCPU cho tối đa 3 app VM, DB VM và builder tạm, nên flavor DB chốt **1 vCPU / 2 GiB** (SRS C-06); host lồng trong EC2 cũng giới hạn ngân sách khoảng 70 USD. Ngày 18/11, CPU DB lên **94–96%** cùng lúc p95 phía server tăng lên 596 ms. Kiểm chỉ đọc ngày 20/11 không thấy backup, autovacuum dài hay checkpoint lớn trùng thời điểm đó. Thay vào đó, kiểm thấy **Shlink mở kết nối PostgreSQL mới cho từng request**, khoảng 50 kết nối mỗi giây, mỗi kết nối có TLS và SCRAM. Ngoài ra, theo mã Shlink, mỗi visit còn đếm lại toàn bộ visit của slug: tối 21/11, slug mới tốn khoảng 25 ms CPU DB mỗi visit và đạt 39,54 RPS, còn slug khoảng 124 nghìn visit tốn khoảng 148 ms và chỉ đạt 23,49 RPS (PR #89, #91). Cả hai vẫn là **tương quan, chưa chứng minh nhân quả**. Hướng cải thiện (pgbouncer, giữ kết nối lâu dài, tăng vCPU DB) để sau bản nộp.
Evidence: `evidence/G5/20261120-FR-INF-12-NFR-01-db-vm-cpu-kiem-chi-doc.txt` (PR #84), `evidence/G4/20261121-FR-INF-11-NFR-05-vi-sao-1411-khac-2011.txt` (PR #89), `evidence/G4/20261121-FR-INF-11-tu-scale-aodh-heat-hai-chieu.txt` (PR #91), #76, #44.
