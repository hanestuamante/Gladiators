# ARCHITECTURE PROPOSAL — Gladiators

> Phạm vi: 12 slide kiến trúc, dùng sau phần Introduction/Bối cảnh.
> Thông điệp xuyên suốt: **Gladiators không để LLM “tự trả lời”; hệ thống chỉ cho LLM lập kế hoạch trong một không gian ngữ nghĩa đóng, còn mọi con số, bằng chứng và quyền phát ngôn đều được kiểm soát bằng code.**

## Quy ước trạng thái dùng trong deck

- **Core available:** nền tảng đã có trong codebase và tiếp tục được giữ.
- **Hardening:** hạng mục đã có defect/spec cụ thể, cần hoàn tất acceptance trước khi tuyên bố hoàn chỉnh.
- **Proposed:** kiến trúc đã thiết kế nhưng chưa triển khai.
- **Conditional:** chỉ bật khi đủ test, artifact và phê duyệt; mặc định fail-closed.
- Final update: 13h45 - 2607

---

## Slide 1 — Architectural Thesis: Intelligence có kiểm chứng

**Thông điệp chính**

Gladiators là một **Open-World Verifiable Product Intelligence Agent**: đủ linh hoạt để hiểu câu hỏi tự nhiên và lập kế hoạch phân tích, nhưng mọi kết quả đều nằm trong một miền bảo đảm có thể kiểm tra.

**Nội dung trên slide**

- **Bounded intelligence:** LLM chỉ parse, chọn semantic object và lập plan; không tự tính số, không tự viết SQL/Pandas, không tự quyết định admission.
- **Deterministic truth path:** metric, join, grain, dedupe, execution và postcondition đều do code kiểm soát.
- **Evidence before language:** câu trả lời chỉ được sinh từ evidence đã admit; mỗi claim phải truy ngược được tới dữ liệu và phép tính.
- **Safe usefulness:** khi thiếu dữ liệu hoặc không đủ quyền suy luận, hệ thống **clarify / trả lời một phần / abstain có cấu trúc**, không đoán.
- Giá trị cốt lõi: **mở rộng coverage mà không mở rộng bề mặt hallucination tương ứng**.

**Chart cần vẽ**

Một sơ đồ “sandwich” 3 lớp:

1. Trên: **Flexible AI** — Natural Language Understanding, Planning, Explanation.
2. Giữa: **Deterministic Control Plane** — Semantic Catalog, Validator, Gate, Verifier.
3. Dưới: **Reproducible Data Plane** — Contracted Data, Compiler/Executor, Evidence Ledger.

Ở cạnh phải đặt kết quả: **Answer / Clarify / Partial / Abstain**. Làm nổi bật câu: *“LLM proposes; code disposes.”*

---

## Slide 2 — End-to-End Architecture: một pipeline, nhiều chốt kiểm soát

**Thông điệp chính**

Kiến trúc gồm 9 stage có trách nhiệm và “negative responsibility” rõ ràng; không module nào vừa hiểu câu hỏi, vừa tính số, vừa tự xác nhận chính nó.

**Nội dung trên slide**

- **S1–S4 · Understand & Control:** dual parser → capability router → entity resolution → gate trước thực thi.
- **S5 · Compute/Augment:** analytical engine nội bộ; reference và external là các nhánh song song, có cờ bật riêng.
- **S6 · Ground:** Evidence Store chỉ nhận record đã qua admission, kèm tier, hash, grain, caveat và lineage.
- **S7–S9 · Communicate & Verify:** generator diễn giải → claim verifier kiểm độc lập → output gate kiểm sufficiency, wording và tier mixing.
- Mỗi stage xuất typed contract; mọi verdict đều ghi `rule_id` vào trace.

**Chart cần vẽ**

Flow ngang:

`Question → S1 Parse → S2 Route → S3 Resolve → S4 Gate → S5 Plan/Execute → S6 Evidence → S7 Generate → S8 Verify → S9 Output Gate`

Thêm ba nhánh kết thúc sớm từ S3/S4/S8: `Clarify`, `Partial/Abstain`, `Deterministic fallback`. Tô màu:

- xanh: deterministic/code;
- tím: LLM;
- vàng: evidence;
- đỏ: checkpoint fail-closed.

---

## Slide 3 — Two-Axis Routing: tách “độ khó” khỏi “nguồn có thể trả lời”

**Thông điệp chính**

Gladiators không đánh đồng câu hỏi phức tạp với câu hỏi thiếu dữ liệu. Router dùng hai trục độc lập để chọn đúng đường xử lý và giới hạn claim.

**Nội dung trên slide**

- **Analytical Complexity L0–L4:** từ lookup một bảng đến plan DAG nhiều bước, nhiều tín hiệu và cross-check.
- **Answerability C1–C4:** dataset đủ → cần reference → cần external context → không thể trả lời bằng dữ liệu hợp lệ.
- Ví dụ đối lập: câu C1 vẫn có thể là L4; câu lookup L0 vẫn có thể là C4 nếu biến `profit_margin` không tồn tại.
- Router dựa trên capability table, coverage manifest, source flags và `missing_vars`—không route bằng cảm tính của model.
- External không được fetch “cho chắc”: **nội bộ đủ thì dừng ở internal path**.

**Chart cần vẽ**

Ma trận 5×4:

- Trục dọc: L0 → L4.
- Trục ngang: C1 → C4.
- Trong từng cột ghi route: `Internal`, `+Reference`, `+External context`, `Structured abstain`.

Đánh dấu ba ví dụ: `listing count = C1·L0`, `multi-signal shop ranking = C1·L4`, `profit lookup = C4·L0`. Mục tiêu chart là cho thấy hai trục trực giao.

---

## Slide 4 — Executable Semantic Layer: “ngữ nghĩa nghiệp vụ as code”

**Thông điệp chính**

Thay vì để LLM đoán schema mỗi lần, Gladiators mã hóa toàn bộ ngữ nghĩa thành một semantic layer versioned, executable và test được.

**Nội dung trên slide**

- **Semantic Catalog:** entity, dimension, measure, derived metric, alias đa ngôn ngữ, unit, grain, aggregation hợp lệ, caveat và answerability.
- **Metric Registry:** một metric chỉ có **một định nghĩa**; tool/compiler chỉ được tham chiếu, không được định nghĩa lại công thức.
- **Typed Schema Graph:** join edge khai báo keys, direction, cardinality, fanout, grain transition, dedupe và temporal validity.
- **Coverage Manifest:** phân biệt `available`, `proxy_only`, `zero_variance`, `absent`, `intentionally_hidden`; là biên chính thức của điều hệ thống được phép claim.
- Không cần GraphRAG/graph database: với 5 bảng quan hệ, graph có giá trị nhất là **metadata thực thi trong code**, không phải thêm một hệ quản trị mới.

**Chart cần vẽ**

Tam giác ba thành phần:

- đỉnh 1: `Metric Registry`;
- đỉnh 2: `Schema Graph`;
- đỉnh 3: `Coverage Manifest`;
- tâm: `Executable Semantic Catalog`.

Từ tâm nối sang `Parser/Planner`, `Validator`, `Compiler`, `Gate`, `Evidence caveats` để thể hiện một nguồn ngữ nghĩa duy nhất phục vụ toàn pipeline.

---

## Slide 5 — Safe Analytical Planning: NL → Typed IR → deterministic execution

**Thông điệp chính**

Khả năng phân tích mở được tạo bằng **grammar đóng**, không bằng quyền chạy raw SQL.

**Nội dung trên slide**

- Planner nhận câu hỏi chuẩn hóa + catalog slice + schema graph + guardrail; không thấy raw CSV, physical column hay metric formula.
- Output duy nhất là `LogicalQueryPlan` dạng DAG, dùng 12 operator whitelist: `Scan, ResolveValue, Filter, Join, Dedupe, Aggregate, DeriveMetric, TemporalCompare, Rank, Similarity, Project, Union`.
- Plan Validator kiểm semantic ref, type/unit, join path, grain/fanout, temporal constraint, output shape và budget trước khi compile.
- Compiler dùng SQL AST parameterized; DuckDB chỉ chạy `SELECT`, external access/extension/file-network function bị khóa.
- Sau execute, hệ thống kiểm cardinality, schema, uniqueness, range, sample size, coverage và fanout inflation trước khi phát evidence.

**Điểm mạnh cần nhấn**

**LLM không viết phép tính; LLM chỉ tham chiếu phép tính đã được governance phê duyệt.** Construct ngoài IR không được “lách” bằng raw SQL mà đi tới `A19-OP` để mở rộng có kiểm soát.

**Chart cần vẽ**

Pipeline biên dịch:

`Natural-language request → Semantic refs → LogicalQueryPlan DAG → Static Validator → SQL AST Compiler → Hardened DuckDB → Postconditions → Evidence`

Vẽ một “bức tường cấm” phía trên compiler với ba mục: `No raw SQL`, `No arbitrary formula`, `No external data in IR`.

---

## Slide 6 — Risk-Adaptive Orchestration: dùng thêm intelligence đúng nơi cần

**Thông điệp chính**

Gladiators không áp multi-agent cho mọi câu hỏi; mức kiểm tra tăng theo rủi ro của chính query plan.

**Nội dung trên slide**

- `QueryRiskScore` là rule-based: số join, N:M/fanout, grain transition, temporal op, derived metric mới, ambiguity, plan depth và anomaly.
- **Low risk / L0–L2:** deterministic template hoặc một planner; tối ưu latency và cost.
- **Medium risk / L3:** thêm independent plan critic để bắt lỗi chọn sai metric/join dù plan vẫn chạy được.
- **High risk / L4:** 2–3 candidate plan độc lập, blinded → deterministic comparison → bounded adjudication.
- Một orchestrator duy nhất giữ quyền quyết định; validator/compiler/executor/verifier vẫn là code module, không phải agent.

**Điểm mạnh cần nhấn**

**Không coi model consensus là proof.** Đồng thuận chỉ là tín hiệu; deterministic invariants và independent execution check mới là lớp bảo đảm chính.

**Chart cần vẽ**

Một “escalation ladder” ba bậc:

`Template/Single planner → + Critic → + N-version plans & adjudicator`

Dưới mỗi bậc ghi `risk`, `latency/cost`, `check strength`. Mũi tên chỉ tăng bậc khi `QueryRiskScore` vượt ngưỡng.

---

## Slide 7 — Semantic Alignment & Context Carrier [PROPOSED]

**Thông điệp chính**

Evidence đúng chưa đủ; hệ thống còn phải chứng minh rằng **plan và answer đang trả lời đúng câu hỏi người dùng**.

**Nội dung trên slide**

- `RequestDigest` giữ requested measures, dimensions, entities, countries, qualifiers, output shape và sub-request.
- `ContextBundle` tạo payload có kiểu theo từng stage, gắn `context_hash`, `plan_hash`, prompt version, dataset version, budget và guard hits; Evidence gốc luôn bất biến.
- Ba chốt A22 deterministic:
  - **A · request ↔ plan:** bắt measure bị bỏ/thay, sai shape, entity chưa bind;
  - **B · plan ↔ evidence:** bắt evidence không phủ output đã hứa;
  - **C · evidence ↔ answer:** phần trả lời và phần chưa trả lời đều phải hiện rõ.
- Entity extraction chuyển sang **ID-first, namespace-aware**; phân biệt `item ID/category ID` với thị trường Indonesia; quote chỉ là hint.
- Compound query được tách thành sub-request: trả phần làm được, nêu rõ phần bị giới hạn, không silent substitution.

**Bằng chứng vấn đề thúc đẩy thiết kế**

Baseline DR40 có trường hợp verifier pass vì số/citation đúng nhưng kết quả không đáp ứng measure được hỏi. Alignment layer đóng đúng khoảng trống giữa **grounded** và **relevant**.

**Chart cần vẽ**

Chuỗi ba cầu kiểm:

`RequestDigest --A22(A)--> Plan --A22(B)--> Evidence --A22(C)--> Answer`

Phía dưới đặt `ContextBundle + context_hash` chạy xuyên cả bốn khối. Gắn ví dụ lỗi: *“hỏi discount → plan trả listing_count”* bị chặn trước execution.

---

## Slide 8 — Evidence-Native Answering: từ con số về tới nguồn trong một trace

**Thông điệp chính**

Mỗi câu trả lời là một sản phẩm có lineage, không phải văn bản “nghe hợp lý”.

**Nội dung trên slide**

- Mỗi Evidence record có `evidence_id`, tool/version, input hash, dataset/content hash, source tier, grain key, value/unit, observed time, caveat và mapping status.
- Composite query bổ sung `plan_id`, parent evidence, `QueryPlanRecord` và `QueryExecutionRecord`: truy ngược **claim → evidence → execution → plan → semantic object**.
- Generator phải xuất answer theo contract: Scope → Answer → Evidence → Calculation → Explanation → Confidence → Limitations → Next action.
- Mỗi numeric/date/money/percent claim bind đúng `value + unit + evidence_id + evidence_path`; trùng số ngẫu nhiên ở evidence khác không được pass.
- Verifier quét toàn answer độc lập với claims; fail → regenerate có feedback → deterministic fallback → cuối cùng abstain nếu vẫn không chứng minh được.

**Điểm mạnh cần nhấn**

**Correct number, wrong evidence, wrong unit hoặc wrong question đều là fail—không phải “gần đúng”.**

**Chart cần vẽ**

Một “lineage chain” với ví dụ một claim:

`“32 listings changed price” → ResponseClaim → ev:... → result row/path → execution hash → plan hash → catalog metric → dataset artifact hash`

Gắn bốn con dấu kiểm: `value`, `unit`, `path`, `tier`.

---

## Slide 9 — Gate Architecture: an toàn nhưng vẫn hữu ích

**Thông điệp chính**

Gate không chỉ từ chối; nó chọn hành vi an toàn hữu ích nhất tại đúng checkpoint.

**Nội dung trên slide**

- **Pre-gate:** chặn claim vượt dữ liệu—profit/cost, SKU, order-level, forecast, causal effect, zero-variance field, cross-currency.
- **Dependency checkpoint:** chỉ chạy delta khi đủ snapshot; không materialize hoặc gọi tool tiếp nếu prerequisite fail.
- **Admission gate:** record injection/span sai/provenance thiếu bị loại trước Evidence Store; mapping chưa chắc chỉ được `context_only`.
- **Output gate:** chặn causal wording, tier mixing, unlabeled external source, excluded evidence và answer thiếu core evidence.
- Bốn outcome có chủ đích: `Allow`, `Clarify`, `Partial + limitation`, `Structured abstain + answerable alternative`.

**Điểm mạnh cần nhấn**

Fail-closed không đồng nghĩa “không trả lời”: C4 luôn mở bằng **phần có thể trả lời**, sau đó mới nêu giới hạn và dữ liệu cần bổ sung.

**Chart cần vẽ**

Decision tree:

`Đủ dữ liệu? → Đúng scope? → Entity rõ? → Plan hợp lệ? → Evidence đủ? → Claims verified?`

Các lá gồm `Answer`, `Clarify`, `Partial`, `Abstain`. Bên cạnh mỗi nhánh fail ghi một ví dụ nghiệp vụ, không dùng mã rule nội bộ trên chart chính.

---

## Slide 10 — External Intelligence as a Sidecar [CONDITIONAL]

**Thông điệp chính**

Nguồn ngoài mở rộng **bối cảnh**, không xuyên vào lõi tính toán và không làm suy yếu tính tái lập của số nội bộ.

**Nội dung trên slide**

- Router chỉ gọi external khi phát hiện `missing_vars`; internal đủ thì không fetch.
- Nhánh live search: bounded planner → Tavily adapter → immutable cache/SHA-256 → deny-filter → injection guard → extractor không có tool → span verification → mapper → admission.
- Live web luôn có trần `context_only`; không dùng làm competitor-price fact, không cross-tier arithmetic, không suy ra quan hệ nhân quả.
- Internal và external xuất hiện ở hai section/claim/tier riêng; lỗi mạng/quota/extraction không làm mất câu trả lời nội bộ.
- Ba mode: `live`, `record`, `cache_only`; mặc định **OFF/cache_only**, cho phép demo replay khi mất mạng và audit đúng nguồn/thời điểm.

**Security boundary cần nêu**

Không scrape Shopee; chặn domain trước extractor; content web là untrusted; field chỉ được dùng khi bind đúng byte span trong cached result.

**Chart cần vẽ**

Hai lane song song:

- Lane A: `Internal Planner/Executor → btc_dataset Evidence`.
- Lane B: `Live Search → Cache → Guard → Extract → Span Verify → context_only Evidence`.

Hai lane chỉ gặp nhau tại Evidence Store/Response Generator, với một “firewall” ghi: `No external data enters Typed IR / DuckDB`.

---

## Slide 11 — Reliability Architecture: test cả kết quả, đường đi và bất biến

**Thông điệp chính**

Eval không phải bước cuối; nó là một tầng của kiến trúc và là điều kiện mở capability.

**Nội dung trên slide**

- **Layer 1 · Trajectory:** parse, route, tool order, gate/checkpoint, source tier và admission có đúng không.
- **Layer 2 · Deterministic correctness:** result/denotation, numeric accuracy, citation binding, plan validity, cardinality và postcondition.
- **Layer 3 · Language quality:** wording, helpfulness, limitation và claim boundary; judge không thay deterministic oracle.
- **[Proposed]** Independent oracle không import code production; metamorphic tests kiểm quote/no-quote, bỏ dấu, paraphrase, filter order và noise.
- **[Proposed]** Cassette record/replay khóa theo model + prompt + tool schema + context hash + dataset version; replay không mở socket.
- Trace dùng hash và artifact manifest để tái lập, khoanh lỗi một câu theo chuỗi request → plan → execution → evidence → claim.

**Các ngưỡng nên đưa nhỏ ở cuối slide**

- Citation precision mục tiêu: **1.00**.
- Unsupported-claim leakage: **0**.
- Cache replay determinism: **100%**.
- Legacy behavior chỉ được migrate sau parity gate.

**Chart cần vẽ**

Test pyramid 4 tầng từ dưới lên:

`Contracts/Mutations → Planner/Executor/Postconditions → E2E Trajectory & Replay → Judge/Human Review`

Bao quanh pyramid bằng vòng `Go/No-Go Gate`; ghi rõ capability mới chỉ bật khi toàn bộ artifact bắt buộc hiện diện.

---

## Slide 12 — Delivery Architecture & Competitive Strength

**Thông điệp chính**

Kiến trúc được triển khai theo dependency để mỗi bước tăng coverage mà không phá bảo đảm cũ.

**Nội dung trên slide**

| Trạng thái             | Khối kiến trúc                                                                                                                                     | Giá trị                                                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Core available** | Semantic catalog/graph, typed IR, validator/compiler, certified macros, evidence/verifier/gate foundation                                             | Lõi phân tích có cấu trúc, audit được                             |
| **Hardening**      | Cache`dataset_version`, enforce cardinality, pre-materialization budget, explicit truncation, guarded internal context, evidence-derived confidence | Biến contract “đã khai báo” thành contract “được cưỡng chế” |
| **Proposed next**  | `ContextBundle`, A22 alignment, entity/ID/country extraction, compound request, cassette, independent DR40 oracle                                   | Đảm bảo không chỉ “đúng số” mà còn “đúng câu hỏi”        |
| **Conditional**    | Tavily live/record/cache rehearsal và external acceptance                                                                                            | Mở rộng bối cảnh mà vẫn giữ external ngoài analytical core         |

**Năm điểm mạnh chốt với giám khảo**

1. **Semantic control thay cho prompt engineering thuần túy.**
2. **General planning nhưng không raw SQL—coverage mở, execution đóng.**
3. **Evidence lineage và per-claim verification end-to-end.**
4. **Risk-adaptive orchestration—multi-agent có lý do, có trần và đo được.**
5. **Fail-closed, reproducible, external-ready mà không overclaim.**

**Câu kết slide**

> **Gladiators biến LLM từ “nguồn sự thật” thành “giao diện lập kế hoạch”; sự thật vẫn thuộc về data contract, deterministic execution và evidence có thể kiểm chứng.**

**Chart cần vẽ**

Roadmap bốn lớp theo mũi tên:

`Core available → Contract hardening → Semantic alignment → Conditional external`

Trên mỗi lớp ghi một acceptance gate; dưới cùng là một đường baseline không đổi: `Typed contracts + no raw SQL + evidence-first + fail-closed`.

---

## Nguồn tổng hợp nội bộ

- `docs/V2_Unified_Architecture.md`
- `docs/External Data Integration.md`
- `docs/2207.md`
- `docs/2507.md`
- `docs/Context_harness20% and TC fix 2607.md`
