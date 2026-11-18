# Bộ kiểm thử CampusLink (`tests/`) – TV4 (`@toancst`)

Thư mục này chứa toàn bộ công cụ kiểm thử hợp đồng API (smoke test), tạo tải (workload / Locust), dữ liệu mẫu (fixtures) và kiểm tra tự động các sản phẩm nghiệm thu của TV4 theo `SRS.md` (`NFR-01`–`04`, `NFR-06`, `NFR-14`, `NFR-16`, `FR-INF-11`, `FR-INF-20`, `FR-INF-21`).

## 1. Cấu trúc thư mục

```text
tests/
  README.md                           # Hướng dẫn chạy lại (NFR-14)
  test_tv4_deliverables.py            # Unit test kiểm tra cost.csv, acceptance.md, versions.lock, bảo mật
  fixtures/
    fixture-slugs.example.json        # Mẫu 5 slug fixture chuẩn (H5, FR-INF-16, NFR-03/04)
  smoke/
    contract-smoke.sh                 # Kiểm thử hợp đồng API Shlink 5.1.8 & Ingress TLS (FR-APP-01..12, FR-INF-06)
  load/
    credentials.env.example           # Mẫu cấu hình endpoint & API key (sao chép thành credentials.env)
    setup-fixture.sh                  # Khởi tạo/xác minh các slug fixture trước phiên đo
    workload.py                       # Bộ phát tải chuẩn NFR-03 (không lộ key trên argv, thu Request-ID)
    workload.sh                       # Wrapper gọi workload.py ở mức 10 / 30 / 60 RPS
  locust/
    locustfile.py                     # Kịch bản tải Locust tương đương (80% redirect, 15% visits, 5% create)
    requirements.txt                  # Khóa phiên bản locust
```

## 2. Nguyên tắc an toàn & bảo mật (`NFR-08`, `NFR-10`)

- **Không truyền API key qua `argv`:** Mọi lệnh gọi REST API trong `smoke/contract-smoke.sh`, `load/setup-fixture.sh`, `load/workload.py` và `locust/locustfile.py` đều đọc `SHLINK_API_KEY` trực tiếp từ file `credentials.env` (bị `.gitignore` chặn) hoặc truyền qua `curl --config -` (stdin), không bao giờ để lộ key trong `ps aux`.
- **Không tắt kiểm chứng TLS:** Không dùng `curl -k` hay `verify=False` khi đo qua Internet (`https://s.44-198-215-187.sslip.io`).
- **Cách ly tải đo (`NFR-03`, `ADR-08`):** Không chạy đồng thời với backup lớn, build image hay job `campus-worker`.

## 3. Chạy lại Smoke Test hợp đồng (`NFR-14`)

```bash
# Bước 1: Tạo file credentials.env từ mẫu (chỉ làm 1 lần, không commit)
cp tests/load/credentials.env.example tests/load/credentials.env
# Điền SHLINK_API_KEY thật vào tests/load/credentials.env (chmod 600)

# Bước 2: Chạy contract smoke test
bash tests/smoke/contract-smoke.sh tests/load/credentials.env
```

## 4. Chạy Workload đo Autoscaling (`FR-INF-11`, `NFR-06`) & Benchmark (`NFR-01`–`04`)

```bash
# Bước 1: Chuẩn bị/kiểm tra các slug fixture
bash tests/load/setup-fixture.sh

# Bước 2: Chạy tải ở mức mục tiêu (10, 30 hoặc 60 RPS; warm-up 120s, steady 300s)
bash tests/load/workload.sh 30
bash tests/load/workload.sh 60
```

Kết quả mỗi lượt chạy được xuất tự động ra `tests/load/logs/<UTC>-workload-<RPS>rps-raw.csv` (gồm `timestamp_utc,request_type,slug,http_status,latency_ms,request_id,location`) kèm bản tóm tắt `p50`, `p95` (`NFR-01 <= 500 ms`), tỷ lệ `5xx/timeout` (`NFR-02 < 1%`) và mốc thời gian UTC để đối chiếu với chuỗi sự kiện `ALARM → Heat event → VM ACTIVE → app ready` của TV2 (`NFR-06`).

## 5. Chạy Unit Test kiểm chứng sản phẩm của TV4 (offline)

```bash
python3 -m unittest discover -s tests -v
```
