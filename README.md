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
│   ├── V1_Architecture.md      # Kiến trúc Agent mục tiêu hiện hành
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
4. [Kiến trúc Agent V1 hiện hành](docs/V1_Architecture.md)
5. [Architecture Spec chi tiết](docs/Architecture-spec.md)
6. [Các phần V1 chưa thể thực hiện đầy đủ](docs/V1_Implementation_Limitations.md)
7. [Historical V0 architecture](docs/V0_Architecture.md)

Data Context and current artifacts remain the source of truth for data. `V1_Architecture.md` is the current target Agent architecture; `Architecture-spec.md` supplies detailed design patterns subject to the documented implementation gaps. `V0_Architecture.md` is retained only to explain superseded decisions.
# Gladiators V1

Thiết lập và kiểm thử runtime:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
bash scripts/configure_secrets.sh       # nhập key ẩn, chỉ lưu local
.venv/bin/python -m pytest
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 3
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

Kiến trúc chuẩn: [docs/V1_Architecture.md](docs/V1_Architecture.md). Các giới hạn còn lại: [docs/V1_Implementation_Limitations.md](docs/V1_Implementation_Limitations.md).

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
