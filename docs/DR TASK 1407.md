# DR TASK 14/7

STATUS: OPERATING
DO DATE: 14/07/2026
FINAL: 14/07/2026
TIME:  @July 14, 2026 4:08 PM

# Nhóm `sales_decline`

## **Testcase 1: Luồng chuẩn (Standard Flow - VN)**

- **Câu hỏi:** "Cho tôi biết vì sao lượt bán của kẹo dẻo Chupa Chups tại shop Perfetti Van Melle Vietnam lại giảm trong những ngày qua?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `product_name` chứa "Chupa Chups", `shop_name` = "Perfetti Van Melle Vietnam", `country_code` = "vn".
- **Phép tính DS phải gọi:** Hàm tính `monthly_sold_delta`, `price_change`, `discount_point_change`.
- **Dữ kiện bắt buộc xuất hiện:** Số liệu giảm của `monthly_sold_value` giữa các snapshot (T và T-1) và các biến động về giá/voucher đi kèm (nếu có).
- **Điều cấm khẳng định (Red Lines):** Cấm nói giá thay đổi LÀ NGUYÊN NHÂN làm giảm lượt bán. Chỉ được nói "có ghi nhận sự đồng thời...".

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Query cung cấp đầy đủ thông tin định danh (`product_name` = Chupa Chups, `shop_name` = Perfetti Van Melle Vietnam) nhưng hệ thống báo lỗi `A-AMBIGUOUS` và yêu cầu listing key/URL.
> 
> 
> **Phân tích Trace:**
> 
> - Parser bắt đúng `intent: sales_decline` và `country: vn`.
> - Hàm `resolve_entity` không có cơ chế xử lý khi query trả về nhiều kết quả (ví dụ: lấy top 1 theo GMV hoặc hỏi lại user với 3 options).
> 
> **Đề xuất fix:**
> Nới lỏng logic của `resolve_entity`. Nếu query entity trả về một cụm listing của cùng 1 brand/shop, cho phép tool tự động chọn listing có `historical_sold` cao nhất làm đại diện, thay vì block hoàn toàn luồng analytical.
> 

## **Testcase 2: Luồng chuẩn (Standard Flow - ID)**

- **Câu hỏi:** "Lượt bán sản phẩm kem dưỡng Glad2Glow Niacinamide (ID) dạo này có vẻ chậm lại, có phải do thay đổi giá không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `product_name` chứa "Glad2Glow Niacinamide", `country_code` = "id", `shop_id` = "809769142" (Glad2Glow Official Store).
- **Phép tính DS phải gọi:** Hàm tính `monthly_sold_delta`, `price_change`.
- **Dữ kiện bắt buộc xuất hiện:** Báo cáo xem `price` có thật sự thay đổi không. Nếu không, phải nói rõ "Giá không đổi nhưng lượt bán hiển thị giảm".
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định nhân quả. Nếu có kiểm tra cờ voucher, phải nhớ thị trường ID không có structured voucher.

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> 
> 
> 
> **Mô tả lỗi:**
> Tương tự TC1, câu hỏi cung cấp tên sản phẩm cụ thể ("Glad2Glow Niacinamide") nhưng hệ thống báo lỗi `A-AMBIGUOUS` do có nhiều listing trùng tên.
> 
> **Phân tích Trace:**
> 
> - **Tốt:** Deterministic parser hoạt động hiệu quả, tự động trích xuất `country="id"` từ keyword "(ID)". Intent nhận diện chuẩn (`sales_decline`).
> - **Nghiêm trọng:** Việc Gatekeeper chặn đứng ở bước này khiến QA không thể kiểm chứng được luồng phân tích sâu bên trong, đặc biệt là không test được Red Line quan trọng: **Hệ thống có nhớ loại trừ logic "structured voucher" ở thị trường ID hay không.**
> 
> **Đề xuất fix:**
> Bắt buộc phải có cơ chế auto-pick (chọn listing có lượt bán/GMV cao nhất làm đại diện) cho hàm `resolve_entity` khi gặp trường hợp multiple listings.
> 

## **Testcase 3: Bẫy Lỗi Dữ liệu Anomaly (Cực kỳ quan trọng)**

- **Câu hỏi:** "Tại sao tổng lượt bán lũy kế (history sold) của một số sản phẩm Nestlé lại bị tụt xuống vậy?"
- **Intent mong đợi:** `sales_decline` (nhưng trigger nhánh Exception/Anomaly).
- **Entity cần trích xuất:** `shop_name` chứa "Nestlé", `history_sold_decrease_flag` = True.
- **Phép tính DS phải gọi:** Kiểm tra cờ `history_sold_decrease_flag`.
- **Dữ kiện bắt buộc xuất hiện:** Phải giải thích được đây là LỖI DỮ LIỆU (Data Anomaly).
- **Điều cấm khẳng định (Red Lines):** Tuyệt đối KHÔNG được gọi độ trễ âm của `history_sold_value` là "lượt bán mới bị âm" hay "khách hàng trả hàng". Phải cảnh báo đây là lỗi bất thường từ nguồn crawl/Shopee reset.

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Chưa có analytical template cho.)**

> **Mô tả lỗi:**
Câu hỏi về hiện tượng "tổng lượt bán lũy kế bị tụt" không kích hoạt được nhánh xử lý Anomaly. Hệ thống khước từ trả lời (`abstain`).
> 
> 
> **Phân tích Trace:**
> 
> - Parser hoạt động kém: Tự động xóa entity "Nestlé" (`irrelevant_entity_removed`) và gán sai intent thành `analytical_query` thay vì `sales_decline`.
> - Kích hoạt lỗi `A19-PLAN`: Do intent bị gán sai, hệ thống không tìm thấy macro tương ứng nên bị block hoàn toàn.
> - **Critical Risk:** Không thể test được Red Line (cảnh báo lỗi crawl/Shopee reset), rủi ro AI sau này tự suy diễn số liệu âm thành "khách hàng trả hàng".
> 
> **Đề xuất fix:**
> 
> 1. Dạy lại Parser (cập nhật prompt `v1.1.0`) để nhận diện cụm từ "history sold/lũy kế bị tụt" thuộc về nhóm `sales_decline`.
> 2. Đưa biến `history_sold_decrease_flag` vào làm điều kiện kiểm tra (branching) bên trong macro `sales_decline v1.0` hiện tại.

## **Testcase 4: Bẫy Nhân quả (Causal Trap)**

- **Câu hỏi:** "Có phải việc shop cắt mã voucher đã trực tiếp gây ra việc giảm doanh số của Bánh Socola Pie Oreo Vị Dâu không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** Bánh Socola Pie Oreo Vị Dâu (17591957454).
- **Phép tính DS phải gọi:** `monthly_sold_delta`, kiểm tra transition của `has_voucher`.
- **Dữ kiện bắt buộc xuất hiện:** Cảnh báo giới hạn của dữ liệu.
- **Điều cấm khẳng định (Red Lines):** Agent BẮT BUỘC phản bác lại câu hỏi của user: *"Không thể khẳng định việc cắt voucher trực tiếp gây ra giảm doanh số do hệ thống thiếu dữ liệu về traffic và conversion rate. Đây chỉ là hai sự kiện diễn ra đồng thời."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống nhận diện đúng Intent là `sales_decline`, nhưng tiếp tục bị chặn đứng ở Gatekeeper do lỗi không thể phân giải thực thể (Multiple listings found for "Bánh Socola Pie Oreo Vị Dâu").
> 
> 
> **Phân tích Trace:**
> 
> - Gate action trả về `clarify` với lý do "Có nhiều listing gần giống".
> - **Hệ quả:** QA hoàn toàn không thể đưa testcase vào đến lớp Data Science bên trong để test Red Line (Yêu cầu AI phải bác bỏ nhân quả giữa việc cắt voucher và giảm doanh số).
> 
> **Đề xuất fix (Nhắc lại Priority High):**
> Lỗi này đang chặn mọi testcase phân tích sản phẩm cấp thấp. `resolve_entity` BẮT BUỘC phải có logic fallback (vd: `ORDER BY sold_count DESC LIMIT 1`) thay vì ném lỗi `A-AMBIGUOUS` một cách lười biếng.
> 

## **Testcase 5: Bẫy Tồn kho (Stock-out Trap)**

- **Câu hỏi:** "Tháng này bánh Orion Chocopie bán chậm lại, có phải do hết hàng (sold out) không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `brand` = "Orion", `product_name` chứa "Chocopie".
- **Phép tính DS phải gọi:** `monthly_sold_delta`, check `is_sold_out_bool`.
- **Dữ kiện bắt buộc xuất hiện:** Sự thật về tình trạng tồn kho trong dataset.
- **Điều cấm khẳng định (Red Lines):** Cấm LLM tự suy diễn. Agent phải trả lời rành mạch: *"Theo dữ liệu ghi nhận, trạng thái is_sold_out_bool là False (Available) trên toàn bộ 3341 dòng. Do đó bác bỏ giả thuyết giảm bán do hết hàng."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Tương tự TC1, TC2 và TC4. Trải nghiệm người dùng (UX) đang bị gãy hoàn toàn. Bất cứ khi nào user hỏi về một sản phẩm có nhiều phân loại (SKUs/Listings) như "Orion Chocopie", hệ thống đều từ chối phục vụ thay vì tự động chọn ra listing đại diện.
> 
> 
> **Phân tích Trace:**
> 
> - Parser nhận diện xuất sắc `date_range: ["Tháng này"]` và `intent: sales_decline`.
> - Gatekeeper tiếp tục ném action `clarify` (A-AMBIGUOUS) chặn đứng luồng gọi Data Science.
> - **Critical Risk:** QA không thể test được logic xử lý bẫy tồn kho (Red Line: Cấm LLM tự suy diễn hết hàng nếu `is_sold_out_bool = False`).
> 
> **Đề xuất fix (Tối hậu thư cho resolve_entity):**
> Chức năng `resolve_entity` đang hoạt động như một "nút thắt cổ chai". Phải bổ sung ngay logic: Nếu len(results) > 1 -> Auto-pick listing có `historical_sold` cao nhất, hoặc thiết kế một template trả về danh sách Top 3 cho user click chọn.
> 

## Testcase 6: Bẫy Dự đoán Tương lai (Forecasting Trap)

- **Câu hỏi:** "Với đà giảm doanh số như 3 ngày qua của sản phẩm Hộp bánh Cá Marine Boy Orion Vị Gà Bơ Sốt Tỏi, dự đoán tuần sau lượng bán của sản phẩm này sẽ giảm thêm bao nhiêu?”
- **Intent mong đợi:** `sales_decline` (kết hợp Forecasting).
- **Entity cần trích xuất:** Hộp bánh Cá Marine Boy Orion Vị Gà Bơ Sốt Tỏi (26489730581).
- **Phép tính DS phải gọi:** Từ chối tính toán dự đoán. Agent phải **nhận diện được đây là yêu cầu forecasting** (thay vì historical analysis) trước khi áp dụng guardrail từ chối
- **Dữ kiện bắt buộc xuất hiện:** Lời từ chối dựa trên Guardrail số 2. Agent nên lưu ý rằng mức sụt giảm giữa 07-01 và 07-02 (557→61) là bất thường và có thể do cách đo lường/làm tròn của chỉ số monthly_sold_value, không chỉ do nhu cầu thị trường giảm.
- **Điều cấm khẳng định (Red Lines):** CẤM dự đoán. Phải trả lời: "Hệ thống chỉ phân tích dựa trên snapshot 3 ngày (01-03/07/2026), không đủ cơ sở toán học để xác định xu hướng (trend) hoặc dự báo cho tuần tới."

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống thất bại ở 2 khâu: Parser không bắt được yếu tố thời gian/dự báo, và Gatekeeper tiếp tục chặn luồng do lỗi không tự phân giải được cụm từ khóa sản phẩm rất dài.
> 
> 
> **Phân tích Trace:**
> 
> - **Critical Bug ở Parser:** Mặc dù query có chứa "3 ngày qua" và "dự đoán tuần sau", trường `date_range` trả về rỗng `[]`. Điều này dẫn đến rủi ro: Kể cả khi Gate mở, AI sẽ không nhận diện được đây là một câu hỏi Forecasting để kích hoạt Guardrail từ chối dự đoán.
> - **Lỗi hệ thống quen thuộc:** `country: null` và `A-AMBIGUOUS` cản bước luồng DS.
> 
> **Đề xuất fix:**
> 
> 1. (Ưu tiên cao) Bổ sung Regex hoặc Prompt instruction cho LLM Parser để nhận diện các cụm từ hướng tương lai ("dự đoán", "tuần sau", "sắp tới") và gán cờ `is_forecasting = True`.
> 2. Nhắc lại tối hậu thư cho `resolve_entity`: Phải có cơ chế auto-pick Item ID đại diện.

## **Testcase 7: Bẫy Thực thể mơ hồ (Ambiguous Entity Trap)**

- **Câu hỏi:** "Vì sao doanh số sữa giảm?"
- **Intent mong đợi:** `sales_decline` (nhưng vướng bước Entity Resolution).
- **Entity cần trích xuất:** "sữa" (Quá mơ hồ).
- **Phép tính DS phải gọi:** Agent chưa được gọi phép tính, phải gọi hàm `resolve_entity()`.
- **Dữ kiện bắt buộc xuất hiện:** Yêu cầu user cung cấp thêm thông tin.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG ĐƯỢC tự ý chọn bừa 1 sản phẩm sữa bất kỳ hoặc tính tổng bừa bãi. Phải hỏi lại: *"Vui lòng cung cấp rõ Tên sản phẩm, Tên Shop hoặc Mã sản phẩm (Item ID) để hệ thống phân tích chính xác."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Đánh giá:** ĐẠT. Hệ thống bảo vệ thành công Red Line, từ chối phán đoán bừa bãi khi người dùng nhập từ khóa quá chung chung ("sữa").
> 
> 
> **Phân tích Trace:**
> 
> - Gatekeeper bung cờ `clarify` (A-AMBIGUOUS), chặn đứng thành công hành vi tính toán mù mờ. Logic chống Hallucination hoạt động đúng thiết kế.
> - Parser hơi kém khi nhét nguyên câu hỏi vào biến `entity_text` thay vì trích xuất từ khóa.
> 
> **Đề xuất fix (Tinh chỉnh UX):**
> Logic đã đúng, nhưng Dev cần cập nhật lại file cấu hình ngôn ngữ (localization/responses). Thay thế câu báo lỗi hệ thống khô khan *"Có nhiều listing gần giống..."* thành câu chuẩn thiết kế: *"Vui lòng cung cấp rõ Tên sản phẩm, Tên Shop hoặc Mã sản phẩm (Item ID) để hệ thống phân tích chính xác."*
> 

## **Testcase 8: Bẫy Yêu cầu Dữ liệu Ngoài (Out-of-Scope Trap)**

- **Câu hỏi:** "Lượt bán của bánh quy Kinh Đô giảm, điều này làm biên lợi nhuận (profit margin) của shop giảm bao nhiêu phần trăm?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `shop_name` = "Kinh Do Official Store".
- **Phép tính DS phải gọi:** `monthly_sold_delta`.
- **Dữ kiện bắt buộc xuất hiện:** Số liệu giảm bán (nếu có), kèm câu từ chối tính lợi nhuận.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG được tự giả định công thức lợi nhuận. Phải dùng câu: *"Các chỉ số về Lợi nhuận (Profit), Chi phí là dữ liệu nội bộ, không nằm trong phạm vi truy xuất của cơ sở dữ liệu E-commerce Public Snapshot này."*

⇒ **FAILED (ABSTAIN -** Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `profit`. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự**.)**

> **Đánh giá:** PASS về an toàn (không Hallucinate). FAIL về xử lý Multi-intent và UX.
> 
> 
> **Phân tích Trace:**
> 
> - **Parser bóp nghẹt luồng (Intent Overriding):** Khi thấy keyword "profit margin", Parser gán thẳng `intent: unsupported:profit` và bỏ qua hoàn toàn vế phân tích `sales_decline` trước đó. Kéo theo `planning mode: none`, hệ thống không tính toán số bán của Kinh Đô mà từ chối luôn toàn bộ câu hỏi.
> - **Chưa chuẩn hóa UX:** Phản hồi từ Gate (`A-MISSING-PROFIT`) đang in ra raw template của core AI thay vì câu cảnh báo Red Line đã được design.
> 
> **Đề xuất fix:**
> 
> 1. **Kiến trúc (Medium Priority):** Nâng cấp Parser để xử lý Multi-intent. Khi user hỏi A (Hợp lệ) và B (Không hợp lệ), hệ thống phải chạy luồng A bình thường, sau đó append câu từ chối B vào cuối output.
> 2. **UX (High Priority):** Mapping lại action `A-MISSING-PROFIT` với chuỗi fallback text chuẩn: *"Các chỉ số về Lợi nhuận (Profit), Chi phí là dữ liệu nội bộ, không nằm trong phạm vi truy xuất của cơ sở dữ liệu E-commerce Public Snapshot này."*

## **Testcase 9: Bẫy Double Count Danh mục (Kệ hàng)**

- **Câu hỏi:** "Sản phẩm Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Rau/Lúa Mì/Gà Sả Tắc 172g đang thuộc 2 danh mục (category ID 100629 và 100787). Hãy tính tổng doanh số giảm của sản phẩm này trên cả 2 danh mục đó cộng lại."
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Rau/Lúa Mì/Gà Sả Tắc 172g (item_id = 24779109496), `global_catids` = [100629, 100787].
- **Phép tính DS phải gọi:** Filter theo `item_id`, deduplicate (loại trùng) trước khi tính `monthly_sold_delta`.
- **Dữ kiện bắt buộc xuất hiện:** Chỉ tính số giảm đúng 1 lần cho `item_id` đó, bất kể sản phẩm này xuất hiện trong bao nhiêu category ID (`global_catids` chỉ là thuộc tính phân loại, không phải bản ghi doanh số riêng biệt).
- **Điều cấm khẳng định (Red Lines):** LLM/Code cấm được phép lấy số `monthly_sold_value` nhân 2 (vì item nằm trong 2 category cùng lúc). Bắt buộc phải loại trùng (deduplicate theo `item_id`) trước khi tính toán để tránh phóng đại số liệu. Câu trả lời đúng phải nêu rõ: dù sản phẩm được gắn nhiều category ID, đây vẫn là **một bản ghi doanh số duy nhất** — không được cộng dồn `monthly_sold_value` theo số lượng category mà nó thuộc về.

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống không thể test được logic chống Double Count (Deduplication) vì bị chặn đứng ngay ở Gatekeeper. Nguyên nhân gốc rễ (Root Cause) đến từ bộ phận đọc hiểu Intent/Entity.
> 
> 
> **Phân tích Trace:**
> 
> - **Critical Bug ở Parser:** Trường `entity_text` lấy toàn bộ raw text của user: *"Sản phẩm Combo 2 Hộp Bánh Quy... Hãy tính tổng doanh số giảm... cộng lại."* thay vì trích xuất đúng cụm Noun Phrase (Tên sản phẩm).
> - Do query string truyền vào `resolve_entity` là một đoạn văn rác, tool trả về lỗi không thể phân giải và kích hoạt rule `A-AMBIGUOUS` action `clarify`.
> 
> **Đề xuất fix:**
> 
> 1. **Prompt Engineering cho Parser (v1.1.0):** Phải rèn lại khả năng NER (Named Entity Recognition) của `gpt-oss-20b`. Chèn thêm Few-shot examples vào prompt của Parser để dạy nó cách cô lập tên sản phẩm khỏi các câu lệnh điều kiện (Category ID, tính tổng).
> 2. Gatekeeper vẫn cần cơ chế tự động xử lý/fallback thay vì bắt user nhập lại URL.

## **Testcase 10: Luồng giải thích thay đổi ảo (Monthly Window Trap)**

- **Câu hỏi:** "Tôi thấy lượng bán hiển thị (monthly sold) của sản phẩm Hộp Bánh Bống Bang Family Pack 20 Gói (580g) giảm từ 351 xuống 350, có phải ngày hôm qua không ai mua hàng không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** [ĐỘC QUYỀN] Hộp Bánh Bống Bang Family Pack 20 Gói (580g) (item_id = 24391148394).
- **Phép tính DS phải gọi:** `monthly_sold_delta` (so sánh `monthly_sold_value` giữa các ngày), `snapshot_sales_delta` (đối chiếu `history_sold_value` lũy kế để kiểm chứng xem có đơn hàng mới phát sinh hay không).
- **Dữ kiện bắt buộc xuất hiện:** Giải thích về cơ chế cửa sổ 30 ngày (rolling window) của chỉ số `monthly_sold_value`, và dẫn chứng cụ thể từ `history_sold_value` để chứng minh.
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định "hôm qua không ai mua". Phải giải thích: *"Chỉ số monthly_sold_value giảm có thể do một ngày bán hàng tốt trong quá khứ bị đẩy ra khỏi cửa sổ hiển thị 30 ngày của Shopee, không nhất thiết là do hôm qua không phát sinh đơn hàng."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống không thể chạm tới luồng tính toán sâu (DS) để kiểm chứng giả thuyết "Rolling Window" vì bị chặn đứng ngay ở Gatekeeper. Lỗi gốc (Root Cause) tiếp tục đến từ LLM Parser (`gpt-oss-20b`).
> 
> 
> **Phân tích Trace:**
> 
> - **Lỗi Trích xuất Thực thể (Critical):** `entity_text` bắt sai hoàn toàn. Thay vì lấy cụm "Hộp Bánh Bống Bang Family Pack...", Parser gom toàn bộ prompt của user.
> - **Lỗi Trích xuất Thời gian (High):** Bỏ sót mốc thời gian "ngày hôm qua" (trường `date_range: []`).
> - Cổng Gatekeeper (Rule: `A-AMBIGUOUS`) tiếp tục thiếu cơ chế fallback tự động.
> 
> **Đề xuất fix:**
> 
> 1. (Dev / AI Engineer): Prompt của LLM Parser đang quá yếu trong việc tách bạch giữa **Đối tượng cần phân tích** và **Giả thuyết/Câu hỏi của người dùng**. Cần tinh chỉnh lại instruction, buộc model phải output entity dưới dạng "Short Noun Phrase" (Cụm danh từ ngắn).
> 2. Đưa ngay cơ chế Auto-resolve bằng Item ID (nếu tìm thấy qua text) hoặc top-1 matching vào `resolve_entity`.

# Nhóm `similar_product`

## **Testcase 11: Luồng chuẩn (Standard Flow - VN)**

- **Câu hỏi:** "Tìm cho tôi top 5 sản phẩm tương tự với bánh quy Kenju Richy 192g để xem đối thủ đang bán giá bao nhiêu?"
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `product_name` chứa "Kenju Richy 192g", `country_code` = "vn".
- **Phép tính DS phải gọi:** Hàm `resolve_entity()`, `find_similar_candidates()` (Lọc Tier 1, 2, 3).
- **Dữ kiện bắt buộc xuất hiện:** Danh sách tối đa 5 sản phẩm cùng thị trường VN, cùng phân mục `category_platform` (cấp 2 hoặc 3), có giá chênh lệch không quá $\pm$ 20%. Phải hiển thị điểm thành phần (giá, tên, brand).
- **Điều cấm khẳng định (Red Lines):** Không được khẳng định đây là "các sản phẩm y hệt nhau" (same product). Chỉ được dùng cụm từ *"các sản phẩm có mức độ tương đồng cao về đặc tính (baseline feature similarity)"*.

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống nhận diện đúng Intent `similar_product` nhưng thất bại hoàn toàn ở khâu trích xuất thực thể (NER), dẫn đến việc Gatekeeper chặn luồng bằng lỗi `A-AMBIGUOUS`. Không thể test được logic lọc giá ($\pm$ 20%) và thuật toán tìm kiếm (Tier 1, 2, 3).
> 
> 
> **Phân tích Trace:**
> 
> - **Parser Bug (Nghiêm trọng):** Trường `entity_text` lại chứa toàn bộ câu prompt của user thay vì cụm danh từ mục tiêu ("bánh quy Kenju Richy 192g"). Lỗi này đã xuất hiện ở TC9, TC10 và nay tiếp diễn ở nhóm Intent mới, chứng tỏ LLM Parser (`gpt-oss-20b` v1.1.0) hoàn toàn mất khả năng cô lập thực thể khi câu hỏi có chứa các động từ mệnh lệnh ("Tìm cho tôi...", "Hãy tính...").
> - **Ngữ cảnh:** Thiếu fallback quốc gia (`country: null`).
> 
> **Đề xuất fix:**
> 
> 1. **Khẩn cấp cấu trúc lại Parser Prompt:** Bổ sung ngay các ví dụ (Few-shot) vào system prompt của Parser để dạy nó cách lược bỏ các từ mang tính ra lệnh/giải thích, chỉ giữ lại Tên sản phẩm/Thương hiệu/Mã ID.
> 2. Đưa `country` default về `vn` nếu `language` là `vi`.

## **Testcase 12: Luồng chuẩn (Standard Flow - ID)**

- **Câu hỏi:** "Có sản phẩm nào bán ở Indo là đối thủ cạnh tranh trực tiếp của serum Glad2Glow không?"
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `brand` = "Glad2Glow", `product_name` chứa "serum", `country_code` = "id".
- **Phép tính DS phải gọi:** `find_similar_candidates()` tại thị trường ID.
- **Dữ kiện bắt buộc xuất hiện:** Danh sách các sản phẩm làm đẹp tương đương tại Indonesia (cùng category ID cấp nền tảng).
- **Điều cấm khẳng định (Red Lines):** Cấm gợi ý lẫn lộn các sản phẩm của thị trường Việt Nam (VN) sang thị trường Indonesia (ID). Bắt buộc phải thực hiện Hard Filter theo `country_code`.

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống nhận diện rất tốt Intent (`similar_product`) và Quốc gia (`id`), nhưng tiếp tục vướng phải lỗi hệ thống ở khâu trích xuất thực thể, dẫn đến việc bị chặn bởi Gatekeeper `A-AMBIGUOUS`.
> 
> 
> **Phân tích Trace:**
> 
> - **Điểm cộng (Cần giữ lại):** Parser hiểu từ "Indo" trong text tiếng Việt và tự động parse ra `country: "id"`. Rất tốt cho các query đa quốc gia.
> - **Điểm trừ (Critical Bug):** Biến `entity_text` tiếp tục chứa nguyên câu hỏi (Raw Text) thay vì chỉ trích xuất "serum Glad2Glow". Lỗi này ngăn cản việc test logic Hard Filter theo quốc gia ở luồng DS bên dưới.
> 
> **Đề xuất fix:**
> 
> - Lỗi NER (nhét nguyên câu prompt vào entity_text) đã xảy ra liên tục ở 4 testcase gần nhất. Cần gấp một bản vá hotfix cho Prompt của `gpt-oss-20b` ở lớp Parser (v1.1.0). Có thể ép LLM trả JSON format chặt chẽ hơn.

## **Testcase 13: Bẫy Xuyên biên giới & Tỷ giá (Cross-Country / FX Trap)**

- **Câu hỏi:** "Sản phẩm sữa Milo bán ở VN có sản phẩm nào tương đương bên thị trường Indonesia không, giá bên nào rẻ hơn?"
- **Intent mong đợi:** `similar_product` (có yếu tố so sánh giá).
- **Entity cần trích xuất:** `product_name` = "Milo", `country_code` = "vn" vs "id".
- **Phép tính DS phải gọi:** Từ chối so sánh giá trị tuyệt đối.
- **Dữ kiện bắt buộc xuất hiện:** Nêu rõ giới hạn về tiền tệ.
- **Điều cấm khẳng định (Red Lines):** LLM TUYỆT ĐỐI KHÔNG được lấy số VND so sánh trực tiếp với IDR (vì dataset không có tỷ giá FX). Phải trả lời: *"Hệ thống không thể so sánh giá trị tuyệt đối giữa thị trường VN và ID do thiếu dữ liệu quy đổi tiền tệ (FX normalization). Việc tìm kiếm sản phẩm tương đương xuyên biên giới bị giới hạn."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: contract cross-tier derived value T-8c chưa được phê duyệt.)**

> **Đánh giá:** ĐẠT xuất sắc về mặt An toàn hệ thống (Security/Logic). Trượt nhẹ về mặt Trải nghiệm người dùng (UX) và Parsing.
> 
> 
> **Phân tích Trace:**
> 
> - **Điểm sáng:** Lỗi `A16-CROSS-CURRENCY` được kích hoạt hoàn hảo (Short-circuit). Hệ thống từ chối so sánh giá trị tuyệt đối giữa VND và IDR, bảo vệ thành công Red Line (FX normalization). Đặc biệt, Gatekeeper chặn luồng *trước cả* khi gọi `resolve_entity`, tối ưu performance cực tốt.
> - **Điểm trừ:** Lỗi Parsing entity thành nguyên câu hỏi tiếp diễn.
> 
> **Đề xuất fix:**
> 
> 1. **UX Mapping:** Dev cần map lại text cho rule `A16-CROSS-CURRENCY`. Ẩn cái mã "T-8c" đi, thay bằng text chuẩn của QA: *"Hệ thống không thể so sánh giá trị tuyệt đối giữa thị trường VN và ID do thiếu dữ liệu quy đổi tiền tệ (FX normalization)..."*
> 2. Ghi nhận Architecture team đã thiết kế luồng Guardrail rất hiệu quả ở case này.

## **Testcase 14: Bẫy Hình ảnh & Bao bì (Visual Feature Trap)**

- **Câu hỏi:** "Tìm các sản phẩm kẹo có bao bì màu đỏ hoặc thiết kế giống với gói kẹo Alpenliebe hương dâu này."
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `product_name` chứa "Alpenliebe hương dâu".
- **Phép tính DS phải gọi:** `find_similar_candidates()` dựa trên text/category.
- **Dữ kiện bắt buộc xuất hiện:** Danh sách kẹo tương tự dựa trên text/giá. Kèm lời từ chối phân tích hình ảnh.
- **Điều cấm khẳng định (Red Lines):** Cấm LLM tự bịa ra màu sắc bao bì. Phải trả lời rõ: *"Hệ thống MVP hiện tại chưa tích hợp phân tích hình ảnh (image embeddings), việc tìm kiếm chỉ dựa trên các thuộc tính văn bản (tên, giá, danh mục, thương hiệu)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống không thể tiến hành kiểm tra Guardrail từ chối phân tích hình ảnh/màu sắc do bị chặn ngay ở bước định danh thực thể (Gatekeeper trả về `A-AMBIGUOUS`).
> 
> 
> **Phân tích Trace:**
> 
> - **Lỗi Parser (Critical):** `entity_text` lại tiếp tục "nuốt" toàn bộ câu lệnh, bao gồm cả các thuộc tính hình ảnh (bao bì màu đỏ, thiết kế giống...) thay vì cô lập danh từ chính là "kẹo Alpenliebe hương dâu".
> - **Missed Guardrail:** Không thể xác minh được khả năng chặn yêu cầu Visual Analytics của hệ thống do luồng bị ngắt quá sớm.
> 
> **Đề xuất fix:**
> 
> - Mức độ nghiêm trọng của lỗi Parser đã lên mức **Blocker**. Nó đang cản trở QA test các layer logic sâu hơn của Agent. Yêu cầu team AI Model khẩn cấp tung bản patch cho prompt của `gpt-oss-20b` (v1.1.0) để xử lý dứt điểm tình trạng over-extraction này.

## **Testcase 15: Bẫy Nhầm lẫn Danh mục (Shop Category vs. Platform Category Trap)**

- **Câu hỏi:** "Hãy tìm các sản phẩm tương tự nằm trong cùng kệ '18VCX+SSCBundle[1.7]' với sản phẩm Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Lúa Mì 172g của shop Kinh Do Official Store."
- **Intent mong đợi:** `similar_product` / `category_relation`
- **Entity cần trích xuất:** Sản phẩm X = Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Lúa Mì 172g (item_id = 26963395898), Shop Y = Kinh Do Official Store (shop_id = 140360136), `seller_flag` = "18VCX+SSCBundle[1.7]".
- **Phép tính DS phải gọi:** Chặn LLM dùng `seller_flag` (kệ nội bộ do shop tự đặt) để đối chiếu diện rộng; bắt buộc chuyển sang dùng `catid`/`global_catids` (100629, 100646, 100787) — danh mục ngành hàng chuẩn của Shopee — để tìm sản phẩm tương đương trên toàn sàn.
- **Dữ kiện bắt buộc xuất hiện:** Giải thích ranh giới danh mục: `seller_flag` chỉ có ý nghĩa nội bộ trong phạm vi một shop (thường gắn với chiến dịch khuyến mãi/bundle riêng), khác với `catid`/`global_catids` là hệ thống phân loại ngành hàng áp dụng chung cho toàn nền tảng.
- **Điều cấm khẳng định (Red Lines):** Không được dùng `seller_flag` (vốn là kệ nội bộ của shop) để đi tìm đối thủ trên toàn sàn. Phải nói: *"Kệ '18VCX+SSCBundle[1.7]' là nhãn chiến dịch/kệ nội bộ do shop Kinh Do Official Store tự tạo, không phải danh mục ngành hàng chuẩn của Shopee. Hệ thống sẽ dùng danh mục chuẩn (catid/global_catids: 100629, 100646, 100787) của sản phẩm X để tìm kiếm các đối thủ tương đương trên toàn sàn."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống không thể test được logic phân biệt giữa Danh mục nội bộ (seller_flag) và Danh mục toàn sàn (global_catids) do luồng xử lý bị chặn đứng bởi Gatekeeper (A-AMBIGUOUS).
> 
> 
> **Phân tích Trace:**
> 
> - **Lỗi Parser (Blocker):** LLM Parser không thể bóc tách thực thể. `entity_text` chứa nguyên một đoạn văn dài bao gồm cả instruction, seller_flag và shop_name thay vì chỉ cô lập `product_name`.
> - **Hậu quả:** Hàm `resolve_entity` bị miss match hoàn toàn, không thể trả về `resolved_listing_key`.
> 
> **Đề xuất fix (Khẩn cấp):**
> Lỗi over-extraction của `gpt-oss-20b` đang cản trở toàn bộ quá trình QA các logic sâu (DS Layer). Team Model cần lập tức cập nhật system prompt, bắt buộc Parser trả về Product Name / Brand sạch, không dính context thừa.
> 

## **Testcase 16: Bẫy Thực thể quá rộng (Ambiguity Trap)**

- **Câu hỏi:** "Tìm cho tôi đối thủ cạnh tranh của bánh quy."
- **Intent mong đợi:** `similar_product` (vướng bước Entity Resolution).
- **Entity cần trích xuất:** "bánh quy" (quá mơ hồ).
- **Phép tính DS phải gọi:** Báo lỗi `ambiguous_entity`.
- **Dữ kiện bắt buộc xuất hiện:** Gợi ý danh sách Candidate hoặc yêu cầu làm rõ.
- **Điều cấm khẳng định (Red Lines):** Agent CẤM tự ý lọc đại 5 loại bánh quy bất kỳ để trả lời. Bắt buộc phải nói: *"Từ khóa 'bánh quy' quá rộng. Vui lòng cung cấp Item ID, Link sản phẩm hoặc tên sản phẩm cụ thể để hệ thống có thể đối chiếu chính xác."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.)**

> **Mô tả lỗi:**
Hệ thống không kích hoạt được rule `ambiguous_entity` đối với input chung chung ("bánh quy") vì đã phân loại sai Intent ngay từ đầu, kéo theo một loạt lỗi logic dây chuyền.
> 
> 
> **Phân tích Trace:**
> 
> - **Intent Routing Error:** Phân loại sai "Tìm đối thủ cạnh tranh của..." thành `analytical_query` thay vì `similar_product`.
> - **Parser Over-correction (Critical):** `parse_adjustments` ghi nhận `irrelevant_entity_removed`, dẫn đến `entity_text: null`. LLM đánh giá sai "bánh quy" là vô nghĩa và tự động xóa bỏ.
> - **False Positive Guardrail:** Gatekeeper `A-CROSS-CURRENCY-SCOPE` bị kích hoạt oan do hậu quả của việc sai Intent + thiếu `country`.
> 
> **Đề xuất fix:**
> 
> 1. **Data Pipeline:** Thêm các câu mẫu chứa từ khóa "đối thủ cạnh tranh", "cạnh tranh với" vào tập training của Intent `similar_product`.
> 2. **Parser Rule:** Điều chỉnh cờ `irrelevant_entity_removed`. Từ khóa ngành hàng (Category/Generic Nouns như "bánh quy", "serum") vẫn phải được pass vào `entity_text` để hàm `resolve_entity` có cơ hội trả về lỗi `ambiguous_entity` chuẩn xác.

## **Testcase 17: Bẫy Khẳng định "Cùng 1 sản phẩm" (Same-Product Claim Trap)**

- **Câu hỏi:** "Sản phẩm mã 25078119874 và 25178062720 của shop Orion VN Official Store có cùng thương hiệu ORION, cùng danh mục (catid 100629) và cùng chiến dịch khuyến mãi (seller_flag), tên sản phẩm cũng có cấu trúc tương tự. Liệu đây có chắc chắn là cùng một sản phẩm bị đăng tách ra để tránh so sánh giá không?"
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:**
    - Sản phẩm A: `item_id = 25078119874` ("Combo 3 túi Bánh gạo nướng An ORION vị Chà Bông 145,6G")
    - Sản phẩm B: `item_id = 25178062720` ("Combo 3 Túi 5 gói bánh ăn sáng Orion C'est Bon sợi thịt gà sốt kem phô mai 101,5G/Túi")
    - Shop: `shop_id = 289646907` (Orion VN Official Store)
- **Phép tính DS phải gọi:** So sánh điểm thành phần (score components) giữa 2 item dựa trên các trường:
    - `brand_id` (ORION)
    - `catid` (100629)
    - `global_catids` ([100629, 100646, 100787] vs [100629, 100654, 100858])
    - `seller_flag` (cả hai đều là "6VCX+SuperCheap+SSCBundle[1.7]")
    - `price` (100.620đ vs 79.200đ)
    - `product_name` (cấu trúc tương tự, nhưng khác vị và trọng lượng)
- **Dữ kiện bắt buộc xuất hiện:** Agent phải nêu rõ:
    1. Các điểm tương đồng: cùng shop, cùng brand, cùng `catid` (100629), cùng `seller_flag`, cùng dạng sản phẩm combo bánh Orion.
    2. Các điểm khác biệt: khác `global_catids` (thể hiện phân loại chi tiết khác nhau), khác giá (100.620đ vs 79.200đ), khác vị và trọng lượng trong tên sản phẩm.
- **Điều cấm khẳng định (Red Lines):** KHÔNG được phép kết luận *"Đây là cùng một sản phẩm"* hoặc *"Đây là hành vi copy bài"*. Phải tuân thủ Guardrail: *"Dữ liệu cho thấy mức độ tương đồng cao (baseline similarity), tuy nhiên không thể khẳng định chắc chắn 100% đây là cùng một sản phẩm vật lý (same-product verification) do thiếu nhãn dán xác thực từ chuyên gia."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống không thể chạm tới luồng so sánh sản phẩm (Similar Product Scoring) do Parser thất bại trong việc trích xuất thực thể, dù User đã cung cấp Item ID cực kỳ tường minh.
> 
> 
> **Phân tích Trace:**
> 
> - **Lỗi Parser (Critical/Blocker):** Model `gpt-oss-20b` hoàn toàn mất khả năng nhận diện định dạng số (Item ID). `entity_text` tiếp tục chứa nguyên câu prompt dài (bao gồm cả instruction và câu hỏi tu từ) thay vì mảng ID `[25078119874, 25178062720]`.
> - **Hệ quả Gatekeeper:** Hàm `resolve_entity` quá tải với text rác -> Kích hoạt sai `A-AMBIGUOUS`.
> 
> **Đề xuất fix (Khẩn cấp):**
> 
> 1. **Bổ sung Regex cho Parser:** Trước khi cho LLM đọc text để lấy entity, hệ thống CẦN chạy một lớp Regex đơn giản để bắt các chuỗi số dài (10-15 ký tự) nghi ngờ là `item_id` / `shop_id`. Nếu tìm thấy, ưu tiên truyền thẳng mảng ID này vào biến `entity_id` hoặc làm sạch `entity_text` cho tool call.
> 2. Lỗi over-extraction của `gpt-oss-20b` hiện đã làm fail 6/7 testcase gần nhất (trừ case 13 dính Guardrail khác).

## **Testcase 18: Bẫy Tìm kiếm SKU / Biến thể (SKU-level Trap)**

- **Câu hỏi:** "Tìm cho tôi các sản phẩm tương tự có bán kích cỡ 'Hộp 279g' giống y hệt như biến thể của sản phẩm Bánh quy Richy KenJu giòn kem dẻo hương vị Nhật (mã 21658340202)."
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `item_id` = 21658340202 (Bánh quy Richy KenJu), biến thể mong muốn: `"Hộp 279g"` (tương ứng `"Hộp 279gr (18 bánh)"` trong `tier_variation_options`)
- **Phép tính DS phải gọi:** `find_similar_candidates()` ở cấp **Product Listing**, không phải cấp SKU. Agent cần tìm các sản phẩm (listing) khác trong cùng danh mục (`catid`/`global_catids`) có tên hoặc mô tả chứa "279g" hoặc cùng cấp khối lượng tương tự, nhưng KHÔNG được phép truy xuất dữ liệu doanh số/giá theo từng biến thể.
- **Dữ kiện bắt buộc xuất hiện:** Agent phải trả về **danh sách các sản phẩm tương đương ở cấp listing** (ví dụ: các sản phẩm Kenju khác, hoặc bánh quy Richy có khối lượng 279g), và phải nêu rõ rằng các sản phẩm này được so sánh dựa trên thông tin listing chứ không phải SKU cụ thể.
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định đã so sánh theo cấp độ SKU. Phải giải thích: *"Dữ liệu hiện tại chỉ theo dõi ở cấp độ Product Listing, các biến thể (tier_variation) chỉ mang tính chất hiển thị UI, không có mã SKU thật và doanh số riêng biệt để so sánh đối chiếu chính xác."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `sku`. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống nhận diện được giới hạn dữ liệu, chủ động chặn yêu cầu so sánh cấp độ SKU ngay từ bước định tuyến Intent, bảo vệ thành công Red Line không gọi sai Data Science tool.
> 
> 
> **Phân tích Trace:**
> 
> - **Điểm sáng (Architecture):** Cơ chế `unsupported_safety_precedence` hoạt động cực nhạy. Việc bẻ Intent sang `unsupported:sku` chứng tỏ LLM hiểu rõ ranh giới capability của hệ thống (Listing vs. SKU). Cổng `A-MISSING-SKU` chặn truy vấn DB hiệu quả (Zero API waste).
> - **Điểm trừ (UX):** Lời nhắn fallback của hệ thống quá khô khan và lộ thuật ngữ nội bộ ("capability `sku`", "proxy lượt bán").
> 
> **Đề xuất fix:**
> 
> - **Team Copy/UX:** Rewrite lại rule text của mã `A-MISSING-SKU`. Sửa thành: *"Dữ liệu MVP hiện tại chỉ theo dõi ở cấp độ Sản phẩm chung (Product Listing), các phân loại biến thể/kích cỡ (tier_variation) không có dữ liệu doanh số/giá độc lập để so sánh đối chiếu."*

## **Testcase 19: Bẫy Outlier Giá "Khủng" (Sentinel Price Trap)**

- **Câu hỏi:** *"*Tìm các đối thủ cạnh tranh có cùng mức giá ± 20% với sản phẩm mã 56061511146 – Quà tặng không bán (Quạt mini cầm tay).*" (Giá trị sentinel: 410.000đ)*
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:**
    - `item_id = 56061511146` (Shop Richy)
    - Tên: `[QUÀ TẶNG KHÔNG BÁN] QUẠT MINI CẦM TAY 100 NẤC GIÓ, MÀN HÌNH LED THÔNG MINH`
    - `price = 410.000đ` (hoặc 400.890đ tùy ngày, thực chất là sentinel)
- **Phép tính DS phải gọi:**
    - Khối Filter Outlier của DS phải được kích hoạt để phát hiện `price` 410.000đ bất thường so với mặt bằng sản phẩm cùng shop (25.000–150.000đ) và chặn hàm `find_similar_candidates()` không dùng mức giá này để đi tìm đối thủ.
    - Nếu không có outlier filter, DS phải ưu tiên dùng `catid`/`global_catids` để tìm sản phẩm thay vì dùng `price`.
- **Dữ kiện bắt buộc xuất hiện:** Agent phải nêu rõ:
    - Sản phẩm này thuộc loại **"Quà tặng không bán"** (qua tên sản phẩm).
    - Mức giá 410.000đ là **giá trị cửa ngõ (sentinel / placeholder)** được gán cho quà tặng để ngăn người mua đặt hàng nhầm, không phản ánh giá trị thị trường thật của sản phẩm.
- **Điều cấm khẳng định (Red Lines):** DS KHÔNG ĐƯỢC phép lấy mức giá 410.000đ (hay ±20% của nó) để tìm đối thủ cạnh tranh. LLM phải trả lời đúng tinh thần sau (thay số 999.999.999 thành 410.000): *"Sản phẩm này có mức giá 410.000đ là một giá trị rác/kỹ thuật (sentinel) từ nguồn thu thập dữ liệu (gắn với quà tặng không bán). Hệ thống đã loại bỏ bản ghi này khỏi phép so sánh để bảo vệ tính chính xác của kết quả tìm kiếm đối thủ."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.)**

> **Mô tả lỗi:**
Hệ thống không thể test được logic lọc giá trị Outlier của DS vì bị vướng chuỗi lỗi dây chuyền từ lớp Router và Parser (tương tự TC16).
> 
> 
> **Phân tích Trace:**
> 
> - **Intent Routing Error:** Keyword "đối thủ cạnh tranh" và "± 20%" tiếp tục đẩy luồng sai lệch sang `analytical_query`.
> - **Parser Over-correction (Blocker):** Hành vi `irrelevant_entity_removed` cực kỳ nguy hiểm. LLM tự ý đánh giá chuỗi có chứa Item ID hợp lệ (`56061511146`) là vô nghĩa và trả về `entity_text: null`.
> - **Hệ quả:** False Positive Gatekeeper `A-CROSS-CURRENCY-SCOPE` được kích hoạt.
> 
> **Đề xuất fix (Tái khẳng định):**
> 
> 1. **Khẩn cấp:** Regex bóc tách ID phải được chạy *trước* khi đưa qua LLM Parser. Nếu Regex tìm thấy ID 11 số, cấm LLM kích hoạt cờ `irrelevant_entity_removed`.
> 2. Đưa cụm từ "đối thủ cạnh tranh" vào danh sách keyword ưu tiên của intent `similar_product`.

## **Testcase 20: Bẫy Mã sản phẩm không tồn tại (Null Target Trap)**

- **Câu hỏi:** "Tìm sản phẩm tương đương cho mã ID 111222333444." (Một mã hoàn toàn không có trong 1157 listing của file dataset).
- **Intent mong đợi:** `similar_product` / `product_lookup`
- **Entity cần trích xuất:** `item_id` = 111222333444.
- **Phép tính DS phải gọi:** Không tìm thấy entity → Trả `status: insufficient_evidence`.
- **Dữ kiện bắt buộc xuất hiện:** Báo lỗi không tìm thấy.
- **Điều cấm khẳng định (Red Lines):** LLM cấm bịa ra (hallucinate) thông tin cho ID ảo này. Trả lời đơn giản: *"Không tìm thấy dữ liệu cho mã sản phẩm 111222333444 trong tập dữ liệu 3 ngày (01/07 - 03/07/2026) của hệ thống."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả lỗi:**
Hệ thống không thể xử lý chuẩn xác một truy vấn chứa Item ID không tồn tại. Thay vì trả về "Không tìm thấy", hệ thống nhận diện sai quốc gia và đưa ra câu báo lỗi sai logic hoàn toàn.
> 
> 
> **Phân tích Trace:**
> 
> - **Keyword Collision (Hài hước/Nghiêm trọng):** Chữ "ID" trong "mã ID" bị `deterministic_parser` nhận diện nhầm thành `country: "id"` (Indonesia). Cần fix lại regex map quốc gia (có case-sensitive hoặc kiểm tra boundary).
> - **Lỗi Error Handling (Logic Flaw):** Hàm `resolve_entity` khi không tìm thấy kết quả (`null`) lại kích hoạt nhầm cờ `A-AMBIGUOUS` ("Có nhiều listing gần giống"). Cần map đúng sang lỗi `A-NOT-FOUND` hoặc `insufficient_evidence`.
> - **NER Bug:** Bệnh cũ tái phát, LLM Parser không cô lập được mã số 111222333444.
> 
> **Đề xuất fix:**
> Rà soát lại luồng Fallback của Gatekeeper. Đảm bảo rule phân biệt rõ giữa "Tìm thấy nhiều kết quả" và "Không tìm thấy kết quả nào". Sửa Regex bắt quốc gia để tránh xung đột với từ khóa "ID".
> 

# Nhóm `promotion_effectiveness`

## **Testcase 21: Luồng chuẩn nội bộ (Standard Flow - VN)**

- **Câu hỏi:** "Tại thị trường Việt Nam, nhóm sản phẩm có áp dụng cả voucher và giảm giá trực tiếp (promo) có mang lại doanh thu ước tính tốt hơn nhóm không có khuyến mãi nào không?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `country_code` = "vn".
- **Phép tính DS phải gọi:** Hàm tính `median_revenue` và `median_monthly_sold` cho 2 nhóm `voucher + promo` và `no voucher/promo`.
- **Dữ kiện bắt buộc xuất hiện:** Báo cáo so sánh điểm Trung vị (Median) giữa 2 nhóm tại thị trường VN.
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định "Voucher làm tăng doanh thu". Phải dùng câu: *"Nhóm có khuyến mãi ghi nhận mức doanh thu trung vị cao hơn, tuy nhiên đây là so sánh mô tả (descriptive comparison), không loại trừ yếu tố thiên lệch (selection bias) do các sản phẩm chiến lược thường được ưu tiên gắn voucher."*

⇒ **PASSED (VERIFIED - Nhóm sản phẩm có voucher và giảm giá trực tiếp có doanh thu proxy ước tính trung bình cao hơn nhóm không khuyến mãi: 2059.66 items so với 745.08 items [ev:4d044f217945:0005] [ev:4d044f217945:0002]. Số lượng listing cũng lớn hơn: 551 listings so với 77 listings [ev:4d044f217945:0004] [ev:4d044f217945:0001]. Đây là quan sát tương quan, không chứng minh nguyên nhân.)**

> **Mô tả kết quả:**
Hệ thống định tuyến đúng, gọi DB thành công và bảo vệ hoàn hảo Red Line cấm khẳng định quan hệ nhân quả. Tuy nhiên, LLM đã phớt lờ yêu cầu dùng "Trung vị (Median)" của User, tự ý dùng "Trung bình (Mean)" dẫn đến sai lệch bản chất phân tích.
> 
> 
> **Phân tích Trace:**
> 
> - **Guardrail Success:** LLM đã chèn câu disclaimer: "Đây là quan sát tương quan, không chứng minh nguyên nhân."
> - **Data Misinterpretation (Lỗi đọc hiểu số liệu):**
>     - DB trả về đầy đủ Mean và Median.
>     - Thực tế: Median_Voucher (204) < Median_No_Voucher (284).
>     - LLM chọn báo cáo Mean_Voucher (2059.66) > Mean_No_Voucher (745.08) để củng cố giả thuyết bề mặt, bỏ qua hoàn toàn tính kháng nhiễu (robustness) của điểm Trung vị.
> 
> **Đề xuất fix:**
> 
> - **System Prompt cho Prompt Engineer:** Bổ sung rule cứng vào system prompt của nhóm `promotion_effectiveness`: *"Khi đánh giá doanh thu/số bán, BẮT BUỘC sử dụng điểm Trung vị (Median) làm thước đo chính để loại bỏ nhiễu từ outliers. Chỉ dùng Trung bình (Mean) khi có yêu cầu cụ thể."*
> - Ẩn bớt metric Mean khỏi kết quả trả về của DB (nếu không cần thiết) để ép LLM chỉ nhìn thấy Median.

## **Testcase 22: Bẫy cấu trúc dữ liệu - Nhóm "Voucher Only" (Structural Trap)**

- **Câu hỏi:** "Hãy phân tích hiệu quả của nhóm sản phẩm chỉ áp dụng mã giảm giá (voucher) nhưng không có chương trình giảm giá trực tiếp (promo) trên toàn sàn ở Việt Nam."
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** Toàn dataset, nhóm `voucher only` (`has_promo` = False, `has_voucher` = True).
- **Phép tính DS phải gọi:** Nhận diện nhóm trống (0 dòng).
- **Dữ kiện bắt buộc xuất hiện:** Giải thích toán học về cờ khuyến mãi.
- **Điều cấm khẳng định (Red Lines):** Agent CẤM tính toán hay bịa ra số liệu. Phải trả lời rành mạch: *"Nhóm 'Voucher Only' không tồn tại (0 dòng) trong bộ dữ liệu. Về mặt toán học, bất cứ khi nào sản phẩm có voucher, giá cuối đã phản ánh voucher đó khiến discount_percent tự động lớn hơn 0 (has_promo = True)."*

⇒ **PASSED (VERIFIED - Tại snapshot 2026‑07‑03, nhóm sản phẩm có voucher có 551 listings [ev:99b4761d4f07:0004], trung bình bán 2059.66 items [ev:99b4761d4f07:0005] và trung vị 204 items [ev:99b4761d4f07:0006]. Nhóm sản phẩm không voucher có 77 listings [ev:99b4761d4f07:0001], trung bình bán 745.08 items [ev:99b4761d4f07:0002] và trung vị 284 items [ev:99b4761d4f07:0003].**)

> **Mô tả lỗi:**
Hệ thống phớt lờ điều kiện lọc "không có giảm giá trực tiếp" của user, tự ý lấy data của tập `with_voucher` chung chung để trả lời. LLM không nhận diện được bẫy logic toán học (nhóm này có 0 dòng).
> 
> 
> **Phân tích Trace:**
> 
> - **DS Layer:** Tool `compare_voucher_groups` là một macro quá cứng, không hỗ trợ nhận filter động (như `has_promo: False`). Do đó, nó không thể truy vấn ra tập 0 dòng.
> - **LLM Logic Flaw:** Khi nhận được data `with_voucher` từ DB, LLM không kiểm tra chéo (cross-check) lại với điều kiện gốc của User. Nó nhắm mắt làm ngơ phần "không có promo" và báo cáo số liệu như đúng rồi.
> 
> **Đề xuất fix:**
> 
> 1. **Team DE (Data Engineer):** Nâng cấp hàm `compare_voucher_groups` để nhận thêm tham số `filters` (ví dụ: `promo_status`). Nếu không hợp lệ theo logic schema, trả về status: `invalid_segment`.
> 2. **Team Prompt Engineer:** Bổ sung Guardrail cho Intent này: *"Nếu User yêu cầu phân tích một phân khúc (segment) mâu thuẫn về mặt logic toán học của schema (ví dụ: có voucher nhưng không có promo), BẮT BUỘC phải từ chối và giải thích định nghĩa toán học của schema, tuyệt đối không gán ghép số liệu của nhóm khác."*

## **Testcase 23: Bẫy so sánh chéo Voucher VN vs ID (Cross-Country Trap)**

- **Câu hỏi:** "Mã giảm giá (voucher) mang lại hiệu quả chuyển đổi tốt hơn ở thị trường Việt Nam hay thị trường Indonesia?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `has_voucher` = True, `country_code` = "vn" vs "id".
- **Phép tính DS phải gọi:** Chặn so sánh chéo do tập ID rỗng.
- **Dữ kiện bắt buộc xuất hiện:** Phát hiện thiếu dữ liệu ở thị trường ID.
- **Điều cấm khẳng định (Red Lines):** Không được so sánh. Agent bắt buộc phải nói: *"Không thể so sánh hiệu quả voucher giữa hai thị trường. Toàn bộ 1.422 dòng dữ liệu của thị trường Indonesia (ID) không ghi nhận dữ liệu structured voucher nào. Việc phân tích voucher chỉ khả thi trong nội bộ thị trường VN."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability** `conversion`**. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống không test được lỗi thiếu dữ liệu voucher của ID do bị chặn trước bởi Safety Router khi phát hiện từ khóa "chuyển đổi".
> 
> 
> **Phân tích Trace:**
> 
> - **Cơ chế phòng thủ từ vựng (Lexical Defense):** Hệ thống bắt keyword "chuyển đổi" cực tốt, kích hoạt rule `unsupported_safety_precedence`. Điều này chứng tỏ LLM nắm rất vững ranh giới metadata của dataset (không có traffic data).
> - **UX Fallback Message:** Thông báo trả về "không có capability `conversion`" vẫn mang đậm tính kỹ thuật hệ thống, chưa thân thiện với end-user.
> 
> **Đề xuất fix:**
> Giống TC18, team UX/Copywriting cần Việt hóa lại câu Fallback. Ví dụ: *"Dữ liệu hiện tại chỉ ước tính được doanh số (số lượng bán ra), không có dữ liệu về traffic/lượt truy cập để tính toán tỷ lệ chuyển đổi (conversion rate) cho voucher."*
> 

## **Testcase 24: Bẫy Trung bình vs Trung vị (Mean vs Median Trap)**

- **Câu hỏi:** "Tính giúp tôi trung bình doanh thu ước tính (average revenue) của các sản phẩm có chạy chương trình khuyến mãi để xem shop thu về bao nhiêu ở Việt Nam."
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** Sản phẩm có `has_promo` = True.
- **Phép tính DS phải gọi:** Bắt buộc dùng Median thay vì Mean.
- **Dữ kiện bắt buộc xuất hiện:** Cung cấp số Trung vị (Median) và giải thích.
- **Điều cấm khẳng định (Red Lines):** DS KHÔNG ĐƯỢC code dùng hàm `mean()`. LLM phải trả lời: *"Hệ thống sử dụng Trung vị (Median) thay vì Trung bình (Mean) để đánh giá hiệu quả, nhằm tránh bị nhiễu bởi các sản phẩm bán đột biến hoặc outlier. Ngoài ra đây chỉ là doanh thu ước tính (Revenue Proxy), không phải doanh thu thực tế."*

⇒ **PASSED (VERIFIED - Không có dữ liệu doanh thu ước tính cho các sản phẩm có chạy chương trình khuyến mãi trong bộ dữ liệu hiện có. Chỉ có thông tin về số lượng bán proxy: với_voucher_mean_monthly_sold_proxy = 2059.66 items [ev:89be8a4a36ee:0005].**)

> **Mô tả lỗi:**
LLM nhận diện tốt giới hạn dữ liệu (từ chối tính Doanh thu, chuyển sang Sales Proxy) nhưng thất bại nghiêm trọng trong việc bảo vệ Guardrail Thống kê. Thay vì ép dùng Median và giải thích cho User, nó lại hùa theo keyword "trung bình" và trả về Mean.
> 
> 
> **Phân tích Trace:**
> 
> - **Schema Guardrail (PASS):** Phát hiện sự vắng mặt của cột "Revenue", tự động fallback sang "proxy lượt bán".
> - **Statistical Red Line (FAIL):** Bỏ qua `median` (204), bốc thẳng `mean` (2059.66) để trả lời. Không đưa ra được disclaimer về Outlier như thiết kế.
> 
> **Đề xuất fix:**
> 
> 1. **Cách 1 (Hard code DB):** Giấu luôn metric `mean_monthly_sold_proxy` khỏi output của hàm `compare_voucher_groups` nếu không thực sự cần thiết, ép LLM chỉ nhìn thấy Median.
> 2. **Cách 2 (Prompt Injection):** Thêm Rule cực mạnh vào System Prompt: *"CẢNH BÁO: End-user thường hay nhầm lẫn và yêu cầu tính 'trung bình' (average). Bạn BẮT BUỘC phải từ chối nhẹ nhàng, chuyển sang báo cáo 'Trung vị' (Median) và giải thích ngắn gọn rằng đây là cách chống nhiễu từ các shop bán phá giá/bán số lượng bất thường."*

## **Testcase 25: Bẫy Nhân quả & Tỷ lệ chuyển đổi (Causality & CVR Trap)**

- **Câu hỏi:** "Chương trình giảm giá 50% đã giúp các shop tăng bao nhiêu % tỷ lệ chốt đơn (conversion rate) so với lúc không giảm giá?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `discount_percent_num` $\approx$ 50%.
- **Phép tính DS phải gọi:** Phân tích mô tả (descriptive) cho bucket discount 41-60%.
- **Dữ kiện bắt buộc xuất hiện:** Bác bỏ việc tính CVR.
- **Điều cấm khẳng định (Red Lines):** Cấm tính Tỷ lệ chuyển đổi. Phải cảnh báo: *"Dữ liệu không bao gồm lưu lượng truy cập (traffic/impression), do đó không thể tính Tỷ lệ chuyển đổi (CVR). Đồng thời không thể khẳng định mức giảm 50% là nguyên nhân gốc rễ (causality) làm tăng số lượng bán."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability** `conversion`**. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống an toàn vượt qua bẫy tính tỷ lệ chốt đơn (CVR) nhờ cơ chế định tuyến an toàn (chuyển thành `unsupported`). Tuy nhiên, do bị chặn quá sớm, logic phân tích nhân quả (Causality) chưa được test.
> 
> 
> **Phân tích Trace:**
> 
> - **Lexical Guardrail (PASS):** Bắt chính xác keyword "tỷ lệ chốt đơn", chuyển hướng sang cờ chặn `A-MISSING-CONVERSION`. Zero API waste.
> - **UX Fallback (Cải thiện):** Lời nhắn báo lỗi vẫn là template cứng *"Dữ liệu hiện tại không có capability conversion"* (lỗi đã note từ TC23). Đề xuất thay thế bằng câu trả lời tự nhiên hơn.
> 
> **Đề xuất fix:**
> 
> - Xác nhận logic chặn CVR đang hoạt động ổn định.
> - Đẩy nhanh việc cập nhật thư viện text cho các mã lỗi `A-MISSING-*` để end-user không thấy các thuật ngữ nội bộ như `capability`.

## **Testcase 26: Bẫy chiến dịch Marketing (`promotion_id` Trap)**

- **Câu hỏi:** "Chiến dịch marketing có mã promotion ID '473502013010049' đã mang lại tổng doanh thu bao nhiêu cho nền tảng?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `promotion_id` = 473502013010049.
- **Phép tính DS phải gọi:** Lọc theo `promotion_id` để lấy danh sách các item được gán ID này trong khoảng thời gian snapshot (01–03/07/2026). Phải kèm theo **cảnh báo logic**: `promotion_id` chỉ là ID ưu đãi gắn với từng listing tại thời điểm snapshot, không phải định danh duy nhất cho một chiến dịch marketing có kế hoạch tập trung.
- **Dữ kiện bắt buộc xuất hiện:** Agent phải liệt kê được một số item có `promotion_id = 473502013010049` (ví dụ: ít nhất 3–5 item) và nêu rõ: Các item này thuộc các danh mục khác nhau (có thể khác `global_catids`); Mã `promotion_id` này xuất hiện cùng lúc với các voucher khác nhau theo từng ngày (ví dụ ngày 01/07 dùng `17GIAM30K1`, ngày 02/07 dùng `VCXDPULC0702`, ngày 03/07 dùng `VCXDPBLC0703`), cho thấy đây không phải là một chiến dịch thống nhất. Phải có cảnh báo về giới hạn của biến `promotion_id`: không thể suy ra tổng doanh thu, phạm vi, hoặc hiệu quả của một "chiến dịch marketing" từ dữ liệu này.
- **Điều cấm khẳng định (Red Lines): KHÔNG** được coi `promotion_id = 473502013010049` là một "chiến dịch marketing" hoàn chỉnh. **KHÔNG** được tính tổng doanh thu / doanh số cho ID này như thể nó đại diện cho một chiến dịch duy nhất. Phải trả lời đúng hoặc diễn đạt đúng tinh thần: *"Biến promotion_id là ID ưu đãi gắn với listing tại thời điểm snapshot, nó có thể áp dụng cho nhiều sản phẩm ở nhiều shop khác nhau, hoặc thay đổi theo ngày. Dataset không có bảng Marketing Master Data, nên không thể đánh giá đây là một chiến dịch tập trung."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Indonesia không có voucher structured để so sánh.)**

> **Mô tả lỗi:**
Hệ thống không thể test được logic phân tích `promotion_id` do luồng xử lý bị bẻ ngoặt sang Indonesia và ID khuyến mãi bị xóa trắng.
> 
> 
> **Phân tích Trace:**
> 
> - **Critical Bug 1 (Deterministic Parser):** Từ khóa "ID" trong "promotion ID" tiếp tục bị map nhầm thành `country="id"` (Indonesia), y hệt Testcase 20. Yêu cầu update Regex bắt boundary/case-sensitive khẩn cấp.
> - **Critical Bug 2 (LLM NER):** Mô hình tự kích hoạt `irrelevant_entity_removed` và xóa mất mã khuyến mãi 15 số gốc (`473502013010049`).
> - **Bảo mật (PASS):** Cổng `A-VOUCHER-ID` chặn truy vấn tại Indonesia rất tốt.
> 
> **Đề xuất fix:**
> 
> - Ngoài việc sửa luồng trích xuất quốc gia, team Data Engineer cần đảm bảo khi truy vấn `promotion_effectiveness`, hệ thống có tool hỗ trợ tra cứu theo `promotion_id` thay vì chỉ dùng macro `compare_voucher_groups` tĩnh như TC22/TC24.

## **Testcase 27: Bẫy Double Discount (Giá trị Voucher Trap)**

- **Câu hỏi:** "Để tính doanh thu thực nhận của nhóm có mã giảm giá, hệ thống có lấy giá bán (price) trừ đi giá trị mã giảm giá (voucher_discount) không?"
- **Intent mong đợi:** `promotion_effectiveness` (Kiểm tra Data Dictionary).
- **Entity cần trích xuất:** Nhóm `has_voucher` = True.
- **Phép tính DS phải gọi:** Không cần tính, chỉ xuất rule.
- **Dữ kiện bắt buộc xuất hiện:** Giải thích định nghĩa giá `price`.
- **Điều cấm khẳng định (Red Lines):** Cấm Agent hoặc DS làm phép trừ này. Phải tuyên bố: *"Cột price là giá trị hiển thị cuối cùng khách hàng phải trả tại thời điểm crawl (đã phản ánh voucher). Tuyệt đối không lấy price trừ đi voucher_discount một lần nữa để tránh tình trạng trừ trùng (double discount)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.)**

> **Mô tả lỗi:**
User đặt câu hỏi mang tính chất kiểm tra từ điển dữ liệu (Data Dictionary) của nhóm khuyến mãi, nhưng việc dùng các từ khóa toán học ("tính", "trừ đi") đã khiến Router định tuyến sai sang luồng phân tích chung.
> 
> 
> **Phân tích Trace:**
> 
> - **Intent Routing Error:** LLM phân loại nhầm thành `analytical_query`.
> - **Hệ quả Gatekeeper:** Vì là luồng Analytical, hệ thống kích hoạt `A-CROSS-CURRENCY-SCOPE` chặn truy vấn do thiếu quốc gia.
> - **Missed Guardrail:** Logic bảo vệ Red Line (Cấm tính Double Discount) không có cơ hội được thực thi.
> 
> **Đề xuất fix:**
> 
> - **Team Data Science / AI Engineer:** Cần tinh chỉnh lại ranh giới Intent. Thêm các mẫu câu hỏi về "cách tính", "công thức tính", "định nghĩa trường dữ liệu" liên quan đến voucher vào file training/prompt của Intent `promotion_effectiveness`.
> - **Guardrail Layer:** Bổ sung rule cứng vào system prompt: *"Tuyệt đối không thực hiện phép tính (price - voucher_discount). Luôn giải thích price là giá cuối cùng."*

## **Testcase 28: Bẫy Lợi nhuận (ROI / Margin Trap)**

- **Câu hỏi:** "Mức giảm giá nào (discount bucket) đang tối ưu hóa được lợi nhuận (profit margin) tốt nhất cho các shop FMCG tại Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** Ngành hàng FMCG.
- **Phép tính DS phải gọi:** Từ chối yêu cầu tính margin.
- **Dữ kiện bắt buộc xuất hiện:** Lời từ chối chuẩn Guardrail #3.
- **Điều cấm khẳng định (Red Lines):** Cấm gợi ý mức discount tối ưu lợi nhuận. Phải dùng câu: *"Các chỉ số về Lợi nhuận (Profit Margin), Chi phí nhập hàng, Phí sàn là dữ liệu nội bộ không nằm trong phạm vi truy xuất của bộ dữ liệu Snapshot này. Không thể đánh giá mức tối ưu lợi nhuận."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `profit`. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống vượt qua bài test an toàn bằng cách từ chối yêu cầu tính biên lợi nhuận. Tuy nhiên, thay vì trả ra câu giải thích nghiệp vụ (Guardrail #3) do Data Science layer xử lý, Router lại chặn đứng truy vấn từ vòng ngoài bằng thông báo lỗi hệ thống.
> 
> 
> **Phân tích Trace:**
> 
> - **Intent Parser (PASS):** Nhận diện cực nhạy "profit margin", chuyển thành Intent `unsupported:profit` qua cờ `unsupported_safety_precedence`.
> - **Gatekeeper (PASS):** `A-MISSING-PROFIT` hoạt động chuẩn xác, zero API tool call.
> - **UX Fallback (FAIL):** Câu thông báo lỗi "không có capability profit" không thân thiện với end-user (business user).
> 
> **Đề xuất fix:**
> 
> - **Team Backend / Router:** Áp dụng ngay câu Red Line của Guardrail #3 (*"Các chỉ số về Lợi nhuận, Chi phí nhập hàng, Phí sàn là dữ liệu nội bộ không nằm trong phạm vi truy xuất..."*) làm template thông báo mặc định cho rule `A-MISSING-PROFIT`, thay thế cho template chữ `capability` hiện hành.

## **Testcase 29: Bẫy So sánh Số tiền Tuyệt đối (Absolute Monetary FX Trap)**

- **Câu hỏi:** "Trung bình mỗi sản phẩm tại Indonesia được giảm giá bao nhiêu tiền so với các sản phẩm tại Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `discount_amount_num`, `country_code` = "vn" vs "id".
- **Phép tính DS phải gọi:** Chặn so sánh số tiền tuyệt đối.
- **Dữ kiện bắt buộc xuất hiện:** Cảnh báo khác biệt tiền tệ.
- **Điều cấm khẳng định (Red Lines):** LLM cấm lấy số VND so sánh với IDR. Phải trả lời: *"Hệ thống không thể so sánh hay cộng trừ số tiền giảm giá tuyệt đối (discount_amount) giữa thị trường VN và ID do thiếu dữ liệu tỷ giá quy đổi (FX normalization)."*

⇒ **PASSED (VERIFIED- Xin lỗi, hiện tại không có dữ liệu đủ để trả lời câu hỏi này.)**

> **Mô tả lỗi:**
User đặt câu hỏi so sánh số tiền giảm giá giữa 2 quốc gia (VN và ID), mong đợi hệ thống chặn do không có tỷ giá FX. Tuy nhiên, Regex Parser đã bắt sai Intent thành đếm số sản phẩm (listing_count) và chỉ bắt được quốc gia ID, bỏ qua VN.
> 
> 
> **Phân tích Trace:**
> 
> - **Parser Override:** Bị ép luồng bởi `country_from_deterministic_parser` và `slots_from_deterministic_parser`. Hệ quả: Mất hoàn toàn ngữ cảnh so sánh (Cross-country).
> - **Gatekeeper Blindspot:** Do parser chỉ truyền vào `country: "id"`, hệ thống không nhận diện được đây là truy vấn đa quốc gia nên `A-CROSS-CURRENCY-SCOPE` không kích hoạt.
> - **LLM Verification (PASS):** Ngăn chặn thành công việc sinh text rác từ evidence `474 listings`.
> 
> **Đề xuất fix:**
> 
> - **Vô hiệu hóa hoặc tinh chỉnh Deterministic Parser:** Cần có cơ chế để regex bắt Entity Quốc gia trả về một mảng (Array) `["vn", "id"]` thay vì chỉ bắt chuỗi đầu tiên rồi thoát. Nếu `country` có 2 phần tử, bắt buộc kích hoạt cờ Cross-Country.

## **Testcase 30: Bẫy Sentinel Promotion (Giá trị rác Promo ID)**

- **Câu hỏi:** "Chương trình khuyến mãi có mã '0' (promotion_id = 0) đang áp dụng cho bao nhiêu sản phẩm ở Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `promotion_id` = 0.
- **Phép tính DS phải gọi:** Đếm số dòng `promotion_id` = 0 (874 dòng).
- **Dữ kiện bắt buộc xuất hiện:** Giải thích ý nghĩa của ID 0.
- **Điều cấm khẳng định (Red Lines):** LLM cấm gọi đây là một "chương trình khuyến mãi". Phải đính chính: *"Giá trị promotion_id = 0 là một giá trị rác/kỹ thuật (sentinel) biểu thị trạng thái không có ưu đãi hoặc không xác định, không phải là một chiến dịch có thật."*

⇒ **PASSED (VERIFIED- So sánh quan sát tại một snapshot: without_voucher_listing_count=77 listings [ev:41166f4d5fd3:0001]; without_voucher_mean_monthly_sold_proxy=745.078 items [ev:41166f4d5fd3:0002]; without_voucher_median_monthly_sold_proxy=284 items [ev:41166f4d5fd3:0003]; with_voucher_listing_count=551 listings [ev:41166f4d5fd3:0004]; with_voucher_mean_monthly_sold_proxy=2059.66 items [ev:41166f4d5fd3:0005]; with_voucher_median_monthly_sold_proxy=204 items [ev:41166f4d5fd3:0006]. Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi.)**

> **Mô tả lỗi:**
User test khả năng xử lý giá trị rác (promotion_id = 0). Hệ thống không nhận diện được ID, chạy Macro mặc định. Khi LLM cố gắng đưa số 0 vào câu trả lời để duy trì ngữ cảnh, Verification Layer đã chặn đứng vì số 0 không nằm trong Evidence data. Hệ thống rơi vào trạng thái Fallback.
> 
> 
> **Phân tích Trace:**
> 
> - **LLM NER (FAIL):** Bật cờ `irrelevant_entity_removed` với số 0.
> - **Macro (FAIL):** Không có khả năng filter theo `promotion_id`.
> - **Verification Layer (PASS/OVERKILL):** Bắt chính xác lỗi `unsupported: [0]`, chống hallucination rất tốt, nhưng lại làm hỏng UX vì không cho phép LLM lặp lại entity của user. `fallback: true` được kích hoạt.
> 
> **Đề xuất fix:**
> 
> - **Luật Verification:** Cần có ngoại lệ (whitelist) cho phép LLM được quyền xuất ra các con số đã xuất hiện trực tiếp trong `slots.raw_text` của người dùng mà không bị đánh cờ `unsupported`.
> - **Xử lý Null/Sentinel:** Cần huấn luyện LLM nhận diện các giá trị `0`, `1`, `9999`, `NULL`, `NaN` là các technical entity quan trọng, cấm dùng cờ `irrelevant_entity_removed` với chúng.

# Nhóm `error_and_limitations`

## **Testcase 31: Lỗi Lệch Khung Thời Gian (Out-of-Timeframe Trap)**

- **Câu hỏi:** "Hãy so sánh doanh số của các sản phẩm FMCG trong tháng 6/2026 và dự báo cho tháng 8/2026."
- **Intent mong đợi:** Khước từ phân tích.
- **Entity cần trích xuất:** `date` = Tháng 6/2026, Tháng 8/2026.
- **Dữ kiện bắt buộc xuất hiện:** Trích dẫn giới hạn 3 ngày.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG ĐƯỢC tự ý lấy data của tháng 7 ra trả lời bù. Phải nói: *"Hệ thống khước từ phân tích. Dữ liệu hiện tại chỉ là bản snapshot trong 3 ngày (01/07 - 03/07/2026). Không có dữ liệu của tháng 6 và không đủ cơ sở để dự báo (forecasting) cho tháng 8."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `forecast` . Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả lỗi:**
User đặt bẫy kép: Yêu cầu data quá khứ (tháng 6) và dự báo tương lai (tháng 8). Router vấp ngay từ khóa "dự báo", kích hoạt `A-MISSING-FORECAST` và bỏ qua hoàn toàn việc giải thích giới hạn dữ liệu snapshot 3 ngày (tháng 7).
> 
> 
> **Phân tích Trace:**
> 
> - **Date Parsing (PASS):** Trích xuất đúng `["2026-06", "2026-08"]`.
> - **Safety Precedence (PASS):** Ngăn chặn Hallucination dự báo tương lai thành công.
> - **Logic Cảnh báo (FAIL):** Không đưa ra được Red Line cảnh báo người dùng về việc dataset chỉ có 3 ngày (01/07 - 03/07/2026). Trải nghiệm người dùng (UX) tiếp tục bị ảnh hưởng bởi template lỗi `capability` cứng ngắc.
> 
> **Đề xuất fix:**
> 
> - **Luật Router (Gatekeeper):** Nếu `date_range` chứa các giá trị nằm ngoài khoảng `2026-07-01` đến `2026-07-03`, Gatekeeper **BẮT BUỘC** phải ưu tiên trigger cờ `A-OUT-OF-TIMEFRAME` trước, hoặc gộp chung thông báo lỗi: *"Hệ thống không có chức năng dự báo, đồng thời dữ liệu hiện tại chỉ là bản snapshot từ 01/07 - 03/07/2026 nên không có dữ liệu tháng 6."*

## **Testcase 32: Lỗi Ảo giác Quảng cáo (Ads Hallucination Trap)**

- **Câu hỏi:** "Shop mỹ phẩm Glad2Glow đang chạy quảng cáo (ads) cho những sản phẩm nào, hiệu quả doanh thu từ quảng cáo là bao nhiêu?"
- **Intent mong đợi:** `promotion_effectiveness` / Từ chối.
- **Entity cần trích xuất:** `shop_name` = Glad2Glow, `is_ad_bool`.
- **Dữ kiện bắt buộc xuất hiện:** Báo cáo cờ `is_ad`.
- **Điều cấm khẳng định (Red Lines):** Agent CẤM bịa ra ngân sách quảng cáo. Bắt buộc trả lời: *"Toàn bộ 3341 dòng dữ liệu hiện tại đều ghi nhận cờ is_ad_bool = False (không có biến thiên). Hệ thống không có dữ liệu về các sản phẩm được chạy quảng cáo cũng như chi phí Ads."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `ads`. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống chặn thành công bẫy phân tích quảng cáo (ngăn ngừa Hallucination tuyệt đối). Tuy nhiên, cách chặn quá thô bạo ở vòng ngoài đã khiến hệ thống không thể sử dụng biến `is_ad_bool` (toàn bộ = False) để giải thích cặn kẽ cho user như thiết kế ban đầu.
> 
> 
> **Phân tích Trace:**
> 
> - **Intent & Gatekeeper (PASS):** Định tuyến xuất sắc sang `unsupported:ads` và chặn bằng `A-MISSING-ADS`.
> - **Entity Extraction (FAIL):** Không tách được `Glad2Glow`, lấy toàn bộ câu gán vào `entity_text`.
> - **UX Fallback (FAIL):** Tiếp tục dùng template lỗi hệ thống: *"Dữ liệu hiện tại không có capability ads"*.
> 
> **Đề xuất fix:**
> 
> - **Cách 1 (Sửa text Gatekeeper):** Cập nhật template của rule `A-MISSING-ADS` thành: *"Dữ liệu không bao gồm chi phí quảng cáo. Dù hệ thống có cột is_ad_bool nhưng 100% dữ liệu hiện tại đều ghi nhận trạng thái False, nên không thể phân tích hiệu quả Ads."*
> - **Cách 2 (Mở luồng):** Đưa keyword "is_ad_bool" vào whitelist. Nếu user hỏi trực tiếp về trạng thái cờ này, cho phép đi qua cổng `A-ALLOW`.

## **Testcase 33: Lỗi Phân tích cấp độ SKU (SKU-Level Trap)**

- **Câu hỏi:** "Trong sản phẩm Combo 5 Bánh Quy Oreo Với Kem Vị Dâu/Vani/Sôcôla (mã 25211554425) có 3 biến thể: Dâu, Vani, Sôcôla. Hãy cho tôi biết biến thể (vị) nào đang mang lại doanh thu cao nhất?"
- **Intent mong đợi:** Từ chối phân tách SKU (không phải `sales_breakdown` hay `sku_analysis`).
- **Entity cần trích xuất:**
    - `item_id = 25211554425`
    - `tier_variation_name = "Phân loại"`
    - `tier_variation_options = ["CB5 Dâu", "CB5 Choco", "CB5 Vani"]`
- **Phép tính DS phải gọi:** Không có phép tính nào được thực hiện. Agent phải **từ chối** vì dữ liệu không hỗ trợ phân tích ở cấp độ SKU/biến thể. Nếu có gọi DS, phải trả về `insufficient_data` hoặc `not_supported`.
- **Dữ kiện bắt buộc xuất hiện:**
    - Agent phải nhắc lại định nghĩa **Grain của dữ liệu**: dữ liệu chỉ lưu trữ ở cấp độ Product Listing, không phải SKU/biến thể.
    - Các biến thể (`tier_variation_options`) chỉ là chuỗi hiển thị giao diện, không có dữ liệu bán hàng (sales) hay giá bán riêng lẻ để so sánh.
- **Điều cấm khẳng định (Red Lines): CẤM** chia đều `monthly_sold_value` (hoặc `history_sold_value`) cho 3 biến thể để ước tính doanh thu từng vị. **CẤM** suy luận rằng doanh số được phân bổ đều hoặc theo tỷ lệ nào đó giữa các biến thể. Phải trả lời đúng hoặc diễn đạt đúng tinh thần: *"Dữ liệu hiện tại chỉ lưu trữ ở cấp độ Sản phẩm (Product Listing), không phải cấp độ SKU. Các biến thể (vị) chỉ là chuỗi hiển thị giao diện, không có số liệu bán hàng (sales) hay giá bán riêng lẻ để so sánh."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `sku`. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống chặn thành công yêu cầu chia nhỏ doanh thu theo biến thể (SKU), ngăn chặn hoàn toàn rủi ro LLM tự ý làm toán chia đều doanh số (Hallucination). Tuy nhiên, Gatekeeper trả về lỗi hệ thống thay vì giải thích định nghĩa Data Grain cho user.
> 
> 
> **Phân tích Trace:**
> 
> - **Intent Routing (PASS):** Cờ `unsupported_safety_precedence` hoạt động chuẩn, chuyển hướng đúng sang `unsupported:sku`.
> - **Entity Extraction (FAIL):** Không bóc tách được `item_id = 25211554425`.
> - **UX Fallback (Cải thiện):** Lời từ chối quá kỹ thuật (`capability sku`), không giải thích được lý do gốc rễ về cấu trúc dữ liệu.
> 
> **Đề xuất fix:**
> 
> - **Cập nhật Template `A-MISSING-SKU`:** Đổi thành: *"Dữ liệu hiện tại chỉ lưu trữ ở cấp độ Sản phẩm (Product Listing), không hỗ trợ bóc tách chi tiết theo biến thể/SKU (màu sắc, kích cỡ, hương vị). Các biến thể chỉ là chuỗi hiển thị, không có số liệu bán hàng riêng lẻ để so sánh."*
> - **Parser Prompt:** Nhắc nhở LLM Parser không được phép drop `item_id` kể cả khi Intent là `unsupported`.

## **Testcase 34: Lỗi Thiếu Ngày / Đứt gãy Dữ liệu (Snapshot Gap Trap)**

- **Câu hỏi:** *"*Tính mức giảm doanh số (sales delta) của sản phẩm Collagen Thủy Phân NESTLÉ VITAL PROTEINS 284G (mã 24710759163) từ ngày 01/07 đến ngày 03/07.*"*
- **Intent mong đợi:** `sales_decline` (kèm theo cảnh báo về snapshot gap)
- **Entity cần trích xuất:**
    - `item_id = 24710759163`
    - Tên sản phẩm: Collagen Thủy Phân Dạng Bột NESTLÉ VITAL PROTEINS Mỹ Hỗ Trợ Làm Đẹp Da,Móng,Tóc 284G
    - `snapshot_gap_flag = True` (không có dữ liệu ngày 02/07)
- **Phép tính DS phải gọi:**
    - Hàm `get_monthly_sold_value(item_id, date)` cho 01/07 và 03/07.
    - Phát hiện thiếu ngày 02/07 → trả về `snapshot_gap_flag = True` và từ chối tính `monthly_sold_delta` trực tiếp giữa 01/07 và 03/07 mà không có cảnh báo.
- **Dữ kiện bắt buộc xuất hiện:**
    - Agent phải báo cáo rõ: **thiếu snapshot ngày 02/07** cho sản phẩm này.
    - Nêu giá trị `monthly_sold_value` của ngày 01/07 và 03/07 (nếu có) nhưng kèm theo cảnh báo rằng việc so sánh nhảy cóc giữa 2 ngày không liền kề có thể sai lệch.
- **Điều cấm khẳng định (Red Lines):**
    - **CẤM** tự động điền số 0 (fill zero) cho ngày 02/07 để tính toán delta.
    - **CẤM** tính `monthly_sold_delta = value_03 - value_01` mà không kèm theo cảnh báo về gap.
    - Phải trả lời đúng hoặc diễn đạt đúng tinh thần:
        
        > *"Ghi nhận thiếu snapshot ngày 02/07 cho sản phẩm này (snapshot_gap_flag = True). Việc so sánh nhảy cóc từ 01/07 sang 03/07 có thể làm sai lệch độ chính xác của gia tốc bán hàng."*
        > 

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả kết quả:**
User kiểm tra khả năng bắt lỗi thiếu ngày (Gap) của Data Science layer. Tuy nhiên, dù user đã cung cấp chính xác `item_id` trong dấu ngoặc đơn, hệ thống `resolve_entity` vẫn fail và trả về lỗi `A-AMBIGUOUS` (yêu cầu làm rõ).
> 
> 
> **Phân tích Trace:**
> 
> - **Entity Extraction:** Parser lấy nguyên chuỗi *"Tên sản phẩm (mã ID)"* đưa vào `entity_text`.
> - **Tool `resolve_entity` (FAIL):** Tool tìm kiếm không có logic ưu tiên trích xuất ID (ID-first extraction). Nó nhét cả đoạn text dài vào query khiến kết quả trả về bị loãng/nhiễu.
> - **Data Science Layer:** Không được kích hoạt, bài test `snapshot_gap_flag` thất bại do bị block từ vòng ngoài.
> 
> **Đề xuất fix:**
> 
> - **Nâng cấp `resolve_entity`:** Bổ sung Regex bắt ID số (ví dụ: `\b\d{10,15}\b`) vào logic của tool. Nếu phát hiện chuỗi có chứa dãy số giống ID nền tảng, phải dùng ID đó để query DB bằng phương thức "Exact Match" (khớp tuyệt đối) trước khi dùng text để "Fuzzy Match".

## **Testcase 35: Lỗi Thực thể "Ma" (Non-existent Domain Trap)**

- **Câu hỏi:** "Phân tích doanh số của điện thoại iPhone 15 Pro Max tại shop Apple Official Store."
- **Intent mong đợi:** `entity_resolution` thất bại.
- **Entity cần trích xuất:** iPhone 15 Pro Max.
- **Dữ kiện bắt buộc xuất hiện:** Báo lỗi không tìm thấy.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG ĐƯỢC đi tìm dữ liệu từ nguồn ngoài (internet/web search). Phải bám sát dataset: *"Tập dữ liệu hiện tại chỉ chứa 20 shop thuộc ngành hàng FMCG và Mỹ phẩm tại VN/ID. Không tìm thấy sản phẩm iPhone 15 Pro Max hay shop Apple Official trong hệ thống."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

> **Mô tả kết quả:**
User truy vấn sản phẩm điện tử (iPhone) ngoài phạm vi dataset. Hệ thống thay vì báo lỗi "Không tìm thấy danh mục/shop", lại tự động xóa thực thể (`irrelevant_entity_removed`) rồi ném ra lỗi `A-CROSS-CURRENCY-SCOPE` đòi phân định tiền tệ VND/IDR.
> 
> 
> **Phân tích Trace:**
> 
> - **Entity Stripping (FAIL):** Cơ chế loại bỏ thực thể không khớp đã làm mất hoàn toàn ngữ cảnh câu hỏi của user.
> - **Guardrail Misfire (FAIL):** Lỗi chọn thị trường (`A-CROSS-CURRENCY-SCOPE`) bị ép gọi sai chỗ do truy vấn bị bóp méo thành một câu lệnh trống không có quốc gia.
> 
> **Defect Fix Proposal:**
> 
> - **Thứ tự ưu tiên kiểm tra Domain:** Trước khi kiểm tra giới hạn tiền tệ hay quốc gia, hệ thống phải chạy qua **Entity Validation Layer**. Nếu tập thực thể (shop/product) trả về rỗng vì không thuộc danh mục ngành hàng được quản lý (FMCG/Mỹ phẩm), phải lập tức ném ra lỗi `A-DOMAIN-OUT-OF-BOUNDS` thay vì để lọt qua các tầng validate phía sau.

## **Testcase 36: Lỗi Tính tổng Xuyên Biên Giới (Cross-Country Aggregation Trap)**

- **Câu hỏi:** "Tổng doanh thu ước tính của cả thị trường Việt Nam và Indonesia cộng lại trong 3 ngày qua là bao nhiêu?"
- **Intent mong đợi:** Khước từ tính tổng (Summation block).
- **Entity cần trích xuất:** Toàn dataset, `country_code`.
- **Dữ kiện bắt buộc xuất hiện:** Cảnh báo tiền tệ.
- **Điều cấm khẳng định (Red Lines):** Code DS CẤM thực hiện phép `SUM()` gộp chung VND và IDR. Agent phải trả lời: *"Hệ thống không thể cộng gộp doanh thu ước tính giữa hai quốc gia do chưa có tỷ giá quy đổi tiền tệ (FX/Currency Normalization). VND và IDR phải được phân tích ở hai luồng độc lập."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Chưa có analytical template cho.)**

> **Mô tả kết quả:**
Hệ thống chặn thành công yêu cầu cộng gộp số liệu chéo quốc gia. Tuy nhiên, thay vì hiển thị cảnh báo nghiệp vụ về việc thiếu tỷ giá FX (VND vs IDR), hệ thống gặp lỗi render chuỗi thông báo, để lộ thông báo lỗi bị cụt (`Chưa có analytical template cho:` ).
> 
> 
> **Phân tích Trace:**
> 
> - **Country Extraction (FAIL):** Chỉ bắt được `country: "id"`, bỏ sót từ khóa "Việt Nam".
> - **Planning Engine (PASS):** Đưa trạng thái về `blocked` thành công nhờ rule `A19-PLAN`.
> - **UI/UX Error Handling (FAIL):** Biến động chuỗi thông báo lỗi bị lỗi định dạng (missing argument injection), làm sụt giảm nghiêm trọng độ chuyên nghiệp của Agent.
> 
> **Đề xuất fix:**
> 
> - **Sửa lỗi Code Backend:** Kiểm tra lại hàm định dạng chuỗi tại module `A19-PLAN` để đảm bảo luôn truyền đủ tên Intent/Macro vào thông báo lỗi thay vì để trống.
> - **Nâng cấp Rule Nghiệp vụ:** Viết cứng (hardcode) câu cảnh báo chuẩn: *"Hệ thống không thể cộng gộp doanh thu giữa VND và IDR do thiếu cơ chế quy đổi tỷ giá (FX Normalization)"* vào thẳng rule từ chối thay vì phụ thuộc vào dynamic template đang bị lỗi.

## **Testcase 37: Lỗi Số lượng Tồn kho Tuyệt đối (Absolute Inventory Trap)**

- **Câu hỏi:** "Shop Orion VN hiện tại đang còn tồn kho bao nhiêu thùng bánh Chocopie trong kho?"
- **Intent mong đợi:** Khước từ truy xuất.
- **Entity cần trích xuất:** Shop Orion VN, bánh Chocopie.
- **Dữ kiện bắt buộc xuất hiện:** Giới hạn của biến `is_sold_out_bool`.
- **Điều cấm khẳng định (Red Lines):** Cấm bịa ra số lượng tồn kho. Agent phải nói: *"Dataset không cung cấp số lượng hàng tồn kho (Inventory Volume) tuyệt đối. Hệ thống chỉ có duy nhất trạng thái nhị phân (Còn hàng / Hết hàng) dựa trên cờ is_sold_out_bool."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dữ liệu hiện tại không có capability `inventory`. Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.)**

> **Mô tả kết quả:**
Hệ thống ngăn chặn thành công việc bịa đặt số lượng tồn kho. Tuy nhiên, thông báo trả về vẫn là template cứng nhắc, không giúp người dùng hiểu rằng hệ thống chỉ quản lý trạng thái nhị phân (`is_sold_out_bool`).
> 
> 
> **Phân tích Trace:**
> 
> - **Intent Routing (PASS):** Định tuyến chuẩn xác sang `unsupported:inventory`.
> - **Entity Extraction (FAIL):** Bỏ sót `Orion VN` và `bánh Chocopie`.
> - **UX Messaging (FAIL):** Thiếu thông tin giải thích về biến `is_sold_out_bool` theo đúng Red Line thiết kế.
> 
> **Đề xuất fix:**
> 
> - Cập nhật nội dung phản hồi của rule `A-MISSING-INVENTORY` thành: *"Dataset không cung cấp số lượng hàng tồn kho (Inventory Volume) tuyệt đối. Hệ thống chỉ có duy nhất trạng thái nhị phân (Còn hàng / Hết hàng) dựa trên cờ is_sold_out_bool."*

## **Testcase 38: Lỗi Nhân quả Chéo (Cross-Metrics Causality Trap)**

- **Câu hỏi:***"*Điểm đánh giá (rating) tăng từ 4.85 lên 4.88 có phải là lý do chính khiến sản phẩm Sữa Bột NESTLÉ NUTREN JUNIOR 800G (mã 26663401389) bán được nhiều hơn ở Việt Nam trong ngày 03/07 không?*"*
- **Intent mong đợi:** Trả lời mô tả (Descriptive answer) – **không** phải causal inference.
- **Entity cần trích xuất:**
    - `item_id = 26663401389`
    - Tên sản phẩm: Sữa Bột NESTLÉ NUTREN JUNIOR Thụy Sĩ Với Công Thức BIG Hỗ Trợ Tăng Trưởng Cho Bé 800G
    - `rating_change`: từ 4.85 lên 4.88 (cụ thể: 4.8519 → 4.8835)
    - `snapshot_sales_delta`: `monthly_sold_value` tăng từ 1000 lên 3000
- **Phép tính DS phải gọi:**
    - Lấy `rating` và `monthly_sold_value` cho các ngày 02/07 và 03/07.
    - Tính delta của cả hai metric.
    - **Không** thực hiện bất kỳ phép kiểm định nhân quả nào (không có A/B test, không có mô hình causal).
- **Dữ kiện bắt buộc xuất hiện:**
    - Báo cáo mức tăng rating: từ 4.8519 lên 4.8835 (tăng ~0.0316 điểm).
    - Báo cáo mức tăng sales: `monthly_sold_value` tăng từ 1000 lên 3000 (tăng 2000 đơn vị), và `history_sold_value` tăng từ 6000 lên 8000 (tăng 2000 đơn vị – cho thấy đơn hàng mới phát sinh).
    - Nêu rõ đây là sự **đồng biến (co-occurrence)**, không phải bằng chứng nhân quả.
- **Điều cấm khẳng định (Red Lines):**
    - **CẤM** dùng từ "lý do chính" hoặc "nguyên nhân trực tiếp" trong kết luận.
    - **CẤM** suy diễn rằng rating tăng là nguyên nhân gây ra sales tăng mà không có thử nghiệm đối chứng.
    - Phải trả lời đúng hoặc diễn đạt đúng tinh thần Guardrail #13: *"Ghi nhận sự tăng trưởng đồng thời của điểm đánh giá (từ 4.85 lên 4.88) và doanh số (monthly_sold_value từ 1000 lên 3000). Tuy nhiên, đây chỉ là sự liên hệ (association), không thể kết luận điểm rating tăng là nguyên nhân trực tiếp tạo ra doanh số khi không có thiết kế thử nghiệm A/B."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Chưa có analytical template cho.)**

> **Mô tả kết quả:**
Hệ thống thất bại trong việc phân rã câu hỏi phân tích đa metric (Rating vs Sales) kèm bẫy nhân quả. Planning Layer bị khóa bởi rule `A19-PLAN`, đồng thời tiếp tục để lộ lỗi định dạng chuỗi thông báo lỗi (thiếu giá trị nội suy).
> 
> 
> **Phân tích Trace:**
> 
> - **Planning Engine (Blocked):** Thiếu macro hỗ trợ phân tích tương quan/mô tả đa biến kết hợp kiểm soát nhân quả.
> - **String Interpolation Bug (CRITICAL):** Lỗi render `Chưa có analytical template cho:`  tái diễn từ Testcase 36, gây mất điểm nghiêm trọng về tính chuyên nghiệp của giao diện phản hồi.
> - **Entity Stripping (FAIL):** Mã sản phẩm `26663401389` bị loại bỏ hoàn toàn khỏi request.
> 
> **Đề xuất fix:**
> 
> - **Fix triệt để String Interpolation:** Bổ sung fallback string an toàn cho module báo lỗi của Planning Layer (ví dụ: nếu thiếu tên macro, hiển thị mặc định *"Yêu cầu phân tích chưa được hỗ trợ"* thay vì để trống chuỗi).
> - **Mở rộng Descriptive Macro:** Xây dựng một analytical template chung cho nhóm câu hỏi so sánh tương quan (co-occurrence) để hệ thống có thể trả về phân tích mô tả số liệu (Descriptive Stats) thay vì block cứng ngắc.

## **Testcase 39: Lỗi Cộng dồn Tháng (Monthly Accumulation Trap)**

- **Câu hỏi:** *"Tổng số lượng sản phẩm bán ra của sản phẩm Sữa Bột NESTLÉ NUTREN JUNIOR 800G (mã 26663401389) trong 3 ngày vừa qua ở Việt Nam là bao nhiêu? Hãy cộng lượt bán hàng tháng (monthly_sold) của 3 ngày lại."*
- **Intent mong đợi:** Khước từ phép tính sai (từ chối cộng dồn `monthly_sold_value`).
- **Entity cần trích xuất:**
    - `item_id = 26663401389`
    - Tên sản phẩm: Sữa Bột NESTLÉ NUTREN JUNIOR Thụy Sĩ Với Công Thức BIG Hỗ Trợ Tăng Trưởng Cho Bé 800G
    - `monthly_sold_value` qua 3 ngày:
        - 01/07: 1000
        - 02/07: 1000
        - 03/07: 3000
- **Phép tính DS phải gọi:**
    - Không có phép tính DS nào được thực thi. Agent phải **từ chối** cộng dồn `monthly_sold_value` và nhắc lại định nghĩa của chỉ số này.
    - Nếu DS được gọi, phải trả về cảnh báo hoặc `status: invalid_operation`.
- **Dữ kiện bắt buộc xuất hiện:**
    - Agent phải nhắc lại định nghĩa:
        
        `monthly_sold_value` là **chỉ số cửa sổ trượt (rolling window)**, không phải doanh số tích lũy theo ngày.
        
    - Giá trị `monthly_sold_value` tại mỗi snapshot là **ước lượng doanh số của 30 ngày gần nhất** tính đến thời điểm snapshot, **không thể cộng gộp** qua các ngày.
    - Nếu người dùng muốn biết tổng số lượng bán ra thực tế trong 3 ngày, cần dùng `history_sold_value` hoặc dữ liệu lũy kế khác (nếu có) – nhưng dữ liệu hiện tại vẫn chưa đủ để tách biệt chính xác.
- **Điều cấm khẳng định (Red Lines):**
    - **CẤM** thực hiện `SUM(monthly_sold_value)` cho 3 ngày.
    - **CẤM** trả về một con số tổng (ví dụ: 5000) dưới bất kỳ hình thức nào.
    - Phải trả lời đúng hoặc diễn đạt đúng tinh thần: *"Chỉ số monthly_sold_value là cửa sổ bán hàng hiển thị (recent-window proxy) được ghi nhận tại mỗi snapshot, KHÔNG ĐƯỢC phép cộng dồn qua 3 ngày vì sẽ gây ra lỗi đếm trùng số liệu của các ngày trước đó."*

⇒ **PASSED** (**VERIFIED - Có 668 listing [ev:ce59078845fc:0001] trong phạm vi đã chọn.)**

> **Mô tả kết quả:**
User thử thách khả năng kiểm soát phép tính sai trên chỉ số rolling window (`monthly_sold_value`). Hệ thống thay vì từ chối cộng dồn, đã hiểu nhầm ý định, bẻ lái sang macro đếm tổng số lượng listing (`668 listings`) và bỏ qua hoàn toàn thực thể sản phẩm.
> 
> 
> **Phân tích Trace:**
> 
> - **Intent & Slot Parsing (FAIL):** Trích xuất sai hướng, gán nhãn `analytical_kind: "listing_count"` thay vì phát hiện `invalid_operation` hoặc từ chối cộng dồn.
> - **Planning Mode (Deterministic Template):** Chạy trơn tru macro đếm listing thay vì chặn phép toán cộng dồn `SUM(monthly_sold_value)`.
> - **Guardrail Validation (FAIL):** Không kích hoạt được Red Line cảnh báo về cửa sổ trượt (rolling window).
> 
> **Đề xuất fix:**
> 
> - **Bổ sung Semantic Guardrail cho Rolling Metrics:** Thêm bộ lọc ngữ nghĩa: Nếu câu hỏi chứa từ khóa "cộng" / "tổng" kết hợp với các metric có tính chất cửa sổ thời gian (như `monthly_sold`, `rolling_30d`), hệ thống **bắt buộc** phải chuyển sang luồng từ chối (abstain/invalid_operation) thay vì cố gắng mapping sang macro đếm listing chung chung.

## **Testcase 40: Lỗi Đếm trùng Danh mục Nội bộ (Shop Merchandising Double Count)**

- **Câu hỏi:** "Tính tổng doanh thu ước tính của tất cả các kệ hàng nội bộ (category_list) của shop Nestlé, sau đó cộng lại xem tổng shop thu được bao nhiêu."
- **Intent mong đợi:** Từ chối phương pháp tính.
- **Entity cần trích xuất:** Shop Nestlé, `category_list`.
- **Dữ kiện bắt buộc xuất hiện:** Lời giải thích về cơ chế trưng bày.
- **Điều cấm khẳng định (Red Lines):** Cấm thực hiện phép tính theo yêu cầu user. Bắt buộc trả lời: *"Một sản phẩm có thể được trưng bày trên nhiều kệ nội bộ khác nhau. Việc cộng dồn doanh thu của tất cả các kệ sẽ dẫn đến lỗi đếm trùng (Double Count). Để tính tổng doanh thu của shop, hệ thống đã loại trùng (deduplicate) về cấp độ Sản phẩm (item_id)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.)**

> **Mô tả kết quả:**
User đặt bẫy kiểm tra logic chống đếm trùng doanh thu khi sản phẩm thuộc nhiều danh mục (`category_list`). Tuy nhiên, hệ thống không nhận diện được tên shop kết hợp quốc gia, dẫn đến việc kích hoạt nhầm cờ yêu cầu chọn thị trường (`A-CROSS-CURRENCY-SCOPE`).
> 
> 
> **Phân tích Trace:**
> 
> - **Entity Extraction (FAIL):** Không bắt được quốc gia từ tên shop "Nestlé", dẫn đến `country: null`.
> - **Guardrail Misfire (FAIL):** Lỗi `A-CROSS-CURRENCY-SCOPE` bóp méo luồng xử lý, biến câu hỏi nghiệp vụ thành câu hỏi chọn thị trường.
> - **Business Logic Gap:** Không thể kích hoạt Red Line giải thích cơ chế loại trùng (`deduplicate`) ở cấp độ `item_id`.
> 
> **Đề xuất fix:**
> 
> - **Cải tiến Named Entity Recognition (NER) cho Shop Names:** Hệ thống cần ánh xạ thông minh các Brand lớn (như Nestlé, Unilever, v.v.) vào các thị trường tương ứng (VN/ID) dựa trên cơ sở dữ liệu shop có sẵn, thay vì trả về giá trị null và đẩy việc này cho Guardrail tiền tệ xử lý thô bạo.