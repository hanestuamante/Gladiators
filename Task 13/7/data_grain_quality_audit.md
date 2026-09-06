# Kiểm định grain và chất lượng dữ liệu sản phẩm

Ngày kiểm định: `2026-07-12`

Notebook tái lập kết quả: `Research/data_grain_quality_audit.ipynb`

Nguồn chính: `Dataset/DataProcessed/product_dataset_ready.csv`. Dữ liệu raw được dùng để xác minh duplicate trước preprocessing.

## 1. Kết luận ngắn

- Xác nhận file processed có đúng **3.341 dòng**.
- Xác nhận có **1.157 product listing** khác nhau theo `country_code + shop_id + item_id`: Indonesia có 475, Việt Nam có 682.
- 3.341 dòng không phải 3.341 sản phẩm và cũng không phải 3.341 SKU. Mỗi dòng là một **snapshot của một product listing tại một ngày**.
- Grain hợp lý và duy nhất sau preprocessing là:

```text
country_code + shop_id + item_id + date
```

- Dataset không có `sku_id`, `model_id`, variation-level price, variation-level stock hoặc variation-level sales. Vì vậy **không thể đếm hay theo dõi SKU thật** từ dữ liệu hiện tại.
- Raw `products` có 3.371 dòng, gồm 30 cặp duplicate exact. Sau khi bỏ 30 dòng thừa, processed còn 3.341 dòng và không còn duplicate ở grain đã chọn.
- Nếu dựng panel cân bằng 1.157 listing x 3 ngày thì cần 3.471 snapshot. Dataset thiếu 130 ô snapshot. Chỉ 1.039/1.157 listing có đủ cả 3 ngày.
- Không có một cột chung tên `sales`: `history_sold_value` là proxy bán lịch sử được kỳ vọng lũy kế, còn `monthly_sold_value` là proxy bán gần đây theo cửa sổ và không lũy kế.
- `history_sold_value` vi phạm tính không giảm ở 88/2.136 chuyển tiếp hợp lệ. Cả 88 trường hợp đều ở VN, nên không thể xem field này là bộ đếm lũy kế sạch nếu chưa gắn cờ chất lượng.
- Dataset không có cột `promo_percent`. Báo cáo tạo `promo_percent_derived` để kiểm định, nhưng đây là biến suy diễn và phải giữ tên `_derived`.
- Structured voucher có ở 1.580/3.341 snapshot và chỉ xuất hiện trong dữ liệu VN. Cột `vouchers` còn chứa nhiều nhãn ưu đãi không phải voucher tiền tệ, nên phải tách hai khái niệm khi phân tích.

## 2. Xác minh 3.341 dòng và 1.157 sản phẩm

### 2.1. Tổng thể theo quốc gia

| Country | Snapshot rows | Shops | Product listings |
| --- | ---: | ---: | ---: |
| `id` | 1.422 | 10 | 475 |
| `vn` | 1.919 | 10 | 682 |
| **Tổng** | **3.341** | **20** | **1.157** |

Trong dataset này, `item_id` cũng có đúng 1.157 giá trị khác nhau và không có `item_id` nào xuất hiện ở nhiều shop hoặc nhiều quốc gia. Tuy nhiên, khóa nghiệp vụ vẫn nên giữ đủ scope `country_code + shop_id + item_id`; không nên dựa vào tính duy nhất tình cờ của `item_id` trong một mẫu dữ liệu hữu hạn.

### 2.2. Số listing theo shop

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
| `vn` | `108166524` | Nestlé Chính hãng | 226 | 82 |
| `vn` | `1145316676` | Nestlé Health Science | 259 | 87 |
| `vn` | `140360136` | Kinh Do Official Store | 103 | 35 |
| `vn` | `1546895026` | Mars Snacking VN | 140 | 71 |
| `vn` | `173513432` | Richy - Chi Nhánh Miền Bắc | 213 | 71 |
| `vn` | `213989179` | Bibica Official Store | 287 | 96 |
| `vn` | `289646907` | Orion VN Official Store | 226 | 84 |
| `vn` | `430972539` | Perfetti Van Melle Vietnam | 66 | 22 |
| `vn` | `438905996` | Richy - Chi nhánh Miền Nam | 363 | 122 |
| `vn` | `464391416` | Bánh Kẹo Hải Hà - Chính hãng | 36 | 12 |

## 3. Grain và khóa ứng viên

### 3.1. Grain thực tế

Một dòng biểu diễn:

```text
Một product listing của một shop, tại một quốc gia, được quan sát trong một ngày snapshot.
```

`item_id` là ID của listing trên Shopee, không phải SKU con. Các size, màu, mùi vị hoặc quy cách có thể nằm trong `tier_variation_options`, nhưng vẫn được gói trong cùng một dòng listing.

### 3.2. Đánh giá khóa

| Ứng viên | Vai trò | Kết quả |
| --- | --- | --- |
| `country_code + shop_id + item_id + date` | Khóa chính snapshot | Duy nhất: 0 duplicate sau preprocessing |
| `country_code + shop_id + item_id` | Khóa thực thể listing qua thời gian | 1.157 thực thể, lặp lại tối đa 3 ngày |
| `item_id + date` | Khóa kỹ thuật trong mẫu hiện tại | Duy nhất, nhưng thiếu scope shop/country nên không khuyến nghị lâu dài |
| `url + date` | Khóa kiểm tra phụ | Dùng đối soát được, không nên là PK vì URL là thuộc tính có thể đổi format |
| `item_id` | ID listing trong mẫu hiện tại | 1.157 giá trị, nhưng lặp giữa các ngày |
| `key` | Không dùng được | Trống trong dữ liệu hiện tại |
| `product_name` | Không phải khóa | Có tên trùng và có 7 listing đổi tên giữa các snapshot |
| `tier_variation_options` | Không phải khóa SKU | Chỉ là JSON list, không có ID ổn định hoặc metric theo từng option |

Khuyến nghị cho semantic layer:

```text
product_listing_key = country_code + ':' + shop_id + ':' + item_id
product_snapshot_key = product_listing_key + ':' + date
```

Chỉ tạo `sku_key` khi nguồn mới cung cấp `sku_id/model_id` thật.

## 4. Snapshot trùng và thiếu

### 4.1. Duplicate
# Một sản phẩm có bị ghi nhận hai lần trong cùng ngày không?
- Vì grain chính gồm `country_code + shop_id + item_id + date` -> Sẽ không biết trường hợp nếu 1 ngày 2 đơn thì liệu có ghi nhận đúng không vì không có thời gian cụ thể mỗi đơn -> chạy raw data thấy 3371 dòng có 60 dòng HOÀN TOÀN giống nhau -> Giữ 1 nửa nên xoá 30 dòng (Giữ sẽ bị đếm 2 lần) -> Nhưng ta không biết liệu ghi nhận 2 lần trong 1 ngày do đặt 2 lần hay không

Raw `products`:

- 3.371 dòng.
- 30 nhóm duplicate grain, mỗi nhóm gồm 2 dòng giống hệt nhau.
- 60 dòng nằm trong các nhóm duplicate, tương đương 30 dòng thừa.
- Toàn bộ duplicate đến từ `country_code=vn`, shop `289646907`.
- Không có duplicate grain chứa dữ liệu mâu thuẫn: mỗi cặp là exact duplicate.

Processed `product_dataset_ready.csv`: -> Đã xử lí 30 trường hợp duplicate

- 3.341 dòng.
- 0 duplicate theo `country_code + shop_id + item_id + date`.

### 4.2. Coverage theo ngày
- Mỗi sản phẩm có đủ dữ liệu ở cả ba ngày không?

| Date | Snapshot rows |
| --- | ---: |
| `2026-07-01` | 1.055 |
| `2026-07-02` | 1.144 |
| `2026-07-03` | 1.142 |

| Số ngày có mặt | Listings | Tỷ lệ |
| ---: | ---: | ---: |
| 3 ngày | 1.039 | 89,80% | -> Phần lớn có mặt ở đủ 3 ngày 
| 2 ngày | 106 | 9,16% |
| 1 ngày | 12 | 1,04% |

 `1.157 x 3 = 3.471` ô. Nhưng Dataset chỉ có 3.341 ô, nên có **130 khoảng trống snapshot**

| Country | Thiếu 01/07 | Thiếu 02/07 | Thiếu 03/07 |
| --- | ---: | ---: | ---: |
| `id` | 1 | 1 | 1 |
| `vn` | 101 | 12 | 14 |

### Các case thiếu snapshot theo quốc gia

#### Việt Nam (`vn`)

| Các ngày listing có mặt | Các ngày bị thiếu | Số listing | Snapshot thiếu |
| --- | --- | ---: | ---: |
| `02/07, 03/07` | `01/07` | 95 | 95 |
| `01/07, 02/07` | `03/07` | 5 | 5 |
| `01/07, 03/07` | `02/07` | 5 | 5 |
| Chỉ `01/07` | `02/07, 03/07` | 5 | 10 |
| Chỉ `02/07` | `01/07, 03/07` | 4 | 8 |
| Chỉ `03/07` | `01/07, 02/07` | 2 | 4 |
| **Tổng case không đầy đủ** |  | **116 listing** | **127 snapshot** |


Ngoài 116 listing không đầy đủ, VN còn 566 listing có đủ cả `01/07, 02/07, 03/07`. Tổng cộng: `116 + 566 = 682 listing VN`.

#### Indonesia (`id`)

| Các ngày listing có mặt | Các ngày bị thiếu | Số listing | Snapshot thiếu |
| --- | --- | ---: | ---: |
| Chỉ `03/07` | `01/07, 02/07` | 1 | 2 |
| `01/07, 02/07` | `03/07` | 1 | 1 |
| **Tổng case không đầy đủ** |  | **2 listing** | **3 snapshot** |


Ngoài 2 listing không đầy đủ, ID còn 473 listing có đủ cả `01/07, 02/07, 03/07`. Tổng cộng: `2 + 473 = 475 listing ID`.

Tổng hợp hai quốc gia:

```text
Listing không đủ 3 ngày = 116 VN + 2 ID = 118 listing
Snapshot thiếu           = 127 VN + 3 ID = 130 snapshot
```

Diễn giải chi tiết khi đi sâu vào ta thấy: 

- 95 listing VN chỉ có `2026-07-02` và `2026-07-03`; đây có thể là listing/shop mới , không đủ bằng chứng gọi là mất dữ liệu.
- 5 listing VN có ngày `01/07` và `03/07` nhưng thiếu `02/07`. Đây là internal gap rõ nhất và nên ta có thể gắn `snapshot_gap_flag = True`.
-> Cần giải pháp xử lí hoặc không xử lí 

## 5. Trùng tên và biến thể
- Có thể dùng product_name thay cho item_id để nhận diện hoặc gộp sản phẩm không? -> Không
Trên snapshot mới nhất của từng listing:

- Có 5 nhóm tên trùng hoàn toàn trong cùng shop.
- 10 `item_id` nằm trong các nhóm này, tức 5 listing dư nếu ai đó deduplicate bằng tên.
- Có 7 listing thay đổi tên giữa các ngày.

Chi tiết 5 nhóm tên trùng nhưng `item_id` khác được trình bày bên dưới.

| Nhóm | Country | Shop | Item ID | Product name đầy đủ ở snapshot mới nhất | Snapshot date |
| ---: | --- | --- | --- | --- | --- |
| 1 | `id` | `809769142` | `46312750544` | [ FREE GIFT FOR 6/25! ]Dapatkan Hadiah Dengan Min. Pembelian 300RB | `2026-07-03` |
| 1 | `id` | `809769142` | `55559898858` | [ FREE GIFT FOR 6/25! ]Dapatkan Hadiah Dengan Min. Pembelian 300RB | `2026-07-03` |
| 2 | `id` | `809769142` | `40781619061` | Glad2Glow Perfect Airbrush Setting Spray -All DAY GLOW SETTINGSPRAY -White Truffle SerumSpray 100ml-All Day Matte Setting Spray -Kunci Makeup 12H Anti Luntur & Kontrol Minyak - Soft Matte Finish Anti Geser Waterproof & Sweatproof-glad2glow offcial | `2026-07-03` |
| 2 | `id` | `809769142` | `45462078618` | Glad2Glow Perfect Airbrush Setting Spray -All DAY GLOW SETTINGSPRAY -White Truffle SerumSpray 100ml-All Day Matte Setting Spray -Kunci Makeup 12H Anti Luntur & Kontrol Minyak - Soft Matte Finish Anti Geser Waterproof & Sweatproof-glad2glow offcial | `2026-07-03` |
| 3 | `id` | `809769142` | `41381802204` | Glad2Glow Perfect Blur&Cover Loose Powder oil control Finishing Kontrol Minyak Tahan Lama Anti Luntur Halus Sempurna & Cover Tinggi bedak padat bedak tabur two way cake cushion foundation setting spray make up g2g glad2glow official store | `2026-07-03` |
| 3 | `id` | `809769142` | `43360906112` | Glad2Glow Perfect Blur&Cover Loose Powder oil control Finishing Kontrol Minyak Tahan Lama Anti Luntur Halus Sempurna & Cover Tinggi bedak padat bedak tabur two way cake cushion foundation setting spray make up g2g glad2glow official store | `2026-07-03` |
| 4 | `vn` | `108166524` | `24814585810` | [Phiên bản ống hút 4 chiều] Sữa Lúa Mạch Nestlé MILO 48x180ml Không Màng Co | `2026-07-02` |
| 4 | `vn` | `108166524` | `55211157221` | [Phiên bản ống hút 4 chiều] Sữa Lúa Mạch Nestlé MILO 48x180ml Không Màng Co | `2026-07-03` |
| 5 | `vn` | `108166524` | `45252508882` | [Tặng Bộ 3 hũ đựng gia vị NESCAFÉ] Bịch Cà phê Hòa tan NESCAFÉ VỊ NGUYÊN BẢN 46 gói Đậm Thơm Hoàn Hảo | `2026-07-03` |
| 5 | `vn` | `108166524` | `51652982842` | [Tặng Bộ 3 hũ đựng gia vị NESCAFÉ] Bịch Cà phê Hòa tan NESCAFÉ VỊ NGUYÊN BẢN 46 gói Đậm Thơm Hoàn Hảo | `2026-07-03` |

Ví dụ ở nhóm 4, hai listing có tên giống nhau nhưng khóa vẫn khác:

```text
vn:108166524:24814585810
vn:108166524:55211157221
```


## 6. Product hay SKU, và có theo dõi SKU nhiều ngày không?
- Định nghĩa theo dõi SKU nhiều ngày: Cùng một SKU được quan sát lặp lại ở nhiều ngày snapshot để theo dõi giá, tồn kho, lượt bán hoặc trạng thái của chính SKU đó theo thời gian.

Kết luận: dataset theo dõi **product listing qua nhiều ngày**, không theo dõi SKU.

- 1.157 listing được theo dõi: 1.039 listing có 3 ngày, 106 có 2 ngày, 12 có 1 ngày.
- 727/1.157 listing có `tier_variation_name` khác rỗng.
- 582/1.157 listing có từ 2 option trở lên ở snapshot mới nhất.
- Listing nhiều nhất có 38 option.
- Không có `sku_id/model_id`, giá, tồn kho hoặc sales riêng theo option.

- Không thể theo dõi SKU nhiều ngày 
- Ở mỗi snapshot chỉ cung cấp tier_variation_name và tier_variation_options nhưng không cho biết chính xác tier_variation_option để ta tạo sku_id -> vấn đề -> Liệu ta có thể tìm cách tạo SKU_id được không và tạo xong ta nhận được gì ( có xem được giá thay đổi, lượt bán trạng thái không)

Ví dụ: 
item_id = 12345
tier_variation_name = "Hương vị"
tier_variation_options = ["Socola", "Dâu", "Vani"]
## 7. Sales có phải lũy kế không, và sales lũy kế có giảm bất thường không?

### 7.1. Trước hết, “Sales” trong dataset là field nào?

Dataset không có order-level sales, daily sales hay một cột duy nhất tên `sales`. Hai field gần nhất với sales là:

| Field | Ý nghĩa phù hợp để sử dụng | Có phải lũy kế không? | Có được xem là sales chính xác không? |
| --- | --- | --- | --- |
| `history_sold_value` | Số lượng đã bán trong lịch sử do Shopee hiển thị | **Được kỳ vọng là lũy kế** | Không; đây là display proxy, có làm tròn và có anomaly |
| `monthly_sold_value` | Số lượng bán gần đây/theo tháng do Shopee hiển thị | **Không lũy kế**; là metric theo cửa sổ gần đây | Không; cửa sổ chính xác chưa được nguồn mô tả |

Vì vậy, câu hỏi “Sales có phải lũy kế không?” không có một đáp án chung cho cả hai field:

```text
history_sold_value -> kỳ vọng lũy kế
monthly_sold_value -> không lũy kế
```

Không được gọi `monthly_sold_value` là “sales lũy kế”, và cũng không được coi `history_sold_value` là transaction ledger.

### 7.2. Có đủ bằng chứng coi `history_sold_value` là lũy kế không?

Có các tín hiệu ủng hộ cách hiểu lũy kế:

- Tên field là `history_sold_value`, tương ứng số bán lịch sử.
- Trong toàn bộ 3.138 dòng có đồng thời hai field, `history_sold_value >= monthly_sold_value`.
- Không có `history_sold_value` âm.
- 2.048/2.136 chuyển tiếp hợp lệ, tương đương 95,88%, không giảm.

Nhưng không thể xác nhận đây là bộ đếm lũy kế sạch vì:

- Nhiều giá trị bị làm tròn/bucket ở `1.000`, `2.000`, ..., `10.000`.
- Có 88 chuyển tiếp giảm, trái với tính chất của một biến lũy kế chuẩn.
- Không có tài liệu API, crawl log hoặc order ledger để xác nhận cơ chế tạo field.

Kết luận phù hợp:

> `history_sold_value` là **cumulative sales proxy được kỳ vọng lũy kế**, nhưng dữ liệu quan sát không hoàn toàn monotonic. Không nên gọi đây là “tổng sales lũy kế chính xác”.

### 7.3. Sales lũy kế proxy có giảm bất thường không?

Có. Chỉ kiểm tra câu hỏi này trên `history_sold_value`, không kiểm tra trên `monthly_sold_value`.

Trên 2.136 chuyển tiếp có đủ `history_sold_value` ở hai snapshot:

| Direction | Transitions | Tỷ lệ | Cách hiểu |
| --- | ---: | ---: | --- |
| Tăng | 395 | 18,49% | Phù hợp với biến lũy kế |
| Không đổi | 1.653 | 77,39% | Phù hợp với biến lũy kế hoặc do làm tròn |
| Giảm | 88 | 4,12% | Bất thường nếu field thực sự lũy kế |

Theo quốc gia:

| Country | Valid transitions | Tăng | Không đổi | Giảm bất thường |
| --- | ---: | ---: | ---: | ---: |
| `id` | 925 | 128 | 797 | 0 |
| `vn` | 1.211 | 267 | 856 | 88 |

Chi tiết 88 lần giảm:

- Thuộc 88 listing khác nhau và đều ở VN.
- 46 lần xảy ra từ `01/07 -> 02/07`; 42 lần từ `02/07 -> 03/07`.
- 86/88 lần đồng thời có `monthly_sold_value` giảm.
- 24/88 lần đồng thời có cả `monthly_sold_value` và `rating_count` giảm.
- Các shop có nhiều case nhất: `173513432` (25), `1145316676` (15), `438905996` (13), `1546895026` (10).

Ví dụ giảm lớn nhất:

```text
country_code = vn
shop_id      = 173513432
item_id      = 2989938577
date         = 2026-07-02 -> 2026-07-03
history_sold = 30.000 -> 10.000
delta        = -20.000
```

Đây là anomaly dữ liệu đối với một biến được kỳ vọng lũy kế. Các nguyên nhân có thể gồm reset/correction phía nguồn, thay đổi cách làm tròn/hiển thị, parser/crawl không ổn định hoặc listing thay đổi cấu hình. Dataset không có đủ evidence để khẳng định nguyên nhân nào.

Rule xử lý:

```text
history_sold_decrease_flag = history_sold_value_num < previous_history_sold_value_num
history_sold_delta_raw     = history_sold_value_num - previous_history_sold_value_num
history_sold_delta_clean   = history_sold_delta_raw nếu delta >= 0, ngược lại để null
```

Giữ nguyên giá trị raw và flag anomaly. Không âm thầm thay delta âm bằng 0, đồng thời loại transition bị flag khỏi phép tính incremental sales.

### 7.4. Vì sao không kiểm tra “giảm bất thường” tương tự cho `monthly_sold_value`?

`monthly_sold_value` không phải biến lũy kế. Trong 2.043 chuyển tiếp hợp lệ, field này tăng 638 lần, không đổi 992 lần và giảm 413 lần.

Việc giảm không tự động là lỗi: giao dịch cũ có thể rời khỏi cửa sổ gần đây, nhu cầu có thể giảm hoặc Shopee có thể thay đổi cách làm tròn. Do đó:

```text
diff(monthly_sold_value) != daily sales
monthly_sold_value giảm  != cumulative-sales anomaly
```

Chỉ gọi 88 lần giảm của `history_sold_value` là anomaly đối với giả định lũy kế. Không gộp 413 lần giảm của `monthly_sold_value` vào cùng kết luận.

## 8. `discount_percent` và `promo_percent`

### 8.1. `discount_percent`

Có 3.034/3.341 dòng có `discount_percent`; 307 dòng để trống. Cả 307 dòng trống đều có `price == price_original`


Chỉ fill 0 khi `price == price_original`; nếu sau này xuất hiện missing nhưng giá khác giá gốc thì phải giữ null và flag lỗi.

Kiểm tra công thức cho thấy 3.034/3.034 dòng có discount khớp trong sai số 1 điểm phần trăm với:

```text
100 * (price_original - price) / price_original
```

Trong đó 3.007 dòng khớp chính xác sau khi làm tròn số nguyên. Vì vậy `discount_percent` là **tổng mức giảm thể hiện trong giá cuối**, không phải phần promo độc lập với voucher.

### 8.2. Không có `promo_percent` gốc

Dataset không có cột `promo_percent`. `promotion_id` không null ở cả 3.341 dòng, nhưng 874 dòng mang giá trị `0`; cần coi `0` là sentinel “không có/không xác định promotion”, không phải một promotion thật. Ngoài ra, 2 dòng không giảm giá vẫn mang `promotion_id = 10000010850`. Vì vậy, cả điều kiện `promotion_id != null` lẫn `promotion_id != 0` đều chưa đủ để khẳng định promotion đang tạo ra discount tại snapshot đó.

Notebook tạo biến kiểm định:

```text
promo_percent_derived =
    100 * (price_original - price_before_promo) / price_original
```

Tên `_derived` là bắt buộc. Dựa trên quan hệ giá/voucher đã kiểm tra trước đây, `price_before_promo` trong export có hành vi gần với giá trước phần voucher cuối. Tên field nguồn gây mơ hồ, nên biến trên chỉ là proxy cho phần giảm trước voucher, không phải phần trăm campaign chính thức.

### 8.3. Thống kê trên snapshot mới nhất của 1.157 listing

Dùng snapshot mới nhất để mỗi listing chỉ đóng góp một lần.

| Metric | Country | N | Min | P25 | Median | Mean | P75 | Max | Bằng 0 | > 0 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `discount_percent_analysis` | All | 1.157 | 0,00 | 16,00 | 26,00 | 33,15 | 50,00 | 99,00 | 84 | 1.073 |
| `discount_percent_analysis` | ID | 475 | 0,00 | 40,00 | 53,00 | 49,96 | 63,00 | 99,00 | 57 | 418 |
| `discount_percent_analysis` | VN | 682 | 0,00 | 12,00 | 19,00 | 21,44 | 27,00 | 98,00 | 27 | 655 |
| `promo_percent_derived` | All | 1.157 | 0,00 | 0,00 | 16,00 | 26,06 | 49,03 | 99,99 | 315 | 842 |
| `promo_percent_derived` | ID | 475 | 0,00 | 38,38 | 51,60 | 49,40 | 63,40 | 99,99 | 59 | 416 |
| `promo_percent_derived` | VN | 682 | 0,00 | 0,00 | 5,50 | 9,81 | 15,97 | 97,50 | 256 | 426 |

ID có discount cao hơn VN rất rõ trong mẫu này. Đây mới là thống kê mô tả; không được kết luận discount gây tăng sales vì khác quốc gia, ngành hàng, shop và phân khúc giá.

### 8.4. `promotion_id` là ID chiến dịch hay ID của từng sản phẩm?

**Kết luận ngắn:** `promotion_id` không phải ID sản phẩm và cũng chưa đủ bằng chứng để gọi nó là ID của một chiến dịch marketing cấp cao. Trong dataset này, cách hiểu an toàn nhất là **ID của promotion/offer được gắn vào listing tại một snapshot**.

Evidence từ chính dữ liệu:

| Kiểm tra | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| `promotion_id` khác `0` | 106 ID | Có nhiều promotion/offer khác nhau |
| Dòng có `promotion_id = 0` | 874 | `0` là sentinel, không phải campaign |
| ID `476043307925741` | 155 `item_id`, 300 snapshot | Một ID có thể áp dụng cho nhiều sản phẩm |
| ID `476165261832290` | 92 `item_id`, 210 snapshot | Tiếp tục bác bỏ giả thuyết “mỗi sản phẩm một promo_id” |
| Listing chỉ có 1 promo ID qua các ngày | 589/1.157 | Một phần listing giữ nguyên promotion context |
| Listing có 2 hoặc 3 promo ID qua các ngày | 568/1.157 | Promotion gắn với listing có thể đổi theo snapshot |
| Promo ID khác `0` xuất hiện ở nhiều shop | 14 ID | Không thể giả định ID chỉ thuộc riêng một shop; nếu tính cả sentinel `0` thì có 15 ID |

Quan hệ quan sát được là nhiều-nhiều theo thời gian:

```text
product listing (country_code, shop_id, item_id)
        1 ---- N snapshot theo date
snapshot N ---- 0..1 promotion_id được export
promotion_id 1 ---- N product listing
```

Không dùng `promotion_id` thay cho `item_id`, không group sản phẩm theo `promotion_id`, và không tự suy ra mỗi ID là một campaign quảng cáo. Muốn ánh xạ chính xác sang chiến dịch cần thêm bảng promotion master có ít nhất: tên/type promotion, thời gian bắt đầu-kết thúc, phạm vi shop/item/SKU, cơ chế giảm, bên tài trợ và ngân sách.

Tài liệu công khai không cung cấp schema chính thức đúng với file export này. Tuy vậy, các schema cộng đồng cho thấy Shopee có thể gắn `promotion_id` trong ngữ cảnh item/model offer, còn tài liệu Open API chính thức tách API lấy promotion information khỏi discount detail. Đây chỉ là evidence bổ trợ; kết luận phía trên chủ yếu dựa trên cardinality của dataset: [Shopee Open API guide](https://cdngarenanow-a.akamaihd.net/shopee/seller/seller_cms/b17e7e1846b98c422e4404f223b9f65f/%5BTW%5D%5BOpen%20API%5DAPI%E4%B8%B2%E6%8E%A5%E8%AA%AA%E6%98%8E%E4%BA%8B%E9%A0%85%20%282020_10_21%29_newnew.pdf), [schema tham khảo `shopee-dataset`](https://github.com/rebrowser/shopee-dataset).

### 8.5. `discount_percent` là của promo, voucher hay cả hai?

**Đó là tổng mức giảm từ giá gốc đến `price` cuối được export, nên khi có voucher nó bao gồm cả hiệu ứng voucher và các giảm giá khác đã phản ánh trong giá cuối. Nó không phải promo percent riêng.**

```text
discount_percent ~= 100 * (price_original - price) / price_original
```

Kiểm định tách theo structured voucher:

| Nhóm snapshot | Số dòng | Khớp tổng giảm đến `price` trong sai số 1 điểm % | Khớp phần giảm đến `price_before_promo` |
| --- | ---: | ---: | ---: |
| Có structured voucher | 1.580 | 1.580 (100%) | 0 (0%) |
| Không structured voucher, có `discount_percent` | 1.454 | 1.454 (100%) | 1.287 (88,51%) |

Với 1.580 dòng có voucher, `discount_percent` khớp tổng giảm đến giá cuối nhưng không khớp phần giảm trước bước cuối. Đây là bằng chứng rõ rằng field này **không tách riêng promo khỏi voucher**. Khi không có structured voucher, nó phản ánh direct markdown/promo hiển thị, nhưng dataset vẫn không đủ để quy toàn bộ mức giảm đó cho một campaign cụ thể.

Không tính:

```text
total_discount = discount_percent + voucher_percent
```

vì cách cộng này sẽ đếm voucher hai lần. Nếu cần decomposition phục vụ phân tích, chỉ dùng tên proxy:

```text
pre_final_reduction_proxy = 100 * (price_original - price_before_promo) / price_original
final_step_reduction_proxy = 100 * (price_before_promo - price) / price_original
```

Hai proxy cộng lại thành tổng discount, nhưng không được tự đổi tên `final_step_reduction_proxy` thành “voucher percent”: chỉ 1.011/1.580 dòng có `voucher_discount` khớp chính xác với `price_before_promo - price`.

## 9. Phân tích voucher và các yếu tố liên quan

### 9.1. Voucher trong dataset gồm những field nào?

Không nên dùng một field duy nhất để kết luận “có voucher”. Các field liên quan gồm:

| Field | Vai trò | Cách dùng an toàn |
| --- | --- | --- |
| `voucher_code` | Mã voucher cụ thể | Định danh chương trình/mã ở snapshot; có thể đổi qua ngày |
| `voucher_discount` | Số tiền voucher được ghi nhận | Dùng để đo mức giảm tiền tệ, cùng đơn vị với giá của thị trường |
| `voucher_min_spend` | Mức chi tiêu tối thiểu | Kiểm tra điều kiện áp dụng voucher |
| `voucher_start_time` | Thời điểm bắt đầu | Unix timestamp; kiểm tra voucher có hiệu lực tại snapshot |
| `voucher_end_time` | Thời điểm kết thúc | Unix timestamp; kiểm tra hết hạn |
| `vouchers` | Danh sách nhãn/ưu đãi hiển thị | Không đồng nghĩa với voucher tiền tệ; có cả `Pilih Lokal`, `Add-on Deal`, `Mua để nhận quà`, `Hàng mới về` |
| `vouchers_count` | Số nhãn trong `vouchers` | Đo số badge/label, không phải số mã voucher chắc chắn áp dụng |
| `price_before_promo` | Giá tham chiếu trước phần voucher cuối theo hành vi quan sát | Dùng để kiểm tra quan hệ giá, nhưng tên field nguồn còn mơ hồ |
| `price` | Giá cuối hiển thị | Không trừ voucher thêm lần nữa |
| `discount_percent` | Tổng discount thể hiện từ giá gốc tới giá cuối | Không cộng cơ học với voucher percent |
| `promotion_id` | ID promotion/offer gắn với listing-snapshot | `0` là sentinel; ID khác 0 cũng chưa đủ xác định discount đang có hiệu lực |

Trong audit này, `has_structured_voucher` được định nghĩa bằng:

```text
has_structured_voucher = voucher_discount > 0
```

Ở dữ liệu hiện tại, toàn bộ dòng thỏa điều kiện trên đồng thời có đủ `voucher_code`, `voucher_min_spend`, `voucher_start_time` và `voucher_end_time`. Đây là định nghĩa đáng tin cậy hơn `vouchers_count > 0`.

### 9.2. Mức độ xuất hiện và completeness

#### Toàn bộ 3.341 snapshot

| Country | Snapshot rows | Structured voucher | Tỷ lệ | Có nhãn trong `vouchers` |
| --- | ---: | ---: | ---: | ---: |
| `id` | 1.422 | 0 | 0,00% | 630 |
| `vn` | 1.919 | 1.580 | 82,33% | 1.090 |
| **Tổng** | **3.341** | **1.580** | **47,29%** | **1.720** |

#### Snapshot mới nhất của 1.157 listing

| Country | Listings | Structured voucher | Tỷ lệ | Có nhãn trong `vouchers` |
| --- | ---: | ---: | ---: | ---: |
| `id` | 475 | 0 | 0,00% | 211 |
| `vn` | 682 | 588 | 86,22% | 425 |
| **Tổng** | **1.157** | **588** | **50,82%** | **636** |

Trên snapshot mới nhất:

| Structured voucher | Có nhãn `vouchers` | Listings | Ý nghĩa |
| --- | --- | ---: | --- |
| Có | Có | 380 | Có cả voucher định lượng và badge/label |
| Có | Không | 208 | Có voucher định lượng nhưng danh sách label rỗng |
| Không | Có | 256 | Có badge/ưu đãi, nhưng không có structured monetary voucher |
| Không | Không | 313 | Không có evidence voucher từ hai nhóm field |

Điểm cần thận trọng:

- Không được kết luận “ID không có voucher ngoài thực tế”. Chỉ có thể nói export ID không cung cấp structured voucher trong ba ngày này.
- 211 listing ID vẫn có nhãn ưu đãi, nhưng không có `voucher_code`, số tiền giảm, min spend hoặc thời gian để định lượng.
- `vouchers` không phải bảng voucher chuẩn; đây là tập nhãn UI hỗn hợp.

### 9.3. Giá trị voucher và minimum spend

Thống kê dưới đây dùng snapshot mới nhất để mỗi listing chỉ đóng góp một lần. Cả 588 structured voucher đều thuộc VN và đơn vị tiền là VND.

| Metric | N | Min | P25 | Median | Mean | P75 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `voucher_discount` | 588 | 5.000 | 10.675 | 19.532,5 | 51.531,5 | 75.055 | 665.820 |
| `voucher_min_spend` | 588 | 50.000 | 50.000 | 150.000 | 226.528,9 | 250.000 | 3.000.000 |
| `voucher_discount / price_before_promo` | 588 | - | 10,00% | 11,63% | 12,60% | 15,90% | 22,00% |
| `voucher_discount / price_original` | 588 | - | 9,02% | 10,75% | 11,51% | 14,02% | 22,00% |

Mean cao hơn median vì một số sản phẩm giá trị lớn có voucher vài trăm nghìn đồng. Voucher lớn nhất là 665.820 VND cho listing `vn:1145316676:42232012026`, với minimum spend 3.000.000 VND. Không nên so sánh số tiền voucher tuyệt đối giữa ngành hàng hoặc quốc gia mà không chuẩn hóa theo giá/minimum spend và tiền tệ.

### 9.4. Thời gian hiệu lực

Trong 1.580 snapshot có structured voucher:

- 1.580/1.580 có đủ cả start và end time.
- 1.580/1.580 thỏa `start_time <= end_time`.
- 1.580/1.580 ngày snapshot nằm trong khoảng hiệu lực khi `date` được notebook quy đổi thành timestamp đầu ngày. Vì dataset không có giờ crawl chính xác, đây là kiểm tra ở cấp ngày chứ không phải xác nhận tới từng phút.
- Duration quan sát có bốn mức xấp xỉ: 24 giờ (808 snapshot), 48 giờ (385), 96 giờ (377) và 120 giờ (10).

Các timestamp bắt đầu nằm từ `2026-07-01 00:00` đến `2026-07-03 00:00` theo giờ Việt Nam; thời điểm kết thúc nằm từ `2026-07-01 23:59` đến `2026-07-06 23:59`. Mốc `23:59` giải thích duration kỹ thuật là 23,983 giờ thay vì đúng 24 giờ.

### 9.5. Voucher, minimum spend và giá cuối liên hệ thế nào?

Trên toàn bộ 1.580 snapshot có structured voucher:

- 1.580/1.580 thỏa `price_before_promo >= voucher_min_spend`.
- Có 335 dòng mà `price < voucher_min_spend` sau khi voucher được phản ánh.
- Cả 335 dòng đó đều thỏa `price + voucher_discount >= voucher_min_spend`.

Điều này ủng hộ cách hiểu rằng điều kiện minimum spend được xét trên giá trước phần voucher cuối, còn `price` là giá đã giảm. Vì vậy không được dùng `price` sau giảm để kết luận voucher không đủ điều kiện.

Kiểm tra công thức:

```text
expected_price = price_before_promo - voucher_discount
```

Kết quả:

- Khớp chính xác ở 1.011/1.580 snapshot (63,99%).
- Trên snapshot mới nhất, khớp ở 339/588 listing (57,65%).
- Các dòng còn lại có `price` thấp hơn công thức trên, cho thấy còn thành phần giảm giá khác hoặc logic nguồn không được biểu diễn đầy đủ.

Do đó:

```text
price_final != luôn luôn price_before_promo - voucher_discount
```

Không trừ `voucher_discount` thêm lần nữa khỏi `price`, và không cộng `discount_percent` với voucher rate vì `discount_percent` đã gần như phản ánh tổng chênh lệch từ `price_original` tới `price`.

### 9.6. Voucher và promotion

Phân nhóm trên toàn bộ snapshot bằng `discount_percent > 0` và structured voucher:

| Nhóm | Snapshot rows |
| --- | ---: |
| Promo/discount và structured voucher | 1.580 |
| Promo/discount, không structured voucher | 1.454 |
| Structured voucher, không promo/discount | 0 |
| Không promo/discount và không structured voucher | 307 |

Không có nhóm `voucher_only` trong dữ liệu. Điều này không chứng minh voucher bắt buộc đi cùng một campaign riêng; `discount_percent` là tổng discount hiển thị và `promotion_id` không phải cờ promo hiệu lực. Dataset không tách sạch contribution của promo và voucher để cộng dồn phần trăm.

### 9.7. Voucher có thay đổi giữa các snapshot không?

Trên 2.184 transition listing-snapshot:

| Trạng thái trước | Trạng thái sau | Transitions | Cách hiểu |
| --- | --- | ---: | --- |
| Không voucher | Không voucher | 1.125 | Không có structured voucher ở cả hai snapshot |
| Không voucher | Có voucher | 67 | Voucher xuất hiện |
| Có voucher | Không voucher | 59 | Voucher biến mất/hết hiệu lực hoặc export không còn ghi nhận |
| Có voucher | Có voucher | 933 | Có voucher ở cả hai snapshot |

Trong 933 transition đều có voucher, `voucher_code` đổi ở 798 transition. Ngoài ra, `voucher_discount` đổi ở 796/2.184 transition và minimum spend đổi ở 234/2.184 transition. Voucher vì vậy là thuộc tính theo snapshot, không phải thuộc tính cố định của product listing.

Khi thiết kế data model nên dùng:

```text
voucher_snapshot_key = country_code + shop_id + item_id + date + voucher_code
```

Không gắn một voucher duy nhất vĩnh viễn vào `item_id`.

### 9.8. Voucher có hiệu quả không?

So sánh mô tả trên snapshot mới nhất của riêng VN:

| Structured voucher | Listings | Shops | Median monthly sold | Median price | Median revenue proxy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Không | 94 | 6 | 284,5 | 38.700 | 10.873.500 |
| Có | 588 | 9 | 205,0 | 143.237,5 | 38.776.320 |

Không được đọc bảng này thành “voucher làm sales giảm” hoặc “voucher làm revenue tăng”. Hai nhóm khác mạnh về shop, ngành hàng và mức giá; một số shop có voucher rate 100%, trong khi shop khác bằng 0%. Đây là selection bias/confounding, không phải thử nghiệm causal.

Để đánh giá hiệu quả voucher cần tối thiểu:

- So sánh cùng listing trước/trong/sau voucher với cửa sổ dài hơn.
- Kiểm soát shop, category, giá, ngày chiến dịch và seasonality.
- Có order-level sales hoặc GMV, số lượt redeem và chi phí voucher.
- Phân biệt voucher do shop tài trợ và nền tảng tài trợ.
- Tốt nhất có holdout/control group hoặc thiết kế causal phù hợp.

### 9.9. Feature và rule đề xuất

```text
has_structured_voucher       = voucher_discount_num > 0
has_voucher_label            = vouchers_count > 0
voucher_rate_pre_price       = voucher_discount_num / price_before_promo_num
voucher_rate_original_price  = voucher_discount_num / price_original_num
voucher_threshold_gap        = price_before_promo_num - voucher_min_spend_num
voucher_active_at_snapshot   = voucher_start_time <= snapshot_time <= voucher_end_time
voucher_price_formula_gap    = price_before_promo_num - voucher_discount_num - price_num
voucher_code_changed         = voucher_code != previous_voucher_code
```

Guardrails cho Agent:

1. Nói rõ đang dùng structured voucher hay chỉ dùng nhãn `vouchers`.
2. Không diễn giải thiếu structured fields ở ID thành chắc chắn không có voucher ngoài thực tế.
3. Không trừ voucher hai lần khỏi `price`.
4. Không cộng `discount_percent` và voucher rate như hai phần độc lập.
5. Không kết luận causal effectiveness từ so sánh nhóm quan sát.
6. Khi so sánh số tiền, giữ đúng tiền tệ và chuẩn hóa theo giá/minimum spend.

## 10. Rule dữ liệu đề xuất cho Agent

1. Dùng `product_snapshot_key` để truy xuất evidence và `product_listing_key` để nối chuỗi thời gian.
2. Không gọi `item_id` là SKU; câu trả lời phải dùng “product listing” hoặc “sản phẩm niêm yết”.
3. Chỉ so sánh theo thời gian khi có ít nhất hai snapshot hợp lệ.
4. Gắn `snapshot_gap_flag` nếu ngày ở giữa bị thiếu.
5. Gắn `history_sold_decrease_flag`; không dùng delta âm làm sales.
6. Không lấy diff của `monthly_sold_value` làm daily sales.
7. Dùng `discount_percent_analysis` sau rule fill 0 có điều kiện.
8. Giữ `promo_percent_derived` là feature suy diễn; không trình bày như field gốc hay campaign uplift.
9. Không deduplicate theo `product_name`.
10. Khi trả lời nguyên nhân sales giảm, nêu rõ chỉ có ba snapshot và dữ liệu sales là proxy hiển thị, không phải transaction log.

## 11. Giới hạn cần bổ sung dữ liệu

Để trả lời chắc chắn ở cấp SKU và promotion, cần thêm:

- `sku_id` hoặc `model_id` cho từng variation.
- Giá, tồn kho và sales theo SKU/ngày.
- Crawl timestamp và crawl status/log cho từng request.
- Order hoặc transaction-level sales.
- Campaign start/end, eligibility, cost/funding và nhóm đối chứng.
- Tài liệu nguồn giải thích chính xác `history_sold_value`, `monthly_sold_value`, `price_before_promo` và `promotion_id`.

Cho tới khi có các trường trên, kết quả trong báo cáo là data audit và descriptive evidence, không phải causal conclusion.
