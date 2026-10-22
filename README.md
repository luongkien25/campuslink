# CampusLink – Nhóm 11, INT3319

Repo hạ tầng và vận hành cho CampusLink: Shlink v5.1.8 + Shlink Web Client v4.8.1 chạy trên OpenStack DevStack 2026.1, lồng trong 2 EC2 AWS ở 2 AZ.

Repo này **không chứa mã nguồn Shlink**. Hai repo upstream dùng nguyên bản theo release, không fork, không sửa:

| Thành phần | Upstream | Cách dùng trong dự án |
| --- | --- | --- |
| Backend | https://github.com/shlinkio/shlink (tag `v5.1.8`) | Docker image `shlinkio/shlink`, khóa bằng RepoDigest trong `docs/versions.lock` |
| Frontend | https://github.com/shlinkio/shlink-web-client (tag `v4.8.1`) | File `shlink-web-client_4.8.1_dist.zip` từ GitHub Release, kiểm SHA256, đặt lên Nginx |

Chỉ khi thật sự phải vá upstream mới lưu patch vào `app/patches/` kèm lý do (ADR).

## Bắt đầu

- Người mới: đọc `CONTRIBUTING.md` (quy trình nhóm, cách dùng AI, dùng chung cloud).
- AI agent: đọc `AGENTS.md` (Claude Code đọc qua `CLAUDE.md`).

## Cấu trúc

```
AGENTS.md                 # ngữ cảnh + luật cho AI (mọi công cụ)
CLAUDE.md                 # trỏ tới AGENTS.md cho Claude Code
GEMINI.md                 # trỏ tới AGENTS.md cho Gemini CLI
CONTRIBUTING.md           # quy trình nhóm
.github/                  # CODEOWNERS, mẫu issue, mẫu PR
docs/
  SRS.md                  # yêu cầu có mã FR/NFR (bản Markdown của SRS)
  troubleshooting.md      # lỗi đã gặp → cách sửa (AI tra ở đây trước)
  references/             # PDF phân công v1.2 (bản nhóm, sửa theo SRS)
  checklists/             # g0-checklist.md ... (TV1, TV4 review)
  inventory.yaml          # tài nguyên thật: ID, IP, tên (TV1); không secret
  versions.lock           # phiên bản/SHA/digest đã kiểm
  architecture.md
  acceptance.md           # ma trận 8 hạng mục (TV4)
  decisions/              # ADR-01..06 và ADR mới
  handoffs/               # H0–H6 theo _TEMPLATE.md
  runbooks/               # start-stop.md (bật/tắt, tự tắt, snapshot), after-start.md, backup-restore.md
infra/
  aws/                    # bảng subnet/route/SG với ID thật (TV1)
  devstack/               # A.local.conf.example, B.local.conf.example, plugin-overlay.example (TV1, TV2)
  heat/                   # root.yaml, app-unit.yaml, env.example.yaml (TV2)
app/
  compose/                # Compose local để phát triển (TV3), không dùng cho production
  shlink.env.example      # hợp đồng env (SRS mục 4.3)
  nginx/                  # campuslink.conf.example (TV1 + TV3)
ops/                      # campus-nat, add-member.sh, idle-shutdown (TV1); ai-snapshot.sh (mọi người); backup/restore/health (TV3)
tests/
  smoke/                  # contract test (TV4)
  locust/                 # locustfile.py, requirements lock (TV4)
  fixtures/
evidence/                 # G0..G5, đặt theo run-id; đã che secret
```

## Quy tắc làm việc

- Nhánh theo người: `tv1/network`, `tv2/scaling`, `tv3/app`, `tv4/loadtest`. PR nhỏ theo mốc, một người review chéo (TV4 → TV1, TV1 → TV2, TV2 → TV3, TV3 → TV4).
- Chủ sở hữu thư mục (CODEOWNERS): `docs/inventory.yaml`, `infra/aws`, `infra/devstack` → TV1; `infra/heat` → TV2; `app`, `ops` → TV3; `tests`, `evidence`, `docs/acceptance.md` → TV4.
- Mỗi issue ghi: mã yêu cầu SRS (FR/NFR), owner, reviewer, đầu vào, lệnh kiểm tra, kết quả mong đợi, bằng chứng, rollback.
- Không commit secret. Chỉ commit file `.example`; giá trị thật để `REPLACE_...`.
- Ảnh evidence phải che Account ID, IP nhà, thông tin thanh toán trước khi commit; bản gốc để trong `evidence/**/raw/` (bị ignore).
- Cuối mỗi phiên cập nhật 4 dòng: đã có bằng chứng gì; vướng gì; cần ai cung cấp gì; bước kế tiếp. Ghi cloud đang ON/OFF và ai tắt.

## Tài liệu nhóm

- SRS – CampusLink (Claude Doc)
- Phân công chi tiết & kế hoạch phối hợp, bản 1.1 - Shlink (22/10/2026)
- Đề xuất xin xét duyệt (4 trang)
- Lab TV1 bản 1.1 (trích phần liên quan cho từng thành viên)
