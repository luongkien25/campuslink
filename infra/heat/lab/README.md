# Lab cân bằng tải OVN với hai HTTP backend

Lab kiểm tra hai listener TCP 8080/8081 trên cùng LB Octavia OVN và VIP đến hai Nova VM, mỗi VM ở một AZ (O-13). Mỗi VM chạy hai HTTP stub: cổng 8080 trả nhãn `app-a`/`app-b`; cổng 8081 trả `portal-a`/`portal-b` để phát hiện nối nhầm pool.

Lab sử dụng HTTP stub, không chạy Shlink. Kết quả của lab hỗ trợ kiểm chứng FR-INF-07; không thay thế nghiệm thu readiness DB/Redis, image ứng dụng hoặc autoscaling.

## Thành phần và đầu vào

| File | Chức năng |
| --- | --- |
| `root.yaml` | Một LB OVN/VIP/FIP, hai listener TCP 8080/8081, mỗi listener có pool `SOURCE_IP_PORT` và TCP monitor; hai app unit |
| `stub-unit.yaml` | Một port private, VM, cloud-config chạy hai stub và hai pool member đúng cổng |
| `stub.py` | HTTP server nhận diện backend; Python standard library |
| `sample_lb.py` | Gửi nhiều kết nối mới, tổng hợp backend và lỗi; Python standard library |
| `tests/` | Tests HTTP local và kiểm tra hợp đồng cấu trúc template; dùng PyYAML |

Thông số mặc định được đối chiếu với [H2](../../../docs/handoffs/H2-project-mang-flavor-sg-image.md); xác nhận lại trên môi trường trước khi tạo stack:

| Parameter | Mặc định / đầu vào |
| --- | --- |
| `app_image` | `ubuntu-noble-base`, Ubuntu 24.04 có Python 3, cloud-init và systemd |
| `app_flavor` | `campus.app`: 1 vCPU, 2 GiB RAM, 10 GiB đĩa |
| `key_name` | Bắt buộc: tên keypair Nova của user tạo stack, không phải đường dẫn private key |
| `app_network` / `app_subnet` | `campus-net` / `campus-subnet`, MTU 1400 |
| `app_security_group` | `campus-app-sg`, cần cho TCP 8080 **và 8081** từ `10.20.0.0/24` và `172.24.4.0/24`; xác minh trước tạo |
| `external_network` | `public`, mạng ảo OpenStack 172.24.4.0/24 |
| `az_a` / `az_b` | `campus-az-a` / `campus-az-b` |

Stack sử dụng **hai VM, hai vCPU, 4 GiB RAM và một FIP** của project dùng chung. Hai VM dùng đĩa ephemeral theo flavor, không tạo Cinder volume. Phải kiểm tra quota và lượng tài nguyên đang dùng trước khi chạy. Không thay đổi mạng, SG, DB port hoặc volume dữ liệu hiện có.

FIP chỉ gắn VIP của LB. VM không có FIP. Truy cập FIP 172.24.4.x từ host A; địa chỉ này không được AWS route trực tiếp từ laptop.

## Kiểm tra offline

Chạy ở thư mục gốc repository trên máy cá nhân. Các bước tạo venv/cài package thay đổi môi trường local, không kết nối cloud:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r infra/heat/lab/tests/requirements.txt
.venv/bin/python -B -m unittest discover -s infra/heat/lab/tests -v
```

Nếu đã có venv riêng, dùng interpreter của venv đó thay `.venv/bin/python`. Tests mở HTTP server tạm trên `127.0.0.1`; cần môi trường cho phép socket loopback. Tests cấu trúc không thay thế xác minh schema và triển khai bằng Heat.

Có thể thử backend độc lập trong một terminal:

```bash
python3 infra/heat/lab/stub.py --backend app-a --bind 127.0.0.1 --port 8080
```

Trong terminal khác:

```bash
python3 infra/heat/lab/sample_lb.py http://127.0.0.1:8080/ --expect app-a --requests 5
```

Đây là kiểm tra một backend local, không chứng minh LB hoặc placement xuyên host. Dừng server bằng Ctrl+C.

## Chuẩn bị phiên cloud

Tuân thủ [runbook bật/tắt](../../../docs/runbooks/start-stop.md): báo sử dụng trên Zalo trước khi SSH; người bật máy ghi nhật ký cloud. A phải sẵn sàng trước B. Mọi thao tác tạo/xóa stack hoặc thay đổi tài nguyên dùng chung phải được xác nhận trước khi thực hiện.

Kết nối A bằng Linux user riêng và cấu hình Keystone riêng:

```bash
ssh campus-a
export OS_CLOUD=campus-tv2
openstack --version
```

Nếu CLI không nằm trong PATH, kiểm tra đường dẫn CLI theo H2 và `ops/ai-snapshot.sh`. Không source `openrc` hoặc dùng credential admin. Không đọc/in `clouds.yaml`, private key hoặc cấu hình dịch vụ chứa secret.

### Xác minh CLI và schema

Chạy `--help` trên CLI đã cài trước khi sử dụng cú pháp dưới đây. Không tiếp tục nếu thiếu plugin hoặc bị 403; chuyển lỗi về phần quản trị nền.

```bash
openstack server list --help
openstack quota show --help
openstack keypair list --help
openstack loadbalancer provider list --help
openstack orchestration resource type show --help
openstack orchestration template validate --help
openstack stack create --help
openstack stack delete --help
```

Đọc tài nguyên và quyền hiện tại; các lệnh dưới không chủ đích thay đổi cloud:

```bash
openstack server list
openstack quota show
openstack floating ip list
openstack keypair list
openstack availability zone list --compute
openstack network show campus-net -c mtu
openstack image show ubuntu-noble-base -c status
openstack loadbalancer provider list
openstack security group rule list campus-app-sg
```

Nếu SG chưa cho TCP 8081 từ hai CIDR nội bộ trên, chuyển TV1 bổ sung, không tự sửa SG nền hoặc tạo stack rồi chờ. [Issue #19](https://github.com/luongkien25/campuslink/issues/19) theo dõi đầu vào này. Không mở 8081 ra Internet.

Kiểm tra schema cho `OS::Octavia::LoadBalancer`, `OS::Octavia::Listener`, `OS::Octavia::Pool`, `OS::Octavia::HealthMonitor`, `OS::Octavia::PoolMember`, `OS::Neutron::Port`, `OS::Neutron::FloatingIP`, `OS::Nova::Server` và `OS::Heat::CloudConfig`. Ví dụ:

```bash
openstack orchestration resource type show OS::Octavia::LoadBalancer
```

Nếu chưa có keypair Nova, thực hiện bước import public key riêng sau khi duyệt và kiểm `openstack keypair create --help`. Public key phải đúng với key SSH của người vận hành; không đưa private key lên A.

### Chuyển file lab lên A

Các lệnh sau **tạo thư mục và ghi file trong home của user trên A**. Chỉ chạy sau khi xác nhận phiên cloud và phạm vi ghi; kiểm thư mục đích chưa chứa thay đổi cần giữ lại. Chạy từ thư mục gốc repository trên máy cá nhân:

```bash
ssh campus-a 'mkdir -p "$HOME/campuslink-tv2-lab"'
scp infra/heat/lab/root.yaml infra/heat/lab/stub-unit.yaml infra/heat/lab/stub.py infra/heat/lab/sample_lb.py campus-a:campuslink-tv2-lab/
```

Không cần cài PyYAML lên A để chạy stub hoặc sampler. Môi trường OpenStack CLI trên A phải do phần quản trị nền cung cấp.

## Tạo và kiểm tra stack

Sau khi đối chiếu `--help` và schema, chạy từ thư mục `~/campuslink-tv2-lab` trên A. Thay `REPLACE_KEYPAIR_NAME` bằng keypair thật. Chưa tạo tài nguyên ở bước validate:

```bash
cd ~/campuslink-tv2-lab
openstack orchestration template validate --template root.yaml --parameter key_name=REPLACE_KEYPAIR_NAME
```

Validate thành công không chứng minh cloud-init hoặc backend đã hoạt động. Nếu validate chưa nhận parameter theo cú pháp trên, dùng đúng cú pháp được `--help` của CLI tại A công bố.

Lệnh tiếp theo **tạo hai VM, một LB, hai listener/pool/monitor, bốn member, port và một FIP**, chỉ thực hiện sau khi duyệt và SG đã đủ hai cổng:

```bash
openstack stack create --template root.yaml --parameter key_name=REPLACE_KEYPAIR_NAME --timeout 20 tv2-lb-lab
```

Không dán lệnh tạo hai lần. Ghi UUID stack; các thao tác tiếp theo dùng UUID, không dựa vào tên có thể trùng.

Sau khi gửi yêu cầu tạo, đặt các biến bằng UUID đọc từ output thật. Theo dõi trạng thái cho đến `CREATE_COMPLETE` hoặc `CREATE_FAILED`; không chạy phép thử traffic khi stack còn đang tạo:

```bash
LAB_STACK_ID=REPLACE_STACK_UUID
openstack stack show "$LAB_STACK_ID" -c stack_status
openstack stack resource list --nested-depth 2 "$LAB_STACK_ID"
openstack stack output show "$LAB_STACK_ID" lb_id
openstack stack output show "$LAB_STACK_ID" pool_id
openstack stack output show "$LAB_STACK_ID" portal_pool_id
openstack stack output show "$LAB_STACK_ID" vip_fip
openstack stack output show "$LAB_STACK_ID" app_a_id
openstack stack output show "$LAB_STACK_ID" app_b_id
```

Kiểm `CREATE_COMPLETE`, LB provider `ovn`/`ACTIVE`, hai listener TCP trên cùng LB/VIP, hai pool `SOURCE_IP_PORT`, hai TCP monitor và bốn member `ONLINE`. Member của pool 8080 phải trỏ guest:8080; pool 8081 phải trỏ guest:8081, cùng hai địa chỉ private. Dùng UUID VM kiểm placement theo H2; nếu member chỉ cho thấy một phía, thu cloud-init/console log và trạng thái LB qua đường chẩn đoán đã được thống nhất. Không tự mở SSH/ICMP hoặc thay SG nền để gỡ lỗi.

Hai listener/pool/monitor, hai app unit và hai member trong mỗi unit được tạo tuần tự để tránh sửa cùng LB đồng thời. Dependency gỡ cả hai member trước VM khi xóa. Tuy nhiên, member có thể được tạo trước khi cloud-init hoàn tất; TCP monitor mới quyết định backend có nhận traffic. Lab không có WaitCondition và không kiểm DB/Redis.

## Kiểm tra phân phối và lỗi backend

Trên A, lấy FIP từ output `vip_fip` rồi đặt URL bằng giá trị thật:

```bash
LAB_URL=http://REPLACE_VIP_FIP:8080/
python3 sample_lb.py "$LAB_URL" --expect app-a --expect app-b --requests 40 --timeout 3
LAB_PORTAL_URL=http://REPLACE_VIP_FIP:8081/
python3 sample_lb.py "$LAB_PORTAL_URL" --expect portal-a --expect portal-b --requests 40 --timeout 3
```

Chỉ coi O-13 đạt khi **cả hai lượt** không lỗi, thấy đủ hai backend đúng cổng và cấu hình LB/member khớp kiểm tra trên. Đây là phép thử stub; không chứng minh portal thật, SSE, readiness hoặc H4b đã đạt. Không bắt buộc lặp phép stop/start ngày 27/10 để kiểm riêng O-13; nếu làm thì phải duyệt và ghi kết quả từng cổng.

Sampler mở kết nối mới, không follow redirect, không dùng proxy từ biến môi trường và vẫn kiểm chứng thư khi dùng HTTPS. URL không được chứa credential, query hoặc fragment. Sampler chỉ dùng với stub, không dùng đánh giá API Shlink.

Kết quả là JSON có thời điểm UTC, số request, `counts`, `errors`, `missing` và `passed`:

- Exit `0`: thấy đủ backend mong đợi, không có lỗi trong lượt lấy mẫu.
- Exit `1`: thiếu backend hoặc có lỗi HTTP/kết nối/payload; không coi là PASS.
- Exit `2`: đầu vào CLI không hợp lệ.

`--timeout` là timeout socket theo thao tác I/O, không phải giới hạn tổng thời gian một lượt chạy. Mỗi response được đọc tối đa 4097 byte và bị từ chối nếu lớn hơn 4096 byte. Không yêu cầu tỷ lệ traffic đúng 50/50.

Để kiểm lỗi backend, **dừng rồi bật lại Nova VM app A của đúng stack lab**, giữ hai host EC2 hoạt động. Phép thử này không cần SSH vào guest hoặc VM nhảy. Đọc UUID từ output `app_a_id`, đối chiếu resource của stack và metadata `campuslink.purpose=lb-stub` trước khi thao tác. Đây là thay đổi trạng thái, cần duyệt phạm vi trước khi chạy.

```bash
LAB_APP_A_ID=REPLACE_APP_A_UUID
openstack server show "$LAB_APP_A_ID"
openstack server stop "$LAB_APP_A_ID"
# Chi bat lai sau khi da thu du ket qua failover.
openstack server start "$LAB_APP_A_ID"
```

1. Trước khi dừng VM, chạy 40 kết nối mới với cả hai nhãn; yêu cầu không lỗi và thấy đủ backend.
2. Ghi thời điểm UTC trước khi gây lỗi, lấy mẫu HTTP từng kết nối khoảng một lần/giây và theo dõi VM/member tối đa 120 giây; giữ cả lỗi chuyển tiếp trong kết quả.
3. Khi VM A đã dừng và member A bị loại, chạy 40 kết nối mới với `--expect app-b`; yêu cầu không lỗi. Không dùng cờ `passed` của sampler một request với hai nhãn để suy ra lỗi HTTP, vì một request không thể thấy cả hai backend.
4. Bật lại đúng VM cũ, chờ phục hồi tối đa 5 phút; chạy lại 40 kết nối với cả hai nhãn và yêu cầu không lỗi.

Nếu hết thời gian chờ mà chưa đạt, lưu trạng thái và log thực tế; không đổi tiêu chí hoặc tạo VM thay thế. Sau phép thử phải xác nhận cả hai backend đã hoạt động lại. Giữ lab để review nếu đó là phạm vi đã duyệt; việc giữ stack không yêu cầu giữ EC2 chạy liên tục.

Đối chiếu response nhận diện với UUID/AZ và log của từng VM. Lưu output thật đã che vào evidence theo gate hiện tại; không tạo evidence từ dữ liệu giả của tests local.

### Kết quả kiểm chứng

[Evidence ngày 27/10/2026](../../../evidence/G2/20261027-FR-INF-07-tv2-lb-cloud.txt) ghi nhận phiên bản lab **một listener 8080** validate và tạo stack thành công trên DevStack stable/2026.1 bằng quyền member. Hai Ubuntu VM nằm đúng hai AZ; LB dùng provider `ovn`, pool `SOURCE_IP_PORT` và TCP monitor. Kết quả lịch sử này không xác nhận template hai cổng hiện tại đã chạy trên cụm.

| Phép đo | Kết quả |
| --- | --- |
| Bình thường, 40 kết nối mới | app-a: 19; app-b: 21; không lỗi |
| Sau khi dừng VM app A, 40 kết nối mới | app-b: 40; không lỗi |
| Sau khi bật lại app A, 40 kết nối mới | app-a: 19; app-b: 21; không lỗi |

Bộ thu ghi 12 mẫu HTTP chuyển tiếp, không gặp lỗi; điều kiện VM A `SHUTOFF`, member A `ERROR`, member B `ONLINE` được xác nhận sau khoảng 12,5 giây từ trước lệnh stop. Sau lệnh start, cả hai member được quan sát `ONLINE` sau khoảng 42,2 giây. Đây là kết quả của một lượt lấy mẫu, không phải giới hạn downtime hoặc cam kết SLO. Capture HTTP chứa nhãn và hostname từng guest, đối chiếu với UUID/AZ qua Nova; chưa thu journal hoặc packet capture bên trong guest. Phép thử không bao gồm SSH guest, ingress Nginx, Shlink hoặc autoscaling.

[Preflight O-13 ban đầu ngày 07/11](../../../evidence/G2/20261107-O-13-tv2-dual-listener-preflight.txt) ghi suite offline 18 tests và Heat validate đạt, nhưng chưa tạo stack vì SG thiếu 8081 tại thời điểm đó. TV1 sau đó bổ sung SG qua PR #23, đóng [issue #19](https://github.com/luongkien25/campuslink/issues/19).

### O-13: hai listener trên cùng LB — đã kiểm trên cụm

[Evidence O-13 ngày 07/11/2026](../../../evidence/G2/20261107-O-13-tv2-dual-listener-cloud.txt) ghi TV2 đọc lại SG bằng quyền member rồi tạo stack `tv2-lb-o13` từ main `87ff75c`. Một LB provider `ovn` có hai listener TCP 8080/8081, mỗi listener nối pool `SOURCE_IP_PORT` và TCP monitor riêng. Cả bốn member `ONLINE`, trỏ đúng cổng trên cùng hai VM private ở hai AZ; FIP chỉ gắn VIP.

| Phép đo lúc 13:41:22 UTC | Kết quả |
| --- | --- |
| FIP của VIP `172.24.4.111:8080`, 40 kết nối mới | app-a: 27; app-b: 13; không lỗi, không thiếu backend |
| Cùng FIP `172.24.4.111:8081`, 40 kết nối mới | portal-a: 22; portal-b: 18; không lỗi, không thiếu backend |

Capture bổ sung qua mỗi listener chứa nhãn và hostname cả hai guest; đối chiếu VM A `10.20.0.127`/`campus-az-a`, VM B `10.20.0.128`/`campus-az-b`. Hai báo cáo sampler đều `passed: true`. **O-13 PASS trong phạm vi stub**; phân phối không cần đúng 50/50. Không đo lại failover trong lượt này và không dùng kết quả để nghiệm thu Shlink, portal thật, SSE, readiness, image hoặc H4b.

## Dọn lab

[Evidence cleanup 07/11/2026](../../../evidence/G2/20261107-FR-INF-07-tv2-lb-cleanup.txt) ghi stack lab cũ `88dabbc1-f487-4f26-9554-ced5c1fdb69b` đã `DELETE_COMPLETE` lúc 06:43:02 UTC. Hậu kiểm không còn VM/LB/FIP/port lab, volume/port DB và tài nguyên nền vẫn tồn tại.

Stack hai listener O-13 `c8338308-8596-4202-8bcf-d707f7760751` cũng đã được dọn sau lượt đo: `DELETE_COMPLETE` lúc 13:44:26 UTC ngày 07/11, CLI exit 0. [Hậu kiểm cùng evidence O-13](../../../evidence/G2/20261107-O-13-tv2-dual-listener-cloud.txt) kết thúc 13:45:36 UTC: stack/VM/LB/listener/pool/monitor/FIP rỗng; port lab đã hết, ba port nền/DB giữ nguyên UUID, volume DB vẫn `available` như trước. Không để lại lab hai listener chạy chờ review.

Kiểm tra UUID stack và danh sách tài nguyên trước khi xóa. Lệnh sau **xóa toàn bộ tài nguyên thuộc stack lab**, phải được duyệt riêng:

```bash
openstack stack delete --wait "$LAB_STACK_ID"
```

Sau khi xóa, xác nhận không còn VM/LB/FIP/port của lab; không xóa tài nguyên ngoài stack hoặc dùng tên trùng để dọn. Stack không sở hữu DB VM, volume DB, network, subnet, SG nền, image hoặc keypair.

Kết thúc phiên theo runbook, gồm kiểm tra người sử dụng và `campus-check` trước khi tắt máy. Không tắt EC2 nếu còn người dùng chung.

## Nguồn đối chiếu

- [Heat 2026.1: resource types](https://docs.openstack.org/heat/2026.1/template_guide/openstack.html).
- [Heat 2026.1: software configuration](https://docs.openstack.org/heat/2026.1/template_guide/software_deployment.html).
- [SRS](../../../docs/SRS.md), [inventory](../../../docs/inventory.yaml) và [troubleshooting](../../../docs/troubleshooting.md).
