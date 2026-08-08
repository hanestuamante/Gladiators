# Data Context and Analysis Notes

> **Status:** Tài liệu tham chiếu chuyên sâu về dữ liệu. Với kiến trúc/runtime
> hiện tại, đọc `../CURRENT_ARCHITECTURE_SPEC.md` trước.
> Nếu dùng `business-dictionary.md` làm system prompt cho Agent, **bắt buộc đọc [mục 9](#9-business-dictionary-chuẩn-hóa-đối-chiếu-business-dictionarymd) trước** — file đó có 4 lỗi/thiếu caveat đã kiểm chứng và sửa ở mục 9.
> Lần cuối cập nhật: 14/7/2026 — đồng bộ theo cấu trúc repo hiện hành và pipeline tái lập trong `notebooks/pipeline`.

> **Quy ước code:** pipeline và kiểm thử chỉ duy trì dưới dạng `.ipynb` trong `notebooks/`; không tạo bản `.py` song song để tránh hai nguồn logic lệch nhau.

## 1. Status và source hierarchy

Tài liệu này là điểm vào hiện hành để hiểu dữ liệu và giới hạn phân tích của repo. Nó tổng hợp context cần dùng, không thay thế raw/processed artifacts hay notebook tái lập kết quả.

Thứ tự ưu tiên khi nguồn mâu thuẫn:

1. CSV hiện tại và logic preprocessing: schema, số dòng và artifact thực tế.
2. `data/processed/pipeline_report.json` và `data_quality_issues.csv`: kết quả kiểm định có thể tái lập.
3. Tài liệu này: grain, semantics, anomaly và guardrail đã tổng hợp.
4. [Pipeline documentation](data-pipeline.md): contract xử lý và metric hiện hành.
5. [V0 Architecture](../archive/architecture/V0_Architecture.md): lịch sử thiết kế đã superseded, không phải source of truth.

Các số liệu ghi là “kiểm tra trực tiếp” bên dưới được đối soát read-only trên:

- `data/processed/products_clean.csv` cho grain, coverage và field snapshot;
- `data/raw/**/products.csv` và `data/processed/products_clean.csv` cho ba population voucher, phân phối giá trị voucher, duration hiệu lực và transition voucher qua snapshot;
- `data/processed/products_clean.csv` cho cardinality `promotion_id` và thống kê `tier_variation`;
- các bảng `*_clean.csv` cho khóa, số cột raw/processed và referential coverage;
- `category_platform_clean.csv` cùng `global_catids` đã parse cho category path.

Toàn bộ số trong tài liệu này — kể cả các số trùng với `data_grain_quality_audit.md` — đã được recompute độc lập bằng pandas trực tiếp trên artifact tại thời điểm cập nhật gần nhất, không chỉ chép lại audit. Một điểm cần lưu ý khi tái lập: `voucher_discount_num`/`voucher_min_spend_num` là `NaN` (không phải `0`) ở các dòng không có structured voucher; so sánh “giá trị đổi giữa hai snapshot” phải loại trừ NaN-vs-NaN trước khi đếm, nếu không sẽ đếm nhầm 1.125 transition “không voucher cả hai lần” thành “đổi”.

Không suy diễn để hòa giải hai số khác scope. Mọi con số phân tích cần nêu rõ raw hay processed, filter, grain và snapshot/date.

## 2. Dataset scope và grain

Dataset là dữ liệu Shopee của hai thị trường:

- `vn`: Việt Nam;
- `id`: Indonesia.

Có 82 CSV raw, 20 shop, mỗi quốc gia 10 shop. Raw data được phân vùng:

```text
data/raw/
  country_code=<vn|id>/
    dataset=<dataset_name>/
      shop_id=<shop_id>/
        <dataset_name>.csv
```

`category_platform` không có tầng `shop_id` vì là taxonomy cấp nền tảng.

### Phạm vi bảng

| Bảng                  | Raw rows | Processed rows | Vai trò                                                     |
| ---------------------- | -------: | -------------: | ------------------------------------------------------------ |
| `products`           |    3.371 |          3.341 | Listing snapshot, giá, rating, sold proxy, voucher/discount |
| `shop_info`          |       20 |             20 | Context shop; chỉ có snapshot`2026-07-03`                |
| `category_list`      |      491 |            491 | Danh mục/kệ nội bộ của shop                             |
| `product_categories` |    4.054 |          4.054 | Mapping listing vào kệ nội bộ                            |
| `category_platform`  |    4.482 |          4.482 | Taxonomy Shopee theo quốc gia                               |

`products` processed gồm 1.919 snapshot VN và 1.422 snapshot ID. Ba ngày quan sát là `2026-07-01`, `2026-07-02`, `2026-07-03`; số dòng tương ứng là 1.055, 1.144 và 1.142.

### Cấu trúc cột từng bảng (raw → processed)

Kiểm tra trực tiếp số cột từng file:

| Bảng | Cột raw | Cột processed | Cột thêm chính |
| --- | ---: | ---: | --- |
| `products` → `products_clean` | 44 | 80 | metadata path/source row; cột `_num` (giá, rating, sold, voucher, thời gian…); cột `_bool`; cột `_count` cho JSON array; clean name và listing/snapshot keys |
| `shop_info` → `shop_info_clean` | 17 | 33 | metadata path/source row; cột `_num` (follower, rating, response…); cột `_bool` (`is_official_shop`, `vacation`) |
| `category_list` → `category_list_clean` | 11 | 22 | metadata path/source row; cột `_num` (ID, `total`); cột `_bool` (`is_parent_category`, `is_sub_category`) |
| `product_categories` → `product_categories_clean` | 5 | 14 | `country_code` bổ sung từ path; metadata path/source row; cột `_num` cho ID |
| `category_platform` → `category_platform_clean` | 9 | 20 | `country_code` bổ sung từ path; metadata path/source row; cột `_num` cho ID; `has_children_bool` |

Chi tiết từng cột và lý do xử lý (tại sao tách `_num`/`_bool`/`_count`, cách JSON array được parse) nằm ở [data-pipeline.md](data-pipeline.md); tài liệu này chỉ giữ số lượng cột đã đối soát để biết “dataset có gì” ở mức tổng quan.

Ba dòng `price_num = 999999999` (raw sentinel/outlier, xem mục 5) và toàn bộ 3.341 dòng `is_ad_bool = False`, `is_sold_out_bool = False` nằm trong `products_clean`; hai cờ này không có variation nên không dùng để phân nhóm.

### Phân bổ theo shop

Kiểm tra trực tiếp trên `products_clean.csv`:

| Country | Shop ID | Shop | Rows | Listings |
| --- | --- | --- | ---: | ---: |
| `id` | `1112776376` | Scora Official Store | 144 | 48 |
| `id` | `1368540320` | Cyeecare Official Store | 198 | 66 |
| `id` | `1379527329` | ZOICY Official Store | 55 | 19 |
| `id` | `187405886` | Alara Cosmetic Official Store | 21 | 7 |
| `id` | `200048291` | Prettywell Official Shop | 68 | 23 |
| `id` | `430940247` | Mooi Pure Glow Official Shop | 120 | 40 |
| `id` | `697604885` | ghaniskin | 9 | 3 |
| `id` | `779266191` | lavojoy Official Shop | 117 | 39 |
| `id` | `809769142` | Glad2Glow Official Store | 660 | 220 |
| `id` | `859233628` | He-Ji Official Store | 30 | 10 |
| `vn` | `108166524` | Nestlé Chính hãng | 226 | 82 |
| `vn` | `1145316676` | Nestlé Health Science | 259 | 87 |
| `vn` | `140360136` | Kinh Do Official Store | 103 | 35 |
| `vn` | `1546895026` | Mars Snacking VN | 140 | 71 |
| `vn` | `173513432` | Richy - Chi Nhánh Miền Bắc | 213 | 71 |
| `vn` | `213989179` | Bibica Official Store | 287 | 96 |
| `vn` | `289646907` | Orion VN Official Store | 226 | 84 |
| `vn` | `430972539` | Perfetti Van Melle Vietnam | 66 | 22 |
| `vn` | `438905996` | Richy - Chi nhánh Miền Nam | 363 | 122 |
| `vn` | `464391416` | Bánh Kẹo Hải Hà - Chính hãng | 36 | 12 |

Tổng 3.341 rows, 1.157 listings, khớp với bảng phạm vi ở trên.

### Đơn vị quan sát và khóa

3.341 dòng là **3.341 product-listing snapshots**, không phải 3.341 product và không phải 3.341 SKU.

```text
product_listing_key = country_code + ':' + shop_id + ':' + item_id
product_snapshot_key = product_listing_key + ':' + date
```

- Có 1.157 product listing theo `country_code + shop_id + item_id`: 682 VN và 475 ID.
- Grain snapshot là `country_code + shop_id + item_id + date`; khóa này không trùng trong processed data.
- Trong mẫu hiện tại, `item_id` tình cờ không lặp giữa shop/quốc gia. Vẫn phải giữ `country_code + shop_id` trong khóa nghiệp vụ.
- `product_name`, URL và variation text không thay thế được khóa listing.

`item_id` là listing ID, không phải SKU. Dataset không có `sku_id`, `model_id`, giá, tồn kho hay sales theo variation. `tier_variation_name` và `tier_variation_options` chỉ mô tả lựa chọn hiển thị ở cấp listing; không được ghép chúng thành SKU proxy để theo dõi.

Kiểm tra trực tiếp trên snapshot mới nhất của 1.157 listing:

- 727/1.157 listing có `tier_variation_name` khác rỗng.
- 582/1.157 listing có từ 2 option trở lên trong `tier_variation_options` (đã parse JSON).
- Listing nhiều option nhất có 38 option.
- Không có `sku_id`/`model_id`, giá, tồn kho hay sales riêng theo từng option đó, nên dù đếm được số option cũng **không thể suy ra SKU thật hay theo dõi SKU qua nhiều ngày**.

### Coverage ba ngày

| Số ngày có snapshot | Listings | Tỷ lệ |
| ---------------------: | -------: | ------: |
|                3 ngày |    1.039 |  89,80% |
|                2 ngày |      106 |   9,16% |
|                1 ngày |       12 |   1,04% |

Panel cân bằng cần `1.157 × 3 = 3.471` ô; dữ liệu hiện có 3.341 ô, thiếu 130 snapshot. Vì vậy không được ngầm coi đây là balanced panel.

Chi tiết pattern thiếu snapshot, kiểm tra trực tiếp trên `products_clean.csv`:

| Country | Các ngày có mặt | Ngày bị thiếu | Số listing | Snapshot thiếu |
| --- | --- | --- | ---: | ---: |
| `vn` | `02/07, 03/07` | `01/07` | 95 | 95 |
| `vn` | `01/07, 02/07` | `03/07` | 5 | 5 |
| `vn` | `01/07, 03/07` | `02/07` | 5 | 5 |
| `vn` | chỉ `01/07` | `02/07, 03/07` | 5 | 10 |
| `vn` | chỉ `02/07` | `01/07, 03/07` | 4 | 8 |
| `vn` | chỉ `03/07` | `01/07, 02/07` | 2 | 4 |
| `id` | chỉ `03/07` | `01/07, 02/07` | 1 | 2 |
| `id` | `01/07, 02/07` | `03/07` | 1 | 1 |

Tổng case không đầy đủ: 116 listing VN (127 snapshot thiếu) + 2 listing ID (3 snapshot thiếu) = 118 listing, 130 snapshot thiếu — khớp đúng con số 130 ở trên. 5 listing VN thuộc dòng `01/07, 03/07` (thiếu `02/07`) là internal gap rõ nhất; các case này nên có `snapshot_gap_flag = True`. Nhóm 95 listing VN chỉ có `02/07` và `03/07` nhiều khả năng là listing/shop mới xuất hiện giữa kỳ quan sát, không đủ bằng chứng gọi là mất dữ liệu.

`shop_info` chỉ có ngày `2026-07-03`. Khi enrich product snapshots của ngày trước, các field shop phải được gọi là **latest/static shop enrichment**, không phải thuộc tính shop đồng thời tại từng ngày.

## 3. Bảng, khóa và quan hệ

### Grain và khóa logic

| Bảng                        | Grain / khóa logic hiện tại                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------------- |
| `products_clean`           | `country_code + shop_id + item_id + date`                                                             |
| `shop_info_clean`          | `country_code + shop_id` trong export hiện tại; chỉ một ngày 03/07                               |
| `category_list_clean`      | `country_code + shop_id + shop_category_id + date`                                                    |
| `product_categories_clean` | `country_code + shop_id + item_id + category_id + date`                                               |
| `category_platform_clean`  | `path_country_code + category_id`                                                                     |

Kiểm tra trực tiếp cho thấy mỗi khóa trên có 0 duplicate-key group trong bảng tương ứng.

### Join được phép

Không rút gọn các join dưới đây khi viết code:

```text
products.country_code = shop_info.country_code
products.shop_id      = shop_info.shop_id
```

Join này chỉ là latest/static enrichment trong dữ liệu hiện tại. Nếu sau này `shop_info` có nhiều snapshot, phải dùng join theo ngày hoặc as-of join phù hợp.

```text
products.country_code = product_categories.country_code
products.shop_id      = product_categories.shop_id
products.item_id      = product_categories.item_id
products.date         = product_categories.date
```

```text
product_categories.country_code = category_list.country_code
product_categories.shop_id      = category_list.shop_id
product_categories.category_id  = category_list.shop_category_id
product_categories.date         = category_list.date
```

Platform category phải join theo cả quốc gia:

```text
products.country_code = category_platform.path_country_code
products.catid        = category_platform.category_id
```

Muốn đọc toàn bộ path, parse từng ID trong `products.global_catids`, rồi join từng ID với `category_platform.category_id` trong cùng `path_country_code`.

### Hai hệ category khác nhau

| Hệ             | Field                                                                  | Ý nghĩa                                     |
| --------------- | ---------------------------------------------------------------------- | --------------------------------------------- |
| Shopee platform | `category_platform.category_id`; `products.catid/global_catids`    | Taxonomy dùng chung trong một thị trường |
| Shop nội bộ   | `category_list.shop_category_id`; `product_categories.category_id` | Kệ/danh mục do từng shop tổ chức         |

Không join `product_categories.category_id` hoặc `category_list.shop_category_id` với `category_platform.category_id` chỉ vì cùng có tên `category_id`.

### Vai trò thực tế của `catid` và `global_catids`

Kiểm tra trực tiếp trên 3.341 snapshots:

- `global_catids` không rỗng và parse được ở 3.341/3.341 dòng.
- `catid` bằng phần tử đầu của `global_catids` ở 3.341/3.341 dòng.
- Category ứng với `catid` có `parent_category_id = 0` ở 3.341/3.341 dòng. Vì vậy, trong export hiện tại, `catid` là **top-level category**, không phải category cụ thể nhất.
- Phần tử cuối của `global_catids` có `has_children = False` ở 3.341/3.341 dòng; dùng phần tử cuối khi cần leaf category trong dataset hiện tại.
- Độ dài path: 395 snapshot có 2 cấp, 2.623 có 3 cấp và 323 có 4 cấp.

### Referential coverage đã kiểm tra

| Quan hệ / kiểm tra                                                          | Kết quả trên artifact hiện tại | Hệ quả                                                         |
| ----------------------------------------------------------------------------- | ----------------------------------: | ---------------------------------------------------------------- |
| `products.catid` → platform category, có country                          |          0 orphan / 3.341 snapshots | Join top-level có coverage đầy đủ trong snapshot hiện tại |
| Mọi ID đã parse trong`global_catids` → platform category, có country   |      0 orphan / 9.951 ID references | Path hiện tại map được đầy đủ                           |
| `products` → `shop_info` bằng country + shop                            |          0 orphan / 3.341 snapshots | Coverage đầy đủ, nhưng enrichment là static/latest         |
| `product_categories` → `category_list` bằng full shop-category-date key |               0 orphan / 4.054 rows | Shop-category mappings đều có category record                 |
| `product_categories` → `products` bằng full listing-snapshot key        |               5 orphan / 4.054 rows | Không được tuyên bố referential integrity tuyệt đối     |
| Product snapshots không có dòng`product_categories`                      |             1.132 / 3.341 snapshots | Dùng left join nếu cần giữ toàn bộ product population      |

Năm mapping orphan đều ở VN, shop `289646907`, ngày `2026-07-01`, thuộc ba `item_id` khác nhau. Không tự đoán nguyên nhân; cần giữ chúng như data-quality exceptions.

Một listing có thể thuộc nhiều shop category. Phân tích theo từng kệ có thể cố ý ghi nhận listing ở nhiều kệ, nhưng không được cộng các kệ để suy ra tổng shop/thị trường. Tổng hợp toàn cục phải trở lại grain `country_code + shop_id + item_id + date`.

## 4. Field/metric semantics

### Giá, sales proxy và revenue proxy

| Field / metric         | Cách hiểu an toàn                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `price`              | Final displayed/exported price tại snapshot; không khẳng định là checkout price thực tế                                 |
| `price_original`     | Giá gốc/giá tham chiếu được export                                                                                       |
| `price_before_promo` | Field nguồn có semantics chưa xác nhận; trong dữ liệu quan sát, thường hành xử như giá trước bước giảm cuối |
| `history_sold_value` | Cumulative-sales proxy được kỳ vọng lũy kế; không phải transaction ledger                                              |
| `monthly_sold_value` | Recent-window sales proxy; cửa sổ chính xác chưa được nguồn mô tả và không phải biến lũy kế                    |

`monthly_sold_value` không được cộng qua ba snapshots và `diff(monthly_sold_value)` không phải daily sales. Việc metric này giảm không phải cumulative anomaly.

```text
revenue_proxy_at_snapshot = price * monthly_sold_value

# implementation trên numeric columns của processed artifact
estimated_recent_revenue = price_num * monthly_sold_value_num
```

Đây chỉ là revenue proxy tại **một snapshot**: giá hiện tại nhân với sold proxy theo cửa sổ chưa xác định. Nó không phải GMV, net revenue hay profit. Khi tổng hợp listing, phải chọn một date/snapshot phù hợp, thường là snapshot mới nhất hoặc một ngày được chỉ định; không cộng cả ba ngày.

### Discount và promotion

Có 3.034/3.341 processed rows có `discount_percent`; 307 dòng để trống và cả 307 có `price == price_original`. Chỉ fill 0 trong trường hợp này; nếu sau này missing nhưng giá khác giá gốc, giữ null và gắn cờ.

```text
discount_percent ~= 100 * (price_original - price) / price_original
```

`discount_percent` là tổng mức giảm thể hiện từ `price_original` đến `price`, không phải promo percent độc lập với voucher.

Dataset không có `promo_percent` gốc. Nếu cần proxy kiểm định:

```text
promo_percent_derived =
    100 * (price_original - price_before_promo) / price_original
```

Phải giữ suffix `_derived`; field này chỉ là pre-final-reduction proxy theo hành vi quan sát, không phải campaign uplift chính thức.

`promotion_id` được hiểu an toàn nhất là ID promotion/offer gắn với listing tại snapshot. Có 874/3.341 dòng mang `promotion_id = 0`; đây là sentinel “không có/không xác định”. `promotion_id != 0` cũng không chứng minh một promotion đang tạo discount. Không dùng `promotion_id` thay cho `item_id`, và không suy ra mỗi ID là một campaign marketing cấp cao.

Bằng chứng cardinality, kiểm tra trực tiếp trên `products_clean.csv`:

| Kiểm tra | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| Số `promotion_id` khác `0` phân biệt | 106 | Nhiều promotion/offer khác nhau cùng tồn tại |
| Dòng có `promotion_id = 0` | 874/3.341 | `0` là sentinel, không phải campaign |
| ID `476043307925741` | 155 `item_id`, 300 snapshot | Một ID áp dụng cho nhiều sản phẩm khác nhau |
| ID `476165261832290` | 92 `item_id`, 210 snapshot | Tiếp tục bác bỏ giả thuyết “mỗi sản phẩm một promotion_id” |
| Listing chỉ giữ 1 giá trị `promotion_id` (tính cả sentinel `0`) qua các ngày | 589/1.157 | Một phần listing giữ nguyên promotion context |
| Listing có 2 hoặc 3 giá trị `promotion_id` khác nhau qua các ngày | 480 + 88 = 568/1.157 | Promotion gắn với listing có thể đổi theo snapshot |
| Giá trị `promotion_id` (kể cả `0`) xuất hiện ở nhiều shop | 15 giá trị (14 giá trị khác `0`, cộng sentinel `0` xuất hiện ở 17/20 shop) | Không thể giả định một `promotion_id` chỉ thuộc riêng một shop |

Quan hệ là nhiều-nhiều theo thời gian: một listing có nhiều snapshot, mỗi snapshot gắn 0 hoặc 1 `promotion_id` được export, và một `promotion_id` có thể áp dụng cho nhiều listing khác nhau. Muốn ánh xạ chính xác sang chiến dịch marketing cần thêm bảng promotion master (tên/loại, thời gian, phạm vi, cơ chế giảm, ngân sách) mà dataset hiện tại không có.

### Voucher và quan hệ giá

Định nghĩa chuẩn:

```text
has_structured_voucher = voucher_discount > 0
has_voucher_label      = vouchers_count > 0
```

Trên processed artifact, triển khai điều kiện đầu bằng cột numeric tương ứng: `voucher_discount_num > 0`.

Hai field này đo hai population khác nhau. `vouchers` là danh sách label/UI hỗn hợp, có thể chứa `Pilih Lokal`, `Add-on Deal`, `Mua để nhận quà`, `Hàng mới về`; nó không đồng nghĩa structured monetary voucher.

Ba population phải được tách rõ:

| Population                                  | Số dòng | Khớp`price_before_promo - voucher_discount = price` | Không khớp |
| ------------------------------------------- | --------: | -----------------------------------------------------: | -----------: |
| Raw có voucher trước dedup               |     1.610 |                     Không dùng làm processed metric |           — |
| Processed structured voucher                |     1.580 |                                                  1.011 |          569 |
| Structured voucher và`promotion_id != 0` |     1.016 |                                                    641 |          375 |

Filter kiểm tra lần lượt là raw `voucher_discount > 0`, processed `voucher_discount_num > 0`, rồi thêm `promotion_id_num != 0`. Cả 30 redundant exact-duplicate rows bị loại khỏi raw đều là structured-voucher rows, giải thích `1.610 → 1.580`. Toàn bộ 1.580 processed structured-voucher snapshots thuộc VN. Nhóm 1.016 chỉ là subgroup theo `promotion_id != 0`; không diễn giải nó thành hai cơ chế khuyến mãi độc lập.

Trong 1.580 processed structured-voucher snapshots:

- 1.580/1.580 có đủ code, discount, minimum spend, start và end time;
- 1.580/1.580 thỏa `price_before_promo >= voucher_min_spend`;
- có 335 dòng `price < voucher_min_spend`, và cả 335 thỏa `price + voucher_discount >= voucher_min_spend`;
- công thức giá khớp 1.011 dòng và không khớp 569 dòng.

Quan hệ 335 dòng chỉ kiểm tra điều kiện số tiền từ các field export; nó không chứng minh mọi điều kiện redeem ngoài thực tế. Các dòng không khớp công thức cho thấy field hiện có chưa biểu diễn toàn bộ logic giá; không suy đoán nguyên nhân nếu không có evidence.

**Phân phối giá trị voucher.** Kiểm tra trực tiếp trên snapshot mới nhất của 588 listing có structured voucher (toàn bộ đều là VN, đơn vị VND):

| Metric | N | Min | P25 | Median | Mean | P75 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `voucher_discount` (VND) | 588 | 5.000 | 10.675 | 19.532,5 | 51.531,5 | 75.055 | 665.820 |
| `voucher_min_spend` (VND) | 588 | 50.000 | 50.000 | 150.000 | 226.528,9 | 250.000 | 3.000.000 |
| `voucher_discount / price_before_promo` | 588 | 9,00% | 10,00% | 11,63% | 12,60% | 15,90% | 22,00% |
| `voucher_discount / price_original` | 588 | 4,00% | 9,02% | 10,75% | 11,51% | 14,02% | 22,00% |

Mean cao hơn median vì một số sản phẩm giá trị lớn có voucher vài trăm nghìn đồng. Voucher lớn nhất là 665.820 VND cho listing `vn:1145316676:42232012026`, minimum spend 3.000.000 VND. Không so sánh số tiền voucher tuyệt đối giữa ngành hàng hoặc quốc gia mà chưa chuẩn hóa theo giá/minimum spend và tiền tệ.

`price` đã phản ánh tổng giảm được export, nên:

- không trừ `voucher_discount` thêm lần nữa khỏi `price`;
- không cộng `discount_percent` với voucher rate;
- không tạo các nhóm promotion/voucher bốn chiều từ các field hiện tại.

Nếu cần decomposition kỹ thuật, chỉ dùng tên proxy:

```text
pre_final_reduction_proxy =
    100 * (price_original - price_before_promo) / price_original

final_step_reduction_proxy =
    100 * (price_before_promo - price) / price_original
```

Không tự đổi `final_step_reduction_proxy` thành “voucher percent”: chỉ 1.011/1.580 structured-voucher rows khớp đúng số tiền bước cuối.

Voucher là thuộc tính theo listing snapshot, không phải thuộc tính cố định của `item_id`. Nếu cần định danh record:

```text
voucher_snapshot_key =
    country_code + ':' + shop_id + ':' + item_id + ':' + date + ':' + voucher_code
```

**Thời gian hiệu lực.** Trong 1.580 snapshot có structured voucher, kiểm tra trực tiếp:

- 1.580/1.580 có đủ cả `voucher_start_time` và `voucher_end_time`.
- 1.580/1.580 thỏa `start_time <= end_time`.
- Duration quan sát rơi vào bốn mốc xấp xỉ: ~24 giờ (808 snapshot), ~48 giờ (385), ~96 giờ (377) và ~120 giờ (10). Mốc kỹ thuật là 23,98/47,98/… giờ (không đúng tròn 24h) vì thời điểm kết thúc thường là `23:59` chứ không phải `24:00`.

Kiểm tra hiệu lực thời gian hiện chỉ ở cấp ngày vì dataset không có giờ crawl chính xác; không trình bày như xác nhận tới từng phút.

**Voucher đổi thế nào qua snapshot.** Trên 2.184 transition listing-snapshot liên tiếp có đủ trạng thái voucher ở cả hai đầu, kiểm tra trực tiếp:

| Trạng thái trước | Trạng thái sau | Transitions | Cách hiểu |
| --- | --- | ---: | --- |
| Không voucher | Không voucher | 1.125 | Không có structured voucher ở cả hai snapshot |
| Không voucher | Có voucher | 67 | Voucher xuất hiện |
| Có voucher | Không voucher | 59 | Voucher biến mất/hết hiệu lực hoặc export không còn ghi nhận |
| Có voucher | Có voucher | 933 | Có voucher ở cả hai snapshot |

Trong 933 transition có voucher ở cả hai đầu, `voucher_code` đổi ở 798 transition. Tính trên toàn bộ 2.184 transition — coi việc voucher xuất hiện/biến mất cũng là “giá trị đổi” — thì `voucher_discount` đổi ở 796/2.184 transition (670 đổi số tiền trong nhóm 933 có voucher cả hai lần, cộng 126 lần xuất hiện/biến mất) và `voucher_min_spend` đổi ở 234/2.184 transition (108 trong nhóm 933, cộng 126 lần xuất hiện/biến mất). Voucher vì vậy là thuộc tính theo snapshot, không phải thuộc tính cố định của product listing; không gắn một voucher duy nhất vĩnh viễn vào `item_id`.

**So sánh mô tả có/không có voucher (chỉ VN, snapshot mới nhất, không phải causal effectiveness).**

| Structured voucher | Listings | Shops | Median monthly sold | Median price (VND) | Median revenue proxy (VND) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Không | 94 | 6 | 284,5 | 38.700 | 10.873.500 |
| Có | 588 | 9 | 205,0 | 143.237,5 | 38.776.320 |

Không được đọc bảng này thành “voucher làm sales giảm” hay “voucher làm revenue tăng”. Hai nhóm khác mạnh về shop, ngành hàng và mức giá — có shop voucher rate 100%, shop khác 0% — nên đây là selection bias/confounding, không phải thử nghiệm causal. Để đánh giá hiệu quả voucher thật sự cần tối thiểu: so sánh cùng listing trước/trong/sau voucher với cửa sổ dài hơn ba ngày, kiểm soát shop/category/giá/seasonality, có order-level sales hoặc GMV, và tốt nhất có holdout/control group.

### Tiền tệ

Dataset không có field currency hay FX chuẩn hóa. VND cho VN và IDR cho Indonesia chỉ là local-market unit suy từ `country_code`. Không so sánh hoặc cộng trực tiếp giá, voucher hay revenue proxy tuyệt đối giữa VN và ID nếu chưa quy đổi theo một phương pháp FX được nêu rõ.

## 5. Data-quality findings

| Phát hiện đã kiểm tra                    | Kết quả / cách xử lý                                                                                                  |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Exact duplicate raw products                  | 30 nhóm, mỗi nhóm 2 dòng y hệt: 60 member rows, 30 redundant rows; processed còn 3.341                               |
| Duplicate theo snapshot key sau preprocessing | 0                                                                                                                          |
| Panel coverage                                | 1.039 listing đủ 3 ngày, 106 có 2 ngày, 12 có 1 ngày; thiếu 130 snapshot                                           |
| `history_sold_value` giảm                  | 88/2.136 valid transitions; tất cả ở VN                                                                                 |
| `monthly_sold_value` transitions            | 638 tăng, 992 không đổi, 413 giảm trên 2.043 valid transitions; giảm không tự động là lỗi                     |
| `shopee_verified`                           | 585`True`, 2.756 `False`                                                                                               |
| `is_ad`, `is_sold_out`                    | Toàn bộ 3.341 snapshot là`False`; không có variation để phân tích                                               |
| Price sentinel/outlier                        | 3 dòng`price = 999999999`; phải flag và làm sensitivity/exclusion rõ ràng                                          |
| Tên listing                                  | 5 nhóm trùng tên trong cùng shop ở snapshot mới nhất; 7 listing đổi tên qua ngày; không deduplicate bằng tên |
| Shop context                                  | Chỉ có snapshot 03/07; enrichment cho ngày trước là static/latest                                                    |
| Category mapping                              | 5 mapping orphan tới products; 1.132 product snapshots không có shop-category mapping                                   |

`history_sold_value` chỉ là cumulative-sales proxy. Với transition:

```text
history_sold_decrease_flag =
    history_sold_value_num < previous_history_sold_value_num

history_sold_delta_raw =
    history_sold_value_num - previous_history_sold_value_num

history_sold_delta_clean =
    history_sold_delta_raw nếu delta >= 0, ngược lại null
```

Giữ raw value và anomaly flag. Không âm thầm thay delta âm bằng 0; loại transition bị flag khỏi phép tính incremental sales.

Các fact chất lượng chỉ mô tả artifact hiện tại. Không dùng ba ngày quan sát để suy ra lỗi nguồn lâu dài, seasonality hoặc cơ chế nghiệp vụ của Shopee.

## 6. Analysis guardrails

1. Luôn nêu grain: listing, listing snapshot, transition hay category-membership row.
2. Dùng `product_snapshot_key` để truy xuất evidence và `product_listing_key` để nối chuỗi thời gian; không gọi `item_id` là SKU.
3. Chỉ so sánh theo thời gian khi có ít nhất hai snapshot hợp lệ; gắn `snapshot_gap_flag` khi thiếu ngày giữa.
4. Không cộng `monthly_sold_value` hoặc revenue proxy qua ba snapshots; không lấy diff của `monthly_sold_value` làm daily sales.
5. Gắn `history_sold_decrease_flag`; không dùng delta âm làm incremental sales.
6. Với phân tích cross-sectional, chọn một snapshot/date trước khi aggregate để mỗi listing chỉ đóng góp một lần.
7. Gọi `price` là final displayed/exported price, không phải checkout price. Không trừ voucher hai lần.
8. Nói rõ dùng structured voucher hay chỉ label UI. Không diễn giải thiếu structured fields ở ID thành chắc chắn không có voucher ngoài thực tế.
9. Không gọi `discount_percent > 0` là một cờ promotion độc lập; không suy luận promotion effectiveness từ `promotion_id`.
10. Khi phân tích shop category, chấp nhận multi-membership chỉ ở cấp từng kệ; deduplicate về listing-snapshot grain trước khi tính tổng shop/thị trường.
11. Dùng country trong mọi platform-category join và country + shop + date trong mọi shop-category join.
12. Không so sánh monetary values VN–ID nếu chưa có FX/currency normalization; không gắn unit VND cho dữ liệu ID.
13. Dùng ngôn ngữ “liên hệ”, “khác biệt mô tả”, “proxy”; không dùng “gây ra”, “tác động” hay “hiệu quả” nếu không có thiết kế causal.
14. Flag ba price sentinel; công bố rule include/exclude và chạy sensitivity check khi metric phụ thuộc giá.
15. Không kết luận từ inner join trên shop category là đại diện toàn bộ product population vì 1.132 snapshots không có mapping.

## 7. Hướng phân tích phù hợp và không phù hợp

### Phù hợp với dữ liệu hiện tại

- EDA theo một snapshot hoặc từng ngày: phân phối giá, rating, sold proxy, discount, voucher và listing attributes.
- So sánh mô tả VN–ID bằng tỷ lệ hoặc metric đã chuẩn hóa; monetary comparisons chỉ sau khi có quy đổi tiền tệ rõ ràng.
- So sánh listing/shop trong cùng thị trường theo official status, follower, shop rating, response metrics, nhưng gọi đây là association.
- Phân tích platform category theo top-level hoặc leaf path đã xác nhận.
- Phân tích cách shop trưng bày theo shop category, có kiểm soát multi-membership và missing mappings.
- Mô tả structured voucher, threshold, rate theo giá và sự thay đổi qua snapshot; không biến so sánh nhóm thành causal claim.
- Kiểm tra data consistency: snapshot coverage, name changes, sales-proxy anomaly, category orphan và price sentinel.
- Phân tích metadata trình bày như `images_count`, brand hoặc keyword title ở mức association.

### Không phù hợp hoặc chưa đủ bằng chứng

- Forecast, seasonality, trend tháng/quý hoặc kết luận tăng trưởng dài hạn từ ba ngày.
- Daily sales từ `diff(monthly_sold_value)`; “tổng sales lũy kế chính xác” từ `history_sold_value`.
- GMV, net revenue, profit, margin hoặc tối ưu chi phí vì không có transaction, cost và fee.
- Kết luận voucher/promotion gây tăng sales hay revenue; không có control group và confounding chưa được xử lý.
- Đánh giá ads vì `is_ad` toàn `False`.
- Phân tích hay theo dõi SKU/variation-level performance vì thiếu ID và metric cấp SKU.
- So sánh giá/voucher/revenue tuyệt đối VN–ID mà không chuẩn hóa currency/FX.
- Computer vision production analysis: hiện chưa có image binaries trong checkout và chưa có visual feature/embedding đáng tin cậy.

### Dữ liệu cần bổ sung để mở rộng phạm vi

Để trả lời chắc chắn ở cấp SKU và promotion, dataset hiện tại cần thêm:

- `sku_id` hoặc `model_id` cho từng variation, cùng giá/tồn kho/sales theo SKU và ngày.
- Crawl timestamp chính xác và crawl status/log cho từng request (hiện chỉ có `date` cấp ngày).
- Order hoặc transaction-level sales (hiện chỉ có `history_sold_value`/`monthly_sold_value` là display proxy).
- Campaign master data: start/end chính xác, eligibility, cost/funding và nhóm đối chứng cho voucher/promotion.
- Tài liệu nguồn giải thích chính xác cơ chế `history_sold_value`, `monthly_sold_value`, `price_before_promo` và `promotion_id`.

Cho tới khi có các trường trên, mọi kết quả trong tài liệu này và trong `data_grain_quality_audit.md` là data audit và descriptive evidence, không phải causal conclusion.

## 8. Repo navigation

```text
Gladiators/
├── data/
│   ├── raw/
│   └── processed/
├── notebooks/
│   ├── pipeline/data_pipeline.ipynb
│   └── tests/test_data_pipeline.ipynb
├── docs/
│   ├── Data_Context_and_Analysis_Notes.md
│   ├── V1_Architecture.md
│   ├── Architecture-spec.md
│   ├── V1_Implementation_Limitations.md
│   ├── data-pipeline.md
│   ├── codegraph.md
│   └── V0_Architecture.md
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

Điểm vào theo nhu cầu:

- Context, grain, semantics và guardrail: tài liệu này (mục 1–7).
- Kiến trúc runtime hiện tại: [CURRENT_ARCHITECTURE_SPEC.md](../CURRENT_ARCHITECTURE_SPEC.md).
- Kiến trúc mục tiêu V2: [V2_Unified_Architecture.md](../design/V2_Unified_Architecture.md).
- Thiết kế cũ và gap V1 để tra lịch sử: [Architecture-spec.md](../archive/architecture/Architecture-spec.md) và [V1_Implementation_Limitations.md](../archive/architecture/V1_Implementation_Limitations.md).
- Pipeline và output columns: [data-pipeline.md](data-pipeline.md).
- Luồng code và dependency metric: [codegraph.md](codegraph.md).
- Phân tích snapshot nhanh: `data/processed/product_snapshot_metrics.csv`.
- Evidence chất lượng: `data/processed/data_quality_issues.csv` và `pipeline_report.json`.
- Thiết kế V0 để tra cứu lịch sử: [V0_Architecture.md](../archive/architecture/V0_Architecture.md), không dùng làm data source of truth.

Image download không còn thuộc phạm vi code hiện hành. Nếu bổ sung lại sau này, cache binary phải tách khỏi artifact phân tích lõi và có kiểm tra coverage riêng.

## 9. Business dictionary chuẩn hóa (đối chiếu `business-dictionary.md`)

`business-dictionary.md` là nghiên cứu độc lập trước đây của một thành viên khác. File nguồn không còn nằm trong cấu trúc hiện hành; mục này giữ phần đối chiếu đã xác minh để tránh tái sử dụng các định nghĩa sai. Các công thức và số liệu được kiểm tra trên `data/processed/products_clean.csv` và metric outputs hiện hành.

### 9.1. Kết luận kiểm tra tính đúng đắn

| Hạng mục trong `business-dictionary.md` | Kết luận | Ghi chú |
| --- | --- | --- |
| Data grain & keys (mục 1) | Đúng | Khớp `product_listing_key`/`product_snapshot_key` và grain `category_list_clean` |
| Metric 1 – Estimated Recent Revenue | Đúng | Khớp `estimated_recent_revenue` trong `preprocessing.md` |
| Metric 2 – Snapshot Sales Delta | **Sai/thiếu caveat quan trọng** | Dùng `history_sold_value` (hiếm giảm, giảm = anomaly) làm tín hiệu chính cho Intent 1, trong khi tín hiệu “giảm bán” thật sự nên dựa trên `monthly_sold_value` |
| Metric 3 – Monthly Sold Delta | Đúng | Caveat sẵn có trong dictionary đã hợp lý |
| Metric 4–7 – Price/Discount deltas | Đúng | `discount_amount_num` khớp 100% với `price_original_num - price_num` (0 mismatch/3.341 dòng) |
| Metric 8 – 4 nhóm Promo/Voucher | **Sai về cấu trúc** | Nhóm “voucher only” luôn = 0/3.341 dòng; `has_promo` định nghĩa đúng thứ mà guardrail #9 của tài liệu này cấm dùng làm cờ độc lập |
| Metric 9–11 – Rating/Like delta | Đúng | Không có vấn đề dữ liệu |
| Metric 12 – Stock Status Matrix | **Sai/vô hiệu với dữ liệu hiện tại** | `is_sold_out_bool = False` ở toàn bộ 3.341 dòng; chỉ trạng thái “Available” từng xảy ra |
| Intent 1 – Sales Decline | **Sai field trigger** | Xem Metric 2; nên tách anomaly `history_sold_value` khỏi tín hiệu giảm bán thật |
| Intent 2 – Similar Product | Không kiểm chứng đúng/sai được | Là lựa chọn thiết kế nghiệp vụ, không phải data claim; đã bổ sung số liệu tham chiếu bên dưới |
| Intent 3 – Promotion Effectiveness | **Sai/không khả thi** | So sánh chéo VN–ID cho nhóm có voucher là bất khả thi vì ID có 0/1.422 dòng structured voucher |
| Guardrail 1–3 | Đúng | Nhất quán với guardrail hiện có ở mục 6–7 |

### 9.2. Data grain & keys (giữ nguyên, đã xác nhận đúng)

Một dòng của `products_clean.csv` là một product listing của một shop, tại một quốc gia, ở một ngày snapshot — không phải cấp SKU.

```text
product_listing_key   = country_code + ':' + shop_id + ':' + item_id
product_snapshot_key  = product_listing_key + ':' + date
merchandising_key      = country_code + ':' + shop_id + ':' + shop_category_id + ':' + date
```

`merchandising_key` khớp đúng grain `category_list_clean` ở mục 3. Ba dòng `price_num = 999999999` là sentinel/outlier, phải loại trước mọi phép tính (Sales, Price, Revenue).

### 9.3. Sales proxy metrics

| Metric | Formula | Trạng thái |
| --- | --- | --- |
| Estimated Recent Revenue | `price_num * monthly_sold_value_num` | Đúng; chỉ là revenue proxy tại một snapshot, không phải doanh thu thực tế |
| Monthly Sold Delta | `monthly_sold_value_num(T) - monthly_sold_value_num(T-1)` | Đúng; giảm không tự động là lỗi |

**Snapshot Sales Delta — đã sửa:**

```text
snapshot_sales_delta = history_sold_value_num(T) - history_sold_value_num(T-1)
```

Định nghĩa cũ mô tả field này “phản ánh lượng bán mới phát sinh” vì `history_sold_value` được kỳ vọng lũy kế. Về công thức thì đúng, nhưng thiếu caveat bắt buộc: trên 2.136 transition có đủ history values, có 88 lần (4,12%) `history_sold_value` **giảm**, toàn bộ ở VN. Pipeline hiện hành xếp đây là anomaly, không phải tín hiệu kinh doanh sạch. Quy tắc bắt buộc khi dùng metric này:

```text
history_sold_decrease_flag = history_sold_value_num(T) < history_sold_value_num(T-1)
```

Khi `history_sold_decrease_flag = True`, không được báo cáo `snapshot_sales_delta` như “lượng bán mới phát sinh” (giá trị sẽ âm, vô nghĩa về nghiệp vụ); phải báo cáo như một data-quality anomaly (khả năng do reset/correction phía nguồn hoặc lỗi crawl), giữ raw value và loại khỏi mọi phép cộng incremental sales.

### 9.4. Pricing & promotion metrics

| Metric | Formula | Trạng thái |
| --- | --- | --- |
| Price Change | `price_num(T) - price_num(T-1)` | Đúng |
| Price Change Percentage | `[(price_num(T) - price_num(T-1)) / price_num(T-1)] * 100%` | Đúng; loại 3 sentinel `price=999999999` trước khi tính |
| Discount Amount | `price_original_num - price_num` | Đúng; khớp 100% cột `discount_amount_num` đã có sẵn trong `products_clean.csv` |
| Discount Point Change | `discount_percent_num(T) - discount_percent_num(T-1)` | Đúng |

**Cờ Promo/Voucher và 4 nhóm — đã sửa:**

```text
has_promo   = discount_percent_num > 0
has_voucher = voucher_discount_num > 0     # tương đương has_structured_voucher ở mục 4
```

Hai công thức này đúng và tương đương định nghĩa `has_structured_voucher` đã dùng ở mục 4. Nhưng 4 nhóm `no voucher/promo` / `promo only` / `voucher only` / `voucher + promo` **không phải bốn nhóm độc lập, cân bằng** như trình bày. Kiểm tra trực tiếp trên toàn bộ 3.341 dòng:

| `has_promo` ↓ / `has_voucher` → | False | True |
| --- | ---: | ---: |
| **False** | 307 | **0** |
| **True** | 1.454 | 1.580 |

Nhóm “voucher only” (`has_promo=False, has_voucher=True`) luôn bằng 0 vì lý do toán học, không phải trùng hợp: cả 1.580/1.580 dòng có voucher đều thỏa `discount_percent ≈ 100 × (price_original - price) / price_original` trong sai số 1 điểm phần trăm — nghĩa là `price` đã phản ánh voucher, nên `discount_percent` tự động dương bất cứ khi nào có voucher. Đây chính là điều guardrail #9 (mục 6) đã cấm: không coi `discount_percent > 0` là cờ promotion độc lập với voucher.

Theo quốc gia (giải thích vì sao Intent 3 không khả thi khi so sánh chéo VN–ID, xem mục 9.6):

| Country | `has_promo=F, has_voucher=F` | `has_promo=T, has_voucher=F` | `has_promo=F, has_voucher=T` | `has_promo=T, has_voucher=T` |
| --- | ---: | ---: | ---: | ---: |
| `id` | 175 | 1.247 | 0 | 0 |
| `vn` | 132 | 207 | 0 | 1.580 |

Khuyến nghị dùng thay thế: chỉ 3 nhóm thực tế tồn tại — `no voucher/promo`, `promo only`, `voucher + promo` — và luôn báo rõ quốc gia vì ID không có dòng nào thuộc nhóm có voucher.

### 9.5. Engagement & stock metrics

| Metric | Formula | Trạng thái |
| --- | --- | --- |
| Rating Change | `rating_num(T) - rating_num(T-1)` | Đúng |
| New Rating Count | `rating_count_num(T) - rating_count_num(T-1)` | Đúng |
| Like Delta | `liked_count_num(T) - liked_count_num(T-1)` | Đúng |

**Stock Status Matrix — đã sửa:** ma trận 4 trạng thái (`Available`/`Newly Sold Out`/`Restocked`/`Still Sold Out`) dựa trên `is_sold_out_bool` qua 2 snapshot liên tiếp là định nghĩa hợp lệ về mặt logic, nhưng **không quan sát được với dữ liệu hiện tại**: `is_sold_out_bool = False` ở toàn bộ 3.341/3.341 dòng (0 variance, trùng với finding `is_ad`/`is_sold_out` ở mục 5). Với dữ liệu hiện tại, mọi transition đều rơi vào `Available`; ba trạng thái còn lại không có evidence. Không dùng ma trận này để phân tích cho tới khi dataset có ít nhất một snapshot ghi nhận `is_sold_out_bool = True`.

### 9.6. Logic điều phối 3 Intent — đã sửa Intent 1 và Intent 3

**Intent 1: Sales Decline.** `business-dictionary.md` định nghĩa điều kiện kích hoạt bằng delta của `history_sold_value_num` — chính là Metric 2 ở trên. Vì `history_sold_value` giảm là **hiếm và bất thường** (88/2.136 = 4,12%, toàn bộ VN) trong khi `monthly_sold_value` giảm là **phổ biến và không tự động là lỗi** (413/2.043 = 20,2%), dùng `history_sold_value` làm trigger chính cho “Sales Decline” sẽ khiến intent này gần như luôn báo cáo một data anomaly như thể là tín hiệu kinh doanh thật. Quy tắc đề xuất:

```text
Trigger chính (tín hiệu giảm bán thật, phổ biến):
  monthly_sold_value_num(T) - monthly_sold_value_num(T-1) < 0

Trigger phụ (data-quality anomaly, hiếm, cần cảnh báo riêng):
  history_sold_value_num(T) - history_sold_value_num(T-1) < 0
  -> văn phong bắt buộc: nêu rõ đây là anomaly dữ liệu (reset/correction phía nguồn nghi vấn),
     không phải bằng chứng giảm bán, trước khi báo cáo covariates.
```

Phần covariates bắt buộc (`price_change`, `discount_point_change`, trạng thái voucher, `is_sold_out`) và mức kết luận “chỉ tương quan” trong dictionary là đúng, giữ nguyên.

**Intent 2: Similar Product.** Ba tầng lọc (cùng `country_code` + giao `global_catids`; biên độ giá ±20%; ưu tiên `is_official_shop`) là lựa chọn thiết kế nghiệp vụ, không phải data claim nên không có “đúng/sai”. Tham chiếu số liệu để áp dụng cho đúng: độ sâu `global_catids` trong dataset hiện tại là 2 cấp (395 snapshot), 3 cấp (2.623) hoặc 4 cấp (323) — lọc “cấp 2 hoặc 3” sẽ bỏ qua ID sâu nhất của 323 snapshot 4-cấp; nên xác nhận chủ đích trước khi áp dụng nguyên văn.

**Intent 3: Promotion Effectiveness — đã sửa.** Yêu cầu “so sánh chéo kết quả này giữa hai thị trường VN và ID” trên 4 nhóm Promo Groups là **bất khả thi với 2 trong 4 nhóm**: ID có 0/1.422 dòng thuộc `voucher only` hoặc `voucher + promo` (bảng ở mục 9.4). Chỉ có thể so sánh chéo VN–ID ở nhóm `no voucher/promo` và `promo only`; nhóm có voucher chỉ phân tích được nội bộ VN. Phương pháp trung vị (median) thay vì trung bình là đúng và nên giữ.

### 9.7. Guardrails

Ba guardrail No-Causal-Inference / No-Forecasting / Out-of-Scope-Handling trong `business-dictionary.md` đúng và nhất quán với guardrail #13 (mục 6) và mục 7 của tài liệu này; không cần sửa. Khi nạp guardrail cho Agent, dùng bản đầy đủ hơn ở mục 6–7 của tài liệu này (15 mục) làm chuẩn, vì bao phủ nhiều trường hợp hơn (ví dụ: SKU-level, ads, category orphan) mà `business-dictionary.md` chưa liệt kê.
