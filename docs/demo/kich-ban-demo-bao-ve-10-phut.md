# Kịch bản demo bảo vệ CampusLink trong 10 phút

Demo đi theo tình huống tổ chức một sự kiện: **đơn vị tạo chiến dịch và link → phát hành thẻ QR → người tham dự quét → theo dõi check-in và xuất CSV → chỉ ra dữ liệu, quyền truy cập và cụm xử lý tự mở rộng**. Phần live kết hợp với bằng chứng ghi trước có ngày, theo mốc thời gian dưới đây.

**Cách demo đã thống nhất:** dùng một laptop chung khi bảo vệ, **đến phần ai thì người đó tự thao tác và tự nói**. TV1 Kiên phụ trách mạng và phân quyền; TV2 Hoàng phụ trách monitoring, autoscaling và failover; TV3 Huy phụ trách portal và dữ liệu; TV4 Toàn phụ trách bằng chứng vận hành, chi phí và hỗ trợ quét QR. TV4 giữ giờ khi không trình bày.

**Thứ tự chuẩn bị tối 27/11:** từng người **chốt kịch bản phần mình trước → tự tập trên laptop của mình → gửi kết quả và điều chỉnh**. Không yêu cầu TV1 thao tác thay các phần khác. Trước buổi bảo vệ 30/11, ráp một lượt 10–15 phút trên laptop chung để tập bàn giao bàn phím/cửa sổ. Các phép thử trên cụm dùng chung phải đăng ký lượt để không phát tải hoặc failover chồng nhau.

**Trạng thái:** timeline bên dưới là khung để từng chủ phần chốt, chưa phải kịch bản đã được họ xác nhận. [Bộ script](../../ops/demo/) đã bổ sung bản chạy theo tài khoản thành viên và kiểm thử offline; chưa kiểm end-to-end trên cụm. Cụm đang tắt theo TV1, nên chưa cài bộ mới lên Host A.

## Chốt kịch bản từng phần trước khi thử

Mỗi người comment trong [issue 104](https://github.com/luongkien25/campuslink/issues/104), hoặc đề xuất sửa trực tiếp phần mình trong PR 103, theo mẫu:

```text
TVx chốt phần ...
1. Bấm/chạy ... → màn hình phải thấy ... → mình nói ...
2. ...
Thời lượng mục tiêu: ...
Dữ liệu/tài khoản/file/script cần chuẩn bị: ... (không đưa secret)
Đoạn chạy live / video và mốc chuyển dự phòng: ...
Sau khi chốt: tự tập lúc ..., cần lượt cloud hay chỉ laptop ...
```

Chưa rõ bước bấm, output hoặc thời lượng thì sửa kịch bản trước. Việc đọc script hoặc chạy `help` có thể làm ngay; thử có tải/thay đổi trạng thái chỉ làm sau khi chốt phạm vi và lượt sử dụng cụm. Hướng dẫn lấy script và dùng tài khoản riêng ở [hướng dẫn script](huong-dan-script.md).

## Phạm vi và bằng chứng hiện có

| Thành phần | Nội dung minh họa | Giới hạn cần nói đúng |
| --- | --- | --- |
| Portal `app.` | Đăng nhập đơn vị, chiến dịch, tạo link, thẻ QR PDF, luật thiết bị, check-in, CSV | Có [bằng chứng trên cụm ngày 23/11](../../evidence/G3/20261123-FR-APP-13-19-portal-len-cum-smoke-va-stop-start.txt); phải kiểm lại trước demo |
| Web Client `admin.` | Giao diện quản trị Shlink, mở sẵn khi kiểm HTTPS | Tách với portal nghiệp vụ, không mở Manage servers khi trình chiếu vì có API key |
| Redirect `s.` | Mở link hoặc quét QR nhận HTTP 302 đúng đích | Link dùng phát tải tách với các thẻ dùng minh họa check-in |
| Cinder, PostgreSQL và Swift | DB trên volume, backup dump, PDF và CSV trên object storage | Hash khớp là kiểm toàn vẹn; khôi phục dùng evidence restore riêng |
| Mạng và quyền | Hai Nova AZ/host, private VM, TLS, IAM allow/deny, Keystone reader | Không dùng kết quả listener `ss` để suy ra rule AWS SG; quyền portal là phép kiểm riêng |
| Autoscaling | Tải thật → CPU → Aodh ALARM → Heat → VM/member mới ONLINE | Áp dụng cụm Shlink `campus-app`, tổng app 2→3; portal `campus-portal-2411` là stack riêng |
| Scale-in | Video lượt tự thu hẹp 3→2 | Nêu ngày ghi; không chờ toàn bộ chiều thu hẹp trong 10 phút live |
| Failover | Dừng một App VM, quan sát HTTP và member; bật lại | Không phải thử mất EC2 Host A, DB hoặc toàn bộ AZ |
| Vận hành nâng cao và chi phí | Evidence restore, chaos, CI; bảng chi phí | Có bản ghi để mở sâu khi hỏi; không chạy thêm restore/chaos trong lượt live |

Theo [acceptance.md](../acceptance.md), nhập CSV 200 dòng, nhật ký thao tác và phép kiểm quyền portal giữa đơn vị/viewer mới có bằng chứng Compose ở lần cập nhật hiện có. Chuẩn bị chúng thành phần mở thêm khi được hỏi, ghi đúng môi trường của bằng chứng.

Portal xử lý lô đồng bộ và bảng check-in polling API 15 giây. `campus-worker` đa replica cùng `campus-stats` pub/sub/SSE đã rút khỏi phạm vi triển khai. Không mô tả chúng là đang chạy hoặc co giãn cùng cụm Shlink.

## Mỗi người cần kiểm và gửi gì

| Người | Việc cần làm trước phiên kiểm | Kết quả gửi vào issue |
| --- | --- | --- |
| **TV1 Kiên** | Chốt mạng/IAM; tự bấm và nói phần đó; chuẩn bị máy chung, bộ script và cài bản dùng chung khi cụm bật | Kịch bản TV1, output đã thử, trạng thái cài script trên cloud và dữ liệu/màn hình cho máy chung |
| **TV2 Hoàng — @nchh06** | Chốt rồi tự thử tải, alarm, Heat, LB, failover và khôi phục từ laptop riêng bằng user `tv2` | Kịch bản TV2, ID/env đã xác nhận, giờ đăng ký lượt cloud, output/video 2→3→2, trạng thái sau khôi phục |
| **TV3 Huy — @dqh1215** | Chốt rồi tự thử portal trên trình duyệt; storage qua user `tv3`; chuẩn bị chiến dịch, thẻ, luật, check-in và CSV | Kịch bản TV3, tên dữ liệu mẫu, thứ tự đã tập, thời gian, phần dùng clip; không gửi mật khẩu/API key |
| **TV4 Toàn — @toancst** | Chốt rồi tự thao tác script laptop, video, bảng chi phí và evidence; review nhịp chuyển phần | Kịch bản TV4, video/mốc tua, số liệu có ngày, kết quả HTTPS từ laptop riêng, output và thời lượng |

**Mẫu phản hồi của mỗi người:**

```text
TVx đã đọc / phần của mình sẵn sàng / còn vướng ...
Cần sửa trong kịch bản: ...
Đã kiểm ở môi trường ... lúc ...; kết quả ...
Evidence hoặc file/clip: ...
Việc mình nhận, hạn hoàn thành hoặc giờ có thể phối hợp: ...
```

Nếu mới review tài liệu, ghi “đã đọc, chưa chạy”, không ghi PASS trên cụm. Không bật cụm hoặc thay đổi stack chỉ để tick checklist; phối hợp phiên theo [CONTRIBUTING](../../CONTRIBUTING.md) và [runbook bật tắt](../runbooks/start-stop.md).

## Điều kiện sử dụng script

Dùng bản trong [ops/demo](../../ops/demo/), không dùng lại bản nháp chỉ có trên máy TV1. Script Host A dùng OpenStack identity hiện có của mỗi người; TV2/TV3 không cần mượn `sudo` của TV1 cho phần mình. Script không cấp thêm quyền và không sao chép credential.

Bản mới đã sửa cách đọc JSON LB/alarm, so đủ 64 ký tự SHA256, chặn failover khi chưa xác nhận alarm đã tắt, giữ log tải theo user và kiểm PID trước khi dừng. `hm5` chỉ dùng IAM dry-run cùng evidence reader, không thử tạo VM thật. Script laptop kiểm thêm portal health, không tự mở GUI/chạy test và không in dự báo chi phí cũ. `cleanup` kiểm baseline, không tự đổi trạng thái để sửa lỗi.

Các thay đổi có kiểm thử offline; từng chủ phần vẫn cần xác nhận lệnh/quyền và output trên cụm. Việc cài vào `/opt/campuslink-demo` chỉ chép file dùng chung, không sửa sudoers, role, alarm, stack hay dịch vụ. Xem [hướng dẫn cài và tự tập](huong-dan-script.md).

## Chuẩn bị máy trình chiếu và dữ liệu mẫu

Hôm bảo vệ dùng một laptop với terminal SSH Host A, PowerShell, Chrome và trình phát video. Mỗi người ngồi vào máy khi đến phần mình, tự bấm và tự nói, xong thì giao bàn phím/cửa sổ cho người tiếp theo. Mở sẵn các phiên `ubuntu`/`tv2`/`tv3` cần dùng bằng quyền đã có; TV1 có thể chuẩn bị phiên thành viên bằng `sudo -iu tv2` hoặc `sudo -iu tv3` trên Host A từ phiên quản trị hiện có. Không chuyển private key hay mật khẩu thành viên sang máy chung.

TV3 cùng TV1 chuẩn bị trước giờ bấm đồng hồ:

1. Đăng nhập tài khoản đơn vị ở `app.`. Tạo chiến dịch mẫu còn hiệu lực sau buổi bảo vệ, có tên dễ nhận biết; tạo 3–5 thẻ QR và giữ một thẻ chưa quét. Dùng tên người mẫu, không đưa danh sách cá nhân thật lên màn hình.
2. Chuẩn bị form **Thêm link** ở trang chiến dịch, một dòng dạng `https://example.org/demo | Demo mới`. Bấm **Thêm** trong lượt live để có mã mới ít visit cho bài tải. Form này không có ô custom slug; sao chép mã link thật để dùng ở mọi lệnh.
3. Đặt trước luật theo thiết bị trên một link mẫu khác, thử điện thoại và máy tính cho hai đích khác nhau. Không chỉnh luật của link phát tải.
4. Mở sẵn **Thẻ QR**, **Theo dõi trực tiếp**, **Báo cáo**, tab `admin.` và video dự phòng. Nếu cần phát hành lại, điền sẵn tối đa 3–5 dòng `Họ tên, Đơn vị` và URL đích; đo trước thời gian tạo PDF.
5. Lượt quét thẻ minh họa check-in dùng link riêng với link phát tải, để người xem hiểu số người check-in khác tổng request tải.

TV4 chuẩn bị video ở ổ máy trình chiếu, không phụ thuộc tải file từ mạng lúc demo. Clip portal `08-tv3-portal-1651Z.mp4` ngày 23/11 dài 4:14 có luật thiết bị, PDF, check-in và CSV; chọn trước các đoạn ngắn cần dùng, không mở cả clip rồi tìm cảnh. Với autoscaling, chuẩn bị cả chiều tăng và chiều giảm, ghi rõ ngày quay.

## Request được gửi từ đâu

TV2 tự gõ `d load-start <slug-moi> 420` **trong phiên SSH user `tv2` trên Host A**; wrapper khởi động ApacheBench (`ab`) trên Host A. Khi tự tập, TV2 điều khiển từ laptop riêng; hôm bảo vệ TV2 dùng laptop chung. `load-start` và `load-stop` phải dùng cùng Linux user vì PID/log nằm trong thư mục riêng của user đó.

| Luồng | Máy gửi request và đường đi | Mục đích |
| --- | --- | --- |
| Tải thử autoscaling | Host A chạy `ab` do TV2 khởi động → VIP HTTP nội bộ của Octavia → các App VM Shlink | TV2 tự kiểm chuỗi CPU/alarm và scale-out; laptop chỉ điều khiển qua SSH |
| Người tham dự quét QR | Điện thoại TV1 hoặc TV4 → HTTPS công khai `s.` → Nginx/LB → Shlink | Minh họa truy cập người dùng và check-in |
| Thao tác portal | Trình duyệt TV3 đang điều khiển → HTTPS `app.` → portal stack riêng | Quản lý chiến dịch, QR, bảng theo dõi và CSV |

Tải `ab` đi nội bộ qua LB; phép kiểm HTTPS/QR từ laptop hoặc điện thoại kiểm đường truy cập công khai. Khi trình bày, nói rõ đây là tải thử bằng công cụ, không coi số request là số người tham dự thật.

## Kiểm cụm trước khi demo

Sau khi chốt phần mình, từng thành viên tự kiểm bằng laptop riêng theo [hướng dẫn script](huong-dan-script.md). TV1 chuẩn bị nền cụm và cài file dùng chung; TV2 chịu trách nhiệm lượt alarm/Heat/LB, tải và failover; TV3 kiểm portal/storage; TV4 kiểm HTTPS và bằng chứng. Dùng [after-start](../runbooks/after-start.md), [inventory](../inventory.yaml) và [versions.lock](../versions.lock) để đối chiếu, không mặc định UUID/IP trong script vẫn đúng.

Trên laptop thành viên, lấy bản repo theo hướng dẫn; phần cài trên cloud do TV1 làm. Sau khi file đã cài, SSH bằng tài khoản của mình (ví dụ TV2):

```powershell
ssh tv2@campus-a
```

Trong phiên SSH Host A:

```bash
alias d='bash /opt/campuslink-demo/demo-host-a.sh'
d help
d pre
```

Trong cửa sổ PowerShell ở thư mục clone repo:

```powershell
.\ops\demo\demo-laptop.ps1 pre
```

**Baseline cần xác nhận:** hai compute up, DB và hai App VM hoạt động, đúng 2 member LB ONLINE, stack ổn định, không có tải khác; health/admin trả 200 và link thử trả 302 đúng đích. Portal `app./healthz` trả 200, chiến dịch mở được, PDF/CSV tải được, bảng check-in cập nhật. `d pre` trả mã 0 không có nghĩa mọi mục đã PASS; phải đọc cảnh báo.

TV2 xác nhận CPU/metric đủ dữ liệu, trạng thái `cpu_high` phù hợp trước khi thử và file env private đúng. Chỉ bật action khi sẵn sàng phát tải; lệnh wrapper là `d alarm-on <file-env-private-TV2-da-xac-nhan>`. Không chép nguyên placeholder và không in nội dung env/action URL.

Không trình chiếu credential, API key, Manage servers, Account ID hoặc IP nhà. Dọn dòng Last login bằng `clear`. Việc wrapper TV1 dùng credential thành viên phải được báo cho người liên quan trước phiên. Phép thử chỉ dừng **App VM A**, không dừng EC2 Host A, portal VM hoặc DB VM.

## Lịch chạy mục tiêu 10 phút

Thay `<slug-moi>` bằng mã link thật vừa tạo, dùng cùng mã ở Host A và laptop. Đây là lịch để đo khi tập; nếu lệnh gọi API/tải dump lâu hơn khung, dùng output đã kiểm hoặc video đã chuẩn bị và ghi rõ nguồn.

| Mốc | Người tự thao tác và nói | Thao tác trên máy chung | Kết quả cần thấy và lời dẫn |
| --- | --- | --- | --- |
| 0:00–0:25 | TV3 | Mở chiến dịch trong portal `app.`, bấm **Thêm** cho link đã điền, mở link mới | Link 302 đúng đích. “Đơn vị dùng portal quản lý chiến dịch; mỗi link có thể dùng làm QR cho người tham dự.” |
| 0:25–0:35 | TV2 | Giao bàn phím cho TV2; phiên `tv2`: `d load-start <slug-moi> 420`, rồi trả TV3 | Probe 302, tải nền đã bắt đầu. “Nhóm phát tải trên lõi xử lý link, trong lúc thu metric sẽ trình bày nghiệp vụ.” |
| 0:35–2:35 | TV3 | Theo bảng thao tác portal bên dưới; TV4 hỗ trợ quét QR | PDF thẻ, hai thiết bị ra đích khác nhau, check-in cập nhật và CSV tải được |
| 2:35–3:20 | TV1 | `d hm1`, `d hm2`; laptop `.\ops\demo\demo-laptop.ps1 app <slug-moi>` nếu đã đo chạy kịp | Chỉ dòng Nova AZ/host, private VM, HTTPS và API không key 401. “Request qua Nginx TLS, VIP Octavia rồi tới app; app và DB nằm trong mạng private.” |
| 3:20–4:00 | TV3 | `d hm34` sau khi xử lý hash; nếu tải dump lâu, mở kết quả kiểm trước và evidence PDF/CSV trên Swift | “PostgreSQL dùng Cinder; PDF/CSV và backup nằm trên Swift. Hash kiểm toàn vẹn, khả năng restore được kiểm bằng phép thử riêng.” |
| 4:00–4:40 | TV1 | `d hm5` khi phép thử đã sẵn sàng; nếu chưa thì evidence IAM/RBAC | IAM Role; dry-run được phép volume A, bị chặn volume B; reader bị từ chối ghi. Phân biệt quyền hạ tầng với quyền đơn vị trong portal |
| 4:40–6:00 | TV2 | Host A: `d watch 10`; Ctrl+C khi cần | CPU/ALARM → Heat → VM/member ONLINE. “Đây là autoscaling cụm Shlink 2→3. Portal là stack riêng.” Chỉ kết luận scale-out khi thấy member mới ONLINE |
| 6:00–6:25 | TV2 | `d load-stop`, `d hm7`, `d alarm-off`; TV2 xác nhận sau update | Lưu metric/history; hai alarm disabled, action trống trước failover. Nếu chưa xác nhận thì chưa dừng App A |
| 6:25–7:50 | TV4 rồi TV2 | TV4 bấm laptop `.\ops\demo\demo-laptop.ps1 failover <slug-moi> 90`, giao TV2 chạy `d fail-stop`, rồi `d fail-start` trong phiên `tv2` | App A lỗi, member còn lại phục vụ, HTTP thực tế được ghi; App A khôi phục. Nếu còn VM scale-out thì số member có thể là 3→2 trong lúc A dừng |
| 7:50–8:35 | TV4 và TV2 | Video scale-in đã tua sẵn; TV2 theo dõi App A nếu còn khôi phục | “Đây là bản ghi ngày …, sau giảm tải cụm tự thu về 2 app.” Nếu đã dùng video autoscaling thì rút cảnh để không lặp |
| 8:35–9:10 | TV4 | Một cảnh evidence vận hành nâng cao đã chọn | Tóm tắt restore trên bản sao, báo cáo chaos và CI quét bảo mật; chỉ số đúng phạm vi, có tài liệu mở sâu khi hỏi |
| 9:10–9:40 | TV4 | Bảng chi phí có nguồn/ngày, ảnh đã che | Tách dự toán 730 giờ, actual, forecast và credit; không chạy unittest hoặc đọc số cũ từ `hm8` |
| 9:40–10:00 | TV1 | Sơ đồ hoặc ma trận hạng mục ngắn | “Nhóm vừa đi từ chiến dịch, QR và check-in tới dữ liệu, quyền truy cập và cụm lõi tự mở rộng; chiều thu hẹp và các phép thử sâu có bằng chứng ghi trước.” |

Hai mốc TV4 báo riêng cho nhóm: **5:45** để quyết định phần autoscaling, **9:40** để chốt. Đến 5:45 mà high chưa ALARM thì chuẩn bị video; đến 6:00 chưa có member mới ONLINE thì chuyển phương án video. Không chờ thêm để vượt giờ.

## Thao tác và lời nói phần portal

Phần này nằm trong 0:35–2:35, tận dụng thời gian cụm lõi đang chịu tải. TV3 tự bấm và tự nói; TV4 hỗ trợ quét bằng điện thoại. Không để nhiều người nói cùng lúc.

| Thứ tự | Bấm gì | Chỉ ra và nói gì |
| --- | --- | --- |
| 1 | Trong **Thẻ QR**, bấm **Phát hành thẻ** nếu đã đo chạy kịp; nếu không, bấm **Tải PDF** của lô đã tạo trước | “Mỗi người một QR riêng; PDF được lưu trên Swift.” Nếu tải lô có sẵn, nói rõ đó là lô đã chuẩn bị |
| 2 | Mở PDF, phóng một thẻ chưa quét; TV4 quét | Điện thoại vào short link rồi tới đích. Không quét link đang dùng phát tải |
| 3 | Mở link mẫu đã đặt **Luật chuyển hướng** bằng điện thoại và máy tính | Hai đích khác nhau. “Luật nằm ở link; có thể phục vụ người dùng theo thiết bị.” Không cấu hình lại từ đầu lúc trình chiếu |
| 4 | Mở **Theo dõi trực tiếp** sau ít nhất một nhịp polling | Chỉ số check-in, tổng lượt, biểu đồ theo phút/top link. “Bảng tự làm mới 15 giây; người đã check-in khác số lượt quét.” Không đợi liên tục nếu mạng chậm: dùng clip đã chọn |
| 5 | Về chiến dịch, bấm **Xuất báo cáo**, rồi **Tải CSV**; mở file đã tải | Chỉ các cột link, đích, nhãn, số lượt và dòng tổng. “Đơn vị tải báo cáo để đối soát; file được lưu trên Swift.” |

Ví dụ chuyển lượt: TV3 nói “Đó là luồng người tổ chức sự kiện sử dụng; Kiên sẽ chỉ ra hạ tầng phía dưới.” Sau phần quyền, TV1 nói “Hoàng sẽ chỉ ra phản ứng của cụm với tải đang chạy.”

## Khi live chậm hoặc lỗi

| Tình huống | Hành động và cách nói |
| --- | --- |
| Portal/PDF/check-in/CSV không sẵn sàng hoặc quá khung | Mở đoạn tương ứng trong clip portal 23/11 và nêu ngày ghi; tiếp tục luồng. Không bỏ toàn bộ phần ứng dụng |
| Autoscaling chưa hoàn tất ở mốc cắt | Dừng tải, tắt action và xác nhận; chiếu video tăng/giảm đã chuẩn bị. Nói “Lượt live chưa hoàn tất trong thời gian dành cho phần này”; không tự quy nguyên nhân khi chưa chẩn đoán |
| Đọc LB/alarm ra UNKNOWN hoặc thiếu dữ liệu | Dừng phần thay đổi VM; kiểm bằng công cụ đọc đã xác nhận hoặc dùng evidence. UNKNOWN không chứng minh tài nguyên đã lỗi hay đã khôi phục |
| Có timeout hoặc HTTP khác 302 khi failover | Giữ kết quả, khôi phục App A, nêu ảnh hưởng thực tế. Không đọc câu “không gián đoạn” khi output không chứng minh |
| App A chưa ONLINE khi hết đoạn | Chuyển video/chi phí trong khi TV2 tiếp tục theo dõi; chưa chạy lượt tải tiếp |
| Laptop mất SSH hoặc đường truy cập | Dùng mạng dự phòng đã thử; nếu vẫn lỗi, chuyển bản ghi local. Không suy từ lỗi máy trình chiếu rằng toàn bộ cụm đã hỏng |

Không signal tay/ép alarm để trình bày thành autoscaling tự động. Tải tăng chỉ tạo điều kiện; hệ thống ra quyết định theo CPU và cửa sổ đánh giá, không đếm trực tiếp số người quét. DB vẫn dùng chung và không tự scale; DB/Host A còn là điểm lỗi đơn.

## Khôi phục và lưu kết quả sau lượt chạy

TV2 thực hiện khôi phục phần tải/alarm/app do mình thử, báo kết quả để TV1 xác nhận/bàn giao; không cần giữ cả nhóm trong cuộc gọi. Bản script mới giữ log riêng, không xóa log khi `cleanup`.

1. `d load-stop`; xác nhận tải của lượt đã dừng. Nếu có tải khác, xác định người chạy trước khi xử lý.
2. `d alarm-off`; kiểm hai alarm disabled/action trống bằng hàm đã sửa hoặc công cụ đọc đã kiểm.
3. Nếu App A còn dừng, `d fail-start`; xác nhận VM ACTIVE và member A ONLINE.
4. Nếu còn 3 member, TV2 đưa về 2 theo quy trình đã chốt. Nếu signal tay để dọn thì ghi rõ là khôi phục, không tính thành scale-in tự động.
5. Xác nhận stack ổn định, đúng 2 member ONLINE, health 200, link 302 và portal còn hoạt động. Lưu log, chạy `d cleanup` và đọc output.
6. Nếu cần lượt tải khác, chờ metric cũ không làm sai điều kiện thử, kiểm lại baseline và dùng mã link mới. Lượt ráp lời nói/chuyển cảnh không cần phát tải lại.
7. Bàn giao người còn dùng cụm; khi kết thúc phiên, hủy keepalive, đóng phiên của mình và tuân thủ `campus-check`/runbook. Chỉ Stop khi đủ điều kiện, B trước A sau; ghi giờ UTC thật trong [nhật ký cloud #4](https://github.com/luongkien25/campuslink/issues/4).

## Cách chốt sau khi thành viên kiểm

Mỗi người gửi **bản chốt kịch bản trước**, rồi gửi **kết quả tự tập sau** trong issue chung. TV1 tổng hợp các phần trước bảo vệ; không tự chốt thay thành viên. Lượt ráp nhóm 10–15 phút trên máy chung tập đúng việc từng người tiếp quản bàn phím, tự nói/tự bấm rồi giao cho người tiếp theo. Không coi việc thành viên mới đọc tài liệu là đã tập xong.

| Mục | Ghi sau lượt kiểm |
| --- | --- |
| Thời lượng | Tổng và đoạn nào vượt khung |
| Portal | Chiến dịch, PDF/QR, luật thiết bị, check-in và CSV chạy live hay dùng clip; bằng chứng |
| Autoscaling | Slug, giờ tải/ALARM/member ONLINE, live hay video |
| Failover | Thời gian phát hiện/khôi phục, HTTP lỗi hoặc timeout quan sát được |
| Khôi phục | Member, alarm/action, tải còn chạy và người nhận bàn giao |
| Việc sửa | Triệu chứng, người nhận, hạn và cách kiểm xong |

Đạt mục tiêu khi có lượt trình bày không quá 10 phút, giải thích đúng output, chuyển lượt rõ và mở được phương án dự phòng. Minh họa đủ nhóm tính năng không thay thế kiểm nghiệm thu chi tiết từng yêu cầu.

## Tài liệu mở sâu khi được hỏi

- [SRS mục 6.2](../SRS.md): đối chiếu 8 hạng mục bắt buộc.
- [Acceptance](../acceptance.md): trạng thái chính thức từng yêu cầu, gồm phần đạt một phần và rút khỏi phạm vi.
- [Evidence portal trên cụm 23/11](../../evidence/G3/20261123-FR-APP-13-19-portal-len-cum-smoke-va-stop-start.txt): nghiệp vụ, clip và stop/start.
- [Portal README](../../app/portal/README.md): chức năng, đường dẫn giao diện và giới hạn polling/lô đồng bộ; ưu tiên evidence mới khi gặp ghi chú cũ.
- [H1 smoke Shlink trên cụm](../../evidence/G3/20261118-FR-APP-01-12-h1-smoke-cum.txt): tạo/sửa link, nhất quán backend, API/key và giao diện.
- [Restore fixture](../../evidence/G3/20261116-FR-INF-16-H5-fixture-restore-cum.txt): kiểm dữ liệu sau khôi phục vào DB riêng.
- [Tự scale hai chiều 21/11](../../evidence/G4/20261121-FR-INF-11-tu-scale-aodh-heat-hai-chieu.txt): timeline; mốc request đầu trên VM mới ở lượt tự động còn thiếu trong acceptance.
- [ADR 12](../decisions/ADR-12-aodh-rate-tung-vm.md): bản vá Aodh và gate đánh giá metric.
- [Issue 93](https://github.com/luongkien25/campuslink/issues/93): phối hợp phần bảo vệ TV2; [issue 74](https://github.com/luongkien25/campuslink/issues/74): video và phối hợp nhóm trước đây.
