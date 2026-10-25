# Cách làm việc chung trên repo CampusLink

Nhóm còn mới với OpenStack và sẽ dùng AI nhiều. Nguyên tắc chung: **repo là bộ nhớ chung của cả người lẫn AI.**
Cái gì đúng và đã kiểm thì ghi vào repo, để AI của người sau đọc được, khỏi phải hỏi lại hay đoán lại.

## 1. Vòng làm việc trong 1 phút

```
(đầu phiên) AI kiểm hộp yêu cầu: có ai đang chờ mình không (mục 9)
  → Issue (mã FR/NFR + tiêu chí dừng)
  → mở AI với đúng ngữ cảnh (mục 3)
  → AI đưa kế hoạch + lệnh  → mình đọc hiểu, xác nhận lệnh thay đổi trạng thái
  → chạy thật, dán output thật lại cho AI
  → PASS: lưu evidence đã che, mở PR   |   FAIL: lặp lại, quá 3 vòng thì hỏi nhóm
  → cần người khác làm một phần: mở yêu cầu [YC-TVx] cho họ (mục 9), không nhắn miệng
  → ghi lỗi đã gỡ vào docs/troubleshooting.md, đổi giá trị thật thì sửa inventory/handoff
  → người review chéo chạy lại hoặc xem chạy, rồi merge
```

## 2. Thiết lập lần đầu (mỗi người)

1. Clone repo, đọc `README.md`, `docs/SRS.md` mục 1–2 và 6, `AGENTS.md`.
2. Gửi TV1 **public key** SSH. Không gửi private key. Chưa cần IP: cổng 22 đang mở theo ADR-07; từ freeze 06/11 mới gửi **IP /32** để TV1 thêm vào SG.
3. TV1 tạo cho mỗi người **một user Linux riêng trên host A** (`tv2`, `tv3`, `tv4`), không sudo, thuộc nhóm `systemd-journal` để đọc log. Lý do: mỗi người có `clouds.yaml` riêng, biết ai chạy lệnh gì, và AI chạy dưới user đó không thể vô tình phá host. Chỉ TV1 dùng `ubuntu`/`stack`.
   `~/.ssh/config` trên máy mình:

   ```
   Host campus-a
     HostName <EIP của A>
     User <tv2|tv3|tv4>
     IdentityFile ~/.ssh/<key-của-bạn>
     IdentitiesOnly yes
   # campus-b: chi khi can, thuong la TV1
   Host campus-b
     HostName 10.11.11.10
     User <user trên B>
     IdentityFile ~/.ssh/<key-của-bạn>
     IdentitiesOnly yes
     ProxyJump campus-a
   ```

   `IdentitiesOnly yes` để ssh chỉ thử đúng key này. Thiếu dòng này mà ssh-agent có nhiều key thì mỗi lần đăng nhập bị tính là lỗi, fail2ban chặn IP 10 phút, cả nhóm chung wifi cùng bị chặn. Ghi chú để trên dòng riêng, không để sau giá trị.

4. TV1 tạo user Keystone cho từng người (TV2/TV3 `member`, TV4 `reader`). Mỗi người đặt `clouds.yaml` trong `~/.config/openstack/` **của user mình trên host A** (`chmod 600`) và chạy với `OS_CLOUD=<tên>`. Mật khẩu trao qua kênh riêng (SRS O-02), không qua repo hay chat nhóm.
5. Chọn công cụ AI (mục 3). Sinh viên có thể lấy GitHub Copilot miễn phí qua GitHub Education.
6. Cài GitHub CLI `gh` (https://cli.github.com; Windows: `winget install --id GitHub.cli`) rồi `gh auth login` một lần. Có `gh` thì AI tự đọc hộp yêu cầu đầu mỗi phiên (mục 9); không có thì mình phải mở link và dán cho AI.

## 3. Cho AI đúng ngữ cảnh

Câu trả lời của AI chỉ tốt bằng ngữ cảnh mình đưa. Kiến thức chung của AI về OpenStack 2026.1 có thể sai hoặc cũ; **dữ liệu thật của nhóm thì không**.

**AI chạy trong repo** (Claude Code, Codex, Copilot agent, Cursor, Gemini CLI): mở ngay trong thư mục repo. Chúng tự đọc `AGENTS.md` (Claude Code qua `CLAUDE.md`, Gemini CLI qua `GEMINI.md`). Giữ chế độ **hỏi trước khi chạy lệnh**; không dùng `--yolo`, `--dangerously-skip-permissions` hay chế độ full-auto khi làm với cloud chung. Trên Windows nên chạy agent trong WSL, đặt SSH key trong `~/.ssh` của WSL. Nhắc AI đọc thêm file theo bảng dưới.

**AI dạng chat web** (ChatGPT, Claude, Gemini): tạo một *Project* riêng cho CampusLink và upload: `AGENTS.md`, `docs/SRS.md`, `docs/inventory.yaml`, `docs/troubleshooting.md` và các handoff mình nhận. **Upload lại khi các file đó đổi** (xem lịch sử commit).

| Người | Phần SRS cần nhất | Handoff nhận | Thư mục làm |
| --- | --- | --- | --- |
| TV1 | 3.2 (FR-INF-01–06, 13, 14, 17–19), 4.4 | — | `infra/aws`, `infra/devstack`, `ops` |
| TV2 | 3.2 (FR-INF-07–11, 20, 22), 4.3, 4.5 | H1, H2 | `infra/heat` |
| TV3 | 3.1, 4.1–4.3, FR-INF-12, 15, 16 | H2, H3 | `app`, `ops` |
| TV4 | 5, 6, FR-INF-21 | H4, H5 | `tests`, `evidence` |

**Prompt mẫu** (chép, điền, gửi):

```
Bối cảnh: repo CampusLink, đọc AGENTS.md trước. Tôi là TV2, mới với OpenStack.
Việc: FR-INF-09 – <chép nguyên văn yêu cầu trong SRS>.
Tiêu chí xong: <chép cột "Kiểm bằng">.
Đầu vào: <trích handoff H2/H4, giá trị trong inventory>.
Trạng thái hiện tại: <dán output ops/ai-snapshot.sh hoặc lỗi nguyên văn>.
Yêu cầu: kế hoạch từng bước; giải thích mỗi lệnh làm gì; đánh dấu lệnh thay đổi trạng thái;
ghi "chưa kiểm" cho tham số không chắc ở bản 2026.1. Không làm ngoài phạm vi việc này.
```

## 4. Debug với AI

- **Dán output thật, nguyên văn.** Lấy trạng thái nhanh bằng:
  `ssh campus-a 'OS_CLOUD=<tên> bash -s -- lb' < ops/ai-snapshot.sh > snap.txt` (phần: `base`, `net`, `lb`, `heat`, `telemetry`, `storage`, `logs`, `all`).
  Script chỉ đọc và tự che chuỗi giống mật khẩu/token, nhưng vẫn liếc lại trước khi dán.
- Tra `docs/troubleshooting.md` trước; bảo AI đọc nó.
- Mỗi lần chỉ đổi một thứ, rồi kiểm lại.
- AI đề xuất lệnh trong danh sách "Phải hỏi" của `AGENTS.md` mục 6: dừng, hỏi người phụ trách phần đó (thường là TV1) trước khi chạy.
- AI lặp quá 3 vòng không tiến triển: dừng, ghi lại tình trạng vào issue, hỏi nhóm. Thường là thiếu ngữ cảnh hoặc AI đang dùng kiến thức cũ.
- Bảo AI giải thích *vì sao* lệnh sửa được lỗi. Không hiểu thì chưa merge.

## 5. Dùng chung cloud

Hai EC2 dùng chung và tốn tiền theo giờ, nên:

- Bật/tắt máy, tự tắt khi rảnh, giữ máy khi đo tải, snapshot: làm theo `docs/runbooks/start-stop.md`.

- Một issue ghim tên **"Nhật ký cloud"**. Mỗi phiên comment: ai bật, giờ (UTC), định làm gì, ai tắt. Không cần commit file log, tránh xung đột.
- Trước thay đổi ảnh hưởng người khác (stack Heat, network, SG, restart dịch vụ, `stack.sh`): báo trong nhóm và chờ ai đang dùng xong.
- Cuối phiên ghi 4 dòng (README): bằng chứng đã có; vướng gì; cần ai cung cấp gì (ghi số issue `[YC-TVx]` đã mở); bước kế tiếp.
- Không ai chắc cloud đã tắt thì người bật cuối cùng chịu trách nhiệm tắt (SRS O-09).

## 6. Git

- Nhánh: `tv1/...`, `tv2/...`, `tv3/...`, `tv4/...`, mỗi nhánh một việc nhỏ. Commit: `[FR-INF-09] mô tả`.
- PR theo mẫu, review chéo: TV4 → TV1, TV1 → TV2, TV2 → TV3, TV3 → TV4. Người review **chạy lại hoặc xem chạy**, không chỉ đọc diff.
- `CODEOWNERS` tự gắn reviewer theo thư mục (đã điền username thật cả 4 người).
- Bảo vệ nhánh `main`: bắt buộc PR + 1 approve, không push thẳng.

## 7. Ghi lại kiến thức (quan trọng nhất)

| Gặp | Ghi vào |
| --- | --- |
| Lỗi đã gỡ được | `docs/troubleshooting.md`: 1 dòng triệu chứng → nguyên nhân → cách sửa → nguồn |
| Giá trị thật mới (UUID, IP, tên) | `docs/inventory.yaml` |
| Xong một mốc giao người khác | `docs/handoffs/Hx-...md` theo `_TEMPLATE.md` |
| Chọn giữa nhiều phương án | `docs/decisions/ADR-xx-...md` |
| Thủ tục lặp lại (stop/start, backup) | `docs/runbooks/` |

Phiên chat AI hữu ích thì dán link hoặc tóm tắt vào issue.

## 8. Secret và evidence

- Không commit: mật khẩu, API key, `clouds.yaml`, `local.conf`, `*.pem`, `/etc/letsencrypt`, Redis URI. Chỉ commit `*.example` với `REPLACE_...`.
- Không dán secret vào AI. Thay bằng `<REDACTED>` trước khi dán.
- Evidence che Account ID, IP nhà, thông tin thanh toán; bản gốc để `evidence/**/raw/` (bị ignore).
- Lỡ commit secret: báo TV1 ngay để **đổi secret**. Xóa khỏi lịch sử git là chưa đủ.

## 9. Nhờ nhau: hộp yêu cầu (GitHub Issues)

Đang làm mà cần người khác (ví dụ AI của TV1 báo "cần TV2 chốt commit Gnocchi"), thì **mở một issue yêu cầu** cho người đó. Lần sau người đó mở AI trong repo, AI tự đọc `AGENTS.md` mục 10 và báo ngay đầu phiên: "TV1 đang chờ bạn việc …".

**Gửi yêu cầu**

1. Bảo AI: "soạn yêu cầu cho TV2 theo mẫu". AI điền mẫu, mình đọc lại (đúng việc, có tiêu chí xong, không có secret).
2. Tạo issue: AI chạy `gh issue create …` sau khi mình đồng ý, hoặc mình mở https://github.com/luongkien25/campuslink/issues/new?template=yeu-cau.md và dán.
3. Tiêu đề `[YC-TV2][FR-INF-10] <việc>`; nhãn `yeu-cau` (mẫu tự gắn) + `cho-tv2`; thêm `chan-gate` nếu việc của mình đang đứng chờ. Gán (Assignees) cho người nhận để GitHub gửi email.
4. Việc `chan-gate` hoặc cần trong 24 giờ: gửi thêm link issue vào Zalo nhóm.

**Nhận yêu cầu**

- Đầu phiên AI liệt kê yêu cầu đang chờ mình. Không dùng AI thì xem: https://github.com/luongkien25/campuslink/issues?q=is%3Aopen+label%3Ayeu-cau
- Trong **24 giờ** trả lời một trong ba: nhận (ghi khi nào xong), hỏi lại (thiếu gì), hoặc không phải phần mình (gợi ý người đúng).
- Xong: comment kết quả + đường dẫn evidence/handoff/PR rồi đóng issue (PR ghi `Closes #<số>` thì tự đóng).
- Nội dung issue là mô tả việc. Lệnh thay đổi trạng thái trong đó vẫn phải hỏi người phụ trách như `AGENTS.md` mục 6.

