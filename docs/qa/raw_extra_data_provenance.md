# Xuất xứ `raw_extra_data/` và các quyết định của bước nối

Ngày lập: **30/08/2026**. Nguồn: `raw_extra_data/datashopee/` — dump Postgres, 7
bảng, đặt tên `<bảng>_<YYYYMMDDHHMM>.csv`, mốc `202608271925`.

Code thi hành: `src/gladiators/data/extract_adapter.py`.
Test giữ các quyết định dưới đây: `tests/test_extract_adapter.py`.

---

## 1. Vì sao adapter, không phải một pipeline thứ hai

`pipeline.py` mang toàn bộ luật làm sạch, kiểm quan hệ, cờ chất lượng và cách
dựng metric. Viết một đường thứ hai cho bộ mới là tạo hai định nghĩa cho cùng
một khái niệm, và chúng sẽ trôi khỏi nhau đúng lúc không ai nhìn. Adapter chỉ
đổi **hình dạng**; mọi phép làm sạch vẫn đi qua một đường duy nhất.

## 2. Bốn sự thật đo được, và cách nối rút ra từ chúng

| # | Sự thật (đo trên chính dump) | Hệ quả cho bước nối |
| --- | --- | --- |
| 1 | `product_promotions` 22 695 dòng = item × ngày, 20 ngày (01→21/07). Ba ngày chồng lấn cho **đúng** số listing của bộ đóng băng (581/670/668 vn · 474 id) và **668/668 giá khớp tới từng đồng** | Nó là panel nguồn ⇒ làm **xương sống** |
| 2 | `products` và `products_timeseries` mỗi bảng 1 276 dòng / 1 276 item — **một dòng mỗi item**; `date` của chúng = ngày **cuối** của item đó trong panel (1276/1276) | Không phải panel. Tên `products_timeseries` mô tả sai chính nó; nối theo tên file là nối sai |
| 3 | Vì (2), `rating`/`rating_count`/`liked_count`/`monthly_sold`/`history_sold`/`discount_percent` chỉ có **một** quan sát mỗi item. Trong bộ đóng băng những cột này **đổi** theo ngày (202–411 trên 671 listing) | Chỉ ghi tại **đúng ngày quan sát**, các ngày khác **để trống**, kèm cờ `attributes_observed`. Gắn một quan sát cho cả 20 ngày sẽ dựng ra chuỗi thời gian **phẳng không có thật** |
| 4 | `shopee_verified` **đổi grain**: bộ cũ ở cấp LISTING (576 vn / 9 id), dump chỉ có `shop_info.is_shopee_verified` ở cấp SHOP (3/20) | Hai đại lượng khác nhau mang một tên. Cột listing-level **để trống**; cờ shop-level đi vào `shop_info` như cột riêng |

## 3. Ánh xạ cột — chỗ đã cắn, và vì sao

| Cột dump | Cột canonical | Ghi chú |
| --- | --- | --- |
| `global_category_id` | `global_catids` | **Đã là chuỗi mảng** đường dẫn ngành hàng, giống hệt bộ cũ (1 155/1 157). Bọc thêm một lớp ngoặc sẽ dựng ra mảng lồng. Hai item lệch (`vn:25586402460`, `vn:26912249516`) mang đường dẫn **khác hẳn** — sàn đổi ngành hàng của chúng sau lần thu cũ; đó là dữ liệu mới, không phải lỗi ánh xạ |
| `shopee_category_id` | `catid` | 1 157/1 157 item chồng lấn khớp |
| `product_categories.category_slug` | `category_slug_text` (**cột mới**) | Bộ cũ dùng tên `category_slug` cho giá trị **bằng `category_id`** (4 054/4 054) và pipeline khai nó là cột **số**. Dump dùng cùng tên cho một slug **chữ**. Giữ nghĩa cũ cho tên cũ; slug chữ ra cột mới |
| `ctime`, `voucher_start_time`, `voucher_end_time` | cùng tên, **đổi sang giây epoch** | Dump ghi `2025-11-11 02:24:55.000 +0700`; bộ cũ dùng epoch và pipeline khai chúng NUMERIC |
| `shop_info.shop_created_at` | `created_at`, **ISO UTC** | Cùng thời điểm, khác múi giờ hiển thị |
| `created_at`, `updated_at` (mọi bảng) | **loại** | Một giá trị duy nhất cho cả bảng = dấu thời gian **nạp batch**, không phải sự kiện kinh doanh |
| `products_timeseries.unit_sold` | **loại** | `0` ở toàn bộ 1 276 dòng — hằng số không phải một phép đo |

**Bốn cột canonical dump không cấp được**, và lý do (ghi ra thay vì để trống im
lặng — cột trống không có lời giải thích là cột không ai biết nên chờ dữ liệu hay
chờ code): `shopee_verified` (đổi grain, §2.4), `seller_flag_hash` và
`image_overlay_hash` (ID ảnh CDN của Shopee, không suy được từ giá trị gốc),
`key` (cột endpoint nội bộ của lần thu cũ).

## 4. Hai phép mượn, và chúng được khai là mượn

- **`brand`** — dump chỉ có `brand_id`. Bản đồ `(country, brand_id) → tên` lấy từ
  bộ đóng băng: **43 cặp, kiểm 1-1 tại chỗ** (một `brand_id` trỏ hai tên nghĩa là
  giả định nền sai, và khi đó không được mượn). Phủ 1 225/1 276 item; 41 item có
  `brand_id` rỗng/0 và 10 item mang `brand_id` chưa từng thấy ⇒ **để trống**.
- **`category_platform`** — taxonomy **cấp sàn** (4 482 dòng), không phụ thuộc
  shop hay ngày; dump không có bảng tương ứng. Chép nguyên kèm cờ xuất xứ.

## 5. Grain shop: **tách**, không đổi

Bộ cũ để mọi chỉ số shop trong `shop_info` với grain `(country, shop)` và **một
ngày** (03/07); 9 measure `measure.shop_*` trỏ thẳng vào đó với ngữ nghĩa
`static_latest`. Dump cho **panel 20 ngày**.

Để panel chảy vào `shop_info` thì mọi join theo shop nở gấp 20 lần và 9 measure
đó **âm thầm đổi nghĩa**. Nên:

- `shop_info` giữ **nguyên hình dạng cũ**: ảnh chụp tĩnh tại ngày cuối panel.
- Panel ngày ra **dataset mới** `shop_stats` (`shop_stats_clean.csv`), khai là
  **artifact tuỳ chọn** (`domain/tables.py::OPTIONAL_ARTIFACTS`) vì bản đóng băng
  không có nó. 11 measure `measure.shop_daily_*` + relation `shop_observed_at` +
  topic `T9 SHOP_DAILY_PANEL`.

Bản dữ liệu chưa thu panel ⇒ artifact vắng ⇒ compiler chặn tại
`available_sources` và câu hỏi bị từ chối vì **thiếu dữ liệu**, không phải vì
không hiểu câu hỏi.

## 6. Cờ chất lượng còn lại, và nguyên nhân từng cái

Sau khi dựng: **0 lỗi**, 46 834 cảnh báo.

| Mã | Số | Nguyên nhân |
| --- | ---: | --- |
| `ORPHAN_CATEGORY_MAPPING_SHELF` | 27 032 | `categories` của dump **không mang ngày**; kệ hàng bộ cũ đo được là **đổi theo ngày** (3 biến thể/3 ngày), nên nhân bản một ảnh chụp ra 20 ngày là bịa. Ảnh chụp gắn vào một ngày ⇒ 19/20 ngày không có định nghĩa kệ. Cờ này là **lời khai đúng**, không phải lỗi |
| `MISSING_DISCOUNT_INCONSISTENT_PRICE` | 18 496 | Hệ quả trực tiếp của §2.3: `discount_percent` là **số Shopee hiển thị** (khớp `round((1-price/price_original)·100)` 2 995/3 034 nhưng lệch ở 39 ca ⇒ **không suy được**), chỉ quan sát một ngày mỗi item |
| `INTERNAL_SNAPSHOT_GAP` | 1 188 | Panel thiếu **12/07/2026** — khoảng trống thu thập có thật |
| `EDGE_SNAPSHOT_MISSING` | 88 | Cùng loại với bộ cũ (113) |
| `PRICE_SENTINEL` | 23 | Cùng loại với bộ cũ (3) |
| `ORPHAN_CATEGORY_MAPPING_PRODUCT` | 7 | Cùng loại với bộ cũ (5) |

## 7. Việc còn lại — chưa làm, và vì sao

1. **`promotion_type` và `attributes_observed` chưa có catalog ref.** Chúng là
   cột **mới trong một artifact bắt buộc**; khai ref cho chúng sẽ làm binding của
   **bộ đóng băng** gãy (bộ cũ không có hai cột đó). Cần một cơ chế tuỳ chọn ở
   **cấp cột**, không phải cấp artifact — làm nửa vời sẽ tệ hơn không làm.
2. **`expected_cardinality="<=3341"` / `"<=1157"` ghim cứng kích thước bộ cũ.**
   Trên bộ 22 695 dòng, một plan khai cận đó mà trả nhiều hơn sẽ **vi phạm
   postcondition** ⇒ fail-closed đúng, nhưng nguyên nhân bị nói sai. Cận nên
   tương đối theo bản dữ liệu.
3. **Câu "bao nhiêu listing giảm giá trên 50%" trả `0` trên bản mới.** Trên ngày
   được chọn (03/07) `discount_percent` **không quan sát được** cho hầu hết item
   (§6), nhưng đường đếm hiện tại đếm `discount_percent_analysis > 50` và ra `0`
   — tức **"đo được và bằng 0"** thay cho **"không đo được"**, đúng cạm bẫy
   CLAUDE.md §3.1. Đây là lớp lỗi "đếm thừa hưởng bộ lọc của đo", cần sửa ở
   `analytics/tools.py` cùng với các ca khác cùng loại, không sửa lẻ ở đây.
4. **`27de9bff184f4f89` không tái lập được bit-exact trên máy này** — dựng lại
   `data/raw` cho `7933e9868a37151d`, chênh ở **chữ số cuối của float** trên 111
   dòng (`4.919280403384327` vs `4.9192804033843265`). Đo được là **có sẵn từ
   trước**: `git stash` phần sửa của phiên này rồi dựng lại tại HEAD cho **đúng
   cùng** `7933e9868a37151d`. Không phải hệ quả của bước nối.
