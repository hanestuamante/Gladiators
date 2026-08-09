# DR TASK 14/7

STATUS: OPERATING
DO DATE: 14/07/2026
FINAL: 14/07/2026
TIME:  @July 14, 2026 4:08 PM

> **Cập nhật 06/08/2026 — vòng đánh giá đầy đủ TC1–TC40.**
> TC1–TC20 bên dưới được chấm trên commit `a00aefa` (**trước** vòng hardening A–Q).
> Ngày 06/08 toàn bộ 40 testcase đã được chạy lại trên HEAD `56b14f8` (**sau** A–Q),
> và TC21–TC40 lần đầu có groundtruth. Kết quả vòng mới nằm ở phần
> **"Tổng kết toàn bộ TC1–TC40"** cuối tài liệu; phần TC1–TC20 dưới đây được **giữ nguyên
> để truy vết**, đối chiếu trước/sau xem [`docs/040826.md` §25.3](040826.md).

# Nhóm `sales_decline`

## **Testcase 1: Luồng chuẩn (Standard Flow - VN)**

- **Câu hỏi:** "Cho tôi biết vì sao lượt bán của kẹo dẻo Chupa Chups tại shop Perfetti Van Melle Vietnam lại giảm trong những ngày qua?"

**Groundtruth (Claude, dựa trên `data/processed/products_clean.csv`, snapshot 01–03/07/2026):**
Cụm "kẹo dẻo Chupa Chups" khớp mơ hồ với ít nhất 5 listing khác nhau tại shop Perfetti Van Melle Vietnam. `monthly_sold_value` của từng listing qua 3 ngày (07-01 → 07-02 → 07-03):
- `17230920919` COMBO Kẹo dẻo Chupa Chups hương trái cây/cola: 7000 → 7000 → 7000 (không đổi)
- `21475359656` COMBO MIX vị kẹo dẻo 90g: 1000 → 1000 → 1000 (không đổi)
- `48360192218` Kẹo dẻo Chupa Chups hương trái cây/cola: 175 → 910 → 169 (tăng vọt rồi rơi mạnh; net 07-01→07-03 gần như đi ngang)
- `28985249725` Kẹo dẻo Dài‑Xoắn Hươu Cao Cổ: 474 → 475 → 476 (tăng nhẹ)
- `10032780626` Kẹo dẻo vị chua: 7000 → 7000 → 7000 (không đổi)

Không có listing "kẹo dẻo" nào của Chupa Chups tại shop này thể hiện xu hướng giảm thực sự và bền vững trong cửa sổ 3 ngày. Phần lớn giá trị đứng yên (khớp cơ chế hiển thị dạng "bucket" 1.000/7.000 của Shopee), chỉ 1 SKU dao động mạnh kiểu tăng‑rồi‑giảm — nhiều khả năng là nhiễu snapshot chứ không phải xu hướng kinh doanh thật. **Đáp án đúng: tiền đề "giảm trong những ngày qua" không được dữ liệu ủng hộ; cần yêu cầu người dùng chỉ rõ SKU, và với dữ liệu hiện có thì không có suy giảm đáng kể để giải thích.**

**Kết quả model Gladiators (offline/certified-macro, `gladiators.cli`):**
Gate trả về `action=clarify`, `rule_id=A-AMBIGUOUS`, nhưng danh sách gợi ý lại là các sản phẩm **Bibica** ("Combo 2 Kẹo Mềm Sumika Sữa Bibica 275g", "Combo Kẹo Cứng Sữa Cà Phê Bibica 140g", "Túi Kẹo Sing‑Gum Cool Air…") — hoàn toàn không thuộc shop Perfetti Van Melle hay thương hiệu Chupa Chups. `verification.coverage = 0.0`, các con số nêu trong câu trả lời đều bị đánh dấu `unsupported`, nên không có số liệu sai lọt ra ngoài.

**So sánh & Phân tích lỗi:** Hành động gate (`clarify` do thực thể mơ hồ) đúng hướng và trùng kết luận của groundtruth, đồng thời tầng verification chặn thành công mọi số liệu chưa được xác minh (an toàn, không hallucinate). Tuy nhiên **bộ resolver thực thể sai hoàn toàn phạm vi**: bỏ qua token phân biệt mạnh nhất trong câu hỏi ("Chupa Chups", "Perfetti Van Melle Vietnam") và chỉ khớp mờ theo từ chung "kẹo", nên trả về ứng viên sai thương hiệu/sai shop. Đây là lỗi retrieval/ranking trong bước `resolve_entity`, không phải lỗi ở tầng gate hay verification.

## **Testcase 2: Luồng chuẩn (Standard Flow - ID)**

- **Câu hỏi:** "Lượt bán sản phẩm kem dưỡng Glad2Glow Niacinamide (ID) dạo này có vẻ chậm lại, có phải do thay đổi giá không?"

**Groundtruth (Claude, dựa trên `data/processed/products_clean.csv`, snapshot 01–03/07/2026, shop Glad2Glow Official Store – ID):**
Cụm từ khớp mơ hồ với 5 listing "Pomegranate/…Niacinamide…Moisturizer". Giá (price_num) và `monthly_sold_value` qua 3 ngày:
- `26892712078` (100g): giá 100.000/100.000/100.000 IDR (không đổi); sold 1000/1000/1000 (không đổi)
- `19691541572` ("…Gel Pelembab…"): giá 43.900/43.900/41.900 (giảm nhẹ ngày 3); sold 1000/1000/1000 (không đổi)
- `56009621582` ("[JADI MEMBER]…"): giá 72.900 cả 3 ngày (không đổi); sold 253/274/277 (**tăng**, không giảm)
- `53308986174` ("[JADI MEMBER]…Serum"): giá 77.900 cả 3 ngày (không đổi); sold 387/409/425 (**tăng**)
- `48150998499` ("[KHUSUS MEMBER]…"): giá 100.000 cả 3 ngày (không đổi, không voucher/promo); sold 305/294/289 (**giảm ~5,2%** — SKU duy nhất có suy giảm thật)

Trong 5 ứng viên, chỉ 1 SKU có suy giảm thật, và giá của chính SKU đó **không hề đổi** suốt 3 ngày; 2 SKU khác còn tăng doanh số. **Đáp án đúng: Không, dữ liệu không ủng hộ giả thuyết "do thay đổi giá" — SKU có sold giảm lại có giá đứng yên; thực thể mơ hồ (5 SKU khớp tên), cần làm rõ SKU trước khi kết luận nguyên nhân.**

**Kết quả model Gladiators:** Nhận diện đúng `country=id`, đúng intent `sales_decline`. Nhưng gate `clarify (A-AMBIGUOUS)` gợi ý toàn sản phẩm thương hiệu **Cyeecare** ("[New Launch] Cyeecare 377 Brightening Essence Spray…", "Cyeecare 377 Glow Radiance Cream…") — sai hoàn toàn thương hiệu, dù "Glad2Glow" là token nguyên văn xuất hiện trong hàng trăm sản phẩm đúng shop. `verification.coverage = 0.0`, mọi số liệu bị chặn là `unsupported`.

**So sánh & Phân tích lỗi:** Cùng dạng lỗi như Testcase 1 nhưng nặng hơn: sai luôn cả thương hiệu/shop, không chỉ sai SKU trong đúng shop. Country routing hoạt động tốt (đúng "id"), nhưng tầng resolve-entity/candidate-retrieval cho macro `sales_decline` có vấn đề hệ thống — nhiều khả năng đang khớp theo few overlapping tokens chung chung (ví dụ "niacinamide"/"moisturizer" xuất hiện ở nhiều shop mỹ phẩm khác) mà không ưu tiên brand-token "Glad2Glow" xuất hiện literal trong entity_text. Tầng verification vẫn chặn hallucination hiệu quả.

## **Testcase 3: Bẫy Lỗi Dữ liệu Anomaly (Cực kỳ quan trọng)**

- **Câu hỏi:** "Tại sao tổng lượt bán lũy kế (history sold) của một số sản phẩm Nestlé lại bị tụt xuống vậy?"

**Groundtruth (Claude, dựa trên `data/processed/products_clean.csv`, shop "Nestlé Health Science" – VN):**
Đây là hiện tượng **có thật trong dữ liệu**: ít nhất 23 sản phẩm của shop Nestlé có `history_sold_value_num` (lượt bán lũy kế/lifetime) **giảm** giữa các snapshot 07-01→07-02→07-03, dù về bản chất đây phải là bộ đếm cộng dồn, không thể giảm theo thời gian thực. Ví dụ:
- `1759126901` NESCAFÉ VỊ NGUYÊN BẢN 20 gói: 10.000 → 6.000 → 10.000
- `24710759163` Collagen NESTLÉ VITAL PROTEINS 284G: 751 → 864 → 768
- `53306094941` Bộ 2 Lốc Sữa NUTREN JUNIOR 110ML: 652 → 656 → 139

**Đáp án đúng:** nguyên nhân hợp lý nhất là lỗi/nhiễu ở nguồn hiển thị "đã bán" của Shopee qua từng lần crawl (làm tròn/bucket không nhất quán, không phải bộ đếm lũy kế chính xác tuyệt đối) — **không phải** do khách trả hàng hàng loạt hay Nestlé "mất" đơn hàng đã bán. Đây là lỗi chất lượng dữ liệu snapshot cần cảnh báo (tương tự các case trong `data/processed/data_quality_issues.csv`), tuyệt đối không nên dùng `history_sold_value` để suy luận nguyên nhân kinh doanh.

**Kết quả model Gladiators:** Intent bị route thành `open_analytical` (không phải `sales_decline`). Gate `clarify (A-ANALYTICAL-AMBIGUOUS)` chỉ yêu cầu "Thiếu country để khóa scope VN hoặc ID" và dừng lại — không đưa ra bất kỳ giải thích nào về hiện tượng, dù shop Nestlé trong dataset chỉ tồn tại ở VN (có thể tự suy luận được).

**So sánh & Phân tích lỗi:** Model **không chạm được vào nội dung cốt lõi** của câu hỏi (giải thích anomaly dữ liệu). Đây là lỗi ở 2 lớp: (1) thiếu suy luận ngữ cảnh — chỉ có đúng 1 shop Nestlé và nó chỉ bán ở VN, lẽ ra hệ thống có thể tự khóa scope thay vì bắt người dùng chọn; (2) ngay cả khi có country, kiến trúc hiện tại dường như chưa có capability "giải thích anomaly lũy kế" (không thấy claim/evidence nào liên quan đến `history_sold` không đơn điệu trong response) — so với groundtruth, đây là khoảng trống năng lực (capability gap), không chỉ là lỗi ứng xử.

## **Testcase 4: Bẫy Nhân quả (Causal Trap)**

- **Câu hỏi:** "Có phải việc shop cắt mã voucher đã trực tiếp gây ra việc giảm doanh số của Bánh Socola Pie Oreo Vị Dâu không?"

**Groundtruth (Claude, item `17591957454`, shop Kinh Do Official Store – VN):**

| Ngày | voucher_code | price | monthly_sold |
|---|---|---|---|
| 07-01 | VCXFM30K107 (giảm 19.880đ) | 122.120 | 297 |
| 07-02 | *(không có voucher)* | 142.000 | 296 |
| 07-03 | VCXDPBLC0703 (giảm 14.200đ) | 127.800 | 300 |

Ngày cắt voucher (07-02), `monthly_sold` chỉ giảm 297→296 (**-0,3%**, nằm trong biên độ nhiễu), đồng thời giá tăng 16,3% (một yếu tố nhiễu/confound khác xảy ra cùng lúc). Sang ngày 07-03 khi voucher quay lại, `monthly_sold` còn **tăng lên 300** — cao hơn cả mức trước khi cắt voucher, mâu thuẫn với giả thuyết nhân quả đơn giản "cắt voucher → giảm doanh số". **Đáp án đúng: Không thể kết luận có quan hệ nhân quả trực tiếp** — biến động quá nhỏ để phân biệt với nhiễu, giá thay đổi đồng thời gây confound, và chỉ có 3 điểm dữ liệu (không đủ để suy luận nhân quả, chỉ là tương quan yếu và trái chiều ở ngày 3).

**Kết quả model Gladiators:** Intent bị route sai thành `promotion_effectiveness` (câu hỏi thực chất thuộc `sales_decline`/causal trap). Gate `clarify (A-MISSING-SLOT)`: "Thiếu thông tin: country" — chặn lại hoàn toàn, không đưa ra bất kỳ phân tích nhân quả nào, dù tên sản phẩm và shop đều là tiếng Việt/chỉ tồn tại ở VN trong dữ liệu.

**So sánh & Phân tích lỗi:** 0% nội dung trùng khớp với groundtruth. Hai lỗi rõ rệt: (1) **sai intent routing** (promotion_effectiveness thay vì sales_decline khiến pipeline không bao giờ chạm tới macro phân tích nhân quả giảm doanh số); (2) **không suy luận được country** từ ngữ cảnh rõ ràng (tên tiếng Việt, thương hiệu Kinh Đô). Đây là hành vi an toàn (fail-closed, không bịa kết luận nhân quả sai) nhưng recall gần như bằng 0 so với groundtruth.

## **Testcase 5: Bẫy Tồn kho (Stock-out Trap)**

- **Câu hỏi:** "Tháng này bánh Orion Chocopie bán chậm lại, có phải do hết hàng (sold out) không?"

**Groundtruth (Claude, shop Orion VN Official Store):** Toàn bộ 12 dòng snapshot của các SKU Chocopie (07-01→07-03) đều có `is_sold_out_bool = False` — **không SKU nào hết hàng**, giả thuyết bị bác bỏ trực tiếp bởi chính field dữ liệu. SKU giảm rõ nhất là `29492921661` "Combo 2 Hộp 12 Gói ChocoPie Giảm Đường (360g)": sold 1000→898→898 (giảm ~10,2% ngày 2 rồi đi ngang), trùng thời điểm đổi mã voucher (VCXFM30K107→237GIAM40K) và giá tăng nhẹ. **Đáp án đúng: Không, không phải do hết hàng — is_sold_out luôn False; nguyên nhân khả dĩ hơn (nếu có) liên quan tới thay đổi giá/voucher, không phải tồn kho.**

**Kết quả model Gladiators:** `entities: []`, `entity_text: null` — **không trích xuất được thực thể sản phẩm "Orion Chocopie" ở bất kỳ mức nào**. Intent = `open_analytical`. Gate `clarify (A-ANALYTICAL-AMBIGUOUS)` chỉ hỏi thiếu country, hoàn toàn không đề cập `is_sold_out` hay bất kỳ SKU nào.

**So sánh & Phân tích lỗi:** Đây là lỗi nặng nhất trong nhóm 10 testcase: NER/entity extraction bỏ sót hoàn toàn cụm "bánh Orion Chocopie" dù đây là brand+product token rõ ràng, không mơ hồ về mặt từ vựng (khác Testcase 1/2 vốn còn trích được entity nhưng resolve sai). Không có entity nghĩa là ngay cả khi user trả lời "VN" ở lượt sau, hệ thống vẫn chưa có gì để tra `is_sold_out` — bẫy tồn kho hoàn toàn không được kiểm tra.

## Testcase 6: Bẫy Dự đoán Tương lai (Forecasting Trap)

- **Câu hỏi:** "Với đà giảm doanh số như 3 ngày qua của sản phẩm Hộp bánh Cá Marine Boy Orion Vị Gà Bơ Sốt Tỏi, dự đoán tuần sau lượng bán của sản phẩm này sẽ giảm thêm bao nhiêu?”

**Groundtruth (Claude, item `26489730581`):** `monthly_sold_value`: 557 → 61 → 60 (07-01→07-02→07-03) — giảm mạnh ngày 2 (-89%) rồi gần như đi ngang ngày 3. Chỉ có 3 điểm dữ liệu (2 khoảng biến thiên), không đủ cơ sở thống kê để ước lượng xu hướng/seasonality đáng tin cậy cho tuần kế tiếp. **Đáp án đúng: hệ thống nên từ chối đưa ra con số dự báo định lượng, chỉ nên mô tả biến động đã quan sát và giải thích rõ vì sao không thể dự báo (mẫu quá nhỏ, không có mô hình time-series).**

**Kết quả model Gladiators:** Intent = `unsupported:forecast`. Gate `abstain (A-MISSING-FORECAST)`: "Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy… Vẫn mô tả được chênh lệch giữa các snapshot đã quan sát." Có gợi ý câu hỏi thay thế hợp lệ.

**So sánh & Phân tích lỗi:** **Khớp gần như hoàn toàn với groundtruth** — đây là testcase model xử lý tốt nhất trong nhóm sales_decline. Model từ chối dự báo đúng lý do (cỡ mẫu 3 snapshot, không đủ cho seasonality), không bịa số % giảm thêm, và gợi ý hướng hỏi thay thế khả thi. Không phát hiện lỗi sai ở testcase này.

## **Testcase 7: Bẫy Thực thể mơ hồ (Ambiguous Entity Trap)**

- **Câu hỏi:** "Vì sao doanh số sữa giảm?"

**Groundtruth (Claude):** "sữa" khớp 388 dòng trên toàn dataset, trải nhiều thương hiệu/nhóm sản phẩm (Nestlé, Milo, cà phê sữa Nescafé, kẹo sữa Bibica…) — quá rộng để xác định 1 sản phẩm cụ thể. **Đáp án đúng: cần làm rõ sản phẩm/thương hiệu/thị trường cụ thể trước khi trả lời; không nên tự chọn 1 sản phẩm để suy diễn.**

**Kết quả model Gladiators:** Gate `clarify (A-AMBIGUOUS)`, đưa ra 3 candidate hợp lý — đều thực sự chứa từ "sữa" trong tên: "Combo 2 Bánh Hura Deli Bibica…", "Cà phê sữa NESCAFÉ Signature…", "Combo 2 Kẹo Mềm Sumika Sữa Bibica 275g".

**So sánh & Phân tích lỗi:** **Khớp tốt với groundtruth** — không như Testcase 1/2/5, lần này candidate list đúng ngữ cảnh (đều chứa "sữa" thật trong tên sản phẩm), cho thấy resolver hoạt động ổn với từ khóa phổ biến/tần suất cao nhưng kém với brand-token hiếm hơn ("Chupa Chups", "Glad2Glow", "Orion Chocopie"). Không phát hiện lỗi sai nghiêm trọng.

## **Testcase 8: Bẫy Yêu cầu Dữ liệu Ngoài (Out-of-Scope Trap)**

- **Câu hỏi:** "Lượt bán của bánh quy Kinh Đô giảm, điều này làm biên lợi nhuận (profit margin) của shop giảm bao nhiêu phần trăm?"

**Groundtruth (Claude):** `products_clean.csv` (80 cột) không có bất kỳ trường giá vốn, phí sàn hay chi phí vận hành nào → **không thể tính được profit margin từ dataset này**, đây là yêu cầu ngoài phạm vi dữ liệu. Đồng thời "bánh quy Kinh Đô" mơ hồ (nhiều SKU: AFC, Cosy, Oreo… cùng thuộc Kinh Do Official Store). **Đáp án đúng: từ chối phần profit margin vì thiếu dữ liệu chi phí, đồng thời làm rõ SKU bánh quy cụ thể cho phần "lượt bán giảm".**

**Kết quả model Gladiators:** Hệ thống tách câu hỏi thành `sub_requests`: sr1 (lượt bán giảm) → `answerable=true`; sr2 (profit margin) → `answerable=false, capability="profit"`. Trả lời: *"Chưa trả lời được… dieu nay lam bien loi nhuan profit margin cua shop giam bao nhieu phan tram: Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận."* Đồng thời vẫn gate `clarify` cho sr1 với 3 candidate SKU bánh quy Kinh Đô hợp lý (AFC Lúa Mì, Socola Pie Oreo Dâu, Bánh Quy Oreo Kem Dâu/Vani/Sôcôla).

**So sánh & Phân tích lỗi:** **Khớp hoàn toàn với groundtruth**, là câu trả lời tốt nhất trong 10 testcase. Model tự tách sub-request, đúng lý do từ chối phần out-of-scope, và vẫn xử lý phần ambiguity ở sr1 một cách hợp lý. Không phát hiện lỗi sai.

## **Testcase 9: Bẫy Double Count Danh mục (Kệ hàng)**

- **Câu hỏi:** "Sản phẩm Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Rau/Lúa Mì/Gà Sả Tắc 172g đang thuộc 2 danh mục (category ID 100629 và 100787). Hãy tính tổng doanh số giảm của sản phẩm này trên cả 2 danh mục đó cộng lại."

**Groundtruth (Claude, item `24779109496`):** Đây là **một listing duy nhất**, `catid` chính = 100629, và `global_catids = [100629, 100646, 100787]` — đúng là xuất hiện ở cả 100629 và 100787 (cộng thêm 100646) nhưng chỉ vì được gắn vào nhiều "kệ hàng" (shelf) khác nhau trên cùng nền tảng, **không phải 2 sản phẩm khác nhau**. `monthly_sold_value` của SKU này **không đổi suốt 3 ngày: 101 → 101 → 101**. **Đáp án đúng:** (1) tiền đề "có giảm" sai — sold phẳng tuyệt đối; (2) dù có giảm thật, tuyệt đối không được cộng dồn qua 2 category vì đó là double-count trên cùng một SKU/doanh số.

**Kết quả model Gladiators:** Route đúng `sales_decline`, tách được `category_id=100629 (exact)` và tên sản phẩm là 2 entity riêng biệt. Gate chặn với `A22-ALIGN-ENTITY`: *"Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity."* → từ chối tính toán.

**So sánh & Phân tích lỗi:** **Đúng về mặt hành động an toàn** (không cộng dồn sai như bẫy yêu cầu), tránh được lỗi double-count — phần này khớp tinh thần groundtruth. Nhưng **thiếu về nội dung**: model không giải thích được *lý do bản chất* (đây là 1 SKU đa danh mục, không phải 2 sản phẩm) và không hề trả về con số thực tế (`monthly_sold` phẳng 101/101/101, tức không có mức giảm nào để cộng) — nên câu trả lời tuy an toàn nhưng không đầy đủ và không giúp người dùng hiểu bẫy nằm ở đâu, khác với groundtruth vốn chỉ thẳng ra cả nguyên nhân lẫn số liệu.

## **Testcase 10: Luồng giải thích thay đổi ảo (Monthly Window Trap)**

- **Câu hỏi:** "Tôi thấy lượng bán hiển thị (monthly sold) của sản phẩm Hộp Bánh Bống Bang Family Pack 20 Gói (580g) giảm từ 351 xuống 350, có phải ngày hôm qua không ai mua hàng không?"

**Groundtruth (Claude, item `24391148394`):** `monthly_sold_value`: 356 (07-01) → 351 (07-02) → 350 (07-03), đúng như câu hỏi mô tả. Mức giảm 351→350 chỉ là **-1 đơn vị (~-0,28%)**, nằm trong biên độ nhiễu của `monthly_sold_value` — theo README của repo, đây là **"a recent-window proxy with an unknown exact window"**, không phải bộ đếm số đơn bán trong đúng 1 ngày. Đồng thời giá lại **tăng** (130.500→132.000) đúng ngày đó với voucher đổi khác — không có dấu hiệu "không ai mua". **Đáp án đúng: Không, không thể suy ra "hôm qua không ai mua hàng" từ chênh lệch -1 của một chỉ số cửa sổ trượt gần đúng; đây là hiểu sai bản chất metric.**

**Kết quả model Gladiators:** Intent = `open_analytical`. Gate `clarify (A-ANALYTICAL-AMBIGUOUS)`: chỉ hỏi "Thiếu country để khóa scope VN hoặc ID", không đề cập gì đến bản chất rolling-window của `monthly_sold`.

**So sánh & Phân tích lỗi:** 0% nội dung trùng khớp với groundtruth — model không chạm được vào bản chất "bẫy" của câu hỏi (giải thích `monthly_sold_value` là proxy cửa sổ trượt, không phải bộ đếm theo ngày), dù đây chính là nội dung cốt lõi cần truyền tải. Giống Testcase 3/4/5, hệ thống dừng lại ở bước hỏi country và chưa thể hiện có capability giải thích ngữ nghĩa của metric.

## Tổng kết đánh giá Testcase 1–10 (nhóm `sales_decline`)

**Phương pháp:** Groundtruth do Claude tạo trực tiếp từ `data/processed/products_clean.csv` (snapshot thực tế 01–03/07/2026, VN+ID). Model được đánh giá là "kiến trúc demo mới nhất của Gladiators" chạy qua `PYTHONPATH=src python -m gladiators.cli "<câu hỏi>" --json`, provider `offline` (certified-macro / deterministic pipeline — không dùng LLM provider vì repo chưa cấu hình `.env`/API key nào; đây là chế độ mặc định của CLI theo README).

**Kết quả tổng quan:**

| TC | Model có khớp nội dung groundtruth? | Ghi chú |
|---|---|---|
| 1 | Một phần | Gate đúng hướng (clarify) nhưng candidate sai thương hiệu/shop (Bibica thay vì Chupa Chups/Perfetti) |
| 2 | Một phần | Gate đúng hướng, country đúng, nhưng candidate sai hẳn thương hiệu (Cyeecare thay vì Glad2Glow) |
| 3 | Không | Không giải thích được anomaly `history_sold`; chỉ dừng ở hỏi country |
| 4 | Không | Sai intent routing (promotion_effectiveness thay vì sales_decline); không phân tích nhân quả |
| 5 | Không | Entity extraction thất bại hoàn toàn ("Orion Chocopie" không được nhận diện) |
| 6 | **Có** | Từ chối dự báo đúng lý do thống kê, khớp gần như hoàn toàn |
| 7 | **Có** | Candidate ambiguity hợp lý, đúng ngữ cảnh |
| 8 | **Có** | Tách sub-request đúng, từ chối phần profit margin đúng lý do, xử lý ambiguity tốt |
| 9 | Một phần | Hành động an toàn (không double-count) nhưng thiếu giải thích bản chất + số liệu thực |
| 10 | Không | Không giải thích bản chất rolling-window của `monthly_sold`; chỉ dừng ở hỏi country |

**Phân tích lỗi sai chính:**

1. **Lỗi resolver/entity-retrieval sai phạm vi (TC1, TC2):** Khi thực thể được trích xuất nhưng mơ hồ, danh sách candidate do `resolve_entity` trả về đôi khi sai cả thương hiệu/shop (Bibica thay Chupa Chups, Cyeecare thay Glad2Glow) dù token thương hiệu xuất hiện literal trong câu hỏi. Nhiều khả năng bước matching đang ưu tiên từ khóa chung ("kẹo", "moisturizer/niacinamide") hơn là brand-token đặc trưng. Ngược lại, với từ khóa phổ biến/tần suất cao như "sữa" (TC7) hay tên thương hiệu đơn giản như "Kinh Đô" (TC8), candidate list lại đúng ngữ cảnh — cho thấy lỗi không đồng đều, phụ thuộc cách token hoá tên sản phẩm.
2. **Lỗi NER bỏ sót thực thể hoàn toàn (TC5):** "bánh Orion Chocopie" — một brand+product rõ ràng — không được trích xuất (`entities: []`). Đây là lỗi nặng nhất vì pipeline mất luôn khả năng tra `is_sold_out` để bác bỏ bẫy tồn kho.
3. **Sai intent routing (TC4):** Câu hỏi nhân quả về giảm doanh số (sales_decline) bị route thành `promotion_effectiveness`, khiến hệ thống không bao giờ chạm tới macro phân tích đúng.
4. **Thiếu suy luận country từ ngữ cảnh (TC3, TC4, TC5, TC10):** Nhiều câu hỏi có brand/tên sản phẩm chỉ tồn tại ở một quốc gia trong dataset (Nestlé, Kinh Đô, Orion, Bống Bang đều chỉ có ở VN) nhưng hệ thống vẫn chặn lại đòi `country` thay vì tự suy luận, khiến các testcase này không bao giờ đi xa hơn bước gate để lộ ra nội dung cốt lõi (giải thích anomaly, bản chất rolling-window…).
5. **Khoảng trống năng lực (capability gap), không chỉ lỗi ứng xử (TC3, TC10):** Ngay cả giả sử vượt qua được bước hỏi country, không có bằng chứng trong response cho thấy hệ thống có khả năng giải thích anomaly `history_sold` không đơn điệu (TC3) hay bản chất "recent-window proxy" của `monthly_sold_value` (TC10) — đây là các mảng kiến thức mà groundtruth cần nhưng kiến trúc hiện tại (certified macro `sales_decline` v1.0) dường như chưa phủ.

**Điểm mạnh đã quan sát được:**
- **Không hallucinate số liệu:** ở mọi testcase có `verification` object, các con số chưa xác minh đều bị đánh dấu `unsupported`/`coverage=0.0` và bị chặn không lộ ra câu trả lời cuối — hành vi fail-closed nhất quán.
- **Từ chối dự báo đúng lý do (TC6)** và **từ chối out-of-scope đúng lý do (TC8, phần profit margin)** — hai năng lực này hoạt động đúng như thiết kế và khớp hoàn toàn với groundtruth.
- **Chặn double-count an toàn (TC9)** dù chưa giải thích được bản chất.

**Kết luận:** Ở nhóm `sales_decline` (TC1–10), kiến trúc offline hiện tại có **precision cao nhưng recall thấp** — gần như không bao giờ đưa ra kết luận sai/số liệu bịa, nhưng phần lớn (6/10) dừng lại ở bước "clarify/abstain" mà không cung cấp được nội dung phân tích sâu như groundtruth, và trong số các lần "clarify", 2/10 lần đưa ra candidate sai hẳn phạm vi. Ưu tiên khắc phục nên là: (a) cải thiện ranking trong `resolve_entity` để ưu tiên brand-token hiếm/đặc trưng; (b) vá lỗi NER bỏ sót entity rõ ràng như TC5; (c) sửa intent routing cho câu hỏi nhân quả (TC4); (d) bổ sung suy luận country từ brand khi chỉ có 1 shop/quốc gia khớp; (e) mở rộng capability giải thích anomaly dữ liệu và ngữ nghĩa metric (`history_sold` không đơn điệu, `monthly_sold` là rolling proxy).

# Nhóm `similar_product`

## **Testcase 11: Luồng chuẩn (Standard Flow - VN)**

- **Câu hỏi:** "Tìm cho tôi top 5 sản phẩm tương tự với bánh quy Kenju Richy 192g để xem đối thủ đang bán giá bao nhiêu?"

**Groundtruth (Claude, `data/processed/products_clean.csv`):**
Cụm "bánh quy Kenju Richy 192g" khớp mơ hồ: **46 listing** chứa token "kenju", trong đó **10 listing** có "192g" trong tên, tất cả đều thuộc **cùng một doanh nghiệp Richy** (Chi Nhánh Miền Bắc: 4, Chi nhánh Miền Nam: 6). Hai ứng viên sát nghĩa nhất:
- `20085751465` "Bánh Quy Kenju Richy Vị Rau Củ - Túi 192g" — 45.000đ, sold 441
- `29286722160` "Bánh Quy Kenju Richy Vị Tôm Giòn Rụm Túi 192g" — 47.000đ, sold 554

Nếu bind `20085751465` và chạy đúng similarity, top-5 hàng xóm cùng platform category (catid 100629) là: `[BAO BÌ MỚI] Bánh quy Kenju Richy vị rau củ/tôm túi 192g` (0.936), `Combo 3 túi bánh quy mỏng giòn Kenju Richy 192g` (0.901), `Combo 3 Túi Bánh Kenju Rau Củ vị Tôm 192g` (0.870), `Combo 3 Bịch Kenju Gà Nướng Phô Mai` (0.855), `Bánh quy que chấm Wismo ly` (0.855) — **5/5 đều là listing của chính Richy**, không có listing nào của Kinh Đô/Bibica/Orion dù cả 6 shop đều nằm chung catid 100629.

**Đáp án đúng:** (1) cần làm rõ SKU (10 listing 192g); (2) trả top-5 **kèm giá** vì câu hỏi hỏi giá; (3) cảnh báo bẫy: "tương tự theo tiêu đề" không đồng nghĩa "đối thủ cạnh tranh" — toàn bộ top-5 là hàng của cùng nhà sản xuất, nên con số giá thu được không phản ánh giá đối thủ.

**Kết quả model Gladiators (offline/certified-macro):** `intent=similar_product` (đúng), nhưng `entity_text` bị bắt trọn 14 token: `"tuong tu voi banh quy kenju richy 192g de xem doi thu dang ban gia bao nhieu"`. `resolve()` trả 20 candidate **toàn bộ là "[Quà tặng không bán] …"** (Gấu trúc ống tre, Bộ mền gối chim cánh cụt, Chảo Chống Dính…) hòa điểm đúng 0.8550. Token-filter trong `classify()` loại sạch 20/20 → `invalid_extraction` → gate `abstain (A-ENTITY-NOT-FOUND)`. **0 evidence.**

**So sánh & Phân tích lỗi:** 0% nội dung trùng groundtruth. Nặng hơn TC1/TC2: ở TC1/TC2 candidate còn sai-nhưng-có, ở đây pool top-20 sạch bóng sản phẩm đúng nên hệ thống kết luận "không tìm thấy" cho một sản phẩm có **46 listing** trong dataset — một false-negative rõ ràng, không phải hành vi an toàn.

## **Testcase 12: Luồng chuẩn (Standard Flow - ID)**

- **Câu hỏi:** "Có sản phẩm nào bán ở Indo là đối thủ cạnh tranh trực tiếp của serum Glad2Glow không?"

**Groundtruth (Claude):** Glad2Glow có **215 listing, 100% ở ID**, trong đó **83 listing** chứa "serum". Đối thủ thật ở ID cũng bán serum: Cyeecare 33, lavojoy 16, Mooi Pure Glow 11, He-Ji 6, Scora 6, Prettywell 5, ZOICY 1 — **78 listing của 7 shop khác**. Kiểm chứng bằng chính `similar_products()` khi bind thẳng `21429166155` (Glad2Glow Centella Salicylic Acid Power Acne Serum): top-5 trả về **5/5 là Cyeecare** (Peeling Solution Serum AHA, AHA BHA PHA LHA Peeling Solution Serum…). **Đáp án đúng: Có** — liệt kê 5 đối thủ kèm giá, ghi rõ chỉ so theo tiêu đề trong cùng platform category, không khẳng định cùng công thức.

**Kết quả model Gladiators:** `intent=open_analytical` (**không** phải `similar_product`), `entities: []`, `entity_text=null`, country nhận đúng `id`. Gate `abstain (A19-PLAN)`: "Không có semantic planner provider cho câu hỏi ngoài certified template." **0 evidence.**

**So sánh & Phân tích lỗi:** 0% nội dung. Đây là ca đau nhất trong nhóm vì **năng lực đã có sẵn và chạy đúng** (đã verify: bind tay ra đúng 5 đối thủ Cyeecare) nhưng câu hỏi không bao giờ được route tới nó — cụm "đối thủ cạnh tranh trực tiếp" hoàn toàn vắng mặt trong vocabulary định tuyến `similar_product`, dù `ultimate solution.md §4.2` ghi rõ MUST "Competitor cue không hỏi giá ngoài sàn đi `similar_product`".

## **Testcase 13: Bẫy Xuyên biên giới & Tỷ giá (Cross-Country / FX Trap)**

- **Câu hỏi:** "Sản phẩm sữa Milo bán ở VN có sản phẩm nào tương đương bên thị trường Indonesia không, giá bên nào rẻ hơn?"

**Groundtruth (Claude):** Milo có **20 listing, 100% ở VN**, đều thuộc shop "Nestlé Chính hãng", catid 100629. Phía Indonesia: **475 listing / 10 shop**, trong đó **98,3% nằm ở catid 100630 (mỹ phẩm)**; đúng **1 listing** ở catid thực phẩm 100629 là "FLASH SALE MOOI Collagen Drink with Zizania"; **0 listing** nào chứa susu/milo/malt. **Đáp án đúng: Không có sản phẩm tương đương ở Indonesia — và lý do gốc không phải tỷ giá mà là phạm vi dữ liệu: nửa ID của dataset gần như thuần mỹ phẩm, không có ngành hàng đồ uống/thực phẩm để so.** Vế "giá bên nào rẻ hơn" hỏng kép: (a) không có đối tượng để so; (b) kể cả có thì VND và IDR không quy đổi được vì dataset không chứa tỷ giá.

**Kết quả model Gladiators:** `intent=similar_product`, `entity_text='sua milo ban'`, `countries=['vn','id']`. Gate `clarify (A16-CROSS-CURRENCY)`: "Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: contract cross-tier derived value T-8c chưa được phê duyệt."

**So sánh & Phân tích lỗi:** **Khớp một nửa.** Model chặn đúng lý do (b) và đúng bất biến "không trộn VND/IDR" (`ultimate solution.md §1.2`) — đây là hành vi tốt. Nhưng gate ở phase 1 short-circuit trước khi bất kỳ tool nào chạy, nên hệ thống **không bao giờ phát hiện lý do (a)** vốn mạnh hơn và hữu ích hơn cho người dùng: không tồn tại sản phẩm tương đương. Người dùng nhận được "không so tiền được" thay vì "không có gì để so".

## **Testcase 14: Bẫy Hình ảnh & Bao bì (Visual Feature Trap)**

- **Câu hỏi:** "Tìm các sản phẩm kẹo có bao bì màu đỏ hoặc thiết kế giống với gói kẹo Alpenliebe hương dâu này."

**Groundtruth (Claude):** Alpenliebe có **5 listing**, đều thuộc shop Perfetti Van Melle Vietnam. **Không có listing nào là "gói kẹo Alpenliebe hương dâu"**; gần nhất là `20848965969` "COMBO Kẹo cứng Alpenliebe đậm vị sữa béo hương Caramel, **Dâu sữa**, Trà sữa và kẹo cứng có nhân Xoài muối ớt" — một combo nhiều vị, không phải gói kẹo hương dâu đơn lẻ. Trường hình ảnh có trong dataset: `image_url`, `images`, `image_overlay`, `image_overlay_hash`, `images_count` — **không có bất kỳ trường màu sắc hay mô tả thiết kế nào**; `image_overlay` là nhãn chiến dịch dạng text (ví dụ `FSS+Promo_Xtra+Pilih_Lokal_New`), không mô tả bao bì. **Đáp án đúng: từ chối phần "bao bì màu đỏ / thiết kế giống" vì không có embedding ảnh hay nhãn thị giác được chứng nhận; chỉ có thể xếp hạng tương đồng theo tiêu đề — đồng thời nêu rõ thực thể được hỏi không tồn tại đúng như mô tả.**

**Kết quả model Gladiators:** `intent=similar_product` (không phải `unsupported:image_similarity`). Gate `clarify (A-AMBIGUOUS)` với 3 candidate: **"Dầu Hào MAGGI® Nấm Hương Chai 350g"; "Combo 2 Dầu Hào MAGGI® Nấm Hương 820g/chai"; "Combo 2 Dầu Hào MAGGI Nấm Hương 350g/chai"** — nước chấm, không phải kẹo. `verification.coverage = 0.0`.

**So sánh & Phân tích lỗi:** Sai hoàn toàn, và sai theo một cơ chế đã được cảnh báo trước mà chưa vá: sau `normalize_text()` (NFD-strip dấu), **"dâu" (strawberry) và "Dầu" (oil) đều thành `"dau"`**, còn "hương" (flavour) trùng "Nấm Hương" (shiitake) → overlap giả `{dau, huong}` đưa dầu hào lên top. Toàn catalog có **60 tên** chứa token `dau` sau chuẩn hoá. Đây chính là homograph collision đã ghi nhận ở `040826.md §5` với cặp "dẻo"/"đeo" — lúc đó không đổi kết quả cuối nên được xếp "chưa cần fix vòng 1"; ở TC14 nó **đã trực tiếp gây sai kết quả**. Ngoài ra hệ thống không nhận ra đây là câu hỏi thị giác nên bỏ mất câu trả lời đúng duy nhất (từ chối vì thiếu capability ảnh).

## **Testcase 15: Bẫy Nhầm lẫn Danh mục (Shop Category vs. Platform Category Trap)**

- **Câu hỏi:** "Hãy tìm các sản phẩm tương tự nằm trong cùng kệ '18VCX+SSCBundle[1.7]' với sản phẩm Combo 2 Hộp Bánh Quy Dinh Dưỡng AFC Vị Lúa Mì 172g của shop Kinh Do Official Store."

**Groundtruth (Claude):** `'18VCX+SSCBundle[1.7]'` **không phải kệ hàng (shop shelf)**. Quét toàn bộ 5 artifact cho thấy chuỗi này chỉ tồn tại ở đúng một cột: **`products_clean.image_overlay`** — nhãn banner chiến dịch của sàn. Bằng chứng số:
- `image_overlay == '18VCX+SSCBundle[1.7]'`: **173 listing, 100% VN, chỉ tồn tại ở ngày 2026-07-01**, trải **8 shop khác nhau** (Bibica 62, Richy MN 35, Richy MB 29, Orion 16, Nestlé 15, Perfetti 8, Kinh Đô 7, Nestlé Health Science 1), catid 100629 (172) + 100632 (1).
- `category_list_clean.csv`, `category_platform_clean.csv`, `product_categories_clean.csv`, `shop_info_clean.csv`: **0 ô** chứa chuỗi này.
- Kệ hàng **thật** của Kinh Do Official Store (`shop_id=140360136`) trong `category_list_clean`: `THÙNG BÁNH`, `Kinh Đô Tết 2026`, `Tất cả sản phẩm`, `AFC`, `RITZ & SLIDE`, `OREO`, `COSY`, `LU`, `SOLITE`.
- Sản phẩm được hỏi `26963395898`: `image_overlay` đổi theo ngày — 07-01 = `18VCX+SSCBundle[1.7]`, 07-02 và 07-03 = `30VCX[26.6-9.7.2026]`.

**Đáp án đúng: bác tiền đề** — đó là overlay chiến dịch của sàn tại một ngày, không phải kệ hàng nội bộ của shop; nó cắt ngang 8 shop nên "cùng kệ" là hiểu sai. `§4.6` còn cấm nối shop shelf với platform taxonomy. Nếu vẫn muốn liệt kê thì phải nói rõ đó là 173 listing cùng nhãn chiến dịch ngày 07-01, không phải quan hệ danh mục.

**Kết quả model Gladiators:** `entity_text` bắt trọn **25 token** cả câu. Gate `clarify (A-AMBIGUOUS)` với candidate: `Combo 4 Hộp Bánh Quy Dinh Dưỡng AFC Vị Lúa Mì 172g` (VN, 0.882) rồi **`[BELI 7 DAPAT 9!] Glad2Glow Cerah Glowing Outing Bundle`, `[New]Glad2Glow Glycolic Acid Facial Wash 70ml`** (ID, mỹ phẩm). Toàn pool 20 candidate: **19 ID / 1 VN**. `coverage = 0.0`.

**So sánh & Phân tích lỗi:** Hai lỗi chồng nhau. (1) Không hề chạm tới bẫy: model không phân biệt được overlay chiến dịch với kệ hàng, cũng không bác tiền đề. (2) Lộ ra một lỗi hệ thống **mới, chưa ghi nhận ở TC1–TC10**: `resolve()` không hề khoá `country_code`, nên với câu hỏi tiếng Việt về một shop VN, **95% pool ứng viên là sản phẩm mỹ phẩm Indonesia**. Candidate top-1 cũng sai listing ("Combo **4** Hộp" thay vì "Combo **2** Hộp" được hỏi).

## **Testcase 16: Bẫy Thực thể quá rộng (Ambiguity Trap)**

- **Câu hỏi:** "Tìm cho tôi đối thủ cạnh tranh của bánh quy."

**Groundtruth (Claude):** "bánh quy" khớp **56 listing** (58 nếu đếm theo token `{banh, quy}`) trải **6 shop VN** — Kinh Do 19, Richy MN 16, Richy MB 10, Bibica 9, Hải Hà 1, Orion 1 — **toàn bộ nằm trong đúng một catid: 100629**. **Đáp án đúng: quá rộng, phải hỏi lại sản phẩm/thương hiệu cụ thể.** Thêm một tầng nữa: "đối thủ cạnh tranh của **một danh mục**" là câu hỏi sai hình dạng — macro `similar_product` bind **một listing**, không bind được danh mục; nếu muốn so cả nhóm thì đó là câu hỏi phân tích khác.

**Kết quả model Gladiators:** `intent=open_analytical`, `entities: []`. Gate `clarify (A-ANALYTICAL-AMBIGUITY)`: "Thiếu country để khóa scope VN hoặc ID."

**So sánh & Phân tích lỗi:** Hành động (clarify) đúng loại nhưng **hỏi sai thứ**. Vấn đề thật là thực thể quá rộng (56 listing), không phải thiếu country — và trong dataset "bánh quy" chỉ tồn tại ở VN nên country vốn suy ra được. Cùng gốc với TC12/TC19: cụm "đối thủ cạnh tranh" không được nhận là competitor cue nên rơi xuống `open_analytical`, nơi thông điệp mặc định là hỏi country.

## **Testcase 17: Bẫy Khẳng định "Cùng 1 sản phẩm" (Same-Product Claim Trap)**

- **Câu hỏi:** "Sản phẩm mã 25078119874 và 25178062720 của shop Orion VN Official Store có cùng thương hiệu ORION, cùng danh mục (catid 100629) và cùng chiến dịch khuyến mãi (seller_flag), tên sản phẩm cũng có cấu trúc tương tự. Liệu đây có chắc chắn là cùng một sản phẩm bị đăng tách ra để tránh so sánh giá không?"

**Groundtruth (Claude):** **Không — đây là hai sản phẩm khác nhau**, và tiền đề của câu hỏi đúng nhưng không đủ để kết luận:

| Trường | `25078119874` | `25178062720` |
|---|---|---|
| Tên | Combo 3 túi **Bánh gạo nướng An ORION vị Chà Bông** 145,6G | Combo 3 Túi 5 gói **bánh ăn sáng Orion C'est Bon sợi thịt gà sốt kem phô mai** 101,5G/Túi |
| `global_catids` | `[100629, **100646**, **100787**]` | `[100629, **100654**, **100858**]` |
| `price_num` (07-01→03) | 100.620 → 117.000 → 105.300 | 79.200 → 90.000 → 81.000 |
| `monthly_sold` | 2.000 (cả 3 ngày) | 3.000 (cả 3 ngày) |
| `history_sold` | 10.000 | 8.000 |
| `liked_count` | 286 → 286 → 287 | 243 → 243 → 245 |
| `rating` | 4.9634 | 4.9116 |
| `images_count` | 5 | 6 |

Ba dấu hiệu người hỏi nêu ra đều là **thuộc tính có độ phân giải thấp**: `brand=ORION` áp cho toàn shop; `catid=100629` là **level-1** dùng chung cho gần như mọi listing bánh kẹo VN (600/682 listing VN); `seller_flag=["OFFICIAL_SHOP"]` là nhãn shop chính hãng, không phải chiến dịch. Ngay khi đọc xuống **level-2/level-3 của `global_catids`** thì hai listing tách hẳn nhau (100646/100787 vs 100654/100858) — đó là bằng chứng phủ định trực tiếp và mạnh nhất.

**Đáp án đúng: Không, không phải cùng một sản phẩm.** Hai sản phẩm khác dòng (bánh gạo vs bánh ăn sáng), khác nhánh danh mục sâu, khác giá, khác lượt bán lũy kế, khác rating/liked/số ảnh. Đồng thời phải nói rõ: dataset **không có** trường nào cho phép khẳng định ý định "đăng tách để tránh so giá" — đó là suy luận về động cơ, ngoài phạm vi dữ liệu.

**Kết quả model Gladiators:** `intent=similar_product`, trích đúng 3 entity (`item_id:25078119874`, `item_id:25178062720`, `category_id:100629`), country đúng `vn`. Gate `clarify (A22-ALIGN-ENTITY)`: "Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity." **0 evidence.**

**So sánh & Phân tích lỗi:** 0% nội dung. Khác TC9 (nơi guard chặn **nhầm** một qualifier), ở đây guard chặn **đúng theo thiết kế** — câu hỏi thật sự nêu hai sản phẩm và macro `similar_product` thật sự chỉ bind được một. Vấn đề vì thế không phải lỗi guard mà là **khoảng trống năng lực**: kiến trúc chưa có macro nào so sánh hai listing đã biết mã, dù toàn bộ dữ liệu cần thiết đều nằm sẵn trong `products_clean.csv` và không cần một phép tính mới nào.

## **Testcase 18: Bẫy Tìm kiếm SKU / Biến thể (SKU-level Trap)**

- **Câu hỏi:** "Tìm cho tôi các sản phẩm tương tự có bán kích cỡ 'Hộp 279g' giống y hệt như biến thể của sản phẩm Bánh quy Richy KenJu giòn kem dẻo hương vị Nhật (mã 21658340202)."

**Groundtruth (Claude):** Listing `21658340202` có `tier_variation_name='Khối lượng'` và `tier_variation_options = ["Túi 186gr (12 bánh)", "Hộp 279gr (18 bánh)", "Combo 2 hộp 279g", "combo 2 túi 186g"]` — xác nhận biến thể 279g tồn tại. Trong dataset có **8 listing** khai báo option chứa "279" (6 listing khác cũng có "279" ngay trong tên):

| item_id | shop | tier options | giá listing |
|---|---|---|---|
| `14158683593` | Richy MB | `["2 Hộp 279g", "3 hộp 279g"]` | 121.440 |
| `25907552758` | Richy MB | `["2 Hộp 279g", "3 Hộp 279g"]` | 121.440 |
| `21658340202` | Richy MN | `[…, "Hộp 279gr (18 bánh)", "Combo 2 hộp 279g", …]` | 44.000 |
| `23044095031` | Richy MN | `["2 gói 186g", "2 hộp 279g", …]` | 79.200 |
| `22759887263` | Richy MN | `["Combo 3 túi", "2 Hộp 279g"]` | 118.976 |
| `22462828294` | Richy MN | `[…, "mix vị kenju 279g", "2 Hộp 279g"]` | 113.520 |
| `42500556873` | Richy MN | `[…, "2 Hộp 279g", …]` | 117.040 |
| `56210343716` | Richy MN | `["combo 1- kenju 186g", "Combo 2-kenju 279g"]` | 187.050 |

**Đáp án đúng — trả lời được một nửa, từ chối một nửa:** phần "tìm listing cũng bán cỡ 279g" **có dữ liệu và trả lời được** (8 listing kèm giá cấp listing); phần suy ra doanh số/giá **riêng cho biến thể 279g** phải từ chối vì `monthly_sold`/`history_sold`/`price` đều ở cấp listing, dataset không phân bổ theo biến thể.

**Kết quả model Gladiators:** `intent=unsupported:sku`, `entities: []` (mã `21658340202` bị bỏ luôn). Gate `abstain (A-MISSING-SKU)`: "Dataset không có sku_id/model_id; đơn vị nhỏ nhất là product listing. tier_variation chỉ mô tả lựa chọn hiển thị, không phân bổ doanh số theo biến thể."

**So sánh & Phân tích lỗi:** Nội dung câu từ chối **hoàn toàn chính xác về mặt kỹ thuật** — và đúng chữ nghĩa đến mức tự phủ định: câu trả lời tự nói "tier_variation mô tả lựa chọn hiển thị", mà câu hỏi chính là hỏi lựa chọn hiển thị. Đây là **từ chối quá tay (over-refusal)**: một keyword "biến thể" nuốt trọn câu hỏi, kể cả phần hoàn toàn nằm trong dữ liệu. Đối chiếu TC8 — nơi cơ chế `sub_requests` tách đúng phần trả lời được và phần out-of-scope — cho thấy cơ chế cần thiết đã tồn tại nhưng không kích hoạt ở đây.

## **Testcase 19: Bẫy Outlier Giá "Khủng" (Sentinel Price Trap)**

- **Câu hỏi:** *"*Tìm các đối thủ cạnh tranh có cùng mức giá ± 20% với sản phẩm mã 56061511146 – Quà tặng không bán (Quạt mini cầm tay).*" (Giá trị sentinel: 410.000đ)*

**Groundtruth (Claude):**
- `56061511146` "[QUÀ TẶNG KHÔNG BÁN] QUẠT MINI CẦM TAY…", shop Richy - Chi nhánh Miền Nam. Giá **410.000 (07-01) → 400.890 (07-02) → 400.890 (07-03)**; `price_original` = 500.000 cả 3 ngày; `discount_percent` 18% → 20% → 20%. **Con số 410.000đ trong câu hỏi chỉ đúng ở đúng 1/3 snapshot.**
- `catid_num = 100013` (`global_catids = [100013, 100075, 100277]`) — **đồ gia dụng/điện, không phải bánh kẹo**. Toàn dataset chỉ có **2 listing** ở catid này (listing còn lại là "[Quà tặng không bán] Quạt kẹp mini NUTREN JUNIOR" của Nestlé Health Science).
- **410.000đ là giá placeholder, không phải giá thị trường:** đúng **13 listing VN** có giá chính xác 410.000, và **100% trong số đó là "quà tặng không bán"**. Rộng hơn: 77 listing quà tặng VN dồn vào 3 mốc giá lặp — 372.600đ (26 listing), 410.000đ (13), 805.100đ (10) = 49/77.
- Band ±20% (328.000–492.000đ) chứa **81 listing VN**, trải **11 catid khác nhau**, trong đó **48/81 cũng là hàng quà tặng không bán**; chỉ **2** listing cùng catid 100013.

**Đáp án đúng: từ chối phép so band ±20%** vì giá neo là giá placeholder của hàng tặng kèm, không phải giá bán thật → mọi "đối thủ cùng tầm giá" suy ra từ nó đều vô nghĩa (bằng chứng: 48/81 kết quả trong band cũng là hàng tặng, tức band chủ yếu bắt được các placeholder khác). Đồng thời sửa lại tiền đề: giá hiện tại là 400.890đ, không phải 410.000đ.

**Kết quả model Gladiators:** `intent=open_analytical`, trích được `item_id:56061511146`. Gate `clarify (A-ANALYTICAL-AMBIGUITY)`: "Thiếu country cho metric tiền tệ; không được trộn VND và IDR."

**So sánh & Phân tích lỗi:** 0% nội dung. Model dừng ở câu hỏi country trong khi bẫy nằm ở bản chất giá trị. Quan trọng hơn — kiểm tra trực tiếp cho thấy **cơ chế bảo vệ đã tồn tại nhưng bắt hụt**: `product_snapshot_metrics.csv` có sẵn cột `price_sentinel_flag`, nhưng chỉ **1 listing** toàn dataset được gắn cờ (`id:809769142:55559898858`, giá 999999999). Listing TC19 **không** được gắn cờ, vì 410.000đ nằm ở **percentile 85,5%**, cách rất xa p99.9 của VN (2.475.984đ) — luật "toàn chữ số 9 / ngoài percentile 99.9" của `§4.8` **về mặt cấu trúc không thể bắt được** dạng sentinel này, vốn là *giá lặp thành cụm ở giữa phân phối*, không phải giá ở đuôi.

## **Testcase 20: Bẫy Mã sản phẩm không tồn tại (Null Target Trap)**

- **Câu hỏi:** "Tìm sản phẩm tương đương cho mã ID 111222333444." (Một mã hoàn toàn không có trong 1157 listing của file dataset).

**Groundtruth (Claude):** `111222333444` xuất hiện **0 lần** trong `item_id` và **0 lần** trong `product_listing_key`; dataset có đúng **1.157 listing** trên 3 snapshot 01–03/07/2026. **Đáp án đúng: báo không tìm thấy, nói rõ mã không tồn tại trong dữ liệu hiện có, không được fallback sang khớp mờ theo chữ số.**

**Kết quả model Gladiators:** `intent=similar_product`, `entity_text='111222333444'` (`kind=item_id`, `confidence=exact`). `resolve()` trả về **rỗng** đúng theo nhánh `str(query).isdigit() → return []`, `classify()` → `invalid_extraction`, gate `abstain (A-ENTITY-NOT-FOUND)`: "Không tìm thấy listing nào khớp phần mô tả sản phẩm trong câu hỏi. Hãy nêu listing key, mã sản phẩm hoặc tên đầy đủ hơn."

**So sánh & Phân tích lỗi:** **Khớp hoàn toàn với groundtruth — testcase duy nhất trong nhóm 11–20 không có lỗi.** Đường ID-first hoạt động đúng thiết kế: mã thuần số không bao giờ rơi xuống fuzzy-match, nên không có nguy cơ trả về một sản phẩm ngẫu nhiên "gần giống chữ số". Ghi nhận một điểm nhỏ có thể cải thiện (không phải bug): message dùng chung với `invalid_extraction` nên nói "không khớp phần mô tả sản phẩm", trong khi ở đây lý do chính xác hơn là "mã sản phẩm không tồn tại trong dataset".

## Tổng kết đánh giá Testcase 11–20 (nhóm `similar_product`)

**Phương pháp:** Groundtruth do Claude tạo trực tiếp từ `data/processed/*.csv` (snapshot thực tế 01–03/07/2026). Model chạy qua `create_runtime("offline")` trên đúng commit hiện tại (`a00aefa`), provider `offline` (certified-macro / deterministic pipeline), cùng cấu hình đã dùng cho TC1–10.

**Kết quả tổng quan:**

| TC | Model có khớp nội dung groundtruth? | Gate | Evidence | Ghi chú |
|---|---|---|---|---|
| 11 | Không | `abstain A-ENTITY-NOT-FOUND` | 0 | Báo "không tìm thấy" cho sản phẩm có 46 listing; pool top-20 toàn hàng "quà tặng không bán" |
| 12 | Không | `abstain A19-PLAN` | 0 | Route sai sang `open_analytical`; năng lực đã có nhưng không bao giờ được gọi |
| 13 | Một phần | `clarify A16-CROSS-CURRENCY` | 0 | Chặn đúng bất biến FX nhưng bỏ sót lý do mạnh hơn: ID không có ngành hàng này |
| 14 | Không | `clarify A-AMBIGUOUS` | 0 | Candidate là **dầu hào MAGGI**; homograph "dâu"/"Dầu" sau khi strip dấu |
| 15 | Không | `clarify A-AMBIGUOUS` | 0 | Không bác được tiền đề "kệ hàng"; pool ứng viên **19 ID / 1 VN** |
| 16 | Không | `clarify A-ANALYTICAL-AMBIGUITY` | 0 | Clarify đúng loại nhưng hỏi sai thứ (country thay vì thực thể) |
| 17 | Không | `clarify A22-ALIGN-ENTITY` | 0 | Guard chặn đúng thiết kế; thiếu hẳn macro so sánh hai listing |
| 18 | Một phần | `abstain A-MISSING-SKU` | 0 | Từ chối quá tay: phần tìm listing cỡ 279g (8 listing) hoàn toàn trả lời được |
| 19 | Không | `clarify A-ANALYTICAL-AMBIGUITY` | 0 | `price_sentinel_flag` có sẵn nhưng luật hiện tại không bắt được sentinel dạng cụm |
| 20 | **Có** | `abstain A-ENTITY-NOT-FOUND` | 0 | Đúng hoàn toàn |

**Chỉ số then chốt: 0/10 testcase tạo ra được dù chỉ một Evidence.** Macro `similar_product` — vốn được verify là **chạy đúng khi bind tay** (TC11 ra 5 hàng xóm Richy, TC12 ra 5 đối thủ Cyeecare) — **không chạy được lần nào qua đường ngôn ngữ tự nhiên**. Đây là khác biệt căn bản so với nhóm `sales_decline`: ở TC1–10 vấn đề là "trả lời an toàn nhưng nông"; ở TC11–20 vấn đề là "không bao giờ tới được bước trả lời".

**Phân tích lỗi sai chính:**

1. **Thứ tự pattern trích entity sai ưu tiên (TC11, TC13, TC15):** cue chung `"san pham"` đứng trước cue chuyên biệt `"san pham tuong tu"` trong cùng tuple, nên luôn khớp trước và nuốt trọn phần đuôi câu — `entity_text` dài 14–25 token thay vì 3–6 token tên sản phẩm. Vi phạm trực tiếp MUST "soft guard 8 token" của `§4.2`.
2. **Thiếu competitor cue trong định tuyến intent (TC12, TC16, TC19):** cụm "đối thủ cạnh tranh", "cạnh tranh trực tiếp", "competitor", "pesaing" không có trong vocabulary route `similar_product`, dù `§4.2` ghi rõ MUST. Ba câu hỏi rơi xuống `open_analytical` và nhận thông điệp hỏi country vô nghĩa.
3. **`resolve()` không khoá `country_code` (TC15, và toàn hệ thống):** một câu hỏi tiếng Việt về shop VN nhận pool ứng viên 95% là mỹ phẩm Indonesia. `similar_products()` cũng không có bất kỳ tham chiếu nào tới `country_code` hay `shop_id`.
4. **Homograph sau khi strip dấu gây overlap giả (TC14):** "dâu"→`dau` đụng "Dầu"→`dau` (60 tên trong catalog), "hương"→`huong` đụng "Nấm Hương". Đã được ghi nhận ở `040826.md §5` như rủi ro lý thuyết; ở TC14 nó đã thành lỗi thật.
5. **Khoảng trống năng lực có dữ liệu sẵn (TC17, TC18):** so sánh hai listing đã biết mã (TC17) và tra biến thể theo `tier_variation_options` (TC18) đều **không cần dữ liệu mới**, chỉ cần macro/tool tương ứng.
6. **Bảo vệ sentinel giá mới cài một nửa (TC19):** `price_sentinel_flag` tồn tại trong artifact và được `insights/` dùng, nhưng (a) luật hiện tại chỉ bắt được giá toàn chữ số 9 (1/1157 listing), (b) tầng agent (`analytics/tools.py`, `entity_resolution.py`) không đọc cờ này ở bất kỳ đâu.
7. **Từ chối quá tay vì keyword đơn lẻ (TC18):** một từ "biến thể" đủ để chặn cả câu hỏi, kể cả phần nằm trọn trong dữ liệu — trong khi cơ chế `sub_requests` đã hoạt động tốt ở TC8 lại không kích hoạt.

**Điểm mạnh đã quan sát được:**
- **Không hallucinate:** không testcase nào để lọt một con số sai; mọi lần không chắc đều dừng ở clarify/abstain.
- **Bất biến FX được giữ tuyệt đối (TC13):** không có ca nào cộng hay so trực tiếp VND với IDR.
- **Đường ID-first đúng (TC20):** mã thuần số không rơi xuống fuzzy-match, không có "gần giống chữ số".
- **Lõi similarity đúng khi được gọi:** khi bind tay listing key, `similar_products()` trả kết quả hợp lý và tôn trọng ràng buộc cùng platform category level-1 của `§4.6`.

**Kết luận:** Nhóm `similar_product` có **precision danh nghĩa 100% nhưng recall thực tế 0%** — không phải vì lõi phân tích sai, mà vì **toàn bộ tổn thất nằm ở tầng trước macro** (trích entity → định tuyến intent → resolve). Lõi đã đúng và đã được verify; ba tầng dẫn vào nó thì chưa. Phân tích root-cause ở mức code và phương án sửa chi tiết được ghi tiếp tại [`docs/040826.md`](040826.md) §12–§21.

# Nhóm `promotion_effectiveness`

## **Testcase 21: Luồng chuẩn nội bộ (Standard Flow - VN)**

- **Câu hỏi:** "Tại thị trường Việt Nam, nhóm sản phẩm có áp dụng cả voucher và giảm giá trực tiếp (promo) có mang lại doanh thu ước tính tốt hơn nhóm không có khuyến mãi nào không?"

**Groundtruth (Claude, `data/processed/product_snapshot_metrics.csv`, snapshot 2026-07-03, VN):**
Cấu trúc 4 nhóm voucher × promo tại VN: **both = 577**, **voucher_only = 0**, **promo_only = 66**, **neither = 25** (tổng 668 dòng).
Doanh thu ước tính (`price_num × monthly_sold_value_num`):

| Nhóm | n | mean | median |
|---|---|---|---|
| both (voucher + promo) | 577 | 537.748.430 | **38.192.000** |
| promo_only | 66 | 21.732.191 | 10.873.500 |
| no_promotion | 25 | 44.164.364 | **10.197.000** |

**Đáp án đúng:** mô tả được — median nhóm có cả voucher lẫn promo cao hơn nhóm không khuyến mãi ~3,7×. Nhưng **bắt buộc kèm hai cảnh báo**: (a) nhóm đối chứng chỉ **n = 25** so với 577, quá nhỏ để khái quát; (b) đây là quan sát **cross-sectional, không phải nhân quả** — listing bán chạy được chọn chạy khuyến mãi, chứ không nhất thiết khuyến mãi làm tăng doanh thu. Phải trả median chứ không phải mean (xem TC24).

**Kết quả model Gladiators:** `intent=promotion_effectiveness`, `country=vn` đúng. Gate `clarify A22-ALIGN-QUALIFIER`: *"Điều kiện ngoài phạm vi macro được chứng nhận: no_promo_segment, revenue_measure"*. 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI** — từ chối một câu trả lời được. `estimated_recent_revenue` là **cột đã tính sẵn** trong `product_snapshot_metrics.csv` và được README định nghĩa chính thức; `revenue_measure` bị cấm là khoảng trống **macro**, không phải khoảng trống **dữ liệu** (khác hẳn TC28 nơi 0/80 cột có giá vốn). Macro `promotion_effectiveness` chỉ có đúng một hình dạng: so `monthly_sold` giữa hai nhóm voucher. Root cause code-level tại [`040826.md` §27](040826.md).

## **Testcase 22: Bẫy cấu trúc dữ liệu - Nhóm "Voucher Only" (Structural Trap)**

- **Câu hỏi:** "Hãy phân tích hiệu quả của nhóm sản phẩm chỉ áp dụng mã giảm giá (voucher) nhưng không có chương trình giảm giá trực tiếp (promo) trên toàn sàn ở Việt Nam."

**Groundtruth (Claude, snapshot 2026-07-03, VN):**
Nhóm "chỉ voucher, không promo" ở VN có **đúng 0 listing**. Toàn bộ **577** listing VN có structured voucher đều **đồng thời** có giảm giá hiển thị. (Ở ID: 0 listing có structured voucher, 419 chỉ có promo.)

**Đáp án đúng:** *"Nhóm anh hỏi không tồn tại — n = 0, nên không có gì để phân tích hiệu quả."* Đây là một **câu trả lời có bằng chứng**, không phải một lời từ chối: bẫy của testcase nằm chính ở chỗ nhóm rỗng.

**Kết quả model Gladiators:** `intent=promotion_effectiveness`, `country=vn`. Gate `clarify A22-ALIGN-QUALIFIER`: *"Điều kiện ngoài phạm vi macro được chứng nhận: no_promo_segment"*. 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI, và là ca bỏ lỡ đáng tiếc nhất nhóm này.** Model không sai về mặt an toàn, nhưng `clarify` **giấu mất chính phát hiện** mà câu hỏi nhắm tới. Người dùng nhận được "điều kiện ngoài phạm vi" thay vì "nhóm này rỗng". Hai cột bool cần thiết (`has_structured_voucher`, `has_displayed_discount`) đều có sẵn. Xem [`040826.md` §27](040826.md).

## **Testcase 23: Bẫy so sánh chéo Voucher VN vs ID (Cross-Country Trap)**

- **Câu hỏi:** "Mã giảm giá (voucher) mang lại hiệu quả chuyển đổi tốt hơn ở thị trường Việt Nam hay thị trường Indonesia?"

**Groundtruth (Claude, snapshot 2026-07-03):**
Số listing có structured voucher: **VN = 577**, **ID = 0**. Dataset **không có** sessions, views hay orders — không tồn tại mẫu số nào để tính tỷ lệ chuyển đổi.

**Đáp án đúng:** không tính được conversion rate ở cả hai thị trường. Phần trả lời được là **độ phủ voucher**: VN 577 listing, ID 0 listing — và chính con số ID = 0 khiến phép so sánh "voucher hiệu quả hơn ở đâu" **không có cơ sở về mặt cấu trúc**, chứ không chỉ thiếu metric.

**Kết quả model Gladiators:** `intent=voucher_coverage`, gate `allow A22-ALIGN-SUBREQUEST`, **2 Evidence**: `structured_voucher_listing_count` VN=577, ID=0. Trả lời: *"Mức độ phủ structured voucher tại snapshot mới nhất: VN=577 listings; ID=0 listings. Đây là số listing sau khi dedupe, không phải tỷ lệ chuyển đổi."* + sub-request: *"conversion effectiveness: Dataset không có sessions, views hay orders nên không tính được tỷ lệ chuyển đổi."*

**So sánh & Phân tích lỗi:** **ĐÚNG — câu trả lời tốt nhất nhóm `promotion_effectiveness`.** Cả hai con số khớp chính xác groundtruth, tách đúng phần trả lời được khỏi phần ngoài dữ liệu, và tự nói rõ đây không phải CVR. Điểm có thể mạnh hơn: chưa nhấn rằng **ID = 0 làm phép so sánh vô nghĩa ngay từ đầu**. Không có lỗi cần sửa.

## **Testcase 24: Bẫy Trung bình vs Trung vị (Mean vs Median Trap)**

- **Câu hỏi:** "Tính giúp tôi trung bình doanh thu ước tính (average revenue) của các sản phẩm có chạy chương trình khuyến mãi để xem shop thu về bao nhiêu ở Việt Nam."

**Groundtruth (Claude, snapshot 2026-07-03, VN, nhóm có khuyến mãi):**

```
n = 643 listing có khuyến mãi  (617 listing có revenue proxy khác rỗng)
mean = 482.550.583    median = 32.849.100    mean/median = 14,69×
std = 2.316.773.963   skew = 11,18
chỉ 84/617 listing (13,6%) đạt tới mức mean
top-5 listing chiếm 36,8% tổng doanh thu ước tính
  53654127440  Combo 3 Bịch NESCAFÉ CAFÉ VIỆT 35 gói  478.800 × 80.000 = 38.304.000.000
```

**Đáp án đúng:** phải trả **median 32.849.100** và giải thích vì sao mean vô nghĩa ở đây — phân bố lệch phải cực mạnh (skew 11,18), mean bị 5 listing combo cà phê Nescafé kéo lên, và **86,4% listing nằm dưới mean**. Trả mean một mình là rơi đúng vào bẫy.

**Kết quả model Gladiators:** `intent=promotion_effectiveness`, `country=vn`. Gate `clarify A22-ALIGN-QUALIFIER`: *"Điều kiện ngoài phạm vi macro được chứng nhận: mean_requested, revenue_measure"*. 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI.** Model chặn đúng chữ "trung bình" nhưng **không dạy lại người dùng điều gì** — trong khi toàn bộ bài học của testcase nằm ở chỗ *trả median và nói vì sao*. Từ chối vì `mean_requested` biến một cơ hội sửa hiểu lầm thành một thông điệp cụt. Xem [`040826.md` §27](040826.md).

## **Testcase 25: Bẫy Nhân quả & Tỷ lệ chuyển đổi (Causality & CVR Trap)**

- **Câu hỏi:** "Chương trình giảm giá 50% đã giúp các shop tăng bao nhiêu % tỷ lệ chốt đơn (conversion rate) so với lúc không giảm giá?"

**Groundtruth (Claude, snapshot 2026-07-03):**
Dataset **không có** sessions/views/orders → **không tính được conversion rate**, và cũng không có nhóm đối chứng "cùng sản phẩm lúc không giảm giá". Về phân bố chiết khấu:

```
bucket 45–55%:  toàn sàn 146 listing  =  ID 127 (87,0%)  +  VN 19 (13,0%)
đúng 50%:       toàn sàn 14           =  ID 12          +  VN 2
median monthly_sold proxy:  gộp VN+ID = 1.000  |  ID riêng = 1.000  |  VN riêng = 80,5
```

**Đáp án đúng:** từ chối phần "tăng bao nhiêu % tỷ lệ chốt đơn" (không có dữ liệu chuyển đổi, không có counterfactual). Nếu mô tả bucket thì **phải tách theo thị trường** — VN chỉ có 19 listing trong dải này.

**Kết quả model Gladiators:** `intent=discount_bucket_observation`, `country=None`. Gate `allow A22-ALIGN-SUBREQUEST`, **2 Evidence**: `discount_bucket_listing_count = 146`, `discount_bucket_median_monthly_sold_proxy = 1000`. Sub-request từ chối đúng phần CVR.

**So sánh & Phân tích lỗi:** **SAI — và là testcase DUY NHẤT trong 40 để lọt một con số sai phạm vi ra ngoài.** Phần từ chối CVR đúng. Nhưng `146` và `1.000` là thống kê **trộn VN + ID**, trong đó **87% là Indonesia**; median VN thật là **80,5**, tức con số trả về **lệch 12,4×** so với thị trường mà câu hỏi tiếng Việt đang nói tới. Root cause: [`analytics/tools.py:333`](../src/gladiators/analytics/tools.py#L333) `discount_bucket_observation()` **không nhận tham số country và không lọc `country_code` ở bất kỳ dòng nào** — khác hẳn `voucher_coverage()` ngay bên trên (vốn nhóm theo `dim.country` và nhờ đó TC23 đúng). Việc trộn là cố ý (`attrs={"country": "vn+id_separate_nonmonetary"}`) với lập luận "không phải đại lượng tiền tệ nên §1.2 không cấm" — nhưng cái hỏng ở đây không phải đơn vị tiền mà là **tính đại diện của mẫu**, và nhãn cảnh báo đó nằm trong `attrs`, **không xuất hiện trong câu trả lời**. Ngoài ra median 1.000 là **mức bucket hiển thị** (100% giá trị `monthly_sold ≥ 1000` trong dataset là bội số của 1000). Fix chi tiết: [`040826.md` §28](040826.md) — **ưu tiên cao nhất**.

## **Testcase 26: Bẫy chiến dịch Marketing (`promotion_id` Trap)**

- **Câu hỏi:** "Chiến dịch marketing có mã promotion ID '473502013010049' đã mang lại tổng doanh thu bao nhiêu cho nền tảng?"

**Groundtruth (Claude, `promotion_id = 473502013010049`):**

```
85 dòng snapshot / 85 listing
country_code: 100% vn        shop: Richy - Chi Nhánh Miền Bắc
ngày:  CHỈ tồn tại ở 2026-07-01  (biến mất ở 07-02 và 07-03)
tổng revenue proxy của 85 listing tại 07-01 = 7.115.226.xxx VND
```

**Đáp án đúng:** **không** quy được doanh thu cho chiến dịch — `promotion_id` là thuộc tính hiển thị ở cấp listing, không phải attribution ở cấp đơn hàng; không có nhóm đối chứng; và mã này chỉ xuất hiện **một** snapshot nên "tổng doanh thu mang lại" không có khung thời gian để tính. Phần **mô tả được**: 85 listing mang mã này, toàn bộ ở VN/Richy, chỉ ngày 01/07, doanh thu proxy quan sát tại snapshot đó ≈ 7,12 tỷ VND.

**Kết quả model Gladiators:** trích đúng `('promotion_id', '473502013010049', 'exact')` nhưng `country=None`. Gate `clarify A-MISSING-SLOT`: *"Thiếu thông tin: country"*. 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI.** Model hỏi country trong khi mã đó **100% thuộc VN** và suy ra được xác định từ dữ liệu. Root cause: [`parser.py:100`](../src/gladiators/agent/parser.py#L100) `COUNTRY_INFERENCE_INTENTS = frozenset({"open_analytical", "analytical_query"})` — `promotion_effectiveness` **không có trong danh sách**; và [`parser.py:362-369`](../src/gladiators/agent/parser.py#L362-L369) chỉ suy country từ **product span**, trong khi TC26 có `entity_text = None`. Cơ chế suy country (Fix G, §24.G) đã dựng xong nhưng chỉ nối vào 2/13 intent và một loại thực thể. Xem [`040826.md` §29](040826.md).

## **Testcase 27: Bẫy Double Discount (Giá trị Voucher Trap)**

- **Câu hỏi:** "Để tính doanh thu thực nhận của nhóm có mã giảm giá, hệ thống có lấy giá bán (price) trừ đi giá trị mã giảm giá (voucher_discount) không?"

**Groundtruth (Claude, snapshot 2026-07-03):**

```
price_original >= price:            1142/1142  (price luôn là giá đã giảm)
price_before_promo > price:          646/1142
listing có voucher_discount > 0:     577
  trong đó voucher_min_spend > price: 125  -> voucher KHÔNG áp được cho 1 sản phẩm đơn lẻ
```

**Đáp án đúng:** **Không, và không được làm vậy.** `price` đã là giá bán quan sát (đã trừ khuyến mãi trực tiếp) — trừ tiếp `voucher_discount` là **trừ hai lần**. Thêm nữa voucher là ưu đãi **có điều kiện ở cấp giỏ hàng**: **125/577** listing có `voucher_min_spend` lớn hơn chính giá sản phẩm, nghĩa là mua một cái không đủ điều kiện dùng voucher. Không có trường nào cho biết voucher có thực sự được áp hay không.

**Kết quả model Gladiators:** `intent=unsupported:price_reconstruction`, gate `abstain A-MISSING-PRICE_RECONSTRUCTION`: *"Không thể tái tạo giá cuối bằng cách trừ voucher lần nữa; price đã là giá quan sát. Voucher có điều kiện áp dụng và không phải mọi listing đều đủ điều kiện. Vẫn trả lời được price và voucher_discount như hai giá trị quan sát riêng."*

**So sánh & Phân tích lỗi:** **ĐÚNG.** Khớp cả hai vế của groundtruth (đã trừ rồi + voucher có điều kiện), và còn gợi ý được hướng hỏi thay thế hợp lệ. Không phát hiện lỗi.

## **Testcase 28: Bẫy Lợi nhuận (ROI / Margin Trap)**

- **Câu hỏi:** "Mức giảm giá nào (discount bucket) đang tối ưu hóa được lợi nhuận (profit margin) tốt nhất cho các shop FMCG tại Việt Nam?"

**Groundtruth (Claude):** `products_clean.csv` có **80 cột**, trong đó số cột chứa giá vốn / phí sàn / chi phí vận hành / hoa hồng: **0**. Không có `cost`, `cogs`, `fee`, `commission`, `margin`, `profit` dưới bất kỳ dạng nào.

**Đáp án đúng:** không tính được profit margin cho bất kỳ discount bucket nào — đây là yêu cầu ngoài phạm vi dữ liệu, không phải bài toán khó.

**Kết quả model Gladiators:** `intent=unsupported:profit`, gate `abstain A-MISSING-PROFIT`: *"Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận... Vẫn trả lời được doanh thu proxy ước tính, giá và lượt bán proxy."* + gợi ý câu hỏi thay thế.

**So sánh & Phân tích lỗi:** **ĐÚNG.** Từ chối đúng lý do, nêu đúng ranh giới năng lực, và chỉ ra được cái thay thế. Đây là mẫu thông điệp tốt mà các nhánh `A22-ALIGN-*` nên học theo (xem [`040826.md` §31](040826.md)).

## **Testcase 29: Bẫy So sánh Số tiền Tuyệt đối (Absolute Monetary FX Trap)**

- **Câu hỏi:** "Trung bình mỗi sản phẩm tại Indonesia được giảm giá bao nhiêu tiền so với các sản phẩm tại Việt Nam?"

**Groundtruth (Claude, snapshot 2026-07-03):**

```
VN:  n=668  mean discount_amount =  96.978 VND   median = 32.260 VND   (mean price   242.351 VND)
ID:  n=472  mean discount_amount = 155.237 IDR   median = 77.150 IDR   (mean price 2.246.673 IDR)
dataset KHÔNG có bảng tỷ giá / cột FX nào
```

**Đáp án đúng:** **không so sánh được.** 155.237 IDR không "lớn hơn" 96.978 VND — hai đơn vị tiền khác nhau, và dataset không chứa tỷ giá nào để quy đổi. Chỉ trả lời được nếu tách riêng từng thị trường theo đơn vị bản địa.

**Kết quả model Gladiators:** `intent=analytical_query`, `countries=['vn','id']`. Gate `clarify A16-CROSS-CURRENCY`: *"Không cộng hoặc so sánh trực tiếp giá trị VND với IDR."* + *"Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương."*

**So sánh & Phân tích lỗi:** **ĐÚNG.** Bất biến `§1.2` được giữ tuyệt đối, và gợi ý thay thế đúng hướng. Không phát hiện lỗi.

## **Testcase 30: Bẫy Sentinel Promotion (Giá trị rác Promo ID)**

- **Câu hỏi:** "Chương trình khuyến mãi có mã '0' (promotion_id = 0) đang áp dụng cho bao nhiêu sản phẩm ở Việt Nam?"

**Groundtruth (Claude):**

```
promotion_id == 0, toàn dataset: 874 dòng
VN snapshot 2026-07-03:  241/668 dòng  (36,1%)
VN cả 3 ngày:            255 listing distinct
Trong 241 dòng đó:  217 vẫn có discount_percent > 0
                    217 vẫn có voucher_code
VN latest có 22 promotion_id distinct
```

**Đáp án đúng:** `0` **không phải một chương trình khuyến mãi**. Đây là giá trị **sentinel** nghĩa là "không ghi nhận mã chiến dịch sàn cho listing này". Bằng chứng đanh nhất: **217/241 listing mang `promotion_id = 0` vẫn đang có giảm giá và voucher** — nếu 0 nghĩa là "không khuyến mãi" thì con số đó phải bằng 0. Trả lời đúng là bác lại tiền đề của câu hỏi rồi mới đưa số 241 dòng / 255 listing kèm giải thích.

**Kết quả model Gladiators:** trích đúng `('promotion_id', '0', 'exact')`, `country=vn` đúng. Gate `clarify A22-ALIGN-QUALIFIER`: *"Điều kiện ngoài phạm vi macro được chứng nhận: promotion_id_filter"*. 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI.** Model nhận diện thực thể chuẩn xác rồi **vứt đi** vì macro không có hình dạng lọc theo `promotion_id`. Bẫy sentinel hoàn toàn không được chạm tới. Cùng root cause với TC21/22/24: [`macros.py:213-216`](../src/gladiators/planner/macros.py#L213-L216) `forbidden_qualifiers`. Xem [`040826.md` §27](040826.md).

# Nhóm `error_and_limitations`

## **Testcase 31: Lỗi Lệch Khung Thời Gian (Out-of-Timeframe Trap)**

- **Câu hỏi:** "Hãy so sánh doanh số của các sản phẩm FMCG trong tháng 6/2026 và dự báo cho tháng 8/2026."

**Groundtruth (Claude):** dataset phủ **đúng 3 snapshot: 2026-07-01, 07-02, 07-03**. Tháng 6/2026: **0 snapshot**. Tháng 8/2026: **0 snapshot**.

**Đáp án đúng:** không so sánh được tháng 6 (ngoài phủ) và không dự báo được tháng 8 (3 snapshot không đủ cho xu hướng/seasonality). Phải nói rõ phạm vi dữ liệu thật.

**Kết quả model Gladiators:** `intent=dataset_coverage`, gate `allow A22-ALIGN-SUBREQUEST`, **3 Evidence**: `coverage_start_date=2026-07-01`, `coverage_end_date=2026-07-03`, `coverage_snapshot_count=3`. Sub-request: *"forecast: Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy."*

**So sánh & Phân tích lỗi:** **ĐÚNG.** Trả lời bằng Evidence thay vì chỉ từ chối, tách đúng hai vế. Không phát hiện lỗi.

## **Testcase 32: Lỗi Ảo giác Quảng cáo (Ads Hallucination Trap)**

- **Câu hỏi:** "Shop mỹ phẩm Glad2Glow đang chạy quảng cáo (ads) cho những sản phẩm nào, hiệu quả doanh thu từ quảng cáo là bao nhiêu?"

**Groundtruth (Claude):**

```
is_ad_bool:  False ở TOÀN BỘ 3341 dòng  (nunique = 1)
shop Glad2Glow Official Store: 220 listing, 660 dòng, 0 listing bật cờ is_ad
cột impressions / clicks / ad_spend / ctr / roas / cpc:  KHÔNG CÓ
```

**Đáp án đúng:** không đo được hiệu quả doanh thu từ quảng cáo — không có impressions, clicks hay ad spend. Về vế "chạy ads cho sản phẩm nào": dataset **không ghi nhận** listing nào của Glad2Glow được đánh dấu quảng cáo, nhưng phải kèm cảnh báo `is_ad` là **cờ suy biến** (một giá trị duy nhất trên toàn dataset) nên nó **không chứng minh** shop không chạy ads — chỉ nói được dataset không ghi nhận.

**Kết quả model Gladiators:** `intent=unsupported:ads`, gate `abstain A-MISSING-ADS`: *"Dataset không có impressions, clicks hay ad spend nên không đo được quảng cáo... Vẫn mô tả được giá, voucher và lượt bán proxy quan sát."*

**So sánh & Phân tích lỗi:** **ĐÚNG** về vế chính (hiệu quả ads). Thiếu một chi tiết có thể bổ sung mà không phá tính đúng đắn: nêu **220 listing Glad2Glow, 0 listing bật `is_ad`** kèm cảnh báo cờ suy biến — trả lời được vế "sản phẩm nào" bằng chính dữ liệu. Ghi ở [`040826.md` §34](040826.md).

## **Testcase 33: Lỗi Phân tích cấp độ SKU (SKU-Level Trap)**

- **Câu hỏi:** "Trong sản phẩm Combo 5 Bánh Quy Oreo Với Kem Vị Dâu/Vani/Sôcôla (mã 25211554425) có 3 biến thể: Dâu, Vani, Sôcôla. Hãy cho tôi biết biến thể (vị) nào đang mang lại doanh thu cao nhất?"

**Groundtruth (Claude, item `25211554425`, Kinh Do Official Store, vn):**

```
product_name: Combo 5 Bánh Quy Oreo Với Kem Vị Dâu/Vani/Sôcôla 110.4g
tier_variation_name:    "Phân loại"
tier_variation_options: ["CB5 Dâu", "CB5 Choco", "CB5 Vani"]   (đúng 3 biến thể)
monthly_sold: 24 / 24 / 24  (phẳng cả 3 ngày, ở CẤP LISTING)
price:        86.000 / 100.000 / 90.000
cột sku_id / model_id / doanh số theo biến thể: KHÔNG CÓ
```

**Đáp án đúng:** **không phân bổ được doanh thu theo biến thể.** `tier_variation_options` chỉ mô tả **lựa chọn hiển thị** trên trang sản phẩm; đơn vị nhỏ nhất mà dataset đo được là **product listing**. Con số duy nhất có thật là 24 lượt bán proxy cho cả listing, không tách được thành Dâu/Vani/Sôcôla.

**Kết quả model Gladiators:** `intent=unsupported:sku`, gate `abstain A-MISSING-SKU`: *"Dataset không có sku_id/model_id; đơn vị nhỏ nhất là product listing. tier_variation chỉ mô tả lựa chọn hiển thị, không phân bổ doanh số theo biến thể."*

**So sánh & Phân tích lỗi:** **ĐÚNG.** Thông điệp nêu chính xác cả nguyên nhân (không có sku_id) lẫn cái bẫy (tier_variation ≠ doanh số theo biến thể). Có thể mạnh hơn nếu trưng luôn 3 biến thể và con số 24 ở cấp listing. Không phát hiện lỗi.

## **Testcase 34: Lỗi Thiếu Ngày / Đứt gãy Dữ liệu (Snapshot Gap Trap)**

- **Câu hỏi:** *"*Tính mức giảm doanh số (sales delta) của sản phẩm Collagen Thủy Phân NESTLÉ VITAL PROTEINS 284G (mã 24710759163) từ ngày 01/07 đến ngày 03/07.*"*

**Groundtruth (Claude, item `24710759163`, Nestlé Health Science, vn):**

```
ngày         price      monthly_sold   history_sold   snapshot_gap_flag
2026-07-01   598.400    193            751            False
2026-07-02   620.840    306            864            False
2026-07-03   595.020    204            768            False

transitions: 07-01→07-02  delta = +113   eligible=True   snapshot_sales_delta_clean = 113
             07-02→07-03  delta = −102   eligible=True   snapshot_sales_delta_clean = NaN
                                          history_sold_decrease_flag = True (864 → 768)
chênh đầu-cuối 01/07 → 03/07 = 204 − 193 = +11  (+5,7%)
```

**Đáp án đúng:** **tiền đề "mức giảm doanh số" của câu hỏi là sai** — từ 01/07 đến 03/07 sản phẩm **tăng +11 (+5,7%)**, không giảm. Phải nêu thêm hai điều: (a) đường đi không đơn điệu, vọt lên 306 ngày 02/07 rồi rơi về 204, nên lấy hai đầu mút che mất biến động trong kỳ; (b) điểm ngày 02→03 **không đáng tin** — pipeline đã vô hiệu hoá `snapshot_sales_delta_clean` thành `NaN` vì lũy kế `history_sold` tụt 864 → 768. Không có snapshot gap (`snapshot_gap_flag = False` cả 3 dòng).

**Kết quả model Gladiators:** `intent=sales_decline`, bind đúng `('item_id','24710759163','high')`, nhưng `country=None`. Gate `clarify A22-ALIGN-DATE`: *"Evidence phủ cửa sổ 2026-07-02→2026-07-03 thay vì 2026-07-01→2026-07-03 đã hỏi."* `verification.coverage = 0.0`, 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI (từ chối quá tay).** Guard bắn **đúng thiết kế** — nó phát hiện evidence không phủ cửa sổ được hỏi và từ chối thay vì trả số sai cửa sổ, đó là hành vi an toàn đáng giữ. Nhưng dữ liệu **hoàn toàn đủ**: cả hai transition đều `eligible=True`, và **1039/1145 listing** trong dataset có đủ hai transition liên tiếp — cửa sổ 2 ngày tính được cho 91% catalog. Root cause: macro `sales_decline` đóng băng ở **một cặp snapshot**, tool chỉ đọc `rows.iloc[-1]` (giới hạn đã ghi ở §24.B). §24.C thêm được *caveat* đa-ngày nhưng **không** thêm *năng lực* đa-ngày — TC34 là ca đầu tiên phân biệt rõ hai thứ đó. Model cũng không bao giờ chạm tới việc **bác tiền đề**. Xem [`040826.md` §30](040826.md).

## **Testcase 35: Lỗi Thực thể "Ma" (Non-existent Domain Trap)**

- **Câu hỏi:** "Phân tích doanh số của điện thoại iPhone 15 Pro Max tại shop Apple Official Store."

**Groundtruth (Claude):**

```
shop tên chứa "Apple":           0
listing chứa "iphone":           0
listing chứa "điện thoại":       0
20 shop trong dataset: toàn bộ là FMCG bánh kẹo/sữa (VN) và mỹ phẩm (ID)
42 brand distinct: AFC, Alpenliebe, Bibica, Chupa Chups, Cosy, Glad2Glow, Kinh Đô, ...
```

**Đáp án đúng:** **không tìm thấy thực thể** — hệt TC20. Shop Apple Official Store và iPhone 15 Pro Max không tồn tại trong dataset; ngành hàng điện thoại hoàn toàn nằm ngoài phạm vi.

**Kết quả model Gladiators:** `intent=sales_decline`, `country=None`. Gate `clarify A-AMBIGUOUS` với 3 ứng viên:

```
Lavojoy Hold Me Tight Pro Shampoo Spring Wonder | Hair Shampoo | Sampo
[LIVE] Lavojoy Hold Me Tight Pro Shampoo Spring Wonder Hair Fall Care
Lavojoy Hold Me Tight Pro Scalp Essence Spring Wonder | Hair Shampoo |
```

**So sánh & Phân tích lỗi:** **SAI — lỗi nặng nhất của vòng đánh giá này.** Ba chai dầu gội Indonesia được đề nghị cho một câu hỏi về iPhone. Nguy hiểm hơn mọi ca `clarify` khác vì `clarify` ngụ ý "hệ thống có dữ liệu, chỉ cần bạn chọn đúng listing" — trong khi sự thật là ngành hàng này không tồn tại. Verify bằng cách gọi thẳng `EntityResolver`:

```
wanted = {dien, iphone, max, pro, thoai}          (5 token)
pool   = 12/1157 listing, kéo vào bởi:  pro -> 9 listing,  dien -> 3 listing
         (iphone -> 0,  thoai -> 0,  max -> 0)
top1 = top2 = 0.855,  margin = 0.0  ->  ambiguous_broad
overlap của cả 3 candidate = {'pro'}  =  1/5 = 20% token truy vấn
```

Cả hai chốt chặn ([`entity_resolution.py:165`](../src/gladiators/agent/entity_resolution.py#L165) và [`:285-295`](../src/gladiators/agent/entity_resolution.py#L285-L295)) chỉ kiểm tra **giao khác rỗng**, không kiểm tra **tỷ lệ phủ**. `0.855` chính là hằng số mà docstring `entity_resolution.py:16-20` đã ghi nhận từ vòng trước; vòng đó xử lý bằng cách mở rộng stop lexicon — một **blocklist**, và blocklist không thể đóng kín (`pro`, `max`, `new`, `big`, `combo` là từ sản phẩm thật). **TC20 thoát được không nhờ chốt nào ở trên** mà nhờ đường ID riêng ([`:190-191`](../src/gladiators/agent/entity_resolution.py#L190-L191)): sàn "không tìm thấy" hiện **chỉ tồn tại cho mã số, không tồn tại cho tên**. Fix đề xuất (orphan-ratio, đã đo ngưỡng trên cả 40 testcase): [`040826.md` §26](040826.md).

## **Testcase 36: Lỗi Tính tổng Xuyên Biên Giới (Cross-Country Aggregation Trap)**

- **Câu hỏi:** "Tổng doanh thu ước tính của cả thị trường Việt Nam và Indonesia cộng lại trong 3 ngày qua là bao nhiêu?"

**Groundtruth (Claude):**

```
VN (VND) revenue proxy:  07-01: 183.611.475.838 | 07-02: 253.042.631.488 | 07-03: 298.219.517.806
ID (IDR) revenue proxy:  07-01:  27.221.907.755 | 07-02:  29.417.731.517 | 07-03:  29.588.926.670
cộng thẳng VN+ID tại snapshot cuối = 327.808.444.476   <- SAI (trộn VND với IDR)
cộng 3 ngày của riêng VN           = 734.873.625.132   <- SAI (đếm trùng cửa sổ trượt)
```

**Đáp án đúng:** câu hỏi chứa **hai** bẫy chồng nhau. (1) **FX**: không cộng được VND với IDR, dataset không có bảng tỷ giá. (2) **Cộng dồn cửa sổ trượt**: "3 ngày qua" ngụ ý cộng 3 snapshot của `monthly_sold` — README cấm rõ (*"Do not aggregate it across the three snapshot dates"*), vì cùng một lượt bán bị đếm lại ở mỗi snapshot. Chỉ trả lời được: từng thị trường, từng snapshot, bằng đơn vị bản địa.

**Kết quả model Gladiators:** `intent=open_analytical`, `countries=['vn','id']`. Gate `clarify A16-CROSS-CURRENCY`: *"Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR..."* + *"Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương."*

**So sánh & Phân tích lỗi:** **MỘT PHẦN.** Bẫy FX bị chặn đúng và dứt khoát. Nhưng **bẫy thứ hai không được chạm**: kể cả khi người dùng làm theo gợi ý và hỏi riêng VN, phép cộng 3 ngày vẫn sai — và câu trả lời hiện tại vô tình dẫn họ tới đó. Cần dùng chung thông điệp `cross_snapshot_sum` đề xuất ở [`040826.md` §31](040826.md).

## **Testcase 37: Lỗi Số lượng Tồn kho Tuyệt đối (Absolute Inventory Trap)**

- **Câu hỏi:** "Shop Orion VN hiện tại đang còn tồn kho bao nhiêu thùng bánh Chocopie trong kho?"

**Groundtruth (Claude):**

```
shop Orion VN Official Store: 84 listing;  listing tên chứa "Chocopie": 10
cột stock / inventory / quantity / qty:  KHÔNG CÓ (0 cột)
is_sold_out_bool: False ở TOÀN BỘ 3341 dòng
stock_status (transition_metrics): chỉ có 'available' (2179) và 'not_comparable_snapshot_gap' (5)
```

**Đáp án đúng:** **không có dữ liệu tồn kho.** Dataset chỉ quan sát trang listing công khai; không có số lượng tồn, và `is_sold_out` là cờ suy biến (luôn `False`) nên cũng không suy ra được gì. Thêm nữa "bao nhiêu **thùng**" đòi quy đổi đơn vị đóng gói mà dataset không có.

**Kết quả model Gladiators:** `intent=unsupported:inventory`, gate `abstain A-MISSING-INVENTORY`: *"Dataset không có số lượng tồn kho; cờ sold-out hiện không đủ để suy ra tồn thực tế..."*

**So sánh & Phân tích lỗi:** **ĐÚNG.** Đáng chú ý là thông điệp nói rõ *"cờ sold-out **không đủ** để suy ra tồn thực tế"* — đúng bản chất cờ suy biến, không chỉ nói "thiếu cột". Không phát hiện lỗi.

## **Testcase 38: Lỗi Nhân quả Chéo (Cross-Metrics Causality Trap)**

- **Câu hỏi:***"*Điểm đánh giá (rating) tăng từ 4.85 lên 4.88 có phải là lý do chính khiến sản phẩm Sữa Bột NESTLÉ NUTREN JUNIOR 800G (mã 26663401389) bán được nhiều hơn ở Việt Nam trong ngày 03/07 không?*"*

**Groundtruth (Claude, item `26663401389`, Nestlé Health Science, vn):**

```
ngày         rating      rating_count   monthly_sold   price      voucher
2026-07-01   4.851894    872            1000           537.030    17GIAM350K2
2026-07-02   4.851894    872            1000           550.290    237GIAM350K2
2026-07-03   4.883527    1203           3000           550.290    237GIAM350K2

transition 07-02→07-03:  rating_change = +0.0316   new_rating_count = +331
                         monthly_sold_delta = +2000   price_change = 0
toàn dataset: corr(rating_change, monthly_sold_delta) = 0,0039   (n = 2038 transition)
              số transition có rating_change != 0: 964
```

**Đáp án đúng:** **Không.** Bốn lý do, tất cả đều tính được từ dữ liệu:
1. **Nhân quả nhiều khả năng ngược chiều** — `rating_count` tăng **+331** đúng ngày đó: nhiều người mua **sinh ra** nhiều đánh giá, chứ không phải điểm đánh giá kéo doanh số. Hai biến nhảy cùng một snapshot nên thứ tự thời gian không tách được nguyên nhân khỏi kết quả.
2. **1000 → 3000 là bước nhảy bucket hiển thị**, không phải +2000 đơn vị đo được — **100% (1015/1015)** giá trị `monthly_sold ≥ 1000` trong dataset là bội số của 1000.
3. **Ở quy mô toàn dataset không có liên hệ nào**: tương quan **0,0039** trên 2038 transition.
4. Một listing × một transition không đủ cơ sở suy nhân quả.

**Kết quả model Gladiators:** `intent=open_analytical`, `country=vn` đúng, bind đúng `('item_id','26663401389','high')`. Gate `abstain A19-PLAN`: *"Không có semantic planner provider cho câu hỏi ngoài certified template."* 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI (0% nội dung).** Model đi qua được mọi tầng trước — country đúng, entity đúng — rồi chết ở planner. Câu hỏi này **không thực sự cần planner**: nó cần một macro *giải nghĩa metric + từ chối nhân quả chéo*, và cả 4 luận điểm của groundtruth đều nằm sẵn trong `product_transition_metrics.csv`. `A19-PLAN` là fallback đúng cho chế độ offline nhưng nằm **cuối** đường nên nuốt cả những câu mà một macro chuyên trách lẽ ra phải bắt trước — cùng khuôn hình với `A22-ALIGN-QUALIFIER` ở TC21/22/24/30. Xem [`040826.md` §32](040826.md).

## **Testcase 39: Lỗi Cộng dồn Tháng (Monthly Accumulation Trap)**

- **Câu hỏi:** *"Tổng số lượng sản phẩm bán ra của sản phẩm Sữa Bột NESTLÉ NUTREN JUNIOR 800G (mã 26663401389) trong 3 ngày vừa qua ở Việt Nam là bao nhiêu? Hãy cộng lượt bán hàng tháng (monthly_sold) của 3 ngày lại."*

**Groundtruth (Claude, item `26663401389`, vn):**

```
monthly_sold:  07-01: 1000  |  07-02: 1000  |  07-03: 3000
cộng 3 ngày = 5000       <- chính là điều câu hỏi yêu cầu, và là SAI
chênh đầu-cuối = +2000
100% (1015/1015) giá trị monthly_sold >= 1000 trong dataset là bội số của 1000
```

**Đáp án đúng:** **không được cộng.** README nói thẳng: *"`monthly_sold_value` is a recent-window proxy with an unknown exact window. **Do not aggregate it across the three snapshot dates.**"* Mỗi snapshot đã bao gồm cùng một khoảng thời gian gần đây, nên cộng 3 ngày là **đếm trùng cùng một lượt bán ba lần**. Trả lời đúng là trích đúng luật đó, đưa ra 3 giá trị quan sát, và nếu cần thì chênh lệch đầu-cuối **+2000** — kèm cảnh báo đó cũng chỉ là một bước nhảy bucket hiển thị.

**Kết quả model Gladiators:** `intent=analytical_query`, `country=vn`, bind đúng item_id. Gate `clarify A22-ALIGN-MEASURE`: *"Plan không giữ measure đã được liên kết từ câu hỏi: measure.monthly_sold; Plan output thay bằng measure không được hỏi: derived.product_count; Plan bỏ chiều đã hỏi: dim.product_name; Entity/ID trong câu hỏi không được bind vào plan."*

**So sánh & Phân tích lỗi:** **SAI.** Model từ chối — an toàn, không phát ra `5000` — nhưng **vì lý do hoàn toàn khác** với lý do đúng, và **không bao giờ nói ra luật cấm cộng dồn**. Thông điệp còn rò rỉ từ vựng nội bộ của planner ("Plan", "measure.", "bind", "dim.") mà người dùng không hành động được: về mặt trải nghiệm đây là `abstain` đội lốt `clarify`. Đối chiếu với TC28 (*"Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận"*) để thấy khoảng cách chất lượng thông điệp. Fix: [`040826.md` §31](040826.md).

## **Testcase 40: Lỗi Đếm trùng Danh mục Nội bộ (Shop Merchandising Double Count)**

- **Câu hỏi:** "Tính tổng doanh thu ước tính của tất cả các kệ hàng nội bộ (category_list) của shop Nestlé, sau đó cộng lại xem tổng shop thu được bao nhiêu."

**Groundtruth (Claude):**

```
shop khớp "Nestlé": 2  ->  Nestlé Chính hãng      (108166524,  82 listing)
                           Nestlé Health Science  (1145316676, 87 listing)
                           cả hai country_code = vn

kệ nội bộ (category_list):  8 + 15 = 23 kệ
  cột 'total' của kệ:  shop 1 = 132  (so với 82 listing thật)
                       shop 2 =  95  (so với 87 listing thật)

product_categories, snapshot cuối: 109 item  ->  227 cặp (item, category)
  76 item thuộc 2 kệ | 15 item thuộc 3 kệ | 4 item thuộc 4 kệ | 14 item thuộc 1 kệ

Doanh thu proxy ĐÚNG (dedupe theo product_listing_key, 1 snapshot) = 217.909.030.928 VND
Cộng theo từng kệ (đúng như câu hỏi yêu cầu)                       = 415.616.618.040 VND
                                                            phóng đại = 1,91×
```

**Đáp án đúng:** ba ý. (1) **"shop Nestlé" mơ hồ** — có 2 shop, phải hỏi rõ shop nào (hoặc trả cả hai). (2) **Cộng doanh thu theo từng kệ là double-count**: 76 item nằm ở 2 kệ, 15 item ở 3 kệ, 4 item ở 4 kệ — cùng một listing bị tính lại ở mỗi kệ, kết quả **phóng đại 1,91×**. (3) Cách đúng là **dedupe theo `product_listing_key`** tại một snapshot → 217.909.030.928 VND.

**Kết quả model Gladiators:** `intent=open_analytical`, `country=None`, `entities=[]`. Gate `clarify A-ANALYTICAL-AMBIGUITY`: *"Thiếu country cho metric tiền tệ; không được trộn VND và IDR."* 0 Evidence.

**So sánh & Phân tích lỗi:** **SAI (0% nội dung).** Model hỏi **sai thứ**: cả 2 shop Nestlé đều ở VN nên country suy ra được, còn thứ thật sự mơ hồ — *"Nestlé nào trong hai shop?"* — thì không được hỏi. Bẫy double-count hoàn toàn không được chạm tới. Hai root cause chồng nhau: (a) suy country không đọc `shop_name` và `promotion_effectiveness`/`open_analytical` không nối đủ nguồn định danh ([`040826.md` §29](040826.md)); (b) `ShopResolver` ([`shop_resolution.py`](../src/gladiators/agent/shop_resolution.py)) đã tồn tại nhưng **chưa nhánh nào của `open_analytical` gọi tới**, nên không có đường phát ra `A-AMBIGUOUS` ở cấp shop.

## Tổng kết đánh giá Testcase 21–30 (nhóm `promotion_effectiveness`)

**Phương pháp:** Groundtruth do Claude tính trực tiếp từ `data/processed/*.csv` (3 snapshot 2026-07-01→03, VN 682 listing / ID 475 listing). Model chạy `create_runtime("offline")` tại HEAD `56b14f8` — tức **sau** vòng hardening A–Q.

| TC | Chấm | Gate | Ev | Ghi chú |
|---|---|---|---|---|
| 21 | ✗ | `clarify A22-ALIGN-QUALIFIER` | 0 | `revenue_measure` bị cấm dù `estimated_recent_revenue` là cột có sẵn |
| 22 | ✗ | `clarify A22-ALIGN-QUALIFIER` | 0 | Bẫy là "nhóm rỗng (n=0)"; model từ chối nên giấu mất phát hiện |
| 23 | **✅** | `allow` + sub-request | 2 | VN=577 / ID=0 chính xác; từ chối CVR đúng |
| 24 | ✗ | `clarify A22-ALIGN-QUALIFIER` | 0 | Bẫy mean-vs-median: đáng lẽ trả median 32.849.100 |
| 25 | ✗ | `allow` + sub-request | 2 | **Số sai phạm vi lọt ra ngoài** — 146/1000 là thống kê trộn 87% ID |
| 26 | ✗ | `clarify A-MISSING-SLOT` | 0 | Hỏi country dù mã 100% thuộc VN |
| 27 | **✅** | `abstain` | 0 | Khớp groundtruth |
| 28 | **✅** | `abstain A-MISSING-PROFIT` | 0 | 0/80 cột có giá vốn |
| 29 | **✅** | `clarify A16-CROSS-CURRENCY` | 0 | Bất biến FX giữ tuyệt đối |
| 30 | ✗ | `clarify A22-ALIGN-QUALIFIER` | 0 | Bẫy sentinel `promotion_id=0` không được chạm |

**4 ✅ / 0 ◐ / 6 ✗ — nhóm yếu nhất trong bộ 40.**

**Điểm mấu chốt:** 4 trong 6 ca hỏng (TC21, 22, 24, 30) hỏng vì **cùng một dòng code** — [`macros.py:213-216`](../src/gladiators/planner/macros.py#L213-L216):

```python
forbidden_qualifiers=frozenset({
    "promotion_id_filter", "no_promo_segment", "revenue_measure",
    "mean_requested", "discount_bucket",
})
```

Toàn bộ năng lực `promotion_effectiveness` là **một** `CertifiedMacro` với **một** hình dạng: so `monthly_sold` giữa nhóm có/không structured voucher, một thị trường, một snapshot. Mọi câu hỏi nhắc tới doanh thu, trung bình, nhóm-không-khuyến-mãi hay `promotion_id` đều bị chặn — **dù dữ liệu có sẵn**. Đây là khoảng trống **macro**, không phải khoảng trống **dữ liệu**, và phải phân biệt rõ với TC28 (profit) nơi từ chối là đúng tuyệt đối.

**Đối chiếu hai loại từ chối trong cùng một nhóm:**

| | Dữ liệu có? | Ví dụ | Hành động đúng |
|---|---|---|---|
| Từ chối **đúng** | Không | TC27, TC28, TC29 | giữ nguyên |
| Từ chối **quá tay** | **Có** | TC21, TC22, TC24, TC26, TC30 | thêm macro (§27, §29) |

Người dùng hiện nhận **cùng một dạng thông điệp** cho hai tình huống trái ngược nhau.

**Ca duy nhất phát số sai: TC25.** Đây là ưu tiên sửa số một của cả vòng — xem [`040826.md` §28](040826.md).

---

## Tổng kết đánh giá Testcase 31–40 (nhóm `error_and_limitations`)

| TC | Chấm | Gate | Ev | Ghi chú |
|---|---|---|---|---|
| 31 | **✅** | `allow` + sub-request | 3 | Phủ 07-01→07-03, 3 snapshot; từ chối forecast đúng |
| 32 | **✅** | `abstain A-MISSING-ADS` | 0 | Đúng; có thể bổ sung "220 listing Glad2Glow, 0 bật `is_ad`" |
| 33 | **✅** | `abstain A-MISSING-SKU` | 0 | Nêu đúng cả nguyên nhân lẫn bẫy `tier_variation` |
| 34 | ✗ | `clarify A22-ALIGN-DATE` | 0 | Cửa sổ 2 ngày tính được (1039/1145 listing); tiền đề "giảm" thật ra là **+11** |
| 35 | ✗ | `clarify A-AMBIGUOUS` | 0 | **Lỗi nặng nhất vòng này** — trả dầu gội Indonesia cho câu hỏi iPhone |
| 36 | ◐ | `clarify A16-CROSS-CURRENCY` | 0 | Chặn FX đúng; bỏ sót bẫy cộng 3 snapshot |
| 37 | **✅** | `abstain A-MISSING-INVENTORY` | 0 | Nêu đúng "cờ sold-out không đủ suy tồn thực" |
| 38 | ✗ | `abstain A19-PLAN` | 0 | Country + entity đều đúng rồi chết ở planner; corr thật = 0,0039 (n=2038) |
| 39 | ✗ | `clarify A22-ALIGN-MEASURE` | 0 | Từ chối đúng nhưng sai lý do; không nói luật cấm cộng cửa sổ trượt |
| 40 | ✗ | `clarify A-ANALYTICAL-AMBIGUITY` | 0 | Hỏi sai thứ; bẫy double-count 1,91× không được chạm |

**4 ✅ / 1 ◐ / 5 ✗.**

**Quan sát:** 4 ca ✅ đều là những ca mà **dữ liệu thật sự không tồn tại** (ads, SKU, tồn kho, khung thời gian) — hệ thống nhận diện giới hạn năng lực của mình rất tốt, thông điệp rõ và có gợi ý thay thế. Cả 5 ca ✗ đều là những ca **dữ liệu có sẵn**: `history_sold_decrease_flag` (TC3/38), 2 transition eligible (TC34), `product_name` toàn catalog (TC35), README quy tắc cấm cộng dồn (TC39), `product_categories_clean` (TC40).

**Ranh giới cần hệ thống tự nhìn thấy:** "tôi không có dữ liệu" vs "tôi chưa có đường tính". Hiện cả hai đều ra `clarify`/`abstain` với thông điệp không phân biệt được.

---

## Tổng kết toàn bộ TC1–TC40 (HEAD `56b14f8`, sau hardening A–Q)

| Nhóm | ✅ | ◐ | ✗ |
|---|---|---|---|
| `sales_decline` (TC1–10) | 3 | 5 | 2 |
| `similar_product` (TC11–20) | 5 | 5 | **0** |
| `promotion_effectiveness` (TC21–30) | 4 | 0 | **6** |
| `error_and_limitations` (TC31–40) | 4 | 1 | 5 |
| **Tổng** | **16** | **11** | **13** |

Gate: `clarify` 24 / `abstain` 10 / `allow` 6. **Chỉ 6/40 testcase sinh Evidence** (TC9, 17, 18, 23, 25, 31 — tổng 24 Evidence).

**Vòng hardening A–Q sửa được gì (đo thật, TC11–20):** vòng trước kết luận nhóm `similar_product` có *"recall thực tế 0% — 0/10 testcase tạo ra được dù chỉ một Evidence"*. Hiện tại nhóm này **không còn ca ✗ nào**: TC17 và TC18 sinh được 11 Evidence, TC14 chuyển từ "dầu hào MAGGI" sang `abstain` đúng, TC19 bắt được sentinel giá, TC1/TC2/TC5/TC11/TC12 trả về candidate **đúng shop và đúng thương hiệu** (trước đó là Bibica / Cyeecare / mất trắng entity).

**Ba lỗi lớn còn lại có chung một hình dạng.** §26 (resolver), §27 (macro promotion), §32 (planner fallback) đều là: *năng lực được định nghĩa bằng một danh sách đóng băng, và mọi thứ ngoài danh sách rơi vào một nhánh từ chối duy nhất, không phân biệt "dữ liệu không có" với "danh sách chưa phủ"*. Bộ 40 testcase phân biệt được hai thứ đó — **12 ca từ chối đúng vì dữ liệu thật sự không có, 13 ca hỏng vì danh sách chưa phủ dù dữ liệu có sẵn**.

**Root cause code-level, số đo và fix đề xuất cho từng lỗi:** [`docs/040826.md`](040826.md) §25–§35.
