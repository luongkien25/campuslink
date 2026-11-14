# H4 — Heat core, LB và scale thủ công

TV2 → TV1, TV3, TV4. Yêu cầu FR-INF-07/08/09/22, NFR-08/15. Kiểm trên cụm ngày 13/11/2026; trạng thái cuối tại **14:18:54 UTC**. Giá trị thật trong [inventory](../inventory.yaml), image pin trong [versions.lock](../versions.lock).

## Trạng thái bàn giao

Core Shlink đã triển khai: một app cố định AZ-A và ASG-B min 1/max 2, hiện giữ một app AZ-B. Cả hai dùng image G4 đã kiểm, không FIP; health HTTP 200/status=pass, Redis PONG và metadata guard đạt. Pool có hai member ACTIVE/ONLINE; 60 kết nối mới được đối chiếu Request ID tới cả hai guest, A33/B27; redirect link thử đúng302/Location.

**HTTPS chưa nghiệm thu:** `https://s.44-198-215-187.sslip.io/rest/health` trả503 với cert được verify hợp lệ. TV1 cần nối Nginx tới VIP FIP mới bên dưới. TV2 không sửa Nginx hoặc dịch vụ nền trên A. Portal/worker/listener8081 thuộc H4b, chưa có trong core; telemetry/Aodh và autoscaling theo tải thuộc giai đoạn 6, chưa được chứng minh bằng scale tay.

## Deployment đang giữ

| Thành phần | Giá trị |
| --- | --- |
| Stack | `campus-app`, `816bd58d-ca22-47b8-abe5-9729719d894e`, CREATE_COMPLETE |
| Image app | `campus-app-tv2-g4-20261111`, `2c43a06d-1db8-4c01-bd31-98803325d932` |
| Flavor | `campus.app`: 1 vCPU/2048 MiB/root10 GiB |
| App A | `523d67b4-9234-4b09-b3dc-c814e6b868fc`, `10.20.0.195`, `campus-az-a` |
| App B hiện tại | `88d79382-b4c2-4868-988f-047421ff967b`, `10.20.0.111`, `campus-az-b` |
| ASG-B | `479438e0-37fe-47d3-a0a3-fcaf53e756b1`, min 1/max 2, current1 |
| LB | `deb301de-fb2a-430b-8bc7-2954a3afe14a`, provider `ovn` |
| VIP port / địa chỉ | `9b107b20-4d06-4716-808b-a57f12a64c45` / `10.20.0.128` |
| VIP FIP nội bộ | **`172.24.4.117:8080`**, FIP UUID `4de69ad4-b09e-4221-803f-f927715769fc` |
| Listener | `b431e26a-0590-48ba-8c5d-544bc01ee7f4`, TCP8080 |
| Pool | `e7014f7e-6883-4198-861e-bf23b0247f9f`, TCP/SOURCE_IP_PORT |
| Monitor | `558c8bab-9cbf-4730-94be-4d705c8d51d4`, TCP, delay5/timeout3/retries3 |
| Member A | `7f3cb4ba-bd65-4f59-b37b-caeccde23d00`, `10.20.0.195:8080` |
| Member B | `fdd7b344-df10-4ad6-88fe-18778ad12efa`, `10.20.0.111:8080` |

FIP trên là mạng ảo OpenStack, không phải IP public AWS và laptop không route trực tiếp tới. Ingress dự kiến: Internet → EIP A → Nginx443 → `http://172.24.4.117:8080`. Giữ Host/forwarded headers theo H1 và [mẫu Nginx](../../infra/nginx/campus.conf.example); TLS vẫn kết thúc tại Nginx.

DB `10.20.0.10`, port `7df6ea1d-2e8c-46d5-99b9-e121855d81b5`, volume `f43fbbd2-b85f-4bb1-b403-ba54a2f84189` thuộc nền/TV3, nằm ngoài app stack. Hậu kiểm xác nhận volume in-use đúng DB VM, cùng attachment từ08/11; port/IP/DB SG giữ nguyên.

## Tham số và quy trình vận hành

Template chuẩn là [infra/heat/root.yaml](../../infra/heat/root.yaml), nested [app-unit.yaml](../../infra/heat/app-unit.yaml), xem [README Heat](../../infra/heat/README.md). Tham chiếu `templates/root.yaml` ở SRS FR-INF-08 là tên cũ; repo dùng một cây `infra/heat/`, không tạo bản sao template.

Root nhận image/flavor/keypair, network/subnet/app SG, external network, AZ-A/B, hai bootstrap parameters hidden, readiness180, drain5, metadata group `campuslink-app` và `diagnostic_security_groups` mặc định[]. Deployment đang giữ dùng danh sách chẩn đoán rỗng; mỗi port chỉ có app SG. Credential chỉ được helper đọc từ file private trên A, không có trong handoff hoặc mẫu. Các env thật do phiên tạo đã gỡ; credential gốc TV1 vẫn giữ nguyên.

Sau khi xác nhận phiên Zalo/A/B/nhật ký, chạy trên A bằng credential member của TV2; cú pháp đã kiểm trên cụm:

```bash
OS_CLOUD=campus-tv2 openstack stack resource signal campus-app scale_out
# Doi B len2, tong3 app, WaitCondition/member hoan tat; do traffic.
# Doi cooldown it nhat180s sau khi scale-out hoan tat.
OS_CLOUD=campus-tv2 openstack stack resource signal campus-app scale_in
```

Hai tên trên là logical resource names, không phải URL webhook. Signal được chấp nhận chưa chứng minh đã scale; phải kiểm current_size, VM/AZ, member và traffic. Không update root giữa lượt đo vì desired_capacity có thể được áp lại. TV4 là reader; thao tác scale do TV2/TV1 thực hiện, không tự tăng role.

Chưa tạo alarm trong giai đoạn 5 nên chưa có alarm ID hay thủ tục disable alarm đã kiểm để bàn giao. Giai đoạn6 phải bổ sung H4 phần telemetry/alarm và cách tắt/bật theo ID thật trước workload tự động. Không dùng signal SUCCESS thủ công để thay readiness.

## Bằng chứng tích hợp và giới hạn

| Kiểm | Kết quả |
| --- | --- |
| HOT validate | Root/nested validate trên Heat2026.1 đạt với fixture credential giả |
| A lỗi DB | FAILURE ACK, stack FAILED, pool rỗng, ASG-B chưa tạo |
| B lỗi DB | A SUCCESS/member; B FAILURE, không thêm B, stack FAILED |
| Callback lỗi | App/Redis khỏe nhưng token giả; WaitCondition0/1, timeout301s, không member/ASG-B |
| Scale tay | Tổng2→3→2; fixed A giữ UUID trong cùng lượt đo |
| Backend mapping | 2 app:26/34; 3 app:15/22/23, từng Request ID khớp đúng một guest |
| Traffic trong scale | 734 request scale-out và117 scale-in, 0 lỗi probe; auth-deny401 là đáp ứng mong đợi |
| Delete lifecycle | Member DELETE_COMPLETE13:55:15Z → VM DELETE_IN_PROGRESS13:55:20Z → VM DELETE_COMPLETE13:55:25Z |
| Runtime guest | Cùng digest/cached image, HTTP/Redis, UID1001/mount RO, metadata DROP counters, JSON/UTC/guest labels đạt |

Scale và các số đo trên thuộc **stack tích hợp `471c4594-1982-4b5f-aebc-07ee1366a162` đã dọn**, không phải UUID live trong bảng đầu. Sau đo, triển khai lại cùng template/image bằng CREATE với SG chẩn đoán rỗng; deployment mới có handle/WaitCondition mới và được kiểm hai app/traffic/guard riêng. Không nhận một lượt scale đã chạy trên deployment mới khi thực tế chưa chạy. Gói code chạy cloud có SHA256 `4a6295aa5eb2896372b7c0c8fd84ccda2bd5607c64fabac1c39faf54e9100310`; helper timeline phía client được sửa theo event thật và có regression test.

Readiness local180s; WaitCondition300s dùng mốc engine riêng. ACK client và WaitCondition COMPLETE không có thứ tự tuyệt đối: Heat có thể hoàn tất trước khi ACK tới client, event Heat chỉ có độ phân giải giây. [Timeline](../../evidence/G4/20261113-FR-INF-09-tv2-heat-timeline.json) dùng Heat Server CREATE_COMPLETE làm mốc engine quan sát Nova ACTIVE; request đầu là request LB đầu **quan sát trong lượt probe**, A/B có chờ thao tác đo nên không lấy độ trễ đó làm benchmark khởi động.

Drain5s đã thấy trong event delete, chưa chứng minh mọi request đang chạy được giữ nguyên. Smoke0 lỗi không chứng minh zero downtime/p95/RPS mục tiêu hoặc chịu mất AWS A. Query DB lúc không tải thấy role shlink có1 kết nối (gồm probe), limit15/max50; chưa phải ngân sách kết nối dưới workload đầy đủ. Chưa ép riêng conflict409, token hết hạn3600s hoặc cross-signal trong cây stack; giới hạn token theo ADR-10, retry conflict theo source plugin đã đọc.

Hai phép đo redirect chưa kiểm được chuyển sang giai đoạn 6: redirect qua đủ ba backend sau scale-out, và A vẫn redirect khi B lỗi DB trong lab cô lập. Mapping Request ID của ba app và health/member của A trong case B lỗi không thay thế hai phép đo này. Redirect đã kiểm ở deployment hai app; không nhận hai phép đo chuyển tiếp là PASS.

Root update để gỡ SG chẩn đoán chưa được nhận là an toàn: preview nested400, shallow preview có replacement LB/policy, ASG source có rolling replacement khi resource definition đổi. Phiên này không áp dụng update đó. App/credential/image/user-data update và Nova rebuild vẫn cần thủ tục fresh handle/condition được kiểm; không tái dùng WaitCondition cũ COMPLETE.

## Cleanup và bước tiếp theo

Cleanup tạm hoàn tất **14:17:59 UTC**: các lab lỗi và stack tích hợp đã dọn; jump/FIP jump/hai SG SSH tạm đã xóa. SG thêm tạm vào port deployment để đo đã được gỡ, port trở về app SG đúng template. Giữ một stack `campus-app`, DB+2 app (3 VM/3 vCPU/6144 MiB), 1 volume10 GiB và1 VIP FIP. `campus-check`14:18:54 UTC: OK; agent không Stop EC2, giờ Stop do người vận hành ghi nhật ký.

1. TV1 nối Nginx tới VIP mới, kiểm HTTPS health 200/redirect với verify cert; hiện còn503. Đây là phần FR-INF-06 còn chờ.
2. TV3/TV4 nhận endpoint/UUID qua bàn giao này để chuẩn bị smoke/workload; chưa chạy benchmark tự động trước giai đoạn 6.
3. Giai đoạn6 bổ sung Ceilometer/Gnocchi/Aodh và H4 alarm; H4b chờ H1b/image portal+worker, không nhận từ HTTP stub.

Evidence: [bản đọc ngắn](../../evidence/G4/20261113-FR-INF-09-tv2-heat-core-cloud.txt), [output/Request IDs/events/programs đã lọc](../../evidence/G4/20261113-FR-INF-08-tv2-heat-checks.json). File có thể chứa tên object/đường dẫn secret để mô tả giao diện, không chứa giá trị secret/token.
