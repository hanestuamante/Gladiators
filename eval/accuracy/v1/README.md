# Benchmark accuracy v1 — cách đọc số, và giới hạn

## Chạy

```bash
python eval/accuracy/v1/oracle.py --verify          # oracle tái tính khớp fixture
PYTHONPATH=src python scripts/run_accuracy_benchmark.py --split dev --runs 3
PYTHONPATH=src python scripts/run_accuracy_benchmark.py --split holdout --runs 3   # chỉ ở release evaluation
python -m pytest tests/test_accuracy_benchmark_contract.py tests/test_accuracy_scorer_mutations.py -q
```

Report ghi vào `eval/reports/accuracy/accuracy_v1__{split}__{provider}__{commit}__{timestamp}.json`
— không bao giờ ghi đè.

## Đọc metric thế nào

Mỗi tỷ lệ đi kèm tử số/mẫu số và Wilson 95% CI. **Không có headline đơn lẻ**;
nếu buộc phải chọn một, dùng `strict_e2e_accuracy` và luôn đặt cạnh
`correct_answer_coverage`, `answer_risk`, `over_refusal_rate`, `over_answer_rate`.

| Metric | Nghĩa |
| --- | --- |
| `strict_e2e_accuracy` | strict-pass trên TOÀN BỘ case (mọi lớp) |
| `correct_answer_coverage` | answerable được trả lời **đúng hoàn toàn** / mọi answerable |
| `answerable_coverage` | answerable có trả lời (đúng hay sai) / mọi answerable |
| `answer_risk` | trong số ĐÃ trả lời, bao nhiêu sai |
| `over_refusal_rate` | answerable bị từ chối/hỏi lại oan |
| `over_answer_rate` | unanswerable bị trả lời |
| `refusal_reason_accuracy` | từ chối đúng NHÓM lý do, không chỉ đúng action |
| `clarification_precision` | clarify hỏi ĐÚNG slot thiếu |
| `clarification_recovery_rate` | sau follow-up, trả đúng oracle |

Strict-pass của một case allow đòi **đồng thời**: đúng action, đủ mọi expected
fact (đúng metric-key theo map ngữ nghĩa — *metric khác nhưng trùng số là
fail*), đúng value/tolerance khai theo từng metric, đúng country/date scope,
con số **hiển thị trong câu trả lời cuối** và evidence được trích dẫn, verifier
pass, không crash. Hoà ở đỉnh phải được nêu là không-duy-nhất. Giá trị trong
`forbidden_values` (ô giữ chỗ 9.999.999/999.999.999) xuất hiện là fail.

## So với suite regression

Bảy suite regression đạt 1.0 đo tính **nhất quán nội bộ** của luật viết tay.
Benchmark này đo **đúng/sai so với oracle pandas độc lập** — hai con số trả lời
hai câu hỏi khác nhau và không thay thế nhau. Đặc biệt: `risk = 0` trên bộ
regression KHÔNG suy ra câu trả lời đúng — baseline đầu của benchmark này đo
được `answer_risk` 18–25% trên các case đã trả lời.

## Giới hạn — đọc trước khi trích số

1. **`provisional_contaminated`**: tác giả benchmark đã đọc và thi công runtime
   trong cùng phiên. Câu soạn thuần từ dữ liệu, oracle pandas độc lập, nhưng
   thiên lệch chọn-câu không loại trừ được. Đây KHÔNG phải holdout độc lập;
   holdout sạch cần người soạn chưa từng đọc implementation (xem
   `review_packet.md`).
2. **Annotation bằng 2 sub-agent cách ly** (cơ chế §5 của đề bài), kappa 1.0 —
   đồng thuận giữa hai AI cùng họ mô hình là bằng chứng yếu hơn hai người thật.
3. **5 case trùng suite regression** — khai ở `manifest.regression_collisions`;
   điểm của chúng không phải bằng chứng độc lập.
4. **`offline_deterministic` không đo model accuracy** — nó đo pipeline
   deterministic. Đường provider thật là run riêng (`--provider <name>`), chưa
   đo: `not_measured`.
5. Đây là **data-grounded synthetic benchmark** — không phải mẫu đại diện
   production traffic (không có log người dùng thật).
