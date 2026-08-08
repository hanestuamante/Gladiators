# Plan nghiên cứu: mở rộng LLM vào intent parsing

> **Loại tài liệu:** research plan, chưa hiện thực hạng mục nào.
>
> | Trường | Giá trị |
> | --- | --- |
> | Baseline code | `645d558`, `pytest -q` = **801 passed, 1 skipped** |
> | Code graph | `graphify-out/` — 3601 node, 7880 edge, 263 community, 0 import cycle |
> | Ràng buộc | `CLAUDE.md` §3 (7 bất biến), `docs/archive/implementation/2-8.md`, `docs/design/ultimate solution.md` |
> | Phạm vi | S1 intent parsing. **Không** đụng gate, alignment, verifier, compiler |

---

## 0. Đính chính một kết luận sai trước khi lập plan

Ngày 27/07 tôi chạy A/B intent parsing trên `eval/questions.json` (60 câu có nhãn)
tại commit `99a024c` và báo cáo:

```
A. Deterministic (rule)      60/60  = 1.000    ~0s
B. LLM prompt cũ (1 dòng)    48/60  = 0.800    179s
C. LLM prompt kỹ             58/60  = 0.967    446s
```

Tôi kết luận rằng prompt B *"bịa tên intent không tồn tại"* — dẫn chứng
`voucher_coverage`, `discount_bucket_observation`.

**Kết luận đó nay không còn đúng.** Ba intent `voucher_coverage`,
`discount_bucket_observation`, `dataset_coverage` **hiện là macro thật** trong
`default_macro_registry()`. Chúng được thêm trong 42 commit landed 31/07–02/08.

Nghĩa là **7 trong 12 "lỗi" của prompt B là tên intent mà team về sau độc lập
quyết định thêm vào taxonomy.** Model không bịa ra khái niệm — nó đề xuất một
phân biệt mịn hơn mà taxonomy lúc đó chưa có.

Ba hệ quả cho plan này:

1. Con số 0.80 / 0.967 **đã cũ**, phải đo lại trên taxonomy 22 intent hiện tại.
2. Nhãn trong `eval/questions.json` mã hoá **một** cách giải quyết mơ hồ. `q33`
   "Nhóm có voucher tại VN bán thế nào?" gắn nhãn `promotion_effectiveness`
   trong khi `voucher_coverage` nay tồn tại và cũng đọc được. Nhãn không phải
   chân lý.
3. Bài học chung: **benchmark viết cùng lúc với bộ rule thì đo bộ rule, không đo
   bài toán.** Đây là lý do W0 phải làm trước mọi thứ khác.

---

## 1. Câu hỏi nghiên cứu thật sự

Câu hỏi **không phải** "LLM hay rule tốt hơn". Kiến trúc hiện tại đã chạy cả hai:
`workflow._parse()` gọi LLM rồi cho deterministic quyền phủ quyết trên nhánh an
toàn (`route_mode`, `unsupported`).

Câu hỏi đúng là:

> **Đặt LLM ở đâu trong pipeline để phương sai của nó bị chặn bởi bộ máy đã có,
> và đo bằng cách nào để biết nó thật sự tốt hơn chứ không phải tốt hơn trên một
> benchmark tự chấm?**

### 1.1. Vì sao đáng làm — bằng chứng, không phải cảm tính

Mọi lỗi thật đã tìm được đều nằm ở **biên ánh xạ chữ → ký hiệu**, không nằm ở
phần suy luận:

| Câu | Rule ánh xạ nhầm | Hậu quả đo được |
| --- | --- | --- |
| "**giá trị** max của images count" | `measure.price` | clarify oan `l4c05` |
| "**Đánh giá** khuyến mãi ở VN" (động từ) | `measure.rating` | clarify oan `q34`, `q57` |
| "Voucher **ID** có hiệu quả không" | `country=id` | sai thị trường |
| DR40 giữ nguyên quote Markdown | entity = cả câu | đổi `(intent, action, rule)` ở **21/40** case |

Rule là danh sách hữu hạn viết tay; ngôn ngữ thì không. Mỗi lỗi trên đều được vá
bằng một luật đặc thù mới (`_FALSE_FRIENDS`, `_VERB_INITIAL`, `_ID_NOUNS`,
`_QUOTE_COVERAGE_LIMIT`). Đó là mô hình chi phí tuyến tính theo số biến thể ngôn
ngữ — không mở rộng được.

### 1.2. Anti-goal — nói trước để không trôi

- **Không** thay thế deterministic parser. Nó là lớp phủ quyết an toàn.
- **Không** cho LLM quyết định gate, tính số, hay chọn grain.
- **Không** nới `intent` thành free-form. Tập đóng 22 phần tử là tài sản, không
  phải hạn chế.
- **Không** tối ưu cho `eval/questions.json`. Suite đó tự chấm bộ rule.

---

## 2. Tài sản đã có — LLM phải chui qua, không được đi vòng

Đây là phần trả lời trực tiếp yêu cầu *"vẫn tận dụng các tool đã có để tránh
hallucinate"*. Không cần xây lớp chống hallucinate mới; cần **bắt buộc** output
của LLM đi qua các lớp sau:

| Tài sản | File | Chặn được gì |
| --- | --- | --- |
| `IntentRegistry` | `domain/intent_registry.py` | tập đóng 22 intent |
| Catalog 83 ref | `domain/catalog.py` | tập đóng semantic object |
| `AliasIndex` | `domain/alias_index.py` | nguồn bind ngôn ngữ **duy nhất** (§3.2) |
| `CapabilitySpec` + matcher | `domain/capability.py` | câu hỏi thứ dataset không có |
| A22 alignment | `agent/alignment.py` | trả lời sai câu hỏi dù evidence đúng |
| Verifier | `agent/verifier.py` | số không có evidence |
| `LLMCassette` | `agent/cassette.py` | test deterministic, không tốn API/quota |
| Topic router (shadow) | `planner/topic_router.py` | tiền lệ rollout shadow → gate |
| `eval/topic_gate.json` | — | tiền lệ gate có `pending_reviewer_signoff` |

**Nguyên tắc thiết kế:** LLM là *proposer*, mọi lớp trên là *validator*. Proposal
không qua validator thì rơi về deterministic — giống hệt cách P5 live-search rơi
về template khi plan không hợp lệ.

---

## 3. Root cause đã xác định, sửa được ngay

`GroqParseOutput.intent` khai là **`str` tự do**:

```python
class GroqParseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str                    # ← tập mở
    entity_text: str | None
    country: str | None
```

Schema được truyền vào Groq dưới dạng `response_format=json_schema, strict=True`.
Nhưng vì `intent` là `str`, **constrained decoding không có gì để ràng buộc** —
model được phép trả bất kỳ chuỗi nào và schema vẫn hợp lệ.

Đổi thành `Literal[*registry.names(), *unsupported]` khiến **chính bộ giải mã**
không sinh được intent ngoài tập đóng. Đây là lớp chống hallucinate rẻ nhất và
mạnh nhất trong toàn bộ plan: nó hoạt động ở tầng token, trước cả validator.

`GeminiParseOutput` có cùng vấn đề (`intent: str`).

> Cần kiểm: Groq/Gemini có hỗ trợ `enum` trong JSON schema ở chế độ strict không.
> Nếu không, fallback là validate sau + repair một vòng có `validator_feedback`
> (đúng khuôn mẫu đã dùng cho P5, đã chứng minh hiệu quả: 17.9s → 1.5s).

---

## 4. Work packages

Thứ tự là **dependency**, không phải mức ưu tiên.

```
W0 corpus có nhãn      ← chặn tất cả, không có thì không đo được gì
 └─ W1 harness + cassette
     └─ W2 constrained decoding
         └─ W3 proposer/validator
             └─ W4 chính sách trọng tài
                 └─ W5 shadow
                     └─ W6 gate + sign-off
```

### W0 — Corpus intent có nhãn trên câu KHÓ

**Vấn đề:** `eval/dr2607.json` có 40 câu tự do thật nhưng **0 câu có
`expected_intent`**. `eval/questions.json` có nhãn nhưng 32/32 câu entity đều
dùng dấu ngoặc kép — nó không đại diện đầu vào thật.

Không có W0 thì mọi số đo sau đều vô nghĩa.

**Việc:**
1. Gán `expected_intent` cho 40 câu DR2607 + 188 câu corpus topic gate.
2. **Hai người gán độc lập**, đo Cohen's κ. Câu κ thấp là câu **mơ hồ thật** —
   tách sang tập `ambiguous`, chấm riêng bằng "chấp nhận tập nhãn" thay vì một
   nhãn duy nhất. `q33` và `q28` thuộc nhóm này.
3. Ghi rõ *vì sao* mỗi nhãn được chọn khi có hơn một cách đọc.
4. Rà lại nhãn `eval/questions.json` theo taxonomy 22 intent hiện tại — mục 0 đã
   cho thấy nhãn cũ có thể lạc hậu.

**DoD:** `eval/intent_labels.json`, ≥228 câu, κ ≥ 0.8 trên tập không mơ hồ, tập
mơ hồ được đánh dấu tường minh. **Người gán không được xem output của parser.**

**Đây là hạng mục cần người, không code thay được** — cùng loại với 6 metric
`pending_oracle` của topic gate.

### W1 — Harness + cassette

**Việc:** `scripts/run_intent_eval.py` chấm một cấu hình parser trên corpus W0.
Bọc `parse_intent` bằng `CassetteLLMClient` (đã có).

**Vì sao:** A/B ngày 27/07 tốn 446s và không lặp lại được. Với cassette, chạy lại
là **0 API call, 0 quota, kết quả bit-identical** — điều kiện để regression test
đường LLM chạy trong CI.

**DoD:** chạy hai lần cho kết quả giống hệt; `replay` mode không mở socket
(`test_cassette.py` đã có test này).

### W2 — Constrained decoding

**Việc:** `intent: Literal[...]` sinh từ registry; kiểm Groq/Gemini/HF có tôn
trọng `enum` ở strict mode; nếu không thì repair một vòng có `validator_feedback`.
Đồng thời sửa prompt P1 theo khuôn mẫu `P5_PROMPT` (mô tả từng intent + quy tắc
ưu tiên, thay vì ném một tuple tên).

**DoD:** trên corpus W0, tỉ lệ intent ngoài tập đóng = **0%**. Đo lại độ chính
xác — đây là con số thay thế 0.80/0.967 đã cũ.

### W3 — Proposer / validator

**Việc:** LLM đề xuất `(intent, entity_refs, countries, qualifiers, measures)`.
Mỗi trường phải qua validator tương ứng:

| Trường | Validator | Không qua thì |
| --- | --- | --- |
| `intent` | `IntentRegistry` | rơi về deterministic |
| `measures` | catalog 83 ref | drop ref lạ, ghi trace |
| `entity_refs` | `entity_extract` + resolver | `A-AMBIGUOUS` / `A-ENTITY-NOT-FOUND` |
| `countries` | `_ID_NOUNS` guard | rơi về deterministic |
| `qualifiers` | `detect_qualifiers` | union, không thay thế |

**Bất biến:** proposal **không bao giờ** ghi đè kết quả deterministic ở nhánh an
toàn. `route_mode` và `unsupported:*` giữ nguyên safety precedence hiện có.

**DoD:** test khẳng định proposal độc hại (intent lạ, ref lạ, entity không tồn
tại) không đi qua được lớp nào.

### W4 — Chính sách trọng tài khi hai bên bất đồng

Đây là phần **nghiên cứu thật**, không phải code. Bốn chính sách, đo cả bốn trên
corpus W0:

| # | Chính sách | Giả thuyết |
| --- | --- | --- |
| P-A | Deterministic thắng luôn | baseline, LLM chỉ để quan sát |
| P-B | LLM thắng khi deterministic rơi `open_analytical` | mở đúng chỗ rule bó tay |
| P-C | Bất đồng ⇒ `clarify` | an toàn nhất, tăng tỉ lệ từ chối |
| P-D | LLM thắng khi confidence cao **và** qua đủ validator | cần định nghĩa confidence |

**Đo:** không chỉ accuracy. Bốn số quan trọng hơn:

- **false_allow_rate** — trả lời tự tin một câu lẽ ra phải từ chối. **Đây là chỉ
  số nguy hiểm nhất**, cùng loại với TC29/TC39.
- **false_abstain_rate** — từ chối một câu lẽ ra trả lời được.
- **quote_stability** — 4 biến thể quote, đã có harness (`≥38/40`).
- **A22 trigger rate** — LLM có làm alignment phải chặn nhiều hơn không.

**DoD:** một bảng bốn chính sách × bốn chỉ số, kèm khuyến nghị có lập luận.
Không tự chọn — trình reviewer.

### W5 — Shadow

**Việc:** chạy LLM parse trên request thật, ghi `intent_shadow` vào trace, **không
đổi câu trả lời**. Theo đúng tiền lệ P5/P6 (`docs/archive/implementation/2-8.md` §5).

**DoD:** `tests/test_shadow_wiring.py` mở rộng — câu trả lời **giống hệt** khi
bật và tắt shadow. Đo latency p50/p95 trên đường chạy thật (tham chiếu: topic
router shadow tốn 3–6ms; parse LLM sẽ tốn hơn nhiều bậc, phải biết chính xác bao
nhiêu).

### W6 — Gate + sign-off

**Việc:** `scripts/build_intent_gate.py` → `eval/intent_gate.json`, cấu trúc
giống `topic_gate.json`: automatic check + `pending_reviewer_signoff`.

**Ngưỡng đề xuất (reviewer chốt):**

| Metric | Ngưỡng | Lý do |
| --- | --- | --- |
| `out_of_registry_rate` | = 0% | bất biến, không thương lượng |
| `false_allow_rate` | ≤ baseline | không được xấu hơn rule |
| accuracy trên tập không mơ hồ | > baseline | phải thắng mới đáng bật |
| `quote_stability` | ≥ 38/40 | giữ mức đã đạt |
| legacy suite | giữ **1.0** | 60/11/6/4/9 × 3 |
| Phase 6 | giữ **12/12** | |
| p95 latency | reviewer chốt | trade-off chất lượng ↔ tốc độ |

**Gate mặc định đóng.** Bật là quyết định vận hành có chủ đích.

---

## 5. Rủi ro

| Rủi ro | Vì sao nguy | Giảm thiểu |
| --- | --- | --- |
| **Benchmark tự chấm** | Đã cắn một lần (mục 0) | W0 gán nhãn mù, hai người, đo κ |
| **Latency** | Đo được 3.0s (prompt ngắn) → 7.4s (prompt dài) mỗi câu | Cassette cho test; đo p95 thật ở W5; cân nhắc model nhỏ cho P1 |
| **Chi phí + quota** | Mỗi request thêm 1 call | Cassette; đo cost/request trước khi bật |
| **Provider drift** | Model đổi ⇒ hành vi đổi âm thầm | `cassette_key` đã gồm `model_revision`; pin version |
| **False allow tăng** | Nguy hiểm nhất — câu trả lời trôi chảy mà sai | A22 + verifier đã ở đó; W4 đo tường minh; gate chặn |
| **Taxonomy còn trôi** | 3 intent mới xuất hiện giữa hai lần đo | W0 khoá taxonomy hash vào corpus, giống `topics_hash` |
| **Prompt injection qua câu hỏi** | Câu hỏi là input không tin cậy | `sanitize_internal_text` đã có; áp cho payload P1 |

---

## 6. Câu hỏi cần người trả lời

Không code thay được, và plan không tự quyết:

1. **Nhãn của câu mơ hồ.** `q33` là `promotion_effectiveness` hay `voucher_coverage`?
   Câu trả lời định nghĩa ranh giới giữa hai macro, không chỉ định nghĩa một nhãn.
2. **Ngưỡng đánh đổi.** Chấp nhận +4s/câu để đổi lấy bao nhiêu điểm accuracy?
3. **Chính sách trọng tài** (W4) — chọn P-A/B/C/D sau khi có số.
4. **Model cho P1.** Model parse hiện là `qwen/qwen3.6-27b` tách khỏi model
   generate. Giữ, đổi nhỏ hơn cho rẻ, hay đổi lớn hơn cho chuẩn?
5. **Có mở LLM sang `measures`/`qualifiers` không**, hay chỉ `intent`? Mở rộng
   càng nhiều thì càng nhiều thứ phải validate.

---

## 7. Việc **không** nằm trong plan này

- Đụng gate, alignment, verifier, compiler, executor.
- Thay `AliasIndex` bằng embedding — §3.2 chốt alias là nguồn bind duy nhất;
  đổi là đổi kiến trúc, cần spec riêng.
- Fine-tune model.
- Bật topic gate (P7) — độc lập, đang chờ dữ liệu shadow.
- Ba lỗi live-search còn treo: relevance gate score floor, throttle, chất lượng
  query P5 (xem `IMPLEMENTATION REPORT 2607.md` §4.5–4.6).

---

## 8. Báo cáo bắt buộc khi hoàn tất

```markdown
## Corpus
- câu có nhãn: N; κ: X; câu mơ hồ tách riêng: M

## Kết quả (trên tập không mơ hồ)
| cấu hình | accuracy | out_of_registry | false_allow | false_abstain | quote_stab | p95 |
| deterministic (baseline) | | | | | | |
| LLM constrained | | | | | | |
| P-A / P-B / P-C / P-D | | | | | | |

## Regression
- pytest / legacy 60×3 / V2 11×3 / A19 6×3 / critic 4×3 / boundaries 9×3 / Phase 6

## Invariants checked
- intent luôn thuộc registry: PASS/FAIL
- deterministic giữ quyền phủ quyết route_mode + unsupported: PASS/FAIL
- câu trả lời không đổi khi shadow bật/tắt: PASS/FAIL
```

Không dùng "done", "production-ready", "all tests pass" nếu không đính kèm lệnh
và kết quả tương ứng.
