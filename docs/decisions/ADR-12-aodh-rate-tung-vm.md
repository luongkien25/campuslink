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

## Gate v2 (20/11/2026)

Trạng thái: **đề xuất, CHƯA áp trên A, chưa có review của TV2.** Mới kiểm offline (mục "Kết quả kiểm offline"); chưa có bằng chứng evaluator chạy gate trên cụm. Vẫn là Heat + Aodh + Gnocchi; chỉ sửa lớp `GnocchiAggregationResourcesThresholdEvaluator` trong `aodh/evaluator/gnocchi.py`. **Không đổi** ngưỡng, granularity, `evaluation_periods`, cooldown, template Heat hay `threshold.py`.

- Bản vá: `infra/devstack/patches/aodh-adr12-gate-v2.patch`, sha256 `efbde2e5fef311741f4609ae00bac30388d213c96ebf1005459142c5399f67d9`; bản vá **tăng dần**, áp **sau** `aodh-adr12-rate-per-vm.patch` (v1); 1 file, 76 dòng thêm, 0 dòng xóa.
- sha256 của `aodh/evaluator/gnocchi.py` (tính offline): upstream `e07aeb6d` = `d63b84f4c61cd8f05a4f76488bc179720edf461592e94bb0c825cba91dd01ca0`; upstream + v1 = `8bc8a1153ce36c4732236834e173bb86cdf52d0fbc43170ce47eb331ad1dbb38`; upstream + v1 + v2 = `443751e5126a08e0abf237238f2148c8d3f088bc6fddecd0fdeb3e4fc76a77e7`.

### Cơ chế

Chỉ áp cho aggregation có tiền tố `rate:` (alarm CPU high/low). Aggregation khác đi đúng đường mã của v1 (bằng upstream). `_statistics` gọi `_campus_gate`; mọi lần từ chối đều ghi `LOG.info("campus-gate reject=<lý do> op=<gt|lt> n=<N> ...")` rồi ném `InsufficientDataError("campus-gate reject=<lý do>")`, nên alarm sang `insufficient data` (state_reason chứa lý do) và không phát `alarm_actions`; `insufficient_data_actions` của hai alarm rỗng (`infra/heat/alarms.yaml`).

1. **Chỉ bucket đã đóng:** bucket `ts` hợp lệ khi `ts + granularity + 45 s <= now` (`now` = giờ đánh giá của evaluator; 45 s vì probe 15/11 thấy điểm Gnocchi tới giây :26 của phút sau). Cửa sổ truy vấn là đúng N bucket đã đóng gần nhất: `start` = bucket đầu, `stop` = bucket cuối + 60 s (Gnocchi cắt `[start, stop)`, `gnocchi/carbonara.py:253-259` ở 4.7.1), nên bucket đang ghi không vào truy vấn.
2. **Đủ VM ở mọi bucket:** truy vấn `['aggregate', 'mean', ['metric', 'cpu', 'rate:mean']]` với `needed_overlap=100`. Theo mã Gnocchi 4.7.1 (`gnocchi/rest/aggregates/processor.py:200-220`, `api.py:169-178`), khi có `start/stop` và một VM thiếu điểm ở bất kỳ timestamp nào trong cửa sổ, Gnocchi **trả 400 cho cả truy vấn** (không loại riêng bucket đó). Gate bắt `BadRequest` → `reject=gnocchi_400`. Không thay điểm thiếu bằng 0, không bỏ VM.
3. **Đủ N bucket liền nhau và mới:** bucket mới nhất phải đúng là bucket đóng gần nhất (`reject=stale`), đủ cả N timestamp cách nhau 60 s (`reject=missing_bucket`, ví dụ mọi VM cùng thiếu một bucket giữa).
4. **Counter reset / giá trị không hữu hạn:** truy vấn thứ hai `['aggregate', 'min', ['metric', 'cpu', 'rate:mean']]` cùng cửa sổ; min < 0 ở bất kỳ bucket nào → `reject=negative` (phép mean che giá trị âm của một VM); NaN/inf ở mean hoặc min → `reject=nonfinite`. Timestamp không đọc được → `reject=bad_timestamp`.
5. Đạt cả bốn mục thì trả đúng N điểm cho `_sanitize`/`evaluate_rule` như cũ; so sánh ngưỡng và chuyển state không đổi.

### Định nghĩa

- **Cohort:** tập resource `instance` mà Gnocchi trả cho `query` của alarm (`server_group`, `project_id`, `ended_at=null`, `deleted_at=null`) **tại thời điểm đánh giá**, và có metric `cpu` (Gnocchi tự bỏ resource không có metric khớp: `api.py:681-697`).
- **Độ mới:** bucket mới nhất phải là bucket đã đóng gần nhất theo mục 1 (tuổi bucket từ 105 s tới dưới 165 s so với giờ đánh giá).
- **Quay lại đánh giá:** tự động ở chu kỳ đánh giá kế tiếp khi lại có đủ N bucket hợp lệ; không cần người thao tác. Hệ quả: high chỉ thấy một bucket sau khi bucket đó đóng 45 s (chậm hơn v1 tối đa khoảng 45 s cộng một chu kỳ đánh giá; cần tính vào NFR-06).

### Kết quả kiểm offline (20/11/2026, laptop Windows, không chạm cụm)

Mã Aodh `e07aeb6d118b4b9099947028e6e809a6bdd8fe22` clone từ opendev, `git rev-parse HEAD` khớp; v1 kiểm sha256 `9afebdfc…` khớp, `git apply --check` rồi áp. v2: `git apply --check` trên cây upstream + v1: đạt; sau khi áp `git apply -R --check`: đạt; áp lần lượt v1 rồi v2 lên cây upstream sạch cho file trùng byte với cây phát triển. Python 3.13 trên Windows, dependency bản mới nhất từ PyPI (không phải upper-constraints 2026.1; A chạy Python 3.12): **chưa kiểm** trên đúng môi trường của A.

`infra/devstack/patches/tests/test_gate_v2.py` chạy mã evaluator thật (`evaluate_rule` của Aodh) với Gnocchi **giả** mô phỏng `aggregated()` của Gnocchi 4.7.1 (needed_overlap, cắt `[start, stop)`, lọc `ended_at`):

| Ca | Kết quả mong đợi | v1 + v2 | chỉ v1 (đối chứng) |
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
| 12. Test upstream `aodh/tests/unit/evaluator/test_gnocchi.py` (25 test) | | upstream 25/25; v1 24/25; v1 + v2 20/25 | |

Ca 12: v1 làm `TestGnocchiAggregationResourcesThresholdEvaluate.test_simple_alarm_trip` đổi kết quả (test khẳng định truy vấn cũ). v2 làm cả 5 test của lớp này đổi kết quả **có chủ đích**: dữ liệu mẫu của upstream gán cùng một timestamp dạng epoch cho mọi điểm và chỉ chuẩn bị một lần `fetch`, nên gate từ chối; 20 test của hai evaluator còn lại không đổi. Mức bảo đảm: Gnocchi giả viết theo đọc mã 4.7.1, **không phải Gnocchi thật**.

### Tiêu chí PASS để TV2 đối chiếu độc lập

1. sha256 của file patch v2 khớp giá trị ở trên; `git apply --check` trên cây A (đang có v1) đạt.
2. Sau khi áp: `git -C /opt/stack/aodh diff --stat` đúng 1 file `aodh/evaluator/gnocchi.py`; sha256 file bằng `443751e5…`; evaluator `active`, không traceback sau 5 phút (`infra/devstack/patches/verify-gate-v2-ro.sh`, chỉ đọc).
3. 12 ca xanh khi TV2 tự chạy `python -I infra/devstack/patches/tests/test_gate_v2.py <cây aodh đã áp v1+v2> <gnocchi.py upstream>`.
4. Trên cụm, **chỉ đánh giá** (cả ba danh sách actions rỗng, `repeat_actions=false`): tải nền 30–45% để low ở `ok`; scale tay 2→3 rồi 3→2. Journal có `campus-gate reject` (dự kiến `gnocchi_400`) đúng ở các bucket VM tham gia/rời; ngoài các bucket đó số reject ≈ 0; alarm history không có chuyển ALARM sai (đặc biệt low) trong cả hai chiều; hai alarm không kẹt `insufficient data` quá N + 2 phút sau khi cohort ổn định.
5. Có lượt kiểm Gnocchi 4.7.1 thật cho `needed_overlap=100` (ít nhất một lần 400 khi VM tham gia, và 200 khi cohort ổn định), xác nhận mục "Rủi ro còn lại" 1.

Chỉ khi 1–5 đạt, có evidence và TV2 xác nhận thì gate dữ liệu (mục 2) mới được coi là đạt; quyết định bật action vẫn theo `AGENTS.md` mục 6.

### Cách áp và lùi (TV1, đổi trạng thái dùng chung: chỉ sau khi người dùng và TV2 cho phép)

```
sha256sum /tmp/aodh-adr12-gate-v2.patch                 # efbde2e5fef311741f4609ae00bac30388d213c96ebf1005459142c5399f67d9
sha256sum /opt/stack/aodh/aodh/evaluator/gnocchi.py      # 8bc8a115... (dang co v1)
sudo -u stack git -C /opt/stack/aodh apply --check /tmp/aodh-adr12-gate-v2.patch
sudo -u stack git -C /opt/stack/aodh apply /tmp/aodh-adr12-gate-v2.patch
sudo systemctl restart devstack@aodh-evaluator
bash verify-gate-v2-ro.sh 5                             # 1 file; sha 443751e5...; active; 0 Traceback
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
2. **VM đã xóa nhưng chưa có `ended_at`** vẫn nằm trong cohort → 400 liên tục → mất liveness tới khi Ceilometer/Gnocchi ghi `ended_at`. Độ trễ ghi `ended_at` trên cụm **chưa đo**.
3. **VM chưa có metric `cpu`** (hoặc chưa có resource trong Gnocchi) không vào cohort nên không bị phát hiện; trung bình chỉ gồm VM đã có metric. Chưa đo khoảng thời gian này trên cụm.
4. Cửa sổ của alarm `rate:*` tự tính từ giờ đánh giá; `additional_ingestion_lag` trong `aodh.conf` không còn tác dụng với hai alarm này (giá trị trên A chưa đọc). Phụ thuộc đồng hồ host A đúng (NTP), chưa kiểm.
5. Rate tồn tại ở bucket đầu sau khi VM có điểm thứ hai (policy `ceilometer-high-rate` lưu sẵn `rate:mean`, `carbonara.py:217` dùng `numpy.diff`, nên reset counter ra số âm): suy từ mã, chưa đối chiếu dữ liệu reset thật.
6. `gnocchiclient` trên A có `exceptions.BadRequest` và trả timestamp ISO có múi giờ: kiểm với gnocchiclient 7.2.0 trên laptop; phiên bản trên A **chưa kiểm**.

## Nếu không duyệt kịp, hoặc không đạt

Nếu chưa được duyệt thì không áp bản vá. Nếu được phép thử nhưng kiểm phép tính hoặc gate dữ liệu chưa đạt thì giữ action tắt; lùi bản vá nếu gây lỗi dịch vụ, sai kết quả hoặc vượt phạm vi đã duyệt. Báo cáo FR-INF-11 là **đạt một phần** theo evidence có thật: đã có lượt scale tay 2→3→2 và các giới hạn alarm nêu trên; không nhận autoscaling tự động là PASS. Nhóm (và giảng viên nếu cần) quyết định phạm vi.

## Hệ quả

- Host A khác upstream đúng một file. Chạy lại `stack.sh` (đã cấm khi cụm có tài nguyên) sẽ xóa bản vá; nếu phải chạy thì áp lại trước khi bật action.
- `docs/versions.lock` điền `aodh_sha`, thêm `aodh_patch` và `aodh_patch_sha256`; khi áp bản vá sẽ thêm vào `docs/runbooks/after-start.md` (phần telemetry) kiểm `git -C /opt/stack/aodh diff --stat` (1 file); PR này không đổi runbook để tránh xung đột với PR #46.
- SRS không đổi: NFR-05 và FR-INF-11 giữ nguyên tiêu chí; chỉ đổi cách Aodh tính giá trị đưa vào tiêu chí đó.
- Chủ review của PR: `docs/decisions/` và `docs/versions.lock` (mặc định TV1), `infra/devstack/patches/` (TV1, TV2), `evidence/` (TV4).
- Vấn đề còn mở trước bật action: độ phủ VM (`needed_overlap=0`), bucket chưa đóng/không liên tiếp/cũ, counter reset và VM rời cohort; theo gate dữ liệu ở phần nghiệm thu. Bản vá sửa phép tính không tự giải quyết các vấn đề này.
