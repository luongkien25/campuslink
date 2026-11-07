# Image app và runtime bootstrap

Bộ công cụ của TV2 cho FR-INF-22, NFR-08/15 và metadata guard #21. Đầu vào là [H1](../../../docs/handoffs/H1-shlink.md), [ADR-10](../../../docs/decisions/ADR-10-cap-secret-swift-va-credential-hep.md) và [hợp đồng tích hợp](../app-integration.md). Không thay mã, entrypoint hoặc migration của Shlink.

## Kiểm offline

Từ gốc repo, dùng Python có PyYAML của môi trường hiện có:

```sh
.venv/bin/python -B -m unittest discover -s infra/heat/bootstrap/tests -v
.venv/bin/python -B -m unittest discover -s infra/heat/lab/tests -v
bash -n infra/heat/image/prepare.sh infra/heat/image/sanitize.sh
sh -n infra/heat/bootstrap/metadata-guard.sh infra/heat/bootstrap/start-shlink.sh
systemd-analyze verify infra/heat/bootstrap/systemd/campuslink-*.service
```

HTTP tests chỉ mở localhost, dùng credential/token/secret giả. Tests Docker/iptables thay executor ở ranh giới cần đặc quyền; không sửa firewall hoặc chạy Docker trên laptop. `systemd-analyze verify` chỉ xác minh tĩnh; không chứng minh lifecycle sau reboot/restart daemon trên Ubuntu guest.

## Luồng runtime

```text
Docker + network-online
  → campuslink-secrets (POST token, GET đúng hai object)
  → campuslink-guard (DOCKER-USER chặn 169.254.169.254)
  → campuslink-shlink (image có sẵn, bridge, restart=no)
  → campuslink-ready (HTTP 200/status=pass và Redis PONG)
```

Config thật ở `/etc/campuslink/bootstrap.json`, root:root/0600, thư mục cha 0700. [Config mẫu](../bootstrap/config.example.json) không dùng được để xác thực. Chỉ CLI trong guest OpenStack có marker `campuslink-app-v1` mới được phép chạy. Thư mục `/run/secrets` dành riêng cho hai secret core; nếu gặp file lạ hoặc symlink, bootstrap từ chối thay vì xóa dữ liệu không rõ chủ sở hữu.

Bootstrap chỉ POST tới Keystone, GET `campus-secrets/app/db_password` và `campus-secrets/app/redis_servers`. Không discovery, list, HEAD, redirect hoặc proxy từ môi trường; bỏ qua `.curlrc`. Payload xác thực đi qua stdin; token header/HTTP scratch đi qua file tạm 0600 trong thư mục 0700 dưới `/run/campuslink`, không dùng `/tmp` trên root disk. Không đưa giá trị vào argv/log. Client có tối đa ba lần thử cho lỗi HTTP tạm; mỗi request tối đa 5 giây. Toàn bộ token→secret→guard→readiness dùng chung deadline 180 giây. Secret sai định dạng, lỗi quyền hoặc quá hạn đều không ready.

Mỗi lần fetch vô hiệu hóa state cũ, gỡ đúng bộ secret do nó quản lý, tải vào staging rồi đổi tên thư mục khi đủ cả hai file. Lỗi giữa chừng không để dùng bộ cũ/mới lẫn nhau. File root:root/0444 trong thư mục root:root/0700, mount read-only **từng file** để uid 1001 trong Shlink đọc được. Secret ứng dụng chỉ ở `/run`; credential bootstrap trong config/user-data là ngoại lệ đã duyệt của ADR-10, vẫn đọc được với guest root/admin Heat.

Guard chỉ hỗ trợ Docker bridge với backend iptables. `iptables-nft` frontend được chấp nhận nếu các chain iptables của Docker hoạt động; Docker native nftables bị từ chối. Docker từ 29 phải cấu hình rõ `firewall-backend=iptables`. Kiểm rule DROP và jump DOCKER-USER đứng đầu chain để tránh ACCEPT trước đó làm vô hiệu guard; không flush hoặc tự sửa các rule khác. Host vẫn gọi metadata qua OUTPUT; container đi qua FORWARD bị chặn. Hiệu lực thực tế cần đo từ container trên từng guest.

Systemd dùng `Requires/After/BindsTo/PartOf`, Docker `Wants` kéo chuỗi lên mỗi lần daemon khởi động. Container có `--restart=no --rm --pull=never`; systemd không tự retry app lỗi. Lỗi readiness dừng container; sửa nguyên nhân rồi restart cả chuỗi bằng restart Docker **trong guest thử**, không restart DevStack. Nếu gặp container `shlink` còn sót, runtime dừng để kiểm tra, không force-delete. Không chạy `fetch_secrets.py` độc lập khi app đang chạy: dừng chuỗi runtime trước để tránh mount file cũ.

Readiness chỉ là kết quả khởi động tại thời điểm kiểm, chưa phải monitor liên tục hay Heat WaitCondition. HTTP health chỉ phản ánh DB; Redis phải trả PONG qua probe nguyên bản của TV3. Container chưa được tạo hoặc đang `created` là pending trong deadline vì `Type=exec` chỉ xác nhận wrapper đã khởi chạy; container exited, RestartCount khác 0 hoặc host networking đều fail ngay. Clone A phải ready/migration xong trước khi khởi động clone B lần đầu.

Docker json-file thêm `attrs` chứa `campuslink.guest_uuid` và `campuslink.guest_ip`, lấy từ instance-data đã lọc của cloud-init và route nội bộ. Log Shlink vẫn JSON/UTC theo env H1; Request ID thuộc Shlink. Khi thu thập, giữ cả envelope Docker và JSON ứng dụng để không mất UUID/IP. Cần kiểm log thật và Request ID trên clone trước nghiệm thu NFR-15.

## Chuẩn bị builder và candidate

Đây là recipe **chưa chạy trên guest**. Trước thao tác cloud: xác nhận Zalo/nhật ký, kiểm A/B, quota, CLI/schema 2026.1 và quyền member. Không chạy scripts này trên laptop hoặc EC2 A/B.

1. Tạo builder Nova private từ `ubuntu-noble-base`, flavor `campus.app`, root 10 GiB. Dùng đường SSH đã xác minh qua jump; private key giữ trên laptop, không copy key hoặc forward agent. Chỉ jump có FIP. Không đụng DB port/volume nền.
2. Sau khi thay đổi được review và commit, tạo archive từ **commit sạch**, chỉ chứa `infra/heat/bootstrap`, `infra/heat/image`, `app/shlink.env.example`, `app/smoke/redis-probe.sh`. Không copy workspace, `.git`, file ignored, credential hoặc SSH key. Giữ cấu trúc thư mục khi giải nén trong builder.
3. Trong builder riêng, chạy `sudo bash infra/heat/image/prepare.sh --confirm-openstack-builder REPLACE_COMMIT_SHA`, thay placeholder bằng SHA 40 ký tự của archive. Script kiểm Ubuntu 24.04/amd64/OpenStack, khoảng trống tối thiểu 3 GB, cài Docker/curl/Python/redis-tools/iptables, đặt MTU Docker 1400 và preload digest Shlink. Kiểm cú pháp/options package thực trên guest trước lần dùng đầu tiên; không lấy version laptop thay version guest.
4. Kiểm `/opt/campuslink/build-manifest.json`, image inspect/architecture, bản probe/env nguyên vẹn, các unit được cài, không container, không config bootstrap hay app secret. Manifest này ghi package/kernel/file hash, chưa phải bằng chứng clone. Thẩm tra manifest amd64 dự kiến bằng công cụ/CLI registry đúng phiên bản; index digest đã khóa không được đổi.
5. Kiểm phạm vi sạch bằng metadata/đường dẫn, không in nội dung nhạy cảm. Bảo đảm không có Docker auth, cloud credential, user-data thật hoặc private key do operator đưa vào. Recipe từ chối các vị trí nhạy cảm đã biết, không chứng minh đã scan mọi byte trên disk.
6. Chạy `sudo bash infra/heat/image/sanitize.sh --confirm-disposable-builder` bằng phiên SSH cuối. Script xóa identity/authorized keys/history/cloud-init state của builder, không dùng cho VM có dữ liệu. **Dừng builder rồi snapshot, không reboot builder trước snapshot.** Lệnh Nova stop/snapshot cần kiểm `--help` trên A và duyệt thao tác cloud trong phiên tương ứng.
7. Theo dõi Glance active, ghi UUID/checksum/min_disk/min_ram/virtual_size/size thật vào manifest. Image phải boot được trên `campus.app` root10 GiB; không giảm `min_disk` để che disk quá lớn. Chỉ cập nhật inventory/versions sau khi có output thật.

`prepare.sh` cần builder sạch, không phải installer nâng cấp chạy lặp tùy ý. Sanitize làm mất identity của builder; không thực thi khi chưa chọn đúng UUID và chưa xác nhận builder dùng một lần. Không có lệnh stop/xóa cloud nào được nhúng trong recipe.

## Kiểm clone

[clone-check.yaml](clone-check.yaml) chỉ sở hữu một VM và port private. Không LB, ASG, floating IP, DB hoặc data volume. [clone-env.example.yaml](clone-env.example.yaml) là mẫu riêng, không dùng `infra/heat/env.example.yaml` của stack chính. Hai bootstrap parameters `hidden: true`; constraint giới hạn ký tự để nội suy JSON an toàn. Giá trị thật chỉ ở env file 0600 trên A theo kênh bàn giao TV1; không truyền giá trị trực tiếp qua CLI.

Trước khi dùng template, kiểm `OS::Nova::Server`, `OS::Neutron::Port`, `OS::Heat::CloudConfig` bằng schema Heat 2026.1 thật và validate với giá trị giả. **Chưa kiểm CLI/schema clone trên cloud.** Không dump parameters, config hoặc user-data khi dùng credential thật; hidden không thay quyền admin/metadata guard.

Sau khi có credential campus-boot hợp lệ và DB/Redis/objects thật:

1. Clone A từ candidate; kiểm host fetch thành công, file/quyền, rule, digest cached, HTTP+Redis cục bộ trong 180s. `ACTIVE` hoặc `CREATE_COMPLETE` không thay readiness. Không thêm LB member tại bước này.
2. A ready/migrate xong mới clone B từ cùng UUID; kiểm độc lập tại B, không kiểm qua VIP hay A.
3. Kiểm metadata bằng container thử: host vẫn gọi được, container không truy cập được; không đưa nội dung user-data vào evidence. Reboot từng clone và restart Docker guest để chứng minh fetch/guard chạy trước app; theo dõi Docker events và logs đã che để chứng minh không pull.
4. Negative tests trên clone/config thử riêng: auth sai, object thiếu/sai, timeout, guard lỗi, DB/Redis không reachable. Không dừng DB chung hay sửa SG nền để gây lỗi. Mỗi lỗi phải không ready; guard/fetch lỗi phải không app.
5. Lưu manifest/evidence thật rồi đề nghị review #21. Chỉ dọn tài nguyên thử theo UUID đã ghi và được duyệt; không xóa DB volume/port, base image, network hay SG dùng chung.

Chưa có image UUID, build thật, clone A/B, reboot hoặc packet test thì FR-INF-22 và #21 vẫn chưa nghiệm thu. Phần ASG/WaitCondition/policy thuộc bước tích hợp tiếp theo.
