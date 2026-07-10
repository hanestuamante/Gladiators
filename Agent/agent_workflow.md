# Product Knowledge Agent Workflow

## 1. Phạm vi

Workflow local này dùng:

```text
Dataset/DataProcessed/product_dataset_ready.csv
Dataset/DataProcessed/category_platform_clean.csv
```

Mục tiêu là tạo câu trả lời có evidence cho `sales_decline`, `similar_product` và `promotion_effectiveness`. Workflow không tự tạo SKU ID, đơn hàng, margin, conversion rate hoặc causal effect khi dữ liệu chưa có.

## 2. Nơi chạy

Giai đoạn hiện tại nên chạy trên máy cá nhân bằng Python/Jupyter. Codex Plus hỗ trợ xây dựng và kiểm tra repo; nó không phải server runtime liên tục cho người dùng cuối.

```text
Local Python/Jupyter
  -> preprocessing
  -> feature preparation
  -> deterministic analysis
  -> evidence JSON/table
  -> Agent answer layer
```

MVP sau này có thể bọc analysis functions bằng API hoặc MCP read-only. MCP chỉ là giao diện gọi tool, không chứa logic nghiệp vụ riêng.

## 3. Nguyên tắc bất biến

1. Chỉ dùng `DataProcessed` cho phân tích; giữ `DataRaw` nguyên trạng.
2. Mọi kết quả lưu scope gồm `country_code`, `shop_id`, `item_id`, `date` khi có.
3. Không trừ `voucher_discount` lần hai khỏi `price`.
4. `monthly_sold_value` là sales proxy, không phải order count hay revenue thật.
5. Promotion comparison là observational comparison.
6. Không join platform category và shop category bằng cùng một `category_id`.
7. Entity resolution không chắc thì trả `insufficient_evidence` hoặc yêu cầu chọn lại.

## 4. Contract

### Input

```json
{
  "question": "Vì sao doanh số sản phẩm A giảm?",
  "country_code": "vn",
  "shop_id": 108166524,
  "item_id": 123,
  "date_from": null,
  "date_to": null,
  "top_k": 5
}
```

Field chưa xác định phải là `null`, không được tự điền từ một sản phẩm bất kỳ.

### Output

```json
{
  "status": "ok",
  "intent": "sales_decline",
  "scope": {},
  "answer": "...",
  "evidence": [],
  "calculations": [],
  "confidence": "low",
  "limitations": [],
  "next_action": "..."
}
```

`status` gồm `ok`, `insufficient_evidence`, `ambiguous_entity`, `data_quality_issue` và `unsupported_question`.

## 5. Các bước thực thi

### Bước 1: Intent

Intent được hỗ trợ:

```text
sales_decline
similar_product
promotion_effectiveness
category_relation
product_lookup
```

Ngoài phạm vi thì nói rõ chưa hỗ trợ.

### Bước 2: Entity resolution

Ưu tiên:

```text
country_code + shop_id + item_id
country_code + product URL/key
country_code + exact product name
country_code + controlled name search
```

Tên gần giống chỉ tạo candidate list. Không tự xem candidate đầu tiên là entity đúng khi có nhiều kết quả.

### Bước 3: Scope validation

Kiểm tra `country_code`, quan hệ `shop_id`, quan hệ `item_id` và các `date` có trong dữ liệu. Nếu thiếu scope, output phải ghi thiếu field nào.

### Bước 4: Retrieval

Chỉ lấy dòng liên quan từ:

```text
product_dataset_ready.csv: product/shop/sales/promo/content
category_platform_clean.csv: platform category
```

Không đưa toàn bộ CSV vào prompt. Analysis function trả bảng nhỏ, đã sắp xếp và giới hạn số dòng.

### Bước 5: Deterministic analysis

Median, change, rank, price distance và groupby phải nằm trong code/notebook có thể chạy lại. LLM chỉ diễn giải kết quả, không tự tính số bằng văn bản.

### Bước 6: Evidence assembly

Mỗi evidence cần có `source_table`, `source_columns`, `filters`, `observed_date`, `value` và `calculation_note`.

### Bước 7: Explanation

Xếp hạng explanation theo evidence, không theo câu chuyện nghe hợp lý. Dùng nhãn `observed`, `consistent signal`, `possible explanation` và `not identifiable from current data`.

### Bước 8: Verification

Kiểm tra entity, scope, unit, phép tính, evidence và causal overclaim trước khi trả lời.

## 6. Logic từng intent

### `sales_decline`

Chỉ gọi là “giảm” khi có từ hai snapshot của cùng product. Evidence ưu tiên `monthly_sold_value_num`, giá, promo/voucher, rating, trust và peer comparison. `history_sold_value_num` là chỉ số tích lũy, không phải biến động theo thời gian.

### `similar_product`

Phân biệt:

```text
same_product: cần nhãn/định danh đáng tin cậy
similar_product: baseline feature similarity
```

Score phải trả component riêng: category, brand, text, price, variation và image nếu có. Không gọi điểm này là accuracy khi chưa có validation set.

### `promotion_effectiveness`

Nhóm ban đầu: `no_promo`, `promo_only`, `voucher_only`, `promo_and_voucher`. Mỗi kết quả phải có `product_count`, median sales proxy và baseline. Không chỉ xếp hạng theo tổng doanh thu proxy.

## 7. Image pipeline

Lưu ảnh ngoài raw/processed:

```text
Dataset/ImageCache/
  manifest.csv
  files/
```

Manifest tối thiểu: `country_code`, `item_id`, `image_url`, `local_path`, `status`, `http_status`, `sha256`, `downloaded_at`.

Giai đoạn 1 kiểm tra URL, HTTP status, định dạng, kích thước và ảnh trùng. Giai đoạn 2 mới trích xuất embedding; mỗi embedding gắn `model_name`, `model_version` và timestamp.

Chạy downloader theo scope:

```bash
python3 scripts/download_images.py \
  --country vn \
  --shop-id 108166524 \
  --output-dir Dataset/ImageCache
```

Nếu môi trường phát triển báo lỗi chứng chỉ self-signed với domain ảnh, chỉ dùng `--insecure` cho đúng host ảnh và ghi nhận rủi ro trong log. Không dùng tùy chọn này như mặc định trong production.

## 8. MCP MVP sau này

Tool read-only dự kiến:

```text
find_product
compare_product_snapshots
find_similar_products
evaluate_promotions
explain_category_relation
verify_analysis
```

Không nhận arbitrary SQL hoặc arbitrary file path. Input phải có schema, scope, date range và `top_k`. MCP chỉ được xem là hoàn chỉnh khi cùng input cho ra cùng analysis result trước khi LLM diễn giải.

## 9. Lộ trình

```text
Phase 1: workflow spec + deterministic calculations + evidence contract
Phase 2: local analysis functions/notebook
Phase 3: evaluation cases và regression checks
Phase 4: image download/cache optional
Phase 5: MCP read-only adapter
Phase 6: UI/API MVP
```

Không đưa Phase 4-6 vào requirements trước khi Phase 1-3 ổn định.
