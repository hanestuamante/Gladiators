# Bàn giao triển khai V2 — trạng thái đến 20/07/2026

Tài liệu này giúp người tiếp tục có thể bắt đầu ngay mà không phải suy đoán từ lịch sử chat. Nguồn kiến trúc chuẩn là `docs/V2_Unified_Architecture.md`. Trạng thái dưới đây được đối chiếu với code và test trong workspace ngày 20/07/2026.

## 1. Tóm tắt điều hành

- Repository đang ở branch `MVP_Dai_V2`, commit nền hiện tại: `37de2dd Generic tool dispatch + V2.3 Phase 1 foundation (tier migration, metric registry)`.
- Worktree đang có nhiều thay đổi chưa commit. Không reset/checkout hoặc ghi đè các file này. Chủ repo sẽ tự push sau.
- Phase 0–4 đã có code và acceptance offline.
- Phase 5 đã có đầy đủ khung code: risk score, critic, N-version, deterministic comparison và adjudicator. Sáu case L4 offline chạy qua hai planner giả lập độc lập.
- Phase 5 **chưa đạt production acceptance**. Lượt Groq thật mới nhất cho thấy provider hoạt động nhưng critic còn false reject/response rỗng và một case validation error.
- Phase 6 external vẫn OFF theo đúng kiến trúc. Không triển khai/scrape external nếu chưa có trigger và governance approval.
- Coverage matrix hiện đạt `158/158 requirements`, ratio `1.0`, với tổng cộng `198` question/fixture được quy chiếu. Coverage 100% chỉ nói rằng đủ ô kiểm thử, không thay thế real-provider eval, human review hoặc ablation.
- Test hiện tại: `142 tests collected`; bộ test chạy xanh bằng lệnh có `PYTHONPATH=.`.

## 2. Lệnh khởi động nhanh

```bash
cd /Users/vqd/BA3
git status --short
PYTHONPATH=. .venv/bin/pytest -q
```

Không dùng trực tiếp `.venv/bin/pytest -q` trong môi trường hiện tại vì `tests/test_planner_mutations.py` import `scripts.build_eval_coverage_matrix`; thiếu `PYTHONPATH=.` sẽ lỗi collection `ModuleNotFoundError: scripts` dù code không hỏng.

Kiểm tra coverage:

```bash
PYTHONPATH=. .venv/bin/python scripts/build_semantic_coverage_manifest.py
PYTHONPATH=. .venv/bin/python scripts/build_eval_coverage_matrix.py
jq .summary eval/coverage_matrix.json
```

Chạy API/UI:

```bash
PYTHONPATH=. .venv/bin/uvicorn gladiators.api:app --reload
```

- UI chính: `http://127.0.0.1:8000/`
- UI flow: `http://127.0.0.1:8000/flow`
- API: `POST /ask` với body `{"text": "Ngày nào doanh thu cao nhất tại VN?"}`
- Health/capability: `GET /health`, `GET /capabilities`

## 3. Phase 0 — inventory, contracts và coverage manifest

### Đã làm

- Chuẩn hóa source tier về `btc_dataset`, `reference`, `external`; loại tier cũ khỏi đường code chính.
- Mở rộng và kiểm tra contract cho 7 processed artifacts.
- Tạo semantic coverage manifest cho toàn bộ cột vật lý.
- Manifest hiện xác nhận 7 artifacts, 219 columns.
- Mỗi cột có trạng thái semantic để phân biệt field được expose, field chỉ hỗ trợ nội bộ, proxy, raw unsafe hoặc absent theo capability.
- Bổ sung CI-style validation để manifest và header thực không lệch nhau.
- Mở rộng response/request contracts phục vụ open analytical, planning metadata, evidence và trace.

### File chính

- `src/gladiators/data/contracts.py`
- `src/gladiators/data/coverage.py`
- `data/processed/semantic_coverage_manifest.json`
- `scripts/build_semantic_coverage_manifest.py`
- `src/gladiators/contracts.py`
- `tests/test_v1.py`

### Acceptance hiện tại

- Header của 7 artifact được validate.
- Coverage manifest khớp 100% physical headers.
- Tier contract được kiểm bằng test và source registry.

## 4. Phase 1 — semantic catalog, metric registry và relation registry

### Đã làm

- Chuyển metric registry thành code có contract đầy đủ, không còn chỉ là danh sách tên.
- Mỗi metric có formula, grain, unit, caveat và quy tắc sử dụng.
- Semantic catalog liên kết semantic ref với physical schema, type, unit, grain, aggregation/filter hợp lệ, time semantics và answerability.
- Relation registry có 10 edge với join keys, cardinality, input/output grain, scope, interpretation, fanout effect, dedupe strategy, temporal validity và traps.
- Có pathfinding và reject khi relation edge không tồn tại.
- Cấm join chéo platform category và shop category.
- Bổ sung catalog slicing để chỉ đưa lát semantic liên quan vào planner.

### File chính

- `src/gladiators/domain/metrics.py`
- `src/gladiators/domain/catalog.py`
- `src/gladiators/domain/relations.py`
- `src/gladiators/domain/intent_registry.py`
- `eval/semantic_linking.json`
- `eval/relation_acceptance.json`

### Acceptance hiện tại

- 10/10 relation edge có executable acceptance.
- Semantic linking fixtures kiểm từng exposed semantic object.
- Metric registry và catalog/physical mapping có unit test.

## 5. Phase 2 — typed IR, validator, compiler và executor

### Đã làm

- Tạo `LogicalQueryPlan` IR version `1.0` với op set đóng.
- Có typed node, predicate, requested output shape, grain và semantic refs.
- Plan validator hoàn toàn deterministic, không dùng LLM để quyết định safety.
- Validator kiểm catalog ref, operator, relation path, scope country/date, grain transition, fanout/dedupe, unit/currency, temporal rule, budget và unsupported claim.
- Compiler sinh SQL từ IR; user value được parameterize.
- SQLGlot kiểm AST; không nhận raw SQL từ user/LLM.
- DuckDB executor read-only theo hiệu lực, chỉ register validated DataFrame/view, giới hạn memory/thread/result rows và kiểm postcondition sau execute.
- Chặn DDL, COPY, ATTACH, external file/network function, multi-statement và SQL không do compiler tạo.
- Query rỗng là kết quả hợp lệ (`result_count=0`), không tự biến thành lỗi hoặc abstain.
- Evidence mang lineage đủ để verifier và UI dùng.

### File chính

- `src/gladiators/planner/query_ir.py`
- `src/gladiators/planner/validator.py`
- `src/gladiators/planner/compiler.py`
- `src/gladiators/planner/executor.py`
- `src/gladiators/planner/analytical.py`
- `src/gladiators/analytics/tools.py`
- `eval/planner_mutations.json`
- `eval/operator_acceptance.json`
- `eval/empty_result_acceptance.json`
- `tests/test_planner_mutations.py`

### Acceptance hiện tại

- Mutation suite tĩnh được validator/gate chặn hoặc caveat đúng.
- Compiler parameterization và executor hardening có test.
- Query viết tay/template chạy đúng trên dữ liệu thật.
- Empty-result acceptance có executable fixture.

## 6. Phase 3 — ba intent V1 thành certified macros

### Đã làm

- Ba intent `sales_decline`, `similar_product`, `promotion_effectiveness` được đăng ký thành certified macros có version và plan hash.
- Workflow dispatch theo `tool_plan`, không còn `if/elif` hard-code riêng cho từng intent.
- Macro có evidence contract; evidence sai loại sẽ bị chặn.
- Giữ nguyên gate, entity resolution, caveat và numeric verifier của V1.
- Independent oracle được tách khỏi production planner/compiler/metric code.

### File chính

- `src/gladiators/planner/macros.py`
- `src/gladiators/agent/tool_dispatch.py`
- `src/gladiators/agent/workflow.py`
- `eval/questions.json`
- `eval/independent/build_golden.py`
- `eval/independent/golden_v2.json`
- `scripts/build_independent_oracle.py`

### Acceptance hiện tại

- 60 câu V1 vẫn là parity anchors.
- Macro registry, plan hash và evidence contract có test.
- Không claim oracle độc lập là human-reviewed: phần human semantic review vẫn còn thiếu.

## 7. Phase 4 — open analytical L0–L3

### Đã làm

- P7 deterministic semantic parser sinh `AnalyticalRequest` typed.
- Parser liên kết measures/dimensions vào catalog ref, khóa country/date, grouping, ranking, comparison, output shape và ambiguity.
- Có complexity classifier L0–L4 độc lập với lời tự khai của LLM.
- A19 được tách thành các nhóm định danh: `A19-CAT`, `A19-OP`, `A19-METRIC`, `A19-PLAN`; data absent dùng rule riêng.
- P8 open planner chỉ được chọn semantic refs và typed IR trong catalog slice.
- Planner có tối đa một vòng repair dựa trên deterministic validator feedback.
- Các template analytical đã có:
  - `highest_revenue_day`
  - `listing_count`
  - `highest_price_listing`
  - `highest_monthly_sold_listing`
  - `top_shop_by_listing_count`
- UI renderer trả kết quả theo khối gọn: Kết quả, Phạm vi, Cách tính, Giới hạn, Độ tin cậy; mọi numeric claim gắn evidence ID.
- Gate giữ các boundary quan trọng: không trộn VND/IDR, không gọi proxy là doanh thu thật, không causal claim, không profit/conversion/SKU nếu data absent.

### File chính

- `src/gladiators/planner/semantic_parser.py`
- `src/gladiators/planner/open_planner.py`
- `src/gladiators/agent/parser.py`
- `src/gladiators/agent/gate.py`
- `src/gladiators/agent/workflow.py`
- `src/gladiators/ui.py`
- `src/gladiators/ui_flow.py`
- `eval/questions_v2.json`
- `eval/questions_a19.json`
- `eval/questions_ambiguity.json`
- `eval/questions_boundaries.json`

### Acceptance hiện tại

- Offline V2/core, A19, boundary và ambiguity suites đã đạt 100% trong lượt kiểm trước.
- Coverage matrix đạt 158/158 requirements.
- Cần chạy lại report chuẩn nếu muốn đóng gói artifact báo cáo mới nhất.

## 8. Phase 5 — L4, QueryRiskScore, critic và N-version

### Khung đã implement

- `QueryRiskScore` chấm deterministic theo relation count, fanout/grain, temporal, metric mới, cross-country, schema-linking, entity margin, plan shape và anomaly.
- Threshold mặc định: `tau1=3`, `tau2=6`.
- Escalation ladder:
  - rủi ro thấp: single/template;
  - L3 hoặc risk trung bình: P9 critic;
  - L4 hoặc risk cao: P8 primary + P10 alternate planner;
  - so sánh normal form và execution signature;
  - nếu kết quả bất đồng: P11 adjudicator chỉ được chọn `primary`, `alternate` hoặc `unresolved`;
  - unresolved/failure: `A19-PLAN`, không chọn ngẫu nhiên.
- P10 ưu tiên method riêng `plan_analytical_alternate` để giữ blind/independent prompt.
- Candidate nào cũng phải qua cùng deterministic validator/compiler.
- N-version consensus không được coi là proof; false-consensus vẫn phải đo với oracle độc lập.
- Critic và N-version có kill-switch riêng, mặc định OFF.
- Sáu composite L4 fixtures chạy offline qua hai fake planner đồng thuận.

### File chính

- `src/gladiators/planner/risk.py`
- `src/gladiators/planner/critic.py`
- `src/gladiators/planner/consensus.py`
- `src/gladiators/agent/llm.py`
- `src/gladiators/agent/workflow.py`
- `eval/questions_critic.json`
- `eval/l4_acceptance.json`
- `tests/test_v1.py`
- `tests/test_planner_mutations.py`

### Sửa lỗi mới nhất

Groq P1 chỉ trả top-level intent nên làm mất `analytical_kind` trong `slots`. Hậu quả là template `top_shop_by_listing_count` nhận kind rỗng và fail. Đã sửa `AgentRuntime._parse()` để khi P1 và deterministic parser đồng ý intent:

- merge typed deterministic slots vào parsed request;
- giữ `analytical` payload deterministic cho open analytical;
- ghi adjustment `slots_from_deterministic_parser` hoặc `analytical_from_deterministic_parser` vào trace.

Đã thêm regression test `test_llm_parser_keeps_deterministic_analytical_template_slots`.

Evaluator cũng đã đổi independent golden lookup sang fail-safe `.get(...)`; thiếu kind/gold trả `False` thay vì làm evaluator crash bằng `KeyError`.

### Real Groq smoke test mới nhất

Provider/key mới hoạt động và user đã cho phép gửi câu hỏi/context đánh giá tới Groq. Lệnh đã chạy:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py \
  --suite eval/questions_critic.json \
  --runs 1 \
  --provider groq \
  --enable-critic \
  --output /tmp/gladiators_phase5_groq_l3_smoke_fixed
```

Kết quả:

- 4 cases completed.
- 6 API calls thành công, 0 provider/network failure.
- 7,365 total tokens.
- Parser fallback 0%.
- Complexity classification trên các row có plan: 100%.
- End-to-end accuracy 25%.
- Crash rate 25%.
- Hai case bị `A19-PLAN`, một case có `ValidationError` ở evaluator/runtime boundary.

Các con số 25% này là **diagnostic**, chưa phải Phase 5 acceptance.

Nguyên nhân đã thấy:

1. `cq02`: Groq critic trả response rỗng; runtime fail-closed thành `A19-PLAN` với lý do `Groq trả response rỗng.`
2. `cq03`: critic false reject một deterministic valid plan. Nó cho rằng `entity.shop`, `entity.product_listing` không map vào `products_clean.csv` và `listing_count` không được có trong expected schema. Critic hiện không được cung cấp catalog/physical mapping và node semantics đầy đủ, nên suy luận sai.
3. `cq04`: evaluator chỉ ghi `ValidationError`, chưa lưu traceback nên chưa biết schema cụ thể nào fail.

Report tạm nằm ngoài repo tại:

- `/tmp/gladiators_phase5_groq_l3_smoke_fixed/2026-07-20.json`
- `/tmp/gladiators_phase5_groq_l3_smoke_fixed/checkpoint.json`

### Việc cần làm tiếp theo để đóng Phase 5

Thứ tự đề nghị:

1. Sửa evaluator để mỗi crash ghi `error_message` và traceback rút gọn, không chỉ `type(exc).__name__`.
2. Chạy riêng `cq04` để xác định `ValidationError` đến từ Groq structured output, request parsing hay critic schema.
3. Siết P9 prompt/input contract:
   - cung cấp semantic catalog slice và physical mapping tương ứng;
   - giải thích rõ `Scan.expected_schema` là semantic output contract, có thể chứa field phục vụ downstream aggregate theo IR contract;
   - yêu cầu critic không được báo lỗi chỉ vì tự suy đoán physical columns;
   - cân nhắc chỉ nhận issue có `issue code + node_id + violated invariant/ref` kiểm được.
4. Xử lý response rỗng bằng retry bounded đúng telemetry; kiểm Groq `max_tokens`/reasoning token behavior với `openai/gpt-oss-20b`.
5. Chạy lại 4 case critic ít nhất 3 runs để đo stability/pass³.
6. Viết/chốt runner Phase 5 riêng cho `eval/l4_acceptance.json`. File này không cùng schema với `scripts/run_evaluation.py`, nên không đưa thẳng vào runner V1.
7. Runner L4 phải bật `enable_nversion=True`, dùng deterministic P7 để cô lập P8/P10/P11, ghi:
   - primary/alternate validity;
   - plan disagreement;
   - result disagreement;
   - adjudicated/unresolved;
   - denotation accuracy với oracle độc lập;
   - false-consensus;
   - latency/token/cost theo case.
8. Làm rõ gold semantics cho 6 câu L4. Câu hiện tại dùng từ “so sánh” nhưng chưa nói aggregation (max/mean/median), nên chưa đủ chặt để chấm denotation. Nên sửa wording/gold thành aggregation rõ ràng trước khi claim accuracy.
9. Chạy ablation công bằng, cùng provider/model/suite/runs và chỉ đổi một nấc:
   - single;
   - single + critic;
   - N-version;
   - N-version + adjudicator khi disagreement.
10. Chỉ bật kill-switch sau khi L4 end-to-end ≥80%, disagreement/false-consensus đo được và latency trong budget. Nếu chưa đạt, giữ OFF.

## 9. Eval và coverage artifacts

Các artifact mới/được mở rộng:

- `eval/coverage_matrix.json`: 158 requirements, 158 satisfied, ratio 1.0.
- `eval/questions.json`: 60 V1 parity anchors.
- `eval/questions_v2.json`: open analytical core fixtures.
- `eval/questions_critic.json`: L3 critic smoke/acceptance.
- `eval/l4_acceptance.json`: 6 composite L4 fixtures.
- `eval/questions_a19.json`: A19 taxonomy.
- `eval/questions_ambiguity.json`: ambiguity/clarification.
- `eval/questions_boundaries.json`: data/claim boundaries.
- `eval/operator_acceptance.json`: IR operator coverage.
- `eval/relation_acceptance.json`: relation edge coverage.
- `eval/semantic_linking.json`: catalog linking coverage.
- `eval/planner_mutations.json`: validator/gate adversarial cases.
- `eval/empty_result_acceptance.json`: empty-is-valid behavior.
- `eval/independent/`: oracle code/golden không import production planner/compiler.

`scripts/build_eval_coverage_matrix.py` sinh matrix từ executable registries/fixtures; không chỉnh tay summary để làm xanh coverage.

## 10. Provider, secrets và cấu hình

- Provider đang chọn: Groq.
- Model trong config hiện tại: `openai/gpt-oss-20b`.
- API key nằm trong `.env`, không được đưa vào tài liệu, trace, commit hoặc chat.
- Đổi key bằng:

```bash
bash scripts/configure_groq.sh
```

- `configs/default.yaml` giữ `planner.enable_critic=false`, `planner.enable_nversion=false` đúng rollout policy.
- Runtime hiện chủ yếu đọc kill-switch từ environment:

```bash
GLADIATORS_ENABLE_CRITIC=1
GLADIATORS_ENABLE_NVERSION=1
```

Lưu ý: `create_runtime()` chưa truyền explicit critic/nversion clients/flags ngoài defaults. `GET /capabilities` hiện hard-code `nversion_enabled: false` thay vì đọc `runtime.enable_nversion`; đây là việc nhỏ cần sửa trước khi bật production.

## 11. Worktree chưa commit

Không xóa các thay đổi hiện tại. Nhóm file đang modified/untracked gồm:

- Runtime/API/UI: `src/gladiators/agent/*`, `src/gladiators/api.py`, `src/gladiators/ui.py`, `src/gladiators/ui_flow.py`, `src/gladiators/contracts.py`.
- Domain/data: `src/gladiators/domain/*`, `src/gladiators/data/*`, semantic manifest.
- Planner stack: toàn bộ `src/gladiators/planner/`.
- Eval/scripts: các suite V2, independent oracle, coverage builders, `scripts/run_evaluation.py`.
- Tests: `tests/test_v1.py`, `tests/test_planner_mutations.py`.
- Docs/config/deps: `README.md`, `docs/V2_Unified_Architecture.md`, `configs/default.yaml`, `requirements.txt`.

Trước khi commit nên chạy:

```bash
git diff --check
PYTHONPATH=. .venv/bin/pytest -q
git status --short
```

Không commit `.env`, `/tmp` report hoặc trace chứa nội dung không cần thiết.

## 12. Definition of done còn lại

Phase 5 chỉ được đánh dấu hoàn tất khi có report versioned chứng minh:

- L4 end-to-end/denotation accuracy ≥80%.
- Disagreement rate và false-consensus rate đo được bằng oracle độc lập.
- Ablation từng nấc escalation có số, cùng provider/model/suite.
- Plan stability/pass³ đạt ngưỡng kiến trúc.
- Latency L4/N-version trong budget mục 15.3.
- Không regression 60 câu V1, mutation suite và boundary suite.
- Human review phần gold semantics được ghi nhận; nếu chưa có thì report phải ghi rõ pending, không claim “answer every dataset question”.

Sau Phase 5, Phase 6 vẫn là conditional external integration. Không tự động chuyển sang Phase 6 chỉ vì Phase 5 code đã có.


---

## 13. Review chống-hallucination 21/07 — kết quả audit + kế hoạch sửa (ĐÃ thực thi — xem 13.6)

Ngày review: 21/07/2026. Phạm vi: toàn bộ đường sinh câu trả lời (`workflow._generate` → `verifier`), planner stack (`open_planner`, `critic`, `consensus`, `risk`, `validator`, `compiler`, `executor`), LLM adapters, và đối chiếu với `docs/V2_Unified_Architecture.md` (v2.3). Mục này là **kế hoạch được duyệt trước khi code** — mỗi fix dưới đây đã được thiết kế ở mức implementation-ready (file, hàm, hành vi, edge case, test contract) nhưng **chưa merge dòng nào**.

### 13.1. Mô hình mối đe dọa — 4 lớp hallucination của hệ này

| Lớp | Mô tả | Lá chắn hiện có | Trạng thái |
| --- | --- | --- | --- |
| H1. Số bịa trong answer | LLM generation viết số không có trong evidence | `verify_numeric_claims` full-answer scan + fallback deterministic | **Có nhưng thủng** (13.2.1–13.2.3) |
| H2. Kết luận bịa (không phải số) | Câu chữ nhân quả/forecast/cùng-SKU/gọi proxy là doanh thu thật | KHÔNG có — chỉ dặn trong prompt | **Trống hoàn toàn** (13.2.4) |
| H3. LLM hallucinate trong planner path | Critic bịa issue → false-reject plan đúng (cq03); adjudicator chọn phe không lý do; planner sinh ref ngoài catalog | Validator + catalog slice chặn planner tốt; critic/adjudicator hở | **Hở ở critic/adjudicator** (13.2.6–13.2.7) |
| H4. Provider failure biến thành abstain sai | Groq trả rỗng → A19-PLAN dù plan đúng (cq02) | Fail-closed nhưng không retry | **Availability bug** (13.2.8) |

Điểm mạnh đã xác nhận (không cần sửa): LLM không bao giờ tính số (quyết định #2 giữ đúng ở mọi đường); planner chỉ chọn semantic refs, ref ngoài catalog slice bị reject kèm bounded repair; compiler sinh SQL từ AST whitelist + parameterize, executor read-only + postconditions; plan invalid không được escalation bypass (`risk.py` trả blocked); relation registry không có edge nối 2 hệ category — join chéo là structurally impossible.

### 13.2. Gap chi tiết + thiết kế fix

#### 13.2.1. [P0] Verifier tolerance quá lỏng — số sai-nhưng-gần đi lọt

- **File:** `src/gladiators/agent/verifier.py`
- **Vấn đề:** `rel_tol=0.011` (1,1%) — ví dụ thật: evidence `745.078`, LLM viết `750` → chênh 0,67% → **PASS dù sai**. Đây là cửa hallucination số im lặng nhất hiện nay.
- **Thiết kế:** thay bằng display-rounding tolerance đúng V2 §9.2: token hiển thị `d` chữ số thập phân pass khi `|shown − true| ≤ max(0.5×10^(−d), 1e-9×max(1,|true|))`. Cần hàm mới `scan_number_tokens(text) -> list[(value, decimals)]` (mở rộng `scan_numbers` hiện có; `decimals` = độ dài phần thập phân của token sau khi đổi `,`→`.`).
- **Đã kiểm tương thích:** deterministic answers dùng `:g`/`:.0f` không sinh thousand-separator; `745.078` (d=3, tol 5e-4) khớp `745.077922`; `2059.66` (d=2) khớp `2059.660617`; `2060` (d=0, tol 0.5) khớp — làm tròn đúng vẫn pass; `750` fail. Cặp test hiện hành (10 pass / 12 fail) và cặp 0.9/0.8 không đổi hành vi.
- **Giữ tham số `tolerance` làm escape hatch** (`None` = strict mới, giá trị cụ thể = legacy isclose) để không phá caller bên ngoài.
- **Giới hạn ghi nhận:** số kiểu VN `1.580` (chấm nghìn) sẽ parse thành 1.58 → fail-closed về deterministic. Locale normalization là target §9.2, chưa làm vòng này.

#### 13.2.2. [P0] Fake citation không bị bắt

- **File:** `verifier.py`
- **Vấn đề:** LLM có thể bịa `[ev:abc:0007]`; hiện chỉ evidence_id THẬT bị strip khỏi vùng scan, citation bịa chỉ fail "tình cờ" nếu digit bên trong không khớp evidence nào.
- **Thiết kế:** regex `\[(ev:[^\[\]\s]+)\]` bắt mọi citation token; token không thuộc tập `{e.evidence_id}` → thêm vào `unknown_citations` → `passed=False`. Sau khi bắt, strip toàn bộ citation token (kể cả lạ) khỏi vùng scan số để không sinh nhiễu kép. Thêm key `unknown_citations` vào dict trả về (additive, không phá consumer).
- **Cẩn trọng:** chỉ match prefix `ev:` — KHÔNG validate bracket bất kỳ, vì product name thật chứa bracket (`[Tặng Quạt Đơn 180k]...`) và test hiện dùng id ngắn `[e1]` (không match pattern → bỏ qua, đúng ý).

#### 13.2.3. [P0] String evidence values gây degraded oan

- **File:** `verifier.py`
- **Vấn đề:** `allowed` chỉ nhận int/float; evidence dạng chuỗi (shop_name `"Glad2Glow Official Store"` chứa digit `2`, date `"2026-07-01"`, product_name) khi xuất hiện trong answer bị scan thành "số bịa" → `degraded=True` oan. Đường open-analytical trả string evidence thường xuyên.
- **Thiết kế:** thêm `item.value` (khi là str, non-empty) vào `ignored_strings` (hiện chỉ strip `attrs`) — giá trị evidence dạng chuỗi LÀ text có bằng chứng, phải loại khỏi vùng scan trước khi quét số.

#### 13.2.4. [P0] Wording gate — lớp H2 đang trống hoàn toàn

- **File mới:** `src/gladiators/agent/wording.py`; tích hợp tại `workflow._generate`.
- **Vấn đề:** V2 §11.3 quy định 13 wording rules enforce bằng "regex list + P4 + judge" — hiện KHÔNG có dòng code nào. LLM nói "voucher làm tăng doanh số" (nhân quả bịa) → không gì chặn; numeric verifier chỉ nhìn số.
- **Thiết kế `check_wording(answer) -> list[violation]`:**
  - So khớp trên văn bản đã fold dấu (tái dùng logic normalize hiện có) để bắt cả có-dấu lẫn không-dấu.
  - **Negation-aware:** loại mệnh đề phủ định trước khi quét — regex dạng `\b(khong|chua|not|no)\b[^.;:\n]{0,90}` xóa từ từ-phủ-định đến hết cụm. Bắt buộc, vì caveat chuẩn của chính hệ thống chứa từ cấm ("**không** chứng minh khuyến mãi **gây ra** thay đổi").
  - Rule set khởi điểm (conservative để không chặn oan, mở rộng dần theo eval):
    1. `causal_language`: "gay ra", "lam tang", "lam giam", "khien", "nho voucher", "nho khuyen mai", "tac dong lam", "hieu qua ro ret", "chung minh hieu qua", "cho thay hieu qua" (KHÔNG cấm "hiệu quả" trần — xuất hiện hợp lệ khi diễn đạt lại câu hỏi).
    2. `same_sku_claim`: "cung mau", "cung sku", "chinh xac cung loai".
    3. `forecast_claim`: "du bao", "se tang", "se giam", "thang sau se".
    4. `revenue_missing_estimate_label` (positive requirement): answer nhắc "doanh thu/revenue" mà thiếu "uoc tinh"/"proxy"/"estimated" → violation (V2 rule 2).
- **Tích hợp:** trong `_generate`, sau numeric verify: `verdict.passed AND not check_wording(answer)` mới nhận answer; violation → ghi vào `verifier_feedback` cho vòng retry; 2 lần fail → deterministic fallback (đúng ladder V2 §9.3). **Chỉ gate answer do LLM sinh** — deterministic template đã được review theo contract (đã kiểm: template promotion chứa cụm phủ định vẫn qua gate an toàn nhờ negation-strip nếu sau này muốn gate cả hai).
- **Test cases:** "Voucher làm tăng doanh số" → violation; "không chứng minh khuyến mãi gây ra thay đổi" → sạch; "Doanh thu ngày 03/07 là X" (thiếu "ước tính") → violation; "doanh thu proxy ước tính" → sạch.

#### 13.2.5. [P0] Caveats không đi vào generation context

- **File:** `workflow._generate`.
- **Vấn đề:** V2 §5.1: caveat là "bắt buộc chèn vào evidence payload — không phải tùy chọn của generator". Metric registry đã có caveats đầy đủ nhưng `_generate` không đưa vào context → LLM không có nguyên liệu để giữ nhãn "ước tính"/"proxy"/"không nhân quả".
- **Thiết kế:** `caveats = sorted({c for e in evidence if (spec := METRICS.get(e.metric)) for c in spec.caveats})` → `context["caveats"]`; mở rộng `context["rules"]` khớp wording gate (cấm nhân quả/forecast/cùng-SKU, bắt buộc "ước tính", giữ caveats khi diễn giải). Import `METRICS` cục bộ trong hàm để tránh import cycle.

#### 13.2.6. [P1] Critic false-reject — LLM hallucinate issue chặn plan đúng (cq03)

- **File:** `src/gladiators/planner/critic.py` (+ 1 nhánh nhỏ trong `workflow`).
- **Vấn đề thật từ smoke Groq 20/07:** critic phán `entity.shop` "không map vào products_clean.csv" và `listing_count` "không được có trong expected_schema" — cả hai SAI, vì critic không được cấp catalog/physical mapping, tự suy đoán rồi bịa issue → plan đúng bị A19-PLAN. Critic hallucinate chính là một dạng hallucination phải trị.
- **Thiết kế 2 lớp:**
  1. **Input đủ ngữ cảnh** — thay vì gửi `(question, plan)` trần, `PlanCritic` tự dựng payload: `{plan, catalog_slice (đúng các ref plan dùng, KÈM physical mapping), relations (spec của các Join trong plan), guidance}`. Guidance nêu rõ: validator đã xác nhận refs/filter-op/join-path/budget/schema — không báo lại; `expected_schema` là semantic output contract được phép chứa field phục vụ downstream node; không suy đoán physical columns (mapping nằm trong `catalog_slice.physical`); chỉ báo issue có `node_id` tồn tại + invariant kiểm được. Giữ nguyên signature `critique_plan(question, payload)` ở mọi client (payload là dict opaque → không phải sửa 4 adapter).
  2. **Lọc issue sai kiểm chứng được** — với plan đã qua deterministic validator: issue thuộc nhóm validator phủ đầy đủ `{missing_semantic_object, wrong_filter, wrong_join_path, budget_exceeded, schema_invalid}` → **drop** (máy chứng minh được là phán sai — đúng lớp lỗi cq03); issue có `node_id` không tồn tại trong plan → drop. Chỉ giữ nhóm semantic ngoài khả năng kiểm cơ học: `grain_mismatch, fanout_risk, unit_mismatch, temporal_mismatch, unsupported_claim`. Issue bị drop ghi vào `planning_meta["critic"]["dropped"]` (chỉ thêm key khi non-empty — xem guardrail 13.5).
- **Kiểu trả về:** đổi `review()` → `CriticReview(issues, dropped)` (dataclass mới); `CriticOutput` pydantic giữ nguyên làm schema structured-output cho LLM (không thêm field vào schema gửi model).

#### 13.2.7. [P1] Adjudicator chọn phe không cần lý do

- **File:** `src/gladiators/planner/consensus.py`.
- **Vấn đề:** V2 §7.9: P11 "chỉ chọn khi nêu được issue định danh". Schema có `reason_issue_type` nhưng code không bắt buộc — LLM chọn `primary` với `reason_issue_type=null` vẫn được nhận = phán bừa không kiểm được.
- **Thiết kế:** sau `model_validate`, nếu `verdict != "unresolved"` và `not reason_issue_type` → raise `ConsensusError` (fail-closed như unresolved → A19-PLAN). Test hiện hành trả `"wrong_filter"` → không regression.

#### 13.2.8. [P1] Groq empty response → abstain oan (cq02)

- **File:** `src/gladiators/agent/llm.py` (`GroqLLMClient._chat`).
- **Thiết kế:** content rỗng → đúng 1 bounded retry cùng tham số (đếm `telemetry["empty_retries"]`), vẫn rỗng → raise như cũ. Không retry vô hạn, không thay đổi ladder fail-closed. Kèm theo (đúng next-step #4 mục 8): kiểm hành vi `max_tokens`/reasoning-token của `openai/gpt-oss-20b` — codebase đã có sẵn `reasoning_effort="none"` cho model Qwen; cân nhắc nâng `max_tokens` cho call site critic/planner nếu đo thấy truncation là nguyên nhân response rỗng.

#### 13.2.9. [P2] Ops nhỏ đúng next-steps mục 8

- `/capabilities`: `"nversion_enabled": runtime.enable_nversion` thay vì hard-code `False` (`api.py` dòng 45).
- Evaluator crash: ghi thêm `error_message` (cắt 500 ký tự) + `traceback` rút gọn (format_exception limit≈6, cắt 2000 ký tự cuối) tại `scripts/run_evaluation.py` khối `except` (~dòng 153) — mở khóa chẩn đoán cq04 (`ValidationError` chưa rõ nguồn).

### 13.3. Thứ tự thực thi đề nghị + phụ thuộc

1. **Verifier (13.2.1–13.2.3)** — một file, tự chứa; chạy lại toàn suite ngay sau đó vì mọi đường đều đi qua verifier.
2. **Wording gate + caveats context (13.2.4–13.2.5)** — phụ thuộc verifier mới (dùng chung shape `verifier_feedback` trong `_generate`).
3. **Critic + adjudicator + Groq retry (13.2.6–13.2.8)** — độc lập với nhau, có thể làm song song.
4. **Ops (13.2.9)** — bất kỳ lúc nào.
5. **Tests mới đi cùng từng bước:** verifier (fake citation fail; string value không degraded; 750-vs-745.078 FAIL; "745.08" PASS), wording (4 case ở 13.2.4), critic filter (issue thiếu node_id bị drop; nhóm deterministic-covered bị drop khi plan valid; `grain_mismatch` vẫn chặn), adjudicator fail-closed khi thiếu reason, Groq empty-retry (mock client).
6. Sau khi xanh: chạy lại **60 câu V1 parity + mutation suite offline** trước khi ghi nhận hoàn thành; các fix KHÔNG đổi contract API (`AgentResponse` chỉ thêm key additive trong `verification`/`planning`).

### 13.4. Nhận diện nhưng CHỦ ĐỘNG HOÃN (target, không thuộc đợt này)

- **Claims JSON + binding path/unit/tier** (V2 §9.1–9.2 Pass 2 đầy đủ): cần Response Generator xuất `{answer_vi, claims}` — thay đổi lớn ở P2 prompt + verifier; làm sau khi wording gate ổn định. Đây là mảnh lớn nhất còn lại giữa verifier hiện tại và target §9.
- **Locale number normalization** (kiểu VN `1.580,5`): thuộc Pass 1 target; hiện fail-closed là chấp nhận được.
- **Machine-generated gate rules từ quality report + đủ 19 rule A1–A19**: đúng lộ trình build order 21/07 của DS1, không gộp vào đợt chống-hallucinate.
- **Human review gold semantics + real-provider eval pass³**: điều kiện đóng Phase 5 (mục 12), không thay đổi.

### 13.5. Guardrails regression đã xác minh trong test suite hiện hành

- `test_top_shop_join_runs_after_critic_acceptance`: assert **exact dict** `planning["critic"] == {"provider": "fake", "issues": []}` → mọi key mới trong critic meta phải conditional (chỉ xuất hiện khi non-empty).
- `test_plan_critic_issue_blocks_execution_without_tool_call`: issue `grain_mismatch` node `n4` phải tiếp tục chặn plan (thuộc nhóm GIỮ của filter — không được drop).
- `test_numeric_verifier_blocks_invented_number` và `test_numeric_verifier_ignores_overlapping_product_names`: giữ nguyên hành vi với tolerance mới.
- N-version test dùng adjudicator trả `reason_issue_type="wrong_filter"` → tương thích fail-closed mới.
- Test id kiểu `[e1]` không match pattern citation `ev:` → không bị chặn oan.

### 13.6. Trạng thái thực thi 21/07 — ĐÃ MERGE (regression-free)

Toàn bộ 9 fix ở 13.2 đã được hiện thực đúng thiết kế. Test: **153 passed / 5 failed**; 5 lỗi còn lại **đều pre-existing, không phải regression** (2 Windows cp1252 `read_text()` thiếu `encoding="utf-8"`: `test_eval_has_exactly_60_cases`, `test_independent_oracle...`; 1 Windows permission `0600`: `test_trace_redaction_and_permissions`; 2 classifier gap L4→L2: `test_composite_l4...[l4c01/l4c05]` — đúng next-step #8 mục 8, gold semantics chưa đủ chặt). Trên Linux/CI 3 lỗi encoding/permission sẽ xanh; 2 lỗi L4 là việc riêng của gold-semantics.

**File thay đổi:**

| File | Nội dung |
| --- | --- |
| `src/gladiators/agent/verifier.py` | Viết lại: `scan_number_tokens` (value+decimals), display-rounding tolerance, `CITATION` regex + `unknown_citations`, string evidence values vào ignored. `tolerance` param giữ làm escape hatch (`None`=strict mới). Dict trả về thêm key `unknown_citations` (additive). |
| `src/gladiators/agent/wording.py` | **File mới**: `check_wording(answer)`, negation-aware, 4 nhóm rule (causal/same-sku/forecast/revenue-label). |
| `src/gladiators/agent/workflow.py` | `_generate`: inject `context["caveats"]` từ METRICS + mở rộng `rules`; gate `verdict.passed AND not check_wording(...)`; feedback gộp numeric+citation+wording. Nhánh critic: thêm key `planning["critic"]["dropped"]` (conditional). |
| `src/gladiators/planner/critic.py` | Viết lại: `_critic_payload` (catalog slice + physical + relations + guidance), `CriticReview(issues, dropped)`, lọc issue nhóm `_DETERMINISTIC_COVERED` và node_id không tồn tại. `CriticOutput` giữ nguyên làm schema LLM. |
| `src/gladiators/planner/consensus.py` | Adjudicator: `verdict != unresolved` mà thiếu `reason_issue_type` → `ConsensusError` fail-closed. |
| `src/gladiators/agent/llm.py` | `GroqLLMClient._chat`: empty content → 1 bounded retry + `telemetry["empty_retries"]`. |
| `src/gladiators/api.py` | `/capabilities`: `nversion_enabled` đọc `runtime.enable_nversion`. |
| `scripts/run_evaluation.py` | Khối crash ghi thêm `error_message` (≤500) + `traceback` rút gọn (≤2000). |
| `tests/test_antihallucination.py` | **File mới**: 16 test phủ 13.2.1–13.2.8 (verifier ×4, wording ×7 param, critic filter ×3, adjudicator fail-closed ×1, Groq empty-retry ×1). |

**Guardrail regression đã xác minh xanh:** `test_top_shop_join_runs_after_critic_acceptance` (exact dict `{"provider":"fake","issues":[]}` — key `dropped` chỉ xuất hiện khi non-empty); `test_plan_critic_issue_blocks_execution_without_tool_call` (`grain_mismatch`/`n4` vẫn chặn); N-version adjudicator test cũ (`reason_issue_type="wrong_filter"`) vẫn pass; 3 cặp `test_numeric_verifier_*` giữ hành vi.

**Contract API additive-only:** `AgentResponse` không đổi field; chỉ thêm key trong `verification` (`unknown_citations`) và `planning["critic"]` (`dropped`) — an toàn cho consumer/UI hiện có.

**Còn nợ (chủ động hoãn — xem 13.4):** claims JSON + binding path/unit/tier (Pass 2 đầy đủ §9) là mảnh lớn nhất còn lại; locale number normalization; 19-rule gate machine-generated; human review gold + real-provider pass³. Đây KHÔNG phải điều kiện của đợt chống-hallucinate này nhưng là mục tiêu Phase-5-close.

### 13.7. Dọn test hygiene cross-platform + phát hiện golden stale (21/07)

Ngoài 9 fix hallucination, đợt này dọn thêm test-code hygiene để suite chạy được nhất quán mọi OS (không đổi logic sản phẩm):

- Thêm `encoding="utf-8"` vào **toàn bộ** `Path(...).read_text()` trong `tests/test_v1.py` và `tests/test_planner_mutations.py` (11 call site). Đây là anti-pattern tiềm ẩn: trên Windows default codec là cp1252 → file fixture tiếng Việt bị méo/crash. Sau fix: 2 case `test_composite_l4[l4c01/l4c05]` từng `assert 'L2'=='L4'` **tự khỏi** — nguyên nhân thật là fixture `l4_acceptance.json` bị đọc sai encoding làm câu hỏi tiếng Việt méo → classifier ra L2, KHÔNG phải gold-semantics gap như phỏng đoán ban đầu ở mục 8 #8.
- Guard assert Unix-permission `0o600` bằng `sys.platform != "win32"` (Windows không có chmod POSIX).

**Kết quả suite: 157 passed / 1 failed** (từ 137/5). 1 lỗi còn lại là **pre-existing, không phải regression và ngoài scope hallucination**:

- `test_independent_oracle_matches_frozen_gold_and_imports_no_production_code`: `artifact_hash` mismatch — golden `89a9b19ba967b8e9` (đóng băng trong `eval/independent/golden_v2.json`) ≠ hash hiện tại `2e2e835c0818cbf9` của `(products_clean, product_snapshot_metrics, shop_info_clean)`. **CSV là LF (không phải CRLF), working tree không sửa CSV nào** → đây là golden **stale so với lần regenerate CSV gần nhất** (pipeline thêm cột derived cho transition metrics sau khi golden được freeze). Trước đợt này lỗi bị che bởi `UnicodeDecodeError` của `read_text()` trên Windows; giờ encoding đã fix nên lộ ra assertion thật — nó cũng đỏ trên Mac/Linux ở state 155e1e5.
- **KHÔNG regenerate golden để ép xanh** (đúng cảnh báo mục 9: "không chỉnh tay để làm xanh coverage"). Việc đúng: DR2 chạy lại `eval/independent/build_golden.py` và **human review** trước khi re-freeze — đúng definition-of-done mục 12 ("Human review phần gold semantics"). Ghi vào backlog, không thuộc đợt chống-hallucination.

### 13.8. Locale number normalization — bug thật bắt được live qua Groq (21/07)

Sau khi UI `/flow` deploy (13.6/13.7), test tay qua Groq thật (`gpt-oss-120b`, query "cửa hàng nào bán mỹ phẩm có doanh thu cao nhất...") cho thấy **generation fallback về deterministic template mọi lần**, dù câu trả lời LLM sinh ra đúng nội dung. Mục 13.4 đã liệt "locale number normalization" là hoãn — bug này chứng minh nó không chỉ lý thuyết, đã xảy ra live và tốn thêm 1 lượt gọi Groq mỗi request.

**Nguyên nhân (xác nhận bằng cách trace raw text trước verify):** Groq sinh câu trả lời dùng ký tự "typographic" thay vì ASCII thường:
- Dấu gạch nối ngày tháng `2026‑07‑03` dùng **non-breaking hyphen U+2011**, không phải `-` (U+002D) — evidence value `"2026-07-03"` không match theo string-replace cũ → cả 3 phần ngày (`2026`, `07`, `03`) bị bộ quét số tách thành 3 "số bịa" riêng.
- Số lớn `298 219 517 806` phân cách bằng **narrow no-break space U+202F** — không rơi vào token liền, verifier tách thành 4 số riêng (298, 219, 517, 806) không khớp evidence `298219517806`.

Cả hai đều bị `verify_numeric_claims` chặn đúng thiết kế (fail-closed, không hallucinate số), nhưng gây fallback không cần thiết cho một câu trả lời vốn đã đúng.

**Fix trong `src/gladiators/agent/verifier.py`:**
1. `_normalize_unicode_punctuation()` — map các biến thể Unicode dash (`‐‑‒–—−`) về `-` ASCII và các biến thể Unicode space (nbsp, narrow no-break space, figure space, thin space) về ` ` thường, chạy đầu tiên trong `verify_numeric_claims` trước mọi bước khác.
2. `_normalize_thousands_grouping()` — gộp cụm số bị dấu phân cách nghìn (`,`, `.`, khoảng trắng) tách thành nhiều token rời thành một số liền, **chỉ khi ≥2 lần lặp nhóm-3-chữ-số** (tránh nhầm với số thập phân dạng `745.078` — chỉ 1 lần lặp, giữ nguyên hành vi display-rounding cũ).
3. `_date_variants()` — evidence value dạng ISO date (`YYYY-MM-DD`) được so khớp thêm với biến thể `/` và `.` trước khi loại khỏi vùng quét số.

**Test:** 5 case mới trong `tests/test_antihallucination.py` (gộp space-separated, comma-separated, không gộp nhầm single-group decimal, date đổi separator ASCII, và case tái hiện đúng bug thật với `chr(0x2011)`/`chr(0x202F)`). Full suite: **162 passed / 1 failed** (giữ nguyên đúng golden-stale ở 13.7, không regression).

**Verify live:** chạy lại đúng câu hỏi qua Groq thật sau fix — `generation.fallback=False`, `attempts=1`, không còn `errors` key (pass verify ngay lần đầu).
