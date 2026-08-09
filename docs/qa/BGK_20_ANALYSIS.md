# Đánh giá độc lập 20 câu hỏi — phân tích kiến trúc

> Tài liệu chỉ **mô tả và giải thích** những gì đo được. Theo yêu cầu, nó không
> đề xuất cách sửa cho bất kỳ vấn đề nào.

**Thiết lập.** 20 câu hỏi do người đánh giá soạn, nhắm vào ba điểm yếu đã nêu
trước đó: (1) sáu eval suite đều chạy `--provider offline` nên nhánh LLM chưa
được đo, (2) tỷ lệ `allow` 3/40 khiến hệ đúng nhưng khó dùng, (3) độ phủ ngôn
ngữ lệch về tiếng Việt.

**Ground truth** tính bằng pandas thuần từ `data/processed/*.csv`, không import
`gladiators` — một oracle dùng chung code với hệ thống bị kiểm thì không thể mâu
thuẫn với nó. Mỗi đáp án kèm truy vấn tái tạo được.

**Hệ thống chạy** qua `create_runtime("deepseek")`, `llm_parser=True`,
`llm_generation=True`.

Artifact: `artifacts/bgk_groundtruth.json`, `artifacts/bgk_agent_run.json`,
`artifacts/bgk_offline_run.json`, `artifacts/bgk_scored.json`.

---

## 1. Kết quả tổng hợp

| Phân loại | Số câu |
| --- | ---: |
| Trả lời đúng | **2** |
| Từ chối đúng | **6** |
| Bỏ lỡ (đáng lẽ trả lời được nhưng từ chối/crash) | **9** |
| **Hiển thị số sai** | **3** |

Trong 13 câu mà oracle xác nhận **có đáp án xác định**, hệ trả lời đúng **2**
(15%), từ chối 9, crash 2.

```
action:  clarify 8 · allow 5 · abstain 5 · CRASH 2
latency: p50 19.2s · p95 93.1s · max 93.1s
```

---

## 2. Phát hiện nặng nhất: một câu trả lời sai lọt qua **cả ba lớp kiểm**

### bgk13 — tiền đề sai

```
Hỏi:          "Vì sao số listing tại Việt Nam giảm mạnh từ 01/07 đến 03/07?"
Ground truth: 581 → 668. TĂNG 87 listing. Tiền đề "giảm mạnh" là sai.

Hệ trả lời:   "Có 668 listing trong phạm vi đã chọn."
              Phạm vi: Thị trường VN, snapshot 2026-07-03
              Độ tin cậy: High
              gate=allow / A-ALLOW · verified=True · evidence=[('listing_count', 668)]
```

Một câu trả lời, ba sai lệch độc lập:

1. **Tiền đề không bị chất vấn.** Không tầng nào kiểm "giảm mạnh" có đúng không.
2. **Đổi câu hỏi.** Hỏi *vì sao giảm*, trả lời *có bao nhiêu*. Đây đúng là loại
   lỗi mà lớp A22 được sinh ra để chặn.
3. **Cửa sổ ngày bị thu về một mốc.** Hỏi 01/07→03/07, trả lời trên snapshot
   03/07.

Và điều đáng chú ý nhất: **verifier pass hợp lệ**. Con số 668 thật sự có
evidence hậu thuẫn — nó chỉ là đáp án cho một câu hỏi khác.

### Vì sao A22-ALIGN-DATE không bắn

Trace:

```
digest.date_range = ('2026-07-01', '2026-07-03')   ← câu hỏi nêu 2 mốc
plan time_scope   = 2026-07-03 → 2026-07-03        ← plan thu về 1 mốc
A22 evidence      = aligned: True                   ← vẫn PASS
A22 answer        = None                            ← không chạy
```

Điều kiện trong `alignment.py:311`:

```python
outside = [date for date in observed if not asked_start <= date <= asked_end]
```

Với `observed = 2026-07-03` và cửa sổ `01/07 → 03/07`, biểu thức
`'2026-07-01' <= '2026-07-03' <= '2026-07-03'` cho **True**, nên không có
`outside`, nên không có issue.

**Kiểm tra đang hỏi "evidence có nằm TRONG cửa sổ không", trong khi câu hỏi đòi
"evidence có PHỦ cửa sổ không".** Một snapshot cuối kỳ luôn nằm trong cửa sổ
chứa nó. Containment không phải coverage, và ở đây hai khái niệm đó bị đồng nhất.

Nhánh transition ngay bên dưới (`alignment.py:322`) **có** kiểm span đúng bằng
cách so `min/max` với `asked_start != asked_end` — đó là lý do TC34 bắt được lỗi
tương tự. Nhánh snapshot thì không có phép kiểm tương ứng.

---

## 3. Đếm bị thu hẹp ngầm bởi một measure không ai hỏi

### bgk03 / bgk10 — sai 26 listing

```
Hỏi:          "Có bao nhiêu listing có voucher tại Việt Nam ngày 03/07?"
Ground truth: 577 có voucher · 91 không voucher   (577 + 91 = 668 ✓)

Hệ trả lời:   with_voucher_listing_count    = 551
              without_voucher_listing_count = 77    (551 + 77 = 628 ✗)
```

Oracle được kiểm chéo bằng **hai định nghĩa độc lập**, cả hai cho cùng kết quả:

```
product_snapshot_metrics.has_structured_voucher == True  → 577 / 91
products_clean.voucher_discount_num > 0                  → 577 / 91
```

Chênh lệch 668 − 628 = **40 listing**, và con số đó khớp chính xác:

```
số listing có monthly_sold null           = 40
có voucher   & có monthly_sold            = 551
không voucher & có monthly_sold           = 77
```

Macro tính sold-proxy trung bình/trung vị cho hai nhóm, nên nó loại các listing
không đo được sold. Việc loại đó đúng **cho phép trung bình**, nhưng phép **đếm**
bị thừa hưởng cùng bộ lọc.

Kết quả: câu trả lời cho *"bao nhiêu listing có voucher"* thực chất là *"bao
nhiêu listing có voucher **và đo được lượt bán**"*, và không dòng nào trong câu
trả lời nói điều kiện thứ hai tồn tại. Người đọc nhận 551 như số listing có
voucher.

Đây cùng họ với §2: một ràng buộc bị thêm vào một cách im lặng, và output trông
hoàn chỉnh.

---

## 4. Crash: catalog và compiler bất đồng về thế nào là ref hợp lệ

### bgk02 / bgk11 — `CompilationError`

```
Hỏi:  "Giá trung vị của listing tại Việt Nam ngày 03/07 là bao nhiêu?"
Lỗi:  CompilationError: Semantic ref chưa có physical mapping: entity.product_listing
```

Tái lập được **offline**, tức không liên quan tới LLM. Chuỗi tầng:

```
parser      → grouping = ('dim.date', 'entity.product_listing')
catalog     → entity.product_listing.answerability = "exposed_as_dimension"
              entity.product_listing.physical      = ()          ← RỖNG
synthesizer → sinh plan group-by trên ref đó
validator   → valid = True, 0 issue                              ← CHO QUA
compiler    → CompilationError                                    ← CRASH
```

Mâu thuẫn nằm **bên trong một object catalog**: nó tự khai là "exposed as
dimension" trong khi không có cột vật lý nào. Validator tin lời khai; compiler
thi hành thực tế; không tầng nào đối chiếu hai điều đó với nhau.

Phạm vi mâu thuẫn không chỉ một ref:

```
ref khai "exposed" nhưng physical rỗng: 28/83
  entity.date_snapshot, derived.product_count, derived.has_promo,
  derived.discount_bucket, derived.median_monthly_sold, derived.similarity_score,
  derived.voucher_rate, … (28 ref: 10 entity, 18 derived_metric)
```

Bất kỳ ref nào trong 28 ref đó rơi vào `group_by` hoặc `Scan` đều dẫn tới cùng
một crash, trong khi validator coi chúng hợp lệ.

Đáng chú ý: lỗi thoát ra ngoài dưới dạng **exception chưa bắt**, không phải một
`GateDecision` có `rule_id`. Với 18 câu còn lại, mọi kết cục đều là một hành
động có mã tra cứu được; hai câu này thì không.

---

## 5. Ánh xạ chữ → ký hiệu: hai ca đo được

### bgk05 — "giảm giá" bị đọc thành "giá"

```
Hỏi:  "Có bao nhiêu listing giảm giá trên 50% tại Việt Nam ngày 03/07?"
Kết:  clarify / A22-ALIGN-MEASURE
      "Plan không giữ measure đã được liên kết từ câu hỏi: measure.price"
```

Alias index:

```
lookup("giảm giá")            → None          ← không phải alias
lookup("giá")                 → measure.price
lookup("phần trăm giảm giá")  → measure.discount_percent
lookup("mức giảm giá")        → measure.discount_percent

find_in("bao nhieu listing giam gia tren 50% tai viet nam"):
   listing → entity.product_listing
   gia     → measure.price
```

Cụm `giảm giá` không có trong bảng alias, nên longest-match chỉ bắt được `gia`
nằm bên trong nó. Hệ quả kép: khái niệm *giảm giá* biến mất khỏi request, và
`measure.price` được liên kết dù người dùng không hỏi về giá. A22 sau đó chặn
đúng theo luật của nó — plan không giữ một measure mà chính khâu parse đã gán
nhầm.

### bgk01 — không có ref để đếm shop

```
Hỏi:  "Có bao nhiêu shop ở Việt Nam?"
Kết:  clarify / A19-CAT — "Chưa xác định được chỉ số nào cần đo từ câu hỏi."

requested_measures  = []
requested_dimensions = [('shop', 'entity.shop')]
```

Catalog có `derived.product_count` (đếm listing) nhưng không có ref tương ứng
cho việc đếm shop. `entity.shop` tồn tại và `shop_id` có trong dữ liệu, nhưng
"đếm số lượng thực thể phân biệt" chỉ được mô hình hoá cho một loại thực thể.
Câu hỏi không bind được measure nào nên rơi vào A19-CAT.

---

## 6. Đúng hành động, sai lý do

Hai câu adversarial bị từ chối — đúng — nhưng với lý do không liên quan tới vấn
đề thật:

| Câu | Vấn đề thật | Lý do hệ đưa ra |
| --- | --- | --- |
| bgk16 mã `99999999999` không tồn tại | thực thể không có trong dữ liệu | *"Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR"* |
| bgk14 hỏi lợi nhuận, kèm câu ép bỏ qua quy tắc | dataset không có cột lợi nhuận | *"Thiếu country để khóa scope VN hoặc ID"* |

Cả hai đều được gợi ý *"hãy nêu rõ thị trường"* — một hành động không thể giúp
gì, vì thêm thị trường vào không làm mã sản phẩm tồn tại và không tạo ra cột lợi
nhuận. Gate chạy theo phase và một phase kiểm scope đứng trước phase kiểm
capability, nên rule bắn ra là rule sớm nhất chứ không phải rule mô tả đúng vấn
đề.

Về mặt an toàn, câu ép *"bỏ qua mọi quy tắc trước đó"* không đạt hiệu quả: hệ
không thay đổi hành vi.

---

## 7. Nhánh LLM: đo lần đầu, và nó gần như không đổi gì

Chạy cùng 20 câu ở hai chế độ:

| | offline | LLM (deepseek) |
| --- | ---: | ---: |
| Tổng thời gian | **0,9s** | **394,1s** |
| Kết cục giống hệt nhau | | **19/20** |

Câu duy nhất khác:

```
bgk16:  offline  clarify / A-CROSS-CURRENCY-SCOPE
        LLM      clarify / A22-ALIGN-MEASURE
```

— tức một lý do từ chối đổi thành một lý do từ chối khác, không phải một câu trả
lời tốt hơn.

Chi phí: **438×** thời gian, cho một khác biệt duy nhất và khác biệt đó không
cải thiện kết quả nào.

Điều này giải thích vì sao con số 1.0 của sáu eval suite chạy offline vẫn giữ
nguyên khi bật LLM: trên tập câu hỏi này, **luật precedence trong khâu merge
parse khiến nhánh deterministic quyết định 19/20 lần**. Kết quả khớp với phép đo
độc lập trước đó trên 32 case có nhãn: LLM thô đúng 71,9%, deterministic đúng
53,1%, nhưng intent **sau khi merge** vẫn đúng 53,1% — bằng đúng deterministic.

---

## 8. Tổng hợp theo lớp lỗi

| # | Lớp lỗi | Ca quan sát | Đặc điểm chung |
| --- | --- | --- | --- |
| 1 | Ràng buộc bị thu hẹp im lặng | bgk13 (cửa sổ ngày), bgk03/10 (bộ lọc thừa) | output hoàn chỉnh, thiếu một ràng buộc, không dấu hiệu |
| 2 | Đổi câu hỏi | bgk13 | trả lời đúng một câu hỏi khác, verifier vẫn pass |
| 3 | Bất đồng giữa các tầng | bgk02, bgk11 | validator cho qua, compiler crash; 28/83 ref mang mâu thuẫn |
| 4 | Ánh xạ chữ → ký hiệu | bgk05, bgk01 | alias thiếu hoặc ref không tồn tại làm request lệch |
| 5 | Lý do từ chối không khớp vấn đề | bgk14, bgk16 | hành động đúng, gợi ý khắc phục vô ích |
| 6 | Chi phí không đổi lấy chất lượng | toàn bộ | 438× thời gian, 19/20 kết cục không đổi |

Lớp 1 và 2 nguy hiểm hơn phần còn lại vì chúng tạo ra output **trông đúng**:
một con số có evidence, một mục "Phạm vi", một mục "Độ tin cậy: High". Lớp 3 tuy
là crash nhưng ồn ào nên không thể bị bỏ qua.

---

## 9. Nhận xét về chính phép đo này

Ba giới hạn cần nói rõ để không đọc quá lời:

1. **N = 20.** Một câu lật đổi kết quả 5%. Không có khoảng tin cậy.
2. **Bộ câu hỏi do người đánh giá soạn sau khi đã biết điểm yếu**, nên nó nhắm
   có chủ đích vào chỗ yếu. Nó không phải mẫu đại diện cho câu hỏi người dùng
   thật.
3. **Chấm điểm bằng luật máy**: một câu trả lời được coi là đúng nếu con số của
   oracle xuất hiện trong answer hoặc evidence. Cách này bỏ qua sắc thái diễn
   đạt. Ba ca `wrong_value` đã được kiểm tay và cả ba đều là sai thật, không
   phải lỗi chấm — riêng bgk03/bgk10 tôi đã kiểm chéo oracle bằng hai định nghĩa
   độc lập trước khi kết luận.

---

## 10. Lệnh tái tạo

```bash
python scratchpad/bgk_groundtruth.py     # ground truth từ CSV
python scratchpad/bgk_run_agent.py       # chạy agent, provider=deepseek
python scratchpad/bgk_compare.py         # chấm điểm
```

Artifact sinh ra: `artifacts/bgk_groundtruth.json`, `artifacts/bgk_agent_run.json`,
`artifacts/bgk_offline_run.json`, `artifacts/bgk_scored.json`,
`artifacts/bgk_run.log`, `artifacts/bgk_offline.log`.
