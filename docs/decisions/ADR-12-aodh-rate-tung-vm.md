# ADR-12: Sửa cách Aodh tính `rate:mean` cho alarm CPU: lấy rate từng VM rồi mới trung bình (một bản vá cục bộ trên host A)

- Ngày: 15/11/2026 · Người quyết: TV1 · Trạng thái: **đề xuất, chờ nhóm duyệt** theo `AGENTS.md` mục 3 và 7 (sửa mã dịch vụ nền đã khóa phiên bản). TV2 duyệt là bắt buộc (chủ FR-INF-10/11, NFR-05 và đồng sở hữu `/infra/devstack/`). Đề nghị phản hồi trước **12:00 17/11/2026**; không phản hồi kịp thì không áp bản vá (mục "Nếu không duyệt kịp").

## Bối cảnh

FR-INF-11 và NFR-05 yêu cầu scale-out khi CPU > 60% qua 2 cửa sổ 60 s và scale-in khi < 25% qua 3 cửa sổ 60 s. Hai alarm của TV2 (`infra/heat/alarms.yaml`) dùng `gnocchi_aggregation_by_resources_threshold`, metric `cpu`, `aggregation_method: rate:mean`, granularity 60.

Issue #47 (TV2) nêu rủi ro bucket CPU thiếu hoặc âm. TV1 đã đọc source và đo trên cụm (15/11/2026):

- Aodh `e07aeb6d118b4b9099947028e6e809a6bdd8fe22` (HEAD của `/opt/stack/aodh` trên A, cây làm việc sạch): `aodh/evaluator/gnocchi.py:155-162` dựng `operations = ['aggregate', 'rate:mean', ['metric', 'cpu', 'mean']]`. Đó là danh sách viết cứng trong mã, không phải cấu hình.
- Gnocchi 4.7.1 (`4a41c1d05052bcabf19fbe2e5bfb5a036a321d32`, `gnocchi/rest/aggregates/operations.py:39-45, 227-235`): `rate:mean` ở bước gộp là `numpy.diff(nanmean(counter các VM))`, tức hiệu của *trung bình counter* theo thời gian, không phải trung bình tốc độ từng VM. Khi tập VM có điểm khác nhau giữa hai bucket liền nhau (VM mới tham gia, VM chưa ghi điểm vào bucket đang ghi, VM thiếu điểm), giá trị lệch theo chênh lệch counter giữa các VM, không còn liên quan tới CPU.
- `needed_overlap=0` (`gnocchi.py:167`) cho phép VM thiếu điểm vẫn được gộp, và `_sanitize` (`gnocchi.py:42-63`) không lọc bucket đang ghi hay giá trị âm.
- Khi alarm đang `insufficient data` và cửa sổ lẫn lộn, state mới lấy theo **điểm cuối** (`threshold.py:100-119`, `:146-157`).

## Quyết định

1. Áp một bản vá cục bộ lên `aodh/evaluator/gnocchi.py` (chỉ lớp `GnocchiAggregationResourcesThresholdEvaluator`, 10 dòng thêm, 5 dòng xóa): với aggregation `rate:X`, `operations` thành `['aggregate', 'X', ['metric', <metric>, 'rate:X']]`, tức rate từng VM rồi mới gộp. Aggregation không có tiền tố `rate:` cho đúng kết quả cũ. Bản vá ở `infra/devstack/patches/aodh-adr12-rate-per-vm.patch` (sha256 `9afebdfcd1e9ceeab495c4353e393034d64500becce3b66cb6a20a41ddc96d20`), áp bằng `git apply`.
2. Chỉ áp trên host A (nơi chạy `aodh-evaluator`). Không sửa Gnocchi, Ceilometer, template Heat. **Không đổi** ngưỡng, granularity, `evaluation_periods`, cooldown: NFR-05 giữ nguyên; bản vá đưa giá trị Aodh về đúng định nghĩa CPU của NFR-05 (từng VM, từ Δcpu_ns), không đổi tiêu chí.
3. `docs/versions.lock` ghi `aodh_sha=e07aeb6d118b4b9099947028e6e809a6bdd8fe22` (đang `REPLACE_SHA`) và sha256 của bản vá.
4. Áp ngoài lúc đang đo, trước khi bật action của hai alarm. Mọi lệnh đổi trạng thái do TV1 chạy sau khi ADR được duyệt (`AGENTS.md` mục 6).
5. Action của alarm (tự scale, FR-INF-11) chỉ được bật khi bản vá đạt các điều kiện ở mục "Điều kiện nghiệm thu bản vá".

## Căn cứ (đã đo)

Probe chỉ-đọc của TV1 chạy truy vấn Gnocchi kiểu Aodh và so với CPU tính riêng từng VM; hai alarm vẫn `disabled`, nên đây là **mô phỏng truy vấn**, không phải Aodh đang chạy.

- **15/11, 06:29–06:49Z, 2 VM ổn định, CPU đúng ≈ 0,6%:** bucket đã đóng 0/240 dòng lệch. Bucket đang ghi 17/63 dòng âm (−22% đến −24% so với đúng ≈ +0,65%), tập trung ở giây :12 đến :26 của mỗi phút (lúc một VM đã ghi điểm, VM kia chưa). Chưa có quyết định sai vì CPU thật dưới ngưỡng low.
- **15/11, 07:06–07:56Z, xuyên lượt scale tay 2→3→2 của TV2** (mốc do TV2 báo cho TV1, UTC: scale-out 07:35:59, đủ 3 VM ONLINE 07:38:22, scale-in 07:45:22, về 2 app 07:47:03; chưa có evidence trong repo, TV1 chưa đối chiếu Heat events):

| | Aodh hiện tại | Rate từng VM rồi trung bình |
| --- | --- | --- |
| Bucket đã đóng (594 dòng, 53 bucket) | 12 dòng lệch, thuộc **1 bucket (07:37, bucket VM thứ ba tham gia)**, sai tới lần quan sát cuối (tuổi 174 s) | 0 lệch |
| Bucket đang ghi (157 dòng) | 49 lệch, 46 âm | 1 lệch (chưa giải thích) |
| low, mô phỏng: cả 3 điểm < 25% trong khi giá trị đúng thì không | **5 mẫu, 2 cửa sổ** | 0 |
| low, mô phỏng: cửa sổ lẫn lộn mà điểm cuối âm làm đường "trending" sai | **5 mẫu, 5 cửa sổ** | 0 |
| high, mô phỏng | 0 sai (không có ý nghĩa: chưa có hai bucket liên tiếp > 60%) | 0 |

  "Giá trị đúng" ở đây là **khớp tham chiếu của probe** (trung bình, trên các VM có đủ hai điểm liên tiếp, của hiệu counter từng VM), chưa đối chiếu độc lập; ở bucket 07:37 tham chiếu chỉ gồm hai VM cũ.

  Bucket 07:37: Aodh hiện tại cho 10,1% (từng −35,1% lúc còn đang ghi), tham chiếu 61,8%; không tự lành trong 174 s quan sát sau khi bucket đóng. Từ 07:37:20,8Z đến 07:38:21,7Z (5 mẫu liên tiếp), cửa sổ 3 điểm của low là `[0,6; 21,5; −35,1]` rồi `[0,6; 21,5; 10,1]` (tham chiếu `[0,6; 21,5; 61,8]`), sau đó `[21,5; 10,1; −17,9]`; cả ba điểm dưới 25% nên mô phỏng cho low = ALARM. Năm cửa sổ "trending" (07:39:22Z đến 07:45:12Z) có điểm cuối của Aodh từ −30,7% đến −108,5% trong khi tham chiếu là `ok`.

  **Điều chưa chứng minh:** trước 07:37 CPU thấp nên low đúng đã là ALARM liên tục (122 mẫu từ 07:06:13Z); nếu alarm thật đang bật thì nó đã ở ALARM từ trước, nên các cửa sổ "ALARM sai" **không tạo chuyển state** trong lượt đo này. Lượt này là scale tay có tải do TV2 (TV2 báo "tải đã dừng" lúc 07:47; loại và mức tải chưa rõ; CPU đúng lên 21,5% lúc 07:36 rồi 61,8% lúc 07:37), không phải scale do alarm; **chưa chứng minh scale-in sai khi scale do alarm**, và hậu quả trong trường hợp đó có thể khác (trì hoãn hoặc chặn scale-out). Phải đo ở phiên 16/11.
- Phép "rate từng VM rồi trung bình" ở bảng trên chính là kết quả của `['aggregate','mean',['metric','cpu','rate:mean']]`, đã chạy được bằng quyền `member` trên Gnocchi thật (`error_samples=0`). Policy `ceilometer-high-rate` có sẵn `rate:mean` từng metric (evidence GĐ6, 14/11).
- **Giới hạn:** mô phỏng, không phải evaluator thật; một lần VM tham gia; có tải do TV2 trong khoảng 07:36–07:47 (loại, mức và thời điểm bắt đầu chưa rõ); chưa có alarm history lúc VM thứ ba tham gia; hai app VM khởi động lại cùng lúc cụm bật (console log VM A: cloud-init 06:18:01Z; chưa kiểm VM B, chưa đọc counter) nên độ lệch với VM chạy lâu chưa đo; `threshold`, `repeat_actions` và state thật của hai alarm chưa đối chiếu (template đặt `repeat_actions=false`); chu kỳ đánh giá 60 s là suy từ alarm history GĐ6, chưa kiểm `aodh.conf`.
- Evidence sẽ thêm cùng PR: bản tóm tắt đã lọc của hai lần chạy ở `evidence/G4/` (không có ID VM, project hay credential). Script probe nằm ngoài repo; đưa vào `ops/` nếu nhóm muốn (thuộc review `/ops/`).

## Phương án đã loại

- **Giữ Aodh nguyên trạng, chấp nhận rủi ro:** đã đo giá trị sai có hệ thống ở bucket đang ghi và ở bucket VM tham gia, cùng các cửa sổ mà quyết định mô phỏng sai; hậu quả khi scale do tải chưa đo, nên chưa đủ căn cứ coi là an toàn để bật action.
- **Chỉ bật action khi alarm đang `ok`:** giảm xác suất đường "trending" nhưng không loại, vì alarm có thể quay về `insufficient data` bất kỳ lúc nào; bucket VM tham gia sai kéo dài nhiều phút, ngoài bucket đang ghi.
- **Tăng `evaluation_periods`:** không sửa được bucket VM tham gia (sai vĩnh viễn trong cửa sổ) và đổi tiêu chí NFR-05.
- **Bộ điều khiển scale tự viết đọc Gnocchi trực tiếp, thay Aodh:** đổi ràng buộc "scaling bằng Heat + Aodh + Gnocchi" (`AGENTS.md` mục 3) và thêm thành phần mới sát mốc cắt.
- **Đổi metric hoặc pipeline Ceilometer** (ví dụ metric tốc độ có sẵn): cần đổi archive policy và cấu hình dịch vụ nền, rủi ro lớn hơn một bản vá nhỏ.
- **Sửa Gnocchi:** lỗi nằm ở cách Aodh dựng truy vấn, không phải ở Gnocchi.

## Cách áp, kiểm và lùi (TV1 làm, chỉ sau khi ADR được duyệt)

Trước khi áp, chỉ đọc (kết quả mong đợi trong ngoặc):
```
git -C /opt/stack/aodh rev-parse HEAD                   # e07aeb6d118b4b9099947028e6e809a6bdd8fe22
git -C /opt/stack/aodh status --short                   # rỗng
sudo -u stack /opt/stack/data/venv/bin/python3 -c "import aodh; print(aodh.__file__)"   # nằm trong /opt/stack/aodh (chưa kiểm: cài kiểu editable)
systemctl is-active devstack@aodh-evaluator             # active
```
Áp (đổi trạng thái dùng chung):
```
sudo -u stack git -C /opt/stack/aodh apply --check /tmp/aodh-adr12-rate-per-vm.patch
sudo -u stack git -C /opt/stack/aodh apply /tmp/aodh-adr12-rate-per-vm.patch
git -C /opt/stack/aodh diff --stat                      # 1 file, 10 chèn, 5 xóa
sudo systemctl restart devstack@aodh-evaluator
systemctl is-active devstack@aodh-evaluator             # active
sudo journalctl -u devstack@aodh-evaluator --since "-3min" | grep -ciE 'traceback|error'   # 0
```
Lùi (dưới 1 phút, không ảnh hưởng dữ liệu: state alarm lưu trong DB Aodh):
```
sudo -u stack git -C /opt/stack/aodh apply -R /tmp/aodh-adr12-rate-per-vm.patch
sudo systemctl restart devstack@aodh-evaluator
git -C /opt/stack/aodh status --short                   # rỗng
```
Bản vá đã thử `git apply --check`, áp và `git apply -R --check` trên bản upstream sạch ngoài cụm (15/11); **chưa thử trên A**.

## Điều kiện nghiệm thu bản vá

Đạt đủ cả năm thì TV2 mới bật action:
1. `git diff` trên A chỉ khác đúng bản vá; `aodh-evaluator` `active` và không có traceback sau 5 phút.
2. Hai alarm bật **chỉ đánh giá** (actions rỗng) ít nhất 15 phút: không kẹt `insufficient data`, state hợp lý với CPU.
3. Một lần VM thứ ba tham gia (scale tay) **khi CPU nền không thấp hơn ngưỡng low** (cần tải nền khoảng 30–60%, ví dụ của TV4, để alarm low đang ở `ok`; lúc rảnh low đúng đã là ALARM nên không kiểm được gì): alarm history **không** có low chuyển sang ALARM trong khoảng VM tham gia; `most recent` trong lý do chuyển state khớp tham chiếu của probe.
4. Dưới tải của TV4: high chuyển ALARM đúng lúc, không bị chặn; nếu tải không vượt 60% thì ghi vào O-10, không hạ ngưỡng.
5. TV2 xác nhận `openstack alarm show` của hai alarm (`alarm_actions`, `ok_actions`, `insufficient_data_actions` rỗng cho tới khi bật action; `repeat_actions=false`).

## Nếu không duyệt kịp, hoặc không đạt

Không áp bản vá. Giữ action tắt. Báo cáo FR-INF-11 là **đạt một phần**: alarm đúng khi tập VM ổn định (bucket đã đóng), sai khi VM tham gia và ở bucket đang ghi (số đo ở mục Căn cứ); lượt scale tay 2→3→2 có timeline thật; không nhận autoscaling tự động là PASS. Nhóm (và giảng viên nếu cần) quyết định phạm vi.

## Hệ quả

- Host A khác upstream đúng một file. Chạy lại `stack.sh` (đã cấm khi cụm có tài nguyên) sẽ xóa bản vá; nếu phải chạy thì áp lại trước khi bật action.
- `docs/versions.lock` điền `aodh_sha` và sha256 bản vá; khi áp bản vá sẽ thêm vào `docs/runbooks/after-start.md` (phần telemetry) kiểm `git -C /opt/stack/aodh diff --stat` (1 file); PR này không đổi runbook để tránh xung đột với PR #46.
- SRS không đổi: NFR-05 và FR-INF-11 giữ nguyên tiêu chí; chỉ đổi cách Aodh tính giá trị đưa vào tiêu chí đó.
- Chủ review của PR: `docs/decisions/` và `docs/versions.lock` (mặc định TV1), `infra/devstack/patches/` (TV1, TV2), `evidence/` (TV4).
- Vấn đề mở mới: tương tác của bản vá với `needed_overlap=0` khi VM bị xóa giữa chừng (FIXME của upstream) chưa kiểm; đo ở điều kiện nghiệm thu 3 và 4.
