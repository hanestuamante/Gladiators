# Pipeline Code Graph

Tài liệu này biểu diễn code hiện hành trong `notebooks/pipeline/data_pipeline.ipynb`. Các graph dùng Mermaid và render trực tiếp trên GitHub hoặc Markdown Preview hỗ trợ Mermaid.

## Repository flow

```mermaid
flowchart LR
    RAW["data/raw<br/>82 CSV"] --> PIPE["data_pipeline.ipynb"]
    PIPE --> CLEAN["*_clean.csv"]
    PIPE --> SNAP["product_snapshot_metrics.csv"]
    PIPE --> TRANS["product_transition_metrics.csv"]
    PIPE --> ISSUES["data_quality_issues.csv"]
    PIPE --> REPORT["pipeline_report.json"]
    TEST["test_data_pipeline.ipynb"] -->|loads and tests| PIPE
    CLEAN & SNAP & TRANS & ISSUES & REPORT --> OUT["data/processed"]
```

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
