# ADR-11: Thêm ba yêu cầu vận hành nâng cao, trong đó có dịch vụ thí nghiệm lỗi tự viết; không bật dịch vụ OpenStack mới

- Ngày: 03/11/2026 · Người quyết: TV1 (Kenn) · Trạng thái: chấp nhận; riêng đề nghị S3 (mục "Đề nghị đổi ràng buộc ngân sách") chờ nhóm duyệt theo `AGENTS.md` mục 7

## Bối cảnh

Giảng viên không nhận xét gì về phần cloud khi duyệt đề tài (SRS O-04); phần cloud của nhóm đã vượt nội dung môn (AWS Academy Cloud Foundations Module 1–7, Lab 1–4 OpenStack). Cái còn thiếu là cách hệ thống thật được vận hành. Nhóm dùng tiêu chí: một giải pháp chỉ tính là "mới" khi cơ chế hoặc khái niệm của nó không có bản tương đương trong phần đã học ở AWS, không phải một dịch vụ khác tên làm cùng việc. Phần mở rộng app (ADR-08) đã chiếm phần lớn sức của TV2–TV4 tới 14/11; freeze bắt đầu 19/11.

## Quyết định

1. Thêm vào SRS bản 1.4:
   - FR-INF-23: chuỗi cung ứng image (CI test, Trivy, SBOM, ký cosign, `cosign verify` trước khi nạp vào Glance image).
   - FR-INF-24: dịch vụ thí nghiệm lỗi `campus-chaos` do nhóm tự viết, chạy trên host A: gây đúng một lỗi có kiểm soát lên app VM (tắt VM, tắt member LB, tắt port), dừng sớm theo điều kiện, tự hoàn tác, ghi báo cáo vào Swift `campus-reports`.
   - FR-INF-25: khôi phục thảm họa 3 tầng có RPO/RTO, bản sao trên S3 có Object Lock.
   - NFR-20–22 (RPO/RTO, số đo tự ghi của thí nghiệm lỗi, SLO).
2. TV1 làm chính; TV4 viết test cho FR-INF-23 và kịch bản cho FR-INF-24, TV3 phối hợp FR-INF-25, TV2 review hành động lên LB member.
3. Mốc cắt: cả ba cắt 14/11 (cập nhật 12/11/2026: mốc 09/11 của FR-INF-23 đã qua khi chưa bắt đầu, giữ 14/11, không dời). Trễ thì FR-INF-25 rút về 2 kịch bản đầu và FR-INF-24 chỉ giữ hành động tắt VM; FR-INF-24 chưa PASS thì làm tay FR-INF-20 như cũ.
4. Không bật thêm dịch vụ OpenStack, không thêm EC2 hay VM thường trực.

## Căn cứ

- Theo tiêu chí trên, FR-INF-23 (chuỗi tin cậy từ mã nguồn tới VM) và FR-INF-24 (thí nghiệm lỗi có giả thuyết, điều kiện dừng, tự hoàn tác) là khái niệm mới; AWS có Signer và FIS nhưng ngoài giáo trình. Chaos engineering có trong ngành từ 2011, nên chỉ mới so với phần đã học. FR-INF-25 tương đương S3/snapshot EBS: không mới nhưng vẫn làm vì cho số đo RPO/RTO.
- `campus-chaos` tự động hóa phép thử FR-INF-20/NFR-07 vốn phải làm tay, nên tải việc tăng ít mà phần đánh giá có số đo lặp lại được; khi demo, giảng viên chọn máy để tắt và xem báo cáo tự sinh.
- Chốt an toàn của `campus-chaos`: chỉ đích có metadata `campus_role=app`, không bao giờ DB VM hay host; mỗi lúc một thí nghiệm; thời lượng tối đa 300 s; trạng thái trước lỗi ghi ra file để `campus-chaos revert` hoàn tác được cả khi tiến trình chết; application credential có access rules, không dùng admin.
- Object Lock chế độ Governance cho phép người có quyền đặc biệt dọn bucket sau khi xong môn; role `CampusLinkBackup` chỉ thêm `s3:PutObject` vào một prefix, guest vẫn không có credential AWS (NFR-09).

## Đề nghị đổi ràng buộc ngân sách (S3), chờ nhóm duyệt (bổ sung 12/11/2026)

`AGENTS.md` mục 3 cấm "dịch vụ AWS trả phí khác" ngoài EC2 và EBS, và mục 7 cấm đổi ràng buộc mục 3 nếu chưa có ADR được nhóm duyệt. Tầng 3 của FR-INF-25 cần một bucket S3, nên đây là một đề nghị đổi ràng buộc (SRS O-22):

- **Đề nghị:** cho phép đúng một khoản AWS ngoài EC2 và EBS: một bucket S3 (Versioning + Object Lock Governance 7 ngày) nhận dump DB đã kiểm checksum, chỉ từ host A bằng role `CampusLinkBackup` (thêm `s3:PutObject` vào một prefix, không có quyền xóa). Guest vẫn không có credential AWS (NFR-09).
- **Vì sao cần:** hai tầng đầu nằm trong cụm nên không mô phỏng được mất cả cụm; bản sao ngoài cụm là tầng duy nhất cho số RTO của kịch bản đó.
- **Chi phí:** dump vài MB, vài lần đẩy, ước rất nhỏ so với ngân sách khoảng 70 USD (credit ước tính còn khoảng 112 USD, 09/11). Số chính thức do TV4 tính bằng AWS Pricing Calculator cho `cost.csv` (FR-INF-21); chưa tính.
- **Cách duyệt:** nhóm đọc PR này. Đồng ý thì mục này thành "chấp nhận" và TV1 mới tạo bucket (TV1 tự bấm trên console). Không đồng ý hoặc không phản hồi kịp thì **không tạo bucket** và FR-INF-25 dừng ở 2 kịch bản đầu (đường lùi ở mục Quyết định 3); yêu cầu không mất.

## Đã kiểm (12/11/2026)

- **O-20, FR-INF-24 giai đoạn lab:** trên stack lab 2 VM `campus_role=app` sau LB `ovn`, `member` (`campus-tv2`) tắt VM, `loadbalancer member set --disable` và `port set --disable` đều được chấp nhận. LB ngừng gửi lưu lượng tới backend lỗi sau khoảng 0,5–2,6 s kể từ lúc gõ lệnh (gồm 1–2 s trễ của CLI); **0/842 probe trả mã khác 200**, xác nhận bằng log thô; hồi phục 1,9–30,5 s. Lưu lượng quay lại backend **trước** khi `operating_status` về ONLINE (0,3–5,6 s), nên `campus-chaos` phải kiểm "đã hoàn tác" bằng lưu lượng thật, không dựa vào `operating_status`. Một lần chạy mỗi hành động, probe ~3,8 kết nối/s; **chưa** kiểm access rules của credential riêng. Evidence `evidence/G3/20261112-FR-INF-24-O-20-chaos-lab-hanh-dong-loi-bang-member.txt`.
- **FR-INF-23, bản nhẹ:** workflow `.github/workflows/supply-chain.yml` chạy trên PR này. gitleaks quét toàn bộ lịch sử (74 commit): 3 dương tính giả (tên file có chữ `secrets` hoặc `api_key_`, giá trị là hash), đã thêm ngoại lệ hẹp theo đường dẫn và dạng dòng trong `.gitleaks.toml`, chạy lại sạch. Trivy trên digest Shlink 5.1.8 (chỉ lỗ hổng đã có bản vá): 21 lỗ hổng (1 CRITICAL `brotli-libs`, 20 HIGH, phần lớn ở lớp Alpine, kèm 1 ở binary RoadRunner `rr` và 1 ở composer); SBOM CycloneDX 1.6 có 414 thành phần. Chỉ báo cáo, vì Shlink bị khóa phiên bản. **Chưa có:** build, ký cosign và `cosign verify` cho `campus-portal`, `campus-stats` (cần Dockerfile của TV3, TV4).
- **FR-INF-25 tầng 1 (Cinder snapshot → volume mới → DB VM thử), 3 lần chạy 12/11:** snapshot crash-consistent của `campus-db-data` (đang gắn vào `campus-db`, không ghi gì vào DB thật) → volume mới → VM thử không FIP, không SSH cài `postgresql-16` và khởi động PostgreSQL trực tiếp trên dữ liệu khôi phục (cổng 5433). Cả 3 lần PostgreSQL lên và truy vấn được: DB `shlink`, `short_urls=1`, `visits=2`, link thử `tv2g4-20261111` có mặt. **RTO đo được 158 s (VM thử ở A), 139 s và 124 s (VM thử ở AZ B; lần 3 xác nhận host `campus-b` bằng quyền admin, `lsblk` trong guest thấy `vdb 10G ext4 campus-db-data`)**; lần 2 chậm hơn ở bước tạo VM (ACTIVE 78 s so với 26 s) vì B kéo image lần đầu. Thời gian dành cho: snapshot và volume ~12 s, tạo VM 26–27 s, từ ACTIVE đến lúc cloud-init chạy 25–90 s (biến động lớn), `apt install postgresql-16` 34–37 s, PostgreSQL 1–2 s. **Giới hạn:** dữ liệu rất nhỏ (RTO sẽ lớn hơn với dữ liệu và WAL thật); đo tới lúc PostgreSQL trả lời, **chưa gồm** việc đưa DB VM về IP `10.20.0.10`, dựng lại cấu hình và `pg_hba` cho app kết nối (phần TV3 chưa thử, runbook `db-vm.md` mục 8); chưa có DB `campus_portal`; sai số đo ±10 s (thăm dò console mỗi 10 s). Ngưỡng RTO tầng 1 (NFR-20) **chưa chốt**. Evidence `evidence/G3/20261112-FR-INF-25-tang-1-snapshot-volume-db-vm-thu-hai-host.txt`.

## Phương án đã loại

- **Rolling update bằng Heat `rolling_updates`** (bản nháp đầu của FR-INF-24): khả thi (theo `heat/scaling/rolling_update.py` stable/2026.1, nhóm 1 máy được tăng tạm lên 2 rồi mới bỏ máy cũ) nhưng tương đương ASG instance refresh của AWS, nên không mới theo tiêu chí trên; lại phụ thuộc G4.
- **Scale-to-zero, FaaS tự dựng:** giống Lambda đã học.
- **Tài nguyên có hạn dùng (lease), xếp lịch job theo carbon:** mới nhưng ít gắn với phần đánh giá tải; xếp lịch theo carbon cần nguồn dữ liệu ngoài chưa kiểm.
- **Kubernetes (Magnum, Zun, k3s trong VM), KEDA, service mesh:** bật dịch vụ DevStack mới phải chạy lại `stack.sh`, xóa DB, OVN, Cinder, Swift của cụm; k3s đổi cả cách đóng gói lẫn Heat ASG đang làm.
- **Barbican, Designate, Trove, Manila:** cùng lý do `stack.sh`; secret đã có hướng riêng (ADR-10).
- **Prometheus + Grafana đầy đủ:** thêm RAM khi NFR-13 đã sát; Gnocchi/Aodh đã có metric cho co giãn.
- **CloudFront hoặc AWS WAF trước `sslip.io`:** ACM không cấp được cert cho tên `sslip.io` vì nhóm không sửa được DNS; cache redirect thì Shlink không đếm được visit.

## Hệ quả

- `versions.lock` ghi digest đã ký cho `campus-portal` và `campus-stats` (thay `REPLACE_DIGEST`). Workflow nằm trong `.github/workflows/`.
- Host A có thêm `campus-chaos` (Python + openstacksdk trong venv riêng) và một application credential mới; Nginx thêm `$request_time` vào `log_format` để tính SLI (NFR-22) và điều kiện dừng của thí nghiệm.
- Vấn đề mở mới: O-18 (GHCR công khai hay riêng tư), O-19 (chu kỳ backup, quyết định RPO), O-20 (bật/tắt member và port qua provider `ovn`, access rules của `campus-chaos`), O-21 (tải việc TV1 10–14/11).
- Phân tích đầy đủ, thiết kế `campus-chaos`, lịch và mốc cắt: Claude Doc "Giải pháp cloud nâng cao cho CampusLink" (03/11/2026).
