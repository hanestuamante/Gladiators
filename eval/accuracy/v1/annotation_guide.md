# Hướng dẫn annotation — benchmark accuracy v1

Người/agent gán nhãn **chỉ** được dựa vào: (1) dữ liệu trong `data/processed/*.csv`,
(2) ngữ nghĩa câu hỏi. **Không** dựa vào việc hệ thống hiện tại trả lời được
hay không — nhãn mô tả *dữ liệu có thể trả lời gì*, không mô tả *hệ đang làm gì*.

## Nhãn `answerability`

| Nhãn | Điều kiện | Ví dụ |
| --- | --- | --- |
| `directly_answerable` | Câu đủ scope (thị trường/ngày xác định hoặc suy được duy nhất), và dữ liệu chứa cột/grain cần thiết | "Có bao nhiêu listing tại VN ngày 03/07?" |
| `needs_clarification` | Mơ hồ THẬT: hai cách hiểu hợp lý cho **hai đáp án khác nhau**, hoặc thiếu scope bắt buộc (thiếu thị trường khi hai thị trường cho số khác nhau), hoặc entity khớp nhiều bản ghi | "Có bao nhiêu listing có voucher?" (hai khái niệm voucher cho 577 vs 419 ở VN) |
| `unanswerable` | Dữ liệu không có cột/grain/phạm vi để trả lời, hoặc tiền đề câu hỏi sai so với dữ liệu | "Lợi nhuận của shop X?" (không có cột chi phí/lợi nhuận) |

Quy tắc chặn thiên lệch: **không** biến câu khó thành `needs_clarification` hay
`unanswerable` chỉ vì khó tính. Nếu pandas 5 dòng tính được một đáp án xác định
duy nhất thì câu đó là `directly_answerable`.

## Expected facts

- Mỗi fact khai đủ: `metric`, `value`, `value_type`, `unit`, `country`,
  `date_start/date_end`, `grain`, `filters`, `tolerance`.
- Đếm listing: `drop_duplicates("product_listing_key")` trong một ngày.
- Cực trị có **hoà** (nhiều dòng cùng đạt đỉnh): không được khai một cái tên
  duy nhất làm đáp án; khai giá trị đỉnh + `tie_count`, và chấp nhận câu trả
  lời nêu-hoà hoặc từ chối-vì-hoà.
- Giá 9 999 999 / 999 999 999 nằm trên dòng tiêu đề GIVEAWAY/FREE GIFT — chúng
  là ô giữ chỗ, không phải mức giá; một câu hỏi cực trị đụng chúng phải khai
  `forbidden_values` cho giá trị thô.
- `tolerance`: integer đếm = exact; decimal khai `absolute` theo từng metric
  (giá: 0.5 đơn vị tiền; rating: 0.005; tỷ lệ %: 0.05). Không dùng một ngưỡng
  chung.

## Clarify

Khai `expected_clarification_slots` — hệ phải hỏi ĐÚNG chỗ thiếu, không hỏi
chung chung. Nếu có follow-up trong `turns`, lượt sau khi bổ sung thông tin
phải trả đúng oracle (đo `clarification_recovery`).

## Refusal

Khai `expected_refusal_reason_class` theo nhóm nguyên nhân:
`missing_field` · `missing_grain` · `forecast_unsupported` · `cross_currency` ·
`date_out_of_range` · `false_premise` · `external_data`. Từ chối đúng action
nhưng SAI nhóm nguyên nhân không được điểm trọn (đo riêng `refusal_reason_accuracy`).

## Quy trình hai lượt

1. Hai annotator độc lập (không chia sẻ reasoning/kết quả) gán:
   answerability, expected_action, scope, expected_value, reason.
2. Adjudicator thứ ba xử bất đồng; mọi quyết định ghi vào review packet.
3. Manifest ghi agreement trước adjudication (Cohen's kappa cho nhãn phân loại,
   tỷ lệ khớp exact/tolerance cho expected value).
4. Sau khi seal (hash trong manifest): không sửa nhãn để hệ pass. Lỗi
   annotation thật ⇒ tạo version mới + changelog, không sửa âm thầm.
