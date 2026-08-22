# Backlogbefore2208 — Hạng mục chưa hiện thực

> **Chốt tại:** commit `e5347df`, nhánh `MVP_Dai_V2`, ngày 22/08/2026.
>
> File này gom mọi thứ **đã có kế hoạch nhưng chưa hiện thực** từ các tài liệu
> plan/handoff/roadmap rải rác trong `docs/`. Phần *đã làm rồi* của các tài liệu
> đó nằm ở [`Archibefore2208.md`](Archibefore2208.md); phần *kết quả kiểm thử*
> nằm ở [`TCresultbefore2208.md`](TCresultbefore2208.md).
>
> **Nguyên tắc phân loại:** một hạng mục chỉ vào đây khi nó **chưa chạy trong
> code đang chạy**. Thứ đã dựng xong nhưng cố ý tắt (§2) khác hẳn thứ chưa viết
> (§3), và cả hai khác hẳn thứ **không ai được tự quyết** (§1).

---

## 0. Bản đồ nhanh

| Nhóm | Số hạng mục | Chặn bởi |
| --- | ---: | --- |
| §1 · Chờ người quyết | 6 | Không code thay được |
| §2 · Đã dựng, cố ý chưa bật | 4 | Thiếu bằng chứng cho gate |
| §3 · Chưa viết | 7 | Ưu tiên / phụ thuộc |
| §4 · Dataset không cho phép | 5 | Bản chất dữ liệu — **đóng vĩnh viễn** |
| §5 · Nợ kiến trúc | 3 | Đã biết, chưa dọn |

---

## 1. Chờ người quyết — không code thay được

Đây là ranh giới thật giữa *"chưa làm"* và *"không được tự quyết"*. Tự động hoá
những mục này là vượt quyền, không phải tiến độ.

### 1.1. Hai luật chất lượng dữ liệu (DR1)

**Vấn đề 1 — giá trị giá nghi placeholder.** Có một dải giá trị giá lặp chữ số
trông như placeholder, nhưng bộ lọc sentinel hiện chỉ nhận **một hằng số ở độ dài
khác** (`999999999`). Chưa rõ dải kia có phải rác không.

**Vấn đề 2 — bậc hiển thị của sold proxy.** Ở một thị trường, một tỉ lệ lớn
listing nằm đúng tại **giá trị lớn nhất** của cột sold proxy. Nếu đó là *bậc hiển
thị* chứ không phải *phép đếm*, thì mọi phép trung vị trên cột đó **đổi nghĩa**.

**Ràng buộc bắt buộc khi viết luật:** phải viết theo **phân bố**, tuyệt đối không
liệt kê dòng cụ thể. Liệt kê dòng là làm rò đáp án của bộ đánh giá vào repo.

**Ai quyết:** DR1. **Trạng thái:** `PENDING`.

### 1.2. Sáu metric gate của topic routing

`eval/topic_gate.json` hiện có `gate_open=false`, 5/5 automatic check PASS, **6
metric còn lại `pending_oracle`** — cố ý không tự chấm.

Cần oracle độc lập cho: `required_ref_recall`, `false_allow_rate`, và 4 metric
còn lại. **Không được tự chấm** — một hệ tự chấm điểm cho cổng của chính nó thì
cổng đó không còn là cổng.

### 1.3. PAM golden review

Đổi trọng số `pam_score = 100 × (0,30·activity + 0,40·momentum + 0,30·monetary)`
phải kèm **ablation 20/40/40 vs 30/40/30**, không đổi bằng cảm tính.

### 1.4. Claim-boundary review (P13)

Ranh giới điều được phép tuyên bố. Chưa có người ký.

### 1.5. Policy sentinel giá (TC19)

Chính sách xử lý giá bất thường ngoài hằng số sentinel hiện tại.

### 1.6. Phase 6 E6 sign-off

`docs/acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md` — trạng thái **`PENDING`**, ba ô
ký đều trống (DR1 · Source/Legal owner · Lead).

Còn thiếu:
- Windows và Linux CI run xanh — chưa có artifact trong workspace
- Tavily W8 rehearsal — **0** fixture/hash Tavily thật, W8 chưa nghiệm thu

> **Không được đổi trạng thái E6 trong file đó, và không được bật cờ mặc định
> trong source.**

---

## 2. Đã dựng xong, cố ý chưa bật

Bốn hệ thống dưới đây **hoàn chỉnh, có test, đang chạy shadow** trên request thật:
ghi lại điều chúng *sẽ* làm, không đổi câu trả lời.

Lý do chưa bật không phải vì chưa xong, mà vì **gate chưa có bằng chứng của
reviewer** — đúng nguyên tắc fail-closed áp dụng cho chính hệ thống.

### 2.1. Topic-routed context

Chọn đúng lát cắt ngữ nghĩa thay vì đưa toàn bộ catalog cho planner.

```
routing trên 188 câu :  topic_scoped 72.3% · multi_topic 14.4%
                        core_only 8.5%     · unknown 4.8%
context              :  toàn catalog 3.610 token → routed p50 1.213  (giảm 66%)
độ trễ               :  3–6ms, catalog_miss_count = 0
```

`catalog_miss_count = 0` nghĩa là lát cắt hẹp **vẫn chứa đủ** mọi ref mà plan
thật đã dùng. Đó chính là bằng chứng mà gate đang chờ.

**Điều kiện bật:** `required_ref_recall = 100%`, `false_allow_rate = 0` (§1.2).
**Tác động:** context giảm 66% ⇒ chi phí LLM giảm tương ứng.

### 2.2. AnalyticalDecomposer

Tách câu phức thành 2–4 subplan atomic rồi ghép bằng 4 composition operator đã
chứng nhận: `side_by_side`, `union_scope`, `join_on_relation`, `filter_then_measure`.

**Luật quan trọng nhất là luật KHÔNG dùng:** *"hai topic thì tách"*. Kiểm chứng
trên corpus — câu *"tỷ lệ có voucher theo shop chính hãng"* route ra hai topic mà
vẫn giải được bằng **một** plan. Tách nó ra sẽ tạo hai nửa đúng rồi cần một
composition để nói lại điều mà join đã nói, với **gấp bốn chi phí**.

**Điều kiện bật:** exact gate signature cho từng shape.

### 2.3. Plan critic escalation

`GLADIATORS_ENABLE_CRITIC=1`. **Điều kiện bật:** acceptance profile có sign-off.
**Tác động:** +1 lớp kiểm cho plan mức L3.

> Lệnh eval `--enable-critic` chạy **acceptance stub offline**, không phải bằng
> chứng chất lượng của model production.

### 2.4. N-version planner

`GLADIATORS_ENABLE_NVERSION=1`. P10 alternate planner bị blind + P11 adjudicator.
**Điều kiện bật:** acceptance/ablation L4.

Hành vi đã đúng sẵn: hai candidate khác kết quả mà adjudicator không phân định
được bằng issue định danh ⇒ trả `A19-PLAN`, **không chọn ngẫu nhiên**.

---

## 3. Chưa viết

### 3.1. LLM intent parsing — W3 đến W6

Chuỗi phụ thuộc trong `PLAN_LLM_INTENT_PARSING.md`:

```
W0 corpus có nhãn  ✔ xong (7e03936)
 └─ W1 harness + cassette
     └─ W2 constrained decoding  ✔ xong (1df8e5b)
         └─ W3 proposer/validator          ← CHƯA
             └─ W4 chính sách trọng tài    ← CHƯA, đây là chỗ mở khoá
                 └─ W5 shadow              ← CHƯA
                     └─ W6 gate + sign-off ← CHƯA
```

**Số liệu chốt vấn đề:**

```
deterministic          17/32 = 53.1%
LLM thô                23/32 = 71.9%   ← đúng hơn 6 case
intent sau khi merge   17/32 = 53.1%   ← precedence cho deterministic thắng 32/32
```

LLM hiện đóng góp **bằng 0** vào intent cuối. Đây không phải lỗi model mà là một
quyết định an toàn **đang quá chặt**. W4 là chỗ mở khoá, và nó cần W0 làm bằng chứng.

**W4 có 4 chính sách ứng viên, chưa chọn:**

| # | Chính sách | Giả thuyết |
| --- | --- | --- |
| P-A | Deterministic thắng luôn | baseline, LLM chỉ để quan sát |
| P-B | LLM thắng khi deterministic rơi `open_analytical` | mở đúng chỗ rule bó tay |
| P-C | Bất đồng ⇒ `clarify` | an toàn nhất |
| P-D | LLM thắng khi confidence cao + qua đủ validator | cần định nghĩa confidence |

**Bối cảnh mới (22/08):** nhánh LLM parser **đã tắt mặc định** vì đo được
`0.622` vs `1.0` offline. Bật lại cần W3/W4 **và** một phép đo chứng minh nhánh
LLM **thắng**, không phải hoà.

Ngoài phạm vi W-package (§7 của plan gốc): không đụng gate/alignment/verifier/
compiler, không thay `AliasIndex` bằng embedding, không fine-tune, không mở topic gate.

### 3.2. Ranh giới macro chưa ai định nghĩa

Câu *"nhóm có voucher tại VN bán thế nào?"* là `promotion_effectiveness` hay
`voucher_coverage`?

Trả lời câu đó là **định nghĩa ranh giới nghiệp vụ**, không phải gán một nhãn —
nên nó thuộc về người, không thuộc về model. Xếp ở đây thay vì §1 vì sau khi
người quyết thì phần code là cơ học.

### 3.3. Bốn Promo Group

`business-dictionary.md` định nghĩa 4 nhóm: `no voucher/promo` · `promo only` ·
`voucher only` · `voucher + promo`.

Hệ hiện có **hai cờ rời** (`has_promo`, `has_structured_voucher`) nhưng **không có
ref nhóm 4 loại**, nên câu hỏi kiểu *"voucher nhưng không giảm giá trực tiếp"*
chưa bind được.

**Thêm ref này gỡ trực tiếp một nhóm câu hỏi đang bị chặn.** Đây là hạng mục
rẻ nhất trong §3.

### 3.4. Similarity 3 tầng

Theo `business-dictionary.md` §3 Intent 2 — ba màng lọc theo thứ tự ưu tiên:

1. **Lọc cứng:** cùng `country_code` **và** có giao tập hợp tại `global_catids`
2. **Lọc khoảng giá:** biên độ `price_num` không quá ±20%
3. **Lọc uy tín:** ưu tiên `is_official_shop = TRUE` hoặc trùng từ khoá chiến lược

**Luật đã có trong tài liệu, chưa nối vào code.**

### 3.5. Dashboard ask-deeper

Click-to-evidence deterministic **đã chạy**. Nhánh ask-deeper chỉ được bật khi
preselected-evidence contract pass. Chưa làm.

### 3.6. Hoàn tất dispatch invariant — 5/6 stage còn lại

Stage `plan` đã chuyển hoàn toàn sang dispatcher. Năm stage còn lại — `request`,
`composition`, `execution`, `evidence`, `answer` — **có handler chạy được + có
test**, nhưng call site vẫn gọi enforcement cũ trực tiếp.

Enforcement **không yếu đi**, nhưng chưa phải một nguồn duy nhất.

Handler yếu nhất: `execution.zero_row_is_a_result` — hiện chỉ bắt
`relaxed_filters` và **chưa có call site**. Cần thiết kế thêm chứ không chỉ nối dây.

### 3.7. Multi-turn state và structured notes

Đánh dấu `DEFERRED` trong spec (`ultimate solution.md` §7.4). Chưa có lịch.

---

## 4. Dataset hiện tại không cho phép — đóng vĩnh viễn

Không phải backlog. Ghi ở đây để không ai mở lại như một hạng mục có thể làm.

| Muốn làm | Vì sao không được |
| --- | --- |
| Dự báo / xu hướng / mùa vụ | 3 snapshot trong 3 ngày |
| Nhân quả ("vì sao giảm") | không thử nghiệm, không nhóm đối chứng |
| Lợi nhuận, ROAS, tồn kho, conversion | dữ liệu nội bộ, không có trong public snapshot |
| Phân tích theo SKU | grain nhỏ nhất là product listing |
| Phân tích hết hàng | `is_sold_out` bằng `False` trên **toàn bộ** 3.341 dòng |

**Hàng cuối đáng chú ý.** `business-dictionary.md` định nghĩa một **Stock Status
Matrix** 4 trạng thái dựa trên `is_sold_out`. Đối chiếu dữ liệu thì cột này
zero-variance, nên ma trận **luôn** cho ra "Available".

Đây là ví dụ điển hình của thứ mà kiến trúc này tồn tại để chặn: **một phân tích
đúng về mặt logic, chạy được, và vô nghĩa.**

---

## 5. Nợ kiến trúc đã biết

### 5.1. Hai bộ máy khớp alias song song

| Bộ máy | File | Nuôi cái gì |
| --- | --- | --- |
| `AliasIndex.find_in` | `domain/alias_index.py` | `TopicRouter` (shadow) |
| `DeterministicSemanticParser._link` | `planner/semantic_parser.py` | **câu trả lời thật** |

Một bản vá ở bộ này **không** áp cho bộ kia. Bug `"giá trị"` → `measure.price`
từng được vá ad-hoc chỉ trong `_link`.

Thêm nữa: `DeterministicSemanticParser.MEASURES`/`DIMENSIONS`
(semantic_parser.py:149,157) là **bộ alias hard-code thứ ba**, dù docstring của
`alias_index.py` khẳng định nó đã bị loại bỏ. Kế hoạch xoá nằm ở
`ultimate solution.md` §3.2 — **chưa làm**.

> Docstring khẳng định sai về một tính chất kiến trúc còn nguy hơn thiếu tính
> năng, vì không ai kiểm lại nó.

### 5.2. `streamlit` chưa khai trong requirements

`src/gladiators/insights/dashboard.py` không chạy được sau khi cài theo README.
Trạng thái **có chủ đích** (`CLAUDE.md` §10) — dashboard render qua stub trong
test, nên test xác minh **wiring và trình tự gọi**, không xác minh giao diện.

### 5.3. `build_slides.py` chưa dùng design kit chung

`scripts/_deck_kit.py` đã tách ra và deck proposal dùng nó.
`scripts/build_slides.py` **vẫn giữ bản token/helper riêng** — nó đang chạy tốt,
refactor 66KB chỉ để gọn hơn là rủi ro không cần thiết. Ghi ra để không quên.

---

## 6. Ưu tiên đề xuất

Xếp theo **tỷ lệ giá trị / rủi ro**, không theo thứ tự tài liệu gốc.

| Hạng | Hạng mục | Vì sao |
| ---: | --- | --- |
| 1 | §3.3 Bốn Promo Group | Rẻ nhất, gỡ ngay một nhóm câu hỏi đang bị chặn |
| 2 | §1.2 Sáu metric gate topic routing | Mở khoá §2.1 — thứ đã dựng xong, tác động lớn nhất, **0 code mới** |
| 3 | §5.1 Gộp ba bộ alias | Là nguồn của phần lớn bug thật đã gặp |
| 4 | §3.6 Hoàn tất dispatch invariant | Biến "không yếu đi" thành "một nguồn duy nhất" |
| 5 | §3.4 Similarity 3 tầng | Luật đã có sẵn trong business dictionary |
| 6 | §3.1 W3/W4 LLM | Chi phí cao, hiện đóng góp bằng 0, cần corpus trước |

---

## 7. Nguồn đã được tổng hợp vào file này

| File gốc | Phần giữ lại |
| --- | --- |
| `docs/PLAN_LLM_INTENT_PARSING.md` | §3.1 — chuỗi W0–W6, 4 chính sách W4, số liệu 53.1/71.9 |
| `docs/design/PROPOSAL_ROADMAP.md` | §2 (đã dựng chưa bật), §3, §4, §6 (chờ người quyết) |
| `docs/acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md` | §1.6 — trạng thái E6, W8 Tavily |
| `docs/archive/implementation/IMPLEMENTATION_HANDOFF_2026-08-01.md` | §1.1 DR1, §1.2 topic gate, §1.3 PAM |
| `docs/design/ultimate solution.md` §7.4, §12.x | §3.7 multi-turn DEFERRED |
| `docs/design/Metadata_Model_And_Binding_Layer.md` | §3.6 — trạng thái migration dispatch |

**Đã bỏ:** mọi hạng mục đã hiện thực xong (nằm ở `Archibefore2208.md`), các số đo
cũ đã lỗi thời (`804 passed` → nay 933; `sáu eval suite` → nay bảy), và các đề
xuất đã bị chính phép đo sau đó bác bỏ.
