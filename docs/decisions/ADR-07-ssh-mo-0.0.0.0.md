# ADR-07: Mở SSH (22) trên host A cho 0.0.0.0/0 trong giai đoạn phát triển

- Ngày: 22/10/2026 · Người quyết: TV1 (Kenn) · Trạng thái: chấp nhận, **tạm thời**
- Cập nhật 02/11/2026: giảng viên lùi lịch (SRS C-09), mốc thu SSH dời từ 06/11 sang đầu freeze 19/11.

## Bối cảnh

Ban đầu SG `campus-ingress-admin` chỉ mở 22 cho IP /32 của từng người. IP nhà và wifi trường của thành viên đổi thường xuyên, nên mỗi lần đổi phải chờ TV1 sửa SG, làm chậm cả nhóm.

## Quyết định

Từ G0 đến trước freeze (19/11), mở TCP 22 trên A cho 0.0.0.0/0, bù lại bằng:

1. Chỉ đăng nhập bằng key: `sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin'` phải ra `passwordauthentication no` và `permitrootlogin no` hoặc `without-password`.
2. `fail2ban` bật jail `sshd` (`sudo apt-get install -y fail2ban`; kiểm `sudo fail2ban-client status sshd`).
3. Mỗi người một user Linux riêng, không sudo (`ops/add-member.sh`); không dùng chung `.pem`.
4. B vẫn không có public IPv4; app/DB VM vẫn không có floating IP.

## Hệ quả

- Log sẽ có nhiều lượt dò SSH từ bot; bình thường nếu chỉ thấy "Invalid user"/"Connection closed".
- SRS (FR-INF-05, mục 4.4) và checklist G0 mục 2.5 đã ghi ngoại lệ này. **Trước freeze phải thu về /32** (hoặc tắt hẳn 22 lúc demo) và chụp lại SG làm evidence; ghi lý do trong báo cáo.
- Lộ private key của một thành viên: xóa key đó khỏi `~tvX/.ssh/authorized_keys` ngay.
