# PHÂN TÍCH KẾT QUẢ TESTCASE NGÀY 28/07

## 1. Mục đích tài liệu

Tài liệu này phân tích kết quả trong `docs/Testcase result 287.md` theo nguyên
nhân kỹ thuật và nghiệp vụ. Mục tiêu là giúp agent tiếp theo:

- hiểu testcase nào thật sự đúng, sai hoặc chỉ an toàn một phần;
- không nhầm nhãn `PASSED` với việc đáp ứng đúng yêu cầu;
- xác định tầng gây lỗi trước khi đề xuất cách sửa;
- viết thêm kiểm thử hồi quy đúng với lỗi đã quan sát.

Tài liệu này không coi mọi đề xuất trong báo cáo QA là kết luận đã được chứng
minh. Những nguyên nhân chưa có thông báo lỗi gốc hoặc dữ liệu đầy đủ được đánh
dấu là **giả thuyết cần xác minh**.

## 2. Cách đọc kết quả

Trong báo cáo gốc:

- `PASSED` chỉ có nghĩa là hành động cuối là `ALLOW/VERIFIED`.
- `FAILED` chỉ có nghĩa là hành động cuối là `CLARIFY` hoặc `ABSTAIN`.

Quy ước đó không phản ánh trực tiếp tính đúng sai về nghiệp vụ. Một lần từ chối
có thể là hành vi đúng để bảo vệ hệ thống. Ngược lại, một lần `ALLOW` vẫn có thể
trả lời sai câu hỏi.

Kết quả cơ học của 40 testcase:

| Hành động cuối | Số lượng |
| --- | ---: |
| Cho phép trả lời | 5 |
| Yêu cầu làm rõ hoặc từ chối | 35 |

Trong 5 testcase được cho phép trả lời:

- TC25 và TC31 tương đối đúng về mục tiêu chính.
- TC19, TC23 và TC34 là các trường hợp cho phép trả lời nhưng nội dung sai hoặc
  làm mất điều kiện quan trọng của câu hỏi.

Vì vậy, không được dùng tỷ lệ `5/40` làm độ chính xác của hệ thống.

## 3. Tóm tắt theo mức độ

### 3.1. Nhóm xử lý đúng hoặc gần đúng về an toàn

Các testcase: TC6, TC7, TC13, TC16, TC18, TC20, TC25, TC27, TC28, TC29, TC31,
TC32, TC33, TC36, TC37.

Hệ thống đã nhận ra một hoặc nhiều giới hạn sau:

- không đủ dữ liệu để dự báo;
- không có dữ liệu cấp biến thể sản phẩm;
- không có giá vốn để tính lợi nhuận;
- không có dữ liệu quảng cáo hoặc tồn kho tuyệt đối;
- không được so sánh trực tiếp VND với IDR;
- không được bịa dữ liệu cho mã sản phẩm không tồn tại.

Một số testcase trong nhóm này vẫn còn lỗi câu chữ hoặc chưa đưa ra phương án
thay thế hữu ích, nhưng không tạo ra kết luận nghiệp vụ sai nghiêm trọng.

### 3.2. Nhóm an toàn nhưng chặn sai lý do hoặc thiếu chức năng

Các testcase: TC8, TC9, TC17, TC22, TC24, TC30, TC38, TC39.

Lớp kiểm tra đồng nhất A22 đã ngăn kế hoạch sai chạy xuống tầng dữ liệu. Tuy
nhiên, hệ thống chưa thực hiện đúng mục tiêu của câu hỏi. Đây không phải là kết
quả hoàn chỉnh, chỉ là trạng thái không gây hại.

### 3.3. Nhóm lỗi kỹ thuật hoặc chưa kiểm thử được mục tiêu chính

Các testcase: TC1-TC5, TC10-TC12, TC14-TC15, TC19, TC21, TC23, TC26, TC34,
TC35, TC40.

Các lỗi chính nằm ở kết nối mô hình, phân tích câu hỏi, phân giải thực thể, lập
kế hoạch, thứ tự kiểm tra và logic tìm kiếm sản phẩm.

## 4. Nhóm lỗi 1: Yêu cầu gửi đến Groq bị từ chối với mã 400

### Testcase liên quan

TC1-TC5, TC8, TC10-TC15, TC23, TC25, TC28, TC30, TC31 và TC40 có ghi nhận lỗi
Groq trong quá trình chạy. Bộ đếm cuối báo cáo tăng đến khoảng 21 lỗi
`BadRequestError:400`.

### Biểu hiện

- Lớp dùng mô hình không trả về kết quả phân tích có cấu trúc.
- Hệ thống chuyển sang bộ phân tích dự phòng.
- Nhiều câu hỏi hợp lệ bị hiểu sai thực thể hoặc sai mục đích.
- Báo cáo chỉ lưu loại lỗi và mã 400, không lưu phần giải thích chi tiết từ Groq.

### Vì sao đây là lỗi thật

Nếu thiếu `GROQ_API_KEY`, `GroqLLMClient` dừng ngay khi khởi tạo với thông báo
`Thiếu GROQ_API_KEY`. Vì hệ thống đã nhận `BadRequestError:400`, yêu cầu đã đi
đến nhà cung cấp và bị từ chối ở mức dữ liệu gửi lên.

Việc API key không xuất hiện trong báo cáo hoặc mã nguồn là đúng yêu cầu bảo
mật, không phải nguyên nhân của mã 400.

### Điều đã xác nhận

- Lỗi phát sinh trong lần gọi Groq thật.
- Mã trạng thái là 400.
- Sau lỗi, hệ thống thường dùng đường dự phòng.
- Code hiện rút gọn ngoại lệ thành `BadRequestError:400`, làm mất thông báo chi
  tiết cần để chẩn đoán.

### Giả thuyết cần xác minh

Các khả năng sau chưa được chứng minh bằng nội dung phản hồi gốc:

- `response_format` với JSON Schema chặt không được model hỗ trợ đầy đủ;
- tham số `reasoning_effort` không tương thích với model đang chạy;
- schema sinh từ Pydantic chứa cấu trúc Groq không chấp nhận;
- model cấu hình thực tế là `gpt-oss-20b` trong khi mặc định code là
  `gpt-oss-120b`, dẫn đến khác biệt khả năng;
- kích thước yêu cầu hoặc số lượng ràng buộc vượt giới hạn.

Không được chọn một giả thuyết để sửa khi chưa lấy được thông báo gốc.

### Dữ liệu agent sửa lỗi cần thu thập

- tên model thực tế của từng lần gọi;
- mục đích lần gọi: phân tích câu hỏi, lập kế hoạch hay tạo câu trả lời;
- phần thông báo lỗi từ Groq đã loại bỏ thông tin nhạy cảm;
- mã yêu cầu của Groq nếu có;
- có hay không dùng `response_format`;
- tên schema được gửi;
- kích thước đầu vào và số token ước tính;
- lần gọi lại không dùng `response_format` có được kích hoạt hay không.

### Điều kiện nghiệm thu

- Một lỗi 400 phải để lại nguyên nhân đủ cụ thể để phân loại, nhưng không lộ API
  key hoặc nội dung nhạy cảm.
- Các câu TC1, TC2, TC11 và TC12 phải đi qua lớp phân tích chính mà không rơi vào
  đường dự phòng.
- Nếu JSON có cấu trúc không được hỗ trợ, hệ thống phải thử đúng một đường thay
  thế có giới hạn và ghi rõ đường nào đã chạy.

## 5. Nhóm lỗi 2: Bộ phân tích dự phòng lấy sai thực thể

### Testcase liên quan

TC1-TC5, TC8, TC11, TC14 và TC15.

### Biểu hiện

Bộ phân tích dự phòng đưa gần như cả câu hỏi vào `entity_text`.

Ví dụ:

- TC1 lấy cả cụm chứa tên sản phẩm, tên shop và các từ nối.
- TC2 lấy cả phần hỏi về thay đổi giá.
- TC4 lấy thêm từ phủ định và phần cuối câu.
- TC11 lấy cả mục đích “để xem đối thủ đang bán giá bao nhiêu”.
- TC15 tạo một chuỗi khoảng 26 từ gồm kệ hàng, sản phẩm và shop.

### Vì sao sai

`entity_text` phải là tên hoặc mã dùng để tìm một thực thể. Khi chứa cả động từ,
điều kiện và phần giải thích, phép tìm kiếm không còn nhận được chuỗi gần với tên
sản phẩm trong dữ liệu.

Lỗi này tạo thành chuỗi:

1. Groq lỗi.
2. Bộ phân tích dự phòng lấy sai đoạn văn bản.
3. Công cụ tìm thực thể không tìm được kết quả rõ ràng.
4. Hệ thống báo `A-AMBIGUOUS`.
5. Tầng phân tích dữ liệu không được chạy.

Do đó, `A-AMBIGUOUS` trong các testcase này chỉ là hậu quả, không phải nguyên
nhân ban đầu.

### Trường hợp cho thấy hướng đúng

- TC16 lấy đúng cụm “bánh quy”.
- TC20 lấy đúng mã sản phẩm không tồn tại.
- TC34 lấy đúng mã sản phẩm.

Điều này cho thấy cách ưu tiên mã số đang hiệu quả, còn việc lấy tên tự do vẫn
chưa ổn định.

### Điều kiện nghiệm thu

- Mã sản phẩm và mã shop phải được tách trước tên tự do.
- Tên sản phẩm không được chứa phần hỏi nguyên nhân, thời gian, giá, dự báo hoặc
  câu phủ định.
- TC1, TC2, TC4, TC11, TC14 và TC15 cần có kiểm thử trực tiếp cho giá trị
  `entity_text`, không chỉ kiểm tra hành động cuối.

## 6. Nhóm lỗi 3: Phân loại sai mục đích câu hỏi

### Testcase liên quan

TC12 là trường hợp rõ nhất. Một số testcase mở như TC38 và TC39 cũng cho thấy
đường chọn chức năng chưa đầy đủ.

### Biểu hiện

TC12 hỏi về sản phẩm cạnh tranh tại Indonesia, nhưng hệ thống chuyển từ chức
năng tìm sản phẩm tương tự sang truy vấn phân tích mở. Sau đó hệ thống báo không
tìm được chỉ số để tính.

### Vì sao sai

Câu hỏi “có sản phẩm nào là đối thủ cạnh tranh” không cần một chỉ số tổng hợp.
Nó cần chức năng tìm sản phẩm tương tự. Thông báo “chưa ánh xạ được chỉ số” là
hậu quả của việc chọn sai chức năng.

### Điều kiện nghiệm thu

- Các cụm “đối thủ cạnh tranh”, “sản phẩm tương tự”, “tương đương” phải có kiểm
  thử phân loại riêng trong đường chính và đường dự phòng.
- Khi chức năng được chọn không yêu cầu chỉ số, hệ thống không được chuyển sang
  truy vấn mở chỉ vì không tìm thấy chỉ số.

## 7. Nhóm lỗi 4: Phân giải thực thể và thông báo mơ hồ

### Testcase liên quan

TC1, TC2, TC4, TC5, TC7, TC8, TC11, TC14, TC15 và TC16.

### Biểu hiện

Nhiều trường hợp khác nhau đều nhận cùng thông báo “Có nhiều listing gần giống”.
Trong thực tế có ít nhất ba tình huống:

- đầu vào quá rộng, ví dụ “sữa” hoặc “bánh quy”;
- đầu vào bị bộ phân tích làm nhiễu;
- không tìm thấy kết quả nào.

### Vì sao sai

Ba tình huống trên cần ba quyết định khác nhau:

- quá rộng: yêu cầu người dùng chọn cụ thể hơn;
- chuỗi bị nhiễu: lỗi nội bộ, cần thử lại bằng chuỗi đã làm sạch;
- không tồn tại: báo không tìm thấy.

TC20 đã phân biệt đúng trạng thái không tìm thấy bằng
`A-ENTITY-NOT-FOUND`. Cách phân biệt này cần được áp dụng nhất quán.

### Lưu ý quan trọng về đề xuất tự chọn sản phẩm

Báo cáo QA nhiều lần đề xuất tự chọn sản phẩm bán chạy nhất khi có nhiều kết
quả. Đây là đề xuất có rủi ro cao.

Tự chọn sản phẩm bán chạy nhất có thể âm thầm đổi đối tượng người dùng muốn hỏi.
Điều này mâu thuẫn với mục tiêu chống trả lời sai. Nếu cần hỗ trợ người dùng,
hệ thống nên trả về một danh sách ngắn gồm tên, shop và mã sản phẩm để người
dùng chọn. Chỉ được tự chọn khi có quy tắc nghiệp vụ được duyệt, độ tin cậy vượt
ngưỡng và câu trả lời nói rõ sản phẩm nào đã được chọn.

### Điều kiện nghiệm thu

- Phân biệt được `ambiguous`, `not_found` và `invalid_extraction`.
- Không tự chọn sản phẩm chỉ dựa trên số bán.
- Thông báo cho người dùng phải phù hợp đúng trạng thái.

## 8. Nhóm lỗi 5: Mâu thuẫn kiểu dữ liệu trong kế hoạch

### Testcase liên quan

TC3 và TC10.

### Biểu hiện

Pydantic từ chối các giá trị:

- `expected_cardinality = "many"` ở TC3;
- `expected_cardinality = "single"` ở TC10.

Kế hoạch bị hỏng trước khi tầng dữ liệu chạy.

### Vì sao sai

Phần sinh kế hoạch và phần kiểm tra kế hoạch đang dùng hai quy ước khác nhau.
Đây là lỗi hợp đồng nội bộ. Câu hỏi của người dùng không thể sửa được lỗi này.

Vòng sửa kế hoạch cũng không giải quyết được, cho thấy template hoặc lời nhắc
vẫn tiếp tục sinh giá trị không hợp lệ.

### Điều kiện nghiệm thu

- Chỉ có một nguồn định nghĩa tập giá trị hợp lệ.
- Template, lời nhắc, bộ lập kế hoạch dự phòng và Pydantic phải dùng cùng định
  nghĩa.
- Kiểm thử phải phủ cả đường sinh bằng mô hình và đường dự phòng.
- TC3 và TC10 không được trả lỗi schema ra giao diện người dùng.

## 9. Nhóm lỗi 6: A22 chưa bảo vệ đầy đủ các điều kiện của câu hỏi

### Những phần A22 đã làm đúng

A22 đã phát hiện:

- thay `monthly_sold` bằng `product_count` ở TC39;
- bỏ điều kiện nhóm không khuyến mãi hoặc yêu cầu doanh thu ở TC21, TC22, TC24;
- dùng chức năng chỉ hỗ trợ một thực thể cho câu hỏi có nhiều thực thể ở TC9 và
  TC17;
- bỏ một phần yêu cầu trong một số câu hỏi ghép.

Các lần chặn này ngăn tầng dữ liệu chạy sai.

### Lỗ hổng 1: Bỏ mất quốc gia ở TC23

Người dùng yêu cầu so sánh Việt Nam và Indonesia. Phần phân tích ban đầu đã có
`countries = ["vn", "id"]`, nhưng lời gọi công cụ chỉ còn `country = "vn"`.
Hệ thống vẫn cho phép trả lời.

Đây là lỗi mất điều kiện trong im lặng. Kết quả Việt Nam có thể đúng, nhưng không
trả lời câu hỏi so sánh hai nước.

### Lỗ hổng 2: Bỏ mất khoảng ngày ở TC34

Người dùng yêu cầu từ 01/07 đến 03/07. Kế hoạch chuyển thành một ngày 03/07, rồi
công cụ so sánh 02/07 với 03/07. Hệ thống vẫn xác minh thành công vì các con số
trong câu trả lời khớp với dữ liệu mà công cụ đã lấy.

Lớp xác minh mới chỉ kiểm tra “câu trả lời có khớp bằng chứng không”, chưa kiểm
tra “kế hoạch và bằng chứng có trả lời đúng câu hỏi gốc không”.

### Lỗ hổng 3: Phép tính và chiều nhóm

TC39 cho thấy A22 đã bắt được việc thay chỉ số, nhưng chưa có quy tắc nghiệp vụ
trực tiếp cho yêu cầu cộng sai `monthly_sold`. TC40 cũng chưa chạm được quy tắc
không cộng dồn các kệ nội bộ.

### Các trường cần được giữ xuyên suốt

- danh sách quốc gia;
- ngày bắt đầu và ngày kết thúc;
- số lượng thực thể;
- chỉ số được hỏi;
- phép tính như tổng, trung bình, trung vị hoặc chênh lệch;
- chiều phân nhóm;
- điều kiện lọc;
- từng phần của câu hỏi ghép.

### Điều kiện nghiệm thu

- Nếu request có hai quốc gia, kế hoạch một quốc gia phải bị chặn hoặc sửa.
- Nếu request có hai mốc ngày, kế hoạch một mốc ngày phải bị chặn hoặc sửa.
- TC23 và TC34 bắt buộc không được `ALLOW` với kế hoạch hiện tại.
- Kiểm thử phải so sánh request với plan trước khi chạy công cụ, không chỉ so
  câu trả lời với bằng chứng sau khi chạy.

## 10. Nhóm lỗi 7: Thứ tự kiểm tra điều kiện chưa hợp lý

### Testcase liên quan

TC35 và TC40. TC3 cũng cho thấy kiểm tra quốc gia có thể che mất lỗi sâu hơn.

### Biểu hiện

- TC35 hỏi về iPhone ngoài phạm vi dữ liệu nhưng nhận thông báo chọn VN hoặc ID.
- TC40 hỏi phép cộng sai trên kệ nội bộ nhưng bị chặn trước vì thiếu quốc gia.

### Vì sao sai

Kiểm tra tiền tệ đang chạy trước khi hệ thống hiểu đầy đủ lĩnh vực và phép tính
người dùng yêu cầu. Điều này tạo thông báo không liên quan và làm testcase không
chạm được quy tắc nghiệp vụ cần kiểm tra.

### Thứ tự hợp lý cần được kiểm chứng

1. Xác định câu hỏi có thuộc phạm vi dữ liệu hay không.
2. Xác định mục đích và thực thể.
3. Phát hiện phép tính bị cấm hoặc khả năng không được hỗ trợ.
4. Kiểm tra quốc gia và tiền tệ nếu phép tính thật sự cần tiền.
5. Kiểm tra sự đồng nhất giữa câu hỏi và kế hoạch.
6. Chạy công cụ dữ liệu.

Thứ tự cuối cùng cần được đội kiến trúc duyệt, nhưng lỗi hiện tại chứng minh
kiểm tra tiền tệ không nên luôn đứng đầu.

### Điều kiện nghiệm thu

- TC35 phải báo ngoài phạm vi dữ liệu, không báo lỗi tiền tệ.
- TC40 phải nhận diện nguy cơ đếm trùng trước hoặc đồng thời với yêu cầu bổ sung
  quốc gia.

## 11. Nhóm lỗi 8: Thiếu chức năng phân tích phù hợp

### Testcase liên quan

TC9, TC17, TC21, TC22, TC24, TC26, TC30, TC38 và TC39.

### Các khoảng trống chức năng

- So sánh trực tiếp hai sản phẩm cụ thể.
- So sánh hai hoặc nhiều quốc gia trong chức năng voucher.
- Phân tích đồng biến giữa hai chỉ số mà không kết luận nhân quả.
- Xử lý nhóm không khuyến mãi.
- Tính doanh thu trung vị theo đúng nhóm.
- Nhận diện phép cộng không hợp lệ trên chỉ số cửa sổ trượt.
- Nhận diện đếm trùng do một sản phẩm nằm trên nhiều kệ nội bộ.
- Xử lý mã chiến dịch hoặc mã khuyến mãi không hợp lệ.

### Vì sao cần phân biệt với lỗi kỹ thuật

Nếu hệ thống chưa được thiết kế để làm một phép phân tích, việc từ chối có thể là
đúng. Không nên sửa bằng cách mở rộng một chức năng cũ cho nhận mọi loại tham số,
vì dễ làm mất các bảo đảm hiện tại.

Mỗi chức năng mới cần:

- đầu vào được định kiểu rõ;
- giới hạn số thực thể và quốc gia;
- chỉ số và phép tính được phép;
- các câu kết luận bị cấm;
- kiểm thử độc lập cho trường hợp thiếu dữ liệu.

## 12. Nhóm lỗi 9: Tìm sản phẩm tương tự sai nghiêm trọng

### Testcase liên quan

TC19.

### Biểu hiện

Người dùng hỏi đối thủ của quạt mini cầm tay. Hệ thống trả về collagen, kem
dưỡng da, bộ mỹ phẩm và mền gối. Các kết quả có cùng điểm tương tự 0,855 vì cùng
chứa cụm “quà tặng không bán”.

### Vì sao sai

Thuật toán đang cho từ khóa chung ảnh hưởng quá mạnh và không bắt buộc cùng danh
mục sản phẩm. “Quà tặng không bán” mô tả trạng thái của sản phẩm, không phải đặc
tính dùng để xác định sản phẩm tương tự.

Ngoài ra, câu trả lời không cảnh báo rằng mức giá của sản phẩm quà tặng có thể
là giá kỹ thuật, mặc dù đó là mục tiêu chính của testcase.

TC19 là trường hợp nguy hiểm vì được đánh dấu `PASSED` và có trích dẫn bằng
chứng, nhưng kết quả vẫn sai hoàn toàn về ý nghĩa.

### Điểm chưa được quyết định

Báo cáo triển khai trước đó ghi rõ dữ liệu hiện tại đặt
`price_sentinel_flag=False` và TC19 cần nhãn do người phụ trách nghiệp vụ duyệt.
Không được tự đổi dữ liệu chuẩn chỉ để làm testcase đạt.

### Điều kiện nghiệm thu

- Sản phẩm tương tự phải có điều kiện bắt buộc về danh mục chuẩn hoặc quy tắc
  tương đương danh mục được phê duyệt.
- Các cụm trạng thái như “quà tặng không bán” không được chi phối điểm tương tự.
- Nếu chưa có nhãn giá kỹ thuật được duyệt, hệ thống phải nói chưa đủ bằng chứng
  thay vì tự khẳng định.
- TC19 không được `ALLOW` với danh sách kết quả hiện tại.

## 13. Nhóm lỗi 10: Tạo câu trả lời và kiểm tra câu trả lời

### Testcase liên quan

TC23, TC25, TC31, TC38 và TC39; lỗi câu chữ xuất hiện rộng hơn ở nhiều testcase.

### Lỗi gắn bằng chứng

Ở TC23 và TC31, mô hình tạo câu trả lời bị lớp kiểm tra từ chối, sau đó hệ thống
đưa chuỗi dữ liệu thô ra giao diện.

TC31 còn cho thấy lớp kiểm tra có thể coi các con số người dùng đã nêu, như tháng
6 và tháng 8, là số do mô hình bịa ra vì các số đó không có trong bằng chứng
truy xuất.

### Lỗi câu trả lời dự phòng

Người dùng nhìn thấy các thuật ngữ nội bộ:

- `artifact`;
- `monthly_sold_proxy`;
- `semantic catalog`;
- `expected_cardinality`;
- mã quy tắc A19, A22;
- chi tiết hợp đồng nội bộ.

TC38 còn có câu chưa điền biến: “Chưa có analytical template cho:”.

### Vì sao sai

Nhật ký kỹ thuật và câu trả lời cho người dùng là hai sản phẩm khác nhau. Nhật
ký cần đủ chi tiết để sửa lỗi; câu trả lời cần ngắn, đúng ngữ cảnh và không lộ
cấu trúc nội bộ.

### Điều kiện nghiệm thu

- Các số và thực thể xuất hiện nguyên văn trong câu hỏi phải được phép lặp lại,
  nhưng không được xem là bằng chứng cho một kết luận mới.
- Khi tạo câu trả lời thất bại, mẫu dự phòng phải là câu hoàn chỉnh dành cho
  người dùng.
- Không đưa tên biến, mã quy tắc hoặc tên lớp nội bộ ra giao diện.
- Mọi mẫu câu có biến phải có kiểm thử cho trường hợp biến thiếu.

## 14. Nhóm lỗi 11: Dữ liệu kiểm thử và tiêu chí đánh giá chưa nhất quán

### TC34 có tiền đề không khớp dữ liệu

Báo cáo triển khai ngày 26/07 ghi rằng sản phẩm trong TC34 thực tế có đủ ba
snapshot. Trong khi mô tả testcase ngày 28/07 yêu cầu phát hiện thiếu ngày
02/07.

Nếu dữ liệu có đủ ngày, testcase hiện tại không thể dùng để kiểm tra lỗi đứt
quãng. Cần chọn một sản phẩm thật sự thiếu ngày hoặc tạo bộ dữ liệu kiểm thử
riêng có chủ đích.

### TC19 chưa có nhãn nghiệp vụ được duyệt

Việc coi giá 410.000 đồng là giá kỹ thuật hiện vẫn là nhận định cần người phụ
trách dữ liệu xác nhận. Không được tự đặt cờ chỉ dựa trên tên sản phẩm hoặc cảm
giác giá bất thường.

### Nhãn `PASSED/FAILED` gây hiểu nhầm

TC19, TC23 và TC34 cho thấy `ALLOW/VERIFIED` không đủ để kết luận testcase đạt.
Hệ thống đánh giá cần ít nhất ba lớp kết quả:

1. Hành động cuối có đúng loại không.
2. Kế hoạch có giữ đủ điều kiện của câu hỏi không.
3. Nội dung trả lời có đạt yêu cầu và không vi phạm điều cấm không.

## 15. Danh sách testcase cần tạo kiểm thử hồi quy trước

### Ưu tiên 0: Có thể trả lời sai mà vẫn được cho phép

| Testcase | Lỗi phải bắt |
| --- | --- |
| TC19 | Kết quả tương tự sai danh mục và bỏ cảnh báo giá kỹ thuật |
| TC23 | Bỏ mất Indonesia nhưng vẫn trả kết quả Việt Nam |
| TC34 | Bỏ ngày 01/07 và tự đổi khoảng so sánh |

### Ưu tiên 0: Lỗi làm hỏng toàn bộ đường xử lý

| Testcase | Lỗi phải bắt |
| --- | --- |
| TC1, TC2, TC11, TC12 | Groq 400 dẫn đến phân tích dự phòng sai |
| TC3, TC10 | `expected_cardinality` không hợp lệ |

### Ưu tiên 1: Chặn sai lý do

| Testcase | Lỗi phải bắt |
| --- | --- |
| TC35 | Ngoài phạm vi nhưng báo lỗi tiền tệ |
| TC40 | Bẫy đếm trùng bị che bởi kiểm tra quốc gia |
| TC39 | Chưa có quy tắc trực tiếp cho cộng sai `monthly_sold` |

### Ưu tiên 1: Chức năng hợp lệ chưa chạy được

| Testcase | Lỗi phải bắt |
| --- | --- |
| TC4, TC5 | Không kiểm thử được bẫy nhân quả và tồn kho |
| TC11-TC15 | Nhóm tìm sản phẩm tương tự bị chặn ở bộ phân tích |
| TC21 | Yêu cầu so sánh hợp lệ vượt khả năng chức năng hiện tại |

## 16. Thứ tự chẩn đoán đề nghị cho agent tiếp theo

1. Tái hiện một lỗi Groq 400 với một câu ngắn và lưu thông báo lỗi đã loại bỏ bí
   mật.
2. Xác định lỗi nằm ở model, tham số, `response_format` hay schema.
3. Chạy lại TC1, TC2, TC11 và TC12 để kiểm tra lớp phân tích chính.
4. Sửa và kiểm thử hợp đồng `expected_cardinality`.
5. Bổ sung kiểm tra đồng nhất cho quốc gia và khoảng ngày.
6. Khóa ba trường hợp cho phép sai TC19, TC23 và TC34 bằng kiểm thử hồi quy.
7. Sửa thứ tự kiểm tra cho TC35 và TC40.
8. Sau khi đường xử lý ổn định, mới đánh giá các chức năng còn thiếu ở tầng dữ
   liệu.
9. Cuối cùng mới chỉnh câu chữ giao diện.

Không nên bắt đầu bằng việc nới lỏng A22 hoặc tự chọn sản phẩm phổ biến nhất.
Hai cách đó có thể làm số lượng câu trả lời tăng lên nhưng đồng thời làm tăng
nguy cơ trả lời sai trong im lặng.

## 17. Kết luận

Bản cập nhật kiến trúc đã cải thiện đáng kể khả năng chặn kế hoạch không đồng
nhất và từ chối yêu cầu vượt phạm vi dữ liệu. Tuy nhiên, kết quả ngày 28/07 chưa
đủ để kết luận hệ thống sẵn sàng sử dụng thực tế.

Ba vấn đề quan trọng nhất là:

1. Đường gọi Groq không ổn định và thiếu thông tin chẩn đoán.
2. Bộ phân tích dự phòng làm hỏng thực thể và mục đích câu hỏi.
3. A22 chưa bảo vệ quốc gia và khoảng thời gian, dẫn đến TC23 và TC34 trả lời
   sai nhưng vẫn được xác minh.

Agent tiếp theo cần ưu tiên loại bỏ các trường hợp “trả lời sai nhưng vẫn được
cho phép” trước khi mở rộng thêm chức năng phân tích.
