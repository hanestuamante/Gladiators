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
4. [Historical V0 architecture](docs/V0_Architecture.md)

The first three are current. `V0_Architecture.md` is retained only to explain superseded decisions.
