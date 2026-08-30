# Gladiators — hướng dẫn cho AI agent

> **Đọc file này trước khi sửa bất cứ thứ gì.** Codebase này có nhiều lớp nhìn
> từ ngoài giống hệt nhau nhưng nghĩa khác hẳn. Sửa mà không hiểu bất biến sẽ tạo
> ra câu trả lời trôi chảy và sai — thứ nguy hiểm nhất mà hệ thống này tồn tại để
> chống lại.

Hệ thống trả lời câu hỏi phân tích thương mại điện tử (VN + ID) từ một dataset
đã đóng băng, với ràng buộc: **mọi con số hiển thị phải truy vết được về evidence,
và không bao giờ được đoán.**

---

## 1. Bắt đầu ở đâu: dùng code graph, đừng đọc mò

Repo có knowledge graph dựng sẵn bằng [graphify](https://github.com/) tại
`graphify-out/` (gitignored, dựng lại bằng lệnh bên dưới).

```bash
graphify update .                       # rebuild sau khi code đổi (không cần LLM)
graphify explain "workflow.py"          # node này nối với gì
graphify path "StructuredRequest" "LogicalQueryPlan"   # đường ngắn nhất giữa hai khái niệm
```

Đọc `graphify-out/GRAPH_REPORT.md` để có bản đồ community. Quy mô hiện tại:
**3601 node, 7880 edge, 263 community, 0 import cycle.**

**God node — các trừu tượng lõi, đụng vào là ảnh hưởng rộng:**

| Node | Edge | Vai trò |
| --- | ---: | --- |
| `LogicalQueryPlan` | 134 | IR v1.0, thứ duy nhất compile được sang SQL |
| `AgentRuntime` | 102 | orchestrator, `workflow.py` |
| `Evidence` | 64 | bản ghi bắt buộc cho mọi số hiển thị |
| `PlanNode` | 62 | một bước trong plan DAG |
| `StructuredRequest` | 56 | output của parse, input của gate |

---

## 2. Luồng chạy (S1→S9)

```
câu hỏi
 │
S1 parse      parser.py           → StructuredRequest (intent, entity, countries, qualifiers)
S2 route      external/router.py  → internal_only | hybrid | external_only | clarify | abstain
S3 entity     entity_resolution.py→ ID chính xác → tên → fuzzy → BGE; margin thấp ⇒ CLARIFY
S4 gate-pre   gate.py             → allow | clarify | abstain
 │
 ├─ S5a internal  macro đã chứng nhận (macros.py) → check_macro_shape
 │                hoặc open analytical → open_planner → validator → check_plan_alignment
 │                → compiler.py (SQLGlot, SELECT-only) → executor.py (DuckDB read-only)
 │
 └─ S5c external  search_planner → Tavily → relevance → web_extract → admission
                  (cờ mặc định OFF; luôn clamp context_only)
 │
S6 evidence   contracts.Evidence  + check_evidence_alignment
S7 generate   workflow._generate  template deterministic | LLM đọc ContextBundle
S8 verify     verifier.py         mọi số phải khớp evidence; citation phải có thật
S9 gate-out   check_answer_alignment + final verify → fail ⇒ A-VERIFICATION-FINAL
```

Ba lớp kiểm **khác nhau**, đừng nhầm:

| Lớp | Hỏi gì | Ở đâu |
| --- | --- | --- |
| **Gate** | Được phép trả lời không? | `gate.py` |
| **Alignment (A22)** | Có đang trả lời **đúng câu hỏi** không? | `alignment.py` |
| **Verifier** | Số hiển thị có evidence không? | `verifier.py` |

Lỗi TC29/TC39 lọt vì gate cho phép ✓, verifier pass ✓, nhưng trả `474 listing`
cho câu hỏi về mức giảm giá. A22 sinh ra để lấp đúng khe đó.

---

## 3. Bất biến — vi phạm là hỏng hệ thống, không phải hỏng một câu

1. **LLM không bao giờ tính số, không bao giờ quyết định gate.** LLM chỉ: đoán
   intent (P1), sinh plan IR (P8), sinh search query (P5), trích span (P6), diễn
   giải câu chữ (P2). Mọi output của LLM phải qua validator deterministic trước
   khi được phép ảnh hưởng bất cứ gì.
2. **`LogicalQueryPlan.source_tier` khoá `btc_dataset`.** External data không bao
   giờ đi qua analytical compiler/DuckDB.
3. **External evidence luôn `source_tier="external"`, `mapping_status="needs_review"`,
   `admission="context_only"`.** Cấm tính toán hoặc suy nhân quả xuyên tier
   (`A20-TIER`).
4. **`Evidence` object là bất biến.** `ContextBundle` chỉ chứa **bản copy** đã
   guard. Sửa `Evidence` gốc ⇒ `verifier._claim_value_matches` lệch ⇒ mọi câu trả
   lời chuyển `A-VERIFICATION-FINAL`.
5. **Không mở raw-SQL path ở runtime** dưới bất kỳ hình thức nào.
6. **Fail-closed.** Không chắc thì `clarify`/`abstain`. `clarify` không phải lỗi —
   với câu mơ hồ hoặc thứ dataset không có, đó là hành vi đúng.
7. **Schema đổi phải additive/backward-compatible.** Fixture cũ không được hỏng
   âm thầm.

### 3.1. Cạm bẫy đã cắn người thật

- **Không viết chữ số vào message abstain.** `verifier.scan_numbers` quét mọi số
  trong answer và đòi evidence hậu thuẫn. Câu abstain không mang evidence, nên
  "1.157 listing" trong `capability_messages` bị chấm là số bịa — đã làm eval rơi
  từ 1.0 xuống 0.77. Mô tả phạm vi **bằng lời**.
- **`nan is None` là `False`.** Đã khiến 63 listing bị void điểm được gán nhãn
  "Steady" — tức "không chấm được" hiện ra thành "bình thường".
- **Thiếu dữ liệu thì gắn cờ, không điền 0.** Điền 0 làm "không đo được" trông
  giống hệt "đo được và bằng phẳng".
- **Một grain bị chọn ngầm là một câu hỏi khác bị trả lời ngầm.** Khi nhiều grain
  đều hợp lý, analyzer **từ chối** thay vì chọn theo path cost hay thứ tự tên.
- **Ánh xạ chữ→ký hiệu là chỗ hỏng, không phải phần suy luận.** Mọi bug thật đã
  gặp đều ở biên này: `"giá trị"`→`measure.price`, `"Đánh giá"`(động từ)→`measure.rating`,
  `"Voucher ID"`→country Indonesia, `"$7.7 billion"`→trùng anchor chiến dịch `7.7`.

---

## 4. Mô hình dữ liệu

- **Bản đang phục vụ (31/08): 20 snapshot 01–21/07/2026**, 22.695 dòng,
  1.276 listing, 20 shop, 2 market (vn/id). `dataset_version` `0bdaf214249f0507`,
  phát hành ở `data/versions/906fc8289f10eca1/`, `data/CURRENT` trỏ vào đó, và
  `data/processed` mang đúng nội dung đó.
- **Bản đóng băng cũ** (3 snapshot 01–03/07, 3.341 dòng, 1.157 listing,
  `27de9bff184f4f89`) nằm ở `data/versions/a3eb6936b1cc5603/` và trong git
  history trước `MVP_Dai_V2`. Ba ngày chồng lấn tái lập đúng: 3.341/3.341 dòng,
  1.157/1.157 listing, giá khớp tới từng đồng. **Trừ `rating`**: dump mới lưu
  làm tròn 2 chữ số (4,896159 → 4,90) nên 7/12 quan sát chồng lấn lệch ở chữ số
  thứ ba — cùng `rating_count`, cùng listing, cùng ngày, tức mất độ chính xác ở
  nguồn chứ không phải giá trị khác.
- **Dựng lại** (`data/raw_extended/` gitignored vì là dẫn xuất):
  `adapt_extract("raw_extra_data/datashopee", "data/raw_extended")` →
  `scripts/build_dataset.py --raw data/raw_extended --publish --activate`. Đã
  chứng minh là **điểm bất động**: dựng lại lần hai, lấy chính bản mới làm
  `reference_dir`, ra raw **trùng khít từng byte** (`e46492a6b4d96ef3`) — nên
  lệnh này chạy được mãi về sau, không chỉ đúng một lần. Mọi quyết định của bước
  nối ở `docs/qa/raw_extra_data_provenance.md` — đọc nó trước khi đụng adapter.
- **Đổi bản kéo theo bốn artifact phải dựng lại**, nếu không hệ nổ lúc khởi động
  hoặc mất một lớp kiểm trong im lặng: `artifacts/value_index.json`,
  `data/processed/observation_density.json`, `eval/independent/answerable_manual.json`,
  `eval/questions_multiturn.json`.
- **Cột đổi theo bản dữ liệu** — đây là đổi HỢP ĐỒNG với người dùng, không phải
  chi tiết kỹ thuật: `shopee_verified` cấp listing **không còn** (dump chỉ có cờ
  cấp SHOP; grain đổi, xem `extract_adapter` §4), và `rating`/`liked_count`/
  `monthly_sold`/`history_sold`/`discount_percent` chỉ được quan sát **một lần
  mỗi listing** thay vì mỗi đợt thu. Câu hỏi tổng hợp trên chúng nay bị W29 hỏi
  lại thay vì trả một con số tính từ vài quan sát.
- **`shop_stats_clean.csv` (panel ngày cấp shop) nay CÓ**, nên 11 measure
  `measure.shop_daily_*` dùng được. Nó vẫn khai ở `OPTIONAL_ARTIFACTS`: vắng mặt
  là trạng thái **được khai**, không phải lỗi. `shop_info` giữ nguyên grain cũ —
  panel KHÔNG chảy vào nó.
- Grain nhỏ nhất là **product listing** = `{country}:{shop_id}:{item_id}`. **Không có SKU.**
- Catalog: **99 semantic object** (`domain/catalog.py`), trong đó 11 measure
  `measure.shop_daily_*` đọc panel shop và chỉ dùng được khi đã thu artifact tuỳ
  chọn. Mọi câu hỏi phải rơi vào
  tập này hoặc bị từ chối. Đây là lý do bài toán hữu hạn hoá được.
- `monthly_sold` là **proxy hiển thị của một cửa sổ chưa xác nhận** — cấm cộng qua
  các snapshot (tính trùng). `estimated_recent_revenue` là proxy ước tính, luôn
  phải kèm chữ "ước tính".
- Zero-variance đã biết: `is_ad_bool` và `is_sold_out_bool` đều `False` trên toàn
  bộ dữ liệu → không phân tích được, chỉ nói được "dataset không quan sát được".

---

## 5. Kiểm chứng

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/run_evaluation.py --suite eval/questions.json --runs 3 --provider offline
.venv/Scripts/python.exe scripts/run_phase6_evaluation.py --suite eval/questions_external.json
.venv/Scripts/python.exe scripts/build_topic_gate.py

# Spec2308 — dựng lại artifact rồi đo (artifacts/ gitignored, phải dựng trước)
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_value_index.py
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_question_bank.py
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_multiturn_suite.py

PYTHONPATH=src .venv/Scripts/python.exe scripts/run_latency_report.py --suite eval/questions.json --provider offline
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_risk_coverage.py  --suite eval/independent/answerable_manual.json --provider offline
PYTHONPATH=src .venv/Scripts/python.exe scripts/run_metamorphic.py    --suite eval/independent/answerable_manual.json --provider offline
.venv/Scripts/python.exe scripts/run_evaluation.py --suite eval/questions_multiturn.json --runs 3 --provider offline
PYTHONPATH=src .venv/Scripts/python.exe scripts/build_ledger_report.py
```

**`artifacts/value_index.json` phải dựng trước khi đo.** Thiếu nó, vòng dò giá trị
(WP-A5.1) **im lặng bỏ qua** — đúng theo thiết kế, vì thiếu chỉ mục là thiếu thông
tin để kết luận chứ không phải bằng chứng rằng giá trị không tồn tại. Hệ quả: eval
vẫn chạy, vẫn xanh, và một lớp kiểm biến mất mà không ai thấy.

Trạng thái đo ngày **29/08/2026** tại `5224c23` (15/15 work package của
`docs/SolutionSpec2808.md` đã thi công phần máy làm được), `--provider offline`:

| Chỉ số (tên mới W9.1) | 27/08 | 29/08 |
| --- | ---: | ---: |
| `pytest -q` | 1200 passed | **1508 passed**, 1 skipped |
| `answerable_coverage` (bộ độc lập, 46 câu) | 0.526 | **0.85** |
| `answer_rate_all` | 0.4545 | **0.7391** |
| `over_refusal_rate` | 0.474 | **0.15** |
| `risk` · `over_answer_rate` | 0.0 · 0.0 | **0.0 · 0.0** (giữ qua MỌI mốc) |
| metamorphic (quan hệ đo được) | 0.910 | **1.0** (MR-3/MR-8 khai not_measured) |
| multiturn 24 ca / 48 lượt | 6 lượt lệch | **0** (cả nhánh stateless, 0 leak) |
| diagnose_refusals | 18 ca oan | **4** (2 A-MISSING-ADS chờ registry, 2 beats_template) |
| AURC | 0.0454 | **0.0294** |

Ablation SAU các khối mới: L0 ≡ L1 ≡ L2 vẫn trùng khít — "nút thắt là thiếu
khối, không phải cổng gác" đứng vững ở coverage 0.85. Còn chờ NGƯỜI/provider
(không code thay được): W9.4 bộ đề độc lập 60–100 câu cần hai người chú thích;
W14 giai đoạn B chờ data
owner duyệt `price-repdigit-nine`; W9.6 đo BGK-20 bằng provider thật; sáu
oracle topic gate chờ reviewer ký. Chú ý W9.1: khoá `coverage` cũ mang HAI
nghĩa — số mới đọc `answerable_coverage`/`answer_rate_all`.

Trạng thái đo cũ ngày **27/08/2026** tại `d4073c2`, `--provider offline`:

| Suite | Hiện tại | Mốc cũ |
| --- | --- | --- |
| `pytest -q` | **1200 passed, 1 skipped** | 804 passed |
| legacy `questions` 60×3 | **1.0** | 1.0 |
| V2 11×3 | **1.0** | 1.0 |
| A19 6×3 | **1.0** | 1.0 |
| boundaries 9×3 | **1.0** | 1.0 |
| ambiguity 4×3 | **1.0** | 1.0 |
| Phase 6 external | **12/12** `offline-no-network` | 12/12 |
| `dr2607` 40×1 | **1.0** | — |
| `p0_probes` 6×3 | **0.833** (1 fixture tự mâu thuẫn) | — |

Regression "0.65 / 0.879 / 0.833" ghi ở bản trước **không còn tái lập**, kể cả khi
checkout lại commit được nêu. Nguyên nhân chưa xác định; đừng dựa vào nó.

**Bảy suite trên đạt 1.0 chứng minh luật viết tay nhất quán với chính nó** — đó là
điểm **hồi quy**, không phải điểm **năng lực**. Con số năng lực nằm ở bộ đề sinh từ
dữ liệu (`eval/independent/`), và nó thấp hơn hẳn:

| Chỉ số | Giá trị | Nghĩa |
| --- | ---: | --- |
| `coverage` | **0.526** | Trả lời được 52,6% câu mà **dữ liệu** trả lời được |
| `over_refusal_rate` | **0.474** | Từ chối oan 47,4% |
| `risk` | **0.0** | Trong số đã trả lời, không câu nào sai |
| `over_answer_rate` | **0.0** | Không bao giờ trả lời thứ dữ liệu không có |
| `metamorphic_consistency_rate` | **0.910** | 308 phép kiểm quan hệ, không cần gán nhãn |
| `clarify_recovery_rate` | **0.75** | Lượt 2 lật được `clarify` thành `allow` (WP-A3) |
| AURC | **0.0454** | Bỏ gate+verifier: +4,5 điểm phủ, đổi lấy 9,1% rủi ro |

**An toàn nhưng quá thận trọng** — đó là câu tóm tắt đúng, và nó là điểm cần cải
thiện tiếp, không phải điểm cần giấu.

**Bất kỳ câu legacy nào chuyển sang `A22-*` là false positive của alignment — sửa
checker, không sửa expected.**

### 5.1. Hai luật vận hành

1. **Xác minh bằng hành vi, không bằng cấu trúc.** Ref do tool tính trông giống
   hệt measure thật; context item bị drop trông giống hệt item chưa từng có; điểm
   bị void trông giống hệt điểm khoẻ mạnh. Cấu trúc không phân biệt được, hành vi
   thì có.
2. **Harness báo lạ thì nghi harness trước.** Đã có harness nuốt exception khiến
   188 phép đo chạy với input rỗng.
3. **Hai bảng số giống nhau không có nghĩa là "không khác biệt".** Nó cũng có thể
   nghĩa là nhánh đang đo **chưa từng chạy**. WP-A11 đo P-A vs P-B ra hai bảng
   trùng khít; sự thật là `arbitrate` đọc nhãn LLM từ `parsed` **sau** khi năm
   nhánh precedence đã ghi đè nó, nên P-B trả `no_change` cho mọi câu và là code
   chết từ lúc viết. Tám test của nó đều xanh vì chúng gọi hàm **cô lập**. Thứ
   phát hiện ra là một khoá telemetry đếm số lần nhánh đó thật sự bắn — **mọi
   nhánh có điều kiện phải mang một khoá như vậy**, nếu không "đã đo" và "đã chạy"
   không phân biệt được.

---

## 6. Trạng thái hiện tại

- P5 topic routing / P6 decomposer chạy **shadow** — ghi verdict, **không** đổi
  câu trả lời. `eval/topic_gate.json` có `gate_open=false`; 5/5 automatic check
  PASS, 6 metric còn lại `pending_oracle` **chờ reviewer**, cố ý không tự chấm.
- Live search (Tavily) mặc định **OFF**; E6 `PENDING`, chưa sign-off.
- **Spec2308 đã thi công xong 25 work package** (làn A và làn B), và ba chỗ từng
  ghi là "chưa đo được vì cần mạng" **đã đo xong** — nhận định đó sai: máy phát
  triển có mạng và `.env` có sẵn khoá. Kết quả ở `eval/reports/`:
  - **WP-B5** (`2026-08-27-sql-baseline.md`): baseline "LLM viết SQL" trả **sai
    số mà không báo 65,9%**, hệ này **0%**. Baseline trả lời nhiều hơn nhưng chậm
    hơn 161 lần và đúng ít hơn ba lần.
  - **WP-A11** (`2026-08-27-intent-policy.md`): P-B bắn 10/44 ca nhưng **không đổi
    một outcome nào** ⇒ giữ `P-A` (A11-R3 đòi thắng, không phải hoà). Lần đo đầu
    tiên đo một thứ **không chạy** — xem cạm bẫy ở §5.1 dưới.
  - **WP-A12.3**: đủ 6 cassette, replay ổn định **kể cả khi socket bị chặn**. Còn
    lại đúng một việc là **người đọc và ký** (A12-R6); cột người duyệt trong
    `artifacts/search_cassettes/REVIEW.md` cố ý để trống.
- **Đường có LLM parser vượt ngân sách độ trễ 2–3 lần ở p95** (30–50 s so với mốc
  15 s). Con số 0,21 s trong `2026-08-27-latency.md` là của đường **offline** —
  tức cấu hình đang phát hành, vì `GLADIATORS_ENABLE_LLM_PARSER` mặc định tắt.
- Đang chờ người quyết (không code thay được): 2 luật chất lượng dữ liệu của DR1,
  PAM golden review, claim-boundary review P13, fixture gap TC34, policy sentinel
  price TC19; 4 nghi vấn `suspect` của kiểm biến hình; và
  `p0-grouping-dropped-official-shop` — fixture đó khai `expected_action="clarify"`
  nhưng `baseline` trong chính nó ghi `abstain/A19-PLAN`, và hệ khớp baseline.

---

## 7. Tài liệu — đọc theo thứ tự tin cậy

Thứ tự khi mâu thuẫn: **code đang chạy > test/eval thực chạy > tài liệu kiến trúc
> narrative viết tay**.

| File | Dùng khi |
| --- | --- |
| `docs/Archibefore2208.md` | **Đặc tả kiến trúc hiện tại** — 9 chặng, 3 lớp kiểm, 11 invariant, mô hình dữ liệu (§14), mã lỗi (§11) |
| `docs/TCresultbefore2208.md` | Testcase, ground truth, kết quả; mỗi lớp kiểm sinh ra từ ca thật nào |
| `docs/Backlogbefore2208.md` | Chưa hiện thực, chia theo thứ đang chặn nó |
| `docs/design/Metadata_Model_And_Binding_Layer.md` | Thiết kế tầng binding metadata ↔ vật lý |
| `docs/qa/DR TASK 1407.md` | Nguồn của `eval/dr2607.json` — **script parse file này, không được xoá** |
| `docs/IMPLEMENTATION_HANDOFF_2026-08-27.md` | Bàn giao phiên 27/08: việc còn treo, lỗi im lặng đã tìm ra, lệnh chạy lại |

Toàn bộ tài liệu plan/handoff/kiến trúc cũ đã gộp vào ba file `*before2208.md` và
xoá khỏi `docs/` ở `24efc77`. Bản gốc nằm trong git history; **đừng khôi phục vào
cây làm việc** — chúng mâu thuẫn với code đang chạy, và đó là lý do bị gộp.

---

## 8. Quy ước khi sửa

- Viết code khớp phong cách xung quanh: mật độ comment, cách đặt tên, idiom.
  Comment giải thích **vì sao**, không mô tả lại code.
- Không sửa golden/fixture chỉ để ép test xanh. Đổi expected phải là thay đổi
  contract **có chủ đích**, ghi rõ lý do trong commit.
- Không dùng "done", "compliant", "production-ready", "all tests pass" nếu không
  đính kèm lệnh + kết quả tương ứng.
- Không đổi trạng thái E6 trong `PHASE6_ACCEPTANCE_SIGNOFF.md`, không bật cờ
  mặc định trong source.
- Docstring khẳng định sai về tính chất an toàn còn nguy hơn thiếu tính năng —
  vì không ai kiểm lại nó.
