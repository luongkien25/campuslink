# Metric CPU và alarm Aodh

Phần này phục vụ FR-INF-10 và NFR-05 cho Shlink core. Đã kiểm SDK, query, CPU 60 giây trên hai host và alarm Aodh bằng tải redirect thật ngày 14/11/2026. Alarm chạy trong **stack riêng**, action rỗng; không áp root update có replacement. Scale tự động bằng tải thật theo FR-INF-11 và notifier gọi Heat chưa được nghiệm thu ở lượt này.

## Kiểm offline

Dùng Python 3.12 và PyYAML đã khóa trong [requirements của lab](../lab/tests/requirements.txt). Không cần cài OpenStack SDK hoặc Gnocchi client lên laptop để chạy tests:

```bash
.venv/bin/python -B -m unittest discover -s infra/heat/telemetry/tests -v
.venv/bin/python -B -m unittest discover -s infra/heat/tests -v
.venv/bin/python -B -m unittest discover -s infra/heat/bootstrap/tests -v
.venv/bin/python -B -m unittest discover -s infra/heat/lab/tests -v
```

Tests telemetry dùng API doubles tại ranh giới client và fixture CPU giả. Tests HOT kiểm payload/intrinsics được sử dụng; không chạy engine Heat, evaluator hoặc notifier Aodh. Tests HTTP chạy trên localhost.

## Thu snapshot trên A

Chỉ thực hiện trong phiên cloud đã xác nhận Zalo, A/B và nhật ký. Dùng user Linux `tv2` và cloud `campus-tv2`; không dùng credential admin hoặc cài lại client dùng chung khi gặp lỗi.

[`collect_metrics.py`](collect_metrics.py) dùng OpenStack SDK và gnocchiclient có sẵn trên A. Nó xác nhận project của session, tìm resource `instance` có `server_group=campuslink-app`, đúng project, `ended_at=null` **và `deleted_at=null`**, rồi lấy metric `cpu`, archive policy và hai chuỗi `mean`/`rate:mean` trong tối đa một giờ. Mỗi request có session timeout; lỗi SDK/API chỉ in thông báo cố định, không in exception hoặc response gốc.

**Giao diện collector đã kiểm trên A:** thay project và mốc UTC bằng giá trị thật từ inventory/phiên đo; không sao chép nguyên placeholder để chạy.

```bash
OS_CLOUD=campus-tv2 /opt/stack/data/venv/bin/python3 telemetry/collect_metrics.py \
  --project REPLACE_PROJECT_UUID \
  --start REPLACE_START_UTC --stop REPLACE_STOP_UTC > cpu-snapshot.json
```

Lệnh giả định thư mục hiện tại là bản `infra/heat` đã chuyển lên A. Đã đối chiếu gnocchiclient 7.2.0, OpenStack SDK 4.10.0 và Keystoneauth 5.13.1 trong venv trên A. `Client` nhận `adapter_options`, không nhận trực tiếp `interface`/`region_name`. Không có fallback sang cloud khác khi thiếu quyền hoặc SDK.

Resource `instance` thực không có thuộc tính `vcpus`: collector đọc metric `vcpus` đơn vị `vcpu`, yêu cầu mẫu tương ứng với các bucket CPU và số vCPU ổn định, nguyên dương. Client trình bày thời lượng archive policy bằng chuỗi như `0:01:00` hoặc `1 day, 0:00:00`; collector chuẩn hóa về giây. Mốc bắt đầu được căn xuống phút trước request vì API trả bucket chứa mốc đó.

`ended_at=null` riêng lẻ còn trả VM đã xóa trên cụm này. Ceilometer ghi thời điểm xóa vào thuộc tính `deleted_at`; ví dụ VM `800623d1-dab5-4215-a931-4da91a2d3b2a` có `deleted_at=2026-11-13T13:55:27Z` nhưng `ended_at=null`. Query phải kiểm cả hai trường; không suy từ tên trường rằng nó đã được cập nhật.

Snapshot chỉ giữ UUID, project/group/vCPU, unit, định nghĩa archive policy và các điểm timestamp/granularity/value/aggregation. Không giữ credential, token, auth response, user-data hay alarm actions. Schema thiếu field/unit khác dự kiến sẽ báo lỗi thay vì đoán. Snapshot không tự chứng minh tập VM đúng: analyzer còn cần danh sách UUID app thực từ Nova/Heat.

## Kiểm CPU và độ mới dữ liệu

[`analyze_cpu.py`](analyze_cpu.py) nhận snapshot đã lọc, UUID app kỳ vọng, mốc đánh giá UTC và giới hạn tuổi dữ liệu theo polling/ingestion delay đã đo. Cần ít nhất bảy điểm counter `mean` và sáu bucket `rate:mean` liên tục 60 giây, đồng bộ giữa tất cả VM. Collector bỏ bucket chưa kết thúc; analyzer từ chối bucket đang ghi, thiếu/gap/trùng/đảo timestamp, counter reset, sai project/group, VM đã ended hoặc tập VM thừa/thiếu.

```bash
/opt/stack/data/venv/bin/python3 telemetry/analyze_cpu.py cpu-snapshot.json \
  --expect-guest REPLACE_APP_A_UUID --expect-guest REPLACE_APP_B_UUID \
  --now REPLACE_EVALUATION_UTC --max-age-seconds REPLACE_MEASURED_MAX_AGE \
  --rate-semantics delta-ns
```

Lựa chọn `delta-ns` đã đối chiếu với counter và source trên cụm ngày 14/11. Khi tái lập trên cụm/version khác vẫn phải kiểm lại. Analyzer đối chiếu hai chuỗi với sai số số học tối đa `max(1000 ns, 0.0001% × delta)`; không tự đoán đơn vị. Nếu nguồn dữ liệu thực không có quan hệ đó, giữ kết quả chưa kiểm và điều chỉnh phép đối chiếu từ evidence/source, không nới ngưỡng để nhận PASS.

CPU% được tính từ counter: `Δcpu_ns / (Δt_seconds × 10^9 × vCPU) × 100`. Với 1 vCPU và bucket 60 giây:

| Cách biểu diễn rate đã xác minh | High >60% | Low <25% |
| --- | --- | --- |
| Delta ns mỗi bucket (`delta-ns`) | 36000000000 | 15000000000 |
| Ns mỗi giây (`ns-per-second`) | 600000000 | 250000000 |

Analyzer kiểm từng VM rồi báo trung bình CPU% giữa các VM, không cộng phần trăm khi thêm replica. `campus.app` thực có 1 vCPU theo SRS và metric đã kiểm. Aodh trên cụm dùng operations `['aggregate', 'rate:mean', ['metric', 'cpu', 'mean']]`, `needed_overlap=0`; đã đối chiếu bucket đầy đủ của hai app với công thức ns/60 giây. Tập VM thay đổi vẫn cần kiểm metadata, query và độ mới dữ liệu trước các lượt scale.

`high_state`/`low_state` trong báo cáo chỉ là phép kiểm cửa sổ offline: high vượt 60% ở cả hai bucket cuối; low dưới 25% ở cả ba bucket cuối. Thiếu/sai dữ liệu trả `insufficient data`, không trả CPU 0. Đây không phải alarm history thật hay bảo đảm evaluator Aodh dùng cùng cách xử lý missing data.

## Tham số alarm và các bước bật

[`root.yaml`](../root.yaml) thêm nested [`alarms.yaml`](../alarms.yaml); định nghĩa VM, ASG-B, LB và ScalingPolicy hiện hữu giữ nguyên. Ngưỡng gắn với flavor 1 vCPU; granularity 60, periods high 2/low 3, cooldown ScalingPolicy 180 và `repeat_actions=false`. `ok_actions` và `insufficient_data_actions` rỗng.

| Root parameter | Mặc định | Điều kiện sử dụng |
| --- | --- | --- |
| `alarms_enabled` | false | Cho phép evaluation sau khi đạt các kiểm dưới đây |
| `telemetry_verified` | false | Chỉ true khi đã kiểm rate, aggregation, query và tập app hiện tại |
| `telemetry_project_id` | chuỗi rỗng | UUID project dạng 32 ký tự hex, từ session thật |
| `cpu_rate_semantics` | unverified | Chọn delta-ns hoặc ns-per-second theo số đo/source |
| `scaling_actions_enabled` | false | Giai đoạn metric/alarm giữ false để chỉ quan sát |
| `scaling_action_transport` | unverified | Native/signed chỉ sau kiểm notifier/auth tương ứng |

Evaluation chỉ bật khi `alarms_enabled` và `telemetry_verified` cùng true, có project và rate semantics đã chọn. Action còn cần flag riêng và transport khác unverified. Helper [`make_app_env.py`](../make_app_env.py) từ chối cấu hình bật chưa đủ điều kiện trước khi đọc/publish env thật. Các flag là xác nhận vận hành, không tự kiểm được trạng thái cloud.

Parent lấy action trực tiếp từ ScalingPolicy qua intrinsic: `signal_url` cho native API, `alarm_url` cho signed URL. Chưa chọn transport trên cụm; cả hai chỉ là nhánh cấu hình được kiểm offline. Khi action chưa được phép, parent chuyển chuỗi rỗng; nested template không gọi action. Không truyền webhook qua env mẫu, không output URL hoặc dùng URL làm lệnh copy/paste. Nếu kiểm notifier/auth cần thêm quyền hay cơ chế chưa được duyệt, chuyển TV1 quyết định trước.

Hai alarm vẫn được khai báo dù mặc định disabled: **disabled không có nghĩa là không tạo resource Aodh**. Cần kiểm member có quyền tạo, schema native và query trên A trước CREATE/UPDATE.

## Áp dụng và thu evidence cloud

1. Kiểm schema/help/source bằng member; lấy metric A/B, archive policy có 60 giây/mean/rate:mean; xác minh timestamp/đơn vị và đúng resource. Thiếu sample hoặc 403 chuyển TV1, không sửa pipeline hay restart service nền.
2. Kiểm query nhận app mới và loại VM đã xóa. Fixture lỗi DB có group `campuslink-tv2-negative-a/b`, không dùng group core. Phải xác minh bộ lọc `deleted_at` và `ended_at` thực sự loại VM đã xóa; nếu không, giữ alarm tắt trước khi chốt phương án lọc đúng.
3. Native validate và preview root update trên core 2 app. Chỉ áp trong phạm vi được duyệt nếu không replace/reset VM/WaitCondition/ASG/LB/policy. Preview lỗi hoặc không rõ thì dừng, không tự xóa/tạo lại core. Root update đã có rủi ro replacement trong [H4](../../../docs/handoffs/H4-heat-lb-scaling.md).
4. Kiểm hai alarm disabled/actions rỗng sau áp. Ghi UUID thật; chưa có ID mới trong inventory cho đến khi bước này đạt.
5. Bật shadow evaluation với actions vẫn rỗng. Phối hợp TV4 chạy tải Shlink thật, không trùng backup/build; không CPU spin, không hạ threshold chữa thiếu metric. Thu metric và history thực, che các action/URL khỏi output.
6. Chốt giai đoạn này: trả alarm disabled/actions rỗng, giữ core 2 app, dọn lab/jump/SG tạm và kiểm baseline. Bật action và chứng minh load → ALARM → Heat → ready → traffic là bước riêng của giai đoạn autoscaling thật.

## Deployment alarm riêng đã kiểm ngày 14/11/2026

Core preview báo replacement listener/pool/monitor và ScalingPolicy, kể cả khi giữ nguyên nested type URI cũ. Không áp update đó. Theo phương án được duyệt, tạo stack `campus-app-cpu-alarms` (`f5b0c4cf-558b-46b2-a4e2-c28d835fc275`) trực tiếp từ `alarms.yaml`; stack này chỉ quản lý hai alarm, không quản lý VM/LB/DB.

| Alarm | UUID | Điều kiện |
| --- | --- | --- |
| High | `37680d7a-7c46-4cf8-a789-035c7d990219` | `rate:mean > 36000000000`, 2 cửa sổ 60 giây |
| Low | `90f9060e-af83-4bba-834c-52753144421c` | `rate:mean < 15000000000`, 3 cửa sổ 60 giây |

Tải GET redirect bằng ApacheBench trên host A, hai lượt 240 giây riêng biệt: kết nối TCP mới và KeepAlive. Lượt KeepAlive có bucket CPU nhóm 61,1917% và 62,075%; high chuyển ALARM lúc **07:49:13.738777 UTC**. Sau dừng tải, ba bucket 0,7667%/0,6167%/0,625% làm low chuyển ALARM lúc **07:54:13.692679 UTC**. Action rỗng trong toàn bộ phép đo; hai app không tự scale. Đây là kiểm CPU/alarm nội bộ, không phải benchmark HTTPS hoặc nghiệm thu RPS/p95 của TV4.

Đã trả hai alarm về `enabled=false`, action rỗng lúc **07:58:40 UTC**. CLI đã dùng trên A cho stack riêng:

```bash
OS_CLOUD=campus-tv2 openstack stack update --existing \
  --parameter evaluation_enabled=false --wait f5b0c4cf-558b-46b2-a4e2-c28d835fc275
```

Bật evaluation dùng cùng giao diện với `evaluation_enabled=true`; chỉ chạy trong phiên cloud/phạm vi đã được duyệt. Không bật `actions_enabled`, không truyền policy URL khi chưa kiểm notifier và lập lượt autoscaling thật. Giá trị group/project/high/low của stack riêng phải được giữ nguyên khi đổi flag.

Lấy thời điểm chuyển trạng thái từ **alarm history**. Field `state_timestamp` của API trong lượt này vẫn giữ giá trị cũ; không dùng nó làm thời điểm ALARM. Aodh bổ sung bộ lọc quyền project vào query gốc; các điều kiện group/project/ended/deleted vẫn phải có.

Một bucket đang ghi từng trả aggregate âm khi các replica chưa có đủ điểm đồng thời. Analyzer từ chối bucket chưa hoàn tất; không dùng điểm âm đó như CPU thấp hợp lệ. `needed_overlap=0` là hành vi evaluator upstream đã đọc, không phải bằng chứng mọi tình huống mất metric đều an toàn cho scale-in. Chưa cố tình làm hỏng pipeline/mất metric trên nền chung; phần fault này vẫn cần kiểm riêng trước kết luận toàn diện.

Hai phép đo redirect chuyển tiếp dùng [`probe_app_pool.py`](../probe_app_pool.py): `--report` chấp nhận batch redirect đã lưu có status 302, `location_matches_target=true` và Request ID hợp lệ để đối chiếu guest logs mà không phát request mới. Boolean chỉ ghi việc so sánh Location với đích trong lệnh probe, không in header Location tùy ý; khi lưu evidence phải ghi đích fixture và lệnh đã dùng. Nếu upstream redirect không có ID dùng được, chưa có phép tương quan được xác minh và không báo PASS từ batch 401 khác.

Nguồn tham khảo: [Heat 2026.1 resource reference](https://docs.openstack.org/heat/2026.1/template_guide/openstack.html), [Aodh 2026.1 alarms](https://docs.openstack.org/aodh/2026.1/admin/telemetry-alarms.html), [OpenStack SDK 2026.1 config](https://docs.openstack.org/openstacksdk/2026.1/user/config/reference.html). Tài liệu đúng nhánh không thay kiểm version/client/source thực trên cụm.
