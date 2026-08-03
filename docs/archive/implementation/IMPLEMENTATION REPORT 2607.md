# Báo cáo triển khai Context Harness và testcase 26/07

Ngày xác minh: 2026-07-26  
Branch: `MVP_Dai_V2`  
Remote HEAD đã pull: `6242c73`  
Nguồn testcase mới: `docs/qa/DR TASK 1407.md`

## 1. Phạm vi đã triển khai

### Context harness và alignment

- Thêm `ContextBundle`/`RequestDigest`, budget theo stage, stable context hash và
  context summary trong response/trace.
- Sanitize bản sao text nội bộ trước khi đưa vào context LLM; evidence gốc không
  bị sửa.
- Thêm kiểm tra request → plan → evidence → answer (`A22-*`), chặn silent
  measure substitution ở TC29/TC39.
- Thêm qualifier contract cho certified macro; TC21/22/24/30 không còn dùng
  chung một output sai điều kiện.
- Thêm ID-first entity extraction, namespace riêng cho item/shop/promotion/
  category, alias `Indo`, và không hiểu chữ `ID` trong `category ID`,
  `promotion ID`, `mã ID` thành Indonesia.
- Thêm structured partial response cho compound request; phần có dữ liệu và
  phần không có capability được ghi riêng.
- Thêm confidence decision table dựa trên evidence completeness, truncation,
  tier và escalation mode.

### Cassette/replay

- Thêm content-addressed cassette key gồm provider, model/revision, sampling,
  prompt version, purpose, system/tool/context hash và dataset version.
- Cassette immutable, redact secret metadata, sanitize text trước khi ghi.
- Runtime factory đã hỗ trợ `off`/`record`/`replay`.
- Replay có thể khởi tạo không cần provider credential và cassette miss không
  fallback sang network/provider.

### Sáu defect trong `2507.md`

- `dataset_version` dùng `cached_property`.
- `expected_cardinality` được validate và cưỡng chế sau execute.
- Executor chạy `EXPLAIN (FORMAT JSON)` để chặn estimated rows trước materialize.
- Open analytical result ghi rõ `result_count`, `returned_rows`, `row_limit`,
  `truncated`.
- Internal text guard được wire vào generation context và trace guard hits.
- Confidence label được tính từ decision table, không còn literal cố định.

### Bộ regression DR 26/07

- `scripts/build_dr2607_suite.py` trích chính xác 40 câu hỏi từ tài liệu nguồn.
- `eval/dr2607.json` lưu question, L/C class, route contract, allowed/forbidden
  rule và trạng thái oracle.
- TC19/TC20 không đưa phần chú thích biên tập vào input.
- `tests/test_dr2607_regression.py` kiểm:
  - đủ 40 question duy nhất;
  - TC29/TC39 không `allow listing_count`;
  - qualifier và compound request;
  - ID/country namespace;
  - nonexistent ID;
  - quote-insensitivity qua bốn biến thể.
- Oracle độc lập và expected denotation nằm trong `eval/independent/`; oracle
  không import production package.
- Metamorphic relations chỉ thay đổi hình thức an toàn, không đổi language,
  country, date hoặc currency.

## 2. Kết quả xác minh

| Suite | Kết quả |
| --- | ---: |
| Full pytest | 326 passed |
| DR 26/07 + context/alignment | 41 passed |
| Legacy | 60 case × 3, accuracy 1.0 |
| V2 | 11 case × 3, accuracy 1.0 |
| A19 | 6 case × 3, accuracy 1.0 |
| Critic | 4 case × 3, accuracy 1.0 |
| Boundaries | 9 case × 3, accuracy 1.0 |
| Phase 5 offline | 6/6, denotation 1.0 ở cả ba mode |
| Phase 6 offline-no-network | 12/12 |
| Quote stability | 40/40 qua bốn biến thể |

Phase 5 vẫn báo `production_go_no_go=NO-GO` đúng theo policy vì
`production_provider=false` và `gold_human_reviewed=false`; đây không phải test
failure của implementation.

## 3. Những phần cố ý chưa thể đóng bằng code

1. TC19 cần policy/human label cho sentinel price. Artifact hiện tại đánh dấu
   `price_sentinel_flag=False`; không được tự đổi oracle.
2. Premise TC34 trong DR cũ sai artifact: item được nêu có đủ ba snapshot. Cần
   reviewer chọn fixture gap thật nếu muốn giữ mục tiêu “missing day”.
3. TC38 và một số open analytical L2/L3 cần cassette đã record từ production
   planner hoặc credential/provider run để đánh giá provider path; offline vẫn
   fail-closed ở `A19-PLAN`.
4. Phase 5 production sign-off cần reviewer nghiệp vụ duyệt gold và một lần chạy
   production provider. Không được tự gắn `approved`.

Không cần thêm file source để chạy core regression. Để đóng production/provider
acceptance, cần cung cấp cassette đã duyệt hoặc credential qua secret store, cùng
quyết định reviewer cho TC19, fixture TC34 và Phase 5 gold.

---

## 4. Bổ sung 27/07 — live-search P5 và query fallback

Phần này nằm **ngoài** ba spec 2507/2607; nó xử lý bốn lỗi phát hiện khi chạy
Tavily thật ngày 26–27/07. Live search vẫn mặc định OFF và E6 vẫn `PENDING`.

### 4.1 Điều kiện đo

Mọi số dưới đây đo bằng `TAVILY_API_KEY` thật, provider `groq`, cache/quota tạm
(không ghi vào `data/external_cache`), câu hỏi `Lịch 7.7 ở Indonesia diễn ra khi nào?`.

### 4.2 (a) Prompt P5 không nêu đủ ràng buộc — ĐÃ SỬA

**Triệu chứng.** `LiveSearchPlanner.plan()` cưỡng chế 7 ràng buộc, nhưng prompt
`plan_live_search` chỉ nêu 5 và **không hề nhắc `validator_feedback`** — trong khi
cả 4 biến thể `plan_analytical` đều có. Đo được: Groq trả về output **giống nhau
từng byte** ở cả hai vòng repair, luôn fail rồi rơi xuống deterministic fallback.
Vòng bounded repair là no-op.

**Sửa.** Gộp thành một hằng `P5_PROMPT` dùng chung cho cả bốn client (Gemini,
HuggingFace, Groq, Anthropic) — trước đó là bốn bản copy đã lệch nhau. Prompt nêu
đủ 7 ràng buộc, `validator_feedback`, và yêu cầu kèm tên sàn.
`_CAMPAIGN_QUALIFIERS` được tách khỏi nhánh validate inline để prompt đọc được
qua `constraints.required_query_qualifiers`.

| | Trước | Sau |
| --- | --- | --- |
| Latency P5 | 17.9 s (2 vòng repair đều fail) | **1.5 s** |
| Kết quả | luôn `plan_id=p5:deterministic:*` | **plan LLM hợp lệ ngay lần đầu** |

### 4.3 (b) Query fallback thiếu tên sàn — ĐÃ SỬA

**Triệu chứng.** Query template không nêu marketplace nên Tavily (`topic=news`)
trả về nội dung lạc đề hoàn toàn.

Đo A/B cùng thời điểm:

| Query | Score | Nội dung trả về |
| --- | --- | --- |
| `Indonesia 7.7 ecommerce shopping campaign 2026 dates` | 0.03 – 0.09 | tên lửa KHAN, hợp đồng UFC, visa Quý Châu, Walmart Mexico |
| `Shopee Tokopedia Indonesia 7.7 ecommerce shopping campaign 2026 dates` | **0.54 – 0.87** | đúng chủ đề 7.7 Shopee Indonesia |

**Sửa.** Thêm `MARKETPLACES` trong `search_planner.py` làm nguồn sự thật duy nhất
cho ánh xạ market → sàn (`vn`: Shopee/Lazada/TikTok Shop; `id`: Shopee/Tokopedia/
Lazada; `global`: Shopee/Lazada). Map này vừa đi vào `constraints.marketplaces`
cho P5, vừa dùng cho deterministic fallback, để hai đường không lệch nhau.

Test `test_search_planner_uses_safe_deterministic_fallback_after_bounded_repairs`
được cập nhật theo query mới; đây là đổi contract có chủ đích, không phải sửa
test cho xanh.

### 4.4 Kết quả không như kỳ vọng — phải ghi lại

Sửa (a) làm P5 hợp lệ, **nhưng query do P5 tự sinh vẫn truy hồi ra rác**:

```
'Shopee 7.7 campaign Indonesia 2026 sale'          → 0.11  Boeing F-15EX Indonesia
'Tokopedia 7.7 promotion Indonesia 2026 ecommerce' → 0.17  Hilliard Law promotion
'Lazada 7.7 shopping Indonesia 2026 marketplace'   → 0.09  janitor fish, Lazada layoffs
```

Tức **template deterministic (0.87) đang tốt hơn LLM planner (≤0.17)** cho use case
này. Hai hệ quả:

1. Chất lượng truy hồi **chưa** được đóng bởi (a)+(b).
2. Latency **xấu đi**: P5 nay sinh 3 query × 5 result = 15 item, relevance gate cho
   qua 12 ⇒ `12 × ~34 s ≈ 408 s` P6, so với 4 item trước đây. Sửa (a) mà không kèm
   (c) làm hệ thống chậm hơn.

### 4.5 (c) Relevance gate — DỰ ĐỊNH, CHƯA LÀM

Gate hiện sai ở **cả hai chiều**, đo trên kết quả thật:

- **Quá lỏng:** bài về hợp đồng UFC lọt vì overlap `['7.7','promotion']`; bài tên
  lửa lọt vì `['7.7','indonesia']`. Mỗi item lọt tốn một P6 call ≈ 34 s.
- **Quá chặt:** bài đúng chủ đề `"Seller jangan sampai ketinggalan ikut campaign
  Gajian Sale"` (score 0.58) bị **drop** vì overlap rỗng — snippet tiếng Bahasa
  không trùng token tiếng Anh của query.

Gate đang dùng token overlap trong khi Tavily đã trả sẵn trường `score`, và phân
tách rất sạch:

```
rác                        : 0.03 – 0.17
hit thật                   : 0.54 – 0.87
fixture Phase 6 / W8 hiện có: 0.36 – 0.90
```

**Kế hoạch:** thêm score floor ≈ 0.30 vào `external/relevance.py`, fail-open khi
`score is None` để không phá fixture offline, giữ token overlap làm lớp phụ.
Ngưỡng 0.30 cắt toàn bộ 12 item rác đo được và giữ nguyên 12/12 fixture Phase 6.

Chưa triển khai vì thay đổi này đụng ngưỡng admission của external evidence, cần
quyết định của reviewer trước. Cân nhắc kèm: hạ `max_queries_per_request` về 1
hoặc ưu tiên deterministic template, vì P5 tự do hiện chưa có giá trị gia tăng.

### 4.6 (d) Latency — DỰ ĐỊNH, CHƯA LÀM

Đo một câu hỏi end-to-end: **158 s**. Phần lớn là hệ quả của (c). Phần còn lại là
`GROQ_MIN_INTERVAL_SECONDS` mặc định 15 s (`llm.py`), tức throttle ép ngủ giữa các
call cùng role. Đây là knob vận hành, cần quyết định của owner chứ không sửa trong
code. Điều kiện rehearsal *"năm câu dưới 5 phút"* của
`PHASE6_ACCEPTANCE_SIGNOFF.md` **chưa đạt** ở trạng thái hiện tại.

### 4.7 Xác minh sau khi sửa (a)+(b)

```
python -m pytest -q                                   326 passed
pytest -q tests/test_external_*.py                     94 passed
run_phase6_evaluation.py --suite eval/questions_external.json
                                                       12/12, offline-no-network
```

Không đổi trạng thái E6, không bật cờ live search, không đụng file nào của
`8cf2073`.
