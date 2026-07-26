# Báo cáo triển khai Context Harness và testcase 26/07

Ngày xác minh: 2026-07-26  
Branch: `MVP_Dai_V2`  
Remote HEAD đã pull: `6242c73`  
Nguồn testcase mới: `docs/DR TASK 1407.md`

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
