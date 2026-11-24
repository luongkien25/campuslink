# CampusLink – Nhóm 11, INT3319

Repo hạ tầng và vận hành cho CampusLink: Shlink v5.1.8 + Shlink Web Client v4.8.1 chạy trên OpenStack DevStack 2026.1, lồng trong 2 EC2 AWS ở 2 AZ.

Repo này **không chứa mã nguồn Shlink**. Hai repo upstream dùng nguyên bản theo release, không fork, không sửa:

| Thành phần | Upstream | Cách dùng trong dự án |
| --- | --- | --- |
| Backend | https://github.com/shlinkio/shlink (tag `v5.1.8`) | Docker image `shlinkio/shlink`, khóa bằng RepoDigest trong `docs/versions.lock` |
| Frontend | https://github.com/shlinkio/shlink-web-client (tag `v4.8.1`) | File `shlink-web-client_4.8.1_dist.zip` từ GitHub Release, kiểm SHA256, đặt lên Nginx |

Chỉ khi thật sự phải vá upstream mới lưu patch kèm lý do (ADR). Hiện có một bản vá cho Aodh (không phải Shlink) ở `infra/devstack/patches/`, theo `docs/decisions/ADR-12-aodh-rate-tung-vm.md`.

## Dành cho người chấm (đọc trước)

Luồng: Internet → EIP → Nginx trên host A (:443, Let's Encrypt) → VIP Octavia OVN → các app VM Shlink ở 2 AZ → PostgreSQL + Redis trên DB VM. Sơ đồ: [`docs/images/kien-truc.png`](docs/images/kien-truc.png).

Thứ tự đọc gợi ý (khoảng 20 phút):

1. [`docs/SRS.md`](docs/SRS.md) mục 6.2: 8 hạng mục bắt buộc và cách kiểm từng hạng mục.
2. [`docs/acceptance.md`](docs/acceptance.md): trạng thái từng hạng mục, đường dẫn bằng chứng và ghi chú giới hạn (Đạt / Đạt một phần / Chưa). **Trạng thái chính xác của từng yêu cầu chỉ ghi ở file này**; README không lặp lại để khỏi lệch nhau.
3. [`evidence/`](evidence/): bằng chứng theo gate G0–G5, tên file `<yyyymmdd>-<mã yêu cầu>-<mô tả>`; ảnh đã che Account ID. [`evidence/cost.csv`](evidence/cost.csv) là sổ giờ chạy và chi phí.
4. [`docs/decisions/`](docs/decisions/): quyết định thiết kế (ADR-07 đến ADR-12). Đáng đọc: ADR-12 (autoscaling và bản vá Aodh), ADR-10 (secret trong Swift và credential hẹp), ADR-07 (SSH).
5. [`docs/runbooks/`](docs/runbooks/): bật/tắt cụm, kiểm sau khi bật, backup DB, dựng DB VM.

| # | Hạng mục (SRS 6.2) | Mã yêu cầu chính | Bằng chứng ở |
| --- | --- | --- | --- |
| 1 | Mạng, 2 AZ | FR-INF-01..04 | `evidence/G0`, `evidence/G1` |
| 2 | Ứng dụng private | FR-INF-05, 06; NFR-10 | `evidence/G2`, `evidence/G3`, ADR-07 |
| 3 | Hai loại storage | FR-INF-13, 14 | `evidence/G0`, `evidence/G1`, `evidence/G3` |
| 4 | Cơ sở dữ liệu | FR-INF-12, 15, 16, 25 | `evidence/G3` |
| 5 | IAM / quyền | FR-INF-17, 18; NFR-08, 09 | `evidence/G0` đến `evidence/G3`, ADR-10 |
| 6 | LB + autoscaling | FR-INF-07..09, 11, 20, 22, 24 | `evidence/G1` đến `evidence/G5`, ADR-12 |
| 7 | Monitoring + alarm | FR-INF-10; NFR-13, 15, 22 | `evidence/G1`, `evidence/G4` |
| 8 | Dự toán, chi phí | FR-INF-21; NFR-16 | `evidence/cost.csv`, `evidence/G0` |

Phạm vi cần biết trước khi đọc bằng chứng:

- Phần mở rộng cổng quản lý chiến dịch (`app/portal`) chạy trên cụm qua stack Heat độc lập (`infra/heat/portal-stack.yaml`, vhost `app.`, Octavia OVN `:8081`), dùng chung mạng `campus-net`, CSDL và Swift với cụm lõi mà không ảnh hưởng các phiên đo tải lõi.
- Chỗ nào chưa đạt hoặc chỉ đạt một phần được ghi thẳng trong `docs/acceptance.md` kèm số đo; tiêu chí gốc nằm ở `docs/SRS.md` và không được nới để "PASS".

### Chạy lại

- **Không cần cụm** (offline): `python3 -m unittest discover -s tests -v` (kiểm tra tài liệu và số liệu của TV4); test Heat offline: [`infra/heat/README.md`](infra/heat/README.md); `campus-chaos`: [`ops/campus-chaos/README.md`](ops/campus-chaos/README.md) và `ops/campus-chaos/test_campus_chaos.py`; chạy Shlink bằng Compose local và smoke H1: [`docs/handoffs/H1-shlink.md`](docs/handoffs/H1-shlink.md), `app/compose/`, `app/smoke/h1-smoke.sh`.
- **Trên cụm** (cần credential và API key, không nằm trong repo): contract smoke và workload tải theo [`tests/README.md`](tests/README.md) mục 3 và 4; kiểm sau khi bật cụm theo [`docs/runbooks/after-start.md`](docs/runbooks/after-start.md).
- **Dựng lại từ đầu:** AWS (VPC, subnet, SG, IAM) ở [`infra/aws/README.md`](infra/aws/README.md); DevStack từ `infra/devstack/A.local.conf.example` và `B.local.conf.example`; các mốc bàn giao H2 đến H4 ở `docs/handoffs/`. Quy trình `stack.sh` từng bước nằm trong tài liệu nhóm "Lab TV1" (ngoài repo).

## Bắt đầu

- Thành viên mới: đọc `CONTRIBUTING.md` (quy trình nhóm, dùng chung cloud, Git/PR và bảo mật secret).
- TV2 triển khai app bằng Heat: [template, tests offline và trình tự kiểm cloud](infra/heat/README.md).

## Cấu trúc

```
CONTRIBUTING.md           # quy trình làm việc nhóm
cost.csv                  # sổ giờ chạy và chi phí (bản gốc; bản trong evidence/ để nộp)
.github/                  # CODEOWNERS, mẫu issue, mẫu PR, workflows/supply-chain.yml (gitleaks, Trivy, SBOM)
docs/
  SRS.md                  # yêu cầu có mã FR/NFR (bản Markdown của SRS)
  acceptance.md           # ma trận 8 hạng mục (TV4)
  troubleshooting.md      # lỗi đã gặp → cách sửa
  inventory.yaml          # tài nguyên thật: ID, IP, tên (TV1); không secret
  versions.lock           # phiên bản/SHA/digest đã kiểm
  images/                 # kien-truc.png, kien-truc.mmd
  references/             # PDF phân công v1.2 (bản nhóm, sửa theo SRS)
  checklists/             # g0-checklist.md (TV1, TV4 review)
  decisions/              # ADR-07..12 (ADR-01..06 được nêu trong SRS, chưa tách thành file)
  handoffs/               # H1..H5 và H3b theo _TEMPLATE.md
  runbooks/               # start-stop.md, after-start.md, db-backup.md, db-vm.md, ssh-key-thanh-vien.md
infra/
  aws/                    # bảng subnet/route/SG với ID thật, IAM start/stop (TV1)
  devstack/               # A/B.local.conf.example, patches/ (bản vá Aodh ADR-12) (TV1, TV2)
  heat/                   # root.yaml, app-unit.yaml, alarms.yaml, portal-stack.yaml, env.example.yaml, telemetry (TV2)
  nginx/                  # campus.conf.example (TV1)
  apache/                 # campus-acme.conf.example (cấp cert, TV1)
app/
  shlink.env.example      # hợp đồng env (SRS mục 4.3)
  compose/                # Compose local để phát triển (TV3), không dùng cho production
  db/                     # DB VM: user-data, backup/restore, secret (TV3)
  portal/                 # cổng quản lý chiến dịch campus-portal (FastAPI)
  smoke/                  # smoke H1 trên cụm và Compose
ops/                      # campus-nat, campus-check, campus-keepalive, idle-shutdown, add-member.sh (TV1); cluster-snapshot.sh (mọi người); dr/ (DR tầng 1-2), campus-chaos/ (FR-INF-24)
tests/
  smoke/                  # contract test (TV4)
  load/                   # workload.py, setup-fixture.sh (TV4)
  locust/                 # locustfile.py, requirements lock (TV4)
  fixtures/
evidence/                 # G0..G5, đặt theo <yyyymmdd>-<mã>-<mô tả>; đã che secret; cost.csv
```

## Quy tắc làm việc

- Nhánh theo người: `tv1/network`, `tv2/scaling`, `tv3/app`, `tv4/loadtest`. PR nhỏ theo mốc, một người review chéo (TV4 → TV1, TV1 → TV2, TV2 → TV3, TV3 → TV4).
- Chủ sở hữu thư mục (xem `.github/CODEOWNERS`): mặc định, `docs/inventory.yaml`, `infra/aws` → TV1; `infra/devstack` → TV1 + TV2; `infra/heat` → TV2; `app` → TV3; `ops` → TV3 + TV1; `tests`, `evidence`, `docs/acceptance.md` → TV4.
- Mỗi issue ghi: mã yêu cầu SRS (FR/NFR), owner, reviewer, đầu vào, lệnh kiểm tra, kết quả mong đợi, bằng chứng, rollback.
- Không commit secret. Chỉ commit file `.example`; giá trị thật để `REPLACE_...`.
- Ảnh evidence phải che Account ID, IP nhà, thông tin thanh toán trước khi commit; bản gốc để trong `evidence/**/raw/` (bị ignore).
- Cuối mỗi phiên cập nhật 4 dòng: đã có bằng chứng gì; vướng gì; cần ai cung cấp gì; bước kế tiếp. Ghi cloud đang ON/OFF và ai tắt.

## Tài liệu nhóm (ngoài repo)

- SRS – CampusLink; bản Markdown trong repo là `docs/SRS.md`
- Phân công chi tiết và kế hoạch phối hợp, bản 1.1 - Shlink (22/10/2026)
- Đề xuất xin xét duyệt (4 trang)
- Lab TV1 bản 1.1 (trích phần liên quan cho từng thành viên)
