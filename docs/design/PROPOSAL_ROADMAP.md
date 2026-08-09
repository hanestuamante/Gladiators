# Gladiators — luận điểm kiến trúc và lộ trình phát triển

> Tài liệu cho ban giám khảo. Mọi con số trong đây đều lấy từ artifact chạy
> được, kèm lệnh tái tạo ở §7. Chỗ nào chưa đo được thì nói rõ là chưa đo.

---

## 1. Bài toán thật không phải "trả lời được", mà là "không trả lời sai"

Một agent phân tích thương mại điện tử dễ trông có vẻ hoạt động. Hỏi *"sản phẩm
nào bán chạy nhất?"*, nó trả về một cái tên và một con số. Câu trả lời trôi
chảy, có vẻ hợp lý, và không ai kiểm lại.

Vòng phát triển này đo được **bảy lớp lỗi** mà mọi lớp đều có chung đặc điểm đó:
plan tự nhất quán, câu trả lời tự tin, và sai.

| Lỗi quan sát được | Câu trả lời sai | Đúng ra phải là |
| --- | --- | --- |
| Rơi nước thứ hai | 668 (chỉ VN) | còn thiếu 474 của ID |
| Thu hẹp cửa sổ ngày | −102 | **+11** — sai cả dấu |
| Rơi chiều gom nhóm | 668 | 465 |
| Đảo hướng xếp hạng | 3.033.180 | **1.000** — lệch ~3000 lần |
| Hỏi số nhiều, trả một dòng | 1 listing | 5 |
| Hoà ở mức cao nhất | chọn 1 trong 21 brand | không xác định được |
| Giá placeholder | "giá cao nhất" | một hằng số rác |

Không lỗi nào trong bảng này lộ ra qua đọc code. Tất cả đều tìm được bằng cách
**chạy hệ thống rồi đối chiếu với dữ liệu gốc**.

Đó là luận điểm trung tâm: giá trị của kiến trúc này nằm ở chỗ nó biến những lỗi
im lặng thành lỗi ồn ào.

---

## 2. Kiến trúc: LLM đề xuất, deterministic quyết định

```
câu hỏi
  │
  ├─ S1 parse ────── LLM đoán intent          → validator deterministic
  ├─ S2 route ────── phân luồng nội bộ/ngoài
  ├─ S3 entity ───── ID → tên → fuzzy → BGE   → margin thấp thì HỎI LẠI
  ├─ S4 gate ─────── allow | clarify | abstain
  │
  ├─ S5 plan ─────── macro đã chứng nhận, hoặc synthesizer, hoặc LLM sinh IR
  │                  → validator → compiler (SELECT-only) → DuckDB read-only
  │
  ├─ S6 evidence ─── mọi số hiển thị phải có bản ghi truy vết được
  ├─ S7 generate ─── template deterministic, hoặc LLM đọc context đã guard
  ├─ S8 verify ───── quét mọi số trong answer, đòi evidence hậu thuẫn
  └─ S9 gate-out ─── alignment cuối; fail thì từ chối, không sửa số
```

**LLM không bao giờ tính số và không bao giờ quyết định gate.** Nó đoán intent,
sinh plan IR, sinh search query, trích span, diễn giải câu chữ. Mọi output đều
phải qua một validator deterministic trước khi được phép ảnh hưởng bất cứ gì.

### 2.1. Ba lớp kiểm khác nhau, và vì sao cần cả ba

| Lớp | Câu hỏi nó trả lời | Bắt được lỗi nào |
| --- | --- | --- |
| **Gate** | Được phép trả lời không? | Hỏi thứ dataset không có |
| **Alignment (A22)** | Có đang trả lời **đúng câu hỏi** không? | Trả `474 listing` cho câu hỏi về mức giảm giá |
| **Verifier** | Số hiển thị có evidence không? | Số do model bịa ra |

Lớp giữa sinh ra vì một lỗi thật: gate cho phép ✓, verifier pass ✓, nhưng câu
trả lời nói về một thứ khác hẳn thứ được hỏi. Hai lớp kia không có cách nào thấy.

### 2.2. Semantic layer là code chạy được, không phải tài liệu

- **83 semantic ref** — mọi câu hỏi phải rơi vào tập này hoặc bị từ chối. Đây là
  lý do bài toán hữu hạn hoá được.
- **10 relation đã chứng nhận** — planner chọn ref, compiler tự tìm đường join.
  Không có edge ShopCategory ↔ PlatformCategory, nên không ai nối nhầm được.
- **11 invariant** (10 hard) — có ID, có version, trỏ tới handler deterministic.
- **14 topic**, ownership là **phân hoạch đúng 83/83 ref**, kiểm lúc import.

Hệ quả: thêm năng lực = thêm registry entry, **không sửa workflow core**.

---

## 3. Bằng chứng: hệ thống an toàn tới mức nào

### 3.1. Bộ 40 testcase DR1407 (đã research và verify đáp án độc lập)

```
crash                        0/40
số hiển thị không evidence   0/40
allow có evidence đầy đủ     3/3
phân bố  clarify 26 · abstain 11 · allow 3
```

Tỷ lệ `allow` thấp **là tính năng, không phải khiếm khuyết**: 26 câu hỏi lại vì
mơ hồ thật, 11 câu từ chối vì dataset không có (lợi nhuận, dự báo, SKU, tồn kho).
Điều đáng nói là **không một câu nào trả lời sai một cách tự tin**.

### 3.2. Sáu eval suite

| Suite | Kết quả |
| --- | --- |
| `questions` 60×3 | 1.0 |
| `questions_v2` 11×3 | 1.0 |
| `questions_a19` 6×3 | 1.0 |
| `questions_boundaries` 9×3 | 1.0 |
| `questions_ambiguity` 4×3 | 1.0 |
| `questions_critic` 4×3 | 1.0 |
| Phase 6 external | 12/12 `offline-no-network` |
| `pytest` | 804 passed, 1 skipped |

### 3.3. Chỉ số quan trọng hơn accuracy

`verifier_mutation_detection = 1.0` — verifier vẫn bắt được số bịa **sau khi**
sửa false positive. Nếu bản vá chỉ đơn giản tắt kiểm tra đi thì chỉ số này đã tụt.
Đây là cách phân biệt "sửa đúng" với "làm cho test xanh".

---

## 4. Năng lực đã dựng nhưng **chưa bật** — đây là chiều sâu

Ba hệ thống dưới đây đã hoàn chỉnh, có test, và đang chạy **shadow** trên mọi
request thật: ghi lại điều chúng *sẽ* làm, không đổi câu trả lời.

Lý do chưa bật không phải vì chưa xong, mà vì **gate chưa có bằng chứng của
reviewer** — đúng nguyên tắc fail-closed của hệ thống áp dụng cho chính nó.

### 4.1. Topic-routed context

Thay vì đưa toàn bộ catalog cho planner, hệ chọn đúng lát cắt ngữ nghĩa mà câu
hỏi cần.

```
routing trên 188 câu:  topic_scoped 72.3% · multi_topic 14.4%
                       core_only 8.5%  · unknown 4.8%
context:  toàn catalog 3610 token → routed p50 1213  (giảm 66%)
```

Đo trên đường chạy thật: **3–6ms**, `catalog_miss_count = 0` — lát cắt hẹp vẫn
chứa đủ mọi ref mà plan thật đã dùng. Đó chính là bằng chứng gate đang chờ.

### 4.2. AnalyticalDecomposer

Tách câu hỏi phức thành 2–4 subplan atomic rồi ghép bằng **4 composition
operator** đã chứng nhận: `side_by_side`, `union_scope`, `join_on_relation`,
`filter_then_measure`.

Luật quan trọng nhất là luật **không** dùng: *"hai topic thì tách"*. Kiểm chứng
trên corpus — câu *"tỷ lệ có voucher theo shop chính hãng"* route ra hai topic mà
vẫn giải được bằng một plan. Tách nó ra sẽ tạo hai nửa đúng rồi cần một
composition để nói lại điều mà join đã nói, với gấp bốn chi phí.

### 4.3. Insight mart + PAM

Bundle bất biến dựng offline: scorecard 1.157 listing, 16 insight card, 22
evidence, 4 miner. API đọc read-only, p95 **4,68ms**.

Ba luật giữ con số khỏi vô nghĩa: chấm điểm trong `country × category` (không xếp
VN với ID), thiếu transition thì **gắn cờ chứ không điền 0**, giá sentinel làm
null cả Monetary lẫn PAM.

---

## 5. Lộ trình — bốn tầng, xếp theo mức chín của bằng chứng

### Tầng 1 — Bật thứ đã dựng (0 code mới, cần dữ liệu A/B)

| Việc | Điều kiện bật | Tác động |
| --- | --- | --- |
| Topic routing | required-ref recall 100%, `false_allow_rate = 0` | context giảm 66%, giá LLM giảm tương ứng |
| Decomposer | exact gate signature cho từng shape | mở nhóm câu hỏi nhiều ràng buộc |
| Critic escalation | acceptance profile có sign-off | +1 lớp kiểm cho plan L3 |

Shadow đã bắt đầu thu số. Đây là việc **rẻ nhất và tác động lớn nhất** còn lại.

### Tầng 2 — Đóng khoảng cách năng lực đã định vị

**a) LLM intent parsing (W0–W6).** Đo được, và con số nói điều bất ngờ:

```
deterministic          17/32 = 53.1%
LLM thô                23/32 = 71.9%   ← đúng hơn 6 case
intent sau khi merge   17/32 = 53.1%   ← luật precedence cho deterministic thắng 32/32
```

LLM hiện đóng góp **bằng 0** vào intent cuối. Đây không phải lỗi của model mà là
một quyết định an toàn đang quá chặt. W4 (chính sách trọng tài) là chỗ mở khoá,
và nó cần corpus có nhãn (W0) làm bằng chứng trước.

**b) Ranh giới macro chưa ai định nghĩa.** Câu *"nhóm có voucher tại VN bán thế
nào?"* là `promotion_effectiveness` hay `voucher_coverage`? Trả lời câu đó là
định nghĩa ranh giới nghiệp vụ, không phải gán một nhãn — nên nó thuộc về người,
không thuộc về model.

**c) Bốn Promo Group.** Business dictionary định nghĩa `no promo` / `promo only` /
`voucher only` / `voucher + promo`. Hệ hiện có hai cờ rời nhưng **không có ref
nhóm 4 loại**, nên câu hỏi kiểu *"voucher nhưng không giảm giá trực tiếp"* chưa
bind được. Thêm ref này gỡ trực tiếp một nhóm câu hỏi đang bị chặn.

### Tầng 3 — Chiều sâu phân tích

- **Similarity 3 tầng** theo business dictionary: cùng `country_code` + giao
  `global_catids`, biên giá ±20%, ưu tiên official shop. Luật đã có, chưa nối.
- **Insight mart → dashboard**: click-to-evidence deterministic đã chạy;
  ask-deeper chỉ bật khi preselected-evidence contract pass.
- **External context** (Tavily): record/replay đã dựng và nối; mặc định OFF,
  luôn clamp `context_only`, cấm tính toán xuyên tier.

### Tầng 4 — Thứ dataset hiện tại **không** cho phép, và nên nói thẳng

| Muốn làm | Vì sao chưa được |
| --- | --- |
| Dự báo / xu hướng | 3 snapshot trong 3 ngày |
| Nhân quả ("vì sao giảm") | không thử nghiệm, không nhóm đối chứng |
| Lợi nhuận, ROAS, tồn kho | dữ liệu nội bộ, không có trong public snapshot |
| Phân tích theo SKU | grain nhỏ nhất là product listing |
| Hết hàng | `is_sold_out` bằng `False` trên **toàn bộ** 3.341 dòng |

Hàng cuối đáng chú ý: business dictionary có định nghĩa một **Stock Status
Matrix** 4 trạng thái dựa trên `is_sold_out`. Đối chiếu dữ liệu thì cột này
zero-variance, nên ma trận luôn cho ra "Available". Đây là ví dụ điển hình của
thứ mà kiến trúc này tồn tại để chặn: một phân tích đúng về mặt logic, chạy
được, và vô nghĩa.

---

## 6. Đang chờ người quyết — không code thay được

Ghi ở đây vì đó là ranh giới thật giữa "chưa làm" và "không được tự quyết".

1. **Hai luật chất lượng dữ liệu (DR1).** Một dải giá trị giá lặp chữ số trông
   như placeholder nhưng bộ lọc sentinel hiện chỉ nhận một hằng số ở độ dài khác.
   Và ở một thị trường, một tỉ lệ lớn listing nằm đúng tại giá trị lớn nhất của
   cột sold proxy — nếu đó là bậc hiển thị chứ không phải phép đếm thì mọi phép
   trung vị trên cột đó đổi nghĩa. Luật phải viết theo **phân bố**, không liệt kê
   dòng.
2. **Sáu metric gate** của topic routing (`required_ref_recall`,
   `false_allow_rate`…) — cần oracle độc lập, không được tự chấm.
3. **PAM golden review** — đổi trọng số phải có ablation 20/40/40 vs 30/40/30.
4. **Claim-boundary review**.

---

## 7. Tái tạo mọi con số trong tài liệu này

```bash
.venv/Scripts/python.exe -m pytest -q                                    # 804 passed
.venv/Scripts/python.exe scripts/run_evaluation.py --suite eval/questions.json --runs 3 --provider offline
.venv/Scripts/python.exe scripts/run_evaluation.py --suite eval/questions_critic.json --runs 3 --provider offline --enable-critic
.venv/Scripts/python.exe scripts/run_phase6_evaluation.py --suite eval/questions_external.json
.venv/Scripts/python.exe scripts/build_topic_gate.py                     # routing + token
.venv/Scripts/python.exe scripts/build_insight_mart.py                   # insight bundle
.venv/Scripts/python.exe scripts/build_insight_performance_report.py     # p95 API
.venv/Scripts/python.exe scripts/build_release_proof.py                  # proof pack
.venv/Scripts/python.exe scripts/render_topic_prompts.py --check         # drift
```

Lưu ý: `streamlit` không phải dependency đã khai báo, nên dashboard render qua
stub trong test. Điều đó xác minh wiring và trình tự gọi, **không** xác minh giao
diện.

---

## 8. Một câu tổng kết

Kiến trúc này không tối ưu cho việc trả lời được nhiều câu nhất. Nó tối ưu cho
việc **mỗi câu trả lời đưa ra đều truy vết được về một dòng dữ liệu**, và mỗi câu
không trả lời được đều nêu rõ lý do có thể tranh luận.

Bằng chứng cụ thể nhất cho điều đó không phải một con số accuracy, mà là bảy lỗi
ở §1: hệ thống này được xây bằng cách liên tục tìm ra chỗ chính nó nói dối một
cách trôi chảy, rồi bịt từng chỗ lại.
