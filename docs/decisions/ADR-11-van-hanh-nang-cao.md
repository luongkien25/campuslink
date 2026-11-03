# ADR-11: Thêm ba yêu cầu vận hành nâng cao, trong đó có dịch vụ thí nghiệm lỗi tự viết; không bật dịch vụ OpenStack mới

- Ngày: 03/11/2026 · Người quyết: TV1 (Kenn) · Trạng thái: chấp nhận

## Bối cảnh

Giảng viên không nhận xét gì về phần cloud khi duyệt đề tài (SRS O-04); phần cloud của nhóm đã vượt nội dung môn (AWS Academy Cloud Foundations Module 1–7, Lab 1–4 OpenStack). Cái còn thiếu là cách hệ thống thật được vận hành. Nhóm dùng tiêu chí: một giải pháp chỉ tính là "mới" khi cơ chế hoặc khái niệm của nó không có bản tương đương trong phần đã học ở AWS, không phải một dịch vụ khác tên làm cùng việc. Phần mở rộng app (ADR-08) đã chiếm phần lớn sức của TV2–TV4 tới 14/11; freeze bắt đầu 19/11.

## Quyết định

1. Thêm vào SRS bản 1.4:
   - FR-INF-23: chuỗi cung ứng image (CI test, Trivy, SBOM, ký cosign, `cosign verify` trước khi nạp vào Glance image).
   - FR-INF-24: dịch vụ thí nghiệm lỗi `campus-chaos` do nhóm tự viết, chạy trên host A: gây đúng một lỗi có kiểm soát lên app VM (tắt VM, tắt member LB, tắt port), dừng sớm theo điều kiện, tự hoàn tác, ghi báo cáo vào Swift `campus-reports`.
   - FR-INF-25: khôi phục thảm họa 3 tầng có RPO/RTO, bản sao trên S3 có Object Lock.
   - NFR-20–22 (RPO/RTO, số đo tự ghi của thí nghiệm lỗi, SLO).
2. TV1 làm chính; TV4 viết test cho FR-INF-23 và kịch bản cho FR-INF-24, TV3 phối hợp FR-INF-25, TV2 review hành động lên LB member.
3. Mốc cắt: FR-INF-23 cắt 09/11; FR-INF-24 và FR-INF-25 cắt 14/11. Trễ thì FR-INF-25 rút về 2 kịch bản đầu và FR-INF-24 chỉ giữ hành động tắt VM; FR-INF-24 chưa PASS thì làm tay FR-INF-20 như cũ.
4. Không bật thêm dịch vụ OpenStack, không thêm EC2 hay VM thường trực.

## Căn cứ

- Theo tiêu chí trên, FR-INF-23 (chuỗi tin cậy từ mã nguồn tới VM) và FR-INF-24 (thí nghiệm lỗi có giả thuyết, điều kiện dừng, tự hoàn tác) là khái niệm mới; AWS có Signer và FIS nhưng ngoài giáo trình. Chaos engineering có trong ngành từ 2011, nên chỉ mới so với phần đã học. FR-INF-25 tương đương S3/snapshot EBS: không mới nhưng vẫn làm vì cho số đo RPO/RTO.
- `campus-chaos` tự động hóa phép thử FR-INF-20/NFR-07 vốn phải làm tay, nên tải việc tăng ít mà phần đánh giá có số đo lặp lại được; khi demo, giảng viên chọn máy để tắt và xem báo cáo tự sinh.
- Chốt an toàn của `campus-chaos`: chỉ đích có metadata `campus_role=app`, không bao giờ DB VM hay host; mỗi lúc một thí nghiệm; thời lượng tối đa 300 s; trạng thái trước lỗi ghi ra file để `campus-chaos revert` hoàn tác được cả khi tiến trình chết; application credential có access rules, không dùng admin.
- Object Lock chế độ Governance cho phép người có quyền đặc biệt dọn bucket sau khi xong môn; role `CampusLinkBackup` chỉ thêm `s3:PutObject` vào một prefix, guest vẫn không có credential AWS (NFR-09).

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
