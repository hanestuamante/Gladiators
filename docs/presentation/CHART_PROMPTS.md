# Prompt vẽ 5 chart — bản dùng cho người vẽ

> **Cách dùng:** mỗi mục dưới đây là một prompt độc lập. Copy nguyên khối trong
> ```` ``` ```` và đưa cho agent vẽ hình. Không cần đọc mục nào khác.
>
> **Nguyên tắc soạn:** mọi nhãn trên hình đều tự giải thích. Không mã nội bộ,
> không tên file mã nguồn, không thuật ngữ chỉ người trong dự án mới hiểu. Người
> lần đầu nghe về dự án vẫn nắm được chi tiết kỹ thuật.

**Bối cảnh chung để người vẽ hiểu đang vẽ gì:**
Đây là một hệ thống hỏi đáp bằng ngôn ngữ tự nhiên trên dữ liệu thương mại điện
tử. Người dùng hỏi tiếng Việt, hệ thống trả lời bằng số liệu. Điểm khác biệt của
nó: hệ thống **thà từ chối còn hơn trả lời sai**, và mọi con số hiển thị đều phải
truy ngược được về dữ liệu gốc.

| Chart | Nội dung | Thông điệp chính |
| ---: | --- | --- |
| 1 | Đường đi của một câu hỏi qua 9 chặng | mọi chặng đều có quyền từ chối |
| 2 | Ba lớp kiểm tra và khe hở giữa chúng | hai lớp cùng "pass" mà kết quả vẫn sai |
| 3 | Tầng nối định nghĩa với dữ liệu thật | khai báo sai thì chương trình không chạy |
| 4 | Kết quả trước/sau đợt sửa lỗi | hai chỉ số xấu về 0 |
| 5 | So sánh chế độ có AI và không AI | đắt hơn 438 lần và kém chính xác hơn |

---

## CHART 1 — Đường đi của một câu hỏi

```
Vẽ một sơ đồ luồng dọc (vertical flowchart) mô tả đường đi của một câu hỏi qua
9 chặng xử lý trong một hệ thống hỏi đáp dữ liệu.

PHONG CÁCH: bản vẽ kỹ thuật cao cấp, tối giản, sang trọng. Nền trắng ngà
#FAFAF8. Đường nét mảnh, sắc, 1.5px. KHÔNG dùng icon hoạt hình, KHÔNG gradient
loè loẹt, KHÔNG hiệu ứng 3D. Bảng màu: navy đậm #1B2A4A (khối chính), xanh mòng
két #2E7D8F (nhánh thành công), hổ phách #C96F1E (nhánh hỏi lại), đỏ trầm
#A6333F (nhánh từ chối), xám nhạt #E8E6E1 (đường phụ). Font sans-serif hình học
(Inter, Manrope hoặc tương đương). Tiếng Việt đủ dấu. Tỷ lệ 16:9.

CỘT GIỮA — 9 khối chữ nhật bo góc nhẹ, xếp dọc, nối bằng mũi tên hướng xuống.
Mỗi khối chia làm HAI PHẦN TRÁI–PHẢI rõ rệt:

  · Nửa trái  (nền navy nhạt): số thứ tự lớn + tên chặng in đậm + việc nó làm
  · Nửa phải  (nền đỏ trầm mờ 12%, viền trái đỏ mảnh): CA HỎNG THẬT mà chặng
              này ngăn được, mở đầu bằng chữ "Nếu thiếu:" in nghiêng màu đỏ trầm

Đây là phần quan trọng nhất của hình. Người xem phải đọc được ngay mỗi chặng
tồn tại để chặn CHÍNH XÁC lỗi nào, chứ không phải "một pipeline 9 bước".

  1  HIỂU CÂU HỎI                      │ Nếu thiếu: chữ "giảm giá" có chứa chữ
     tách ý định, tên sản phẩm,        │ "giá" bên trong → hệ đọc thành chỉ số
     thị trường, khoảng ngày           │ GIÁ BÁN và trả lời một câu hoàn toàn khác

  2  CHỌN NGUỒN DỮ LIỆU                │ Nếu thiếu: hỏi giá của đối thủ ngoài sàn
     dữ liệu nội bộ hay                │ → dữ liệu không hề có, hệ sẽ bịa ra một
     thông tin bên ngoài               │ con số nghe hợp lý

  3  XÁC ĐỊNH SẢN PHẨM ĐƯỢC HỎI        │ Nếu thiếu: nhiều sản phẩm tên gần giống
     khớp theo mã, rồi theo tên,       │ nhau → chọn đại một cái là trả lời số
     rồi theo độ tương đồng            │ liệu của SẢN PHẨM KHÁC

  4  CỔNG KIỂM TRA TRƯỚC               │ Nếu thiếu: hỏi lợi nhuận hay tồn kho →
     có đủ điều kiện để                │ dữ liệu công khai của sàn KHÔNG CÓ những
     trả lời không                     │ cột đó, nhưng hệ vẫn cố ghép đại

  5  LẬP KẾ HOẠCH TRUY VẤN VÀ CHẠY     │ Nếu thiếu: "lượt bán tháng" là số sàn
     sinh câu truy vấn,                │ hiển thị sẵn — cộng nó qua 3 ngày là ĐẾM
     chạy ở chế độ chỉ đọc             │ TRÙNG. Giá 999.999.999 là rác, lấy làm
                                       │ giá cao nhất là sai

  6  GHI BẰNG CHỨNG                    │ Nếu thiếu: 40 sản phẩm không đo được
     mỗi con số gắn với                │ lượt bán bị loại ÂM THẦM khỏi phép đếm →
     dòng dữ liệu tạo ra nó            │ kết quả thiếu 40 mà không ai biết

  7  SOẠN CÂU TRẢ LỜI                  │ Nếu thiếu: hệ nói "doanh số giảm VÌ hạ
     diễn đạt kết quả bằng             │ giá" trong khi dữ liệu chỉ cho thấy hai
     ngôn ngữ người dùng               │ việc xảy ra cùng lúc, không chứng minh
                                       │ được nhân quả

  8  ĐỐI CHIẾU SỐ VỚI BẰNG CHỨNG       │ Nếu thiếu: một con số nghe rất hợp lý
     quét mọi con số trong             │ nhưng không có dòng dữ liệu nào đỡ phía
     câu trả lời                       │ sau vẫn được hiển thị như thật

  9  CỔNG KIỂM TRA CUỐI                │ Nếu thiếu: hỏi "vì sao giảm" mà trả lời
     kiểm lần cuối trước               │ "có 668 sản phẩm" — số đúng, bằng chứng
     khi hiển thị                      │ đủ, nhưng SAI CÂU HỎI

NHÁNH RẼ tại chặng 5 — tách thành hai nhánh song song rồi nhập lại ở chặng 6:
  nhánh trái  : "Mẫu câu hỏi đã được kiểm duyệt sẵn"
  nhánh phải  : "Câu hỏi tự do — tự lập kế hoạch rồi kiểm lại"
Ghi nhãn nhỏ màu xám dưới nhánh phải:
  "chỉ sinh câu truy vấn đọc dữ liệu, không bao giờ ghi hay xoá"

CỘT PHẢI — ba khối dọc màu khác nhau, mỗi khối có mũi tên nét đứt trỏ vào đúng
chặng tương ứng. Nhãn mỗi khối là câu hỏi mà lớp đó đặt ra:

  hổ phách   "Được phép trả lời không?"            → trỏ vào chặng 4
  navy       "Số hiển thị có bằng chứng không?"    → trỏ vào chặng 8
  xanh két   "Có đang trả lời ĐÚNG câu được hỏi?"  → trỏ vào chặng 9

LỐI THOÁT — ĐÂY LÀ CHI TIẾT QUAN TRỌNG NHẤT CỦA HÌNH.
Từ MỖI chặng trong 9 chặng, vẽ một mũi tên ngắn màu đỏ trầm đi sang trái. Tất cả
9 mũi tên gom vào MỘT khối đỏ trầm duy nhất bên trái, chữ trắng:

  "DỪNG AN TOÀN
   Hỏi lại  |  Từ chối
   luôn kèm lý do cụ thể, không bao giờ đoán bừa"

Ý đồ thị giác: người xem phải thấy ngay rằng KHÔNG chặng nào bắt buộc phải trả
lời. Bất kỳ chặng nào cũng có quyền dừng cả quy trình.

DẢI DƯỚI CÙNG — một băng ngang mảnh, nền navy, chữ trắng, in đậm, căn giữa:

  "AI không tự tính ra con số  ·  AI không tự quyết định được phép trả lời hay không
   Câu truy vấn dữ liệu chỉ do bộ sinh tự động tạo ra, không do AI viết"
```

---

## CHART 2 — Ba lớp kiểm tra và khe hở giữa chúng

```
Vẽ một sơ đồ Venn hai vòng tròn không đối xứng, kèm lớp phủ thứ ba, minh hoạ một
"khe hở" giữa hai lớp kiểm tra trong một hệ thống phần mềm — nơi cả hai lớp đều
báo "đạt" nhưng kết quả cuối vẫn sai.

PHONG CÁCH: kỹ thuật cao cấp, tối giản. Nền trắng ngà #FAFAF8. Không icon hoạt
hình. Font sans-serif hình học, tiếng Việt đủ dấu. Tỷ lệ 16:9.

HAI VÒNG TRÒN LỚN, giao nhau khoảng 35% diện tích:

  Vòng trái  — màu hổ phách #C96F1E, nền mờ 15%
     Nhãn:  "LỚP 1 — CỔNG CHO PHÉP
             Câu hỏi này có đủ điều kiện để trả lời không?"

  Vòng phải  — màu navy #1B2A4A, nền mờ 15%
     Nhãn:  "LỚP 2 — ĐỐI CHIẾU SỐ
             Mỗi con số hiển thị có bằng chứng thật không?"

VÙNG GIAO NHAU: tô màu đỏ trầm #A6333F đậm rõ, đặt một dấu chấm than lớn màu
trắng ở giữa, kèm nhãn in đậm chữ trắng:

  "Cả hai lớp đều ĐẠT ✓ ✓
   MÀ KẾT QUẢ VẪN SAI"

HỘP CHÚ THÍCH có mũi tên trỏ vào vùng giao nhau. Nền trắng, viền đỏ trầm dày,
nội dung trình bày dạng chữ đều (monospace):

  Người dùng hỏi :  "Có bao nhiêu sản phẩm giảm giá trên 50%?"
  Hệ thống trả   :  474
  Sự thật        :  474 là TỔNG SỐ SẢN PHẨM,
                    không phải số sản phẩm đang giảm giá

  → Con số này CÓ bằng chứng thật.
     Nó chỉ là đáp án cho một câu hỏi KHÁC.

VÒNG TRÒN THỨ BA — màu xanh mòng két #2E7D8F, viền nét đứt dày, vẽ bao trùm lên
trên vùng giao nhau màu đỏ (như một lớp phủ). Nhãn đặt phía trên vòng:

  "LỚP 3 — KHỚP CÂU HỎI
   Kết quả này có đang trả lời ĐÚNG câu được hỏi không?"

Kéo một nhãn nhỏ có đường chỉ từ vòng này, chữ nghiêng màu xanh két:
  "lớp sinh ra để lấp đúng khe hở này —
   không lớp nào trước đó được giao việc đặt câu hỏi đó"

DẢI DƯỚI CÙNG — ba ô ngang bằng nhau, mỗi ô tô màu tương ứng một lớp, ghi ví dụ
những gì lớp đó bắt được (viết bằng lời, không dùng mã lỗi):

  CỔNG CHO PHÉP  →  Hỏi thứ dữ liệu không có · Thiếu thị trường ·
                    Sản phẩm không tồn tại

  KHỚP CÂU HỎI   →  Trả lời sai khoảng thời gian · Đổi sang chỉ số khác ·
                    Tiền đề trong câu hỏi trái với dữ liệu

  ĐỐI CHIẾU SỐ   →  Con số không có bằng chứng nào đỡ phía sau

Ý đồ thị giác: mắt người xem phải bị hút vào vùng giao nhau màu đỏ trước tiên.
Đó là thông điệp chính — hai lớp kiểm tra vẫn để lọt một loại lỗi.
```

---

## CHART 3 — Tầng nối định nghĩa với dữ liệu thật

```
Vẽ một sơ đồ kiến trúc ba tầng (layered architecture diagram) thể hiện một tầng
trung gian bắt buộc, nằm giữa tầng định nghĩa khái niệm và tầng dữ liệu thật.

PHONG CÁCH: giống một bản vẽ kỹ thuật blueprint cao cấp, KHÔNG giống infographic
quảng cáo. Nền trắng ngà #FAFAF8, đường nét mảnh sắc. Màu: navy #1B2A4A, xanh
mòng két #2E7D8F, hổ phách #C96F1E, xám #E8E6E1. Font sans-serif hình học, tiếng
Việt đủ dấu. Tỷ lệ 16:9.

BỐI CẢNH — vấn đề mà tầng này sinh ra để giải. Ghi thành một dải phụ đề ngay
dưới tiêu đề, nền đỏ trầm mờ 12%, viền trái đỏ:

  "Hệ thống có 11 quy tắc bắt buộc ghi trong tài liệu — ví dụ 'phải loại giá rác
   trước khi tính giá cao nhất', 'phải khử trùng lặp trước khi đếm'.
   Nhưng KHÔNG có gì bảo đảm phần code chạy thật sự thi hành đúng 11 quy tắc đó.
   Lần đầu dựng tầng kiểm tra và đối chiếu, phát hiện 4 sai lệch có thật:"

  ✗  2 cột được khai báo để nối bảng nhưng KHÔNG TỒN TẠI trong dữ liệu thật
  ✗  2 quan hệ giữa các bảng bị khai KHÁC NHAU ở hai nơi trong hệ thống

  → Nối sai cột giữa bảng sản phẩm và bảng danh mục thì mọi phép đếm
     "mỗi ngành hàng có bao nhiêu sản phẩm" đều sai, mà không có gì báo lỗi.

BA TẦNG NGANG XẾP CHỒNG. Tầng trên hẹp nhất, tầng dưới rộng nhất.

TẦNG 1 (trên cùng, màu navy) — tiêu đề "ĐỊNH NGHĨA KHÁI NIỆM"
Chia thành 5 ô vuông bằng nhau, mỗi ô một dòng tên + một dòng số:

  Từ điển khái niệm        86 khái niệm nghiệp vụ
  Định nghĩa chỉ số        33 chỉ số · 13 quan hệ phụ thuộc
  Quan hệ giữa các bảng    10 quan hệ
  Ràng buộc bắt buộc       11 quy tắc
  Danh mục bảng dữ liệu    7 bảng · 219 cột

TẦNG 2 (giữa, màu xanh mòng két, VIỀN DÀY NHẤT — đây là nhân vật chính của hình)
Tiêu đề lớn: "TẦNG KIỂM TRA KHAI BÁO"
Bên trong vẽ 6 hình lục giác nhỏ xếp hàng ngang, mỗi hình ghi tên một loại chữ
ký số dùng để phát hiện khai báo bị đổi:

  Bảng · Khái niệm · Quan hệ · Chỉ số · Ràng buộc · Tổng hợp

Dưới hàng lục giác, một dòng chữ nhỏ căn giữa:
  "mọi khai báo phải trỏ tới một cột hoặc một hàm XỬ LÝ CÓ THẬT"

TẦNG 3 (dưới cùng, màu xám) — tiêu đề "DỮ LIỆU THẬT"
Vẽ 7 hình trụ (biểu tượng cơ sở dữ liệu) xếp ngang, nhãn tiếng Việt:

  Sản phẩm · Cửa hàng · Kệ hàng của shop · Danh mục sản phẩm
  · Danh mục của sàn · Chỉ số theo ngày · Biến động giữa hai ngày

ĐƯỜNG NỐI — chi tiết quyết định thông điệp:
  Từ tầng 1 xuống tầng 2: nhiều đường liền mảnh hội tụ vào giữa tầng 2.
  Từ tầng 2 xuống tầng 3: nhiều đường liền toả ra các hình trụ.
  TUYỆT ĐỐI KHÔNG vẽ bất kỳ đường nào nối thẳng từ tầng 1 xuống tầng 3.
  Ý đồ: mọi thứ bắt buộc phải đi QUA tầng giữa.

KHỐI NHẤN MẠNH — bên phải tầng 2, một khối nhỏ màu đỏ trầm #A6333F, mũi tên trỏ
vào tầng 2, chữ trắng in đậm:

  "Khai báo sai
   ⇒ CHƯƠNG TRÌNH DỪNG NGAY LÚC KHỞI ĐỘNG
   không tự đoán, không chạy tiếp với dữ liệu sai"

MŨI TÊN DỌC BÊN TRÁI — chạy dọc suốt ba tầng, nhãn xoay dọc theo mũi tên:
  "chữ ký số đi vào: kế hoạch truy vấn · bộ nhớ đệm · cổng kiểm tra · hồ sơ bằng chứng"

Cảm giác tổng thể phải giống một bản vẽ chính xác của kỹ sư, không phải poster
marketing.
```

---

## CHART 4 — Kết quả trước và sau đợt sửa lỗi

```
Vẽ một biểu đồ độ dốc (slope chart) kết hợp một dải trạng thái, thể hiện kết quả
của một hệ thống phần mềm trước và sau khi sửa các lỗi do một đợt đánh giá độc
lập tìm ra.

PHONG CÁCH: kỹ thuật cao cấp, tối giản. Nền trắng ngà #FAFAF8. Màu: navy
#1B2A4A, xanh lá trầm #2F7A4F (chuyển biến tốt), đỏ trầm #A6333F (chỉ số xấu),
hổ phách #C96F1E, xám #E8E6E1. Font sans-serif hình học, tiếng Việt đủ dấu.
Tỷ lệ 16:9.

BỐI CẢNH cần ghi thành một dòng phụ đề nhỏ dưới tiêu đề:
  "Một người đánh giá độc lập soạn 20 câu hỏi nhằm phá hệ thống.
   Đáp án chuẩn được tính riêng bằng công cụ khác, không dùng lại code của hệ thống."

PHẦN TRÊN — BIỂU ĐỒ ĐỘ DỐC. Hai cột dọc, cột trái nhãn "TRƯỚC", cột phải nhãn
"SAU". Bốn đường nối chéo giữa hai cột, ghi số ở cả hai đầu:

  "Trả lời ra số SAI"       3  →  0
      đường màu đỏ trầm, DÀY NHẤT, dốc xuống chạm đáy.
      Gắn nhãn lớn cạnh đường này:
      "chỉ số KHÔNG được phép đánh đổi"

  "Lỗi chương trình dừng"   2  →  0
      đường màu đỏ trầm, dốc xuống chạm đáy

  "Trả lời đúng"            2  →  tăng
      đường màu xanh lá, dốc lên

  "Đáng lẽ trả lời được
   nhưng lại từ chối"       9  →  giảm
      đường màu xanh lá, dốc xuống

Trục dọc từ 0 đến 10. Hai đường đỏ chạm 0 phải là điểm nhấn thị giác mạnh nhất.

PHẦN DƯỚI — SÁU Ô VUÔNG XẾP NGANG, nền xanh lá trầm mờ 20%, viền xanh lá, mỗi ô
có dấu tick ✔ xanh lá ở góc trên phải. Mỗi ô là một loại lỗi đã được sửa tận gốc,
ghi bằng lời dễ hiểu:

  1  Nhầm giữa "thứ được đếm"
     và "cách chia nhóm kết quả"

  2  Bằng chứng chỉ có một ngày
     mà câu hỏi hỏi cả một khoảng

  3  Phép đếm bị thu hẹp ngầm
     bởi bộ lọc của một phép tính khác

  4  Báo sai nguyên nhân từ chối,
     gợi ý người dùng làm việc vô ích

  5  Hiểu sai từ khoá:
     "giảm giá" bị đọc thành "giá"

  6  Nhánh dùng AI tốn kém
     mà không cải thiện kết quả

BĂNG NGANG DƯỚI CÙNG, nền navy, chữ trắng in đậm, căn giữa:
  "Cả sáu loại lỗi đều được sửa ở tầng thiết kế, không vá riêng từng câu hỏi"

GÓC TRÊN PHẢI — một ô nhỏ viền xám, chữ nhỏ màu xám. Ô này BẮT BUỘC PHẢI CÓ:
  "Giới hạn của chính phép đo này:
   chỉ 20 câu · bộ câu được soạn sau khi đã biết điểm yếu ·
   chấm điểm tự động nên bỏ qua sắc thái diễn đạt"
```

---

## CHART 5 — So sánh chế độ có AI và không AI

```
Vẽ một biểu đồ so sánh chi phí và lợi ích giữa hai chế độ vận hành của một hệ
thống hỏi đáp: chế độ có dùng mô hình ngôn ngữ lớn (AI) để hiểu câu hỏi, và chế
độ chỉ dùng luật cố định. Thông điệp: chế độ dùng AI đắt hơn rất nhiều mà lại
kém chính xác hơn.

PHONG CÁCH: kỹ thuật cao cấp, tối giản. Nền trắng ngà #FAFAF8. Màu: xanh lá trầm
#2F7A4F (chế độ luật cố định), đỏ trầm #A6333F (chế độ AI), navy #1B2A4A, xám
#E8E6E1. Font sans-serif hình học, tiếng Việt đủ dấu. Tỷ lệ 16:9.

BỐ CỤC BA PHẦN XẾP NGANG, ba phần có trọng lượng thị giác ngang nhau.

PHẦN TRÁI — BIỂU ĐỒ THANH NGANG so sánh thời gian xử lý 20 câu hỏi.
Dùng thang logarit để cả hai thanh cùng hiển thị được:

  Chỉ dùng luật cố định      0,9 giây     (thanh xanh lá, rất ngắn)
  Có dùng AI hiểu câu hỏi  394,1 giây     (thanh đỏ, rất dài)

Giữa hai thanh, đặt một nhãn CỰC LỚN in đậm màu đỏ trầm:  "438×"
Ngay dưới nhãn, chữ nhỏ:  "chậm hơn 438 lần"
Dưới cùng phần này, chữ nhỏ màu xám:
  "19 trên 20 câu cho ra kết cục y hệt nhau"

PHẦN GIỮA — BIỂU ĐỒ CỘT so sánh độ chính xác, đo trên bộ 60 câu hỏi chạy 3 lần:

  Chỉ dùng luật cố định     1,000      (cột xanh lá, cao đầy khung)
  Có dùng AI hiểu câu hỏi   0,622      (cột đỏ, thấp hơn hẳn)

Trục dọc từ 0 đến 1,0. Ghi số trên đỉnh mỗi cột, cỡ chữ lớn.
Nhãn đặt giữa hai cột, in đậm:
  "đắt hơn 438 lần VÀ kém chính xác hơn"

PHẦN PHẢI — MỘT Ô NHẤN MẠNH, nền navy, chữ trắng, viền xanh lá dày.
Đây là thông điệp tích cực của hình, không phải chú thích phụ — phải nổi bật
ngang hai biểu đồ bên trái:

  "PHÉP THỬ GIEO LỖI CỐ Ý

        1,0            1,0
   luật cố định      có AI

   Khi AI hiểu sai câu hỏi hàng loạt,
   KHÔNG một con số bịa nào lọt ra ngoài.

   Lớp bảo vệ đã làm đúng việc của nó
   trong điều kiện xấu nhất."

Ghi chú nhỏ dưới ô, chữ xám:
  "Phép thử gieo lỗi: cố ý sửa sai dữ liệu bên trong rồi kiểm xem
   hệ thống có phát hiện được không. Đạt 1,0 nghĩa là phát hiện 100%."

BĂNG NGANG DƯỚI CÙNG, nền xám nhạt, chữ navy:
  "Quyết định: tắt nhánh AI hiểu câu hỏi.
   Bật lại chỉ khi có phép đo chứng minh nhánh AI THẮNG, không phải hoà."

Ý đồ thị giác: mắt người xem đi theo thứ tự
  "đắt hơn 438 lần"  →  "chính xác kém hơn"  →  "nhưng lớp bảo vệ vẫn giữ 100%".
```
