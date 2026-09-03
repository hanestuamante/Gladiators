# SolutionSpec2808 — Đặc tả kỹ thuật thi công

> **Cơ sở kiến trúc:** `docs/Archi2808.md` (source cuối d14fa75; HEAD 3118022 chỉ
> thêm dữ liệu/tài liệu sau source đó, `git diff d14fa75 HEAD -- src/` rỗng).
> **Nền test:** ✅ `1207 passed, 1 skipped` — chạy lại 29/08 bằng lệnh ở §21.1
> với `--basetemp` ngắn; không có assertion nghiệp vụ nào hỏng.
> **Nền hành vi:** ✅ chạy lại **mọi** bộ đề có nhãn ngày 29/08 (§1.6) — bộ 44
> câu giữ đúng 19 ca lệch của §1.2, và ba lớp lỗi nữa lộ ra ngoài bộ đó:
> `questions_critic` 3/4, `questions_multiturn` 6/48 lượt, và **24/84 câu xếp
> hạng trả HTTP 500**. Ba lớp đó thành `W13` (§14), `W14` (§15), `W15` (§16).
> **Phạm vi:** đặc tả thay đổi ở mức file · symbol · hợp đồng · số nghiệm thu.

---

## §0. Cách đọc và ràng buộc bao trùm

### 0.1. Ký hiệu

| Ký hiệu | Nghĩa |
| --- | --- |
| ✅ | Đã chạy code thật ngày 28/08 và ghi lại kết quả; lệnh tái lập ở §21 |
| ◻ | Con số lấy từ artifact có sẵn trong repo, chưa chạy lại |
| ⚠ | Giả định — chưa có phép đo; không được dùng làm cơ sở nghiệm thu |

Mọi con số nghiệm thu trong tài liệu này mang dấu ✅: chúng được tính bằng cách
dựng plan thật, compile thật, chạy DuckDB thật trên `data/processed/`.

### 0.2. Bảy bất biến không được phá

Kế thừa nguyên văn từ `Archi2808` §1 và `CLAUDE.md` §3. Không thay đổi nào trong
tài liệu này được nới một trong bảy điều dưới đây:

1. LLM không tính số, không quyết gate.
2. `LogicalQueryPlan.source_tier` khoá `btc_dataset`.
3. External evidence luôn `context_only`, không đi vào aggregate nội bộ.
4. `Evidence` không được sửa sau khi tạo; mọi enrichment dùng
   `model_copy(update=...)`; `ContextBundle` chỉ giữ bản copy đã guard. W1 phải
   cưỡng chế điều này bằng `ConfigDict(frozen=True)`, không chỉ dựa vào kỷ luật
   của caller như trạng thái hiện tại trong `Archi2808` §7.
5. Không mở raw-SQL path ở runtime.
6. Fail-closed: không chắc thì `clarify`/`abstain`.
7. Schema đổi phải additive; fixture cũ không được hỏng âm thầm.

**Hai ràng buộc số học phải giữ ở MỌI mốc nghiệm thu:**

```
risk              = 0.0
over_answer_rate  = 0.0
```

Một thay đổi làm tăng coverage nhưng đụng vào hai con số này là một thay đổi bị
từ chối, không phải một đánh đổi.

### 0.3. Checklist bắt buộc cho mỗi thay đổi

`Archi2808` §16 đòi mọi thay đổi kiến trúc cập nhật đồng thời tám thứ. Bảng dưới
là dạng kiểm được của nó; mỗi work package ở §2–§11 khai rõ ô nào nó chạm.

| # | Hạng mục | Bằng chứng phải kèm |
| -: | --- | --- |
| 1 | registry / contract | diff registry + hash mới |
| 2 | call site runtime nếu khai WIRED | `rg <symbol> src/` thấy call site ngoài chính module |
| 3 | test hành vi | test chạy qua runtime, không chỉ gọi hàm cô lập |
| 4 | trace / telemetry | khoá đếm số lần nhánh **thật sự bắn** (`CLAUDE.md` §5.1.3) |
| 5 | bảng rule_id | `Archi2808` §12 |
| 6 | metadata verifier hash | `scripts/verify_metadata_bindings.py` |
| 7 | eval report | khi đổi default hoặc đổi trade-off |
| 8 | ma trận WP + khoảng trống | `Archi2808` §14, §15 |

### 0.4. Ba fixture khoá hành vi — sửa phải theo đúng thủ tục

| Fixture | Khoá gì | Thủ tục đổi |
| --- | --- | --- |
| `tests/fixtures/synthesizer_equivalence_baseline.json` | 173 câu; 58 câu có plan, so bằng `model_dump_json()` sau khi chuẩn hoá đuôi `:<relations>:1.x`. ⚠ Nó khoá **hình dạng** plan và **không bao giờ compile hay chạy** plan — ✅ 5/58 entry mang hình `Scan→Filter→Rank` không thoả hợp đồng output của chính chúng (§14.2). `tests/test_plan_executes_its_contract.py` (W13.4) là phép kiểm còn thiếu | Chỉ được đổi kèm lý do contract; entry biến mất phải nằm trong allowlist có ghi lý do |
| `eval/p0_probes.json` + `eval/independent/p0_probe_expected.json` | action · plan · oracle · answer của 9 probe | Ba bước ghi ở docstring `tests/test_p0_regression_lock.py`; `xfail_strict=true` nên contract chuyển xanh phải được khai báo |
| Bảy suite eval viết tay | điểm hồi quy `1.0` | Ghim `dataset_version` đóng băng; không đo năng lực trên chúng |

---

## §1. Nền sự thật — đo lại toàn bộ ngày 28/08, mở rộng ngày 29/08

### 1.1. Ground truth số học

✅ Tính trực tiếp bằng pandas trên `data/processed/`, không qua `gladiators`:

| Đại lượng | VN | ID |
| --- | ---: | ---: |
| listing 2026-07-03 | **668** | **474** |
| listing 2026-07-01 | **581** | **474** |
| delta 01/07→03/07 | **+87** | **0** |
| brand phân biệt 03/07 | **30** | **12** |
| shop | **10** | **10** |
| shop chính hãng | **7** | **9** |
| listing của shop chính hãng 03/07 | **465** | **471** |
| giá trung vị 03/07 (đã loại sentinel) | **132 000** | **78 900** |
| rating trung vị 03/07 | **4.923603693479375** | **4.901304084208852** |
| listing brand `Bibica` VN 03/07 | **96** | — |
| listing shop `Richy - Chi nhánh Miền Nam` VN 03/07 | **120** | — |
| `Bibica` ∩ `Richy - Chi nhánh Miền Nam` | **0** (giao rỗng thật) | — |

Ghi chú `Bibica`: 96 listing nằm trọn trong `Bibica Official Store`. Ca giao rỗng
vì thế là zero-row **thật**, không phải zero-row do lọc hỏng.

### 1.2. Bản đồ 19 ca lệch — nguồn duy nhất để chấm tiến độ

✅ Chạy `eval/independent/answerable_manual.json` (44 câu) qua
`create_runtime("offline")`: **19 ca lệch `expected_action`**, trong đó 18 ca
`answerable=true` (từ chối oan) và 1 ca `answerable=false` từ chối bằng nhãn khác.

| Ca | Câu hỏi | Rule hiện tại | Nguyên nhân kỹ thuật đã xác định | Gỡ bởi |
| --- | --- | --- | --- | --- |
| ans011 · ans012 | listing là quảng cáo | `A-MISSING-ADS` | `parser.UNSUPPORTED["ads"]` khớp `"quang cao"` ⇒ intent thành `unsupported:ads`, dù câu chỉ hỏi cờ `is_ad` đã quan sát | **W8** |
| ans013 · ans014 | listing đã hết hàng | `A19-PLAN` | `"het hang"` nằm trong `_LITERAL_QUALIFIER_MARKERS`; không có ref catalog nào bind `is_sold_out_bool` | **W8** |
| ans017 · ans018 | listing có voucher (ID) | `A-VOUCHER-ID` | gate chặn structured voucher cho ID | **W8** |
| ans019 · ans020 | số listing thay đổi 01/07→03/07 | `A22-ALIGN-DATE` | parser cho `time_scope=(01,03)` nhưng `_synthesis_beats_template` trả `False` ⇒ rơi về template `listing_count` ghim 03/07; alignment chặn đúng | **W6** |
| ans028 · ans030 | có bao nhiêu **brand** khác nhau | `A19-CAT` clarify | `"brand"` chỉ bind `dim.brand`; `derived.brand_count` chỉ có alias `"bao nhiêu thương hiệu"`, không có `"bao nhiêu brand"` ⇒ `requested_measures` rỗng | **W4** |
| ans031 · ans032 · ans033 · ans034 | shop chính hãng | `A19-PLAN` | plan **đúng và chạy được**; bị `risk.score_plan` chấm 3 (`relation_count=1`, `plan_shape=2`) ⇒ `requested_mode="critic"` ⇒ `enable_critic=False` ⇒ `blocked` | **W7** |
| ans035–ans038 | giá / rating **trung vị** | `A19-PLAN` | `_synthesis_beats_template` trả `False` ⇒ synthesizer không được thử; và ngay cả khi thử, synthesizer chỉ phát `Aggregate` khi `dimensions or counted_unit` | **W5** |
| ans044 | giá đối thủ ngoài sàn | `A-CROSS-CURRENCY-SCOPE` clarify | câu không trả lời được; nhãn hiện tại mô tả sai vấn đề (route external mới đúng) | **W8.4** |

Phân bố: **12 ca thiếu năng lực** (W4–W7) · **6 ca chờ ngữ nghĩa nghiệp vụ** (W8)
· **1 ca sai nhãn từ chối** (W8.4).

⚠ **Bản đồ này chấm tiến độ trên bộ 44 câu, và chỉ trên bộ đó.** Phép chạy lại
toàn bộ ngày 29/08 (§1.6) cho thấy ba lớp lỗi không ca nào trong 44 câu chạm
tới. Câu ở §1.5 — *"một bộ đề duy nhất không đủ để lái thiết kế"* — đúng thêm
một lần nữa, và lần này với một lớp lỗi nặng hơn mọi ca từ chối oan: một câu
hỏi trả lời được đi ra bằng traceback (§1.6.3).

### 1.3. Hai công thức cùng tên `coverage` — nguồn của mọi tranh cãi số

✅ Đã định vị chính xác:

| Nơi | Dòng | Công thức | Giá trị hôm nay |
| --- | --- | --- | ---: |
| `scripts/run_evaluation.py` | `:141` | `answered ∩ answerable / answerable` | 20/38 = **0.5263** |
| `scripts/run_risk_coverage.py` | `:97` | `answered / labelled` | 20/44 = **0.4545** |

Hai script, một cái tên, hai mẫu số. Đây là lý do cùng một hệ được mô tả lúc
45,45% lúc 52,63%. **W9.1** đặt lại tên cho cả hai.

### 1.4. `raw_extra_data` — đo lại, và bốn cái bẫy

✅ Toàn bộ đo trực tiếp:

| Đo | Kết quả |
| --- | --- |
| Shop | 20/20 trùng khớp `data/processed` |
| Item | 1157 item cũ **có đủ**, thêm 119 ⇒ superset 1276 |
| Ngày trong `product_promotions` | **20 ngày**: 2026-07-01 → 2026-07-21, **thiếu 2026-07-12** |
| Ngày trong `shop_stats` | 20 ngày × 20 shop |
| `products_timeseries` | 1276 dòng / 1276 item / **đúng một dòng mỗi item**; cột `date` là *ngày quan sát cuối*, 19 giá trị phân biệt |
| `unit_sold` | **0 ở toàn bộ 1276 dòng** |
| `public/test_*.csv` | rỗng hoàn toàn — `pandas.read_csv` ném `EmptyDataError` |
| `products.created_at` | **distinct = 1** (`2026-07-22 17:23:49.200 +0700`) ⇒ một lần backfill |

**Câu tóm gọn:** thêm 18 ngày lịch sử **giá**, không thêm ngày nào lịch sử **bán**.

✅ Và bằng chứng nó sẽ phá golden nếu ghép trước:

- 12 listing hiện có `<2` snapshot; **10 trong số đó sẽ có ≥2** sau khi ghép.
- `bnd09` khoá listing `id:1379527329:44863265062` với kỳ vọng
  `abstain`/`A-INSUFFICIENT-SNAPSHOTS`. Listing đó hiện có **1** snapshot, trong
  bộ mới có **18**. Luật `tool_dispatch.py:111` (`nunique() < 2`) sẽ không nổ.

Vì vậy thứ tự ở §18 đặt **W10 sau cùng**, và bộ mới vào như `dataset_version`
thứ hai chứ không đè bộ cũ.
---

### 1.5. BGK-20 — chạy lại offline ngày 28/08, và bốn ca không work package nào gỡ

✅ **Nguồn cần nói trước:** con số `4/13` là của **23/08**, đo bằng provider
`deepseek` với LLM generation BẬT. Phép chạy dưới đây là `--provider offline`,
tức **cấu hình đang phát hành** nhưng **không cùng điều kiện với lần đo 23/08**.
Nó không thay thế `W9.6`; nó trả lời một câu hẹp hơn: *đường tất định hôm nay
làm gì với 20 câu đó.*

✅ `git diff d14fa75 HEAD -- src/` **rỗng** — commit `6a5af5e` chỉ thêm dữ liệu
thô. Nên mọi phép đo ngày 27/08 và 28/08 đứng trên **cùng một source**.

Kết quả offline 28/08: **4 trả lời đúng · 7 từ chối đúng · 9 bỏ lỡ** — trùng khít
phân bố 23/08. ✅ Bốn ca đúng vẫn cho đúng số: `bgk01` = 10 · `bgk03` = 577 ·
`bgk07` = 474 · `bgk10` = 577/91.

**Chín ca bỏ lỡ — chẩn đoán mới, và work package nào gỡ:**

| Ca | Rule hôm nay | Nguyên nhân đã xác định | Đáp án đúng | Gỡ bởi |
| --- | --- | --- | ---: | --- |
| `bgk02` | `clarify` `A22-ALIGN-MEASURE` | ✅ synth ra plan `measure.price:median:nogroup` nhưng **không có node `Aggregate`** ⇒ trả 668 dòng thô ⇒ alignment chặn | **132 000** | **W5** |
| `bgk04` | `abstain` `A19-PLAN` | như trên, với `measure.images_count` (`valid_aggregations = median, min, max`) | **6** | **W5** |
| `bgk06` | `abstain` `A19-PLAN` | như trên, với `measure.rating` | **4.901304084208852** | **W5** |
| `bgk09` | `abstain` `A19-PLAN` | ✅ plan **đã có `Aggregate`** (vì có group-by) và **chạy đúng**: 10 shop, `108166524 → 212 080` khớp pandas. Bị chặn bởi thang leo thang | 10 nhóm | **W7** |
| `bgk08` | `abstain` `A19-PLAN` | ✅ `mode = deterministic_template`, `analytical_kind = top_shop_by_listing_count` ⇒ `complexity_level = "L3"` ⇒ `critic` **bất kể điểm** | shop `809769142` | **W7** (xem 8.3.1) |
| `bgk20` | `clarify` `A22-ALIGN-DATE` | cùng lỗi với `ans019` | **+87** | **W6** |
| `bgk05` | `clarify` `A22-ALIGN-MEASURE` | ✅ `">50%"` **không bao giờ được bind thành predicate**; parser ra **hai** measure (`derived.product_count` + `measure.discount_percent`) ⇒ `synthesize` trả `None` vì `len(measures) != 1` | **8** | **W11** |
| `bgk11` | `clarify` `A22-ALIGN-MEASURE` | ✅ `"tỷ lệ"` bind **không ref nào**; câu rơi về `measure.discount_percent` + aggregation mặc định `median`. Tức *"tỷ lệ listing có giảm giá"* bị đọc thành *"mức giảm giá trung vị"* — **hai đại lượng khác hẳn nhau** | **96.26 %** | **W11** |
| `bgk12` | `clarify` `A19-CAT` | ✅ `measure.liked_count` có alias `"số lượt thích"`, `"lượt yêu thích"`, `"likes"` — **không có `"lượt thích"` trần**. `find_in("nhieu luot thich nhat")` trả `[]` | **10 449** (1 listing đạt đỉnh) | **W4** (xem 5.5) |

**Dự phóng ⚠, không phải số đã đo:** W4–W7 gỡ 6 ca (`bgk02` `bgk04` `bgk06`
`bgk08` `bgk09` `bgk20`), W11 gỡ 2 ca (`bgk05` `bgk11`), W4.3 gỡ `bgk12` ⇒
**4/13 → 13/13**. Con số này chỉ đúng nếu `W9.6` chạy lại bằng provider thật xác
nhận, và nó là **điều kiện nghiệm thu**, không phải một kết luận.

> **Điều Next2508 nói đúng và tài liệu này suýt bỏ sót:** §3.3 của nó liệt kê
> *"predicate làm measure"* là một trong năm khối cần đúc. Khối đó **không xuất
> hiện** trong 18 ca từ chối oan của bộ 44 câu (§1.2), nên nếu chỉ thiết kế theo
> bộ đó thì `bgk05` và `bgk11` bị bỏ lại. Đây là bằng chứng cụ thể cho `W9.4`:
> **một bộ đề duy nhất không đủ để lái thiết kế.**


### 1.6. Chạy lại **toàn bộ** suite ngày 29/08 — ba lớp lỗi bộ 44 câu không thấy

✅ Bảng dưới là kết quả chạy `create_runtime("offline")` qua **mọi** suite có
nhãn kỳ vọng trong `eval/`, cộng một phép quét sinh tự động. Lệnh ở §21.14.

| Suite | Ca | Lệch | Ghi chú |
| --- | ---: | ---: | --- |
| `eval/independent/answerable_manual.json` | 44 | **19** | trùng khít bản đồ §1.2 |
| `eval/questions.json` (suite CI) | 60 | 0 | |
| `eval/dr2607.json` | 40 | 0 | chấm theo `action` + `allowed/forbidden_rule_ids` |
| `eval/questions_v2` · `_schema` · `_counting` · `_boundaries` · `_a19` · `_ambiguity` | 41 | 0 | |
| `eval/questions_critic.json` | 4 | **3** | §1.6.1 |
| `eval/questions_multiturn.json` | 24 ca · 48 lượt | **6 lượt** | §1.6.2 |
| BGK-20 | 20 | 9 bỏ lỡ | trùng khít §1.5 |
| Quét xếp hạng sinh tự động (3 chủ thể × 7 measure × 2 chiều × 2 thị trường) | 84 | **24 CRASH** | §1.6.3 |

Nền test không đổi: ✅ `1207 passed, 1 skipped`.

Ba lớp cuối **không có work package nào sở hữu** trong W1–W12. Chúng thành
`W13` (§14), `W14` (§15), `W15` (§16).

#### 1.6.1. `questions_critic` — bộ đề khai kỳ vọng mà không ai chấm

✅ `cq02` `cq03` `cq04` khai `expected_action: "allow"`; runtime trả
`abstain` / `A19-PLAN`. Đây **cùng một nguyên nhân với `ans031`–`ans034`**
(thang leo thang, §8), nhưng bộ đề này chưa từng xuất hiện ở §1.2 vì
`expected_action` của nó **không được assert ở đâu cả**: hai test đọc file này
(`tests/test_evidence_consistency.py:100`, `tests/test_synthesizer_equivalence.py:41`)
chỉ lấy `case["question"]` làm **đầu vào**.

✅ Và nó bị chặn ở **cả hai** cấu hình:

| Cấu hình | Lý do từ chối |
| --- | --- |
| `enable_critic=False` (phát hành) | `risk.py:105` — "Plan critic chưa qua acceptance bắt buộc hoặc đang bị kill-switch tắt." |
| `GLADIATORS_ENABLE_CRITIC=1` trên `create_runtime("offline")` | "Plan critic được yêu cầu nhưng chưa có LLM provider hỗ trợ P9." |

Tức **không có cấu hình nào của bản phát hành trả lời được `cq02`–`cq04`**. Vị
từ tất định ở §8.4 gỡ cả hai lối; W15 làm cho bộ đề này được chấm.

#### 1.6.2. `questions_multiturn` — suite được sinh ra và không ai chạy

✅ `scripts/build_multiturn_suite.py` sinh 24 ca / 48 lượt. `rg questions_multiturn`
trên `src/`, `tests/`, `scripts/` chỉ trả về **chính script sinh ra nó**. Không
có harness nào chấm nó.

Chạy tay: **6/48 lượt lệch**.

| Ca | Lượt 2 | Nhận được | Nguyên nhân | Gỡ bởi |
| --- | --- | --- | --- | --- |
| `mt005` `mt011` `mt017` `mt023` | *"Shop nào có nhiều listing nhất?"* | `abstain` `A19-PLAN` | `top_shop_by_listing_count` ⇒ `L3` ⇒ critic | **W7** |
| `mt016` `mt022` | *"Sản phẩm nào có giá cao nhất?"* (ID) | `abstain` `A22-ALIGN-RANK-TIE` | hai dòng hoà ở `9 999 999` — **giá giữ chỗ chưa được khai là giữ chỗ** | **W14** |

⚠ Và oracle của chính suite này ghi `expected_value.max_price = 9999999.0`, tức
nó **kỳ vọng hệ trả về một giá trị giữ chỗ**. W15.4 sửa bộ sinh, không sửa gate.

#### 1.6.3. 24/84 câu xếp hạng trả về **HTTP 500**

✅ Phép quét sinh `84` câu dạng *"{Listing|Sản phẩm|Mặt hàng} nào có {measure}
{cao nhất|thấp nhất} tại {VN|ID}?"*:

| Kết cục | Số ca |
| --- | ---: |
| `CRASH ExecutionFailure` | **24** |
| `clarify` `A22-ALIGN-MEASURE` | 18 |
| `allow` `A-ALLOW` | 14 |
| `abstain` `A19-PLAN` | 14 |
| `abstain` `A22-ALIGN-RANK-TIE` | 14 |

✅ `ExecutionFailure` **không được bắt ở bất kỳ đâu trong `src/gladiators/`**
(`rg ExecutionFailure src/` chỉ thấy chính `planner/executor.py`). Nó thoát khỏi
`AgentRuntime.run()`, và `api.py:165` biến nó thành **HTTP 500
`AGENT_RUNTIME_ERROR`**:

```
POST /ask {"text": "Listing nào có giá thấp nhất tại Việt Nam?"}
-> 500 {"detail": {"code": "AGENT_RUNTIME_ERROR", "type": "ExecutionFailure"}}
```

Đây là **vi phạm bất biến #6** (fail-closed): một câu hỏi trả lời được không ra
`clarify`/`abstain` mà ra traceback. Nó nặng hơn mọi ca từ chối oan ở §1.2, và
không suite nào trong repo chứa cách diễn đạt làm nó bắn. Chi tiết ở §14.
---

## §2. W1 — Literal đi lọc phải là giá trị có thật trong dữ liệu

> Gỡ: lỗi trả `0` trong khi đáp án là `96`. Chặn: W5, W7 (mọi thứ mở rộng năng
> lực đều nhân bản lỗi này nếu nó còn).
> Checklist §0.3 chạm: 1 · 2 · 3 · 4 · 5 · 6 · 8.

### 2.1. Chẩn đoán, đã tái lập bằng runtime

✅ `run("Có bao nhiêu listing của brand Bibica ở VN ngày 03/07?")` cho:

```
action  = allow / A-ALLOW
filters = [dim.country=vn, dim.date=2026-07-03, dim.brand="bibica"]
evidence= result_count 0  attrs.empty_result=True
```

Dữ liệu ghi `Bibica`. ✅ Thay đúng một literal `"bibica"` → `"Bibica"` rồi chạy
lại plan đó: **96**.

Chuỗi nhân quả đầy đủ:

| # | Vị trí | Sự thật |
| -: | --- | --- |
| 1 | `agent/value_probe.py:46-49` | `_index()` fold tên rồi **chỉ giữ bản đã fold** — `set[str]`, không giữ bản gốc |
| 2 | `agent/value_probe.py:122` | `bind_values()` trả `max(hits, key=len)` — một phần tử của tập đã fold |
| 3 | `planner/semantic_parser.py:248-252` | literal đã fold đi thẳng vào `AnalyticalPredicate.value_binding` |
| 4 | `planner/compiler.py` | predicate compile thành `brand = ?` với tham số `'bibica'` ⇒ 0 dòng |
| 5 | `analytics/tools.py:483-499` | zero-row sinh `Evidence(metric="result_count", value=0, attrs.empty_result=True)` — **không ghi literal nào đã chạy** |
| 6 | `agent/alignment.py:234`, `:463`, `:475` | ba hàm alignment `return AlignmentVerdict(True, ())` **vô điều kiện** khi thấy `empty_result` |
| 7 | `domain/invariant_handlers.py:330-335` | `_ZeroRowIsAResult` chỉ kiểm `relaxed_filters`; không kiểm literal có tồn tại không |

✅ Hai phát hiện thêm, cả hai đều nằm đúng trên đường sửa:

- **`scripts/build_value_index.py:47-50` CÓ lưu tên gốc.** Bản gốc mất ở bước
  **nạp**, không ở bước dựng. Sửa là ở `value_probe`, không ở script.
- **`external/lexicon.py:117-131` đã giải đúng bài toán này** — `_original_of()`
  đọc lại JSON để đổi bản fold về bản gốc, kèm docstring nói thẳng *"Trả bản đã
  fold sẽ là trả một chuỗi không tồn tại trong dữ liệu"*. Tức trong cùng một
  repo, một nhánh làm đúng còn nhánh kia làm sai. W1 hợp nhất chúng.

### 2.2. Chẩn đoán thứ hai — tên shop không bao giờ trở thành bộ lọc

✅ `parse("Có bao nhiêu listing của shop Richy - Chi nhánh Miền Nam ở VN ngày 03/07?")`:

```
requested_dimensions = [("shop", entity.shop), ("ngay", dim.date)]
filters              = [dim.country=vn, dim.date=2026-07-03]      # KHÔNG có shop
bind_values(..., {"dim.shop_name"}) = (("dim.shop_name", "richy - chi nhanh mien nam"),)
plan                 = synth:derived.product_count:count:entity.shop:...
```

Hai lỗi chồng nhau:

1. `"shop"` được `PREFERRED_REF_BY_SURFACE` giải thành `entity.shop`, nên
   `dimension_refs` truyền vào `bind_values` **không chứa** `dim.shop_name` ⇒
   giá trị không bao giờ được bind.
2. Kết quả: câu *"đếm listing CỦA một shop"* trở thành *"đếm listing THEO TỪNG
   shop"* — một câu hỏi khác, trả lời trong im lặng.

✅ Bổ sung predicate `dim.shop_name = "Richy - Chi nhánh Miền Nam"` và bỏ
`entity.shop` khỏi dimensions rồi chạy plan: **120**. Thêm `dim.brand="Bibica"`:
**0 dòng** — giao rỗng thật.

### 2.3. W1.1 — Chỉ mục giá trị mang cả bản gốc

**`scripts/build_value_index.py`** — đổi schema output:

```json
{
  "schema_version": "value-index.v2",
  "dataset_version": "<compute_dataset_version(data/processed)>",
  "values": {
    "dim.brand": { "vn": { "bibica": "Bibica", "nestle": "Nestlé" } }
  }
}
```

- `values[ref][country]` đổi từ `list[str]` sang `dict[folded, original]`.
- Fold bằng **cùng một hàm** `value_probe._fold`; script được phép import đúng
  hàm này (xem W1.3 về lý do phá lệ "không import gladiators").
- Hai tên gốc khác nhau fold về cùng một khoá ⇒ **script fail**, không được
  chọn một cái. Ghi cả hai vào thông báo lỗi. Đây là ambiguity thật và nó phải
  lộ ra lúc dựng chỉ mục, không phải lúc trả lời một câu hỏi.

**`src/gladiators/agent/value_probe.py`** — hợp đồng mới:

| Symbol | Trước | Sau |
| --- | --- | --- |
| `INDEX_SCHEMA_VERSION` | — | `"value-index.v2"`, hằng module |
| `_index()` | `dict[ref][country] -> set[folded]` | `dict[ref][country] -> dict[folded, original]` |
| `index_is_available()` | không đổi | không đổi |
| `index_dataset_version()` | — | `str \| None`, đọc từ payload |
| `original_of(ref, country, folded)` | — | `str \| None` — công khai, thay `lexicon._original_of` |
| `missing_values(request)` | so `_fold(value) not in known` | so với `known.keys()`; **không đổi hành vi** |
| `bind_values(...)` | trả `(ref, folded)` | trả `(ref, original)`; chọn **maximal span** trên bản fold rồi ánh xạ sang bản gốc |
| `named_but_absent(...)` | `any(candidate in name for name in known)` | `known` là `keys()`; **không đổi hành vi** |

`maximal span` không đồng nghĩa với `max(hits, key=len)`. `bind_values` phải giữ
vị trí bắt đầu/kết thúc của từng khớp, bỏ khớp nằm trọn trong một khớp dài hơn,
rồi chỉ bind khi còn **đúng một** span cực đại. Hai span cực đại rời nhau (ví dụ
câu nêu hai brand để so sánh) ⇒ không chọn span dài hơn; trả ambiguity/để tầng
phân rã xử lý. Luật này vừa cho tên `Bibica Official Store` thắng phần con
`Bibica`, vừa không âm thầm thu hẹp câu hỏi nhiều thực thể thành một thực thể.

`_index()` phải **từ chối payload sai schema**: thiếu `schema_version`, hoặc
`schema_version != INDEX_SCHEMA_VERSION`, hoặc `values[ref][country]` không phải
`dict` ⇒ trả `{}` như khi thiếu file. Lý do: một chỉ mục v1 nạp bằng loader v2 sẽ
đọc `list` thành iterable của ký tự và bind ra literal một chữ cái.

**`src/gladiators/external/lexicon.py`** — xoá `_original_of` (dòng 117-131) và
gọi `value_probe.original_of`. `_candidates()` giữ nguyên: nó làm việc trên khoá
fold, và khoá fold vẫn là khoá.

### 2.4. W1.2 — Bind giá trị cho đơn vị phân tích

**`src/gladiators/domain/catalog.py`** — registry mới, đặt cạnh `_COUNTS_UNIT`:

```python
# Chiều mang TÊN của một đơn vị phân tích. Câu hỏi nêu tên shop dùng surface
# "shop", mà surface đó giải thành entity.shop (đơn vị đếm) chứ không phải
# dim.shop_name (chiều mang tên) -- nên giá trị không bao giờ được bind và câu
# "listing CỦA shop X" bị đọc thành "listing THEO TỪNG shop".
VALUE_DIMENSION_BY_UNIT: dict[str, str] = {
    "entity.shop": "dim.shop_name",
    "entity.brand": "dim.brand",
    "entity.platform_category": "dim.platform_category_name",
}
```

Kiểm ở `_build_catalog`: cả khoá lẫn giá trị phải tồn tại trong catalog và giá
trị phải có `physical`, nếu không ⇒ `CatalogError` lúc import.

**`src/gladiators/planner/semantic_parser.py::parse`** — sau khối `bind_values`
hiện có (dòng 246-253), thêm bước hai:

1. Với mỗi `SemanticBinding` trong `requested_dimensions` có `ref` nằm trong
   `VALUE_DIMENSION_BY_UNIT`, gọi `bind_values(normalized, country, {dim_ref})`.
2. Khớp **đúng một** giá trị ⇒ thêm `AnalyticalPredicate(field_ref=dim_ref,
   op="eq", value_binding=<bản gốc>)` và **loại** binding đơn vị đó khỏi
   `requested_dimensions`.
3. Khớp 0 hoặc >1 ⇒ **không làm gì** — giữ nguyên hành vi hôm nay. Câu đang gom
   nhóm chứ không lọc (§A4.4 bước 2).

Ràng buộc: bước này chỉ chạy khi `country` đã xác định, giống `bind_values`.

### 2.5. W1.3 — Một hàm `dataset_version` duy nhất

✅ Hôm nay có **hai thuật toán khác hẳn nhau và không chỗ nào kiểm lệch**:

| Nơi | Thuật toán | Giá trị 28/08 |
| --- | --- | --- |
| `data/repository.py:33-41` | SHA-256 trên **byte đã chuẩn hoá CRLF** của 3 CSV | `27de9bff184f4f89` |
| `scripts/build_value_index.py:36-38` | SHA-256 trên `",".join(sorted(product_snapshot_key))` | `a821e39d98ff4079` |

**File mới `src/gladiators/data/dataset_version.py`:**

```python
"""Một nguồn duy nhất cho dataset_version.

Trước đây repository và build_value_index mỗi bên tự băm một thứ khác nhau, nên
"chỉ mục dựng cho dataset nào" là một câu hỏi không ai trả lời được. Module này
chỉ phụ thuộc stdlib -- đó là điều kiện để script chỉ mục import được nó mà
không thừa hưởng giả định ngữ nghĩa nào của hệ bị kiểm.
"""
VERSIONED_ARTIFACTS = (
    "products_clean.csv",
    "product_snapshot_metrics.csv",
    "product_transition_metrics.csv",
)

def compute_dataset_version(root: Path) -> str: ...
```

Thân hàm là thuật toán hiện có ở `repository.py:33-41`, chuyển nguyên vẹn —
**giá trị `27de9bff184f4f89` không được đổi**, vì nó nằm trong trace, plan cache
key và evidence đã ghi.

- `ArtifactRepository.dataset_version` gọi hàm này.
- `build_value_index.build()` gọi hàm này; bỏ đoạn băm `product_snapshot_key`.
- Docstring "cố ý KHÔNG import gladiators" ở đầu script phải được viết lại cho
  đúng phạm vi: **không import tầng ngữ nghĩa**; nó *phải* dùng chung hàm băm
  phiên bản, vì hai hàm băm khác nhau là đúng thứ lỗi mục này đang sửa.

**Preflight — `assert_index_matches()`, gọi từ `AgentRuntime.__init__` sau khi
dựng repository:**

| Điều kiện | Kết quả |
| --- | --- |
| Không có `artifacts/value_index.json` | log + `value_probe` im lặng bỏ qua (**giữ nguyên hành vi**) |
| Có file, `schema_version` sai | **raise** `DatasetVersionError` |
| Có file, `dataset_version` khác repository | **raise** `DatasetVersionError` |

Lý do phân biệt: thiếu chỉ mục là thiếu *thông tin*; chỉ mục **lệch phiên bản**
là thông tin *sai*, và nó sinh ra literal thuộc về một dataset khác.

### 2.6. W1.4 — Evidence zero-row phải khai bộ lọc đã chạy

**`src/gladiators/analytics/tools.py`**, nhánh `if result.frame.empty` (dòng
483-499). `attrs` hiện có `filtered_refs` — chỉ TÊN chiều, cố ý không kèm giá
trị vì `verifier.scan_numbers` sẽ chấm chữ số trong giá trị là số bịa
(`CLAUDE.md` §3.1). Ràng buộc đó vẫn giữ; thêm ba khoá **không chứa giá trị thô**:

```python
"filter_bindings": tuple(sorted(
    # ref, và literal đã được chứng minh tồn tại trong value index hay chưa.
    # Chỉ CỜ, không phải literal: literal có thể chứa chữ số và verifier sẽ
    # chấm chúng là số không có evidence.
    (predicate.ref, bool(literal_verified(predicate)))
    for node in plan.nodes for predicate in node.predicates
)),
"executed_predicate_count": <số predicate thực sự nằm trong SQL đã chạy>,
"planned_predicate_count":  <số predicate trong plan>,
```

`literal_verified(predicate)` là `True` khi một trong ba điều đúng:

1. `predicate.ref` không nằm trong `value_probe.INDEXED_REFS` (không dò được ⇒
   không phải chỗ lỗi này sống);
2. giá trị không phải `str` (bool/số);
3. `value_probe.original_of(ref, country, _fold(value)) == value` — literal đúng
   **bằng** bản gốc trong chỉ mục.

`executed_predicate_count` phải được lấy từ `CompiledQuery`, không đếm lại trên
plan: mục đích của nó là phát hiện predicate rơi mất giữa plan và SQL.

**`src/gladiators/planner/compiler.py`** — `CompiledQuery` thêm hai field có
mặc định để không phá caller cũ:

```python
planned_predicate_count: int = 0
executed_predicate_count: int = 0
```

- `planned_predicate_count = sum(len(node.predicates) for node in plan.nodes)`;
- `executed_predicate_count` tăng **ngay tại** `_predicate_expression`, tức chỉ
  tăng khi predicate thật sự được biến thành AST. Không suy nó từ số parameter:
  `IN` có nhiều parameter còn `IS NULL` có thể không có parameter;
- `compile_plan` fail nếu hai số khác nhau. Execution invariant vẫn kiểm lại và
  ghi vào evidence để bắt cả `CompiledQuery` được dựng tay ở test/caller.

**`src/gladiators/contracts.py::Evidence`** — thêm
`model_config = ConfigDict(extra="forbid", frozen=True)`. Mọi chỗ đang enrich
evidence phải dựng `attrs` hoàn chỉnh trước constructor hoặc dùng
`model_copy(update=...)`; cấm assignment vào field sau khởi tạo. Đây là
immutability cấp model mà `Archi2808` §7 đang thiếu; không tuyên bố deep-freeze
cho object lồng trong `attrs`, nên caller cũng không được giữ rồi mutate dict đã
truyền vào.

Thêm `"relaxed_filters": False` một cách tường minh vào `attrs` của evidence
zero-row. Xem 2.8 để biết vì sao.

### 2.7. W1.5 — Invariant mới: literal đi lọc phải là giá trị của dataset

**`src/gladiators/domain/invariants.py`** — spec thứ 12:

```python
InvariantSpec(
    invariant_id="INV-FILTER-LITERAL-IS-DATASET-VALUE", version="1.0",
    severity="hard", applies_to=("execution",),
    semantic_refs=("dim.brand", "dim.shop_name", "dim.platform_category_name"),
    operators=("Filter",),
    validator_id="binding.filter_literal_exists_in_dataset",
    message_key="invariant.filter_literal_is_dataset_value",
    owner="architecture",
),
```

**`src/gladiators/domain/invariant_handlers.py`** — handler mới
`_FilterLiteralIsDatasetValue`, `stages={"execution"}`. Handler **đọc**
`spec.semantic_refs`, không giữ bản sao danh sách ref.

Luật: vi phạm khi `execution.row_count == 0` **và** tồn tại một binding
`(ref, verified=False)` với `ref ∈ spec.semantic_refs`, **hoặc**
`executed_predicate_count != planned_predicate_count`.

Không vi phạm khi mọi literal đều verified — đó là zero-row thật.

`_EmptyExecution` (`agent/workflow.py:195-205`) phải mang thêm ba trường
`filter_bindings`, `executed_predicate_count`, `planned_predicate_count`.
Dataclass này tồn tại chính vì `InvariantContext.execution: Any` — truyền dict
thì handler `getattr` luôn trả mặc định và luật im lặng không bao giờ bắn.

**Hệ quả bắt buộc theo checklist §0.3:** invariant 11 → 12, `REGISTRY_HASH` đổi,
`scripts/verify_metadata_bindings.py` phải in hash mới, `Archi2808` §6.2 và §6.4
phải được cập nhật.

### 2.8. W1.6 — Một AttributeError chết và một nhánh chưa từng chạy

✅ Hai lỗi đo được, cả hai nằm đúng trong khối W1 phải sửa:

1. **`agent/workflow.py:1527`** viết `[item.rule_id for item in violations]`.
   `InvariantViolation` là dataclass có `('invariant_id', 'stage', 'severity',
   'message_key', 'node_id', 'details')` — **không có `rule_id`**. Dòng này ném
   `AttributeError` ngay lần đầu có violation. Sửa thành `item.invariant_id`.
2. **`A-EMPTY-RESULT-RELAXED` chưa bao giờ chạy được.** `rg relaxed_filters src
   tests` chỉ ra bốn vị trí: khai báo dataclass, đọc từ `attrs`, và handler. ✅
   **Không producer nào từng ghi `relaxed_filters` vào `attrs`**, nên
   `_ZeroRowIsAResult` luôn trả `()`, nên nhánh ở dòng 1529-1536 là code chết —
   và nếu chạy sẽ nổ ở lỗi (1).

Đây đúng lớp lỗi `CLAUDE.md` §5.1.3 mô tả. Vì vậy W1 bắt buộc kèm telemetry:

```python
planning_meta["empty_result"] = {
    "row_count": 0,
    "violations": [item.invariant_id for item in violations],
    # Khoá đếm: một nhánh không bao giờ bắn trông giống hệt một nhánh bắn mà vô
    # ích, và chỉ telemetry phân biệt được hai thứ đó.
    "handler_fired": {"zero_row_relaxed": ..., "filter_literal": ...},
}
```

### 2.9. W1.7 — Alignment không còn cửa sau vô điều kiện

Ba vị trí `agent/alignment.py:234`, `:463`, `:475` hiện là:

```python
if any(item.metric == "result_count" and item.attrs.get("empty_result") for item in evidence):
    return AlignmentVerdict(True, ())
```

Thay bằng **một** helper dùng chung — ba bản sao của một luật là ba chỗ để luật
lệch nhau:

```python
def _empty_result_is_self_evident(evidence: list[Evidence]) -> bool:
    """Zero-row được miễn đối chiếu measure CHỈ KHI nó tự chứng minh được.

    "Không dòng nào khớp" là một kết quả hợp lệ và nó không mang measure, nên
    check_evidence_alignment sẽ báo measure_dropped cho một câu trả lời đúng.
    Nhưng miễn VÔ ĐIỀU KIỆN thì một số 0 do lọc hỏng cũng được miễn -- và hai
    số 0 đó trông giống hệt nhau.
    """
```

Trả `True` chỉ khi: có evidence `result_count`/`empty_result`, **và**
`executed_predicate_count == planned_predicate_count`, **và** mọi phần tử của
`filter_bindings` có `verified=True`. Ngược lại trả `False` — alignment chạy đủ
như với mọi câu trả lời khác.

### 2.10. W1.8 — Rule mới `A-EMPTY-RESULT-UNVERIFIED`

**`agent/workflow.py`**, khối `elif ... empty_result` (dòng 1498-1541): sau khi
`enforce_invariants("execution", ...)`, phân ba nhánh thay vì hai:

| Violation | action | rule_id | reason |
| --- | --- | --- | --- |
| `INV-EMPTY-RESULT-IS-VALID` | `abstain` | `A-EMPTY-RESULT-RELAXED` (đã có) | như hiện tại |
| `INV-FILTER-LITERAL-IS-DATASET-VALUE` | `abstain` | **`A-EMPTY-RESULT-UNVERIFIED`** | "Không chứng minh được bộ lọc đã chạy đúng giá trị được nêu, nên số 0 này không phải một kết quả." |
| không có | `allow` | `A-ALLOW` | như hiện tại |

`fixable=False`: không thông tin nào người dùng thêm vào sửa được một literal
lệch. Câu từ chối **không được chèn chữ số** (`CLAUDE.md` §3.1).

Thêm dòng vào bảng `Archi2808` §12.

### 2.11. Bộ test bắt buộc — `tests/test_value_binding.py` (mới)

Mọi ca dưới đây chạy **qua runtime**, không gọi hàm cô lập (checklist §0.3 mục 3):

| Ca | Kỳ vọng | Vì sao ca này |
| --- | ---: | --- |
| brand `Bibica`, VN, 03/07 | `allow` · **96** | positive control chiều brand |
| shop `Richy - Chi nhánh Miền Nam`, VN, 03/07 | `allow` · **120** | positive control chiều shop (**cần W7**) |
| `Bibica` **tại** shop `Richy - Chi nhánh Miền Nam` | `allow` · **0** | zero-row thật (**cần W7**) |
| brand `Bibika` (sai chính tả) | `abstain` · `A-VALUE-NOT-FOUND` | phải từ chối, **không** nới thành "tất cả brand" |
| chỉ mục v1 nạp bằng loader v2 | `_index()` trả `{}` | schema sai không được đọc nhầm |
| `dataset_version` chỉ mục lệch repository | `DatasetVersionError` lúc dựng runtime | không im lặng bỏ qua |
| literal chưa verified + zero-row | `abstain` · `A-EMPTY-RESULT-UNVERIFIED` | cửa sau đã đóng |
| `original_of` cho mọi khoá của chỉ mục | round-trip `_fold(original) == folded` | chỉ mục tự nhất quán |

> **Thứ tự nghiệm thu không được đảo:** ca giao rỗng chỉ được dùng để nghiệm thu
> *"không có kết quả cũng là một kết quả"* **sau khi** hai positive control trả
> đúng 96 và 120. Nghiệm thu bằng một số 0 mà chưa chứng minh được hệ biết trả
> ra số khác 0 là nghiệm thu chính cái lỗi này.

### 2.12. Ba việc W1 **không** làm

- **Không** thêm bảng alias tay cho từng thương hiệu. `domain/alias_overlay.json`
  hiện **rỗng**; chi phí bảo trì tay đang là 0 và W1 giữ nguyên con số đó. Chỉ
  mục tự dựng từ dữ liệu; thêm brand mới vào dữ liệu là lần dựng lại tự có mặt.
- **Không** thay khớp chính xác bằng BM25 hay embedding. Khớp chính xác theo
  token đã chuẩn hoá là thứ mua về `over_answer_rate = 0`.
- **Không** đưa gợi ý trigram vào đường thực thi. Nếu sau này thêm, hợp đồng là:
  *truy hồi chỉ được quyền **đề xuất**; chỉ khớp chính xác mới được quyền **thực
  thi***. Điểm nối duy nhất được phép là `agent/suggestions.py`, nơi mọi
  candidate đã phải chạy qua chính runtime trước khi được trả về.

---

## §3. W2 — Cassette tái lập được từ checkout

> Checklist §0.3 chạm: 3 · 7 · 8.

### 3.1. Sự thật

✅ `artifacts/search_cassettes/` chỉ có `REVIEW.md`; **0 file JSON**.
✅ `scripts/record_search_cassettes.py:88-93`:

```python
store = CassetteStore(CASSETTE_DIR)
if not store.keys():
    print("SKIP: chưa có cassette nào; chạy record trước.")
    return 0          # <- CI xanh trên một kho RỖNG
```

Nghĩa là mệnh đề *"chỉ còn thiếu chữ ký người duyệt"* không đúng: chưa có **nội
dung** để ai đó đọc mà ký. Ba khẳng định trong bản bàn giao — replay ổn định
6/6, replay chạy khi chặn socket, injection guard 6/6 sạch — hiện **không tái
lập được từ repository**.

`REVIEW.md` **đã** có đủ manifest để kiểm: 6 file, thị trường, mục đích, số kết
quả, thời điểm ghi, `sha256` 16 ký tự đầu, và `max_results=3` (nằm trong khoá
cassette).

### 3.2. Manifest thành dữ liệu máy đọc được

File mới **`artifacts/search_cassettes/MANIFEST.json`** — được **force-track**
(`git add -f`, vì `artifacts/` nằm trong `.gitignore`):

```json
{
  "schema_version": "search-cassette-manifest.v1",
  "provider": "tavily",
  "max_results": 3,
  "cassettes": [
    {"key": "0d6bc87c27b16fda2e9e", "market": "vn", "purpose": "market_event",
     "query": "Vietnam e-commerce market event July 2026",
     "results": 3, "recorded_at": "2026-08-01T22:59:55",
     "sha256_16": "7bd07be2888aa627",
     "reviewed_by": null, "reviewed_at": null}
  ]
}
```

Sáu entry, số liệu chép nguyên từ `REVIEW.md` §1. `reviewed_by`/`reviewed_at`
khởi tạo `null`. **Agent không được điền hai ô này** — A12-R6 tồn tại để chặn
đúng việc đó, và một chữ ký do máy gõ biến "đã có người xem" thành một chuỗi ký
tự.

`REVIEW.md` §1 giữ nguyên vai trò văn bản cho người đọc; MANIFEST là bản máy
kiểm. Hai bản lệch nhau ⇒ `--verify` đỏ (xem 3.3, mục 5).

### 3.3. `--verify` phải đỏ khi thiếu

`scripts/record_search_cassettes.py::verify()` viết lại theo đúng thứ tự này,
dừng ở lỗi đầu tiên và trả mã khác 0:

| # | Kiểm | Mã lỗi in ra |
| -: | --- | --- |
| 1 | `MANIFEST.json` tồn tại và đúng `schema_version` | `FAIL MANIFEST_MISSING` |
| 2 | Tập `cassette_key(q, max_results=MAX_RESULTS)` của 6 `QUERIES` **bằng** tập `key` trong manifest | `FAIL QUERY_SET_MISMATCH` |
| 3 | Mọi `key` trong manifest có file `<key>.json` trên đĩa | `FAIL CASSETTE_MISSING` |
| 4 | Mỗi file parse được và có `schema_version == CASSETTE_SCHEMA_VERSION` | `FAIL CASSETTE_SCHEMA` |
| 5 | `sha256(file bytes)[:16]` khớp `sha256_16` của manifest | `FAIL CASSETTE_HASH` |
| 6 | `verify_determinism(ReplaySearchProvider(store), QUERIES, runs=3, max_results=3)` cho `stable=True` | `FAIL REPLAY_UNSTABLE` |
| 7 | `injection_guard.sanitize_and_check` sạch trên **title + snippet** của từng item | `FAIL GUARD_HIT` |

Nhánh `if not store.keys(): return 0` **bị xoá**. Kho rỗng đi vào mục 3 và trả 1.

Mục 7 chỉ quét phần chữ **thật sự đi vào prompt**. ✅ Ghi lại để lần sau không
mất công: quét cả JSON làm cả 6 cassette dính `A17_PII_PHONE` — mọi khớp đều là
hiện vật metadata (điểm liên quan dạng `0.86331123`, mảnh `content_hash`, khoá
URL). Metadata không bao giờ chạm prompt.

### 3.4. Giao artifact

Chọn **force-track JSON đã redact**: sáu file `<key>.json` được `git add -f` vào
`artifacts/search_cassettes/`. Lý do chọn phương án này thay vì bundle tải trong
CI: mục tiêu là *tái lập từ checkout*, và một bundle tải về vẫn để lại đúng khoảng
trống hiện tại khi mạng hoặc kho artifact không có.

Trước khi track: chạy `injection_guard` và một pass redact bỏ mọi khoá không cần
cho replay (`raw_html`, `favicon`, `score` nếu không nằm trong `content_hash`).
Redact xong ⇒ `sha256` đổi ⇒ **cập nhật lại manifest và `REVIEW.md`**, đúng như
`REVIEW.md` §4 đã ghi.

### 3.5. Test

`tests/test_search_record_replay.py` bổ sung, không sửa test cũ:

- kho rỗng ⇒ `verify()` trả **khác 0** (dựng `CASSETTE_DIR` tạm);
- thiếu 1 trong 6 ⇒ khác 0, thông báo nêu đúng `key` thiếu;
- file bị sửa 1 byte ⇒ khác 0 với `CASSETTE_HASH`;
- manifest thừa một key không có trong `QUERIES` ⇒ `QUERY_SET_MISMATCH`.

### 3.6. Không đổi

`GLADIATORS_ENABLE_LIVE_SEARCH` giữ **OFF** trong source (A12-R4). Trạng thái E6
trong `PHASE6_ACCEPTANCE_SIGNOFF.md` **không đổi**. `ReplaySearchProvider` vẫn
`raise ReplayMiss` khi thiếu cassette (A12-R5).

---

## §4. W3 — CI dựng lại được từ số 0

> Checklist §0.3 chạm: 7 · 8.

### 4.1. Sự thật

✅ `pyproject.toml:9` ghi `dependencies = []`, trong khi `requirements.txt` và
`requirements-dev.txt` đã liệt kê đầy đủ và có ghi chú vì sao từng gói tồn tại.
Hai nguồn, một cái được cài, một cái được khai.

✅ `artifacts/` nằm trong `.gitignore`, và `value_index.json` là artifact **bắt
buộc** cho vòng dò giá trị: thiếu nó thì `value_probe._index()` trả `{}` và một
lớp kiểm biến mất **trong im lặng** — eval vẫn xanh.

### 4.2. Khai phụ thuộc

`pyproject.toml`:

```toml
[project]
dependencies = [ ... nội dung requirements.txt, giữ nguyên ràng buộc phiên bản ... ]

[project.optional-dependencies]
dev = [ ... phần requirements-dev.txt không có trong requirements.txt ... ]
```

`requirements.txt` / `requirements-dev.txt` **giữ lại** nhưng đổi thành trỏ về
`pyproject` (`-e .` và `-e .[dev]`), để không sinh nguồn thứ hai.

Test mới `tests/test_packaging.py`: mọi top-level import trong `src/gladiators/`
và `scripts/` phải resolve về một distribution có tên trong
`project.dependencies ∪ optional-dependencies.dev` hoặc là stdlib. Đây là phép
kiểm đã bắt được `python-pptx` và `httpx` thiếu ở lần trước — giữ nó chạy tự động
thay vì chạy tay.

### 4.3. Bước dựng artifact trong CI

`.github/workflows/*` thêm bước **trước** `pytest`, đúng thứ tự này:

```bash
python scripts/build_value_index.py
python scripts/build_question_bank.py
python scripts/build_multiturn_suite.py
```

Ba lệnh này chạy offline, không cần provider.

### 4.4. Nghiệm thu

Clone sạch → `pip install -e .[dev]` → ba lệnh dựng → `pytest -q` cho
**1207 passed** mà không cài tay gói nào. Trước W3, ✅ baseline `1207 passed,
1 skipped` chỉ đạt được trên một `.venv` đã cài tay và sau khi dựng
`value_index.json`.

---

## §5. W4 — Khung đếm: một ngữ pháp, không phải tám bản vá

> Gỡ: ans028, ans030 (2 ca từ chối oan) và **cả 8 lỗi MR-1** của kiểm biến hình.
> Phụ thuộc: không.
> Checklist §0.3 chạm: 1 · 3 · 4 · 8.

### 5.1. Hai lỗ hổng độc lập trong cùng một khái niệm

✅ **Lỗ 1 — khung diễn đạt.** Các metric đếm chỉ với tới được bằng **surface
dính liền**: `_DERIVED_ALIASES["shop_count"]` chứa `"bao nhiêu shop"`. Đổi khung
sang `"Số lượng shop … là bao nhiêu?"` thì cụm đó không còn xuất hiện liền nhau:

```
parse("Số lượng shop ở Việt Nam là bao nhiêu?")
  -> requested_measures = []          # không có gì để đo
  -> A19-CAT clarify
```

Toàn bộ 8 lỗi MR-1 của báo cáo `2026-08-27-metamorphic.json` là một họ duy nhất
này, 4 cặp × 2 thị trường:

| Cặp | Khung gốc `allow` | Khung biến thể |
| --- | --- | --- |
| ans005 · ans007 | Có bao nhiêu shop ở …? | Số lượng shop ở … là bao nhiêu? |
| ans009 · ans010 | Có bao nhiêu listing **đã xác minh** …? | Số lượng listing **đã xác minh** … là bao nhiêu? |
| ans027 · ans029 | Có bao nhiêu thương hiệu …? | Số lượng thương hiệu … là bao nhiêu? |
| ans031 · ans033 | Có bao nhiêu shop **chính hãng** …? | Số lượng shop **chính hãng** … là bao nhiêu? |

✅ **Lỗ 2 — từ vựng.** `_DERIVED_ALIASES["brand_count"]` có
`("số thương hiệu", "bao nhiêu thương hiệu", "brand count", "jumlah merek")` —
không có `"bao nhiêu brand"`. Nên:

```
parse("Việt Nam ngày 03/07 có bao nhiêu brand khác nhau?")
  -> requested_measures = []
  -> requested_dimensions = [("brand", dim.brand), ("ngay", dim.date)]
  -> A19-CAT clarify
```

Vá bằng cách thêm alias sẽ đóng đúng hai ca và để nguyên lớp lỗi. W4 đóng lớp.

### 5.2. W4.1 — Chuẩn hoá khung đếm

**`src/gladiators/planner/semantic_parser.py`**, áp **sau** `normalize()` và
**trước** `_link()`:

```python
# Khung "Số lượng X là bao nhiêu?" và "Có bao nhiêu X?" hỏi cùng một thứ. Bộ
# alias khớp trên cụm dính liền ("bao nhieu shop"), nên khung thứ hai làm cụm
# đó tách ra và câu mất measure. Viết lại NGUYÊN KHUNG và chép `rest` nguyên
# văn: định ngữ ("da xac minh", "chinh hang") nằm trong `rest` nên nó không thể
# rơi mất -- đó là điều kiện để phép viết lại này không đổi câu hỏi.
_COUNT_FRAME_VI = re.compile(
    r"^(?P<lead>.*?)\bso luong\s+(?P<rest>.+?)\s+la bao nhieu\b.*$"
)
_COUNT_FRAME_ID = re.compile(
    r"^(?P<lead>.*?)\bjumlah\s+(?P<rest>.+?)\s+(?:adalah\s+)?berapa\b.*$"
)
```

Kết quả: `f"{lead} co bao nhieu {rest}".strip()`, đã chuẩn hoá khoảng trắng.

**Nghĩa vụ chứng minh, và nó là điều kiện nghiệm thu:** với mọi cặp
(khung gốc, khung biến thể), `parse()` phải cho **cùng** `requested_measures`,
`requested_dimensions` và `filters`. ✅ Đã kiểm trên cả 4 cặp: khớp 4/4.

Ghi phép viết lại vào `AnalyticalRequest.assumptions` dưới dạng
`"count_frame_normalised"` — checklist §0.3 mục 4: một nhánh không đếm được số
lần nó bắn thì "đã đo" và "đã chạy" không phân biệt được.

### 5.3. W4.2 — Đếm theo cấu trúc, không theo cụm dính liền

**`src/gladiators/domain/catalog.py`** — registry mới, dựng cạnh `_COUNTS_UNIT`
đã có nên không sinh nguồn sự thật thứ hai:

```python
# Chiều nào, khi đứng ngay sau một từ để hỏi số lượng, là "đếm đơn vị nào".
# Đếm shop_name phân biệt KHÔNG bằng đếm shop: metric đích mang counts_unit
# riêng (entity.shop -> counting_key shop_id) và phép đếm vẫn chạy trên khoá đó.
COUNT_METRIC_BY_SURFACE_REF: dict[str, str] = {
    "dim.brand":                  "derived.brand_count",
    "entity.brand":               "derived.brand_count",
    "dim.shop_name":              "derived.shop_count",
    "entity.shop":                "derived.shop_count",
    "dim.platform_category_name": "derived.category_count",
    "entity.platform_category":   "derived.category_count",
    "dim.product_name":           "derived.product_count",
    "entity.product_listing":     "derived.product_count",
}
```

Kiểm ở `_build_catalog`: mọi khoá và giá trị phải có trong catalog, và mỗi giá
trị phải có `counts_unit` khác `None` ⇒ `CatalogError` lúc import.

**`DeterministicSemanticParser.parse`** — luật chạy sau `_link()` và **trước**
khối `counted_unit`/lọc bỏ `analysis_unit` hiện tại. Nếu chạy sau, chính khối đó
đã loại `entity.product_listing`/`entity.brand` không có physical binding và
không còn dữ liệu để suy metric đếm:

> Nếu `requested_measures` **rỗng**, và trong `requested_dimensions` có **đúng
> một** binding mà `ref ∈ COUNT_METRIC_BY_SURFACE_REF` và surface của nó đứng
> **ngay sau** một từ hỏi số lượng (`"bao nhieu"`, `"berapa"`, `"how many"`),
> thì đặt binding đó thành `requested_measures` với ref là metric đếm tương ứng,
> và **bỏ** nó khỏi `requested_dimensions`.

Kiểm vị trí bằng boundary regex trên `normalized_question`; không dùng
`surface in text` vì nó coi `brand` trong một token dài hơn là liền kề. Nếu có
hai ứng viên cùng thoả, ghi ambiguity và không chọn theo thứ tự registry.

Bốn điều kiện đều bắt buộc, mỗi cái chặn một cách hỏng:

| Điều kiện | Nếu bỏ |
| --- | --- |
| `requested_measures` rỗng | Câu "giá trung vị theo brand" biến brand thành measure |
| **đúng một** ứng viên | Câu nêu hai chiều thì việc chọn một là chọn hộ người hỏi |
| **liền kề** từ hỏi số lượng | "Rating theo brand tại VN có bao nhiêu listing" đếm nhầm brand |
| ref nằm trong registry | Không suy diễn ngoài tập đã duyệt |

✅ Kết quả đo: `ans028` → **30**, `ans030` → **12** — khớp oracle.

### 5.4. W4.3 — Ba alias trần còn thiếu

Lỗ 2 ở §5.1 không chỉ có `brand`. ✅ `find_in` trả `[]` cho cả ba cụm dưới đây,
trong khi ref đích **đã tồn tại và đã có alias dài hơn**:

| Cụm không bind | Ref đích | Alias đang có | Ca lộ ra |
| --- | --- | --- | --- |
| `luot thich` | `measure.liked_count` | `"số lượt thích"`, `"lượt yêu thích"`, `"likes"`, `"jumlah suka"` | `bgk12` |
| `luot danh gia` | `measure.rating_count` | `"số lượt đánh giá"`, `"số đánh giá"`, `"review count"` | ⚠ chưa có ca đo |
| `ty le` | — | không ref nào | `bgk11` → thuộc **W11**, không phải alias |

Hai dòng đầu là **thiếu alias trần**: người dùng nói *"nhiều lượt thích nhất"*,
không nói *"số lượt thích nhiều nhất"*. Thêm `"lượt thích"` và `"lượt đánh giá"`
vào `_DERIVED_ALIASES` / `_MEASURE_ALIASES`.

**Ràng buộc bắt buộc kèm theo:** `"lượt thích"` là chuỗi con của
`"thay đổi lượt thích"` (alias của `derived.liked_delta`). `AliasIndex.find_in`
khớp **dài trước** và xoá span đã nhận khỏi residual, nên thứ tự đúng được bảo
toàn — nhưng đây chính là loại thay đổi `compound_shadowed` tồn tại để chặn, nên
test phải khoá cả hai chiều:

- `"thay doi luot thich tai vn"` → `derived.liked_delta`, **không** phải
  `measure.liked_count`;
- `"listing nao co nhieu luot thich nhat"` → `measure.liked_count`.

✅ Đáp án `bgk12`: giá trị đỉnh **10 449**, và **đúng 1 listing** đạt đỉnh — nên
ca này không chạm nhánh `A22-ALIGN-RANK-TIE`.

⚠ Dòng `luot danh gia` chưa có ca đo nào lộ ra; nó được thêm vì cùng một lớp lỗi,
và `W9.4` phải sinh câu cho nó để khẳng định này thôi là giả định.

### 5.5. Nghiệm thu W4

| Phép đo | Trước | Sau |
| --- | ---: | ---: |
| ans028 / ans030 | `A19-CAT` clarify | `allow` · 30 / 12 |
| MR-1 `fail` | ◻ **8** | **0** |
| MR-1 `rate` | ◻ 0.6923 | ≥ 0.95 |
| `risk` · `over_answer_rate` | 0.0 · 0.0 | **0.0 · 0.0** |
| `synthesizer_equivalence_baseline.json` | — | **không entry nào đổi** |

Điều kiện cuối là bắt buộc: W4 chỉ chạm parser ở nhánh mà hôm nay không sinh ra
measure nào, nên không plan nào đang tồn tại được phép đổi.
`test_existing_plans_are_unchanged` là phép kiểm đó.

Test mới `tests/test_counting_frame.py`:

- 4 cặp khung: `parse` cho cùng ba trường ngữ nghĩa;
- `"co bao nhieu brand khac nhau"` → `derived.brand_count`, `dim.brand` rời khỏi
  dimensions;
- **negative:** `"gia trung vi theo brand tai vn"` → measure vẫn là
  `measure.price`, `dim.brand` **vẫn là dimension**;
- **negative:** `"rating theo brand tai vn co bao nhieu listing"` → đếm listing,
  không đếm brand;
- **negative:** câu nêu hai chiều cùng liền kề ⇒ **không** áp luật.

---

## §6. W5 — Khối tổng hợp vô hướng (scalar aggregate)

> Gỡ: ans035, ans036, ans037, ans038. Phụ thuộc: **W1** (xem 6.5), phần
> decline typed của **W12** để `aggregation_not_certified` đi ra đúng rule,
> **W14 giai đoạn A** (xem 6.7) và **W13** cho W5.3.
> Checklist §0.3 chạm: 1 · 3 · 4 · 5 · 7 · 8.

### 6.1. Hai lỗi tách biệt, phải sửa theo đúng thứ tự

✅ **Lỗi A — bộ sinh kế hoạch không bao giờ được thử.**
`planner/open_planner.py:70-111::_synthesis_beats_template` trả `False` cho
`"Giá trung vị tại Việt Nam ngày 03/07 là bao nhiêu?"`: không ranking asc, không
predicate ngoài country/date, ngày = `LATEST_SNAPSHOT`, measure không
`counts_unit`, không dimension ngoài scope. Rồi
`infer_deterministic_template` trả `None` (không có template trung vị), rồi
không có provider ⇒ `OpenPlannerError` ⇒ `A19-PLAN`.

✅ **Lỗi B — ngay cả khi được thử, plan không có node `Aggregate`.**
`planner/synthesizer.py:421` phát `Aggregate` chỉ khi `dimensions or
counted_unit`. Với `measure.price`, không dimension, không counted unit:

```
plan_id = synth:measure.price:median:nogroup:none:vn:2026-07-03:norel:1.1
nodes   = Scan -> Filter -> Project
SQL     = SELECT price_num AS "price" FROM (... WHERE country_code=? AND date=? AND price_num < ?) ...
```

`plan_id` khai `:median:` còn SQL trả **668 dòng giá thô**. `_choose_aggregation`
tính giá trị rồi không ai dùng — plan_id đang nói dối.

✅ **Kiểm chứng phương án:** thay node `Project` bằng
`Aggregate(refs=("measure.price",), group_by=(), aggregation="median")` rồi
chạy: `validate_plan` **valid**, SQL thành

```sql
SELECT MEDIAN(price_num) AS "price"
FROM (SELECT * FROM (SELECT * FROM products) AS q_n2
      WHERE (country_code = ? AND date = ?) AND price_num < ?) AS q_n4
```

kết quả **132000.0** — khớp oracle `ans035`. Predicate loại sentinel đã có sẵn ở
`synthesizer.py:361-365` cho `measure.price`, nên `INV-PRICE-SENTINEL-EXCLUDED`
không cần đổi.

### 6.2. W5.1 — Aggregation phải là thứ câu hỏi yêu cầu

Làm **trước** 6.3, để không bao giờ phát ra một `Aggregate` mang phép tính đã bị
thay thầm.

`AnalyticalRequest` thêm field, dùng **chính** kiểu `Aggregation` của IR thay vì
chép một `Literal` thứ hai:

```python
requested_aggregation: Aggregation | None = None
```

Additive, mặc định `None` ⇒ fixture cũ không hỏng (bất biến #7).

Parser đặt field này từ cụm **tường minh** trong câu:

| Cụm | Giá trị |
| --- | --- |
| `trung vi`, `median` | `median` |
| `trung binh`, `binh quan`, `rata-rata`, `average`, `mean` | `mean` |
| `tong`, `tong cong`, `cong lai`, `total`, `sum` | `sum` |
| `cao nhat`, `lon nhat`, `toi da`, `maximum`, `max` và không hỏi một entity xếp hạng | `max` |
| `thap nhat`, `nho nhat`, `toi thieu`, `minimum`, `min` và không hỏi một entity xếp hạng | `min` |
| không có cụm nào | `None` |

Hai cue aggregation khác nhau cùng xuất hiện ⇒ ghi ambiguity và không chọn theo
thứ tự bảng. `cao nhất/thấp nhất` chỉ là scalar aggregate khi câu không hỏi
`listing/shop/brand nào`; nếu có chủ thể xếp hạng thì giữ `ranking` hiện tại.

`synthesizer._choose_aggregation` viết lại:

```python
requested = request.requested_aggregation
if requested is not None:
    # Yêu cầu một phép tính catalog chưa chứng nhận là một lời TỪ CHỐI, không
    # bao giờ là một phép thay thế. Trả lời câu hỏi trung bình bằng trung vị
    # đúng là lớp sai mà cả tầng này tồn tại để chặn.
    return requested if requested in allowed else None
# Không nêu phép tính: giữ nguyên đường mặc định hôm nay, để plan_id của 58 plan
# đang bị khoá không đổi.
```

Phần còn lại của hàm (`counts_unit` → `count`, ngược lại `median` hoặc
`allowed[0]`) **giữ nguyên từng dòng**.

Nhánh `"mean_requested" in request.assumptions or "mean" in
request.analytical_operators` bị thay bởi `requested_aggregation`; giữ lại việc
ghi `"mean_requested"` vào `assumptions` để trace cũ đọc được.

**Khoá aggregation xuyên suốt bốn lớp, không chỉ ở synthesizer:**

- `agent/context.py::RequestDigest` thêm `requested_aggregation: Aggregation | None`
  và `request_digest()` lấy từ payload analytical;
- `planner/atoms.py::atoms_from_request` phát atom không-shareable
  `kind="aggregation"`, `value=requested_aggregation`; atom ranking hiện tại vẫn
  là atom riêng `rank:<direction>`;
- `agent/alignment.py::check_plan_alignment` phát
  `aggregation_mismatch` khi request nêu aggregation nhưng output không có
  `Aggregate` tương ứng, hoặc node dùng aggregation khác;
- `analytics/tools.py` ghi `attrs["aggregation"]` từ node `Aggregate` đã compile;
  `check_evidence_alignment` đối chiếu lại với digest. Không ghi/đọc từ
  `plan_id`: plan id là telemetry, không phải contract thực thi.

Nếu aggregation tường minh không nằm trong `valid_aggregations`, `synthesize`
ghi decline `aggregation_not_certified`. `OpenPlannerError` thêm field
`rule_id` mặc định `A19-PLAN`; riêng decline này đặt `A19-AGGREGATION`, và
workflow bảo toàn field khi đổi sang `AnalyticalPlanError`. Nếu chỉ trả `None`
như hiện tại, ca này sẽ vẫn ra thông báo sai *"thiếu provider"* dù W5 đã được
cài.

**Delta lên fixture bị khoá** — hai entry, cả hai có lý do contract:

| Entry | Trước | Sau | Vì sao |
| --- | --- | --- | --- |
| `dr2607:tc29` | `synth:measure.discount_percent:median:…` | **`None`** | Câu hỏi *"**Trung bình** mỗi sản phẩm … được giảm giá bao nhiêu"*; `measure.discount_percent.valid_aggregations = ('median','min','max')` — **không có `mean`**. Hôm nay hệ thay thầm mean→median |
| `dr2607:tc36` | `synth:derived.estimated_recent_revenue:median:…` | `…:sum:…` | Câu hỏi *"**Tổng** doanh thu … cộng lại"*; `sum` nằm trong `valid_aggregations` |

Cả hai là câu **cross-market**, bị `A16-CROSS-CURRENCY` chặn trước khi thực thi
⇒ **hành vi runtime không đổi**, chỉ plan đổi. `tc29` rơi khỏi
`test_no_plan_is_lost` nên cần allowlist tường minh:

```python
# Plan biến mất CÓ CHỦ ĐÍCH: câu hỏi yêu cầu mean, catalog không chứng nhận mean
# cho discount_percent, và phép thay thầm sang median là đúng lớp sai
# _choose_aggregation tồn tại để chặn. Từ chối đúng hơn một con số sai.
INTENTIONALLY_LOST = {"dr2607:tc29": "mean không được chứng nhận cho measure.discount_percent"}
```

### 6.3. W5.2 — Phát node `Aggregate` cho câu hỏi vô hướng

`planner/synthesizer.py` thêm:

```python
def _wants_scalar_aggregate(request: AnalyticalRequest) -> bool:
    """Câu hỏi một CON SỐ TỔNG HỢP trên toàn tập, không phải các DÒNG.

    Chỉ True khi câu nêu TƯỜNG MINH một phép tổng hợp. Suy từ việc
    _choose_aggregation có trả về gì đó thì mọi câu xếp hạng cũng dính: hàm đó
    trả "median" như một giá trị mặc định cho mọi measure, kể cả plan chỉ Rank
    các dòng -- 6 trong 58 plan đang bị khoá có hình Scan->Filter->Rank và một
    node Aggregate ở đó sẽ gộp cả thị trường thành một dòng rồi xếp hạng nó.
    """
    return request.requested_aggregation is not None and request.ranking is None
```

Điều kiện phát node đổi từ `if dimensions or counted_unit:` thành
`if dimensions or counted_unit or _wants_scalar_aggregate(request):`.
`output_grain` = `"country_snapshot"`, `expected_cardinality` = `"1"` — giống
hệt nhánh `not dimensions` đang có.

**Delta lên fixture bị khoá:** ✅ đã đo — trong 58 plan, **35 plan không có node
`Aggregate`**. Chỉ những plan mà câu hỏi nêu tường minh một phép tổng hợp mới
đổi, tức đúng `tc29` và `tc36` ở 6.2. 33 plan còn lại (`questions:q02`…`q60`,
`semantic_linking:sl03`…, `questions_v2:v2q01`…) không nêu phép tổng hợp nào nên
`_wants_scalar_aggregate` trả `False` và plan giữ nguyên từng byte.

### 6.4. W5.3 — Mở cổng cho bộ sinh kế hoạch

`planner/open_planner.py::_synthesis_beats_template` thêm mệnh đề, đặt **trước**
mệnh đề `dates[0] != LATEST_SNAPSHOT`:

```python
# Không template nào tính một con số tổng hợp trên toàn thị trường: lựa chọn
# hôm nay không phải "một số sai" mà là A19-PLAN cho một câu dữ liệu trả lời
# được. Điều kiện "nêu tường minh" giữ nguyên tính một chiều của guard.
if _wants_scalar_aggregate(request):
    return True
```

Import `_wants_scalar_aggregate` từ `synthesizer` — `open_planner` đã import
`synthesize` từ đó nên không thêm cạnh phụ thuộc mới.

### 6.5. Vì sao W5 phụ thuộc W1

Comment ở `open_planner.py:196-201` ghi rõ: nới điều kiện gọi synthesizer từng
làm câu *"Rating theo brand không tồn tại tại VN"* được trả lời bằng cả 19
brand, vì parser không bind được brand không tồn tại và synthesizer mở rộng câu
hỏi trong im lặng — *"Widening the trigger needs the entity-binding guard
first."*

W1 **chính là** guard đó: sau W1, một giá trị được nêu mà không tồn tại đi ra
`A-VALUE-NOT-FOUND`, và một literal chưa chứng minh được đi ra
`A-EMPTY-RESULT-UNVERIFIED`. Nới cổng trước W1 là lặp lại đúng sự cố đã ghi.

### 6.7. Vì sao W5 phụ thuộc W14 — và vì sao chỗ này là chỗ dễ sai nhất

W5.1 khai `cao nhat / lon nhat / toi da / max` ⇒ `requested_aggregation="max"`,
W5.2 phát node `Aggregate`, và `measure.price.valid_aggregations` **đã có
`max`**. Nên `bgk19` *"Giá cao nhất tại Indonesia ngày 03/07 là bao nhiêu?"* —
hôm nay là một trong bảy ca **từ chối đúng** của §1.5 — sẽ đi trọn đường allow.

✅ Và nó trả **9 999 999**: một giá trị giữ chỗ trên một listing quà tặng. Bộ lọc
sentinel hiện hành là `price < 999999999`, còn hai dòng `9 999 999` chưa được
khai là giữ chỗ (§15.1). Đáp án đúng là **1 135 000**.

Tấm lưới đang che ca này là tie detector, và ✅ nó **chỉ có trên đường `Rank`**
(`executor.py:125` chỉ chấm hoà khi `rank_limit is not None`). Một node
`Aggregate` với `max` trả đúng một dòng và không đi qua nhánh đó. Nghĩa là W5
không có lớp nào phía sau đỡ.

⇒ **W14 giai đoạn A phải merge trước W5.2.** Đây là một ca `wrong_value_silent`
mới do chính W5 tạo ra, tức phá `over_answer_rate = 0.0` ở §0.2 — mà đó là một
ràng buộc bị từ chối, không phải một đánh đổi.

### 6.6. Nghiệm thu W5

| Ca | Kỳ vọng |
| --- | ---: |
| ans035 · Giá trung vị VN 03/07 | `allow` · **132 000** |
| ans036 · Rating trung vị VN 03/07 | `allow` · **4.923603693479375** |
| ans037 · Giá trung vị ID 03/07 | `allow` · **78 900** |
| ans038 · Rating trung vị ID 03/07 | `allow` · **4.901304084208852** |
| "Giá **trung bình** tại VN 03/07" | `abstain` · `A19-AGGREGATION` (mean chưa chứng nhận cho `measure.price`) |
| "Listing nào có giá cao nhất ở VN?" | plan **giữ nguyên** `Scan→Filter→Rank`, không có `Aggregate` |
| `bgk19` *"Giá cao nhất tại Indonesia 03/07"* | **`abstain` `A19-VALUE-CLASS`** — không bao giờ `allow · 9 999 999` |
| `risk` · `over_answer_rate` | **0.0 · 0.0** |

Rule mới `A19-AGGREGATION` — xem §17.1. Dòng `bgk19` là cổng chung của W5 và
W14: nó đỏ nếu một trong hai bị merge một mình.

---

## §7. W6 — Khối so hai mốc thời gian

> Gỡ: ans019, ans020, và ca `tc34`. Phụ thuộc: không.
> Checklist §0.3 chạm: 1 · 3 · 4 · 7 · 8.

### 7.1. Sự thật

✅ `parse("Số listing tại Việt Nam thay đổi thế nào từ 01/07 đến 03/07?")`:

```
requested_measures = [("so listing", derived.product_count)]
time_scope         = ('2026-07-01','2026-07-03'), mode='all_with_caveat'
_synthesis_beats_template = False
infer_deterministic_template = "listing_count"     # ghim 2026-07-03
```

Template trả 668, evidence gắn `observed_date=2026-07-03`, và
`alignment._scope_issues` (dòng 313-346) chặn đúng với `date_range_narrowed` ⇒
`A22-ALIGN-DATE`. **Lớp alignment đang làm đúng việc của nó**; thứ thiếu là một
plan biết trả lời câu hỏi.

✅ Ca `tc34` là cùng một lỗ ở đường macro: `analytics/tools.py:42-51::sales_decline`
lấy `rows.iloc[-1]` — **chặng cuối**, bất kể cửa sổ được hỏi. Oracle
`p0_tc34_window` ghi `monthly_sold` = 193 (01/07) → 306 (02/07) → 204 (03/07),
`window_delta = 11.0`, `answered_delta = -102.0`.

### 7.2. W6.1 — `TemporalCompare` hai đầu mút trong compiler

`planner/compiler.py:248-252` hiện coi `TemporalCompare` là pass-through
(`_from_input`) — nó chỉ chiếu một cột delta đã được materialize sẵn. Thêm dạng
thứ hai, **không đụng dạng cũ** (macro `sales_decline` đang dùng dạng cũ):

Kích hoạt khi node có `refs` một measure **và** `len(plan.time_scope) == 2`
**và** input node là `Aggregate` có `group_by == ("dim.date",)`. Sinh:

```sql
SELECT
  MAX(CASE WHEN date = ?d0 THEN <m> END)                                          AS "<name>_start",
  MAX(CASE WHEN date = ?d1 THEN <m> END)                                          AS "<name>_end",
  MAX(CASE WHEN date = ?d1 THEN <m> END) - MAX(CASE WHEN date = ?d0 THEN <m> END) AS "<name>_delta"
FROM <input>
```

Không dùng `_column_for(measure_ref)` trên input của `TemporalCompare`: sau
`Aggregate`, cột vật lý đã được materialize dưới alias. Compiler phải đọc alias
từ `input_node.expected_schema`. Schema hai node là:

```python
# n4 Aggregate — schema trung gian thật, không chép schema final vào mọi node
(
    OutputField(name="date", type="date", semantic_ref="dim.date"),
    OutputField(name=f"{base}_at_date", type="number", semantic_ref=measure_ref),
)

# n6 TemporalCompare / LogicalQueryPlan.requested_output_shape
(
    OutputField(name=f"{base}_start", type="number", semantic_ref=measure_ref),
    OutputField(name=f"{base}_end",   type="number", semantic_ref=measure_ref),
    OutputField(name=f"{base}_delta", type="number", semantic_ref=measure_ref),
)
```

`base = measure_ref.rsplit(".", 1)[-1]`. Ba output cùng semantic ref là có chủ
ý: chúng là ba vai trò thời gian của cùng đại lượng, không phải ba metric tĩnh
mới. Alias phải lấy từ schema, không parse `plan_id`.

`d0 = min(time_scope)`, `d1 = max(time_scope)` — **không** phải cặp gần nhất có
sẵn. Đây là toàn bộ điểm của khối: `alignment` đã chặn đúng việc trả chặng cuối.

✅ Kiểm trên DuckDB với view `products`:

| country | `_start` | `_end` | `_delta` |
| --- | ---: | ---: | ---: |
| vn | 581 | 668 | **87** |
| id | 474 | 474 | **0** |

Khớp oracle `ans019` (+87) và `ans020` (0).

`validator.py:206-208` đã đòi `len(plan.time_scope) >= 2` cho `TemporalCompare`;
bổ sung: ở dạng hai đầu mút, `expected_schema` phải có **đúng ba** trường
`_start` / `_end` / `_delta` và `expected_cardinality == "1"`.

### 7.3. W6.2 — Synthesizer sinh plan hai đầu mút

`synthesizer.py::synthesize` — nới ràng buộc `len(dates) != 1 → None` thành:

| `len(dates)` | Hành vi |
| ---: | --- |
| 1 | như hôm nay |
| 2 | nhánh mới dưới đây |
| khác | `None` (câu hỏi phân rã, §8.6 `union_scope`) |

Nhánh hai mốc, các điều kiện **đều bắt buộc**:

- `request.ranking is None`;
- `dimensions` rỗng (so hai mốc **và** gom nhóm là hai chiều tự do — vượt grammar);
- phép tổng hợp nằm trong `valid_aggregations` của measure;
- không có `remote_predicates` (join + temporal cùng lúc vượt grammar).

Hình plan:

```
n1 Scan   (source)
n2 Filter (dim.country = c, dim.date IN (d0, d1) [+ sentinel nếu measure.price])
n4 Aggregate group_by=("dim.date",)  aggregation=<agg>   output_grain="date"
n6 TemporalCompare refs=(measure_ref,) time_scope=(d0,d1) output_grain="country_window"
```

`plan_id`: `synth:<measure>:<agg>:temporal:<direction>:<country>:<d0>..<d1>:<rel>:1.1`.
Không plan cũ nào có `len(dates) == 2` (hôm nay trả `None`), nên **không entry
nào của baseline bị đổi**; đây là mở rộng thuần.

`open_planner._synthesis_beats_template` thêm:

```python
# Mọi template ghim một snapshot; một câu hỏi hai mốc đi qua chúng sẽ được trả
# lời bằng chặng cuối, và alignment chặn nó bằng date_range_narrowed. Đó là một
# lời từ chối đúng cho một plan sai, không phải một câu hỏi không trả lời được.
if request.time_scope and len(set(request.time_scope.dates)) == 2:
    return True
```

### 7.4. W6.3 — Evidence, lineage và consistency

`analytics/tools.py` — nhận diện bằng output node `op == "TemporalCompare"`,
không bằng chuỗi `"temporal"` trong `plan_id`; sinh **ba** Evidence, mỗi cái một
`evidence_id` riêng:

| metric | value | attrs bắt buộc |
| --- | --- | --- |
| `<name>_start` | giá trị tại `d0` | `observed_date = d0` |
| `<name>_end` | giá trị tại `d1` | `observed_date = d1` |
| `<name>_delta` | `end - start` | `previous_date = d0`, `date = d1`, `derivation_op = "end_minus_start"`, `parent_evidence_ids = (start_id, end_id)` |

Hai thuộc tính `previous_date`/`date` là đúng cặp khoá mà
`alignment._scope_issues` (dòng 348-364) đọc để so span với câu hỏi, nên khối
mới đi qua chính phép kiểm đang chặn nó hôm nay — không phải một cửa riêng.

`agent/consistency.py::check_evidence_arithmetic` thêm một luật, cùng họ với
luật `partition + partition = total` đã có:

> Với ba evidence cùng gốc tên `X_start`, `X_end`, `X_delta` có cùng `country` và
> cùng `(previous_date, date)`: `X_end - X_start == X_delta` trong dung sai của
> kiểu số. Lệch ⇒ issue ⇒ `A26-CONSISTENCY`.

Đây là lineage **động**, không được khai giả là một cạnh tĩnh trong
`MetricGraph`: cùng operator áp được cho price, rating hoặc count và không thể
đăng ký vô hạn các tên `<name>_delta`. `verifier` bổ sung luật chung cho mọi
Evidence có `parent_evidence_ids`:

1. mọi parent id tồn tại trong cùng response, không tự tham chiếu, không trùng;
2. cùng `source_tier` và `dataset_version`;
3. `derivation_op="end_minus_start"` ⇒ đúng hai parent mang vai trò start/end,
   cùng unit/country, và `value == end - start` trong dung sai số học hiện có.

`MetricGraph` tiếp tục kiểm lineage của metric **tĩnh**; typed derivation kiểm
lineage của phép biến đổi **động**. Không có một trong hai đường này thì derived
evidence không được claim.

**Renderer deterministic** trong `agent/workflow.py` thêm nhánh trước renderer
open-result chung: hiển thị “tại đầu kỳ”, “tại cuối kỳ”, “thay đổi” và phạm vi
`d0 → d1`, trích dẫn cả ba evidence. Không in thô
`product_count_start/product_count_delta`, và không mô tả toàn bộ kết quả là
“snapshot d1”; nếu không, plan đúng vẫn trả câu chữ sai scope và vi phạm mục
tiêu `INV-NO-INTERNAL-VOCABULARY`.

### 7.5. W6.4 — Macro `sales_decline` phải tôn trọng cửa sổ được hỏi

`analytics/tools.py:42-51`:

- nhận thêm tham số `window: tuple[str, str] | None = None` (mặc định `None` ⇒
  hành vi cũ nguyên vẹn);
- `window` khác `None` ⇒ chọn các transition có `previous_date >= window[0]` và
  `date <= window[1]`, rồi **cộng dồn** `monthly_sold_delta` trên các chặng liên
  tiếp phủ kín cửa sổ;
- không phủ kín được cửa sổ ⇒ **trả `[]`**, để tầng gọi ra `A-NO-EVIDENCE`. Trả
  chặng cuối là đúng lỗi `tc34`;
- `attrs`: `previous_date = window[0]`, `date = window[1]`, thêm
  `legs = <số chặng đã cộng>`.

`agent/tool_dispatch.py::_get_sales_transitions` truyền `ctx.request.date_range`
xuống khi nó có hai mốc.

✅ Với `tc34` (item `24710759163`): 193 → 306 → 204 ⇒ hai chặng `+113` và `-102`
⇒ tổng **+11**, khớp `p0_tc34_window.window_delta = 11.0`.

### 7.6. Nghiệm thu W6

| Ca | Trước | Sau |
| --- | --- | --- |
| ans019 | `clarify` `A22-ALIGN-DATE` | `allow` · start 581 · end 668 · **delta +87** |
| ans020 | `clarify` `A22-ALIGN-DATE` | `allow` · start 474 · end 474 · **delta 0** |
| `tc34` | trả chặng cuối `-102` hoặc bị chặn | `allow` · **+11**, `legs = 2` |
| Câu một mốc bất kỳ | — | plan **không đổi** |
| `synthesizer_equivalence_baseline.json` | — | **không entry nào đổi** |

`eval/dr2607.json#tc34` đang có `expected_action: null` và
`status: "executable_red_date_window_narrowing"`. Sau W6 đổi thành
`expected_action: "allow"` với oracle `+11` lấy từ
`eval/independent/p0_probe_expected.json#p0_tc34_window` — **không** gõ lại con
số vào fixture. Trước khi có W6, ghi rõ đây là **"từ chối an toàn"**; không được
để một bộ khai kỳ vọng rỗng trong khi bộ khác ghim `clarify`.

---

## §8. W7 — Thang leo thang rủi ro không áp cho plan tất định

> Gỡ: ans031, ans032, ans033, ans034; **và** ✅ `cq02` `cq03` `cq04`
> (§1.6.1) cùng `mt005` `mt011` `mt017` `mt023` (§1.6.2) — bảy ca nữa cùng
> nguyên nhân, nằm ngoài bộ 44 câu. Mở khoá hai ca nghiệm thu của W1 (120 và
> giao rỗng). Phụ thuộc: **W1**, và **W13** (W7 làm nhiều plan tất định được
> chạy hơn, nên nó phóng đại lớp lỗi ở §14).
> Checklist §0.3 chạm: 1 · 3 · 4 · 7 · 8.

### 8.1. Sự thật — plan đã đúng, chỉ không được chạy

✅ Cả bốn câu shop chính hãng đều **sinh plan hợp lệ và cho đúng đáp án**:

| Câu | `plan_id` | Kết quả chạy thật |
| --- | --- | ---: |
| listing shop chính hãng VN | `synth:derived.product_count:count:nogroup:none:vn:2026-07-03:belongs_to:1.1` | **465** |
| shop chính hãng VN | `synth:derived.shop_count:count:nogroup:none:vn:2026-07-03:belongs_to:1.1` | **7** |
| listing shop chính hãng ID | `…:id:2026-07-03:belongs_to:1.1` | **471** |
| shop chính hãng ID | `…:id:2026-07-03:belongs_to:1.1` | **9** |

SQL sinh ra đúng hình mong đợi:

```sql
SELECT COUNT(DISTINCT product_listing_key) AS "listing_count"
FROM (SELECT l.*, r.is_official_shop_bool AS "is_official_shop_bool"
      FROM (... products WHERE country_code=? AND date=?) l
      LEFT JOIN shop_info r ON ...) ...
WHERE is_official_shop_bool = ?
```

✅ Thứ chặn là `planner/risk.py::score_plan`:

```
validate_plan  -> valid, depth=5
relation_count -> 1   (1 join)
plan_shape     -> 2   (depth=5 > 3)
score          -> 3  >= tau1=3  -> requested_mode="critic"
enable_critic  -> False          -> effective_mode="blocked", allowed=False
```

⇒ `AnalyticalPlanError("Plan critic chưa qua acceptance…")` ⇒ `A19-PLAN`.

Đối chiếu: câu trung vị cho `score=0, depth=3` ⇒ `single` ⇒ chạy được. Nói cách
khác, **cái duy nhất đẩy bốn câu này qua ngưỡng là việc plan có một node `Join`
đã được chứng nhận** — thứ mà cả tầng relation registry tồn tại để cho phép.

### 8.2. Lập luận: thang này đo cái gì

Thang leo thang tồn tại để **review một plan do mô hình ngôn ngữ viết**. Các yếu
tố của nó nói lên điều đó: `schema_linking`, `entity_margin`, `new_metric` đều
là bất định của bước ánh xạ chữ→ký hiệu.

Một plan do `DeterministicPlanSynthesizer` sinh **không chứa output nào của mô
hình**. Nó là hàm của một grammar đã phát hành, một relation registry đã chứng
nhận, và một validator. Đưa nó cho một critic — bản thân critic là một mô hình —
không thêm thông tin nào về nó; nó chỉ thêm một nguồn bất định vào một thứ đang
tất định, và một khoản chi phí.

Vì vậy W7 **không bật critic**. Nó nói: với plan tất định, phép kiểm đúng là một
**vị từ tất định**, không phải một thang leo thang.

### 8.3. W7.1 — `plan_provenance`

`planner/risk.py::score_plan` thêm keyword-only:

```python
plan_provenance: Literal["deterministic_synthesis", "deterministic_template",
                         "certified_macro", "llm_ir"] = "llm_ir",
```

Mặc định `"llm_ir"` ⇒ mọi call site chưa cập nhật giữ **nguyên hành vi hôm nay**.
Không được đọc provenance từ `planning_meta["mode"]`: ở source hiện tại dict này
chỉ được dựng **sau** lời gọi `score_plan`. `agent/workflow.py` phải xác định một
biến cục bộ ngay sau khi chọn plan và trước khi chấm điểm:

```python
if planner_result is not None:
    plan_provenance = (
        "llm_ir" if planner_result.mode == "llm_semantic_plan"
        else planner_result.mode
    )
elif synthesized is not None:
    plan_provenance = "deterministic_synthesis"
else:
    plan_provenance = "deterministic_template"

risk = score_plan(
    logical_plan,
    complexity_level=complexity_level,
    plan_provenance=plan_provenance,
    config=...,
)
```

Nhánh nào đã chọn plan thì nhánh đó cấp provenance; không suy ngược bằng prefix
của `plan_id`. Sau lời gọi, `planning_meta["mode"]` vẫn giữ tên mode tương thích
hiện tại (`"llm_semantic_plan"` ở đường LLM), còn
`planning_meta["risk"]["provenance"]` nhận chính `plan_provenance` vừa truyền vào
`score_plan`. Hai giá trị có chủ đích khác nhau: một cái là mode telemetry hiện
hành, một cái là lớp xuất xứ mà risk policy tiêu thụ.

#### 8.3.1. Đường template cũng bị chặn, và bị chặn bằng một cơ chế khác

✅ `bgk08` (*"Shop nào có nhiều listing nhất tại Indonesia ngày 03/07?"*) đi
đường `deterministic_template`, không phải synthesizer. Nó bị chặn ở
[`workflow.py:1265-1268`](../src/gladiators/agent/workflow.py):

```python
complexity_level = (
    classify_complexity(analytical_request)
    if request.intent == "open_analytical"
    else "L3" if analytical_kind == "top_shop_by_listing_count" else "L2"
)
```

`"L3"` ⇒ `risk.py:95` `elif score >= config.tau1 or complexity_level == "L3"` ⇒
`critic` ⇒ blocked — **bất kể điểm rủi ro là bao nhiêu**. Tức đây là một đường
chặn **thứ hai**, độc lập với ngưỡng `tau1` đã mô tả ở §8.1.

✅ Và bật cờ **không** gỡ được: với `GLADIATORS_ENABLE_CRITIC=1` trên
`create_runtime("offline")`, `risk.allowed` thành `True` rồi nhánh critic ném
*"Plan critic được yêu cầu nhưng chưa có LLM provider hỗ trợ P9."* ⇒ vẫn
`A19-PLAN`. Tức **không cấu hình phát hành nào trả lời được nhóm câu này**, và
đó là lý do §8.2 chọn một vị từ tất định thay vì một cờ.

Hệ quả cho W7:

- `plan_provenance` phải nhận **cả** `"deterministic_template"` — một plan
  template là plan do người viết và đã được chứng nhận, nên lập luận §8.2 áp
  y hệt;
- vị từ ở §8.4 chạy **trước** cả nhánh `complexity_level == "L3"`, không chỉ
  trước phép so với `tau1`. Nếu chỉ vòng qua `tau1`, `bgk08` vẫn bị chặn và W7
  sẽ trông như đã xong trong khi một nửa cơ chế còn nguyên;
- `complexity_level` **vẫn được tính và ghi trace**. Nó là quan sát về độ phức
  tạp, không phải quyết định về việc ai được review.

### 8.4. W7.2 — Vị từ chấp nhận tất định

```python
def deterministic_plan_is_acceptable(plan: LogicalQueryPlan) -> tuple[bool, str]:
    """Plan tất định có được chạy mà không cần critic hay không.

    Đây KHÔNG phải một ngưỡng điểm nới lỏng. Nó là danh sách những tính chất mà
    thang leo thang đang dùng điểm số để ước lượng, kiểm trực tiếp trên plan:
    một critic là mô hình, và một mô hình không nói được điều gì về một plan
    không có mô hình nào trong đó.
    """
```

Sáu điều kiện, **tất cả** phải đúng; sai bất kỳ ⇒ `blocked` như hôm nay:

| # | Điều kiện | Chặn cái gì |
| -: | --- | --- |
| 1 | `validate_plan(plan).valid` | mọi thứ validator đang chặn |
| 2 | Mọi `node.relation` có trong `RELATIONS` và `find_path` cho đường **dài đúng 1** | registry đổi hình mà không ai review |
| 3 | Số node `Join` `<= RELATION_EDGE_BUDGET` (3) | ngân sách A1.4 |
| 4 | Mọi relation có `fanout_effect != "none"` được theo sau bởi một node `Dedupe` trước node `Aggregate` đầu tiên | INV-DEDUPE-BEFORE-AGGREGATE |
| 5 | Mọi relation `temporal_validity == "static_latest_only"` ⇒ `len(plan.time_scope) == 1` và `"dim.date" not in group_by` | enrichment tĩnh bị dùng như panel theo ngày |
| 6 | Không node nào có `op` ngoài 12 operator của IR | operator ngoài hợp đồng |

Đạt ⇒ `QueryRiskResult(score, factors, requested_mode, effective_mode="single",
allowed=True, reason="Plan tất định đạt vị từ chấp nhận; thang leo thang chỉ áp
cho plan do mô hình sinh.")`.

**Điểm `score` và `factors` vẫn được tính và ghi trace nguyên vẹn** — chúng là
quan sát, và bỏ chúng đi thì không ai đo được vị từ này có đang che một plan
đáng ngờ hay không.

### 8.5. W7.3 — Telemetry bắt buộc

`planning_meta["risk"]` phải mang:

```python
{"score": ..., "requested_mode": ..., "effective_mode": ...,
 "provenance": ...,
 # Khoá đếm số lần nhánh THẬT SỰ bắn (CLAUDE.md §5.1.3). Không có nó, "vị từ
 # tất định đã mở khoá 4 câu" và "vị từ chưa bao giờ chạy" là hai bảng số giống
 # hệt nhau.
 "deterministic_bypass": {"applied": bool, "reason": str}}
```

Trong một chu kỳ tương thích, vẫn ghi các khoá phẳng đang được consumer hiện tại
đọc: `risk_score`, `requested_escalation`, `escalation_mode`, `risk_factors`.
Giá trị của chúng phải được lấy từ cùng `QueryRiskResult` với object `risk`; test
contract khẳng định hai biểu diễn không lệch. Consumer mới chỉ đọc object `risk`,
sau một release mới được xoá các khoá phẳng.

### 8.6. W7.4 — Fixture `p0-grouping-dropped-official-shop`

✅ Fixture này đang tự mâu thuẫn: `expected_action: "clarify"` với
`allowed_rule_ids: ["A22-ALIGN-GROUPING"]`, trong khi `baseline.action` trong
**chính nó** ghi `"abstain"` / `"A19-PLAN"`, và runtime khớp `baseline`.

Sau W7 câu *"Có bao nhiêu listing của shop official tại VN?"* trả **465**
(oracle `p0_grouping_official_shop.vn_official_shop_listings = 465`). Cập nhật
theo đúng ba bước ở docstring `tests/test_p0_regression_lock.py`:

1. `expected_state: "green"`, điền `fixed_in` / `fixed_at`;
2. dán khối observed mới vào `baseline`, đối chiếu với oracle độc lập;
3. chạy lại `scripts/build_release_proof.py`, diff với proof P0.

`expected_action: "allow"`, `allowed_rule_ids: ["A-ALLOW"]`.
**`forbidden_answer_tokens: ["668"]` giữ nguyên** — nó là thứ khoá lại con số sai
cũ, và nó phải sống sót qua thay đổi này.

### 8.7. Nghiệm thu W7

| Ca | Kỳ vọng |
| --- | ---: |
| ans031 · shop chính hãng VN | `allow` · **7** |
| ans032 · listing shop chính hãng VN | `allow` · **465** |
| ans033 · shop chính hãng ID | `allow` · **9** |
| ans034 · listing shop chính hãng ID | `allow` · **471** |
| W1 · shop `Richy - Chi nhánh Miền Nam` | `allow` · **120** |
| W1 · `Bibica` ∩ `Richy - Chi nhánh Miền Nam` | `allow` · **0** |
| `GLADIATORS_ENABLE_CRITIC` | **vẫn `False`** trong source |
| Plan `llm_ir` bất kỳ | thang leo thang **không đổi một chút nào** |
| Câu trả về `668` cho một câu hỏi có lọc | **không tồn tại** (khoá bởi `forbidden_answer_tokens`) |
| `eval/questions_critic.json` | `cq02` `cq03` `cq04` · `allow` — và bộ đề này **được chấm** (W15.2) |
| `questions_multiturn` · `mt005` `mt011` `mt017` `mt023` | `allow` · **120** ⇒ lượt lệch **6 → 2** |

Test mới `tests/test_deterministic_escalation.py`:

- plan tất định 1 join đạt vị từ ⇒ `allowed=True`, `effective_mode="single"`;
- plan tất định có relation `fanout_effect != "none"` mà **thiếu** `Dedupe` ⇒
  `blocked`;
- plan tất định dùng relation `static_latest_only` với `time_scope` 2 ngày ⇒
  `blocked`;
- cùng một plan với `plan_provenance="llm_ir"` ⇒ `blocked` (thang cũ nguyên vẹn);
- `deterministic_bypass.applied` bật đúng khi và chỉ khi vị từ mở khoá.

---

## §9. W8 — Ngữ nghĩa cột quan sát, khai bằng registry

> Sửa oracle/route: ans017, ans018, ans044. Ans011–ans014 chỉ được mở sau khi
> chủ dữ liệu duyệt `ColumnSemantics`; mặc định `unknown` giữ fail-closed.
> Checklist §0.3 chạm: 1 · 3 · 4 · 8.

### 9.1. Vấn đề không phải thiếu code

✅ Ba sự thật đo được:

| Cột | Dữ liệu | Diễn giải hiện tại |
| --- | --- | --- |
| `is_ad_bool` | **False ở 3341/3341 dòng**, không null | `data/coverage.py:30` xếp `zero_variance`; không ref catalog nào bind |
| `is_sold_out_bool` | **False ở 3341/3341 dòng**, không null | như trên |
| `has_structured_voucher` | VN 1580/1919 · **ID 0/1422** | gate ra `A-VOUCHER-ID` cho ID |

✅ Và một sự thật làm đổi cách đọc `ans017`/`ans018`: cột `vouchers` (nhãn
voucher dạng mảng) có **630/1422 dòng ID với `vouchers_count > 0`**. Nghĩa là ở
Indonesia listing **có voucher**, chỉ không có voucher **được ghi có cấu trúc**.

⇒ Oracle `ans017`/`ans018` kỳ vọng `listing_count: 0` đang đo
`has_structured_voucher`, còn câu hỏi *"có bao nhiêu listing có voucher"* không
nói rõ nó hỏi cái nào. **Trả `0` ở đây sẽ là một câu trả lời sai một cách im
lặng**, và `A-VOUCHER-ID` đang từ chối đúng. Việc phải làm là sửa **câu hỏi và
oracle**, không phải nới gate — xem 9.5.

Với `is_ad`/`is_sold_out` thì lỗi lại là **nhãn từ chối mô tả sai vấn đề**:
`parser.UNSUPPORTED["ads"]` khớp `"quang cao"` và trả về thông điệp *"Dataset
không có impressions, clicks hay ad spend"*. Đúng cho câu hỏi về **hiệu quả**
quảng cáo; sai cho câu hỏi *"có bao nhiêu listing được gắn cờ là quảng cáo"*, vì
cột `is_ad` **có tồn tại và có giá trị**.

### 9.2. W8.1 — Registry ngữ nghĩa quan sát

File mới **`src/gladiators/domain/column_semantics.py`**:

```python
"""Một cột toàn False nghĩa là gì -- và ai được quyền nói.

"Đã quan sát và đúng là không có cái nào" với "chỗ này không thu thập được" cho
HAI câu trả lời trái ngược nhau từ cùng một cột. Không dữ liệu nào trong dataset
phân biệt được hai thứ đó, nên nó là một quyết định của người sở hữu dữ liệu.

Mặc định là `unknown` và `unknown` fail-closed: viết code trả lời trước khi có
quyết định sẽ đẻ ra một câu trả lời trông rất chuẩn, có số má đầy đủ, và sai âm
thầm -- đúng lớp lỗi ở §2.
"""

ObservationSemantics = Literal["observed", "not_collected", "unknown"]

@dataclass(frozen=True)
class ColumnSemantics:
    column: str                  # "<table>.<column>"
    semantics: ObservationSemantics
    approved_by: str | None      # None khi semantics == "unknown"
    approved_at: str | None
    caveat_key: str | None       # message key BẮT BUỘC khi semantics == "observed"

COLUMN_SEMANTICS: dict[str, ColumnSemantics] = {
    "products_clean.csv.is_ad_bool":       ColumnSemantics(..., "unknown", None, None, None),
    "products_clean.csv.is_sold_out_bool": ColumnSemantics(..., "unknown", None, None, None),
}

REGISTRY_HASH: str = ...   # vào context hash như mọi registry khác
```

Bất biến kiểm ở import (`ColumnSemanticsError`):

- `semantics != "unknown"` ⇒ `approved_by` và `approved_at` bắt buộc;
- `semantics == "observed"` ⇒ `caveat_key` bắt buộc;
- `column` phải tồn tại trong `domain/tables.py`;
- **Agent không được điền `approved_by`.** Cùng luật với A12-R6 ở §3.2.

Mọi thay đổi registry ⇒ `REGISTRY_HASH` đổi ⇒ chạy lại oracle / PAM / eval.

### 9.3. W8.2 — Ba hành vi theo giá trị registry

| `semantics` | Catalog | Hành vi runtime |
| --- | --- | --- |
| `unknown` | không expose ref | **Y HỆT hôm nay** — `A-MISSING-ADS` / `A19-PLAN` |
| `not_collected` | không expose ref | `abstain` · **`A-DATA-ABSENT`** với lý do nêu đúng: cột không được thu thập, không phải "dataset không có khái niệm này" |
| `observed` | expose `dim.is_ad` / `dim.is_sold_out` (`type="bool"`, `answerability="exposed_as_dimension"`) | trả lời được, **bắt buộc kèm caveat** từ `caveat_key` |

Để bảng trên thật sự điều khiển runtime, thêm một đường gọi duy nhất
`classify_column_observation(normalized_text)` và gọi nó trong
`StructuredRequestParser.parse`, **trước** vòng `UNSUPPORTED` và trước khi dựng
`AnalyticalRequest`. Hàm nhận diện riêng hai loại yêu cầu: hỏi cờ quảng cáo và
hỏi trạng thái hết hàng; sau đó đọc `COLUMN_SEMANTICS`:

- `unknown` trả `None`, để nguyên đường từ chối hiện hành của từng câu;
- `not_collected` trả một kết quả có kiểu gồm `column`, `semantics`, `caveat_key`
  và gate ánh xạ duy nhất sang `A-DATA-ABSENT`;
- `observed` không tự dựng predicate; nó cho phép catalog và qualifier registry
  phát hành ref, rồi semantic parser bind theo đường chuẩn.

Không đặt nhánh kiểm registry thứ hai trong gate hoặc synthesizer. Test wiring
phải thay lần lượt ba trạng thái registry và chứng minh call site trên thật sự
bắn; chỉ kiểm nội dung dict registry là không đủ.

Với `observed`, ba việc phải làm cùng lúc:

1. `domain/catalog.py` thêm ref, và `data/coverage.py:30` bỏ cột khỏi
   `ZERO_VARIANCE_COLUMNS` — hai nơi này nói về cùng một cột và không được lệch;
2. `parser.UNSUPPORTED["ads"]` phải **thu hẹp**: chỉ khớp khi câu hỏi nêu chỉ số
   **hiệu quả** (`impression`, `click`, `chi phí`, `hiệu quả`), không khớp câu
   chỉ hỏi cờ đã quan sát. Đây là một thay đổi taxonomy có rủi ro làm rơi lời từ
   chối đúng, nên nó **chỉ được làm khi registry đã duyệt**;
3. `domain/qualifiers.py` thêm surface `"het hang"` / `"sold out"` bind về
   `dim.is_sold_out`, và **xoá** chúng khỏi
   `synthesizer._LITERAL_QUALIFIER_MARKERS` — danh sách đó là nơi giữ marker
   **chưa** bind được; giữ lại một marker đã bind sẽ chặn đúng câu vừa bind được.

Câu trả lời khi `observed` phải nói *"0 listing **được dataset gắn cờ**"*, kèm
caveat rằng không suy ra được thực tế. `INV-NO-INTERNAL-VOCABULARY` áp bình
thường: caveat viết bằng lời, không bằng tên cột.

### 9.4. W8.3 — Voucher: hai khái niệm, hai ref

Registry ngữ nghĩa **không** áp cho voucher, vì đây không phải "cột có được thu
thập không" mà là "hai khái niệm khác nhau bị gọi bằng một từ".

`domain/catalog.py` — dùng đúng hai ref **đã tồn tại**, không tạo ref thứ ba:

| Ref | Nghĩa | Cột |
| --- | --- | --- |
| `derived.has_structured_voucher` | có mã voucher **có cấu trúc** (code, chiết khấu, cửa sổ) | `product_snapshot_metrics.csv.has_structured_voucher` |
| `derived.has_voucher_label` | có **nhãn** voucher hiển thị | bind vật lý mới tới `products_clean.csv.vouchers_count` |

Ref `derived.has_voucher_label` đã ở catalog nhưng chưa có physical, vì vậy
không thể chỉ thêm alias. `_DERIVED_PHYSICAL` phải ánh xạ nó tới
`products_clean.csv.vouchers_count`; predicate dương là `gte 1`, không phải
`eq True`. Mở rộng `QualifierSpec` thành hợp đồng predicate có kiểu dùng operator
chuẩn ở §12.2.1:

```python
@dataclass(frozen=True)
class QualifierSpec:
    qualifier_id: str
    ref: str
    surfaces: tuple[str, ...]
    negations: tuple[str, ...]
    op: ExecutablePredicateOp = "eq"
    value: Scalar = True
    negated_op: ExecutablePredicateOp = "eq"
    negated_value: Scalar = False
    null_policy: Literal["exclude", "false"] = "exclude"
    bindable: bool = False
```

`qualifiers.match` trả `MatchedQualifier(spec, op, value, surface)`; parser dùng
`op/value` đó thay vì hard-code `op="eq"`. Validator kiểm cả hai operator nằm
trong `CATALOG[ref].allowed_filters`. Hai qualifier voucher chỉ nhận surface
tường minh:

| Qualifier | Surface dương | Predicate |
| --- | --- | --- |
| structured | `"voucher có cấu trúc"`, `"mã voucher có cấu trúc"` | `derived.has_structured_voucher eq True` |
| display label | `"có nhãn voucher"`, `"voucher hiển thị"` | `derived.has_voucher_label gte 1` |

Với label, `null_policy="exclude"`: null không được suy thành “không có”. Câu
phủ định dùng `lte 0` và vẫn loại null. Compiler tiếp tục bind tham số, không
ghép literal vào SQL.

Surface chung `"có voucher"`, `"voucher"`, `"has voucher"` phải xuất hiện ở
alias của **cả hai** ref và bị xoá khỏi `QUALIFIERS`; tuyệt đối không thêm chúng
vào `PREFERRED_REF_BY_SURFACE`. Source hiện tại có một lỗ hổng: `_link` gặp
`AliasMatch.ambiguous` không có preferred ref thì `continue`, tức nuốt mất sự
mơ hồ. Thay return type của `_link` bằng:

```python
class SemanticAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["alias_collision"]
    surface: str
    candidate_refs: tuple[str, ...]

@dataclass(frozen=True)
class LinkResult:
    bindings: tuple[SemanticBinding, ...]
    ambiguities: tuple[SemanticAmbiguity, ...]
```

`parse` gộp ambiguity từ lượt link measure và dimension vào
`AnalyticalRequest.semantic_ambiguities`; `classify_a19` ánh xạ danh sách khác
rỗng sang `clarify / A-ANALYTICAL-AMBIGUITY`, với lựa chọn được render từ mô tả
catalog chứ không lộ ref nội bộ. Field `ambiguities: tuple[str, ...]` cũ được
giữ đọc trong một release để tương thích payload, nhưng parser mới chỉ ghi field
có kiểu. Như vậy mọi alias collision không có quyết định ưu tiên đều fail-closed,
không chỉ voucher.

Đây là khác biệt thật: trên snapshot 03/07 của ID,
`has_structured_voucher=True` là **0/474**, còn `vouchers_count > 0` là
**210/474** (toàn ba ngày: 0/1422 so với 630/1422).

### 9.5. W8.4 — Sửa bộ đề, không sửa gate

Hai ca phải sửa ở phía **bộ đề**, không phía hệ:

| Ca | Vấn đề | Việc |
| --- | --- | --- |
| ans017 · ans018 | Câu hỏi mơ hồ giữa hai khái niệm voucher; oracle đo `has_structured_voucher` | Tách thành hai câu tường minh trong `scripts/build_question_bank.py`; câu mơ hồ giữ `expected_action: "clarify"` |
| ans044 | *"Giá của đối thủ ngoài sàn"* nhận `A-CROSS-CURRENCY-SCOPE` thay vì nhãn route external | Nhãn từ chối sai vấn đề. Router phải nhận ra yêu cầu giá external theo cấu trúc, không dựa vào một cụm từ liền nhau ⇒ `A14-EXT` |

`external/router.py` hiện chỉ khớp các chuỗi liền nhau như `"gia doi thu"` và
`"gia ben ngoai"`; câu ans044 chen `"của"` và `"ngoài sàn"` nên rơi qua. Thay
`_COMPETITOR` bằng hai nhóm khái niệm có word-boundary:

```python
_PRICE_CONCEPT = ("gia", "price", "harga")
_EXTERNAL_COMPETITOR_CONCEPT = (
    "doi thu", "pesaing", "competitor", "ngoai san", "ben ngoai san",
    "outside platform", "external marketplace",
)
```

`_is_external_competitor_price` tách câu theo dấu câu/liên từ mạnh và trả true
khi **cùng một mệnh đề** có ít nhất một price concept và một external competitor
concept. Nó chạy trước định tuyến internal và trước các gate thiếu country;
riêng yêu cầu tường minh quy đổi/so sánh VN–ID vẫn giữ `A16-CROSS-CURRENCY`.
`agent/parser.py::UNSUPPORTED["external"]` phải bỏ hoặc gọi chính helper này,
không duy trì một danh sách phrase thứ hai. `classify_external_need` là nguồn
quyết định duy nhất cho `route_mode`, `purpose` và `rule_id`.

`ans044` không đổi `answerable` (vẫn `false`) và không đổi `over_refusal_rate` —
nó chỉ đổi `expected_action` từ `clarify` sang `abstain` và làm
`refusal_precision` phản ánh đúng.

### 9.6. Nghiệm thu W8

| Điều kiện | Kỳ vọng |
| --- | --- |
| Registry giữ toàn `unknown` | **19 ca lệch giảm đúng 1** (ans044); 6 ca nghiệp vụ **không đổi** |
| `is_ad` → `not_collected` | ans011 · ans012 ra `A-DATA-ABSENT` với lý do đúng |
| `is_ad` → `observed` | ans011 · ans012 ra `allow` · **0**, có caveat, `risk` vẫn 0.0 |
| Câu hỏi *hiệu quả* quảng cáo | vẫn `A-MISSING-ADS` ở cả ba trạng thái registry |
| `"có voucher"` sau W8.3 | `clarify` với hai lựa chọn nêu rõ; không ref nào bị chọn ngầm |
| `"voucher có cấu trúc"` · ID · 03/07 | `allow` · **0/474** |
| `"có nhãn voucher"` · ID · 03/07 | `allow` · **210/474** |
| ans044 và các biến thể chèn `của`, `ở`, `ngoài sàn` | `abstain` · **`A14-EXT`**; không rơi vào gate currency/country |

---

## §10. W9 — Sửa phép đo trước khi đọc kết quả

> Không hạng mục nào ở §5–§9 được chấm bằng một phép đo chưa qua §10.
> Checklist §0.3 chạm: 3 · 4 · 7 · 8.

### 10.1. W9.1 — Bốn con số, bốn cái tên

✅ Xung đột đã định vị ở §1.3. Từ điển bắt buộc:

| Tên | Công thức | Hôm nay |
| --- | --- | ---: |
| `answer_rate_all` | `answered / labelled` | ◻ 20/44 = 0.4545 |
| `answerable_coverage` | `answered ∩ answerable / answerable` | ◻ 20/38 = 0.5263 |
| `over_refusal_rate` | `refused ∩ answerable / answerable` | ◻ 18/38 = 0.4737 |
| `over_answer_rate` | `answered ∩ unanswerable / unanswerable` | ◻ 0.0 |
| `risk` | `answered − correct − unscored / answered − unscored` | ◻ 0.0 |
| `refusal_precision` | `refused ∩ unanswerable / refused` | ◻ 0.273 |
| `refusal_recall` | `refused ∩ unanswerable / unanswerable` | ◻ 1.0 |

Việc:

- `scripts/run_evaluation.py:141` — đổi khoá `"coverage"` thành
  `"answerable_coverage"`, **thêm** `"answer_rate_all"`;
- `scripts/run_risk_coverage.py:97` — đổi khoá `"coverage"` thành
  `"answer_rate_all"`, **thêm** `"answerable_coverage"`;
- `schema_version` của cả hai report tăng lên `v2`;
- một hàm dùng chung `selective_metrics()` cho cả hai script, thay vì hai bản.
  Hai bản là lý do hai công thức trôi khỏi nhau;
- `rate()` trả `None` khi mẫu số rỗng — **không phải `0.0`** (giữ nguyên luật đã
  có ở `run_evaluation.py:120-131`, và áp cả cho script kia);
- `risk` và `over_answer_rate` phải xuất hiện **cạnh** mọi con số coverage trong
  mọi report. Tách rời chúng là mở đường cho việc tối ưu coverage bằng đoán bừa.

Test `tests/test_eval_metrics.py` bổ sung: hai script cho **cùng** giá trị cho
mọi tên chung khi chạy trên cùng một suite và cùng rows.

### 10.2. W9.2 — Kiểm biến hình: hơn một nửa phép kiểm không chạy

◻ Báo cáo `2026-08-27-metamorphic.json`: 122 pass · 8 fail · **174 skip** ·
4 suspect; rate 0.9104. **174/308 = 56,5% bị bỏ qua.** Chi tiết theo quan hệ:

| Quan hệ | pass | fail | skip | suspect | rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| MR-1 | 18 | **8** | 18 | 0 | 0.6923 |
| MR-3 | 0 | 0 | **44** | 0 | `null` |
| MR-4 | 44 | 0 | 0 | 0 | 1.0 |
| MR-5 | 44 | 0 | 0 | 0 | 1.0 |
| MR-6 | 2 | 0 | **42** | 0 | 1.0 |
| MR-7 | 14 | 0 | 26 | **4** | 0.7778 |
| MR-8 | 0 | 0 | **44** | 0 | `null` |

- **MR-1 (8 fail):** đóng bởi **W4**, không hard-code câu nào.
- **MR-3 skip 44/44:** `run_metamorphic.py:124-127` cần `case["entity_text"]`
  nguyên văn; **không case nào trong bộ 44 có khoá đó**. Bộ đề mới ở W9.4 phải
  cố ý chứa entity nguyên văn kèm `entity_text`.
- **MR-8 skip 44/44:** cần câu cực trị (`cao nhất`/`thấp nhất`) có đáp án tất
  định. Bộ mới phải chứa, và phải xử lý hoà (`rank_tie_at_cut`).
- **MR-6 skip 42/44:** `add_narrowing_filter` chèn `"có voucher"`; sau **W8.3**
  cụm đó thành mơ hồ ⇒ biến thể ra `clarify` ⇒ vẫn skip. Đổi transform sang một
  qualifier **không mơ hồ** lấy từ `domain/qualifiers.py` (`"chính hãng"`), theo
  đúng docstring hiện có: *"Dùng đúng cụm đã có trong `domain/qualifiers.py`,
  không tự nghĩ từ mới"*.

**Ngưỡng số ca tối thiểu.** `eval/metamorphic/relations.py` thêm field
`min_applicable: int = 1` cho `MetamorphicRelation`; `run_metamorphic.py` thêm
vào report:

```json
"by_relation": {"MR-3": {"pass": 0, "fail": 0, "skip": 44, "suspect": 0,
                         "rate": null, "applicable": 0, "min_applicable": 10,
                         "status": "not_measured"}}
```

Quan hệ có `applicable < min_applicable` ⇒ `status: "not_measured"` và **bị loại
khỏi mẫu số** của `metamorphic_consistency_rate`. Một tỷ lệ tính trên các quan hệ
chưa từng chạy là một tỷ lệ che đúng thứ cần xem.

### 10.3. W9.3 — Bốn ca `suspect`: kiểm cơ chế, không kiểm kết quả

◻ Cả bốn đều là MR-7 với lý do `"hai câu khác nhau cho cùng kết quả (10.0,)"`
(ans005–ans008). ✅ Dữ liệu có **đúng 10 shop ở mỗi thị trường** ⇒ bằng nhau là
**đúng**.

Phép kiểm hiện tại đòi *"hai phạm vi khác nhau phải cho số khác nhau"* — một đòi
hỏi sai về nguyên tắc. Đổi `expectation="values_differ"` của MR-7 thành
`expectation="scope_actually_changed"`, và `_verdict` kiểm **cơ chế**:

| # | Kiểm | Nguồn |
| -: | --- | --- |
| 1 | Predicate `dim.country` trong plan của hai câu **khác nhau** | `planning.plan_id` |
| 2 | `Evidence.attrs["country"]` của hai câu **khác nhau** | evidence |
| 3 | `plan_hash` của hai câu **khác nhau** | `planning.plan_cache.plan_hash` |

Ba điều kiện đúng ⇒ `pass`, kể cả khi giá trị bằng nhau. Sai bất kỳ ⇒ `fail`
(scope thật sự bị bỏ qua — đúng lớp lỗi `p0-scope-dropped-vn-id` khoá lại).
`suspect` **biến mất khỏi từ vựng** của MR-7.

### 10.4. W9.4 — Bộ đề độc lập về quy trình

◻ Bộ hiện tại: 44 câu, **mọi case mang `author_read_source_code: true`**, dưới
mức 60–100 mà spec đòi. `scripts/build_question_bank.py` tự khai điều này ở
docstring; nó là chặn dưới của thiên lệch, không phải phép đo sạch.

Hợp đồng cho bộ mới (`eval/independent/answerable_external.json`):

| Yêu cầu | Kiểm bằng máy |
| --- | --- |
| 60–100 câu | `len(cases)` |
| `author_read_source_code: false` ở **mọi** case | assert trong test |
| Hai người chú thích độc lập cho `answerable` và `expected_value`; có người phân xử khi lệch | `annotators: [a, b]`, `adjudicated_by` khi lệch |
| Chia `dev` / `holdout`, holdout niêm phong bằng hash | `split: "dev" \| "holdout"`, `holdout_sha256` trong manifest |
| Cân bằng VN/ID, loại câu hỏi, cách diễn đạt | phân phối tối thiểu khai trong manifest |
| Có câu **nêu tên cụ thể** kèm `entity_text` nguyên văn | ≥10 case (mở khoá MR-3) |
| Có câu **cực trị** đáp án tất định | ≥10 case (mở khoá MR-8) |
| Có câu **kết quả rỗng** thật | ≥5 case |

Thêm test `tests/test_question_bank_contract.py` kiểm toàn bộ bảng trên. Người
sửa code **không được xem holdout** trước khi chốt; kiểm bằng cách để holdout
trong một file riêng và chỉ mở ở bước chấm.

Bộ 44 câu hiện tại **giữ nguyên** làm bộ `dev` nội bộ, và mọi con số trích từ nó
phải kèm giới hạn ở `eval/reports/2026-08-27-independent-bank.md` §2.

### 10.5. W9.5 — Corpus topic gate bị nhiễm

✅ `scripts/build_topic_gate.py:73`:

```python
for path in glob.glob(str(REPO / "eval" / "**" / "*.json"), recursive=True):
    if "independent" in path.replace("\\", "/").split("/"):
        continue
```

Loại `eval/independent/`, nhưng **không loại `eval/reports/`** — nơi chứa report
do chính hệ sinh ra. Một phép đo được phép **đọc** corpus; nó **không được phép
trở thành** corpus.

Việc, đúng thứ tự:

1. File mới `eval/topic_gate_corpus.json`:
   ```json
   {"schema_version": "topic-gate-corpus.v1",
    "sources": ["eval/questions.json", "eval/questions_v2.json", "..."],
    "excluded": ["eval/reports/**", "eval/independent/**", "eval/topic_gate.json"],
    "question_count": 0,
    "corpus_sha256": ""}
   ```
2. `corpus()` đọc **danh sách file cố định** từ manifest, không `glob`;
3. `corpus_sha256` = SHA-256 của danh sách câu đã sort; lệch ⇒ script **đỏ**;
4. Report ghi `corpus_sha256` cạnh `topics_hash` / `invariants_hash` /
   `alias_index_hash`;
5. **Rồi mới** trình sáu metric `pending_oracle` để xin ký.

`gate_open` giữ `False` cho tới khi cả sáu metric có oracle của người duyệt. Ký
một oracle dựng trên corpus nhiễm là ký một con số vô nghĩa.

⚠ Ghi chú giữ lại từ chính script: bộ đề sinh từ dữ liệu chỉ route được **34,1%**
so với **69,3%** của suite viết tay. Ngưỡng `MIN_TOPIC_SCOPED_RATE = 0.65` được
hiệu chỉnh trên suite viết tay và **không** áp cho bộ sinh từ dữ liệu; giữ hai
con số tách nhau, đừng trộn vào một ngưỡng không dành cho nó.

### 10.6. W9.6 — Đo lại BGK-20

◻ Con số **4/13** là của 23/08, đo bằng provider `deepseek`. 25 work package
dựng xong 27/08.

✅ **Đã chạy lại offline ngày 28/08** (§1.5): kết quả **4 đúng / 7 từ chối đúng /
9 bỏ lỡ** — trùng khít phân bố 23/08, và ✅ `git diff d14fa75 HEAD -- src/` rỗng
nên điều đó là dự kiến, không phải bất ngờ. Chín ca bỏ lỡ đã được chẩn đoán
từng ca và gắn work package ở bảng §1.5.

**Việc còn lại của W9.6 là chạy bằng provider thật**, vì hai lý do:

1. Phép đo 23/08 dùng `deepseek` với LLM generation BẬT; phép chạy 28/08 dùng
   `offline`. Trùng phân bố **không** chứng minh trùng hành vi — hai ca `bgk04`
   và `bgk06` từng tốn 85,5 s và 115,3 s vì LLM lập plan rồi thua, còn offline
   thì hỏng ngay. Cùng kết cục, hai đường khác nhau.
2. Chỉ đường có provider mới đo được `A6` (ngân sách độ trễ) trên bộ này.

Công cụ có sẵn: `scripts/bgk_run_agent.py` + `scripts/bgk_compare.py` (cần
provider thật, 20 câu). Báo cáo phải là **bảng trước/sau**, và phải tách riêng ca
nào gỡ bởi work package nào theo bản đồ §1.5 — nếu không thì "đã sửa" và "may
mắn" không phân biệt được.

✅ Điều này đã được xác nhận thay vì phỏng đoán: `bgk04` và `bgk06` **vẫn bỏ lỡ**
trên bản chạy 28/08, và §1.5 chỉ ra vì sao — cả hai là cùng một lỗ với `ans035`
(synth ra plan nhưng không có node `Aggregate`), tức **W5**, không phải A5.

### 10.7. W9.7 — Ablation là bằng chứng, phải giữ chạy được

✅ Chạy lại ngày 28/08 (`eval/reports/2026-08-28-risk-coverage-recheck.json`):
L0 ≡ L1 ≡ L2 **trùng khít**, và **trùng khít từng con số với bản 27/08** —
coverage 0.4545, risk 0.0, over_refusal 0.4737, answered 20, wrong 0, AURC
0.0454. Kiểm biến hình cũng vậy: 122/8/174/4, rate 0.9104, **cùng 8 ca hỏng**. Tức tắt A13 và tắt
cả ba vòng lặp rẻ A5 **không đổi một câu nào**.

Đây là bằng chứng dứt điểm cho luận điểm của §5–§8: nút thắt **không phải cổng
gác**, mà là **thiếu khối**. Vì vậy `scripts/run_ablation.py` và
`scripts/run_risk_coverage.py` phải chạy lại sau **mỗi** work package, không đợi
tới cuối; và nếu sau W4–W7 mà L0 ≡ L2 vẫn đúng thì kết luận đó vẫn đứng.

**Không tối ưu A5/A13 cho nhóm 6 ca nghiệp vụ** — ablation đã cho thấy chúng cứu
0 câu.

---

## §11. W10 — Pipeline, cửa publish, và dataset thứ hai

> Phụ thuộc: **W3** (W10.1), **W10.1** (W10.2), **W10.2 + xuất xứ** (W10.3).
> Checklist §0.3 chạm: 1 · 3 · 6 · 7 · 8.

### 11.1. W10.1 — Notebook thành module có test

Hôm nay `data/processed/` là đầu ra của `notebooks/pipeline/data_pipeline.ipynb`
và **không có đường tái dựng bằng lệnh**. Đồng thời `raw_extra_data/` nằm ở gốc
repo mà không có đường nào biến nó thành `data/processed`.

- Module mới `src/gladiators/data/pipeline.py` mang logic làm sạch từ notebook;
- Script mới `scripts/build_processed.py --source data/raw --out data/processed`;
- Notebook giữ lại làm tài liệu, nhưng **gọi module**, không giữ bản sao logic;
- Nghiệm thu: dựng lại `data/processed` từ `data/raw` cho **đúng
  `dataset_version` hiện tại `27de9bff184f4f89`** (§2.5). Khác một bit là một
  thay đổi ngữ nghĩa chưa ai khai.

### 11.2. W10.2 — Cửa publish

Module mới `src/gladiators/data/publish.py`. Mọi bộ dữ liệu muốn vào
`data/processed/` phải qua bốn bước:

| Bước | Nội dung | Hỏng thì |
| -: | --- | --- |
| 1 | `manifest.json`: nguồn, thời điểm export, `sha256` từng file, số dòng | từ chối, không ghi gì |
| 2 | `data/contracts.py::validate_artifacts` (pandera + coverage manifest) | quarantine |
| 3 | Luật chất lượng: cột hằng số, cột toàn null, ngày thiếu trong dải liên tục, tên bảng không khớp grain khai báo | quarantine |
| 4 | `compute_dataset_version` và ghi vào manifest | — |

Trạng thái cách ly: ghi vào `data/quarantine/<dataset_version>/` kèm lý do
typed; **hệ vẫn phục vụ bản cũ**.

✅ `raw_extra_data` cung cấp **bốn ca lỗi thật** — không cần gieo lỗi giả:

| Ca | Bước bắt | Sự thật đo được |
| --- | :-: | --- |
| `products_timeseries` không phải time series | 3 | 1276 dòng / 1276 item / **đúng một dòng mỗi item**; `date` là ngày quan sát cuối, 19 giá trị phân biệt. Join theo tên file là sai |
| `unit_sold` toàn 0 | 3 | 0/1276 khác 0 — cột hằng số |
| `public/test_*.csv` rỗng | 2 | `pandas.read_csv` ném `EmptyDataError` |
| Thiếu **2026-07-12** | 3 | `product_promotions` có 20 ngày trong dải 07-01→07-21; một ngày khuyết giữa dải |

### 11.3. W10.3 — Ghép thành `dataset_version` thứ hai

Bắt buộc, và không có ngoại lệ:

- Bộ mới vào như `dataset_version` **thứ hai**, **không đè** bộ cũ;
- Bảy suite eval **luôn ghim phiên bản đóng băng** `27de9bff184f4f89`;
- Dữ liệu mới đo bằng **bộ đề riêng**, không trộn số với bộ cũ;
- `artifacts/value_index.json` phải có **một bản cho mỗi `dataset_version`**;
  preflight §2.5 sẽ nổ nếu không.

**Vì sao ghép SAU, không ghép TRƯỚC** — đây là chỗ ngược trực giác nhất:

> `answerable_coverage` là *"% câu mà **dữ liệu** trả lời được"*. Thêm 20 ngày
> lịch sử giá và `shop_stats` theo ngày ⇒ bộ đề sinh từ dữ liệu đẻ ra một lớp câu
> hỏi thời gian mới ⇒ **mẫu số tăng** ⇒ hệ chưa trả lời được lớp đó thì
> `over_refusal_rate` **TĂNG**, không giảm.

✅ Và ghép trước còn phá golden ngay: 12 listing hiện có `<2` snapshot, **10 sẽ
có ≥2**; `bnd09` khoá đúng một trong số đó (1 snapshot → 18).

Khi ghép rồi, nó mở đúng hai khía cạnh hiện gần như trống: `A1 TEMPORAL_CHANGE`
có thêm 18 mốc giá, và `T5 SHOP_PROFILE` có một trục thời gian
(`follower_count` đổi ở 20/20 shop).

### 11.4. Xuất xứ — điều kiện chặn

⚠ `raw_extra_data` không có README, không license, không mô tả cách thu thập.
✅ Tên file `<bảng>_<YYYYMMDDHHMM>.csv` và hai schema `datashopee`/`public` cho
thấy đây là dump Postgres, export 2026-08-27 19:24–19:29; `created_at` distinct
= 1 xác nhận một lần backfill.

**W10.3 không được bắt đầu cho tới khi xuất xứ được ghi vào `docs/qa/`**: ai
cấp, thu bằng cách nào, được dùng tới đâu, có được đưa vào bài nộp không. Đây là
một điều kiện đầu vào, không phải một chi tiết hành chính — W10.1 và W10.2 không
bị chặn bởi nó và làm được ngay.

---

## §12. W11 — Predicate làm measure: đếm theo điều kiện và tỷ lệ

> Gỡ: `bgk05`, `bgk11`. Phụ thuộc: contract `requested_aggregation` của
> **W5.1** và decline typed của **W12**; W11.2 phải xong trước gateway W5.3.
> Checklist §0.3 chạm: 1 · 3 · 4 · 5 · 8.
>
> ⚠ **Vì sao work package này suýt không tồn tại:** hai ca nó gỡ **không nằm
> trong** 18 ca từ chối oan của bộ 44 câu (§1.2). Thiết kế chỉ theo bộ đó sẽ bỏ
> chúng lại. Chúng lộ ra khi chạy BGK-20 ở §1.5 — và đó là toàn bộ lý do `W9.4`
> tồn tại.

### 12.1. Hai hình thái của cùng một khoảng trống

✅ Đo trực tiếp:

**`bgk05` — *"Có bao nhiêu listing giảm giá trên 50% tại VN ngày 03/07?"***

```
requested_measures = [("bao nhieu listing", derived.product_count),
                      ("giam gia",          measure.discount_percent)]
synthesize(...)    = None          # vì len(measures) != 1
```

`">50%"` **không bao giờ trở thành predicate**. Câu hỏi có một measure (đếm) và
một **điều kiện** trên một measure khác; parser đọc thành hai measure.
✅ Đáp án đúng: `(vn.discount_percent_num > 50).sum()` = **8**.

**`bgk11` — *"Tỷ lệ listing có giảm giá tại VN ngày 03/07 là bao nhiêu phần trăm?"***

```
find_in("ty le")   = []                                   # không ref nào
requested_measures = [("giam gia", measure.discount_percent)]
synthesize(...)    = synth:measure.discount_percent:median:nogroup:...
```

Từ `"tỷ lệ"` biến mất, và câu còn lại được đọc thành *"mức giảm giá trung vị"*.
**Hai đại lượng khác hẳn nhau, và hôm nay chỉ `A22-ALIGN-MEASURE` chặn được.**
✅ Đáp án đúng: `100 * vn.discount_percent_num.notna().mean()` = **96.26 %**.

Đây là chỗ nguy hiểm nhất trong ba khối còn lại: nếu W5 mở cổng scalar aggregate
mà W11 chưa có, `bgk11` sẽ **có node `Aggregate`**, chạy được, và trả về một con
số trung vị hoàn toàn hợp lệ cho một câu hỏi về tỷ lệ. Alignment vẫn chặn vì
measure không khớp — nhưng nó là lớp cuối, và dựa vào lớp cuối là dựa vào một
lớp không được thiết kế cho việc đó.

> **Ràng buộc thứ tự:** W11 **phải xong cùng hoặc trước** khi `W5.3` mở
> `_synthesis_beats_template` cho scalar aggregate. Hoặc, nếu tách rời, `W5.1`
> phải khai `"ty le"` / `"phan tram"` là **cụm chặn**: gặp chúng mà chưa có
> `derived.*_rate` bind được ⇒ `synthesize` trả `None`.

### 12.2. W11.1 — Điều kiện trên measure thành predicate

#### 12.2.1. Một chuẩn operator từ parser tới compiler

Source hiện tại có ba dialect không khớp nhau:

- `AnalyticalPredicate`: `le/ge/between/isnull`;
- Query IR và catalog: `lte/gte`;
- `MetricConstraint`: `lte/gte` nhưng là một type tự khai khác.

Nếu W11 sinh `ge/le` như bản nháp cũ, synthesizer sẽ từ chối ngay ở
`item.op not in obj.allowed_filters`. Tạo
`src/gladiators/planner/predicate_ops.py` làm nguồn duy nhất:

```python
ExecutablePredicateOp = Literal[
    "eq", "ne", "lt", "lte", "gt", "gte", "in", "contains"
]
ORDERED_OPS = frozenset({"lt", "lte", "gt", "gte"})
LEGACY_ALIASES = {"le": "lte", "ge": "gte"}

def canonicalize_predicate_op(value: str) -> ExecutablePredicateOp: ...
```

`AnalyticalPredicate`, Query IR `Predicate`, catalog `allowed_filters` và
`MetricConstraint` import type/validator này. `le/ge` chỉ được nhận ở biên đọc
payload cũ rồi lưu thành `lte/gte`; không object nội bộ nào được giữ legacy op.
`between` phải được parser tách thành hai predicate `gte` + `lte` trước khi dựng
model. `isnull` chưa có compiler semantics nên bị ghi vào
`unsupported_operators` và fail-closed `A19-OP`, không biến thành `eq None`.
Compiler có một dispatch map exhaustiveness-tested cho toàn bộ
`ExecutablePredicateOp`; thêm operator vào type mà chưa có compiler branch làm
test import/contract nổ.

#### 12.2.2. Nhận dạng phép so sánh

**`src/gladiators/planner/semantic_parser.py`** — bộ nhận dạng so sánh, chạy
**sau** khi `_link()` đã bind measure và **trước** khi chốt `requested_measures`:

```python
# Một measure đứng sau một từ so sánh là ĐIỀU KIỆN, không phải thứ được đo.
# "bao nhiêu listing giảm giá TRÊN 50%" đo số listing; "giảm giá trên 50%" là
# bộ lọc. Để nó ở cả hai chỗ làm request khai hai measure cho một câu hỏi một
# measure, và synthesizer từ chối vì đúng lý do sai.
_COMPARISON = (
    ("tren", "gt"), ("lon hon", "gt"), ("cao hon", "gt"), ("hon", "gt"),
    ("duoi", "lt"), ("nho hon", "lt"), ("thap hon", "lt"),
    ("tu", "gte"), ("it nhat", "gte"), ("toi da", "lte"),
    ("di atas", "gt"), ("di bawah", "lt"),
)
_NUMBER_WITH_UNIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%|phan tram|persen)?")
```

Luật, và cả bốn điều kiện đều bắt buộc:

| # | Điều kiện | Nếu bỏ |
| -: | --- | --- |
| 1 | Có **≥2** measure đã bind, trong đó **đúng một** có `counts_unit` | Câu một measure không có gì để lọc |
| 2 | Measure **không** `counts_unit` đứng liền sau/trước một cụm so sánh và một số | `"giảm giá"` trần bị biến thành bộ lọc `> None` |
| 3 | Toán tử suy ra nằm trong `CATALOG[ref].allowed_filters` | Catalog cấm thì không được lách |
| 4 | Đơn vị của số khớp `CATALOG[ref].unit` (`%` ↔ `percent`) | `"trên 50"` với measure đơn vị VND là một câu hỏi khác |

Đạt ⇒ chuyển measure đó thành `AnalyticalPredicate(field_ref=ref, op=<op>,
value_binding=<số>)`, và `requested_measures` còn đúng một phần tử là metric đếm.

✅ Kết quả mong đợi `bgk05`: plan
`synth:derived.product_count:count:nogroup:none:vn:2026-07-03:norel` với predicate
`measure.discount_percent > 50` ⇒ **8**.

Không đạt bất kỳ điều kiện nào ⇒ **giữ nguyên hành vi hôm nay** (`synthesize`
trả `None` ⇒ `A19-PLAN`). Guard một chiều, như `_has_unbound_qualifier`.

### 12.3. W11.2 — Tỷ lệ là một metric, không phải một cách diễn đạt

Không suy `"tỷ lệ"` thành một phép chia ở runtime. Một tỷ lệ cần **mẫu số được
khai**, và mẫu số là một quyết định nghiệp vụ: *"tỷ lệ listing có giảm giá"* có
mẫu số là toàn bộ listing của scope, không phải listing có dữ liệu giảm giá.

Không thêm `numerator_ref`/`denominator_ref` tuỳ ý vào lời gọi `MetricSpec`:
dataclass hiện tại không có hai field đó, và compiler `share` hiện chỉ làm
`AVG(CAST(column AS DOUBLE))`, nên bản nháp ấy không thể tạo ba giá trị
tử số–mẫu số–tỷ lệ. Thay bằng một hợp đồng dùng lại được cho mọi conditional
share:

```python
@dataclass(frozen=True)
class ShareDefinition:
    condition_ref: str
    condition_op: ExecutablePredicateOp
    condition_value: object
    numerator_metric: str
    denominator_metric: str
    scale: Literal[1, 100]
    null_policy: Literal["false", "exclude"]

@dataclass(frozen=True)
class MetricSpec:
    # các field hiện có giữ nguyên
    ...
    share: ShareDefinition | None = None
```

Validator registry bắt buộc: `share is not None` khi và chỉ khi
`"share" in valid_aggregations`; condition ref có physical và cho phép operator;
hai metric tử/mẫu tồn tại; denominator là count metric cùng grain/dedupe; scale
khớp unit (`percent` ⇒ 100, `share_0_1` ⇒ 1); đồ thị source metric không có cycle.

Sửa metric `has_promo` đang có để dùng quan sát đã materialize:

```python
MetricSpec(
    name="has_promo", grain="snapshot", unit="bool",
    dedupe="one_snapshot_per_listing",
    source_columns=("has_displayed_discount",),
    formula="has_displayed_discount; null theo null_policy của consumer",
    ...,
)
```

và thêm `_DERIVED_PHYSICAL["has_promo"] =
("product_snapshot_metrics.csv.has_displayed_discount",)`. Không suy lại cờ từ
text/discount tại query time.

Khai đủ hai metric mới bằng toàn bộ field bắt buộc của `MetricSpec`:

```python
MetricSpec(
    name="discounted_listing_count", grain="group", unit="listings",
    dedupe="one_snapshot_per_listing", traps=(),
    source_columns=("product_listing_key",), source_metrics=("has_promo",),
    valid_aggregations=("count",), owner="data-engineering",
    tags=("group", "count", "discount"),
    formula="count distinct listing where has_promo=True",
    caveats=("Đếm cờ giảm giá hiển thị tại đúng một snapshot.",),
),
MetricSpec(
    name="discounted_listing_rate", grain="group", unit="percent",
    dedupe="one_snapshot_per_listing", traps=(),
    source_metrics=("discounted_listing_count", "product_count"),
    valid_aggregations=("share",), owner="data-owner",
    tags=("group", "share", "discount"),
    formula="100 * discounted_listing_count / product_count",
    share=ShareDefinition(
        condition_ref="derived.has_promo", condition_op="eq",
        condition_value=True,
        numerator_metric="discounted_listing_count",
        denominator_metric="product_count",
        scale=100, null_policy="false",
    ),
    caveats=("Mẫu số là toàn bộ listing trong scope; cờ giảm giá null được tính là không có cờ.",),
),
```

`_COUNTS_UNIT["discounted_listing_count"] = "entity.product_listing"`.
Alias `"tỷ lệ listing có giảm giá"`, `"phần trăm listing giảm giá"` bind ref
`derived.discounted_listing_rate`.

Khi alias rate được bind, parser đặt `requested_aggregation="share"` theo định
nghĩa metric (không phải vì gặp từ `"tỷ lệ"` trần). Digest/alignment ở §6.3 phải
thấy cùng giá trị; evidence tỷ lệ cũng ghi `aggregation="share"`.

`AliasIndex` phải khớp **cả cụm**, không khớp `"tỷ lệ"` trần: `"tỷ lệ"` một mình
không nói mẫu số là gì, và một tỷ lệ không có mẫu số khai báo là đúng thứ
`INV-PROXY-NOT-VERIFIED-SALES` và `_lineage_gaps` tồn tại để chặn.

#### 12.3.1. Plan, compiler và schema kết quả

Synthesizer thấy metric có `ShareDefinition` phải:

1. mở closure `needed`: bỏ rate ref không có physical, thêm `condition_ref` và
   counting key của denominator; chọn source phủ closure đó;
2. phát đúng một node `Aggregate(aggregation="share",
   refs=("derived.discounted_listing_rate",))`;
3. khai `expected_schema` gồm các dimension trước (nếu có), rồi đúng thứ tự
   `discounted_listing_count`, `product_count`, `discounted_listing_rate`;
4. thêm `condition_ref` và counting key vào `scan_refs`, nhưng không project
   chúng ra output cuối.

Validator mở closure từ `MetricSpec.share` và đòi schema đúng ba ref trên; plan
không được tự thay numerator/denominator. Compiler không dùng branch theo tên
`discounted_listing_rate`, mà dùng `ShareDefinition` tổng quát. Nó tạo AST hai
tầng:

- tầng aggregate: `COUNT(DISTINCT CASE WHEN <condition> THEN
  product_listing_key END)` và `COUNT(DISTINCT product_listing_key)`;
- tầng project: giữ hai count và tính
  `CASE WHEN denominator = 0 THEN NULL ELSE scale * numerator / denominator END`.

Condition đi qua cùng predicate compiler và parameter binding với Filter. Với
`null_policy="false"`, null không vào numerator nhưng vẫn vào denominator. Mọi
expression dựng bằng SQLGlot AST; không nhận raw SQL/formula string. Alias output
lấy từ `expected_schema`, nên Rank/Project phía sau chỉ đọc alias của node input,
không gọi `_column_for` trên một aggregate đã materialize.

Nếu denominator bằng 0, hai count vẫn có thể vào trace nhưng không tạo numeric
rate evidence; workflow fail-closed `A-NO-EVIDENCE`, không trả `0%`.

#### 12.3.2. Evidence và lineage

**Lineage bắt buộc.** `verifier._lineage_gaps` dựng `MetricGraph` từ 33 metric;
`discounted_listing_rate` là derived nên nó **phải** có evidence tổ tiên. Evidence
sinh ra ba mục theo thứ tự tử số, mẫu số, tỷ lệ. Evidence tỷ lệ có
`derivation_op="share"`, `scale=100` và
`parent_evidence_ids=(numerator_evidence_id, denominator_evidence_id)`; cả ba
cùng country, snapshot, dataset version và source tier. `source_path` là semantic
ref, không phải tên cột.

`MetricGraph` kiểm dependency tĩnh của metric; verifier kiểm cạnh động giữa các
evidence instance: parent tồn tại, không tự tham chiếu/trùng ID, đúng hai metric
tử/mẫu mà `ShareDefinition` khai, cùng scope/version/tier. Consistency thêm luật
`abs(rate - scale*numerator/denominator) <= 1e-9` trên giá trị chưa làm tròn và
luật `0 <= numerator <= denominator`; renderer mới làm tròn **96.26%** và nêu
`643/668`, không làm tròn trước verifier.

✅ Kết quả mong đợi `bgk11`: **96.26 %**, kèm tử số **643** và mẫu số **668**.

### 12.4. Nghiệm thu W11

| Ca | Kỳ vọng |
| --- | ---: |
| `bgk05` | `allow` · **8**; plan có predicate `measure.discount_percent > 50` |
| `bgk11` | `allow` · **96.26 %**; ba evidence tử/mẫu/tỷ lệ, lineage đủ |
| *"Giảm giá trung vị tại VN 03/07"* (không có `"tỷ lệ"`) | vẫn ra **median discount**, không bị W11 cướp |
| *"Tỷ lệ"* trần, không nêu mẫu số | `clarify` — không đoán mẫu số |
| `"trên 50"` với measure đơn vị VND | **không** áp W11.1 (điều kiện 4) |
| `risk` · `over_answer_rate` | **0.0 · 0.0** |
| `synthesizer_equivalence_baseline.json` | ⚠ phải đo lại: `dr2607` có câu chứa cụm so sánh; entry nào đổi phải khai lý do contract |

Dòng cuối là ⚠ **chưa đo** — khác với W4/W6 (đã đo, 0 entry đổi) và W5 (đã đo,
2 entry đổi có tên). W11 chạm bộ nhận dạng measure nên blast radius phải được đo
**trước** khi viết code, bằng đúng script ở §21.9.

---

## §13. W12 — Từ "câu nào hỏng" tới "chỗ nào hỏng"

> Gỡ: **không ca nào**. Nó là thứ làm cho mười một work package kia **kiểm được
> bằng máy** thay vì bằng một phiên đọc code.
> Phụ thuộc: không. Nên làm **sớm**, vì nó rẻ hơn mọi lần chẩn đoán tay sau đó.
> Checklist §0.3 chạm: 3 · 4 · 8.

### 13.1. Vấn đề: lời từ chối nêu chặng hỏng CUỐI, không nêu chặng chưa bao giờ chạy

Mọi bảng chẩn đoán ở §1.2 và §1.5 là **kết quả của một phiên đọc code bằng tay**.
Chúng là ảnh chụp, không phải cơ chế. Ca thứ 20 hỏng thì người tiếp theo phải làm
lại đúng công việc đó.

✅ Ba ca, chạy thật, cho thấy hệ tự nói được bao nhiêu:

| Ca | `rule_id` | `reason` hệ trả về | Nguyên nhân THẬT |
| --- | --- | --- | --- |
| `ans035` | `A19-PLAN` | *"Không có semantic planner provider cho câu hỏi ngoài certified template."* | `_synthesis_beats_template` trả `False` ⇒ **synthesizer chưa bao giờ được thử**. Có provider cũng không sửa được gì |
| `ans019` | `A22-ALIGN-DATE` | *"Evidence chỉ phủ 03/07→03/07 thay vì 01/07→03/07"* | Đúng triệu chứng, nhưng không nói template `listing_count` **ghim cứng** 2026-07-03. Và `planning.alignment` ghi `{"aligned": true, "issues": []}` — **mâu thuẫn với chính `rule_id`**, vì verdict chặn nằm ở khoá `evidence_alignment` |
| `ans028` | `A19-CAT` | *"Chưa xác định được chỉ số nào cần đo từ câu hỏi."* | Đúng chặng, nhưng không nói **surface nào** không bind được (`"brand"`) |

Ca `ans035` là lớp lỗi tệ nhất: lời từ chối **chỉ sai đường**. Người đọc trace sẽ
đi mua một provider. Đây đúng thứ mà comment ở `gate.py:292` gọi tên — *"một lời
từ chối mô tả sai bản chất khiến người dùng diễn đạt lại và nhận đúng lời từ chối
đó"* — chỉ khác là ở đây nạn nhân là người **sửa hệ**, không phải người dùng.

### 13.2. Đo được: 20 lối từ chối im lặng trong một hàm

✅ `synthesize()` và `_plan_relations()` có **20 lệnh `return None`**, mỗi cái là
một lý do khác nhau, và **không cái nào để lại dấu vết**:

| Dòng | Điều kiện | Nghĩa |
| ---: | --- | --- |
| 176 | `sources and source not in sources` | base artifact không phủ được scope ref |
| 194 | `entity is None` | artifact không có entity tương ứng |
| 199 | `path is None or len(path) != 1` | đồ thị quan hệ không còn hình sao |
| 202 | `source not in RELATION_LEFT_SOURCES[...]` | relation không nhận base này làm vế trái |
| 207 | `len(chosen) > RELATION_EDGE_BUDGET` | quá 3 nan hoa |
| 213 | `temporal_validity == static_latest_only` + nhiều ngày | enrichment tĩnh bị dùng như panel |
| 259 | `not allowed` | catalog không chứng nhận phép tổng hợp nào |
| 270 | `not country` | thiếu scope thị trường |
| 272 | `_has_unbound_qualifier(request)` | câu có điều kiện chưa bind được |
| 276 | `len(measures) != 1` | **0 hoặc ≥2 measure** — lối của `bgk05` |
| 279 | `measure_ref not in CATALOG` | ref lạ |
| 281 | `answerability in {absent, context_only}` | ref không được phép đo |
| 291 | `len(dimensions) > MAX_DIMENSIONS` | quá 2 chiều |
| 295 | `len(extra) > MAX_EXTRA_PREDICATES` | quá 2 predicate |
| 299 | `aggregation is None` | lối của `W5.1` |
| 305 | `len(dates) != 1` | lối `W6` mở ra cho 2 mốc |
| 315 | `plan_edges is None` | quan hệ không lập được |
| 321 | `ranking.order_by != measure_ref` | xếp hạng theo thứ không đo |
| 351 | `item.op not in obj.allowed_filters` | catalog cấm toán tử lọc đó |
| 399 | `len(policies) > 1` | hai chiến lược dedupe trong một plan |

Cộng với `_synthesis_beats_template` — được gọi ở `workflow.py:1226` và
`open_planner.py:202`, ✅ **cả hai đều không ghi kết quả** — thì một ca nhận
`A19-PLAN` có **ít nhất 21 nguyên nhân khả dĩ**, và trace thu hẹp được **0**.

### 13.3. W12.1 — Lý do từ chối có kiểu, truyền qua tham số ra

Không đổi kiểu trả về của `synthesize` — 58 plan đang bị khoá và mọi caller sẽ
phải sửa. Dùng **tham số ra tuỳ chọn**, đúng khuôn additive của `plan_provenance`
và `window` ở các work package trước:

```python
# planner/synthesizer.py
DeclineCode = Literal[
    "scope_ref_off_base", "no_entity_for_artifact", "relation_path_not_single_edge",
    "relation_left_source_mismatch", "relation_budget_exceeded", "temporal_validity",
    "no_certified_aggregation", "country_missing", "unbound_qualifier",
    "measure_count_not_one", "measure_not_in_catalog", "measure_not_answerable",
    "too_many_dimensions", "too_many_predicates", "aggregation_not_certified",
    "date_count_unsupported", "relation_plan_failed", "ranking_ref_mismatch",
    "filter_op_forbidden", "dedupe_policy_conflict",
]

def synthesize(request, country, *, decline: list[DeclineCode] | None = None):
    """``decline`` là tham số RA tuỳ chọn: mỗi lối ``return None`` ghi tên nó
    vào đây trước khi trả về.

    Không đổi kiểu trả về, vì 58 plan đang bị khoá bởi
    test_synthesizer_equivalence và mọi caller sẽ phải sửa. Caller không truyền
    ``decline`` nhận hành vi y hệt hôm nay -- đó là điều kiện để W12 vào được
    trước W4-W11 mà không đụng vào chúng.
    """
```

Mỗi `return None` thành hai dòng: `_decline(decline, "<code>")` rồi `return None`.
`_plan_relations(..., decline=decline)` nhận và ghi vào cùng collector của
`synthesize`; không tạo list con rồi làm mất lý do.

Test AST không chỉ so số lượng — hai danh sách cùng dài vẫn có thể đặt nhầm code
hoặc quên một return và lặp code ở return khác. Với mọi `Return(value=None)`
trong đúng hai hàm:

1. statement liền trước trong cùng block phải là `_decline(decline,
   <string-literal>)`;
2. literal thuộc `DeclineCode`;
3. tập literal quan sát được bằng **đúng** tập `DeclineCode` (không thiếu, không
   thừa, không trùng cho 20 lý do hiện tại).

Đếm/trích bằng `ast`, không regex. Thêm một lối thoát mà quên đặt tên, hoặc đổi
điều kiện nhưng giữ code sai chỗ, đều làm test đỏ.

### 13.4. W12.2 — `planning.attempts`: cái gì đã thử, và từ chối vì sao

Lý do typed phải sống sót qua exception boundary. Mở rộng hai exception:

```python
class OpenPlannerError(ValueError):
    rule_id: str = "A19-PLAN"
    decline_codes: tuple[DeclineCode, ...] = ()
    attempts: tuple[PlanningAttempt, ...] = ()
    # issues/context_relax hiện có giữ nguyên

class AnalyticalPlanError(ValueError):
    rule_id: str = "A19-PLAN"
    decline_codes: tuple[DeclineCode, ...] = ()
    attempts: tuple[PlanningAttempt, ...] = ()
```

`OpenAnalyticalPlanner.plan` truyền collector vào synthesizer và gắn nó vào lỗi
nếu các nhánh sau cũng không thắng. Bảng ánh xạ tập trung
`DECLINE_RULE_BY_CODE` đặt `aggregation_not_certified -> A19-AGGREGATION`; các
code chưa có rule chuyên biệt dùng `A19-PLAN`. Nếu có nhiều code, chọn rule theo
một priority tuple được test, không theo thứ tự tình cờ của nhánh.

Ở `workflow.py`, khi đổi `OpenPlannerError` sang `AnalyticalPlanError`, copy
`rule_id`, `decline_codes`, `attempts`, `context_relax`; catch cuối dựng
`GateDecision(rule_id=exc.rule_id)` và ghi cùng rule vào `planning.a19_rule`.
Đường `analytical_query` gọi synthesizer trực tiếp cũng áp dụng y hệt: một
`aggregation_not_certified` do yêu cầu aggregate tường minh phải chặn fallback
template, vì template sẽ bỏ aggregate trong im lặng.

`agent/workflow.py` — thay vì chỉ ghi chặng cuối, ghi **cả chuỗi**:

```python
planning_meta["attempts"] = [
    {"branch": "synthesizer", "tried": True,  "declined": ["measure_count_not_one"]},
    {"branch": "template",    "tried": True,  "declined": ["no_template_for_shape"]},
    {"branch": "llm_ir",      "tried": False, "declined": ["no_provider"]},
]
```

Ba luật, mỗi cái chặn một cách đọc sai:

| Luật | Chặn |
| --- | --- |
| `tried=False` phải kèm lý do **vì sao không thử** | `ans035` hôm nay: nhánh không chạy trông giống nhánh chạy rồi thua |
| Ghi **mọi** nhánh, kể cả nhánh thắng | Không có mẫu số thì không biết nhánh nào đang gánh việc |
| `_synthesis_beats_template` ghi cả `True` lẫn `False` | `CLAUDE.md` §5.1.3 — nhánh không đếm được số lần bắn thì "đã đo" và "đã chạy" không phân biệt được |

Và sửa mâu thuẫn đã đo ở §13.1: `planning.alignment` với
`planning.evidence_alignment` phải **không thể** cùng lúc nói `aligned: true`
trong khi `gate.rule_id` là `A22-*`. Test: với mọi ca `A22-*`, tồn tại ít nhất
một khoá alignment có `aligned: false`.

### 13.5. W12.3 — `scripts/diagnose_refusals.py`

Đây là thứ **thay thế phiên đọc code bằng tay** đã sinh ra §1.2 và §1.5:

```
PYTHONPATH=src python scripts/diagnose_refusals.py \
  --suite eval/independent/answerable_manual.json --provider offline
```

Với mỗi ca **`answerable=true` mà bị từ chối**, in một dòng:

```
ca      | action  | rule_id        | chặng chặn  | mã từ chối               | nhánh đã thử
ans035  | abstain | A19-PLAN       | planner     | beats_template=False     | synthesizer:KHÔNG THỬ
ans031  | abstain | A19-PLAN       | risk        | escalation_blocked:critic | synthesizer:OK
ans028  | clarify | A19-CAT        | gate        | a19_admission            | —
ans019  | clarify | A22-ALIGN-DATE | alignment   | date_range_narrowed      | template:listing_count
```

Rồi gộp theo `(chặng, mã)` và in bảng đếm. **Bảng đó chính là §1.2, sinh tự
động.** Ràng buộc thiết kế: script chỉ đọc `AgentResponse`, **không import**
`planner`/`domain` — nếu nó phải đọc internal để giải thích thì internal chưa
lộ đủ, và đó là lỗi của W12.1/W12.2 chứ không phải của script.

### 13.6. Nghiệm thu W12

| Điều kiện | Kỳ vọng |
| --- | --- |
| AST obligation cho mọi `return None` | statement trước là `_decline`; tập code đúng bằng `DeclineCode`, không trùng/thiếu |
| Aggregate tường minh nhưng catalog không cho phép | `A19-AGGREGATION`; `decline_codes` còn `aggregation_not_certified` qua mọi exception boundary |
| `ans035` | `attempts` ghi `synthesizer tried=False, reason=beats_template` |
| `ans031` | `attempts` ghi `synthesizer tried=True` **và** chặng chặn là `risk`, không phải `planner` |
| Mọi ca `A22-*` | ít nhất một khoá alignment có `aligned: false` |
| `diagnose_refusals.py` trên bộ 44 | sinh ra bảng **trùng khớp §1.2**, không cần đọc source |
| Hành vi runtime | **không đổi một ca nào** — W12 chỉ thêm quan sát |
| `synthesizer_equivalence_baseline.json` | **0 entry đổi** |

Dòng cuối là điều kiện đủ để W12 đi trước mọi work package khác: nó không được
đổi một quyết định nào, chỉ được nói rõ hơn về quyết định đã có.

---

## §14. W13 — Plan phải sinh ra đúng cột nó đã khai; và không exception nào được thoát `run()`

> Gỡ: ✅ 24/84 câu xếp hạng đang trả **HTTP 500** (§1.6.3).
> Chặn: **W5.3**, **W7**, **W11** — cả ba mở rộng tập plan tất định *thật sự
> được thực thi*, nên mỗi cái đều làm lớp lỗi này lộ ra rộng hơn.
> Phụ thuộc: không. **Làm trước W5, W7, W11.**
> Checklist §0.3 chạm: 2 · 3 · 4 · 5.

### 14.1. Sự thật — ba lớp cùng bỏ sót một điều

✅ Plan sinh cho *"Listing nào có điểm đánh giá thấp nhất tại Indonesia?"*:

```
plan_id       synth:measure.rating:median:nogroup:asc:id:2026-07-03:norel:1.1
nodes         n1 Scan -> n2 Filter -> n5 Rank            (output_node = n5)
n5.expected_schema   [product_name (dim.product_name), rating (measure.rating)]
SQL sinh ra   SELECT * FROM (SELECT * FROM (SELECT * FROM products) AS q_n2
                             WHERE country_code = ? AND date = ?) AS q_n5
              ORDER BY rating_num ASC LIMIT 2
frame.columns 80 cột của products_clean
expected      ('product_name', 'rating')
```

Ba lớp, mỗi lớp làm đúng phần của nó, và không lớp nào bắt được:

| Lớp | Kiểm cái gì | Vì sao lọt |
| --- | --- | --- |
| `planner/validator.py:109` | `nodes[output_node].expected_schema == plan.requested_output_shape` | node **khai** đúng schema; sai nằm ở chỗ nó không **tạo ra** schema đó |
| `planner/compiler.py:287` `Rank` | render `SELECT * … ORDER BY … LIMIT n+1` | `Rank` là toán tử **đi xuyên**; nó không chiếu cột |
| `planner/executor.py:151` | `tuple(frame.columns) != query.expected_columns` | bắt được — nhưng bằng cách **ném exception**, và không ai bắt exception đó |

✅ Trong compiler hiện tại chỉ **`Aggregate`, `Project`, `Join`** dựng danh sách
cột tường minh. **`Scan`, `Filter`, `Dedupe`, `Rank`, `DeriveMetric`,
`TemporalCompare`, `Union`** đều đi xuyên bằng `SELECT *`. Vì vậy luật thật sự là:

> Một plan mà `output_node` là toán tử đi xuyên, và tổ tiên vật chất hoá gần
> nhất của nó là `Scan`, **luôn luôn** vi phạm hợp đồng output của chính nó.

### 14.2. Vì sao không suite nào thấy

✅ Ba lý do độc lập, và cả ba đều là bài học về hình dạng bộ kiểm:

1. **Fixture P0 khoá đúng cách diễn đạt không bắn.** `p0-rank-direction-inverted`
   dùng *"**Sản phẩm** nào có giá thấp nhất tại VN?"*. `"sản phẩm"` bind
   `dim.product_name` như một **dimension**, nên plan thành
   `Scan→Filter→Aggregate→Rank` — có `Aggregate`, có chiếu cột, chạy được.
   `"Listing nào"` và `"Mặt hàng nào"` không bind dimension nào ⇒
   `Scan→Filter→Rank`.
2. **Hình plan hỏng đã nằm sẵn trong baseline bị khoá.** ✅ 5 trong 58 plan của
   `tests/fixtures/synthesizer_equivalence_baseline.json` mang đúng hình
   `Scan→Filter→Rank` (`questions_v2:v2q01` `v2q02` `v2q03`,
   `semantic_linking:sl01` `sl08`). Chúng **không nổ** vì cả năm đều xếp hạng
   *giảm dần*, mà `_synthesis_beats_template` chỉ ưu tiên synthesizer khi
   *tăng dần* — nên runtime dùng template và plan synth không bao giờ được chạy.
   `test_existing_plans_are_unchanged` so `model_dump_json()` của plan và
   **không bao giờ compile hay chạy nó**.
3. **Nhánh làm lộ lỗi được thêm để sửa một lỗi khác.** Docstring
   `open_planner.py:70-79` ghi: *"ascending ranking — every template ranks
   descending, so 'giá thấp nhất' came back as 3.033.180 instead of 1.000"*.
   Nhánh đó đúng; nó chỉ đưa một hình plan chưa từng chạy vào đường chạy.

### 14.3. W13.1 — Compiler chiếu hợp đồng output ở biên plan

`planner/compiler.py`. Thêm cạnh `_compile_node`:

```python
# Chỉ ba toán tử này dựng danh sách cột; phần còn lại đi xuyên bằng SELECT *.
# Danh sách là dữ liệu chứ không phải trí nhớ của người đọc code: thêm một
# toán tử vật chất hoá mà quên cập nhật ở đây làm phép chiếu cuối chọn sai biên.
_MATERIALIZING_OPS = frozenset({"Scan", "Aggregate", "Project", "Union", "Join"})

RANK_KEY_ALIAS = "__rank_key__"


def _exposed_name(ref: str, node: PlanNode, nodes: dict[str, PlanNode]) -> str:
    """Tên cột mà sub-query của ``node`` THẬT SỰ phơi ra cho ``ref``.

    Đi ngược theo ``inputs[0]`` tới toán tử vật chất hoá gần nhất. Tới ``Scan``
    thì tên là cột vật lý; tới ``Aggregate``/``Project``/``Union``/``Join`` thì
    tên là alias mà node đó đã khai. Đoán một trong hai là sai một nửa số plan.
    """
    current, seen = node, set()
    while current.node_id not in seen:
        seen.add(current.node_id)
        if current.op in _MATERIALIZING_OPS:
            if current.op == "Scan":
                return _column_for(ref, current.source)
            for field in current.expected_schema:
                if field.semantic_ref == ref:
                    return field.name
            return _column_for(ref, _source_hint(current, nodes))
        if not current.inputs or current.inputs[0] not in nodes:
            break
        current = nodes[current.inputs[0]]
    return _column_for(ref, _source_hint(node, nodes))


def _project_output_contract(expression, plan, nodes, rank_state):
    """Chiếu đúng các cột plan đã KHAI, ở đúng biên của plan.

    Phát ra KHÔNG ĐIỀU KIỆN. Một nhánh "chỉ chiếu khi cần" là một nhánh ai đó
    sẽ quên khi thêm toán tử thứ mười ba; chiếu luôn làm hợp đồng đúng *theo
    cấu trúc*. Khi biên đã đúng tên, câu chiếu là `"x" AS "x"` — vô hại.
    """
    output = nodes[plan.output_node]
    fields = []
    for field in plan.requested_output_shape:
        if not field.semantic_ref:
            raise CompilationError("requested_output_shape thiếu semantic_ref")
        fields.append(exp.alias_(
            exp.column(_exposed_name(field.semantic_ref, output, nodes)),
            field.name, quoted=True,
        ))
    if rank_state.get("column"):
        # Khoá xếp hạng phải sống sót qua phép chiếu, nếu không tie detector của
        # executor bị mù và một kết quả HOÀ ở mép cắt đi ra như một câu trả lời
        # chắc chắn. Đây là hồi quy đã đo được ở bản thiếu nhánh này.
        rank_ref = rank_state.get("ref")
        exposed = (_exposed_name(rank_ref, output, nodes) if rank_ref
                   else rank_state["column"])
        fields.append(exp.alias_(exp.column(exposed), RANK_KEY_ALIAS, quoted=True))
        rank_state["column"] = RANK_KEY_ALIAS
    return exp.select(*fields).from_(expression.subquery("q_out"))
```

Nhánh `Rank` (`compiler.py:287-303`) ghi thêm **một** dòng cạnh
`rank_state["column"] = column`:

```python
rank_state["ref"] = node.rank_by      # ref semantic, không phải tên cột vật lý
```

Lý do dòng này bắt buộc: ✅ ở đường template `analytical:highest_price_listing`,
`rank_state["column"]` là `price_num`, còn `output_node` là một `Project` phơi
ra `price`. Chiếu theo tên vật lý ở biên đó cho `BinderException: Referenced
column "price_num" not found` — đã đo được ở bản thiếu dòng này, trên 4/84 câu.

`compile_plan` (`compiler.py:388`) đổi đúng một dòng:

```python
expression = _project_output_contract(compiled[plan.output_node], plan, nodes, rank_state)
_assert_select_only(expression)
```

**Ba thứ cố ý KHÔNG đổi:**

| Không đổi | Vì sao |
| --- | --- |
| `CompiledQuery.expected_columns` | vẫn là `plan.requested_output_shape`; nó là *hợp đồng*, và hợp đồng không được đổi theo cách thi hành |
| `plan_hash` | băm từ `plan.model_dump_json()`, không từ SQL ⇒ **khoá `PlanResultCache` không dịch chuyển**, `(plan_hash, dataset_version)` giữ nguyên nghĩa |
| `LogicalQueryPlan` và synthesizer | thêm một node `Project` ở synthesizer sẽ đổi **cả 58 plan** trong baseline bị khoá (§0.4). Sửa ở compiler thì baseline **0 entry đổi** |

### 14.4. W13.2 — Executor bỏ khoá xếp hạng trước khi so hợp đồng

`planner/executor.py`, ngay **sau** khối tie detection và **trước** phép so
`tuple(frame.columns) != query.expected_columns`:

```python
frame = frame.iloc[: query.rank_limit].reset_index(drop=True)
if RANK_KEY_ALIAS in frame.columns and RANK_KEY_ALIAS not in query.expected_columns:
    # Cột kỹ thuật, không thuộc hợp đồng. Bỏ SAU tie detection: bỏ trước là
    # lấy đi đúng thứ vừa được mang theo để phát hiện hoà.
    frame = frame.drop(columns=[RANK_KEY_ALIAS])
```

Thứ tự này là bắt buộc, không phải sở thích: tie detection đọc
`frame.iloc[rank_limit][rank_column]`, và `rank_column` giờ là `RANK_KEY_ALIAS`.

### 14.5. W13.3 — Không exception nào được thoát `run()`

Phần này **độc lập với W13.1/W13.2** và phải làm kể cả khi hai mục trên đã xong:
chúng sửa *một* nguyên nhân, mục này sửa *lớp hậu quả*.

`agent/workflow.py`, bọc lời gọi `dispatch`:

```python
with timer.stage("execute"):
    try:
        dispatch(tool_plan, ctx)
    except (ExecutionFailure, CompilationError, duckdb.Error) as exc:
        # Fail-closed (bất biến #6): một plan không chạy được là một lời TỪ
        # CHỐI, không phải một traceback. Bắt ba lớp CÓ KIỂU, không bắt
        # `Exception`: nuốt mọi thứ biến một lỗi lập trình thành một lời từ
        # chối trông bình thường, và đó là cách một hồi quy sống sót qua CI.
        decision = GateDecision(
            action="abstain", rule_id="A19-EXECUTION",
            reason="Kế hoạch không chạy được trên dữ liệu hiện tại.",
            answerable_alternative="Hãy hỏi lại với phạm vi hẹp hơn, hoặc hỏi "
                                   "một chỉ số khác.",
        )
        ctx.evidence, evidence, tool_plan = [], [], ()
        planning_meta.update(
            outcome="execution_failed",
            execution_error={
                "type": type(exc).__name__,
                "code": getattr(getattr(exc, "issue", None), "code", None),
                "message_key": getattr(getattr(exc, "issue", None), "message_key", None),
                "details": dict(getattr(getattr(exc, "issue", None), "details", {}) or {}),
            },
        )
```

Ba ràng buộc:

- **Không Evidence nào được đi tiếp.** Một plan hỏng giữa chừng có thể đã ghi
  Evidence một phần; trả nó ra là trả một phần câu trả lời không ai kiểm.
- **`execution_error` phải mang `code` và `details` có kiểu**, không phải
  `str(exc)`. `scripts/diagnose_refusals.py` (§13.5) đọc nó; một chuỗi tự do ở
  đây làm W12 mất đúng lớp chẩn đoán nó tồn tại để cung cấp.
- **Khoá đếm bắt buộc** (checklist §0.3 ô 4): số lần `execution_error` thật sự
  bắn phải đếm được. Nếu W13.1 đúng thì con số này là **0** trên mọi suite — và
  một số 0 *đo được* khác hẳn một nhánh không ai biết có chạy hay không.

`A19-EXECUTION` vào bảng rule ở §17.1.

### 14.6. W13.4 — Lớp test còn thiếu: plan bị khoá phải **compile và chạy được**

`tests/test_plan_executes_its_contract.py` (**mới**). Đây là phép kiểm mà nếu
tồn tại từ đầu thì cả lớp lỗi này không ra tới runtime:

```python
@pytest.mark.parametrize("key", sorted(k for k, v in BASELINE.items()
                                       if isinstance(v, dict) and "exc" not in v))
def test_locked_plan_produces_the_columns_it_declares(key):
    """58 plan bị khoá không chỉ phải GIỮ NGUYÊN — chúng phải CHẠY ĐƯỢC.

    `test_existing_plans_are_unchanged` so model_dump_json và không bao giờ
    compile. Vì vậy 5/58 plan mang hình Scan->Filter->Rank sống trong baseline
    như một hợp đồng đã duyệt, trong khi chúng không thể thoả hợp đồng output
    của chính chúng.
    """
    plan = _plan_from(BASELINE[key])
    compiled = compile_plan(plan)
    frame = QueryExecutor(repo).execute(compiled).frame
    assert tuple(frame.columns) == compiled.expected_columns
```

Và một test hành vi **qua runtime** (checklist ô 3), không gọi hàm cô lập:

```python
@pytest.mark.parametrize("question", RANKING_SWEEP)   # 84 câu ở §21.14
def test_ranking_question_never_raises(question):
    response = runtime.run(question)          # không try/except: raise = fail
    assert response.gate.action in {"allow", "clarify", "abstain"}
```

### 14.7. W13.5 — Lời từ chối hoà phải nói đúng chiều đã hỏi

✅ `workflow.py:1493` ghi cứng *"Nhiều nhóm cùng đạt giá trị **cao nhất**"*, kể
cả khi câu hỏi là *"điểm đánh giá **thấp nhất**"* — đã đo được trên
*"Sản phẩm nào có điểm đánh giá thấp nhất tại Việt Nam?"*.

Lấy chiều từ node `Rank` của `logical_plan` (`node.descending`), không từ chuỗi
câu hỏi:

```python
superlative = "cao nhất" if rank_descending else "thấp nhất"
```

Không chèn chữ số vào message (`CLAUDE.md` §3.1).

### 14.8. Nghiệm thu W13

✅ **Đã đo bằng bản vá tạm** theo thủ tục §21.13 — con số dưới là kết quả chạy
thật, không phải dự phóng:

| Phép đo | Trước | Sau |
| --- | ---: | ---: |
| Quét xếp hạng 84 câu · `CRASH` | **24** | **0** |
| `POST /ask` *"Listing nào có giá thấp nhất tại Việt Nam?"* | `500` | `200` · `allow` · **1 000 VND** |
| `pytest -q` | 1207 passed, 1 skipped | **1207 passed, 1 skipped** |
| `synthesizer_equivalence_baseline.json` | — | **0 entry đổi** |
| Bộ 44 câu · lệch | 19 | **19** — W13 không tự gỡ ca nào, đúng như thiết kế |
| `questions_multiturn` · lượt lệch | 6 | **6** |

Ràng buộc luôn kèm: `risk = 0.0` · `over_answer_rate = 0.0`.

Và hai điều kiện về **hình dạng**, không phải về số:

- ✅ *"Listing nào có điểm đánh giá thấp nhất tại Indonesia?"* ra
  `abstain` `A22-ALIGN-RANK-TIE` — **không** ra `allow` với `rating = 0.0`.
  Đây là phép kiểm rằng W13.1 không bịt mắt tie detector; bản thiếu
  `RANK_KEY_ALIAS` cho `allow` ở đúng câu này.
- ✅ Đường template không đổi: *"Listing nào có giá cao nhất tại Việt Nam?"*
  vẫn `allow` · **3 033 180**.

> **Ranh giới với W14.** Sau W13, *"Listing nào có điểm đánh giá thấp nhất"* ra
> `A22-ALIGN-RANK-TIE` vì 17 listing ID cùng có `rating = 0`. Con số `0` đó là
> **"chưa có đánh giá nào"**, không phải điểm 0 — xem §15. W13 làm cho lời từ
> chối *tồn tại*; W14 làm cho nó *đúng lý do*.

---

## §15. W14 — Giá trị không phải phép đo: một registry thay một hằng số

> Gỡ: ✅ `mt016` · `mt022` (§1.6.2), và làm cho `bgk19` từ chối **đúng lý do**.
> Chặn: **W5.2/W5.3** — không có W14, W5 biến một lời từ chối đúng thành một con
> số sai. Đây là phần thi công được của hợp đồng còn treo ở §17.5.1.
> Phụ thuộc: không (giai đoạn A). Giai đoạn B sau **W10.1**.
> Checklist §0.3 chạm: 1 · 2 · 3 · 4 · 5 · 6.

### 15.1. Sự thật — cùng một cửa hàng, cùng một tên sản phẩm, hai số phận

✅ Đo trực tiếp trên `data/processed/products_clean.csv`:

| `product_listing_key` | Tên sản phẩm | `price_num` | Được gắn cờ? |
| --- | --- | ---: | :-: |
| `id:809769142:55559898858` | `[ FREE GIFT FOR 6/25! ]Dapatkan Hadiah Dengan Min. Pembelian 300RB` | **999 999 999** | ✔ |
| `id:809769142:46312750544` | `[ FREE GIFT FOR 6/25! ]Dapatkan Hadiah Dengan Min. Pembelian 300RB` | **9 999 999** | ✘ |
| `id:1379527329:49163119181` | `[GIVEAWAY] ZOICY Tea Tree Moisturizing Toner …` | **9 999 999** | ✘ |

Hai dòng đầu là **hai listing của cùng một shop mang y hệt một tên sản phẩm**.
Một cái được xử lý như "không có giá", cái kia đi thẳng vào phép xếp hạng — và
sự khác nhau duy nhất là số chữ số 9.

✅ Vì luật hiện hành là **một hằng số**, được chép lại ở **sáu** chỗ:

| Nơi | Dạng |
| --- | --- |
| `planner/synthesizer.py:46` + `:364` | `PRICE_SENTINEL = 999999999`, dùng trong `if measure_ref == "measure.price"` |
| `planner/analytical.py:76` | literal `999999999` trong plan `median_price_by_day` |
| `planner/analytical.py:177` | literal `999999999`, chỉ cho `kind == "highest_price_listing"` |
| `domain/invariant_handlers.py:26` | `PRICE_SENTINEL = 999_999_999`, dùng bởi `_SentinelExcluded` |
| `notebooks/pipeline/data_pipeline.ipynb` cell 1 | `PRICE_SENTINEL = 999_999_999`; `price_sentinel_flag = price_num.eq(PRICE_SENTINEL)` |
| `scripts/build_multiturn_suite.py:64` | `clean = latest[latest.price_num < 999_999_999]` — **trong bộ sinh oracle**, nên bộ đề kế thừa đúng lỗi của hệ (§16.5) |

cộng hai chỗ **chỉ nói bằng lời** (`domain/catalog.py:257`,
`domain/metrics.py:104` và `:111`) và **một oracle độc lập đã kế thừa cùng lỗi**
(`scripts/bgk_groundtruth.py` đọc `price_sentinel_flag`, nên `bgk19` ghi ground
truth là `9999999` — chính giá trị giữ chỗ).

✅ Hệ quả số học tại ID ngày 03/07:

```
max(price)                                    = 999 999 999   (1 dòng, đã gắn cờ)
max(price) sau filter < 999999999             =   9 999 999   (2 dòng — HOÀ)
max(price) sau khi loại cả hai lớp giữ chỗ    =   1 135 000   (1 dòng, sản phẩm thật)
```

### 15.2. Vì sao hôm nay chưa sai — và vì sao W5 làm nó sai

✅ Hôm nay hai dòng `9 999 999` hoà nhau ở đỉnh, `executor.py:130` đặt
`rank_tie_at_cut=True`, và `workflow.py:1481` cho ra `A22-ALIGN-RANK-TIE`. Lời
từ chối **an toàn**, nhưng lý do nó nêu — *"nhiều nhóm cùng đạt giá trị cao
nhất"* — mô tả một triệu chứng, không phải bệnh.

✅ Và tấm lưới đó **chỉ tồn tại trên đường `Rank`**: `executor.py:125` chỉ chấm
hoà khi `query.rank_limit is not None`. Một node `Aggregate` với
`aggregation="max"` trả **đúng một dòng** và không đi qua nhánh đó.

W5.1 khai `cao nhat / lon nhat / toi da / maximum / max` ⇒
`requested_aggregation="max"`, W5.2 phát node `Aggregate` cho câu vô hướng, và
`measure.price.valid_aggregations = ('median','min','max')` — **`max` đã được
chứng nhận**. Nên sau W5, `bgk19` *"Giá cao nhất tại Indonesia ngày 03/07 là bao
nhiêu?"* đi trọn đường allow.

✅ Đã đo bằng chính SQL mà W5 sẽ sinh:

```sql
SELECT MAX(price_num) AS price FROM (
  SELECT * FROM products
  WHERE country_code='id' AND date='2026-07-03' AND price_num < 999999999)
-- ->  9 999 999          <-- con số W5 sẽ trả lời
-- loại thêm 9999999 ->  1 135 000   <-- đáp án đúng
```

Tức **W5 không cộng thêm một ca đúng; nó biến một lời từ chối đúng thành một
`wrong_value_silent`** — đúng lớp lỗi mà `over_answer_rate = 0.0` ở §0.2 tồn tại
để cấm. Đây là lý do W14 phải xong trước W5.2/W5.3.

### 15.3. Lớp vấn đề rộng hơn một giá trị giá

✅ Cùng một hình dạng lỗi có ở ba measure khác, và không cái nào được khai:

| Measure | Giá trị không phải phép đo | Đo được | Ảnh hưởng |
| --- | --- | --- | --- |
| `measure.rating` | `rating_num == 0` ⟺ `rating_count_num == 0` — **"chưa có đánh giá nào"**, không phải điểm 0 | ✅ đúng **43/668** VN và **17/474** ID; không dòng nào có `rating > 0` mà `rating_count == 0` | trung vị VN `4.923603693479375` → `4.928571428571429`; ID `4.901304084208852` → `4.902690838143241`. Sau W13, `min(rating)` ra `A22-ALIGN-RANK-TIE` vì 17 listing cùng bằng 0 |
| `measure.monthly_sold` | trần hiển thị: ✅ **693/3138** dòng bằng đúng `1000`; ID 03/07 **184/450** | `bgk18` từ chối đúng, nhưng bằng `A19-CAT` — một nhãn nói về danh mục, không về trần hiển thị | |
| `measure.history_sold` | phân phối theo rổ `1000/2000/…/10000`: ✅ **742** dòng bằng `10000` | mọi `max`/`Rank` trên nó đọc trần như đỉnh thật | |

Ba dòng trên **không** được sửa bằng cách thêm ba hằng số nữa. Chúng là bằng
chứng rằng thứ còn thiếu là **một chỗ để khai** *"giá trị nào của measure này
không phải một phép đo, và loại nào"*.

### 15.4. Chỗ để khai đã có sẵn, và chưa ai đọc nó

✅ `domain/metrics.py:25-38` đã có `MetricConstraint` — có kiểu, bắt buộc
`decision_id`, kiểm ở binding time (`domain/bindings.py:347`: ref phải tồn tại
trong catalog), và đi vào payload băm (`bindings.py:148`) nên **mọi thay đổi làm
đổi binding hash**. Đúng mọi tính chất một luật chất lượng dữ liệu cần.

✅ Và `rg definition_constraints src/` cho thấy: **chỉ `bindings.py` đọc nó**.
Không planner, không compiler, không invariant handler. Đúng một metric khai một
constraint (`has_structured_voucher`). Nó là một registry đã có kiểm và **chưa
có call site** — cùng lớp "dark component" mà `Archi2808` §5.10 ghi cho
`external/lexicon.py`.

W14 **không tạo registry mới**. Nó nối registry đã có vào đường compile.

### 15.5. W14.1 — Lớp giá trị, khai bằng `definition_constraints`

`domain/metrics.py`. Mở rộng `MetricConstraint` bằng **một** field additive:

```python
ValueClass = Literal[
    "measurement",       # giá trị là một phép đo thật (mặc định, không đổi gì)
    "placeholder",       # ô "không có giá trị" được điền bằng một số
    "display_ceiling",   # trần hiển thị của sàn: giá trị thật >= số này
    "no_observation",    # null bị mã hoá thành 0 (chưa ai đánh giá, chưa ai thích)
]

@dataclass(frozen=True)
class MetricConstraint:
    ...
    value_class: ValueClass = "measurement"     # additive, bất biến #7
```

Và **luật phát hiện** — vì §17.5.1 đã chốt: luật phải theo *đặc tính dữ liệu*,
không theo danh sách ID:

```python
@dataclass(frozen=True)
class ValueClassRule:
    """Luật nhận ra một giá trị không phải phép đo.

    ``repdigit_nine`` khớp một số nguyên dương mà MỌI chữ số đều là 9 và có ít
    nhất ``min_digits`` chữ số. Luật theo đặc tính, nên nó sống sót qua một lần
    làm mới dữ liệu; một danh sách ID thì không.
    """
    rule_id: str
    ref: str
    kind: Literal["repdigit_nine", "equals", "companion_is_zero"]
    value_class: ValueClass
    min_digits: int | None = None
    values: tuple[float, ...] = ()
    companion_ref: str | None = None
    decision_id: str | None = None      # None = ĐÃ PHÁT HIỆN, CHƯA DUYỆT
```

✅ Độ chính xác của `repdigit_nine` đã đo trên toàn dataset:

| `ref` | `min_digits` | Số dòng khớp | Giá trị phân biệt | Listing |
| --- | ---: | ---: | --- | ---: |
| `measure.price` | 7 | **9** | `9 999 999` · `999 999 999` | 3 |
| `measure.price_original` | 7 | **12** | `9 999 999` · `999 999 999` | 4 |
| 6 measure số còn lại | 7 | **0** | — | — |

Cả bốn listing khớp đều mang `[GIVEAWAY]`, `[ FREE GIFT FOR 6/25! ]` hoặc
`[LINK]` trong tiêu đề. Luật **không đọc tiêu đề** — đó chỉ là phép đối chứng
của người review, và §17.5.1 đã cấm suy nghĩa nghiệp vụ từ tiêu đề lúc chạy.

Nội dung khởi tạo registry, **cố ý tối thiểu**:

```python
VALUE_CLASS_RULES = (
    # Hằng số đang chạy, di trú NGUYÊN VĂN. decision_id ghi đúng xuất xứ của nó
    # -- một literal trong source, không phải một quyết định có chữ ký. Ghi như
    # vậy để lần review đầu tiên nhìn thấy sự thật đó.
    ValueClassRule("price-sentinel-legacy", "measure.price", "equals",
                   "placeholder", values=(999_999_999,),
                   decision_id="legacy-source-literal"),
    # PHÁT HIỆN, CHƯA DUYỆT: decision_id=None => KHÔNG loại dòng nào, chỉ chặn
    # câu trả lời mà giá trị biên rơi vào đây (15.7).
    ValueClassRule("price-repdigit-nine", "measure.price", "repdigit_nine",
                   "placeholder", min_digits=7, decision_id=None),
    ValueClassRule("price-original-repdigit-nine", "measure.price_original",
                   "repdigit_nine", "placeholder", min_digits=7, decision_id=None),
    ValueClassRule("rating-no-observation", "measure.rating", "companion_is_zero",
                   "no_observation", companion_ref="measure.rating_count",
                   decision_id=None),
)
```

Bất biến kiểm ở import (`ValueClassError`), cùng khuôn `_build_catalog`:

- `ref` và `companion_ref` phải có trong `CATALOG`;
- `kind == "repdigit_nine"` ⇒ `min_digits >= 3`;
- `kind == "equals"` ⇒ `values` không rỗng;
- `kind == "companion_is_zero"` ⇒ `companion_ref` bắt buộc;
- **agent không được điền `decision_id`** — cùng luật với `COLUMN_SEMANTICS.approved_by` (§9.2) và A12-R6.

`VALUE_CLASS_RULES` băm vào `REGISTRY_HASH` và đi vào
`scripts/verify_metadata_bindings.py` như mọi registry khác.

### 15.6. W14.2 — Synthesizer phát predicate từ registry, không từ một nhánh `if`

`planner/synthesizer.py:361-365`. Xoá nhánh đặc thù:

```python
# TRƯỚC -- một measure được bảo vệ, tám measure không, và không ai thấy sự
# chênh đó vì nó là một câu `if` chứ không phải một hàng trong bảng.
if measure_ref == "measure.price":
    predicates.append(Predicate(ref="measure.price", op="lt",
                                parameter="price_sentinel", value=PRICE_SENTINEL))

# SAU -- luật đã DUYỆT của bất kỳ measure nào đều thành predicate, theo cùng
# một đường. Một measure chưa khai luật nào thì không có predicate nào -- y hệt
# hôm nay, nên không measure nào đổi hành vi vì bản thân thay đổi này.
for predicate in approved_exclusion_predicates(measure_ref):
    predicates.append(predicate)
```

`approved_exclusion_predicates(ref)` sống ở `domain/metrics.py` và **chỉ** trả
predicate cho `ValueClassRule` có `decision_id is not None`. Với registry khởi
tạo ở 15.5, nó trả đúng `price < 999999999` cho `measure.price` và rỗng cho tất
cả các ref khác ⇒ ✅ **58 plan trong baseline không đổi một byte**.

Hai chỗ literal ở `planner/analytical.py:76` và `:177` dùng cùng hàm. Chú ý
`:177` hiện chỉ gắn predicate cho `kind == "highest_price_listing"`; sau W14 nó
gắn theo `metric_ref`, nên `lowest_price_listing` và các kind khác được cùng một
luật — điều kiện `kind == …` biến mất.

`domain/invariant_handlers.py::_SentinelExcluded` bỏ hằng số riêng và hỏi
registry cùng câu hỏi: *một predicate tổ tiên có loại được lớp `placeholder` đã
duyệt của ref này không*. Spec `sentinel.price_excluded_before_rank` giữ
`invariant_id`, `severity` và `applies_to` nguyên vẹn; chỉ nguồn tập giá trị đổi.

`domain/catalog.py:257` và `domain/metrics.py:104`/`:111` là **caveat bằng lời
có ghim con số**. Sinh chúng từ registry thay vì viết tay, nếu không lần đầu
tiên data owner đổi luật là lần đầu tiên caveat nói dối.

### 15.7. W14.3 — Luật đã phát hiện nhưng chưa duyệt: **chặn câu trả lời, không sửa dữ liệu**

Đây là mấu chốt của W14, và là chỗ nó tôn trọng ranh giới ở §17.5.1.

Một `ValueClassRule` có `decision_id is None` **không được** loại dòng nào: loại
dòng là đổi định nghĩa metric, và đó là quyết định của chủ dữ liệu. Nhưng nó
**được** chặn một câu trả lời mà giá trị quyết định câu trả lời đó rơi vào luật:

| Tình huống | Hành vi |
| --- | --- |
| Rule đã duyệt (`decision_id` có) | thành predicate ⇒ dòng bị loại trước aggregate/rank (15.6) |
| Rule chưa duyệt, **và** giá trị biên của kết quả khớp rule | `abstain` · **`A19-VALUE-CLASS`** |
| Rule chưa duyệt, giá trị biên không khớp | **không đổi gì** — trả lời như hôm nay |
| Không rule nào cho ref đó | **không đổi gì** |

"Giá trị biên" có định nghĩa chính xác theo hình plan, và chỉ đọc những dòng đã
được lấy về — không quét thêm dữ liệu:

- plan có `Rank`: các dòng trong `frame` sau khi cắt, cộng dòng thứ
  `rank_limit + 1` mà executor vẫn lấy để chấm hoà;
- plan có `Aggregate` với `aggregation ∈ {"max", "min"}`: chính dòng kết quả;
- `aggregation ∈ {"median", "mean", "sum", "count", "share"}`: **không kiểm**.
  Trung vị bền với đuôi — ✅ `ans037 = 78 900` không đổi dù có hay không sáu dòng
  `9 999 999` — và chặn nó sẽ lấy đi năng lực mà không đổi được con số nào.

Điểm nối: `analytics/tools.py`, ngay sau `executor.execute(compiled)` và **trước**
khi dựng Evidence, cùng chỗ `rank_tie_at_cut` đang được đọc. Kết quả ghi vào
`planning.value_class`:

```python
{"checked_refs": [...], "boundary_hits": [
    {"ref": "measure.price", "rule_id": "price-repdigit-nine",
     "value": 9999999.0, "row_index": 0, "approved": False}],
 # Khoá đếm bắt buộc (§0.3 ô 4): không có nó, "chưa bao giờ có ca nào" và
 # "nhánh chưa bao giờ chạy" là hai bảng số giống hệt nhau.
 "blocked": True}
```

`A19-VALUE-CLASS` phải nói đúng thứ nó biết và không hơn — **không** khẳng định
giá trị đó là rác, chỉ khẳng định chưa ai quyết định nó là gì:

> *"Giá trị quyết định câu trả lời này là một giá trị mà quy tắc chất lượng dữ
> liệu chưa được duyệt: chưa xác định được nó là một mức giá thật hay một ô để
> trống. Trả lời bằng nó sẽ là một con số không ai kiểm được."*

Không chèn chữ số vào message (`CLAUDE.md` §3.1).

### 15.8. W14.4 — Loại bao nhiêu dòng thì phải nói ra bấy nhiêu

✅ `workflow.py:768` hiện nói *"giá sentinel và giá không hợp lệ đã bị loại
trước khi xếp hạng"* — đúng, nhưng **không có số**. Một câu trả lời dựa trên
`n − k` dòng mà không nói `k` là một câu trả lời không tái lập được.

`CompiledQuery` thêm `exclusion_predicate_refs`; `analytics/tools.py` ghi vào
`Evidence.attrs`:

```python
"excluded_by_value_class": {"measure.price": 3}     # đếm thật, từ COUNT phụ
```

và câu chữ ở mục *Cách tính* nêu con số đó. Dùng `model_copy(update=...)`, không
mutate Evidence đã tạo (bất biến #4).

### 15.9. W14.5 — Giai đoạn B: một luật, chạy ở pipeline (sau W10.1)

Giai đoạn A ở trên **không đổi `data/processed`**, nên không đổi
`dataset_version` và không buộc chạy lại oracle. Giai đoạn B mới đổi, và vì vậy
nó xếp sau `W10.1`:

1. `src/gladiators/data/pipeline.py` (module do W10.1 dựng) import
   `VALUE_CLASS_RULES` và tính cờ theo **từng measure**, thay
   `price_sentinel_flag = price_num.eq(PRICE_SENTINEL)`. Cột mới:
   `value_class_flag__<measure>` với giá trị `ValueClass`.
2. Mọi dòng khớp một rule **chưa duyệt** đi vào `data_quality_issues.csv` với
   `code = "VALUE_CLASS_CANDIDATE"` — đó là hàng đợi review, và nó là thứ biến
   một phát hiện thành một quyết định.
3. `scripts/bgk_groundtruth.py` và `eval/independent/*_oracle.py` đọc cột mới
   thay vì `price_sentinel_flag`. ⚠ Oracle **phải** đổi cùng lúc: hôm nay
   `bgk19` ghi ground truth `9999999` vì nó kế thừa đúng cái cờ thiếu.
4. Khi data owner duyệt: `decision_id` được điền ⇒ rule thành predicate (15.6)
   ⇒ `A19-VALUE-CLASS` biến thành `allow`, `dataset_version` đổi, chạy lại toàn
   bộ oracle/PAM/eval theo §17.5.1.

**Không được** làm bước 4 thay chủ dữ liệu.

### 15.10. Nghiệm thu W14

Giai đoạn A — phải đạt **trước** khi W5.2 được merge:

| Ca | Trước | Sau (giai đoạn A) |
| --- | --- | --- |
| `bgk19` *"Giá cao nhất tại Indonesia 03/07"* | `clarify` `A22-ALIGN-MEASURE` | `abstain` **`A19-VALUE-CLASS`** |
| `bgk19` **sau W5, nếu thiếu W14** | — | ⚠ `allow` · **9 999 999** ← chính là ca phải không bao giờ xảy ra |
| `mt016` · `mt022` | `abstain` `A22-ALIGN-RANK-TIE` | `abstain` **`A19-VALUE-CLASS`** |
| *"Listing nào có giá cao nhất tại Việt Nam?"* | `allow` `3 033 180` | **`allow` `3 033 180`** — không đổi |
| *"Listing nào có số lượt thích cao nhất"* (VN) | `allow` `10 449` | **`allow` `10 449`** — không đổi (không rule nào cho ref đó) |
| `ans035` · `ans037` (trung vị, sau W5) | — | `132 000` · **`78 900`** — nhánh median không bị kiểm |
| `synthesizer_equivalence_baseline.json` | — | **0 entry đổi** |
| `pytest -q` | 1207 passed | **1207 passed** |

Giai đoạn B — sau W10.1:

| Ca | Kỳ vọng |
| --- | --- |
| Dòng `VALUE_CLASS_CANDIDATE` trong `data_quality_issues.csv` | **9** cho `measure.price` · **12** cho `measure.price_original` |
| `bgk19` ground truth trong `scripts/bgk_groundtruth.py` | `9999999` → **`1 135 000`** (1 listing, không hoà) |
| Sau khi data owner duyệt `price-repdigit-nine` | `bgk19` → `allow` · **1 135 000**; `mt016`/`mt022` → `allow` · **1 135 000** |
| `dataset_version` | đổi ⇒ chạy lại §21.7 và §21.11 |

Ràng buộc luôn kèm: `risk = 0.0` · `over_answer_rate = 0.0`.

Test mới `tests/test_value_class.py`:

- `repdigit_nine(min_digits=7)` khớp `9999999` và `999999999`, **không** khớp
  `3033180`, `999`, `1000`, `0`, số âm, số thập phân;
- rule chưa duyệt ⇒ `approved_exclusion_predicates` trả **rỗng** ⇒ plan không đổi;
- rule chưa duyệt + giá trị biên khớp ⇒ `A19-VALUE-CLASS`, và
  `planning.value_class.blocked` bật;
- rule chưa duyệt + giá trị biên **không** khớp ⇒ `allow`, `blocked` tắt;
- `aggregation="median"` ⇒ không kiểm biên, kể cả khi đuôi có dòng khớp;
- điền `decision_id` ⇒ predicate xuất hiện, câu trả lời đổi, và
  `excluded_by_value_class` báo đúng số dòng bị loại.

---

## §16. W15 — Bộ đề khai kỳ vọng mà không ai chấm

> Gỡ: làm cho `cq02`–`cq04` (§1.6.1) và 48 lượt multiturn (§1.6.2) trở thành
> **phép đo**, chứ không phải file JSON. Không tự nó sửa hành vi nào.
> Phụ thuộc: không. Nên làm **cùng W12** — cả hai đều là "biết chỗ nào hỏng".
> Checklist §0.3 chạm: 3 · 7 · 8.

### 16.1. Sự thật — 14 bộ đề khai kỳ vọng, CI chấm một

✅ Kiểm kê toàn bộ `eval/`: **14 file khai `expected_action`**, tổng **240 ca**.
Ai chấm chúng:

| Bộ đề | Ca | Được chấm bởi | Trong CI? |
| --- | ---: | --- | :-: |
| `questions.json` | 60 | `scripts/run_evaluation.py` (mặc định `--suite`) | ✔ |
| `dr2607.json` | 40 | `tests/test_dr2607_regression.py:37` | ✔ (pytest) |
| `p0_probes.json` | 9 | `tests/test_p0_regression_lock.py` | ✔ (pytest) |
| `independent/answerable_manual.json` | 44 | `scripts/run_risk_coverage.py` — chạy tay | ✘ |
| `questions_v2` `_a19` `_ambiguity` `_boundaries` `_counting` `_schema` | 41 | `run_evaluation.py --suite` nếu **có ai gõ**; test chỉ dùng làm đầu vào | ✘ |
| `questions_critic.json` | 4 | **không ai** | ✘ |
| `questions_multiturn.json` | 24 ca / 48 lượt | **không ai** | ✘ |
| `groq_regression.json` · `pilot_gemini.json` | 18 | **không ai** (`rg` không ra call site nào) | ✘ |

✅ `.github/workflows/ci.yml` chạy đúng hai lệnh: `pytest -q` và
`run_evaluation.py --runs 3 --provider offline` — tức **đúng một** suite ngoài
pytest. Ba lớp lỗi ở §1.6 nằm trọn trong phần không được chấm.

Đây không phải "quên viết harness". Nó là cùng một lỗi mà `Archi2808` §13.1 đã
nêu cho một chuyện khác: **một file kỳ vọng không có người đọc là một tài liệu,
không phải một phép đo** — và nó trông giống hệt một phép đo đang xanh.

### 16.2. W15.1 — Harness multiturn

`scripts/run_multiturn.py` (**mới**). Suite này có một hợp đồng riêng mà
`run_evaluation.py` không diễn đạt được: mỗi ca là một **chuỗi lượt chung
`session_id`**, và lượt 2 khai **hai** kỳ vọng.

```python
# Bộ nhớ hội thoại chỉ chứng minh được điều gì đó khi CẢ HAI nhánh cùng được
# chạy: có session_id thì kế thừa được country/date; không có thì phải hỏi lại.
# Chấm một nhánh là không chấm A3 -- một hệ bỏ qua session_id hoàn toàn vẫn
# xanh nếu chỉ chạy nhánh có bộ nhớ.
for case in suite:
    for turn in case["turns"]:
        with_memory = runtime.run(turn["question"], session_id=case["session_id"])
        assert_action(with_memory, turn["expected_action"])
        if "expected_action_without_memory" in turn:
            stateless = runtime.run(turn["question"])          # session_id=None
            assert_action(stateless, turn["expected_action_without_memory"])
```

Ràng buộc bắt buộc:

- **`session_id` phải được reset giữa các ca**, và harness phải chứng minh điều
  đó: hai ca liên tiếp cùng thị trường mà rò state sẽ cho cùng một kết quả và
  không ai thấy;
- báo cáo dùng **cùng bộ chỉ số của W9.1** (`coverage`, `over_refusal_rate`, …),
  không phát minh một tỷ lệ pass thứ ba — §1.3 đã ghi cái giá của việc có hai
  công thức cùng tên;
- mẫu số là **lượt**, không phải ca, và báo cả hai con số. Một ca hai lượt hỏng
  một lượt không phải "nửa đúng".
- `expected_value` được chấm khi có, bằng `verify_numeric_claims` như mọi suite
  khác — không so chuỗi.

Ghi báo cáo vào `eval/reports/<ngày>-multiturn.json`.

### 16.3. W15.2 — `questions_critic` vào bảng chấm

Không viết harness thứ ba. `questions_critic.json` khai đúng hợp đồng
`run_evaluation.py` đã đọc được (`id` · `question` · `expected_action` ·
`expected_intent`), nên nó chỉ cần **được gọi**:

```
run_evaluation.py --suite eval/questions_critic.json --runs 3 --provider offline
```

Điều kiện để con số có nghĩa: bộ đề này khai `expected_action: "allow"` cho ba
ca mà **cả hai cấu hình phát hành đều chặn** (§1.6.1). Vì vậy nó phải vào CI
**sau W7**, và trước đó nó chạy ở chế độ báo cáo — có số, không có cổng. Đặt nó
làm cổng trước W7 là ghim một cổng đỏ vào CI và dạy mọi người bỏ qua CI.

### 16.4. W15.3 — Hợp đồng: khai kỳ vọng thì phải có người chấm

`tests/test_suite_has_a_scorer.py` (**mới**). Đây là phép kiểm ngăn lớp lỗi này
quay lại, và nó là loại kiểm mà §16.1 cho thấy còn thiếu:

```python
SCORED_BY = {
    "eval/questions.json": "scripts/run_evaluation.py (CI)",
    "eval/dr2607.json": "tests/test_dr2607_regression.py",
    "eval/p0_probes.json": "tests/test_p0_regression_lock.py",
    ...
}
# Bộ đề chỉ dùng với provider thật, cố ý không có scorer offline. Nằm trong
# allowlist CÓ LÝ DO, không nằm ngoài bảng: "không ai chấm" phải là một quyết
# định đọc được, không phải một khoảng trống.
PROVIDER_ONLY = {"eval/groq_regression.json": "cần provider Groq",
                 "eval/pilot_gemini.json": "cần provider Gemini"}


def test_every_suite_declaring_expected_action_has_a_scorer():
    for path in glob("eval/**/*.json"):
        if not _declares_expected_action(path):
            continue
        assert path in SCORED_BY or path in PROVIDER_ONLY, (
            f"{path} khai expected_action nhưng không ai đọc nó"
        )
```

Và phép kiểm đối ngẫu — quan trọng hơn, vì nó là cách `questions_critic` lọt:

```python
def test_scorer_actually_asserts_the_expectation():
    """Đọc `case["question"]` làm ĐẦU VÀO không phải là chấm.

    tests/test_evidence_consistency.py và tests/test_synthesizer_equivalence.py
    đều đọc questions_critic.json; không file nào chạm expected_action. Vì vậy
    "có test đọc file" không phải là điều kiện -- điều kiện là có ai đó so
    response.gate.action với expected_action.
    """
```

Cách kiểm được, không dựa vào đọc code bằng mắt: mỗi entry của `SCORED_BY` trỏ
tới một **test id hoặc lệnh** cụ thể, và test này chạy nó với một bản ghi đè
`expected_action` cố tình sai rồi khẳng định nó **đỏ**. Một scorer không đỏ được
khi kỳ vọng sai là một scorer không tồn tại.

### 16.5. W15.4 — Sửa oracle multiturn, không sửa gate

✅ `scripts/build_multiturn_suite.py:64` tính đáp án bằng

```python
clean = latest[latest.price_num < 999_999_999]
```

— **bản sao thứ sáu của cùng hằng số** ở §15.1, lần này trong bộ sinh oracle.
Vì vậy `mt016`/`mt022` khai `expected_value.max_price = 9999999.0`, tức bộ đề
**kỳ vọng hệ trả về một giá trị giữ chỗ**.

Sửa: bộ sinh gọi cùng hàm registry của W14 (`approved_exclusion_predicates` /
`VALUE_CLASS_RULES`) thay literal. Sau W14 giai đoạn B, `max_price` của ID thành
**1 135 000**.

⚠ Cho tới khi data owner duyệt (§15.9 bước 4), hai ca đó khai
`expected_action: "abstain"` với `allowed_rule_ids: ["A19-VALUE-CLASS"]` —
**không** khai `allow` với một con số chưa ai duyệt. Đây là chỗ dễ sai nhất của
W15: sửa bộ đề cho khớp hành vi là đúng khi bộ đề sai, và là `CLAUDE.md` §8 khi
hành vi sai. Ở đây bộ đề sai — nó ghim một giá trị giữ chỗ làm đáp án — và bằng
chứng là §15.1, không phải việc hệ đang từ chối.

`author_read_source_code` giữ `true`, và ghi chú xuất xứ giữ nguyên: bộ đề này
không trở thành độc lập về quy trình chỉ vì được sửa (`W9.4`, §10.4).

### 16.6. Nghiệm thu W15

| Ca | Kỳ vọng |
| --- | --- |
| `scripts/run_multiturn.py` | chạy 24 ca / **48 lượt**, báo cả nhánh có và không có `session_id` |
| Điểm khởi đầu ghi vào báo cáo | ✅ **6/48 lượt lệch** (4 × W7, 2 × W14) — con số này là **mốc**, không phải cổng |
| Sau W7 | 4 ca `top_shop` chuyển xanh ⇒ **2/48** |
| Sau W14 giai đoạn A | `mt016`/`mt022` ra `A19-VALUE-CLASS`, khớp kỳ vọng đã sửa ⇒ **0/48** |
| `questions_critic` sau W7 | **4/4**, và vào CI như một cổng |
| `test_suite_has_a_scorer` | mọi file khai `expected_action` nằm trong `SCORED_BY` hoặc `PROVIDER_ONLY`; thêm file mới mà quên scorer ⇒ **đỏ** |
| Scorer giả (kỳ vọng cố tình sai) | **đỏ** ở mọi entry của `SCORED_BY` |
| Rò `session_id` giữa hai ca | test riêng chứng minh **không** rò |

Không cổng nào ở §18.2 được sửa để dùng con số của W15 trước khi W7 xong: W15
đo, nó không gỡ.

---

## §17. Registry và mã mới

### 17.1. Rule id — bổ sung `Archi2808` §12

| Rule | Nghĩa | Sinh ở |
| --- | --- | --- |
| `A-EMPTY-RESULT-UNVERIFIED` | Zero-row mà không chứng minh được bộ lọc chạy đúng giá trị được nêu | W1.8 · `agent/workflow.py` |
| `A19-AGGREGATION` | Câu hỏi nêu một phép tổng hợp mà catalog chưa chứng nhận cho measure đó | W5.1 · `planner/synthesizer.py` → `AnalyticalPlanError` |
| `A19-EXECUTION` | Plan đã qua validator nhưng không chạy được trên dữ liệu hiện tại | W13.3 · `agent/workflow.py`, bắt `ExecutionFailure`/`CompilationError`/`duckdb.Error` |
| `A19-VALUE-CLASS` | Giá trị quyết định câu trả lời khớp một luật chất lượng dữ liệu **đã phát hiện, chưa được duyệt** | W14.3 · `analytics/tools.py` → `AnalyticalPlanError` |

Cả bốn `fixable=False`, `action="abstain"`, và **không được chèn chữ số** vào
message (`CLAUDE.md` §3.1: `verifier.scan_numbers` chấm chúng là số bịa).

`A19-EXECUTION` có một tính chất riêng đáng ghi: nếu W13.1/W13.2 đúng thì nó
**không bao giờ bắn** trên các suite hiện có. Nó vẫn phải tồn tại — nó là lớp
fail-closed cho mọi nguyên nhân chưa biết, và khoá đếm của nó là cách phân biệt
"chưa từng có ca nào" với "nhánh chưa từng chạy".

### 17.2. Invariant — 11 → 12

| Invariant | Severity | `applies_to` | Handler |
| --- | --- | --- | --- |
| `INV-FILTER-LITERAL-IS-DATASET-VALUE` | hard | `("execution",)` | `binding.filter_literal_exists_in_dataset` |

`INVARIANTS.REGISTRY_HASH` đổi ⇒ `scripts/verify_metadata_bindings.py` in hash
mới ⇒ `Archi2808` §6.2 (bảng hash) và §6.4 (bảng 11 invariant) phải cập nhật.

### 17.3. Registry mới

| Registry | File | Vai trò |
| --- | --- | --- |
| `VALUE_DIMENSION_BY_UNIT` | `domain/catalog.py` | đơn vị phân tích → chiều mang tên (W1.2) |
| `COUNT_METRIC_BY_SURFACE_REF` | `domain/catalog.py` | chiều/đơn vị → metric đếm (W4.2) |
| `COLUMN_SEMANTICS` | `domain/column_semantics.py` (mới) | ngữ nghĩa quan sát của cột (W8.1) |
| `VERSIONED_ARTIFACTS` | `data/dataset_version.py` (mới) | tập file quyết định `dataset_version` (W1.3) |
| `ExecutablePredicateOp` + canonicalizer | `planner/predicate_ops.py` (mới) | một dialect operator cho parser · IR · catalog · compiler (W11.0) |
| `DECLINE_RULE_BY_CODE` | `planner/synthesizer.py` | decline typed → rule id, có priority ổn định (W12) |
| `_MATERIALIZING_OPS` | `planner/compiler.py` | toán tử nào dựng danh sách cột, toán tử nào đi xuyên (W13.1) |
| `VALUE_CLASS_RULES` | `domain/metrics.py` | giá trị nào của một measure không phải một phép đo, và loại nào (W14.1) |

Các registry trên kiểm bất biến **lúc import** và fail build khi mâu thuẫn, theo đúng khuôn
`_build_catalog` và `_check_dispatch` đang dùng.

### 17.4. Trường hợp đồng mới

| Nơi | Trường | Mặc định | Additive? |
| --- | --- | --- | :-: |
| `AnalyticalRequest` | `requested_aggregation` | `None` | ✔ |
| `AnalyticalRequest` | `semantic_ambiguities: tuple[SemanticAmbiguity, ...]` | `()` | ✔ |
| `RequestDigest` | `requested_aggregation` | `None` | ✔ |
| `PlanAtom` | `kind="aggregation"` | không có atom | ✔ |
| `CompiledQuery` | `planned_predicate_count`, `executed_predicate_count` | `0` | ✔ |
| `Evidence.attrs` (zero-row) | `filter_bindings`, `executed_predicate_count`, `planned_predicate_count`, `relaxed_filters` | — | ✔ |
| `_EmptyExecution` | ba trường trên | — | ✔ |
| `score_plan()` | `plan_provenance` | `"llm_ir"` | ✔ |
| `planning.risk` | score · modes · factors · provenance · deterministic_bypass | — | ✔ |
| `MetricSpec` | `share: ShareDefinition | None` | `None` | ✔ |
| `OpenPlannerError` · `AnalyticalPlanError` | `rule_id`, `decline_codes`, `attempts` | `A19-PLAN`, `()`, `()` | ✔ |
| `MetamorphicRelation` | `min_applicable` | `1` | ✔ |
| `ToolBox.sales_decline()` | `window` | `None` | ✔ |
| `compiler.rank_state` | `ref` (ref semantic của khoá xếp hạng) | không có khoá | ✔ |
| `CompiledQuery` | `exclusion_predicate_refs` | `()` | ✔ |
| `MetricConstraint` | `value_class` | `"measurement"` | ✔ |
| `planning` | `execution_error` · `value_class` | không có khoá | ✔ |
| `Evidence.attrs` | `excluded_by_value_class` | không có khoá | ✔ |
| `value_index.json` | `schema_version`, `values[ref][country]: dict` | — | ✘ **breaking** |

`Evidence` đồng thời chuyển sang `ConfigDict(extra="forbid", frozen=True)`;
đây là siết invariant của object, không phải thêm field. Chỗ cần bổ sung attrs
phải dựng đủ từ đầu hoặc dùng `model_copy(update=...)`, không mutate instance đã
truyền cho verifier.

Chỉ **một** thay đổi breaking, và nó được chặn bằng kiểm `schema_version` cộng
preflight `dataset_version` (§2.3, §2.5).

### 17.5. Bốn hợp đồng còn treo — code phải fail-closed cho tới khi được khai

Bốn mục dưới đây **không** thuộc W1–W10 vì chúng không phải thiếu code. Chúng ở
đây để trạng thái fail-closed hiện tại là một quyết định có ghi chép, không phải
một chỗ ai đó quên. Nguyên tắc chung: **không sửa code để ép các ca này xanh
trước khi hợp đồng được khai.**

#### 17.5.1. Luật chất lượng giá — sentinel và `[QUÀ TẶNG KHÔNG BÁN]`

> **Cập nhật sau phép đo 29/08 — phần thi công được đã tách thành `W14` (§15).**
> Mục này giữ nguyên vì ranh giới của nó vẫn đúng: **giá trị nào là giữ chỗ** là
> quyết định của chủ dữ liệu. Thứ W14 thêm vào là phần **không** cần quyết định
> đó: một chỗ để khai luật, một đường để luật đã duyệt thành predicate, và một
> lời từ chối có kiểu khi giá trị quyết định câu trả lời rơi vào một luật **đã
> phát hiện mà chưa duyệt**. Đọc §15.7 trước khi đọc đoạn dưới.

✅ Đo lại trên `data/processed`:

| Sự thật | Con số |
| --- | ---: |
| `product_snapshot_metrics.price_sentinel_flag = True` | **3 / 3341** |
| Dòng có `price_num == 999999999` | **3** (đúng ba dòng đã gắn cờ) |
| Dòng có `price_num == 9999999` (bảy chữ số 9) | **6 — chưa gắn cờ** |
| VN trên ngưỡng p99,9 (`2 965 266`) | **2 dòng** |

✅ Và ca `tc19`: item `56061511146` tên `[QUÀ TẶNG KHÔNG BÁN] QUẠT MINI CẦM
TAY …`, giá `410 000` / `400 890` / `400 890` — **một mức giá hoàn toàn bình
thường**. Ngưỡng giá không bắt được nó; chỉ chuỗi trong tiêu đề mới nói lên
điều đó, và **suy nghĩa nghiệp vụ từ tiêu đề sản phẩm ngay trong lúc chạy là
đúng lớp lỗi §2**.

Hợp đồng khi được khai:

- Luật được duyệt phải là **luật theo đặc tính dữ liệu** (ví dụ: "mọi giá bằng
  một hằng số lặp lại `9…9` là sentinel"), **không** duyệt theo ID từng dòng —
  một danh sách ID không sống sót qua một lần làm mới dữ liệu.
- Cờ `price_sentinel_flag` là **đầu ra của luật**, không phải đầu vào; nó được
  tính lại ở `W10.1` cùng lúc với `data/processed`.
- Trạng thái "không bán" cần một **trường được quản trị**, không suy từ tiêu đề.
- Mọi luật được duyệt **làm đổi `dataset_version`** ⇒ chạy lại oracle / PAM /
  eval.

Vì sao mục này chặn `W5`: `_choose_aggregation` chọn `median`, và
`synthesizer.py:361-365` chỉ loại sentinel cho `measure.price`. Sáu dòng
`9999999` chưa gắn cờ nằm ở thị trường ID và **sẽ đi vào phép trung vị** của
`ans037` nếu luật mở rộng. ✅ Hôm nay chúng không đổi kết quả
(`ans037 = 78 900` khớp oracle vì trung vị bền với đuôi), nhưng `mean` hay
`max` thì có.

⚠ **Và biện pháp "giữ nguyên `valid_aggregations`" là chưa đủ — đã đo được.**
`measure.price.valid_aggregations` hiện là `('median', 'min', 'max')`, tức
`max` **đã được chứng nhận**. Sau W5.1/W5.2, *"Giá cao nhất tại Indonesia ngày
03/07"* đi trọn đường allow và trả ✅ **9 999 999** — một giá trị giữ chỗ — vì
tie detector chỉ tồn tại trên đường `Rank`, không trên đường `Aggregate`
(`executor.py:125`). Vì vậy `W14` giai đoạn A là **điều kiện chặn của W5.2**,
không phải một cải tiến kèm theo. Chi tiết và số đo ở §15.2.

#### 17.5.2. PAM — trọng số và cái phải kèm theo mọi lần chấm

✅ `insights/pam.py:32` hiện là `DEFAULT_WEIGHTS = (0.30, 0.40, 0.30)`, tức bộ
trọng số **mới** đã nằm trong code. ◻ Phép so với bộ cũ `(0.20, 0.40, 0.40)`:
tương quan Spearman **0.9806** — nghe như vô hại — nhưng **nhóm đầu bảng đổi tới
~19%** (top-decile overlap 81,1%).

`segment_churn = 0` **không** phải bằng chứng vô hại: phân khúc được xác định
chủ yếu từ điểm thành phần chứ không từ trọng số tổng.

Hợp đồng kỹ thuật, độc lập với việc ai chọn trọng số nào:

| Yêu cầu | Vì sao |
| --- | --- |
| Output PAM phải mang `config_hash` (hash của `weights` + `MOMENTUM_DELTA_WEIGHT`), `input_hash`, và `dataset_version` | ✅ `pam.py` hiện **không có** khoá nào trong ba khoá này ⇒ hai bảng xếp hạng dựng bằng hai cấu hình khác nhau trông giống hệt nhau |
| Báo cáo so sánh phải có: chồng lấn nhóm đầu **theo từng nước × danh mục**, danh sách listing xê dịch nhiều nhất, và 63 listing không đủ dữ liệu | Một con số tương quan tổng che mất chỗ duy nhất người dùng nhìn |
| Khai rõ PAM dùng để **xếp hạng** hay chỉ để **mô tả** | Hai mục đích chịu hai ngưỡng chấp nhận khác nhau |

⚠ `nan is None` là `False` — cạm bẫy đã cắn: 63 listing bị void điểm từng được
gán nhãn "Steady", tức "không chấm được" hiện ra thành "bình thường"
(`CLAUDE.md` §3.1). Mọi thay đổi PAM phải giữ 63 listing đó ở trạng thái **void
tường minh**.

#### 17.5.3. Chính sách ranh giới phát ngôn — file tham chiếu đã mất

✅ `docs/Spec2308.md:91` trỏ tới `docs/acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md`.
**Thư mục `docs/acceptance/` không tồn tại trong checkout ngày 28/08**; `docs/qa/`
chỉ còn `DR TASK 1407.md`.

◻ Các lớp kỹ thuật đã khá tốt: ràng buộc phát ngôn ↔ evidence
(`verifier.verify_numeric_claims`), phân tầng nguồn (`source_tier`), lineage
(`_lineage_gaps`), gác từ ngữ (`INV-NO-INTERNAL-VOCABULARY`,
`INV-NO-CAUSAL-CLAIM`). Thứ thiếu là **văn bản** để ai đó ký.

Hợp đồng: tạo **một** chính sách hiện hành duy nhất, ghi rõ sáu cột — loại phát
ngôn · tầng nguồn được phép · động từ / phép tổng hợp được phép · caveat bắt
buộc · evidence bắt buộc · chủ sở hữu và hash chữ ký. Cho tới khi có chữ ký,
phát ngôn **nhân quả**, **thời gian thực** và **nguồn ngoài** giữ fail-closed —
tức trạng thái hôm nay, và nó là trạng thái đúng.

Không được tạo lại `docs/acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md` bằng nội dung
suy đoán; hoặc khôi phục từ git history, hoặc viết mới và sửa con trỏ ở
`Spec2308.md:91`.

#### 17.5.4. Bốn kết nối OAuth — ngoài phạm vi nghiệm thu lõi

Bốn kết nối (Gmail, Calendar, Phoenix, notebookLLM) **không có call site nào
trong `src/gladiators/`** và không xuất hiện trong 12 route của `api.py`
(`Archi2808` §10.2). Vì vậy chúng **không nằm trong phạm vi nghiệm thu lõi** và
không được phép chặn bất kỳ cổng nào ở §18.2.

Nếu sau này đưa vào: chúng đi qua đúng hợp đồng external hiện có —
`source_tier="external"`, `admission="context_only"`, `mapping_status=
"needs_review"`, provenance bắt buộc — và **không có ngoại lệ nào** cho phép số
từ chúng đi vào aggregate nội bộ (bất biến #3).

---

## §18. Thứ tự phụ thuộc và cổng nghiệm thu

### 18.1. Đồ thị phụ thuộc

```
W3 ─────────────────────────────► W10.1 ──► W10.2 ──► W10.3
 (CI dựng lại được)                (pipeline) (publish) (dataset #2)
                                                          ▲
                                              xuất xứ ────┘  (điều kiện đầu vào)

W1 ──┬──► W5.1/W5.2 (aggregate contract — cần entity-binding guard)
     └──► W7   (thang leo thang — mở khoá 2 ca nghiệm thu của chính W1)

W12 ──► W5.1, W11  (decline typed phải tồn tại trước khi mở thêm lối từ chối)

W5.1 ──► W11.2 ──► W5.3
 (field `requested_aggregation`) (metric rate phải có trước khi mở gateway scalar)

W11.0 ──► W8.3  (QualifierSpec dùng cùng canonical predicate operator)

W12  tự nó không đổi quyết định nào và nên làm đầu tiên; các mũi tên trên là
     phụ thuộc quan sát/rule propagation, không phải phụ thuộc hành vi

W13 ──┬──► W5.3
      ├──► W7        (cả ba mở rộng tập plan tất định THẬT SỰ được chạy;
      └──► W11        W13 sửa lớp lỗi mà việc mở rộng đó phóng đại)

W14(A) ──► W5.2 ──► W5.3        (không có W14, W5 trả 9 999 999 cho bgk19)
W10.1  ──► W14(B)               (cờ per-measure đổi dataset_version)

W15  ──► không gỡ gì; nó làm cho W7 và W14 ĐO ĐƯỢC. Làm cùng W12.

W4   độc lập
W6   độc lập
W2   độc lập
W8.1/W8.2 registry mặc định `unknown` ⇒ không đổi hành vi; W8.3 sau W11.0
W9   sau W4 (MR-1), sau W8.3 (MR-6); trước mọi kết luận về coverage
```

Bảy chỗ **không được đảo**, mỗi chỗ có lý do đo được:

1. **W1 trước W5.** `open_planner.py:196-201` ghi lại sự cố: nới điều kiện gọi
   synthesizer khi chưa có entity-binding guard đã trả lời *"Rating theo brand
   không tồn tại tại VN"* bằng cả 19 brand.
2. **W7 trước khi nghiệm thu W1.** Hai ca `120` và giao rỗng cần plan có
   `belongs_to`, mà plan đó đang bị thang leo thang chặn.
3. **W11 cùng hoặc trước W5.3.** ✅ `bgk11` bind `measure.discount_percent` với
   aggregation mặc định `median`; mở cổng scalar aggregate trước khi `"tỷ lệ"` có
   ref sẽ cho *"tỷ lệ listing có giảm giá"* một node `Aggregate` chạy được và một
   con số trung vị hợp lệ cho một câu hỏi về tỷ lệ. Alignment vẫn chặn — nhưng
   dựa vào lớp cuối là dựa vào một lớp không được thiết kế cho việc đó (§12.1).
4. **W10.3 sau cùng.** Ghép dữ liệu trước làm `over_refusal_rate` **tăng**
   (§11.3) và phá `bnd09` (§1.4).
5. **W11.0 trước W8.3.** Voucher label cần predicate `gte 1`; nếu qualifier tiếp
   tục hard-code `eq bool`, ref có physical vẫn biên dịch sai kiểu hoặc bị catalog
   từ chối.
6. **W13 trước W5.3, W7, W11.** ✅ 24/84 câu xếp hạng hiện trả HTTP 500 vì một
   plan `Scan→Filter→Rank` không sinh ra được các cột nó đã khai (§14.1). Cả ba
   work package kia làm **nhiều plan tất định hơn** thật sự chạy, nên mỗi cái
   đều nhân số ca chạm lớp lỗi này. Sửa sau là sửa trong lúc bề mặt đang lớn dần.
7. **W14 giai đoạn A trước W5.2.** ✅ Đo bằng chính SQL mà W5 sẽ sinh:
   `MAX(price_num)` với bộ lọc sentinel hiện hành trả **9 999 999** trên ID —
   một giá trị giữ chỗ — trong khi đáp án đúng là **1 135 000**. Đường
   `Aggregate` **không có** tie detector (`executor.py:125` chỉ chấm hoà khi có
   `rank_limit`), nên không lớp nào phía sau chặn nó. Làm W5 trước W14 là biến
   một lời từ chối đúng thành một `wrong_value_silent`, tức phá ràng buộc
   `over_answer_rate = 0.0` ở §0.2.

Và hai chỗ **không được ký sớm**:

- Không xin chữ ký cassette trước khi payload ổn định (§3.4) — sửa cassette làm
  `sha256` đổi và phải duyệt lại.
- Không xin ký sáu oracle topic gate trước khi corpus có manifest và hash
  (§10.5).

### 18.2. Bảng nghiệm thu

Mỗi dòng là một cổng: chưa đạt thì work package chưa xong.

| WP | Con số nghiệm thu | Ràng buộc luôn kèm |
| --- | --- | --- |
| **W1** | 5 ca: `96` · `120` · `0` · `A-VALUE-NOT-FOUND` · `DatasetVersionError`; `original_of` round-trip 100% | `risk` 0.0 · `over_answer_rate` 0.0 |
| **W2** | Kho rỗng ⇒ exit ≠ 0; 6 file có `sha256` khớp manifest; replay ×3 `stable=true` với socket bị chặn | `GLADIATORS_ENABLE_LIVE_SEARCH` vẫn OFF |
| **W3** | Clone sạch → `pip install -e .[dev]` → 3 lệnh dựng → **1207 passed** | không cài tay gói nào |
| **W4** | ans028 `30` · ans030 `12`; MR-1 fail **8 → 0** | baseline synthesizer **0 entry đổi** |
| **W5** | ans035 `132000` · ans036 `4.923603693479375` · ans037 `78900` · ans038 `4.901304084208852` | baseline chỉ đổi `tc29` (→`None`, có allowlist) và `tc36` (→`sum`) |
| **W6** | ans019 `+87` · ans020 `0` · tc34 `+11`; evidence mang **cả** `d0` và `d1` | baseline **0 entry đổi** |
| **W7** | ans031 `7` · ans032 `465` · ans033 `9` · ans034 `471`; **và** bgk08 `809769142` · bgk09 10 nhóm | `enable_critic` vẫn `False`; đường `llm_ir` không đổi; vị từ chạy trước **cả** nhánh `complexity_level == "L3"` (§8.3.1) |
| **W11** | bgk05 `8` · bgk11 `96.26 %` với evidence **643/668/rate** và arithmetic verified | operator canonical xuyên parser→compiler; ⚠ blast radius baseline phải đo bằng §21.9 trước code |
| **W12** | `diagnose_refusals.py` sinh bảng trùng §1.2; mọi `return None` có `_decline` liền trước và tập code exact | **0 ca đổi hành vi**; baseline **0 entry đổi** |
| **W8** | registry `unknown` ⇒ 6 ca nghiệp vụ không đổi; voucher mơ hồ clarify; explicit ID structured/label = **0/474 · 210/474**; ans044 `A14-EXT` | không case nào hard-code; router có một nguồn phrase/concept |
| **W9** | Hai script cho cùng giá trị cho mọi tên chung; `metamorphic_consistency_rate` loại quan hệ `not_measured`; corpus có hash | `gate_open` vẫn `False` |
| **W10** | `data/processed` dựng lại cho đúng `27de9bff184f4f89`; 4 ca lỗi thật của `raw_extra_data` **đều bị chặn** | bảy suite giữ `1.0` khi ghim bản đóng băng |
| **W13** | Quét 84 câu: `CRASH` **24 → 0**; `POST /ask` câu giá thấp nhất VN: `500 → 200` · **1 000**; câu min-rating ID vẫn `A22-ALIGN-RANK-TIE` | `pytest` **1207 passed**; baseline **0 entry đổi**; bộ 44 câu giữ **19** lệch |
| **W14** | `bgk19` · `mt016` · `mt022` ra **`A19-VALUE-CLASS`**; *"giá cao nhất VN"* giữ **3 033 180**; *"lượt thích cao nhất VN"* giữ **10 449** | `approved_exclusion_predicates` trả predicate **y hệt** hôm nay ⇒ baseline **0 entry đổi**; median không bị kiểm biên |
| **W15** | `run_multiturn.py` chạy **48 lượt** cả hai nhánh bộ nhớ; mốc **6/48**; `questions_critic` **4/4** sau W7; scorer giả ⇒ **đỏ** | không cổng nào ở bảng này được sửa để dùng số của W15 |

### 18.3. Bằng chứng đã đo cho W5 + W7 — vá tạm, chạy end-to-end

✅ Ngày 28/08 đã vá **tối thiểu** W5.2 · W5.3 · W7 vào runtime bằng monkey-patch
(§21.13) rồi chạy sáu suite. Mục đích là trả lời một câu mà mọi phần trên **chưa**
trả lời được: *bốn lớp kiểm có chấp nhận những câu trả lời này không, hay chúng
chỉ chạy được ở tầng SQL?*

**Chiều thuận — 13/13 ca đích qua đủ bốn lớp:**

| Ca | action | rule | số | verified |
| --- | --- | --- | ---: | :-: |
| ans035 · bgk02 | `allow` | `A-ALLOW` | **132 000** | ✅ |
| ans036 | `allow` | `A-ALLOW` | **4.923603693479375** | ✅ |
| ans037 | `allow` | `A-ALLOW` | **78 900** | ✅ |
| ans038 · bgk06 | `allow` | `A-ALLOW` | **4.901304084208852** | ✅ |
| bgk04 | `allow` | `A-ALLOW` | **6** | ✅ |
| ans031 | `allow` | `A-ALLOW` | **7** | ✅ |
| ans032 | `allow` | `A-ALLOW` | **465** | ✅ |
| ans033 | `allow` | `A-ALLOW` | **9** | ✅ |
| ans034 | `allow` | `A-ALLOW` | **471** | ✅ |
| bgk08 | `allow` | `A-ALLOW` | `Glad2Glow Official Store` / **220** | ✅ |
| bgk09 | `allow` | `A-ALLOW` | 10 nhóm, 20 claim | ✅ |

bgk08 khớp oracle: shop_id `809769142` = `Glad2Glow Official Store`, 220 listing.

**Chiều nghịch — hồi quy trên 76 câu golden + 6 probe P0:**

| Suite | Số ca | Ca đổi |
| --- | ---: | --- |
| `eval/questions.json` | 60 | **0** |
| `eval/questions_boundaries.json` | 9 | **0** |
| `eval/questions_counting.json` | 3 | **0** |
| `eval/questions_ambiguity.json` | 4 | **0** |
| `eval/p0_probes.json` | 6 | **1** — `p0-grouping-dropped-official-shop` `abstain` → `allow` **465** |
| `eval/independent/answerable_manual.json` | 44 | **8** — đúng ans031–ans038 |

Ca P0 đổi là ca §8.6 đã dự đoán, và giá trị khớp oracle độc lập
`p0_grouping_official_shop.vn_official_shop_listings = 465`.

**Chỉ số trên bộ 44 câu — đo, không phải dự phóng:**

| Chỉ số | Gốc | W5 + W7 |
| --- | ---: | ---: |
| `answered` | 20 | **28** |
| `answerable_coverage` | 0.5263 | **0.7368** |
| `answer_rate_all` | 0.4545 | **0.6364** |
| `over_refusal_rate` | 0.4737 | **0.2632** |
| `risk` | 0.0 | **0.0** |
| `over_answer_rate` | 0.0 | **0.0** |

> **Giới hạn của bằng chứng này, phải đọc kèm:** bản vá là monkey-patch tối thiểu.
> Nó **không** cài `W5.1` (`_choose_aggregation` trung thực), **không** cài
> `W4`/`W6`/`W11`, và **không** chạy `pytest`. Nó chứng minh đúng một điều:
> **đường từ plan tới câu trả lời không có chướng ngại nào khác** — evidence dựng
> được, verifier qua, alignment qua, consistency qua. Nó **không** chứng minh bản
> cài đặt thật sẽ hành xử y hệt.

### 18.4. Dự phóng — và nó là dự phóng

✅ **Đã đo** (§18.3): W5 + W7 gỡ 8 ca ⇒ `over_refusal_rate` **47,37 % → 26,32 %**,
`risk` giữ **0.0**, hồi quy **0**.

⚠ **Dự phóng** cho phần còn lại: W4 gỡ thêm 2 (ans028 · ans030), W6 gỡ thêm 2
(ans019 · ans020) ⇒

```
over_refusal_rate   10/38 = 26,32 %  ->   6/38 = 15,79 %
answerable_coverage 28/38 = 73,68 %  ->  32/38 = 84,21 %
```

**Sáu ca cuối KHÔNG phải là code.** Chúng là `W8`, và hai trong sáu (ans017 ·
ans018) tài liệu này đã lập luận là **oracle sai chứ không phải hệ sai** (§9.1).
Nên `over_refusal_rate = 0` **không phải mục tiêu của tài liệu này**, và một bản
cài đặt đạt được nó gần như chắc chắn đã đánh đổi bằng `risk`.

⚠ Và **trên BGK-20**, theo bản đồ §1.5 — W4–W7 gỡ 6 ca, W11 gỡ 2, W4.3 gỡ 1:

```
BGK-20 (bộ kiểu giám khảo)   4/13 = 31 %  ->  13/13 = 100 %
```

Hai dự phóng này đo **hai thứ khác nhau** và không được cộng hay so với nhau: bộ
44 câu sinh từ dữ liệu, BGK-20 do người soạn theo kiểu giám khảo. Cả hai phải
được báo cạnh nhau, kèm `risk` và `over_answer_rate`.

**Đây là dự phóng, không phải số đã đo.** Phải đo lại sau **mỗi** work package
(§10.7), không đợi tới cuối. Sáu ca còn lại là W8 và chúng phụ thuộc một quyết
định nghiệp vụ, không phụ thuộc code.

---

## §19. Những gì tài liệu này cố ý KHÔNG làm

| Không làm | Lý do đo được |
| --- | --- |
| **Không xây streaming / Kinesis** | ◻ 9 ca bỏ lỡ của BGK-20 phân bố A4 4 · A5 2 · A1 2 · A13 1 — **không ca nào thiếu dữ liệu**. ✅ 18 ca từ chối oan ở §1.2 cũng vậy. Và `raw_extra_data` đã cho sẵn độ sâu lịch sử, lại là backfill một lần (`created_at` distinct = 1) nên không cho bằng chứng về nhịp quan sát |
| **Không bật `enable_critic` / `enable_nversion`** | W7 thay bằng vị từ tất định; bật critic toàn cục đưa một mô hình vào review một plan không có mô hình nào trong đó |
| **Không bật LLM parser** | ◻ p95 30–50 s so với ngân sách 15 s; ◻ P-B bắn 10/44 ca mà **không đổi một kết cục nào**. Trước khi đo lại phải có: chỉ gọi khi nhánh tất định bó tay · hạn chót theo ngân sách còn lại + ngắt mạch + tối đa một lần thử · cache theo yêu cầu đã chuẩn hoá + phiên bản prompt/mô hình · timeout rơi về nhánh tất định. Chỉ bật khi trên holdout: coverage **tăng**, risk **không tăng**, p95 **≤ 15 s**, và telemetry chứng minh nhánh đó **thật sự chạy** |
| **Không nới A5/A13** | ◻ L0 ≡ L1 ≡ L2 trùng khít — tắt chúng cứu **0 câu**. Cổng chưa bao giờ là nút thắt |
| **Không dùng BM25 / embedding cho tên riêng** | Danh sách brand/shop/danh mục là danh sách **đóng và hữu hạn**; khớp chính xác nhanh hơn, không trôi, kiểm thử được. Embedding xếp hạng tự tin giữa hai tên riêng không có ngữ nghĩa — sai thầm lặng |
| **Không sửa golden để test xanh** | `CLAUDE.md` §8. Mọi thay đổi fixture ở tài liệu này đều kèm lý do contract và số oracle độc lập |
| **Không để agent điền chữ ký duyệt** | A12-R6 (§3.2) và `COLUMN_SEMANTICS.approved_by` (§9.2) |
| **Không ghép `raw_extra_data` vào `data/raw`** | Chưa có xuất xứ (§11.4); và ghép trước W7 làm `over_refusal_rate` tăng |

---

## §20. Bảng tra: file → thay đổi

| File | WP | Thay đổi |
| --- | :-: | --- |
| `pyproject.toml` | W3 | `dependencies` + `optional-dependencies.dev` |
| `src/gladiators/data/dataset_version.py` | W1 | **mới** — `compute_dataset_version`, `assert_index_matches` |
| `src/gladiators/data/repository.py:33-41` | W1 | gọi hàm chung |
| `src/gladiators/data/pipeline.py` | W10 | **mới** — logic từ notebook |
| `src/gladiators/data/publish.py` | W10 | **mới** — manifest · validate · quarantine |
| `src/gladiators/data/coverage.py:30` | W8 | `ZERO_VARIANCE_COLUMNS` khi cột được duyệt `observed` |
| `src/gladiators/agent/value_probe.py:33-123` | W1 | `_index` v2 · `original_of` · `bind_values` trả bản gốc · `index_dataset_version` |
| `src/gladiators/agent/alignment.py:234,463,475` | W1 | ba bản sao → một `_empty_result_is_self_evident` |
| `src/gladiators/agent/workflow.py:195-205` | W1 | `_EmptyExecution` thêm 3 trường |
| `src/gladiators/agent/workflow.py:1498-1541` | W1 | `A-EMPTY-RESULT-UNVERIFIED` · sửa `item.rule_id` → `item.invariant_id` · telemetry `handler_fired` |
| `src/gladiators/agent/parser.py:54` | W8 | thu hẹp `UNSUPPORTED["ads"]` (chỉ khi registry duyệt) |
| `src/gladiators/agent/tool_dispatch.py` | W6 | truyền `date_range` vào `sales_decline` |
| `src/gladiators/agent/consistency.py` | W6 | luật `end - start == delta` |
| `src/gladiators/analytics/tools.py:42-51` | W6 | `sales_decline(window=…)` |
| `src/gladiators/analytics/tools.py:483-499` | W1 | `filter_bindings` · `executed_predicate_count` · `relaxed_filters` |
| `src/gladiators/analytics/tools.py` | W6 | 3 Evidence cho plan `temporal` |
| `src/gladiators/domain/catalog.py` | W1·W4 | `VALUE_DIMENSION_BY_UNIT` · `COUNT_METRIC_BY_SURFACE_REF` |
| `src/gladiators/domain/catalog.py` | W8 | `dim.is_ad` · `dim.is_sold_out` · tách hai ref voucher |
| `src/gladiators/domain/catalog.py` | W4.3 | alias trần `"lượt thích"`, `"lượt đánh giá"` |
| `src/gladiators/domain/metrics.py` | W11 | metric `discounted_listing_rate` (`share`, numerator/denominator khai tường minh) |
| `src/gladiators/domain/column_semantics.py` | W8 | **mới** |
| `src/gladiators/domain/invariants.py` | W1 | `INV-FILTER-LITERAL-IS-DATASET-VALUE` |
| `src/gladiators/domain/invariant_handlers.py` | W1 | handler `binding.filter_literal_exists_in_dataset` |
| `src/gladiators/domain/qualifiers.py` | W8 | surface `het hang` (khi duyệt) |
| `src/gladiators/external/lexicon.py:117-131` | W1 | xoá `_original_of`, dùng `value_probe.original_of` |
| `src/gladiators/planner/semantic_parser.py` | W1·W4·W5 | bind giá trị cho đơn vị · khung đếm · `requested_aggregation` |
| `src/gladiators/planner/semantic_parser.py` | W11 | `_COMPARISON` — measure sau từ so sánh thành predicate |
| `src/gladiators/planner/synthesizer.py:243-266` | W5 | `_choose_aggregation` trung thực |
| `src/gladiators/planner/synthesizer.py:415-425` | W5 | `_wants_scalar_aggregate` + phát `Aggregate` |
| `src/gladiators/planner/synthesizer.py` | W6 | nhánh hai mốc thời gian |
| `src/gladiators/planner/open_planner.py:70-111` | W5·W6 | hai mệnh đề mới cho `_synthesis_beats_template` |
| `src/gladiators/planner/compiler.py:248-252` | W6 | `TemporalCompare` dạng hai đầu mút |
| `src/gladiators/planner/validator.py:206-208` | W6 | schema 3 trường cho dạng mới |
| `src/gladiators/planner/risk.py:40-106` | W7 | `plan_provenance` · `deterministic_plan_is_acceptable` |
| `src/gladiators/agent/workflow.py:1265-1272` | W7 | vị từ tất định chạy trước **cả** nhánh `complexity_level == "L3"` (§8.3.1) |
| `scripts/build_value_index.py` | W1 | schema v2 · hàm băm chung |
| `scripts/build_processed.py` | W10 | **mới** |
| `scripts/record_search_cassettes.py:88-105` | W2 | `verify()` 7 bước |
| `scripts/build_topic_gate.py:53-80` | W9 | corpus manifest thay `glob` |
| `scripts/run_evaluation.py:94-151` | W9 | đổi tên chỉ số · `selective_metrics` dùng chung |
| `scripts/run_risk_coverage.py:75-106` | W9 | như trên |
| `scripts/run_metamorphic.py:46-98` | W9 | `min_applicable` · MR-7 kiểm cơ chế |
| `scripts/build_question_bank.py` | W8·W9 | tách câu voucher mơ hồ · `entity_text` |
| `eval/metamorphic/relations.py` | W9 | `min_applicable` · MR-6 đổi qualifier · MR-7 `expectation` |
| `eval/p0_probes.json` | W7 | `p0-grouping-dropped-official-shop` theo 3 bước §8.6 |
| `eval/dr2607.json#tc34` | W6 | `expected_action: "allow"`, oracle `+11` |
| `eval/topic_gate_corpus.json` | W9 | **mới** |
| `eval/independent/answerable_external.json` | W9 | **mới** — bộ đề độc lập quy trình |
| `artifacts/search_cassettes/MANIFEST.json` | W2 | **mới**, force-track |
| `tests/test_value_binding.py` | W1 | **mới** |
| `tests/test_counting_frame.py` | W4 | **mới** |
| `tests/test_deterministic_escalation.py` | W7 | **mới** |
| `tests/test_predicate_as_measure.py` | W11 | **mới** |
| `src/gladiators/planner/synthesizer.py` | W12 | `DeclineCode` · tham số ra `decline` ở 20 lối `return None` |
| `src/gladiators/agent/workflow.py:1226` | W12 | ghi kết quả `_synthesis_beats_template` vào `planning.attempts` |
| `scripts/diagnose_refusals.py` | W12 | **mới** — chỉ đọc `AgentResponse`, không import `planner`/`domain` |
| `tests/test_refusal_diagnostics.py` | W12 | **mới** |
| `tests/test_packaging.py` | W3 | **mới** |
| `tests/test_question_bank_contract.py` | W9 | **mới** |
| `src/gladiators/planner/compiler.py:287-303` | W13 | `rank_state["ref"] = node.rank_by` |
| `src/gladiators/planner/compiler.py:368-401` | W13 | `_MATERIALIZING_OPS` · `_exposed_name` · `_project_output_contract` · `RANK_KEY_ALIAS` |
| `src/gladiators/planner/executor.py:125-160` | W13 | bỏ `__rank_key__` **sau** tie detection, **trước** phép so hợp đồng |
| `src/gladiators/agent/workflow.py:1462-1464` | W13 | bọc `dispatch` bằng `except (ExecutionFailure, CompilationError, duckdb.Error)` → `A19-EXECUTION` |
| `src/gladiators/agent/workflow.py:1488-1497` | W13.5 | chiều của lời từ chối hoà lấy từ `Rank.descending` |
| `src/gladiators/domain/metrics.py` | W14 | `ValueClass` · `MetricConstraint.value_class` · `ValueClassRule` · `VALUE_CLASS_RULES` · `approved_exclusion_predicates` |
| `src/gladiators/planner/synthesizer.py:46,361-365` | W14 | xoá `PRICE_SENTINEL` và nhánh `if measure_ref == "measure.price"` |
| `src/gladiators/planner/analytical.py:76,177` | W14 | hai literal `999999999` → `approved_exclusion_predicates(metric_ref)`; bỏ điều kiện `kind == "highest_price_listing"` |
| `src/gladiators/domain/invariant_handlers.py:26,119-158` | W14 | `_SentinelExcluded` hỏi registry thay hằng số riêng |
| `src/gladiators/domain/catalog.py:257` | W14 | caveat sinh từ registry, không ghim con số bằng tay |
| `src/gladiators/analytics/tools.py:437-470` | W14 | kiểm giá trị biên · `planning.value_class` · `excluded_by_value_class` |
| `notebooks/pipeline/data_pipeline.ipynb` → `data/pipeline.py` | W14(B) | `value_class_flag__<measure>` · `VALUE_CLASS_CANDIDATE` |
| `scripts/bgk_groundtruth.py:31` | W14(B) | oracle đọc cờ mới; `bgk19` `9999999` → `1 135 000` |
| `scripts/build_multiturn_suite.py:64` | W15.4 | literal `999_999_999` → registry; `mt016`/`mt022` khai lại kỳ vọng |
| `scripts/run_multiturn.py` | W15 | **mới** — 48 lượt, cả hai nhánh bộ nhớ |
| `.github/workflows/ci.yml` | W15 | thêm `questions_critic` (sau W7) và `run_multiturn.py` |
| `tests/test_plan_executes_its_contract.py` | W13 | **mới** |
| `tests/test_value_class.py` | W14 | **mới** |
| `tests/test_suite_has_a_scorer.py` | W15 | **mới** |
| `docs/Archi2808.md` §6.2 · §6.4 · §14 · §16 · §17 | tất cả | cập nhật hash · invariant · rule · ma trận WP · khoảng trống |

---

## §21. Lệnh tái lập

Chạy từ root repository.

### 21.1. Nền test

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=D:\tg28_solspec
# ✅ 28/08: 1207 passed, 1 skipped in 80.50s
```

### 21.2. Dựng artifact bắt buộc trước mọi phép đo

```powershell
$env:PYTHONPATH='src'; $env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts/build_value_index.py
.\.venv\Scripts\python.exe scripts/build_question_bank.py
.\.venv\Scripts\python.exe scripts/build_multiturn_suite.py
```

### 21.3. Bản đồ 19 ca lệch (§1.2)

```python
# PYTHONPATH=src PYTHONIOENCODING=utf-8 python <file>
import json, pathlib
from gladiators.runtime_factory import create_runtime

cases = json.loads(
    pathlib.Path("eval/independent/answerable_manual.json").read_text(encoding="utf-8")
)
runtime = create_runtime("offline")
for case in cases:
    response = runtime.run(case["question"])
    if response.gate.action != case["expected_action"]:
        print(case["id"], case["answerable"], case["expected_action"],
              response.gate.action, response.gate.rule_id, sep=" | ")
```

### 21.4. Tái lập lỗi literal (§2.1)

```python
from gladiators.runtime_factory import create_runtime

response = create_runtime("offline").run(
    "Có bao nhiêu listing của brand Bibica ở VN ngày 03/07?"
)
print(response.gate.action, response.gate.rule_id)
print(response.request.analytical["filters"])
# ✅ allow A-ALLOW ; dim.brand = "bibica"  (dữ liệu ghi "Bibica")
```

### 21.5. Hai `dataset_version` đang lệch (§2.5)

```python
import json, pathlib
from gladiators.data.repository import ArtifactRepository

print("repository  ", ArtifactRepository().dataset_version)
print("value_index ", json.loads(
    pathlib.Path("artifacts/value_index.json").read_text(encoding="utf-8")
)["dataset_version"])
# ✅ 27de9bff184f4f89  /  a821e39d98ff4079
```

### 21.6. Điểm rủi ro chặn bốn ca shop chính hãng (§8.1)

```python
import gladiators.agent  # nạp trước để tránh import vòng
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import synthesize
from gladiators.planner.risk import score_plan

request = DeterministicSemanticParser().parse(
    "Có bao nhiêu listing của shop chính hãng tại Việt Nam ngày 03/07?", "vi", "vn"
)
result = score_plan(synthesize(request, "vn").plan)
print(result.score, result.requested_mode, result.effective_mode, result.allowed)
# ✅ 3 critic blocked False
```

### 21.7. Ground truth độc lập (§1.1)

```python
import pandas as pd

products = pd.read_csv("data/processed/products_clean.csv")
shops = pd.read_csv("data/processed/shop_info_clean.csv")
for country in ("vn", "id"):
    day = products[(products.country_code == country) & (products.date == "2026-07-03")]
    first = products[(products.country_code == country) & (products.date == "2026-07-01")]
    joined = day.merge(
        shops[shops.country_code == country][["shop_id", "shop_name", "is_official_shop"]],
        on="shop_id", how="left", suffixes=("", "_s"),
    )
    print(country,
          "listing", day.product_listing_key.nunique(),
          "delta", day.product_listing_key.nunique() - first.product_listing_key.nunique(),
          "brand", day.brand.nunique(),
          "official_shop", int(shops[(shops.country_code == country) & shops.is_official_shop].shape[0]),
          "official_listing", joined[joined.is_official_shop == True].product_listing_key.nunique(),
          "median_price", day[day.price_num < 999999999].price_num.median(),
          "median_rating", day.rating_num.median())
```

### 21.8. Các report

```powershell
$env:PYTHONPATH='src'; $env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts/run_risk_coverage.py
.\.venv\Scripts\python.exe scripts/run_metamorphic.py
.\.venv\Scripts\python.exe scripts/build_topic_gate.py
.\.venv\Scripts\python.exe scripts/run_ablation.py
```

Các lệnh gọi provider ngoài (`bgk_run_agent.py`, `run_intent_policy_report.py`,
`record_search_cassettes.py` không có `--verify`) tốn tiền và phụ thuộc key;
**không dùng report offline để suy ra độ trễ hoặc chi phí của đường LLM**.

### 21.9. Blast radius lên baseline bị khoá — chạy TRƯỚC khi sửa parser/synthesizer

Bắt buộc cho `W5` và `W11`; nên chạy cho mọi thay đổi chạm
`semantic_parser.py` hoặc `synthesizer.py`. Nó trả lời đúng một câu: *thay đổi
này làm đổi plan của bao nhiêu trong 58 câu đang bị khoá, và câu nào.*

```python
# PYTHONPATH=src PYTHONIOENCODING=utf-8 python <file>
import json, pathlib
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import synthesize

BASELINE = json.loads(
    pathlib.Path("tests/fixtures/synthesizer_equivalence_baseline.json")
    .read_text(encoding="utf-8")
)
SUITES = ("questions", "questions_v2", "questions_a19", "questions_boundaries",
          "questions_ambiguity", "questions_counting", "questions_critic",
          "dr2607", "semantic_linking")
questions = {}
for suite in SUITES:
    for case in json.loads(pathlib.Path(f"eval/{suite}.json").read_text(encoding="utf-8")):
        if case.get("question"):
            questions[f"{suite}:{case['id']}"] = (case["question"], case.get("country") or "vn")

parser = DeterministicSemanticParser()
for key, expected in BASELINE.items():
    if not isinstance(expected, dict) or "exc" in expected:
        continue
    question, country = questions[key]
    result = synthesize(parser.parse(question, "vi", country), country)
    if result is None:
        print("MẤT PLAN  ", key, "|", question[:60])
        continue
    ops = [node.op for node in result.plan.nodes]
    if [node["op"] for node in expected["nodes"]] != ops:
        print("ĐỔI HÌNH  ", key, "|", ops, "|", question[:50])
```

✅ Đo ngày 28/08 với source hiện tại: **35/58 plan không có node `Aggregate`**;
chỉ 2 trong số đó (`dr2607:tc29`, `dr2607:tc36`) nêu một phép tổng hợp tường
minh, nên `W5` đổi đúng 2 entry — xem §6.2 và §6.3.

### 21.10. BGK-20 trên đường tất định

Không thay `W9.6` (cần provider thật), nhưng chạy được ngay và không tốn tiền.
Nó là cách nhanh nhất để biết một work package có gỡ được ca nào của bộ giám
khảo hay không.

```python
# PYTHONPATH=src PYTHONIOENCODING=utf-8 python <file>
import re, pathlib
from gladiators.runtime_factory import create_runtime

source = pathlib.Path("scripts/bgk_groundtruth.py").read_text(encoding="utf-8")
cases = re.findall(r'add\("(bgk\d\d)",\s*"[A-D]",\s*\n?\s*"(.+?)",', source, re.S)
missed_on_23_08 = {"bgk02", "bgk04", "bgk05", "bgk06",
                   "bgk08", "bgk09", "bgk11", "bgk12", "bgk20"}
runtime = create_runtime("offline")
for case_id, question in cases:
    response = runtime.run(question)
    flag = "BỎ LỠ 23/08" if case_id in missed_on_23_08 else ""
    print(f"{case_id} | {response.gate.action:8} | {response.gate.rule_id:22} | "
          f"{flag:12} | {question[:56]}")
```

✅ Kết quả 28/08: **4 đúng · 7 từ chối đúng · 9 bỏ lỡ**, và chín ca bỏ lỡ đúng là
chín ca của 23/08. Giá trị của bốn ca đúng cũng không đổi: `bgk01` = 10,
`bgk03` = 577, `bgk07` = 474, `bgk10` = 577/91.

### 21.11. Ground truth BGK-20

```python
import pandas as pd

products = pd.read_csv("data/processed/products_clean.csv")
snapshots = pd.read_csv("data/processed/product_snapshot_metrics.csv")
vn = products[(products.country_code == "vn") & (products.date == "2026-07-03")]
idn = products[(products.country_code == "id") & (products.date == "2026-07-03")]
svn = snapshots[(snapshots.country_code == "vn") & (snapshots.date == "2026-07-03")]

print("bgk02", svn.price_num.median())                                   # 132000.0
print("bgk04", vn.images_count.median())                                 # 6.0
print("bgk05", int((vn.discount_percent_num > 50).sum()))                # 8
print("bgk06", idn.rating_num.median())                                  # 4.901304084208852
print("bgk08", idn.groupby("shop_id").product_listing_key.nunique().idxmax())  # 809769142
print("bgk11", round(100 * vn.discount_percent_num.notna().mean(), 2))   # 96.26
print("bgk12", vn.liked_count_num.max(),
      int((vn.liked_count_num == vn.liked_count_num.max()).sum()))       # 10449.0, 1
```

### 21.12. Xác nhận source chưa đổi kể từ mốc đo

Mọi phép so "trước/sau" chỉ có nghĩa khi biết source có đổi hay không.

```powershell
git log --oneline -3
git diff --stat d14fa75 HEAD -- src/    # rỗng = source không đổi
git status --short src/ tests/ eval/    # rỗng = cây làm việc sạch ở ba thư mục đó
```

✅ 28/08: cả ba đều rỗng ⇒ các report 27/08 và 28/08 đứng trên cùng một source,
nên chúng **phải** trùng nhau, và việc chúng trùng nhau không nói gì về chất
lượng — nó chỉ xác nhận phép đo tái lập được.


### 21.13. Vá tạm một work package rồi chạy end-to-end — cách lấy bằng chứng §18.3

Đây là cách rẻ nhất để biết một work package có **thật sự** gỡ được ca nào,
**trước** khi viết code thật. Nó trả lời câu mà mọi phép kiểm ở tầng plan không
trả lời được: *bốn lớp kiểm có chấp nhận câu trả lời không.*

**Luật dùng:** file này là **phép thử một chiều, dùng xong bỏ**. Nó vá internal
theo tên (`open_planner._synthesis_beats_template`, `workflow.score_plan`), nên
nó sẽ hỏng ngay khi code đổi — và đó là chủ ý: một probe sống lâu sẽ biến thành
một bản cài đặt thứ hai của cùng một luật. **Không commit vào `scripts/`.**

```python
# PYTHONPATH=src PYTHONIOENCODING=utf-8 python probe.py
import gladiators.agent                      # nạp trước, tránh import vòng
from gladiators.planner import open_planner, synthesizer as synth_mod
from gladiators.planner.query_ir import LogicalQueryPlan, PlanNode
from gladiators.planner.risk import QueryRiskResult, score_plan as real_score_plan
from gladiators.agent import workflow as wf
from gladiators.domain.catalog import CATALOG

_AGG_CUE = (("trung vi", "median"), ("median", "median"), ("trung binh", "mean"),
            ("binh quan", "mean"), ("tong cong", "sum"), ("cong lai", "sum"))

def requested_aggregation(request):
    return next((agg for cue, agg in _AGG_CUE
                 if cue in request.normalized_question), None)

def wants_scalar_aggregate(request):
    return requested_aggregation(request) is not None and request.ranking is None

# W5.3 — mở cổng cho synthesizer
_real_beats = open_planner._synthesis_beats_template
def patched_beats(request):
    return True if wants_scalar_aggregate(request) else _real_beats(request)

# W5.2 — phát node Aggregate; W5.1 — phép tính chưa chứng nhận thì TỪ CHỐI
_real_synth = synth_mod.synthesize
def patched_synthesize(request, country):
    result = _real_synth(request, country)
    if result is None or not wants_scalar_aggregate(request):
        return result
    plan = result.plan
    if any(node.op == "Aggregate" for node in plan.nodes):
        return result
    measure_ref, agg = plan.plan_id.split(":")[1], requested_aggregation(request)
    if agg not in CATALOG[measure_ref].valid_aggregations:
        return None
    keep = [node for node in plan.nodes if node.op != "Project"]
    keep.append(PlanNode(
        node_id="n4", op="Aggregate", inputs=(keep[-1].node_id,), refs=(measure_ref,),
        group_by=(), aggregation=agg, input_grain="listing_snapshot",
        output_grain="country_snapshot", expected_schema=plan.requested_output_shape,
        expected_cardinality="1",
    ))
    return type(result)(
        plan=LogicalQueryPlan(
            plan_id=plan.plan_id, time_scope=plan.time_scope, output_node="n4",
            requested_output_shape=plan.requested_output_shape, nodes=tuple(keep),
        ),
        grammar_path=result.grammar_path, aggregation=agg,
        dimensions=result.dimensions, relations=result.relations,
    )

# W7 — vị từ tất định thay thang leo thang
def patched_score_plan(plan, **kwargs):
    result = real_score_plan(plan, **kwargs)
    if result.allowed or not str(plan.plan_id).startswith(("synth:", "analytical:", "open:")):
        return result
    from gladiators.planner.validator import validate_plan
    from gladiators.domain.relations import RELATIONS
    if not validate_plan(plan).valid:
        return result
    joins = [node for node in plan.nodes if node.op == "Join"]
    if any(node.relation not in RELATIONS for node in joins) or len(joins) > 3:
        return result
    fanout = [node for node in joins if RELATIONS[node.relation].fanout_effect != "none"]
    if fanout and not any(node.op == "Dedupe" for node in plan.nodes):
        return result
    return QueryRiskResult(result.score, result.factors, result.requested_mode,
                           "single", True, "Plan tat dinh dat vi tu chap nhan (probe).")

open_planner._synthesis_beats_template = patched_beats
wf._synthesis_beats_template = patched_beats
open_planner.synthesize = synth_mod.synthesize = wf.synthesize = patched_synthesize
wf.score_plan = patched_score_plan
```

**Chiều nghịch — bắt buộc chạy, và bắt buộc chạy HAI lần.** Một probe chỉ báo
"gỡ được N ca" mà không báo "phá M ca" là một probe nói dối bằng cách im lặng:

```python
import json, pathlib, sys

SUITES = {
    "independent44": "eval/independent/answerable_manual.json",
    "p0_probes":     "eval/p0_probes.json",
    "questions":     "eval/questions.json",
    "boundaries":    "eval/questions_boundaries.json",
    "counting":      "eval/questions_counting.json",
    "ambiguity":     "eval/questions_ambiguity.json",
}

def load(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("cases", [])

mode = sys.argv[1]                       # "base" | "patched"
if mode == "patched":
    import probe                         # áp bản vá qua side effect
from gladiators.runtime_factory import create_runtime

runtime = create_runtime("offline")
snapshot = {}
for name, path in SUITES.items():
    rows = {}
    for case in load(path):
        if not case.get("question"):
            continue
        response = runtime.run(case["question"])
        rows[case["id"]] = (
            response.gate.action, response.gate.rule_id,
            tuple(round(float(e.value), 4) for e in response.evidence
                  if isinstance(e.value, (int, float)) and not isinstance(e.value, bool)),
        )
    snapshot[name] = rows
pathlib.Path(f"probe_{mode}.json").write_text(
    json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
)
```

Rồi diff hai file. ✅ Kết quả 28/08 ghi ở §18.3: **8 ca đổi trên bộ 44 (đúng
ans031–ans038), 1 ca đổi trên P0 (đúng ca §8.6 dự đoán), 0 ca đổi trên 76 câu
golden.**

✅ Cùng thủ tục này cho ra bằng chứng W13 ở §14.8: vá `compiler.py` +
`executor.py`, chạy §21.14(c), §21.14(d) và `pytest -q`, rồi **hoàn nguyên**.
Kết quả 29/08: `CRASH` 24 → 0 · `/ask` 500 → 200 · `1207 passed, 1 skipped` ·
baseline 0 entry đổi.

### 21.14. Chạy mọi suite có nhãn, và phép quét xếp hạng (§1.6)

Hai lệnh dưới là nguồn của toàn bộ §1.6. Chạy sau §21.2.

**(a) Mọi bộ đề có `expected_action`:**

```python
# PYTHONPATH=src PYTHONIOENCODING=utf-8 python <file>
import json, pathlib
from gladiators.runtime_factory import create_runtime

runtime = create_runtime("offline")
suites = ["eval/independent/answerable_manual.json", "eval/questions.json",
          "eval/questions_v2.json", "eval/questions_schema.json",
          "eval/questions_counting.json", "eval/questions_boundaries.json",
          "eval/questions_a19.json", "eval/questions_ambiguity.json",
          "eval/questions_critic.json", "eval/dr2607.json"]
for path in suites:
    cases = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    bad = []
    for case in cases:
        if not case.get("question"):
            continue                      # ca fixture-only của questions_external
        expected = case.get("expected_action")
        if expected is None:
            continue                      # DR-40 để trống 19 ca có chủ đích
        response = runtime.run(case["question"])
        allowed = case.get("allowed_rule_ids") or []
        forbidden = case.get("forbidden_rule_ids") or []
        ok = (response.gate.action == expected
              and (not allowed or response.gate.rule_id in allowed)
              and response.gate.rule_id not in forbidden)
        if not ok:
            bad.append((case["id"], expected, response.gate.action, response.gate.rule_id))
    print(f"{path:44s} lệch={len(bad)}")
    for row in bad:
        print("   ", row)
```

✅ Kết quả 29/08: `answerable_manual` **19** · `questions_critic` **3** · tất cả
những suite còn lại **0**.

**(b) Suite multiturn — chưa có harness, chạy tay cho tới W15.1:**

```python
import json, pathlib
from gladiators.runtime_factory import create_runtime

runtime = create_runtime("offline")
fails = 0
for case in json.loads(pathlib.Path("eval/questions_multiturn.json").read_text(encoding="utf-8")):
    for turn in case["turns"]:
        response = runtime.run(turn["question"], session_id=case["session_id"])
        if turn.get("expected_action") and response.gate.action != turn["expected_action"]:
            fails += 1
            print(case["id"], response.gate.rule_id, "|", turn["question"])
print("lượt lệch:", fails)
```

✅ Kết quả 29/08: **6/48** — `mt005` `mt011` `mt017` `mt023` `A19-PLAN`;
`mt016` `mt022` `A22-ALIGN-RANK-TIE`.

**(c) Phép quét xếp hạng 84 câu — nguồn của §1.6.3 và của nghiệm thu W13:**

```python
import itertools
from collections import Counter
from gladiators.runtime_factory import create_runtime

runtime = create_runtime("offline")
sweep = [
    f"{subject} nào có {measure} {direction} {market}?"
    for subject, measure, direction, market in itertools.product(
        ["Listing", "Sản phẩm", "Mặt hàng"],
        ["giá", "giá gốc", "điểm đánh giá", "số lượt đánh giá",
         "số lượt thích", "số ảnh", "phần trăm giảm giá"],
        ["cao nhất", "thấp nhất"],
        ["tại Việt Nam", "tại Indonesia"],
    )
]
counts = Counter()
for question in sweep:
    try:
        response = runtime.run(question)
        counts[f"{response.gate.action}/{response.gate.rule_id}"] += 1
    except Exception as exc:                      # noqa: BLE001 — đo đúng cái này
        counts[f"CRASH:{type(exc).__name__}"] += 1
        print("CRASH", question)
print(dict(counts))
```

✅ Kết quả 29/08 trên source hiện tại: `CRASH:ExecutionFailure` **24** ·
`clarify/A22-ALIGN-MEASURE` 18 · `allow/A-ALLOW` 14 · `abstain/A19-PLAN` 14 ·
`abstain/A22-ALIGN-RANK-TIE` 14.
✅ Với bản vá W13.1+W13.2 (thủ tục §21.13): `CRASH` **0** ·
`abstain/A22-ALIGN-RANK-TIE` 32 · `allow/A-ALLOW` 20 ·
`clarify/A22-ALIGN-MEASURE` 18 · `abstain/A19-PLAN` 14.

**(d) Xác nhận HTTP 500 qua route thật:**

```python
from fastapi.testclient import TestClient
from gladiators.api import app

client = TestClient(app, raise_server_exceptions=False)
print(client.post("/ask", json={"text": "Listing nào có giá thấp nhất tại Việt Nam?"}).status_code)
# ✅ 29/08: 500  {"detail": {"code": "AGENT_RUNTIME_ERROR", "type": "ExecutionFailure"}}
# ✅ với bản vá W13: 200, action=allow, giá trị 1000
```

### 21.15. Giá trị không phải phép đo (§15)

```python
import pandas as pd

P = pd.read_csv("data/processed/products_clean.csv", low_memory=False)
S = pd.read_csv("data/processed/product_snapshot_metrics.csv", low_memory=False)

def repdigit_nine(value, min_digits=7):
    if pd.isna(value):
        return False
    number = float(value)
    if number <= 0 or number != int(number):
        return False
    text = str(int(number))
    return len(text) >= min_digits and set(text) == {"9"}

flag = S.price_sentinel_flag.astype(str).str.lower().isin(("true", "1"))
print("cờ hiện hành bắt   :", int(flag.sum()))                        # ✅ 3
print("luật repdigit bắt  :", int(P.price_num.apply(repdigit_nine).sum()))          # ✅ 9
print("price_original     :", int(P.price_original_num.apply(repdigit_nine).sum())) # ✅ 12

idn = P[(P.country_code == "id") & (P.date == "2026-07-03")].drop_duplicates("product_listing_key")
print("max thô            :", idn.price_num.max())                                  # ✅ 999999999
print("max sau < 1e9      :", idn[idn.price_num < 999999999].price_num.max())       # ✅ 9999999
print("max sau cả hai lớp :", idn[~idn.price_num.apply(repdigit_nine)].price_num.max())  # ✅ 1135000

for country in ("vn", "id"):
    day = P[(P.country_code == country) & (P.date == "2026-07-03")].drop_duplicates("product_listing_key")
    zero = day.rating_num == 0
    print(country, "rating==0:", int(zero.sum()),
          "| trong đó rating_count==0:", int((zero & (day.rating_count_num == 0)).sum()),
          "| median mọi dòng:", day.rating_num.median(),
          "| median bỏ dòng chưa ai đánh giá:", day[day.rating_count_num > 0].rating_num.median())
# ✅ vn 43 43 4.923603693479375 4.928571428571429
# ✅ id 17 17 4.901304084208852 4.902690838143241
```

Và con số W5 **sẽ** trả nếu thiếu W14:

```python
import duckdb, pandas as pd

connection = duckdb.connect()
connection.register("products", pd.read_csv("data/processed/products_clean.csv", low_memory=False))
query = """SELECT MAX(price_num) FROM (SELECT * FROM products
           WHERE country_code='id' AND date='2026-07-03' AND price_num < {})"""
print(connection.execute(query.format(999999999)).fetchone())   # ✅ (9999999.0,)
print(connection.execute(query.format(9999999)).fetchone())     # ✅ (1135000.0,)
```

### 21.16. Bộ đề nào có người chấm (§16.1)

```bash
# Suite khai expected_action
python - <<'EOF'
import glob, json, pathlib
for path in sorted(glob.glob("eval/**/*.json", recursive=True)):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        continue
    items = data if isinstance(data, list) else data.get("cases")
    if not isinstance(items, list):
        continue
    hit = sum("expected_action" in json.dumps(c) for c in items if isinstance(c, dict))
    if hit:
        print(f"{path:46s} ca={len(items):3d} khai expected_action={hit}")
EOF

# Ai đọc chúng
rg -l questions_critic tests scripts src
rg -l questions_multiturn tests scripts src
rg -n expected_action tests/*.py
```

✅ 29/08: **14 file · 240 ca**. `questions_multiturn` chỉ được chính
`scripts/build_multiturn_suite.py` nhắc tới. `questions_critic` được hai test
đọc làm **đầu vào**; `rg expected_action tests/` chỉ thấy
`test_dr2607_regression.py:37` và bộ dựng của `test_eval_metrics.py`.

---

## §22. Thứ tự tin cậy

**code đang chạy > test/eval thực chạy > tài liệu kiến trúc > mô tả viết tay**

Tài liệu này thuộc nhóm ba: nó mô tả thay đổi **sẽ** làm. Mọi con số ✅ trong nó
đến từ nhóm một và nhóm hai, và mỗi con số có lệnh tái lập ở §21. Chỗ nào nó mâu
thuẫn với một lần chạy thật thì **lần chạy thật đúng**, và tài liệu phải được sửa
— không phải ngược lại.

Khi một work package xong, `docs/Archi2808.md` phải được cập nhật theo checklist
§0.3 **trước** khi work package tiếp theo bắt đầu. Một tài liệu kiến trúc trễ một
work package là một tài liệu mô tả một hệ không còn tồn tại.
