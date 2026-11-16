# H4 — Heat core, LB, metric/alarm và scale thủ công

TV2 → TV1, TV3, TV4. Yêu cầu FR-INF-07/08/09/10/11/22, NFR-05/08/15 và O-06. Kiểm trên cụm ngày 13–16/11/2026; hậu kiểm tài nguyên cuối **16/11 15:28:41 UTC**, HTTPS sau cleanup 15:30:09–17 UTC. `campus-check` trả 1 vì còn phiên/việc khác trên A. Giá trị thật trong [inventory](../inventory.yaml), image pin trong [versions.lock](../versions.lock).

## Trạng thái bàn giao

Core Shlink giữ một app cố định AZ-A và một app ASG-B tại AZ-B, min1/max2. Sau lượt baseline có tải TV1 ngày 16/11, B mới `10.20.0.102` được giữ lại; B `10.20.0.185` đã xóa. Hai app/member ONLINE; image/VIP giữ nguyên. Đã ghép một request302 từ CSVTV1 với log app mới. Lượt này scale tay2→3→2, không phải autoscaling tự động. Evidence và các phép đối chiếu backend ngày14/11 thuộc các UUID lịch sử ở mục tương ứng bên dưới.

**HTTPS:** hậu kiểm16/11 sau cleanup đạt8/8 (health200/pass và redirect302đúngđích), chứng thư được verify đầy đủ. Health từng503 ở lượt13/11; kiểm lại14/11 08:27:30Z trả200/pass và redirect08:32:55Z trả302 đúng đích, chứng thư được verify đầy đủ. TV2 chỉ kiểm, không sửa Nginx hoặc dịch vụ nền trên A. Portal/worker/listener8081 thuộc H4b, chưa có trong core. Metric và high/low alarm đã kiểm trong stack riêng; action rỗng nên chưa chứng minh autoscaling tự động theo tải.

## Deployment đang giữ

| Thành phần | Giá trị |
| --- | --- |
| Stack | `campus-app`, `816bd58d-ca22-47b8-abe5-9729719d894e`, CREATE_COMPLETE |
| Image app | `campus-app-tv2-g4-20261111`, `2c43a06d-1db8-4c01-bd31-98803325d932` |
| Flavor | `campus.app`: 1 vCPU/2048 MiB/root10 GiB |
| App A | `523d67b4-9234-4b09-b3dc-c814e6b868fc`, `10.20.0.195`, `campus-az-a` |
| App B hiện tại | `6ed60f3b-aa27-4679-b762-ca7e88264785`, `10.20.0.102`, `campus-az-b` |
| ASG-B | `479438e0-37fe-47d3-a0a3-fcaf53e756b1`, min 1/max 2, current1 |
| LB | `deb301de-fb2a-430b-8bc7-2954a3afe14a`, provider `ovn` |
| VIP port / địa chỉ | `9b107b20-4d06-4716-808b-a57f12a64c45` / `10.20.0.128` |
| VIP FIP nội bộ | **`172.24.4.117:8080`**, FIP UUID `4de69ad4-b09e-4221-803f-f927715769fc` |
| Listener | `b431e26a-0590-48ba-8c5d-544bc01ee7f4`, TCP8080 |
| Pool | `e7014f7e-6883-4198-861e-bf23b0247f9f`, TCP/SOURCE_IP_PORT |
| Monitor | `558c8bab-9cbf-4730-94be-4d705c8d51d4`, TCP, delay5/timeout3/retries3 |
| Member A | `7f3cb4ba-bd65-4f59-b37b-caeccde23d00`, `10.20.0.195:8080` |
| Member B | `1d1b931f-9702-4d05-852c-2f8edc479b81`, `10.20.0.102:8080` |

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

Giai đoạn5 chưa có alarm. Giai đoạn6 đã bổ sung stack alarm riêng và thủ tục tắt bên dưới; các ScalingPolicy trong core vẫn giữ cooldown180. Không dùng signal SUCCESS thủ công để thay readiness và không nối action tự động trước lượt kiểm notifier/phạm vi giai đoạn7.

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

Scale và các số đo trong bảng trên thuộc **lượt13/11 trên stack tích hợp `471c4594-1982-4b5f-aebc-07ee1366a162` đã dọn**. Sau đó CREATE deployment816bd58d đang giữ với SG chẩn đoán rỗng và kiểm hai app riêng; batch13/11 từng đối chiếu A33/B27, ứng với B cũ. Lượt14/11 đã bổ sung scale tay và redirect ba backend trên chính deployment816bd58d, xem phần giai đoạn6 bên dưới. Gói code13/11 có SHA256 `4a6295aa5eb2896372b7c0c8fd84ccda2bd5607c64fabac1c39faf54e9100310`; helper timeline phía client được sửa theo event thật và có regression test.

Readiness local180s; WaitCondition300s dùng mốc engine riêng. ACK client và WaitCondition COMPLETE không có thứ tự tuyệt đối: Heat có thể hoàn tất trước khi ACK tới client, event Heat chỉ có độ phân giải giây. [Timeline](../../evidence/G4/20261113-FR-INF-09-tv2-heat-timeline.json) dùng Heat Server CREATE_COMPLETE làm mốc engine quan sát Nova ACTIVE; request đầu là request LB đầu **quan sát trong lượt probe**, A/B có chờ thao tác đo nên không lấy độ trễ đó làm benchmark khởi động.

Drain5s đã thấy trong event delete, chưa chứng minh mọi request đang chạy được giữ nguyên. Smoke0 lỗi không chứng minh zero downtime/p95/RPS mục tiêu hoặc chịu mất AWS A. Query DB lúc không tải thấy role shlink có1 kết nối (gồm probe), limit15/max50; chưa phải ngân sách kết nối dưới workload đầy đủ. Chưa ép riêng conflict409, token hết hạn3600s hoặc cross-signal trong cây stack; giới hạn token theo ADR-10, retry conflict theo source plugin đã đọc.

Hai phép redirect chuyển tiếp từ lượt13/11 đã hoàn thành14/11:60GET302 qua đủ ba backend với log tương quan, và12GET302 khớp log A khi B lỗi DB trong lab riêng. Mapping batch401 hay health/member không được dùng thay cho các phép đo302 này. Xem [evidence chuyển tiếp](../../evidence/G4/20261114-FR-INF-09-tv2-redirect-carryover.json).

Root update để gỡ SG chẩn đoán chưa được nhận là an toàn: preview nested400, shallow preview có replacement LB/policy, ASG source có rolling replacement khi resource definition đổi. Phiên này không áp dụng update đó. App/credential/image/user-data update và Nova rebuild vẫn cần thủ tục fresh handle/condition được kiểm; không tái dùng WaitCondition cũ COMPLETE.

## Cleanup và bước tiếp theo

Cleanup tạm hoàn tất **14:17:59 UTC**: các lab lỗi và stack tích hợp đã dọn; jump/FIP jump/hai SG SSH tạm đã xóa. SG thêm tạm vào port deployment để đo đã được gỡ, port trở về app SG đúng template. Giữ một stack `campus-app`, DB+2 app (3 VM/3 vCPU/6144 MiB), 1 volume10 GiB và1 VIP FIP. `campus-check`14:18:54 UTC: OK; agent không Stop EC2, giờ Stop do người vận hành ghi nhật ký.

1. Kiểm HTTPS core14/11 đã đạt health200/pass và redirect302 với verify cert; cấu hình Nginx do TV1 quản lý. Ingress portal/H4b vẫn chờ đầu vào riêng.
2. TV3/TV4 nhận endpoint/UUID qua bàn giao này để chuẩn bị smoke/workload; chưa chạy benchmark tự động trước giai đoạn 6.
3. Metric/alarm giai đoạn6 được ghi bên dưới. Giai đoạn7 cần notifier/action và lượt tải tự2→3→2; H4b chờ H1b/image portal+worker, không nhận từ HTTP stub.

Evidence: [bản đọc ngắn](../../evidence/G4/20261113-FR-INF-09-tv2-heat-core-cloud.txt), [output/Request IDs/events/programs đã lọc](../../evidence/G4/20261113-FR-INF-08-tv2-heat-checks.json). File có thể chứa tên object/đường dẫn secret để mô tả giao diện, không chứa giá trị secret/token.

## Giai đoạn6 — metric CPU và alarm, 14/11/2026

Gnocchi4.7.1 trên A chạy module `/opt/stack/gnocchi/gnocchi/__init__.py`, SHA `4a41c1d05052bcabf19fbe2e5bfb5a036a321d32`. Đã kiểm CPU60s ở cả hai host, group aggregate và high/low evaluation với DevStack2026.1/Python3.12; giữ nguyên pin O-06. Không suy tương thích mọi chức năng khác chưa kiểm từ kết quả này.

Query của alarm: nhóm `campuslink-app`, đúng project, `ended_at=null` **và `deleted_at=null`**. Ceilometer trên cụm ghi thời điểm xóa vào `deleted_at`; chỉ dùng `ended_at` còn lấy VM đã xóa. Query đã nhận đủ3 khi scale-out và về đúng2 sau scale-in; B cũ có `deleted_at=2026-11-14T08:18:05Z`.

| Resource hiện tại | Metric CPU | Metric vCPUs |
| --- | --- | --- |
| A523d… / AZ-A | `123ecdaf-efc2-4815-931e-cd846de6e910` | `05418399-d872-4659-a41a-e1b71d91c229` |
| B157e… / AZ-B | `bd3a4524-7121-42ea-aba3-344525fcdd25` | `d4340a4e-0fe2-46f8-9368-ba3d6845b03a` |

`cpu` có đơn vị ns; `vcpus` là metric riêng, đơn vị vcpu, cả hai guest có1vCPU. Policy `ceilometer-high-rate` có mean/rate:mean tại60giây. CPU% được đối chiếu từ counter bằng `Δcpu_ns / (60 × 10^9 × vCPU) × 100`; raw rate trên cụm là delta ns theo bucket, không phải ns/giây.

### Hai alarm riêng và thủ tục tắt

Core update preview báo replacement listener/pool/monitor/policies, kể cả khi giữ nested type URI cũ; **không áp update lên core**. Theo phương án được duyệt, stack `campus-app-cpu-alarms` / `f5b0c4cf-558b-46b2-a4e2-c28d835fc275` chỉ quản lý hai alarm Aodh từ [alarms.yaml](../../infra/heat/alarms.yaml), không quản lý VM/LB/DB. Root tích hợp có native validate nhưng chưa được áp vào deployment đang giữ.

| Alarm | UUID | Rule |
| --- | --- | --- |
| High | `37680d7a-7c46-4cf8-a789-035c7d990219` | cpu/rate:mean,60s,gt36000000000,2periods |
| Low | `90f9060e-af83-4bba-834c-52753144421c` | cpu/rate:mean,60s,lt15000000000,3periods |

Tương ứng >60% qua2cửa sổ và <25% qua3cửa sổ; repeat_actions=false. `alarm_actions`, `ok_actions`, `insufficient_data_actions` rỗng suốt lượt kiểm. Bàn giao cuối: **enabled=false, action0** cho cả hai, đã tắt07:58:40Z.

CLI đã kiểm trên A, chỉ thực hiện trong phiên/phạm vi được duyệt:

```bash
OS_CLOUD=campus-tv2 openstack stack update --existing \
  --parameter evaluation_enabled=false --wait f5b0c4cf-558b-46b2-a4e2-c28d835fc275
```

Bật evaluation dùng cùng tham số với giá trị true; chỉ quan sát, giữ actions rỗng. Giai đoạn7 phải chốt notifier/auth và nối high/low tới đúng policy trước nghiệm thu tự scale; hiện chưa có policy URL trong output, handoff hoặc evidence. Hướng dẫn kiểm CPU tại [telemetry README](../../infra/heat/telemetry/README.md).

### Bằng chứng tải và hai phép chuyển tiếp

Hai lượt GET redirect thật bằng ApacheBench trên A, qua VIP nội bộ, không follow Location. Lượt TCP mới8470request/240s có CPU nhóm57–59%, chưa vượt high. Lượt KeepAlive8756request/240s có bucket07:47/48/49 lần lượt61,1917%/62,075%/61,975%. High chuyển ALARM **07:49:13.738777Z**. Sau hết tải, ba bucket07:51/52/53 là0,7667%/0,6167%/0,625%; low chuyển ALARM **07:54:13.692679Z**. Dùng timestamp trong **alarm history**, không dùng field state_timestamp cũ. ApacheBench failed0 ở cả hai lượt; non2xx là counter gồm302, chỉ spot probes kiểm riêng Location đúng.

Sau khi tắt alarm, scale tay07:58:41Z;3ONLINE quan sát08:01:24Z.60GET302/Location đúng, mỗi RequestID khớp đúng một guest: A21/Bcũ15/Bmới24. New B WaitCondition/ready/SUCCESS đạt, cùng image; A/B cũ không gửi lại signal sau reboot. Dọn jump/SG trước scale-in08:17:48Z, đã chờ984s sau mốc3ONLINE.08:22:32Z quan sát hai member ONLINE, A giữ UUID, B cũ88d… bị xóa và B mới157e… giữ lại.

Lab riêng lỗi DB chỉ B: A0c3bd7a8… SUCCESS/memberONLINE, B2e98a2fe… FAILURE/no ready/no member;12GET302 khớp logA. Lab và VIP riêng đã dọn07:13:25Z. Cả hai phép chuyển tiếp đều có [raw request/correlation](../../evidence/G4/20261114-FR-INF-09-tv2-redirect-carryover.json), không nhận từ batch401 hoặc stub.

SSH hai app cũ dùng ED25519 được TV1 xác minh từ disk hypervisor tại [issue42](https://github.com/luongkien25/campuslink/issues/42), không dùng TOFU. A giữ fingerprint `SHA256:chWPXeef/ZDCO9ee4smKz6ilsIAQvBvZorzmDZEzyb0`; B hiện tại157e… có fingerprint `SHA256:Acr0rxOaQt0BT5z8kLImaSx0xErhyMuV8cLPAJ32H8k`, pin từ Nova console lần boot đầu và đã SSH strict thành công.

### Trạng thái cuối và giới hạn

08:32:38Z: DB+2app (3VM/3vCPU/6144MiB),1volume10GiB,1VIPFIP,2Heatstacks(core+CPUalarm). Không còn lab/jump/FIPjump/SGSSH tạm; port app chỉ appSG, DBport/volume/attachment giữ nguyên. Env chứa credential do phiên tạo đã xóa; credential gốc không đổi. Native validate bản source cuối bằng credential giả đạt;97tests offline và review integration0Critical/0Important/0Minor. `campus-check`08:37:30Z:OK, đã export artifact và đóng SSH; agent không Stop EC2.

Chưa chứng minh FR-INF-11 tự động2→3→2: **ALARM và lượt scale tay là hai phép thử tách biệt**. Không lấy RPS/p95 từ generator trên A làm benchmark HTTPS của nhóm. Chưa fault pipeline/mất metric: bucket đang ghi từng có aggregate âm, phải loại khỏi CPU hợp lệ; `needed_overlap=0` của evaluator upstream chưa được nhận an toàn trong mọi tình huống thiếu dữ liệu. H4b/worker và ngân sách kết nối DB dưới workload đầy đủ còn thuộc phần kiểm riêng.

Evidence14/11: [bản ngắn](../../evidence/G4/20261114-FR-INF-10-tv2-metric-alarm.txt), [metric/history/preview/final checks](../../evidence/G4/20261114-FR-INF-10-tv2-metric-alarm.json), [redirect carryover](../../evidence/G4/20261114-FR-INF-09-tv2-redirect-carryover.json).

## GĐ7 — kiểm chỉ đọc ngày 15/11/2026

Hai app/DB, image, VIP và pool giữ các UUID ở trên; hai member ONLINE, cả AZ available. Collector/analyzer kiểm sáu bucket đầy đủ05:37–05:42 UTC: PASS, CPU nhóm khoảng0,62–0,71%. Đây là dữ liệu nền, không phải workload nghiệm thu autoscaling.

Đã kiểm source/plugin cho ứng viên native signal qua `trust+http`/`trust+https`; chưa tạo trust, lấy target thật, POST action hoặc update stack. `trust+heat` là autohealing, không dùng thay ScalingPolicy signal. Source evaluator còn nhận bucket chưa kết thúc/âm khi xử lý dữ liệu giả trong characterization, nên chưa đủ căn cứ bật action; TV1 xác minh/chốt qua [#47](https://github.com/luongkien25/campuslink/issues/47). Không suy phép kiểm mã thành việc daemon đã false alarm hoặc scale sai.

Hậu kiểm05:44:55 UTC: cả hai alarm disabled/actions0; campus-check05:44:56 UTC: RC0/OK. Không tạo lab/jump/FIP/SG/env thật, không thay core/DB/volume/EC2; SSH đã đóng. FR-INF-11 runtime còn chờ gate trên và workload/lịch TV4 [#44](https://github.com/luongkien25/campuslink/issues/44).

Nguồn: [evidence ngắn](../../evidence/G4/20261115-FR-INF-11-tv2-notifier-preflight.txt) và [JSON đã lọc](../../evidence/G4/20261115-FR-INF-11-tv2-notifier-preflight.json). HTTPS mới nhất TV2 đã kiểm vẫn là lượt14/11 ở trên; không nhận snapshot chỉ đọc15/11 là phép đo HTTPS mới.

## Khôi phục app A trước lượt chẩn đoán — 15/11/2026

Trước khi gửi signal, kiểm baseline phát hiện app A ACTIVE nhưng member ERROR, Shlink/readiness failed và không còn container; Redis PONG, Docker daemon active. Journal boot hiện tại ghi app đã ready06:18:11Z, sau đó service bị dừng/khởi động lại06:27:39–42Z. State bootstrap có deadline khoảng06:21:04Z, `active_state()` trả lỗi `deadline`. Chưa xác định người thực hiện lượt restart đó.

Sau khi được duyệt, TV2 restart chuỗi `campuslink-secrets` → `campuslink-guard` → `campuslink-shlink` → `campuslink-ready` trong guest A, dùng quy trình fetch sẵn có để tạo generation/deadline mới. Hoàn tất07:29:47.907645Z; HTTP200/pass, RedisPONG, container running/restarts0; boot ID không đổi. Heat signal service vẫn inactive, không gửi lại callback cũ. Hai member ONLINE lúc07:30:25Z.

Jump/FIP và hai SG SSH riêng dùng cho chẩn đoán đã dọn07:31:23Z, port A trở về SG gốc. Không đổi code/config, reboot VM/EC2 hoặc sửa SG chung. Đây là khôi phục có kiểm chứng, không phải bằng chứng autoscaling; xem [evidence đã lọc](../../evidence/G4/20261115-FR-INF-09-tv2-app-a-recovery.json).

## Chẩn đoán scale thủ công với probe CPU — 15/11/2026

Lượt này dùng signal Heat thủ công để thu dữ liệu cohort 2→3→2; không phải nghiệm thu autoscaling. Hai alarm giữ disabled, repeat_actions=false và toàn bộ action list rỗng; không thay cấu hình alarm.

| Mốc | UTC ngày 15/11/2026 | Nguồn |
| --- | --- | --- |
| Bắt đầu scale-out | 07:35:59.355796 | Trước lệnh signal; CLI rc0 |
| 3 VM ACTIVE và 3 member ONLINE | 07:38:22.507728 | Lần đầu quan sát qua API |
| Bắt đầu scale-in | 07:45:22.781320 | Trước lệnh signal; CLI rc0 |
| Trở lại 2 app/2 member ONLINE | 07:47:03.262613 | Lần đầu quan sát qua API |

Giữ 3 app 420.273592s, khoảng 7 phút. Mốc ONLINE là lần đầu quan sát, không phải thời điểm chuyển trạng thái chính xác của dịch vụ. A giữ UUID; Heat xóa B157e… và giữ Bc6d…/10.20.0.185. Metric CPU/vcpus của B mới và fingerprint ED25519 đã cập nhật inventory; fingerprint lấy từ Nova first-boot console, chưa kiểm SSH tới B mới.

Tải redirect Shlink thật từ A qua VIP HTTP, ApacheBench keep-alive/concurrency 32: 664.204 s, 23173 request hoàn tất, failed 0, non-2xx 23173, 34.89 RPS. Smoke trước/sau trả 302 đúng Location; số non-2xx không xác nhận mọi response đều 302. Bucket đóng 07:38–07:41 có CPU trung bình nhóm khoảng 40.3–40.9%, tính từ từng VM 1 vCPU. Đây là dữ liệu đối chiếu probe, không xác minh công thức evaluator Aodh với bucket chưa đủ/VM mới, không thay benchmark HTTPS/p95 của TV4.

Tải dừng 07:47:03Z; jump/FIP/hai SG SSH tạm đã dọn, mỗi port app chỉ còn app SG, DB/volume/port nền giữ nguyên. Hậu kiểm 07:50Z còn DB + 2 app, 1 volume 10 GiB, 1 VIP FIP và 2 top-level stack. `campus-check` 07:52:43Z trả 1 vì còn hai phiên SSH ubuntu, nên phải phối hợp người đang dùng trước khi Stop EC2; không diễn giải thành lỗi health app.

Evidence: [bản ngắn](../../evidence/G4/20261115-FR-INF-11-tv2-manual-probe.txt), [API/timeline/CPU/cleanup](../../evidence/G4/20261115-FR-INF-11-tv2-manual-probe.json). GĐ7 vẫn còn gate evaluator ở issue #47 và workload/phối hợp issue #44, sau đó mới kiểm notifier/action và chuỗi tự động.

## Hậu kiểm chỉ đọc và cấp key H5 — 16/11/2026

Snapshot Aodh 05:42:08Z xác nhận high state `ok` (>36e9ns/2 kỳ) và low state `alarm` (<15e9ns/3 kỳ), granularity60s, aggregation `rate:mean`; cả hai `enabled=false`, `repeat_actions=false`, ba danh sách actions rỗng. Không thay cấu hình alarm hoặc áp ADR-12. Xem [snapshot đã lọc](../../evidence/G4/20261116-FR-INF-11-tv2-alarm-config-readonly.json).

Theo yêu cầu53, tạo key admin Shlink tên `tv3-admin`, không author-only, chuyển thẳng qua pipeSSH tới `campus-secrets/ops/shlink_api_key_tv3-admin` lúc05:49:34Z. PUT201/HEAD200, độ dài37byte; API xác thực qua VIP nội bộ trả200. Không in giá trị key, không đưa vào argv hoặc evidence. Bản key tạm trong guest đã xóa. TV3 còn cần nhận vào file0600, kiểm qua HTTPS và xóa object trung chuyển theo tiêu chí H5; chưa nhận là HTTPS PASS hoặc đóng issue53.

Hậu kiểm05:56:51Z: jump/FIP/haiSGSSH riêng đã dọn, SG app giữ nguyên; DB+2app ACTIVE, hai member ONLINE, health200/pass và hai alarm vẫn disabled/actionsrỗng. `campus-check`rc0: có thể StopB→A sau khi phối hợp nhóm. Không thao tác EC2. [Evidence cấp key/cleanup](../../evidence/G4/20261116-FR-INF-16-tv2-tv3-key-handoff.json).

## Điều kiện sau Start và khi chỉ bật A — yêu cầu #56

Khi chỉ EC2 A chạy, không coi Nova app B `ACTIVE` hoặc member B `ONLINE` là bằng chứng backend B đang phục vụ. TV3 ghi nhận timeout xen kẽ khi B tắt trong lượt16/11; nguyên nhân chính xác của trạng thái health monitor chưa được xác minh. Không tái hiện tắt B trong phiên benchmark.

Quy trình mặc định trước khi dùng VIP hoặc đo NFR-03/04: bật A trước, chờ checks đạt, bật B và hoàn tất after-start; kiểm hai guest/member và gửi request thật qua HTTPS bằng kết nối mới, verify TLS. Health phải200/pass, redirect phải302 đúng Location, không timeout. Nếu chỉ bật A, không nhận hệ thống đã sẵn sàng cho benchmark hai AZ; ưu tiên bật B, không tự sửa pool/monitor hoặc tạm disable memberB trong phiên đo. Một phương án vận hành chỉ A cần được duyệt riêng và có bước khôi phục member trước benchmark.

Lượt kiểm16/11 lúc13:42:05–13:42:22Z với A/B đã bật:24requestHTTPS kết nối mới đạt (12health200/pass,12redirect302 tới fixturetv4fix1 đúng đích), không timeout. Đây là kiểm chức năng giới hạn, chưa có tương quan log từng backend và không thay benchmark/p95. [Evidence baseline](../../evidence/G4/20261116-FR-INF-11-tv2-evening-baseline.json). Việc kiểm riêng từng backend và timeline phiên tối đang tiếp tục; chưa gọi issue56 hoặc phiên đo hoàn tất.

## Baseline Aodh chưa vá dưới tải TV1 — tối 16/11/2026

TV1 phát tải từ Windows, mục tiêu30 RPS, warm-up120 s; steady bắt đầu **14:53:04Z**, yêu cầu1200 s. RUN_START14:50:59.5796622Z, RUN_END15:13:05.0281007Z do TV1 cung cấp. Probe TV1 đã xác nhận thu nền hơn9phút trước lượt. TV2 chỉ gửi request chức năng trước/sau steady; không chạy thêm workload đồng thời. Aodh giữ đúng SHA `e07aeb6d118b4b9099947028e6e809a6bdd8fe22`, cây làm việc sạch.

| Mốc | UTC ngày 16/11 | Nguồn |
| --- | --- | --- |
| Bắt đầu scale-out | 14:56:17.725232 | Trước signal thủ công, CLI rc0 |
| App mới ACTIVE | 14:57:01.314729 | Lần đầu quan sát Nova |
| Request302 khớp app mới | 14:57:02.561767 | Timestamp client TV1, ghép Request ID |
| Ba app/member ONLINE | 14:57:06.538306 | Lần đầu quan sát API |
| Bắt đầu scale-in | 15:04:06.809375 | Trước signal thủ công, CLI rc0 |
| Hai app/member ONLINE hậu kiểm | 15:07:52.252237 | Lần đầu hậu kiểm sau scale-in, không phải thời điểm engine chính xác |

Giữ 3 app khoảng 7 phút (420.271069s tính từ marker UTC). Request ID `3b405014-611f-448e-8342-06662e3bd3a2` trong CSV TV1 có302/Location `https://example.org/campuslink-fixture-3`, khớp log guest mới `6ed60f3b…`/`.102`, GET `/tv4fix3`/302 lúc 14:57:03.159917198Z. Request thực có thể tới trước lần poll thấy đủ 3 ONLINE; không sửa timestamp để ép thứ tự. Đây là request đầu khớp trong cửa sổ log đã kiểm, không suy thành thời điểm đầu tiên tuyệt đối của mọi traffic.

Low chuyển `ok` 14:55:23.019524Z và về `alarm` 15:16:23.010644Z sau dừng tải; high không có transitionALARM trong lượt. Actions luôn rỗng, repeat_actions=false. CPU bucket 14:54 trước scale-out là A 48.5333% / B 47.0833% (mỗi VM 1 vCPU); không đổi ngưỡng. Collector TV2 có 97 snapshot thành công / 98 attempt, một KeyError giữa các mẫu lúc VM mới tham gia; chưa xác minh nguyên nhân, không nhận 0 lỗi hoặc dùng collector làm guard của evaluator.

TV1 báo 36000 request, 28764 redirect 302, p50=847.38ms, p95=1080.74ms,47 lỗi 5xx/timeout (0.13056%). P95 **chưa đạt 500 ms**; ratio theo báo cáo dưới 1% không có nghĩa toàn bộ nghiệm thu hiệu năng đạt. Chỉ nhận một dòng CSV và summary do TV1 cung cấp, chưa nhận full CSV hoặc tính lại quantile. Không thu được log B`.185` trước khi Heat xóa, nên không nhận phép mapping đầy đủ 3 backend cho lượt30 RPS. Phép xác minh hai backend `.195`/`.185` trước tải đã có 32 request ghép log 15/17 trong evidence.

Evaluation bật 13:42:05Z, tắt 15:25:03Z; actions_enabled giữfalse trong mọi lần update. Cleanup 15:26:04Z xóa đúng jump/FIP/port/hai SG SSH, port app trở về app SG. Hậu kiểm 15:28:41Z giữ A`.195`+B`.102`, DB VM/volume 10 GiB và VIP gốc; health 200/pass, hai member ONLINE, cả hai alarm disabled/actions 0. HTTPS sau cleanup 8/8 đạt, verifyTLS. `campus-check` rc1 vì còn phiên/việc khác: phối hợp TV1 trước Stop B→A, không coi đây là lỗi health.

Key `tv1-load` được cấp riêng, không author-only, chuyển kín qua object `campus-secrets/ops/shlink_api_key_tv1-load`; HEAD 37 byte và GET visits của năm fixture trả 200. Bản key tạm trong guest đã xóa; không đưa giá trị vào tài liệu/evidence. Object trung chuyển dành cho TV1 nhận/xóa, chưa tự xóa hoặc revoke key.

Nguồn: [bản ngắn](../../evidence/G4/20261116-FR-INF-11-tv2-evening-baseline.txt), [API/CPU/history/client-row/guest-log/cleanup](../../evidence/G4/20261116-FR-INF-11-tv2-evening-baseline.json). Đây là baseline và scale tay đã hoàn tất; không nghiệm thu tự scale hoặc đóng gate dữ liệu #47, không áp ADR-12 lên cụm.
