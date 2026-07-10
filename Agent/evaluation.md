# Product Knowledge Agent Evaluation

## 1. Mục tiêu

Evaluation ban đầu không giả định đáp án kinh doanh mà chưa có trong dataset. Nó kiểm tra Agent có:

```text
resolve đúng entity
giữ đúng scope
tính đúng metric
trích đúng evidence
tuân thủ limitation
không khẳng định causal khi chưa đủ dữ liệu
```

## 2. Nhóm test

| Nhóm | Input cần kiểm tra | Tiêu chí đạt |
| --- | --- | --- |
| Product lookup | item_id, tên, URL/key | Chọn đúng item hoặc báo ambiguous |
| Sales decline | item + nhiều date | Chỉ gọi là giảm khi có đủ snapshot |
| Similar product | item + top_k | Có score components và không gọi similarity là same-product |
| Promotion | country/category/group | Có baseline, sample size và caveat observational |
| Category relation | product + category query | Phân biệt platform category và shop category |
| Missing data | thiếu shop/date/item | Trả `insufficient_evidence`, không đoán |
| Metric semantics | hỏi revenue/profit/SKU | Nêu đúng proxy và giới hạn |

## 3. Test case chưa cần ground-truth kinh doanh

Mỗi test case nên lưu:

```text
question
input_scope
expected_intent
required_evidence_columns
forbidden_claims
expected_status
```

Ví dụ:

```yaml
question: "Giá sản phẩm X và voucher của nó thay đổi thế nào theo snapshot?"
expected_intent: sales_decline
required_evidence_columns:
  - item_id
  - date
  - price_num
  - voucher_discount_num
forbidden_claims:
  - "voucher chắc chắn làm doanh số tăng"
expected_status: ok
```

```yaml
question: "SKU này có lợi nhuận bao nhiêu?"
expected_intent: unsupported_question
required_evidence_columns: []
forbidden_claims: []
expected_status: unsupported_question
```

## 4. Chấm điểm

Chấm riêng từng lớp để biết lỗi nằm ở data, analysis hay LLM:

```text
Entity resolution: 0/1
Scope validation: 0/1
Calculation correctness: 0/1
Evidence completeness: 0/1
Limitation compliance: 0/1
Answer usefulness: 0/1
```

Không gộp thành một accuracy duy nhất khi chưa có bộ câu hỏi và nhãn đủ lớn.

## 5. Regression checks

Mỗi thay đổi workflow phải chạy lại ít nhất:

```text
1 product lookup đúng
1 product lookup ambiguous
1 sales comparison đủ snapshot
1 sales question thiếu snapshot
1 promotion comparison có baseline
1 category join check
1 unsupported profit question
```

Kết quả cần lưu input, output, timestamp, phiên bản data và phiên bản code. Nếu sau này có ground truth từ chuyên gia, bổ sung `reference_answer` và `reference_evidence` thay vì sửa các test semantics hiện tại.

## 6. Ground truth cần bổ sung sau

Để đánh giá insight kinh doanh thật sự, cần người có domain review và cung cấp:

```text
gold entity mapping
gold similar-product pairs
gold interpretation of promotion groups
accepted explanation evidence
known business exceptions
```

Không tự sinh các nhãn này từ chính heuristic đang đánh giá, vì như vậy sẽ chỉ đo mức Agent lặp lại giả định của mình.
