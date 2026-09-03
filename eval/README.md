# Eval V1 end-to-end

`questions.json` chứa đúng 60 case tiếng Việt, Bahasa Indonesia, không dấu và paraphrase. Mỗi case có ground truth `expected_intent`, `expected_action`; các case entity tiêu biểu còn khóa `expected_listing_key`.

Một run chỉ pass khi đồng thời đạt:

1. intent và `allow|clarify|abstain` đúng;
2. tool trajectory đúng `IntentSpec` và không có tool lỗi/rỗng ở case `allow`;
3. listing đã resolve khớp ground truth nếu case có khóa;
4. evidence metric/value khớp oracle tính độc lập từ processed artifact;
5. citation recall và precision đều bằng 1;
6. numeric answer vượt verifier;
7. verifier phát hiện mutation số giả `987654.321`.

Chạy offline ba lần:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 3
```

Chạy BGE-M3 local, không gửi dữ liệu ra ngoài:

```bash
GLADIATORS_ENABLE_BGE=1 PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 1
```

`--provider gemini` sẽ gửi question, structured request và evidence cần diễn giải tới Gemini. Chỉ sử dụng sau khi data owner duyệt phạm vi external transmission.


---

## Chỉ số dự đoán có chọn lọc (WP-B1)

Một hệ **được phép nói "không biết"** không thể chấm bằng một tỷ lệ pass duy
nhất. Cặp `abstention_precision/recall` cũ chỉ đếm `abstain`, nên `clarify` —
32% bộ đề chính và 52,5% của DR-40 — nằm ngoài toàn bộ phép đo từ chối: một câu
**trả lời được** mà hệ trả `clarify` không rơi vào chỉ số nào, nó biến mất.

### Từ vựng

```
refused(r)     := r.action ∈ {clarify, abstain}
answered(r)    := r.action == allow VÀ có evidence
answerable(c)  := c["answerable"] nếu có khoá đó
                  ngược lại: c["expected_action"] == "allow"
                  ngược lại nữa (expected_action = null): CHƯA GÁN NHÃN
correct(r)     := answered(r) và chấm được là đúng
```

Hành động của một case lấy theo **đa số phiếu qua các lần chạy**, không phải
`run == 1`. `action_stability_rate` báo tỷ lệ case cho cùng một `action` ở mọi
lần chạy — một hệ không ổn định về `action` là hệ mà mọi chỉ số khác đều mất nghĩa.

### Sáu chỉ số

| Chỉ số | Công thức |
| --- | --- |
| `coverage` | `answered ∧ answerable` / `answerable` |
| `risk` | `answered ∧ ¬correct` / `answered` (chỉ trên câu chấm được) |
| `over_refusal_rate` | `refused ∧ answerable` / `answerable` — **từ chối oan** |
| `over_answer_rate` | `answered ∧ ¬answerable` / `¬answerable` — **trả lời oan** |
| `refusal_precision` | `refused ∧ ¬answerable` / `refused` |
| `refusal_recall` | `refused ∧ ¬answerable` / `¬answerable` |

### ⚠️ Cảnh báo bắt buộc đọc kèm (B1-R2)

> **`over_refusal_rate` đo trên bộ tự viết LUÔN bằng 0.**
>
> Nhãn `answerable` được suy ra từ `expected_action`, mà `expected_action` được
> viết **cùng lúc** với bộ luật. Nên theo định nghĩa, không case nào vừa
> `expected_action = allow` vừa bị hệ từ chối mà không làm rơi
> `end_to_end_accuracy` trước.
>
> Con số `0` ở đây **không** có nghĩa "hệ không từ chối oan". Nó có nghĩa **bộ đề
> này không đo được điều đó**. Chỉ số chỉ có nghĩa trên bộ đề độc lập (WP-B3).

### Hai quy ước chống số giả

1. **Mẫu số rỗng ⇒ `null`, không phải `0.0`.** `questions_a19` và
   `questions_ambiguity` không có case answerable nào; báo `coverage = 0.0` ở đó
   sẽ đọc thành "hệ không phủ được gì" trong khi sự thật là không có gì để phủ.
   (`CLAUDE.md` §3.1 — điền 0 làm "không đo được" trông giống "đo được và bằng 0".)
2. **Case chưa gán nhãn bị loại khỏi mọi tập**, và số bị loại được báo ở
   `selective_unlabelled_cases`. DR-40 cố ý để `expected_action = null` ở 19/40
   case chưa có oracle người duyệt — gộp chúng vào nhóm không-answerable là bịa
   ra 19 nhãn.

### Chấm suite không có nhãn intent

DR-40 có `legacy_expected_intent = null` ở **cả 40 case**, nhưng 21 case có
`expected_action` + `allowed_rule_ids`. Harness chấm chúng theo **hành động và mã
rule** (`scoring_mode = "action_rule_only"`), là đúng hợp đồng mà suite đó khai.

Row không chấm được **không** vào mẫu số của `end_to_end_accuracy`; số bị loại
báo ở `unscoreable_rows`. Trước bản vá này, `case["expected_intent"]` ném
`KeyError`, bị nuốt thành `passed: false`, và harness in ra
`end_to_end_accuracy = 0.0` cho 120/120 row lỗi đọc suite — một con số **trông
như** phép đo.
