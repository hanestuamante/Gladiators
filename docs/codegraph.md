# Pipeline Code Graph

Tài liệu này biểu diễn code hiện hành ở hai tầng: (1) **preprocessing** trong `notebooks/pipeline/data_pipeline.ipynb` (raw → `data/processed`), và (2) **runtime agent** trong `src/gladiators/` (câu hỏi → answer verified, mục "Runtime agent flow (S1–S9)"). Các graph dùng Mermaid và render trực tiếp trên GitHub hoặc Markdown Preview hỗ trợ Mermaid.

## Repository flow

```mermaid
flowchart LR
    RAW["data/raw<br/>82 CSV"] --> PIPE["data_pipeline.ipynb"]
    PIPE --> CLEAN["*_clean.csv<br/>(products, shop_info,<br/>category_list/platform,<br/>product_categories)"]
    PIPE --> SNAP["product_snapshot_metrics.csv"]
    PIPE --> TRANS["product_transition_metrics.csv"]
    PIPE --> ISSUES["data_quality_issues.csv"]
    PIPE --> REPORT["pipeline_report.json"]
    TEST["test_data_pipeline.ipynb"] -->|loads and tests| PIPE
    CLEAN & SNAP & TRANS & ISSUES & REPORT --> OUT["data/processed"]

    OUT --> COVGEN["scripts/build_semantic_coverage_manifest.py<br/>→ data/coverage.py"]
    COVGEN --> MANIFEST["semantic_coverage_manifest.json<br/>(ghi vào data/processed)"]
    MANIFEST --> OUT

    OUT -->|"products_clean + snapshot + transition<br/>+ manifest (validate lúc khởi động)"| AGENT["Runtime agent<br/>ArtifactRepository / validate_artifacts"]
```

> `semantic_coverage_manifest.json` KHÔNG do notebook sinh — nó do `scripts/build_semantic_coverage_manifest.py` (gọi `src/gladiators/data/coverage.py`) tạo từ `data/processed`, rồi được `data/contracts.py` validate lúc agent khởi động. Agent runtime chỉ đọc `products_clean.csv`, `product_snapshot_metrics.csv`, `product_transition_metrics.csv` (qua `ArtifactRepository`) cộng manifest — không chạm notebook.

## Function call graph

```mermaid
flowchart TD
    RUN["run_pipeline(input_dir, output_dir)"] --> LOAD["load_raw"]
    LOAD --> PATH["parse_path"]
    LOAD --> TEXT["clean_text"]
    LOAD --> ISSUE["add_issue"]

    RUN --> NORMALIZE["normalize"]
    NORMALIZE --> BOOL["safe_bool"]
    NORMALIZE --> ARRAY["safe_array"]
    NORMALIZE --> TEXT
    NORMALIZE --> ISSUE

    RUN --> REL["check_relationships"]
    REL --> ISSUE

    RUN --> COVERAGE["add_snapshot_checks"]
    COVERAGE --> ISSUE

    RUN --> METRICS["build_metrics"]
    METRICS --> ISSUE

    RUN --> WRITE["write_outputs"]
    WRITE --> CLEAN_OUT["clean tables"]
    WRITE --> METRIC_OUT["snapshot and transition metrics"]
    WRITE --> QUALITY_OUT["issues and report"]

    ISSUE --> ENTITY["entity_key"]
    ENTITY --> TEXT
```

## Validation and error flow

```mermaid
flowchart TD
    ROW["Raw row + source_file + source_row"] --> SCHEMA{"Schema/path valid?"}
    SCHEMA -->|No| ERROR["Issue severity: error"]
    SCHEMA -->|Yes| PARSE{"Typed values parse?"}
    PARSE -->|No| NULL["Typed value = null"]
    NULL --> ERROR
    PARSE -->|Yes| KEY{"Logical key complete and unique?"}
    KEY -->|No| ERROR
    KEY -->|Yes| DUP{"Exact duplicate?"}
    DUP -->|Yes| WARN_DUP["Warning + exclude duplicate from clean output"]
    DUP -->|No| KEEP["Retain clean row"]
    KEEP --> SNAPSHOT{"Snapshot gap or known anomaly?"}
    SNAPSHOT -->|Yes| WARN["Warning + flag + retain evidence"]
    SNAPSHOT -->|No| VALID["Metric eligible"]
    WARN --> GUARDED["Metric null/guarded where unsafe"]
    ERROR --> REPORT["data_quality_issues.csv + pipeline_report.json"]
    WARN_DUP --> REPORT
    WARN --> REPORT
```

Pipeline không đổi giá trị lỗi thành `0` và không âm thầm loại logical-key conflict. Chỉ exact duplicate được bỏ khỏi clean output, nhưng từng dòng bị bỏ vẫn có evidence trong issue table.

## Metric dependency graph

```mermaid
flowchart LR
    PRICE["price_num"] --> SENTINEL{"price != 999999999"}
    MONTHLY["monthly_sold_value_num"] --> REVENUE["estimated_recent_revenue"]
    SENTINEL --> REVENUE

    ORIGINAL["price_original_num"] --> DISCOUNT_AMOUNT["discount_amount"]
    SENTINEL --> DISCOUNT_AMOUNT
    ORIGINAL --> PRE_FINAL["pre_final_reduction_proxy"]
    BEFORE["price_before_promo_num"] --> PRE_FINAL

    DISCOUNT_RAW["discount_percent_num"] --> DISCOUNT_ANALYSIS["discount_percent_analysis"]
    ORIGINAL --> ZERO_RULE["fill 0 only when price = original"]
    PRICE --> ZERO_RULE
    ZERO_RULE --> DISCOUNT_ANALYSIS
    DISCOUNT_ANALYSIS --> DISPLAYED["has_displayed_discount"]

    VOUCHER["voucher_discount_num"] --> STRUCTURED["has_structured_voucher"]
    PROMO["promotion_id_num"] --> PROMO_CLEAN["promotion_id_clean<br/>0 becomes null"]
```

```mermaid
flowchart LR
    PREV["Snapshot T-1"] --> ELIGIBLE{"Same listing and day gap = 1?"}
    CURR["Snapshot T"] --> ELIGIBLE
    ELIGIBLE -->|No| NULLS["Transition metrics = null"]
    ELIGIBLE -->|Yes| DELTAS["price / discount / monthly sold / rating / like deltas"]
    ELIGIBLE --> HISTORY["history_sold_delta_raw"]
    HISTORY --> DECREASE{"delta < 0?"}
    DECREASE -->|Yes| ANOMALY["history_sold_decrease_flag = true"]
    ANOMALY --> CLEAN_NULL["snapshot_sales_delta_clean = null"]
    DECREASE -->|No| CLEAN_DELTA["snapshot_sales_delta_clean = raw delta"]
```

## Reading order

1. `run_pipeline` để hiểu orchestration.
2. `load_raw` và `normalize` để hiểu provenance và chuyển kiểu.
3. `check_relationships` và `add_snapshot_checks` để hiểu data-quality contract.
4. `build_metrics` để hiểu snapshot/transition semantics.
5. `write_outputs` để hiểu artifact và trạng thái pass/fail.

## Runtime agent flow (S1–S9)

Graph này biểu diễn `AgentRuntime.run()` (`src/gladiators/agent/workflow.py`) theo bảng giai đoạn S1–S9 của `V2_Unified_Architecture.md §1.1–1.2`. Đường nét liền = đã triển khai và chạy; nét đứt/nhãn `[OFF]` = có contract/code nhưng cờ mặc định tắt hoặc chưa có adapter.

```mermaid
flowchart TD
    Q["User query (vi/id, có thể không dấu)"] --> S1

    S1["S1 · Dual Intent Parse<br/>parser.py (+ llm.py optional, safety precedence)<br/>→ StructuredRequest / AnalyticalRequest + route_mode"] --> S2
    S2["S2 · Capability Router (rule)<br/>router.classify_external_need + semantic_parser.classify_a19/complexity<br/>→ tool_plan + A19 class"] --> S3DEC

    S3DEC{"intent cần entity slot?"}
    S3DEC -->|có| S3["S3 · Entity Resolution<br/>resolver.py: rapidfuzz → BGE-M3 rerank"]
    S3DEC -->|aggregate/không cần| S4
    S3 -->|margin thấp| CLAR["CLARIFY"]
    S3 --> S4

    S4{"S4 · Gate-pre<br/>gate.ContractDrivenGate + A19 / T-11<br/>allow · abstain · clarify"}
    S4 -->|abstain/clarify| OUTA["Structured Abstain / Clarify (4 phần)"]
    S4 -->|allow| DISP["tool_dispatch.dispatch(tool_plan)"]

    DISP --> S5a
    DISP --> S5c
    DISP -.-> S5b

    subgraph S5a["S5a · Internal Analytical Engine — deterministic, không LLM tính số"]
        direction TB
        MACRO["Certified Macro (4)<br/>macros.py: sales_decline, similar_product,<br/>promotion_effectiveness, voucher_profile_rank<br/>+ evidence contract"]
        OPEN["Open Analytical<br/>analytical.py template / open_planner.py (P8)"]
        OPEN --> VAL["Plan Validator (code)<br/>validator.py: refs/join/grain/dedupe/unit/trap"]
        VAL -->|fail| REPAIR["bounded repair | A19-PLAN"]
        VAL --> RISK["QueryRiskScore<br/>risk.py → single/critic/nversion"]
        RISK -->|risk cao| CRIT["Critic P9 / N-version P10–P11<br/>critic.py · consensus.py"]
        RISK --> COMP["Compiler IR→SQL AST<br/>compiler.py (SQLGlot, SELECT-only)"]
        CRIT --> COMP
        MACRO --> COMP
        COMP --> EXEC["Executor<br/>executor.py: DuckDB read-only + postconditions"]
    end

    subgraph S5c["S5c · External Research — Phase 6, cờ mặc định OFF"]
        direction TB
        P5["Live-search Planner P5<br/>search_planner.py"] --> XEX["Executor + cache + quota<br/>search_executor.py"]
        XEX --> RELV["Relevance gate (code)<br/>relevance.py — loại rác trước P6"]
        RELV --> P6["P6 Extractor (LLM)<br/>web_extract.py — untrusted, span-bound"]
        P6 --> ADM["Admission A15/A17/A18<br/>admission.py → context_only"]
    end

    S5b["S5b · Reference Provider (Tier A FX)<br/>[OFF — chưa có adapter]"]

    EXEC --> S6
    ADM --> S6
    S5b -.-> S6

    S6["S6 · Admitted Evidence Store<br/>evidence_id · source_tier · input_hash · dataset_version · provenance"] --> S7
    S6 -->|không có evidence| NOEV["A-NO-EVIDENCE abstain"]

    S7["S7 · Response Generator<br/>deterministic template | LLM (llm.py)<br/>+ caveats từ metric registry + wording gate (wording.py)"] --> S8

    S8{"S8 · Claim Verifier<br/>verifier.py: numeric scan + per-claim<br/>value/unit/path/tier/citation"}
    S8 -->|fail lần 1| S7
    S8 -->|fail lần 2| FB["verified deterministic fallback"]
    S8 -->|pass| S9
    FB --> S9

    S9{"S9 · Gate-output<br/>final verify (require_claims) + mixing/source label"}
    S9 -->|fail| VF["A-VERIFICATION-FINAL abstain"]
    S9 -->|pass| ANS["Answer 9 phần + Sources theo tier"]

    classDef offNode stroke-dasharray:5 5;
    class S5b,P5,XEX,RELV,P6,ADM offNode;
```

**Ánh xạ stage → module chính:**

| Stage | Module | Ghi chú |
| --- | --- | --- |
| S1 | `agent/parser.py`, `agent/llm.py` | deterministic luôn chạy; LLM parse là tuỳ chọn, có safety precedence |
| S2 | `external/router.py`, `planner/semantic_parser.py` | route + A19/complexity bằng rule, không LLM |
| S3 | `agent/resolver.py` | rapidfuzz → BGE-M3 (BGE bật bằng `GLADIATORS_ENABLE_BGE=1`) |
| S4 | `agent/gate.py` | ContractDrivenGate; T-11 clarify cho voucher_profile khi cờ OFF |
| S5a | `planner/{analytical,open_planner,validator,risk,critic,consensus,compiler,executor,macros}.py` | validator/compiler/executor 100% code |
| S5b | — | Tier A FX OFF (config `sources.reference.enabled: false`, chưa có adapter) |
| S5c | `external/{search_planner,search_executor,relevance,web_extract,admission,pipeline}.py` | code đủ, cờ `GLADIATORS_ENABLE_LIVE_SEARCH` mặc định OFF |
| S6 | `contracts.py` (Evidence), `analytics/tools.py` | chỉ ghi record đã qua checkpoint |
| S7 | `agent/workflow.py::_generate`, `agent/wording.py`, `agent/llm.py` | template deterministic hoặc LLM; wording gate chặn nhân quả/forecast/SKU |
| S8 | `agent/verifier.py` | pass 1 numeric answer-wide + pass 2 per-claim binding |
| S9 | `agent/workflow.py` (final verify) | `A-VERIFICATION-FINAL` nếu claim binding fail |
