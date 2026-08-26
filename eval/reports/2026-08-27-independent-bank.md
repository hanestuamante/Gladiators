# WP-B3 / WP-B12 — bộ đề sinh từ dữ liệu, và con số từ chối oan

> **Ngày đo:** 27/08/2026 · **Commit:** `d133888` · `--provider offline`
> **Bộ đề:** `eval/independent/answerable_manual.json` — 44 câu, 36 nhóm diễn đạt
> **Sinh bởi:** `scripts/build_question_bank.py` (pandas thuần, không import `gladiators`)

---

## 1. Con số

| Chỉ số | Giá trị | Nghĩa |
| --- | ---: | --- |
| `coverage` | **0.579** | Trả lời được 57,9% câu mà **dữ liệu** trả lời được |
| **`over_refusal_rate`** | **0.421** | **Từ chối oan 42,1%** |
| `risk` | **0.0** | Trong số đã trả lời, **không câu nào sai** |
| `over_answer_rate` | **0.0** | **Không bao giờ** trả lời thứ dữ liệu không có |
| `refusal_precision` | 0.273 | Chỉ 27,3% lời từ chối là chính đáng |
| `refusal_recall` | **1.0** | Bắt được **100%** câu thật sự không trả lời được |
| `action_stability_rate` | 1.0 | Hành động ổn định qua các lần chạy |

**Đọc thành một câu:** hệ thống **an toàn nhưng quá thận trọng**. Nó không bao giờ
trả lời sai và không bao giờ trả lời thứ không có dữ liệu — nhưng nó từ chối oan
gần một nửa số câu mà chính dữ liệu của nó trả lời được.

Đây là con số mà `WP-B1 §B1.2` cảnh báo là **không thể đo trên bộ đề tự viết**:
ở đó nhãn `answerable` suy ra từ `expected_action`, nên `over_refusal_rate` luôn
bằng 0 theo định nghĩa.

---

## 2. Giới hạn — phải in kèm mọi lần trích dẫn con số trên

**Bộ đề này KHÔNG thoả `B3-R1`.** Spec đòi người soạn không đọc `src/gladiators/`.
Bộ đề này do một tác nhân **đã đọc toàn bộ codebase** sinh ra. Hệ quả:

1. `over_refusal_rate = 0.421` là **chặn dưới của thiên lệch**, không phải một
   phép đo sạch. Câu hỏi sinh từ cột và giá trị có thật trong dữ liệu, nhưng cách
   **diễn đạt** khó tránh khỏi ảnh hưởng của việc biết hệ nhận dạng thế nào.
   Một người ngoài diễn đạt tự nhiên hơn nhiều khả năng làm con số này **tăng**.
2. Nó **không thay thế** bộ đề do người ngoài soạn. Nó chỉ làm việc soạn bộ đó
   rẻ hơn: đáp án đã có sẵn, tái lập được, và khuôn dạng đã chuẩn.
3. 44 câu, dưới mức 60–100 mà spec yêu cầu.

Từng case mang cờ `author_read_source_code: true` để con số không bao giờ bị
trích dẫn như một phép đo độc lập.

---

## 3. Vì sao con số này quan trọng hơn 1.0 của bảy suite

Bảy bộ eval chính đều đạt `1.0`. Nhưng chúng được viết **cùng lúc với bộ luật**,
nên `1.0` ở đó chứng minh **luật viết tay nhất quán với chính nó** — đó là điểm
**hồi quy**, không phải điểm **năng lực**.

Bộ đề này soạn từ **dữ liệu**, nên nó hỏi được câu mà bộ luật chưa nghĩ tới. Và
nó cho thấy khoảng cách thật:

```
bảy suite tự viết   :  1.000
dữ liệu hỏi ngược   :  0.579 coverage · 0.421 từ chối oan
```

---

## 4. Từ chối oan nằm ở đâu

Các nhóm câu bị từ chối tập trung ở:

- câu hỏi **trung vị** giá và điểm đánh giá (`Giá trung vị tại … là bao nhiêu?`)
- câu hỏi đếm theo **ngày không phải snapshot mới nhất**
- câu hỏi đếm **thương hiệu phân biệt**
- câu hỏi đếm listing của **shop chính hãng** (cần join, hiện fail-closed khi
  critic tắt — xem WP-A1)

Đây đúng là các nhóm mà **WP-A5** (ba vòng lặp rẻ) và **WP-A13** (trả lời từng
phần) nhắm tới. Con số 0.421 là mốc nền để đo chúng.

---

## 5. Lệnh tái lập

```bash
# sinh lại bộ đề từ dữ liệu
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/build_question_bank.py

# đo
.venv/Scripts/python.exe scripts/run_evaluation.py \
  --suite eval/independent/answerable_manual.json --runs 1 --provider offline
```
