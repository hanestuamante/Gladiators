# Minimum Data Pipeline and Metrics

Pipeline này chuyển dữ liệu Shopee raw thành các bảng sạch có audit trail, kiểm tra grain/key/snapshot và hiện thực hóa metrics đã được xác nhận trong [Data Context](Data_Context_and_Analysis_Notes.md).

## 1. Chạy pipeline

Pipeline chỉ lưu code dưới dạng notebook `.ipynb`, không duy trì bản `.py` song song. Từ thư mục gốc repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook notebooks/pipeline/data_pipeline.ipynb
```

Trong notebook, chọn **Run All**. Cell cuối dùng cấu hình:

```python
INPUT_DIR = REPO_ROOT / "data/raw"
OUTPUT_DIR = REPO_ROOT / "data/processed"
FAIL_ON_ERROR = False
```

Mặc định:

```text
Input:  data/raw
Output: data/processed
```

Để notebook dừng khi có lỗi severity `error`, đặt:

```python
FAIL_ON_ERROR = True
```

Warning không làm pipeline dừng vì dòng vẫn được giữ hoặc đã có audit trail rõ ràng. Error gồm schema/path mâu thuẫn, thiếu key, duplicate logical key, số/boolean/date/JSON không parse được.

## 2. Chính sách làm sạch

- Đọc đủ 82 CSV và bổ sung `country_code`, `shop_id` từ partition path khi raw thiếu.
- Giữ `source_file` và `source_row` để truy ngược mọi dòng.
- Chuyển số bằng `pandas.to_numeric(errors="coerce")`; giá trị lỗi thành null và đồng thời tạo issue `INVALID_NUMBER`, không tự đổi thành `0`.
- Boolean chỉ chấp nhận tập giá trị rõ ràng; JSON array sai cấu trúc được báo lỗi và count để null.
- Chỉ loại exact duplicate, đồng thời ghi từng dòng bị loại vào `data_quality_issues.csv`.
- Duplicate theo logical key không bị âm thầm loại; row được giữ và pipeline báo error.
- `image_overlay` và `image_overlay_hash` được giữ là scalar text. Preprocessing cũ từng coi hai field này là array và âm thầm trả count `0` khi parse thất bại.
- Ba dòng `price=999999999` được giữ và gắn `price_sentinel_flag=True`, nhưng giá/revenue metric liên quan để null.

Logical key được kiểm tra:

| Dataset | Key |
| --- | --- |
| `products` | `country_code + shop_id + item_id + date` |
| `shop_info` | `country_code + shop_id` |
| `category_list` | `country_code + shop_id + shop_category_id + date` |
| `product_categories` | `country_code + shop_id + item_id + category_id + date` |
| `category_platform` | `country_code + category_id` |

Pipeline cũng kiểm tra các quan hệ product-shop, product-category mapping, shop-category mapping và platform category trong đúng phạm vi quốc gia/shop/date.

## 3. Kiểm tra snapshot

Grain trung tâm là **product listing snapshot**, không phải SKU:

```text
product_listing_key  = country_code + shop_id + item_id
product_snapshot_key = product_listing_key + date
```

Kết quả chạy hiện tại:

| Check | Kết quả |
| --- | ---: |
| Product snapshot sau exact dedup | 3.341 |
| Product listing | 1.157 |
| Duplicate logical key sau dedup | 0 |
| Ngày snapshot | 3 |
| Balanced panel cells kỳ vọng | 3.471 |
| Snapshot cells quan sát | 3.341 |
| Snapshot thiếu | 130 |
| Listing có internal gap | 5 |
| Listing thiếu ở biên | 113 |

Chỉ 5 listing có ngày đầu và cuối nhưng thiếu ngày giữa được gắn `snapshot_gap_flag=True`. Transition cách nhau hơn một ngày vẫn được xuất để truy vết, nhưng `transition_metric_eligible=False` và các delta để null.

## 4. Metrics đã chuyển thành code

### Snapshot metrics

| Metric | Code/formula | Guardrail |
| --- | --- | --- |
| Estimated Recent Revenue | `price_num * monthly_sold_value_num` | Revenue proxy tại một snapshot, không phải GMV/profit; null với price sentinel |
| Discount Amount | `price_original_num - price_num` | Không trừ voucher lần nữa |
| Discount Percent Analysis | raw `discount_percent_num`; chỉ fill `0` nếu `price == price_original` | Là tổng displayed discount, không phải promo-only |
| Pre-final Reduction Proxy | `100 * (price_original - price_before_promo) / price_original` | Proxy, không gọi là campaign uplift |
| Structured Voucher | `voucher_discount_num > 0` | Không suy từ nhãn trong `vouchers` |
| Displayed Discount | `discount_percent_analysis > 0` | Không đặt tên `has_promo` |
| Promotion ID Clean | `promotion_id_num`, đổi sentinel `0` thành null | Không dùng thay item/campaign master |

### Transition metrics

Các metric chỉ tính khi cùng `product_listing_key` và hai snapshot cách nhau đúng một ngày:

| Metric | Formula/hành vi |
| --- | --- |
| Price Change | `price(T) - price(T-1)` |
| Price Change Percent | `price_change / price(T-1) * 100` |
| Discount Point Change | `discount_percent(T) - discount_percent(T-1)` |
| Monthly Sold Delta | `monthly_sold_value(T) - monthly_sold_value(T-1)`; đây là biến động rolling proxy, không phải daily sales |
| History Sold Delta Raw | `history_sold_value(T) - history_sold_value(T-1)` |
| Snapshot Sales Delta Clean | Giữ history delta không âm; đặt null nếu cumulative proxy giảm |
| Rating Change | `rating(T) - rating(T-1)` |
| New Rating Count | `rating_count(T) - rating_count(T-1)` |
| Like Delta | `liked_count(T) - liked_count(T-1)` |
| Stock Status | available/newly sold out/restocked/still sold out; hiện dữ liệu chỉ quan sát available |

Không cộng snapshot metrics qua ba ngày. Mọi aggregate cross-sectional phải chọn một snapshot/date để mỗi listing chỉ đóng góp một lần.

## 5. Output và kết quả chất lượng

| Output | Nội dung |
| --- | --- |
| `*_clean.csv` | Năm bảng sạch, giữ raw fields + typed fields + provenance |
| `product_snapshot_metrics.csv` | 3.341 dòng metric đúng grain listing-snapshot |
| `product_transition_metrics.csv` | 2.184 cặp quan sát kế tiếp trong chuỗi listing; 5 cặp cách hai ngày được đánh dấu không eligible |
| `data_quality_issues.csv` | Mỗi anomaly kèm severity, code, nguồn, key, field và raw value |
| `pipeline_report.json` | Tổng hợp rows, key checks, snapshot coverage, issue counts và status |

Lần chạy hiện tại có status `passed_with_warnings`, không có conversion/key error. 244 warning gồm:

| Warning | Count | Xử lý |
| --- | ---: | --- |
| Exact duplicate raw | 30 | Loại khỏi clean output, giữ evidence |
| Listing thiếu snapshot ở biên | 113 | Giữ row, không tự kết luận lỗi crawl |
| Internal snapshot gap | 5 | Gắn flag, không tính delta qua gap |
| `history_sold_value` giảm | 88 | Giữ raw delta, clean incremental metric để null |
| Category mapping không có product snapshot | 5 | Giữ mapping và báo orphan |
| Price sentinel | 3 | Giữ row, loại khỏi price/revenue metrics |

## 6. Kiểm thử

Mở `notebooks/tests/test_data_pipeline.ipynb` từ thư mục gốc repo và chọn **Run All**. Notebook test nạp `data_pipeline.ipynb`, chạy pipeline rồi thực thi test suite bằng `unittest`.

Test bao phủ parse JSON lỗi, chuyển số lỗi không bị biến thành `0`, row/key/snapshot counts, 30 duplicate, 5 internal gap, 88 cumulative anomaly, 3 price sentinel, và bảo đảm delta sạch để null ở anomaly/gap.
