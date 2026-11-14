# Heat app core và scale thủ công

Chủ sở hữu: TV2. Yêu cầu FR-INF-07/08/09, FR-INF-22 và NFR-08; hợp đồng ứng dụng ở [app-integration.md](app-integration.md), [H1](../../docs/handoffs/H1-shlink.md), quyết định callback ở [ADR-10](../../docs/decisions/ADR-10-cap-secret-swift-va-credential-hep.md).

## Phạm vi và trạng thái

`root.yaml` tạo LB OVN TCP 8080, một app cố định tại AZ-A và ASG-B min 1/max 2 tại AZ-B, ban đầu tổng2 app. Hai ScalingPolicy tăng/giảm một unit để kiểm tổng2→3→2. Network, subnet, app SG, image, DB/Redis và volume dữ liệu là đầu vào ngoài stack. App không FIP; chỉ VIP có FIP nội bộ172.24.4.x để Nginx trên A truy cập.

Đã có implementation, 73 tests offline và kiểm tích hợp trên Heat 2026.1: validate root/nested, negative A/B, callback timeout và scale tay 2→3→2. [Evidence cloud](../../evidence/G4/20261113-FR-INF-09-tv2-heat-core-cloud.txt) phân biệt stack tích hợp đã dọn với deployment giữ lại. Image core giai đoạn 4 có evidence riêng; kết quả clone không thay phép kiểm callback/member/scale. Portal/worker và listener8081 thuộc H4b, cần H1b và image mở rộng; telemetry/alarm thuộc giai đoạn 6.

Image đầu vào đã kiểm là `campus-app-tv2-g4-20261111`, UUID `2c43a06d-1db8-4c01-bd31-98803325d932`; kiểm lại active/min_disk10GiB và manifest trước mỗi phiên. Dùng `campus.app` và keypair cá nhân đã import; không bake credential vào image hoặc pull Shlink lúc boot.

## Lifecycle của mỗi app unit

```text
handle TOKEN_SIGNAL → CloudConfig → VM private
  → activate bootstrap → secrets → metadata guard → Shlink/migration
  → local health + Redis PONG → signal → WaitCondition → member
DELETE: member → delay → VM → port
```

CloudConfig chuyển code callback/units mới qua `get_file` để dùng được image giai đoạn 4. Bootstrap thật chỉ được activate sau khi ghi đủ config/drop-in và reload systemd; Docker bị dừng trong guest mới trước activation. Docker kéo chuỗi runtime; chỉ lần CREATE gọi signal unit. Sau reboot hoặc restart Docker, runtime vẫn tự phục hồi nhưng không gửi lại handle cũ.

Readiness có budget180s từ attempt activation, đồng thời tuân deadline180s từ fetch; không cộng budget từng bước. SUCCESS cần cùng boot/generation, guard đúng thứ tự, HTTP 200/status=pass và Redis PONG tại thời điểm gửi. WaitCondition timeout 300s theo ADR-10 dùng mốc engine riêng. ACK200 mới là xác nhận gửi; phải kiểm WaitCondition COMPLETE và member sau đó. Lỗi bootstrap gửi FAILURE bằng handler độc lập; không gửi được thì Heat timeout, không thêm member.

Token chỉ nằm trong file root0600 ở thư mục0700, header curl qua file, payload qua stdin; descriptor bị xóa khi kết thúc lượt gửi. Xóa file trong VM không có nghĩa token đã được thu hồi trên Keystone hoặc xóa khỏi user-data lưu bởi Heat/cloud-init. Token hết hạn hoặc user bị xóa theo vòng đời stack; reader/member vẫn có thể đọc attribute token theo rủi ro đã ghi ở ADR. Không dùng `curl_cli`, không dump token/endpoint/config/user-data hoặc full stack parameters.

`drain_seconds` mặc định5 là đề xuất H1, chưa phải số đo đảm bảo request đang chạy. `OS::Heat::Delay` chỉ chạy khi DELETE; graph yêu cầu member bị gỡ trước delay và server. Đã đọc source plugin Octavia xử lý conflict bằng poll và đo delete thực tế; chưa ép riêng lỗi409 để stress; rolling_updates batch1 chỉ áp cho replacement, không chứng minh mọi mutation LB được serialize.

## Kiểm thử offline

Từ repo root, dùng venv đã có và PyYAML đã khóa trong `lab/tests/requirements.txt`:

```bash
.venv/bin/python -B -m unittest discover -s infra/heat/bootstrap/tests -v
.venv/bin/python -B -m unittest discover -s infra/heat/tests -v
.venv/bin/python -B -m unittest discover -s infra/heat/lab/tests -v
```

Tests mở HTTP server localhost và dùng credential giả. Không gọi systemctl/Docker/firewall thật trên laptop. Tests HOT kiểm graph/ownership/interface và file references, không thay `openstack orchestration template validate` trên A.

## Chuẩn bị env trên A

Chỉ thực hiện trong phiên cloud đã được xác nhận Zalo/A/B/nhật ký. Chuyển cây `infra/heat/` và `app/shlink.env.example` giữ nguyên đường dẫn tương đối bằng allowlist code; credential cá nhân giữ trên A, không tải về laptop. Cú pháp validate/signal và helper đã kiểm trên A trong phiên13/11. Vẫn kiểm `--help` khi môi trường thay đổi; chỉ chạy thao tác thay trạng thái trong phiên được duyệt.

Helper Python chỉ nhận đường dẫn credential, tái dùng parser giai đoạn 4, xuất env JSON hợp lệ với Heat, mode0600 và không ghi đè. Thư mục cha phải thuộc user hiện tại và mode0700. Thay toàn bộ `REPLACE_...` bằng inventory/keypair đã kiểm trước khi chạy:

```bash
python3 infra/heat/make_app_env.py \
  --credential-file /home/tv2/.config/openstack/campus-boot.cred \
  --out /home/tv2/.config/openstack/app-env.yaml \
  --app-image 2c43a06d-1db8-4c01-bd31-98803325d932 \
  --app-network REPLACE_NETWORK_UUID \
  --app-subnet REPLACE_SUBNET_UUID \
  --app-security-group REPLACE_APP_SG_UUID \
  --key-name REPLACE_PERSONAL_KEYPAIR
```

`--diagnostic-sg REPLACE_TEMP_SG_UUID` tùy chọn để gắn thêm SG SSH tạm đã được duyệt vào port app. Mặc định rỗng. Không sửa SG chung hoặc tạo FIP cho app; đường SSH private đi qua jump đã duyệt. Chỉ dùng tham số SG chẩn đoán cho stack lab sẽ dọn. Source ASG trên cụm gọi rolling replacement khi thay định nghĩa resource; preview có thể kéo theo replacement listener/pool/policies và preview nested đang lỗi400. Vì vậy không nhận SG-only root update là thao tác giữ nguyên VM. Deployment giữ lại được CREATE với danh sách rỗng; khi cần kiểm guest, tạm gắn SG SSH vào đúng port app bằng Neutron, giữ app SG, rồi gỡ và đối chiếu port trở về cấu hình template trước khi xóa SG. Không để drift hoặc tham chiếu SG đã xóa trong Heat.

## Trình tự phiên cloud

1. Kiểm baseline UUID DB/volume/port/network, quota, AZ, image và SG. Kiểm schema WaitCondition/Handle/Delay/ASG/ScalingPolicy/Octavia bằng `resource type show` và source đúng nhánh trên A; không hiển thị signal attributes. TV1 đã kiểm nền token ở #34; TV2 kiểm từ VM thật tới `10.11.0.10:80/heat-api/...`.
2. Validate bằng env fixture giả trước. Cú pháp đã kiểm trên A ngày 13/11: `openstack orchestration template validate -t infra/heat/root.yaml -e REPLACE_FAKE_ENV_PATH`. Không dùng env secret thật nếu CLI trả lại parameters trong output.
3. Chạy negative riêng từng case trước core. `tests/fixtures/make_negative.py --fault a|b --out REPLACE_NEW_DIRECTORY` tạo bản sao standalone và chỉ thay DB_HOST trong app_env của A hoặc B thành localhost. A lỗi: không có member/ASG-B. B lỗi: A đã ready/member, B không được thêm. Tạo và dọn đúng từng stack thử; không dừng DB/Redis chung hoặc signal SUCCESS thủ công.
4. Tạo core stack sau khi các case đạt. Lệnh **thay đổi trạng thái, cần duyệt phiên** và kiểm help trước: `openstack stack create -t infra/heat/root.yaml -e REPLACE_PRIVATE_ENV_PATH campus-app`. Thu timeline thật A→B; kiểm đủ2 app đúng AZ, không FIP, guard/HTTP/Redis đạt.
5. Bàn giao VIP FIP:8080 cho TV1 nối ingress, kiểm HTTPS với verify cert. TV2 không sửa Nginx trên A.
6. Signal policy bằng member OSC, **thay đổi trạng thái; cú pháp đã kiểm trên A ngày 13/11**: `openstack stack resource signal campus-app scale_out`, rồi kiểm B tăng1→2/tổng3 và member mới chỉ xuất hiện sau readiness. Đợi cooldown≥180s thật; signal `scale_in`, kiểm tổng2, gỡ member trước xóa VM và fixed A giữ UUID. Root outputs chỉ có logical policy names, không signed URL.
7. Dọn negative/spike/jump/SG tạm theo UUID và quyền đã duyệt. Core ở2 app có thể giữ cho giai đoạn 6 nếu được đồng ý; ghi đúng baseline còn DB+2app và VIP FIP. Nếu xóa core, kiểm DB/port/volume còn nguyên. Chạy campus-check, phối hợp Zalo trước Stop B rồi A; agent không tự Stop EC2.

## Probe và timeline

`probe_app_pool.py` mở TCP mới từng request. Probe không API key tới `/rest/v3/short-urls` đòi401 và Request ID khác nhau. Kết quả này chỉ chứng minh HTTP auth-deny; phải đối chiếu Request ID với log từng guest để chứng minh phân phối backend. Thiếu guest hit hoặc một ID khớp nhiều guest là FAIL. Redirect smoke riêng đòi302 đúng Location và không follow.

```bash
python3 infra/heat/probe_app_pool.py --url http://REPLACE_VIP_FIP:8080 \
  --host s.44-198-215-187.sslip.io --count 60 > REPLACE_SAFE_REPORT_PATH
```

Chỉ trích Request ID và guest UUID/IP/UTC từ Docker JSON log, không ghi raw body hoặc config. Hàm `correlate(request_ids, per_vm_logs, expected_guests)` nhận map UUID→danh sách ID đã lọc và đòi đủ mọi guest dự kiến; cùng ID phải khớp chính lượt probe đó. Không yêu cầu tỷ lệ50/50 hoặc sửa Shlink trả backend giả.

Sau khi thu log của chính lượt probe trên thành JSON map UUID→danh sách Request ID, đối chiếu report đã lưu mà không gửi request mới:

```bash
python3 infra/heat/probe_app_pool.py --report REPLACE_SAFE_REPORT_PATH \
  --guest-request-ids REPLACE_FILTERED_GUEST_IDS_PATH \
  --expect-guest REPLACE_VM_A_UUID --expect-guest REPLACE_VM_B_UUID
```

Ở mức3 app thêm `--expect-guest` cho VM B mới. Lượt probe riêng chỉ nhận HTTP đạt; chỉ khi bước đối chiếu đủ backend đạt mới có bằng chứng phân phối.

`collect_app_timeline.py` tổng hợp JSON event đã chuẩn hóa, không tự suy mốc từ trạng thái hiện tại. Mỗi event có đúng `instance_id`, `event`, `utc`; event lần lượt là `vm_active`, `local_ready`, `signal_ack`, `wait_complete`, `member_active`, `first_request`. Timestamp UTC có timezone. Thiếu/trùng mốc hoặc vi phạm quan hệ nhân quả khiến báo FAIL: VM ACTIVE→local ready; local ready→ACK; local ready→WaitCondition→member→request. ACK phía client và WaitCondition phía engine không có thứ tự bắt buộc: engine có thể hoàn tất trước khi client nhận ACK, và event Heat chỉ có độ phân giải giây. Nguồn và độ phân giải từng mốc phải lưu trong evidence. Provider không trả ONLINE thì ghi trạng thái thật và đo traffic riêng, không tạo giá trị ONLINE giả.

## Giới hạn và bàn giao

Đường được triển khai cho giai đoạn 5 là CREATE và policy grow/shrink tạo app unit mới. Chưa hỗ trợ raw Nova rebuild hoặc update image/bootstrap credential/user-data trên unit tồn tại: các thao tác này có thể thay VM mà giữ WaitCondition cũ COMPLETE. Cần thủ tục tạo handle/condition mới và phép kiểm riêng trước thực hiện. Không root update tùy tiện giữa lượt scale vì desired_capacity có thể được áp lại.

[H4](../../docs/handoffs/H4-heat-lb-scaling.md) đã có UUID/endpoint/policies và timeline cloud thật; inventory không nhận UUID lab đã xóa làm app đang chạy. Scale tay chưa chứng minh alarm/benchmark hoặc fault run toàn nhóm. Image portal/worker, H4b, telemetry/Aodh và công cụ campus-chaos/DR đang review thuộc các vòng sau; không tự đưa yêu cầu chưa merge thành phần core đã nghiệm thu.
