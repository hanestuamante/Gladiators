# Implementation handoff — 2026-08-27

> **Phạm vi phiên này:** hoàn tất 25 work package của `docs/Spec2308.md` (làn A và
> làn B), rồi đo bằng provider thật ba chỗ trước đó bị ghi nhầm là "không đo được".
>
> **Commit cuối:** `d14fa75` trên `MVP_Dai_V2`, đã push, cây làm việc sạch.
> **Trạng thái kiểm:** `pytest -q` → **1207 passed, 1 skipped** · năm suite offline
> giữ `end_to_end 1.0` · phase 6 external **12/12** `offline-no-network`.

---

## 1. Thứ cần người quyết, không ai code thay được

### 1.1. Sáu cassette tìm kiếm chờ chữ ký — chặn nghiệm thu WP-A12.3

`artifacts/search_cassettes/REVIEW.md`, cột **Người duyệt** để **trống 6/6**.

Đây là hạng mục duy nhất của Spec2308 còn thiếu để đạt nghiệm thu, và nó thiếu
đúng thứ máy không được phép làm. A12-R6 đòi *một người* đọc nội dung từng
cassette; một chữ ký do agent tự gõ là đúng thứ luật đó tồn tại để chặn.

Đã làm sẵn phần máy làm được, để việc của người duyệt còn là đọc:

- 6/6 cassette **replay ổn định** (3 lần, content hash không đổi);
- replay chạy được **khi socket bị chặn** ở tầng Python — bằng chứng hành vi cho
  A12-R5, vì chỉ ngắt mạng mới phân biệt được replay thật với replay lén gọi mạng;
- `injection_guard` quét phần chữ thật sự đi vào prompt: **6/6 sạch**.

Một chi tiết người duyệt cần biết trước: lần quét đầu chạy trên **cả JSON** và báo
cả 6 cassette dính `A17_PII_PHONE`. Kiểm lại thì mọi khớp là hiện vật — điểm liên
quan kiểu `0.86331123`, một mảnh `content_hash`, một khoá URL. Metadata không bao
giờ chạm prompt. Gặp cảnh báo tương tự thì **xem ngữ cảnh trước khi kết luận**.

Bốn điều phải xác nhận cho từng cassette nằm ở §4 của chính `REVIEW.md`.

### 1.2. Đường LLM parser vượt ngân sách độ trễ 2–3 lần

| | P-A | P-B | Ngân sách §A6 |
| --- | ---: | ---: | ---: |
| p50 | 23,0 s | 18,3 s | 8 s ❌ |
| p95 | 50,2 s | 30,0 s | 15 s ❌ |

Chưa có hướng xử lý, và **không phải là lỗi cần sửa gấp**: cấu hình đang phát hành
có `GLADIATORS_ENABLE_LLM_PARSER` **tắt**, nên con số vận hành thật là 0,21 s
(`eval/reports/2026-08-27-latency.md`). Nhưng nó là con số phải biết trước khi bất
kỳ ai đề xuất bật cờ đó.

Người quyết cần trả lời: chấp nhận p95 30–50 s cho đường LLM, hay coi ngân sách 15 s
là ràng buộc cứng và đóng luôn khả năng bật cờ này?

### 1.3. Còn treo từ trước, không đổi trong phiên này

- Hai luật chất lượng dữ liệu của DR1; PAM golden review; claim-boundary review
  P13; fixture gap TC34; policy sentinel price TC19.
- Sáu metric `pending_oracle` của topic gate.
- **4 nghi vấn `suspect`** của kiểm biến hình (WP-B7): hai thị trường cho cùng kết
  quả. Dữ liệu có đúng 10 shop ở **mỗi** thị trường nên bằng nhau là ĐÚNG — nhưng
  spec nói bằng nhau thì "rất có thể scope bị bỏ qua", nên chúng được chấm là
  *nghi vấn* chứ không phải *lỗi*, và cần người xem.
- **`p0-grouping-dropped-official-shop` là một fixture tự mâu thuẫn**: nó khai
  `expected_action="clarify"` / `A22-ALIGN-GROUPING`, nhưng khối `baseline` trong
  **chính nó** ghi `abstain` / `A19-PLAN` — và hệ thống khớp baseline. Không sửa
  `expected` để ép xanh; cần người quyết bên nào là hợp đồng thật.
- Bốn MCP connector (Gmail, Google Calendar, Phoenix, notebookLLM) chưa được cấp
  quyền; phiên phi tương tác không chạy được OAuth.

---

## 2. Đã dựng phiên này

25/25 work package. Phần đáng đọc lại:

| WP | Thứ nó thêm |
| --- | --- |
| A3 | Bộ nhớ hội thoại ngắn hạn · `clarify_recovery_rate` **0,75** |
| A5 | Ba vòng lặp rẻ: dò giá trị · nới ngữ cảnh · sửa câu chữ |
| A6 | `StageTimer` 9 chặng · cache kế hoạch theo `(plan_hash, dataset_version)` |
| A11 | Trọng tài intent tách khỏi `_parse`, chính sách P-A/P-B |
| A12 | Nấc 1 (`external/lexicon.py`) · nấc 2 (ba khối tách bạch) |
| A13 | `A23-PARTIAL` — trả phần trả lời được thay vì từ chối cả câu |
| B4 | Đường cong rủi ro–độ phủ · **AURC 0,0454** |
| B5 | Đối chứng "LLM viết SQL" |
| B7 | Kiểm biến hình mở rộng · **308 phép kiểm, 0 nhãn thêm** |
| B9 | `GET /trace/{id}` — mọi con số bấm về tới dòng dữ liệu gốc |
| B10 | Đơn giá mỗi câu, đơn giá là **dữ liệu có ngày** chứ không phải hằng số |
| B11 | Vòng bảo trì **có người duyệt** (không gọi là "tự học") |

### 2.1. Con số đáng công bố

**Đối chứng "sao không để LLM tự viết SQL?"** — cùng 44 câu, cùng oracle:

| | Baseline SQL | Gladiators |
| --- | ---: | ---: |
| Trả lời **đúng** số | 15,9 % | **45,5 %** |
| **Trả lời SAI mà KHÔNG BÁO** | **65,9 %** | **0 %** |
| Thời gian trung vị | 14,7 s | 0,091 s |

Baseline sai vì **đoán thứ chưa từng được cho xem**: `country_code = 'VN'` (dữ liệu
lưu `'vn'`), `date = '2024-07-03'` và `'2021-07-03'` (dataset là 2026). Cả ba trả
`COUNT(*) = 0`, và `0` là một con số hợp lệ.

**Bốn chỗ đã sửa CÓ LỢI cho baseline** trước khi tin con số — chi tiết ở
`eval/reports/2026-08-27-sql-baseline.md` §4. Một đối chứng bị dìm là một đối chứng
vô giá trị.

**Điểm năng lực** (bộ đề sinh từ dữ liệu, 44 câu): `coverage` 0,526 ·
`over_refusal_rate` 0,474 · `risk` **0,0** · `over_answer_rate` **0,0** ·
`metamorphic_consistency_rate` 0,910 · AURC 0,0454.

Bảy suite tự viết đạt 1.0 là điểm **hồi quy**, không phải điểm **năng lực**.
"An toàn nhưng quá thận trọng" là câu tóm tắt đúng.

---

## 3. Lỗi im lặng tìm được bằng cách chạy, không phải bằng cách đọc

### 3.1. Điều kiện đã bind bị template bỏ âm thầm — trả **474** thay vì **3**

*"Số lượng listing đã xác minh tại Indonesia ngày 03/07 là bao nhiêu?"* trả **474**
(tổng listing). Cùng câu hỏi diễn đạt *"Có bao nhiêu listing đã xác minh…?"* trả
đúng **3**.

Cả hai bind đúng `dim.shopee_verified=True`, nhưng câu sau không khớp surface
measure nào ⇒ bộ sinh kế hoạch bỏ cuộc ⇒ template đếm-tất-cả tiếp quản, và template
chỉ diễn đạt được `country` và `date`.

**Không lớp nào phía sau bắt được**: con số đó *có* evidence, *khớp* plan, và *đúng*
với câu hỏi mà nó thật sự đã trả lời — chỉ không phải câu người dùng hỏi. Tìm ra
bằng **kiểm biến hình** (WP-B7) ngay lần chạy đầu. Đã chặn bằng
`synthesizer.unexpressible_filters`.

### 3.2. P-B là code chết từ lúc được viết

Phép đo P-A/P-B đầu tiên cho hai bảng **trùng khít** và `llm_label_taken = 0`. Đọc
thoáng: *"P-B vô hại"*. Sự thật: *"P-B chưa từng chạy"*.

`arbitrate` đọc nhãn LLM từ `parsed.intent`, nhưng tới lúc nó chạy, năm nhánh
precedence **đã ghi `deterministic.intent` vào `parsed`** — nên hai nhãn luôn bằng
nhau và nhánh `no_change` bắn cho mọi câu.

Tám test của WP-A11 xanh suốt thời gian đó vì chúng gọi `arbitrate` **cô lập**.

Thứ phát hiện ra là khoá telemetry `llm_label_taken`. **Luật rút ra, đã ghi vào
`CLAUDE.md` §5.1.3:** mọi nhánh có điều kiện phải mang một khoá đếm số lần nó thật
sự bắn — nếu không, *"đã đo"* và *"đã chạy"* không phân biệt được.

Sau khi sửa: P-B bắn **10/44** ca và **không đổi một outcome nào**. Giữ `P-A`
(A11-R3 đòi thắng, không phải hoà).

### 3.3. Ba lỗi harness cùng một họ

| Lỗi | Hậu quả nếu không thấy |
| --- | --- |
| `run_evaluation` không đọc được suite dạng `{"cases": […]}` | `p0_probes` **chưa từng** được đo qua harness này |
| Case `question: null` bị chấm thành crash | `crash_rate` 0,333 trên bộ mà hệ không hề hỏng |
| Corpus topic router glob cả `eval/reports/` | Report B5 tự bơm 44 câu của mình vào corpus ⇒ `topic_scoped` tụt còn 63,4 % |
| `FallbackLLMClient.telemetry()` trả cấu trúc **lồng** | WP-B10 báo **0 USD** — một số 0 im lặng, tệ hơn `n/a` |

Ba cái đầu: *harness báo lạ thì nghi harness trước*. Cái cuối: một phép đo được
phép **đọc** corpus, nó không được phép **trở thành** corpus.

### 3.4. Phép biến hình tự sinh ra lỗi nó đi bắt

MR-1 thay thẳng `"bao nhiêu"` → `"số lượng"`, cho ra *"Có số lượng listing?"* —
không phải tiếng Việt đúng. 24/40 phép kiểm "hỏng", trong khi paraphrase **đúng ngữ
pháp** được trả lời bình thường. Một phép biến đổi sinh input không hợp lệ thì mọi
con số nó tạo ra đều vô nghĩa. Viết lại nguyên khung — và **chính bản sửa đó lộ ra
lỗi 474** ở §3.1.

MR-7 chấm "hai thị trường cùng kết quả" thành lỗi; dữ liệu có đúng 10 shop ở mỗi
thị trường nên bằng nhau là đúng. Thêm verdict `suspect`, nằm **trong** mẫu số —
bỏ nó ra sẽ làm tỷ lệ đẹp lên bằng cách giấu đúng những ca cần người xem.

---

## 4. Chạy lại các artifact

`artifacts/` bị gitignore và **phải dựng trước khi đo**:

```bash
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_value_index.py
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_question_bank.py
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_multiturn_suite.py
```

**Thiếu `artifacts/value_index.json` thì vòng dò giá trị (WP-A5.1) im lặng bỏ
qua** — đúng theo thiết kế, vì thiếu chỉ mục là thiếu *thông tin để kết luận*, chứ
không phải bằng chứng rằng giá trị không tồn tại. Hệ quả: eval vẫn chạy, vẫn xanh,
và một lớp kiểm biến mất mà không ai thấy.

Đo (offline, không tốn tiền):

```bash
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_latency_report.py --suite eval/questions.json --provider offline
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_risk_coverage.py  --suite eval/independent/answerable_manual.json --provider offline
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_metamorphic.py    --suite eval/independent/answerable_manual.json --provider offline
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_ledger_report.py
```

Đo có provider (**tốn tiền, ~20–30 phút mỗi lệnh**):

```bash
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_sql_baseline.py         --suite eval/independent/answerable_manual.json --provider deepseek
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_intent_policy_report.py --suite eval/independent/answerable_manual.json --provider deepseek
.venv/Scripts/python.exe scripts/record_search_cassettes.py --verify   # replay, KHÔNG gọi mạng
```

> **Đừng sửa file script trong lúc nó đang chạy.** Một lần đo độ trễ ~20 phút mất
> trắng vì đúng lỗi đó trong phiên này.

---

## 5. Việc dựng được tiếp theo, xếp theo giá trị

1. **Kéo `over_refusal_rate` 0,474 xuống.** Đây là con số yếu nhất và là con số
   duy nhất còn nhiều dư địa. `eval/reports/2026-08-27-independent-bank.md` §4 liệt
   bốn nhóm câu bị từ chối oan; ba vòng lặp rẻ của WP-A5 **cứu được 0 câu** ở đó
   (đo được, `cheap_loops_fired` toàn 0), nên nguyên nhân nằm chỗ khác.
2. **Bộ đề do người ngoài soạn.** Mọi con số năng lực hiện tại đo trên bộ do tác
   nhân **đã đọc codebase** sinh ra (`author_read_source_code: true` trên từng
   case). Chúng là **chặn dưới của thiên lệch**, không phải phép đo sạch.
3. **8 vi phạm còn lại của kiểm biến hình** — paraphrase brittleness thật, chi tiết
   ở `eval/reports/2026-08-27-metamorphic.json`.
4. **MR-3 và MR-8 skip 44/44**: bộ đề không có entity nguyên văn và không có câu
   cực trị. Hai quan hệ đó hiện **không kiểm được gì**.
5. **`execution.zero_row_is_a_result` chưa có trigger tự nhiên.** Nhánh kết quả
   rỗng chạy đúng và có test, nhưng không câu hỏi thật nào trong các bộ đề hiện có
   dẫn tới nó.

---

## 6. Tài liệu — thứ tự tin cậy khi mâu thuẫn

**code đang chạy > test/eval thực chạy > tài liệu kiến trúc > narrative viết tay**

| File | Dùng khi |
| --- | --- |
| `docs/Archibefore2208.md` | Đặc tả kiến trúc hiện tại · §11 bảng tra mã lỗi |
| `docs/Spec2308.md` | 25 WP đã thi công xong; giữ để đối chiếu ràng buộc `*-R*` |
| `eval/reports/2026-08-27-*.md` | **Mọi con số của phiên này**, kèm giới hạn |
| `artifacts/search_cassettes/REVIEW.md` | Việc còn lại của A12.3 |
| `CLAUDE.md` §5.1 | Bốn cạm bẫy đo lường, ba trong số đó cắn trong phiên này |

---

## 7. Bổ sung 28/08 — pipeline và đợt dữ liệu mới

### 7.1. Gốc rễ của "pipeline bị tù"

Hai điểm được nêu (notebook phải Run All bằng tay; server đọc CSV một lần lúc
khởi động) là **hai triệu chứng của một thiếu vắng**: không ai đặt tên cho bản dữ
liệu. Không có danh tính thì không có gì để CI gọi, để trỏ server vào, hay để
rollback về — nên sửa riêng lẻ từng cái không gỡ được.

Lỗi đo được chứng minh điều đó: sửa CSV giữa hai lần hỏi thì số đổi **668 → 568**
trong khi `dataset_version` vẫn đứng ở bản mà đáp án là 668. Evidence khai **xuất
xứ sai**. Nguyên nhân: một tiến trình có **hai vòng đời** cho cùng một dữ liệu
(`read()` không cache, `cached_property` thì cache). Hệ quả nặng nhất là **A6-R1
đúng trên thiết kế mà không thi hành được**.

Đã sửa (`311e3c1`, `0d52edd`):

| | |
| --- | --- |
| `data/versions/<id>/` + con trỏ `data/CURRENT` | file trỏ, **không symlink** — symlink trên Windows đòi admin |
| Notebook **505 → 30 dòng** | 482 dòng logic trích nguyên văn sang `gladiators.data.pipeline`; notebook gọi lại chính nó |
| `build_dataset.py --verify-against` | **`reproducible: true`** |
| `AgentRuntime.reload()` | 668 → đổi con trỏ → 568 → rollback → 668, **trong một tiến trình** |
| `ingest_raw.py` | kho raw bất biến có mốc; `data/raw/` **không đụng** |

Một quyết định đáng nhớ: **so byte là ngưỡng sai cho cột số thực.** Dựng lại lệch
1/2184 dòng ở mức 1,6e-9 — trôi phiên bản numpy, không phải đổi logic. Ngưỡng
đúng là schema khớp tuyệt đối + số khớp trong `rtol=1e-6`, **kèm báo cáo
`max_rel_deviation`** để biên đó tự kiểm được.

### 7.2. Đợt dữ liệu 27/08 — KHÔNG dùng thay thế được

`raw_extra_data/` (commit `6a5af5e`) không đụng `data/processed/`, nên **mọi con
số đã đo vẫn còn giá trị**. Nó là mở rộng: giữ đủ 1157 listing, thêm 119, dải
01–21/07.

**Nhưng nó không dựng nổi một dataset đầy đủ** (`audit_raw_drop.py`): thiếu hẳn
`category_platform`, thiếu `catid`/`key`/`platform`/`username`, và **`products`
chỉ đủ 26/44 cột**.

Hai bẫy phải biết trước khi ai đó dùng:

1. **`products_timeseries` không phải chuỗi thời gian** — 1276/1276 listing xuất
   hiện đúng **một** ngày, 1154 dồn vào 21/07. Ai đọc tên file rồi hỏi "giá trung
   vị ngày 15/07" sẽ nhận một con số tính trên **13 listing**.
2. **`product_promotions` mới là bảng giá theo ngày**, nhưng nó **lệch chọn mẫu**
   (chỉ listing *có* bản ghi khuyến mãi, 83–92%/ngày). `build_price_panel.py`
   dựng panel **cân bằng 776×20** và in cảnh báo lệch **trong chính metadata**.

Đồng nghiệp nói đúng: **20 ngày không đủ mùa vụ tuần.** Nhưng dải này bao trọn
7.7, nên nó đủ cho một **nghiên cứu sự kiện**: mức giảm trung vị 34,9% → 32,8% →
26,5%. Ba khoảng rộng khác nhau (5/5/13 ngày) nên đó là **ba lát cắt, không phải
một đường**.

### 7.3. Còn treo

- **Quyết định dùng đợt 27/08 thế nào** — người quyết, không code thay được.
  `artifacts/raw_drop_audit.json` có bảng ở mức cột.
- **Bốn ứng viên đổi tên sai nếu áp mù**, nguy nhất là
  `shop_category_id → shopee_category_id` (0,941) — đúng phép nhầm mà
  `INV-SHELF-NOT-PLATFORM-CATEGORY` cấm. Cờ `name_vs_id` **không** bắt được ca
  này vì cả hai đều là mã; giới hạn đó ghi rõ trong test.
- **Gộp bố cục raw mới vào `data/raw`** để pipeline đọc được: chưa làm, và không
  nên làm trước khi có quyết định ở trên.
