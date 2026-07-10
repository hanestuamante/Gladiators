# Preprocessing Documentation

Tài liệu này mô tả riêng phần xử lý dữ liệu trước khi phân tích. Mục tiêu là giải thích rõ:

- Raw data có những vấn đề gì.
- Preprocessing đã xử lý từng vấn đề như thế nào.
- Mỗi bảng sau xử lý có thêm cột gì.
- Mỗi bảng đóng góp gì vào mạch phân tích doanh thu/insight.

Chi tiết bối cảnh và ý nghĩa nghiệp vụ của từng bảng nằm ở `Documentation.md`. File này tập trung vào kỹ thuật xử lý dữ liệu.

## 1. File chính

Notebook preprocessing:

```text
Preprocessing/preprocess_dataset.ipynb
```

Input:

```text
Dataset/DataRaw
```

Output:

```text
Dataset/DataProcessed
```

Khi cần chạy lại preprocessing, mở notebook và chạy các cell theo thứ tự. Notebook sẽ ghi đè các file output trong `Dataset/DataProcessed`.

## 2. Tổng quan dữ liệu raw và output

Dataset raw có 82 file CSV, chia theo:

```text
Dataset/DataRaw/
  country_code=<vn|id>/
    dataset=<dataset_name>/
      shop_id=<shop_id>/
        <dataset_name>.csv
```

Riêng `category_platform` không có `shop_id` vì đây là taxonomy cấp nền tảng.

| Bảng | Raw rows | Processed rows | File output | Vai trò phân tích |
| --- | ---: | ---: | --- | --- |
| `products` | 3,371 | 3,341 | `products_clean.csv` | Bảng trung tâm: sản phẩm, giá, rating, lượt bán, voucher/promo |
| `shop_info` | 20 | 20 | `shop_info_clean.csv` | Bổ sung uy tín/quy mô/vận hành shop |
| `category_list` | 491 | 491 | `category_list_clean.csv` | Danh mục/kệ nội bộ từng shop |
| `product_categories` | 4,054 | 4,054 | `product_categories_clean.csv` | Mapping sản phẩm vào kệ nội bộ shop |
| `category_platform` | 4,482 | 4,482 | `category_platform_clean.csv` | Taxonomy ngành hàng chuẩn của Shopee |
| `product_dataset_ready` | - | 3,341 | `product_dataset_ready.csv` | Bảng chính dùng nhanh cho phân tích |

## 3. Vấn đề trong raw data và cách xử lý chung

### 3.1. Dữ liệu bị chia nhỏ theo thư mục

Raw data không nằm trong một file duy nhất mà tách theo `country_code`, `dataset`, `shop_id`.

Xử lý:

- Đọc toàn bộ file CSV trong `Dataset/DataRaw`.
- Parse metadata từ đường dẫn:
  - `path_country_code`
  - `path_dataset`
  - `path_shop_id`
- Thêm `source_file` để truy ngược dòng dữ liệu đến file raw ban đầu.

Đóng góp phân tích:

- Có thể phân tích theo quốc gia `vn`/`id`.
- Có thể kiểm tra shop/dataset nào sinh ra dòng dữ liệu.
- Dễ debug nếu một dòng bất thường.

### 3.2. Một số bảng thiếu `country_code` hoặc `shop_id`

Ví dụ:

- `product_categories.csv` raw không có `country_code`.
- `category_platform.csv` raw không có `country_code` và không có `shop_id`.

Xử lý:

- Nếu `country_code` bị thiếu, bổ sung từ `path_country_code`.
- Nếu `shop_id` bị thiếu và path có `shop_id`, bổ sung từ `path_shop_id`.

Đóng góp phân tích:

- Giúp join bảng an toàn hơn.
- Tránh mất ngữ cảnh quốc gia khi so sánh `vn` và `id`.

### 3.3. Kiểu dữ liệu trong CSV đều là text

CSV đọc vào ban đầu khiến giá, rating, lượt bán, follower, category ID đều là text.

Xử lý:

- Tạo thêm cột số với suffix `_num`.
- Ví dụ:
  - `price` -> `price_num`
  - `rating` -> `rating_num`
  - `monthly_sold_value` -> `monthly_sold_value_num`
  - `follower_count` -> `follower_count_num`

Đóng góp phân tích:

- Có thể tính toán, groupby, correlation, chart.
- Tránh lỗi khi model/EDA dùng nhầm text thay vì numeric.

### 3.4. Boolean đang ở dạng text

Các cột như `True`, `False` trong raw là text.

Xử lý:

- Tạo thêm cột boolean chuẩn hóa với suffix `_bool`.
- Ví dụ:
  - `is_ad` -> `is_ad_bool`
  - `is_sold_out` -> `is_sold_out_bool`
  - `shopee_verified` -> `shopee_verified_bool`
  - `is_official_shop` -> `is_official_shop_bool`

Đóng góp phân tích:

- Dễ lọc nhóm official/non-official.
- Dễ so sánh nhóm có/không có trạng thái.

### 3.5. Một số cột là JSON array được lưu trong CSV

Ví dụ trong `products`:

- `images`
- `seller_flag`
- `vouchers`
- `global_catids`
- `tier_variation_options`
- `rating_count_detail`

Xử lý:

- Parse JSON array.
- Tạo cột đếm với suffix `_count`.
- Ví dụ:
  - `images` -> `images_count`
  - `vouchers` -> `vouchers_count`
  - `global_catids` -> `global_catids_count`
  - `tier_variation_options` -> `tier_variation_options_count`

Đóng góp phân tích:

- `images_count`: kiểm tra sản phẩm nhiều ảnh có bán tốt hơn không.
- `vouchers_count`: đo độ dày ưu đãi.
- `global_catids_count`: biết độ sâu cây ngành hàng Shopee.
- `tier_variation_options_count`: biết sản phẩm có nhiều lựa chọn biến thể không.

### 3.6. Text có thể thừa khoảng trắng

Một số text có khoảng trắng không đều.

Xử lý:

- Strip đầu/cuối.
- Collapse nhiều khoảng trắng thành một khoảng trắng.
- Với `products`, tạo thêm `product_name_clean`.

Đóng góp phân tích:

- Dễ tìm keyword trong tên sản phẩm.
- Tránh cùng một tên bị xem là khác nhau chỉ vì khoảng trắng.

### 3.7. Duplicate exact

Raw `products` có 3,371 dòng. Có 30 dòng bị lặp y hệt.

Xử lý:

- Deduplicate exact row trên toàn bộ dictionary dòng.
- Chỉ `products` bị loại duplicate.

Kết quả:

```text
products raw = 3,371
products processed = 3,341
exact duplicate products removed = 30
```

Đóng góp phân tích:

- Tránh đếm trùng sản phẩm.
- Tránh phóng đại doanh thu/lượt bán.

### 3.8. Kiểm tra mismatch giữa path và dữ liệu

Vì folder path đã chứa `country_code` và `shop_id`, cần kiểm tra xem nội dung CSV có mâu thuẫn với path không.

Kết quả:

```text
path mismatches = 0
```

Đóng góp phân tích:

- Có thể tin tưởng metadata từ path.
- An toàn khi bổ sung `country_code` cho bảng thiếu cột này.

## 4. Xử lý chi tiết từng bảng

### 4.1. `products`

Raw schema có 44 cột. Sau preprocessing, `products_clean.csv` có 79 cột.

Raw rows:

```text
3,371
```

Processed rows:

```text
3,341
```

Vấn đề raw chính:

- Có 30 dòng duplicate exact.
- Cột số đang ở dạng text: giá, rating, sold, liked count.
- Cột boolean đang ở dạng text: `is_ad`, `is_sold_out`, `shopee_verified`.
- Cột JSON array nằm trong CSV: `images`, `vouchers`, `global_catids`, `tier_variation_options`.
- Có 3 dòng `price = 999999999`, nên xem là outlier/sentinel khi phân tích giá.
- `is_ad` và `is_sold_out` đều `False` cho toàn bộ 3,341 dòng processed, nên hai biến này không giúp phân nhóm trong dataset hiện tại.

Xử lý đã làm:

- Bỏ 30 duplicate exact.
- Thêm metadata:
  - `source_file`
  - `path_country_code`
  - `path_dataset`
  - `path_shop_id`
- Tạo numeric columns:
  - `ctime_num`
  - `discount_percent_num`
  - `price_num`
  - `voucher_min_spend_num`
  - `history_sold_value_num`
  - `voucher_discount_num`
  - `monthly_sold_value_num`
  - `price_original_num`
  - `voucher_start_time_num`
  - `liked_count_num`
  - `price_before_promo_num`
  - `catid_num`
  - `voucher_end_time_num`
  - `promotion_id_num`
  - `brand_id_num`
  - `rating_num`
  - `rating_count_num`
- Tạo boolean columns:
  - `is_ad_bool`
  - `is_sold_out_bool`
  - `shopee_verified_bool`
- Tạo array count columns:
  - `image_overlay_count`
  - `seller_flag_hash_count`
  - `vouchers_count`
  - `tier_variation_options_count`
  - `seller_flag_count`
  - `global_catids_count`
  - `images_count`
  - `rating_count_detail_count`
  - `image_overlay_hash_count`
- Tạo feature text/discount:
  - `product_name_clean`
  - `discount_amount_num = price_original - price`

Đóng góp vào mạch phân tích:

- Là bảng trung tâm để tính:

```text
estimated_recent_revenue = price_num * monthly_sold_value_num
```

- Trả lời câu hỏi:
  - Sản phẩm nào bán tốt?
  - Giá/discount/voucher có liên quan đến lượt bán không?
  - Rating, liked count, số ảnh, brand có liên quan đến performance không?
  - VN và ID khác nhau thế nào về giá/lượt bán/promo?

Lưu ý phân tích:

- `price` trong dataset nên hiểu là giá cuối hiển thị sau khi đã phản ánh voucher/promo.
- Không nên trừ `voucher_discount` thêm một lần nữa khỏi `price`.
- Nếu phân tích giá, nên xử lý riêng 3 outlier `price = 999999999`.

### 4.2. `shop_info`

Raw schema có 17 cột. Sau preprocessing, `shop_info_clean.csv` có 32 cột.

Rows:

```text
20 shops = 10 shop VN + 10 shop ID
```

Vấn đề raw chính:

- Các chỉ số shop như follower, rating, response rate đang ở dạng text.
- Boolean `is_official_shop`, `vacation` đang ở dạng text.
- Chỉ có một snapshot ngày `2026-07-03`.

Xử lý đã làm:

- Thêm metadata:
  - `source_file`
  - `path_country_code`
  - `path_dataset`
  - `path_shop_id`
- Tạo numeric columns:
  - `response_time_num`
  - `rating_good_num`
  - `cancellation_rate_num`
  - `response_rate_num`
  - `rating_star_num`
  - `item_count_num`
  - `rating_normal_num`
  - `follower_count_num`
  - `rating_bad_num`
- Tạo boolean columns:
  - `is_official_shop_bool`
  - `vacation_bool`

Đóng góp vào mạch phân tích:

- Bổ sung ngữ cảnh shop cho sản phẩm.
- Dùng để kiểm tra:
  - Official shop có performance tốt hơn không?
  - Shop nhiều follower có doanh thu ước tính cao hơn không?
  - Rating shop có liên quan đến performance sản phẩm không?
  - Response rate/time có liên quan đến bán hàng không?

Join chính:

```text
products.country_code = shop_info.country_code
products.shop_id      = shop_info.shop_id
```

Trong `product_dataset_ready.csv`, các cột từ `shop_info` được thêm với prefix `shop_`, ví dụ:

- `shop_rating_star`
- `shop_follower_count`
- `shop_item_count`
- `shop_is_official_shop`
- `shop_response_rate`
- `shop_response_time`

### 4.3. `category_list`

Raw schema có 11 cột. Sau preprocessing, `category_list_clean.csv` có 21 cột.

Rows:

```text
491
```

Vấn đề raw chính:

- Đây là danh mục/kệ nội bộ của shop, không phải category chuẩn Shopee.
- Numeric IDs và `total` đang ở dạng text.
- Boolean `is_parent_category`, `is_sub_category` đang ở dạng text.
- Một danh mục chỉ có ý nghĩa khi đi kèm `country_code + shop_id + date`.

Xử lý đã làm:

- Thêm metadata:
  - `source_file`
  - `path_country_code`
  - `path_dataset`
  - `path_shop_id`
- Tạo numeric columns:
  - `shop_category_id_num`
  - `category_type_num`
  - `parent_shop_category_id_num`
  - `total_num`
- Tạo boolean columns:
  - `is_sub_category_bool`
  - `is_parent_category_bool`

Đóng góp vào mạch phân tích:

- Cho biết shop có những kệ/danh mục nội bộ nào.
- Khi join với `product_categories` và `products`, có thể tính:
  - Kệ nào có nhiều sản phẩm.
  - Kệ nào có tổng lượt bán cao.
  - Kệ nào có doanh thu ước tính cao.
  - Các kệ như `Combo`, `Best Seller`, `Khuyến mãi` có hiệu quả không.

Join chính:

```text
product_categories.country_code = category_list.country_code
product_categories.shop_id      = category_list.shop_id
product_categories.category_id  = category_list.shop_category_id
product_categories.date         = category_list.date
```

Lưu ý:

- `category_list.shop_category_id` không cùng hệ với `category_platform.category_id`.
- Không join trực tiếp `category_list.shop_category_id` với `category_platform.category_id`.

### 4.4. `product_categories`

Raw schema có 5 cột. Sau preprocessing, `product_categories_clean.csv` có 13 cột.

Rows:

```text
4,054
```

Vấn đề raw chính:

- Raw không có cột `country_code`; country nằm trong đường dẫn.
- `category_id` trong bảng này là category/kệ nội bộ shop, không phải category platform.
- IDs đang ở dạng text.
- Một sản phẩm có thể nằm trong nhiều category nội bộ, nên có thể gây double count nếu tính doanh thu theo category.

Xử lý đã làm:

- Bổ sung `country_code` từ `path_country_code`.
- Thêm metadata:
  - `source_file`
  - `path_country_code`
  - `path_dataset`
  - `path_shop_id`
- Tạo numeric columns:
  - `item_id_num`
  - `category_slug_num`
  - `category_id_num`

Đóng góp vào mạch phân tích:

- Là bảng nối giữa `products` và `category_list`.
- Cho biết sản phẩm nào nằm trong kệ/danh mục nội bộ nào.
- Giúp phân tích doanh thu/lượt bán theo cách shop trưng bày sản phẩm.

Join chính:

```text
products.country_code = product_categories.country_code
products.shop_id      = product_categories.shop_id
products.item_id      = product_categories.item_id
products.date         = product_categories.date
```

Sau đó join tiếp:

```text
product_categories.category_id = category_list.shop_category_id
```

Lưu ý double count:

- Một sản phẩm có thể nằm trong nhiều category nội bộ.
- Khi phân tích theo category, sản phẩm đó có thể được tính ở nhiều category.
- Nếu muốn tổng doanh thu toàn shop/toàn thị trường, cần deduplicate theo `country_code + shop_id + item_id + date`.

### 4.5. `category_platform`

Raw schema có 9 cột. Sau preprocessing, `category_platform_clean.csv` có 18 cột.

Rows:

```text
4,482 = 2,241 category VN + 2,241 category ID
```

Vấn đề raw chính:

- Raw không có `country_code`; country nằm trong đường dẫn.
- Không có `shop_id` vì đây là taxonomy toàn nền tảng.
- IDs và boolean `has_children` đang ở dạng text.
- Đây là hệ category chuẩn Shopee, khác với category nội bộ shop.

Xử lý đã làm:

- Bổ sung `country_code` từ `path_country_code`.
- Thêm metadata:
  - `source_file`
  - `path_country_code`
  - `path_dataset`
  - `path_shop_id`
- Tạo numeric columns:
  - `parent_category_id_num`
  - `category_id_num`
  - `client_num`
- Tạo boolean column:
  - `has_children_bool`

Đóng góp vào mạch phân tích:

- Chuẩn hóa ngành hàng để so sánh giữa shop và giữa quốc gia.
- Giúp phân tích doanh thu theo ngành hàng chuẩn Shopee.
- Dùng để đọc tên category từ `products.catid` hoặc `products.global_catids`.

Join chính:

```text
products.country_code = category_platform.path_country_code
products.catid        = category_platform.category_id
```

Hoặc parse từng ID trong:

```text
products.global_catids
```

rồi map sang:

```text
category_platform.category_id
```

Lưu ý:

- `category_platform.category_id` không cùng hệ với `product_categories.category_id`.
- Không join `product_categories.category_id = category_platform.category_id`.

## 5. Bảng phân tích chính: `product_dataset_ready.csv`

File:

```text
Dataset/DataProcessed/product_dataset_ready.csv
```

Rows:

```text
3,341
```

Columns:

```text
94
```

Bảng này lấy `products_clean.csv` làm trung tâm và merge thêm:

- Thông tin shop từ `shop_info_clean.csv`.
- Danh mục nội bộ từ `product_categories_clean.csv`.
- Tên danh mục nội bộ từ `category_list_clean.csv`.

Các cột bổ sung từ shop:

- `shop_rating_star`
- `shop_follower_count`
- `shop_item_count`
- `shop_is_official_shop`
- `shop_response_rate`
- `shop_response_time`
- `shop_rating_good`
- `shop_rating_normal`
- `shop_rating_bad`
- `shop_cancellation_rate`
- `shop_created_at`
- `shop_vacation`

Các cột bổ sung từ category nội bộ:

- `shop_category_ids`
- `shop_category_names`
- `shop_category_count`

Đóng góp vào mạch phân tích:

- Đây là bảng tiện nhất để EDA/modeling.
- Có đủ thông tin sản phẩm + shop + kệ nội bộ.
- Có thể dùng trực tiếp để tạo các feature:

```text
estimated_recent_revenue = price_num * monthly_sold_value_num
has_voucher = voucher_discount_num > 0
has_promo = discount_percent_num > 0
```

Lưu ý:

- Bảng này chưa merge `category_platform` trực tiếp.
- Nếu cần phân tích ngành hàng chuẩn Shopee, join thêm `category_platform_clean.csv` qua `catid` hoặc `global_catids`.

## 6. File `data_quality_report.json`

File:

```text
Dataset/DataProcessed/data_quality_report.json
```

Report này lưu:

- Số file raw đã đọc.
- Schema từng dataset.
- Số dòng raw và số dòng sau xử lý.
- Số duplicate exact bị loại.
- Missing count các cột core.
- Date range.
- Danh sách output.
- Kiểm tra mismatch giữa đường dẫn và dữ liệu.

Kết quả hiện tại:

```text
file_count = 82
countries = vn, id
shops = 20
products raw = 3,371
products processed = 3,341
exact duplicate products removed = 30
path mismatches = 0
```

## 7. Tóm tắt mạch phân tích sau preprocessing

Sau preprocessing, mạch phân tích nên đi như sau:

1. Dùng `product_dataset_ready.csv` để phân tích nhanh sản phẩm, shop, voucher/promo, category nội bộ.
2. Tạo doanh thu ước tính:

```text
estimated_recent_revenue = price_num * monthly_sold_value_num
```

3. So sánh theo quốc gia:

```text
country_code = vn vs id
```

4. So sánh theo shop:

```text
shop_name, shop_is_official_shop, shop_follower_count, shop_rating_star
```

5. So sánh theo category nội bộ:

```text
shop_category_names
```

6. Nếu cần phân tích ngành hàng chuẩn Shopee, join thêm `category_platform_clean.csv`.

## 8. Lưu ý khi chỉnh preprocessing

- Nếu đổi cấu trúc `Dataset/DataRaw`, cần kiểm tra lại logic parse metadata từ path.
- Nếu thêm bảng mới, cần cập nhật danh sách dataset trong notebook.
- Nếu thêm cột số/boolean/array mới, cần cập nhật danh sách cột tương ứng.
- Nếu muốn phân tích ảnh sản phẩm, có thể mở rộng preprocessing để tạo thêm `local_image_path` sau khi download/cache ảnh.
- Nếu chạy notebook nhiều lần, các file trong `Dataset/DataProcessed` sẽ được ghi đè bằng output mới.
