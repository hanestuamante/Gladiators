# Kiến trúc Agent V1 — Verifiable E-commerce Intelligence MVP

> **Trạng thái:** Kiến trúc hiện hành, có runtime, API và UI chạy được.
> **Ngày đối soát:** 2026-07-16.
> **Phạm vi:** Hợp nhất [Architecture Spec](Architecture-spec.md), [V0 Architecture](V0_Architecture.md), [Data Context and Analysis Notes](Data_Context_and_Analysis_Notes.md) và implementation thực tế trong repository.

Tài liệu này mô tả cả thiết kế V1 và phần đã được triển khai. Một component chỉ được ghi là **Implemented** khi có code hoặc artifact kiểm chứng trong repository. Phần chưa đạt đầy đủ so với Architecture Spec được tập trung tại [V1 Implementation Limitations](V1_Implementation_Limitations.md).

## 1. Thứ tự ưu tiên nguồn

Khi schema, semantics hoặc đường dẫn mâu thuẫn, dùng thứ tự sau:

1. Artifact hiện tại trong `data/processed/` và preprocessing notebook có thể chạy lại.
2. `pipeline_report.json`, `data_quality_issues.csv` và các report thực thi hiện có.
3. [Data Context and Analysis Notes](Data_Context_and_Analysis_Notes.md) cho grain, key, field semantics và analysis guardrail.
4. Code, test và config V1 hiện tại cho trạng thái implementation.
5. Tài liệu này cho ranh giới component và contract V1.
6. [Architecture Spec](Architecture-spec.md) cho kiến trúc chuẩn và acceptance criteria chưa mâu thuẫn dữ liệu.
7. [V0 Architecture](V0_Architecture.md) chỉ để truy vết ý tưởng lịch sử.

V1 không tạo một data dictionary thứ hai. Data Context sở hữu sự thật về dữ liệu; V1 sở hữu orchestration, interface, evidence, verification, evaluation và product boundary.

## 2. Mục tiêu và bảo đảm

V1 là single-agent pipeline chạy local, trả lời một tập câu hỏi giới hạn về Shopee listing intelligence. Hệ thống phải:

- parse intent tiếng Việt, Bahasa Indonesia và câu không dấu;
- resolve listing mà không đoán khi tên mơ hồ;
- chỉ chạy deterministic tool trên processed artifact;
- trả typed evidence có dataset version và source locator;
- chặn hoặc fallback khi LLM sinh số không được evidence hỗ trợ;
- clarify khi thiếu entity/scope và abstain khi dữ liệu không có capability;
- giữ mọi so sánh promotion ở mức mô tả, không nhân quả;
- cho phép đổi LLM provider mà không sửa analytics core;
- cung cấp CLI, HTTP API và UI nội bộ cho MVP.

Các bảo đảm hiện hành:

1. LLM không trực tiếp tính business metric hoặc viết query tùy ý.
2. Mỗi số analytical được trả qua runtime phải thuộc tập numeric evidence; output vi phạm bị regenerate rồi fallback deterministic.
3. Request không hỗ trợ đi qua rule-based gate thay vì trông chờ LLM tự từ chối.
4. Trace được redaction, lưu quyền `0600`, có retention policy và dataset version.
5. Kết luận causal, SKU, profit, conversion, forecast, ads, inventory và image similarity không được nội suy từ dữ liệu hiện tại.

Bảo đảm số hiện tại chưa đồng nghĩa với claim-level proof đầy đủ theo Architecture Spec: verifier chưa kiểm tra `claim → evidence_id → source path → unit` cho từng số. Khoảng cách này được ghi tại tài liệu limitations.

## 3. Trạng thái tổng hợp

| Khối | Trạng thái | Bằng chứng chính |
| --- | --- | --- |
| Processed-artifact repository | Implemented | `src/gladiators/data/repository.py` |
| Pandera startup validation | Partial | `src/gladiators/data/contracts.py`; projection còn hẹp và `strict=False` |
| Metric/relation registry | Partial | Registry có kiểu đã tồn tại nhưng chưa enforce mọi tool/join |
| Parser đa ngôn ngữ | Implemented | Deterministic parser + LLM structured parser + fallback |
| Intent registry | Partial | Đăng ký được intent; workflow vẫn branch theo ba intent hiện tại |
| Entity resolution | Implemented, cần hardening | RapidFuzz; BGE-M3 optional, ambiguity gate |
| BGE-M3 artifact | Implemented | 1.157 × 1.024, revision/hash/CPU benchmark |
| Ba deterministic tool | Implemented ở MVP scope | Sales transition, listing similarity, voucher observation |
| Evidence record + source locator | Implemented ở MVP scope | Typed evidence, `url|file|api|internal`, dataset version |
| Numeric verifier | Partial | Numeric coverage/mutation detection có; unit/path/claims contract còn thiếu |
| Contract-driven gate | Partial | Các capability chính có; chưa đủ taxonomy/rule generation của spec |
| LLM provider abstraction | Implemented | Fake, Gemini, Hugging Face, Groq và Anthropic adapter |
| Trace redaction/retention | Implemented ở single-process scope | Redaction, `0600`, prune theo ngày |
| Eval 60 câu × repeated runs | Implemented | Checkpoint/resume, pass^3, citation, verifier, abstention, telemetry |
| Human similarity ground truth | Deferred | CSV 30 cặp đã xuất nhưng chưa có nhãn reviewer |
| External data | Contract-only | Source locator/record có; fetch/map/cache/mixing runtime chưa có |
| API/CLI/UI | Implemented cho MVP nội bộ | `/`, `/health`, `/capabilities`, `/ask`, CLI, Dockerfile |
| Production security/operations | Deferred | Chưa auth, tenant isolation, rate limit, TLS và production observability |

## 4. Nền dữ liệu

### 4.1. Artifact và scope

V1 đọc read-only từ `data/processed/`:

| Artifact | Dòng | Vai trò |
| --- | ---: | --- |
| `products_clean.csv` | 3.341 | Listing snapshot và thuộc tính nguồn |
| `shop_info_clean.csv` | 20 | Latest/static shop context tại 2026-07-03 |
| `category_list_clean.csv` | 491 | Kệ nội bộ của shop |
| `product_categories_clean.csv` | 4.054 | Membership listing-snapshot → shop category |
| `category_platform_clean.csv` | 4.482 | Platform taxonomy có country scope |
| `product_snapshot_metrics.csv` | 3.341 | Metric snapshot đã xử lý |
| `product_transition_metrics.csv` | 2.184 | Metric giữa các snapshot kế tiếp |
| `data_quality_issues.csv` | Theo run | Data-quality evidence |
| `pipeline_report.json` | 1 | Tóm tắt pipeline và quality |

Dataset gồm VN và ID, 20 shop, ba ngày 2026-07-01 đến 2026-07-03. Panel không cân bằng: 1.157 listing, 3.341 snapshot và thiếu 130 ô quan sát so với panel đủ.

### 4.2. Grain và identity

```text
product_listing_key = country_code + ':' + shop_id + ':' + item_id
product_snapshot_key = product_listing_key + ':' + date
```

- `item_id` là listing ID, không phải SKU.
- `ListingSnapshot` là grain phân tích trung tâm.
- `tier_variation_*` chỉ là display attribute; không tạo variation entity.
- Tên, URL và brand không thay thế khóa listing.
- Shop context hiện chỉ là latest/static enrichment cho snapshot cũ hơn.

### 4.3. Join hợp lệ

```text
products -> shop_info
  country_code + shop_id

products -> product_categories
  country_code + shop_id + item_id + date

product_categories -> category_list
  country_code + shop_id + category_id=shop_category_id + date

products -> category_platform
  country_code=path_country_code + category ID
```

Platform category và shop category là hai namespace khác nhau. `catid` là top-level trong export hiện tại; leaf là phần tử cuối của `global_catids`. Tổng hợp qua shop shelf phải deduplicate lại về listing-snapshot vì một listing có thể thuộc nhiều kệ. Có 5 orphan mapping và 1.132 snapshot không có shop-category mapping, nên inner join không đại diện toàn population.

### 4.4. Guardrail dữ liệu bắt buộc

1. `monthly_sold_value` là recent-window display proxy, không phải daily sales; không cộng qua ba snapshot.
2. `history_sold_value` là cumulative proxy có 88 transition giảm bất thường; delta âm là anomaly, không phải sales âm sạch.
3. `price` là displayed/exported price; không trừ voucher lần hai.
4. `estimated_recent_revenue = price × monthly_sold_value` chỉ là snapshot proxy, không phải GMV/profit.
5. Cross-sectional aggregate phải chọn một ngày và deduplicate về listing.
6. Structured voucher là `voucher_discount_num > 0`; UI voucher label là population khác.
7. Không dùng `discount_percent > 0` như promotion flag độc lập và không dựng bốn nhóm promo/voucher.
8. Structured voucher quan sát được chỉ có ở VN; ID không đủ group variance cho intent này.
9. `is_ad` và `is_sold_out` toàn False nên không thể phân tích ads hoặc inventory status.
10. Không so sánh tiền tuyệt đối VN–ID khi chưa có FX evidence.
11. Ba price sentinel `999999999` phải được flag/loại khỏi metric giá.
12. Mọi kết luận từ ba ngày là descriptive association, không causal/seasonal/forecast.

## 5. Knowledge Graph và semantic layer

V1 kế thừa ý tưởng hữu ích nhất từ V0: Agent không đọc CSV như text tự do mà đi qua semantic layer. Knowledge Graph được biểu diễn bằng typed entity/relation registry trên bảng, không dùng graph database.

### 5.1. Entity được dữ liệu hỗ trợ

| Entity | Identity / scope |
| --- | --- |
| `ProductListing` | country + shop + item |
| `ListingSnapshot` | listing + date |
| `Shop` | country + shop; latest/static context |
| `PlatformCategory` | country + category ID |
| `ShopCategory` | country + shop + category + date |
| `VoucherObservation` | listing snapshot + voucher code |
| `PromotionIdObservation` | listing snapshot + non-sentinel promotion ID |
| `MetricObservation` | metric + grain key + dataset version |

Không có entity đáng tin cậy cho SKU, canonical product, canonical brand hoặc marketing campaign. Brand và variation hiện là attribute.

### 5.2. Relation chuẩn

| Relation | Từ → Đến | Caveat |
| --- | --- | --- |
| `listing_has_snapshot` | Listing → Snapshot | Hai grain khác nhau |
| `sold_by` | Listing → Shop | Shop context là latest/static |
| `in_platform_category` | Snapshot → PlatformCategory | Join phải có country |
| `in_shop_category` | Snapshot → ShopCategory | Multi-membership, missing mapping, cần full key |
| `observed_structured_voucher` | Snapshot → VoucherObservation | Quan sát theo ngày, không cố định |
| `observed_promotion_id` | Snapshot → PromotionIdObservation | Không chứng minh campaign/effect |
| `has_display_variation_info` | Snapshot → attribute | Không tạo SKU |

Registry hiện tồn tại nhưng mới là catalog tối thiểu; analytics tool chưa bắt buộc thực thi join thông qua registry. Do đó relation registry hiện là semantic contract một phần, chưa phải policy enforcement hoàn chỉnh.

### 5.3. Metric semantics

Các metric chính gồm `monthly_sold_delta`, `days_since_previous`, các snapshot sales/price/voucher proxy và similarity score. Metric đã có trong processed artifact được tái sử dụng; LLM không tính lại.

Metric registry phải là nơi duy nhất khai báo source, grain, unit, interpretation, dedupe và caveat. Implementation hiện mới khai báo một projection nhỏ; mở rộng metric/relation yêu cầu registry entry, deterministic tool test và eval case tương ứng.

## 6. Kiến trúc runtime

```text
Browser / CLI / API client
  -> Request contract
  -> Deterministic parser hoặc LLM structured parser
  -> Intent slot normalization + safety precedence
  -> Contract-driven pre-gate
  -> Entity resolution (nếu cần)
  -> Clarify khi mơ hồ
  -> Deterministic analytics tool
  -> Typed evidence bundle
  -> Deterministic hoặc LLM response generation
  -> Numeric verifier
  -> Regenerate một lần nếu sai
  -> Verified deterministic fallback nếu vẫn sai
  -> Trace redaction + persistence
  -> Answer | Clarify | Abstain
```

| Layer | Trách nhiệm | Không được làm |
| --- | --- | --- |
| Repository | Validate và đọc processed artifact | Re-clean raw data |
| Parser | Tạo `StructuredRequest` | Tính metric hoặc tự đoán ID |
| Intent registry | Required slot, tool plan, capability | Chứa data calculation |
| Gate | Enforce capability/scope | Chỉ dựa model confidence |
| Entity resolver | Resolve hoặc báo ambiguity | Tự chọn top-1 khi margin thấp |
| Analytics tool | Filter/tính/rank deterministic | Gọi LLM hoặc viết causal claim |
| Evidence | Mang typed value/provenance | Biến đổi giá trị tool |
| Generator | Diễn giải evidence | Sinh số ngoài evidence |
| Verifier | Chặn numeric claim không được hỗ trợ | Đoán hoặc sửa hộ số |
| Trace | Debug/reproducibility | Lưu secret rõ |
| Eval | Chấm trajectory/evidence/citation/abstention | Biến fixture thành production truth tổng quát |

Runtime là single-agent tuyến tính. Verifier và gate là code module, không phải agent phụ. Không có GraphRAG, vector DB, arbitrary SQL hoặc multi-agent coordination.

## 7. Contract và khả năng mở rộng

### 7.1. Request/response

`StructuredRequest` hiện có:

```text
intent: str
entity_text: str | null
country: str | null
date_range: list[str]
slots: dict
language: vi | id | unknown
```

`AgentResponse` gồm trace ID, normalized request, gate decision, answer, evidence, tool calls, resolved listing key, verification verdict, LLM metadata, degraded flag và timestamp.

### 7.2. Intent registry

Ba intent được đăng ký bằng `IntentSpec{name, required_slots, tool_plan, required_capabilities}`. Parser prompt lấy danh sách intent động và gate kiểm required slot từ spec.

Thêm intent mới ở trạng thái mục tiêu cần:

1. `IntentSpec` và aliases/language examples.
2. Typed deterministic tool hoặc tái sử dụng tool có sẵn.
3. Metric/relation/capability dependencies.
4. Ít nhất 12 eval case gồm positive, ambiguous và unsupported edges.
5. Generic dispatch từ tool registry.

Bước 5 chưa hoàn tất: workflow hiện vẫn có branch cụ thể cho ba intent.

### 7.3. LLM boundary

Interface chung hỗ trợ:

- parse intent sang schema;
- generate answer từ evidence bundle;
- judge rubric trong eval;
- telemetry, retry, timeout và provider-specific structured output.

Có fake client để test offline và adapter cho Gemini, Hugging Face, Groq, Anthropic. Provider/model/prompt version nằm ở config hoặc environment; secret không đi vào prompt/trace.

LLM output luôn chịu deterministic safety precedence: taxonomy unsupported, entity trong dấu nháy và country có thể được parser deterministic chuẩn hóa lại trước khi tool chạy.

## 8. Ba intent hiện hành

### 8.1. `sales_decline`

Ý nghĩa an toàn: báo thay đổi `monthly_sold_value` proxy giữa hai snapshot eligible gần nhất của một listing.

Luồng MVP:

1. Resolve listing.
2. Clarify nếu nhiều candidate gần nhau.
3. Lấy transition eligible mới nhất.
4. Trả `monthly_sold_delta` và `days_since_previous` dưới dạng evidence.
5. Nêu đây là chênh lệch snapshot, không phải causal evidence.

Thiết kế chuẩn còn yêu cầu covariate price/discount/voucher/rating, anomaly channel, baseline nhóm tương tự và date selection. Các phần đó chưa nằm trên hot path hiện tại.

### 8.2. `similar_product`

Ý nghĩa: xếp hạng listing tương tự, không phải same-product hoặc SKU matching.

Luồng MVP resolve source listing, lấy candidate bằng RapidFuzz và tùy chọn BGE-M3, loại source rồi trả top 5 cùng lexical/semantic score trong evidence attrs. BGE-M3 artifact có 1.157 vector 1.024 chiều, version/hash và CPU benchmark; runtime mặc định không tải dense model nếu `GLADIATORS_ENABLE_BGE` chưa bật.

Architecture Spec yêu cầu blocking cùng country, category-path overlap, price band và score breakdown đa thành phần. Các ràng buộc này chưa được enforce đầy đủ trong tool hiện tại, nên similarity vẫn là MVP retrieval chứ chưa phải production product matching.

### 8.3. `promotion_effectiveness`

Tên intent được giữ để tương thích, nhưng action thực tế là descriptive structured-voucher comparison.

Luồng MVP:

1. Yêu cầu country.
2. Chọn snapshot mới nhất trong market.
3. Chỉ giữ dòng có monthly-sold proxy.
4. So nhóm có/không structured voucher.
5. Trả listing count, mean và median monthly-sold proxy.
6. Nêu rõ đây là tương quan nhóm, không chứng minh promotion gây thay đổi.

Gate từ chối ID vì không có structured voucher. Revenue proxy median, explicit snapshot selection và confounder breakdown chưa được tool trả đầy đủ như spec.

## 9. Evidence, verification và trace

### 9.1. Evidence contract hiện hành

Mỗi evidence có:

```text
evidence_id = ev:{trace_id}:{sequence}
source_tier = T1 | T2 | T3
metric + typed value + unit
source_locator(kind=url|file|api|internal, value)
source_path
dataset_version
attrs (scope, listing/date/group/rank...)
```

Evidence ID được tạo tuần tự per request. Internal metrics hiện dùng `T1`; source locator cho phép external extension mà không đổi response schema.

### 9.2. Numeric verification hiện hành

Verifier:

1. Loại evidence ID và một số text attribute khỏi vùng scan.
2. Trích numeric token.
3. So với toàn bộ numeric evidence bằng tolerance.
4. Nếu LLM generation fail, gửi feedback và thử lại một lần.
5. Nếu vẫn fail, dùng deterministic answer đã verify.

Cơ chế này đã bắt mutation test và bảo vệ MVP, nhưng chưa đạt claim JSON + evidence path + unit matching + locale normalization đầy đủ. Numeric token trong product title là edge case đã quan sát ở q14.

### 9.3. Trace policy

Trace JSON chứa dataset version và response đầy đủ. Store:

- redact field nhạy cảm theo key;
- redact email, Gemini-key pattern và bearer token trong chuỗi;
- ghi file quyền `0600`;
- hỗ trợ prune theo `retention_days` (mặc định 30).

Trace hiện phù hợp demo single-process, chưa có concurrent locking, centralized audit log hoặc tenant boundary.

## 10. Clarify và abstention

Gate trả một trong ba action:

- `allow`: slot và capability đủ;
- `clarify`: thiếu slot hoặc entity resolution mơ hồ;
- `abstain`: intent/country/capability không được dữ liệu hỗ trợ.

Các capability unsupported được parser nhận diện gồm profit, forecast, SKU, ads, inventory, conversion và image similarity. Gate còn chặn voucher comparison cho ID và no-evidence từ tool.

Nguyên tắc V1 là không dùng “Low confidence” để che evidence thiếu. Nếu core evidence không đủ, hệ thống clarify hoặc abstain. Full taxonomy 16 rule và message ba phần của Architecture Spec chưa được triển khai đầy đủ cho mọi nhánh.

## 11. External data extension

`SourceLocator` đã chuẩn hóa bốn locator: `url`, `file`, `api`, `internal`. `ExternalRecord` có retrieval time, SHA-256 content hash, license và payload.

Kiến trúc mục tiêu cho dữ liệu ngoài:

```text
ExternalSourceAdapter
  -> source registry
  -> fetch/load + cache bytes
  -> schema validation
  -> exact/manual/entity mapping
  -> provenance + time-drift policy
  -> typed evidence T2/T3
  -> verifier + mixing rules
```

External analytical data không được bật chỉ bằng config. Mỗi source mới cần contract, grain, key, time semantics, mapping, relation, license/provenance và eval approval. Runtime hiện mới có contract; adapter/registry/entity map/cache chưa được triển khai.

## 12. Evaluation và bằng chứng chất lượng

### 12.1. Harness

`scripts/run_evaluation.py` hỗ trợ:

- 60 câu, ba lần chạy;
- offline hoặc provider thật;
- trajectory, evidence, entity/action correctness;
- citation recall/precision;
- verifier pass và mutation detection;
- abstention precision/recall/F1;
- parse/generation fallback, crash rate và telemetry;
- checkpoint/resume và fail-fast khi provider rate-limit.

Suite bao phủ ba intent, Vietnamese/Bahasa/không dấu, clarify và unsupported capability. Offline full đạt 100% trên fixture cố định. Groq full checkpoint 180/180 có end-to-end 91,67%, `pass^3` 90%, trajectory/evidence 96,67%, citation/verifier 100% và crash 0%. Targeted regression sau parser fix đạt 5/6; q14 còn generation fallback an toàn.

### 12.2. Embedding, judge và ablation

- BGE-M3 artifact: model revision cố định, matrix hash, 1.157 rows, 1.024 dimensions, CPU encode benchmark.
- Judge reliability fixture hiện có 10 mẫu và script tính accuracy/Cohen's kappa.
- Ablation có ba mode `direct`, `gated`, `full` và report artifact.
- Similarity review CSV đã xuất 30 cặp để người nghiệp vụ gán nhãn.

Kết quả hiện chứng minh wiring và guardrail trên fixture, chưa chứng minh retrieval relevance ngoài fixture hoặc novelty. Ablation hiện chưa công bằng vì pass definition yêu cầu mutation detection kể cả ở mode verifier bị tắt; không dùng con số đó làm contribution claim.

## 13. API, UI và vận hành MVP

FastAPI hiện cung cấp:

| Endpoint | Vai trò |
| --- | --- |
| `GET /` | UI hỏi đáp nội bộ |
| `GET /health` | status, dataset version, provider |
| `GET /capabilities` | intent, country/date/field coverage |
| `POST /ask` | chạy Agent với request `{text}` |

UI cho nhập câu hỏi, chọn câu gợi ý, xem action, answer, evidence và JSON kỹ thuật. CLI, Dockerfile và GitHub Actions cũng đã có. Đây là internal MVP; không expose trực tiếp ra Internet khi chưa có auth, TLS, rate limiting và operational controls.

## 14. Chuyển đổi từ V0

| Ý tưởng V0 | Disposition trong V1 |
| --- | --- |
| Semantic layer trên CSV | Giữ, chuyển thành typed registry + processed repository |
| Knowledge Graph | Giữ dưới dạng relation registry, không graph DB |
| Skill theo intent | Giữ dưới dạng intent spec + deterministic tool trong single agent |
| Scoped retrieval | Giữ qua parser, gate, resolver và bounded tool |
| Deterministic calculation | Giữ và enforce ở analytics layer |
| Evidence assembly | Mở rộng thành typed evidence + dataset version/source locator |
| Verification | Có numeric verifier/fallback; claim-path/unit enforcement còn mở |
| `insufficient_evidence` | Tách thành clarify và structured abstain |
| Similar SKU | Sửa thành similar listing |
| Promotion effectiveness | Sửa thành voucher descriptive comparison |
| Product-level promo/voucher edge | Sửa thành snapshot observation |
| MCP adapter | Chưa cần cho MVP; business logic độc lập MCP |
| Image/KG embedding | Image deferred; BGE text embedding đã có artifact |

Các assumption V0 về SKU proxy, promotion groups, checkout price, cross-market currency, category join, balanced panel và causal explanation tiếp tục bị bác bỏ.

## 15. Repository hiện hành

```text
src/gladiators/
  data/                 # Pandera projection + repository
  domain/               # intent, metric, relation registries
  analytics/            # deterministic tools
  agent/                # parser, resolver, BGE, gate, LLM, verifier, trace, workflow
  external/             # source locator và external record contract
  api.py                 # FastAPI boundary
  cli.py                 # command-line boundary
  runtime_factory.py     # provider/runtime wiring
  ui.py                  # internal MVP web UI
configs/default.yaml
eval/                    # suites, judge fixture và reports
scripts/                 # eval, ablation, judge, embedding, review export
artifacts/               # embeddings, reports, human-review template, traces
tests/test_v1.py
```

## 16. Điều kiện nâng từ MVP nội bộ

Trước khi gọi V1 là production-ready hoặc tuyên bố đạt hoàn toàn Architecture Spec, cần đóng các nhóm sau:

1. Enforce đúng blocking và score breakdown cho similarity.
2. Hoàn chỉnh sales/promotion analytical workflows theo spec.
3. Nâng verifier lên claim/evidence path/unit contract.
4. Enforce relation/metric registry thay vì chỉ khai báo.
5. Hoàn chỉnh strict data contracts và machine-readable quality gating.
6. Làm eval oracle độc lập, human relevance labels và ablation công bằng.
7. Bổ sung auth, rate limit, tenant boundary, observability và deployment validation.

Chi tiết, mức ưu tiên và dữ liệu cần bổ sung nằm tại [V1 Implementation Limitations](V1_Implementation_Limitations.md).
