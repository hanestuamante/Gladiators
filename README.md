# Gladiators

Shopee dataset analysis project for Vietnam (`vn`) and Indonesia (`id`). The repo contains raw CSV data, processed analysis-ready tables, preprocessing documentation/notebook, and a research notebook for insight exploration.

## Project Structure

```text
Dataset/
  DataRaw/            Raw CSV files partitioned by country_code/dataset/shop_id
  DataProcessed/      Cleaned and analysis-ready CSV files

Preprocessing/
  preprocessing.md    Detailed preprocessing documentation
  preprocess_dataset.ipynb

Research/
  research.md         Research questions, hypotheses, and insight roadmap
  research.ipynb      Charts and EDA notebook

Documentation.md      Dataset context, table definitions, and relationships
requirements.txt      Runtime dependencies
requirements-dev.txt  Optional notebook/dev dependencies
```

## Setup

Recommended Python version: `3.11+`.

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

For optional notebook conversion/validation tools:

```bash
pip install -r requirements-dev.txt
```

Register the environment as a Jupyter kernel:

```bash
python -m ipykernel install --user --name gladiators --display-name "Python (Gladiators)"
```

## Data

Raw data is stored in:

```text
Dataset/DataRaw
```

Processed data is stored in:

```text
Dataset/DataProcessed
```

Main analysis table:

```text
Dataset/DataProcessed/product_dataset_ready.csv
```

Suggested target metric:

```text
estimated_recent_revenue = price_num * monthly_sold_value_num
```

Important caveats:

- `price` is treated as the displayed final price after visible voucher/promo effects in this dataset.
- `monthly_sold_value` is a Shopee-displayed recent/monthly sold metric; the exact day window is not confirmed.
- The dataset has only 3 snapshot dates (`2026-07-01` to `2026-07-03`), so avoid long-term trend or seasonality claims.
- `price = 999999999` appears in 3 rows and should be handled as an outlier/sentinel before price analysis.

## Preprocessing

Read the detailed preprocessing documentation:

```text
Preprocessing/preprocessing.md
```

Run preprocessing by opening and executing:

```text
Preprocessing/preprocess_dataset.ipynb
```

The notebook:

- reads all raw CSV files,
- adds metadata from paths,
- normalizes numeric/boolean/array fields,
- removes exact duplicates,
- creates clean per-table CSVs,
- creates `product_dataset_ready.csv`,
- writes `data_quality_report.json`.

## Research

Read the research roadmap:

```text
Research/research.md
```

Run charts and EDA in:

```text
Research/research.ipynb
```

Core research themes:

- Vietnam vs Indonesia market comparison.
- Revenue drivers.
- Voucher/promo effectiveness.
- Shop trust and shop performance.
- Category and merchandising strategy.
- Product presentation: images, brand, and title keywords.

## Documentation

Start with:

```text
Documentation.md
```

It explains:

- table meanings,
- column definitions,
- category ID differences,
- table relationships,
- preprocessing summary,
- folder structure,
- research scope and limitations.

## Git Notes

Ignored files include:

- Python cache files,
- `.DS_Store`,
- notebook checkpoint folders,
- local virtual environments.

Do not commit downloaded product images unless there is a deliberate data-storage plan. If image analysis is added later, prefer a separate cache/download script and document whether images should be versioned.
