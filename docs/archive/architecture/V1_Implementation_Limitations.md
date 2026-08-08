# Các giới hạn triển khai V1 còn tồn tại

> **Lưu trữ:** Danh sách này phản ánh gap tại mốc V1. Không dùng trực tiếp làm
> backlog hiện tại nếu chưa đối chiếu
> [CURRENT_ARCHITECTURE_SPEC.md](../../CURRENT_ARCHITECTURE_SPEC.md).

> **Ngày đối soát:** 2026-07-16.
> Tài liệu này chỉ ghi những khoảng cách **chưa được giải quyết tại mốc V1** so với [Architecture Spec](Architecture-spec.md), sau khi đối chiếu [V0 Architecture](V0_Architecture.md), [Data Context](../../reference/Data_Context_and_Analysis_Notes.md), [V1 Architecture](V1_Architecture.md) và repository tại thời điểm đó.

“MVP chạy được” không tự động có nghĩa là mọi acceptance criterion của Architecture Spec đã đạt.

## 1. Khoảng cách P0 — ảnh hưởng trực tiếp tính đúng đắn

### L-01. Similarity chưa enforce candidate blocking theo spec

Tool hiện resolve/rank candidate trên toàn catalog bằng tên và tùy chọn BGE-M3. Nó chưa bắt buộc:

- cùng `country_code`;
- overlap toàn platform category path;
- loại price sentinel và áp price band;
- brand/category/price/shelf score breakdown với weight từ config.

Vì vậy output hiện là lexical/dense nearest listing, chưa phải product-similarity pipeline đã giới hạn đúng business scope. Có rủi ro trả candidate khác market hoặc gần tên nhưng khác category/quy cách. Cần xây candidate frame theo source listing, enforce blocking trước scoring, rồi thêm hard-negative tests.

### L-02. `sales_decline` mới trả transition tối thiểu

Hot path chỉ trả `monthly_sold_delta` và `days_since_previous` của transition eligible mới nhất. Chưa có:

- chọn date range từ request;
- price/discount/voucher/rating/engagement covariates;
- `history_sold_decrease_flag` như anomaly channel;
- baseline của nhóm listing tương tự;
- ranking tín hiệu đồng thời và coverage/confidence rule.

Do đó Agent trả lời “thay đổi bao nhiêu” tốt hơn “vì sao giảm”. Không được nâng wording thành explanation toàn diện hoặc causal diagnosis.

### L-03. Promotion comparison chưa đủ output contract

Tool đã so count/mean/median monthly-sold proxy tại snapshot mới nhất, nhưng còn thiếu:

- snapshot date do user chọn;
- median `estimated_recent_revenue`;
- descriptive gap so với baseline;
- confounder breakdown theo shop/category/price;
- explicit dedupe assertion và sample coverage metadata.

Kết quả chỉ là mô tả hai nhóm structured voucher trong VN, không phải promotion effectiveness.

### L-04. Numeric verifier chưa đạt claim-level verification

Verifier hiện scan số rồi kiểm mỗi số có gần một numeric evidence bất kỳ. Nó chưa enforce:

- claims JSON có `claim_id`, `evidence_id`, `path`, `unit`;
- đúng số phải trỏ đúng evidence/path thay vì chỉ trùng một giá trị ở evidence khác;
- money/count/percent/date/ID classification và unit equality;
- locale Việt/Indonesia đầy đủ cho dấu nghìn/thập phân;
- score recomposition từ component × weight;
- non-metric token policy tổng quát.

q14 cho thấy số trong product title có thể kích hoạt generation fallback. Fallback hiện an toàn, nhưng chưa đạt bảo đảm “mọi số truy đúng source path” của Architecture Spec.

### L-05. Relation/metric registry chưa phải enforcement point

Registry hiện chỉ chứa catalog tối thiểu. Analytics tools đọc DataFrame trực tiếp và không bắt buộc join/calculate thông qua registry. Chưa có CI rule chặn ad-hoc join/formula ngoài semantic layer.

Hệ quả: thêm tool mới vẫn có thể vô tình bỏ country/shop/date scope hoặc định nghĩa lại metric. Cần registry giàu grain, join keys, cardinality, dedupe, caveat và một executor chung; test phải fail khi relation ngoài allow-list được dùng.

## 2. Khoảng cách P1 — contract và orchestration

### L-06. Pandera contract mới là projection hẹp

Startup chỉ validate ba artifact lõi và các schema đều `strict=False`. Chưa validate đầy đủ năm bảng nguồn, toàn bộ cột cần cho ba intent, unique key/cardinality, sentinel, panel gap và referential coverage. Repository đọc `pipeline_report.json` nhưng chưa fail rõ theo status/error threshold và không tự sinh quarantine report như Architecture Spec.

Cần nâng contract theo header thật cho tất cả artifact, dùng projection rõ ràng với strict schema, enforce logical key, đọc machine-readable quality flags và tách fail-fast khỏi warning/quarantine.

### L-07. Intent registry mới mở rộng một phần

Parser và gate đọc registry động, nhưng `AgentRuntime.run()` vẫn chứa nhánh cụ thể cho `sales_decline`, `similar_product`, `promotion_effectiveness`. Thêm intent mới vẫn phải sửa orchestration core.

Cần tool registry/executor generic ánh xạ `IntentSpec.tool_plan` sang typed call, metric/relation dependencies, answer template và eval minimum. Khi đó intent mới mới thực sự là “thêm spec + tool + eval, không sửa core”.

### L-08. Gate chưa triển khai đủ contract-driven taxonomy

Gate hiện xử lý unsupported capability, missing slot, country, voucher-ID, ambiguity và no-evidence. Chưa có đầy đủ 16 rule của spec, machine-generated rules từ quality report, temporal window/gap handling, cross-market FX, shop-history, category semantics và structured three-part abstention message cho mọi case.

Một phần safety hiện phụ thuộc keyword taxonomy trong deterministic parser. Cần chuyển điều kiện về capability specs và facts từ repository/quality report để giảm phụ thuộc cách diễn đạt câu hỏi.

### L-09. Answer contract chín phần và evidence confidence chưa có

Response hiện ngắn, phù hợp MVP, nhưng chưa bảo đảm cấu trúc Question/Scope/Answer/Evidence/Calculation/Inference/Confidence/Limitations/Next action. Chưa có confidence rule-based theo evidence completeness và chưa có final wording gate tổng quát cho mọi causal phrase.

Không được diễn giải `degraded` hoặc model confidence thành xác suất đúng. Cần render answer từ typed sections và chấm từng section trong eval.

### L-10. Evidence ledger còn thiếu provenance chi tiết

Evidence hiện có source locator, source path và dataset version nhưng chưa có input hash, tool version, exact source row/filter, grain key, calculation inputs, anomaly list và immutable claim mapping theo contract chuẩn. Tên tier hiện dùng `T1|T2|T3`, chưa được ánh xạ/enforce rõ sang `btc_dataset|reference|external` như Architecture Spec.

Trace có thể debug request, nhưng chưa đủ để tái lập độc lập từng phép tính chỉ từ evidence record. Cần canonical input hash và provenance serializer chung cho mọi tool.

## 3. Eval và bằng chứng chất lượng còn thiếu

### L-11. Evaluation oracle chưa độc lập hoàn toàn

Runner import production runtime và tính expected values bằng chính repository/schema assumptions của code. Điều này có thể tạo lỗi “cùng bug ở production và oracle”. Architecture Spec yêu cầu oracle độc lập không import `src/gladiators` cho tầng số liệu.

Cần frozen fixture, independent calculation package/script và golden expected values được review. Báo cáo offline 100% hiện chứng minh wiring trên fixture, không chứng minh toàn bộ business correctness.

### L-12. Similarity chưa có human ground truth

`artifacts/human_review/similarity_pairs.csv` đã có 30 cặp nhưng nhãn relevance/reviewer còn trống. Chưa thể báo Precision@5, MRR, F1, inter-reviewer agreement hoặc calibrate threshold/weight đáng tin cậy.

Cần ít nhất một reviewer nghiệp vụ; tốt hơn là hai reviewer độc lập và quy tắc giải quyết bất đồng. Agent không được tự gán nhãn rồi gọi đó là human ground truth.

### L-13. Judge reliability còn mẫu nhỏ

Judge reliability mới dựa trên 10 mẫu. Chưa có human spot-check 20% toàn suite, review 100% judge-fail, nhiều loại lỗi định tính và versioned rubric dataset đủ lớn.

Không dùng một accuracy/kappa trên 10 mẫu để khẳng định judge production-grade. Cần mở rộng nhãn và đánh giá drift khi đổi model/prompt version.

### L-14. Ablation hiện chưa chứng minh contribution

Mode `direct` và `gated` tắt verifier nhưng pass definition vẫn yêu cầu mutation detection; vì vậy hai mode bị buộc fail end-to-end và không tạo comparator công bằng. Ngoài ra ablation offline không đo contribution của LLM/model retrieval thật.

Cần định nghĩa metric áp dụng riêng cho từng mode, giữ cùng provider/model/suite, chỉ thay đúng một component mỗi lần và báo confidence interval/repeated stability. Cho tới lúc đó không dùng artifact ablation để claim novelty hoặc causal contribution.

### L-15. Coverage test còn hẹp

Repository hiện có 18 test trong một file. Chưa có đủ unit test cho mọi relation/metric, locale-number parser, five-table contract, cross-country similarity blocking, source mapping, concurrent trace writes, API auth/error/load và deployment smoke test.

Eval 60 câu tập trung nhiều vào một số title Scora và expected entity/action khóa cứng. Cần bổ sung listing/shop/category đa dạng hơn, câu dài/noisy, hard negative và user acceptance set ngoài development fixture.

## 4. Các capability bị dữ liệu hoặc ground truth chặn

### L-16. Không có campaign entity đáng tin cậy

`promotion_id` là observation theo snapshot, có sentinel và quan hệ nhiều-nhiều; không có campaign master chứa type, lifecycle, eligibility, funding, budget hoặc control group. Không thể tạo campaign entity hay causal promotion analysis.

### L-17. Không có canonical brand/product/SKU

Brand chưa có master/alias mapping đã duyệt. Dataset không có `sku_id`, `model_id`, variation-level price/stock/sales và same-product labels. Vì vậy chưa thể làm canonical brand, same-product matching hoặc SKU analytics.

### L-18. Không đủ dữ liệu cho business outcome nâng cao

Thiếu transaction/order, traffic, conversion, cost, fee, margin, inventory variation, ad variation và chuỗi thời gian dài. Chưa thể cung cấp conversion/AOV/basket/GMV thật/profit, causal promotion uplift, forecast/seasonality, ads attribution hoặc inventory analytics.

### L-19. Image similarity chưa khả dụng

Checkout không có image binary/versioned visual feature và chưa có image relevance labels. `images_count` chỉ là metadata đếm. Chưa thể triển khai image embedding, multimodal similarity hoặc suy luận chất lượng content từ ảnh.

### L-20. Qualitative claim verifier chưa có ontology/labels

Numeric verifier không chứng minh được các claim định tính như “cùng dòng”, “brand uy tín”, “nội dung tốt” hoặc “tín hiệu mạnh”. Chưa có ontology, entailment policy và labeled claim-evidence set để kiểm chứng các câu này một cách deterministic hoặc calibrated.

### L-21. Cross-market monetary comparison cần reference data

Dataset không có currency field/FX series được quản trị. VND/IDR chỉ suy từ country. Muốn so tiền tuyệt đối VN–ID cần source tỷ giá versioned, observed date, license, content hash và time-drift policy; nếu không phải abstain.

## 5. External data extension chưa chạy được

`SourceLocator` và `ExternalRecord` đã có, nhưng chưa có:

- `ExternalSourceAdapter` runtime;
- source registry và allow-list;
- cache/checksum manifest;
- external entity map với exact/manual/review states;
- temporal/unit normalization;
- mixing rules giữa internal/reference/external evidence;
- fetch failure/unmapped/time-drift gate;
- integration tests bằng fake adapter.

Vì vậy kiến trúc “sẵn contract” nhưng chưa thể nạp một external analytical source chỉ bằng config. Mỗi source mới vẫn cần implementation và governance cụ thể.

## 6. Productization và vận hành

### L-22. API/UI chỉ dành cho MVP nội bộ

FastAPI và UI đã chạy, nhưng chưa có authentication, authorization, TLS termination, tenant isolation, CSRF/security headers, request/body quota, user-level rate limiting hoặc audit identity. Không expose trực tiếp lên Internet.

### L-23. Observability và concurrency chưa production-grade

Trace là local JSON per request. Chưa có structured centralized logs, metrics/alerts, distributed tracing, multi-worker file locking, request correlation qua reverse proxy, provider SLO hay automated retention job. Runtime và embedding cũng chưa có multi-process resource policy.

### L-24. Packaging/deployment chưa được xác nhận đầy đủ

`requirements.txt` có dependency nhưng `pyproject.toml` đang để `dependencies=[]`, nên wheel cài độc lập không kéo runtime dependency. Dockerfile chưa được build/smoke-test trong môi trường hiện tại; GitHub Actions chưa được xác nhận trên remote runner có data fixture. Chưa có migration/release/rollback procedure.

### L-25. Security/privacy chưa qua kiểm định độc lập

Đã có redaction và prompt-injection regression cơ bản, nhưng chưa có red-team, dependency/secret/container scan, privacy classification, retention enforcement job, legal/license review cho external data hoặc incident response procedure. Regex redaction không bảo đảm bắt mọi loại credential/PII.

## 7. Thứ tự khắc phục đề xuất

1. **Tính đúng đắn:** L-01 đến L-05.
2. **Contract/orchestration:** L-06 đến L-10.
3. **Evaluation:** L-11 đến L-15.
4. **Internal production hardening:** L-22 đến L-25.
5. **Mở capability:** L-16 đến L-21 chỉ sau khi có dữ liệu/ground truth tương ứng.

Mọi capability chưa đạt phải tiếp tục `clarify`, `abstain` hoặc fallback verified; không được thêm prompt để che khoảng trống schema, evidence hoặc evaluation.
