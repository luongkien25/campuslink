# ADR-12: Sửa cách Aodh tính `rate:mean` cho alarm CPU: lấy rate từng VM rồi mới trung bình (một bản vá cục bộ trên host A)

- Ngày: 15/11/2026 · Người quyết: TV1 · Trạng thái (cập nhật 18/11/2026): **đã áp thử có kiểm soát trên host A lúc 17/11/2026 13:35:09Z (TV1); gate dữ liệu CHƯA ĐẠT; chưa bật action; giữ bản vá trên A (TV2 ghi nhận trong [mô tả PR #64](https://github.com/luongkien25/campuslink/pull/64), 18/11/2026)** theo `AGENTS.md` mục 3 và 7 (sửa mã dịch vụ nền đã khóa phiên bản). TV2 duyệt là bắt buộc (chủ FR-INF-10/11, NFR-05 và đồng sở hữu `/infra/devstack/`); nếu TV2 hoặc nhóm yêu cầu lùi thì lùi theo mục "Cách áp, kiểm và lùi". Kết quả phiên 17/11 ở mục "Kết quả phiên 17/11/2026".

## Bối cảnh

FR-INF-11 và NFR-05 yêu cầu scale-out khi CPU > 60% qua 2 cửa sổ 60 s và scale-in khi < 25% qua 3 cửa sổ 60 s. Hai alarm của TV2 (`infra/heat/alarms.yaml`) dùng `gnocchi_aggregation_by_resources_threshold`, metric `cpu`, `aggregation_method: rate:mean`, granularity 60.

Issue #47 (TV2) nêu rủi ro bucket CPU thiếu hoặc âm. TV1 đã đọc source và đo trên cụm (15/11/2026):

- Aodh `e07aeb6d118b4b9099947028e6e809a6bdd8fe22` (HEAD của `/opt/stack/aodh` trên A, `git status --short` rỗng; TV1 chạy sau 07:56Z ngày 15/11, giờ chính xác chưa ghi): `aodh/evaluator/gnocchi.py:155-162` dựng `operations = ['aggregate', 'rate:mean', ['metric', 'cpu', 'mean']]`. Đó là danh sách viết cứng trong mã, không phải cấu hình.
- Gnocchi 4.7.1 (`4a41c1d05052bcabf19fbe2e5bfb5a036a321d32`, `gnocchi/rest/aggregates/operations.py:39-45, 227-235`): `rate:mean` ở bước gộp là `numpy.diff(nanmean(counter các VM))`, tức hiệu của *trung bình counter* theo thời gian, không phải trung bình tốc độ từng VM. Khi tập VM có điểm khác nhau giữa hai bucket liền nhau (VM mới tham gia, VM chưa ghi điểm vào bucket đang ghi, VM thiếu điểm), giá trị lệch theo chênh lệch counter giữa các VM, không còn liên quan tới CPU.
- `needed_overlap=0` (`gnocchi.py:167`) cho phép VM thiếu điểm vẫn được gộp, và `_sanitize` (`gnocchi.py:42-63`) không lọc bucket đang ghi hay giá trị âm.
- Khi alarm đang `insufficient data` và cửa sổ lẫn lộn, state mới lấy theo **điểm cuối** (`threshold.py:100-119`, `:146-157`).

### Cập nhật review ngày 16/11/2026

- [TV4 đã APPROVE](https://github.com/luongkien25/campuslink/pull/51#pullrequestreview-5911937928) phần evidence và hướng ADR. [TV2 đồng ý hướng sửa để thử có kiểm soát](https://github.com/luongkien25/campuslink/pull/51#pullrequestreview-5915451775), đồng thời yêu cầu chốt gate cho metric thiếu/âm/cũ trước khi bật action. Review TV2 có trạng thái GitHub `COMMENTED`; không diễn giải thành bản vá đã nghiệm thu.
- [TV2 bổ sung nguồn tải và cấu hình alarm](https://github.com/luongkien25/campuslink/issues/47#issuecomment-6908651479): ApacheBench trên host A, GET redirect qua VIP nội bộ, keep-alive/concurrency 32, từ `15/11 07:35:59.053906Z` đến `07:47:03.262872Z`; 23.173 request/664,204 s, khoảng 34,89 RPS. Đây không phải workload 80/15/5 hay benchmark HTTPS/p95 của TV4. Snapshot `16/11 05:42:08.609980Z` do TV2 báo: high `ok`, low `alarm`, cả hai `enabled=False`, mọi actions rỗng, `repeat_actions=False`; ngưỡng high/low và số kỳ khớp NFR-05. TV1 chưa kiểm độc lập snapshot này trên A; không dùng nó thay cấu hình cần đọc ngay trước phiên đo.
- Cập nhật lịch 16/11 theo xác nhận của TV1: TV2 và TV4 đã thống nhất lùi giờ bắt đầu xuống **20:30 giờ VN**, giữ thời lượng dự kiến hai giờ (**20:30–22:30**, 13:30–15:30 UTC). TV1 bật probe trước **20:25**; vẫn đo baseline chưa vá, chỉ bật đánh giá, mọi actions rỗng. Lịch mới được cập nhật tại #44. TV4 cũng rảnh tối 17/11 hoặc sáng 18/11; khung nghiệm thu sau vá vẫn cần TV2 xác nhận.

## Quyết định

1. Áp một bản vá cục bộ lên `aodh/evaluator/gnocchi.py` (chỉ lớp `GnocchiAggregationResourcesThresholdEvaluator`, 10 dòng thêm, 5 dòng xóa): với aggregation `rate:X`, `operations` thành `['aggregate', 'X', ['metric', <metric>, 'rate:X']]`, tức rate từng VM rồi mới gộp. Aggregation không có tiền tố `rate:` cho đúng kết quả cũ. Bản vá ở `infra/devstack/patches/aodh-adr12-rate-per-vm.patch` (sha256 `9afebdfcd1e9ceeab495c4353e393034d64500becce3b66cb6a20a41ddc96d20`), áp bằng `git apply`.
2. Chỉ áp trên host A (nơi chạy `aodh-evaluator`). Không sửa Gnocchi, Ceilometer, template Heat. **Không đổi** ngưỡng, granularity, `evaluation_periods`, cooldown: NFR-05 giữ nguyên; bản vá đưa giá trị Aodh về đúng định nghĩa CPU của NFR-05 (từng VM, từ Δcpu_ns), không đổi tiêu chí.
3. `docs/versions.lock` ghi `aodh_sha=e07aeb6d118b4b9099947028e6e809a6bdd8fe22` (đang `REPLACE_SHA`), `aodh_patch` (đường dẫn) và `aodh_patch_sha256`. `.gitattributes` thêm `*.patch text eol=lf` để Windows không đổi bản vá sang CRLF (làm lệch sha256).
4. Áp ngoài lúc đang đo, trước khi bật action của hai alarm. Mọi lệnh đổi trạng thái do TV1 chạy sau khi ADR được duyệt (`AGENTS.md` mục 6).
5. Bản vá này chỉ sửa phép tính rate; không bổ sung kiểm độ phủ metric, timestamp, counter reset hoặc giá trị âm. **Chưa cho bật action của cả high và low.** Muốn bật tự scale (FR-INF-11) phải đạt cả kiểm phép tính và gate dữ liệu ở mục "Điều kiện nghiệm thu bản vá"; vài lượt tải không có lỗi không chứng minh evaluator tự từ chối dữ liệu sai.

## Căn cứ (đã đo)

Probe chỉ-đọc của TV1 chạy truy vấn Gnocchi kiểu Aodh và so với CPU tính riêng từng VM; hai alarm vẫn `disabled`, nên đây là **mô phỏng truy vấn**, không phải Aodh đang chạy.

- **15/11, 06:29–06:49Z, 2 VM ổn định, CPU đúng ≈ 0,6% (trừ hai bucket 06:27 và 06:28, khoảng 11–13%):** bucket đã đóng 0/240 dòng lệch. Bucket đang ghi 17/63 dòng âm (−22% đến −24% so với đúng ≈ +0,65%), tập trung ở giây :12 đến :26 của mỗi phút (lúc một VM đã ghi điểm, VM kia chưa). Chưa có quyết định sai vì CPU thật dưới ngưỡng low.
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

  **Điều chưa chứng minh:** trước 07:37 CPU thấp nên low đúng đã là ALARM liên tục (122 mẫu từ 07:06:13Z); nếu alarm thật đang bật thì nó đã ở ALARM từ trước, nên các cửa sổ "ALARM sai" **không tạo chuyển state** trong lượt đo này. Lượt này là scale tay có tải do TV2 (TV2 ghi "tải đã dừng" cùng dòng mốc 07:47:03, không nêu giờ dừng; loại và mức tải chưa rõ; CPU đúng lên 21,5% lúc 07:36 rồi 61,8% lúc 07:37), không phải scale do alarm; **chưa chứng minh scale-in sai khi scale do alarm**, và hậu quả trong trường hợp đó có thể khác (trì hoãn hoặc chặn scale-out; suy từ mã, chưa thử trên cụm). Phải đo ở phiên 16/11.
- Phép "rate từng VM rồi trung bình" ở bảng trên chính là kết quả của `['aggregate','mean',['metric','cpu','rate:mean']]`, đã chạy được bằng quyền `member` trên Gnocchi thật (`error_samples=0`). Ứng viên dùng cùng công thức với tham chiếu nên việc nó khớp là điều đã định sẵn; giá trị của phép đo là so với Aodh hiện tại và việc truy vấn chạy được trên Gnocchi thật, không phải kiểm độc lập. Policy `ceilometer-high-rate` có sẵn `rate:mean` từng metric (evidence GĐ6, 14/11).
- **Giới hạn:** mô phỏng, không phải evaluator thật; một lần VM tham gia; có tải do TV2 trong khoảng 07:36–07:47 (loại, mức và thời điểm bắt đầu chưa rõ); chưa có alarm history lúc VM thứ ba tham gia; hai app VM khởi động lại cùng lúc cụm bật (console log VM A: cloud-init 06:18:01Z; chưa kiểm VM B, chưa đọc counter) nên độ lệch với VM chạy lâu chưa đo; `threshold`, `repeat_actions` và state thật của hai alarm chưa đối chiếu (template đặt `repeat_actions=false`); chu kỳ đánh giá 60 s là suy từ alarm history GĐ6, chưa kiểm `aodh.conf`.
- Evidence sẽ thêm cùng PR: bản tóm tắt đã lọc của hai lần chạy ở `evidence/G4/` (không có ID VM, project hay credential). Script probe nằm ngoài repo; đưa vào `ops/` nếu nhóm muốn (thuộc review `/ops/`).

## Phương án đã loại

- **Giữ Aodh nguyên trạng, chấp nhận rủi ro:** đã đo giá trị sai có hệ thống ở bucket đang ghi và ở bucket VM tham gia, cùng các cửa sổ mà quyết định mô phỏng sai; hậu quả khi scale do tải chưa đo, nên chưa đủ căn cứ coi là an toàn để bật action.
- **Chỉ bật action khi alarm đang `ok`:** giảm xác suất đường "trending" nhưng không loại, vì alarm có thể quay về `insufficient data` bất kỳ lúc nào; bucket VM tham gia sai kéo dài nhiều phút, ngoài bucket đang ghi.
- **Tăng `evaluation_periods`:** không sửa được bucket VM tham gia (không tự lành trong 174 s quan sát; suy từ cách tính là cố định trong cửa sổ, chưa kiểm lâu hơn) và đổi tiêu chí NFR-05.
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
sha256sum /tmp/aodh-adr12-rate-per-vm.patch            # phải ra 9afebdfcd1e9ceeab495c4353e393034d64500becce3b66cb6a20a41ddc96d20 trước khi áp
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
Bản vá đã thử `git apply --check`, áp và `git apply -R --check` trên bản upstream sạch ngoài cụm (15/11). **Đã áp trên A lúc 17/11/2026 13:35:09Z**, evaluator khởi động lại; chưa lùi lần nào trên A.

## Điều kiện nghiệm thu bản vá

**Lịch:** phiên 16/11 chỉ đo baseline **chưa vá** (alarm history thật dưới tải, chế độ đánh giá), theo xác nhận ở mục cập nhật review. Nghiệm thu sau vá dự kiến tối 17/11 hoặc sáng 18/11 (TV4 đã rảnh, chờ TV2 xác nhận), trước snapshot EBS 18/11 và freeze 19/11. Không làm gián đoạn lượt benchmark để thử lỗi telemetry.

### 1. Kiểm phép tính sau vá (chưa đủ để bật action)

Trong tất cả các lượt dưới đây, `alarm_actions`, `ok_actions` và `insufficient_data_actions` phải rỗng:

1. `git diff` trên A chỉ khác đúng bản vá; `aodh-evaluator` `active` và không có traceback sau 5 phút.
2. Hai alarm bật **chỉ đánh giá** (actions rỗng) ít nhất 15 phút: không kẹt `insufficient data`, state hợp lý với CPU.
3. Một lần VM thứ ba tham gia (scale tay) **khi CPU nền không thấp hơn ngưỡng low** (cần tải nền khoảng 30–60%, ví dụ của TV4, để alarm low đang ở `ok`; lúc rảnh low đúng đã là ALARM nên không kiểm được gì): alarm history **không** có low chuyển sang ALARM trong khoảng VM tham gia; `most recent` trong lý do chuyển state khớp tham chiếu của probe.
4. Dưới tải của TV4: high chuyển ALARM đúng lúc, không bị chặn; nếu tải không vượt 60% thì ghi vào O-10, không hạ ngưỡng.
5. TV2 xác nhận `openstack alarm show` của hai alarm (`alarm_actions`, `ok_actions`, `insufficient_data_actions` rỗng cho tới khi bật action; `repeat_actions=false`).

### Kết quả phiên 17/11/2026 (đã áp bản vá trên A)

Nguồn: bảng nhật ký UTC ở #61 (TV1 điền) và các comment của TV2 ở #61 (13:48Z–15:08Z). Probe tmux 17/11 đã chép về laptop lúc 15:18Z (sha256 `54e37c74aeb571d7ea2ddf6f1917f3d8254b67be02bcff9a32118cc7a1304a99`), nhưng TV1 chưa dùng nó để đối chiếu lại các mục dưới đây; bản trên A đã mất do `/tmp` bị dọn khi boot. Suốt phiên cả ba danh sách actions rỗng và `repeat_actions=false`.

| Mục | Kết quả |
| --- | --- |
| 1.1 | Đạt. Bản vá áp lúc 13:35:09Z (sha256 `9afebdfc…`); TV2 đối chiếu độc lập: chỉ `gnocchi.py` đổi, khớp upstream cộng bản vá. |
| 1.2 | Đạt. Hai alarm `enabled` không muộn hơn 13:48:10Z; low ở `alarm` lúc chưa tải, về `ok` lúc 14:27:10Z khi có tải 30 RPS. |
| 1.3 | Đạt trong một lần quan sát. Signal scale-out 14:28:00Z, 3 ONLINE lần đầu thấy 14:29:27Z, signal scale-in 14:36:51Z; history TV2 thu không có low→ALARM trong khoảng VM thứ ba tham gia. |
| 1.4 | **Chưa kiểm được (O-10).** Lượt B lần 1 bị hủy (khoảng 32 RPS do máy phát); lần 2 bị dừng cưỡng bức lúc 15:00:24Z (17.880/25.200 request, khoảng 33 RPS). CPU mean các bucket đóng 14:52–14:57 chỉ 39–51%, chưa quá 60%. Không hạ ngưỡng. |
| 1.5 | Đạt. TV2 `alarm show` lúc 15:05:13Z: `enabled=false`, ba danh sách actions rỗng, `repeat_actions=false`. |

Kết luận: phép tính sau vá đạt bốn trong năm mục, mục 1.4 chưa kiểm được. Gate dữ liệu (mục 2) vẫn **chưa đạt**, nên không bật action và FR-INF-11 báo "đạt một phần" ([kết luận TV1 ở #47](https://github.com/luongkien25/campuslink/issues/47#issuecomment-6976933022)). Bản vá đang áp trên A; TV1 đề xuất **giữ** (actions rỗng) vì lùi cần thêm một lần SSH mà không đổi kết luận. Nếu TV2 hoặc nhóm yêu cầu lùi, TV1 chạy `git apply -R` ở mục "Cách áp, kiểm và lùi" trước snapshot EBS và freeze.

### 2. Gate dữ liệu trước khi cho phép tự scale

Đối chiếu lại đúng source Aodh `e07aeb6d118b4b9099947028e6e809a6bdd8fe22` ngày 16/11: `_sanitize` lấy giá trị theo granularity rồi lấy N điểm cuối; `evaluate_rule` kiểm số điểm, không kiểm tính liên tiếp, độ mới hoặc độ phủ VM. Bản vá giữ `needed_overlap=0` và giữ nguyên các hàm này. Vì vậy **gate dữ liệu hiện CHƯA ĐẠT**. Probe bên ngoài chỉ phát hiện lỗi; người vận hành nhìn probe không phải cơ chế tự bảo vệ evaluator.

| Trường hợp phải kiểm | Kết quả bắt buộc trước bật action | Tình trạng ở bản vá hiện tại |
| --- | --- | --- |
| CPU thấp hợp lệ | 3 bucket 60 s liên tiếp đã đóng, không âm, đủ dữ liệu từng VM trong cohort; mỗi bucket < 25% thì low mới được coi hợp lệ | Cần đối chiếu dữ liệu từng VM và alarm history; probe hiện có chỉ tham chiếu trên VM đủ hai điểm |
| VM mới chưa có metric `cpu`, hoặc thiếu một trong hai điểm counter | Không thay metric thiếu bằng 0, không bỏ VM âm thầm để kết luận cả nhóm CPU thấp | `needed_overlap=0` cho phép gộp trên phần còn lại; chưa có chốt tự bảo vệ |
| Counter reset/giá trị âm hoặc không hữu hạn | Không tính là CPU thấp hợp lệ và không sinh quyết định high/low từ cửa sổ sai | `_sanitize` chưa lọc; đổi vị trí rate không xử lý reset counter |
| Bucket đang ghi, thiếu bucket giữa hoặc chỉ còn điểm cũ | Không đủ N bucket liên tiếp đã đóng theo thời gian đánh giá thì không dùng cửa sổ đó để scale | Chỉ đếm N điểm; chưa có kiểm timestamp/độ mới. Đọc `evaluation_interval`/`additional_ingestion_lag` bằng allowlist khi cụm bật; không in toàn bộ `aodh.conf` |
| VM rời cohort trong lượt 3→2 | Đối chiếu cohort trước/sau bằng tài nguyên thật và metric từng VM; không sinh ALARM từ phép gộp sai | Chưa nghiệm thu; phải đo cả chiều rời cohort, không chỉ VM tham gia |

TV1 và TV2 cần chốt **cơ chế chạy tự động từ chối cửa sổ sai trước khi evaluator có thể phát action**, cùng định nghĩa cohort, mốc độ mới và cách quay lại đánh giá sau khi đủ dữ liệu. Đây là phần bổ sung cần nhóm review; không tự coi một script giám sát, `repeat_actions=false`, hoặc việc bật action lúc state `ok` là đã giải quyết. Nếu sửa thêm mã evaluator thì cập nhật ADR, bản vá và checksum, chạy kiểm tái lập rồi mới xin phép áp lên A.

Phép kiểm metric thiếu/reset/cũ trước hết làm offline với source đúng SHA hoặc trên môi trường thử riêng. Trên cụm dùng chung chỉ đo thụ động và lượt scale tay đã hẹn; không dừng collector, reboot app hay đổi metric để gây lỗi trong phiên G5. Mọi thử lỗi hoặc thay đổi dịch vụ phải có kế hoạch và được TV1/người dùng cho phép riêng. Offline characterization không thay bằng chứng evaluator chạy trên A.

Chỉ khi cả hai phần đạt, TV1 xác nhận bằng evidence và TV2 đối chiếu độc lập thì mới **đề xuất** bật actions theo `AGENTS.md` mục 6. Trước đó giữ actions rỗng, kể cả khi bản vá đã được phép thử có kiểm soát. Giữ #47 mở cho tới khi có kết luận và bằng chứng tương ứng.

## Gate v2.1 (20/11/2026)

Trạng thái lúc viết (20/11): đề xuất, chưa áp trên A. **Cập nhật 21/11/2026: bản này đã được áp trên A (khoảng 08:27Z) và bị thay bằng v2.2; trên cụm thật gate v2.1 từ chối mọi cửa sổ vì lỗi đọc timestamp, xem mục "Gate v2.2" bên dưới.** TV2 review PR #81 (bản v2, sha256 `efbde2e5…`) và tìm ra lỗ hổng ở nhánh hồi phục từ `insufficient data` (mục "Nhánh trending khi alarm đang insufficient data"); v2.1 sửa lỗ hổng đó, gộp vào cùng file patch (v2 chưa áp trên A, PR #81 chưa merge). Mới kiểm offline (mục "Kết quả kiểm offline"); chưa có bằng chứng evaluator chạy gate trên cụm. Vẫn là Heat + Aodh + Gnocchi; chỉ sửa lớp `GnocchiAggregationResourcesThresholdEvaluator` trong `aodh/evaluator/gnocchi.py`. **Không đổi** ngưỡng, granularity, `evaluation_periods`, cooldown, template Heat hay `threshold.py`.

- Bản vá: `infra/devstack/patches/aodh-adr12-gate-v2.patch` (nội dung v2.1), sha256 `ea3d1ceed6cd054a2fad3b5f7df10f712d56ba974668dd1293cccca97bd41bc2`; bản vá **tăng dần**, áp **sau** `aodh-adr12-rate-per-vm.patch` (v1); 1 file, 92 dòng thêm, 0 dòng xóa.
- sha256 của `aodh/evaluator/gnocchi.py` (tính offline): upstream `e07aeb6d` = `d63b84f4c61cd8f05a4f76488bc179720edf461592e94bb0c825cba91dd01ca0`; upstream + v1 = `8bc8a1153ce36c4732236834e173bb86cdf52d0fbc43170ce47eb331ad1dbb38`; upstream + v1 + v2.1 = `3d2bed8247161e54cfdaad29efcc6f5e040cc6011c251e32c000dda2798a56fb` (bản v2 cũ cho `443751e5…`, không dùng nữa).

### Cơ chế

Chỉ áp cho aggregation có tiền tố `rate:` (alarm CPU high/low). Aggregation khác đi đúng đường mã của v1 (bằng upstream). `_statistics` gọi `_campus_gate`; mọi lần từ chối đều ghi `LOG.info("campus-gate reject=<lý do> op=<gt|lt> n=<N> ...")` rồi ném `InsufficientDataError("campus-gate reject=<lý do>")`, nên alarm sang `insufficient data` (state_reason chứa lý do) và không phát `alarm_actions`; `insufficient_data_actions` của hai alarm rỗng (`infra/heat/alarms.yaml`).

1. **Chỉ bucket đã đóng:** bucket `ts` hợp lệ khi `ts + granularity + 45 s <= now` (`now` = giờ đánh giá của evaluator; 45 s vì probe 15/11 thấy điểm Gnocchi tới giây :26 của phút sau). Cửa sổ truy vấn là đúng N bucket đã đóng gần nhất: `start` = bucket đầu, `stop` = bucket cuối + 60 s (Gnocchi cắt `[start, stop)`, `gnocchi/carbonara.py:253-259` ở 4.7.1), nên bucket đang ghi không vào truy vấn.
2. **Đủ VM ở mọi bucket:** truy vấn `['aggregate', 'mean', ['metric', 'cpu', 'rate:mean']]` với `needed_overlap=100`. Theo mã Gnocchi 4.7.1 (`gnocchi/rest/aggregates/processor.py:200-220`, `api.py:169-178`), khi có `start/stop` và một VM thiếu điểm ở bất kỳ timestamp nào trong cửa sổ, Gnocchi **trả 400 cho cả truy vấn** (không loại riêng bucket đó). Gate bắt `BadRequest` → `reject=gnocchi_400`. Không thay điểm thiếu bằng 0, không bỏ VM.
3. **Đủ N bucket liền nhau và mới:** bucket mới nhất phải đúng là bucket đóng gần nhất (`reject=stale`), đủ cả N timestamp cách nhau 60 s (`reject=missing_bucket`, ví dụ mọi VM cùng thiếu một bucket giữa).
4. **Counter reset / giá trị không hữu hạn:** truy vấn thứ hai `['aggregate', 'min', ['metric', 'cpu', 'rate:mean']]` cùng cửa sổ; min < 0 ở bất kỳ bucket nào → `reject=negative` (phép mean che giá trị âm của một VM); NaN/inf ở mean hoặc min → `reject=nonfinite`. Timestamp không đọc được → `reject=bad_timestamp`.
5. Đạt cả bốn mục thì trả đúng N điểm cho `_sanitize`/`evaluate_rule` như cũ; so sánh ngưỡng không đổi.
6. **Không hồi phục theo xu hướng (v2.1):** lớp override `_transition_alarm`; khi aggregation có tiền tố `rate:`, alarm đang `insufficient data` và cửa sổ lẫn lộn (có `trending_state`), evaluator ghi `LOG.info("campus-gate hold=equivocal op=… n=… trend=…")` và **không đổi state** (không gọi `_refresh`, không notify). Mọi trường hợp khác gọi nguyên `_transition_alarm` của upstream.

### Nhánh trending khi alarm đang insufficient data (lỗ hổng của v2, TV2 phát hiện)

Đọc lại đúng source `e07aeb6d` trên cây upstream + v1 + v2:

- `aodh/evaluator/threshold.py:100-119` `_process_statistics`: khi các điểm không cùng chiều (`unequivocal` sai), trả `(None, trending_state, …)` với `trending_state = ALARM if compared[-1] else OK`, tức chỉ theo **bucket cuối**.
- `threshold.py:146-157` `_transition_alarm`: nếu có `trending_state` và `alarm.state == UNKNOWN` (`'insufficient data'`, `aodh/evaluator/__init__.py:44`) thì lấy `state = trending_state` và gọi `_refresh` (`__init__.py:120-145`), tức chuyển state và notify (phát `alarm_actions` nếu có).
- `threshold.py:168-183` `evaluate`: gọi `evaluate_rule` rồi `_transition_alarm`. 11 ca của v2 chỉ gọi `evaluate_rule` nên không đi qua nhánh này.

Hệ quả với v2: ngay sau một lần gate từ chối (alarm sang `insufficient data`), cửa sổ high `[55%, 65%]` hoặc low `[30%, 30%, 20%]` vẫn làm alarm sang ALARM với `count=1`, trái NFR-05 (đủ 2 bucket high hoặc 3 bucket low). Đã tái hiện offline: hai ca (a), (c) dưới đây **không đạt** trên v2 cũ.

Cách chọn: override `_transition_alarm` trong lớp, chỉ chặn đúng nhánh (UNKNOWN + trending + `rate:`). Đã loại: sửa `_process_statistics` (đổi cả nhánh `repeat_actions=true` khi alarm đang OK/ALARM và khó chứng minh không đổi đường mã khác); sửa `threshold.py` (ảnh hưởng mọi loại alarm, ngoài phạm vi một lớp); ném `InsufficientDataError` khi cửa sổ lẫn lộn (sẽ kéo alarm đang OK/ALARM về `insufficient data`, đổi hành vi khi alarm cũ là OK hoặc ALARM).

Rủi ro mới: alarm có thể ở `insufficient data` lâu hơn v2/upstream, tới khi có một cửa sổ quyết định (đủ N bucket cùng chiều: N bucket > 60% cho ALARM, hoặc N bucket không vượt thì OK). Với CPU dao động quanh ngưỡng, alarm có thể nằm ở `insufficient data` nhiều phút; vì `insufficient_data_actions` rỗng nên không có action sai, nhưng scale-out bị trễ tương ứng. Khi alarm đã là OK/ALARM thì hành vi như upstream (cửa sổ lẫn lộn không đổi state).

### Định nghĩa

- **Cohort:** tập resource `instance` mà Gnocchi trả cho `query` của alarm (`server_group`, `project_id`, `ended_at=null`, `deleted_at=null`) **tại thời điểm đánh giá**, và có metric `cpu` (Gnocchi tự bỏ resource không có metric khớp: `api.py:681-697`).
- **Độ mới:** bucket mới nhất phải là bucket đã đóng gần nhất theo mục 1 (tuổi bucket từ 105 s tới dưới 165 s so với giờ đánh giá).
- **Quay lại đánh giá:** tự động ở chu kỳ đánh giá kế tiếp khi lại có đủ N bucket hợp lệ; không cần người thao tác. Hệ quả: high chỉ thấy một bucket sau khi bucket đó đóng 45 s (chậm hơn v1 tối đa khoảng 45 s cộng một chu kỳ đánh giá; cần tính vào NFR-06).

### Kết quả kiểm offline (20/11/2026, laptop Windows, không chạm cụm)

Mã Aodh `e07aeb6d118b4b9099947028e6e809a6bdd8fe22` clone từ opendev, `git rev-parse HEAD` khớp; v1 kiểm sha256 `9afebdfc…` khớp, `git apply --check` rồi áp. v2.1 (sha256 `ea3d1cee…`): `git apply --check` trên cây upstream + v1: đạt; sau khi áp `git apply -R --check`: đạt, lùi xong cây về đúng v1; áp lần lượt v1 rồi v2.1 lên cây upstream sạch cho file trùng byte với cây phát triển (`3d2bed82…`). Python 3.13 trên Windows, dependency bản mới nhất từ PyPI (không phải upper-constraints 2026.1; A chạy Python 3.12): **chưa kiểm** trên đúng môi trường của A.

`infra/devstack/patches/tests/test_gate_v2.py` chạy mã evaluator thật của Aodh với Gnocchi **giả** mô phỏng `aggregated()` của Gnocchi 4.7.1 (needed_overlap, cắt `[start, stop)`, lọc `ended_at`). Ca 1–11 ở tầng `evaluate_rule`; ca (a)–(h) ở tầng `evaluate()` (đi qua `_transition_alarm` và `_refresh`; storage và notifier là mock), cấu hình như `infra/heat/alarms.yaml` (high `gt` 36e9 ns, N = 2; low `lt` 15e9 ns, N = 3; granularity 60; `repeat_actions=false`).

| Ca | Kết quả mong đợi | v1 + v2.1 | chỉ v1 (đối chứng) |
| --- | --- | --- | --- |
| 1. 2 VM ổn định, 2 bucket đóng > 60% | ALARM; truy vấn `start=09:58`, `stop=10:00`, `needed_overlap=100` | đạt | không đạt |
| 2. Bucket đang ghi (một VM có điểm âm) | bucket bị loại khỏi cửa sổ, vẫn ALARM | đạt | không đạt |
| 3. Thiếu bucket giữa (mọi VM / một VM) | insufficient (`missing_bucket` / `gnocchi_400`) | đạt | không đạt |
| 4. VM mới thiếu rate | insufficient tới khi đủ N bucket, rồi đánh giá lại tự động | đạt | không đạt |
| 5. Counter reset (min âm, mean dương) | insufficient (`negative`) | đạt | không đạt |
| 6. NaN / inf | insufficient (`nonfinite`) | đạt | không đạt |
| 7. Điểm cũ (mới nhất 09:58 lúc 10:00:50) | insufficient (`stale`; không điểm nào: `gnocchi_400`) | đạt | không đạt |
| 8. VM rời cohort có `ended_at` | đánh giá đúng hai VM còn lại | đạt | đạt |
| 9. VM rời cohort chưa có `ended_at` | insufficient, kẹt tới khi có `ended_at` | đạt | không đạt |
| 10. low: 3 bucket < 25% | ALARM | đạt | đạt |
| 11. Aggregation không `rate:` | kết quả và tham số truy vấn trùng upstream | đạt | đạt |
| 12. Test upstream `aodh/tests/unit/evaluator/test_gnocchi.py` (25 test) | | upstream 25/25; v1 24/25; v1 + v2.1 20/25 (v2 cũ cũng 20/25, cùng 5 test) | |

Ca ở tầng `evaluate()` (v2.1), cột thứ tư là **v2 cũ** (`efbde2e5…`) để đối chứng lỗ hổng:

| Ca | Kết quả mong đợi | v1 + v2.1 | v1 + v2 cũ |
| --- | --- | --- | --- |
| (a) insufficient + high `[55, 65]` | giữ `insufficient data`, không `_refresh`, không notify | đạt | không đạt (sang ALARM) |
| (b) insufficient + high `[65, 70]` | ALARM (một `_refresh` tới `alarm`) | đạt | đạt |
| (c) insufficient + low `[30, 30, 20]` | giữ `insufficient data`, không notify | đạt | không đạt (sang ALARM) |
| (d) insufficient + low `[20, 22, 18]` | ALARM | đạt | đạt |
| (e) insufficient + high `[30, 35]` | OK | đạt | đạt |
| (f) OK + cửa sổ lẫn lộn (high và low) | giữ OK, không `_refresh` | đạt | đạt |
| (g) ALARM + cửa sổ lẫn lộn (high và low) | giữ ALARM, không `_refresh` | đạt | đạt |
| (h) aggregation không `rate:`, từ insufficient/OK/ALARM, 4 cửa sổ, 2 mốc giờ | state, lời gọi `_refresh` và notify trùng `gnocchi.py` upstream; nhánh trending upstream vẫn còn | đạt | đạt |

Tổng: v1 + v2.1 đạt 19/19 (11 ca cũ + 8 ca mới); v1 + v2 cũ 17/19 (hỏng (a), (c)); chỉ v1 9/19.

Ca 12: v1 làm `TestGnocchiAggregationResourcesThresholdEvaluate.test_simple_alarm_trip` đổi kết quả (test khẳng định truy vấn cũ). v2/v2.1 làm cả 5 test của lớp này (`test_simple_insufficient`, `test_simple_alarm_trip`, `test_simple_alarm_clear`, `test_equivocal_from_known_state_ok`, `test_retry_transient_api_failure`) đổi kết quả **có chủ đích**: dữ liệu mẫu của upstream gán cùng một timestamp dạng epoch cho mọi điểm và chỉ chuẩn bị một lần `fetch`, nên gate từ chối; 20 test của hai evaluator còn lại không đổi. Mức bảo đảm: Gnocchi giả viết theo đọc mã 4.7.1, **không phải Gnocchi thật**.

### Tiêu chí PASS để TV2 đối chiếu độc lập

1. sha256 của file patch v2.1 khớp `ea3d1cee…` ở trên; `git apply --check` trên cây A (đang có v1) đạt.
2. Sau khi áp: `git -C /opt/stack/aodh diff --stat` đúng 1 file `aodh/evaluator/gnocchi.py`; sha256 file bằng `3d2bed82…`; evaluator `active`, không traceback sau 5 phút (`infra/devstack/patches/verify-gate-v2-ro.sh`, chỉ đọc).
3. 19 ca của `test_gate_v2.py` xanh (11 ca `evaluate_rule` + 8 ca hồi phục ở tầng `evaluate()`), và bộ test upstream đúng 20/25 với đúng 5 test nêu ở ca 12. Cách tự chạy, ngoài thư mục clone: clone Aodh, `git checkout e07aeb6d118b4b9099947028e6e809a6bdd8fe22`, `git apply` v1 rồi v2.1; `git show e07aeb6d:aodh/evaluator/gnocchi.py > /tmp/up_gnocchi.py`; venv có `requirements.txt` + `test-requirements.txt` của Aodh (bộ test upstream còn cần metadata gói `aodh`, ví dụ một thư mục `aodh-0.0.0.dist-info` tối thiểu trên `sys.path`); `python -I infra/devstack/patches/tests/test_gate_v2.py <cây aodh đã áp v1+v2.1> /tmp/up_gnocchi.py`. Đối chứng: trên cây chỉ áp v2 cũ, ca (a) và (c) phải hỏng.
4. Trên cụm, **chỉ đánh giá** (cả ba danh sách actions rỗng, `repeat_actions=false`): tải nền 30–45% để low ở `ok`; scale tay 2→3 rồi 3→2. Journal có `campus-gate reject` (dự kiến `gnocchi_400`) đúng ở các bucket VM tham gia/rời; ngoài các bucket đó số reject ≈ 0; sau mỗi lần reject, alarm chỉ rời `insufficient data` khi có cửa sổ quyết định (journal có thể có `campus-gate hold=equivocal` ở giữa); alarm history không có chuyển ALARM sai (đặc biệt low) trong cả hai chiều; ghi lại thời gian mỗi alarm nằm ở `insufficient data` sau khi cohort ổn định (dự kiến ≥ N + 2 phút, dài hơn nếu CPU dao động quanh ngưỡng).
5. Có lượt kiểm Gnocchi 4.7.1 thật cho `needed_overlap=100` (ít nhất một lần 400 khi VM tham gia, và 200 khi cohort ổn định), xác nhận mục "Rủi ro còn lại" 1.

Chỉ khi 1–5 đạt, có evidence và TV2 xác nhận thì gate dữ liệu (mục 2) mới được coi là đạt; quyết định bật action vẫn theo `AGENTS.md` mục 6.

### Cách áp và lùi (TV1, đổi trạng thái dùng chung: chỉ sau khi người dùng và TV2 cho phép)

```
sha256sum /tmp/aodh-adr12-gate-v2.patch                 # ea3d1ceed6cd054a2fad3b5f7df10f712d56ba974668dd1293cccca97bd41bc2 (v2.1)
sha256sum /opt/stack/aodh/aodh/evaluator/gnocchi.py      # 8bc8a115... (dang co v1)
sudo -u stack git -C /opt/stack/aodh apply --check /tmp/aodh-adr12-gate-v2.patch
sudo -u stack git -C /opt/stack/aodh apply /tmp/aodh-adr12-gate-v2.patch
sudo systemctl restart devstack@aodh-evaluator
bash verify-gate-v2-ro.sh 5                             # 1 file; sha 3d2bed82...; active; 0 Traceback
```
Lùi về đúng v1 (dưới 1 phút):
```
sudo -u stack git -C /opt/stack/aodh apply -R /tmp/aodh-adr12-gate-v2.patch
sudo systemctl restart devstack@aodh-evaluator
bash verify-gate-v2-ro.sh 5                             # sha 8bc8a115... (upstream + v1)
```
Muốn về upstream sạch thì lùi tiếp v1 theo mục "Cách áp, kiểm và lùi".

### Rủi ro còn lại và điều chưa kiểm

1. **Gnocchi bug [1479429](https://bugs.launchpad.net/gnocchi/+bug/1479429)** (lý do upstream đặt `needed_overlap=0`): theo mã 4.7.1, thiếu điểm cho 400 cả truy vấn. Gate coi đó là từ chối (an toàn: không action) nhưng có thể **kẹt không scale** nếu một VM trong cohort thiếu điểm kéo dài. **Chưa kiểm trên Gnocchi 4.7.1 thật.**
2. **VM đã xóa nhưng chưa có `ended_at`** vẫn nằm trong cohort → 400 liên tục → alarm giữ `insufficient data` (mất liveness) tới khi Ceilometer/Gnocchi ghi `ended_at` (TV2 cũng nêu trong review PR #81). Độ trễ ghi `ended_at` trên cụm **chưa đo**.
3. **VM chưa có metric `cpu`** (hoặc chưa có resource trong Gnocchi) không vào cohort nên không bị phát hiện; trung bình chỉ gồm VM đã có metric (TV2 cũng nêu). Chưa đo khoảng thời gian này trên cụm.
7. **v2.1 kéo dài `insufficient data`:** sau mỗi lần reject, alarm chỉ rời `insufficient data` khi có cửa sổ quyết định; CPU dao động quanh ngưỡng có thể giữ alarm ở `insufficient data` nhiều phút và làm trễ scale-out (không gây action sai). Độ dài thực tế trên cụm **chưa đo**.
4. Cửa sổ của alarm `rate:*` tự tính từ giờ đánh giá; `additional_ingestion_lag` trong `aodh.conf` không còn tác dụng với hai alarm này (giá trị trên A chưa đọc). Phụ thuộc đồng hồ host A đúng (NTP), chưa kiểm.
5. Rate tồn tại ở bucket đầu sau khi VM có điểm thứ hai (policy `ceilometer-high-rate` lưu sẵn `rate:mean`, `carbonara.py:217` dùng `numpy.diff`, nên reset counter ra số âm): suy từ mã, chưa đối chiếu dữ liệu reset thật.
6. `gnocchiclient` trên A có `exceptions.BadRequest` và trả timestamp ISO có múi giờ: kiểm với gnocchiclient 7.2.0 trên laptop; phiên bản trên A **chưa kiểm**.

## Gate v2.2 (21/11/2026): sửa lỗi đọc timestamp, lộ ra khi bật đánh giá trên cụm thật

Trạng thái: **đề xuất, CHƯA áp trên A.** Mới kiểm offline (22 ca, mục dưới); chưa có bằng chứng v2.2 chạy trên cụm. A đang giữ v2.1 (áp khoảng 08:27Z 21/11) và v2.1 **không dùng được**: gate từ chối mọi cửa sổ. Hai alarm đang tắt (`enabled=false`), ba danh sách actions rỗng, nên không có scale nào xảy ra.

### Sự cố trên cụm (21/11/2026, UTC)

- 08:44:53Z TV2 bật `evaluation_enabled=true` (Heat `UPDATE_COMPLETE`), `actions_enabled=false`, ba danh sách actions rỗng, `repeat_actions=false`. Chu kỳ đánh giá đầu (08:44:59Z) đưa cả hai alarm sang `insufficient data` (trước đó `cpu_high` = ok, `cpu_low` = alarm, đóng băng từ lúc tắt).
- Journal `devstack@aodh-evaluator` 08:44:59Z–08:48:59Z (5 chu kỳ, mỗi chu kỳ hai alarm): `campus-gate reject=bad_timestamp` ở **mọi** chu kỳ, cả `gt n=2` (high) và `lt n=3` (low). 0 Traceback, 0 `hold=equivocal`, không có `gnocchi_400`. Nghĩa là hai truy vấn Gnocchi 4.7.1 thật (`mean` và `min`, `needed_overlap=100`, cohort ổn định) trả 200, và điểm đầu của mỗi kết quả đúng là bucket đầu của cửa sổ gate tính (08:42:00 cho high, 08:41:00 cho low ở chu kỳ 08:44:59Z). Dữ liệu thô: `docs/_scripts/session-20261121/results/aodh-eval-20261121-0844Z.log` (ngoài repo).
- Giá trị timestamp bị từ chối ghi trong journal có dạng `2026-11-21 08:42:00+00:00` (dấu cách, không có chữ T): đó là `str(datetime)`. TV2 xác nhận client trả `datetime` có múi giờ. Gate v2.1 gọi `timeutils.parse_isotime(ts)`, hàm này chỉ nhận chuỗi, nên ném `ValueError` và gate ghi `bad_timestamp`.
- 08:53:20Z TV2 tắt evaluation; hậu kiểm hai alarm tắt, actions rỗng. Kiểm VM trước khi tắt evaluation (trước 08:53Z): ba VM `ACTIVE` (`campus-db`, app A, một app của nhóm ASG), không có VM lạ. Trạng thái alarm chưa đọc lại sau khi tắt; lần đọc gần nhất (TV2, 08:46:02Z) cả hai là `insufficient data`.
- **Nguyên nhân gốc:** trong `gnocchiclient` (7.2.0, cài thử offline), `aggregates.fetch` luôn gọi `_convert_dates` (`gnocchiclient/v1/aggregates.py`), đổi mọi timestamp trong kết quả thành `datetime` có múi giờ UTC bằng `iso8601.parse_date`; kết quả có dạng `{'measures': {'aggregated': [(datetime, granularity, value), ...]}}`. Vậy `datetime` là hành vi bình thường của client, không riêng A. Nhận định ở "rủi ro còn lại" số 6 của v2.1 (client trả chuỗi ISO) **sai**, và 19 ca của v2.1 không bắt được vì Gnocchi giả chỉ trả chuỗi ISO. Dạng giá trị trong journal (`2026-11-21 08:42:00+00:00`) khớp đúng `str()` của `datetime` UTC do hàm này tạo ra. Phiên bản `gnocchiclient` trên A chưa đọc.

### Thay đổi (v2.2)

- Đoạn đọc timestamp trong `_campus_gate`: nhận `datetime` (có hoặc không múi giờ; không múi giờ coi là UTC, giống `parse_isotime` với chuỗi không múi giờ) hoặc chuỗi ISO, rồi chuẩn hóa về UTC bằng `timeutils.normalize_time`. Kiểu khác (None, số, `date`, bytes, chuỗi sai định dạng) vẫn `reject=bad_timestamp`.
- Dòng log `bad_timestamp` ghi `repr(ts)` thay `str(ts)`, để thấy cả kiểu (`datetime.datetime(...)` hay chuỗi có dấu nháy).
- **Không đổi:** ngưỡng, granularity, `evaluation_periods`, cooldown, template Heat, `threshold.py`, và mọi cơ chế khác của v2.1 (bucket đã đóng, `needed_overlap=100`, min âm, hold khi hồi phục từ `insufficient data`).

### Checksum (tính offline trên cây upstream `e07aeb6d` + v1 sha256 `9afebdfc…`)

| Tệp (`infra/devstack/patches/`) | Dùng cho | sha256 | Thay đổi |
| --- | --- | --- | --- |
| `aodh-adr12-gate-v2.patch` (nội dung v2.2) | máy chỉ có v1 hoặc cây sạch | `ea9aa702fc960b2370a7e2b502281b1e7714ed81786d1ca5e2e4915c22a1ac04` | 1 file, 96 dòng thêm so với v1 (v2.1 là 92) |
| `aodh-adr12-gate-v2.1-to-v2.2.patch` (delta) | **A hiện tại** (đang v2.1) | `46a0f8defe45faad8ec06f3766611252327d2e8ad60e20bbeb0ed6d3d199a962` | 6 dòng thêm, 2 dòng xóa |

- sha256 của `aodh/evaluator/gnocchi.py`: upstream `d63b84f4…`; + v1 `8bc8a115…`; + v1 + v2.1 `3d2bed8247161e54cfdaad29efcc6f5e040cc6011c251e32c000dda2798a56fb` (đang trên A, bị thay); + v1 + v2.2 `529d40bbec3052efce221f559f201634eb161df9d5aff1f982aa034d75533086`. Hai đường (v1 + patch đầy đủ; v1 + v2.1 + delta) cho cùng `529d40bb…`.
- `verify-gate-v2-ro.sh` nhận ra v2.2 và báo riêng khi file còn là v2.1.

### Kết quả kiểm offline (21/11/2026, laptop Windows, không chạm cụm)

Môi trường: Aodh `e07aeb6d118b4b9099947028e6e809a6bdd8fe22` (clone mirror GitHub `openstack/aodh`, `git rev-parse HEAD` khớp), Python 3.13.13, venv mới từ `requirements.txt` và `test-requirements.txt` của Aodh (`gnocchiclient` 7.2.0, `oslo.utils` 10.3.0, `iso8601` 2.1.0); A chạy Python 3.12 với bản thư viện khác, **chưa kiểm** trên đúng môi trường của A. Lưu ý khi clone trên Windows: `core.autocrlf=true` đổi file làm việc sang CRLF và làm sha256 `gnocchi.py` lệch `d63b84f4…`; đặt `core.autocrlf=false` trước khi checkout (hoặc so sha bằng `git show e07aeb6d:aodh/evaluator/gnocchi.py | sha256sum`).

- Cây upstream sạch → v1 → patch đầy đủ v2.2: `git apply --check` rồi áp đạt, file `529d40bb…`; áp ngược về đúng `8bc8a115…`. Trên cây v1 + v2.1: delta `--check` và áp đạt → `529d40bb…`; áp ngược → `3d2bed82…`.
- `test_gate_v2.py`: Gnocchi giả nay trả được 6 kiểu timestamp (chuỗi `+00:00`, chuỗi `Z`, `datetime` UTC, `datetime` múi giờ +07:00, `datetime` không múi giờ, và kiểu `client`: chuỗi ISO đi qua chính hàm `_convert_dates` của `gnocchiclient` đã cài, tức đầu ra như client thật) và chèn được timestamp sai ở vị trí bất kỳ. Thêm 3 ca:

| Ca | Mong đợi | v1 + v2.1 | v1 + v2.2 |
| --- | --- | --- | --- |
| 13. Cùng bucket, 6 kiểu timestamp × 5 tình huống (high alarm, low alarm, low ok, thiếu bucket giữa, counter reset âm) | state, lý do reject và danh sách điểm trả về giống hệt nhau; client trả +07:00 (16:58, 16:59) vẫn là bucket 09:58, 09:59 UTC | không đạt (`datetime` → `bad_timestamp`, tái hiện lỗi cụm) | đạt |
| 14. Timestamp sai (chuỗi rác, rỗng, None, số epoch int và float, ngày giờ không hợp lệ, `date`, bytes) ở đầu, giữa, cuối cửa sổ; high n=2 và low n=3; cả hai kiểu chuỗi và `datetime` (80 tổ hợp) | `reject=bad_timestamp` | đạt | đạt |
| 15. Tầng `evaluate()` với 6 kiểu timestamp: từ `insufficient data` cửa sổ lẫn lộn thì giữ, cửa sổ quyết định thì ALARM; `low` đang `alarm` gặp ba bucket 30–40% thì về `ok` | như ca (a)–(d); low alarm → ok có `_refresh` | không đạt | đạt |

Tổng: v1 + v2.2 đạt **22/22** (19 ca cũ + 3 ca mới); v1 + v2.1 đạt 19 ca cũ, hỏng ca 13 và 15.

Ca 12 (25 test upstream `aodh/tests/unit/evaluator/test_gnocchi.py`): v1 + v2.1 và v1 + v2.2 đều 20/25, cùng đúng 5 test đã nêu ở ca 12 của v2.1 (`test_simple_insufficient`, `test_simple_alarm_trip`, `test_simple_alarm_clear`, `test_equivocal_from_known_state_ok`, `test_retry_transient_api_failure`). Mức bảo đảm vẫn là Gnocchi giả (nay có `datetime`) viết theo đọc mã 4.7.1, **không phải client và Gnocchi thật trên A**.

### Tiêu chí PASS để TV2 đối chiếu độc lập

1. sha256 hai tệp patch khớp bảng trên; `git apply --check` đạt: patch đầy đủ trên cây v1 sạch, delta trên cây A (đang v2.1).
2. Sau khi áp trên A: `git -C /opt/stack/aodh diff --stat` đúng 1 file; sha256 `gnocchi.py` = `529d40bb…`; evaluator `active`, 0 Traceback sau 5 phút (`verify-gate-v2-ro.sh`, chỉ đọc).
3. 22 ca `test_gate_v2.py` xanh và bộ test upstream đúng 20/25 với đúng 5 test ở ca 12. Cách chạy như mục v2.1 (cây Aodh đã áp v1 rồi `aodh-adr12-gate-v2.patch` đầy đủ; `python -I test_gate_v2.py <cây aodh> <up_gnocchi.py>`). Đối chứng: trên cây v1 + v2.1 ca 13 và 15 phải hỏng, ca 14 vẫn đạt.
4. Trên cụm, **chỉ đánh giá** (ba danh sách actions rỗng, `repeat_actions=false`): TV2 bật `evaluation_enabled=true` rồi mới đo. Journal **không còn** `reject=bad_timestamp`; nếu có reject thì chỉ `gnocchi_400` hoặc `missing_bucket` ở các bucket VM tham gia hoặc rời cohort; alarm rời `insufficient data` khi đủ N bucket (high 2, low 3) sau khi cohort ổn định. Phần còn lại của tiêu chí 4 ở mục v2.1 giữ nguyên (tải nền 30–45% để low về `ok`, scale tay 2→3 rồi 3→2, alarm history không có ALARM sai).
5. Kiểm Gnocchi 4.7.1 thật cho `needed_overlap=100`: nửa "200 khi cohort ổn định" đã thấy ở sự cố 21/11 (hai truy vấn trả 200); còn thiếu "400 khi VM tham gia".

### Cách áp và lùi (TV1; đổi trạng thái dùng chung, chỉ sau khi TV2 đối chiếu và người dùng cho phép từng lệnh)

Trên A (đang v2.1; scp hai tệp patch lên `/tmp/`):

```
sha256sum /tmp/aodh-adr12-gate-v2.1-to-v2.2.patch      # 46a0f8defe45faad8ec06f3766611252327d2e8ad60e20bbeb0ed6d3d199a962
sha256sum /opt/stack/aodh/aodh/evaluator/gnocchi.py     # 3d2bed82... (dang co v2.1); khac thi DUNG
sudo -u stack git -C /opt/stack/aodh apply --check /tmp/aodh-adr12-gate-v2.1-to-v2.2.patch
sudo -u stack git -C /opt/stack/aodh apply /tmp/aodh-adr12-gate-v2.1-to-v2.2.patch
sudo systemctl restart devstack@aodh-evaluator
bash verify-gate-v2-ro.sh 5                             # 1 file; sha 529d40bb...; active; 0 Traceback
```

Chạy từng lệnh, dừng ngay nếu một lệnh báo lỗi (`apply` khi file đã là v2.2 sẽ báo lỗi, không phải hỏng). Lùi (dưới 1 phút mỗi bước):
- Về v2.1: `apply -R` delta, restart evaluator, `verify-gate-v2-ro.sh 5` (sha `3d2bed82…`).
- Về v1: `apply -R` patch đầy đủ `/tmp/aodh-adr12-gate-v2.patch` trên A đang v2.2, restart, `verify-gate-v2-ro.sh 5` (sha `8bc8a115…`).

Sau khi áp, `evaluation_enabled` vẫn `false`; bật lại là bước riêng của TV2 (stack alarm `campus-app-cpu-alarms`, `actions_enabled=false`, `stack preview` trước), kèm kế hoạch tải nền và giờ UTC bắt đầu.

### Rủi ro còn lại và điều chưa kiểm của v2.2

1. Các nhánh phía sau vòng đọc timestamp (`stale`, `missing_bucket`, `nonfinite`, `negative`, và kiểu của granularity và giá trị trong kết quả thật) **chưa từng chạy trên dữ liệu Gnocchi thật**: v2.1 dừng ngay ở timestamp. v2.2 có thể lộ một lỗi kiểu khác cùng loại; kiểm thử Gnocchi giả không thay được chạy thật.
2. Phiên bản `gnocchiclient` trên A chưa đọc (đọc nhanh: `ls /opt/stack/data/venv/lib/python3.12/site-packages | grep -i gnocchiclient`). Hành vi trả `datetime` có ở 7.2.0 thử offline và khớp journal trên A; nếu A dùng bản khác thì kiểu timestamp có thể khác, nhưng v2.2 nhận cả chuỗi lẫn `datetime`. Kiểu `client` của ca 13 chỉ phủ phần chuyển đổi timestamp; kiểu của granularity và giá trị trong kết quả thật vẫn là giả định (xem mục 1).
3. Các rủi ro còn lại 1–7 của mục v2.1 (VM đã xóa chưa có `ended_at`, `insufficient data` kéo dài, NTP, và các điều khác) vẫn đúng.
4. Hai alarm đang ở `insufficient data` sau sự cố; khi bật lại, `cpu_low` cần đủ 3 bucket quyết định mới ra khỏi trạng thái này.

## Nếu không duyệt kịp, hoặc không đạt

Nếu chưa được duyệt thì không áp bản vá. Nếu được phép thử nhưng kiểm phép tính hoặc gate dữ liệu chưa đạt thì giữ action tắt; lùi bản vá nếu gây lỗi dịch vụ, sai kết quả hoặc vượt phạm vi đã duyệt. Báo cáo FR-INF-11 là **đạt một phần** theo evidence có thật: đã có lượt scale tay 2→3→2 và các giới hạn alarm nêu trên; không nhận autoscaling tự động là PASS. Nhóm (và giảng viên nếu cần) quyết định phạm vi.

## Hệ quả

- Host A khác upstream đúng một file. Chạy lại `stack.sh` (đã cấm khi cụm có tài nguyên) sẽ xóa bản vá; nếu phải chạy thì áp lại trước khi bật action.
- `docs/versions.lock` điền `aodh_sha`, thêm `aodh_patch` và `aodh_patch_sha256`; khi áp bản vá sẽ thêm vào `docs/runbooks/after-start.md` (phần telemetry) kiểm `git -C /opt/stack/aodh diff --stat` (1 file); PR này không đổi runbook để tránh xung đột với PR #46.
- SRS không đổi: NFR-05 và FR-INF-11 giữ nguyên tiêu chí; chỉ đổi cách Aodh tính giá trị đưa vào tiêu chí đó.
- Chủ review của PR: `docs/decisions/` và `docs/versions.lock` (mặc định TV1), `infra/devstack/patches/` (TV1, TV2), `evidence/` (TV4).
- Vấn đề còn mở trước bật action: độ phủ VM (`needed_overlap=0`), bucket chưa đóng/không liên tiếp/cũ, counter reset và VM rời cohort; theo gate dữ liệu ở phần nghiệm thu. Bản vá sửa phép tính không tự giải quyết các vấn đề này.
