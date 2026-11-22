# Báo cáo CampusLink — Hạng mục 6 và 7

## 5.6. Cân bằng tải

### Thiết kế

Nginx trên EC2 A nhận HTTPS, kết thúc TLS và chuyển kết nối tới VIP nội bộ của Octavia. Load balancer dùng provider OVN, listener TCP cổng 8080, pool theo thuật toán SOURCE_IP_PORT và health monitor TCP. Hai VM Shlink nằm trên mạng riêng, một VM ở AZ-A và một VM ở AZ-B, dùng chung PostgreSQL và Redis. Khi thêm VM, Heat đợi app qua kiểm tra HTTP và Redis trước khi đăng ký member vào pool. [Thiết kế FR-INF-07](../SRS.md) · [Bàn giao H4](../handoffs/H4-heat-lb-scaling.md)

Ngày 14/11/2026, sau một lần tăng số VM bằng tay, 60 yêu cầu redirect trả 302 đúng đích. Request ID khớp log guest của cả ba backend, gồm 21 yêu cầu tới app A, 15 tới app B cũ và 24 tới app B mới. Kết quả xác nhận cả ba backend thực sự nhận yêu cầu trong lượt đó. [Evidence phân phối yêu cầu](../../evidence/G4/20261114-FR-INF-09-tv2-redirect-carryover.json)

### Phép đo failover ngày 18/11/2026

Nhóm đặt tải 10 request/giây với 100 luồng, warm-up 120 giây và steady 1.020 giây. Trong steady, nhóm dừng rồi bật lại app VM A bằng Nova, theo dõi trạng thái VM và LB qua API. Một probe HTTPS độc lập kiểm redirect qua VIP khi chỉ còn app B phục vụ. [Evidence failover](../../evidence/G5/20261118-FR-INF-20-NFR-07-tv2-app-a-failover.txt)

| Mốc UTC | Kết quả |
| --- | --- |
| 14:57:27.063 → 14:57:36.530 | Từ lệnh dừng A đến lần đầu thấy A ERROR, B ONLINE mất **9,47 giây**. |
| 14:59:11 | Probe HTTPS trả **302 đúng đích** khi chỉ còn B ONLINE. |
| 15:02:28.479 → 15:03:19.474 | Từ lệnh bật lại A đến lần đầu thấy hai member ONLINE mất **51,00 giây**. |
| 15:03:19.603 | HTTPS health qua VIP đạt sau **51,12 giây** kể từ lệnh bật A. |

| Cửa sổ steady, phân theo thời điểm phát yêu cầu | Yêu cầu | Redirect 302 | HTTP 5xx | Lỗi client 599 |
| --- | ---: | ---: | ---: | ---: |
| Trước lệnh dừng A | 2.992 | 2.396 | 0 | 1 |
| Từ lệnh dừng đến lệnh bật lại A | 3.015 | 2.409 | 0 | 2 |
| Sau lệnh bật lại A | 4.193 | 3.350 | 0 | 4 |
| **Toàn steady** | **10.200** | **8.155** | **0** | **7** |

Mã 599 gộp timeout và lỗi kết nối phía máy phát. Backend B ONLINE trong cả 57 mẫu của cửa sổ lỗi. Probe 302 nằm ngoài CSV. Các mốc Nova và Octavia là thời điểm lần đầu quan sát qua API. [Phân tích CSV và cách chia cửa sổ](../../evidence/G4/20261118-FR-INF-20-NFR-07-tv1-failover-analysis.txt)

### Rủi ro và phạm vi kết luận

- **Một điểm lỗi ở đường vào.** Phép thử FR-INF-20/NFR-07 dừng một app VM OpenStack. Nginx và các dịch vụ dùng chung vẫn phụ thuộc host A, nên mất EC2 A hoặc cả AZ-A có thể gián đoạn dịch vụ.
- **Độ bao phủ của health monitor.** TCP monitor kiểm cổng còn nhận kết nối. Probe HTTPS bổ sung kiểm hành vi redirect ở tầng ứng dụng. Sau hồi phục, Nova, LB và HTTPS health xác nhận đường phục vụ hoạt động. Chưa đối chiếu Request ID với log riêng app A để xác định yêu cầu nào quay lại A.
- **Phạm vi tải.** Đây là một lượt failover ở mức đặt 10 RPS. Lượt đặt 30 RPS chạy riêng để đối chứng. Số liệu của hai lượt không đủ để suy rộng kết quả failover lên các mức tải khác. [Thiết kế và giới hạn NFR-07](../SRS.md) · [Evidence TV2](../../evidence/G5/20261118-FR-INF-20-NFR-07-tv2-app-a-failover.txt)

## 5.7. Tự động co giãn

### 5.7a. Kiến trúc và quy tắc scaling

Heat giữ một app cố định ở AZ-A và một nhóm AutoScalingGroup ở AZ-B với 1–2 app, nên tổng số app là 2–3. Khi VM mới khởi động, bootstrap kiểm HTTP và Redis, gửi tín hiệu hoàn tất WaitCondition rồi Heat tạo member Octavia. Khi scale-in, quan hệ phụ thuộc trong Heat cho phép gỡ member trước khi xóa VM. Hai alarm nằm trong stack riêng và gọi hai Heat ScalingPolicy của stack ứng dụng qua native signal. [SRS FR-INF-09/11, NFR-05](../SRS.md) · [Template Heat](../../infra/heat/root.yaml) · [Bàn giao H4](../handoffs/H4-heat-lb-scaling.md)

| Chính sách | Điều kiện | Thay đổi |
| --- | --- | --- |
| Scale-out | CPU nhóm > 60% qua 2 bucket 60 giây liên tiếp | Tăng 1 app trong AZ-B, tối đa 3 app toàn cụm. |
| Scale-in | CPU nhóm < 25% qua 3 bucket 60 giây liên tiếp | Giảm 1 app trong AZ-B, tối thiểu 2 app toàn cụm. |

Cooldown cấu hình là **180 giây**. App flavor có 1 vCPU. Với bucket 60 giây, ngưỡng raw của Aodh tương ứng 36e9 và 15e9 ns. [Cấu hình alarm](../../infra/heat/alarms.yaml) · [Cách đối chiếu CPU](../../infra/heat/telemetry/README.md)

ADR-12 tính rate theo từng VM trước khi lấy trung bình. Gate v2.2 kiểm bucket đã đóng, độ phủ và kiểu timestamp từ Gnocchi. Khi số VM thay đổi, alarm có thể tạm sang insufficient data trong lúc chờ điểm đo hợp lệ. Ngưỡng và cooldown giữ nguyên. Mục 5.7b do TV1 trình bày chi tiết bản vá. [ADR-12](../decisions/ADR-12-aodh-rate-tung-vm.md) · [Gate v2.2, PR #81](https://github.com/luongkien25/campuslink/pull/81) · [Phần TV1, PR #92](https://github.com/luongkien25/campuslink/pull/92)

### Lượt tự động 2→3→2 ngày 21/11/2026

Lượt 2 dùng slug mới tv3dc-20261121. TV3 ghi nhận 0 visit khi mới tạo và 1 visit sau probe trước lượt tải. CPU nhóm đạt đỉnh **62,48%**, ở bucket 60 giây bắt đầu lúc **15:50:00 UTC**. Aodh tự kích hoạt cả hai Heat ScalingPolicy trong cùng lượt. Nhóm giữ nguyên ngưỡng 60%/25% và không gửi signal tay. [Số đo slug trước tải](https://github.com/luongkien25/campuslink/issues/90#issuecomment-7065064776) · [Alarm history, Heat events, CPU và LB](https://github.com/luongkien25/campuslink/issues/77#issuecomment-7065510182)

| Mốc UTC | Quan sát |
| --- | --- |
| 15:48:39 | Bắt đầu phát tải ab qua VIP nội bộ. |
| 15:53:22.719 | cpu_high chuyển ALARM. |
| 15:53:40 | Heat ghi server CREATE_COMPLETE cho VM mới. |
| 15:54:08 | Heat ghi readiness hoàn tất. |
| 15:54:12 → 15:54:19.543 | Heat ghi scale_out SIGNAL_COMPLETE, rồi lần đầu quan sát 3 member ONLINE. |
| 15:58:39 | Dừng phát tải. |
| 16:04:22.582 | cpu_low chuyển ALARM. |
| 16:04:38 → 16:04:57.781 | Heat ghi scale_in SIGNAL_COMPLETE, rồi lần đầu quan sát LB trở về 2 member ONLINE. |
| 16:11:07.154 → 16:11:10.357 | Stack alarm UPDATE_COMPLETE. Hậu kiểm thấy hai alarm đã tắt, ba danh sách action đều rỗng và LB vẫn có 2 member ONLINE. |

TV1 đối chiếu journal notifier với hai sự kiện Heat. Trong các cửa sổ quanh hai lần gọi, bộ lọc journal không ghi 401, 403, error hoặc Traceback. Sau scale-out, cả hai alarm tạm sang insufficient data lúc 15:54:22 UTC và về OK lần lượt lúc 15:58:22 và 15:59:22 UTC. [Đối chiếu độc lập TV1](https://github.com/luongkien25/campuslink/issues/77#issuecomment-7065622142) · [Evidence đầy đủ, PR #91](https://github.com/luongkien25/campuslink/pull/91)

### Điều kiện tải và giới hạn

| Điều kiện | Lượt 1 ngày 21/11 | Lượt 2 ngày 21/11 |
| --- | --- | --- |
| Slug | tv4fix1, khoảng 124 nghìn visit | tv3dc-20261121, slug mới |
| Tải thực tế theo ab | 23,49 RPS | 39,54 RPS |
| p95 phía máy phát ab | 3.075 ms | 2.017 ms |
| Kết quả ab | 14.096 phản hồi non-2xx, Failed requests = 0 | 23.724 phản hồi non-2xx, Failed requests = 0 |
| Đỉnh CPU nhóm app | 27,35% | 62,48% |
| CPU DB, 1 vCPU | 99,5–99,7% trong tải, tiếp tục cao khoảng 26 phút sau tải | Khoảng 88–94% trong tải, về nền khoảng 1–2 phút sau tải |
| Kết quả scaling dưới tải | cpu_high giữ OK, không có scale-out. Chiều scale-in được quan sát ở một pha riêng trước tải. | Tự tăng 2→3 rồi tự giảm 3→2 trong cùng lượt. |

ab không phân loại mã cụ thể trong nhóm non-2xx. Redirect 302 là hành vi kỳ vọng của fixture. Hai lượt dùng slug khác nhau nên số liệu chỉ cho thấy tương quan giữa dữ liệu đã tích lũy, tải DB và CPU app. TV3 chưa kiểm trực tiếp truy vấn đang chạy trong DB VM. [Log tải và CPU, PR #91](https://github.com/luongkien25/campuslink/pull/91) · [Kiểm DB và slug, #90](https://github.com/luongkien25/campuslink/issues/90#issuecomment-7064777556)

**Phạm vi kết luận.** Báo cáo giữ trạng thái **đạt một phần** cho FR-INF-11. Lượt 2 đạt các mốc tải → ALARM → Heat event → VM ready và ghi nhận 2→3→2 tự động. Còn thiếu mốc **request đầu tiên tới VM mới** của FR-INF-11/NFR-06 vì chưa ghép Request ID của lượt tự động với log guest. Thời điểm LB ONLINE phục vụ timeline LB. Đã ghi mốc request tới VM mới trong lượt scale tay ngày 16/11, với phạm vi riêng. Kết quả một lượt thành công chưa chứng minh tính lặp lại hoặc thay cho benchmark nhiều lượt static-vs-auto theo NFR-04. Rủi ro DB bão hòa và khả năng đạt ngưỡng dưới workload khác vẫn thuộc O-10. [Bàn giao H4](../handoffs/H4-heat-lb-scaling.md) · [Phạm vi nghiệm thu](../acceptance.md) · [Bản cập nhật PR #95](https://github.com/luongkien25/campuslink/pull/95)

## 5.8. Monitoring

### 5.8.1. Metric và alarm

Ceilometer thu counter CPU tích lũy theo nanosecond cho VM app trên cả hai host. Gnocchi 4.7.1 lưu metric với granularity 60 giây. Nhóm đối chiếu mức CPU từng VM bằng công thức **Δcpu_ns / (Δt × 10⁹ × số vCPU) × 100** rồi lấy trung bình nhóm. Query lọc đúng project, server group campuslink-app và VM còn hoạt động theo ended_at/deleted_at. Việc lọc này tránh đưa VM lab cũ hoặc VM đã xóa vào số đo nhóm. [Evidence metric hai host](../../evidence/G4/20261114-FR-INF-10-tv2-metric-alarm.txt) · [Cách thu và phân tích dữ liệu](../../infra/heat/telemetry/README.md)

| Phép kiểm | Quan sát |
| --- | --- |
| 14/11, chỉ đánh giá với action rỗng | CPU nhóm 61,19–62,08% ở các bucket 07:47–07:49 UTC. High vào ALARM lúc 07:49:13.739 UTC. Sau dừng tải, low vào ALARM lúc 07:54:13.693 UTC. |
| 21/11, lượt tự động | Alarm history ghi high/low chuyển ALARM, khớp với journal và Heat events. Khi thêm VM, cả hai alarm tạm insufficient data trước khi hồi phục. |

Nhóm dùng timestamp trong alarm history để ghi lúc đổi trạng thái. Trường state_timestamp trong phép đo 14/11 đã giữ giá trị cũ. Lượt chỉ đánh giá chứng minh chuỗi thu metric và đánh giá alarm. Lượt có actions ở mục 5.7 cung cấp bằng chứng gọi Heat. [Alarm history 14/11](../../evidence/G4/20261114-FR-INF-10-tv2-metric-alarm.json) · [Đối chiếu alarm history 21/11](https://github.com/luongkien25/campuslink/issues/77#issuecomment-7065510182)

### 5.8.2. Log, độ trễ và giới hạn

Nhóm dùng timestamp UTC và Request ID để ghép kết quả máy phát với log guest khi có dữ liệu. Log Nginx ghi request_time để tính độ trễ phía ingress và làm đầu vào SLI/SLO. Trong ngày 18/11, p95 của các redirect 302 tại Nginx lần lượt là **76, 117 và 74 ms** ở cửa sổ trước, trong và sau failover 10 RPS theo kế hoạch. Lượt đối chứng đặt 30 RPS cho p95 phía Nginx **596 ms**. [Evidence p95 Nginx và định nghĩa cửa sổ](../../evidence/G4/20261118-NFR-01-tv1-nginx-request-time-p95.txt)

Request_time tại Nginx và thời gian từ máy phát là hai vị trí đo khác nhau. NFR-01 quy định p95 qua Internet ở tải thực đạt khoảng 30 RPS, nên cần đối chiếu theo đúng phép đo của chương kiểm thử. NFR-22 và error budget chi tiết thuộc chương kiểm thử của TV4. Khi telemetry trễ hoặc thiếu bucket trong lúc VM mới vào nhóm, alarm tạm không đủ dữ liệu. Vì vậy báo cáo kèm cửa sổ đo, trạng thái alarm và mốc Heat thay vì suy ra hành vi scaling chỉ từ một điểm CPU. [SRS NFR-01/NFR-22](../SRS.md) · [Chương kiểm thử của TV4, PR #95](https://github.com/luongkien25/campuslink/pull/95)
