# BUSINESS DICTIONARY & LOGIC RULES
 
**Mục đích:** Định nghĩa Data Contract (Hợp đồng dữ liệu), chuẩn hóa thuật ngữ E-commerce và thiết lập Guardrails cho AI Agent và Deterministic Pipeline.

## 1. DATA GRAIN & KEYS

Việc hiểu sai grain sẽ dẫn đến sai lệch toàn bộ phép tính tổng và phép join. Agent và Pipeline bắt buộc phải tuân thủ các định danh sau.

### Định nghĩa Hạt dữ liệu (Grain):
Một dòng duy nhất trong file `product_dataset_ready.csv` đại diện cho **1 Sản phẩm (Product)** bán tại **1 Shop** thuộc **1 Quốc gia**, được ghi nhận vào **1 Ngày cụ thể (Snapshot Date)**. Dữ liệu này nằm ở cấp độ Product, **KHÔNG PHẢI** cấp độ SKU (Mã phân loại chi tiết).

### Bộ Khóa Định Danh (Primary Keys):
- **Khóa định danh Sản phẩm (Product ID Key):** `country_code + shop_id + item_id`
- **Khóa định danh Điểm ảnh (Snapshot Key):** `country_code + shop_id + item_id + date`
- **Khóa định danh Kệ trưng bày nội bộ (Merchandising Key):** `country_code + shop_id + shop_category_id + date`

### Quy tắc Xử lý Dữ liệu Ngoại lai (Outliers):
Dữ liệu có chứa `price = 999999999` là giá trị rác/sentinel từ hệ thống crawler. Mọi pipeline tính toán toán học (Sales, Price, Revenue) **bắt buộc phải loại bỏ (Filter/Drop)** các bản ghi này trước khi phân tích.

## 2. CHUẨN HÓA THUẬT NGỮ & METRICS E-COMMERCE

Phần này định nghĩa toàn bộ metric được sử dụng trong hệ thống. Tất cả metric phải được tính thống nhất giữa Data Pipeline và AI Agent nhằm đảm bảo kết quả phân tích nhất quán.

**Naming Convention (Quy ước đặt tên):**
Các trường có hậu tố `_num` là phiên bản đã được Data Pipeline chuẩn hóa sang kiểu dữ liệu số sau bước Data Cleaning. Mọi phép tính trong tài liệu này đều sử dụng các trường `_num`. Dataset không chứa doanh thu thực tế hoặc số lượng giao dịch theo ngày. Hệ thống sử dụng các Sales Proxy Metrics được suy luận từ dữ liệu công khai của Shopee.

### 2.1. Nhóm Biến Số Doanh Số (Sales Proxy Metrics)

**Metric 1. Estimated Recent Revenue**

* **Formula:** `estimated_recent_revenue = price_num * monthly_sold_value_num`
* **Meaning:** Ước tính quy mô doanh thu của sản phẩm dựa trên giá bán hiện tại và lượng bán gần đây được Shopee hiển thị (`monthly_sold_value`).
* **Business Purpose:** Ranking sản phẩm theo quy mô doanh thu; Ranking shop; Ranking category.
* **Limitation:** Đây chỉ là Revenue Proxy, không phải doanh thu thực tế. Cấm Agent sử dụng cho báo cáo tài chính.

**Metric 2. Snapshot Sales Delta (Metric cốt lõi cho Intent Sales Decline)**

* **Formula:** `snapshot_sales_delta = history_sold_value_num(T) - history_sold_value_num(T-1)`
* **Meaning:** Đo số lượng sản phẩm bán thêm giữa hai snapshot liên tiếp. Do `history_sold_value` là giá trị lũy kế nên hiệu số giữa hai snapshot phản ánh lượng bán mới phát sinh.
* **Business Purpose:** Đánh giá hiệu suất bán hàng. Phát hiện sản phẩm bán nhanh hoặc bán chậm.
* **Limitation:** Phản ánh lượng bán giữa hai snapshot, không nhất thiết là doanh số chính xác trong 24 giờ nếu thời gian lấy mẫu bị lệch.

**Metric 3. Monthly Sold Delta**

* **Formula:** `monthly_sold_delta = monthly_sold_value_num(T) - monthly_sold_value_num(T-1)`
* **Meaning:** Đo sự thay đổi của chỉ số `monthly_sold_value` giữa hai snapshot.
* **Business Purpose:** Giải thích sự thay đổi của chỉ số hiển thị trên giao diện người dùng. Hỗ trợ AI tránh kết luận sai (ví dụ: số tháng giảm do dữ liệu cũ bị đẩy ra khỏi chu kỳ, không hẳn do hôm nay ế).
* **Limitation:** Là chỉ số do Shopee hiển thị, không phải số lượng bán phát sinh trong ngày.

### 2.2. Nhóm Biến Số Giá & Khuyến Mãi (Pricing & Promotion Taxonomy)

**Metric 4. Price Change**

* **Formula:** `price_change = price_num(T) - price_num(T-1)`
* **Meaning:** Đo mức thay đổi tuyệt đối của giá bán (Âm = giảm giá; Dương = tăng giá).
* **Business Purpose:** Theo dõi chiến lược giá, phân tích thay đổi giá của đối thủ.

**Metric 5. Price Change Percentage**

* **Formula:** `price_change_percentage = [(price_num(T) - price_num(T-1)) / price_num(T-1)] * 100%`
* **Meaning:** Đo tỷ lệ thay đổi giá giữa hai snapshot.
* **Business Purpose:** So sánh mức độ thay đổi giá tương đối giữa các sản phẩm có phân khúc giá khác nhau.

**Metric 6. Discount Amount**

* **Formula:** `discount_amount = price_original_num - price_num`
* **Meaning:** Đo số tiền được giảm trực tiếp trên mỗi sản phẩm.
* **Business Purpose:** So sánh giá trị khuyến mãi, hỗ trợ AI giải thích mức giảm giá theo giá trị tuyệt đối.

**Metric 7. Discount Point Change**

* **Formula:** `discount_point_change = discount_percent_num(T) - discount_percent_num(T-1)`
* **Meaning:** Đo sự thay đổi của mức giảm giá theo điểm phần trăm (percentage points). (Ví dụ: 20% -> 10% = -10 điểm phần trăm).
* **Business Purpose:** Theo dõi sự thay đổi độ sâu của chương trình giảm giá.

**Metric 8. Cờ Phân Loại Khuyến Mãi & Promo Groups (Quy tắc DR)**
Tuyệt đối không dùng độ dài chuỗi để xét duyệt khuyến mãi. Data Pipeline phải đánh cờ (Flag) như sau:

* **`has_promo`:** `TRUE` khi `discount_percent_num > 0`.
* **`has_voucher`:** `TRUE` khi `voucher_discount_num > 0`.
* **Bốn nhóm Promo Groups (Phục vụ phân tích hiệu quả):**
1. `no voucher/promo`: Cả hai cờ đều False.
2. `promo only`: Cờ Promo True, cờ Voucher False.
3. `voucher only`: Cờ Promo False, cờ Voucher True.
4. `voucher + promo`: Cả hai cờ đều True.

### 2.3. Nhóm Biến Số Tương Tác & Tồn Kho (Engagement & Stock Metrics)

**Metric 9. Rating Change**

* **Formula:** `rating_change = rating_num(T) - rating_num(T-1)`
* **Meaning:** Đo sự thay đổi điểm đánh giá trung bình.
* **Business Purpose:** Theo dõi chất lượng cảm nhận của khách hàng.

**Metric 10. New Rating Count**

* **Formula:** `new_rating_count = rating_count_num(T) - rating_count_num(T-1)`
* **Meaning:** Đo số lượng đánh giá mới giữa hai snapshot.
* **Business Purpose:** Đánh giá mức độ tương tác của khách hàng.

**Metric 11. Like Delta**

* **Formula:** `like_delta = liked_count_num(T) - liked_count_num(T-1)`
* **Meaning:** Đo sự thay đổi số lượt yêu thích.
* **Business Purpose:** Theo dõi mức độ quan tâm của người dùng đối với sản phẩm.

**Metric 12. Stock Status Matrix (Ma trận Trạng thái Hàng hóa)**
Đánh giá tình trạng hết hàng (`is_sold_out_bool`) qua 2 snapshot liên tiếp.

| Snapshot (T-1) | Snapshot (T) | Phân loại Trạng thái (Stock Status) |
| --- | --- | --- |
| False | False | **Available** (Đang bán bình thường) |
| False | True | **Newly Sold Out** (Vừa mới hết hàng) |
| True | False | **Restocked** (Vừa được bổ sung hàng) |
| True | True | **Still Sold Out** (Tiếp tục hết hàng) |

## 3. LOGIC ĐIỀU PHỐI 3 INTENT PHÂN TÍCH CHÍNH

### Intent 1: Sales Decline (Phân tích Doanh số Giảm)
- **Điều kiện kích hoạt:** `history_sold_value_num` (Ngày T) - `history_sold_value_num` (Ngày T-1) mang lại giá trị thấp hơn so với chu kỳ liền trước.
- **Truy xuất bắt buộc (Covariates):** Pipeline phải gọi ra các thay đổi đồng thời bao gồm chênh lệch giá (`price_change`), thay đổi điểm phần trăm khuyến mãi (`discount_point_change`), trạng thái cờ Voucher, và tình trạng hết hàng (`is_sold_out`).
- **Mức độ kết luận:** Báo cáo các yếu tố thay đổi đồng thời (Tương quan).

### Intent 2: Similar Product (Tìm kiếm Sản phẩm Tương tự)
Thuật toán lọc và xếp hạng đối thủ cạnh tranh bắt buộc đi qua 3 màng lọc (Filters) theo thứ tự ưu tiên:

1. **Lọc Cứng (Tier 1):** Bắt buộc cùng `country_code` và có giao tập hợp tại `global_catids` (Khớp ID ngành hàng cấp 2 hoặc 3).
2. **Lọc Khoảng giá (Tier 2):** Biên độ chênh lệch `price_num` không vượt quá 20% so với sản phẩm mục tiêu.
3. **Lọc Uy tín (Tier 3):** Ưu tiên hiển thị các sản phẩm thuộc shop có cờ `is_official_shop = TRUE` hoặc có cùng từ khóa chiến lược trong `product_name`.

### Intent 3: Promotion Effectiveness (Đo lường Hiệu quả Khuyến mãi)
- **Phương pháp thống kê:** So sánh **Trung vị (Median Comparison)** thay vì Trung bình (Mean) để tránh nhiễu từ các sản phẩm bán đột biến.
- **Biến số đo lường:** Tính toán `median_monthly_sold` và `median_revenue` trên 4 nhóm Promo Groups (Đã định nghĩa ở Phần 2). So sánh chéo kết quả này giữa hai thị trường VN và ID.

## 4. GUARDRAILS

Các nguyên tắc dưới đây phải được nạp trực tiếp vào System Prompt của Agent. Nếu vi phạm, câu trả lời sẽ bị đánh trượt trong bộ 60 Testcases.

### Quy tắc 1: Cấm khẳng định Nhân Quả (No Causal Inference)
- Agent không được phép sử dụng các cụm từ khẳng định tuyệt đối như "Doanh số giảm **BỞI VÌ**...", "Nguyên nhân chính là do...".
- **Văn phong bắt buộc:** *"Hệ thống ghi nhận sự sụt giảm doanh số xảy ra đồng thời với việc [Yếu tố X] giảm. Đây là bằng chứng hỗ trợ cho thấy sự liên quan, tuy nhiên chưa đủ dữ kiện để kết luận nguyên nhân - kết quả."*

### Quy tắc 2: Giới hạn Khoảng thời gian (No Forecasting)
- Dataset chỉ tồn tại dữ liệu snapshot của 3 ngày (01/07/2026 - 03/07/2026).
- **Văn phong bắt buộc:** Cấm mọi hành vi dự đoán xu hướng tuần tới, tháng tới. Phải nêu rõ *"Với dữ liệu snapshot 3 ngày, không đủ cơ sở toán học để xác định xu hướng (trend) dài hạn hay yếu tố mùa vụ (seasonality)"*.

### Quy tắc 3: Xử lý Truy vấn Ngoài Phạm vi (Out-of-Scope Handling)
- Khi user yêu cầu phân tích Lợi nhuận (Profit), Chi phí Quảng cáo (ROAS), Tỷ lệ Chuyển đổi (Conversion Rate), hoặc Hàng tồn kho (Inventory).
- **Văn phong bắt buộc:** *"Hệ thống Deterministic Analytics hiện tại hoạt động dựa trên Public E-commerce Snapshot. Các chỉ số về Profit, Inventory, Traffic là dữ liệu nội bộ không nằm trong phạm vi truy xuất của cơ sở dữ liệu này."*