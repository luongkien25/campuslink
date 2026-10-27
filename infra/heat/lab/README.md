# Lab cân bằng tải OVN với hai HTTP backend

Lab kiểm tra phân phối kết nối TCP qua Octavia OVN đến hai Nova VM, mỗi VM ở một AZ. Các backend trả về nhãn `app-a` hoặc `app-b` để nhận diện đường đi của traffic.

Lab sử dụng HTTP stub, không chạy Shlink. Kết quả của lab hỗ trợ kiểm chứng FR-INF-07; không thay thế nghiệm thu readiness DB/Redis, image ứng dụng hoặc autoscaling.

## Thành phần và đầu vào

| File | Chức năng |
| --- | --- |
| `root.yaml` | LB OVN, listener TCP 8080, pool `SOURCE_IP_PORT`, TCP monitor, FIP của VIP và hai app unit |
| `stub-unit.yaml` | Một port private, VM, cloud-config và pool member |
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
| `app_security_group` | `campus-app-sg`, cho TCP 8080 từ mạng tenant và mạng external OpenStack |
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

### Xác minh CLI và schema — chưa kiểm trên cụm

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
```

Kiểm tra schema cho `OS::Octavia::LoadBalancer`, `OS::Octavia::Listener`, `OS::Octavia::Pool`, `OS::Octavia::HealthMonitor`, `OS::Octavia::PoolMember`, `OS::Neutron::Port`, `OS::Neutron::FloatingIP`, `OS::Nova::Server` và `OS::Heat::CloudConfig`. Ví dụ — **chưa kiểm trên cụm**:

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

## Tạo và kiểm tra stack — chưa kiểm trên cụm

Sau khi đối chiếu `--help` và schema, chạy từ thư mục `~/campuslink-tv2-lab` trên A. Thay `REPLACE_KEYPAIR_NAME` bằng keypair thật. Chưa tạo tài nguyên ở bước validate:

```bash
cd ~/campuslink-tv2-lab
openstack orchestration template validate --template root.yaml --parameter key_name=REPLACE_KEYPAIR_NAME
```

Validate thành công không chứng minh cloud-init hoặc backend đã hoạt động. Nếu validate chưa nhận parameter theo cú pháp trên, dùng đúng cú pháp được `--help` của CLI tại A công bố.

Lệnh tiếp theo **tạo hai VM, LB, listener, pool, monitor, member, port và một FIP**, chỉ thực hiện sau khi duyệt:

```bash
openstack stack create --template root.yaml --parameter key_name=REPLACE_KEYPAIR_NAME --wait tv2-lb-lab
```

Không dán lệnh tạo hai lần. Ghi UUID stack; các thao tác tiếp theo dùng UUID, không dựa vào tên có thể trùng.

Sau khi tạo, đặt các biến bằng UUID đọc từ output thật. Lệnh đọc trạng thái/output — **chưa kiểm trên cụm**:

```bash
LAB_STACK_ID=REPLACE_STACK_UUID
openstack stack show "$LAB_STACK_ID" -c stack_status
openstack stack resource list --nested-depth 2 "$LAB_STACK_ID"
openstack stack output show "$LAB_STACK_ID" lb_id
openstack stack output show "$LAB_STACK_ID" pool_id
openstack stack output show "$LAB_STACK_ID" vip_fip
openstack stack output show "$LAB_STACK_ID" app_a_id
openstack stack output show "$LAB_STACK_ID" app_b_id
```

Kiểm `CREATE_COMPLETE`, LB `ACTIVE` và member TCP hoạt động. Dùng UUID VM kiểm placement theo H2; nếu member chỉ cho thấy một phía, thu cloud-init/console log và trạng thái LB qua đường chẩn đoán đã được thống nhất. Không tự mở SSH/ICMP hoặc thay SG nền để gỡ lỗi.

Hai app unit được tạo tuần tự để tránh sửa pool đồng thời. Dependency gỡ member trước VM khi xóa. Tuy nhiên, member có thể được tạo trước khi cloud-init hoàn tất; TCP monitor mới quyết định backend có nhận traffic. Lab không có WaitCondition và không kiểm DB/Redis.

## Kiểm tra phân phối và lỗi backend

Trên A, lấy FIP từ output `vip_fip` rồi đặt URL bằng giá trị thật:

```bash
LAB_URL=http://REPLACE_VIP_FIP:8080/
python3 sample_lb.py "$LAB_URL" --expect app-a --expect app-b --requests 40 --timeout 3
```

Sampler mở kết nối mới, không follow redirect, không dùng proxy từ biến môi trường và vẫn kiểm chứng thư khi dùng HTTPS. URL không được chứa credential, query hoặc fragment. Sampler chỉ dùng với stub, không dùng đánh giá API Shlink.

Kết quả là JSON có thời điểm UTC, số request, `counts`, `errors`, `missing` và `passed`:

- Exit `0`: thấy đủ backend mong đợi, không có lỗi trong lượt lấy mẫu.
- Exit `1`: thiếu backend hoặc có lỗi HTTP/kết nối/payload; không coi là PASS.
- Exit `2`: đầu vào CLI không hợp lệ.

`--timeout` là timeout socket theo thao tác I/O, không phải giới hạn tổng thời gian một lượt chạy. Mỗi response được đọc tối đa 4097 byte và bị từ chối nếu lớn hơn 4096 byte. Không yêu cầu tỷ lệ traffic đúng 50/50.

Để kiểm lỗi backend, dùng phương thức quản trị VM đã được thống nhất để **dừng service `campuslink-stub` trong một VM thử**, giữ host EC2 hoạt động. Đây là thao tác thay đổi trạng thái, cần duyệt; không tự suy đoán đường SSH guest.

1. Ghi thời điểm UTC trước khi gây lỗi và theo dõi LB/member trong thời gian monitor hội tụ; giữ cả lỗi chuyển tiếp trong kết quả.
2. Sau khi backend bị loại, chạy sampler với `--expect` chỉ backend còn sống. Đối chiếu trạng thái member để phân biệt failover với thiếu phân phối.
3. Khởi động lại service sau khi duyệt, chờ phục hồi; chạy lại sampler với cả hai backend.

Đối chiếu response nhận diện với UUID/AZ và log của từng VM. Lưu output thật đã che vào evidence theo gate hiện tại; không tạo evidence từ dữ liệu giả của tests local.

## Dọn lab — chưa kiểm trên cụm

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
