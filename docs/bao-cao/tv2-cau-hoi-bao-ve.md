# Câu hỏi bảo vệ hạng mục 6 và 7 — TV2

## 1. Vì sao nhóm dùng Heat AutoScalingGroup thay cho Senlin?

Heat đã quản lý VM, cấu hình khởi động và tài nguyên của ứng dụng trong cùng stack.
Nhóm dùng lại Heat để giữ một app cố định ở AZ-A và từ một đến hai app ở AZ-B. VM mới qua kiểm tra HTTP/Redis trước khi Heat thêm member vào Octavia.
Aodh gọi hai Heat ScalingPolicy theo ngưỡng CPU. Cách này đáp ứng yêu cầu của lab với các dịch vụ đang dùng và tránh bổ sung một dịch vụ quản lý cụm riêng.
[Nguồn: SRS FR-INF-11 và hợp đồng bàn giao H4](../handoffs/H4-heat-lb-scaling.md).

## 2. Vì sao phải vá Aodh và gate v2.2 làm gì?

Khi tập VM đổi giữa hai bucket, lấy hiệu của trung bình các counter CPU có thể cho rate sai, kể cả rate âm. ADR-12 đổi thứ tự thành tính rate từng VM trước khi lấy trung bình.
Gate v2.2 đọc được timestamp dạng chuỗi ISO và datetime của Gnocchi, chỉ xét bucket đã đóng và đủ độ phủ. Nếu dữ liệu không đạt hoặc cửa sổ phục hồi còn lẫn tín hiệu, alarm giữ trạng thái thiếu dữ liệu đến khi đủ điều kiện.
Ngưỡng 60%/25% giữ nguyên. Lượt tối 21/11 ghi nhận Aodh tự gọi Heat ở cả hai chiều.
[Nguồn: ADR-12](../decisions/ADR-12-aodh-rate-tung-vm.md) · [PR #81](https://github.com/luongkien25/campuslink/pull/81) · [Evidence lượt tối](https://github.com/luongkien25/campuslink/issues/77#issuecomment-7065510182).

## 3. Vì sao lượt dùng slug cũ không vượt 60%, và làm gì nếu demo trực tiếp không kích alarm?

Lượt dùng `tv4fix1` với khoảng 124 nghìn visit đẩy CPU DB VM 1 vCPU lên 99,5–99,7%, trong khi CPU nhóm app đạt đỉnh 27,35%.
Lượt dùng slug mới đạt đỉnh 62,48% và tự chạy 2→3→2. Hai lượt có điều kiện dữ liệu khác nhau. Lượt tự động còn thiếu mốc request đầu tiên tới VM mới.
Nếu demo trực tiếp chưa vượt ngưỡng, giữ cấu hình và chiếu evidence đã thu ngày 21/11, ghi rõ đó là kết quả của lượt trước.
[Nguồn: #77](https://github.com/luongkien25/campuslink/issues/77#issuecomment-7065622142) · [Đối chiếu điều kiện tải ở #90](https://github.com/luongkien25/campuslink/issues/90#issuecomment-7065064776).
