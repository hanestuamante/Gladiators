# Implementation handoff — 2026-08-01

Bàn giao vòng triển khai `docs/ultimate solution.md` trên nhánh `MVP_Dai_V2`.

Trạng thái: **801 passed, 1 skipped, 0 failed**. Ước lượng **~85%** của 62 hạng
mục con trong §16. Phần còn lại gần như toàn bộ chờ quyết định của người, không
chờ code — chi tiết ở mục "Đang chặn" bên dưới.

---

## 1. Thứ cần người quyết, không ai code thay được

Đây là mục quan trọng nhất của tài liệu này. Mọi thứ khác đều đọc được từ code
và test; riêng những mục dưới đây thì không.

### 1.1. DR1 — hai luật chất lượng dữ liệu (§1.5)

Hai phân bố bất thường đã quan sát được, cả hai **chưa** có luật xử lý và tôi
không được phép tự quyết:

| Hiện tượng | Vì sao phải quyết | Nếu bỏ qua |
| --- | --- | --- |
| Một dải giá trị giá lặp chữ số ở độ dài nhất định trông như placeholder, nhưng bộ lọc sentinel hiện chỉ nhận ra một hằng số ở độ dài khác | Cần luật theo **phân bố**, không phải danh sách dòng | Các dòng này vẫn vào phép tính giá và revenue proxy |
| Ở một thị trường, một tỉ lệ lớn listing nằm đúng tại giá trị lớn nhất của cột sold proxy | Nếu đó là **bậc hiển thị** chứ không phải phép đếm thì mọi phép trung vị/xếp hạng trên cột này đổi nghĩa | `derived.median_monthly_sold` đang là metric đã chứng nhận, aggregate trên cột đó |

Cách viết luật: **theo phân bố**, ví dụ "loại giá trị lặp chữ số ở độ dài N" hoặc
"gắn cờ khi tỉ lệ trùng tại giá trị biên vượt ngưỡng X". Không được liệt kê ID
dòng hay tên sản phẩm cụ thể vào code/comment/commit — làm vậy là gắn sẵn đáp án
vào repo, agent sẽ khớp đáp án thay vì lọc nhiễu.

Cùng nhóm: miner `top_mover` hiện **mô tả** trung thực trường hợp nhiều listing
hoà cùng một mức thay đổi tại giá trị biên (xem caveat trong `miners.py`), nhưng
**có loại chúng khỏi bảng xếp hạng hay không là quyết định sản phẩm**, chưa làm.

### 1.2. Topic gate — 6 metric chờ reviewer

`eval/topic_gate.json` hiện `gate_open=false`. 5/5 automatic check PASS
(`topic_scoped_rate` 72.3%, `unknown_rate` 4.8%, `overflow` 0%, cả 8 domain
reachable, ownership là phân hoạch 83/83 ref).

Sáu metric còn thiếu đều ghi `pending_oracle`:
`required_ref_recall`, `required_relation_recall`, `plan_valid_rate_delta`,
`false_allow_rate`, `false_abstain_rate`, `adversarial_topic_cases`.

Script **cố ý không tự chấm** những metric này. Chúng cần một oracle liệt kê
từng câu hỏi thật sự cần ref/relation nào, và oracle đó thuộc reviewer. Lấy
chính routing của mình chấm cho mình rồi gọi đó là recall thì gate mất ý nghĩa.

### 1.3. P7 rollout — chờ dữ liệu, chưa chờ người

Shadow routing mới bắt đầu thu từ commit `63d172e`. Chưa đủ lưu lượng để chạy
A/B. Đây là điều kiện tiên quyết của việc bật gate; không rút ngắn được bằng
cách viết thêm code.

### 1.4. Khác

- **PAM golden review** — §12.2 yêu cầu đổi weights phải có ablation 20/40/40 vs
  30/40/30 kèm sign-off. Weights hiện tại là mặc định 30/40/30, chưa ablation.
- **Claim-boundary review** (P13).
- **Groq structured-output capture** (P1) — cần một lỗi 400 thật để tái hiện.

---

## 2. Đã dựng phiên này

| Package | Trạng thái | Ghi chú |
| --- | --- | --- |
| P5 topic/context | 5/5 | registry, router, packer, prompt library, gate |
| P6 decomposer | 7/7 | atom, feasibility, ExecutionPlan, validator+gate, 4 composition operator, decomposer API, subrequest planning |
| P8 insight foundation | contracts, PAM, builder, **build lock** | golden review chờ người |
| P9 miners | 2/2 | 4 miner + evidence linkage + wording guard |
| P10 insight API | 2/2 | + performance report (p95 cao nhất 4.68ms) |
| P11 dashboard | 3/3 | + security/UI smoke |
| P12 Tavily | 4/4 | record/replay + **nối vào provider factory** |
| P3 wiring | shadow | P5/P6 chạy trên request thật, không đổi câu trả lời |

### 2.1. Vì sao P5/P6 chạy ở chế độ shadow chứ không bật thẳng

Đây là chỗ dễ hiểu nhầm nhất nếu chỉ nhìn danh sách "đã xong".

§6.5 quy định topic chưa qua gate thì context về legacy broad slice, trace ghi
`topic_gate_disabled`, **không đổi capability decision**. §8.11 quy định shadow
chỉ ghi verdict và tuyệt đối không execute. Gate đang đóng (mục 1.2), nên shadow
là trạng thái đúng, không phải nửa vời.

Đo trên đường chạy thật: **3–6ms**, `catalog_miss_count = 0` — routed context
chứa đủ mọi ref mà plan thật đã dùng. Đó chính là bằng chứng cho
`required_ref_recall` mà gate đang chờ, nay tính trên câu hỏi thật thay vì trên
eval corpus.

Test khoá tính chất quyết định: câu trả lời **giống hệt** khi bật và tắt shadow
(`tests/test_shadow_wiring.py`).

---

## 3. Lỗi im lặng tìm được bằng cách chạy, không phải bằng cách đọc

Ghi lại vì mỗi lỗi đại diện một lớp, và lớp đó sẽ tái xuất hiện.

| Lỗi | Vì sao im lặng |
| --- | --- |
| `nan is None` là False, nên 63 listing bị void monetary score được gán nhãn **Steady** — nhãn "khoẻ mạnh" | Đúng cái việc void điểm là để nói "không chấm được", mà kết quả lại nói "bình thường" |
| Cohort fallback chỉ gồm các dòng rơi xuống (8 dòng), nhỏ hơn cả ngưỡng 20 đã kích hoạt fallback | Fallback báo thành công trong khi tự đánh bại mục đích của nó |
| `activity_days` đọc chặng cuối thay vì ngày gần nhất **có** delta dương | 79% listing bị coi là không hoạt động; con số vẫn hợp lý khi nhìn qua |
| Bộ lọc `non_sql_refs` chỉ áp cho required ref | Ref similarity do tool tính lọt vào qua candidate optional; chúng giống hệt measure thật trong catalog nên không tầng nào phía sau phân biệt được |
| Proposal tự sinh vi phạm chính validator của nó | Nhánh xác định là nhánh không được kiểm |
| Docstring builder khẳng định "take a lock on dataset_version" trong khi **không có lock nào** | Lời khẳng định sai về tính chất an toàn không ai kiểm lại |
| record/replay dựng xong mà **không gì chọn nó** | `mode=record` trông như đã cấu hình và không ghi cassette nào |

Hai lỗi nằm trong chính công cụ kiểm tra: một harness đo nuốt exception nên 188
phép đo chạy với input rỗng; và tôi kết luận sai "insight API 0 route" vì đo
`app.routes` trong khi FastAPI bản này giữ `_IncludedRouter` — xác minh lại bằng
hành vi thì endpoint trả 200.

**Bài học vận hành:** xác minh bằng hành vi, không bằng cấu trúc. Và khi một
harness báo kết quả bất thường, nghi ngờ harness trước.

---

## 4. Chạy lại các artifact

```bash
.venv/Scripts/python.exe -m pytest -q                              # 801 passed
.venv/Scripts/python.exe scripts/build_insight_mart.py             # bundle
.venv/Scripts/python.exe scripts/build_topic_gate.py               # gate report
.venv/Scripts/python.exe scripts/render_topic_prompts.py --check    # drift
.venv/Scripts/python.exe scripts/build_release_proof.py            # proof pack
.venv/Scripts/python.exe scripts/build_insight_performance_report.py
.venv/Scripts/python.exe scripts/smoke_llm.py                      # cần API key
```

Lưu ý: `streamlit` **không** phải dependency đã khai báo, nên `render()` chạy qua
stub trong test. Việc đó xác minh wiring và trình tự gọi, **không** xác minh
trang trông đúng. Đừng đọc "P11 3/3" thành "đã kiểm giao diện".

---

## 5. Việc dựng được tiếp theo, xếp theo giá trị

1. **P3 adapter `open_planner` + migration `ToolContext`** — chỉ có nghĩa sau khi
   P7 quyết định bật gate hay không, nên làm trước là làm sớm.
2. **P13 ablation report** — slice 10/20/30 object, cần cho acceptance của P7.
3. **LLM decomposition proposal service** — hiện suy xác định đã phủ hai hình
   dạng (union_scope cho đa thị trường, side_by_side cho compound part); phần
   còn lại mới cần model.
