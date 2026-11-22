# Chương 6, Chương 8 (Chi phí) và Phụ lục A: Kiểm thử, Hiệu năng, Độ tin cậy và Chi phí (TV4)

> **Chủ trì:** TV4 – Cao Song Toàn (`@toancst`) · **Cập nhật:** 22/11/2026 (bổ sung kết quả tự scale `Aodh → Heat` 2 chiều tối 21/11 tại #77, PR #91, phân tích `14/11 vs 20/11` tại PR #89 và đồng bộ với khung báo cáo cuối ở #74, PR #92).
> **Tham chiếu:** #80 (`T4-5`), #74, `docs/SRS.md` (mục 5, 6.2, 6.3), `docs/acceptance.md`, `cost.csv` (`evidence/cost.csv`).
> Mọi số liệu đều trỏ tới bằng chứng trong `evidence/`. Các tệp thuộc PR đang chờ merge được ghi kèm số PR.

---

## 1. Phương pháp kiểm thử và bộ công cụ tái lập (`NFR-03`, `NFR-14`)

### 1.1. Kiến trúc bộ kiểm thử
Bộ kiểm thử của CampusLink được chia thành 3 lớp độc lập để vừa kiểm chứng hợp đồng API từ phía người dùng Internet, vừa tách biệt được độ trễ mạng với độ trễ xử lý nội bộ trên cụm OpenStack:

1. **Unit & Deliverable Tests (`tests/test_tv4_deliverables.py`):** Chạy tự động bằng `python3 -m unittest discover -s tests -v` (không cần mạng hay cụm cloud), kiểm chứng:
   - Đồng bộ tuyệt đối giữa `cost.csv` và `evidence/cost.csv`, kiểm schema và chuỗi 7 mốc đối chiếu AWS Credit (`131,38` → `93,96 USD`).
   - Toàn bộ liên kết Markdown trong `docs/acceptance.md` đều trỏ tới tệp tồn tại thực tế trong repo và đủ 8 hạng mục bắt buộc.
   - Các script trong `tests/` không truyền `X-Api-Key` qua `argv` (`NFR-08`); `tests/load/setup-fixture.sh` kiểm tra lại `longUrl` sau khi tạo (`FR-INF-16`); `tests/load/workload.py` dùng `NoRedirectHandler` ghi nhận mã HTTP `302`, `X-Request-Id` và `Location`.
2. **Smoke Tests hợp đồng API (`tests/smoke/contract-smoke.sh`, `app/smoke/h1-smoke.sh`):**
   - Kiểm tra chứng thư TLS Let's Encrypt hợp lệ (không dùng `curl -k`, `NFR-10`), `GET /rest/health` (`200/pass`), tạo short URL, redirect `302`, sửa đích `PATCH` xuyên 2 replica (`NFR-12`), phân trang visit, thống kê tag, phân tách dữ liệu `--author-only` (`FR-APP-08`) và CORS (`FR-APP-10`).
   - Kết quả chạy trên cụm ngày 18/11/2026 đạt **27 PASS, 0 FAIL** (`evidence/G3/20261118-FR-APP-01-12-h1-smoke-cum.txt`, PR #62).
3. **Workload Generator theo hồ sơ `NFR-03` (`tests/load/workload.py`, `tests/load/setup-fixture.sh`):**
   - Sử dụng 5 slug fixture chuẩn `tv4fix1..tv4fix5` đã khóa trong `docs/handoffs/H5-fixture-backup-restore.md` (PR #52).
   - Tỷ lệ request đúng hợp đồng `NFR-03`: **80% `GET /{shortCode}`** (redirect, không follow 302), **15% `GET /rest/v3/short-urls/{slug}/visits`** (đọc thống kê có `X-Api-Key`), **5% `POST /rest/v3/short-urls`** (tạo link mới gắn tag `campus-load`).
   - Ghi log CSV từng request (`phase,timestamp_utc,request_type,slug,http_status,latency_ms,request_id,location`), trong đó mã `599` quy ước cho timeout (10 s) hoặc lỗi kết nối phía máy phát, tách biệt với mã HTTP `5xx` (`500..598`) từ phía server.
   - Song song với CSV phía máy phát, Nginx trên Host A ghi `/var/log/nginx/campus-rt.log` có thêm `$request_time` (`rt`) và `$upstream_response_time` (`urt`) theo `NFR-22` (`evidence/G3/20261114-FR-INF-06-NFR-22-nginx-noi-vip-va-kiem-1-7b.txt`).

---

## 2. Kết quả đo hiệu năng và độ tin cậy (`NFR-01`, `NFR-02`, `NFR-03`, `NFR-22`)

Chi tiết toàn bộ các cửa sổ đo được tổng hợp tại [`evidence/G5/20261121-NFR-01-03-tong-hop.txt`](../../evidence/G5/20261121-NFR-01-03-tong-hop.txt).

### 2.1. Bảng tổng hợp các lượt đo qua Internet và phía server (Nginx `$request_time`)

| Cửa sổ / Lượt đo (UTC) | Mức đặt / Thực đạt | Tổng req / Redirect `302` | `p50` máy phát | `p95` máy phát (`NFR-01`) | `p50` server (Nginx) | `p95` server (Nginx) | `p99` server (Nginx) | HTTP `5xx` | Lỗi client `599` (`NFR-02`) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **W1** (16/11 `14:53–15:13Z`, baseline + scale tay) | 30 / ~28,8 RPS | 36.000 / 28.764 | 847,4 ms | **1.080,7 ms** | 57,0 ms | **238,0 ms** | 604,0 ms | 0 | 47 (**0,131%**) |
| **W2** (17/11 `14:24–14:44Z`, sau vá ADR-12 v1) | 30 / ~24,0 RPS | 36.000 / 28.788 | — | **~1.200,0 ms** | 67,0 ms | **256,0 ms** | 425,0 ms | 0 | **< 0,150%** |
| **W3** (17/11 `14:24–14:28Z`, trước scale-out, 2 app) | 30 / ~24,0 RPS | — / 5.496 | — | — | 72,0 ms | **313,0 ms** | 501,0 ms | 0 | — |
| **W4** (17/11 `14:28–14:36Z`, khi có 3 app VM) | 30 / ~24,0 RPS | — / 12.743 | — | — | 61,0 ms | **189,0 ms** | 334,0 ms | 0 | — |
| **W5** (17/11 `14:36–14:44Z`, sau scale-in, 2 app) | 30 / ~24,0 RPS | — / 10.549 | — | — | 75,0 ms | **288,0 ms** | 459,0 ms | 0 | — |
| **W6** (18/11 `14:25–14:47Z`, đối chứng 30 RPS, 32 luồng) | 30 / 23,7 RPS | 30.600 / 24.444 *(Nginx: 24.447)* | 935,0 ms | **2.674,0 ms\*** | 129,0 ms | **596,0 ms** | 839,0 ms | 0 | 47 (**0,154%**) |
| **W7** (18/11 `14:52–14:57Z`, 10 RPS trước khi dừng A) | 10 / 10,0 RPS | 2.992 / 2.396 *(Nginx: 2.397)* | 933,0 ms | **2.726,0 ms\*** | 50,0 ms | **76,0 ms** | 131,0 ms | 0 | 1 (**0,033%**) |
| **W8** (18/11 `14:57–15:02Z`, 10 RPS khi app A tắt) | 10 / 10,0 RPS | 3.015 / 2.409 *(Nginx: 2.403)* | 926,0 ms | **2.613,0 ms\*** | 57,0 ms | **117,0 ms** | 263,0 ms | 0 | 2 (**0,066%**) |
| **W9** (18/11 `15:02–15:09Z`, 10 RPS hồi phục + sau bật A) | 10 / 10,0 RPS | 4.193 / 3.350 *(Nginx: 3.355)* | 906,0 ms | **2.519,0 ms\*** | 52,0 ms | **74,0 ms** | 126,0 ms | 0 | 4 (**0,095%**) |
| **Toàn lượt Failover 10 RPS** (18/11 `14:52–15:09Z`) | 10 / 10,0 RPS | 10.200 / 8.155 | 918,0 ms | **2.635,0 ms\*** | 53,0 ms | **91,0 ms** | 180,0 ms | 0 | 7 (**0,069%**) |

*\*Ghi chú:* Theo manifest của PR #68 (`evidence/G4/20261118-FR-INF-20-NFR-07-tv1-manifest.txt`), hai lượt đo tối 18/11 có `p95` phía máy phát xấp xỉ nhau (`2.674 ms` ở 23,7 RPS và `2.635 ms` ở 10 RPS); nguyên nhân cụ thể chưa rõ (chưa đo lại RTT tối 18/11) nên hai lượt này không dùng làm số đo chuẩn của `NFR-01`.

### 2.2. Phép đo Ramp Chỉ-Redirect nội bộ từ Host A qua VIP (`20/11/2026`, PR #88)
Để tách hoàn toàn độ trễ mạng Internet và kiểm tra trần thông lượng thực tế của cụm (2 app VM + 1 DB VM), ngày 20/11 TV1 đã chạy `ApacheBench` (`ab -k` keep-alive) gọi `GET http://172.24.4.117:8080/tv4fix1` qua 5 mức concurrency (`c = 8, 16, 24, 32, 64`, mỗi mức 240 s, nghỉ 120 s; `evidence/G4/20261120-FR-INF-11-ramp-redirect-ab-cpu-gnocchi.txt`):

| Mức Concurrency | Request hoàn tất | Lỗi (`ab` / probe) | RPS thực đạt | `p50` (`ab`) | `p95` (`ab`) | `p99` (`ab`) | CPU nhóm app (TB A, B) | CPU `campus-db` (1 vCPU) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `c = 8` | 7.791 | 0 / `0/106` | **32,46 RPS** | 245 ms | **303 ms** | 542 ms | 43,5 – 44,6 % | **96,1 – 96,6 %** |
| `c = 16` | 7.711 | 0 / `0/95` | **32,13 RPS** | 547 ms | **665 ms** | 876 ms | 42,2 – 42,7 % | **97,1 – 97,2 %** |
| `c = 24` | 7.870 | 0 / `0/87` | **32,79 RPS** | 712 ms | **913 ms** | 1.054 ms | 41,7 – 42,5 % | **97,2 – 97,5 %** |
| `c = 32` | 7.814 | 0 / `0/80` | **32,56 RPS** | 773 ms | **1.395 ms** | 1.601 ms | 40,8 – 41,3 % | **97,5 – 97,8 %** |
| `c = 64` | 7.872 | 0 / `0/61` | **32,80 RPS** | 1.758 ms | **2.498 ms** | 2.660 ms | 40,2 – 40,8 % | **97,8 – 98,0 %** |

Trong phiên tối 21/11/2026 (PR #91, #77), TV1 và TV2 tiếp tục chạy 2 lượt `ab -k -c 64 -t 600` (10 phút) từ Host A qua VIP nội bộ `172.24.4.117:8080` khi đã bật `alarm_actions` trên stack alarm riêng:
- **Lượt 1 (slug `tv4fix1`, ~124.000 visit tích lũy, `14:25:46–14:35:47Z`):** Hoàn tất `14.096` request (`Failed = 0`), đạt **`23,49 RPS`**, `p50 = 2.746 ms`, **`p95 = 3.075 ms`**, `p99 = 3.210 ms`; CPU `campus-db` ở mức **`99,5–99,7%`** (đuôi xử lý sau tải dài ~26 phút), CPU nhóm app tối đa **`27,35%`** (không chạm ngưỡng `60%`).
- **Lượt 2 (slug mới `tv3dc-20261121`, `0` visit lúc bắt đầu, `15:48:39–15:58:39Z`):** Hoàn tất `23.724` request (`Failed = 0`), đạt **`39,54 RPS`**, `p50 = 1.660 ms`, **`p95 = 2.017 ms`**, `p99 = 2.128 ms`; CPU `campus-db` ở mức **`87,5–94,0%`** (đuôi sau tải 1–2 phút), CPU nhóm app đạt đỉnh **`62,48%`** ở bucket `15:50:00Z` và kích hoạt tự động `Aodh → Heat` cả 2 chiều `2 → 3 → 2`.

### 2.3. Đánh giá theo tiêu chí SRS và phân tích giới hạn
1. **`NFR-01` (`p95 redirect ≤ 500 ms` ở ~30 RPS qua Internet): Không đạt.**
   - Theo định nghĩa của SRS (đo từ máy phát qua Internet, mỗi request mở kết nối TCP/TLS mới tới `us-east-1`), `p95` đạt `1.080,7 ms` (16/11) và `~1.200 ms` (17/11), vượt ngưỡng 500 ms.
   - Số đo chẩn đoán phía server từ log Nginx (`$request_time`) đạt `238 ms` (16/11), `256 ms` (17/11), `74–117 ms` ở 10 RPS (18/11), nhưng ở lượt đối chứng 18/11 (W6) đạt `596 ms` (> 500 ms). Vì vậy báo cáo ghi rõ cả hai vị trí đo kèm điều kiện từng lượt, không kết luận chung rằng phía server luôn dưới 500 ms.
2. **`NFR-02` (Tỷ lệ 5xx/timeout < 1% trong lượt không gây lỗi): Đạt.**
   - Mọi lượt đo đều có **0 HTTP `5xx`** từ server; tỷ lệ client timeout `599` chỉ từ **`0,00%` đến `0,154%`**, tức chỉ tiêu thụ **3,34% – 15,36% quỹ lỗi (error budget 1%)** theo `NFR-22`.
3. **`NFR-03` (Hồ sơ tải 10 / 30 / 60 RPS): Đạt một phần (thiếu mức 60 RPS ổn định).**
   - Hai lần thử mức 60 RPS ngày 17/11 (`B1`, `B2`) chỉ đạt ~32–33 RPS thực tế. Phép đo ramp `ab` ngày 20/11 từ chính Host A qua VIP nội bộ trên `tv4fix1` cho thấy thông lượng dừng ở **~32,5 RPS** ngay từ mức `c = 8` (và trên slug mới `tv3dc-20261121` tối 21/11 đạt `39,54 RPS` ở `c = 64`), chưa chạm mức 60 RPS do giới hạn 1 vCPU của DB VM.
4. **Quan sát tương quan về CPU của DB VM (`FR-INF-12`, `NFR-01`, #76, #77, PR #84, PR #89, PR #91):**
   - Trong log Nginx, `urt ≈ rt` (lệch ≤ 1 ms) nên độ trễ phía server nằm ở đoạn sau Nginx.
   - Dữ liệu Gnocchi cho thấy ở cả lượt W6 (18/11, `p95 = 596 ms`) và 5 mức ramp (20/11, ~32,5 RPS), CPU của `campus-db` (1 vCPU) đều ở mức **`92–98%`**, trong khi CPU mỗi app VM ở mức `27–51,5%` (và lúc cụm thực sự rảnh từ `14:22Z` ngày 20/11, CPU `campus-db` chỉ `0,60–0,75%`).
   - Kiểm tra chỉ-đọc trên `campus-db` ngày 20/11 ([`evidence/G5/20261120-FR-INF-12-NFR-01-db-vm-cpu-kiem-chi-doc.txt`](../../evidence/G5/20261120-FR-INF-12-NFR-01-db-vm-cpu-kiem-chi-doc.txt), PR #84) xác nhận không có backup hay autovacuum dài trùng thời điểm `14:32Z` ngày 18/11, đồng thời ghi nhận **ứng viên thứ nhất**: Shlink mở kết nối PostgreSQL TCP + TLSv1.3 + `scram-sha-256` mới cho từng request và từng task async (**~50 phiên mới/giây** ở ~25 visit/giây).
   - Phân tích mã nguồn Shlink v5.1.8 và bản sao dump local ngày 21/11 ([`evidence/G4/20261121-FR-INF-11-NFR-05-vi-sao-1411-khac-2011.txt`](../../evidence/G4/20261121-FR-INF-11-NFR-05-vi-sao-1411-khac-2011.txt), PR #89) ghi nhận **ứng viên thứ hai**: mỗi visit kích hoạt task async `NotifyVisitToRedis` chạy 4 lệnh `SELECT COUNT(*)` trên toàn bộ visit của slug, khiến chi phí CPU DB mỗi visit tăng theo số visit đã tích lũy (`O(N)`). Cặp lượt đo tối 21/11 (PR #91) khớp với chiều dự đoán này: slug mới `tv3dc-20261121` (`0` visit ban đầu) tốn ~25 ms CPU DB/visit và đạt `39,54 RPS` (CPU nhóm app `62,48%`), trong khi `tv4fix1` (~124k visit) tốn ~148 ms CPU DB/visit và chỉ đạt `23,49 RPS` (CPU nhóm app `27,35%`). Đây là **quan sát tương quan khớp số liệu**, chưa đối chứng lặp lại và chưa đổi cấu hình trong freeze (hướng tối ưu sau freeze: tắt pub/sub khi không chạy `campus-stats`, dùng PgBouncer / persistent connection, hoặc tăng vCPU cho DB VM).

---

## 3. Khả năng chịu lỗi, Co giãn và Tài nguyên host (`FR-INF-20`, `NFR-06`, `NFR-07`, `NFR-13`)

### 3.1. Chịu lỗi tắt nóng App VM A (`FR-INF-20`, `NFR-07`)
Lượt đo ngày 18/11/2026 ở mức tải steady **10 RPS** (1.020 s = 10.200 request; [`evidence/G5/20261118-FR-INF-20-NFR-07-tv2-app-a-failover.txt`](../../evidence/G5/20261118-FR-INF-20-NFR-07-tv2-app-a-failover.txt), PR #68, PR #69):
- **Gây lỗi:** TV2 gửi lệnh `openstack server stop` lên app VM A (`10.20.0.195`, AZ-A) lúc `14:57:27.063046Z`.
- **Thời gian phát hiện:** Nova báo `SHUTOFF` lúc `14:57:31.261210Z` (`4,20 s`); Octavia OVN health monitor chuyển member A sang `ERROR` lúc `14:57:36.529516Z` (**`9,47 s`**). Trong cửa sổ 9,5 s này có 95 request (`74` redirect `302`, `0` HTTP `5xx`, chỉ **1 timeout `599`** bắt đầu ở `+1,5 s`).
- **Duy trì dịch vụ qua AZ-B:** Member B (`10.20.0.196`, `campus-az-b`) giữ `ONLINE` trong cả 57 mẫu poll; suốt `301,4 s` A tắt chỉ có **2/3.015 request timeout (`0,066%`)** và **0 HTTP `5xx`**; `p95` phía server (W8) là **`117 ms`**.
- **Hồi phục:** Từ lệnh `openstack server start` (`15:02:28.479184Z`) đến khi cả 2 member `ONLINE` (`15:03:19.474286Z`) mất **`51,00 s`** (HTTPS health `pass` sau `51,12 s`), với **0 lỗi** trong 510 request của cửa sổ hồi phục.

### 3.2. Timeline co giãn `2 → 3 → 2` (scale tay và tự động `Aodh → Heat`) và hiệu quả trên độ trễ phía server (`NFR-06`, `FR-INF-11`)
- **Lượt scale tay có đối chiếu log guest (`16/11/2026`, [`evidence/G4/20261116-FR-INF-11-tv2-evening-baseline.txt`](../../evidence/G4/20261116-FR-INF-11-tv2-evening-baseline.txt)):** Khi kích hoạt scale-out `2 → 3` lúc `14:56:17.725232Z`:
  - VM thứ ba (`10.20.0.102`, UUID `6ed60f3b-aa27-4679-b762-ca7e88264785`) đạt `ACTIVE` lúc `14:57:01.314729Z` (**`43,59 s`**).
  - Request redirect đầu tiên được VM mới phục vụ thành công lúc **`14:57:02.561767Z`** (sau **`44,84 s`**, đối chiếu khớp `Request ID 3b405014-611f-448e-8342-06662e3bd3a2` trên cả CSV máy phát và log container guest).
  - Cả 3 member `ONLINE` ở lần poll `14:57:06.538306Z` (**`48,81 s`**).
- **Hiệu quả giảm độ trễ phía server (`17/11/2026`, `W3` → `W4` → `W5`):** Khi tăng từ 2 lên 3 app VM dưới tải 30 RPS, `p95` phía server giảm từ **`313,0 ms` xuống `189,0 ms`** (giảm ~39,6%), và khi scale-in về 2 app VM thì `p95` trở lại **`288,0 ms`**.
- **Lượt tự động `Aodh → Heat` cả 2 chiều `2 → 3 → 2` (`21/11/2026`, #77, PR #91 `evidence/G4/20261121-FR-INF-11-tu-scale-aodh-heat-hai-chieu.txt`):**
  - Sau khi áp bản vá Aodh `ADR-12 v1 + Gate v2.2` trên Host A (`09:38:04Z`, PR #81) và kiểm chứng chỉ-đánh-giá (`09:46:28Z–10:11:57Z`: `0` `bad_timestamp`, `0` `Traceback`), TV2 bật `alarm_actions` trên stack alarm riêng (giữ nguyên ngưỡng `60%/25%`).
  - Trong **lượt 2 tối 21/11** trên slug mới `tv3dc-20261121` (`0` visit lúc bắt đầu, TV1 phát tải `ab -k -c 64 -t 600` từ `15:48:39Z` đến `15:58:39Z`, đạt `39,54 RPS`, CPU nhóm app đạt đỉnh **`62,48%`** ở bucket `15:50:00Z`, không gửi signal tay):
    - **`15:53:22.719459Z` (`+4 phút 43,7 s` sau khi bắt đầu tải):** Alarm `cpu_high` chuyển sang **`ALARM`** (2 mẫu liên tiếp vượt `36e9` ns, mẫu gần nhất `37,345e9` ns).
    - **`15:53:40Z` / `15:54:08Z`:** Heat ghi nhận VM mới `CREATE_COMPLETE` (`+17,3 s` sau `ALARM`) và readiness `WaitCondition` `CREATE_COMPLETE` (`+45,3 s` sau `ALARM`).
    - **`15:54:12Z` (`+49,3 s` sau `ALARM`):** Heat ghi `scale_out SIGNAL_COMPLETE`.
    - **`15:54:19.543Z` (`+56,8 s` sau `ALARM`):** Octavia OVN LB có đủ **3 member `ONLINE`** (thêm VM mới `10.20.0.102`). Khi VM mới vào nhóm, Gate v2.2 chuyển hai alarm sang `insufficient data` (`campus-gate reject=gnocchi_400`) lúc `15:54:22Z` rồi tự hồi phục về `ok` lúc `15:58:22Z` (`cpu_high`) và `15:59:22Z` (`cpu_low`).
    - **`16:04:22.582082Z` (`+5 phút 43,6 s` sau khi dừng tải lúc `15:58:39Z`):** Alarm `cpu_low` chuyển sang **`ALARM`** (3 mẫu liên tiếp dưới `15e9` ns, mẫu gần nhất `0,35e9` ns).
    - **`16:04:38Z` (`+15,4 s` sau `ALARM`):** Heat ghi `scale_in SIGNAL_COMPLETE`.
    - **`16:04:57.781Z` (`+35,2 s` sau `ALARM`):** LB trở về **2 member `ONLINE`** (`10.20.0.195` và `10.20.0.102`), VM B cũ (`10.20.0.170`) được xóa. Journal `aodh-notifier` và `aodh-evaluator` hoàn toàn sạch (không có `401`, `403`, `error` hay `Traceback`).
  - **Giới hạn ghi nhận (giữ `FR-INF-11`, `NFR-05`, `NFR-06` ở mức Đạt một phần):** (1) Lượt tự động 21/11 còn thiếu mốc cuối của `NFR-06` là *"request đầu tiên tới VM mới (`10.20.0.102`)"* do chưa đối chiếu log guest; (2) Ở lượt 1 cùng tối trên `tv4fix1` (~124k visit), CPU nhóm app chỉ đạt `27,35%` (không scale-out) vì DB VM 1 vCPU bão hòa trước; (3) Mới có 1 lượt tự động 2 chiều thành công và PR #81 (mã Gate v2.2) đang chờ merge lên `main`. Thực nghiệm `NFR-04` (so sánh static vs auto ≥ 3 lượt đảo thứ tự) là **chưa làm**.

### 3.3. Tài nguyên Host và Placement Reservation (`NFR-13`)
- Cấu hình Placement trên 2 host (`evidence/G2/20261027-NFR-13-placement-reserved.txt`): Host A (`m7i.2xlarge` 8 vCPU / 32 GiB) giữ lại `4 vCPU / 16.384 MiB` cho controller + storage; Host B (`m7i.xlarge` 4 vCPU / 16 GiB) giữ lại `1 vCPU / 8.192 MiB` cho compute agent; `cpu_allocation_ratio = 1.0`, `ram_allocation_ratio = 1.0`.
- Qua toàn bộ các phiên chạy 3 app VM + 1 DB VM dưới tải (14/11 – 21/11), không xảy ra OOM hay swap kéo dài trên cả host lẫn guest (trên `campus-db` lúc tải ~90% CPU ngày 20/11: RAM dùng `348,6 / 1.968,0 MiB`, `avail Mem = 1.619,4 MiB`, `Swap = 0`, PR #84).

---

## 4. Quản lý Chi phí và Đánh giá Trụ cột Cost Optimization – AWS Well-Architected (`FR-INF-21`, `NFR-16`)

Bản xuất chi tiết phép tính AWS Pricing Calculator và dự báo đến 30/11 nằm tại [`evidence/G5/20261121-FR-INF-21-NFR-16-aws-pricing-calculator.txt`](../../evidence/G5/20261121-FR-INF-21-NFR-16-aws-pricing-calculator.txt) và [`cost.csv`](../../cost.csv).

### 4.1. Kết quả theo dõi chi phí thực tế và dự toán 2 kịch bản
1. **Theo dõi giờ chạy theo phiên (`cost.csv`):**
   - Từ 22/10/2026 đến hết tối 21/11/2026 (61 dòng phiên theo Nhật ký cloud #4 và `last -x`), các phiên đã có giờ Start/Stop cụ thể ghi nhận Host A chạy **2.199,6 phút (~36,66 giờ)** và Host B chạy **1.598,6 phút (~26,64 giờ)**, tương ứng tiền máy EC2 là **~20,51 USD** (cộng phiên tối 21/11 boot `13:27Z` và chi phí nền ~0,52–0,62 USD/ngày của 150 GiB EBS `gp3`, 1 EIP và EBS Snapshot DLM khi máy tắt).
2. **Đối chiếu AWS Billing Credits & Budgets:**
   - **AWS Credits ([`evidence/G0/20261118-FR-INF-21-aws-credits.png`](../../evidence/G0/20261118-FR-INF-21-aws-credits.png)):** Tổng credit được cấp là **`140,00 USD`** (Free Tier `100 USD` + hai gói Explore AWS `20 + 20 USD`). Số dư ước tính giảm từ `131,38 USD` (22/10) xuống **`93,96 USD`** (18/11), tức toàn dự án tiêu thụ **`37,42 USD`** từ ngày bắt đầu lab 22/10 đến 18/11 (tổng dùng lũy kế trên tài khoản là `46,04 USD`, gồm `8,62 USD` trước 22/10).
   - **AWS Budgets ([`evidence/G0/20261119-FR-INF-21-aws-budgets.png`](../../evidence/G0/20261119-FR-INF-21-aws-budgets.png)):** Ba ngưỡng cảnh báo **`30 / 50 / 65 USD`** đều `Healthy`; chi phí tháng 11 tính đến 19/11 là **`27,34 USD`**, AWS dự báo cả tháng 11 là **`53,65 USD`** (và dự báo lũy kế thực tế của nhóm đến hết bảo vệ 30/11 là **~51,50 USD**, đạt mục tiêu **`≤ 70 USD`** của `C-08` / `NFR-16`).
3. **Kịch bản chạy liên tục 24/7 (`730 giờ/tháng`) và so sánh với AWS Managed (`us-east-1`, ngày 21/11/2026):**
   - **CampusLink (OpenStack trên 2 EC2 `m7i.2xlarge` + `m7i.xlarge`):** $(0{,}615 \times 730 + 18{,}56) \times 1{,}2 = \mathbf{561{,}01\text{ USD/tháng}}$ (theo đơn giá On-Demand `0,6048 USD/giờ` của Calculator là `552,08 USD/tháng`).
   - **Kiến trúc AWS Managed tương đương** (`ALB` 2 AZ + 2–3 `t3.small` Auto Scaling + `RDS PostgreSQL db.t4g.small` + `ElastiCache Redis cache.t4g.small` + `S3` + `NAT Gateway`): **`162,44 USD/tháng`** (Single-AZ DB) đến **`193,24 USD/tháng`** (Multi-AZ DB, đã gồm 20% dự phòng).

### 4.2. Đánh giá trụ cột Tối ưu hóa Chi phí (Cost Optimization – AWS Well-Architected Framework)

| Nguyên tắc Well-Architected | Cách CampusLink áp dụng và bằng chứng thực nghiệm | Đánh giá & Đánh đổi (Trade-offs) |
| --- | --- | --- |
| **1. Quản trị tài chính đám mây (Cloud Financial Management)** | Thiết lập 3 mức AWS Budgets (`30 / 50 / 65 USD`) ngay từ G0 trước khi bật EC2; ghi chép giờ bật/tắt từng host vào Issue #4 và `cost.csv`; đối chiếu định kỳ với AWS Credits (`g0-checklist.md`). | Giúp phát hiện sớm chi phí nền (~0,5–0,6 USD/ngày khi tắt máy) và giữ tổng chi tiêu cả kỳ (`~51,50 USD`, dự báo Budgets `53,65 USD`) dưới trần `70 USD`. |
| **2. Chi tiêu theo nhu cầu thực (Expenditure & Usage Awareness)** | Cơ chế **3 lớp chống quên tắt máy**: (1) `campus-idle-shutdown.timer` tự tắt host sau 60 phút không có SSH hay `campus-keepalive`; (2) `EventBridge Scheduler` tự gửi `StopInstances` lúc 02:00 giờ VN hằng ngày; (3) IAM policy `CampusLinkStartStop` cho phép TV2–TV4 tự bật/tắt theo tag `Project=CampusLink` và script `campus-check` kiểm tra trước khi Stop. | Thời gian bật EC2 thực tế chỉ ~37 giờ cho Host A và ~27 giờ cho Host B trong suốt 1 tháng, tiết kiệm **> 90%** chi phí compute so với chạy 24/7 (`561,01 USD/tháng`). |
| **3. Sử dụng tài nguyên hiệu quả (Cost-Effective Resources)** | Chọn `m7i.2xlarge` (A) và `m7i.xlarge` (B) là dòng nhỏ nhất hỗ trợ **nested KVM** đủ RAM cho control plane + compute; thay AWS NAT Gateway (`~33,85 USD/tháng`) bằng `campus-nat` (`iptables MASQUERADE` ngay trên Host A, `0 USD`); dùng `sslip.io` + Let's Encrypt miễn phí thay vì mua domain/Route 53 + ACM Private CA; dùng EBS `gp3` thay `gp2`. | Rất tối ưu cho môi trường Lab bật/tắt theo phiên. Tuy nhiên nếu chạy 24/7 ở quy mô nhỏ (2–3 app), việc gánh nguyên control plane OpenStack làm chi phí cao hơn ~2,9–3,5 lần so với dùng AWS Managed (`ALB` + `t3.small` + `RDS` + `ElastiCache`). |
| **4. Khớp cung – cầu theo thời gian (Manage Demand and Supply)** | Kết hợp 1 app cố định ở AZ-A với `OS::Heat::AutoScalingGroup` (`min=1, max=2`) ở AZ-B, tự động co giãn `2 → 3 → 2` qua `Aodh → Heat` (PR #91) và hạn mức project cứng (`C-07`: tối đa 6 VM, 8 vCPU, 12 GiB RAM) để tránh mở rộng vượt ngân sách. | Khi tải tăng (lượt 17/11 W4 và lượt tự scale tối 21/11), thêm replica thứ 3 giúp giảm `p95` phía server từ `313 ms` xuống `189 ms`; khi tải giảm (`cpu_low < 25%` trong 3 phút) thì tự động thu hồi VM về `min=1`. |
| **5. Tối ưu hóa theo thời gian (Optimize Over Time)** | Sau khi hoàn thành bằng chứng `FR-INF-17`, TV4 đã rà soát và xác nhận hoàn tất biên bản cho snapshot thử `snap-03f8a6038bec5b942` (30 GiB) để TV1 có thể xóa giảm phí lưu trữ; DLM snapshot tự động giới hạn retention `3 bản`. | Duy trì chi phí lưu trữ cố định trong đúng ngân sách `18,56 USD/tháng`. |

---

## 5. Phụ lục A: Tóm tắt Ma trận Nghiệm thu Toàn bộ Yêu cầu (`FR-APP`, `FR-INF`, `NFR`)

Bảng ma trận chi tiết từng đường dẫn bằng chứng được duy trì tại [`docs/acceptance.md`](../acceptance.md) (Mục 1 và Phụ lục Mục 5). Dưới đây là thống kê tổng hợp trạng thái nghiệm thu của toàn bộ 68 mã yêu cầu trong `docs/SRS.md` tính đến ngày **22/11/2026**:

| Nhóm yêu cầu | Tổng số mã | **Đạt** | **Đạt một phần** | **Không đạt** | **Rút (theo mốc cắt #40)** | Chi tiết các mã không phải "Đạt" |
| --- | --- | --- | --- | --- | --- | --- |
| **1. Ứng dụng (`FR-APP-01..21`)** | 21 | **12** (`FR-APP-01`..`12` trên cụm, 27 PASS) | **3** (`FR-APP-13`, `14`, `16`: đạt 31 PASS trên Compose MVP, trên cụm dừng ở DB/secret/Swift) | **0** | **6** (`FR-APP-15`, `17`, `18`, `19`, `20`, `21`) | Theo luật lùi cứng #40 (PR #73, PR #85) để ưu tiên ổn định cụm cho G4–G5. |
| **2. Hạ tầng (`FR-INF-01..25`)** | 25 | **19** (`FR-INF-01`..`04`, `06`..`10`, `12`..`18`, `20`..`22`) | **6** (`FR-INF-05`, `11`, `19`, `23`, `24`, `25`) | **0** | **0** | • `FR-INF-05`: chưa có evidence giữ SG cổng 22 ở `/32` cố định.<br>• `FR-INF-11`: đã tự scale `Aodh → Heat` 2 chiều `2→3→2` tối 21/11 (PR #91), còn thiếu mốc request đầu tiên tới VM mới và lượt trên slug cũ `tv4fix1` không chạm 60%.<br>• `FR-INF-19`: Phần 1 & 2 PASS, Phần 3 mới chạy cột "Trước".<br>• `FR-INF-23`: có gitleaks + Trivy/SBOM, không ký cosign.<br>• `FR-INF-24`: `campus-chaos` PASS trên stack lab AZ-A.<br>• `FR-INF-25`: tầng 1 & 2 PASS, tầng 3 dùng bản thay thế restore vào Compose mới (RTO 18,2 s, PR #86). |
| **3. Phi chức năng (`NFR-01..22`)** | 22 | **11** (`NFR-02`, `07`, `08`, `09`, `11`..`16`, `22`) | **7** (`NFR-03`, `05`, `06`, `10`, `18`, `20`, `21`) | **2** (`NFR-01`, `NFR-04`) | **2** (`NFR-17`, `NFR-19`) | • **Đạt (11 mã):** `NFR-02`, `07`, `08`, `09`, `11`, `12`, `13`, `14`, `15`, `16`, `22`.<br>• **Đạt một phần (7 mã):** `NFR-03` (thiếu 60 RPS), `NFR-05` & `06` (tự scale 2 chiều tối 21/11 thiếu mốc request đầu tiên tới VM mới; PR #81 chờ merge), `NFR-10` (cert + SSL Labs hạng A, chưa chạy ZAP), `NFR-18` (cách ly đạt trên Compose + key `--author-only`, `O-14` mở phần container portal), `NFR-20` (tầng 3 thay thế không S3), `NFR-21` (JSON chaos chưa tự ghi kết luận `NFR-01/02`).<br>• **Không đạt (2 mã):** `NFR-01` (`p95` qua Internet `1,08–1,20 s > 500 ms`), `NFR-04` (chưa chạy so sánh static vs auto ≥ 3 lượt).<br>• **Rút (2 mã):** `NFR-17`, `NFR-19` (#40). |
| **Tổng cộng** | **68** | **42** | **16** | **2** | **8** | **8/8 hạng mục bắt buộc của đề bài đều có sản phẩm và bằng chứng thực nghiệm trên cụm (6 hạng mục Đạt, 2 hạng mục Đạt một phần là Hạng mục 2 và Hạng mục 6).** |
