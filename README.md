# Gladiators

Shopee product-listing snapshot pipeline for Vietnam (`vn`) and Indonesia (`id`). The current repository focuses on auditable preprocessing, snapshot validation and reproducible business metrics.

## Repository structure

```text
Gladiators/
├── data/
│   ├── raw/                    # 82 source CSV files, partitioned by country/dataset/shop
│   └── processed/              # Generated clean tables, metrics and quality reports
├── notebooks/
│   ├── pipeline/
│   │   └── data_pipeline.ipynb
│   └── tests/
│       └── test_data_pipeline.ipynb
├── docs/
│   ├── README.md               # Mục lục và giá trị của từng tài liệu
│   ├── CURRENT_ARCHITECTURE_SPEC.md
│   ├── reference/              # Data context, pipeline và code graph
│   ├── design/                 # Kiến trúc mục tiêu và đặc tả chuyên đề
│   ├── topics/                 # Topic cards và projection cho topic routing
│   ├── agents/                 # Ownership và quy ước triage/vận hành
│   ├── qa/                     # Kết quả và phân tích kiểm thử
│   ├── acceptance/             # Checklist nghiệm thu đang mở
│   └── archive/                # Kiến trúc cũ, handoff và báo cáo theo ngày
├── requirements.txt
└── requirements-dev.txt
```

Task/date folders are intentionally avoided. Artifacts live with the capability they implement, so there is one maintained pipeline and one maintained test notebook.

## Setup

Recommended Python version: 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run the pipeline from the repository root:

```bash
jupyter notebook notebooks/pipeline/data_pipeline.ipynb
```

Open the notebook and select **Run All**. It reads `data/raw` and writes `data/processed`.

Run the notebook test suite in the same way:

```bash
jupyter notebook notebooks/tests/test_data_pipeline.ipynb
```

## Outputs

| Artifact | Grain or role |
| --- | --- |
| `data/processed/products_clean.csv` | Clean product-listing snapshots |
| `data/processed/*_clean.csv` | Clean source tables with typed columns and provenance |
| `data/processed/product_snapshot_metrics.csv` | One row per listing snapshot |
| `data/processed/product_transition_metrics.csv` | One row per pair of consecutive observed snapshots |
| `data/processed/data_quality_issues.csv` | Row-level warnings/errors with source evidence |
| `data/processed/pipeline_report.json` | Key checks, snapshot coverage and issue summary |

Important metric semantics:

```text
estimated_recent_revenue = price_num * monthly_sold_value_num
```

This is a snapshot revenue proxy, not GMV, net revenue or profit. `monthly_sold_value` is a recent-window proxy with an unknown exact window. Do not aggregate it across the three snapshot dates.

## Documentation

Read in this order:

1. [Mục lục tài liệu](docs/README.md)
2. [Đặc tả kiến trúc hiện tại](docs/CURRENT_ARCHITECTURE_SPEC.md)
3. [Ngữ cảnh dữ liệu](docs/reference/Data_Context_and_Analysis_Notes.md)
4. [Pipeline và metrics](docs/reference/data-pipeline.md)
5. [Code graph](docs/reference/codegraph.md)
6. [Kiến trúc V2 mục tiêu](docs/design/V2_Unified_Architecture.md)

Source code, test và artifact hiện tại được ưu tiên cao nhất.
`CURRENT_ARCHITECTURE_SPEC.md` mô tả hiện trạng; `V2_Unified_Architecture.md`
mô tả thiết kế mục tiêu. Tài liệu V0/V1 được giữ trong `docs/archive` để truy vết.

# Gladiators V2 runtime

Thiết lập và kiểm thử runtime:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
bash scripts/configure_secrets.sh       # nhập key ẩn, chỉ lưu local
.venv/bin/python -m pytest
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 3
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --suite eval/questions_v2.json --runs 3
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --suite eval/questions_critic.json --runs 3 --enable-critic
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --suite eval/questions_a19.json --runs 3
PYTHONPATH=src .venv/bin/python scripts/build_eval_coverage_matrix.py
PYTHONPATH=src .venv/bin/python scripts/build_independent_oracle.py
```

Để chọn Gemini và thay key an toàn:

```bash
bash scripts/configure_gemini.sh
```

Để chọn Groq và nhập key an toàn:

```bash
bash scripts/configure_groq.sh
```

Lệnh trên chạy end-to-end offline, không gửi dữ liệu ra ngoài. Chỉ chạy Gemini sau khi đã duyệt nội dung được gửi:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 3 --provider gemini
```

Phase 6 live-search mặc định **OFF** và mode mặc định là `cache_only`. Offline/cache
replay không khởi tạo Tavily và không mở socket. Có thể chạy cache replay có chủ đích:

```bash
GLADIATORS_ENABLE_LIVE_SEARCH=1 \
GLADIATORS_LIVE_SEARCH_MODE=cache_only \
GLADIATORS_LLM_PROVIDER=groq \
PYTHONPATH=src .venv/bin/uvicorn gladiators.api:app
```

Mode `record`/`live` cần thêm `TAVILY_API_KEY`. Không có gate
`GLADIATORS_LIVE_SOURCE_REVIEWED` hay `GLADIATORS_LIVE_SEARCH_LICENSE`: E0 đã cho
phép Tavily làm demo context, còn nhãn provenance dự án được cấu hình bằng
`GLADIATORS_DEMO_EXTERNAL_LABEL` khi cần. Mọi record live bị clamp `context_only`,
không scrape/fetch URL Shopee, và cross-market currency conversion vẫn bị A16 chặn.

Trạng thái 23/07/2026: W1–W7 đã có implementation và **254 test pass trên macOS**;
W8 Tavily rehearsal và CI Windows/Linux chưa có bằng chứng, nên Phase 6 E6 vẫn
`PENDING`. Xem handoff ngày 23/07 và checklist sign-off trước khi bật mode mạng.

Build BGE-M3 có version và CPU benchmark:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_embeddings.py
```

Runtime hiện hỗ trợ ba certified macro kế thừa (`sales_decline`, `similar_product`, `promotion_effectiveness`), analytical templates L0–L2 và open analytical path P7/P8. P7 chỉ phát semantic refs từ catalog; P8 nhận catalog slice tối đa 30 object, sinh typed IR, qua deterministic validator và chỉ được repair một lần. Thất bại được tách riêng thành `A19-CAT`, `A19-OP`, `A19-METRIC` hoặc `A19-PLAN`. Câu analytical phải chọn riêng VN hoặc ID; không cộng chéo VND/IDR.

Query có join/risk trung như “shop nào có nhiều listing nhất” yêu cầu Plan Critic. Mặc định vẫn fail-closed; chỉ bật sau acceptance bằng `GLADIATORS_ENABLE_CRITIC=1` với provider đã cấu hình. Lệnh eval `--enable-critic` dùng acceptance stub offline, không phải bằng chứng chất lượng của model production.

Nhánh L4 có P10 alternate planner bị blind và P11 adjudicator bounded. Kill-switch N-version mặc định tắt; chỉ bật bằng `GLADIATORS_ENABLE_NVERSION=1` sau khi có acceptance/ablation L4. Nếu hai candidate khác kết quả mà adjudicator không chọn được bằng issue định danh, runtime trả `A19-PLAN`, không chọn ngẫu nhiên.

Eval analytical dùng golden oracle tại `eval/independent/`, được tính trực tiếp từ artifact và không import production planner/repository. `eval/coverage_matrix.json` được sinh từ catalog, relation registry, IR và tag của từng case; trường `phase_4_5_acceptance_ready` chỉ thành `true` khi phủ đủ mọi yêu cầu mục 14.9.

P7 deterministic fallback dùng longest-match trên toàn semantic catalog, không chỉ bảng từ khóa MVP. Acceptance hiện có 36 case schema-linking và test phân biệt alias lồng nhau như `shop rating`/`rating`, `price original`/`price`. Toàn bộ 12 IR operators đã có tối thiểu 3 positive và 1 adversarial case; operator SQL phải compile/execute thật, còn `ResolveValue`/`Similarity` được kiểm qua delegated certified macro.

Coverage gate mục 14.9 hiện có 198 question/fixture và phủ 158/158 requirements. Cả 10 relation edges có executable acceptance; query rỗng được trả như kết quả hợp lệ với `result_count=0`; sáu composite L4 chạy qua hai planner bị blind. Coverage 100% chỉ xác nhận đủ ô kiểm thử, không thay thế production-provider eval, human review hoặc ablation critic/N-version.

Phase 5 L4 có runner riêng vì fixture composite không dùng schema của evaluator V1:

```bash
# Kiểm wiring/oracle/ablation hoàn toàn offline; luôn NO-GO cho production.
PYTHONPATH=. .venv/bin/python scripts/run_phase5_evaluation.py \
  --provider offline --runs 3 --output artifacts/phase5/offline

# Chỉ chạy sau khi được phép gửi context đánh giá tới provider.
PYTHONPATH=. .venv/bin/python scripts/run_phase5_evaluation.py \
  --provider groq --runs 3 --output artifacts/phase5/groq
```

Không đặt `--gold-review-status approved` trước khi reviewer nghiệp vụ duyệt đủ semantics/gold của sáu case. Runner đo riêng denotation accuracy, plan/result disagreement, false-consensus, adjudication, stability và latency; offline provider không thể cho kết quả `GO`.

Kiến trúc hiện trạng:
[docs/CURRENT_ARCHITECTURE_SPEC.md](docs/CURRENT_ARCHITECTURE_SPEC.md).
Thiết kế mục tiêu:
[docs/design/V2_Unified_Architecture.md](docs/design/V2_Unified_Architecture.md).

Chạy API demo nội bộ:

```bash
PYTHONPATH=src .venv/bin/uvicorn gladiators.api:app --host 127.0.0.1 --port 8000
```

CLI offline, Hugging Face hoặc Gemini:

```bash
PYTHONPATH=src .venv/bin/python -m gladiators.cli 'Phân tích voucher tại VN'
PYTHONPATH=src .venv/bin/python -m gladiators.cli --provider huggingface 'Phân tích voucher tại VN'
PYTHONPATH=src .venv/bin/python -m gladiators.cli --provider gemini 'Phân tích voucher tại VN'
```
