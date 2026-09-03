# Review packet — benchmark accuracy v1

Gói này tồn tại để hai người duyệt ĐỘC LẬP (chưa từng đọc `src/gladiators`)
hoàn tất phần việc mà phiên tạo benchmark không thể tự làm sạch.

## Trạng thái trung thực

- `status: provisional_contaminated` — tác giả benchmark là agent đã đọc và
  thi công runtime trong cùng phiên. Câu hỏi soạn thuần từ dữ liệu và oracle
  tính bằng pandas độc lập, nhưng thiên lệch chọn-câu-theo-hiểu-biết-về-hệ
  không thể loại trừ. **Không được gọi đây là holdout độc lập.**
- Annotation: HAI sub-agent cách ly (chỉ đọc câu hỏi + CSV; cấm đọc source) đã
  gán độc lập — agreement 100/100, Cohen's kappa 1.0; giá trị khớp oracle
  53/53 và 50/53 (3 lệch là trình bày delta-thay-vì-start, xem manifest).
  Đồng thuận hoàn hảo giữa hai AI cùng họ mô hình là bằng chứng YẾU hơn hai
  người thật — vì vậy packet này vẫn cần người.
- 5 case trùng nguyên văn suite regression, đã khai trong manifest
  (`regression_collisions`) — không xoá, người đọc điểm tự trừ hao.

## Việc cần người duyệt làm

1. Đọc `annotation_guide.md`, rồi gán lại độc lập 100 câu trong
   `dev.json`/`holdout.json` (che các trường expected_* khi gán).
2. So với `annotations_A.json`/`annotations_B.json`; ghi kappa người-vs-agent.
3. Xử các ca phán đoán nêu dưới; mọi thay đổi nhãn ⇒ version mới + changelog
   (không sửa âm thầm — hash đã seal trong manifest).
4. Ký tên + ngày vào bảng cuối file này.

## Các phán đoán cần người xác nhận nhất

| Case | Phán đoán hiện tại | Câu hỏi cho người duyệt |
| --- | --- | --- |
| acc-v1-0045 (giá cao nhất ID) | chấp nhận abstain/clarify HOẶC allow 1.135.000; CẤM 999.999.999 | các dòng GIVEAWAY giá toàn-số-9 có đúng là ô giữ chỗ? |
| acc-v1-0043/0044 (nhiều ảnh nhất) | hoà 76/64 dòng ⇒ answer phải nêu không-duy-nhất | ngưỡng chấp nhận cách diễn đạt hoà? |
| acc-v1-0069/0070 (có voucher) | mơ hồ THẬT (577 vs 419; 0 vs 210) | đồng ý hai khái niệm voucher? |
| acc-v1-0076 (trung bình theo nhóm) | clarify (thiếu chiều nhóm) | hay chấp nhận abstain vì "mean chưa định nghĩa"? |
| acc-v1-0080 (Doanh số thay đổi thế nào?) | clarify slot country | hay chấp nhận abstain entity? |
| median_rating (0027/0028) | oracle GỘP cả rating=0 (chưa được đánh giá) | có nên loại dòng chưa đánh giá khỏi trung vị? (annotator A nêu nghi vấn này) |

## Chữ ký

| Người duyệt | Vai trò | Ngày | Kết luận |
| --- | --- | --- | --- |
| *(trống — agent không được điền)* | | | |
| *(trống — agent không được điền)* | | | |
