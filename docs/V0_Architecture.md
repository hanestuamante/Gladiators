# Agent Architecture V0 (Historical)

> **Status:** Historical / superseded V0 design.
> Tài liệu này không phải đặc tả kiến trúc hiện hành. Không tái sử dụng các assumption hoặc feature cũ nếu chưa đối chiếu Data Context và pipeline hiện tại.

Nguồn hiện hành về dữ liệu là [Data Context and Analysis Notes](Data_Context_and_Analysis_Notes.md), [pipeline contract](data-pipeline.md) và các quality artifacts trong `data/processed`. Tài liệu này chỉ lưu lại mục tiêu, quyết định và bài học của thiết kế V0.

## 1. Bài toán và mục tiêu lịch sử

V0 đã được viết để phác thảo cách một AI Agent có thể hiểu quan hệ giữa listing, shop, brand, category, promotion, voucher, content và sales proxy trong bộ dữ liệu Shopee. Thiết kế khi đó hướng tới ba nhóm câu hỏi:

- giải thích mô tả vì sao sales proxy của một listing thay đổi giữa các snapshot;
- tìm các listing tương tự; câu hỏi gốc dùng từ “SKU”, dù dữ liệu không hỗ trợ grain SKU;
- so sánh mô tả các listing có tín hiệu promotion hoặc voucher.

V0 đã theo đuổi ba mục tiêu:

1. Tạo một lớp ngữ nghĩa để Agent không phải tự suy diễn trực tiếp từ CSV.
2. Biểu diễn quan hệ giữa các thực thể eCommerce ở mức khái niệm.
3. Trả lời bằng evidence có scope, phép tính có thể chạy lại và limitation rõ ràng.

Các mục tiêu này là bối cảnh lịch sử, không phải cam kết rằng repo hiện đã triển khai kiến trúc đó.

## 2. Disposition của nội dung V0 cũ

| Section cũ | KEEP IN V0 | MOVE/MERGE | DELETE | CORRECT |
|---|---|---|---|---|
| 1–2. Bối cảnh và mục tiêu | Mục tiêu, use case lịch sử | — | Folder tree và giọng hiện tại | Dùng ngôn ngữ mô tả, không causal |
| 3, 5, 6, 8. Entity, dataset, feature, limitation | Bài học rằng semantics cần được định nghĩa | Data Context | Data dictionary lặp lại | Grain, key, metric, voucher, currency và image semantics |
| 4 và 9. KG và kiến trúc | KG, semantic, retrieval, analysis ở mức khái quát | Join và schema sang Data Context | Mapping chi tiết không còn đúng | Identity và snapshot scope |
| 7. Workflow theo câu hỏi | Ba intent lịch sử | Câu hỏi phân tích và guardrail sang Data Context | SKU proxy và promo decomposition | Listing similarity và descriptive comparison |
| 10. Roadmap | — | — | Roadmap triển khai cũ | — |
| 11–14. Repo tham khảo | Ý tưởng đã ảnh hưởng V0 | Một bảng ngắn | Thống kê, dependency, pipeline và folder đề xuất dài | Không trình bày inspiration như implementation |
| 15–16. Kết luận và workflow | Workflow, evidence và verification principles | Contract chi tiết sang tài liệu Agent | Nội dung trùng và roadmap MCP | Bảng assumption toàn diện và lý do superseded |

## 3. Các quyết định kiến trúc V0 có giá trị lịch sử

### 3.1. Semantic layer và Knowledge Graph

V0 đã chọn cách nhìn dữ liệu eCommerce như một mạng quan hệ thay vì một tập CSV rời rạc. Semantic layer dự kiến tách ba loại khái niệm:

- entity và relationship;
- metric và quy tắc diễn giải;
- nguồn evidence và limitation.

Knowledge Graph trong V0 chủ yếu là abstraction để Agent hiểu rằng listing có quan hệ với shop, brand, hai hệ category, content và các quan sát theo thời gian. Ý tưởng tách platform category khỏi shop category là một quyết định hữu ích. Tuy nhiên, node, key và edge cụ thể trong bản cũ có nhiều lỗi về grain và snapshot scope; chúng không còn là schema có thể triển khai.

### 3.2. Skill và retrieval theo intent

V0 đã đề xuất chia năng lực Agent theo intent thay vì dùng một prompt lớn. Các nhóm skill lịch sử bao gồm tra cứu entity, so sánh snapshot, tìm listing tương tự, phân tích mô tả promotion và kiểm tra câu trả lời.

Retrieval dự kiến chỉ nạp context liên quan tới câu hỏi, giới hạn số dòng và giữ scope. Quyết định này nhằm giảm việc Agent suy diễn từ toàn bộ CSV hoặc từ tài liệu không liên quan.

### 3.3. Deterministic analysis và answer layer

V0 đã tách phép tính khỏi phần diễn giải: median, change, rank, distance và group-by dự kiến được thực hiện bằng hàm có thể chạy lại; LLM chỉ tổng hợp evidence thành câu trả lời. Cách tách này giúp truy vết lỗi về data, calculation hoặc explanation.

### 3.4. MCP ở vai trò adapter

MCP trong V0 chỉ được hình dung như adapter read-only bao quanh các analysis function đã kiểm chứng. Tool dự kiến có input/output định kiểu, scope và giới hạn kết quả; không nhận arbitrary SQL hoặc arbitrary file path. MCP không được xem là nơi chứa logic nghiệp vụ riêng.

## 4. Workflow V0 cô đọng

```text
Question
  -> Intent và entity resolution
  -> Scope validation
  -> Scoped retrieval
  -> Deterministic analysis
  -> Evidence assembly
  -> Descriptive explanation
  -> Verification
  -> Final answer hoặc insufficient_evidence
```

V0 đã yêu cầu xác định scope trước khi phân tích, không tự chọn candidate đầu tiên khi entity mơ hồ và không để LLM tự tính số trong văn bản. Chi tiết contract và test không được lặp lại ở đây; chúng nằm trong tài liệu Agent được dẫn ở cuối.

## 5. Nguyên tắc evidence và verification có thể tái sử dụng

1. Mỗi kết quả phải nêu nguồn, cột, filter, dataset scope và ngày quan sát.
2. Phép tính phải có thể chạy lại và phải chọn đúng grain trước khi aggregate.
3. Entity mơ hồ hoặc thiếu snapshot phải trả trạng thái thiếu evidence thay vì đoán.
4. Evidence phải được xếp hạng theo mức hỗ trợ, không theo một câu chuyện nghe hợp lý.
5. Sales, revenue, promotion và similarity phải dùng đúng tên proxy và limitation.
6. So sánh quan sát không được đổi thành kết luận causal hoặc uplift.
7. Bước verification phải kiểm tra entity, scope, unit, join, calculation, provenance và causal language.

Những nguyên tắc này là bài học thiết kế của V0. Định nghĩa dữ liệu để áp dụng chúng phải lấy từ Data Context và audit hiện hành.

## 6. Nguồn cảm hứng bên ngoài

| Repo | Ý tưởng V0 đã tham khảo | Vì sao hiện không dùng |
|---|---|---|
| `BanMartinCode/b01-gbrain-ecommerce` | Commerce graph, skill modules và structured answers | Là playbook tổng quát, không phải pipeline hay source of truth cho dữ liệu Shopee của repo |
| `OpenBGBenchmark/OpenBG-IMG` | Multimodal KG và link prediction | Là benchmark khác format; repo hiện chưa có visual feature hoặc embedding đáng tin cậy để áp dụng |
| `OpenBGBenchmark/OpenBG-Align` | Text-image product matching | Không có image coverage, label và same-product ground truth phù hợp; pipeline và dependency riêng |
| `vercel/vercel-plugin` | Relational documentation, scoped context, typed tools, read-only MCP và verification | Là pattern cho coding agent, không phải commerce analysis engine và không được tích hợp trực tiếp |

## 7. Known invalid or superseded assumptions

Bảng này thay thế mọi claim cũ trong V0. Các token hoặc công thức sai chỉ được giữ ở đây để giải thích vì sao không được tái sử dụng.

| Assumption hoặc pattern cũ | Vì sao invalid hoặc superseded | Cách hiểu hiện hành |
|---|---|---|
| Xem mỗi dòng là một Product hoặc SKU độc lập | Dataset processed ở grain listing snapshot, không phải product master hay SKU | Listing dùng key `country_code + shop_id + item_id`; snapshot thêm `date` |
| `Product(item_id)` là identity đủ | `item_id` không mang đầy đủ market và seller scope | Không resolve hoặc join listing nếu thiếu `country_code + shop_id`; thêm `date` cho quan sát |
| Dùng `item_id + tier_variation_*` làm SKU proxy có thể theo dõi | Không có `sku_id`, `model_id`, variation-level price, stock hoặc sales | Không tạo SKU proxy; use case phù hợp chỉ là listing-level similarity |
| Node `SKU_or_Variant` và edge `HAS_VARIATION` phản ánh entity thật | Variation text không tạo một entity có identity và metric riêng | Xóa khỏi graph V0; chỉ mô tả field variation theo semantics trong Data Context |
| `Product -> Promotion` hoặc `Product -> Voucher` là quan hệ không đổi theo thời gian | Promotion và voucher được quan sát tại listing snapshot | Nếu nhắc quan hệ lịch sử, scope phải gồm `country_code + shop_id + item_id + date`; V0 không còn cung cấp executable mapping |
| `has_promo = discount_percent > 0` | `discount_percent` phản ánh tổng markdown giữa giá gốc và giá hiển thị, không chứng minh một promotion độc lập | Không tạo cờ này từ `discount_percent` |
| `has_voucher` có thể suy ra từ mọi nội dung trong `vouchers` | `vouchers` là label hoặc UI hỗn hợp, không đồng nghĩa monetary voucher có cấu trúc | Chỉ dùng `has_structured_voucher = voucher_discount > 0` khi cần cờ có cấu trúc |
| `promo_group = no promo / promo only / voucher only / voucher + promo` | Các field hiện có không tách được bốn cơ chế này; `promotion_id != 0` cũng không chứng minh discount do promotion tạo ra | Không tạo `promo_group`; chỉ mô tả từng population và filter quan sát đã kiểm định |
| Nhóm có structured voucher và `promotion_id != 0` là “voucher + promo” | Đây chỉ là giao của hai điều kiện field, không phải bằng chứng về hai cơ chế discount | Gọi đúng là subgroup có structured voucher và `promotion_id != 0` |
| `price` là checkout price sau mọi ưu đãi và có thể tiếp tục trừ voucher | Dataset chỉ cho biết final displayed hoặc exported price tại snapshot | Không khẳng định checkout price và không trừ `voucher_discount` thêm lần nữa |
| `price_before_promo` có semantics nguồn đã xác nhận | Ý nghĩa nghiệp vụ của field chưa được xác nhận từ source | Chỉ mô tả hành vi quan sát và không suy đoán nguyên nhân mismatch |
| Platform category join chỉ bằng `products.catid = category_platform.category_id` | Category ID cần market scope; shorthand này có thể join nhầm quốc gia | Join thêm `products.country_code = category_platform.path_country_code` và dùng phần tử phù hợp của `catid/global_catids` |
| `catid` và `global_catids` luôn đại diện cùng một category hoặc leaf | Hai field thể hiện các mức khác nhau trong category path và cần được kiểm tra trên artifact | Không gọi `catid` là leaf; chọn đúng phần tử `global_catids` cho mức category cần phân tích |
| `history_sold_value` là cumulative sales chính xác và luôn tăng | Đây chỉ là cumulative-sales proxy kỳ vọng; audit đã phát hiện các transition giảm bất thường | Nêu anomaly và không dùng như transaction ledger |
| `monthly_sold_value` có thể cộng qua ba snapshot hoặc lấy diff làm daily sales | Đây là recent-window proxy được quan sát lặp lại | Chọn snapshot/date phù hợp; không cộng toàn panel và không lấy diff làm daily sales |
| `price * monthly_sold_value` là GMV, net revenue hoặc profit | Không có order ledger, cost, margin hay checkout price | Chỉ gọi là revenue proxy tại một snapshot, với market và unit được nêu rõ |
| Unit cố định `VND_proxy` dùng được cho mọi country | Dataset không có currency field hoặc FX normalization; VN và ID dùng local-market unit khác nhau | Không cộng hoặc so sánh giá, voucher hay revenue tuyệt đối giữa market nếu chưa quy đổi |
| `shop_info` là thuộc tính đồng thời với mọi product snapshot | Shop table chỉ có snapshot mới nhất trong phạm vi audit | Khi enrich ngày trước, gọi là latest hoặc static shop enrichment |
| Repo chỉ có image URL, hoặc ngược lại đã có sẵn local image và embedding | Repo có downloader và manifest, nhưng image files không được version-control và chưa có visual feature đáng tin cậy | Không giả định file ảnh tồn tại; mọi image claim cần coverage, model, version và timestamp |
| Từ association có thể kết luận promotion, giá, content hoặc rating “gây ra” thay đổi sales | Dữ liệu quan sát ngắn hạn không có experiment, control hay order-level evidence | Dùng “liên hệ”, “so sánh mô tả” hoặc “possible explanation” |
| File processed nằm ở `Preprocessing/product_dataset_ready.csv` | Đây là đường dẫn sai | Artifact nằm dưới `data/processed/`; đường dẫn và schema hiện hành phải tra trong Data Context |
| Các folder như `KnowledgeGraph/`, `Similarity/` hoặc bộ `Agent/skills` đề xuất đã tồn tại | Đây từng là roadmap giả định, không phải filesystem fact | Không giữ folder tree giả định và không dùng V0 để thiết kế V1 |

## 8. Vì sao V0 bị supersede

V0 không còn là đặc tả hiện hành vì:

- audit sau đó đã xác nhận grain là listing snapshot, panel không hoàn toàn cân bằng và một số sales proxy có anomaly;
- promotion, voucher và discount không hỗ trợ decomposition mà V0 từng giả định;
- category join cần country scope, còn currency và shop enrichment cần limitation rõ hơn;
- trạng thái image pipeline và filesystem đã thay đổi so với các giả định trong roadmap;
- data dictionary, workflow contract và evaluation detail đã có nguồn chuyên trách, nên việc lặp lại trong V0 dễ tạo hai source of truth;
- phần đối chiếu repo ngoài và roadmap cũ dài hơn giá trị lịch sử mà chúng mang lại.

Tài liệu này không đề xuất kiến trúc V1 hoặc thay thế kiến trúc hiện hành. Nó chỉ ghi lại V0 để truy vết quyết định và tránh tái sử dụng các assumption đã bị bác bỏ.

## 9. Tài liệu cần dùng thay cho V0

- [Data Context and Analysis Notes](Data_Context_and_Analysis_Notes.md): source of truth tổng hợp về dataset, key, semantics, data quality và analysis guardrails.
- [Pipeline contract](data-pipeline.md): xử lý dữ liệu, metric và quality policy hiện hành.
- [Code graph](codegraph.md): luồng gọi hàm và dependency metric có thể triển khai.

Khi các nguồn này mâu thuẫn, phải ưu tiên artifact hiện tại và audit, nêu rõ filter, grain cùng dataset scope, và không dùng V0 để tự chọn một cách diễn giải.
