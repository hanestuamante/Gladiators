# Documentation

## 1. Bối cảnh dataset

Dataset này là dữ liệu Shopee được thu thập cho 2 thị trường:

- `vn`: Việt Nam
- `id`: Indonesia

Dữ liệu trong `Dataset/` được chia làm 2 phần rõ ràng:

- `Dataset/DataRaw`: dữ liệu gốc, giữ nguyên cấu trúc CSV ban đầu.
- `Dataset/DataProcessed`: dữ liệu đã được preprocessing, dùng trực tiếp cho phân tích.

Dữ liệu gốc nằm trong thư mục `Dataset/DataRaw` theo cấu trúc phân vùng:

```text
Dataset/DataRaw/
  country_code=<vn|id>/
    dataset=<dataset_name>/
      shop_id=<shop_id>/
        <dataset_name>.csv
```

Riêng `category_platform` không có `shop_id` vì đây là taxonomy cấp nền tảng, dùng chung theo từng quốc gia.

Dataset bao gồm 20 shop, mỗi quốc gia có 10 shop. Các bảng có dữ liệu snapshot theo ngày chủ yếu từ `2026-07-01` đến `2026-07-03`; riêng `shop_info` chỉ có snapshot ngày `2026-07-03`.

## 2. Tổng quan bảng gốc

| Bảng | Số file | Dòng raw | Dòng sau preprocessing | Mô tả |
| --- | ---: | ---: | ---: | --- |
| `products` | 20 | 3,371 | 3,341 | Thông tin sản phẩm theo shop và ngày snapshot |
| `shop_info` | 20 | 20 | 20 | Thông tin tổng quan mỗi shop |
| `category_list` | 20 | 491 | 491 | Danh mục nội bộ do shop tự tạo |
| `product_categories` | 20 | 4,054 | 4,054 | Mapping sản phẩm với danh mục nội bộ của shop |
| `category_platform` | 2 | 4,482 | 4,482 | Taxonomy danh mục Shopee theo quốc gia |

Tổng cộng có 82 file CSV gốc. Không phát hiện mismatch giữa `country_code`/`shop_id` trong đường dẫn và nội dung CSV.

## 3. Ý nghĩa từng bảng

### `products`

Đây là bảng trung tâm cho phân tích sản phẩm. Mỗi dòng đại diện cho một sản phẩm trong một shop tại một ngày snapshot.

Khóa logic sau preprocessing:

```text
country_code + shop_id + item_id + date
```

Nhóm cột quan trọng:

- Định danh: `platform`, `country_code`, `date`, `shop_id`, `shop_slug`, `shop_name`, `item_id`
- Nội dung sản phẩm: `product_name`, `url`, `image_url`, `images`, `brand`, `brand_id`
- Trạng thái: `is_ad`, `is_sold_out`, `shopee_verified`, `seller_flag`
- Giá và khuyến mãi: `price`, `price_original`, `price_before_promo`, `discount_percent`, `voucher_*`
- Hiệu suất bán hàng: `history_sold_value`, `monthly_sold_value`, `liked_count`
- Đánh giá: `rating`, `rating_count`, `rating_count_detail`
- Danh mục nền tảng: `catid`, `global_catids`
- Biến thể: `tier_variation_name`, `tier_variation_options`

Ý nghĩa từng cột gốc trong `products.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `platform` | Nền tảng thương mại điện tử; trong dataset này là `Shopee`. |
| `key` | Khóa/ngữ cảnh crawl hoặc API nếu có; hiện phần lớn để trống. |
| `country_code` | Mã quốc gia của dữ liệu, gồm `vn` hoặc `id`. |
| `date` | Ngày snapshot/crawl dữ liệu sản phẩm. |
| `shop_id` | ID định danh duy nhất của shop trên Shopee. |
| `shop_slug` | Slug/tên định danh shop dùng trong URL hoặc profile. |
| `shop_name` | Tên hiển thị của shop. |
| `location` | Khu vực/địa điểm shop hoặc nơi bán hiển thị trên Shopee. |
| `item_id` | ID định danh duy nhất của sản phẩm trong shop. |
| `product_name` | Tên sản phẩm hiển thị trên Shopee. |
| `url` | URL trang chi tiết sản phẩm. |
| `image_url` | URL ảnh đại diện/chính của sản phẩm. |
| `images` | Danh sách URL ảnh sản phẩm, lưu dưới dạng JSON array. |
| `seller_flag` | Nhãn/trạng thái của seller, ví dụ `OFFICIAL_SHOP`, lưu dạng JSON array. |
| `seller_flag_hash` | Mã hash tương ứng với các seller flag, nếu nguồn dữ liệu cung cấp. |
| `image_overlay` | Nhãn overlay hiển thị trên ảnh sản phẩm, nếu có. |
| `image_overlay_hash` | Mã hash tương ứng với overlay ảnh, nếu có. |
| `is_ad` | Cho biết sản phẩm có phải listing quảng cáo hay không. |
| `is_sold_out` | Cho biết sản phẩm đã hết hàng hay chưa. |
| `shopee_verified` | Cho biết sản phẩm/shop có trạng thái Shopee verified hay không. |
| `ctime` | Thời điểm tạo sản phẩm trên hệ thống Shopee, thường là Unix timestamp. |
| `price` | Giá bán hiện tại tại thời điểm snapshot. |
| `price_original` | Giá gốc/giá niêm yết trước giảm giá. |
| `price_before_promo` | Giá trước khi áp dụng chương trình khuyến mãi. |
| `discount_percent` | Phần trăm giảm giá đang hiển thị. |
| `promotion_id` | ID chương trình khuyến mãi liên quan, nếu có. |
| `voucher_code` | Mã voucher áp dụng/hiển thị cho sản phẩm, nếu có. |
| `voucher_discount` | Giá trị giảm từ voucher, nếu có. |
| `voucher_start_time` | Thời điểm bắt đầu voucher, thường là Unix timestamp nếu có dữ liệu. |
| `voucher_end_time` | Thời điểm kết thúc voucher, thường là Unix timestamp nếu có dữ liệu. |
| `voucher_min_spend` | Giá trị đơn hàng tối thiểu để dùng voucher, nếu có. |
| `history_sold_value` | Tổng số lượng đã bán tích lũy theo Shopee hiển thị. |
| `monthly_sold_value` | Số lượng đã bán trong tháng/giai đoạn gần nhất theo Shopee hiển thị. |
| `rating` | Điểm đánh giá trung bình của sản phẩm. |
| `rating_count` | Tổng số lượt đánh giá của sản phẩm. |
| `rating_count_detail` | Phân bố số đánh giá theo từng mức sao, lưu dạng JSON array. |
| `vouchers` | Danh sách voucher/nhãn ưu đãi liên quan đến sản phẩm, lưu dạng JSON array. |
| `brand` | Tên thương hiệu của sản phẩm, nếu có. |
| `brand_id` | ID thương hiệu trên Shopee, nếu có. |
| `catid` | ID danh mục nền tảng chính của sản phẩm trên Shopee. |
| `global_catids` | Đường dẫn danh mục nền tảng từ cha đến con, lưu dạng JSON array. |
| `liked_count` | Số lượt thích sản phẩm. |
| `tier_variation_name` | Tên nhóm biến thể, ví dụ màu, size, phân loại. |
| `tier_variation_options` | Danh sách lựa chọn biến thể, lưu dạng JSON array. |

Lưu ý chất lượng:

- Có 30 dòng sản phẩm bị lặp y hệt trong dữ liệu raw; preprocessing đã loại bỏ.
- `is_sold_out` và `is_ad` đều là `False` cho toàn bộ 3,341 dòng sau preprocessing.
- `shopee_verified` có 585 dòng `True` và 2,756 dòng `False`.
- Có 3 dòng có `price = 999999999`, nên xem là outlier/sentinel trước khi phân tích giá.

#### Giải thích thêm các biến dễ nhầm

`monthly_sold_value`

- Ý nghĩa trong dataset: số lượng đã bán trong giai đoạn gần đây do Shopee hiển thị tại thời điểm snapshot.
- Tên biến là `monthly_sold_value`, nên có thể hiểu theo cách Shopee thường hiển thị là lượng bán trong khoảng tháng gần nhất/gần đây.
- Tuy nhiên, dataset hiện không có metadata crawl/API nói rõ “monthly” chính xác là 30 ngày gần nhất, tháng dương lịch, hay một cửa sổ rolling khác. Vì vậy trong phân tích nên mô tả thận trọng là “lượt bán gần đây/theo tháng hiển thị bởi Shopee”, không khẳng định chính xác là bao nhiêu ngày nếu chưa có tài liệu nguồn crawl.
- Nếu cần tính trend, lưu ý dataset chỉ có snapshot từ `2026-07-01` đến `2026-07-03`; biến này là chỉ số Shopee đã tổng hợp sẵn, không phải số bán phát sinh riêng trong từng ngày snapshot.

`discount_percent`, `promotion_id` và nhóm `voucher_*`

- `discount_percent`/`promotion_id` mô tả ưu đãi giảm giá trực tiếp ở listing sản phẩm. Thường phần này đã phản ánh vào các cột giá như `price`, `price_original`, `price_before_promo`.
- Nhóm `voucher_*` gồm `voucher_code`, `voucher_discount`, `voucher_start_time`, `voucher_end_time`, `voucher_min_spend`; đây là ưu đãi dạng voucher/coupon, thường có điều kiện riêng như mã, thời hạn và đơn tối thiểu.
- Hai loại ưu đãi này khác nhau: promo là giảm giá ở cấp listing/chương trình sản phẩm, voucher là mã/ưu đãi có điều kiện có thể áp dụng thêm khi mua.
- Không nên tự cộng `discount_percent` với `voucher_discount` một cách cơ học để ra “tổng giảm giá cuối cùng”. Lý do là `price` trong dataset này đã có dấu hiệu là giá cuối hiển thị sau khi áp dụng voucher; cộng/trừ thêm lần nữa sẽ dễ double count.
- Cách dùng an toàn: coi `price` là giá bán hiện tại sau khi hệ thống đã phản ánh voucher/promo hiển thị; dùng `price_before_promo`, `discount_percent`, `voucher_discount` để giải thích các thành phần giảm giá.

Kiểm tra thực tế trong dataset:

- Có 1,016 dòng vừa có promo (`discount_percent` + `promotion_id`) vừa có voucher (`voucher_discount`).
- Trong 641/1,016 dòng, công thức `price = price_before_promo - voucher_discount` khớp chính xác. Điều này cho thấy ở nhiều dòng, `price` đã phản ánh cả voucher, không chỉ riêng promo.
- Trong 375/1,016 dòng còn lại, công thức trên không khớp hoàn toàn. Nguyên nhân có thể là rule giảm giá khác, rounding, quà tặng/ưu đãi bổ sung, hoặc logic Shopee không được biểu diễn đầy đủ trong các cột hiện có.
- Có 1,610 dòng có `voucher_min_spend`; không có dòng nào thật sự không thỏa điều kiện nếu xét theo giá trước voucher. Cụ thể, `price_before_promo >= voucher_min_spend` ở toàn bộ 1,610 dòng. Với 335 dòng có `price < voucher_min_spend`, tất cả đều thỏa `price + voucher_discount >= voucher_min_spend`, cho thấy `price` đã là giá sau khi voucher được trừ.

Ví dụ khớp:

```text
Sản phẩm: [GIAO NHANH] [Mua 3 Tặng 1 Quạt] Bánh Yến mạch Richy Oatmeal Túi 250g New
price_original      = 75,000
price_before_promo = 51,000
voucher_discount   = 6,120
price              = 44,880

51,000 - 6,120 = 44,880
```

Ví dụ không khớp:

```text
Sản phẩm: Combo 3 túi bánh quy mỏng giòn Kenju Richy 192g/túi 2 vị rau củ
price_original      = 180,000
price_before_promo = 136,000
voucher_discount   = 13,100
price              = 117,900

136,000 - 13,100 = 122,900
```

Trong ví dụ không khớp, `price` thấp hơn kết quả tính tay 5,000. Vì vậy, khi modeling/phân tích, nên kết luận `price` là giá cuối hiển thị sau khi đã phản ánh voucher/promo trong dataset; các cột promo/voucher dùng để giải thích thành phần giảm giá, không nhất thiết tái tạo được đầy đủ giá cuối.

`is_ad`

- `is_ad` cho biết sản phẩm/listing có được đánh dấu là quảng cáo/sponsored placement tại thời điểm crawl hay không.
- `True` nghĩa là sản phẩm xuất hiện trong ngữ cảnh quảng cáo theo nguồn dữ liệu crawl; `False` nghĩa là không có dấu hiệu quảng cáo ở snapshot đó.
- Trong dataset đã xử lý hiện tại, toàn bộ 3,341 dòng đều có `is_ad = False`, nên biến này không có khả năng phân tách nhóm quảng cáo và không quảng cáo trong bộ dữ liệu hiện có.
- Không nên diễn giải `is_ad = False` là shop không bao giờ chạy quảng cáo; nó chỉ nói rằng các dòng trong snapshot này không được ghi nhận là quảng cáo.

`tier_variation_options`

- Đây là danh sách các lựa chọn biến thể của sản phẩm, lưu dưới dạng JSON array.
- Biến này đi cùng `tier_variation_name`. Ví dụ `tier_variation_name = "Mùi vị"` thì `tier_variation_options` có thể là danh sách các vị; `tier_variation_name = "Combo"` thì options có thể là các gói combo; `tier_variation_name = "Hàng"` thì options có thể là `Chính hãng`, `Khuyến mãi`, `Combo`.
- Giá trị `[""]` nghĩa là nguồn dữ liệu vẫn lưu field variation nhưng sản phẩm gần như không có lựa chọn biến thể rõ ràng.
- Trong preprocessing, cột `tier_variation_options_count` đếm số phần tử trong danh sách này. Cột đếm này hữu ích để phân biệt sản phẩm không có biến thể, có một biến thể, hoặc có nhiều lựa chọn.
- Không nên coi mỗi option là một SKU riêng nếu chưa có bảng variant/SKU chi tiết; dataset này chỉ cho biết danh sách lựa chọn biến thể hiển thị ở cấp sản phẩm.

### `shop_info`

Mỗi shop có 1 dòng thông tin tổng quan.

Khóa logic:

```text
country_code + shop_id
```

Nhóm cột quan trọng:

- Định danh: `shop_id`, `shop_name`, `username`, `country_code`, `date`
- Uy tín shop: `rating_star`, `follower_count`, `is_official_shop`
- Quy mô: `item_count`
- Vận hành: `response_rate`, `response_time`, `cancellation_rate`, `vacation`
- Đánh giá chi tiết: `rating_good`, `rating_normal`, `rating_bad`
- Thời điểm tạo shop: `created_at`

Ý nghĩa từng cột gốc trong `shop_info.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `shop_id` | ID định danh duy nhất của shop trên Shopee. |
| `shop_name` | Tên hiển thị của shop. |
| `username` | Username/slug tài khoản shop trên Shopee. |
| `rating_star` | Điểm đánh giá trung bình của shop. |
| `follower_count` | Số người theo dõi shop. |
| `item_count` | Số lượng sản phẩm/listing shop đang có theo nguồn dữ liệu. |
| `is_official_shop` | Cho biết shop có phải Official Shop/Shopee Mall/nhãn chính hãng theo nguồn dữ liệu hay không. |
| `response_rate` | Tỷ lệ phản hồi chat/tin nhắn của shop, thường tính theo phần trăm. |
| `response_time` | Thời gian phản hồi trung bình của shop theo Shopee; đơn vị chính xác không được mô tả trong dataset, nên dùng như chỉ số vận hành tương đối. |
| `rating_good` | Số lượng đánh giá tốt của shop. |
| `rating_normal` | Số lượng đánh giá trung bình/bình thường của shop. |
| `rating_bad` | Số lượng đánh giá xấu của shop. |
| `cancellation_rate` | Tỷ lệ hủy đơn của shop theo nguồn dữ liệu. |
| `created_at` | Thời điểm tạo shop/tài khoản shop, định dạng timestamp ISO. |
| `vacation` | Cho biết shop có đang bật chế độ nghỉ/bảo trì/vacation mode hay không. |
| `country_code` | Mã quốc gia của shop, gồm `vn` hoặc `id`. |
| `date` | Ngày snapshot/crawl thông tin shop. |

### `category_list`

Danh mục nội bộ của từng shop, thường dùng để nhóm sản phẩm theo logic riêng của shop.

Hiểu đơn giản: `category_list` giống như các “kệ hàng” hoặc “gian trưng bày” do chính shop tự sắp xếp bên trong trang shop. Ví dụ một shop bánh kẹo có thể tạo các kệ như `Bánh quy`, `Kẹo`, `Combo tiết kiệm`, `Hàng bán chạy`, `Khuyến mãi hôm nay`. Người mua vào trang shop sẽ dùng các kệ này để tìm sản phẩm nhanh hơn.

`category_list` khác với `category_platform`:

- `category_platform`: danh mục chuẩn của Shopee, dùng toàn sàn, ví dụ ngành hàng lớn như thực phẩm, làm đẹp, quần áo.
- `category_list`: danh mục riêng của từng shop, do shop tự đặt tên và tự nhóm sản phẩm.

Vì vậy, `category_list` không trực tiếp là doanh thu, nhưng có thể tác động gián tiếp tới doanh thu thông qua cách shop tổ chức trải nghiệm mua hàng:

- Giúp khách tìm sản phẩm nhanh hơn: danh mục rõ ràng làm giảm thời gian tìm kiếm, tăng khả năng thêm vào giỏ.
- Đẩy sản phẩm chiến lược: shop có thể tạo danh mục như `Best Seller`, `Combo`, `Flash Sale`, `Mua 2 giảm thêm` để kéo sự chú ý vào nhóm sản phẩm muốn bán.
- Tăng cross-sell/bundle: các danh mục `Combo`, `Set quà`, `Mua kèm` có thể làm tăng giá trị đơn hàng.
- Phản ánh chiến lược merchandising: danh mục nào có nhiều sản phẩm, tên nổi bật, có ảnh riêng hoặc nằm ở cấp cha có thể là nhóm shop muốn ưu tiên.
- Là tín hiệu để phân tích doanh thu theo “kệ hàng”: khi join `product_categories` với `products`, có thể tính tổng/ước tính doanh thu theo từng `display_name`.

Trong dataset này, muốn phân tích tác động tới doanh thu thì không dùng riêng `category_list`, mà cần join:

```text
category_list
  -> product_categories
  -> products
```

Sau khi join, có thể tạo các chỉ số theo từng danh mục nội bộ:

- Số sản phẩm trong danh mục: dùng `total` hoặc đếm `item_id`.
- Lượt bán gần đây: tổng `monthly_sold_value`.
- Doanh thu ước tính gần đây: `sum(price * monthly_sold_value)`.
- Giá trung bình: trung bình `price`.
- Rating trung bình: trung bình `rating`.
- Tỷ trọng sản phẩm có voucher/promo trong danh mục.

Lưu ý quan trọng: nếu một sản phẩm nằm trong nhiều danh mục nội bộ, khi tính doanh thu theo danh mục có thể bị double count. Khi cần tính tổng doanh thu toàn shop, nên deduplicate theo `country_code + shop_id + item_id + date`; khi cần so sánh hiệu quả từng danh mục, có thể chấp nhận việc một sản phẩm được tính vào nhiều danh mục nếu mục tiêu là đo “độ phủ/trưng bày” của danh mục.

Khóa logic:

```text
country_code + shop_id + shop_category_id + date
```

Cột chính:

- `shop_id`
- `shop_category_id`
- `display_name`
- `total`
- `is_parent_category`
- `is_sub_category`
- `parent_shop_category_id`
- `image`
- `category_type`
- `country_code`
- `date`

Ý nghĩa từng cột gốc trong `category_list.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `shop_id` | ID shop sở hữu danh mục nội bộ này. |
| `shop_category_id` | ID danh mục nội bộ do shop tạo/hiển thị. |
| `display_name` | Tên danh mục hiển thị trên trang shop. |
| `total` | Số sản phẩm thuộc danh mục theo Shopee hiển thị tại snapshot. |
| `is_parent_category` | Cho biết danh mục này là danh mục cha hay không. |
| `is_sub_category` | Cho biết danh mục này là danh mục con hay không. |
| `parent_shop_category_id` | ID danh mục cha nếu danh mục hiện tại là danh mục con; để trống nếu không có. |
| `image` | Mã/đường dẫn ảnh đại diện của danh mục nếu có. |
| `category_type` | Loại danh mục nội bộ theo mã của Shopee/nguồn crawl. Dataset không có bảng giải mã chi tiết cho trường này. |
| `country_code` | Mã quốc gia của shop/danh mục, gồm `vn` hoặc `id`. |
| `date` | Ngày snapshot/crawl danh mục shop. |

### `product_categories`

Mapping giữa sản phẩm và danh mục nội bộ shop.

Hiểu đơn giản: `product_categories` là bảng “sản phẩm nào đang nằm trên kệ nào”. Nếu `category_list` là danh sách các kệ hàng của shop, thì `product_categories` là bảng nối sản phẩm vào từng kệ.

Ví dụ:

```text
Sản phẩm A -> danh mục "Combo tiết kiệm"
Sản phẩm A -> danh mục "Bán chạy"
Sản phẩm B -> danh mục "Bánh quy"
```

Một sản phẩm có thể nằm trong nhiều danh mục nội bộ cùng lúc. Điều này giống một món hàng trong siêu thị có thể vừa nằm ở kệ `Bánh quy`, vừa được đặt thêm ở khu `Khuyến mãi`.

Vai trò với phân tích doanh thu:

- Bảng này giúp gắn doanh thu/lượt bán của từng sản phẩm về từng danh mục nội bộ shop.
- Không có bảng này thì `category_list` chỉ cho biết shop có những kệ nào, nhưng không biết sản phẩm cụ thể nào nằm trong kệ đó.
- Khi join với `products`, có thể tính danh mục nào đang tạo nhiều lượt bán hoặc doanh thu ước tính nhất.
- Có thể phát hiện shop đang ưu tiên nhóm nào: ví dụ danh mục `Combo`, `Best Seller`, `Flash Sale` có nhiều sản phẩm bán tốt hay không.
- Có thể so sánh cách đặt sản phẩm vào danh mục giữa các shop: shop nào dùng nhiều danh mục khuyến mãi/combo hơn, shop nào sắp xếp ít nhưng tập trung hơn.

Cách dùng để phân tích:

```text
product_categories.item_id
  -> products.item_id

product_categories.category_id
  -> category_list.shop_category_id
```

Sau khi join, có thể tạo chỉ số theo danh mục:

- `sum(monthly_sold_value)`: tổng lượt bán gần đây của các sản phẩm trong danh mục.
- `sum(price * monthly_sold_value)`: doanh thu ước tính gần đây của danh mục.
- `avg(price)`: mức giá trung bình của sản phẩm trong danh mục.
- `count(distinct item_id)`: số sản phẩm khác nhau trong danh mục.
- `avg(rating)`: chất lượng/đánh giá trung bình của nhóm sản phẩm.

Lưu ý double count: nếu một sản phẩm nằm trong 2 danh mục, doanh thu của sản phẩm đó sẽ xuất hiện ở cả 2 danh mục khi phân tích theo danh mục. Đây không hẳn là lỗi nếu mục tiêu là phân tích hiệu quả từng “kệ trưng bày”, nhưng không nên cộng các danh mục lại để ra tổng doanh thu toàn shop nếu chưa deduplicate sản phẩm.

Khóa logic:

```text
country_code + shop_id + item_id + category_id + date
```

Cột chính:

- `shop_id`
- `date`
- `item_id`
- `category_slug`
- `category_id`
- `country_code` được bổ sung từ đường dẫn trong preprocessing

`category_id` ở bảng này map được với `category_list.shop_category_id`.

Ý nghĩa từng cột gốc trong `product_categories.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `shop_id` | ID shop chứa sản phẩm. |
| `date` | Ngày snapshot/crawl mapping sản phẩm-danh mục. |
| `item_id` | ID sản phẩm trên Shopee. |
| `category_slug` | Slug hoặc ID dạng text của danh mục nội bộ shop; trong dataset này thường trùng với `category_id`. |
| `category_id` | ID danh mục nội bộ shop mà sản phẩm thuộc về; dùng để join với `category_list.shop_category_id`. |

Lưu ý: file gốc `product_categories.csv` không có cột `country_code`; preprocessing bổ sung cột này từ đường dẫn `Dataset/DataRaw/country_code=<...>`.

### `category_platform`

Taxonomy danh mục của Shopee theo quốc gia. Bảng này không gắn với shop cụ thể.

Hiểu đơn giản: `category_platform` là “bản đồ ngành hàng chính thức” của Shopee. Đây là hệ thống phân loại dùng chung toàn sàn, không phải danh mục tự tạo của từng shop.

Ví dụ với Shopee, một sản phẩm có thể thuộc cây danh mục như:

```text
Food & Beverages
  -> Snacks
    -> Biscuits / Candy / Chocolate
```

Trong khi `category_list` là cách shop tự đặt kệ, `category_platform` là cách Shopee hiểu sản phẩm thuộc ngành hàng nào trên toàn nền tảng.

Vai trò với phân tích doanh thu:

- Giúp so sánh sản phẩm/shop theo ngành hàng chuẩn, thay vì chỉ theo danh mục tự đặt của từng shop.
- Cho phép gom sản phẩm của nhiều shop vào cùng một nhóm ngành để so sánh công bằng hơn.
- Hữu ích khi phân tích thị trường: ngành hàng nào có nhiều sản phẩm, giá cao/thấp, rating tốt, lượt bán cao.
- Giúp chuẩn hóa dữ liệu giữa các shop vì mỗi shop có thể đặt tên danh mục nội bộ khác nhau, nhưng taxonomy nền tảng có cấu trúc chung.
- Có thể dùng để phân tích cấp cha/cấp con: ví dụ so sánh ngành lớn `Food & Beverages` với nhóm nhỏ hơn như `Biscuits` hoặc `Candy`.

Cách dùng với bảng `products`:

```text
products.catid
  -> category_platform.category_id

products.global_catids
  -> chuỗi category_id từ danh mục cha đến danh mục con
```

Ví dụ, nếu `global_catids = [100629, 100646, 100794]`, có thể hiểu đây là đường dẫn danh mục từ cấp lớn đến cấp nhỏ. Muốn đọc tên từng cấp thì map từng ID trong `global_catids` sang `category_platform.category_id`.

Tác động tới doanh thu thường là gián tiếp:

- Ngành hàng đúng giúp sản phẩm xuất hiện ở đúng nơi khách tìm kiếm.
- Category nền tảng ảnh hưởng tới browsing/search/filter trên Shopee.
- Sản phẩm bị đặt sai ngành có thể khó được khách phù hợp tìm thấy hơn.
- Khi phân tích doanh thu, category nền tảng giúp biết doanh thu đến từ ngành nào, không chỉ từ shop nào.

Khác biệt quan trọng:

- `category_platform` trả lời câu hỏi: “Sản phẩm này thuộc ngành hàng nào trên Shopee?”
- `category_list` trả lời câu hỏi: “Shop đang trưng bày sản phẩm này ở kệ nào trong trang shop?”
- `product_categories` trả lời câu hỏi: “Sản phẩm nào được gắn vào kệ nội bộ nào của shop?”

Khóa logic:

```text
path_country_code + category_id
```

Cột chính:

- `platform`
- `client`
- `key`
- `category_id`
- `parent_category_id`
- `original_category_name`
- `display_category_name`
- `has_children`
- `debug_message`

Ý nghĩa từng cột gốc trong `category_platform.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `platform` | Nền tảng thương mại điện tử; trong dataset này là `Shopee`. |
| `client` | Mã client/nguồn gọi API hoặc ngữ cảnh crawl danh mục. |
| `key` | Tên tác vụ/API liên quan đến taxonomy; trong dataset này thường là `get_category`. |
| `category_id` | ID danh mục nền tảng của Shopee. |
| `parent_category_id` | ID danh mục cha; giá trị `0` thường biểu thị danh mục cấp gốc. |
| `original_category_name` | Tên danh mục gốc, thường bằng tiếng Anh hoặc tên chuẩn từ nguồn taxonomy. |
| `display_category_name` | Tên danh mục hiển thị theo thị trường/quốc gia, ví dụ tiếng Việt hoặc tiếng Indonesia. |
| `has_children` | Cho biết danh mục này còn danh mục con hay không. |
| `debug_message` | Thông tin debug/thông báo từ nguồn crawl/API nếu có; đa số có thể để trống. |

Lưu ý: file gốc `category_platform.csv` không có cột `country_code`; preprocessing lưu quốc gia vào `path_country_code` lấy từ đường dẫn.

# Giải thích về sự khác nhau giữa category_platform.category_id, category_list.shop_category_id, product_categories.category_id

Ba cột này dễ nhầm vì đều có chữ `category_id`, nhưng chúng thuộc **hai hệ danh mục khác nhau**:

```text
1. Hệ danh mục chuẩn của Shopee toàn sàn
   -> category_platform.category_id
   -> products.catid / products.global_catids

2. Hệ danh mục/kệ nội bộ do từng shop tự tạo
   -> category_list.shop_category_id
   -> product_categories.category_id
```

## 3.1. `category_platform.category_id`: ID ngành hàng chuẩn của Shopee

`category_platform.category_id` là ID trong hệ thống phân loại chính thức của Shopee. Hệ này dùng chung trên toàn sàn, không phụ thuộc vào shop nào.

Ví dụ logic:

```text
100629 = Food & Beverages
100646 = Snacks
100794 = Biscuits / Candy / Chocolate
```

Cột này trả lời câu hỏi:

```text
Sản phẩm này thuộc ngành hàng chuẩn nào trên Shopee?
```

Trong bảng `products`, hệ ID này nằm ở:

```text
products.catid
products.global_catids
```

Join đúng:

```text
products.country_code = category_platform.path_country_code
products.catid        = category_platform.category_id
```

Hoặc nếu muốn đọc đầy đủ cây danh mục, parse từng ID trong `products.global_catids` rồi map từng ID đó sang:

```text
category_platform.category_id
```

Ví dụ:

```text
products.global_catids = [100629, 100646, 100794]

100629 -> Food & Beverages
100646 -> Snacks
100794 -> Biscuits / Candy / Chocolate
```

Ý nghĩa phân tích:

- Dùng để so sánh ngành hàng giữa nhiều shop.
- Dùng để phân tích doanh thu theo taxonomy chuẩn của Shopee.
- Dùng để gom sản phẩm cùng ngành, dù mỗi shop tự đặt tên danh mục nội bộ khác nhau.

## 3.2. `category_list.shop_category_id`: ID kệ/danh mục nội bộ của shop

`category_list.shop_category_id` là ID của danh mục do **chính shop tự tạo** trong trang shop.

Nó giống như “kệ hàng” trong cửa hàng:

```text
Best Seller
Combo tiết kiệm
Bánh quy
Flash Sale
Hàng mới
Quà tặng
```

Cột này trả lời câu hỏi:

```text
Shop này có những kệ/danh mục nội bộ nào?
```

Điểm quan trọng:

- ID này chỉ có ý nghĩa trong phạm vi shop.
- Hai shop khác nhau có thể có `shop_category_id` giống nhau về mặt số, nhưng không nên coi là cùng một danh mục nếu khác `shop_id`.
- Vì vậy khi join luôn phải dùng kèm `shop_id`, `country_code`, và thường cả `date`.

Khóa đúng của một danh mục nội bộ shop:

```text
country_code + shop_id + shop_category_id + date
```

Ý nghĩa phân tích:

- Dùng để biết shop đang trưng bày sản phẩm theo kệ nào.
- Dùng để phân tích kệ nào có nhiều sản phẩm, kệ nào tạo doanh thu ước tính cao.
- Dùng để hiểu chiến lược merchandising của shop.

## 3.3. `product_categories.category_id`: ID kệ nội bộ mà sản phẩm được gắn vào

Tên cột này gây nhầm nhất. Trong dataset này, `product_categories.category_id` **không phải** ID ngành hàng chuẩn của Shopee.

Nó là ID danh mục/kệ nội bộ shop mà sản phẩm được gắn vào, nên nó map với:

```text
category_list.shop_category_id
```

`product_categories` trả lời câu hỏi:

```text
Sản phẩm nào được đặt vào kệ nội bộ nào của shop?
```

Join đúng:

```text
product_categories.country_code = category_list.country_code
product_categories.shop_id      = category_list.shop_id
product_categories.category_id  = category_list.shop_category_id
product_categories.date         = category_list.date
```

Ví dụ logic:

```text
product_categories:
item_id = 123
category_id = 555

category_list:
shop_category_id = 555
display_name = "Combo tiết kiệm"

Kết luận:
Sản phẩm 123 đang nằm trong kệ "Combo tiết kiệm" của shop đó.
```

Một sản phẩm có thể xuất hiện ở nhiều dòng trong `product_categories`, nghĩa là nó được đặt vào nhiều kệ nội bộ cùng lúc.

Ví dụ:

```text
item_id = 123 -> category_id = 555 -> Combo tiết kiệm
item_id = 123 -> category_id = 777 -> Best Seller
```

Điều này không mâu thuẫn. Nó giống một sản phẩm trong siêu thị vừa nằm ở kệ chính, vừa được đặt ở khu khuyến mãi.

## 3.4. Không join nhầm hai hệ category

Không nên join:

```text
product_categories.category_id = category_platform.category_id
```

Lý do: hai cột này thuộc hai hệ ID khác nhau.

| Cột | Hệ danh mục | Ý nghĩa | Join đúng với |
| --- | --- | --- | --- |
| `category_platform.category_id` | Danh mục chuẩn Shopee | Ngành hàng toàn sàn | `products.catid` hoặc từng ID trong `products.global_catids` |
| `category_list.shop_category_id` | Danh mục nội bộ shop | Kệ/danh mục shop tự tạo | `product_categories.category_id` |
| `product_categories.category_id` | Danh mục nội bộ shop | Kệ mà sản phẩm được gắn vào | `category_list.shop_category_id` |

## 3.5. Ví dụ dễ nhớ

Giả sử có một sản phẩm bánh Oreo.

Trong hệ Shopee platform:

```text
products.catid = 100794
category_platform.category_id = 100794
display_category_name = "Bánh quy / Kẹo / Chocolate"
```

Điều này nói rằng:

```text
Oreo thuộc ngành hàng chuẩn "Bánh quy / Kẹo / Chocolate" trên Shopee.
```

Trong hệ shop nội bộ:

```text
product_categories.category_id = 555
category_list.shop_category_id = 555
category_list.display_name = "Combo tiết kiệm"
```

Điều này nói rằng:

```text
Shop đang đặt sản phẩm Oreo vào kệ "Combo tiết kiệm".
```

Cùng một sản phẩm có thể đồng thời có:

```text
Shopee category: Bánh quy / Kẹo / Chocolate
Shop category: Combo tiết kiệm, Best Seller, Flash Sale
```

Hai lớp category này phục vụ hai mục đích khác nhau:

- Shopee category giúp khách tìm sản phẩm theo ngành hàng toàn sàn.
- Shop category giúp shop trưng bày sản phẩm trong trang shop của riêng họ.

## 4. Quan hệ giữa các bảng

### Cách nhìn tổng thể

Trong dataset này, bảng trung tâm là `products`. Mỗi dòng trong `products` là một sản phẩm tại một shop trong một ngày snapshot. Các bảng còn lại bổ sung thêm ngữ cảnh cho sản phẩm đó:

```text
shop_info
  cho biết shop là ai, uy tín thế nào, vận hành ra sao
        |
        | country_code + shop_id
        v
products
  sản phẩm, giá, voucher, rating, lượt bán, ảnh
        |
        | country_code + shop_id + item_id + date
        v
product_categories
  sản phẩm này được shop đặt vào kệ/danh mục nội bộ nào
        |
        | country_code + shop_id + category_id + date
        v
category_list
  tên kệ/danh mục nội bộ của shop là gì

products
  catid/global_catids
        |
        v
category_platform
  ngành hàng chính thức của Shopee
```

Nói ngắn gọn:

- `products`: bán cái gì, giá bao nhiêu, bán được bao nhiêu, rating thế nào.
- `shop_info`: ai bán, shop lớn hay nhỏ, official hay không, phản hồi tốt không.
- `product_categories`: sản phẩm được đặt vào danh mục/kệ nào của shop.
- `category_list`: danh mục/kệ đó tên gì, là kệ cha hay kệ con.
- `category_platform`: sản phẩm thuộc ngành hàng chuẩn nào trên Shopee.

### Quan hệ join chính

| Từ bảng | Sang bảng | Điều kiện join |
| --- | --- | --- |
| `products` | `shop_info` | `country_code + shop_id` |
| `products` | `product_categories` | `country_code + shop_id + item_id + date` |
| `product_categories` | `category_list` | `country_code + shop_id + category_id = shop_category_id + date` |
| `products` | `category_platform` | `country_code = path_country_code` và `catid/global_catids` với `category_id` |

### Ví dụ truy vết một sản phẩm

Giả sử có một dòng trong `products`:

```text
country_code = vn
shop_id      = 108166524
item_id      = 123
date         = 2026-07-03
product_name = Bánh/Kẹo A
price        = 50,000
monthly_sold_value = 1,000
```

Từ dòng này, có thể nối sang các bảng khác để trả lời các câu hỏi khác nhau.

1. Nối sang `shop_info`

```text
products.country_code = shop_info.country_code
products.shop_id      = shop_info.shop_id
```

Trả lời được:

- Shop này tên gì?
- Có phải official shop không?
- Có bao nhiêu follower?
- Rating shop thế nào?
- Response rate/time có tốt không?

Ý nghĩa phân tích: biết sản phẩm bán tốt là do bản thân sản phẩm, hay nằm trong shop mạnh/có uy tín cao.

2. Nối sang `product_categories`

```text
products.country_code = product_categories.country_code
products.shop_id      = product_categories.shop_id
products.item_id      = product_categories.item_id
products.date         = product_categories.date
```

Trả lời được:

- Sản phẩm này được shop đặt vào những kệ/danh mục nội bộ nào?
- Một sản phẩm có thể nằm trong nhiều kệ không?

Ý nghĩa phân tích: biết sản phẩm được shop trưng bày ở đâu, ví dụ `Best Seller`, `Combo`, `Khuyến mãi`, `Bánh quy`.

3. Nối tiếp sang `category_list`

```text
product_categories.country_code = category_list.country_code
product_categories.shop_id      = category_list.shop_id
product_categories.category_id  = category_list.shop_category_id
product_categories.date         = category_list.date
```

Trả lời được:

- Tên kệ/danh mục là gì?
- Kệ đó là danh mục cha hay con?
- Kệ đó có bao nhiêu sản phẩm?

Ý nghĩa phân tích: tính doanh thu/lượt bán theo từng kệ nội bộ của shop.

4. Nối sang `category_platform`

```text
products.country_code = category_platform.path_country_code
products.catid        = category_platform.category_id
```

Hoặc đọc từng ID trong `products.global_catids` rồi map sang `category_platform.category_id`.

Trả lời được:

- Sản phẩm thuộc ngành hàng chuẩn nào của Shopee?
- Danh mục cha/con của ngành đó là gì?
- Có thể so sánh sản phẩm giữa nhiều shop trong cùng một ngành hàng không?

Ý nghĩa phân tích: gom sản phẩm về taxonomy chung của Shopee để so sánh thị trường, thay vì phụ thuộc vào tên kệ tự đặt của từng shop.

### Tại sao cần cả `category_list`, `product_categories`, `category_platform`?

Ba bảng này dễ nhầm, nhưng vai trò khác nhau:

| Bảng | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `category_list` | Shop có những kệ/danh mục nội bộ nào? | `Combo tiết kiệm`, `Best Seller`, `Bánh quy` |
| `product_categories` | Sản phẩm nào nằm trong kệ nào? | Sản phẩm A nằm trong `Best Seller` và `Combo` |
| `category_platform` | Sản phẩm thuộc ngành hàng chuẩn nào trên Shopee? | `Food & Beverages -> Snacks -> Biscuits` |

Nếu chỉ có `category_list`, ta biết shop có kệ gì nhưng không biết sản phẩm nào nằm trong kệ đó.
Nếu chỉ có `product_categories`, ta biết sản phẩm nối với category ID nào nhưng chưa biết tên category dễ đọc.
Nếu chỉ có `category_platform`, ta biết ngành hàng chuẩn của Shopee nhưng không biết shop đang trưng bày sản phẩm thế nào trong trang shop.

### Quan hệ với doanh thu

Dataset không có cột doanh thu trực tiếp, nhưng có thể ước tính bằng:

```text
estimated_recent_revenue = price * monthly_sold_value
```

Sau đó có thể phân tích theo nhiều hướng:

- Theo sản phẩm: dùng trực tiếp `products`.
- Theo shop: join `products` với `shop_info`, group by `shop_id/shop_name`.
- Theo kệ nội bộ shop: join `products -> product_categories -> category_list`, group by `display_name`.
- Theo ngành hàng Shopee: join `products -> category_platform`, group by `display_category_name`.

Lưu ý khi tính doanh thu theo category nội bộ:

- Một sản phẩm có thể nằm trong nhiều `category_list`.
- Nếu group theo category nội bộ, sản phẩm đó có thể được tính ở nhiều category.
- Điều này phù hợp nếu mục tiêu là xem từng kệ trưng bày đóng góp thế nào.
- Nhưng nếu muốn tính tổng doanh thu toàn shop/toàn dataset, cần deduplicate theo `country_code + shop_id + item_id + date`.

Bảng nên dùng cho phân tích nhanh là:

```text
Dataset/DataProcessed/product_dataset_ready.csv
```

Bảng này đã merge `products` với thông tin shop và gom danh mục nội bộ shop vào các cột:

- `shop_rating_star`
- `shop_follower_count`
- `shop_item_count`
- `shop_is_official_shop`
- `shop_category_ids`
- `shop_category_names`
- `shop_category_count`

## 5. Preprocessing đã thực hiện

Chi tiết preprocessing được tách riêng tại:

```text
Preprocessing/preprocessing.md
Preprocessing/preprocess_dataset.ipynb
```

Các bước xử lý:

1. Đọc toàn bộ 82 file CSV trong `Dataset/DataRaw`.
2. Parse metadata từ đường dẫn: `path_country_code`, `path_dataset`, `path_shop_id`.
3. Chuẩn hoá text bằng cách strip và collapse khoảng trắng.
4. Bổ sung `country_code`/`shop_id` từ đường dẫn nếu file không có sẵn cột đó.
5. Tạo các cột số chuẩn hoá với suffix `_num`, ví dụ `price_num`, `rating_num`, `monthly_sold_value_num`.
6. Tạo các cột boolean chuẩn hoá với suffix `_bool`, ví dụ `is_sold_out_bool`, `is_official_shop_bool`.
7. Parse các cột JSON array và tạo cột đếm với suffix `_count`, ví dụ `images_count`, `vouchers_count`, `global_catids_count`.
8. Tạo `product_name_clean` cho tên sản phẩm đã chuẩn hoá khoảng trắng.
9. Tạo `discount_amount_num = price_original - price` khi đủ dữ liệu.
10. Loại duplicate exact. Kết quả chỉ có `products` bị loại 30 dòng.
11. Xuất các bảng clean và bảng phân tích đã merge.
12. Xuất report chất lượng dữ liệu tại `Dataset/DataProcessed/data_quality_report.json`.

## 6. Cấu trúc folder

```text
Dataset/
  DataRaw/            Dữ liệu gốc theo country_code/dataset/shop_id
  DataProcessed/      Dữ liệu sau preprocessing

Preprocessing/
  preprocessing.md    Tài liệu riêng cho preprocessing
  preprocess_dataset.ipynb

Research/
  research.md         Câu hỏi nghiên cứu, giả thuyết, hướng insight
  research.ipynb      Notebook vẽ biểu đồ kiểm định giả thuyết

Documentation.md      Tài liệu bối cảnh dataset và quan hệ bảng
README.md
```

## 7. Gợi ý sử dụng

Nếu cần phân tích sản phẩm, bắt đầu từ:

```text
Dataset/DataProcessed/product_dataset_ready.csv
```

Một số hướng phân tích phù hợp:

- So sánh giá, discount, rating, lượt bán theo quốc gia.
- Tìm sản phẩm outlier về giá hoặc doanh số.
- Phân tích shop official vs non-official.
- So sánh `monthly_sold_value`, `history_sold_value`, `liked_count` theo shop.
- Nhóm sản phẩm theo `shop_category_names` hoặc taxonomy nền tảng `catid/global_catids`.

Khi phân tích giá, nên xử lý riêng 3 dòng có `price = 999999999` vì nhiều khả năng là sentinel/outlier.

Khi phân tích theo thời gian, lưu ý dataset chỉ có 3 ngày snapshot (`2026-07-01` đến `2026-07-03`), không đủ dài để suy luận trend dài hạn.

## 8. Định hướng nghiên cứu và phạm vi phát triển

Phần nghiên cứu insight được tách riêng trong:

```text
Research/research.md
Research/research.ipynb
```

Mục này giúp người dùng sau hiểu các hướng đã được định hình, tránh đào trùng, đồng thời biết hướng nào có thể phát triển tiếp.

### 8.1. Các hướng đã được đặt trong `Research/research.md`

`Research/research.md` đã đặt câu hỏi nghiên cứu trung tâm:

```text
Các yếu tố về giá, khuyến mãi, uy tín shop, danh mục, hình ảnh và nội dung sản phẩm ảnh hưởng như thế nào đến doanh thu ước tính trên Shopee, và các yếu tố này khác nhau ra sao giữa Việt Nam và Indonesia?
```

Các nhóm hướng đã được nêu:

| Nhóm nghiên cứu | Mục tiêu | Trạng thái |
| --- | --- | --- |
| So sánh thị trường `vn` vs `id` | Hiểu khác biệt về giá, lượt bán, voucher/promo, rating giữa hai nước | Nên triển khai trước |
| Yếu tố liên quan tới doanh thu | Kiểm tra quan hệ giữa giá, rating, liked count, images, follower với doanh thu ước tính | Nên triển khai trước |
| Hiệu quả voucher/promo | So sánh sản phẩm có/không có voucher/promo, discount bucket, promo group | Nên triển khai trước |
| Shop trust và vận hành shop | Official shop, follower, rating shop, response rate/time ảnh hưởng thế nào | Nên triển khai nếu cần insight về shop |
| Category và cách trưng bày | Category nền tảng và kệ nội bộ shop đóng góp gì vào doanh thu | Nên triển khai, nhưng cần chú ý double count |
| Hình ảnh và nội dung sản phẩm | `images_count`, brand, keyword trong tên sản phẩm có liên quan tới performance không | Có thể triển khai mở rộng |

### 8.2. Hướng nên tiếp tục đào sâu

Các hướng dưới đây phù hợp với dataset hiện tại và có thể phát triển thành insight tốt:

1. **So sánh VN và ID**

Nên làm vì dataset có 2 quốc gia và mỗi quốc gia có 10 shop. Đây là góc nhìn tự nhiên nhất.

Câu hỏi nên trả lời:

- Thị trường nào có doanh thu ước tính cao hơn?
- Thị trường nào có giá median cao hơn?
- Voucher/promo phổ biến hơn ở nước nào?
- `monthly_sold_value` khác nhau ra sao giữa hai nước?

2. **Promotion effectiveness**

Nên làm vì dataset có đủ các cột:

- `discount_percent`
- `promotion_id`
- `voucher_discount`
- `voucher_min_spend`
- `price`
- `price_before_promo`
- `monthly_sold_value`

Câu hỏi nên trả lời:

- Nhóm `voucher + promo` có bán tốt hơn nhóm không có ưu đãi không?
- Discount bucket nào có doanh thu ước tính tốt nhất?
- Promo/voucher hiệu quả khác nhau giữa VN và ID không?

3. **Shop trust**

Nên làm vì `shop_info` có đủ các tín hiệu:

- `shop_follower_count`
- `shop_rating_star`
- `shop_is_official_shop`
- `shop_response_rate`
- `shop_response_time`

Câu hỏi nên trả lời:

- Official shop có performance tốt hơn không?
- Shop nhiều follower có tạo doanh thu ước tính cao hơn không?
- Rating shop có còn quan trọng khi đã xét price/promo không?

4. **Category nội bộ và merchandising**

Nên làm vì dataset có `category_list` và `product_categories`, giúp nhìn cách shop trưng bày sản phẩm.

Câu hỏi nên trả lời:

- Kệ nội bộ nào có doanh thu ước tính cao?
- Các kệ có từ khóa như `Combo`, `Best Seller`, `Flash Sale`, `Khuyến mãi` có performance tốt hơn không?
- Sản phẩm nằm trong nhiều kệ nội bộ có bán tốt hơn không?

Lưu ý: hướng này dễ bị double count vì một sản phẩm có thể nằm trong nhiều kệ. Nếu tính tổng toàn shop/toàn thị trường, phải deduplicate theo `country_code + shop_id + item_id + date`.

5. **Presentation: ảnh, brand, keyword sản phẩm**

Có thể làm để bổ sung insight mềm về listing quality.

Câu hỏi nên trả lời:

- Sản phẩm có nhiều ảnh hơn có bán tốt hơn không?
- Sản phẩm có brand rõ ràng có performance tốt hơn không?
- Tên sản phẩm có keyword `combo`, `official`, `new`, `gift`, `sale` có khác biệt không?

### 8.3. Hướng tạm thời không nên đào sâu quá mức

Các hướng dưới đây không nên đi quá sâu nếu chỉ dùng dataset hiện tại:

1. **Trend dài hạn theo thời gian**

Dataset chỉ có snapshot từ `2026-07-01` đến `2026-07-03`, tức 3 ngày. Không đủ để kết luận trend dài hạn, seasonality, tăng trưởng theo tháng/quý.

Có thể làm:

- So sánh snapshot 3 ngày rất nhẹ.
- Kiểm tra data consistency.

Không nên làm:

- Forecast doanh thu.
- Kết luận xu hướng tăng/giảm dài hạn.
- Phân tích seasonality.

2. **Causal inference: khẳng định voucher/promo gây tăng doanh thu**

Dataset là observational data, không phải A/B test. Sản phẩm có voucher có thể vốn đã là sản phẩm chiến lược hoặc sản phẩm bán tốt.

Có thể nói:

```text
Sản phẩm có voucher/promo có liên quan tới performance cao/thấp hơn.
```

Không nên nói chắc:

```text
Voucher/promo là nguyên nhân trực tiếp làm tăng doanh thu.
```

3. **Profit/margin**

Dataset không có cost, margin, phí sàn, phí ads, phí vận chuyển, chiết khấu thật.

Không nên kết luận:

- Sản phẩm nào lợi nhuận cao nhất.
- Discount nào tối ưu profit.
- Voucher nào tối ưu margin.

Chỉ nên kết luận về:

```text
estimated_recent_revenue = price * monthly_sold_value
```

4. **Hiệu quả quảng cáo**

Cột `is_ad` hiện toàn `False` trong processed data. Vì vậy không có đủ variation để phân tích quảng cáo.

Không nên đào sâu:

- Ads có hiệu quả không.
- Sponsored listing ảnh hưởng doanh thu thế nào.

5. **Chất lượng ảnh bằng computer vision**

Dataset có link ảnh, nhưng hiện preprocessing chưa download/cache ảnh và chưa trích xuất feature thị giác.

Có thể làm sau nếu mở rộng:

- Download ảnh.
- OCR chữ trên ảnh.
- Chấm chất lượng ảnh.
- Trích màu chủ đạo, số object, ảnh lifestyle vs packshot.

Nhưng chưa nên đưa vào core analysis nếu chưa tạo pipeline ảnh riêng.

### 8.4. Hướng mới có thể phát triển sau

Nếu muốn phát triển project lên thêm, có thể đi các hướng sau:

| Hướng mới | Cần thêm gì | Giá trị |
| --- | --- | --- |
| Image analysis | Script download/cache ảnh, feature ảnh | Hiểu ảnh sản phẩm ảnh hưởng performance thế nào |
| Text/NLP sản phẩm | Keyword extraction, text length, brand/entity parsing | Hiểu title/product copy ảnh hưởng bán hàng thế nào |
| Category platform deep dive | Parse `global_catids` thành từng cấp category | So sánh ngành hàng chuẩn Shopee sâu hơn |
| Simple predictive model | Feature engineering + model target `log1p(estimated_recent_revenue)` | Ước lượng yếu tố nào quan trọng nhất |
| Country-specific recommendation | Tách model/EDA riêng cho VN và ID | Đề xuất chiến lược khác nhau theo thị trường |
| Data collection extension | Thêm nhiều ngày snapshot hơn | Phân tích trend, seasonality, trước/sau campaign |

### 8.5. Khuyến nghị cho người phát triển tiếp

Nếu là người mới mở repo, nên đi theo thứ tự:

1. Đọc `Documentation.md` để hiểu bảng và quan hệ.
2. Đọc `Preprocessing/preprocessing.md` để hiểu dữ liệu đã được xử lý thế nào.
3. Chạy/đọc `Research/research.ipynb` để xem chart cơ bản.
4. Nếu muốn mở rộng, ưu tiên một trong ba hướng:
   - So sánh VN vs ID.
   - Promotion/voucher effectiveness.
   - Shop/category strategy.

Không nên bắt đầu bằng model phức tạp ngay. Dataset nhỏ và chỉ có 3 ngày snapshot, nên EDA kỹ và giải thích business rõ ràng sẽ có giá trị hơn.
