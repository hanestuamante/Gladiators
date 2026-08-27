# WP-B5 — đối chứng "sao không để LLM tự viết SQL?"

> **Ngày đo:** 27/08/2026 · **Model:** `deepseek-v4-flash` (`DeepSeekLLMClient`)
> **Bộ đề:** `eval/independent/answerable_manual.json` — 44 câu, oracle pandas
> **Cho thử lại khi lỗi cú pháp:** 1 lần, kèm thông báo lỗi
> **Tái lập:** `PYTHONPATH=src .venv/Scripts/python.exe scripts/run_sql_baseline.py --suite eval/independent/answerable_manual.json --provider deepseek`

---

## 1. Bảng đối chứng

Cùng 44 câu, **cùng một oracle** cho cả hai phía (B5-R2).

| | Baseline "LLM viết SQL" | Hệ Gladiators |
| --- | ---: | ---: |
| Trả lời **đúng** số | 15,9 % (7) | **45,5 %** (20) |
| **Trả lời SAI mà KHÔNG BÁO** | **65,9 %** (29) | **0 %** (0) |
| Từ chối (nói rõ không làm được) | 4,5 % (2) | 54,5 % (24) |
| SQL hợp lệ bị guard chặn | 4,5 % (2) | — |
| Model trả rỗng | 9,1 % (4) | — |
| Lỗi thật khi chạy | 0 % | 0 % |
| Thời gian trung vị một câu | 14,7 s | **0,091 s** |

**Ô ăn tiền là dòng thứ hai.** 29/44 câu, baseline trả về một con số **sai**, ở
định dạng giống hệt một con số đúng, không kèm bất kỳ tín hiệu nào. Người đọc
không có cách nào biết. Hệ Gladiators trả 0 câu như vậy — không phải vì nó thông
minh hơn, mà vì mọi con số phải qua gate, alignment và verifier trước khi hiển thị.

---

## 2. Điều tôi đã dự đoán sai, và nói ra

Ghi chú trong script viết trước khi đo: *"Baseline nhanh hơn và trả lời nhiều câu
hơn là kết quả DỰ KIẾN"*. Đo xong thì **chỉ nửa sau đúng**:

- Baseline **trả lời** nhiều hơn: 86,4 % số câu cho ra một con số (38/44), so với
  45,5 % của Gladiators. Đúng như dự kiến.
- Baseline **không nhanh hơn**: 14,7 s so với 0,091 s — chậm hơn **161 lần**. Nó
  gọi một model reasoner qua mạng cho từng câu; Gladiators biên dịch một kế hoạch
  đã kiểm rồi chạy DuckDB cục bộ.
- Baseline **không đúng nhiều hơn**: 15,9 % so với 45,5 %.

Nói ra cả ba làm luận điểm mạnh hơn, không yếu đi (B5-R3). Nếu chỉ nêu ô "sai mà
không báo" mà giấu việc baseline trả lời nhiều hơn, người đọc có quyền nghi ngờ
toàn bộ bảng.

---

## 3. Baseline sai ở đâu — ba nhóm

Đọc SQL sinh ra thì gần như toàn bộ 29 câu sai rơi vào ba nhóm, và cả ba đều là
**đoán một thứ chưa bao giờ được cho xem**:

```sql
-- 1. Đoán hoa/thường của giá trị
WHERE country_code = 'VN'          -- dữ liệu lưu 'vn'

-- 2. Đoán năm
WHERE date = '2024-07-03'          -- dataset là 2026-07-03
WHERE date = '2021-07-03'          -- cùng model, cùng bộ đề, năm khác

-- 3. Đoán định dạng ngày
WHERE date LIKE '%-07-03' OR date LIKE '03/07/%' OR date = '03/07'
```

Cả ba đều trả về `COUNT(*) = 0`, và `0` là một con số hợp lệ. Không lớp nào trong
kiến trúc "LLM viết SQL" hỏi *"kết quả rỗng này là câu trả lời hay là một phép lọc
hỏng?"* — đó chính là câu hỏi `INV-EMPTY-RESULT-IS-VALID` và vòng dò giá trị
(WP-A5.1) tồn tại để trả lời.

Đây **không** phải lỗi của model. Nó được đưa lược đồ thô — tên bảng, tên cột,
kiểu — và không được đưa giá trị mẫu. Một hệ text-to-SQL nghiêm túc sẽ thêm bước
schema linking, và bước đó chính là **catalog ngữ nghĩa** của Gladiators dưới một
cái tên khác. Đó là toàn bộ luận điểm: phần "phức tạp" không phải trang trí, nó
là phần thay thế cho việc đoán.

---

## 4. Đã làm gì để đối chứng công bằng

Luật 1 của §B5: *một đối chứng bị dìm là một đối chứng vô giá trị*. Bốn chỗ phải
sửa **có lợi cho baseline** trước khi con số ở §1 đáng tin:

| Vấn đề ở lần đo đầu | Đã sửa |
| --- | --- |
| Prompt dùng đường `_chat` của production, có system prompt *"Bạn là lớp diễn giải analytics… không tự thêm số"* | Đổi sang system prompt đúng vai: *"expert DuckDB SQL writer"* |
| `max_tokens=1000` cố định trong production ⇒ model reasoner tiêu hết vào phần nghĩ, trả **rỗng cho 100 %** prompt có lược đồ đầy đủ | Nâng lên 4000 cho script đo |
| Kiểu cột in ra `unknown` cho cả 219 cột (`TableColumnSpec.physical_type` là `None`) | Đọc dtype thật từ chính file CSV |
| 6 ca "crash" thực ra là 4 ca model trả rỗng + 2 ca guard của **hệ này** chặn SQL read-only hợp lệ (`LAG`, `REGR_SLOPE`) | Tách thành ba cột riêng |

Cái **không** được nới: SQL vẫn phải qua `assert_read_only_sql` và vẫn chạy trong
executor đã khoá cấu hình (B5-R2), và script không chạm `/ask` hay `AgentRuntime`
(B5-R1).

Hai ca `blocked_by_readonly_guard` **không biết** đúng hay sai — chúng chưa từng
chạy. Chúng không được tính vào cột nào có lợi cho bên nào.

---

## 5. Giới hạn phải đọc kèm

1. **Bộ đề không thoả B3-R1** (người soạn đã đọc codebase) — cùng giới hạn với
   mọi con số đo trên `eval/independent/`.
2. **Một model, một ngày, một lần chạy.** `deepseek-v4-flash`, 27/08/2026, không
   lặp lại nhiều lần. Một đối chứng không tái lập được là một giai thoại
   (B5-R4) — lệnh tái lập ở đầu file, và `rows[]` trong JSON giữ nguyên từng câu
   SQL đã sinh.
3. **Baseline không được cho giá trị mẫu**, có chủ đích: §B5 nói lược đồ **thô**.
   Thêm giá trị mẫu là bắt đầu dựng lại catalog, tức đo lại chính Gladiators dưới
   một cái tên khác. Hệ quả — baseline đoán `'VN'` thay vì `'vn'` — được ghi ở §3
   thay vì giấu đi.
4. Cột Gladiators đo `--provider offline`; nó không gọi mạng theo thiết kế, nên so
   thời gian giữa hai cột là so hai kiến trúc, không phải so hai model.
