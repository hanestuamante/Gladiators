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

- Dataset đóng băng: **3 snapshot 01–03/07/2026**, 3.341 dòng, 1.157 listing, 20 shop, 2 market (vn/id).
- Grain nhỏ nhất là **product listing** = `{country}:{shop_id}:{item_id}`. **Không có SKU.**
- Catalog: **83 semantic object** (`domain/catalog.py`). Mọi câu hỏi phải rơi vào
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
```

Trạng thái đo ngày 08/08 tại `1df8e5b` — **có regression chưa sửa**:

| Suite | Hiện tại | Mốc cũ |
| --- | --- | --- |
| `pytest -q` | **804 passed, 1 skipped** | — |
| boundaries 9×3 | **1.0** | 1.0 |
| Phase 6 external | **12/12** `offline-no-network` | 12/12 |
| legacy `questions` 60×3 | **0.65** (21 case fail) | 1.0 |
| V2 11×3 | **0.879** (2 fail) | 1.0 |
| A19 6×3 | **0.833** (1 fail) | 1.0 |

Cả 21 case fail chung **một** nguyên nhân, và nó là biến thể của bẫy §3.1: message
`A-AMBIGUOUS` echo tên listing ứng viên, tên chứa chữ số (`"... Cream 30 Gr"`) →
`verifier.scan_numbers` đọc thành claim `30.0` không có evidence → `passed=False`.
Đây là **false positive của verifier**, không phải câu trả lời sai — nhưng chưa sửa.
Regression đã có sẵn ở `origin/MVP_Dai_V2` (645d558), không phải do commit local.

**Bất kỳ câu legacy nào chuyển sang `A22-*` là false positive của alignment — sửa
checker, không sửa expected.**

### 5.1. Hai luật vận hành

1. **Xác minh bằng hành vi, không bằng cấu trúc.** Ref do tool tính trông giống
   hệt measure thật; context item bị drop trông giống hệt item chưa từng có; điểm
   bị void trông giống hệt điểm khoẻ mạnh. Cấu trúc không phân biệt được, hành vi
   thì có.
2. **Harness báo lạ thì nghi harness trước.** Đã có harness nuốt exception khiến
   188 phép đo chạy với input rỗng.

---

## 6. Trạng thái hiện tại

- P5 topic routing / P6 decomposer chạy **shadow** — ghi verdict, **không** đổi
  câu trả lời. `eval/topic_gate.json` có `gate_open=false`; 5/5 automatic check
  PASS, 6 metric còn lại `pending_oracle` **chờ reviewer**, cố ý không tự chấm.
- Live search (Tavily) mặc định **OFF**; E6 `PENDING`, chưa sign-off.
- Đang chờ người quyết (không code thay được): 2 luật chất lượng dữ liệu của DR1,
  PAM golden review, claim-boundary review P13, fixture gap TC34, policy sentinel
  price TC19.

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
