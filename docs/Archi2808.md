# Archi2808 — Đặc tả kiến trúc và trạng thái triển khai hiện tại

> **Chốt kiểm tra:** 28/08/2026, nhánh MVP_Dai_V2, HEAD 6a5af5e.
>
> **Mốc source cuối:** d14fa75. Commit 6a5af5e chỉ thêm dữ liệu thô, không đổi
> mã dưới src/gladiators.
>
> **Phạm vi:** kiến trúc đang chạy sau vòng Spec2308. SolutionSpec2808 là đặc tả
> thi công tương lai và không được dùng để mô tả năng lực hiện tại.
>
> **Nguyên tắc nguồn sự thật:** code và artifact hiện có thắng tài liệu. Spec2308
> là yêu cầu đích; một mục có trong spec nhưng chưa được gọi từ runtime phải ghi
> là chưa nối, không được nâng thành năng lực đã hoàn tất.

---

## 0. Cách dùng tài liệu này

Archi2808 là cơ sở phát triển hiện tại, thay thế Archibefore2208. Tài liệu phục
vụ bốn mục đích:

1. mô tả đúng đường chạy của một request;
2. định nghĩa các bất biến an toàn không được phá;
3. chỉ rõ phần nào của Spec2308 đã nối runtime, phần nào chỉ là công cụ đo;
4. lưu các khoảng trống đã kiểm chứng để người phát triển không xây tiếp trên
   một giả định sai.

### 0.1. Ký hiệu trạng thái

| Trạng thái | Nghĩa |
| --- | --- |
| **WIRED** | Có call site trong đường chạy production hoặc API đang phục vụ |
| **SHADOW** | Có tính toán và trace, mặc định không đổi gate/plan/answer |
| **OPS/EVAL** | Công cụ đo, report hoặc giao diện vận hành; không phải inference runtime |
| **PARTIAL** | Có một phần nhưng chưa đủ acceptance hoặc chưa được nối |
| **ABSENT** | Spec có nêu nhưng source/API/artifact hiện tại không có |

### 0.2. Bằng chứng chốt

| Phép kiểm | Kết quả ngày 28/08/2026 |
| --- | --- |
| Toàn bộ pytest, thư mục tạm ngắn trên Windows | **1207 passed, 1 skipped** |
| Metadata binding verifier | 7 bảng, 219 cột, 86 catalog object, 10 relation, 33 metric, 12 invariant, 0 lỗi |
| Test lỗi đường dẫn dài chạy riêng | 1 passed |
| Cassette vật lý trong checkout | **0 file JSON**; chỉ có artifacts/search_cassettes/REVIEW.md |
| UI schema graph | **Không có** src/gladiators/ui_schema.py và không có route /schema-graph |
| Smoke runtime: macro / analytical / external OFF / hybrid OFF | Lần lượt `A-ALLOW` / `A-ALLOW` / `A14-LIVE` / `A14-HYBRID-PARTIAL`; các response có số đều verify qua |
| Conversation + plan cache | Lượt sau kế thừa `country=vn`; query lặp chuyển cache miss → hit, giá trị giữ nguyên và evidence_id được sinh mới |
| Kiểm tính bất biến của Evidence | **Assignment vào `Evidence.value` thành công**; model hiện chưa `frozen` |
| Probe contract evidence của macro | Contract bị cố ý đổi để không khớp nhưng response vẫn `A-ALLOW`; guard hiện chưa chặn đường allow end-to-end |

Lần pytest đầu với thư mục tạm dài nằm dưới workspace đạt 1206 passed, 1
skipped và lỗi một test khi Windows tạo đường dẫn quarantine quá dài. Chính test
đó qua khi dùng D:/tg28_archi_target; toàn suite sau đó qua với
D:/tg28_archi_full. Đây là lỗi môi trường đường dẫn, không phải assertion logic.

---

## 1. Mục tiêu và các bất biến cấp hệ thống

Hệ thống trả lời câu hỏi phân tích thương mại điện tử Việt Nam và Indonesia trên
dataset đóng băng gồm ba snapshot 01–03/07/2026.

Ràng buộc chi phối toàn kiến trúc:

> Mọi con số hiển thị phải truy vết được về evidence; hệ thống không được đoán,
> thay metric, bỏ filter hoặc thu hẹp scope trong im lặng.

Hệ quả:

- clarify và abstain là kết quả hợp lệ;
- LLM không có quyền quyết gate, tính số, tự đặt join key hoặc thực thi SQL tùy ý;
- plan phải dùng semantic ref đã đăng ký và qua validator;
- compiler/executor chỉ đọc dữ liệu;
- external evidence chỉ là context, không được nhập làm số nội bộ;
- một câu trả lời có số đúng nhưng trả sai câu hỏi vẫn bị chặn;
- một tập số riêng lẻ đều có evidence nhưng mâu thuẫn số học vẫn bị chặn.

### 1.1. Bốn lớp kiểm độc lập

| Lớp | Câu hỏi | Điểm chạy chính | File |
| --- | --- | --- | --- |
| Gate | Có được phép trả lời không? | S4, cập nhật S5/S9 | agent/gate.py |
| Alignment | Có giữ đúng measure, scope, shape, filter và tiền đề không? | S5, S9 | agent/alignment.py |
| Verifier | Mọi số/claim có evidence, tier, provenance và lineage không? | S8 | agent/verifier.py |
| Consistency | Các evidence nội bộ có tự nhất quán số học không? | sau generate, trước gate-out | agent/consistency.py |

Không lớp nào thay thế lớp nào. Ví dụ, một số có thật trong evidence vẫn có thể
trả lời nhầm câu hỏi; verifier sẽ qua nhưng alignment phải chặn. Tương tự,
min/median/max đều có evidence riêng vẫn có thể mâu thuẫn; consistency phải chặn.

---

## 2. Luồng kiến trúc tổng thể

~~~mermaid
flowchart TB
    Q["Câu hỏi + session_id tùy chọn"]

    subgraph PRE["S1–S4 · Hiểu và cấp phép"]
      S1["S1 PARSE<br/>deterministic + LLM tùy chọn<br/>intent arbiter + phân loại route"]
      CM["Conversation inheritance<br/>sau parse, trước digest"]
      S2["S2 ROUTE · bước logic<br/>field do parser đặt, gate tính lại<br/>không có call site/timer riêng"]
      S3["S3 ENTITY-PRE<br/>chỉ mã listing/item trước gate<br/>tên tự do resolve ở S5 macro"]
      S4["S4 GATE-PRE<br/>route recheck + capability + value probe<br/>connectivity shadow"]
    end

    subgraph PLAN["S5 · Plan và execute"]
      M["Certified macro"]
      A["Open analytical<br/>synthesizer hoặc LLM IR"]
      R["Relation planner<br/>validator → compiler → DuckDB"]
      X["External pipeline<br/>mặc định OFF"]
      C["Plan-result cache<br/>(plan_hash, dataset_version)"]
    end

    subgraph OUT["S6–S9 · Bằng chứng và kiểm"]
      E["S6 Evidence dùng theo quy ước read-only<br/>Pydantic model hiện chưa frozen"]
      G["S7 Generate<br/>template hoặc ContextBundle"]
      V["S8 Verifier + lineage<br/>Consistency"]
      O["S9 Gate-out<br/>Alignment"]
    end

    REC["Vòng khôi phục có chặn<br/>wording repair · partial answer<br/>suggestions"]
    OBS["Trace · timing · budget verdict<br/>ledger · capability UI"]
    RESP["AgentResponse"]

    Q --> S1 --> CM --> S3 --> S4
    S1 -.->|route fields| S2
    S2 -.->|gate recheck| S4
    S4 -->|allow| M
    S4 -->|allow| A --> R
    S4 -->|allow external| X
    R <--> C
    M --> E
    R --> E
    X --> E
    E --> G --> V --> O
    O --> RESP
    O -->|reject| REC --> RESP
    S1 -.-> OBS
    S4 -.-> OBS
    R -.-> OBS
    O -.-> OBS
~~~

S1→S9 ở đây là phân rã trách nhiệm logic, không ánh xạ một-một sang call stack.
Trong code hiện tại, `classify_external_need` chạy trong parser và chạy lại trong
gate; không có lời gọi route độc lập giữa parse và entity. Tương tự, pre-gate chỉ
resolve entity dạng mã, còn tên sản phẩm tự do được `resolve_entity` xử lý sau
khi macro đã được chọn ở S5.

Mỗi điểm dừng có quyền trả `rule_id` ổn định và ghi trace cuối. Riêng kết quả typed
của entity resolver hiện chỉ nằm trong `ToolContext` trong lúc dispatch; response
chỉ giữ `resolved_listing_key`, không giữ score/margin đầy đủ.

### 2.1. Các package chính

| Package | Trách nhiệm |
| --- | --- |
| agent | Orchestrator, parse, entity, gate, alignment, verifier, consistency, conversation, suggestions, ledger |
| planner | IR, synthesizer, relation planning, validator, compiler, executor, cache, risk escalation |
| domain | Catalog, alias, qualifier, table, relation, metric, invariant, capability |
| analytics | Công cụ deterministic và chuyển kết quả thành Evidence |
| external | Router, search plan, record/replay, relevance, extract, admission, lexicon |
| insights | Insight mart, miner, PAM, dashboard |
| data | ArtifactRepository, data contract và dataset version |

---

## 3. Hợp đồng request và response

### 3.1. StructuredRequest

Các field chính:

| Field | Ý nghĩa |
| --- | --- |
| intent | Intent đã đăng ký hoặc unsupported:* |
| entity_text, entities | Thực thể được nêu |
| country, countries | Scope thị trường đã chuẩn hóa |
| date_range | Scope ngày |
| slots | Slot có kiểu và metadata bổ sung |
| analytical | AnalyticalRequest đã serialize |
| language | vi, id hoặc unknown |
| route_mode | internal_only, external_only, hybrid, clarify, abstain |
| external_purpose | campaign_context, market_event, product_external_info |
| requested_variables | Biến mà câu hỏi yêu cầu |

### 3.2. AgentResponse

Response gồm:

- trace_id;
- request sau parse/inheritance;
- gate gồm action, rule_id, reason và evaluated_phases;
- answer;
- danh sách evidence; `Evidence` hiện là Pydantic model mutable dù workflow đối
  xử với nó theo quy ước read-only;
- response claims;
- tool calls;
- `resolved_listing_key` nếu phân giải được; chưa có field chứa toàn bộ
  `EntityResolutionResult` trong `AgentResponse`;
- verification;
- telemetry LLM;
- planning metadata;
- context summary;
- degraded.

TraceStore ghi schema_version v1.1 cùng dataset_version vào
artifacts/traces/{trace_id}.json.

### 3.3. 11 intent hiện tại

| Intent | Đường chính |
| --- | --- |
| sales_decline | certified macro |
| similar_product | certified macro |
| promotion_effectiveness | certified macro |
| voucher_profile_rank | macro, mặc định bị khóa nếu profile chưa bật |
| voucher_coverage | certified macro |
| discount_bucket_observation | certified macro |
| dataset_coverage | certified macro |
| analytical_query | deterministic analytical template |
| open_analytical | synthesizer hoặc semantic planner |
| schema_relation_explain | prose từ relation registry |
| external_context | external pipeline |

---

## 4. S1–S4: hiểu câu hỏi và cấp phép

### 4.1. S1 Parse

MultilingualIntentParser chạy deterministic. Khi bật LLM parser, workflow gọi
provider và áp các luật precedence an toàn trước khi đưa kết quả qua intent
arbiter.

Các nguyên tắc merge:

- deterministic giữ quyền với route external/hybrid;
- unsupported taxonomy và capability contract không được LLM lách;
- field deterministic chỉ backfill vào ô LLM để trống;
- lỗi từ provider không được làm mất đường deterministic;
- parser scope có thể là always hoặc fallback_only;
- offline không gọi LLM.

Mặc định LLM parser OFF. Runtime factory đọc
GLADIATORS_ENABLE_LLM_PARSER=1 để bật.

### 4.2. Intent arbiter

agent/intent_arbiter.py cung cấp hai policy:

- **P-A**, mặc định: giữ kết quả sau precedence;
- **P-B**: chỉ nhận nhãn LLM khi deterministic rơi vào open/unregistered, nhãn
  LLM đã đăng ký và capability contract chứng minh request được phục vụ.

Workflow truyền llm_intent gốc, tức nhãn trước khi precedence ghi đè. Đây là sửa
lỗi d14fa75; nếu truyền parsed.intent sau precedence thì P-B trở thành code chết.

Hàm two_way_clarify tồn tại như helper thuần nhưng provider contract hiện vẫn
trả một nhãn. Vì vậy nhánh hỏi chọn giữa hai intent chưa phải luồng end-to-end.

Đo 44 câu với DeepSeek cho P-A và P-B cùng coverage 0.4545, risk 0.0,
over_refusal 0.4737. P-B không thắng nên mặc định vẫn P-A.

### 4.3. Bộ nhớ hội thoại

ConversationStore sống trong tiến trình:

- capacity 512 session;
- TTL 30 phút;
- slot cũ tối đa ba lượt;
- không có session_id thì hành vi stateless;
- endpoint reset xóa state theo session;
- chỉ ghi slot đã xác lập chắc chắn.

Điểm nối chính xác là **sau parse, trước RequestDigest**. Cách đặt này cho phép
country/date/entity ở lượt trước tham gia gate và planning của lượt sau.

Khi đổi topic, code giữ scope slot country/countries/date_range nhưng bỏ entity
topic-bound. Đây là chủ ý thực tế khác cách đọc cứng “xóa mọi slot khi đổi
topic”; tài liệu này mô tả code đang chạy.

### 4.4. S2 Route — trách nhiệm logic, chưa phải stage độc lập

external/router.py phân loại:

- internal_only;
- external_only;
- hybrid;
- clarify;
- abstain.

Live search OFF không được biến thành internal answer cho câu chỉ nguồn ngoài.
Hybrid giữ kết quả internal đã hoàn tất và hạ lỗi external thành limitation.

Call site thực tế nằm trong `MultilingualIntentParser.parse`; gate gọi lại cùng
hàm từ `slots.raw_text` để fail-closed nếu parser không bảo toàn route. Không có
`timer.stage("route")` cho bước phân loại này. Timer `route` hiện chỉ bọc lúc chạy
external pipeline cho request `external_context`.

### 4.5. S3 Entity

EntityResolver thực tế đi theo thang:

1. `product_listing_key` chính xác;
2. `item_id` chính xác nếu input toàn chữ số;
3. RapidFuzz WRatio trên tên sản phẩm, cộng recall từ rare token;
4. hợp nhất điểm BGE-M3 với lexical nếu GLADIATORS_ENABLE_BGE=1.

Không có nhánh lookup “tên chính xác” riêng; tên trùng tuyệt đối chỉ là một fuzzy
match có điểm tối đa.

Margin thấp dẫn tới clarify, không chọn bừa. expected_entity_types suy loại từ
semantic ref đã bind, nhưng hiện **chỉ ghi**
`planning.entity_type_constraint`. `EntityResolver.resolve/classify` không nhận
tham số loại và pool của resolver chỉ gồm product listing. Vì vậy A10 chưa thực
sự lọc ứng viên theo shop, brand, platform category hay shop shelf.

Chỉ entity dạng mã được kiểm trước gate. Entity tên tự do của macro được resolve
trong tool dispatch ở S5. Một mã không tồn tại phải thắng issue fixable như thiếu
country.

### 4.6. S4 Gate

ContractDrivenGate thu thập issue rồi chọn, không return ở rule đầu. Issue
không thể khắc phục có ưu tiên hơn issue người dùng có thể bổ sung.

Các nhóm kiểm:

- capability, unsupported, route, entity existence;
- intent registry và live-search admission;
- grain/admission khi có liên quan;
- cross-market currency;
- slot, country, voucher và scope;
- value existence;
- ref connectivity.

### 4.7. Value probe

agent/value_probe.py đọc artifacts/value_index.json để kiểm giá trị dimension
được nêu nhưng không tồn tại trước khi planning. Artifact hiện có trong
workspace.

Nếu artifact mất, probe không tự dựng lại và không được xem là bằng chứng giá
trị có thật. Cần chạy scripts/build_value_index.py khi dataset đổi.

### 4.8. Connectivity gate

planner/feasibility.py::connectivity_blockers tính các semantic ref có nối được
bằng relation registry hay không. Gate luôn ghi verdict vào
planning.connectivity.

Mặc định là SHADOW. Chỉ
GLADIATORS_ENABLE_CONNECTIVITY_GATE=1 mới cho blocker đổi kết quả thành
A-REFS-DISCONNECTED.

---

## 5. S5: lập kế hoạch và thực thi

### 5.1. Ba nhánh thực thi; hybrid ghép hai nhánh

| Nhánh | Khi dùng | Hợp đồng |
| --- | --- | --- |
| Certified macro | Intent đã có macro duyệt | check_macro_shape; evidence contract đã khai nhưng guard runtime còn PARTIAL |
| Open analytical | Câu phân tích có semantic request | synthesizer/template/LLM IR rồi validator |
| External | external_context hoặc phần ngoài của hybrid | context_only, provenance bắt buộc |

Với request thuần, ba đường trên loại trừ nhau. Với `route_mode=hybrid`, runtime
chạy internal macro/analytical trước rồi mới nối external context; live search OFF
vẫn giữ phần internal và trả `A14-HYBRID-PARTIAL`.

### 5.2. Certified macro

Macro mang certified shape, plan template/hash và evidence contract. Request sai
shape được chặn bằng alignment. Source cũng có nhánh dự định chặn evidence sai
contract bằng `A-MACRO-EVIDENCE-CONTRACT`, nhưng guard này **chưa có hiệu lực trên
đường allow bình thường**: nhánh `elif` evidence-alignment phía trước đã nhận mọi
macro `allow` có evidence, nên nhánh contract phía sau không tới được.

Probe end-to-end ngày 28/08 cố ý thay `sales_decline.evidence_metrics` bằng một
metric không thể khớp; `accepts_evidence(...)` trả false nhưng runtime vẫn trả
`A-ALLOW` với hai evidence thật. Các macro bình thường hiện vẫn phát đúng contract,
nhưng fail-closed guard cho trường hợp regression chưa được thực thi.

sales_decline và similar_product chỉ bind một entity. Nhiều entity không được
âm thầm chọn một.

### 5.3. Open analytical

Thứ tự:

1. DeterministicPlanSynthesizer thử grammar phát hành;
2. deterministic template nếu phù hợp;
3. LLM semantic planner nếu có provider;
4. validator;
5. risk escalation tùy cấu hình;
6. compiler;
7. DuckDB executor;
8. evidence builder.

LLM chỉ sinh IR semantic, không sinh SQL cho đường production. IR có 12 operator:
Scan, ResolveValue, Filter, Join, Dedupe, Aggregate, DeriveMetric,
TemporalCompare, Rank, Similarity, Project và Union.

Validator kiểm ref, filter, join path, grain, fanout, unit, temporal, claim,
budget, schema, tier và grouping. Compiler chỉ chấp nhận SELECT/UNION và executor
tắt external access/extensions trước khi khóa cấu hình.

### 5.4. Relation planner nhiều cạnh

WP-A1 đã nối vào synthesizer:

- chọn base artifact phủ nhiều ref nhất;
- gom ref còn thiếu theo artifact;
- tìm một cạnh đã chứng nhận từ tâm ProductListing tới từng artifact;
- hợp nhất tối đa ba cạnh theo RELATION_EDGE_BUDGET;
- sắp thứ tự deterministic theo path cost, risk và tên;
- tách predicate của bảng xa sang sau Join;
- chèn Dedupe khi cần bảo vệ grain;
- compiler chiếu ref qua relation metadata, không tự phát minh join key.

Đồ thị hiện là hình sao và mỗi path hợp lệ dài đúng một cạnh. “Nhiều cạnh” ở
đây là nhiều nan hoa trong cùng plan, không phải traversal tùy ý nhiều hop.
Registry đổi hình phải được review; code hiện fail-closed nếu path dài hơn một.

### 5.5. Qualifier binding

domain/qualifiers.py là registry cho bốn qualifier:

| Qualifier | Semantic ref |
| --- | --- |
| shop_official | dim.shop_official |
| shop_vacation | dim.shop_vacation |
| has_voucher | derived.has_structured_voucher |
| shopee_verified | dim.shopee_verified |

Negation được khớp trước surface dương. Qualifier trở thành Predicate có kiểu;
grouping cue không bị biến nhầm thành filter. Registry fail ở import nếu ref hoặc
operator không hợp lệ.

### 5.6. Một nguồn alias

CatalogObject.aliases cùng alias_overlay.json là nguồn binding. AliasIndex:

- chuẩn hóa Unicode/case/diacritic/whitespace;
- trả ambiguity thay vì chọn theo thứ tự tên;
- xử lý compound trap đã biết;
- hash index để cache/prompt không dùng alias cũ;
- dùng chung ở deterministic semantic parser và entity parsing.

Các bảng MEASURES/DIMENSIONS cứng trong DeterministicSemanticParser đã được xóa;
test khóa thuộc tính này.

alias_overlay.json chỉ được ánh xạ surface mới tới ref đã tồn tại, bắt buộc có
approved_by; overlay không được tạo metric hay định nghĩa nghiệp vụ mới.

### 5.7. Ba vòng lặp rẻ P/R/W

| Vòng | Điểm chạy | Giới hạn |
| --- | --- | --- |
| P — value probe | trước planning | tra exact folded value index; không đoán |
| R — context relax | semantic planner | nới catalog slice và thử lại đúng một lần |
| W — wording repair | sau verifier/alignment | chỉ sửa câu chữ, không sửa evidence/plan |

W chỉ chạy khi verifier hỏng nhưng answer alignment và question alignment vẫn
qua, consistency không có issue và enable_cheap_loops=True. Sau sửa phải verify
lại. Đây không phải vòng sinh câu vô hạn.

Không có các env GLADIATORS_ENABLE_VALUE_PROBE hoặc
GLADIATORS_ENABLE_WORDING_REPAIR trong source hiện tại. Value probe chạy mặc
định cho request analytical đủ điều kiện; context relax nằm trong open planner;
wording repair chịu enable_cheap_loops. Đây không phải các env được phác trong
Spec2308.

### 5.8. Kết quả rỗng và context relax

Zero-row hợp lệ đi ra A-ALLOW. Nếu chỉ có kết quả sau khi nới điều kiện người dùng
đã yêu cầu thì không được giả là cùng câu hỏi; hệ dùng
A-EMPTY-RESULT-RELAXED.

Context relax của planner chỉ nới **catalog slice** để lấy lại ref bị cắt, không
nới predicate nghiệp vụ.

### 5.9. Cache theo plan

PlanResultCache là LRU capacity 256, khóa:

~~~text
(plan_hash, dataset_version)
~~~

Cache lưu frame/row count/tie state, không lưu Evidence. Khi hit, Evidence mới
được dựng với trace_id hiện tại. Plan có rank tie ở mép cắt không được cache.

analytics/tools.py tra cache sau compile và trước execute, rồi ghi hit/stats vào
planning.plan_cache.

### 5.10. External pipeline

Đường hiện có:

~~~text
route → search planner → provider hoặc replay → relevance
      → web extract → admission → external Evidence
~~~

Các clamp bắt buộc:

- source_tier=external;
- mapping_status=needs_review;
- admission=context_only;
- provenance bắt buộc;
- không dùng external number làm internal metric;
- fail-closed khi replay miss, quota hoặc admission không qua.

Mặc định live search OFF và còn cần external_pipeline được cấu hình; chỉ đặt env
mà không có pipeline cũng không bật được.

#### Trạng thái lexicon

external/lexicon.py có normalize_to_dataset_value, injection guard và test. Tuy
nhiên không có call site nào từ workflow/pipeline; ngoài test, symbol chỉ xuất
hiện trong chính module. Vì vậy A12 nấc 1 là **thư viện có kiểm**, chưa phải
runtime wiring.

#### Trạng thái cassette

REVIEW.md ghi lịch sử sáu cassette và replay ổn định, nhưng sáu JSON nằm dưới
artifacts bị gitignore và không có trong checkout ngày 28/08. Do đó:

- không thể chạy lại replay acceptance chỉ từ repository hiện tại;
- chưa có chữ ký người duyệt trong REVIEW.md;
- không được mô tả “cassette sẵn sàng demo” cho đến khi file vật lý được cung
  cấp và người duyệt ký.

---

## 6. Metadata, binding và mô hình dữ liệu

### 6.1. Ba tầng

~~~mermaid
flowchart TB
    D["Tầng khái niệm<br/>Catalog · Relation · Metric · Invariant · Qualifier"]
    B["Tầng binding đã kiểm<br/>physical column · join key · handler · hash"]
    P["Tầng vật lý<br/>7 bảng · 219 cột"]
    F["Sai binding<br/>fail lúc build/import/verify"]
    D --> B --> P
    F -.-> B
~~~

Không semantic ref nào được nối thẳng xuống cột bằng suy đoán ở compiler.

### 6.2. Snapshot registry hiện tại

| Thành phần | Số lượng |
| --- | ---: |
| Table | 7 |
| Physical column | 219 |
| Catalog object | 86 |
| Catalog binding | 82 |
| Relation | 10: 4 join, 6 inline |
| Metric | 33 |
| Metric edge | 13 |
| Invariant | 12: 11 hard, 1 warning |
| Qualifier | 4 |
| Topic card | 14 |
| Intent | 11 |

Hash chốt từ scripts/verify_metadata_bindings.py:

| Registry | Hash |
| --- | --- |
| table | a3f67e54a1f181c4 |
| catalog | 7e448513d3c60b20 |
| relation | 2b7e06170852ab14 |
| metric | b906688ffa6ecb55 |
| invariant | f0ef05c393b16b9c |
| binding | 4d27637768639fb1 |

Hash là bằng chứng trạng thái, không phải hằng số nghiệp vụ. Registry đổi hợp lệ
thì hash phải đổi và tài liệu/release proof phải được cập nhật.

### 6.3. Catalog có hai trục

| Trục | Giá trị |
| --- | --- |
| answerability | exposed_as_dimension, exposed_as_measure, proxy_only, raw_but_unsafe, absent, context_only |
| analysis_role | physical_dimension, analysis_unit, computed_value |

analysis_unit là đơn vị đếm và có counting_key; nó không mặc nhiên là cột
GROUP BY. physical_dimension mới bắt buộc có physical binding để gom nhóm.

### 6.4. 12 invariant

| Invariant | Mức |
| --- | --- |
| INV-PRICE-SENTINEL-EXCLUDED | hard |
| INV-DEDUPE-BEFORE-AGGREGATE | hard |
| INV-SHELF-NOT-PLATFORM-CATEGORY | hard |
| INV-CURRENCY-NO-MIX | hard |
| INV-SNAPSHOT-SCOPE | hard |
| INV-DATE-RANGE-HONOURED | hard |
| INV-COUNTRY-COVERAGE | hard |
| INV-EMPTY-RESULT-IS-VALID | hard |
| INV-FILTER-LITERAL-IS-DATASET-VALUE | hard |
| INV-NO-CAUSAL-CLAIM | hard |
| INV-NO-INTERNAL-VOCABULARY | hard |
| INV-PROXY-NOT-VERIFIED-SALES | warning |

Registry invariant và handler đều resolve. Cần lưu ý kiến trúc dispatcher chưa
trở thành một call site duy nhất cho mọi stage: plan dùng dispatcher; một số
stage còn giữ enforcement trực tiếp đã có trước đó. Không được xóa enforcement
cũ chỉ vì handler đã đăng ký nếu chưa chứng minh call site thay thế.

### 6.5. Grain và khóa logic

| Bảng | Khóa logic |
| --- | --- |
| products_clean | country_code + shop_id + item_id + date |
| shop_info_clean | country_code + shop_id |
| category_list_clean | country_code + shop_id + shop_category_id + date |
| product_categories_clean | country_code + shop_id + item_id + category_id + date |
| category_platform_clean | path_country_code + category_id |
| product_snapshot_metrics | listing snapshot grain |
| product_transition_metrics | listing transition grain |

shop_info hiện chỉ có snapshot 03/07 nên relation belongs_to là enrichment
static_latest_only. Nếu dữ liệu có nhiều ngày, phải đổi contract sang join theo
ngày hoặc as-of join trước khi mở rộng.

### 6.6. Join được phép

~~~text
products → shop_info
  country_code, shop_id

products → product_categories
  country_code, shop_id, item_id, date

product_categories → category_list
  country_code, shop_id, category_id = shop_category_id, date

products → category_platform
  country_code = path_country_code, catid = category_id
~~~

### 6.7. Hai hệ category

| Hệ | Field | Nghĩa |
| --- | --- | --- |
| Platform | category_platform.category_id, products.catid/global_catids | taxonomy sàn |
| Shop shelf | category_list.shop_category_id, product_categories.category_id | kệ do shop tổ chức |

Cấm join shop category với platform category chỉ vì cùng tên category_id.

catid là top-level category; phần tử cuối global_catids là leaf. Không dùng
catid như category cụ thể nhất.

### 6.8. Referential coverage và fanout

Các bằng chứng dữ liệu giữ từ đợt kiểm binding:

- products.catid sang platform category: 0 orphan trên 3.341 snapshot;
- mọi ID trong global_catids: 0 orphan trên 9.951 ref;
- products sang shop_info: 0 orphan trên 3.341;
- product_categories sang category_list: 0 orphan trên 4.054;
- product_categories sang products: 5 orphan trên 4.054;
- 1.132 trên 3.341 snapshot không có product_categories.

Vì vậy quan hệ shop shelf phải dùng LEFT JOIN nếu cần giữ population. Listing có
thể thuộc nhiều shelf; aggregate toàn cục phải Dedupe về grain listing snapshot
trước khi đếm.

---

## 7. S6: Evidence và provenance

Workflow và các handler hiện **đối xử** với Evidence theo quy ước read-only; cache
cũng sinh Evidence mới cho từng trace. Tuy nhiên `contracts.Evidence` chưa khai
`ConfigDict(frozen=True)`, nên đây chưa phải bất biến được type/runtime cưỡng chế.
Assignment trực tiếp vào `Evidence.value` đã được kiểm và thành công. Các field
quan trọng:

| Field | Vai trò |
| --- | --- |
| evidence_id | gắn trace hiện tại |
| source_tier | btc_dataset, reference, external |
| metric, value, unit | claim định lượng |
| source_locator, source_path | vị trí truy nguyên |
| dataset_version | phiên bản dữ liệu |
| attrs | country, date, plan_hash, exclusion, sub_id... |
| provenance | bắt buộc với tier ngoài |
| parent_evidence_ids | lineage trực tiếp |
| claimable_paths | dot-path được phép claim |

Chuỗi truy vết:

~~~text
số trong answer
→ ResponseClaim
→ evidence_id
→ Evidence
→ SourceLocator
→ artifact/row
→ dataset_version
~~~

### 7.1. Count khác measure

Count và aggregate phải dùng đúng population của từng phép:

- count trên population câu hỏi yêu cầu;
- aggregate trên tập đo được sau exclusion hợp lệ;
- excluded_count phải lộ trong attrs/caveat khi nó thay nghĩa diễn giải;
- bộ lọc của measure không được rò sang count.

### 7.2. Tier

btc_dataset cấm external provenance. reference/external bắt buộc có provenance.
Verifier kiểm tier mixing và source label. Hybrid phải trình bày internal result
và external context thành các khối tách biệt.

---

## 8. S7: sinh câu trả lời

Hai đường:

| Đường | Điều kiện |
| --- | --- |
| Deterministic template | mặc định/offline |
| LLM generation | provider và use_llm_generation=True |

LLM generation chỉ đọc ContextBundle đã guard, không đọc object repository hoặc
SQL executor trực tiếp.

Token budget theo ContextBundle:

| Stage | Budget |
| --- | ---: |
| plan | 6000 |
| alternate | 6000 |
| critic | 4000 |
| generate | 4000 |
| adjudicate | 3000 |
| extract | 2000 |

External answer có cấu trúc tách internal, bối cảnh ngoài và độ tin cậy. Nhãn
context_only phải xuất hiện; external context không được viết như bằng chứng
nhân quả.

Câu từ chối không nên chèn chữ số không có evidence. Text người dùng được echo
phải nằm trong quoted_texts để verifier biết đó không phải claim hệ thống.

---

## 9. S8–S9: verify, consistency và gate-out

### 9.1. Numeric verifier

verify_numeric_claims:

- quét mọi token số;
- chuẩn hóa dấu phân cách và Unicode;
- khớp claim với claimable path;
- kiểm tier mixing;
- kiểm provenance và source label;
- kiểm block rule của external answer;
- kiểm lineage của metric dẫn xuất.

### 9.2. Metric lineage

_lineage_gaps dựng MetricGraph từ 33 metric. Một derived metric phải có ancestor
evidence theo graph hoặc caveat được khai đúng. Boolean ancestor không bị buộc
thành evidence số.

### 9.3. Consistency

check_evidence_arithmetic hiện kiểm **chính xác** các luật:

- percent trong 0–100;
- ratio trong khoảng hợp lệ;
- count nguyên và không âm đối với metric nhận dạng là count;
- min ≤ median ≤ max cho cùng đại lượng/scope;
- cộng các partition listing_count bằng total listing_count khi attrs scope
  tương thích.

Chỉ internal evidence được kiểm. Có thể tắt cho ablation bằng
GLADIATORS_DISABLE_EVIDENCE_CONSISTENCY=1.

Khoảng trống so với cách diễn giải rộng của Spec2308: implementation không nhận
digest/plan và chưa có phép kiểm tổng quát
count + excluded_rows = population cho mọi metric. Không được ghi rằng luật này
đã hiện thực.

Issue consistency làm gate thành A26-CONSISTENCY.

### 9.4. Alignment cuối

Các lớp alignment kiểm:

- macro shape;
- plan giữ requested measure/dimension/filter/scope/output shape;
- evidence giữ country/date/ref;
- answer khớp evidence;
- causal premise và chiều biến động;
- rank tie;
- qualifier/subrequest không bị bỏ.

Các rule chính:

| Nhóm | Rule |
| --- | --- |
| measure | A22-ALIGN-MEASURE |
| shape/causal | A22-ALIGN-SHAPE |
| qualifier | A22-ALIGN-QUALIFIER |
| entity | A22-ALIGN-ENTITY |
| subrequest | A22-ALIGN-SUBREQUEST |
| country | A22-ALIGN-COUNTRY |
| date | A22-ALIGN-DATE |
| aggregation | A22-ALIGN-AGGREGATION |
| grouping | A22-ALIGN-GROUPING |
| filter | A22-ALIGN-FILTER |
| premise | A22-ALIGN-PREMISE |
| rank tie | A22-ALIGN-RANK-TIE |

### 9.5. Fail-closed

Khi verifier, alignment hoặc consistency không qua:

1. thử wording repair nếu đủ điều kiện hẹp;
2. nếu vẫn hỏng, xóa evidence/claims khỏi lời từ chối;
3. sinh deterministic refusal;
4. verify refusal;
5. trả clarify cho premise/alignment phù hợp hoặc abstain
   A-VERIFICATION-FINAL.

Không được giữ answer cũ rồi chỉ đổi action.

### 9.6. Partial answer

Khi câu có từ hai question clause trở lên, decision ban đầu bị từ chối và
enable_partial_answer=True:

- chạy từng clause trong chế độ trial chống recursion;
- phải có ít nhất một phần allow và một phần blocked;
- ghép lại phần allow và chạy lần nữa;
- mọi evidence gắn sub_id;
- nêu nguyên văn phần chưa trả lời và rule reason;
- câu ghép phải qua verifier lại;
- trả A23-PARTIAL.

Nếu mọi phần allow hoặc mọi phần blocked, giữ hành vi cũ. Mệnh đề chỉ là tiền đề
không được tách thành một câu hỏi giả.

### 9.7. Suggestions

Sau refusal, nearest_answerable:

- sinh candidate từ topic/capability graph;
- chạy candidate qua chính runtime;
- tối đa bốn trial;
- chỉ giữ câu thật sự allow;
- trả tối đa hai suggestion;
- không cho trial tạo suggestion lồng nhau.

---

## 10. Quan sát, ngân sách và vận hành

### 10.1. Stage timer

StageTimer ghi thời gian cho chín stage. Ngân sách:

- p50 ≤ 8 giây;
- p95 ≤ 15 giây;
- tối đa hai critical LLM call.

within_budget chỉ trả verdict và được ghi vào planning.budget. **Nó không abort,
không fallback và không thay đổi answer.** Đây là khác biệt quan trọng với câu
chữ mục tiêu trong Spec2308.

Tên timer không hoàn toàn trùng chín chặng logic: `route` không đo
`classify_external_need`; nó chỉ có thời gian khác zero khi nhánh external-only
thực sự gọi pipeline. Vì vậy không được đọc `timing.route=0` như bằng chứng router
không chạy.

Report offline 27/08:

| Suite | p50 | p95 | Cache hit |
| --- | ---: | ---: | ---: |
| questions, 60 câu | 0.080 s | 0.212 s | không tra |
| questions_v2, 11 câu | 0.232 s | 0.251 s | 0.0 |
| independent, 44 câu | 0.021 s | 0.241 s | 0.40 |

Đường LLM parser DeepSeek vượt budget: P-A p50/p95 23.0/50.2 giây; P-B
18.3/30.0 giây. Vì vậy con số offline không đại diện đường LLM.

### 10.2. Trace

Các route nghiệp vụ khai báo trực tiếp trong api.py hiện có:

| Method | Route | Vai trò |
| --- | --- | --- |
| GET | / | trang chính |
| GET | /flow | flow UI |
| GET | /health | health |
| GET | /trace/{trace_id} | trace HTML |
| GET | /trace/{trace_id}.json | trace summary JSON |
| GET | /capability-map | capability HTML |
| GET | /capability-map.json | capability JSON |
| GET | /capabilities | capability contract |
| GET | /ledger | ledger UI |
| POST | /ledger/decision | quyết định duyệt |
| POST | /session/{session_id}/reset | xóa conversation state |
| POST | /ask | chạy agent |

Không có /schema-graph.
FastAPI còn tự sinh /docs, /redoc và /openapi.json; chúng không phải capability
nghiệp vụ.

### 10.3. Refusal ledger

Mọi refusal ngoài trial được ghi redacted vào
artifacts/ledger/refusals.jsonl. UI và scripts/build_ledger_report.py hỗ trợ
người duyệt.

Ledger không tự sửa production. Alias overlay chỉ được cập nhật sau duyệt và chỉ
trỏ đến ref đã có.

### 10.4. Capability map

ui_capability.py sinh bản đồ từ registry, không duy trì danh sách năng lực tay.
Map cho thấy intent/ref/topic đã mở, hạn chế và câu mẫu.

### 10.5. Cost report

scripts/run_cost_report.py đọc telemetry token/call và eval/pricing.json. Test
khóa cách tính và trạng thái NOT_AVAILABLE. Checkout không có cost report ngày
27/08 được commit; vì vậy B10 có tooling nhưng không có artifact kết quả để trích
con số chi phí hiện tại.

---

## 11. Cấu hình thực tế

### 11.1. Constructor AgentRuntime

Các default có ảnh hưởng kiến trúc:

| Tham số | Default |
| --- | --- |
| enable_gate | True |
| enable_verifier | True |
| enable_partial_answer | True |
| enable_cheap_loops | True |
| use_llm_parser | False |
| use_llm_generation | False khi offline |
| llm_parser_scope | always |
| enable_critic | env hoặc False |
| enable_nversion | env hoặc False |
| enable_live_search | env + pipeline, mặc định False |
| enable_voucher_profile | env hoặc False |

### 11.2. Env được source đọc

| Nhóm | Env |
| --- | --- |
| Runtime LLM | GLADIATORS_LLM_PROVIDER, GLADIATORS_ENABLE_LLM_PARSER, GLADIATORS_PROMPT_VERSION |
| LLM cassette | GLADIATORS_CASSETTE_MODE, GLADIATORS_CASSETTE_DIR |
| Planner risk | GLADIATORS_ENABLE_CRITIC, GLADIATORS_ENABLE_NVERSION |
| Shadow/gate | GLADIATORS_DISABLE_SHADOW, GLADIATORS_ENABLE_CONNECTIVITY_GATE |
| Intent | GLADIATORS_INTENT_POLICY |
| Resolution | GLADIATORS_ENABLE_BGE |
| Voucher | GLADIATORS_ENABLE_VOUCHER_PROFILE |
| Consistency ablation | GLADIATORS_DISABLE_EVIDENCE_CONSISTENCY |
| External | GLADIATORS_ENABLE_LIVE_SEARCH, GLADIATORS_LIVE_SEARCH_PROVIDER, GLADIATORS_LIVE_SEARCH_MODE, các limit/cache/quota/timeout |
| Insights | GLADIATORS_INSIGHT_ROOT |

Spec từng phác các env cho relation planner, conversation memory, value probe và
wording repair. Source hiện tại **không đọc** các env đó. Relation planner và
conversation object được dựng theo runtime; value probe chạy mặc định khi gate
có analytical request; wording repair chịu enable_cheap_loops và điều kiện call
site.

---

## 12. Bảng tra rule_id

| Rule | Nghĩa |
| --- | --- |
| A-ALLOW | Cho phép |
| A-ENTITY-NOT-FOUND | Mã/thực thể không có trong dữ liệu |
| A-AMBIGUOUS | Nhiều listing gần điểm nhau; cần người dùng chọn |
| A-MISSING-{CAP} | Dataset không có capability |
| A-MISSING-SLOT | Thiếu slot bắt buộc |
| A-COUNTRY | Không có scope quốc gia |
| A-VOUCHER-ID | Structured voucher không có cho scope |
| A-UNKNOWN-INTENT | Intent chưa đăng ký |
| A-CAPABILITY-MISS | Không có đường capability hợp lệ |
| A-DATA-ABSENT | Dữ liệu cần thiết vắng |
| A-CROSS-CURRENCY-SCOPE | Cần chọn một thị trường |
| A16-CROSS-CURRENCY | Phép tính trộn VND/IDR |
| A14-LIVE | Live search tắt |
| A14-EXT | Route external |
| A14-INTERNAL | Route internal |
| A14-HYBRID | Route hybrid |
| A14-HYBRID-PARTIAL | Hybrid thiếu phần |
| A14-ROUTE-MISMATCH | Route và capability không khớp |
| A15-EXTERNAL-UNUSABLE | Không có external record qua admission |
| A15-INTERNAL-PARTIAL | Internal xong, external hạ limitation |
| A19-PLAN | Plan không hợp lệ/không lập được |
| A19-PLAN-GROUPING | Grouping không phải physical dimension |
| A19-METRIC | Metric chưa được duyệt |
| A19-CAT | Catalog binding thất bại |
| A19-OP | Operator không hỗ trợ |
| A20-TIER | Tính toán xuyên tier |
| A21-PROV | Thiếu/sai provenance |
| A22-ALIGN-* | Sai alignment, xem §9.4 |
| A23-PARTIAL | Trả phần answerable và nêu phần bị chặn |
| A26-CONSISTENCY | Evidence mâu thuẫn số học |
| A-REFS-DISCONNECTED | Ref không nối được; mặc định shadow |
| A-VALUE-NOT-FOUND | Giá trị dimension được nêu không có trong index |
| A-EMPTY-RESULT-RELAXED | Chỉ có kết quả sau khi nới sai điều kiện |
| A-EMPTY-RESULT-UNVERIFIED | Zero-row nhưng không chứng minh được bộ lọc đã chạy đúng giá trị được nêu (W1.8); fixable=False |
| A-MACRO-EVIDENCE-CONTRACT | Dự kiến chặn evidence sai contract macro; nhánh allow hiện chưa tới được mã này |
| A-NO-EVIDENCE | Không có evidence đủ dùng |
| A-INSUFFICIENT-SNAPSHOTS | Không đủ snapshot |
| A-ANALYTICAL-AMBIGUITY | Câu phân tích mơ hồ |
| A-VERIFICATION-FINAL | Fail-closed sau verify cuối |
| ABLATION-NO-GATE | Gate tắt chỉ để đo |

Kết quả zero-row không có mã lỗi; nếu đúng plan và scope, nó là A-ALLOW.

---

## 13. Kiến trúc đánh giá

### 13.1. Không trộn regression với capability

Suite do đội phát triển viết cùng rule chứng minh tính hồi quy, không chứng minh
độ phủ ngoài phân phối. B1 thêm:

- coverage;
- risk;
- over_refusal_rate;
- over_answer_rate;
- refusal precision/recall;
- action stability.

clarify được tính là refusal trong selective metrics.

### 13.2. Bằng chứng đo hiện có

| Hạng mục | Artifact | Kết quả chính |
| --- | --- | --- |
| B2 BGK-20 | eval/reports/2026-08-23-bgk20-after.md | oracle pandas và agent artifacts |
| B3/B12 bank | eval/independent/answerable_manual.json | 44 câu, 36 nhóm diễn đạt |
| B4 risk/coverage | 2026-08-27-risk-coverage.json | L0 coverage 0.4545, risk 0.0, over-refusal 0.4737, AURC 0.0454 |
| B5 LLM SQL baseline | 2026-08-27-sql-baseline.json | 7/44 correct; 29/44 wrong_value_silent |
| B7 metamorphic | 2026-08-27-metamorphic.json | 122 pass, 8 fail, 174 skip, 4 suspect; rate 0.9104 |
| A11 policy | 2026-08-27-intent-policy.json | P-A và P-B hòa về coverage/risk |
| A6 latency | 2026-08-27-latency.md | offline trong budget, LLM parser ngoài budget |

### 13.3. Giới hạn của bank độc lập

Tên thư mục independent không đủ làm nó độc lập về quy trình. Report tự ghi:

- generator đã được tác nhân đọc source tạo;
- author_read_source_code=true;
- 44 câu, dưới acceptance 60–100;
- vì vậy over-refusal là bằng chứng hữu ích nhưng không phải phép đo độc lập sạch.

B12 thực tế dùng scripts/build_question_bank.py, không phải tên
build_answerable_suite.py được phác trong spec. scripts/build_multiturn_suite.py
tạo suite hội thoại riêng.

---

## 14. Ma trận toàn bộ 25 work package của Spec2308

### 14.1. Nhóm A — kiến trúc

| WP | Trạng thái | Bằng chứng chính | Kết luận chính xác |
| --- | --- | --- | --- |
| A1 Relation planner | **WIRED** | planner/synthesizer.py, compiler.py; test_relation_bindings, test_synthesizer_equivalence | Nhiều nan hoa, tối đa 3; đồ thị hiện yêu cầu mỗi path dài 1 |
| A2 Connectivity gate | **SHADOW** | feasibility.connectivity_blockers, gate.last_connectivity, test_connectivity_gate | Luôn trace; chỉ block khi env bật |
| A3 Conversation | **WIRED** | agent/conversation.py, workflow run, API reset, test_conversation_memory | In-memory 512/30 phút/3 lượt; đổi topic giữ scope, bỏ entity |
| A4 Alias + qualifier | **WIRED** | alias_index.py, alias_overlay.json, qualifiers.py; test_alias_index, test_qualifier_binding | Một alias source; 4 qualifier bind thành predicate |
| A5 Cheap loops | **WIRED** | value_probe.py, open_planner.py, wording_repair.py; ba test tương ứng | P/R/W đều có call site; riêng W chịu enable_cheap_loops |
| A6 Timing/cache | **PARTIAL** | budget.py, plan_cache.py, latency report; test_budget, test_plan_cache | Đo/cache wired; budget chỉ báo, chưa tự fallback |
| A7 Relation explain | **PARTIAL** | parser, intent_registry, relation_prose, workflow; test_schema_explain | Intent/prose wired; ui_schema.py và /schema-graph absent |
| A8 Suggestions | **WIRED** | suggestions.py, workflow; test_suggestions | Tối đa 4 trial, 2 câu đã chạy thật |
| A9 Metric lineage | **WIRED** | verifier._lineage_gaps, domain/metrics.py; test_metric_lineage | Chặn derived claim thiếu ancestor/caveat |
| A10 Entity type | **PARTIAL/SHADOW** | expected_entity_types, workflow telemetry; test_entity_type_constraint | Suy loại và vào trace, nhưng không truyền vào resolver để lọc ứng viên |
| A11 Intent arbiter | **WIRED** | intent_arbiter.py, workflow._parse; test_intent_arbiter, policy report | P-A default; P-B chạy được nhưng chưa thắng; two-way clarify chưa end-to-end |
| A12 External ladder | **PARTIAL** | external/lexicon.py, pipeline hiện hữu, record_replay; test_external_lexicon | Pipeline nấc 2 wired nhưng OFF; lexicon nấc 1 chưa được gọi; cassette JSON vắng, chưa ký duyệt |
| A13 Partial answer | **WIRED** | workflow._partial_answer; test_partial_answer | Tách question clause có giới hạn, gắn sub_id và verify lại |

### 14.2. Nhóm B — đo và vận hành

| WP | Trạng thái | Bằng chứng chính | Kết luận chính xác |
| --- | --- | --- | --- |
| B1 Selective metrics | **OPS/EVAL** | scripts/run_evaluation.py, test_eval_metrics | Có đủ metric; ý nghĩa phụ thuộc nhãn answerability |
| B2 BGK-20 | **OPS/EVAL** | bgk_groundtruth.py, bgk_run_agent.py, bgk_compare.py, report 23/08 | Có oracle và report; không phải runtime feature |
| B3 Bank 60–100 | **PARTIAL** | eval/independent/answerable_manual.json, report independent-bank | Chỉ 44 câu; tác giả đã đọc source, chưa đạt R1 và size |
| B4 Risk–coverage | **OPS/EVAL** | run_risk_coverage.py, JSON/SVG report | Có L0–L3, AURC; L3 không phải release |
| B5 Model viết SQL | **OPS/EVAL** | run_sql_baseline.py, test_sql_baseline, report | Đã đo; baseline sai im lặng cao |
| B6 Arithmetic consistency | **WIRED/PARTIAL** | consistency.py, workflow, test_evidence_consistency | Wired fail-closed; phạm vi luật hẹp hơn spec |
| B7 Metamorphic | **OPS/EVAL** | eval/metamorphic/relations.py, run_metamorphic.py, report | Có report và còn 8 fail/4 suspect, không được gọi là toàn pass |
| B8 Capability map | **WIRED/OPS** | domain/capability.py, ui_capability.py, API routes, test_capability_map | Sinh từ registry và phục vụ HTML/JSON |
| B9 Trace UI | **WIRED/OPS** | ui_trace.py, /trace routes, test_trace_view | Đọc trace hiện có, validate trace_id |
| B10 Cost per answer | **OPS/EVAL PARTIAL** | run_cost_report.py, eval/pricing.json, test_cost_report | Tooling có; chưa có report chi phí hiện tại được commit |
| B11 Human ledger | **WIRED/OPS** | ledger.py, ui_ledger.py, alias overlay, test_ledger | Ghi refusal và duyệt; không tự sửa |
| B12 Raw-data question generator | **PARTIAL** | build_question_bank.py, build_multiturn_suite.py | Generator có nhưng output 44 câu và không thỏa độc lập 60–100 |

### 14.3. Kết luận audit Spec2308

Không thể kết luận “Spec2308 đã được cập nhật 100% vào runtime”. Kết luận đúng:

- phần lớn thay đổi A đã có code và test;
- A2 cố ý shadow;
- A6 budget enforcement, A7 schema UI, A12 lexicon/cassette chưa đầy đủ;
- A10 mới có telemetry, chưa có typed filtering ở resolver;
- B chủ yếu là hạ tầng đo/vận hành, không phải luồng inference;
- B3/B12 chưa đạt acceptance về quy mô và tính độc lập;
- B6 đã nối nhưng chưa bao phủ luật rộng nhất của spec;
- B7 report vẫn còn failure/suspect.

### 14.4. Mốc source kiểm chứng trực tiếp

Các vị trí dưới đây là anchor tại source d14fa75. Chúng cho phép reviewer kiểm
nhanh kết luận trong ma trận mà không dựa vào narrative:

| Bằng chứng | Vị trí |
| --- | --- |
| Relation planner có budget ba cạnh | src/gladiators/planner/synthesizer.py:154 và :164 |
| Conversation store là runtime object | src/gladiators/agent/conversation.py:100; workflow.py:240 và :1059 |
| Connectivity luôn tính, chỉ block khi env bật | src/gladiators/agent/gate.py:326–331 |
| Entity type suy từ bound ref nhưng chỉ vào telemetry | src/gladiators/agent/entity_resolution.py:287; workflow.py:1075–1085 và :1117–1126; resolver signatures không nhận expected type |
| Intent arbiter nhận nhãn LLM gốc | src/gladiators/agent/workflow.py:471–478 |
| schema_relation_explain có registry và call site | domain/intent_registry.py:44; agent/workflow.py:1395 |
| Consistency được gọi trong runtime | src/gladiators/agent/workflow.py:1629–1632 |
| Wording repair có điều kiện fail hẹp | src/gladiators/agent/workflow.py:1652–1690 |
| Macro evidence contract bị che bởi nhánh `elif` trước | src/gladiators/agent/workflow.py:1543–1569 |
| Evidence chưa frozen | src/gladiators/contracts.py:99–129; class không có `model_config=ConfigDict(frozen=True)` |
| Partial answer và suggestions chạy sau refusal | src/gladiators/agent/workflow.py:1746–1764 |
| Plan cache telemetry vào response | src/gladiators/agent/workflow.py:1799–1801 |
| Refusal ledger có call site | src/gladiators/agent/workflow.py:1802–1808 |
| Budget verdict ghi trace, không điều khiển flow | src/gladiators/agent/budget.py:89–98; workflow.py:1819–1828 |
| Lexicon chỉ có định nghĩa, không có runtime call | external/lexicon.py:52; tìm toàn src chỉ thấy chính định nghĩa |
| API không có schema graph | src/gladiators/api.py:30–159; route introspection không có /schema-graph |

---

## 15. Khoảng trống và nợ kiến trúc đang mở

1. **Schema graph UI absent.** Có relation explanation intent nhưng không có
   ui_schema.py hay /schema-graph.
2. **External lexicon chưa nối.** normalize_to_dataset_value chỉ được test trực
   tiếp, không chạy trong external pipeline/workflow.
3. **Cassette không tái lập từ checkout.** REVIEW.md là manifest lịch sử; JSON
   bị bỏ khỏi repo cùng artifacts và người duyệt chưa ký.
4. **Budget là observability.** within_budget không làm fallback.
5. **Consistency hẹp hơn spec.** Chưa có population/excluded tổng quát và không
   dùng RequestDigest/plan.
6. **Two-way intent clarify chưa nối provider.**
7. **Bộ đề “independent” chưa độc lập quy trình và chỉ 44 câu.**
8. **Cost report chưa có artifact kết quả hiện hành.**
9. **Invariant enforcement chưa hợp nhất call site hoàn toàn.**
10. **External/live-search và voucher profile giữ OFF mặc định.**
11. **Value index là artifact bắt buộc ngoài registry.** Dataset đổi phải dựng
    lại và kiểm version.
12. **Dữ liệu mới ở commit 6a5af5e chưa tự động trở thành semantic capability.**
    Thêm raw file không đồng nghĩa catalog/table binding đã mở cho nó.
13. **Evidence chưa immutable ở cấp model.** Code tuân quy ước read-only và
    ContextBundle dùng copy, nhưng assignment trực tiếp vẫn hợp lệ; invariant này
    hiện dựa vào kỷ luật caller.
14. **Macro evidence-contract guard chưa bắn trên đường allow.** Nhánh kiểm bị
    evidence-alignment `elif` phía trước che; suite hiện chỉ chứng minh macro đang
    phát đúng contract, chưa chứng minh runtime chặn contract sai.
15. **A10 mới là telemetry.** expected entity type không được truyền vào resolver;
    `resolver_pool="listing"` chỉ là mô tả trace, không phải một phép lọc.
16. **S2 route chưa có stage/timer riêng.** Route được tính trong parser và gate;
    timer `route` đang đo external execution nên tên stage dễ bị diễn giải sai.
17. **EntityResolutionResult không ra response/trace đầy đủ.** Score, margin và
    resolution source dừng ở `ToolContext`; chỉ listing key hoặc shortlist text
    sống tới response.

---

## 16. Quy tắc phát triển tiếp từ Archi2808

Mọi thay đổi kiến trúc phải cập nhật đồng thời:

1. registry hoặc contract;
2. call site runtime nếu tuyên bố WIRED;
3. test behavior, không chỉ test symbol tồn tại;
4. trace/telemetry tương ứng;
5. rule_id table nếu có mã mới;
6. metadata verifier/hash nếu binding đổi;
7. eval report nếu đổi default hoặc trade-off;
8. ma trận WP và khoảng trống trong file này.

Không được:

- đánh dấu hoàn tất chỉ vì có file/module;
- dùng report lịch sử thay cho artifact hiện có mà không ghi giới hạn;
- biến shadow thành release gate mà không đo risk/coverage;
- đổi default P-A, live search, critic, nversion hoặc voucher profile chỉ bằng
  cảm tính;
- cho external số đi vào internal aggregate;
- cache Evidence;
- group-by analysis_unit như physical dimension;
- join hai hệ category theo tên cột.

---

## 17. Lệnh tái lập

Chạy từ root repository.

### 17.1. Full test trên Windows

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=D:\tg28_archi_full
~~~

Kết quả chốt:

~~~text
1207 passed, 1 skipped in 99.44s
~~~

### 17.2. Metadata binding

~~~powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts/verify_metadata_bindings.py
~~~

### 17.3. Smoke runtime và cache

~~~powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -c "from gladiators.runtime_factory import create_runtime; r=create_runtime('offline'); a=r.run('Có bao nhiêu shop ở Việt Nam?'); b=r.run('Có bao nhiêu shop ở Việt Nam?'); print(a.gate.action,a.gate.rule_id,a.verification['passed']); print(b.planning.get('plan_cache'))"
~~~

### 17.4. Kiểm API route

~~~powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -c "from gladiators.api import app; print(sorted((','.join(sorted(x.methods)),x.path) for x in app.routes if hasattr(x,'methods')))"
~~~

### 17.5. Các report

~~~powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts/build_question_bank.py
.\.venv\Scripts\python.exe scripts/run_risk_coverage.py
.\.venv\Scripts\python.exe scripts/run_metamorphic.py
.\.venv\Scripts\python.exe scripts/run_cost_report.py --report eval/reports/2026-08-27.json
~~~

Các lệnh gọi provider ngoài có thể tốn tiền và phụ thuộc key; không dùng report
offline để suy ra độ trễ/chi phí của đường LLM.

---

## 18. Tuyên bố chốt

Archi2808 mô tả kiến trúc thực tế tại source d14fa75/HEAD 6a5af5e và cố ý giữ
nguyên các khoảng trống đã chứng minh. File này không tuyên bố Spec2308 hoàn tất
100%; nó chỉ đánh dấu WIRED khi có call site, test và bằng chứng hành vi. Một test
cô lập xanh không đủ để nâng thành WIRED nếu giá trị tính ra không được consumer
thực sự sử dụng để đổi hành vi runtime.

Khi source thay đổi sau mốc trên, hash, test count, API routes, default flags và
ma trận 25 WP phải được kiểm lại trước khi dùng Archi2808 làm cơ sở release mới.
