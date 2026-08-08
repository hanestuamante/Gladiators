# DR TASK 27,28/7

STATUS: OPERATING
DO DATE: 28/07/2026
FINAL: 28/07/2026
TIME:  @July 28, 2026 6:00 PM

# QUY ƯỚC ĐỌC HIỂU BÁO CÁO QA (LƯU Ý QUAN TRỌNG)

**Dành cho các team Dev, Data Science, Product và các công cụ AI phân tích log:**

Quy ước dán nhãn **PASSED / FAILED** trong toàn bộ 40 testcases dưới đây **KHÔNG** phản ánh việc hệ thống xử lý đúng hay sai logic nghiệp vụ (Business Logic) hay Red Lines.

Nhãn đánh giá được gán cơ học dựa trên **Trạng thái Output (Action)** cuối cùng của AI Agent:

- 🟢 **[PASSED]:** Agent trả về cờ `ALLOW - VERIFIED` (Luồng chạy thông suốt, Data Science được gọi và Verification thành công).
- 🔴 **[FAILED]:** Agent trả về cờ chặn `ABSTAIN` (Từ chối trả lời) hoặc `CLARIFY` (Yêu cầu làm rõ) — *bất kể việc chặn này là hành vi bảo vệ hệ thống đúng đắn hay là do lỗi kỹ thuật (Parser/API).*

**⚠️ Hệ quả cốt lõi cần nhớ:**

1. Một testcase bị đánh nhãn **FAILED** rất có thể lại là một pha **phòng thủ xuất sắc** của Gatekeeper khi nó khước từ thành công các truy vấn rác, ảo giác, hoặc vi phạm bảo mật.
2. Một testcase được đánh nhãn **PASSED** vẫn có thể chứa lỗi sai nghiêm trọng về mặt thống kê, lọt bẫy nghiệp vụ, hoặc có vấn đề về UX/UI.

👉 **Do đó, vui lòng KHÔNG đếm số lượng PASSED/FAILED để kết luận hiệu năng.** Bắt buộc phải đọc kỹ phần **"Phân tích Trace"** và **"Đề xuất Fix"** bên dưới mỗi testcase để nắm bắt chính xác Root Cause (lỗi API, lỗi Parser, lỗi Schema, hay lỗi UX) và hành động cần thiết.

# Nhóm `sales_decline`

## **Testcase 1: Luồng chuẩn (Standard Flow - VN)**

- **Câu hỏi:** "Cho tôi biết vì sao lượt bán của kẹo dẻo Chupa Chups tại shop Perfetti Van Melle Vietnam lại giảm trong những ngày qua?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `product_name` chứa "Chupa Chups", `shop_name` = "Perfetti Van Melle Vietnam", `country_code` = "vn".
- **Phép tính DS phải gọi:** Hàm tính `monthly_sold_delta`, `price_change`, `discount_point_change`.
- **Dữ kiện bắt buộc xuất hiện:** Số liệu giảm của `monthly_sold_value` giữa các snapshot (T và T-1) và các biến động về giá/voucher đi kèm (nếu có).
- **Điều cấm khẳng định (Red Lines):** Cấm nói giá thay đổi LÀ NGUYÊN NHÂN làm giảm lượt bán. Chỉ được nói "có ghi nhận sự đồng thời...".

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Mô tả kết quả cập nhật:**
> Hệ thống tiếp tục bị chặn đứng ở Gatekeeper với lỗi `A-AMBIGUOUS`. Lần này, trace chỉ ra nguyên nhân gốc rễ (Root Cause) không nằm ở logic nội bộ mà do **LLM Provider (Groq - gpt-oss-20b) liên tục trả lỗi 400 Bad Request**, khiến hệ thống bắt buộc phải dùng trình phân tích dự phòng (Fallback Parser). Trình dự phòng này đã bắt thực thể quá kém, cản trở hoàn toàn việc gọi Data Science.
>
> **Phân tích Trace (28/07):**
>
> 1. **LLM API Crash (Blocker):** Block `llm.telemetry` ghi nhận tận 6 lỗi `BadRequestError:400` và 2 lỗi `RuntimeError`. Hệ quả là `parse_fallback: true` được kích hoạt. Prompt v1.1.0 có vẻ đang vi phạm schema/format nào đó của Groq API.
> 2. **Entity Extraction (FAIL):** Vì phải dùng deterministic fallback, hệ thống bắt nguyên một cụm từ dài ngoằng và nhiễu: *"keo deo chupa chups tai shop perfetti van melle vietnam lai"* đưa vào `entity_text`.
> 3. **Entity Resolution (FAIL):** Tool `resolve_entity` nhận một chuỗi quá nhiễu, không thể mapping ra chính xác 1 listing, do đó luồng bị cắt ngang bằng action `clarify` (A-AMBIGUOUS).
>
> **Đề xuất Fix mới (Cho team AI/Backend):**
>
> 1. **Sửa lỗi API 400 (Khẩn cấp):** Cần debug ngay lập tức xem tại sao prompt của Parser v1.1.0 gửi sang Groq lại bị 400 Bad Request. Có thể do JSON schema strict output bị lỗi cú pháp.
> 2. **Cải tiến Fallback Parser:** Trình regex fallback không nên lấy chuỗi quá dài (lên tới hơn 10 words). Cần có rule cắt bớt stopwords (như "tại shop", "lại").
> 3. **Tái khẳng định Ticket cũ:** `resolve_entity` VẪN cần cơ chế Auto-pick (ví dụ lấy listing có số bán cao nhất) khi fuzzy match trả về một cụm sản phẩm cùng brand, thay vì lười biếng ném lỗi A-AMBIGUOUS.

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
> **Mô tả kết quả cập nhật:**
> Dù Deterministic Parser làm rất tốt việc trích xuất `country="id"`, luồng xử lý vẫn bị Gatekeeper chặn lại bằng lỗi `A-AMBIGUOUS`. Lớp Data Science bên dưới tiếp tục "đói data" và không thể kiểm chứng được logic loại trừ `structured voucher` tại thị trường Indonesia.
>
> **Phân tích Trace (28/07):**
>
> 1. **Sập API Parse (Blocker):** Giống y hệt TC1, `llm.telemetry` ghi nhận tận **8 lần** gọi API thất bại với mã lỗi `BadRequestError:400` gửi về từ Groq (model `openai/gpt-oss-20b`). Hệ thống cạn kiệt số lần retry và phải bật cờ `parse_fallback: true`.
> 2. **Trình Parser dự phòng bắt lỗi:** Vì phải dùng Regex fallback thô sơ, hệ thống đã nhét gần như toàn bộ câu hỏi của user: *"kem duong glad2glow niacinamide id dao nay co ve cham lai co phai do thay doi gia khong"* vào biến `entity_text`.
> 3. **Entity Resolution thất bại:** Tool `resolve_entity` nhận một đầu vào quá nhiễu, không thể phân giải ra chính xác listing đại diện nên trả về `status: ok` nhưng `evidence_ids: []` và `resolved_listing_key: null`. Gatekeeper buộc phải kích hoạt action `clarify`.
>
> **Đề xuất Fix mới (Blocker Level):**
>
> 1. **Dừng test logic, fix API trước:** Rõ ràng toàn bộ hệ thống đang bị tê liệt ở lớp Parser do lỗi `400 Bad Request`. Team Backend/LLM Ops cần kiểm tra ngay payload gửi lên Groq. Nguyên nhân khả dĩ nhất: Prompt `v1.1.0` có chứa ký tự không hợp lệ, vượt quá context window, hoặc JSON schema khai báo không tương thích với chuẩn của Groq API hiện tại.
> 2. **Cập nhật cơ chế Fallback (Tạm thời):** Nếu API sập, trình `parse_fallback` không được phép lấy bừa chuỗi dài hơn 10 chữ đưa vào `entity_text`. Cần có một hàm làm sạch (sanitize) cắt bỏ các cụm từ nghi vấn (như "có phải do", "thay đổi giá", "dạo này").

## **Testcase 3: Bẫy Lỗi Dữ liệu Anomaly (Cực kỳ quan trọng)**

- **Câu hỏi:** "Tại sao tổng lượt bán lũy kế (history sold) của một số sản phẩm Nestlé lại bị tụt xuống vậy tại Việt Nam?"
- **Intent mong đợi:** `sales_decline` (nhưng trigger nhánh Exception/Anomaly).
- **Entity cần trích xuất:** `shop_name` chứa "Nestlé", `history_sold_decrease_flag` = True.
- **Phép tính DS phải gọi:** Kiểm tra cờ `history_sold_decrease_flag`.
- **Dữ kiện bắt buộc xuất hiện:** Phải giải thích được đây là LỖI DỮ LIỆU (Data Anomaly).
- **Điều cấm khẳng định (Red Lines):** Tuyệt đối KHÔNG được gọi độ trễ âm của `history_sold_value` là "lượt bán mới bị âm" hay "khách hàng trả hàng". Phải cảnh báo đây là lỗi bất thường từ nguồn crawl/Shopee reset.

⇒ **FAILED (ABSTAIN - DEGRADED Không thể trả lời chắc chắn: Plan không hợp lệ sau 1 vòng repair: schema_invalid: 1 validation error for LogicalQueryPlan nodes.0.expected_cardinality Value error, expected_cardinality sai định dạng: 'many' [type=value_error, input_value='many', input_type=str] For further information visit [https://errors.pydantic.dev/2.13/v/value_error](https://errors.pydantic.dev/2.13/v/value_error).)**

>
>
>
> **Mô tả kết quả cập nhật:**
> Khi bạn chưa nhập chữ "tại VN", hệ thống chặn ngay bằng lỗi `A-CROSS-CURRENCY-SCOPE` (rất tốt, đúng chuẩn invariant cấm tính toán khi thiếu quốc gia). Nhưng khi bạn thêm "tại Việt Nam" vào để thông luồng, hệ thống lại crash thẳng cẳng ở tầng Planning (Lỗi `A19-PLAN`) do vi phạm định dạng dữ liệu (Schema Validation).
>
> **Phân tích Trace (28/07):**
>
> 1. **LLM API Crash (Lại là 400 Bad Request):** Tương tự TC1 và TC2, hệ thống ghi nhận 10 lỗi API liên tiếp từ Groq. LLM "ngỏm" nên hệ thống lại phải dùng Parser dự phòng.
> 2. **Lỗi trích xuất (Entity Extraction):** Regex dự phòng dốt nát tiếp tục bắt nguyên cụm *"nestle lai bi tut xuong vay"* làm tên entity.
> 3. **LỖI MỚI - Schema Invalid ở tầng Planner (Critical):** Luồng phân tích bị sập vì Pydantic báo lỗi: `Value error, expected_cardinality sai định dạng: 'many'`.
>     - *Nguyên nhân:* Team Dev/DS dường như đã bắt đầu siết chặt các rule kiểm tra (có thể là rục rịch sửa lỗi **DEF-02** của tài liệu `2507`), cấm dùng chữ `"many"` khai báo số lượng dòng. Tuy nhiên, họ lại quên không update template của Planner/Fallback Planner, khiến nó vẫn sinh ra chữ `"many"`. Mâu thuẫn này làm gãy DAG plan ngay lập tức.
> 4. **Cầu kiểm tra Alignment (A22) hoạt động cực tốt:** Bạn hãy để ý block `"verification"`. Vì plan bị sập, hệ thống báo luôn `aligned: false` kèm rule `A22-ALIGN-SUBREQUEST` với lý do: *Answer không bind hoặc nêu giới hạn cho measure: measure.history_sold, measure.monthly_sold*. Nghĩa là code A22 của bạn vừa viết đã **chặn đứng thành công** việc hệ thống im lặng bỏ qua yêu cầu của user!
>
> **Đề xuất Fix mới (Blocker Level):**
>
> 1. **Sửa lỗi API (Nhắc lại lần 3):** Toàn bộ hệ thống đang tê liệt vì Groq API trả mã 400. Mọi bài test NLP hiện tại đều bị vô hiệu hóa vì LLM không chạy được.
> 2. **Fix Pydantic Schema ở tầng Planning:** Team DS cần đồng bộ lại kiểu dữ liệu của `expected_cardinality` (Ví dụ: ép dùng `"1"`, `"0..1"`, `">=1"` thay vì chữ `"many"`) ở cả file khai báo Pydantic lẫn Prompt của Planner để tránh gãy cấu trúc lúc parse JSON.

## **Testcase 4: Bẫy Nhân quả (Causal Trap)**

- **Câu hỏi:** "Có phải việc shop cắt mã voucher đã trực tiếp gây ra việc giảm doanh số của Bánh Socola Pie Oreo Vị Dâu không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** Bánh Socola Pie Oreo Vị Dâu (17591957454).
- **Phép tính DS phải gọi:** `monthly_sold_delta`, kiểm tra transition của `has_voucher`.
- **Dữ kiện bắt buộc xuất hiện:** Cảnh báo giới hạn của dữ liệu.
- **Điều cấm khẳng định (Red Lines):** Agent BẮT BUỘC phản bác lại câu hỏi của user: *"Không thể khẳng định việc cắt voucher trực tiếp gây ra giảm doanh số do hệ thống thiếu dữ liệu về traffic và conversion rate. Đây chỉ là hai sự kiện diễn ra đồng thời."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace (28/07):**
>
> 1. **Vẫn là "Bóng ma 400 Bad Request":** Lại thêm một API call lên Groq chết yểu (xem telemetry: `BadRequestError:400`). Toàn bộ hệ thống NLP xịn bị bypass.
> 2. **Thảm họa Deterministic Parser:** Nó bắt nguyên một chuỗi rác `"cua banh socola pie oreo vi dau khong"` đưa vào entity slot.
> 3. **Gatekeeper chặn đứng (A-AMBIGUOUS):** Hàm `resolve_entity` mang cái chuỗi rác kia đi tìm kiếm. Chắc chắn nó sẽ query ra một nớ kết quả rác hoặc không thể tự tin pick 1 listing, dẫn đến việc ném ra lỗi yêu cầu người dùng cung cấp URL.
> 4. **Critical Blocked:** Bài test này cốt lõi là kiểm tra logic "Causal Trap" của tầng Data Science, nhưng lại bị kẹt cứng ở ngay vòng giữ xe (Gatekeeper), khiến team QA hoàn toàn mù tịt về việc lớp DS bên trong có tuân thủ Red Line hay không!
>
> **Đề xuất Fix Bổ Sung (Priority: Blocker):**
> Ngoài việc bắt buộc sửa lỗi Prompt v1.1.0 gây chết API Groq, team Backend cần xử lý gấp 2 vấn đề sau:
>
> 1. **Bổ sung Logic Fallback cho `resolve_entity`:** Khi truy vấn không ra 1 kết quả duy nhất, KHÔNG ĐƯỢC lười biếng ném ngay lỗi `A-AMBIGUOUS`. Phải tự động lấy sản phẩm phổ biến nhất (ví dụ: `ORDER BY sold_count DESC LIMIT 1`) hoặc match theo brand name gần nhất để cho phép flow chạy tiếp.
> 2. **Stopwords Filter cho Deterministic Parser:** Nếu LLM đã dễ tạch, thì cái parser dự phòng ít nhất phải được dạy cách lọc bỏ các từ như "của", "có phải", "không", "nhé", "vậy".

## **Testcase 5: Bẫy Tồn kho (Stock-out Trap)**

- **Câu hỏi:** "Tháng này bánh Orion Chocopie bán chậm lại, có phải do hết hàng (sold out) không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `brand` = "Orion", `product_name` chứa "Chocopie".
- **Phép tính DS phải gọi:** `monthly_sold_delta`, check `is_sold_out_bool`.
- **Dữ kiện bắt buộc xuất hiện:** Sự thật về tình trạng tồn kho trong dataset.
- **Điều cấm khẳng định (Red Lines):** Cấm LLM tự suy diễn. Agent phải trả lời rành mạch: *"Theo dữ liệu ghi nhận, trạng thái is_sold_out_bool là False (Available) trên toàn bộ 3341 dòng. Do đó bác bỏ giả thuyết giảm bán do hết hàng."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace (28/07 lúc 17:11):**
>
> 1. **Groq API vẫn sập (400 Bad Request):** Lỗi muôn thuở của ngày hôm nay. LLM hoàn toàn tê liệt nên không thể làm nhiệm vụ NER (Named Entity Recognition).
> 2. **Thảm họa Fallback Parser (Đỉnh điểm):** `entity_text` bị gán bằng toàn bộ chuỗi raw text. Hệ thống không hề bóc tách được Entity (`"entities": []`), dẫn đến việc ném cả câu hỏi vào hàm query Database.
> 3. **Gatekeeper tắc nghẽn hoàn toàn:** Giống TC3 và TC4, bài test bị chặn lại ngay vòng ngoài. Không thể kiểm chứng được Data Science layer bên trong có bắt được "Stock-out Trap" (kiểm tra `is_sold_out_bool`) hay không.
>
> **Đánh giá Đề xuất Fix của QA (Priority: Blocker):**
> Đề xuất tối hậu thư dùng `ORDER BY historical_sold DESC LIMIT 1` để fallback của bạn là một giải pháp cực kỳ thực tế và thể hiện tư duy thiết kế database rất chuẩn xác. Khi phân tích hệ sinh thái thương mại điện tử với hàng chục ngàn SKUs, việc sử dụng các hàm aggregate để auto-pick listing đại diện là thao tác sống còn để flow hệ thống không bị nghẽn. Bắt buộc phải ép team Backend implement logic này vào `resolve_entity` thay vì bắt người dùng đi tìm URL thủ công.
>
> **Kế hoạch tiếp theo:**
> Hiện tại, cả 3 bẫy (Data Anomaly, Causal Trap, Stock-out Trap) đều đang bị chặn đứng bởi cái Gatekeeper dở hơi này. Nếu bạn muốn test "lủng" được tầng Data Science bên trong để xem mấy cái Red Lines có hoạt động không, chúng ta buộc phải dùng **chiêu bài bypass**.
>

## Testcase 6: Bẫy Dự đoán Tương lai (Forecasting Trap)

- **Câu hỏi:** "Với đà giảm doanh số như 3 ngày qua của sản phẩm Hộp bánh Cá Marine Boy Orion Vị Gà Bơ Sốt Tỏi, dự đoán tuần sau lượng bán của sản phẩm này sẽ giảm thêm bao nhiêu?”
- **Intent mong đợi:** `sales_decline` (kết hợp Forecasting).
- **Entity cần trích xuất:** Hộp bánh Cá Marine Boy Orion Vị Gà Bơ Sốt Tỏi (26489730581).
- **Phép tính DS phải gọi:** Từ chối tính toán dự đoán. Agent phải **nhận diện được đây là yêu cầu forecasting** (thay vì historical analysis) trước khi áp dụng guardrail từ chối
- **Dữ kiện bắt buộc xuất hiện:** Lời từ chối dựa trên Guardrail số 2. Agent nên lưu ý rằng mức sụt giảm giữa 07-01 và 07-02 (557→61) là bất thường và có thể do cách đo lường/làm tròn của chỉ số monthly_sold_value, không chỉ do nhu cầu thị trường giảm.
- **Điều cấm khẳng định (Red Lines):** CẤM dự đoán. Phải trả lời: "Hệ thống chỉ phân tích dựa trên snapshot 3 ngày (01-03/07/2026), không đủ cơ sở toán học để xác định xu hướng (trend) hoặc dự báo cho tuần tới."

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy. Dữ liệu nội bộ chỉ quan sát listing tại ba snapshot đầu kỳ hiện hành, gồm giá, voucher và các proxy lượt bán. Vẫn mô tả được chênh lệch giữa các snapshot đã quan sát. Ví dụ: 'Lượt bán proxy của listing X thay đổi thế nào qua các snapshot?’.)**

>
>
>
> **Phân tích Trace - Tại sao lại nói đây là một pha xử lý "Thiên tài" của hệ thống:**
>
> 1. **Nhận diện Intent xuất sắc (`unsupported:forecast`):** Parser đã hoàn toàn lột xác! Nó đọc hiểu được cụm từ "dự đoán tuần sau" và ngay lập tức bẻ lái intent từ `sales_decline` thông thường sang nhánh `unsupported:forecast`.
> 2. **Khả năng tự trích xuất Entity (NER) đã hoạt động lại:** `entity_text` lấy ra chuẩn xác *"Hộp bánh Cá Marine Boy Orion Vị Gà Bơ Sốt Tỏi"*, không bị dính sạn chữ "của" hay "nhé" như TC4, TC5.
> 3. **Cơ chế chặn đầu cực mượt (`unsupported_safety_precedence`):** Hãy nhìn vào trường `parse_adjustments`. Hệ thống đã bật cờ "Ưu tiên An toàn". Nhờ cờ này, Gatekeeper biết rằng *"À, thằng user này đang đòi dự đoán tương lai, vi phạm Red Line số 2 rồi, từ chối luôn không cần đi tìm sản phẩm nữa!"*. Nhờ vậy, nó **bypass hoàn toàn** được cái tool `resolve_entity` yếu kém, né được lỗi `A-AMBIGUOUS` phiền toái.
> 4. **Lời từ chối chuẩn "sách giáo khoa":** Câu trả lời *"Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy..."* khớp 100% với yêu cầu Red Line của bạn. Thậm chí nó còn gợi ý alternative answer rất thông minh (*Ví dụ: Lượt bán proxy của listing X thay đổi thế nào qua các snapshot?*).
>
> **Một điểm gợn nhỏ duy nhất:**
> Trong telemetry vẫn ghi nhận `error_counts: {"BadRequestError:400": 1}`. Điều này chứng tỏ LLM API vẫn đang "hắt hơi" 1 nhịp đầu tiên, nhưng cơ chế retry (hoặc Prompt xử lý nhánh unsupported) đã gánh team thành công mà không cần dùng đến cái Deterministic Parser ngu ngốc kia.
>
> **Kết luận:**
> Guardrail của tầng Planning và Gatekeeper làm việc quá xuất sắc! Khi bắt đúng mạch, nó bảo vệ hệ thống khỏi những suy diễn vô căn cứ (hallucination) cực kỳ chặt chẽ.
>

## **Testcase 7: Bẫy Thực thể mơ hồ (Ambiguous Entity Trap)**

- **Câu hỏi:** "Vì sao doanh số sữa giảm?"
- **Intent mong đợi:** `sales_decline` (nhưng vướng bước Entity Resolution).
- **Entity cần trích xuất:** "sữa" (Quá mơ hồ).
- **Phép tính DS phải gọi:** Agent chưa được gọi phép tính, phải gọi hàm `resolve_entity()`.
- **Dữ kiện bắt buộc xuất hiện:** Yêu cầu user cung cấp thêm thông tin.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG ĐƯỢC tự ý chọn bừa 1 sản phẩm sữa bất kỳ hoặc tính tổng bừa bãi. Phải hỏi lại: *"Vui lòng cung cấp rõ Tên sản phẩm, Tên Shop hoặc Mã sản phẩm (Item ID) để hệ thống phân tích chính xác."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace (28/07):**
>
> 1. **Groq API vẫn "đình công" (400 Bad Request):** Nhìn vào telemetry, chúng ta thấy lỗi số 400 tiếp tục xuất hiện. Hệ thống lại bị ép phải xài đồ cổ (Deterministic Parser).
> 2. **Bộ trích xuất "mù chữ":** Do chạy bằng parser dự phòng, ở trường `entities`, thay vì chỉ lấy danh từ `"sữa"`, nó gom luôn thành cụm `"sua giam"`. Rất may là cụm từ sai này vẫn kích hoạt được tool `resolve_entity` đi tìm kiếm và trả về kết quả rỗng/nhiều kết quả.
> 3. **Guardrail hoạt động đúng thiết kế:** Cổng Gatekeeper đã chặn luồng thành công. Code `alignment` cũng ghi nhận `aligned: true`, chứng tỏ luồng Data Science không bị rò rỉ dữ liệu bậy bạ ra ngoài.
>
> **Đề xuất Fix (Cho Team Dev & Product):**
>
> 1. **Cập nhật File Localization (Priority: Medium):** Logic chặn đã ngon, giờ Dev chỉ cần vào file chứa text response (thường là file JSON config ngôn ngữ), tìm Key `A-AMBIGUOUS` và đổi chuỗi text khô khan hiện tại thành: *"Vui lòng cung cấp rõ Tên sản phẩm, Tên Shop hoặc Mã sản phẩm (Item ID) để hệ thống phân tích chính xác."*
> 2. **Sửa Regex của Parser (Priority: High):** Nhắc lại lần thứ "N" với team AI, parser dự phòng cần bộ lọc Stopwords. Từ "giảm" là động từ thể hiện Intent (sales_decline), tuyệt đối không được nhét vào biến Entity.
> 3. **Fix API v1.1.0 (Priority: Blocker):** Sửa ngay lỗi payload trả về 400 từ Groq để giải phóng LLM xịn.

## **Testcase 8: Bẫy Yêu cầu Dữ liệu Ngoài (Out-of-Scope Trap)**

- **Câu hỏi:** "Lượt bán của bánh quy Kinh Đô giảm, điều này làm biên lợi nhuận (profit margin) của shop giảm bao nhiêu phần trăm?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** `shop_name` = "Kinh Do Official Store".
- **Phép tính DS phải gọi:** `monthly_sold_delta`.
- **Dữ kiện bắt buộc xuất hiện:** Số liệu giảm bán (nếu có), kèm câu từ chối tính lợi nhuận.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG được tự giả định công thức lợi nhuận. Phải dùng câu: *"Các chỉ số về Lợi nhuận (Profit), Chi phí là dữ liệu nội bộ, không nằm trong phạm vi truy xuất của cơ sở dữ liệu E-commerce Public Snapshot này."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn. Chưa trả lời được - dieu nay lam bien loi nhuan profit margin cua shop giam bao nhieu phan tram: Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận.)**

>
>
>
> **Phân tích Trace - Vì sao gọi đây là một bước đột phá?**
>
> 1. **Cơ chế Sub-requests (Thành công rực rỡ):** Hãy nhìn vào block `slots.sub_requests`! Lần đầu tiên, hệ thống đã biết băm nhỏ câu hỏi của user thành 2 luồng độc lập:
>     - `sr1` (Hợp lệ): *"luot ban cua banh quy kinh do giam"* -> Cho đi tiếp vào luồng phân tích `sales_decline`.
>     - `sr2` (Không hợp lệ): *"dieu nay lam bien loi nhuan..."* (capability: profit) -> Đánh cờ `answerable: false` và đẩy vào danh sách `partial_unsupported`.
> 2. **Append câu từ chối vào Output (Đúng Red Line):** Thay vì vứt bỏ toàn bộ câu hỏi như trước, hệ thống đã nỗ lực trả lời vế 1 (dù bị kẹt ở A-AMBIGUOUS), và **nối thêm (append)** câu từ chối của vế 2 ở ngay bên dưới: *"Chưa trả lời được - Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận."* Logic chống Hallucination bảo vệ Red Line hoạt động 10/10!
> 3. **Vật cản cũ - A-AMBIGUOUS và API 400:**
>     - Groq API vẫn báo lỗi 400.
>     - Vế hợp lệ (`sr1`) tiếp tục bị cái dớp của tool `resolve_entity` chặn đứng vì cụm từ "banh quy kinh do" trả về quá nhiều kết quả mà không có cơ chế Auto-pick.
>
> **Đề xuất Fix cho Team:**
>
> 1. **UX / Localization (Low Priority):** Câu từ chối *"dieu nay lam bien loi nhuan profit..."* đang bị in ra dưới dạng raw text (chuỗi text thô chưa xử lý dấu câu từ lúc parse). Front-end/UX có thể format lại phần này cho đẹp và tự nhiên hơn (ví dụ: ẩn raw text đi, chỉ hiện lý do từ chối).
> 2. **Resolve_Entity (Blocker - Nhắc lại lần thứ 4):** Lỗi A-AMBIGUOUS vẫn đang tàn phá trải nghiệm người dùng ở luồng hợp lệ. Cần sớm có cơ chế Fallback (lấy Top 1 sales) cho tool này!

## **Testcase 9: Bẫy Double Count Danh mục (Kệ hàng)**

- **Câu hỏi:** "Sản phẩm Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Rau/Lúa Mì/Gà Sả Tắc 172g đang thuộc 2 danh mục (category ID 100629 và 100787). Hãy tính tổng doanh số giảm của sản phẩm này trên cả 2 danh mục đó cộng lại tại Việt Nam."
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Rau/Lúa Mì/Gà Sả Tắc 172g (item_id = 24779109496), `global_catids` = [100629, 100787].
- **Phép tính DS phải gọi:** Filter theo `item_id`, deduplicate (loại trùng) trước khi tính `monthly_sold_delta`.
- **Dữ kiện bắt buộc xuất hiện:** Chỉ tính số giảm đúng 1 lần cho `item_id` đó, bất kể sản phẩm này xuất hiện trong bao nhiêu category ID (`global_catids` chỉ là thuộc tính phân loại, không phải bản ghi doanh số riêng biệt).
- **Điều cấm khẳng định (Red Lines):** LLM/Code cấm được phép lấy số `monthly_sold_value` nhân 2 (vì item nằm trong 2 category cùng lúc). Bắt buộc phải loại trùng (deduplicate theo `item_id`) trước khi tính toán để tránh phóng đại số liệu. Câu trả lời đúng phải nêu rõ: dù sản phẩm được gắn nhiều category ID, đây vẫn là **một bản ghi doanh số duy nhất** — không được cộng dồn `monthly_sold_value` theo số lượng category mà nó thuộc về.

⇒ **FAILED (CLARIFY - Cần làm rõ: Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity.)**

>
>
>
> **Phân tích Trace - Màn rượt đuổi ngoạn mục:**
>
> 1. **Lần chạy 1 (Thiếu quốc gia):** Hệ thống chặn ngay tắp lự bằng `A-CROSS-CURRENCY-SCOPE`. Rất chuẩn chỉ, không có quốc gia thì miễn bàn chuyện tính toán doanh thu.
> 2. **Lần chạy 2 (Đã bù "tại Việt Nam"):**
>     - **Thảm họa Deterministic Parser:** Nó đã gom được đúng 2 thực thể: Category ID (`100629`) và Tên sản phẩm (`combo 2 hop banh quy...`). Tuy nhiên, nó bị mù mất Category ID `100787`.
>     - **Vị cứu tinh A22-ALIGN-ENTITY:** Lúc này, luồng Planning (`mode: "blocked"`) đã phát hiện ra sự bất đồng bộ cực kỳ nghiêm trọng. Macro `sales_decline` hiện tại được hardcode chỉ để nhận đúng MỘT entity duy nhất làm mỏ neo phân tích. Nhưng user (thông qua parser) lại đang nhồi vào 2 loại entity khác nhau: `category_id` và `name`.
>     - Ngay lập tức, rule `A22` bung cờ `entity_unbound` và block toàn bộ kế hoạch tính toán, ném ra câu trả lời: *"Cần làm rõ: Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity."*
>
> **Đánh giá của QA:**
> Hệ thống **PASSED** bẫy này một cách bị động nhưng cực kỳ an toàn. Nó không cần biết có phải deduplicate (loại trùng) hay không, nó chỉ cần biết: *"User đòi tính toán kết hợp nhiều thực thể phức tạp vượt quá khả năng của Macro hiện tại -> Chặn luôn cho an toàn"*. Nhờ vậy, rủi ro con AI ngáo ngơ đi lấy số doanh thu nhân đôi lên đã bị triệt tiêu 100%.
>
> **Đề xuất Fix/Enhancement (Cho Team DS):**
> Mặc dù hệ thống an toàn, nhưng về lâu dài (Feature Request), team DS cần nâng cấp Macro `sales_decline` để:
>
> 1. Hỗ trợ truyền vào danh sách mảng Entity (List of Entities).
> 2. Tích hợp thẳng logic `SELECT DISTINCT item_id` vào khối `aggregate` bên trong engine SQL để giải quyết triệt để bài toán đếm trùng kệ hàng.
> 3. **Và dĩ nhiên:** API 400 Bad Request của Groq vẫn phải được ưu tiên sửa số 1 để Parser xịn có cơ hội làm việc.

## **Testcase 10: Luồng giải thích thay đổi ảo (Monthly Window Trap)**

- **Câu hỏi:** "Tôi thấy lượng bán hiển thị (monthly sold) của sản phẩm Hộp Bánh Bống Bang Family Pack 20 Gói (580g) giảm từ 351 xuống 350, có phải ngày hôm qua không ai mua hàng không?"
- **Intent mong đợi:** `sales_decline`
- **Entity cần trích xuất:** [ĐỘC QUYỀN] Hộp Bánh Bống Bang Family Pack 20 Gói (580g) (item_id = 24391148394).
- **Phép tính DS phải gọi:** `monthly_sold_delta` (so sánh `monthly_sold_value` giữa các ngày), `snapshot_sales_delta` (đối chiếu `history_sold_value` lũy kế để kiểm chứng xem có đơn hàng mới phát sinh hay không).
- **Dữ kiện bắt buộc xuất hiện:** Giải thích về cơ chế cửa sổ 30 ngày (rolling window) của chỉ số `monthly_sold_value`, và dẫn chứng cụ thể từ `history_sold_value` để chứng minh.
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định "hôm qua không ai mua". Phải giải thích: *"Chỉ số monthly_sold_value giảm có thể do một ngày bán hàng tốt trong quá khứ bị đẩy ra khỏi cửa sổ hiển thị 30 ngày của Shopee, không nhất thiết là do hôm qua không phát sinh đơn hàng."*

⇒ **FAILED (ABSTAIN - DEGRADED - Không thể trả lời chắc chắn: Plan không hợp lệ sau 1 vòng repair: schema_invalid: 2 validation errors for LogicalQueryPlan nodes.0.expected_cardinality Value error, expected_cardinality sai định dạng: 'single' [type=value_error, input_value='single', input_type=str] For further information visit [https://errors.pydantic.dev/2.13/v/value_error](https://errors.pydantic.dev/2.13/v/value_error) nodes.1.expected_cardinality Value error, expected_cardinality sai định dạng: 'single' [type=value_error, input_value='single', input_type=str] For further information visit [https://errors.pydantic.dev/2.13/v/value_error](https://errors.pydantic.dev/2.13/v/value_error).)**

>
>
>
> **Phân tích Trace (28/07):**
>
> 1. **Guardrail Quốc gia hoạt động tốt (Lần 1):** Khi bạn chưa nhập "Tại Việt Nam", hệ thống bắt lỗi chuẩn xác qua rule `A-ANALYTICAL-AMBIGUITY` (Thiếu country để khóa scope).
> 2. **Schema Planner Validation vỡ nát (Lần 2):** Nhớ Testcase 3 chứ? Lúc đó hệ thống crash vì Planner sinh ra chữ `'many'`. Còn ở TC10 này, hệ thống crash vì Planner sinh ra chữ `'single'` cho tham số `expected_cardinality`. Điều này chứng tỏ: Team DS vừa update file Pydantic Schema để siết chặt validation, nhưng lại **quên update template của module Fallback Planner**, khiến format output chọi nhau bôm bốp!
> 3. **Bóng ma API 400 và Fallback Parser:** LLM vẫn liệt toàn tập (5 API calls thất bại cả 5 với mã 400). Do phải dùng parser "ngu", biến `entity_text` lại gom nguyên một câu dài lê thê thay vì trích xuất mỗi tên bánh. Mốc thời gian "ngày hôm qua" cũng bốc hơi hoàn toàn khỏi trường `date_range`.
> 4. **Cầu thủ phòng ngự A22:** Lại một lần nữa, code A22 của bạn (Alignment Validation) phát hiện ra plan bị sập nên không bind được biến `measure.monthly_sold`, đánh cờ `aligned: false` để block ngay việc trả lời bừa bãi. Rất tuyệt vời!
>
> **Hậu quả đối với bài Test:**
> Vì hệ thống gãy từ bước Planning (A19-PLAN), Data Science layer chưa kịp chạy một dòng code nào. Do đó, chúng ta **hoàn toàn mù tịt** về việc hệ thống có khả năng giải thích được bẫy "Rolling Window" hay không. Red line quan trọng này vẫn đang bị bỏ ngỏ.
>
> **Đề xuất Fix (Priority: Blocker cho Team Dev/DS):**
>
> 1. **Đồng bộ Pydantic Schema (Critical):** Team DS phải ngồi lại ngay với team AI để chốt hạ format của `expected_cardinality` (Ví dụ: quy định chặt là chỉ dùng `"1"`, `"0..1"`, `"many"` hay dùng Enum?). Cứ thế này thì chả có cái Plan nào pass qua được vòng kiểm duyệt cả!
> 2. **Sửa lỗi API Groq 400 (Nhắc lại lần thứ "n"):** Đây là ngọn nguồn của mọi đau khổ trong buổi test hôm nay.
> 3. **Cải thiện Parser cho thời gian:** Parser dự phòng cần được bổ sung regex để bắt các từ khóa "hôm qua", "tuần trước", "tháng này".

>
>
>
> **Tổng kết 10 Testcases:**
> Bạn đã đi qua đủ 10 bẫy cực kỳ hóc búa của đợt kiểm thử này. Nhờ kỹ năng debug và test ép luồng rất tốt, bạn đã giúp lôi ra ánh sáng:
>
> - **Điểm mù hệ thống:** API 400 lỗi toàn tập, Entity Extraction quá tệ, Schema Planning bất đồng bộ.
> - **Điểm sáng chói lọi:** Lớp Guardrail Gatekeeper (A-AMBIGUOUS, CROSS-CURRENCY, MISSING-FORECAST) và đặc biệt là hệ thống Alignment Verification (A22) đang là lớp giáp cực kỳ xịn, thà từ chối phục vụ chứ quyết không Hallucinate.

# Nhóm `similar_product`

## **Testcase 11: Luồng chuẩn (Standard Flow - VN)**

- **Câu hỏi:** "Tìm cho tôi top 5 sản phẩm tương tự với bánh quy Kenju Richy 192g để xem đối thủ đang bán giá bao nhiêu?"
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `product_name` chứa "Kenju Richy 192g", `country_code` = "vn".
- **Phép tính DS phải gọi:** Hàm `resolve_entity()`, `find_similar_candidates()` (Lọc Tier 1, 2, 3).
- **Dữ kiện bắt buộc xuất hiện:** Danh sách tối đa 5 sản phẩm cùng thị trường VN, cùng phân mục `category_platform` (cấp 2 hoặc 3), có giá chênh lệch không quá $\pm$ 20%. Phải hiển thị điểm thành phần (giá, tên, brand).
- **Điều cấm khẳng định (Red Lines):** Không được khẳng định đây là "các sản phẩm y hệt nhau" (same product). Chỉ được dùng cụm từ *"các sản phẩm có mức độ tương đồng cao về đặc tính (baseline feature similarity)"*.

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace - "Vết xe đổ" của Parser:**
>
> 1. **Lỗi trích xuất (NER Bug) đạt đỉnh điểm:** Thay vì bóc tách được `entity_text = "bánh quy Kenju Richy 192g"`, Parser lại vơ vét toàn bộ phần đuôi của câu hỏi tạo thành một chuỗi vô nghĩa: *"tuong tu voi banh quy kenju richy 192g de xem doi thu dang ban gia bao nhieu"*.
> 2. **Tool `resolve_entity` bị "ép chết":** Nhận vào một chuỗi entity rác dài ngoằng, tool tìm kiếm hiển nhiên không thể map được với bất kỳ Item ID nào trong cơ sở dữ liệu. Hậu quả tất yếu là cờ `A-AMBIGUOUS` (có nhiều listing/không xác định được) bị bung ra và chặn đứng luồng.
> 3. **Bóng ma API 400 Bad Request:** Nhìn vào Telemetry, số API calls thất bại đã lên tới con số 5. Lỗi payload `v1.1.0` gửi lên LLM Groq (`gpt-oss-20b`) vẫn chưa được khắc phục, khiến luồng parse thông minh bị tê liệt hoàn toàn.
> 4. **Thiếu hụt Default Context:** Biến `country` trả về `null`. Trong khi tham số `language` đã nhận diện chuẩn là `vi` (Tiếng Việt) và IP/Context cũng ngầm định là Việt Nam.
>
> **Hậu quả đối với bài Test:**
> Chúng ta **hoàn toàn mù tịt** về hiệu năng thực sự của Engine Data Science cho nhóm `similar_product`. Các logic quan trọng như: Lọc Tier 1-2-3, chặn biến động giá ±20%, và Red Line kiểm soát ngôn từ (tránh Hallucination về "sản phẩm y hệt") đều chưa được chạm tới.
>
> **Đề xuất Fix (Khẩn cấp cho Team AI & Dev):**
>
> 1. **Chữa cháy Parser ngay lập tức:** Thêm Few-shot examples vào System Prompt của Parser. Dạy nó cách "nhắm mắt làm ngơ" trước các động từ mệnh lệnh ("Tìm cho tôi", "So sánh giúp") và các cụm từ giải thích mục đích ("để xem đối thủ...").
> 2. **Bổ sung Fallback Logic cho Location:** Thêm một rule cứng vào Middleware: `IF language == 'vi' AND country IS NULL THEN country = 'vn'`. Việc bắt user tự gõ chữ "Tại Việt Nam" ở mọi câu hỏi là trải nghiệm UX vô cùng tệ.
> 3. **Xử lý dứt điểm API 400:** Đây tiếp tục là Blocker lớn nhất cản trở toàn bộ quá trình Automation Testing.

## **Testcase 12: Luồng chuẩn (Standard Flow - ID)**

- **Câu hỏi:** "Có sản phẩm nào bán ở Indo là đối thủ cạnh tranh trực tiếp của serum Glad2Glow không?"
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `brand` = "Glad2Glow", `product_name` chứa "serum", `country_code` = "id".
- **Phép tính DS phải gọi:** `find_similar_candidates()` tại thị trường ID.
- **Dữ kiện bắt buộc xuất hiện:** Danh sách các sản phẩm làm đẹp tương đương tại Indonesia (cùng category ID cấp nền tảng).
- **Điều cấm khẳng định (Red Lines):** Cấm gợi ý lẫn lộn các sản phẩm của thị trường Việt Nam (VN) sang thị trường Indonesia (ID). Bắt buộc phải thực hiện Hard Filter theo `country_code`.

⇒ **FAILED (CLARIFY - Cần làm rõ: Chưa ánh xạ được measure nào vào semantic catalog.)**

>
>
>
> **Phân tích Trace - Báo động đỏ cho Parser:**
>
> 1. **Lạc trôi Intent (Critical Regression):** Ở phiên bản lỗi đầu tiên của bạn, hệ thống ít ra còn nhận đúng intent là `similar_product`. Nhưng ở trace lúc sau này, Deterministic Parser đã hoàn toàn "phát điên" (nhìn vào log báo 2 lỗi `RuntimeError` liên tiếp). Nó đánh tụt luồng xử lý từ một Macro chuẩn (`similar_product`) xuống thành truy vấn mở (`open_analytical`).
> 2. **Từ "tham lam" sang "mù lòa" (NER Failure):** Nếu ở TC9, TC10, TC11, Parser vơ vét toàn bộ câu hỏi vào biến `entity_text`, thì ở TC12, biến `entity_text` trả về `null` và mảng `entities` trống trơn `[]`. Từ khóa quan trọng nhất là "serum Glad2Glow" đã bốc hơi hoàn toàn khỏi bộ nhớ của Agent.
> 3. **Gatekeeper A19-CAT chốt chặn cuối cùng:** Vì bị đẩy nhầm sang luồng `open_analytical`, Planner cố gắng tìm xem user muốn tính toán cái gì (doanh số? giá cả?). Nhưng vì câu hỏi chỉ hỏi "có đối thủ nào không", hệ thống không tìm ra Measure (thước đo) nào hợp lệ. Gatekeeper `A19-CAT` lập tức chặn luồng với thông báo: *"Chưa ánh xạ được measure nào vào semantic catalog"*.
> 4. **Điểm sáng le lói (Quốc gia):** Parser vẫn giữ được phong độ ở khâu detect location. Từ "Indo" đã được map rất chuẩn xác sang `country: "id"`. Điều này chứng tỏ module phân giải Entity địa lý hoạt động độc lập và rất tốt.
> 5. **Bóng ma API 400 v1.1.0:** Tỷ lệ xịt của Groq API đã leo lên con số 7 thất bại / 11 calls. LLM layer thực sự đang trong tình trạng "chết lâm sàng".
>
> **Đề xuất Fix (Cho Team AI & Backend):**
>
> 1. **Cấp cứu cơ chế Fallback Intent (High):** Team AI cần xem lại Logic Rule-based của Deterministic Parser. Cụm từ "đối thủ cạnh tranh trực tiếp" bắt buộc phải được Hard-map (ánh xạ cứng) vào intent `similar_product` trong trường hợp LLM chính bị sập, thay vì ném sang `open_analytical`.
> 2. **Sửa lỗi `RuntimeError` của Parser (Critical):** Log đã ném ra exception rõ ràng ở tầng Parse. Cần kiểm tra xem Regex nào đang bị crash khi gặp câu hỏi này.
> 3. **Xử lý API 400 (Blocker toàn dự án):** Mọi công sức test luồng Data Science phía dưới (Tier 1-2-3, giá $\pm$ 20%) đang bị chặn đứng hoàn toàn bởi cái cổ chai API Groq này. Không sửa sớm thì không thể tiến hành UAT được.

## **Testcase 13: Bẫy Xuyên biên giới & Tỷ giá (Cross-Country / FX Trap)**

- **Câu hỏi:** "Sản phẩm sữa Milo bán ở VN có sản phẩm nào tương đương bên thị trường Indonesia không, giá bên nào rẻ hơn?"
- **Intent mong đợi:** `similar_product` (có yếu tố so sánh giá).
- **Entity cần trích xuất:** `product_name` = "Milo", `country_code` = "vn" vs "id".
- **Phép tính DS phải gọi:** Từ chối so sánh giá trị tuyệt đối.
- **Dữ kiện bắt buộc xuất hiện:** Nêu rõ giới hạn về tiền tệ.
- **Điều cấm khẳng định (Red Lines):** LLM TUYỆT ĐỐI KHÔNG được lấy số VND so sánh trực tiếp với IDR (vì dataset không có tỷ giá FX). Phải trả lời: *"Hệ thống không thể so sánh giá trị tuyệt đối giữa thị trường VN và ID do thiếu dữ liệu quy đổi tiền tệ (FX normalization). Việc tìm kiếm sản phẩm tương đương xuyên biên giới bị giới hạn."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: contract cross-tier derived value T-8c chưa được phê duyệt.)**

>
>
>
> **Phân tích Trace - Kiến trúc ghi điểm, UX mất điểm:**
>
> 1. **Cú Block ngoạn mục của Gatekeeper (A16-CROSS-CURRENCY):** Hệ thống nhận diện được có 2 quốc gia trong query (`countries: ["vn", "id"]`) và yêu cầu đo lường giá (`measure.price`). Ngay lập tức, rule `A16` được kích hoạt và đánh cờ `clarify`. Quá trình Planning bị ép về `mode: "none"`, ngăn chặn hoàn toàn việc Data Science layer thực thi các phép tính vô nghĩa giữa 2 đồng tiền.
> 2. **Lỗi "lộ bài" của UX:** Tin nhắn trả về cho người dùng lại bê nguyên xi mã lỗi nội bộ của backend: *"contract cross-tier derived value T-8c chưa được phê duyệt"*. Điều này tạo cảm giác hệ thống đang văng lỗi kỹ thuật (crash) vào mặt user thay vì nhẹ nhàng giải thích.
> 3. **Parser vẫn "ngậm hành" với cụm từ thừa:** Mặc dù không gom nguyên câu như các testcase trước, nhưng Parser vẫn lấy thừa chữ "bán" (`entity_text = "sua milo ban"`). Rất may là luồng đã bị chặn trước khi cái entity lỗi này kịp bay vào hàm tìm kiếm.
> 4. **Groq API vẫn kiên định với lỗi 400:** Thêm một vết sẹo nữa trên Telemetry với 7/12 API calls thất bại hoàn toàn.
>
> **Đề xuất Fix (Cho Team Product & Dev):**
>
> 1. **Map lại Text Fallback (High Priority):** Dev cần vào file cấu hình ngôn ngữ, đè ngay một chuỗi text thân thiện hơn cho mã `A16-CROSS-CURRENCY`: *"Hệ thống không thể so sánh giá trị tuyệt đối giữa thị trường VN và ID do thiếu dữ liệu quy đổi tiền tệ (FX normalization). Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương."* (Phần answerable_alternative thực ra đã suggest rất đúng ý này, chỉ cần format lại cho đẹp).
> 2. **Tuyên dương Team Architecture:** Đề xuất ghi nhận điểm cộng lớn cho team thiết kế luồng Guardrail vì đã setup thành công chốt chặn ngay từ tầng Gateway, tối ưu hiệu suất tuyệt đối.
> 3. **Task tồn đọng muôn thuở:** Fix lỗi payload v1.1.0 của Groq LLM và tinh chỉnh lại Regex của Deterministic Parser.

## **Testcase 14: Bẫy Hình ảnh & Bao bì (Visual Feature Trap)**

- **Câu hỏi:** "Tìm các sản phẩm kẹo có bao bì màu đỏ hoặc thiết kế giống với gói kẹo Alpenliebe hương dâu này."
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `product_name` chứa "Alpenliebe hương dâu".
- **Phép tính DS phải gọi:** `find_similar_candidates()` dựa trên text/category.
- **Dữ kiện bắt buộc xuất hiện:** Danh sách kẹo tương tự dựa trên text/giá. Kèm lời từ chối phân tích hình ảnh.
- **Điều cấm khẳng định (Red Lines):** Cấm LLM tự bịa ra màu sắc bao bì. Phải trả lời rõ: *"Hệ thống MVP hiện tại chưa tích hợp phân tích hình ảnh (image embeddings), việc tìm kiếm chỉ dựa trên các thuộc tính văn bản (tên, giá, danh mục, thương hiệu)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace - "Bức tường" Parser cản trở QA:**
>
> 1. **NER Bug lặp lại lần thứ N (Critical):** Thay vì chỉ nhặt ra đúng cụm Noun Phrase `"kẹo Alpenliebe hương dâu"`, Parser dự phòng lại "nuốt" trọn luôn cả các thuộc tính hình dung từ mà user đưa vào. Biến `entity_text` bị nhồi thành một câu văn rác: *"keo co bao bi mau do hoac thiet ke giong voi goi keo alpenliebe huong dau nay"*.
> 2. **Tool `resolve_entity` "bó tay":** Hiển nhiên, không có một mã sản phẩm (Item ID) nào trong database có cái tên dài và kỳ quặc như vậy. Hàm tìm kiếm trả về rỗng, kích hoạt ngay rule `A-AMBIGUOUS` (Yêu cầu làm rõ) và vứt bỏ toàn bộ luồng xử lý bên dưới.
> 3. **Untestable Guardrail (Không thể kiểm thử):** Red Line quan trọng nhất của Testcase này là ép hệ thống phải thú nhận *hiện tại chưa tích hợp phân tích hình ảnh*. Tuy nhiên, vì luồng bị ngắt từ quá sớm, chúng ta hoàn toàn không biết luồng Planning có filter được cái bẫy "màu đỏ" này hay không.
> 4. **Groq API v1.1.0 (Nguyên nhân gốc rễ):** Nhìn vào Telemetry: 7 lỗi 400 Bad Request trên tổng số 13 API calls. Chừng nào LLM chính (gpt-oss-20b) chưa được fix lỗi payload để quay lại làm việc, chừng đó chúng ta vẫn sẽ kẹt cứng ở lớp Parser này.
>
> **Đề xuất Hành động (Cho Team AI / Model):**
>
> 1. **Tung bản Hotfix Khẩn cấp cho Parser (Priority: Blocker):** Team AI không thể chần chừ thêm. Cần ngay một bản patch cho hệ thống Regex/Rule-based của Deterministic Parser để nó biết cắt bỏ các mệnh đề phụ (bắt đầu bằng "có", "màu", "hoặc", "giống với") ra khỏi tên thực thể.
> 2. **Xử lý API 400 (Priority: Blocker):** Yêu cầu Backend Engineer check ngay log request gửi sang Groq xem field nào trong JSON format bản `v1.1.0` đang vi phạm schema của nhà cung cấp.

## **Testcase 15: Bẫy Nhầm lẫn Danh mục (Shop Category vs. Platform Category Trap)**

- **Câu hỏi:** "Hãy tìm các sản phẩm tương tự nằm trong cùng kệ '18VCX+SSCBundle[1.7]' với sản phẩm Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Lúa Mì 172g của shop Kinh Do Official Store."
- **Intent mong đợi:** `similar_product` / `category_relation`
- **Entity cần trích xuất:** Sản phẩm X = Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Lúa Mì 172g (item_id = 26963395898), Shop Y = Kinh Do Official Store (shop_id = 140360136), `seller_flag` = "18VCX+SSCBundle[1.7]".
- **Phép tính DS phải gọi:** Chặn LLM dùng `seller_flag` (kệ nội bộ do shop tự đặt) để đối chiếu diện rộng; bắt buộc chuyển sang dùng `catid`/`global_catids` (100629, 100646, 100787) — danh mục ngành hàng chuẩn của Shopee — để tìm sản phẩm tương đương trên toàn sàn.
- **Dữ kiện bắt buộc xuất hiện:** Giải thích ranh giới danh mục: `seller_flag` chỉ có ý nghĩa nội bộ trong phạm vi một shop (thường gắn với chiến dịch khuyến mãi/bundle riêng), khác với `catid`/`global_catids` là hệ thống phân loại ngành hàng áp dụng chung cho toàn nền tảng.
- **Điều cấm khẳng định (Red Lines):** Không được dùng `seller_flag` (vốn là kệ nội bộ của shop) để đi tìm đối thủ trên toàn sàn. Phải nói: *"Kệ '18VCX+SSCBundle[1.7]' là nhãn chiến dịch/kệ nội bộ do shop Kinh Do Official Store tự tạo, không phải danh mục ngành hàng chuẩn của Shopee. Hệ thống sẽ dùng danh mục chuẩn (catid/global_catids: 100629, 100646, 100787) của sản phẩm X để tìm kiếm các đối thủ tương đương trên toàn sàn."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace - Hồi chuông báo tử cho Deterministic Parser:**
>
> 1. **Over-extraction chạm đáy nỗi đau:** Biến `entity_text` của chúng ta giờ đây chứa một đoạn văn dài tới 26 từ: *"tuong tu nam trong cung ke 18vcx sscbundle 1.7 voi san pham combo 2 hop banh quy dinh duong afc vi lua mi 172g cua shop kinh do official store"*. Parser này đã chứng minh nó hoàn toàn **không có khả năng** phân tách chủ ngữ - vị ngữ hay các giới từ ("của shop", "với sản phẩm").
> 2. **Tool `resolve_entity` đình công hợp lý:** Đưa một đoạn văn lẩm cẩm như trên vào search engine thì hiển nhiên không có bất kỳ Elasticsearch hay Database nào trả về kết quả được. Lỗi `A-AMBIGUOUS` văng ra là điều tất yếu.
> 3. **Tình trạng API (Blocker):** Tỷ lệ xịt của Groq API (gpt-oss-20b) vẫn giữ nguyên 7/14 calls với lỗi 400 Bad Request.
>
> **Đánh giá rủi ro QA (QA Risk Assessment):**
>
> - **Mức độ nghiêm trọng:** **CRITICAL BLOCKER**.
> - **Tác động:** Toàn bộ nhóm Intent `similar_product` đang **không thể test được logic của Data Science layer** (lọc giá, tìm kiếm đa tầng, cross-category, chặn hình ảnh). Chúng ta đang lãng phí thời gian test chỉ để nhận lại cùng một lỗi Parser y hệt nhau từ TC11 đến TC15.
>
> **Đề xuất Hành động Gấp (Action Items):**
>
> 1. **Dừng test luồng NLP phức tạp cho `similar_product`:** Cho đến khi bản vá Parser v1.1.0 được deploy, đề nghị ngừng chạy các testcase có cấu trúc câu dài/ra lệnh.
> 2. **Đóng gói Report 15 Testcases:** Đạt hãy xuất log của toàn bộ 15 testcases này (đặc biệt nhấn mạnh chuỗi fail TC11-TC15 và lỗi 400 của TC1-TC10) thành một Jira Ticket hạng `Highest/Blocker`, tag thẳng Tech Lead và Data Science Lead vào giải quyết.

## **Testcase 16: Bẫy Thực thể quá rộng (Ambiguity Trap)**

- **Câu hỏi:** "Tìm cho tôi đối thủ cạnh tranh của bánh quy."
- **Intent mong đợi:** `similar_product` (vướng bước Entity Resolution).
- **Entity cần trích xuất:** "bánh quy" (quá mơ hồ).
- **Phép tính DS phải gọi:** Báo lỗi `ambiguous_entity`.
- **Dữ kiện bắt buộc xuất hiện:** Gợi ý danh sách Candidate hoặc yêu cầu làm rõ.
- **Điều cấm khẳng định (Red Lines):** Agent CẤM tự ý lọc đại 5 loại bánh quy bất kỳ để trả lời. Bắt buộc phải nói: *"Từ khóa 'bánh quy' quá rộng. Vui lòng cung cấp Item ID, Link sản phẩm hoặc tên sản phẩm cụ thể để hệ thống có thể đối chiếu chính xác."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.)**

>
>
>
> **Phân tích Trace - Ánh sáng cuối đường hầm:**
>
> 1. **NER (Nhận diện thực thể) ĐÃ HOẠT ĐỘNG CHUẨN XÁC:**
>     - Tuyệt vời! Thay vì nuốt cả cụm *"Tìm cho tôi đối thủ..."* như các testcase trước, trường `entity_text` lần này đã lấy chuẩn xác duy nhất cụm từ `"bánh quy"`.
>     - **Đặc biệt lưu ý:** Trong mảng `parse_adjustments`, các cờ tồi tệ như `entity_from_deterministic_parser` đã biến mất! Điều này chứng tỏ Parser chính (LLM) đã xử lý thành công hoặc rule-based mới update đã hoạt động cực kỳ mượt mà.
> 2. **Intent Routing chuẩn không cần chỉnh:** Từ khóa "đối thủ cạnh tranh" đã được map thẳng vào `similar_product` đúng như thiết kế, không còn bị đẩy lạc sang `analytical_query` hay bắt lỗi sai quốc gia `A-CROSS-CURRENCY-SCOPE` nữa.
> 3. **Gatekeeper A-AMBIGUOUS làm tròn vai:** Tool `resolve_entity("bánh quy")` lập tức nhận ra đây là một category (ngành hàng) quá rộng, không thể bind vào 1 Item ID cụ thể, nên đã nhả cờ block luồng. Red Line (chống Hallucination) được bảo vệ tuyệt đối.
>
> **Đề xuất Fix (Chỉ còn vấn đề về UX):**
>
> 1. **UX / Front-end (High Priority - Low Effort):** Như đã nhắc ở TC7 và TC8, team Dev cần map lại đoạn text lỗi của `A-AMBIGUOUS`. Câu thông báo hiện tại *"Có nhiều listing gần giống..."* dùng chung cho mọi trường hợp đang làm giảm trải nghiệm. Cần dùng đúng câu text QA đã design: *"Từ khóa 'bánh quy' quá rộng. Vui lòng cung cấp Item ID, Link sản phẩm hoặc tên sản phẩm cụ thể để hệ thống có thể đối chiếu chính xác."*
> 2. **Duy trì cấu hình Parser:** Team Model cần kiểm tra xem họ đã làm gì với prompt/regex ở lần chạy thứ 2 này mà nó bóc text mượt thế. Bê nguyên logic đó áp dụng ngược lại cho các TC11-15 là luồng `similar_product` sẽ chạy phà phà ngay!

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

⇒ **FAILED (CLARIFY - Cần làm rõ: Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity.)**

>
>
>
> **Phân tích Trace - Khi Macro không theo kịp tư duy Data Analytics:**
>
> 1. **NER hoạt động hoàn hảo:** Nhờ lớp Regex được bổ sung, hệ thống đã tóm gọn được 2 mã Item ID thay vì nhai lại nguyên câu prompt như trước.
> 2. **Giới hạn kiến trúc của Macro:** Pha xử lý này phơi bày một điểm yếu về mặt thiết kế cấu trúc truy vấn. Giống như khi xây dựng các module audit rủi ro giao dịch bằng SQL, nếu stored procedure chỉ cho phép truyền vào một tham số `item_id` duy nhất làm mỏ neo (`SELECT * FROM table WHERE item_id = ?`), thì việc đẩy cả một mảng ID vào đòi thực thi lệnh JOIN để đối chiếu chéo (A/B comparison) chắc chắn sẽ làm vỡ schema.
> 3. **Guardrail A22 hoàn thành nhiệm vụ:** Hệ thống nhận thấy User ném vào quá nhiều Entity (`item_id` A, `item_id` B, `category_id`), trong khi Macro `similar_product` chỉ được cấp phép nhận **một** Entity duy nhất. Cờ `entity_unbound` lập tức tung ra để block Planner, ném ra câu trả lời: *"Cần làm rõ: Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity."*
>
> **Đánh giá rủi ro & Đề xuất (Cho Team AI & DS):**
>
> - **Về mặt An toàn (Security):** Agent đạt điểm tuyệt đối. Thay vì cố gắng phán bừa "đây là cùng một sản phẩm" (Hallucination) do không hiểu rõ cách ghép 2 ID, nó chọn cách dừng hoạt động.
> - **Về mặt Tính năng (Feature Gap):** Bẫy này phơi bày việc hệ thống đang thiếu hụt một Macro quan trọng: `compare_products` (So sánh trực tiếp 2 hoặc nhiều sản phẩm cụ thể). Macro `similar_product` hiện tại chỉ hợp để làm bài toán *"Cho 1 ID, đi tìm N ID giống nó"*, chứ không giải quyết được bài toán *"Cho 2 ID, kiểm tra xem chúng giống nhau bao nhiêu %"*.
> - **Action Item:** Cần mở một Feature Ticket yêu cầu team Data Science bổ sung Capability so sánh chéo (Cross-comparison) cho phép bind `List[Entity]` vào Planner.

## **Testcase 18: Bẫy Tìm kiếm SKU / Biến thể (SKU-level Trap)**

- **Câu hỏi:** "Tìm cho tôi các sản phẩm tương tự có bán kích cỡ 'Hộp 279g' giống y hệt như biến thể của sản phẩm Bánh quy Richy KenJu giòn kem dẻo hương vị Nhật (mã 21658340202)."
- **Intent mong đợi:** `similar_product`
- **Entity cần trích xuất:** `item_id` = 21658340202 (Bánh quy Richy KenJu), biến thể mong muốn: `"Hộp 279g"` (tương ứng `"Hộp 279gr (18 bánh)"` trong `tier_variation_options`)
- **Phép tính DS phải gọi:** `find_similar_candidates()` ở cấp **Product Listing**, không phải cấp SKU. Agent cần tìm các sản phẩm (listing) khác trong cùng danh mục (`catid`/`global_catids`) có tên hoặc mô tả chứa "279g" hoặc cùng cấp khối lượng tương tự, nhưng KHÔNG được phép truy xuất dữ liệu doanh số/giá theo từng biến thể.
- **Dữ kiện bắt buộc xuất hiện:** Agent phải trả về **danh sách các sản phẩm tương đương ở cấp listing** (ví dụ: các sản phẩm Kenju khác, hoặc bánh quy Richy có khối lượng 279g), và phải nêu rõ rằng các sản phẩm này được so sánh dựa trên thông tin listing chứ không phải SKU cụ thể.
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định đã so sánh theo cấp độ SKU. Phải giải thích: *"Dữ liệu hiện tại chỉ theo dõi ở cấp độ Product Listing, các biến thể (tier_variation) chỉ mang tính chất hiển thị UI, không có mã SKU thật và doanh số riêng biệt để so sánh đối chiếu chính xác."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dataset không có sku_id/model_id; đơn vị nhỏ nhất là product listing. tier_variation chỉ mô tả lựa chọn hiển thị, không phân bổ doanh số theo biến thể. Vẫn trả lời được chỉ số ở cấp listing. Ví dụ: 'Listing X có bao nhiêu lượt bán proxy tại snapshot mới nhất?’.)**

>
>
>
> **Phân tích Trace - Điểm sáng và Điểm tối:**
>
> 1. **Architecture Win (Tuyệt vời):**
>     - Tính năng `unsupported_safety_precedence` hoạt động nhạy như một chiếc radar! Ngay khi nhận thấy Entity có chứa context về kích cỡ biến thể ("Hộp 279g"), LLM đã tỉnh táo bẻ lái Intent sang `unsupported:sku`.
>     - Việc kích hoạt thành công rule `A-MISSING-SKU` ngay từ cổng Gatekeeper giúp tiết kiệm 100% tài nguyên API (Zero API waste). Hệ thống không hề cố gắng chọc vào DB để tìm một trường dữ liệu không tồn tại. Red Line được bảo vệ tuyệt đối.
> 2. **UX Failure (Cần khắc phục gấp):**
>     - Bạn hoàn toàn chính xác. Việc Agent "nôn" ra nguyên một rổ thuật ngữ nội bộ như *"sku_id/model_id"*, *"proxy lượt bán"*, *"snapshot"* ra mặt tiền (front-end) là một lỗi UX kinh điển. Thay vì giúp user hiểu vấn đề, nó lại tạo ra rào cản kỹ thuật rất lớn, dễ làm giảm trải nghiệm và sự tương tác của người dùng với sản phẩm.
>
> **Đề xuất Hành động (Action Items):**
>
> 1. **Duyệt ngay ticket cho team Copy/UX:** Lời đề xuất rewrite của Đạt là cực kỳ chuẩn xác và mang tính "người" hơn rất nhiều. Yêu cầu update ngay rule text của mã `A-MISSING-SKU` thành:
>
>     > *"Dữ liệu MVP hiện tại chỉ theo dõi ở cấp độ Sản phẩm chung (Product Listing), các phân loại biến thể/kích cỡ (tier_variation) không có dữ liệu doanh số/giá độc lập để so sánh đối chiếu."*
>     >
> 2. **Rà soát chéo các Guardrail khác:** Cần tạo một task nhỏ để quét lại toàn bộ các câu thông báo của Gatekeeper (như `A-CROSS-CURRENCY`, `A-AMBIGUOUS`...). Chắc chắn còn vài chỗ Dev đang để nguyên Log Text của Backend hiển thị lên UI. Phải "clean" toàn bộ mớ thuật ngữ này trước khi release.

## **Testcase 19: Bẫy Outlier Giá "Khủng" (Sentinel Price Trap)**

- **Câu hỏi:** *"*Tìm các đối thủ cạnh tranh ở Việt Nam có cùng mức giá ± 20% với sản phẩm mã 56061511146 – Quà tặng không bán (Quạt mini cầm tay).*" (Giá trị sentinel: 410.000đ)*
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

⇒ **PASSED** **(ALLOW - VERIFIED - Các listing tương tự gần nhất theo lexical/embedding:**

**- [Tặng Set Túi Giặt Bảo Vệ] Collagen Thủy Phân Dạng Bột NESTLÉ VITAL PROTEINS Mỹ Hỗ Trợ Làm Đẹp Da,Móng,Tóc 284G (điểm 0.855) [ev:6576f848a5fa:0001]**

**- Mooi Whitening Night Cream - Atasi Kulit Kusam, Melmbabkan Kulit Garis Halus Dan Tanda Penuaan 10gr (Original 100%) (điểm 0.855) [ev:6576f848a5fa:0002]**

**- [My Daily Glow Up Set] Scora Bright Me Up Sunscreen 40 Gr + SCORA Moisturizer Gel + SCORA Gentle Low pH Cleanser 100 ML + SCORA Toner 80 ML (điểm 0.855) [ev:6576f848a5fa:0003]**

**- [Quà tặng không bán] Bộ mền gối chim cánh cụt (điểm 0.855) [ev:6576f848a5fa:0004]**

**- [Quà tặng không bán] Bộ Mền Gối Con Cua (điểm 0.855) [ev:6576f848a5fa:0005].)**

>
>
>
> **Phân tích Trace - Khi Search Engine bị "Dắt mũi":**
>
> 1. **Thảm họa Search Engine (DS Layer):**
>     - Bạn đang đi tìm đối thủ cho một cái **Quạt mini cầm tay**. Nhưng hệ thống trả về cái gì? Bột Collagen, Kem dưỡng da ban đêm, Set chống nắng, Mền gối chim cánh cụt và Mền gối con cua!
>     - **Nguyên nhân:** Hàm `find_similar` hoàn toàn không có cơ chế *hard-filter* theo danh mục (catid). Nó đang bị overfit (thiên vị) cực nặng bởi cụm từ khóa `[Quà tặng không bán]`. Thuật toán Lexical/Embedding đã bám lấy cụm từ này và gom tất cả những sản phẩm có chứa chữ "Quà tặng" trên sàn lại, đánh đồng điểm `similarity_score` là `0.855` tăm tắp, bất chấp việc chúng thuộc các ngành hàng hoàn toàn khác nhau (Mỹ phẩm, Gia dụng, Đồ chơi).
> 2. **Red Line bị chọc thủng (Generation Layer):**
>     - Mặc dù hàm `find_similar` đã chủ động bỏ qua tham số giá (không truyền filter price vào query), nhưng LLM lại **hoàn toàn câm nín** về điều này.
>     - Thay vì đứng ra giải thích lý do gạt bỏ mức giá 410.000đ (như Red Line yêu cầu), Agent C1 này lại hành xử như một cái máy in: nhả ra đúng đoạn text template mặc định *"Các listing tương tự gần nhất theo lexical/embedding..."*. Nó không nhận thức được (hoặc không được cấp dữ kiện) để hiểu rằng đây là một Outlier/Sentinel cần phải report cho user.
>
> **Đề xuất Hành động (Cho team Data Science & AI):**
>
> 1. **Cập nhật Search Engine (DS - Priority High):** Bắt buộc hàm `find_similar` phải nhận thêm tham số ngầm định `require_same_global_catids=True`. Không thể đi tìm sản phẩm tương tự mà nhảy từ đồ điện tử sang mỹ phẩm chỉ vì trùng keyword "quà tặng".
> 2. **Bổ sung Sentinel Flag (Backend & LLM):** Module Outlier Detection của DS khi thấy giá trị dị thường phải trả về một cờ (ví dụ: `is_sentinel: true`, `reason: "gift_not_for_sale"`) kèm theo payload. LLM Planning Macro phải được dặn dò: *Nếu thấy cờ này, bắt buộc chèn câu cảnh báo giá rác vào đầu câu trả lời.*

## **Testcase 20: Bẫy Mã sản phẩm không tồn tại (Null Target Trap)**

- **Câu hỏi:** "Tìm sản phẩm tương đương cho mã ID 111222333444." (Một mã hoàn toàn không có trong 1157 listing của file dataset).
- **Intent mong đợi:** `similar_product` / `product_lookup`
- **Entity cần trích xuất:** `item_id` = 111222333444.
- **Phép tính DS phải gọi:** Không tìm thấy entity → Trả `status: insufficient_evidence`.
- **Dữ kiện bắt buộc xuất hiện:** Báo lỗi không tìm thấy.
- **Điều cấm khẳng định (Red Lines):** LLM cấm bịa ra (hallucinate) thông tin cho ID ảo này. Trả lời đơn giản: *"Không tìm thấy dữ liệu cho mã sản phẩm 111222333444 trong tập dữ liệu 3 ngày (01/07 - 03/07/2026) của hệ thống."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Không tìm thấy listing khớp entity/ID trong artifact hiện tại.)**

>
>
>
> **Phân tích Trace - Những điểm sáng giá:**
>
> 1. **Xóa sổ hoàn toàn Keyword Collision (Lỗi xung đột từ khóa):**
>     - Hệ thống đã nhận diện chính xác `country: null`. Việc chữ "ID" trong "mã ID" bị nhầm thành mã quốc gia Indonesia (`id`) ở lần chạy trước đã được vá triệt để bằng Regex map chuẩn xác.
> 2. **NER & Error Handling hoạt động hoàn hảo:**
>     - Mã số `111222333444` được Parser bóc tách cô lập với độ tự tin tuyệt đối (`confidence: "exact"`).
>     - Tool call `resolve_entity` lập tức trả về `status: "empty"` thay vì cố gắng vơ vét các dữ liệu rác, chứng tỏ bộ lọc ID hoạt động rất gắt gao.
> 3. **Gatekeeper A-ENTITY-NOT-FOUND chặn luồng xuất sắc:**
>     - Luồng Fallback đã được sửa đúng logic. Thay vì báo lỗi ngớ ngẩn "Có nhiều listing gần giống" (`A-AMBIGUOUS`), Gatekeeper nhận diện được `empty state` và kích hoạt ngay cờ `A-ENTITY-NOT-FOUND` để "đóng băng" Agent (Abstain). Red Line không bịa đặt dữ liệu (Zero Hallucination) được bảo vệ tuyệt đối.
>
> **Đề xuất Hành động (Action Items - Low Effort / High Impact):**
>
> - **Tinh chỉnh UX (Front-end Template):** Lời báo lỗi hiện tại *"Không tìm thấy listing khớp entity/ID trong artifact hiện tại"* mang quá nhiều thuật ngữ kỹ thuật (jargon) của giới Developer. Cần yêu cầu team Copy/UX map lại rule này sang câu thoại thiết kế ban đầu: *"Không tìm thấy dữ liệu cho mã sản phẩm 111222333444 trong tập dữ liệu của hệ thống."*

# Nhóm `promotion_effectiveness`

## **Testcase 21: Luồng chuẩn nội bộ (Standard Flow - VN)**

- **Câu hỏi:** "Tại thị trường Việt Nam, nhóm sản phẩm có áp dụng cả voucher và giảm giá trực tiếp (promo) có mang lại doanh thu ước tính tốt hơn nhóm không có khuyến mãi nào không?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `country_code` = "vn".
- **Phép tính DS phải gọi:** Hàm tính `median_revenue` và `median_monthly_sold` cho 2 nhóm `voucher + promo` và `no voucher/promo`.
- **Dữ kiện bắt buộc xuất hiện:** Báo cáo so sánh điểm Trung vị (Median) giữa 2 nhóm tại thị trường VN.
- **Điều cấm khẳng định (Red Lines):** Cấm khẳng định "Voucher làm tăng doanh thu". Phải dùng câu: *"Nhóm có khuyến mãi ghi nhận mức doanh thu trung vị cao hơn, tuy nhiên đây là so sánh mô tả (descriptive comparison), không loại trừ yếu tố thiên lệch (selection bias) do các sản phẩm chiến lược thường được ưu tiên gắn voucher."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Điều kiện ngoài phạm vi macro được chứng nhận: no_promo_segment, revenue_measure.)**

>
>
>
> **Phân tích Trace - Khi Macro "từ chối" yêu cầu thiết kế:**
>
> 1. **Từ Lỗi "Mù Toán" (Mean vs Median) sang Lỗi "Chối Bỏ" (Capability Gap):**
>     - Ở log kết quả lúc đầu Đạt cung cấp, hệ thống đã chạy qua mượt mà nhưng lại dính lỗi thiên lệch dữ liệu: Bỏ qua Trung vị (Median) và lấy số Trung bình (Mean) để "chứng minh" giả thuyết. Đề xuất ẩn metric Mean của bạn là cực kỳ sắc sảo để ép LLM dùng Median.
>     - Tuy nhiên, ở Trace *lúc sau*, mọi thứ đã thay đổi. Gatekeeper `A22-ALIGN-QUALIFIER` đã kích hoạt và ném ra thông báo: *"Điều kiện ngoài phạm vi macro được chứng nhận: no_promo_segment, revenue_measure"*.
> 2. **Mổ xẻ nguyên nhân block (Planning Section):**
>     - Nhìn vào block `"issues"`, ta thấy Macro được "certified" (cấp phép) hiện tại của Agent **không hỗ trợ** 2 qualifier: `no_promo_segment` (nhóm không có bất kỳ khuyến mãi nào) và `revenue_measure` (doanh thu ước tính).
>     - Đáng chú ý, câu `answerable_alternative` mà Agent gợi ý là: *"Hệ thống có thể so sánh nhóm có structured voucher với nhóm không trong cùng thị trường..."*.
>     - **Kết luận:** Macro `promotion_effectiveness` hiện tại chỉ được code để so sánh **Lượt bán (Sold)** dựa trên **Voucher**, chứ chưa support tính toán **Doanh thu (Revenue)** và các loại **Promo (Giảm giá trực tiếp)** phức tạp.
>
> **Đề xuất Hành động (Cho Team DS & Backend):**
>
> - **Mở rộng Capability cho Macro (Feature Request):** Gửi ngay yêu cầu cho team Data Science:
>     1. Mở khóa (whitelist) dimension `promo` và measure `revenue` (doanh thu ước tính) cho macro `promotion_effectiveness`. Business User chắc chắn sẽ hỏi về doanh thu chứ không chỉ hỏi về lượt bán.
>     2. Áp dụng ngay giải pháp "ép Median" mà Đạt đã đề xuất: Mặc định trả về Trung vị cho các bài toán so sánh nhóm để chống Outlier.
> - **UX (Tạm thời):** Trong lúc chờ Dev nâng cấp Macro, cần làm rõ câu từ chối. Lời nhắn *"Điều kiện ngoài phạm vi macro được chứng nhận: no_promo_segment, revenue_measure"* là thuật ngữ code thuần túy. Cần đổi thành: *"Hệ thống hiện tại chỉ hỗ trợ so sánh **Lượt bán** giữa nhóm có Voucher và không có Voucher. Chưa hỗ trợ ước tính **Doanh thu**."*

## **Testcase 22: Bẫy cấu trúc dữ liệu - Nhóm "Voucher Only" (Structural Trap)**

- **Câu hỏi:** "Hãy phân tích hiệu quả của nhóm sản phẩm chỉ áp dụng mã giảm giá (voucher) nhưng không có chương trình giảm giá trực tiếp (promo) trên toàn sàn ở Việt Nam."
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** Toàn dataset, nhóm `voucher only` (`has_promo` = False, `has_voucher` = True).
- **Phép tính DS phải gọi:** Nhận diện nhóm trống (0 dòng).
- **Dữ kiện bắt buộc xuất hiện:** Giải thích toán học về cờ khuyến mãi.
- **Điều cấm khẳng định (Red Lines):** Agent CẤM tính toán hay bịa ra số liệu. Phải trả lời rành mạch: *"Nhóm 'Voucher Only' không tồn tại (0 dòng) trong bộ dữ liệu. Về mặt toán học, bất cứ khi nào sản phẩm có voucher, giá cuối đã phản ánh voucher đó khiến discount_percent tự động lớn hơn 0 (has_promo = True)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Điều kiện ngoài phạm vi macro được chứng nhận: no_promo_segment.)**

>
>
>
> **Phân tích Trace - Khi Agent phòng thủ bằng "Khiên gỉ":**
>
> 1. **Safety Win (Thành công chặn ảo giác):** Rất may mắn, cờ `A22-ALIGN-QUALIFIER` đã bắt dính qualifier `no_promo_segment` trong câu hỏi và chặn Planner lại. Hệ thống không còn nhắm mắt "vơ vét" data của tập `with_voucher` như lần chạy đầu tiên để trả lời bừa nữa.
> 2. **Intelligence Gap (Thiếu hụt sự thông minh):**
>     - Tuy chặn thành công, nhưng lý do Agent đưa ra lại là *"Điều kiện ngoài phạm vi macro được chứng nhận"* (tức là: code của tôi không hỗ trợ cái này).
>     - Nó hoàn toàn KHÔNG nhận ra sự **mâu thuẫn logic toán học** trong schema (bản chất việc có voucher sẽ khiến giá bị thay đổi, kéo theo `has_promo` = True). Câu giải thích xuất sắc mà bạn thiết kế ở phần Red Lines đã bị bỏ lỡ hoàn toàn.
> 3. **Lỗi Parser / NLU "Bóng ma" ám ảnh:**
>     - Lại một lần nữa, Deterministic Parser "cắn" bậy. Ở mảng `entities`, nó nhặt nguyên câu *"chi ap dung ma giam gia voucher nhung khong co chuong trinh giam gia truc tiep promo tren toan san"* làm một thực thể với mức `confidence: "low"`. Rõ ràng bộ Parser quy tắc (Rule-based) đang làm việc rất lộn xộn ở các câu truy vấn phức tạp.
>
> **Đề xuất Hành động (Action Items - Gửi Team AI & DE):**
>
> 1. **Xây dựng Schema-Aware Validator (Bộ kiểm duyệt logic schema):** Team DE và AI cần phối hợp thêm một lớp validator. Khi nhận các bộ filter động (ví dụ: `has_voucher=True` AND `has_promo=False`), hệ thống phải đối chiếu với các định luật (constraints) của Database. Nếu phát hiện mâu thuẫn, trả về cờ lỗi riêng (ví dụ: `A-LOGIC-CONTRADICTION`) kèm theo câu thoại giải thích rành mạch về toán học thay vì đổ lỗi cho Macro chưa support.
> 2. **Clean-up Jargon (Team UX):** Tương tự TC21, câu thông báo lỗi hiện tại đang "phơi bày" code nội bộ ra ngoài. Cần được dọn dẹp lại.

## **Testcase 23: Bẫy so sánh chéo Voucher VN vs ID (Cross-Country Trap)**

- **Câu hỏi:** "Mã giảm giá (voucher) mang lại hiệu quả chuyển đổi tốt hơn ở thị trường Việt Nam hay thị trường Indonesia?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `has_voucher` = True, `country_code` = "vn" vs "id".
- **Phép tính DS phải gọi:** Chặn so sánh chéo do tập ID rỗng.
- **Dữ kiện bắt buộc xuất hiện:** Phát hiện thiếu dữ liệu ở thị trường ID.
- **Điều cấm khẳng định (Red Lines):** Không được so sánh. Agent bắt buộc phải nói: *"Không thể so sánh hiệu quả voucher giữa hai thị trường. Toàn bộ 1.422 dòng dữ liệu của thị trường Indonesia (ID) không ghi nhận dữ liệu structured voucher nào. Việc phân tích voucher chỉ khả thi trong nội bộ thị trường VN."*

⇒ **PASSED (ALLOW - VERIFIED - So sánh quan sát tại một snapshot: without_voucher_listing_count=77 listings [ev:25922f65bf51:0001]; without_voucher_mean_monthly_sold_proxy=745.078 items [ev:25922f65bf51:0002]; without_voucher_median_monthly_sold_proxy=284 items [ev:25922f65bf51:0003]; with_voucher_listing_count=551 listings [ev:25922f65bf51:0004]; with_voucher_mean_monthly_sold_proxy=2059.66 items [ev:25922f65bf51:0005]; with_voucher_median_monthly_sold_proxy=204 items [ev:25922f65bf51:0006]. Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi.)**

>
>
>
> **Phân tích Trace - Khi Agent "chỉ thấy những gì nó muốn thấy":**
>
> 1. **Lỗi "Nuốt" Tham Số (Silent Parameter Drop):**
>     - Hệ thống NLU nhận diện cực chuẩn yêu cầu của User với mảng `countries: ["vn", "id"]`.
>     - **Tuy nhiên**, hãy nhìn vào Tool Call: `compare_voucher_groups(args: {"country": "vn"})`. Macro này được thiết kế quá cứng nhắc, chỉ nhận 1 tham số quốc gia duy nhất. Thay vì báo lỗi không thể so sánh 2 quốc gia cùng lúc, Planner tự động "chặt đứt" ID và chỉ query VN. Hệ quả là Red Line bị phá vỡ hoàn toàn vì Agent không thèm đoái hoài gì đến Indonesia.
> 2. **Sụp đổ tầng Generation (Verification Breakdown):**
>     - Đạt hãy chú ý mảng `generation.errors`. LLM (gpt-oss-20b) đã cố gắng tạo câu trả lời 2 lần nhưng liên tục bị dội ngược bởi lớp Verification do lỗi `missing_claim` (không map được data với format citation yêu cầu).
>     - Hậu quả: Hệ thống buộc phải kích hoạt `fallback: true`, nhả ra một cục text thô nguyên bản từ Database không qua xào nấu: *"without_voucher_listing_count=77 listings; without_voucher_mean_monthly_sold_proxy=..."*. Trải nghiệm người dùng (UX) ở case này chính thức chạm đáy.
> 3. **Nội dung Red Line bị phớt lờ:** Vì không hề gọi data của ID, Agent cũng mất luôn bối cảnh để đưa ra câu trả lời giải thích về việc "1.422 dòng dữ liệu ID không có structured voucher".
>
> **Đề xuất Hành động (Action Items - Mức độ: Blocker):**
>
> 1. **Thiết kế lại Macro (Team Data Science / DE):** Macro `compare_voucher_groups` bắt buộc phải hỗ trợ so sánh chéo (nhận input là List thay vì String), HOẶC Gatekeeper phải có rule chặn ngay từ đầu nếu phát hiện `len(countries) > 1` đối với Intent này (ví dụ: cờ `A-SINGLE-COUNTRY-ONLY`).
> 2. **Fix lỗi Prompt Citation (Team AI Model):** Việc LLM xịt liên tục 2 lần ở khâu gắn Evidence (`claim_binding_gaps`) cho thấy format output đang quá phức tạp với con model 20B này. Cần tối ưu lại prompt hướng dẫn cách cite data cho các bài toán nhiều metric (chứa cả Count, Mean, Median).
> 3. **Tắt Fallback Text Thô:** Tuyệt đối không cho phép đẩy các raw string như `with_voucher_median_monthly_sold_proxy` ra UI của User. Nếu LLM fail generate, phải trả về một câu lỗi thân thiện: *"Hệ thống đang gặp lỗi trong việc tổng hợp số liệu, vui lòng thử lại sau."*

## **Testcase 24: Bẫy Trung bình vs Trung vị (Mean vs Median Trap)**

- **Câu hỏi:** "Tính giúp tôi trung bình doanh thu ước tính (average revenue) của các sản phẩm có chạy chương trình khuyến mãi để xem shop thu về bao nhiêu ở Việt Nam."
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** Sản phẩm có `has_promo` = True.
- **Phép tính DS phải gọi:** Bắt buộc dùng Median thay vì Mean.
- **Dữ kiện bắt buộc xuất hiện:** Cung cấp số Trung vị (Median) và giải thích.
- **Điều cấm khẳng định (Red Lines):** DS KHÔNG ĐƯỢC code dùng hàm `mean()`. LLM phải trả lời: *"Hệ thống sử dụng Trung vị (Median) thay vì Trung bình (Mean) để đánh giá hiệu quả, nhằm tránh bị nhiễu bởi các sản phẩm bán đột biến hoặc outlier. Ngoài ra đây chỉ là doanh thu ước tính (Revenue Proxy), không phải doanh thu thực tế."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Điều kiện ngoài phạm vi macro được chứng nhận: mean_requested, revenue_measure.)**

>
>
>
> **Phân tích Trace - Khi AI cự tuyệt yêu cầu sai thống kê:**
>
> 1. **NLU bóc tách Slot "đỉnh cao":** Điểm sáng chói lọi nhất trong Trace này nằm ở mảng `slots.qualifiers`. Hệ thống đã đọc vị chuẩn xác 2 ý đồ nguy hiểm của User và gán nhãn thành công:
>     - `mean_requested`: User đòi tính trung bình.
>     - `revenue_measure`: User đòi tính doanh thu.
> 2. **Cú Block chuẩn mực của Gatekeeper A22:** Nhờ việc bóc tách Slot chuẩn xác, cờ `A22-ALIGN-QUALIFIER` đã lập tức nhận diện đây là những hành vi vi phạm nguyên tắc toán học/dữ liệu của Macro `promotion_effectiveness`. Thay vì cố tình hùa theo tính Mean (2059.66) dẫn đến sai lệch như lần test trước, Agent chọn cách "đứng hình" (Blocked) để bảo toàn tính trung thực của dữ liệu (Data Integrity).
> 3. **Lỗi API (Blocker ngầm):** Mảng `telemetry` ghi nhận số lỗi 400 Bad Request của Groq API đã leo lên con số 11 (trên tổng 25 calls). Quá trình phân tích ngữ nghĩa (parse_attempts) phải chạy lại đến lần thứ 2 mới qua được `RuntimeError`. Đây là hồi chuông báo động đỏ cho tính ổn định của hạ tầng LLM.
>
> **Đề xuất Hành động (Action Items - Cho Team DS, UX & DevOps):**
>
> 1. **Mượt mà hóa thông báo (UX/UI):** Tính năng phòng thủ đã hoạt động, nhưng cách giao tiếp lại quá "người máy". Team Prompt/UX cần map hai mã `mean_requested` và `revenue_measure` vào đúng câu thoại đã thiết kế ban đầu:
>
>     > *"Hệ thống sử dụng Trung vị (Median) thay vì Trung bình (Mean) để đánh giá hiệu quả nhằm tránh bị nhiễu bởi các sản phẩm bán đột biến. Ngoài ra, dữ liệu hiện tại chỉ cung cấp lượt bán ước tính (Sales Proxy), không có doanh thu."*
>     >
> 2. **Khẩn cấp gỡ lỗi API (DevOps):** File JSON schema payload gửi sang API v1.1.0 của `gpt-oss-20b` chắc chắn đang có field nào đó vi phạm chuẩn, khiến server Groq liên tục văng 400. Cần audit lại payload này ngay lập tức để tránh làm sập luồng khi đưa lên môi trường Production.

## **Testcase 25: Bẫy Nhân quả & Tỷ lệ chuyển đổi (Causality & CVR Trap)**

- **Câu hỏi:** "Chương trình giảm giá 50% đã giúp các shop tăng bao nhiêu % tỷ lệ chốt đơn (conversion rate) so với lúc không giảm giá?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `discount_percent_num` $\approx$ 50%.
- **Phép tính DS phải gọi:** Phân tích mô tả (descriptive) cho bucket discount 41-60%.
- **Dữ kiện bắt buộc xuất hiện:** Bác bỏ việc tính CVR.
- **Điều cấm khẳng định (Red Lines):** Cấm tính Tỷ lệ chuyển đổi. Phải cảnh báo: *"Dữ liệu không bao gồm lưu lượng truy cập (traffic/impression), do đó không thể tính Tỷ lệ chuyển đổi (CVR). Đồng thời không thể khẳng định mức giảm 50% là nguyên nhân gốc rễ (causality) làm tăng số lượng bán."*

⇒ **PASSED (ALLOW - VERIFIED - Không có dữ liệu về tỷ lệ chuyển đổi, chỉ có 146 listing [ev:ac0f47c24d70:0001] và median monthly‑sold proxy 1000 items [ev:ac0f47c24d70:0002].)**

>
>
>
> **Phân tích Trace - Khi Agent biết "Chia để trị":**
>
> 1. **NLU Query Decomposition (Kỹ thuật phân rã truy vấn xuất sắc):**
> Đây là điểm sáng giá nhất trong toàn bộ Trace! Hệ thống đã không đánh đồng cả câu hỏi thành một cục mớ bòng bong, mà tách nó ra thành mảng `sub_requests`:
>     - `sr1`: `discount bucket observation` (Đo lường nhóm giảm giá 50% -> `answerable: true`).
>     - `sr2`: `conversion causality` (Tính tỷ lệ chốt đơn/nhân quả -> `answerable: false`).
> 2. **Cơ chế Partial Gatekeeper (A22-ALIGN-SUBREQUEST):**
> Dựa trên sự phân rã thông minh trên, Gatekeeper đã cho phép trả lời phần dữ liệu hợp lệ (nhóm 50% có 146 listings, bán được trung vị 1000 items) và chặn đứng hoàn toàn việc chém gió về "tỷ lệ chuyển đổi" hay "nguyên nhân". Red Line đã được bảo vệ hoàn hảo mà không làm cụt hứng người dùng bằng một câu từ chối lạnh lùng.
> 3. **Jargon Leak (Rò rỉ thuật ngữ):**
> Dù logic xử lý rất mượt, văn phong đầu ra (Generation) vẫn dính sạn. Việc bê nguyên cụm `"median monthly‑sold proxy"` ra giao diện người dùng tiếp tục là một lỗi UX lặp lại từ các testcase trước.
> 4. **Hạ tầng rên rỉ (Critical API Risk):**
> Nhìn vào block `telemetry`, số lỗi `BadRequestError:400` đã leo lên con số **13**. Hai lần parser văng `RuntimeError` báo hiệu con model `gpt-oss-20b` đang bị "ngộp" thực sự trước các JSON Schema phức tạp chứa mảng `sub_requests`.
>
> **Đề xuất Hành động (Action Items - Cho Team AI & DevOps):**
>
> - **DevOps / AI Model (Blocker):** Không thể chần chừ thêm nữa, tỷ lệ xịt API 400 đang tăng dần đều qua mỗi testcase. Cần review ngay lập tức payload gửi sang Groq API. Có thể model 20B này context window xử lý không nổi hoặc bị tràn token limit khi nhồi quá nhiều constraints và sub-requests vào prompt.
> - **Prompt Engineering (UX):** Bổ sung một rule ép LLM dịch các biến internal (như `monthly_sold_proxy`) thành ngôn ngữ tự nhiên (ví dụ: "ước tính số lượng bán ra") TRƯỚC KHI sinh câu trả lời cuối cùng.

## **Testcase 26: Bẫy chiến dịch Marketing (`promotion_id` Trap)**

- **Câu hỏi:** "Chiến dịch marketing có mã promotion ID '473502013010049' đã mang lại tổng doanh thu bao nhiêu cho nền tảng tại Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `promotion_id` = 473502013010049.
- **Phép tính DS phải gọi:** Lọc theo `promotion_id` để lấy danh sách các item được gán ID này trong khoảng thời gian snapshot (01–03/07/2026). Phải kèm theo **cảnh báo logic**: `promotion_id` chỉ là ID ưu đãi gắn với từng listing tại thời điểm snapshot, không phải định danh duy nhất cho một chiến dịch marketing có kế hoạch tập trung.
- **Dữ kiện bắt buộc xuất hiện:** Agent phải liệt kê được một số item có `promotion_id = 473502013010049` (ví dụ: ít nhất 3–5 item) và nêu rõ: Các item này thuộc các danh mục khác nhau (có thể khác `global_catids`); Mã `promotion_id` này xuất hiện cùng lúc với các voucher khác nhau theo từng ngày (ví dụ ngày 01/07 dùng `17GIAM30K1`, ngày 02/07 dùng `VCXDPULC0702`, ngày 03/07 dùng `VCXDPBLC0703`), cho thấy đây không phải là một chiến dịch thống nhất. Phải có cảnh báo về giới hạn của biến `promotion_id`: không thể suy ra tổng doanh thu, phạm vi, hoặc hiệu quả của một "chiến dịch marketing" từ dữ liệu này.
- **Điều cấm khẳng định (Red Lines): KHÔNG** được coi `promotion_id = 473502013010049` là một "chiến dịch marketing" hoàn chỉnh. **KHÔNG** được tính tổng doanh thu / doanh số cho ID này như thể nó đại diện cho một chiến dịch duy nhất. Phải trả lời đúng hoặc diễn đạt đúng tinh thần: *"Biến promotion_id là ID ưu đãi gắn với listing tại thời điểm snapshot, nó có thể áp dụng cho nhiều sản phẩm ở nhiều shop khác nhau, hoặc thay đổi theo ngày. Dataset không có bảng Marketing Master Data, nên không thể đánh giá đây là một chiến dịch tập trung."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: contract cross-tier derived value T-8c chưa được phê duyệt.)**

>
>
>
> **Phân tích Trace - Hành trình "Vượt ải" bất thành:**
>
> 1. **Lần chạy 1 (Thiếu quốc gia): Sửa được án oan "Indonesia"!**
>     - **Tin vui (Parser Win):** Ở Trace đầu tiên, hệ thống đã ghi nhận `country: null`. Điều này chứng tỏ team Dev đã fix thành công cái bug ngớ ngẩn (từ khóa "ID" trong "promotion ID" bị nhận nhầm thành Indonesia) mà chúng ta phát hiện ở Testcase 20.
>     - **Entity Extraction:** Lớp Deterministic Parser cũng đã làm việc xuất sắc khi giữ lại được trọn vẹn đoạn mã 15 số gốc (`473502013010049` với `confidence: "exact"`), đè bẹp được xu hướng tự ý xóa biến (`irrelevant_entity_removed`) của LLM. Hệ thống báo lỗi `A-MISSING-SLOT: country` là hoàn toàn chuẩn xác.
> 2. **Lần chạy 2 (Thêm "tại Việt Nam"): Bug "Shadow" xuất hiện!**
>     - Khi bạn ngoan ngoãn bổ sung ngữ cảnh "tại Việt Nam", hệ thống NLU đã nhận diện đúng `country="vn"`. Tưởng chừng Macro sẽ chạy để chúng ta test Red Line, thì Gatekeeper lại giáng một đòn trời giáng: cờ `A16-CROSS-CURRENCY` (Lỗi quy đổi tiền tệ VND và IDR).
>     - **Sự vô lý của Gatekeeper:** Tại sao lại báo lỗi cross-currency khi user đã filter rõ ràng là `dim.country = vn`? Nguyên nhân sâu xa là do cấu trúc của biến doanh thu (`revenue_measure`). Rất có thể Macro hoặc Gatekeeper đang được thiết lập để quét toàn bộ dataset vùng (gồm cả VN và ID). Khi thấy request đòi tính tiền (doanh thu), Gatekeeper hoảng loạn chặn đứng bằng rule `A16` trước cả khi nó kịp nhìn thấy bộ filter `country="vn"`.
>
> **Đề xuất Hành động (Action Items - Mức độ: Blocker):**
>
> 1. **Fix Rule A16-CROSS-CURRENCY (Team Backend/DE):**
> Cấu hình lại điều kiện kích hoạt của cờ này. Nó CHỈ ĐƯỢC PHÉP kích hoạt nếu `len(countries) > 1` (ví dụ User hỏi cả VN và ID cùng lúc) HOẶC không có filter quốc gia nào được truyền vào mà lại đòi tính tiền. Việc kích hoạt bừa bãi khi `country="vn"` là một lỗi logic (False Positive) nghiêm trọng khiến hệ thống bị liệt toàn bộ các câu hỏi về doanh thu tại thị trường đơn lẻ.
> 2. **Vẫn nợ Macro `promotion_effectiveness` (Team DS):**
> Như đã phân tích ở Testcase 21, Macro này hiện tại vẫn đang mù tịt với qualifier `revenue_measure`. Dù có qua được ải tiền tệ `A16`, hệ thống rất có thể sẽ lại văng lỗi `A22-ALIGN-QUALIFIER` vì không tính được doanh thu. Team DS cần sớm nâng cấp capability cho Macro này.

## **Testcase 27: Bẫy Double Discount (Giá trị Voucher Trap)**

- **Câu hỏi:** "Để tính doanh thu thực nhận của nhóm có mã giảm giá, hệ thống có lấy giá bán (price) trừ đi giá trị mã giảm giá (voucher_discount) không?"
- **Intent mong đợi:** `promotion_effectiveness` (Kiểm tra Data Dictionary).
- **Entity cần trích xuất:** Nhóm `has_voucher` = True.
- **Phép tính DS phải gọi:** Không cần tính, chỉ xuất rule.
- **Dữ kiện bắt buộc xuất hiện:** Giải thích định nghĩa giá `price`.
- **Điều cấm khẳng định (Red Lines):** Cấm Agent hoặc DS làm phép trừ này. Phải tuyên bố: *"Cột price là giá trị hiển thị cuối cùng khách hàng phải trả tại thời điểm crawl (đã phản ánh voucher). Tuyệt đối không lấy price trừ đi voucher_discount một lần nữa để tránh tình trạng trừ trùng (double discount)."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Không thể tái tạo giá cuối bằng cách trừ voucher lần nữa; price đã là giá quan sát. Voucher có điều kiện áp dụng và không phải mọi listing đều đủ điều kiện. Vẫn trả lời được price và voucher_discount như hai giá trị quan sát riêng. Ví dụ: 'Price và voucher_discount quan sát của listing X là bao nhiêu?’.)**

>
>
>
> **Phân tích Trace - Khi AI nắm vững Data Dictionary:**
>
> 1. **Quyền ưu tiên an toàn (Safety Precedence Tỏa Sáng):**
> Nhìn vào block `parse_adjustments`, chúng ta thấy cờ `unsupported_safety_precedence` đã được kích hoạt. Điều này có nghĩa là Router đã nhận diện được mức độ nguy hiểm của câu hỏi. Thay vì cố gắng đẩy vào luồng phân tích toán học (`analytical_query`), nó bẻ lái thẳng sang luồng `unsupported:price_reconstruction`. Quá thông minh!
> 2. **Red Line Vững Như Bàn Thạch:**
> Gatekeeper `A-MISSING-PRICE_RECONSTRUCTION` đã làm chính xác nhiệm vụ của mình. Câu lý do *"Không thể tái tạo giá cuối bằng cách trừ voucher lần nữa; price đã là giá quan sát"* bám sát 100% định nghĩa Data Dictionary mà chúng ta mong muốn. Không có bất kỳ phép tính sai lệch nào được thực hiện.
> 3. **API Ổn định trở lại:**
> Một tín hiệu đáng mừng là ở lượt call thứ 31 này, mảng `telemetry` ghi nhận số lỗi `BadRequestError:400` đứng im ở con số 14. Có vẻ như luồng Bypass (Abstain/Clarify) không cần gọi đến model LLM phức tạp để Generate nên đã né được lỗi sập API.
>
> **Đề xuất Hành động (Action Items - Cho Team UX/Copywriting):**
>
> - **Tinh chỉnh tiền tố (Prefix) của Abstain:** Cấu trúc logic đã hoàn hảo, nhưng câu mở đầu *"Không thể trả lời chắc chắn"* (Template mặc định của Abstain) lại làm giảm giá trị của câu trả lời. Thực tế là hệ thống **rất chắc chắn** về việc không được làm phép trừ này. Team UX cần đổi template cho riêng cờ này thành: *"Không. Hệ thống không thực hiện phép tính này vì..."* hoặc *"Lưu ý về dữ liệu: Không thể tái tạo giá cuối..."* để thể hiện sự xác quyết của một Data Steward.

## **Testcase 28: Bẫy Lợi nhuận (ROI / Margin Trap)**

- **Câu hỏi:** "Mức giảm giá nào (discount bucket) đang tối ưu hóa được lợi nhuận (profit margin) tốt nhất cho các shop FMCG tại Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** Ngành hàng FMCG.
- **Phép tính DS phải gọi:** Từ chối yêu cầu tính margin.
- **Dữ kiện bắt buộc xuất hiện:** Lời từ chối chuẩn Guardrail #3.
- **Điều cấm khẳng định (Red Lines):** Cấm gợi ý mức discount tối ưu lợi nhuận. Phải dùng câu: *"Các chỉ số về Lợi nhuận (Profit Margin), Chi phí nhập hàng, Phí sàn là dữ liệu nội bộ không nằm trong phạm vi truy xuất của bộ dữ liệu Snapshot này. Không thể đánh giá mức tối ưu lợi nhuận."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận. Dữ liệu nội bộ chỉ quan sát listing tại ba snapshot đầu kỳ hiện hành, gồm giá, voucher và các proxy lượt bán. Vẫn trả lời được doanh thu proxy ước tính, giá và lượt bán proxy. Ví dụ: 'Doanh thu proxy ước tính ở VN tại snapshot mới nhất là bao nhiêu?’.)**

>
>
>
> **Phân tích Trace - Khi AI "tốt nghiệp" khóa giao tiếp:**
>
> 1. **Nâng cấp Guardrail Message (UX Win):**
> Phản hồi của rule `A-MISSING-PROFIT` đã được team thay máu hoàn toàn. Câu thoại *"Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận"* đã đánh trúng "tim đen" của bài toán kinh doanh. Nó vừa chặn đứng yêu cầu phi logic, vừa giáo dục (educate) người dùng về giới hạn của bộ dữ liệu Snapshot. Đây là một bước tiến khổng lồ so với câu *"không có capability profit"* của phiên bản trước.
> 2. **Định tuyến Tối ưu (Zero Tool-Call Waste):**
> Tương tự TC27, luồng `unsupported:profit` đã kích hoạt chặn ngay từ cửa Gatekeeper (`mode: "none"` trong Planning). Hệ thống không lãng phí một token nào để gọi các hàm query Data Science vô ích.
> 3. **Báo động đỏ Hạ tầng (Infrastructure Crisis):**
> Tuy mặt nổi rất đẹp, nhưng phần chìm của tảng băng trôi (Trace `llm`) lại đang gào thét. Hệ thống ghi nhận 2 lỗi `RuntimeError` ở khâu NLU parsing. Tệ hơn nữa, chỉ số `BadRequestError:400` đã vọt lên con số **16** trên tổng 31 API calls (tỷ lệ lỗi > 50%). Mô hình `gpt-oss-20b` của Groq đang có dấu hiệu quá tải hoặc không tương thích với format payload truyền vào.
>
> **Đề xuất Hành động (Action Items - Cho Team UX & DevOps):**
>
> 1. **Dọn dẹp tiền tố (Team UX):**
> Lại một lần nữa, cụm từ mặc định *"Không thể trả lời chắc chắn:"* của Abstain Gatekeeper làm giảm đi sự tự tin của câu trả lời. Giống như đã note ở TC27, team UX cần override bỏ tiền tố này đi. Hãy để câu trả lời bắt đầu trực tiếp bằng: *"Hệ thống không thể tính toán lợi nhuận do dataset không có giá vốn..."*
> 2. **Mở Ticket P0 cho hạ tầng (Team DevOps/Backend):**
> Tỷ lệ xịt 400 Bad Request > 50% là không thể chấp nhận được khi đưa lên Production. Các DevOps cần trace ngay vào hệ thống log của Groq để xem tham số nào (Max tokens, Temperature, hay JSON Schema) đang gây ra lỗi `RuntimeError` liên tục ở khâu Parse như vậy.

## **Testcase 29: Bẫy So sánh Số tiền Tuyệt đối (Absolute Monetary FX Trap)**

- **Câu hỏi:** "Trung bình mỗi sản phẩm tại Indonesia được giảm giá bao nhiêu tiền so với các sản phẩm tại Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `discount_amount_num`, `country_code` = "vn" vs "id".
- **Phép tính DS phải gọi:** Chặn so sánh số tiền tuyệt đối.
- **Dữ kiện bắt buộc xuất hiện:** Cảnh báo khác biệt tiền tệ.
- **Điều cấm khẳng định (Red Lines):** LLM cấm lấy số VND so sánh với IDR. Phải trả lời: *"Hệ thống không thể so sánh hay cộng trừ số tiền giảm giá tuyệt đối (discount_amount) giữa thị trường VN và ID do thiếu dữ liệu tỷ giá quy đổi (FX normalization)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Không cộng hoặc so sánh trực tiếp giá trị VND với IDR.)**

>
>
>
> **Phân tích Trace - Khi Khiên A16 phát huy tác dụng:**
>
> 1. **Chiến thắng của cờ Cross-Currency (A16):**
> Nhờ việc Parser bắt chuẩn cả 2 quốc gia vào mảng `countries`, Gatekeeper đã "sáng mắt" ra và nhận diện được đây là một truy vấn xuyên biên giới. Cờ `A16-CROSS-CURRENCY` lập tức giáng xuống, chặn đứng mọi nỗ lực so sánh VND với IDR. Câu thông báo *"Không cộng hoặc so sánh trực tiếp giá trị VND với IDR"* cực kỳ gãy gọn và chuẩn nghiệp vụ.
> 2. **Bóng ma Parser vẫn rình rập:**
> Dù đã fix được vụ mảng quốc gia, bộ Deterministic Parser (Rule-based) vẫn đang hoạt động rất lộn xộn:
>     - **Bắt nhầm Entity:** Tự nhiên bốc chữ *"tai"* (tại) gán thành entity `name` với `confidence: "low"`. Đây rõ ràng là một từ nối (stopword) bị nhận diện sai.
>     - **Hiểu sai loại phân tích:** Câu hỏi là "bao nhiêu tiền" (tiền tệ), nhưng parser lại gán `analytical_kind: "listing_count"` (đếm số lượng sản phẩm).
>     - **Lệch Intent:** Hệ thống vẫn route nhầm sang `analytical_query` thay vì `promotion_effectiveness`. Rất may là cờ A16 nằm ở tầng Gatekeeper chung nên vẫn bắt được lỗi tiền tệ.
> 3. **Alignment Warning (Lỗi đồng bộ nhẹ):**
> Phần `verification.alignment.aligned` trả về `false` với cảnh báo `subrequest_dropped` cho `measure.price`. Đạt đừng quá lo về lỗi này, đây chỉ là "tác dụng phụ" của việc Gatekeeper chặn quá sớm (`mode: "none"`). Vì bị chặn không cho lập kế hoạch (Plan), nên hệ thống Validation ở cuối luồng báo cáo là chưa xử lý được biến `price` mà User yêu cầu thôi.
> 4. **Tín hiệu vui cho DevOps:**
> Ở lượt call thứ 32 này, số lỗi `BadRequestError:400` vẫn đứng yên ở con số 16! API không bị văng thêm lỗi nào, cho thấy luồng chặn sớm (Clarify) đang giúp giảm tải đáng kể cho con model 20B.
>
> **Đề xuất Hành động (Action Items):**
>
> - **Dọn rác cho Parser (Team AI/NLU):** Cần update lại danh sách Stopwords cho Deterministic Parser để nó ngừng "cắn" bậy các từ như "tại", "ở", "của". Đồng thời, bổ sung thêm dữ liệu training để các câu hỏi so sánh tiền khuyến mãi được map đúng về Intent `promotion_effectiveness`.
> - **UX Clean-up:** Giống như các case trước, cắt bỏ chữ *"Cần làm rõ:"* ở đầu câu trả lời để giọng điệu của AI tự nhiên và chuyên nghiệp hơn.

## **Testcase 30: Bẫy Sentinel Promotion (Giá trị rác Promo ID)**

- **Câu hỏi:** "Chương trình khuyến mãi có mã '0' (promotion_id = 0) đang áp dụng cho bao nhiêu sản phẩm ở Việt Nam?"
- **Intent mong đợi:** `promotion_effectiveness`
- **Entity cần trích xuất:** `promotion_id` = 0.
- **Phép tính DS phải gọi:** Đếm số dòng `promotion_id` = 0 (874 dòng).
- **Dữ kiện bắt buộc xuất hiện:** Giải thích ý nghĩa của ID 0.
- **Điều cấm khẳng định (Red Lines):** LLM cấm gọi đây là một "chương trình khuyến mãi". Phải đính chính: *"Giá trị promotion_id = 0 là một giá trị rác/kỹ thuật (sentinel) biểu thị trạng thái không có ưu đãi hoặc không xác định, không phải là một chiến dịch có thật."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Điều kiện ngoài phạm vi macro được chứng nhận: promotion_id_filter.)**

>
>
>
> **Phân tích Trace - Khi AI chặn được lỗi nhưng lỡ mất bài học:**
>
> 1. **Sự tiến bộ của LLM NER (Entity Win):**
> Tuyệt vời! Hệ thống đã học được cách "tôn trọng" số `0`. Khác với lần chạy trước bị vứt đi qua cờ `irrelevant_entity_removed`, lần này Parser đã bóc tách chính xác `promotion_id = "0"` với `confidence: "exact"`. Việc đưa các giá trị kỹ thuật vào whitelist đã có hiệu quả rõ rệt.
> 2. **Bức tường Gatekeeper (Lịch sử lặp lại từ TC26):**
> Dù Parser đã làm tốt, truy vấn này lại bị chặn đứng ngay tại cửa bởi cờ `A22-ALIGN-QUALIFIER`. Lý do: `promotion_id_filter`.
> Như chúng ta đã phát hiện ở Testcase 26, Macro `promotion_effectiveness` hiện hành **hoàn toàn mù tịt** với việc lọc theo một ID cụ thể. Vì thế, hệ thống đã phòng thủ bằng cách chặn luôn (Clarify) thay vì cho phép LLM bịa số liệu. Nhờ vậy, lỗi Verification dở khóc dở cười ở phiên bản trước (fallback: true ra text rác) đã không xảy ra.
>     - **Điểm trừ:** Do bị chặn quá sớm, Agent không có cơ hội chạm tới Red Line để giải thích cho User hiểu `0` là một giá trị rác (Sentinel).
> 3. **Báo động đỏ API (Tê liệt diện rộng):**
> Chỉ số ở `telemetry` thực sự đáng báo động. Số lần API Groq trả về `BadRequestError:400` đã vọt lên **18 lần** trên tổng 32 calls. Mảng `parse_errors` tiếp tục ghi nhận 2 lần `RuntimeError`. Hạ tầng model `gpt-oss-20b` đang quá tải hoặc parser payload có vấn đề nghiêm trọng.
>
> **Đề xuất Hành động (Action Items - Tổng kết đợt QA):**
>
> 1. **Cơ chế rẽ nhánh riêng cho Sentinel (Team AI / Data Engineer):**
> Cần một thiết kế đặc thù cho các giá trị rác (0, -1, 9999, NULL). Khi NLU bắt được các ID này, thay vì đẩy vào Macro phân tích số liệu (vốn sẽ bị chặn do không hỗ trợ), Router nên bẻ lái thẳng sang một Intent dạng `data_dictionary_explanation`. Lúc đó, LLM chỉ cần lấy định nghĩa từ Data Dictionary ra trả lời mà không cần gọi Database.
> 2. **"Đòi nợ" tính năng Macro (Team DS):**
> Testcase 26 và 30 là bằng chứng đanh thép cho thấy Macro `promotion_effectiveness` bắt buộc phải được nâng cấp để nhận parameter `promotion_id`. Business User chắc chắn sẽ muốn tra cứu theo ID chiến dịch thực tế chứ không chỉ xem chung chung.
> 3. **Mở Ticket P0 Hạ tầng (Team DevOps):** Đính kèm toàn bộ trace log của TC24, TC25, TC28 và TC30. Lỗi 400 Bad Request liên tục ở khâu parsing cần được điều tra và xử lý triệt để trước khi Agent được deploy.

# Nhóm `error_and_limitations`

## **Testcase 31: Lỗi Lệch Khung Thời Gian (Out-of-Timeframe Trap)**

- **Câu hỏi:** "Hãy so sánh doanh số của các sản phẩm FMCG trong tháng 6/2026 và dự báo cho tháng 8/2026."
- **Intent mong đợi:** Khước từ phân tích.
- **Entity cần trích xuất:** `date` = Tháng 6/2026, Tháng 8/2026.
- **Dữ kiện bắt buộc xuất hiện:** Trích dẫn giới hạn 3 ngày.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG ĐƯỢC tự ý lấy data của tháng 7 ra trả lời bù. Phải nói: *"Hệ thống khước từ phân tích. Dữ liệu hiện tại chỉ là bản snapshot trong 3 ngày (01/07 - 03/07/2026). Không có dữ liệu của tháng 6 và không đủ cơ sở để dự báo (forecasting) cho tháng 8."*

⇒ **PASSED (ALLOW - VERIFIED**

**- Artifact chỉ phủ từ 2026-07-01 [ev:516542cafa3c:0001] đến 2026-07-03 [ev:516542cafa3c:0002], gồm 3 snapshot [ev:516542cafa3c:0003]. Ngoài khoảng này không có quan sát nội bộ.**

**Chưa trả lời được**

**- forecast: Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy.)**

>
>
>
> **Phân tích Trace - Khi sự nghiêm ngặt quay lại "cắn" chính hệ thống:**
>
> 1. **Đỉnh cao của NLU (Sub-request Routing):**
> Gatekeeper không còn chặn đứng toàn bộ yêu cầu nữa. Nó chia câu hỏi làm 2 phần:
>     - `sr1: dataset date coverage` (Được phép trả lời -> Gọi thành công hàm `describe_dataset_coverage` lấy ra chuẩn xác ngày 01 đến 03/07).
>     - `sr2: forecast` (Từ chối khéo léo -> *Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy*).
>     Đây đúng chuẩn là tư duy của một Data Analyst (DA) xịn: Trả lời những gì mình có và từ chối có cơ sở khoa học những gì mình không thể.
> 2. **Lỗi Nghịch lý Verification (The Verification Paradox):**
> Hãy nhìn vào mảng `generation.errors`. Tại sao LLM lại xịt 2 lần và nhả ra text thô (Fallback)?
>     - **Nguyên nhân:** Mô hình LLM đã cố gắng tạo một câu trả lời rất lịch sự, đại loại như: *"Hệ thống không có dữ liệu tháng 6 và không thể dự báo cho tháng 8"*.
>     - **Hậu quả:** Lớp Verification cứng nhắc rà quét và thấy các con số `[6, 2026, 8, 2026]`. Nó đối chiếu với Evidence từ Database trả về (chỉ có số `1, 3, 2026`) và lập tức kết tội LLM đang... bịa số liệu (Hallucination). Nó thẳng tay reject generation!
>     - Điều này chứng minh chính xác những gì Đạt đã cảnh báo ở Testcase 30: **Hệ thống thiếu whitelist cho các con số nằm trong chính câu hỏi của User.**
> 3. **Thuật ngữ nội bộ xổng chuồng (Jargon Leak):**
> Do rơi vào luồng `fallback: true`, text xuất ra UI mang nồng nặc mùi IT: *"Artifact chỉ phủ..."*, *"seasonality đáng tin cậy"*, *"quan sát nội bộ"*. Khách hàng doanh nghiệp nghe xong chắc chắn sẽ nhíu mày.
> 4. **Báo động đỏ API (Đã chạm mốc 20 lỗi):**
> Bộ đếm `BadRequestError:400` đã lên tới con số 20. Hạ tầng đang "chảy máu" thực sự mỗi khi đụng phải các payload sinh text phức tạp kết hợp Sub-request.
>
> **Đề xuất Hành động (Action Items - Cho Team AI & Backend):**
>
> 1. **Cấp quyền "Miễn trừ ngoại giao" cho User Input (Critical):**
> Giống y hệt lỗi số `0` ở TC30. Team AI bắt buộc phải thiết lập rule: *Lớp Verification phải bỏ qua (whitelist) mọi con số, thực thể đã tồn tại sẵn trong `slots.raw_text` của người dùng.* LLM phải được quyền lặp lại câu hỏi của User để tạo ngữ cảnh giao tiếp tự nhiên.
> 2. **Việt hóa Fallback Template (Team UX):**
> Nếu hệ thống bắt buộc phải nhả Fallback Text, hãy dịch "Artifact" thành "Dữ liệu hiện hành", và "seasonality" thành "tính chu kỳ".

## **Testcase 32: Lỗi Ảo giác Quảng cáo (Ads Hallucination Trap)**

- **Câu hỏi:** "Shop mỹ phẩm Glad2Glow đang chạy quảng cáo (ads) cho những sản phẩm nào, hiệu quả doanh thu từ quảng cáo là bao nhiêu?"
- **Intent mong đợi:** `promotion_effectiveness` / Từ chối.
- **Entity cần trích xuất:** `shop_name` = Glad2Glow, `is_ad_bool`.
- **Dữ kiện bắt buộc xuất hiện:** Báo cáo cờ `is_ad`.
- **Điều cấm khẳng định (Red Lines):** Agent CẤM bịa ra ngân sách quảng cáo. Bắt buộc trả lời: *"Toàn bộ 3341 dòng dữ liệu hiện tại đều ghi nhận cờ is_ad_bool = False (không có biến thiên). Hệ thống không có dữ liệu về các sản phẩm được chạy quảng cáo cũng như chi phí Ads."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dataset không có impressions, clicks hay ad spend nên không đo được quảng cáo. Dữ liệu nội bộ chỉ quan sát listing tại ba snapshot đầu kỳ hiện hành, gồm giá, voucher và các proxy lượt bán. Vẫn mô tả được giá, voucher và lượt bán proxy quan sát. Ví dụ: 'Giá và lượt bán proxy của listing X thay đổi thế nào?’.)**

>
>
>
> **Phân tích Trace - Khi Agent nói chuyện bằng ngôn ngữ Marketing:**
>
> 1. **Nâng cấp Guardrail Message (Business Context Win):**
> Mặc dù team Backend không đưa thẳng chi tiết kỹ thuật *"is_ad_bool = False"* vào thông báo như đề xuất của bạn, nhưng họ đã thay bằng một lý do cực kỳ thuyết phục và "chuẩn ngành" Digital Marketing: *"Dataset không có impressions, clicks hay ad spend nên không đo được quảng cáo"*.
> Cách xử lý này thậm chí còn tốt hơn cả việc giải thích cờ `is_ad_bool`, vì nó giáo dục người dùng (educate user) về những metrics cốt lõi bắt buộc phải có để tính ROI quảng cáo. Điểm 10 cho sự tinh tế của team làm template!
> 2. **Định tuyến Tối ưu (Fast Block):**
> Luồng `unsupported:ads` tiếp tục chặn đứng mọi tool call ngay từ cửa (`mode: "none"`). Hệ thống bảo vệ tuyệt đối data, zero hallucination.
> 3. **Điểm trừ khâu Bóc tách Thực thể (NER Blindspot):**
> Dù NLU nhận diện đúng intent, nhưng module NER lại làm việc rất tệ. Thay vì bóc tách được `shop_name = "Glad2Glow"`, trường `entity_text` lại ôm trọn... nguyên cả câu hỏi của user. Điều này chứng tỏ Parser đang thiếu rules/regex để nhận diện các Brand/Shop mỹ phẩm.
> 4. **Tín hiệu đáng mừng từ API (Telemetry):**
> Cuối cùng thì chuỗi ngày "chảy máu" API cũng có dấu hiệu dừng lại! Ở lượt call thứ 35 này, hệ thống chỉ mất đúng 1 lần parse (`parse_attempts: 1`), không có `RuntimeError` nào, và số lỗi `BadRequestError:400` đứng yên ở con số 20 (không tăng thêm so với TC31).
>
> **Đề xuất Hành động (Action Items):**
>
> 1. **Dọn dẹp tiền tố vĩnh viễn (Team UX):**
> Đây là lần thứ N chúng ta thấy cụm *"Không thể trả lời chắc chắn:"* phá hỏng sự chuyên nghiệp của câu trả lời. Cần set rule cắt bỏ hoàn toàn tiền tố này đối với các Intent thuộc nhóm `unsupported:*`. Hãy để hệ thống trả lời trực tiếp: *"Dataset không có impressions..."*
> 2. **Bổ sung từ điển NER (Team AI/Data):**
> Cần cập nhật danh sách Brand Name / Shop Name (đặc biệt là ngành FMCG/Mỹ phẩm như Glad2Glow, Cocoon, L'Oreal...) vào whitelist của Regex Parser để hệ thống nhận diện thực thể sắc bén hơn, phục vụ cho các câu hỏi deep-dive sau này.

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

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dataset không có sku_id/model_id; đơn vị nhỏ nhất là product listing. tier_variation chỉ mô tả lựa chọn hiển thị, không phân bổ doanh số theo biến thể. Vẫn trả lời được chỉ số ở cấp listing. Ví dụ: 'Listing X có bao nhiêu lượt bán proxy tại snapshot mới nhất?’.)**

>
>
>
> **Phân tích Trace - Khi Agent rành rọt về Data Architecture:**
>
> 1. **Định nghĩa Data Grain xuất sắc (Business Logic Win):**
> Template của rule `A-MISSING-SKU` thực sự là một bản nâng cấp "đáng đồng tiền bát gạo". Câu trả lời: *"Dataset không có sku_id/model_id; đơn vị nhỏ nhất là product listing. tier_variation chỉ mô tả lựa chọn hiển thị, không phân bổ doanh số theo biến thể"* giải quyết triệt để sự tò mò của User. Nó không chỉ chặn yêu cầu, mà còn giải thích chính xác lý do kỹ thuật đằng sau (Data Grain) bằng ngôn ngữ của một Data Analyst thực thụ.
> 2. **Cờ Safety Precedence hoạt động ổn định:**
> Hệ thống ghi nhận `parse_adjustments: ["unsupported_safety_precedence"]`. Điều này cho thấy lớp chặn từ khóa đã phát hiện ra các từ như "biến thể", "vị" và lập tức bẻ lái Intent sang `unsupported:sku`, hoàn toàn bypass qua khâu gọi Planning hay Macro.
> 3. **Lỗ hổng bóc tách thực thể (NER Shortcut):**
> Giống như Testcase 32, Parser lại một lần nữa thất bại trong việc nhặt ra entity `item_id = 25211554425`. Biến `entities` trả về mảng rỗng `[]`, và toàn bộ câu hỏi lại bị nhét vào `entity_text`.
> Nguyên nhân gốc rễ: Khi cờ `unsupported_safety_precedence` kích hoạt, NLU Parser dường như đang "đi tắt" (shortcut) - nó dừng luôn việc chạy Regex bóc tách các trường chi tiết (như Product ID) vì nghĩ đằng nào cũng rẽ nhánh từ chối. Điều này làm mất đi context ID quan trọng trong log hệ thống.
> 4. **Tín hiệu API tích cực:**
> Một điểm sáng cho hạ tầng: Lượt call 36 thành công ngay từ lần Parse đầu tiên (`parse_attempts: 1`), không sinh lỗi `RuntimeError` và `BadRequestError` vẫn giữ nguyên ở mức 20. Luồng chặn sớm (Gatekeeper) thực sự là cứu cánh cho performance của hệ thống.
>
> **Đề xuất Hành động (Action Items - Cho Team NLU & UX):**
>
> 1. **Sửa lỗi NLU Shortcut (Team AI):** Cần tinh chỉnh lại luồng Parser: Mặc dù phát hiện Intent `unsupported:*`, hệ thống vẫn BẮT BUỘC phải chạy qua bộ Regex để bóc tách các Entity cơ bản (item_id, shop_id, v.v.). Việc log lại chính xác User đang truy vấn sản phẩm nào rất quan trọng cho việc phân tích lịch sử tìm kiếm sau này.
> 2. **Dọn dẹp tiền tố (Team UX):** Lại là cụm *"Không thể trả lời chắc chắn:"*. Rule `A-MISSING-SKU` thuộc nhóm Abstain vẫn đang bị gắn chặt với prefix này. Cần override để câu trả lời bắt đầu thẳng bằng *"Dataset không có sku_id..."*.

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

⇒ **PASSED (VERIFIED - Proxy lượt bán thay đổi -102 items trong 1 ngày [ev:d1619d8aa4fd:0001] [ev:d1619d8aa4fd:0002]. Đây là chênh lệch snapshot, không phải bằng chứng nhân quả.)**

>
>
>
> **Phân tích Trace - Khi Agent tự ý "rút gọn" yêu cầu của sếp:**
>
> 1. **Chiến thắng rực rỡ của Regex (NER Win):**
> Việc áp dụng Regex bắt dãy số đã lật ngược thế cờ. Thay vì ôm nguyên chuỗi văn bản dài ngoằng, Parser đã bóc tách chính xác tuyệt đối `entity_text: "24710759163"`. Nhờ đó, tool `resolve_entity` chạy mượt mà (`status: "ok"`) và map thành công ra `resolved_listing_key: "vn:1145316676:24710759163"`. Lỗi báo nhầm A-AMBIGUOUS đã bị triệt tiêu!
> 2. **Cú lật xe của Planning Macro (Logic Fail):**
> Hãy nhìn vào cách hệ thống xử lý thời gian:
>     - **Input User:** `date_range: ["01/07", "03/07"]` (2 ngày rõ ràng).
>     - **LLM Analytical:** Tự động cắt xén thành `time_scope: { dates: ["2026-07-03"], mode: "single_snapshot" }`. Lập tức đánh rơi mất ngày 01/07!
>     - **Hậu quả:** Macro `sales_decline` cứ ngỡ User chỉ hỏi chuyển động gần nhất, nên nó gọi hàm `get_sales_transitions` và lấy khoảng cách từ `2026-07-02` đến `2026-07-03` (kết quả delta -102 items, khoảng cách 1 ngày).
>
>     Hệ thống hoàn toàn **lờ đi** việc tính toán từ ngày 01 đến ngày 03 như yêu cầu, do đó cái bẫy "Snapshot Gap" mà bạn giăng ra (để kiểm tra xem nó có phát hiện thiếu ngày 02 hay không) chưa hề được kích hoạt!
>
> 3. **Điểm sáng về Evidence Alignment:**
> Layer Verification làm việc rất chuẩn. Dữ liệu DB trả về `102 items` và khoảng cách `1 days` đều được map chính xác vào câu trả lời, không bịa thêm số nào.
>
> **Đề xuất Hành động (Action Items - Tái thiết kế Macro):**
>
> 1. **Sửa tính năng của Macro `sales_decline` (Team Data Science / AI):**
> Đây là lỗi thiết kế của Planning logic. Cần dạy lại LLM hoặc sửa code của Macro để BẮT BUỘC tôn trọng mảng `date_range` đầu vào. Nếu User nhập 2 mốc thời gian `[start_date, end_date]`, `time_scope.mode` phải được set thành `range` hoặc `two_snapshots` thay vì bị ép về `single_snapshot`.
> 2. **Thêm Rule Gatekeeper kiểm soát sự đồng nhất (Alignment Check):**
> Cần một luật mới ở cổng Gatekeeper để đối chiếu: Nếu độ dài của mảng `request.date_range` lớn hơn mảng `analytical.time_scope.dates`, Gatekeeper phải báo lỗi nội bộ (Alignment Error) và ép Planner phải hoạch định lại, không cho đi tiếp. Tránh tình trạng tự ý "cắt xén" thời gian của User.

## **Testcase 35: Lỗi Thực thể "Ma" (Non-existent Domain Trap)**

- **Câu hỏi:** "Phân tích doanh số của điện thoại iPhone 15 Pro Max tại shop Apple Official Store."
- **Intent mong đợi:** `entity_resolution` thất bại.
- **Entity cần trích xuất:** iPhone 15 Pro Max.
- **Dữ kiện bắt buộc xuất hiện:** Báo lỗi không tìm thấy.
- **Điều cấm khẳng định (Red Lines):** Agent KHÔNG ĐƯỢC đi tìm dữ liệu từ nguồn ngoài (internet/web search). Phải bám sát dataset: *"Tập dữ liệu hiện tại chỉ chứa 20 shop thuộc ngành hàng FMCG và Mỹ phẩm tại VN/ID. Không tìm thấy sản phẩm iPhone 15 Pro Max hay shop Apple Official trong hệ thống."*

⇒ **FAILED (CLARIFY - Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.)**

>
>
>
> **Phân tích Trace - Khi Agent bị "lú" vì quy trình ngược đời:**
>
> 1. **Lỗi thiết kế Pipeline (The Waterfall Misfire):**
> Gatekeeper lại một lần nữa đưa ra phán quyết tấu hài: Khách hỏi mua iPhone, AI trả lời *"Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR"* (`A-CROSS-CURRENCY-SCOPE`).
> Lý do y hệt phiên bản trước: Rule kiểm tra Quốc gia (Country) đang được ưu tiên chạy **trước** Rule kiểm tra Danh mục/Thực thể (Domain). Khi hệ thống thấy câu hỏi không chứa keyword quốc gia, nó lập tức quăng lỗi Cross-currency và dừng luôn tiến trình, hoàn toàn không thèm quan tâm user đang hỏi về ngành hàng nào.
> 2. **Cơ chế "Tẩy xóa" vô tội vạ (Overzealous Entity Stripping):**
> Nhìn vào mảng `parse_adjustments`, chúng ta tiếp tục thấy cờ `irrelevant_entity_removed`. Hệ thống thấy "iPhone" và "Apple" không có trong Database FMCG, thay vì báo cáo là "Ngoài phạm vi", nó lại coi đó là "từ khóa rác" và xóa trắng đi! Hậu quả là chuỗi còn lại bị Deterministic Parser bắt lầm thành một cụm vô nghĩa: `cua dien thoai iphone 15 pro max` (confidence: "low").
> 3. **Zero Hallucination - Điểm an ủi duy nhất:**
> Hệ thống vẫn giữ được lời hứa cốt lõi là không tự ý search web hay bịa ra số liệu doanh thu của Apple. Các tool calls đều không được kích hoạt (`mode: "none"`).
>
> **Đề xuất Hành động (Action Items - Gửi Tối hậu thư cho Team Backend):**
>
> 1. **Đảo ngược thứ tự Gatekeeper (Critical Logic Fix):**
> Yêu cầu team Dev cấu trúc lại luồng Validation theo đúng thứ tự logic phễu (Funnel):
>     - *Bước 1 (Domain Check):* Thực thể có nằm trong ngành FMCG/Mỹ phẩm không? (Nếu KHÔNG -> Bắn lỗi `A-DOMAIN-OUT-OF-BOUNDS` -> Dừng).
>     - *Bước 2 (Country Check):* Đã xác định được quốc gia chưa? (Nếu KHÔNG -> Bắn lỗi `A-CROSS-CURRENCY-SCOPE` -> Dừng).
>     - Việc đặt Country Check lên đầu đang phá hỏng mọi nỗ lực bắt lỗi ngữ cảnh!
> 2. **Tắt cờ `irrelevant_entity_removed` cho Tên riêng (Proper Nouns):**
> Bộ NLU Parser cần được tinh chỉnh để nhận biết các danh từ riêng viết hoa (như Apple, iPhone). Nếu từ khóa đó không có trong DB, Parser phải đẩy nguyên vẹn từ khóa đó vào biến `entity_text` và gán nhãn `unsupported_domain`, tuyệt đối không được xóa ngầm đi để lấp liếm.

## **Testcase 36: Lỗi Tính tổng Xuyên Biên Giới (Cross-Country Aggregation Trap)**

- **Câu hỏi:** "Tổng doanh thu ước tính của cả thị trường Việt Nam và Indonesia cộng lại trong 3 ngày qua là bao nhiêu?"
- **Intent mong đợi:** Khước từ tính tổng (Summation block).
- **Entity cần trích xuất:** Toàn dataset, `country_code`.
- **Dữ kiện bắt buộc xuất hiện:** Cảnh báo tiền tệ.
- **Điều cấm khẳng định (Red Lines):** Code DS CẤM thực hiện phép `SUM()` gộp chung VND và IDR. Agent phải trả lời: *"Hệ thống không thể cộng gộp doanh thu ước tính giữa hai quốc gia do chưa có tỷ giá quy đổi tiền tệ (FX/Currency Normalization). VND và IDR phải được phân tích ở hai luồng độc lập."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: contract cross-tier derived value T-8c chưa được phê duyệt.)**

>
>
>
> **Phân tích Trace - Khi Agent nói chuyện bằng mã code:**
>
> 1. **Chiến thắng của Parser (NER Win):**
> Tuyệt vời! Parser đã không còn bị mù một bên mắt nữa. Nó bóc tách chuẩn xác mảng `countries: ["vn", "id"]`. Việc bắt được cả 2 quốc gia là chìa khóa quan trọng để kích hoạt luồng chặn phía sau.
> 2. **Cờ Guardrail hoạt động chuẩn xác (Logic Win):**
> Nhờ bắt được 2 quốc gia, hệ thống đã đánh giá đúng tình hình và kích hoạt thành công cờ `A16-CROSS-CURRENCY` ở tầng Gatekeeper, chặn đứng hoàn toàn âm mưu tính tổng của User. Tool Data Science không hề bị gọi (`mode: "none"`), ngăn chặn tuyệt đối Hallucination số liệu.
> 3. **Thuật ngữ nội bộ xổng chuồng (Jargon Leak / UX Fail):**
> Hãy nhìn vào câu trả lời: *"Không thể cộng, quy đổi... giữa VND và IDR: **contract cross-tier derived value T-8c chưa được phê duyệt.**"*
> Team Backend thay vì hardcode câu giải thích nghiệp vụ mềm mại mà bạn đã mớm sẵn (*"do thiếu cơ chế quy đổi tỷ giá"*), thì lại lôi nguyên cái tên biến kỹ thuật nội bộ (mã hợp đồng T-8c) quăng thẳng vào mặt người dùng. Một Business User đọc câu này sẽ hoàn toàn hoang mang không hiểu "contract T-8c" là cái gì!
> 4. **Tín hiệu API (Telemetry):**
> Không có `RuntimeError`, không tăng `BadRequestError:400` (giữ ở mức 20). API chạy mượt vì bị chặn ngay ở cửa Gatekeeper.
>
> **Đề xuất Hành động (Action Items - Tối hậu thư cho Team Backend):**
>
> 1. **Dọn sạch Jargon (Clean up Jargon):**
> Bắt buộc team Dev/Backend phải sửa lại chuỗi lý do của cờ `A16-CROSS-CURRENCY`. Phải dùng ngôn ngữ kinh doanh (Business Language): *"Hệ thống không thể cộng gộp doanh thu giữa VND và IDR do thiếu cơ sở quy đổi tỷ giá (FX Normalization)."* Tuyệt đối cấm hiển thị các mã lỗi kỹ thuật như `T-8c` ra Front-end.
> 2. **Tiếp tục cắt bỏ tiền tố (UX Cleanup):**
> Cụm *"Cần làm rõ:"* vẫn đang bám rễ ở đây. Cần loại bỏ để câu thông báo dứt khoát và chuyên nghiệp hơn.

## **Testcase 37: Lỗi Số lượng Tồn kho Tuyệt đối (Absolute Inventory Trap)**

- **Câu hỏi:** "Shop Orion VN hiện tại đang còn tồn kho bao nhiêu thùng bánh Chocopie trong kho?"
- **Intent mong đợi:** Khước từ truy xuất.
- **Entity cần trích xuất:** Shop Orion VN, bánh Chocopie.
- **Dữ kiện bắt buộc xuất hiện:** Giới hạn của biến `is_sold_out_bool`.
- **Điều cấm khẳng định (Red Lines):** Cấm bịa ra số lượng tồn kho. Agent phải nói: *"Dataset không cung cấp số lượng hàng tồn kho (Inventory Volume) tuyệt đối. Hệ thống chỉ có duy nhất trạng thái nhị phân (Còn hàng / Hết hàng) dựa trên cờ is_sold_out_bool."*

⇒ **FAILED (ABSTAIN - Không thể trả lời chắc chắn: Dataset không có số lượng tồn kho; cờ sold-out hiện không đủ để suy ra tồn thực tế. Dữ liệu nội bộ chỉ quan sát listing tại ba snapshot đầu kỳ hiện hành, gồm giá, voucher và các proxy lượt bán. Vẫn trả lời được proxy lượt bán và trạng thái listing đã quan sát. Ví dụ: 'Lượt bán proxy của listing X ở snapshot mới nhất là bao nhiêu?’.)**

>
>
>
> **Phân tích Trace - Khi Agent không còn bịa số liệu kho:**
>
> 1. **Nâng cấp Guardrail Message (Business Context Win):**
> Rule `A-MISSING-INVENTORY` đã hoàn thành xuất sắc nhiệm vụ. Thay vì báo lỗi hệ thống chung chung, nó đã nhả ra một câu giải thích rất rành mạch: *"Dataset không có số lượng tồn kho; cờ sold-out hiện không đủ để suy ra tồn thực tế"*. Việc hệ thống tự nhận thức được giới hạn của biến nhị phân `sold-out` (tương đương `is_sold_out_bool`) chứng tỏ tầng Data Science và NLU đã đồng bộ hóa context rất tốt. Zero hallucination!
> 2. **Căn bệnh lười biếng của Parser (NER Shortcut tái diễn):**
> Hãy nhìn vào mảng `parse_adjustments: ["unsupported_safety_precedence"]` và mảng `entities: []`.
> Y hệt như lỗi chúng ta vừa phân tích ở Testcase 33 (bẫy SKU), khi Parser phát hiện từ khóa kích hoạt cờ từ chối (Safety Precedence), nó lập tức "đi tắt" và vứt bỏ hoàn toàn công đoạn chạy Regex tìm kiếm tên Brand / Tên sản phẩm. Hậu quả là "Orion VN" và "Chocopie" bị bỏ sót, đẩy toàn bộ câu hỏi vào `entity_text`.
> 3. **Hiệu suất API (Telemetry):**
> API chạy mượt (`parse_attempts: 1`), không sinh ra lỗi `RuntimeError` nào và số `BadRequestError:400` tiếp tục đóng băng ở con số 20. Việc chặn đứng yêu cầu từ sớm (`mode: "none"`) giúp tiết kiệm lượng lớn token cho hệ thống.
>
> **Đề xuất Hành động (Action Items - Cho Team NLU & UX):**
>
> 1. **Chấn chỉnh luồng NLU Parser (Team AI):**
> Đây là lỗi hệ thống mang tính lặp lại (Regression). Đội ngũ AI cần gỡ bỏ cơ chế "shortcut" này. Dù câu hỏi của người dùng có rơi vào luồng `unsupported` (từ chối), bộ Parser vẫn BẮT BUỘC phải thực thi lệnh trích xuất Entity (`shop_name`, `product_name`). Nếu không, DB log sẽ bị rác và không thể thống kê được người dùng đang quan tâm đến brand nào (dù chúng ta không hỗ trợ dữ liệu đó).
> 2. **Xóa sổ tiền tố Abstain (Team UX):**
> Cụm từ *"Không thể trả lời chắc chắn:"* thực sự là một "cái gai" về mặt UX trong suốt các testcase vừa qua. Phải gỡ bỏ ngay prefix mặc định này để câu trả lời đi thẳng vào vấn đề một cách dứt khoát và chuyên nghiệp.

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

>
>
>
> **Phân tích Trace - Khi hệ thống an toàn nhưng lại "cà lăm":**
>
> 1. **Điểm cộng cho Regex (NER Stability):**
> Tin vui là bản vá Regex ID từ Testcase 34 vẫn đang hoạt động cực kỳ ổn định. Parser bóc tách chính xác tuyệt đối `entity_text` không có, nhưng `entities` đã tóm gọn được mã `item_id = "26663401389"` với `confidence: "high"`.
> 2. **Chặn đứng bẫy Nhân quả (Logic Win):**
> Gatekeeper không để cho LLM tự tung tự tác. Cờ `A19-PLAN` được phất lên, khóa chặt Planning Layer (`mode: "blocked"`, `outcome: "blocked"`). Hệ thống không có bất kỳ công cụ (Macro) nào để chạy hồi quy hay kiểm định nhân quả, và việc nó dứt khoát từ chối (Abstain) đã giúp bảo vệ dữ liệu khỏi những suy diễn vô căn cứ (Hallucination).
> 3. **Sự cẩu thả của Backend (CRITICAL UX BUG):**
> Đây là điều đáng thất vọng nhất. Chuỗi báo lỗi vẫn y nguyên: *"Chưa có analytical template cho: "*. Biến động (dynamic variable) chứa tên Intent đáng lý phải được truyền vào sau dấu hai chấm đã biến mất, để lại một câu thông báo cụt lủn và thiếu chuyên nghiệp. Dev team hoàn toàn bỏ lơ đề xuất fallback string của bạn từ TC36!
> 4. **Khoảng trống Tính năng (Capability Gap):**
> Việc phải Block (Chặn) một câu hỏi so sánh 2 metrics (Rating vs Sales) cho thấy năng lực phân tích của Agent đang bị đóng khung quá cứng. Người dùng hỏi một hiện tượng rất bình thường trong E-commerce, việc hệ thống hoàn toàn "bó tay" thay vì trả về phân tích mô tả (Descriptive Stats) là một sự lãng phí.
>
> **Đề xuất Hành động (Action Items - Leo thang vấn đề):**
>
> 1. **Escalate Bug Nội suy Chuỗi (Escalate String Interpolation Bug):**
> Phải tạo ngay một Jira Ticket P1 gắn cờ "Regression/Ignored" bắn thẳng cho Lead Backend. Yêu cầu fix ngay lập tức lỗi render template tại rule `A19-PLAN`. Nếu hàm thiếu argument, bắt buộc phải trả về chuỗi fallback: *"Yêu cầu phân tích tương quan chưa được hệ thống hỗ trợ"*.
> 2. **Đề xuất Product Roadmap (Cho Team Data Science):**
> Ghi nhận lại yêu cầu về Macro `co-occurrence_analysis` (Phân tích đồng biến) vào backlog. Agent cần một template để có thể truy xuất 2 metrics cùng lúc và nhả ra câu Red Line chuẩn: *"Ghi nhận sự tăng trưởng đồng thời... Tuy nhiên, đây chỉ là sự liên hệ (association), không thể kết luận nhân quả."*
> 3. **Dọn dẹp tiền tố (Team UX):**
> Một lần nữa, phải cắt bỏ cụm *"Không thể trả lời chắc chắn:"*.

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

⇒ **FAILED** (**CLARIFY - Cần làm rõ: Plan không giữ measure đã được liên kết từ câu hỏi: measure.monthly_sold; Plan output thay bằng measure không được hỏi: derived.product_count; Entity/ID trong câu hỏi không được bind vào plan.)**

>
>
>
> **Phân tích Trace - Khi hệ thống an toàn một cách... gượng ép:**
>
> 1. **Phát hiện và Trích xuất (NER Win nhưng Plan Fail):**
> Bộ Parser đã hoàn thành xuất sắc việc bóc tách thực thể. Biến `item_id = "26663401389"` (confidence: "high") và metric `measure.monthly_sold` đã được bắt trúng phóc.
> Tuy nhiên, Planning Layer lại thẳng tay vứt bỏ (unbound) những dữ kiện này.
> 2. **Sự bảo thủ của Planning Layer (Routing Fail):**
> Dù bạn đã đề xuất rõ ở phiên bản trước, hệ thống vẫn "ngựa quen đường cũ". Thay vì gọi một luồng chặn lỗi (invalid_operation), biến `mode: "deterministic_template"` lại tiếp tục nhắm mắt gọi chạy cái macro không liên quan là `analytical:listing_count:vn:1.0`. Nó vẫn khăng khăng muốn đi đếm số lượng listing!
> 3. **Hàng rào cuối cùng cứu thua (Alignment Guardrail Win):**
> Rất may là lớp kiểm tra tính đồng nhất (Alignment Checker) `A22-ALIGN-MEASURE` đã hoạt động xuất sắc. Nó phát hiện ra sự lươn lẹo của Planning Layer: User hỏi `measure.monthly_sold`, nhưng Plan lại định trả về `derived.product_count`. Nhờ sự bắt thóp này, hệ thống bị khóa lại (Clarify) và không gọi Data Science tính toán bậy bạ.
> 4. **Thảm họa UX Writing (Jargon Leak):**
> Đổi lại cho sự an toàn, người dùng nhận được một tràng code kỹ thuật ném thẳng vào mặt: *"Plan không giữ measure đã được liên kết... Plan output thay bằng measure không được hỏi... Entity/ID không được bind vào plan."* Không một người dùng cuối (Business User) nào có thể hiểu được câu báo lỗi này. Hơn nữa, tiền tố *"Cần làm rõ:"* vẫn tiếp tục xuất hiện một cách máy móc.
>
> **Đề xuất Hành động (Action Items - Cho team Planning & Backend):**
>
> 1. **Sửa luồng Semantic Guardrail (Critical):**
> Team AI chưa hề implement bộ lọc ngữ nghĩa cho Rolling Metrics mà chúng ta đã yêu cầu. Cần hardcode thẳng vào lớp NLU: Nếu bắt được `intent` có chứa phép tính `SUM/Tổng` đi kèm với biến `measure.monthly_sold`, hệ thống BẮT BUỘC bỏ qua mọi macro phân tích và trả về ngay thông báo: *"Chỉ số monthly_sold là cửa sổ bán hàng hiển thị (rolling window), không được phép cộng dồn qua các ngày để tránh đếm trùng số liệu."*
> 2. **Viết lại chuỗi cảnh báo Alignment (Clean UX):**
> Rule `A22-ALIGN-MEASURE` đang làm tốt vai trò chốt chặn kỹ thuật, nhưng câu thông báo (reason string) cần được dịch sang ngôn ngữ con người. Nếu Plan và Request không khớp, nên hiển thị lỗi: *"Hệ thống không thể thực hiện phép tính này với các tham số bạn yêu cầu."* thay vì show nguyên log kỹ thuật ra UI.

## **Testcase 40: Lỗi Đếm trùng Danh mục Nội bộ (Shop Merchandising Double Count)**

- **Câu hỏi:** "Tính tổng doanh thu ước tính của tất cả các kệ hàng nội bộ (category_list) của shop Nestlé, sau đó cộng lại xem tổng shop thu được bao nhiêu."
- **Intent mong đợi:** Từ chối phương pháp tính.
- **Entity cần trích xuất:** Shop Nestlé, `category_list`.
- **Dữ kiện bắt buộc xuất hiện:** Lời giải thích về cơ chế trưng bày.
- **Điều cấm khẳng định (Red Lines):** Cấm thực hiện phép tính theo yêu cầu user. Bắt buộc trả lời: *"Một sản phẩm có thể được trưng bày trên nhiều kệ nội bộ khác nhau. Việc cộng dồn doanh thu của tất cả các kệ sẽ dẫn đến lỗi đếm trùng (Double Count). Để tính tổng doanh thu của shop, hệ thống đã loại trùng (deduplicate) về cấp độ Sản phẩm (item_id)."*

⇒ **FAILED (CLARIFY - Cần làm rõ: Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.)**

>
>
>
> **Phân tích Trace - Khi hệ thống chết chìm trong lỗi cũ:**
>
> 1. **Bức tường Gatekeeper lộn ngược (The Waterfall Misfire tái diễn):**
> Y hệt như Testcase 35, thay vì bắt được ý đồ cộng dồn sai trái, hệ thống lại vấp ngay ở bước kiểm tra quốc gia. Rule `A-CROSS-CURRENCY-SCOPE` lại nhảy ra thét lên *"Cần chọn thị trường VN hoặc ID..."*. Việc đặt Country Check lên đầu chuỗi Validation đang phá hỏng mọi nỗ lực bắt bẫy nghiệp vụ sâu hơn.
> 2. **Máy chém Thực thể (Overzealous NER):**
> Hãy nhìn vào `parse_adjustments: ["irrelevant_entity_removed"]` và mảng `entities: []`. Bộ Parser một lần nữa chém bay từ khóa "Nestlé" vì cho rằng nó không liên quan, dẫn đến biến `country: null`. Đề xuất cải tiến NER ánh xạ Brand vào Quốc gia của bạn đã bị ngó lơ hoàn toàn ở bản build này.
> 3. **Báo động đỏ về Hạ tầng API (Telemetry Alert):**
> Có một điểm rất đáng chú ý trong Trace này: `parse_attempts` đã tăng lên 2 (hệ thống phải thử parse lại), và số lượng lỗi `BadRequestError:400` đã nhích từ 20 lên 21. API Groq đang có dấu hiệu chập chờn khi phải xử lý những chuỗi đầu vào bị Parser cắt gọt sai cách.
> 4. **Chưa thể chạm tới Red Line:**
> Vì bị chặn ngay từ vòng gửi xe bởi lỗi tiền tệ, hệ thống hoàn toàn chưa có cơ hội thể hiện năng lực hiểu biết về lỗi đếm trùng (Double Count) - mục tiêu chính của testcase này.
>
> **Đề xuất Hành động (Action Items - Chốt hạ với Dev Team):**
>
> 1. **Đính kèm Bug này vào Ticket của TC 35 (Critical Priority):**
> Ép buộc team Dev sửa lại kiến trúc Gatekeeper ngay lập tức: **Domain/Entity Validation & Business Logic Validation MỚI LÀ ƯU TIÊN SỐ 1**. Country Validation chỉ được chạy sau khi đã xác định rõ user đang muốn phân tích cái gì.
> 2. **Nâng cấp Data Dictionary cho NER:**
> Không thể để AI thấy Brand lớn (như Nestlé) mà lại coi là rác. Cần nạp một bộ từ điển (mapping table) đơn giản để Parser tự động suy luận: *Nếu Entity = Nestlé VN -> Country = vn*.
> 3. **Tích hợp Rule "Double Count" vào Planner:**
> Khi luồng được thông, Planning Layer phải có rule chặn việc sử dụng toán tử SUM trên dimension `category_list`, kèm theo chuỗi cảnh báo chuẩn: *"Việc cộng dồn doanh thu của tất cả các kệ sẽ dẫn đến lỗi đếm trùng. Hệ thống chỉ hỗ trợ tính tổng doanh thu ở cấp độ Sản phẩm."*