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
│   ├── Data_Context_and_Analysis_Notes.md
│   ├── V2_Unified_Architecture.md # Kiến trúc Agent mục tiêu hiện hành
│   ├── V1_Architecture.md      # Runtime baseline kế thừa
│   ├── Architecture-spec.md    # Kiến trúc tham chiếu chi tiết
│   ├── V1_Implementation_Limitations.md
│   ├── data-pipeline.md        # Pipeline contract, metrics and run instructions
│   ├── codegraph.md            # Data flow, function graph and metric dependencies
│   └── V0_Architecture.md      # Superseded architecture retained for history
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

1. [Data context](docs/Data_Context_and_Analysis_Notes.md)
2. [Pipeline and metrics](docs/data-pipeline.md)
3. [Code graph](docs/codegraph.md)
4. [Kiến trúc Agent V2 hợp nhất](docs/V2_Unified_Architecture.md)
5. [Kiến trúc V1 baseline](docs/V1_Architecture.md)
6. [Architecture Spec chi tiết](docs/Architecture-spec.md)
7. [Các phần V1 chưa thể thực hiện đầy đủ](docs/V1_Implementation_Limitations.md)
8. [Historical V0 architecture](docs/V0_Architecture.md)

Data Context and current artifacts remain the source of truth for data. `V2_Unified_Architecture.md` is the current target Agent architecture; V1 remains the compatibility and parity baseline. `V0_Architecture.md` is retained only to explain superseded decisions.

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

Kiến trúc chuẩn: [docs/V2_Unified_Architecture.md](docs/V2_Unified_Architecture.md). V1 được giữ làm parity baseline: [docs/V1_Architecture.md](docs/V1_Architecture.md).

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
