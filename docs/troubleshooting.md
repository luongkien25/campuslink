# Nhật ký lỗi và cách sửa

Mỗi lỗi đã gỡ được = 1 dòng. Ghi **triệu chứng đúng như thấy** (thông báo lỗi nguyên văn, đã che secret) để lần sau AI tìm được.
Cột "Nguồn": link tài liệu, commit, hoặc issue. Nếu chỉ là AI đoán mà chưa kiểm, ghi "chưa kiểm".

## Đã biết trước (từ SRS/Lab, chưa gặp thật)

| Triệu chứng | Nguyên nhân | Cách sửa | Nguồn |
| --- | --- | --- | --- |
| B không `apt update` được, timeout | B không có public IPv4; NAT trên A chưa chạy, hoặc A còn bật source/dest check, hoặc route 0.0.0.0/0 của private RT chưa trỏ ENI A | Tắt source/dest check A; bật `ops/campus-nat.service`; kiểm route table | SRS FR-INF-01, `infra/aws/README.md` |
| Ping giữa guest A↔B được nhưng HTTP/SSH treo | MTU: Geneve thêm header, guest phải MTU 1400 | `campus-net` đặt MTU 1400; kiểm `ping -M do -s 1372` | SRS FR-INF-04 |
| Tạo LB với `--provider ovn` báo không hỗ trợ HTTP/L7/HTTP monitor | OVN provider chỉ hỗ trợ listener TCP/UDP/SCTP và health monitor TCP/UDP | Dùng listener TCP, pool `SOURCE_IP_PORT`, monitor TCP; kiểm HTTP bằng readiness trong VM | SRS C-03, FR-INF-07 |
| Từ laptop không vào được FIP 172.24.4.x | 172.24.4.0/24 là mạng ảo bên trong host A, AWS không route tới | Đi qua Nginx trên A (EIP:443) hoặc SSH vào A rồi curl | SRS mục 2 |
| `stack.sh` lỗi khi clone Gnocchi `stable/2026.1` | Gnocchi không có nhánh stable theo release OpenStack | Ghim commit cụ thể (SRS O-06), ghi vào `docs/versions.lock` | SRS O-06 |
| VM boot rất chậm, CPU guest 100% lúc boot | Không có nested KVM, Nova đang chạy QEMU thuần | Kiểm `/dev/kvm`, `kvm-ok`; `virt_type=kvm` | SRS C-02, FR-INF-02 |

## Đã gặp thật

| Ngày | Ai | Triệu chứng | Nguyên nhân | Cách sửa | Nguồn |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
