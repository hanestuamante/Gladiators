# MỤC LỤC TÀI LIỆU GLADIATORS

## 1. Điểm bắt đầu

Đọc theo thứ tự sau khi cần hiểu hệ thống đang chạy:

1. [Đặc tả kiến trúc hiện tại](CURRENT_ARCHITECTURE_SPEC.md)
2. [Ngữ cảnh và ngữ nghĩa dữ liệu](reference/Data_Context_and_Analysis_Notes.md)
3. [Pipeline dữ liệu](reference/data-pipeline.md)
4. [Đồ thị luồng code](reference/codegraph.md)

`CURRENT_ARCHITECTURE_SPEC.md` là tài liệu kiến trúc hiện trạng duy nhất. Tài liệu
này được đóng đinh theo commit và phải được cập nhật sau thay đổi kiến trúc.

Khi tài liệu mâu thuẫn nhau, ưu tiên:

1. source code, test và cấu hình đang chạy;
2. artifact trong `data/processed`;
3. `CURRENT_ARCHITECTURE_SPEC.md`;
4. tài liệu chuyên đề trong `reference`;
5. tài liệu mục tiêu trong `design`;
6. báo cáo theo ngày và tài liệu trong `archive`.

## 2. Cấu trúc thư mục

```text
docs/
├── README.md
├── CURRENT_ARCHITECTURE_SPEC.md
├── reference/                 # Dữ liệu, pipeline và code graph còn dùng
├── design/                    # Thiết kế mục tiêu/chuyên đề, không tự động là hiện trạng
├── topics/                    # Topic cards và projection dùng bởi topic routing
├── agents/                    # Quy ước vận hành, triage và ownership cho agent
├── qa/                        # Input, kết quả và phân tích kiểm thử thủ công
├── acceptance/                # Checklist nghiệm thu chưa đóng
└── archive/
    ├── architecture/          # Kiến trúc đã bị thay thế
    └── implementation/        # Handoff và báo cáo theo mốc thời gian
```

## 3. Tài liệu hiện hành

| Tài liệu | Giá trị | Cách sử dụng |
| --- | --- | --- |
| [CURRENT_ARCHITECTURE_SPEC.md](CURRENT_ARCHITECTURE_SPEC.md) | Rất cao | Nguồn bắt đầu để hiểu pipeline/runtime hiện tại tại commit được ghi trong file |
| [Data Context and Analysis Notes](reference/Data_Context_and_Analysis_Notes.md) | Rất cao cho dữ liệu | Tra grain, khóa, field semantics, anomaly và giới hạn phân tích; artifact mới hơn luôn được ưu tiên |
| [Data pipeline](reference/data-pipeline.md) | Cao | Cách chạy notebook, chính sách làm sạch, metric và artifact đầu ra |
| [Code graph](reference/codegraph.md) | Cao nhưng dễ cũ | Tra luồng gọi hàm và dependency; phải cập nhật khi module/runtime đổi |

## 4. Thiết kế và đặc tả chuyên đề

Các file trong `design` có giá trị giải thích quyết định và kiến trúc mục tiêu.
Không được dùng một câu có nhãn `target`, `proposed` hoặc `conditional` để khẳng
định code hiện tại đã triển khai.

| Tài liệu | Giá trị | Trạng thái sử dụng |
| --- | --- | --- |
| [V2 Unified Architecture](design/V2_Unified_Architecture.md) | Rất cao | Thiết kế mục tiêu đầy đủ và rationale; đối chiếu với đặc tả hiện trạng trước khi triển khai |
| [Ultimate Solution](<design/ultimate solution.md>) | Rất cao | Implementation specification hợp nhất đang được đội triển khai; trạng thái thực tế vẫn phải đối chiếu với code và test |
| [Topic-Routed Context Architecture 29/07](design/2907.md) | Cao | Thiết kế topic registry, context projection và routing vừa được hiện thực hóa trên nhánh MVP |
| [Ultimate Solution 28/07](<design/ultimate solution2807.md>) | Trung bình | Đặc tả nguồn của đợt sửa testcase 28/07 và kiến trúc V3 vòng 1; dùng để truy vết quyết định trước bản hợp nhất |
| [Context Harness 20% và TC fix 2607](<design/Context_harness20% and TC fix 2607.md>) | Cao | Đặc tả ContextBundle, A22, cassette và các sửa lỗi 26/07; hữu ích để hiểu hợp đồng và phần còn thiếu |
| [External Data Integration](<design/External Data Integration.md>) | Cao | Thiết kế, policy, source matrix và acceptance cho external sidecar; baseline lịch sử trong file không còn đại diện toàn bộ code |
| [Architecture proposal](design/Archi_proposal.md) | Trung bình | Dàn ý trình bày/slide dẫn xuất từ thiết kế; không phải nguồn kiểm chứng kỹ thuật |

## 5. Kiểm thử và nghiệm thu

| Tài liệu | Giá trị | Trạng thái sử dụng |
| --- | --- | --- |
| [Kết quả testcase 28/07](<qa/Testcase result 287.md>) | Rất cao, theo thời điểm | Dữ liệu QA thô sau cập nhật kiến trúc; giữ nguyên để truy vết |
| [Phân tích kết quả 28/07](qa/Testcase2807_result_analysis.md) | Rất cao, theo thời điểm | Nhóm lỗi, nguyên nhân, bằng chứng cần thu thập và tiêu chí sửa |
| [Phân tích testcase 26/07](<qa/Testcases result 2607 analysis.md>) | Trung bình | Baseline trước đợt sửa mới; hữu ích để so sánh hồi quy, không phải kết quả hiện tại |
| [DR task 14/07](<qa/DR TASK 1407.md>) | Lịch sử QA | Testcase và phân tích trace gốc dùng để dựng suite DR2607 |
| [Phase 6 acceptance](acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md) | Cao | Checklist E6 còn mở; tên file có chữ sign-off không có nghĩa là đã được ký |

Kết quả QA theo ngày không thay thế full test tự động và cũng không tự động trở
thành benchmark hiện hành sau khi source code thay đổi.

## 6. Tài liệu lưu trữ

### 6.1. Kiến trúc cũ

| Tài liệu | Giá trị còn lại | Không nên dùng cho |
| --- | --- | --- |
| [Architecture Spec cũ](archive/architecture/Architecture-spec.md) | Acceptance/rationale ban đầu trước V2 | Mô tả runtime hiện tại |
| [V1 Architecture](archive/architecture/V1_Architecture.md) | Baseline và lịch sử chuyển từ ba intent sang V2 | Nguồn kiến trúc chuẩn |
| [V1 Implementation Limitations](archive/architecture/V1_Implementation_Limitations.md) | Danh sách gap V1 để kiểm tra hồi quy quyết định | Backlog hiện tại nếu chưa đối chiếu lại |
| [V0 Architecture](archive/architecture/V0_Architecture.md) | Nguồn gốc các quyết định semantic/evidence | Thiết kế đang áp dụng |

### 6.2. Handoff và báo cáo triển khai

| Tài liệu | Giá trị còn lại |
| --- | --- |
| [Handoff 20/07](archive/implementation/IMPLEMENTATION_HANDOFF_2026-07-20.md) | Lịch sử triển khai Phase 0-5 và các quyết định ban đầu |
| [Handoff 22/07](archive/implementation/IMPLEMENTATION_HANDOFF_2026-07-22.md) | Trạng thái Phase 6 E1-E5 tại ngày 22/07 |
| [Handoff 23/07](archive/implementation/IMPLEMENTATION_HANDOFF_2026-07-23.md) | Chi tiết field-span, cache, router, hybrid và security |
| [Defect remediation 25/07](archive/implementation/2507.md) | Đặc tả và bằng chứng cho đợt sửa lỗi ngày 25/07 |
| [Báo cáo 26/07](<archive/implementation/IMPLEMENTATION REPORT 2607.md>) | Bằng chứng triển khai Context Harness và đo live-search trước relevance fix |
| [Báo cáo 27/07](archive/implementation/IMPLEMENTATION_REPORT_2707.md) | Kết quả DR40 ngay trước commit kiến trúc hiện tại |
| [Handoff 01/08](archive/implementation/IMPLEMENTATION_HANDOFF_2026-08-01.md) | Trạng thái triển khai Ultimate Solution, các quyết định còn chờ người và lệnh tái tạo artifact |
| [Quyết định kiến trúc 02/08](archive/implementation/2-8.md) | Bằng chứng đo được và rationale cho topic routing, context, decomposer và insight mart |

Các file archive không bị xóa vì vẫn cần cho audit, điều tra hồi quy và hiểu lý
do thiết kế. Chúng không được đặt ngang hàng với đặc tả hiện trạng.

## 7. Quy tắc duy trì

1. Không tạo thêm file kiến trúc tổng hợp ở cấp `docs`.
2. Sửa kiến trúc hiện trạng trong `CURRENT_ARCHITECTURE_SPEC.md`.
3. Đặc tả một subsystem mới đặt trong `design` và ghi rõ `target` hay
   `implemented`.
4. Kết quả chạy test thô và phân tích đặt trong `qa`, kèm ngày và commit.
5. Checklist chưa nghiệm thu đặt trong `acceptance`.
6. Handoff/báo cáo đã qua mốc đặt trong `archive/implementation`.
7. Không xóa tài liệu lịch sử chỉ vì nội dung đã cũ; chuyển vào `archive` và ghi
   rõ tài liệu thay thế.
