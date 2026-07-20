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

