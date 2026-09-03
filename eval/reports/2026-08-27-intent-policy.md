# WP-A11 — chính sách trọng tài intent: P-A vs P-B

> **Ngày đo:** 27/08/2026 · **Model:** `deepseek-v4-flash`
> **Bộ đề:** `eval/independent/answerable_manual.json` — 44 câu (bộ đề độc lập B3,
> **không** phải bộ tự viết: ở đó `over_refusal_rate` luôn bằng 0 theo định nghĩa
> §B1.2, nên nó không phân biệt được hai chính sách)
> **Tái lập:** `PYTHONPATH=src .venv/Scripts/python.exe scripts/run_intent_policy_report.py --suite eval/independent/answerable_manual.json --provider deepseek`

---

## 1. Bảng nghiệm thu

| | P-A | P-B |
| --- | ---: | ---: |
| Độ phủ (coverage) | 0,4545 | 0,4545 |
| Rủi ro (risk) | 0 | 0 |
| Từ chối oan | 0,4737 | 0,4737 |
| Trả lời thứ dữ liệu không có | 0 | 0 |
| p50 độ trễ | 23,0 s | 18,3 s |
| p95 độ trễ | 50,2 s | 30,0 s |
| **Nhãn LLM được lấy** | **0** | **10 / 44** |

**Kết luận: giữ `P-A`.** A11-R3 đòi P-B phải **thắng**, không phải hoà — cần độ
phủ tăng **và** rủi ro không tăng **và** p95 trong ngân sách. Ở đây độ phủ
**không đổi**, nên điều kiện đầu đã trượt.

---

## 2. Kết quả thật sự đáng nói

P-B **có bắn**, và bắn không ít:

```
no_change              28   luật deterministic tìm được đường ⇒ P-B không can thiệp
llm_label_not_served    6   nhãn LLM có đăng ký nhưng KHÔNG thoả capability contract
deterministic_open     10   nhãn LLM được lấy
```

Mười lần nhãn của LLM thay thế nhãn deterministic, và **không một outcome nào
đổi**: cùng độ phủ, cùng rủi ro, cùng tỷ lệ từ chối oan. Đây là phép đo trực tiếp
cho tiền đề của §WP-A11 — *"LLM đóng góp bằng 0 vào intent cuối"* — và nó cho
thấy điều đó **không** chỉ do precedence chặn: kể cả khi nhãn LLM được cho qua,
các tầng phía sau vẫn cho ra cùng câu trả lời.

Sáu ca `llm_label_not_served` là điều kiện capability contract đang làm đúng việc
của nó. Đó chính là hàng rào ngăn P-B lặp lại lỗi đã đo trong spec: DeepSeek gán
*"Có bao nhiêu listing ở VN?"* thành `dataset_coverage`, mà hình dạng đã chứng
nhận của macro đó không sinh được một con số vô hướng.

---

## 3. Lần đo đầu tiên đo một thứ không chạy

Lần chạy đầu cho hai bảng số **giống hệt nhau** và `llm_label_taken = 0` cho cả
hai. Đọc thoáng thì đó là *"P-B vô hại"*. Sự thật là *"P-B chưa từng chạy"*.

`arbitrate` đọc nhãn LLM từ `parsed.intent`. Nhưng tới lúc nó chạy, **năm nhánh
precedence đã ghi `deterministic.intent` vào `parsed`** — nên bên trong hàm, hai
nhãn luôn bằng nhau và nhánh `no_change` bắn cho **mọi** câu. P-B là code chết từ
lúc được viết.

Tám test của WP-A11 đều xanh suốt thời gian đó, vì chúng gọi `arbitrate` **cô
lập**, với một `parsed` chưa bị precedence đụng vào. Đây đúng là bẫy *"xác minh
bằng hành vi, không bằng cấu trúc"*: một hàm có mặt trong code và một hàm thật sự
ảnh hưởng tới kết quả trông giống hệt nhau từ ngoài.

Thứ phát hiện ra nó là **telemetry `llm_label_taken`**. Không có khoá đó, hai
bảng giống nhau sẽ được đọc thành *"đã đo, P-B hoà"* và ghi thẳng vào báo cáo —
một kết luận đúng chữ, sai nghĩa.

Đã sửa: truyền `meta["llm_intent"]` (nhãn gốc, ghi lại **trước** mọi lần ghi đè)
vào `arbitrate`. Hai test mới đi qua `_parse` thật, và đã **xác nhận chúng đỏ
trên code cũ** trước khi tin chúng.

---

## 4. Độ trễ: cả hai chính sách đều vượt ngân sách

Ngân sách §A6: p50 ≤ 8 s · p95 ≤ 15 s.

| | P-A | P-B | Ngân sách |
| --- | ---: | ---: | ---: |
| p50 | 23,0 s | 18,3 s | 8 s ❌ |
| p95 | 50,2 s | 30,0 s | 15 s ❌ |

Đường có LLM parser vượt ngân sách **2–3 lần ở p95**. Con số 0,21 s trong
`2026-08-27-latency.md` là của đường **offline** — đó là cấu hình đang phát hành
(`GLADIATORS_ENABLE_LLM_PARSER` mặc định tắt), nên nó không mâu thuẫn; nhưng nó
cũng không nói gì về đường này.

P-B **không nhanh hơn P-A** theo bất kỳ nghĩa nào kiểm được: hai chính sách gọi
đúng cùng số lời gọi LLM, và khác biệt 23,0/18,3 đến từ độ biến động mạng trong
một lần chạy 44 câu. **Không** trích dẫn nó như một cải thiện.

---

## 5. Giới hạn

1. **Một lần chạy, một model, một ngày.** Không lặp lại nhiều lần, nên mọi khác
   biệt độ trễ dưới hàng chục giây là nhiễu.
2. **Bộ đề không thoả B3-R1** (người soạn đã đọc codebase) — cùng giới hạn với
   mọi con số đo trên `eval/independent/`.
3. `llm_telemetry` trong JSON rỗng: `FallbackLLMClient.telemetry()` không phơi
   ra telemetry của client con theo hình dạng script này đọc. Số lời gọi và tỷ lệ
   trúng cache của lần chạy này **không đo được** — ghi ra để không ai đọc `{}`
   thành "không có lời gọi nào".
4. Chưa chạy hai lệnh nghiệm thu trên `eval/questions.json` mà §A11 liệt kê;
   bảng bắt buộc của WP này đòi bộ đề **độc lập**, và đó là bảng ở §1.

---

## 6. Không đổi

- `DEFAULT_POLICY = "P-A"` giữ nguyên (A11-R3).
- `GLADIATORS_ENABLE_LLM_PARSER` **không** bật trong source (A11-R4); nó chỉ được
  bật bên trong script đo, và chỉ sống trong tiến trình đó.
- Năm nhánh precedence giữ nguyên văn và vẫn luôn chạy trước (A11-R2).
