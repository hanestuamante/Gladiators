# Product Knowledge Solution

## 1. Bối cảnh đề bài

Đề bài yêu cầu đề xuất giải pháp giúp AI Agent hiểu mối quan hệ giữa:

```text
Product, SKU, Category, Brand, Promotion, Content, Sales
```

và các thực thể khác trong hệ sinh thái eCommerce.

Mục tiêu cuối cùng là AI Agent có thể trả lời các câu hỏi như:

- Vì sao doanh số sản phẩm A giảm?
- Sản phẩm nào tương tự với SKU này?
- Promotion nào mang lại hiệu quả tốt nhất?

Giải pháp dưới đây được thiết kế dựa trên cấu trúc folder/dataset hiện tại của repo:

```text
Dataset/
  DataRaw/
  DataProcessed/

Preprocessing/
  preprocess_dataset.ipynb
  preprocessing.md

Research/
  research.md
  research.ipynb

Documentation.md
```

## 2. Mục tiêu giải pháp

AI Agent cần làm được 3 việc:

1. **Hiểu dữ liệu**

Biết mỗi bảng chứa thực thể nào, khóa join nào, cột nào đại diện cho giá, doanh số, khuyến mãi, category, brand, shop, content.

2. **Hiểu quan hệ**

Biết Product liên quan tới Shop, Brand, Category, Promotion, Sales, Content như thế nào.

3. **Giải thích được nguyên nhân**

Không chỉ trả lời “sản phẩm nào cao/thấp”, mà còn giải thích dựa trên dữ liệu:

```text
Doanh số giảm có thể liên quan tới tăng giá, giảm discount, hết voucher, rating thấp, ít ảnh, category yếu, hoặc shop trust thấp.
```

## 3. Các thực thể chính trong dataset hiện tại

| Thực thể eCommerce | Có trong dataset không? | Mapping trong repo | Ghi chú |
| --- | --- | --- | --- |
| Product | Có | `products.item_id`, `products.product_name` | Thực thể trung tâm |
| SKU | Có một phần | `item_id` + `tier_variation_name` + `tier_variation_options` | Dataset chưa có SKU/variant ID riêng |
| Shop/Seller | Có | `shop_info.shop_id`, `products.shop_id` | Bổ sung uy tín shop |
| Brand | Có | `products.brand`, `products.brand_id` | Có thể thiếu ở một số sản phẩm |
| Category platform | Có | `products.catid`, `products.global_catids`, `category_platform.category_id` | Danh mục chuẩn Shopee |
| Category shop | Có | `category_list.shop_category_id`, `product_categories.category_id` | Kệ/danh mục nội bộ shop |
| Promotion | Có | `discount_percent`, `promotion_id`, `voucher_*` | Promo/voucher hiển thị |
| Content | Có | `product_name`, `image_url`, `images`, `images_count`, `tier_variation_options` | Chưa có mô tả dài sản phẩm |
| Sales | Có dạng proxy | `monthly_sold_value`, `history_sold_value` | Không phải doanh thu thật |
| Revenue | Tự tạo | `price * monthly_sold_value` | Doanh thu ước tính |
| Rating/Review | Có | `rating`, `rating_count`, `rating_count_detail` | Social proof |

## 4. Knowledge Graph đề xuất

AI Agent nên xây một lớp Product Knowledge Graph từ dữ liệu processed.

### 4.1. Nodes

Các node chính:

```text
Product
SKU_or_Variant
Shop
Brand
PlatformCategory
ShopCategory
Promotion
Voucher
Content
SalesMetric
Country
DateSnapshot
```

### 4.2. Edges

Các quan hệ chính:

```text
Product BELONGS_TO Shop
Product HAS_BRAND Brand
Product IN_PLATFORM_CATEGORY PlatformCategory
Product IN_SHOP_CATEGORY ShopCategory
Product HAS_PROMOTION Promotion
Product HAS_VOUCHER Voucher
Product HAS_CONTENT Content
Product HAS_SALES_METRIC SalesMetric
Product HAS_VARIATION SKU_or_Variant
Shop OPERATES_IN Country
Product OBSERVED_AT DateSnapshot
```

### 4.3. Mapping từ bảng sang graph

| Quan hệ | Bảng nguồn | Join/key |
| --- | --- | --- |
| Product -> Shop | `products`, `shop_info` | `country_code + shop_id` |
| Product -> ShopCategory | `products`, `product_categories`, `category_list` | `country_code + shop_id + item_id + date`, sau đó `category_id = shop_category_id` |
| Product -> PlatformCategory | `products`, `category_platform` | `products.catid = category_platform.category_id` |
| Product -> Brand | `products` | `brand`, `brand_id` |
| Product -> Promotion | `products` | `promotion_id`, `discount_percent` |
| Product -> Voucher | `products` | `voucher_code`, `voucher_discount`, `voucher_min_spend` |
| Product -> Content | `products` | `product_name`, `image_url`, `images`, `images_count` |
| Product -> SalesMetric | `products` | `monthly_sold_value`, `history_sold_value`, `rating_count`, `liked_count` |

## 5. Dataset processed nên dùng cho Agent

Bảng trung tâm:

```text
Dataset/DataProcessed/product_dataset_ready.csv
```

Bảng này đã có:

- Product attributes.
- Shop attributes.
- Shop category attributes.
- Price/promotion/voucher.
- Rating/sales proxy.
- Content features như `images_count`, `product_name_clean`.

Nếu Agent cần phân tích category chuẩn Shopee, join thêm:

```text
Dataset/DataProcessed/category_platform_clean.csv
```

## 6. Feature layer cho AI Agent

Agent không nên trả lời trực tiếp từ raw CSV. Nên có một lớp feature được chuẩn hóa.

### 6.1. Sales features

```text
monthly_sold_value_num
history_sold_value_num
estimated_recent_revenue = price_num * monthly_sold_value_num
```

Ý nghĩa:

- `monthly_sold_value_num`: proxy cho nhu cầu gần đây.
- `history_sold_value_num`: proxy cho sức bán tích lũy.
- `estimated_recent_revenue`: proxy cho doanh thu gần đây.

### 6.2. Price and promotion features

```text
price_num
price_original_num
price_before_promo_num
discount_percent_num
discount_amount_num
voucher_discount_num
voucher_min_spend_num
promotion_id_num
has_promo = discount_percent_num > 0
has_voucher = voucher_discount_num > 0
promo_group = no promo / promo only / voucher only / voucher + promo
```

Lưu ý:

- Trong dataset này, `price` nên được hiểu là giá cuối hiển thị sau khi đã phản ánh voucher/promo.
- Không trừ `voucher_discount` thêm lần nữa khỏi `price`.

### 6.3. Trust features

```text
rating_num
rating_count_num
liked_count_num
shop_rating_star
shop_follower_count
shop_is_official_shop
shop_response_rate
shop_response_time
```

Ý nghĩa:

- Đo social proof của sản phẩm.
- Đo độ uy tín/quy mô/vận hành của shop.

### 6.4. Content features

```text
product_name_clean
images_count
vouchers_count
tier_variation_options_count
brand
brand_id
```

Có thể mở rộng:

- `product_name_length`
- keyword flags: `combo`, `official`, `sale`, `new`, `gift`
- image quality nếu download ảnh về.

### 6.5. Category features

```text
catid
global_catids
shop_category_ids
shop_category_names
shop_category_count
```

Ý nghĩa:

- `catid/global_catids`: ngành hàng chuẩn Shopee.
- `shop_category_names`: kệ trưng bày nội bộ của shop.
- `shop_category_count`: sản phẩm được đặt vào bao nhiêu kệ.

## 7. Cách Agent trả lời câu hỏi

### 7.1. Câu hỏi: “Vì sao doanh số sản phẩm A giảm?”

Dataset hiện chỉ có 3 ngày snapshot, nên không đủ kết luận trend dài hạn. Agent phải trả lời thận trọng.

Quy trình Agent:

1. Tìm Product A bằng `item_id` hoặc `product_name`.
2. Lấy các snapshot theo `date`.
3. So sánh:
   - `monthly_sold_value_num`
   - `price_num`
   - `discount_percent_num`
   - `voucher_discount_num`
   - `rating_num`
   - `rating_count_num`
   - `liked_count_num`
   - `shop_category_names`
4. So sánh với sản phẩm tương tự cùng category/brand/shop.
5. Trả lời bằng dạng nguyên nhân khả dĩ, không khẳng định causal tuyệt đối.

Ví dụ câu trả lời Agent nên tạo:

```text
Doanh số gần đây của sản phẩm A giảm có thể liên quan đến 3 yếu tố:
1. Giá cuối tăng từ X lên Y.
2. Voucher không còn hoặc voucher_discount giảm.
3. Sản phẩm tương tự trong cùng category có discount cao hơn và monthly_sold_value tốt hơn.

Do dataset chỉ có 3 ngày snapshot, đây là phân tích tương quan ngắn hạn, không đủ kết luận nguyên nhân tuyệt đối.
```

### 7.2. Câu hỏi: “Sản phẩm nào tương tự với SKU này?”

Dataset chưa có SKU ID riêng. Agent nên xem SKU như:

```text
item_id + tier_variation_name + tier_variation_options
```

Quy trình tìm sản phẩm tương tự:

1. Lấy sản phẩm gốc.
2. Tìm các sản phẩm cùng:
   - `country_code`
   - `catid` hoặc cùng `global_catids`
   - `brand` nếu có
   - khoảng giá gần nhau
   - keyword tên sản phẩm tương tự
3. Rank theo:
   - giống category
   - giống brand
   - giá gần
   - rating gần
   - tên chứa keyword giống
   - cùng shop category nếu cùng shop

Ví dụ câu trả lời:

```text
Các sản phẩm tương tự SKU này là B, C, D vì chúng cùng category Shopee, cùng brand/nhóm giá, và có tên sản phẩm chứa keyword tương tự. Trong đó B có monthly_sold_value cao nhất và voucher tốt hơn.
```

### 7.3. Câu hỏi: “Promotion nào mang lại hiệu quả tốt nhất?”

Quy trình Agent:

1. Tạo `promo_group`:
   - no promo
   - promo only
   - voucher only
   - voucher + promo
2. Group theo:
   - `promotion_id`
   - `voucher_code`
   - `discount_bucket`
   - `country_code`
3. Tính:

```text
median_monthly_sold
median_estimated_recent_revenue
total_estimated_recent_revenue
product_count
```

4. So sánh với baseline không có promo/voucher.

Ví dụ câu trả lời:

```text
Nhóm voucher + promo có median estimated_recent_revenue cao hơn nhóm không có ưu đãi. Tuy nhiên, không thể khẳng định promotion là nguyên nhân trực tiếp vì sản phẩm được chọn chạy promo có thể vốn là sản phẩm chiến lược.
```

## 8. Agent cần biết giới hạn dữ liệu

Agent phải luôn nhớ các giới hạn sau:

| Giới hạn | Tác động |
| --- | --- |
| Chỉ có 3 ngày snapshot | Không kết luận trend dài hạn |
| Không có cost/margin | Không trả lời profit thật |
| Không có order-level data | Không biết conversion rate, AOV, basket size |
| Không có SKU ID riêng | SKU chỉ là proxy từ `item_id` + variation |
| `is_ad` toàn `False` | Không phân tích hiệu quả quảng cáo |
| Category nội bộ có thể double count | Cẩn thận khi tính tổng theo category |
| Promotion data là observational | Không khẳng định causal tuyệt đối |

## 9. Kiến trúc giải pháp đề xuất

```text
Raw CSV
  -> Preprocessing Notebook
  -> DataProcessed CSV
  -> Feature Layer
  -> Product Knowledge Graph / Semantic Layer
  -> Retrieval + Analysis Tools
  -> AI Agent Answer
```

### 9.1. Semantic Layer

Semantic layer nên định nghĩa:

- Entity: Product, Shop, Brand, Category, Promotion, Voucher, Content, SalesMetric.
- Relationship: belongs_to, has_brand, has_promotion, in_category, has_sales_metric.
- Metric: estimated_recent_revenue, monthly_sold_value, discount_rate, voucher_value.
- Guardrails: không overclaim causal, không dùng `price` trừ voucher thêm lần nữa.

### 9.2. Retrieval Layer

Agent cần retrieve:

- Dòng sản phẩm liên quan.
- Sản phẩm tương tự.
- Shop info.
- Category/platform info.
- Promotion/voucher info.
- Historical snapshots nếu có.

### 9.3. Analysis Layer

Agent cần tool tính:

- Groupby theo country/shop/category/promo.
- Ranking sản phẩm tương tự.
- So sánh trước/sau theo date.
- Correlation/feature importance nếu làm model.
- Outlier detection.

## 10. Đề xuất phát triển tiếp

Nếu muốn nâng giải pháp lên mức production hơn:

1. **Tạo Product Knowledge Graph**

Lưu entity và relationship vào graph database hoặc bảng semantic layer.

2. **Tạo product similarity index**

Dùng text embedding từ `product_name_clean`, category, brand, price bucket để tìm sản phẩm tương tự.

3. **Tạo promotion evaluation module**

Chuẩn hóa cách so sánh promo group, discount bucket, voucher code theo country/category.

4. **Thêm image pipeline**

Download/cache ảnh từ `image_url/images`, trích xuất feature ảnh.

5. **Thêm nhiều ngày dữ liệu**

Để trả lời tốt câu hỏi “vì sao doanh số giảm”, cần nhiều snapshot hơn.

## 11. Đối chiếu với repo `BanMartinCode/b01-gbrain-ecommerce`

Repo tham khảo:

```text
https://github.com/BanMartinCode/b01-gbrain-ecommerce
```

Repo này có liên quan mạnh về mặt ý tưởng vì nó mô tả một **Commerce Intelligence Brain**: một bộ skill/workflow để xây knowledge graph cho eCommerce operations.

### 11.1. Điểm liên quan trực tiếp

Các skill trong repo đó có thể map khá tốt với bài Product Knowledge:

| Skill trong repo tham khảo | Ý nghĩa | Liên quan tới bài hiện tại |
| --- | --- | --- |
| `/product-ingest` | Ingest product specs, reviews, sales data, extract attributes, link entities | Rất liên quan; tương ứng bước đưa `products`, `shop_info`, category, promotion vào semantic layer |
| `/competitor-track` | Track competitor products, prices, promotions | Liên quan nếu mở rộng phân tích cạnh tranh giữa shop/country |
| `/campaign-ingest` | Link marketing campaign với product, audience, conversion | Liên quan với promotion/voucher effectiveness |
| `/pricing-signal` | Detect pricing opportunities, competitor gaps, elasticity patterns | Liên quan với phân tích price, discount, voucher |
| `/review-ingest` | Extract sentiment/issues từ review | Hữu ích nhưng dataset hiện chưa có review text |
| `/inventory-brain` | Inventory, supplier, reorder, demand patterns | Hữu ích nhưng dataset hiện chưa có tồn kho |
| `/returns-query` | Return patterns, root causes, quality signals | Hữu ích nhưng dataset hiện chưa có returns |
| `/customer-graph` | Customer segments, LTV, purchase patterns | Hữu ích nhưng dataset hiện chưa có customer/order-level data |

### 11.2. Nên học gì từ repo đó?

Có 3 ý nên tận dụng:

1. **Commerce brain / knowledge graph mindset**

Repo đó không xem dữ liệu eCommerce như bảng rời rạc, mà xem là mạng quan hệ:

```text
Product -> Category -> Brand -> Promotion -> Customer -> Sales -> Review -> Inventory
```

Điều này rất phù hợp với bài thi vì đề bài yêu cầu AI Agent hiểu mối quan hệ giữa Product, SKU, Category, Brand, Promotion, Content, Sales.

2. **Skill-based workflow**

Repo đó chia năng lực Agent thành nhiều skill:

```text
product-ingest
pricing-signal
campaign-ingest
competitor-track
review-ingest
inventory-brain
```

Với repo hiện tại, có thể thiết kế Agent theo module tương tự:

```text
product-knowledge-ingest
promotion-effectiveness
category-insight
pricing-signal
product-similarity
sales-explain
```

3. **Structured answer pattern**

Repo đó dùng pattern:

```text
Scope -> Execute -> Findings -> Actions -> Next Steps
```

Agent của bài này cũng nên trả lời theo format tương tự:

```text
Question
Evidence
Likely reasons
Confidence/limitations
Recommended actions
Next analysis
```

Format này giúp Agent không chỉ trả lời số liệu, mà còn giải thích và đề xuất hành động.

### 11.3. Phần không áp dụng trực tiếp

Repo `b01-gbrain-ecommerce` là skill/playbook tổng quát, không phải code xử lý dataset Shopee hiện tại. Vì vậy không thể copy trực tiếp để chạy.

Các phần chưa áp dụng được ngay vì dataset hiện tại thiếu dữ liệu:

| Ý tưởng trong repo tham khảo | Vì sao chưa áp dụng trực tiếp |
| --- | --- |
| Customer graph | Dataset không có customer/order-level data |
| LTV/purchase pattern | Không có lịch sử đơn hàng theo khách |
| Review sentiment | Không có review text, chỉ có rating/rating_count |
| Inventory brain | Không có tồn kho/supplier/reorder |
| Returns query | Không có return/refund data |
| Competitor tracking đầy đủ | Có thể so sánh giữa shop trong dataset, nhưng chưa có crawler competitor riêng |

### 11.4. Cách đưa ý tưởng đó vào bài hiện tại

Nên dùng repo tham khảo như **framework tư duy**, không dùng như source code chính.

Áp dụng vào bài hiện tại như sau:

```text
1. product-ingest
   -> Preprocessing/product_dataset_ready.csv

2. commerce knowledge graph
   -> Entity/relationship mapping trong Product_Knowledge_Solution.md

3. pricing-signal
   -> price_num, discount_percent_num, voucher_discount_num, estimated_recent_revenue

4. campaign-ingest
   -> promotion_id, voucher_code, promo_group, discount_bucket

5. product similarity
   -> product_name_clean + brand + catid + price bucket + shop_category_names

6. explain sales
   -> so sánh price/promo/rating/category/shop trust theo date và sản phẩm tương tự
```

### 11.5. Kết luận về mức độ liên quan

Repo `BanMartinCode/b01-gbrain-ecommerce` **có liên quan cao về kiến thức và hướng thiết kế Agent**, đặc biệt ở các ý:

- commerce knowledge graph,
- product ingest,
- pricing signal,
- campaign/promotion analysis,
- structured findings/action plan.

Nhưng repo đó **không thay thế preprocessing/research hiện tại**, vì nó là playbook/skill template tổng quát, còn repo này đã có dataset Shopee cụ thể, preprocessing cụ thể, và semantic mapping riêng.

Nên sử dụng repo tham khảo để làm phần “kiến trúc giải pháp AI Agent chuyên nghiệp hơn”, còn phần phân tích thực nghiệm vẫn dựa trên:

```text
Dataset/DataProcessed/product_dataset_ready.csv
Research/research.ipynb
Preprocessing/preprocessing.md
Documentation.md
```

## 12. Đối chiếu với repo `OpenBGBenchmark/OpenBG-IMG`

Repo tham khảo:

```text
https://github.com/OpenBGBenchmark/OpenBG-IMG
```

Repo này liên quan rất rõ tới đề bài Product Knowledge vì nó là benchmark về **multimodal eCommerce knowledge graph link prediction**.

Nói đơn giản: OpenBG-IMG xử lý bài toán **dùng quan hệ giữa entity + hình ảnh sản phẩm để dự đoán liên kết còn thiếu trong knowledge graph**.

### 12.1. OpenBG-IMG là gì?

Theo README của repo, OpenBG-IMG là:

```text
Multi-modal dataset in the field of e-commerce
Knowledge graph embedding models for link prediction
CCKS2022 Digital Commerce multimodal commodity KG link prediction
```

Dataset mẫu của họ có dạng triple:

```text
head_entity    relation    tail_entity
ent_021198     rel_0031    ent_017656
ent_008185     rel_0092    ent_025949
```

Ngoài triple text/ID, họ còn có ảnh cho entity:

```text
data/OpenBG-IMG/images/ent_xxxxxx/...
```

Thống kê trong README:

```text
Entities: 27,910
Relations: 136
Train triples: 230,087
Dev: 5,000
Test: 14,675
Multimodal entities: 14,718
```

### 12.2. Vì sao repo này liên quan tới bài hiện tại?

Bài thi yêu cầu AI Agent hiểu quan hệ giữa:

```text
Product, SKU, Category, Brand, Promotion, Content, Sales
```

OpenBG-IMG cho thấy một hướng formal hơn:

```text
Product Knowledge = Knowledge Graph + Multimodal Entity Representation + Link Prediction
```

Điểm liên quan trực tiếp:

| Ý tưởng OpenBG-IMG | Liên quan tới repo hiện tại |
| --- | --- |
| Entity trong KG | Có thể map thành product, shop, brand, category, promotion, voucher |
| Relation trong KG | Có thể map thành belongs_to, has_brand, in_category, has_promotion, sold_by |
| Image embedding | Repo hiện tại có `image_url` và `images`; có thể mở rộng thành visual features |
| Link prediction | Có thể dùng để gợi ý sản phẩm tương tự, category còn thiếu, brand/category relation |
| Multimodal KG | Phù hợp với Product Knowledge Agent vì sản phẩm có cả text, category, price, image |

### 12.3. Các model trong OpenBG-IMG có ý nghĩa gì?

OpenBG-IMG triển khai nhiều model knowledge graph embedding:

| Model | Ý nghĩa ngắn |
| --- | --- |
| TransE / TransH / TransD | Embedding KG dạng translation-based, học quan hệ giữa entity |
| DistMult / ComplEx | Embedding KG dạng bilinear/factorization |
| TuckER | Tensor factorization cho KG completion |
| TransAE | Mở rộng KG embedding với ảnh |
| RSME | Multimodal KG embedding, kết hợp visual representation |

Với bài hiện tại, không cần chạy các model này ngay. Nhưng chúng cho thấy hướng phát triển nếu muốn Agent trả lời các câu hỏi như:

```text
Sản phẩm nào tương tự SKU này?
Sản phẩm này nên thuộc category nào?
Brand nào/category nào có quan hệ gần nhất?
Thiếu relation nào trong graph?
```

### 12.4. Cách map dataset Shopee hiện tại sang KG kiểu OpenBG-IMG

Dataset hiện tại không có sẵn triple KG, nhưng có thể tạo triple từ các bảng processed.

Ví dụ mapping:

```text
Product(item_id) --sold_by--> Shop(shop_id)
Product(item_id) --has_brand--> Brand(brand_id/brand)
Product(item_id) --in_platform_category--> Category(catid)
Product(item_id) --in_shop_category--> ShopCategory(shop_category_id)
Product(item_id) --has_promotion--> Promotion(promotion_id)
Product(item_id) --has_voucher--> Voucher(voucher_code)
Product(item_id) --observed_in--> Country(country_code)
Product(item_id) --has_image--> Image(image_url)
```

Từ CSV hiện tại có thể sinh ra file triple dạng:

```text
head_entity    relation                  tail_entity
product_123    sold_by                   shop_108166524
product_123    has_brand                 brand_nestle
product_123    in_platform_category      cat_100629
product_123    has_voucher               voucher_17GIAM30K1
product_123    has_image                 image_xxx
```

Đây là bước bridge quan trọng nếu muốn biến repo hiện tại thành Product Knowledge Graph thật sự.

### 12.5. Ứng dụng cho câu hỏi “Sản phẩm nào tương tự với SKU này?”

OpenBG-IMG rất liên quan tới bài similarity/recommendation.

Trong repo hiện tại, sản phẩm tương tự có thể dựa trên:

- `product_name_clean`
- `brand`
- `catid`
- `global_catids`
- `shop_category_names`
- `price_num`
- `rating_num`
- `images_count`

Nếu học theo OpenBG-IMG, có thể nâng cấp similarity bằng:

1. Tạo entity embedding từ KG triples.
2. Tạo image embedding từ `image_url/images`.
3. Kết hợp text/category/brand/price/image embedding.
4. Tìm nearest neighbors của product/SKU.

Khi đó Agent trả lời tốt hơn:

```text
Sản phẩm B tương tự SKU A vì cùng category Shopee, cùng brand, giá gần nhau, title có keyword giống nhau, và ảnh sản phẩm có embedding gần.
```

### 12.6. Ứng dụng cho câu hỏi “Vì sao doanh số sản phẩm A giảm?”

OpenBG-IMG không trực tiếp xử lý sales decline, nhưng KG embedding giúp Agent có nhóm so sánh tốt hơn.

Thay vì chỉ so sản phẩm A với toàn dataset, Agent có thể tìm:

```text
Các sản phẩm gần A nhất trong Product KG
```

Sau đó so:

- Giá của A vs sản phẩm tương tự.
- Voucher của A vs sản phẩm tương tự.
- Rating của A vs sản phẩm tương tự.
- Category/kệ shop của A vs sản phẩm tương tự.
- Content/image của A vs sản phẩm tương tự.

Điều này giúp câu trả lời có cơ sở hơn:

```text
Doanh số A thấp hơn nhóm tương tự vì A có giá cao hơn median category 18%, không có voucher trong khi 70% sản phẩm tương tự có voucher, và rating_count thấp hơn nhóm cạnh tranh.
```

### 12.7. Ứng dụng cho câu hỏi “Promotion nào hiệu quả nhất?”

OpenBG-IMG gợi ý cách xem promotion như một entity trong graph:

```text
Promotion --applies_to--> Product
Product --in_category--> Category
Product --sold_by--> Shop
Product --has_sales_metric--> SalesMetric
```

Khi đó Agent có thể đánh giá promotion theo nhiều lớp:

- Hiệu quả theo product.
- Hiệu quả theo category.
- Hiệu quả theo brand.
- Hiệu quả theo shop.
- Hiệu quả theo country.

Ví dụ:

```text
Voucher X hiệu quả nhất trong nhóm snack ở VN, nhưng không hiệu quả tương tự ở ID.
```

### 12.8. Phần chưa áp dụng trực tiếp

OpenBG-IMG là benchmark/model repo, không phải pipeline phân tích Shopee hiện tại. Không nên copy trực tiếp vì:

- Dataset của OpenBG-IMG có format triple KG, còn dataset hiện tại là CSV eCommerce crawl/snapshot.
- OpenBG-IMG cần ảnh local trong `data/OpenBG-IMG/images`, còn repo hiện tại mới có image URL.
- Model dùng dependency cũ như `torch==1.7.1`, `torchvision==0.8.2`, `transformers==4.11.3`; không nên đưa vào `requirements.txt` hiện tại.
- Chạy KG embedding cần preprocessing riêng, train/dev/test split riêng, metric riêng như HIT@K, MRR.

Vì vậy, repo này nên dùng làm **inspiration cho kiến trúc nâng cao**, không dùng làm dependency trực tiếp lúc này.

### 12.9. Cách phát triển repo hiện tại theo hướng OpenBG-IMG

Nếu muốn nâng project lên sau này, có thể thêm một folder mới:

```text
KnowledgeGraph/
  kg_schema.md
  build_triples.ipynb
  triples/
    train.tsv
    valid.tsv
    test.tsv
  image_features/
```

Pipeline đề xuất:

```text
product_dataset_ready.csv
  -> build entity IDs
  -> build relation triples
  -> optionally download/cache images
  -> extract image embeddings
  -> train/evaluate KG embedding or nearest-neighbor retrieval
  -> expose product similarity + missing relation prediction to Agent
```

Các relation nên tạo trước:

```text
product -> shop
product -> brand
product -> platform_category
product -> shop_category
product -> voucher
product -> promotion
product -> country
product -> image
```

Các relation nên thêm sau nếu có data mới:

```text
product -> review_topic
product -> return_reason
customer -> product
campaign -> product
inventory -> product
competitor_product -> product
```

### 12.10. Kết luận về mức độ liên quan

Repo `OpenBGBenchmark/OpenBG-IMG` **rất liên quan với phần Product Knowledge Graph và multimodal product understanding**.

Nó đặc biệt hữu ích cho các mục tiêu:

- Tìm sản phẩm tương tự.
- Dự đoán relation còn thiếu.
- Kết hợp ảnh sản phẩm vào Product Knowledge.
- Xây semantic layer dạng graph thay vì chỉ dùng bảng CSV.

Nhưng với phạm vi hiện tại, nên ghi nó là **future direction**:

```text
Hiện tại: CSV processed + feature layer + research notebook
Tiếp theo: KnowledgeGraph folder + triples + image embeddings + link prediction/similarity
```

## 13. Đối chiếu với repo `OpenBGBenchmark/OpenBG-Align`

Repo tham khảo:

```text
https://github.com/OpenBGBenchmark/OpenBG-Align
```

Repo này liên quan trực tiếp tới một câu hỏi rất quan trọng trong đề bài:

```text
Sản phẩm nào tương tự với SKU này?
```

OpenBG-Align là baseline cho bài toán **商品同款挖掘**, tức là **same-product mining / product matching / product alignment** trong eCommerce.

### 13.1. OpenBG-Align là gì?

Theo README, repo này là baseline cho:

```text
CCKS2022 Digital Commerce Knowledge Graph Evaluation Task 2:
Knowledge-graph-based same-product mining
```

Nó dùng mô hình pretrain multimodal **CAPTURE** từ paper:

```text
Product1M: Towards Weakly Supervised Instance-Level Product Retrieval via Cross-modal Pretraining
```

Mục tiêu:

```text
Ảnh sản phẩm + tiêu đề sản phẩm -> multimodal product embedding -> tìm sản phẩm cùng loại/cùng mẫu
```

### 13.2. Vì sao liên quan tới Product Knowledge Agent?

Trong dataset hiện tại, mỗi product có:

- `product_name`
- `product_name_clean`
- `image_url`
- `images`
- `brand`
- `catid`
- `global_catids`
- `price`
- `tier_variation_name`
- `tier_variation_options`

OpenBG-Align cho thấy cách dùng **text + image** để tạo representation cho product. Điều này rất phù hợp để Agent trả lời:

```text
Sản phẩm nào tương tự với SKU này?
Sản phẩm nào cùng mẫu/cùng loại với sản phẩm A?
Sản phẩm nào là đối thủ gần nhất?
Có sản phẩm tương tự nhưng giá thấp hơn/promo tốt hơn không?
```

### 13.3. Pipeline của OpenBG-Align

OpenBG-Align có pipeline chính:

```text
Product image + product title
  -> object/region feature extraction bằng detectron2 / Faster R-CNN
  -> CAPTURE multimodal embedding
  -> item_features.tsv
  -> retrieval / same-product matching
```

Trong `Capture/inference.py`, output là:

```text
item_id    features
```

Tức là mỗi sản phẩm được biến thành một vector embedding. Sau đó có thể so sánh cosine similarity để tìm sản phẩm gần nhất.

### 13.4. Mapping sang repo hiện tại

Với repo Shopee hiện tại, có thể map như sau:

| OpenBG-Align | Repo hiện tại |
| --- | --- |
| item id | `products.item_id` |
| product title/caption | `products.product_name_clean` |
| product image | `products.image_url` hoặc `products.images` |
| multimodal embedding | future feature: `product_embedding` |
| same-product mining | future module: `product_similarity` |

Pipeline đề xuất cho repo hiện tại:

```text
product_dataset_ready.csv
  -> lấy item_id, product_name_clean, image_url/images
  -> download/cache ảnh
  -> tạo text embedding từ product_name_clean
  -> tạo image embedding từ ảnh
  -> combine text + image + category + brand + price
  -> tìm nearest neighbors
  -> Agent trả lời sản phẩm tương tự
```

### 13.5. Ứng dụng cho câu hỏi “Sản phẩm nào tương tự với SKU này?”

OpenBG-Align là repo liên quan nhất trong các repo đã xem cho câu hỏi này.

Agent có thể trả lời theo quy trình:

1. Nhận SKU/product cần tìm.
2. Lấy `item_id`, `product_name_clean`, `image_url`, `brand`, `catid`, `price`.
3. Tìm candidate cùng `country_code` và cùng/sát `catid`.
4. Tính similarity:
   - text similarity từ tên sản phẩm,
   - image similarity từ ảnh,
   - category similarity từ `global_catids`,
   - brand match,
   - price distance.
5. Trả về top sản phẩm tương tự và giải thích vì sao.

Ví dụ câu trả lời Agent:

```text
Sản phẩm B tương tự SKU A vì:
- cùng category Shopee,
- cùng brand,
- giá chỉ lệch 8%,
- title cùng keyword "combo bánh quy",
- ảnh sản phẩm có embedding gần nhất trong nhóm candidate.
```

### 13.6. Ứng dụng cho câu hỏi “Vì sao doanh số sản phẩm A giảm?”

OpenBG-Align không trực tiếp giải thích sales decline, nhưng nó giúp xác định **nhóm sản phẩm tương tự** để so sánh.

Thay vì hỏi:

```text
Sản phẩm A giảm so với toàn bộ dataset?
```

Agent nên hỏi:

```text
Sản phẩm A giảm so với các sản phẩm tương tự nhất không?
```

Sau đó so sánh:

- Giá của A vs nhóm tương tự.
- Voucher/promo của A vs nhóm tương tự.
- Rating của A vs nhóm tương tự.
- Hình ảnh/content của A vs nhóm tương tự.
- Shop trust của A vs nhóm tương tự.

Điều này giúp giải thích nguyên nhân tốt hơn.

Ví dụ:

```text
Doanh số A thấp hơn nhóm tương tự vì A không có voucher trong khi 6/10 sản phẩm tương tự có voucher, giá A cao hơn median nhóm 15%, và ảnh sản phẩm ít hơn nhóm top sellers.
```

### 13.7. Phần chưa nên áp dụng trực tiếp

Không nên đưa OpenBG-Align vào requirements hiện tại vì:

- Repo dùng dependency nặng/cũ, gồm detectron2, torch version riêng, CAPTURE pretrained model.
- Cần download model ngoài:
  - Faster R-CNN model.
  - CAPTURE model `pytorch_model_8.bin`.
- Cần ảnh local, trong khi repo hiện tại mới có image URL.
- Cần pipeline riêng để download/cache ảnh và extract embedding.

Vì vậy, OpenBG-Align nên được ghi là **future direction cho product similarity**, không dùng ngay trong pipeline hiện tại.

### 13.8. Cách phát triển repo hiện tại theo hướng OpenBG-Align

Nếu muốn phát triển tiếp, nên thêm folder:

```text
Similarity/
  similarity.md
  build_product_embeddings.ipynb
  download_images.ipynb
  product_neighbors.csv
```

Pipeline thực tế nên làm theo mức độ tăng dần:

1. **Baseline không cần model nặng**

```text
product_name_clean + brand + catid + price bucket
```

Dùng TF-IDF hoặc embedding nhẹ để tìm sản phẩm tương tự.

2. **Thêm image availability**

```text
images_count
image_url domain
main_image_available
```

Chưa cần deep learning, chỉ kiểm tra ảnh có tồn tại và số ảnh.

3. **Thêm image embedding**

Download ảnh và dùng model nhẹ hơn như CLIP/SigLIP nếu môi trường cho phép.

4. **Multimodal product matching**

Kết hợp:

```text
text embedding + image embedding + category + brand + price
```

để tạo `product_similarity_score`.

### 13.9. Kết luận về mức độ liên quan

Repo `OpenBGBenchmark/OpenBG-Align` **rất liên quan tới product similarity / same-product mining**, tức phần:

```text
Sản phẩm nào tương tự với SKU này?
```

Nếu `OpenBG-IMG` phù hợp với hướng **KG link prediction**, thì `OpenBG-Align` phù hợp với hướng **multimodal product matching**.

Với repo hiện tại, nên dùng OpenBG-Align làm cơ sở để đề xuất future module:

```text
Similarity/
  text + image + category + brand + price
  -> product neighbors
  -> Agent giải thích sản phẩm tương tự
```

## 14. Đối chiếu với repo `vercel/vercel-plugin`

Repo tham khảo:

```text
https://github.com/vercel/vercel-plugin
```

`vercel-plugin` không phải là một dataset eCommerce, Product Knowledge Graph hay mô hình recommendation. Đây là plugin giúp các AI coding agent hiểu hệ sinh thái Vercel thông qua một knowledge graph dạng tài liệu, thư viện skill, agent chuyên trách, command và cơ chế truy hồi context theo ngữ cảnh.

### 14.1. Những điểm liên quan tới bài Product Knowledge

| Thành phần trong `vercel-plugin` | Bài học có thể áp dụng cho repo này |
| --- | --- |
| `vercel.md` | Tạo một tài liệu graph trung tâm mô tả entity, quan hệ, quyết định và giới hạn |
| Skills theo chủ đề | Tách năng lực Agent thành các module như `product-similarity`, `promotion-effectiveness`, `sales-explanation` |
| Agents chuyên trách | Có thể tách vai trò phân tích thành Product Analyst, Promotion Analyst và Similarity Analyst |
| Context injection theo pattern | Chỉ nạp context liên quan tới câu hỏi, tránh đưa toàn bộ dataset/documentation vào prompt |
| Retrieval ranking và budget | Ưu tiên evidence quan trọng, giới hạn số tài liệu/dòng dữ liệu trả về cho Agent |
| MCP server | Có thể mở dữ liệu/metric/graph dưới dạng tool có schema rõ ràng thay vì cho Agent đọc CSV tùy ý |
| Verification workflow | Mỗi câu trả lời cần kiểm tra lại nguồn dữ liệu, phép tính và giới hạn trước khi trả kết quả |

### 14.2. Cách chuyển mẫu “relational knowledge graph” sang eCommerce

Trong `vercel.md`, các thực thể được nối bằng quan hệ như `depends on`, `integrates with`, `alternative to`. Với dataset này, ta có thể dùng graph tương tự:

```text
Product
  -> sold_by -> Shop
  -> has_brand -> Brand
  -> in_platform_category -> PlatformCategory
  -> in_shop_category -> ShopCategory
  -> has_promotion -> Promotion
  -> has_voucher -> Voucher
  -> has_content -> Content
  -> has_sales_metric -> SalesMetric
```

Điểm quan trọng là mỗi quan hệ cần có **nguồn dữ liệu và quy tắc diễn giải**. Ví dụ:

```text
Product --in_platform_category--> PlatformCategory
source: products.catid = category_platform.category_id

Product --in_shop_category--> ShopCategory
source: product_categories.category_id = category_list.shop_category_id
scope: cùng country_code và shop_id
```

Như vậy Agent không chỉ biết tên quan hệ, mà còn biết cách kiểm chứng quan hệ đó và tránh join nhầm hai loại `category_id`.

### 14.3. Skill architecture đề xuất cho Agent

Thay vì một prompt lớn chứa toàn bộ logic, có thể tổ chức các năng lực như sau:

```text
Product Knowledge Agent
├── product-ingest
├── product-similarity
├── sales-explanation
├── promotion-effectiveness
├── category-insight
├── shop-trust-analysis
└── answer-verification
```

Mỗi skill nên định nghĩa 4 phần:

```text
Input -> Data retrieval -> Calculation -> Answer contract
```

Ví dụ `promotion-effectiveness`:

```text
Input: country/category/time scope
Retrieval: product, promotion, voucher, sales proxy
Calculation: median sales, estimated revenue, product count, baseline gap
Answer: ranking + evidence + observational limitation
```

### 14.4. Context injection cho repo này

Agent không nên luôn nạp cả `Documentation.md`, `preprocessing.md`, `research.md` và toàn bộ CSV. Có thể chọn context theo câu hỏi:

| Câu hỏi | Context ưu tiên |
| --- | --- |
| Vì sao doanh số sản phẩm A giảm? | `product_dataset_ready`, sales/price/promo features, `Research/research.md` |
| Sản phẩm nào tương tự SKU này? | product name, brand, category, variation, image URL/embedding |
| Promotion nào hiệu quả nhất? | promotion/voucher features, country/category, sales proxy, guardrails |
| Category nào đóng góp nhiều doanh thu? | platform category, shop category, revenue proxy, category mapping |

Cách này vừa giảm chi phí context, vừa làm câu trả lời dễ kiểm tra hơn. Đây là ý tưởng nên học từ cơ chế skill matching của `vercel-plugin`; không cần sao chép toàn bộ hook TypeScript của repo đó.

### 14.5. Tool contract cho AI Agent

Nếu triển khai thành ứng dụng, nên expose các thao tác phân tích bằng tool có input/output cố định:

```text
find_product(query) -> product records + confidence
compare_product_snapshots(item_id, dates) -> metric changes + evidence
find_similar_products(item_id, filters, top_k) -> ranked candidates
evaluate_promotions(scope, group_by) -> comparison table + baseline
explain_category_relation(item_id) -> platform/shop category evidence
verify_answer(evidence, calculations) -> validation result
```

Tool trả về dữ liệu có cấu trúc, chẳng hạn:

```json
{
  "metric": "estimated_recent_revenue",
  "value": 1250000,
  "unit": "VND_proxy",
  "source": "Dataset/DataProcessed/product_dataset_ready.csv",
  "observed_at": "snapshot_date",
  "caveat": "Không phải doanh thu thực tế"
}
```

Điều này giúp Agent trích dẫn evidence và giảm lỗi diễn giải tự do từ CSV.

### 14.6. Verification và guardrails

Repo tham khảo có xu hướng coi verification là một phần của workflow. Với Product Knowledge, bước kiểm tra cuối nên bắt buộc xác nhận:

1. Product có đúng `country_code`, `shop_id`, `item_id` và snapshot không.
2. Metric có được tính từ đúng cột processed không.
3. `price` không bị trừ voucher lần hai.
4. Không join `category_platform.category_id` với `product_categories.category_id` nếu thiếu mapping qua `catid`/shop category.
5. Kết luận về promotion là tương quan quan sát, không phải causal proof.
6. Câu trả lời nêu rõ khi chỉ có 3 ngày snapshot hoặc thiếu margin/order-level data.

### 14.7. MCP và triển khai production

`vercel-plugin` có ví dụ tích hợp MCP để Agent truy cập nguồn dữ liệu qua tool. Nếu triển khai Product Knowledge Agent production, có thể xây một MCP server nội bộ với các nhóm tool:

```text
product tools
category tools
promotion tools
sales analysis tools
similarity tools
```

MCP chỉ nên expose các thao tác cần thiết và read-only ở giai đoạn đầu. Không nên cho Agent chạy SQL/đọc filesystem tùy ý. Mọi tool cần:

- schema input/output rõ ràng;
- filter bắt buộc theo country/shop/date khi phù hợp;
- giới hạn số dòng và `top_k`;
- tên file hoặc query provenance;
- kiểm soát quyền truy cập dữ liệu.

### 14.8. Phần không áp dụng trực tiếp và rủi ro

Không nên đưa `vercel-plugin` vào `requirements.txt` hoặc xem nó là engine phân tích của repo này vì:

- Plugin tập trung vào coding agent và hệ sinh thái Vercel, không xử lý bảng Shopee.
- Các skill của plugin là hướng dẫn/context, không thay thế feature engineering, KG construction hay evaluation.
- Hook tự động inject context có thể làm Agent nhận quá nhiều thông tin nếu không giới hạn scope.
- Plugin có telemetry bật mặc định; nếu dùng trong môi trường dữ liệu nhạy cảm cần kiểm tra policy và tắt telemetry khi cần.
- MCP endpoint cần authentication, permission và audit nếu expose dữ liệu thật.

### 14.9. Cách phát triển repo hiện tại theo hướng `vercel-plugin`

Giai đoạn tiếp theo có thể bổ sung cấu trúc:

```text
Agent/
  agent_architecture.md
  skills/
    product_similarity.md
    promotion_effectiveness.md
    sales_explanation.md
    category_insight.md
  tools/
    product_lookup.md
    promotion_analysis.md
    similarity_search.md
  evals/
    product_questions.jsonl
    expected_evidence.jsonl
```

Mỗi câu trả lời của Agent nên được đánh giá theo 4 tiêu chí:

```text
Entity resolution -> Relation correctness -> Calculation correctness -> Explanation quality
```

### 14.10. Kết luận về mức độ liên quan

Repo `vercel/vercel-plugin` **liên quan ở tầng kiến trúc Agent và quản trị knowledge**, không liên quan trực tiếp ở tầng dữ liệu eCommerce hay thuật toán similarity.

Nên học từ repo này các nguyên tắc:

```text
relational knowledge graph
+ context theo ngữ cảnh
+ skill/tool chuyên biệt
+ verification trước khi trả lời
+ provenance và guardrails
```

Không nên copy plugin vào pipeline hiện tại. Với bài thi, đây là phần giúp giải pháp chuyển từ “CSV + notebook” thành một kiến trúc AI Agent có thể mở rộng và kiểm thử được.

## 15. Kết luận

Với folder hiện tại, giải pháp Product Knowledge phù hợp nhất là:

```text
product_dataset_ready.csv làm bảng trung tâm
+ category_platform_clean.csv để hiểu ngành hàng chuẩn
+ semantic layer định nghĩa entity/relationship/metric
+ research notebook để kiểm định insight
+ guardrails để Agent không kết luận quá mức
```

Giải pháp này đủ để AI Agent trả lời các câu hỏi về sản phẩm, category, shop, promotion, content và sales proxy, đồng thời giải thích được mối quan hệ giữa các dữ liệu thay vì chỉ trả về số liệu rời rạc.

Workflow triển khai chi tiết nằm tại `Agent/agent_workflow.md` và thiết kế evaluation tại `Agent/evaluation.md`. Giai đoạn đầu chạy local trên `Dataset/DataProcessed`; MCP chỉ là lớp adapter read-only cho MVP sau này.

## 16. Workflow triển khai được đề xuất

### 16.1. Workflow end-to-end

```text
Question
  -> Intent/entity resolution
  -> Scope validation: country/shop/date
  -> Retrieve processed rows and metadata
  -> Deterministic analysis function
  -> Evidence table
  -> Explanation with confidence and caveats
  -> Verification checks
  -> Final answer
```

Nếu không xác định được sản phẩm, date hoặc scope, Agent phải hỏi lại hoặc trả `insufficient_evidence`, không tự chọn một dòng gần đúng.

### 16.2. Ba workflow nghiệp vụ tối thiểu

```text
sales_decline:
  resolve product -> compare snapshots -> compare peers
  -> inspect price/promo/voucher/trust/content
  -> rank plausible signals -> report correlation, not causation

similar_product:
  resolve item/variation -> filter candidates
  -> score text/category/brand/price -> optional image score
  -> return top-k with score components

promotion_effectiveness:
  validate scope -> construct promo_group -> calculate metrics
  -> compare baseline -> report sample size and confounders
```

Điều kiện tối thiểu để nói “doanh số giảm” là có ít nhất hai snapshot của cùng product. Promotion chỉ được gọi là `observed association` hoặc `descriptive comparison` cho tới khi có experiment/control hoặc dữ liệu order-level.

### 16.3. Cấu trúc câu trả lời chuẩn

```text
Question
Scope
Answer
Evidence
Calculation
Likely explanation
Confidence
Limitations
Next action
```

`Evidence` phải trỏ được tới bảng, cột, bộ lọc và snapshot. `Confidence` ban đầu chỉ là mức completeness/consistency của evidence, không phải xác suất đã calibration.

### 16.4. Image pipeline

Ảnh được tải vào cache riêng, không ghi đè `DataRaw` hoặc `DataProcessed`:

```text
1. Validate URL, timeout và retry giới hạn.
2. Ghi manifest gồm item_id, URL, status, HTTP code, checksum, timestamp.
3. Kiểm tra ảnh lỗi, ảnh trùng và định dạng.
4. Bắt đầu bằng image availability/quality features.
5. Sau đó mới thử image embedding và đo lại similarity.
```

Ảnh thiếu không được tự diễn giải là content kém. Mọi kết luận dựa trên ảnh phải lưu model/version, timestamp và coverage.

### 16.5. Lộ trình MVP có MCP

```text
Local analysis functions
  -> typed input/output
  -> read-only MCP tools
  -> simple chat/API UI
  -> audit log and evaluation
```

Tool MVP: `find_product`, `compare_product_snapshots`, `find_similar_products`, `evaluate_promotions`, `explain_category_relation`, `verify_analysis`. Không expose arbitrary SQL hoặc arbitrary file path.

### 16.6. Những phần chưa được phép tự giả định

| Hạng mục | Hiện có thể nói gì | Chưa được tự khẳng định |
| --- | --- | --- |
| SKU | Proxy từ item và variation | SKU ID thật |
| Revenue | Proxy `price * monthly_sold_value` | GMV/net revenue/profit |
| Promotion | So sánh quan sát | Uplift/causal effect |
| Ảnh | URL có thể tải | Chất lượng ảnh nếu chưa đo |
| Similarity | Baseline text/category/brand/price | Same-product nếu chưa có nhãn |
| Confidence | Completeness của evidence | Calibrated probability |

Workflow local và evaluation contract được đặc tả trong `Agent/agent_workflow.md` và `Agent/evaluation.md`.
