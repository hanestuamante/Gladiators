# finalarchi — Kiến trúc Gladiators sau khi thi công Spec3008

> **Trạng thái: PHA TRỘN, và chỗ nào là chỗ nào thì phải đọc kỹ.** §1–§30 viết
> khi Spec3008 (W16–W31) còn là TARGET — chúng mô tả hệ **sẽ** thành gì, và ghi
> **[ĐANG CHẠY]** cho cơ chế đã có, **[W-nn]** cho cơ chế Spec3008 thêm.
>
> **§31–§34 thêm ngày 01/09/2026 và mô tả hệ ĐANG CHẠY**, mỗi khẳng định kèm số
> đo được và câu lệnh sinh ra nó. Phần lớn W16–W31 nay đã thi công; nếu một mục
> ở §1–§30 mâu thuẫn với §31–§34 thì §31–§34 mới hơn.
>
> Thứ tự tin cậy khi mâu thuẫn (CLAUDE.md §7):
> **code đang chạy > test/eval thực chạy > tài liệu kiến trúc > narrative.**
> Tài liệu này nằm ở bậc ba. Nếu nó mâu thuẫn với code, code đúng và tài liệu
> này sai.

| Tài liệu | Vai trò |
| --- | --- |
| `docs/Archibefore2208.md` | Kiến trúc trước SolutionSpec2808 — nền lịch sử |
| `docs/SolutionSpec2808.md` | W1–W15, đã thi công |
| `docs/Spec3008.md` | W16–W31 — phần lớn **đã** thi công (xem §31–§34) |
| `docs/qa/raw_extra_data_provenance.md` | Mọi quyết định của bước nối bộ 20 ngày |
| **`docs/finalarchi.md`** | **Hệ sau khi Spec3008 xong — tài liệu này** |

---

# Phần I — Hệ này là gì

## §1. Mệnh đề nền

Hệ trả lời câu hỏi phân tích thương mại điện tử (VN + ID) từ một **bản dữ liệu đã
đóng băng**, dưới một ràng buộc duy nhất và tuyệt đối:

> **Mọi con số hiển thị phải truy vết được về evidence, và hệ không bao giờ được
> đoán.**

Hệ quả trực tiếp, và đây là chỗ kiến trúc khác một chatbot SQL:

1. **Từ chối là một câu trả lời đúng.** `clarify` và `abstain` không phải lỗi.
2. **Một câu trả lời trôi chảy và sai nguy hiểm hơn không có câu trả lời.** Mọi
   lớp kiểm tồn tại để chặn đúng thứ đó.
3. **LLM không tính số và không quyết định gate.** Nó chỉ đoán ý định, sinh IR,
   sinh truy vấn tìm kiếm, trích span, và diễn giải câu chữ — mỗi output đều qua
   một validator tất định trước khi được phép ảnh hưởng bất cứ gì.

## §2. Bốn câu hỏi mà bốn lớp khác nhau trả lời

Đây là trục tổ chức của toàn bộ kiến trúc. Nhầm lớp là lỗi thiết kế, không phải
lỗi một ca.

| Lớp | Câu hỏi | Module | Chạy khi nào |
| --- | --- | --- | --- |
| **Gate** | *Được phép trả lời không?* | `agent/gate.py` | trước khi lập kế hoạch, và lại sau khi có câu trả lời |
| **Alignment (A22)** | *Có đang trả lời **đúng câu hỏi** không?* | `agent/alignment.py` | sau khi có plan, evidence, và answer |
| **Verifier** | *Số hiển thị có evidence không?* | `agent/verifier.py` | sau khi sinh câu trả lời |
| **Density (W29)** | *Dữ liệu có **đủ** để phát biểu điều này không?* | `analytics/tools.py` | **[W29]** giữa compile và execute |

Lỗi TC29/TC39 lọt vì gate cho phép ✓, verifier pass ✓, nhưng hệ trả `474 listing`
cho một câu hỏi về mức giảm giá — A22 sinh ra để lấp đúng khe đó.

Lỗi `median rating = 4.93 trên 5 quan sát` (Spec3008 §1.5.2) lọt qua **cả ba**
lớp trên — W29 sinh ra để lấp khe thứ hai, và nó là khe mà bộ dữ liệu 20 ngày mở
ra.

---

# Phần II — Mô hình dữ liệu

## §3. Bản dữ liệu

### 3.1. Hai bản, và quan hệ giữa chúng

| | bộ đóng băng | bộ 20 ngày |
| --- | ---: | ---: |
| snapshot | 3 (01–03/07/2026) | 20 (01–21/07/2026, **thiếu 12/07**) |
| dòng | 3.341 | 22.695 |
| listing | 1.157 | 1.276 |
| shop | 20 | 20 |
| thị trường | vn, id | vn, id |
| panel ngày cấp shop | không | **396 dòng** |
| `dataset_version` | `27de9bff184f4f89` | dựng lại từ nội dung |

Ba ngày chồng lấn **tái lập chính xác**: 1055/1144/1142 listing, giá khớp tới
từng đồng, `catid` khớp 100%. Đây là bằng chứng bước nối đúng, và nó là lý do
89/100 ca benchmark giữ nguyên oracle.

### 3.2. Grain

- Grain nhỏ nhất của listing: **product listing** = `{country}:{shop_id}:{item_id}`.
  **Không có SKU.**
- Grain quan sát: **listing-snapshot** = `{listing}:{date}`.
- **[MỚI]** Grain shop theo ngày: **shop-snapshot** = `{country}:{shop_id}:{date}`.
  Nó **trực giao** với listing-snapshot; trộn hai grain trong một `Aggregate` bị
  `validate_plan` từ chối (`grain_mismatch`).

### 3.3. Artifact

Tám artifact, khai một chỗ ở `domain/tables.py::ArtifactName` **[ĐANG CHẠY]**:

| artifact | grain | bắt buộc |
| --- | --- | --- |
| `products_clean.csv` | country, shop, item, date | ✓ |
| `product_snapshot_metrics.csv` | country, shop, item, date | ✓ |
| `product_transition_metrics.csv` | country, shop, item, previous_date, date | ✓ |
| `shop_info_clean.csv` | country, shop | ✓ |
| `category_list_clean.csv` | country, shop, shop_category, date | ✓ |
| `product_categories_clean.csv` | country, shop, item, category, date | ✓ |
| `category_platform_clean.csv` | country, category | ✓ |
| **`shop_stats_clean.csv`** | country, shop, date | **tuỳ chọn** |

**Tầng artifact tuỳ chọn [ĐANG CHẠY]:** `OPTIONAL_ARTIFACTS` khai artifact có thể
vắng mặt mà bản dữ liệu vẫn hợp lệ. Vắng mặt là một trạng thái **đọc được**:

- `build_table_registry` cho nó vào registry với **0 cột** — không bỏ khỏi
  registry (bỏ đi thì consumer phải hỏi "artifact này tồn tại không" bằng
  `KeyError`, tức lại một danh sách artifact thứ hai).
- `QueryExecutor` **không** đăng ký view cho nó — đăng ký một frame rỗng sẽ khiến
  mọi truy vấn trả "0 dòng", tức *"đo được và không có gì"*.
- `compile_plan(available_sources=…)` chặn plan đọc nó.
- `compute_dataset_version` băm nó **chỉ khi có mặt** — bản không có nó giữ
  nguyên version cũ; bản có nó không thể trùng version với bản không có.

### 3.4. **[W29]** Chế độ quan sát — trục thứ hai của mô hình dữ liệu

Catalog khai *một measure đo cái gì*. Nó **chưa** khai *nó được quan sát như thế
nào*. Trên bộ 3 ngày hai thứ đó trùng nhau; trên bộ 20 ngày chúng tách hẳn:

| mode | measure | mật độ mỗi ngày |
| --- | --- | ---: |
| `panel` | `price`, `price_original`, `images_count`, `vouchers_count`, `promotion_*` | 100% × 20 ngày |
| `point_in_time` | `rating`, `rating_count`, `liked_count`, `monthly_sold`, `history_sold`, `discount_percent` | ~5% tổng thể; 100% tại **đúng một** ngày mỗi listing |
| `derived` | `estimated_recent_revenue`, mọi `derived.*` | kế thừa mode **chặt nhất** trong đầu vào |

Nguồn sự thật: `<data_root>/observation_density.json`, dựng bởi
`scripts/build_observation_density.py` cùng lúc với bản dữ liệu. **Đo được, không
viết tay.** Cột `attributes_observed` trong `products_clean.csv` đánh dấu dòng
nào mang quan sát trạng thái.

**Vì sao đây là một khái niệm kiến trúc chứ không phải một chi tiết dữ liệu:**
`median rating vn 03/07` = 4,9236 trên 668 quan sát (bộ cũ) và 4,9300 trên **5**
quan sát (bộ mới). Cả hai qua gate ✓, compiler ✓, executor ✓, evidence ✓,
verifier ✓, A22 ✓. Không có gì trong hệ **trước W29** phát biểu được rằng con số
thứ hai là một mẫu 0,4%.

### 3.5. Proxy và cạm bẫy đã biết

- `monthly_sold` là **proxy hiển thị của một cửa sổ chưa xác nhận** — **cấm cộng
  qua các snapshot** (tính trùng). Trên 20 snapshot, cộng nhầm nhân sai số lên 20
  lần thay vì 3. **[W26-R4]** luật này chuyển từ synthesizer sang **validator**.
- `estimated_recent_revenue` là ước tính, luôn phải kèm chữ "ước tính".
- `discount_percent` là **số Shopee hiển thị**, khớp `round((1−p/p₀)·100)` ở
  2.995/3.034 nhưng lệch ở 39 ca ⇒ **không suy được**.
- Zero-variance đã biết: `is_ad_bool`, `is_sold_out_bool` đều `False` toàn bộ ⇒
  không phân tích được, chỉ nói được "dataset không quan sát được".
- Sentinel giá `999_999_999` (23 dòng ở bộ mới) — loại khỏi cực trị theo mặc
  định, khai `sentinel_excluded=True` trong evidence.

## §4. **[W30]** Lịch snapshot

Cửa sổ ngày **là dữ liệu**, không phải hằng số. Trước W30 nó được viết thẳng vào
**45 chỗ / 13 file**.

```python
# domain/calendar.py
@dataclass(frozen=True)
class SnapshotCalendar:
    dates: tuple[str, ...]        # CHỈ ngày có đợt thu
    gaps:  tuple[str, ...]        # ngày lịch trong [first,last] KHÔNG có đợt thu
    listing_count: int
    row_count: int

    def first(self) -> str
    def last(self) -> str
    def contains(self, iso) -> bool      # có đợt thu
    def in_range(self, iso) -> bool      # trong [first,last], kể cả gap
    def is_gap(self, iso) -> bool
    def boundary_pair(self) -> tuple[str, str]
```

Lịch đo từ bản dữ liệu lúc build và ghi vào `DATASET_VERSION.json.calendar`.

**Ba trạng thái của một ngày, không phải hai:**

| trạng thái | ví dụ (bộ 20 ngày) | xử lý |
| --- | --- | --- |
| có đợt thu | 04/07 | trả lời bình thường |
| **gap** — trong kỳ, không có đợt thu | **12/07** | `A-SNAPSHOT-GAP`, abstain |
| ngoài cửa sổ | 30/06, 25/07 | `A-SNAPSHOT-SCOPE`, abstain |

Gộp gap vào "ngoài cửa sổ" sẽ nói với người dùng rằng dữ liệu chỉ có tới 11/07 —
sai. Nội suy gap sang ngày lân cận là `LATEST_SNAPSHOT` mặc một cái áo khác.

---

# Phần III — Tầng ngữ nghĩa

## §5. Catalog

**102 semantic object / 440 alias / 36 metric** ở `domain/catalog.py` và
`domain/metrics.py` (đo ngày 01/09/2026; con số này đổi theo mỗi lần thêm ref,
nên đọc bằng lệnh chứ đừng tin bản in: `len(CATALOG)`, `len(METRICS)`).
Mọi câu hỏi phải rơi vào tập này hoặc bị từ chối — đây là lý do bài toán hữu
hạn hoá được.

Hai chốt chặn LÚC IMPORT giữ tập này không tự mâu thuẫn, và cả hai đã bắt lỗi
thật khi `derived.observed_day_count` được thêm ngày 01/09:

* `CatalogError` — ref đếm một đơn vị mà đơn vị đó chưa khai `counting_key`;
* `TopicRegistryError` — ref không thuộc topic nào.

Thêm một ref mà quên một trong hai thì hệ **không khởi động được**, chứ không
phải trả lời sai lúc chạy.

### 5.1. Cấu trúc một `CatalogObject`

```python
ref              # "measure.price", "dim.brand", "entity.shop", "derived.product_count"
kind             # measure | dimension | entity | derived_metric
aliases          # cách gọi trong VI/ID/EN
physical         # ("<artifact>.<column>", …)  — có thể RỖNG với entity
type, unit, grain
aggregations     # SUY RA từ additivity  [W26]
time             # per_snapshot | static_latest | transition
filters          # eq, in, lt, lte, gt, gte
answerability    # exposed_as_dimension | exposed_as_measure | proxy_only | …
source_tier      # btc_dataset (khoá cứng cho mọi analytical)
analysis_role    # physical_dimension | computed_value | analysis_unit
counting_key     # cột cho COUNT(DISTINCT …) khi role == analysis_unit
observation_mode # panel | point_in_time | derived        [W29]
additivity       # additive|ordinal|snapshot_stock|ratio|count|proxy_window|observed_once  [W26]
groupable        # False cho dim.item_id                   [W24]
```

**Ba luật build-time**, fail ở import:

1. `answerability == exposed_as_dimension` và `analysis_role != analysis_unit`
   ⇒ `physical` phải khác rỗng. **[ĐANG CHẠY]**
2. `analysis_role == analysis_unit` ⇒ `counting_key` phải set. **[ĐANG CHẠY]**
3. `valid_aggregations` suy ra từ `additivity`; khai cả hai mà lệch ⇒ fail. **[W26]**

### 5.2. Họ measure theo grain

| grain | measure | artifact |
| --- | --- | --- |
| `listing_snapshot` | `price`, `discount_percent`, `rating`, `liked_count`, `monthly_sold`, … | products, snapshot_metrics |
| `shop` (static_latest) | 9 × `measure.shop_*` | shop_info |
| **`shop_snapshot`** | 11 × `measure.shop_daily_*` | **shop_stats (tuỳ chọn)** |

`measure.shop_rating` (ảnh chụp tĩnh) và `measure.shop_daily_rating` (theo ngày)
là **hai ref riêng**, có chủ đích: *"điểm shop hôm nay"* và *"điểm shop tại ngày
d"* trả lời hai câu hỏi khác nhau. Đặt chung một ref sẽ khiến một câu hỏi theo
thời gian được trả bằng một con số tĩnh mà không ai thấy.

## §6. Relation registry

**11 relation** ở `domain/relations.py`, mỗi cái khai `cardinality`,
`fanout_effect`, `dedupe_strategy`, `temporal_validity`, `path_cost`, `risk`, và
một `RelationBinding` vật lý (`inline` hoặc `left_join`).

| relation | trái → phải | kiểu | ghi chú |
| --- | --- | --- | --- |
| `belongs_to` | ProductListing → Shop | left_join | `static_latest_only` — **không** phải thuộc tính đồng thời từng ngày |
| `observed_at` | ProductListing → DateSnapshot | inline | |
| **`shop_observed_at`** | Shop → DateSnapshot | inline | **panel ngày cấp shop** |
| `in_platform_category` | ProductListing → PlatformCategory | left_join | |
| `in_shop_category` | ProductListing → ShopCategory | left_join | **N:M**, `dedupe=one_row_per_listing` |
| `has_sales_metric` | ProductListing → SalesMetric | left_join | |
| 5 relation inline khác | | inline | |

`belongs_to` và `shop_observed_at` là hai chiều khác nhau của cùng một thực thể:
cái đầu gắn một **ảnh chụp tĩnh** của shop vào listing; cái sau **là** thuộc tính
từng ngày. Dùng nhầm chiều nào cũng ra một câu trả lời trôi chảy.

## §7. Table registry và binding layer

`domain/tables.py` + `domain/bindings.py` **[ĐANG CHẠY]**. Một nguồn duy nhất cho
"artifact nào tồn tại"; trước đó bốn consumer mỗi cái giữ một danh sách.

```
semantic_coverage_manifest.json  ──┐
                                   ├──► build_table_registry ──► TableSpec[]
TABLE_DECLARATIONS (hằng thuần) ───┘                                │
                                                                    ▼
CATALOG + RELATIONS + METRICS + INVARIANTS ──► validate_metadata_bindings
                                                                    │
                                                    MetadataBindingSnapshot
                                              (table_hash, catalog_hash, …, binding_hash)
```

Fail-closed ở mọi lệch: thiếu declaration, thiếu manifest entry, view trùng, cột
trùng, quality handler không resolve, binding trỏ cột không tồn tại.

**Ngoại lệ duy nhất, được khai:** binding trỏ vào một artifact **tuỳ chọn chưa
thu** không phải lỗi. *"Chưa thu"* khác *"khai sai"* — chặn nó sẽ khiến một năng
lực mới chỉ khai được sau khi mọi bản dữ liệu cũ được thu lại.

## §8. Topic registry

9 topic domain + topic phụ trợ, `domain/topics.py`. Ràng buộc C3: **4 ≤ ref ≤ 20**
mỗi topic domain. `T9 SHOP_DAILY_PANEL` tách khỏi `T5 SHOP_PROFILE` vì gộp lại
chạm trần 20 ref — và vì một câu hỏi theo thời gian không được trả bằng một con
số tĩnh.

Topic routing chạy **shadow**: ghi verdict, **không** đổi câu trả lời.

---

# Phần IV — Luồng chạy

## §9. Mười một chặng

```
câu hỏi thô
 │
 ├─ S0  ledger        planner/spans.py          → BindingLedger          [W16]
 │                    tokenize → lattice → mọi binder CLAIM span
 │
 ├─ S1  parse         agent/parser.py           → StructuredRequest
 │                    ├─ frames                 planner/frames.py        [W17]
 │                    ├─ value bind             agent/value_probe.py     [W18/W19]
 │                    ├─ dates                  planner/dates.py         [W20/W30]
 │                    ├─ premise                domain/polarity.py       [W21]
 │                    └─ entity                 agent/entity_extract.py  [W28-B]
 │
 ├─ S1.5 memory       agent/conversation.py     → điền ô TRƯỚC analytical parse [W27-R4]
 │
 ├─ S2  route         external/router.py        → internal|hybrid|external|clarify|abstain
 ├─ S3  entity        agent/entity_resolution.py→ ID → tên → fuzzy → BGE; margin thấp ⇒ clarify
 ├─ S4  gate-pre      agent/gate.py             → allow | clarify | abstain
 │                    phase 1 đọc ledger.significant()                   [W22]
 │                    phase 1 đọc artifact availability                  [W31]
 │
 ├─ S5  plan          luôn thử synthesizer TRƯỚC, cả hai nhánh intent    [W23]
 │        ├─ synthesize()      planner/synthesizer.py
 │        ├─ template/macro    planner/analytical.py, macros.py
 │        └─ open_planner      chỉ khi có provider
 │
 ├─ S6  validate      planner/validator.py      → PlanValidationResult
 ├─ S7  compile       planner/compiler.py       → CompiledQuery (SQLGlot, SELECT-only)
 │
 ├─ S7.5 density      analytics/tools.py        → coverage(scope) vs ngưỡng [W29]
 │                    ⇒ clarify A-SPARSE-OBSERVATION nếu quá thưa
 │
 ├─ S8  execute       planner/executor.py       → DuckDB read-only
 ├─ S9  evidence      contracts.Evidence        + check_evidence_alignment
 ├─ S10 generate      workflow._generate        template tất định | LLM đọc ContextBundle
 └─ S11 verify+gate-out  verifier + check_answer_alignment
                      fail ⇒ A-VERIFICATION-FINAL
```

Hai chặng mới so với kiến trúc hiện tại: **S0** (ledger) và **S7.5** (density).

## §10. **[W16]** S0 — Binding Ledger

### 10.1. Vì sao tầng này tồn tại

Tầng binding **trước W16** là *N bộ khớp chuỗi con liền kề chạy độc lập trên một
chuỗi đã chuẩn hoá*, mỗi bộ giữ một danh sách cụm riêng, và **không bộ nào ghi
lại nó đã tiêu thụ gì, cũng không ai ghi lại phần còn dư**.

Năm hệ quả đo được:

1. **Cấu trúc rời không chạm tới được.** `bao nhiêu … ?`, `berapa banyak X`,
   `nhiều X nhất` là *circumfix*; bộ khớp liền kề cần một cụm cho mỗi
   (ngôn ngữ × khung × đơn vị) — một dãy vô hạn.
2. **Phần không khớp bị vứt không dấu vết.** Khi `Bibica` không bind được,
   request không có filter brand: plan khớp request, evidence khớp plan, answer
   khớp evidence, verifier xanh — **chuỗi nhất quán quanh một câu hỏi khác**.
3. **Lý do từ chối do thứ tự luật quyết định**, không do thứ đã chặn.
4. **Bộ lập kế hoạch tất định chỉ nằm trên một trong hai nhánh intent.**
5. **`clarify` là ngõ cụt** cho chính câu hỏi.

### 10.2. Hợp đồng

```python
# planner/spans.py
Token(index, normalized, raw, char_start, char_end, capitalized, quoted, numeric)
Span(start, end, normalized, raw)

Producer = Literal["alias","frame","value","qualifier","date","country",
                   "number","entity_id","function_word"]
BoundSpan(span, producer, ref, payload)

ResidualKind = Literal["proper_name","date_like","quantity_phrase",
                       "unknown_concept","grain_term","magnitude_claim","function_word"]
ResidualSpan(span, kind, evidence)

BindingLedger(tokens, bound, residual)
    .significant() -> tuple[ResidualSpan, ...]   # khác function_word — thứ W22 được nhìn
    .coverage()    -> float                      # khoá telemetry
    .claimed(start, end) -> bool
```

### 10.3. Bốn luật

- **R1 — chuẩn hoá theo TOKEN.** `Token.raw` và `char_start` luôn có, nên mọi câu
  hỏi hình thái (viết hoa? trong ngoặc? là số?) trả lời được tại chỗ. Trước đó
  `value_probe` phải quét lại `raw_question` bằng một regex thứ hai.
- **R2 — một token chỉ được claim MỘT lần**, span dài thắng span ngắn.
  `AliasIndex.find_in` **phải** đọc `ledger.claimed()` thay vì giữ chuỗi
  `residual` riêng — hai bản của một luật là cách chúng lệch nhau.
- **R3 — từ chức năng là registry** (`domain/function_words.py`), không phải ba
  set rời rạc như hôm nay.
- **R4 — phân loại phần dư là hàm TOÀN PHẦN.** Mỗi token không được claim nhận
  đúng một `ResidualKind`. `unknown_concept` là đáy.

### 10.4. Thứ tự claim — cố định, deterministic

```
1 quoted → 2 entity_id → 3 date → 4 country → 5 alias → 6 qualifier
→ 7 value → 8 frame → 9 number → 10 function_word → 11 residual
```

Value **sau** alias là điều làm việc xoá `MIN_VALUE_LENGTH` an toàn: `gia` trong
`gia tri` đã bị alias tiêu thụ và không còn là span dư. Frame **cuối cùng** vì nó
cần biết đâu là đơn vị/measure.

### 10.5. Telemetry

`planning_meta["ledger"] = {"coverage", "residual_kinds", "claims_by_producer"}`.
Không có khoá này thì *"ledger đã chạy"* và *"ledger chạy mà không claim gì"* là
hai bảng số giống hệt nhau.

## §11. **[W17]** Ngữ pháp khung

Đếm **không phải** một danh sách chuỗi; nó là một **quan hệ ngữ pháp** giữa một
*từ hỏi lượng* và một *đơn vị đếm được*.

```python
# planner/frames.py
FrameKind  = Literal["quantity","superlative","comparative","selector","aggregate"]
Attachment = Literal["prefix","suffix","circumfix","free"]
FrameMarker(surfaces, kind, language, attachment, polarity, measure_hint)
ResolvedFrame(marker, marker_span, argument_span, argument_ref, resolution, grain)
```

**Thuật toán phân giải** — độc lập ngôn ngữ:

```
với mỗi marker M theo thứ tự vị trí:
  hướng = phải nếu prefix, trái nếu suffix, cả hai nếu free
  quét trong CÙNG MỆNH ĐỀ (ranh giới: dấu phẩy, và/dan/and, dấu hỏi),
  bỏ qua INTENSIFIERS và function_word, dừng ở BoundSpan đầu tiên:
      ref ∈ COUNT_METRIC_BY_SURFACE_REF → count_metric
      ref.kind ∈ {measure, derived}     → measure
      ref.kind ∈ {dimension, entity}    → dimension
  không tìm được → unresolved + ResidualSpan(quantity_phrase)
```

**Tám luật:**

| luật | nội dung |
| --- | --- |
| R1 | hình thái số nhiều là **fallback** của alias (`shops` → `shop`), chỉ chạy khi khớp thẳng thất bại |
| R2 | quantity + count_metric ⇒ measure là metric đếm; đơn vị **rời khỏi** `requested_dimensions` |
| R3 | cue tổng hợp có đối số là **đơn vị đếm** ⇒ khung quantity, **không** phải phép cộng (`Tổng số listing` → count; `Tổng số lượt thích` → sum) |
| R4 | selector + dimension ⇒ chiều gom nhóm; superlative ⇒ ranking |
| R5 | comparative + hai giá trị cùng chiều ⇒ shape `comparison`, `in`-predicate |
| R6 | số **có đơn vị viết ra** cạnh một measure là ĐIỀU KIỆN, bất kể đơn vị gì (`5 triệu đồng` → `price gt 5000000`); số **trần** giữ nguyên: không bind |
| R7 | `tỷ lệ` / `bao nhiêu phần trăm` + điều kiện ⇒ metric **share**, không phải measure trong mệnh đề điều kiện |
| **R8** | khung trên measure panel phải khai **grain**; trộn `shop_snapshot` với `listing_snapshot` ⇒ `grain_mismatch` |

**Cái bị xoá:** `_normalise_count_frame`, `_COUNT_FRAME_VI/ID`, `_COUNTING_CUES`,
khối `count_candidates` với adjacency regex, hai bảng `descending`/`ascending`.
Tất cả là các bản riêng lẻ của **một** quan hệ.

## §12. **[W18/W19]** Bind giá trị và ngữ nghĩa vắng mặt

### 12.1. Ba điều kiện cấu trúc thay hai proxy sai

Trước W18, `bind_values` lọc bằng `ref in dimension_refs` (⇒ **vị trí trong câu**
quyết định một giá trị có bind hay không) và `len(name) < 6` (⇒ không phân biệt
được *chuỗi ngắn ngẫu nhiên* với *tên riêng ngắn*).

Sau W18, ứng viên là span **cực đại chưa bị claim** thoả **cả ba**:

1. **còn dư trên lattice** (alias đã chạy trước);
2. **hình dạng tên riêng** — `capitalized` hoặc `quoted` trên câu GỐC, **hoặc**
   khớp nguyên văn một khoá trong chỉ mục (vế này cho phép `bibica` viết thường);
3. **khớp chính xác theo token đã fold**, không fuzzy.

Ba luật: một span khớp ≥2 chiều ⇒ **ambiguity, không phải chọn**; hai span rời
nhau cùng chiều ⇒ hỏi W17 trước khi bỏ; **bind rồi thì chiều đó rời khỏi
grouping**.

### 12.2. Chỉ mục giá trị v3

```json
{
  "schema_version": "value-index.v3",
  "dataset_version": "...",
  "values":    {"<ref>": {"<country>": {"<folded>": "<original>"}}},
  "universe":  {"<ref>": {"<folded>": {"original": "...", "countries": [...]}}},
  "ambiguous": {"<ref>": {"<country>": {"<folded>": ["orig1","orig2"]}}}
}
```

Chỉ mục nằm **cạnh bản dữ liệu**, dựng bằng `--data-dir`, và runtime kiểm
`dataset_version` khớp repository — **lệch thì nổ**, thiếu thì im lặng bỏ qua
(thiếu là thiếu *thông tin*; lệch là thông tin *SAI*).

### 12.3. Ba trạng thái vắng mặt

| trạng thái | hành vi |
| --- | --- |
| có trong `values[ref][country]` | bind predicate, `verified=True` |
| có trong `universe[ref]`, **không** ở country | **bind như thường**, `verified=True`, assumption `value_absent_in_market`; evidence zero-row; câu trả lời là **0** |
| không có ở đâu | `A-VALUE-NOT-FOUND`, `fixable=False` |

`ORION` có ở VN, không có ở ID ⇒ *"ORION có bao nhiêu listing tại Indonesia"* có
đáp án **0** — một kết quả rỗng hợp lệ, không phải một câu không trả lời được.
Nhập hai thứ này làm một tạo ra một lời từ chối **nói sai sự thật về dataset**.

Điều kiện sống: predicate từ nhánh universe **phải** khai `verified=True`, nếu
không `_empty_result_is_self_evident` chặn câu trả lời 0 **đúng** bằng
`A-EMPTY-RESULT-UNVERIFIED` — đổi một lỗi lấy một lỗi khác.

## §13. **[W20/W30]** Thời gian

### 13.1. `DateRequest` — hàm toàn phần, năm ô

```python
DateRequest(
    dates,             # có đợt thu
    missing_snapshot,  # trong kỳ, KHÔNG có đợt thu       ← gap
    out_of_window,     # phân tích được, ngoài kỳ
    relative,          # "tuần đầu tháng 7", "tuần trước"
    clamped,           # relative đã bị cắt về cửa sổ
    unparsed,          # hình-dạng-ngày không phân giải được
)
```

Mọi span hình-dạng-ngày rơi vào **đúng một** ô. Không có ô "bỏ qua". Trước W20,
ba ô cuối không tồn tại nên nội dung của chúng thành số 0 lặng lẽ.

### 13.2. Bốn luật

- **R2 — KHÔNG chữ số trong message từ chối.** `verifier.scan_numbers` quét mọi
  số trong answer và đòi evidence hậu thuẫn; câu abstain không mang evidence. Đã
  làm eval rơi 1.0 → 0.77 một lần.
- **R3 — clamp phải khai báo**: `assumptions += ("date_window_clamped",)` **và**
  evidence attr `scope_clamped=True`, để A22 kiểm được phép cắt thay vì tin nó.
- **R4 — có ngày được nêu thì KHÔNG BAO GIỜ mặc định `LATEST_SNAPSHOT`.**
  Assumption đó chỉ được thêm khi `DateRequest` rỗng ở **cả năm** ô.
- **R5 — `missing_snapshot` không được nội suy sang ngày lân cận.**

### 13.3. **[W21]** Tiền đề

```python
Premise(direction, magnitude, magnitude_kind, subject_ref, span)
```

Hai nguồn **hợp nhất** (không phải hai bảng): registry cực tính
`domain/polarity.py`, và cấu trúc mất/được + magnitude phrase (`mất một nửa`,
`gấp đôi`, `2/3`).

**Năm luật**, trong đó luật quyết định là **R1**:

```
premise is not None
  ⇒ time_scope.mode = "transition"
  ⇒ không nêu hai mốc ⇒ mặc định hai mốc BIÊN của lịch snapshot
  ⇒ plan phải sinh ≥2 quan sát có observed_date
  ⇒ không sinh được ⇒ A22-ALIGN-PREMISE, KHÔNG BAO GIỜ trả một con số một snapshot
```

Trên bộ 3 ngày, luật này gần như luôn chỉ có thể **từ chối**. Trên bộ 20 ngày,
hai mốc biên cách nhau 20 ngày ⇒ `premise_contradicted` bắn vì **dữ liệu nói
ngược**, không vì thiếu dữ liệu. **R4** đòi cặp mốc là hai **đợt thu**, không
phải hai ngày lịch — lấy theo ngày lịch sẽ chọn trúng gap và một vế rỗng trong
phép so sánh trông giống hệt "giảm về 0".

---

# Phần V — Lập kế hoạch và thực thi

## §14. **[W23]** Một thứ tự, hai nhánh intent

Trước W23, `open_analytical` đi thẳng tới `open_planner` (cần LLM provider). Cấu
hình phát hành chạy `--provider offline` ⇒ mọi câu *"listing nào có nhiều lượt
thích nhất"* nhận `A19-PLAN` với lời từ chối *"Không có semantic planner
provider"* — một câu **mô tả harness**, cho một câu hỏi mà `synthesize()` **có
thể** trả lời.

```
1. synthesize(candidate, country, decline=codes)     ← LUÔN chạy
2. có plan và validate_plan(...).valid  → plan_provenance = "deterministic_synthesis"
3. không → open_planner nếu CÓ provider → plan_provenance = "llm_ir"
4. không → abstain rule_for_declines(codes)
```

**R1 — không bao giờ nói "không có provider" khi synthesizer đã từ chối có lý
do.** Lời từ chối phải mô tả **câu hỏi**, không mô tả cấu hình chạy.

**Tách một khái niệm đang bị nhập làm một:** `_synthesis_beats_template` trước
đây quyết định *có thử synthesize không*; sau W23 nó quyết định *có ƯU TIÊN plan
synth hơn template không*. Luôn thử ⇒ `decline_codes` tồn tại cho mọi câu, và 58
`plan_id` bị khoá giữ nguyên đường template.

## §15. IR và validator

`LogicalQueryPlan` là **thứ duy nhất compile được sang SQL** (134 edge — god node
lớn nhất của repo). `source_tier` khoá cứng `btc_dataset`: external data không
bao giờ đi qua analytical compiler/DuckDB.

`validate_plan(plan)` → `PlanValidationResult(valid, issues, depth)`:

```python
IssueCode = Literal[
    "missing_semantic_object","wrong_filter","wrong_join_path","grain_mismatch",
    "fanout_risk","unit_mismatch","temporal_mismatch","unsupported_claim",
    "budget_exceeded","schema_invalid","tier_violation","non_physical_grouping",
    "internal_identifier_exposed",   # [W25]
    "non_additive_aggregation",      # [W26-R4]
    "ungroupable_ref",               # [W24-R1]
]
```

Bốn luật đặt ở **validator** chứ không ở synthesizer, vì validator là chỗ **mọi**
producer đi qua — template, synthesizer và LLM planner:

- **[W25-R2]** `OutputField` trùng một cột định danh nội bộ (`shop_id`, `item_id`,
  `catid`, `brand_id`, `*_hash`, `key`) ⇒ từ chối.
- **[W26-R4]** `sum(monthly_sold)` với `time_scope` > 1 ngày ⇒ từ chối.
- **[W24-R1]** ref khai `groupable=False` xuất hiện trong `group_by` ⇒ từ chối.
- **[W17-R8]** trộn grain trong một `Aggregate` ⇒ `grain_mismatch`.

## §16. Compiler

`planner/compiler.py`, SQLGlot, **SELECT-only**, không bao giờ mở raw-SQL path.

- `compile_plan(plan, available_sources=None)` **[ĐANG CHẠY]** —
  `available_sources` là artifact **thật sự có** trong bản dữ liệu; plan đọc một
  bảng chưa thu bị chặn **tại đây**, trước khi thành SQL.
- **[W30-R3]** `expected_cardinality` là **biểu thức trên lịch**, không phải số:
  `"<=snapshot_rows"`, `"<=listings"`, `"1"`. Giữ được cả hai tính chất — cận vẫn
  là hợp đồng do plan khai, và nó không còn ghim một bản dữ liệu.
- **[W25-R1]** `_field()` tra `LABEL_REF_BY_UNIT`: gom nhóm theo `shop_id` (khoá)
  nhưng **chiếu ra ngoài** `dim.shop_name`. Khoá gom nhóm và nhãn hiển thị là
  HAI thứ.

## §17. **[W29]** S7.5 — Cửa mật độ quan sát

Chạy **sau compile, trước execute**. Vị trí này là có chủ đích: nó cần plan đã
hợp lệ để biết scope, và phải chặn **trước khi một con số tồn tại** — một con số
đã tính rồi thì mọi lớp sau đều thấy nó hợp lệ.

```
coverage = observed_rows / scope_rows       # scope = plan đã áp mọi predicate
                                            #         TRỪ điều kiện notna của measure

coverage ≥ 0.95   → trả lời; evidence attr observation_coverage BẮT BUỘC
0.50 ≤ c < 0.95   → trả lời + NÊU phạm vi quan sát bằng lời; partial_observation=True
coverage < 0.50   → clarify  A-SPARSE-OBSERVATION  slot=observation_window
```

Hai ngưỡng là **NGƯỠNG ĐƯỢC CHỌN, không phải số đo**. Căn cứ cho `0.50`: một
trung vị tính trên dưới nửa phạm vi không phải một phát biểu về phạm vi đó, bất
kể mẫu có đại diện hay không — vì hệ **không biết** nó có đại diện không và không
có cách nào biết. Đây là ranh giới của thứ *nói được*, không phải một ngưỡng
thống kê.

**Sáu luật:**

| luật | nội dung |
| --- | --- |
| R1 | `A-SPARSE-OBSERVATION` là **clarify**, không phải abstain — câu hỏi trả lời được, chỉ không ở grain thời gian người dùng nêu |
| R2 | cách đọc "as-observed" là một **grain có tên** (`TimeScopeMode = "as_observed"`), lọc `attributes_observed == True`, khai cửa sổ quan sát thật; **không** phải một mẹo |
| R3 | `observed_rows` và `scope_rows` **luôn** có trong `Evidence.attrs` — thiếu thì W29 không kiểm được sau khi chạy |
| R4 | `derived` kế thừa mode **chặt nhất** trong đầu vào |
| R5 | mật độ tính trên **scope của plan**, không trên toàn bảng |
| R6 | chạy **sau compile, trước execute** |

**W29 KHÔNG làm:** không loại dòng thiếu quan sát khỏi phép **đếm** (đó là lớp
lỗi *"đếm thừa hưởng bộ lọc của đo"*); không nội suy, không điền, không "lấy giá
trị gần nhất" ngầm; **không đổi hành vi trên bộ 3 ngày** (ở đó mọi measure đều
`panel`, coverage 1.0, mọi ca rơi vào nhánh đầu).

`observation_density.json` **vắng mặt phải là một lỗi ồn ào**: nếu thiếu nó mà
W29 lùi về "coi như dày đặc", thì cấu hình nguy hiểm nhất lại là cấu hình dễ xảy
ra nhất.

## §18. Executor

`planner/executor.py`, DuckDB in-memory, read-only:

```
SET enable_external_access = false
SET autoload_known_extensions = false
SET allow_community_extensions = false
SET memory_limit = <hạn mức ghi vào trace>     [W28-C2]
SET lock_configuration = true
```

View đăng ký **chỉ cho artifact thật sự có** — đăng ký một frame rỗng thay thế sẽ
khiến mọi truy vấn trả "0 dòng", tức *"đo được và không có gì"*.

**Hai cận số dòng, hai khái niệm khác nhau [ĐANG CHẠY]:**

| cận | đo cái gì | nguồn |
| --- | --- | --- |
| `max_result_rows` | số dòng **kết quả** | `expected_cardinality` do plan khai (postcondition kiểm lại sau khi chạy) |
| `max_intermediate_rows` | cardinality **trung gian** rộng nhất | bảng lớn nhất của **chính bản dữ liệu** × `FANOUT_ALLOWANCE` |

Guard cũ so `max_result_rows` với cardinality lớn nhất ở node **bất kỳ** — kể cả
lần quét bảng gốc. Trên 3.341 dòng nó chưa bao giờ bắn; trên 22.695 dòng nó chặn
**mọi** truy vấn kể cả truy vấn trả một dòng. Một hằng số tuyệt đối lại đúng ở bộ
nhỏ và sai ở bộ lớn — nên ngưỡng bám dữ liệu.

**[W28-C]** `MemoryError` và `RecursionError` là **outcome có kiểu**
(`A19-EXECUTION`, `code="resource_exhausted"`), **không** mở rộng thành
`except Exception`: nuốt mọi thứ biến một lỗi lập trình thành một lời từ chối
trông bình thường.

---

# Phần VI — Bốn lớp kiểm

## §19. Gate

`agent/gate.py:ContractDrivenGate.decide()`. **Thu thập mọi issue trước khi chọn
một**, nên trace cho thấy còn gì sai chứ không chỉ luật đầu tiên bắn.

```python
select_issue = min(issues, key=lambda i: (i.fixable, i.priority))
```

`fixable=False` **thắng** — một blocker không khắc phục được thắng một blocker
khắc phục được, bất kể thứ tự gọi. **[ĐANG CHẠY]**

### 19.1. Phase

| phase | kiểm gì |
| --- | --- |
| 1 | capability; **[W22]** span dư significant(); **[W31]** artifact chưa thu |
| 2 | intent/route |
| 3 | scope thời gian — **[W20]** `A-SNAPSHOT-SCOPE`, `A-SNAPSHOT-GAP` |
| 4 | currency |
| 5 | entity |
| 6 | slot |

### 19.2. **[W22]** Lý do từ chối chọn từ ledger

Trước W22, một câu hỏi về NPS thiếu country nhận lời khuyên *"hãy chọn thị
trường"* — một hành động **không thể làm cột NPS tồn tại**.
`refusal_reason_accuracy` 0.58/0.63 chính là con số này.

```
với mỗi span dư significant():
    khớp ABSENT_CONCEPTS → rule của concept, abstain, fixable=False
    kind == "date_like"   → W20 đã xử lý
    kind == "proper_name" → W19 đã xử lý
    kind ∈ {unknown_concept, grain_term, quantity_phrase}
                          → A-UNBOUND-CONSTRAINT, clarify, fixable=True
```

`domain/absent_concepts.py` khai 12 khái niệm (`nps`, `headcount`, `pageview`,
`profit`, `inventory`, `conversion`, `ads`, `sku`, `orders`, `hourly`,
`forecast`, `competitor`) với `refusal_class` và `capability_key`. **Fail ở
import** nếu `capability_key` không có trong `CAPABILITY_MESSAGES` hoặc
`refusal_class` không có trong `REFUSAL_CLASS_BY_RULE`.

**R4 — `ABSENT_CONCEPTS` và catalog không được chồng lấn**: một khái niệm có ref
trong catalog **không** được có mục trong registry vắng mặt. Nếu nó có ref nhưng
artifact chưa thu, đó là W31.

### 19.3. **[W22-R3]** `clarify` mang tên ô nó hỏi

```python
GateDecision.clarification_slot: str | None
# tập đóng, CÙNG tập với run_accuracy_benchmark.SLOT_CUES:
{"country","voucher_definition","ranking_metric","entity_disambiguation",
 "definition_threshold","group_dimension","metric","date_scope",
 "observation_window"}
```

Câu hỏi lại sinh **từ ô**, không phải từ chuỗi `reason` của một luật — đây là
điều làm `clarification_precision` đo được thay vì phụ thuộc vào việc chuỗi
reason tình cờ chứa từ khoá nào.

### 19.4. **[W31]** Chưa thu ≠ không bao giờ có

| luật | nói gì | lời khuyên |
| --- | --- | --- |
| `A-MISSING-ADS` | sàn không cấp dữ liệu quảng cáo | đừng hỏi nữa |
| `A-ARTIFACT-NOT-COLLECTED` | lần thu này chưa lấy | thu thêm thì hỏi được |

Gộp hai cái là nói sai một trong hai. Kiểm ở **gate** (gate biết ref nào được yêu
cầu và repository nào đang phục vụ, không cần plan); guard ở compiler **giữ
nguyên** làm phòng tuyến thứ hai vì nó bắt cả plan do LLM sinh.

## §20. Alignment (A22)

`agent/alignment.py`. Ba điểm gọi: sau plan, sau evidence, sau answer.

| issue code | rule_id |
| --- | --- |
| `measure_mismatch` | `A22-ALIGN-MEASURE` |
| `entity_mismatch` | `A22-ALIGN-ENTITY` |
| `country_mismatch` | `A22-ALIGN-COUNTRY` |
| `date_range_narrowed` | `A22-ALIGN-DATE` |
| `grouping_mismatch` | `A22-ALIGN-GROUPING` |
| `aggregation_mismatch` | `A22-ALIGN-AGGREGATION` |
| `filter_dropped` | `A22-ALIGN-FILTER` |
| `shape_mismatch` | `A22-ALIGN-SHAPE` |
| `qualifier_dropped` | `A22-ALIGN-QUALIFIER` |
| `rank_tie_at_cut` | `A22-ALIGN-RANK-TIE` |
| `premise_contradicted` | `A22-ALIGN-PREMISE` |
| `subrequest_dropped` | `A22-ALIGN-SUBREQUEST` |

**[W16]** `RequestDigest.unbound_spans` là đường để A22 **thấy được phần dư** —
trước đó nó không thể trả lời câu *"một ràng buộc có mặt trong câu hỏi đã được
biểu diễn hay đã bị bỏ rơi?"*, vì tới lúc đó câu hỏi không còn, chỉ còn request.

**[W21-R2]** Câu hỏi nhân quả kiểm tiền đề **trước**: có `Premise` thì
`premise_contradicted` được đánh giá trước, và nếu tiền đề sai thì đó là lý do
**duy nhất** báo ra. Giải thích một cú giảm không xảy ra tệ hơn từ chối.

## §21. Verifier

`agent/verifier.py`. Mọi số hiển thị phải khớp evidence; mọi citation phải có
thật. Fail ⇒ `A-VERIFICATION-FINAL`.

`scan_numbers` quét **mọi** số trong answer. Hệ quả vận hành, đã cắn một lần:
**không viết chữ số vào message abstain** — câu abstain không mang evidence, nên
"1.157 listing" trong `capability_messages` bị chấm là số bịa và đã làm eval rơi
từ 1.0 xuống 0.77. Mô tả phạm vi **bằng lời**.

`GateDecision.quoted_texts` là lối thoát có kiểm soát: span trích nguyên văn từ
dataset (tên listing trong một shortlist) là **dữ liệu được lặp lại để người dùng
chọn**, không phải một tuyên bố số.

## §22. Evidence

```python
Evidence:                       # frozen, extra="forbid"
    evidence_id
    source_tier: btc_dataset | reference | external
    metric, value, unit
    source_locator, source_path
    dataset_version
    attrs: dict                 # aggregation, sentinel_excluded, scope_clamped,
                                # observation_coverage, observed_rows, scope_rows,
                                # partial_observation, unmeasurable_excluded_count
    provenance, parent_evidence_ids, claimable_paths
```

**Bất biến #4:** `Evidence` là **bất biến**, cưỡng chế bằng model chứ không dựa
vào kỷ luật của caller. `ContextBundle` chỉ chứa **bản copy** đã guard. Sửa
`Evidence` gốc ⇒ `verifier._claim_value_matches` lệch ⇒ **mọi** câu trả lời
chuyển `A-VERIFICATION-FINAL`.

**External evidence luôn** `source_tier="external"`,
`mapping_status="needs_review"`, `admission="context_only"`. Cấm tính toán hoặc
suy nhân quả xuyên tier (`A20-TIER`).

---

# Phần VII — Hội thoại và câu trả lời

## §23. **[W27]** `clarify` là một request nối lại được

Trước W27, bộ nhớ mang **ô phạm vi**, không mang **request chưa phục vụ được**.
Lượt 2 `"Tại Việt Nam."` parse lại từ số 0, mất measure, và nhận `A19-CAT`
*"Chưa xác định được chỉ số nào cần đo"* — người dùng vừa trả lời đúng câu hỏi hệ
vừa hỏi và bị hỏi lại một câu khác.

```python
PendingRequest(turn, normalized_question, analytical, asked_slot, rule_id)
ConversationState(..., pending: PendingRequest | None)
```

**Luật hợp nhất — một chiều:**

```
lượt N+1:
  fresh = parse(text)
  pending tồn tại VÀ fresh không bind measure nào
                 VÀ fresh không có khung quantity phân giải được  → REFINEMENT
  ngược lại                                                       → CÂU HỎI MỚI
```

| luật | nội dung |
| --- | --- |
| R1 | refinement chỉ **điền**, không được thay khái niệm; **không** được thêm measure vào pending |
| R2 | bộ nhớ **điền ô, không cấp phép** — request đã hợp nhất vẫn đi đủ mọi chặng |
| R3 | ngữ cảnh kế thừa phải **hiển thị và huỷ được**, mang `carried_from_turn` |
| R4 | **analytical parse chạy SAU khi ô được điền** — lỗi thứ tự này sai **kể cả khi không có clarify nào** |
| R5 | lượt `allow` cũng ghi `pending` (cho *"Còn ở Indonesia thì sao?"*) |

`INHERITABLE_SLOTS`: `country`, `countries`, `date_range`, `entity_text`,
**`observation_window`** — lượt 2 *"Lấy theo lần quan sát gần nhất của mỗi
listing"* là một câu trả lời hợp lệ cho clarify của W29.

## §24. Sinh câu trả lời

Hai đường, `workflow._generate`:

1. **Template tất định** — mặc định, không LLM.
2. **LLM đọc `ContextBundle`** — LLM chỉ **diễn giải câu chữ**; mọi con số đã
   nằm sẵn trong bundle và đã qua verifier.

Câu trả lời luôn có bốn phần: **Kết quả**, **Phạm vi**, **Cách tính**, và (khi
có) **Giới hạn**. `agent/wording.py` cấm từ vựng nội bộ lọt ra
(`expected_cardinality`, `artifact`, `semantic catalog`, `A22`, …) —
`INV-NO-INTERNAL-VOCABULARY`.

**[W19-R3]** Zero-row do vắng mặt theo thị trường thêm một câu: *"Giá trị này có
trong dữ liệu, nhưng không có listing nào ở thị trường được hỏi."* — không chữ
số.

**[W29]** Coverage trong khoảng giữa thêm một câu nêu **phạm vi quan sát bằng
lời**.

---

# Phần VIII — Bất biến, mã lỗi, vận hành

## §25. Bất biến hợp nhất

| # | Bất biến | Cưỡng chế ở đâu |
| --- | --- | --- |
| 1 | LLM không tính số, không quyết định gate | mọi output LLM qua validator tất định |
| 2 | `source_tier` khoá `btc_dataset` cho analytical | `LogicalQueryPlan` |
| 3 | External luôn `context_only`, cấm tính xuyên tier | `A20-TIER` |
| 4 | `Evidence` bất biến | pydantic `frozen=True` |
| 5 | Không mở raw-SQL path ở runtime | compiler SELECT-only |
| 6 | Fail-closed: không chắc ⇒ clarify/abstain | gate `select_issue` |
| 7 | Schema đổi phải additive/backward-compatible | fixture cũ vẫn validate |
| 8 | `INV-SNAPSHOT-SCOPE` — chỉ dùng ngày đã thu | **[W30]** calendar |
| 9 | `INV-EMPTY-RESULT-IS-VALID` — 0 là một câu trả lời | `_empty_result_is_self_evident` |
| 10 | `INV-CURRENCY-NO-MIX` | gate phase 4 |
| 11 | `INV-DEDUPE-BEFORE-AGGREGATE` | relation `dedupe_strategy` |
| 12 | `INV-NO-INTERNAL-VOCABULARY` | **[W25]** validator, không chỉ wording |
| 13 | **Cấm cộng `monthly_sold` qua snapshot** | **[W26-R4]** validator |
| 14 | **Không phát biểu về phạm vi từ một mẫu thưa** | **[W29]** density gate |
| 15 | **"Chưa thu" ≠ "không bao giờ có"** | **[W31]** |

## §26. Mã lỗi — phân theo lớp

**Gate — capability và dữ liệu vắng:**
`A-MISSING-<CAP>`, `A-DATA-ABSENT`, **`A-ARTIFACT-NOT-COLLECTED`** [W31],
`A-VOUCHER-ID`, `A-UNKNOWN-INTENT`

**Gate — scope:**
`A-COUNTRY`, `A-MISSING-SLOT`, `A16-CROSS-CURRENCY`, `A-CROSS-CURRENCY-SCOPE`,
**`A-SNAPSHOT-SCOPE`**, **`A-SNAPSHOT-GAP`** [W20], `A-INSUFFICIENT-SNAPSHOTS`

**Gate — ràng buộc không bind được:**
**`A-UNBOUND-CONSTRAINT`** [W22], `A-VALUE-NOT-FOUND`, `A-ENTITY-NOT-FOUND`,
`A-AMBIGUOUS`, `A-ANALYTICAL-AMBIGUITY`

**Gate — mật độ:** **`A-SPARSE-OBSERVATION`** [W29]

**Plan/exec:**
`A19-CAT`, `A19-METRIC`, `A19-OP`, `A19-AGGREGATION`, `A19-PLAN`,
`A19-PLAN-GROUPING`, `A19-EXECUTION`, `A19-VALUE-CLASS`

**Alignment:** 12 mã `A22-ALIGN-*` (§20)

**Evidence/verify:**
`A-NO-EVIDENCE`, `A-MACRO-EVIDENCE-CONTRACT`, `A-EMPTY-RESULT-UNVERIFIED`,
`A-EMPTY-RESULT-RELAXED`, `A-VERIFICATION-FINAL`, `A26-CONSISTENCY`

**Route/external:** `A14-*`, `A15-*`, `A23-PARTIAL`

`refusal_class` (nhóm lý do, đọc bởi scorer): `missing_field`, `missing_grain`,
`missing_scope`, `cross_currency`, `date_out_of_range`, `forecast_unsupported`,
`external_data`, `unbound_constraint`, **`not_collected`** [W31],
**`sparse_observation`** [W29].

## §27. Telemetry và trace

**Luật nền (CLAUDE.md §5.1.3):** *mọi nhánh có điều kiện phải mang một khoá đếm
số lần nó thật sự bắn.* Không có nó thì **"đã đo" và "đã chạy" không phân biệt
được** — WP-A11 đã đo hai bảng trùng khít cho một nhánh **là code chết từ lúc
viết**, và tám test của nó đều xanh vì chúng gọi hàm cô lập.

| khoá | nguồn |
| --- | --- |
| `ledger.coverage`, `ledger.residual_kinds`, `ledger.claims_by_producer` | **[W16]** |
| `frame_hits: {kind: n}` | **[W17]** |
| `PlanningAttempt[]` — `{branch, tried, declined}` cho **cả hai** nhánh | **[W23]** |
| `observation_coverage`, `observed_rows`, `scope_rows` | **[W29]** |
| `calendar.dates`, `calendar.gaps` trong `DATASET_VERSION.json` | **[W30]** |
| `plan_provenance` — `deterministic_synthesis` \| `llm_ir` \| `template` | **[W23]** |

## §28. Dựng và phát hành bản dữ liệu

```
raw_extra_data/datashopee (dump Postgres, 7 bảng)
        │  extract_adapter.adapt_extract        ← chỉ đổi HÌNH DẠNG
        ▼
data/raw/country_code=X/dataset=Y/shop_id=Z/Y.csv   (layout canonical)
        │  pipeline.run_pipeline                ← MỘT đường làm sạch duy nhất
        ▼
<version>/  products_clean.csv, …, shop_stats_clean.csv, data_quality_issues.csv
        │  coverage.write_manifest
        │  build_value_index.py       --data-dir
        │  build_observation_density.py --data-dir   [W29]
        ▼
data/publish.py  →  4 bước, lý do có kiểu, cách ly thay vì nửa-ghi
        ▼
data/versions/<id>/ + data/CURRENT
```

**Vì sao adapter chứ không phải pipeline thứ hai:** viết một đường làm sạch thứ
hai cho bộ dữ liệu mới là tạo **hai định nghĩa cho cùng một khái niệm**, và chúng
sẽ trôi khỏi nhau đúng lúc không ai nhìn.

`data_quality_issues.csv` trên bộ 20 ngày: **0 lỗi**, 46.834 cảnh báo, mỗi mã có
nguyên nhân đã ghi ở `docs/qa/raw_extra_data_provenance.md` §6.

## §29. Kiến trúc đo lường

| bộ | đo cái gì | nó **không** đo cái gì |
| --- | --- | --- |
| 7 suite regression (`questions`, `v2`, `a19`, `boundaries`, `ambiguity`, `counting`, `critic`) | luật viết tay **nhất quán với chính nó** | năng lực |
| `eval/independent/` (risk-coverage, metamorphic) | phủ/rủi ro trên đề sinh từ dữ liệu | |
| `eval/accuracy/v1` dev + holdout | đúng/sai so với **oracle pandas độc lập** | năng lực **sau khi** đã đọc đề |
| **bộ paraphrase sinh máy** | năng lực gắn với **khái niệm** hay gắn với **khuôn câu** | |

**Bảy suite đạt 1.0 là điểm HỒI QUY, không phải điểm NĂNG LỰC.** Đó chính là lý
do W1–W15 đạt 1.0 trên bảy suite mà benchmark accuracy vẫn tìm ra 45 lỗi.

**[W20.4 của Spec3008]** Bộ paraphrase sinh **nghịch đảo** của frame grammar:
mỗi tổ hợp (khung × đơn vị × ngôn ngữ × vị trí giá trị × **ngày**) phát một câu
hỏi cùng một oracle. Trục **ngày** kiểm rằng năng lực gắn với *khái niệm ngày*
chứ không gắn với *ba ngày cụ thể* — đúng lớp lỗi mà `_DATE_DAY_MONTH` là ví dụ.

**Ba điều kiện cứng** — vi phạm bất kỳ điều nào là hồi quy, bất kể accuracy:

```
answer_risk                  ≤ 0.05
over_answer_rate             = 0.0
sparse_aggregate_leak_rate   = 0.0     [W29]
cross_snapshot_sum_rate      = 0.0     [W32 §31.2]
cross_currency_compare_rate  = 0.0     [W32 §31.2]
```

Hai điều kiện cuối thêm ngày 01/09: chúng đo **tầng gộp**, và chúng cần thiết vì
mỗi bước con hợp lệ riêng lẻ — không lớp kiểm nào cũ nhìn thấy phép gộp.

## §30. Giới hạn đã biết của kiến trúc này

Ghi ra thay vì để người sau tự phát hiện:

1. **Đếm thừa hưởng bộ lọc của đo.** `analytics/tools.py` có chỗ đếm trên tập đã
   lọc `monthly_sold.notna()`. Trên bộ 20 ngày lớp lỗi này nặng hơn hẳn: câu
   *"bao nhiêu listing giảm giá trên 50%"* trả **0** trong khi sự thật là **không
   đo được** ở ngày đó. Spec3008 **cố ý không** sửa nó — nó cần khảo sát riêng,
   và nhét vào W29 sẽ làm W29 mang hai nhiệm vụ.
2. **`27de9bff184f4f89` không tái lập bit-exact trên mọi máy.** Chênh ở **chữ số
   cuối của float** trên 111 dòng. Có sẵn từ trước bước nối (chứng minh bằng cách
   dựng lại tại HEAD), không phải hệ quả của nó.
3. **Kệ hàng chỉ biết ở một ngày.** `categories` của dump không mang ngày, và kệ
   hàng đo được là **đổi theo ngày** ⇒ 19/20 ngày không có định nghĩa kệ
   (`ORPHAN_CATEGORY_MAPPING_SHELF`, 27.032 cờ). Đó là lời khai đúng, không phải
   lỗi — nhưng nó giới hạn thật câu hỏi về kệ hàng.
4. **`shopee_verified` mất ở cấp listing.** Bộ mới chỉ có cờ cấp shop; hai đại
   lượng khác nhau mang một tên, nên cột listing-level để trống.
5. **Đường có LLM parser vượt ngân sách độ trễ 2–3 lần ở p95.** Cấu hình phát
   hành tắt nó (`GLADIATORS_ENABLE_LLM_PARSER` mặc định OFF).
6. **Live search mặc định OFF**, E6 chưa sign-off.
7. **Topic gate chạy shadow**, sáu metric `pending_oracle`.
8. **Ngưỡng `COVERAGE_REFUSE = 0.50` là ranh giới của thứ nói được, không phải
   một ngưỡng thống kê.** Đừng đi tìm cơ sở thống kê cho nó; không có.

Bổ sung 01/09/2026 — giới hạn tìm ra khi đo trên bộ 20 ngày:

9. **Nhận ý LIỆT KÊ vẫn là một DANH SÁCH CỤM viết tay.** `"liệt kê"`,
   `"tên của"`, `"những … nào"`, `"có các sản phẩm gì"` — bốn cách nói, bốn lần
   thêm vào danh sách. Đã thử suy từ CẤU TRÚC ("có chiều mang tên đã bind, không
   measure, không phép tổng hợp ⇒ đang hỏi các giá trị") và **bỏ**: nó bắn trên
   ba câu chỉ NHẮC TỚI một chiều mang tên chứ không hỏi nó
   (`"Shopee verified theo product"`, `"URL sản phẩm"`,
   `"Shop nào có chiến lược voucher hiệu quả nhất"`) và biến ba lời từ chối đúng
   thành ba bảng liệt kê. Danh sách cụm sẽ còn trượt; đây là giới hạn đã biết,
   không phải chỗ chưa ai nghĩ tới.
10. **Tên sản phẩm không có trong chỉ mục giá trị.** Chỉ mục chứa danh mục
    (1732+1689), brand (30+12), shop (10+10) — không có `dim.product_name`. Nên
    tra một sản phẩm cụ thể theo tên rơi `A22-ALIGN-ENTITY`. Thêm ~1.276 tên là
    khả thi về kích thước; chưa làm.
11. **Mã thị trường và đơn vị tiền RÒ RỈ vào tầng ngôn ngữ.** Đo trên
    `src/gladiators`: `'vn'`/`'id'` viết cứng **97 lần / 25 file** (kể cả
    `semantic_parser`, `frames`, `contracts`, `entity_extract`), tiền tệ VND/IDR
    **79 lần / 30 file**, ngày `2026-07…` **29 lần / 14 file**. Không có danh
    sách thị trường tập trung nào — `dim.country` đã khai `value_index=("vn",
    "id")` mà không chỗ nào đọc nó. Tầng dữ liệu thì cách ly tốt (catalog +
    metrics + relations + pipeline); đây là chỗ quyết định "thêm một thị trường
    thứ ba" là một dòng khai báo hay một cuộc săn literal.
12. **`eval/coverage_matrix.json` check-in có thể LỆCH bản dữ liệu.** Bản
    check-in khai `162/162 = 1.0`; dựng lại trên bộ 20 ngày ra `182 yêu cầu, 13
    thiếu` — 12 trong đó là nhóm `measure.shop_daily_*` chưa có ca kiểm nào, bị
    che vì bộ kiểm ghim vào bộ 3 ngày (nơi bảng panel không tồn tại nên chúng
    được xếp `not_measured` thay vì `missing`). Một artifact độ phủ dựng ở một
    bản rồi đọc như thể nói về bản khác là đúng lớp lỗi mà chính nó tồn tại để
    chống.

---

## §31. **[W32]** Hai tầng LLM có ranh giới, và cả hai mặc định TẮT

Thi công 31/08–01/09/2026. Chúng **không** đổi bất biến nào ở §25: LLM vẫn không
tính số, không chọn evidence, không quyết định gate. Cái chúng đổi là **đầu vào**
của đường tất định, và đầu ra của chúng bị kiểm lại trên tập đóng.

### 31.1. Ánh xạ chữ → ref (`planner/term_resolver.py`, cờ `llm_terms`)

Vấn đề nó giải: CLAUDE.md §3.1 nói *"ánh xạ chữ→ký hiệu là chỗ hỏng, không phải
phần suy luận"*, và đo được thì đúng vậy — `mặt hàng` không map được trong khi
`sản phẩm` map được.

```
binder tất định để lại cụm dư  →  gửi CẢ CÂU + danh sách ref ĐÓNG cho LLM
                               →  ref trả về ∈ danh sách đã gửi ?  nhận : vứt
```

Ba luật nhận, mỗi luật sinh từ một lỗi đo được:

1. **ref phải nằm trong danh sách đã gửi.** Một ref bịa không tới được plan, và
   điều đó đúng theo cấu trúc chứ không theo lời hứa.
2. **Cụm chỉ PHÉP TÍNH bị bỏ.** Đọc cả câu thì model ánh xạ luôn `"trung vị"` →
   `derived.median_monthly_sold`, request thành hai measure ⇒ `A19-PLAN`. Phép
   tính đã có đường tất định riêng.
3. **Ánh xạ phải nói về CỤM ĐÃ HỎI** (trùng theo token, không đòi chuỗi bằng
   nhau — bộ tách cắt cụt nên cụm đúng thường dài hơn). Thiếu luật này:
   *"Cái xí xổn ở VN có bao nhiêu?"* — hỏi vì `xí xổn`, model bỏ qua nó, ánh xạ
   `"bao nhiêu"` → `derived.product_count`, hệ trả **"Có 672 listing"**. Tắt LLM
   thì câu này `clarify`. Đó là over-answer do chính tầng này mở ra.

Đo trên 13 câu dùng từ ngoài catalog (deepseek): **1/13 → 10/13**. Trên bộ đề phá
hoại 15 câu (không có cột / cột đã bỏ / vô nghĩa / mơ hồ / ngoài cửa sổ / nhân
quả / cộng sai / zero-variance / thị trường không có): **0/15 ca lật từ chối
thành cho phép**.

### 31.2. Bẻ câu (`planner/question_split.py`, cờ `llm_plan`)

LLM nhận câu hỏi và **bức tranh dữ liệu sinh từ `observation_density.json`** (số
ngày, các cột thưa dưới 50%), trả về hai thứ: danh sách **câu hỏi con** bằng
tiếng người, và **một** toán tử gộp trong tập đóng
`{argmax, argmin, sum, compare, list}`.

Mỗi câu con chạy lại qua chính `AgentRuntime.run` — nên nó mang nguyên gate →
plan → compiler → verifier. Câu con chạy với cờ bẻ câu TẮT: một câu con lại được
bẻ tiếp là một cây không có đáy.

**Bốn cổng sống ở bước gộp, và ba trong bốn sinh ra từ một lỗi đã đo:**

| cổng | ca đã bắt |
| --- | --- |
| `argmax/argmin/sum` fail-closed khi còn bước không trả lời được | doanh thu chỉ quan sát 6/20 ngày; `max` trên 20 kết quả trong đó 14 rỗng trả "21/07" — ngày dữ liệu tồn tại, không phải ngày bán chạy |
| `sum` từ chối khi các bước hỏi ≥2 ngày | *"bao nhiêu listing từ 1/7 đến 5/7"* → 581+670+668+684+680 = **3283**, đúng số học, đủ 5 evidence id, và sai: đáp án là **701** listing phân biệt |
| `compare` đòi mọi bước trả về **con số cùng đơn vị** | bẻ *"giá trung vị VN so với Indonesia"* thành hai câu một-thị-trường làm mất cổng `A-CROSS-CURRENCY-SCOPE`, rồi đặt 145.220 VND cạnh 79.000 IDR |
| `compare` từ chối khi bước trả về **nhãn** | câu con bịa thêm "của shop", hệ gom nhóm và trả về TÊN shop; bước `allow`, có evidence, không trả lời câu hỏi |

**Bài học kiến trúc, quan trọng hơn cả bốn cổng:** mỗi bước con **hợp lệ riêng
lẻ**, còn phép gộp xảy ra **sau** khi tất cả đã qua verifier. Nên mọi luật của
tầng dưới (cấm cộng qua snapshot, cấm so chéo tiền tệ) **không với tới đây** và
phải sống lại tại đúng chỗ phép gộp được thực hiện. Đây là một lớp kiểm thứ năm,
không phải một tính năng.

---

## §32. Đếm phân biệt qua CỬA SỔ — ngoại lệ có cơ sở của luật một-snapshot

Ba tầng độc lập đều khoá "đúng một snapshot", và cả ba đều đúng **cho phép gộp**:
trộn nhiều lát cắt vào một trung bình là trộn nhiều câu trả lời. Nhưng
`COUNT(DISTINCT k)` **tự khử trùng theo định nghĩa**, nên một cửa sổ nhiều ngày
là ĐÚNG phạm vi câu hỏi yêu cầu.

Hai câu hỏi nó mở ra, cả hai **không bẻ câu được** vì chúng cần MỘT truy vấn:

```
"shop X xuất hiện trong bao nhiêu ngày"   COUNT(DISTINCT date)         → 18
"có bao nhiêu listing từ 1/7 đến 5/7"     COUNT(DISTINCT listing_key)  → 701
```

Phải gỡ **năm** chốt, ghi ra vì mỗi chốt là một quyết định có lý do:

| chốt | file | luật cũ | ngoại lệ |
| --- | --- | --- | --- |
| mở khoảng ngày | `semantic_parser.py` | "từ A đến B" → hai mốc | có cụm cửa sổ và KHÔNG có cụm so sánh ⇒ mở thành các đợt thu trong khoảng |
| dựng plan | `synthesizer.py` | >2 ngày ⇒ `date_count_unsupported` | `aggregation == count` và ref có `counts_unit` ⇒ nhánh `_synthesize_window_count` |
| validator | `validator.py` | `temporal_mismatch` | như trên, **và không có `Join` phía trên** — join làm fanout, phép đếm sau fanout không còn tự khử trùng |
| chọn nhánh | `open_planner.py` | template thắng | `>= 2` ngày ⇒ template một-snapshot không được thử |
| evidence | `analytics/tools.py` | `observed_date = time_scope[-1]` | plan quét nhiều ngày trả MỘT dòng ⇒ khai `observed_window`, và A22 kiểm cửa sổ thay vì kiểm một ngày |

Chốt cuối là chỗ đáng nhớ nhất: câu trả lời **đúng** bị chặn bởi một **lời tự mô
tả sai**. A22 không sai — nó tin đúng thứ evidence khai.

---

## §33. Bốn lỗi ÁNH XẠ ở biên, tìm bằng cách đối chiếu oracle pandas

Không lỗi nào ở tầng suy luận; cả bốn ở đúng biên mà CLAUDE.md §3.1 đã chỉ.

**34.1. Tên riêng bị bộ ghép alias xé nhỏ.** Quét cả 20 shop thật với câu *"có
bao nhiêu sản phẩm của shop &lt;tên&gt; ngày 21/7"*: **13/20 → 19/20 đúng, 0
sai**. Cả 7 ca hỏng đều có một từ catalog nằm TRONG tên riêng (`Official
**Shop**`, `Mars Snacking **VN**`, `Perfetti Van Melle **Vietnam**`), còn 13 ca
chạy được đều là `Official STORE` — một từ catalog không có. Tỷ lệ đúng đang phụ
thuộc vào việc shop tự đặt tên trùng từ vựng của hệ hay không.

Vá: vùng trong ngoặc kép **và** mọi giá trị ≥2 từ có thật trong chỉ mục được
đọc NGUYÊN VĂN, trừ khỏi text mà bộ ghép alias nhìn thấy. Nguồn là **chỉ mục giá
trị** — một sự thật về dữ liệu, không phải phỏng đoán về câu chữ.

**34.2. Bảng chụp một lần gắn vào MỌI ngày.** `shop_info_clean.csv` có đúng 20
dòng, một ngày duy nhất. Plan lọc `products` theo ngày đúng rồi `LEFT JOIN
shop_info` **không kèm điều kiện ngày**:

```
hỏi 01/07 → 305   (panel thật: 298)
hỏi 10/07 → 305   (panel thật: 300)
```

Vá: hai phía đều mang cột ngày thì `ON` phải khớp ngày. Khớp chứ không bỏ join —
phía phải không có dòng cho ngày đó thì `LEFT JOIN` trả NULL, và *"không quan sát
được"* là câu trả lời đúng, khác hẳn việc điền một con số của ngày khác.

**34.3. Hai bộ đọc ngày, một cái đóng băng ở bản cũ.** `extract_date_range` —
thứ nuôi `StructuredRequest.date_range` mà **A22 dùng làm "phạm vi người dùng đã
hỏi"** — là `_DATE_ISO = r"2026-07-0[1-3]"` cộng một regex chỉ khớp `1/7`, `2/7`,
`3/7`. Trên bộ 20 ngày nó **không nhìn thấy ngày nào sau 03/07**, nên *"từ 1/7
đến 5/7"* co thành `[01/07, 01/07]` và lời từ chối nói về một phạm vi người dùng
chưa bao giờ nêu.

Bộ kiểm không bắt được vì `tests/conftest.py` ghim vào chính bộ 3 ngày, nơi hai
bộ đọc trùng nhau. §29 của tài liệu này đã nêu `_DATE_DAY_MONTH` làm ví dụ cho
lớp lỗi *"năng lực gắn với ba ngày cụ thể"* — nó đúng, và nó đã xảy ra. Vá bằng
cách **xoá bản thứ hai**, đọc qua `parse_date_expressions` của lịch.

**34.4. Cùng chữ, hai tập hợp.** *"số sản phẩm của shop X"* trả **95**;
*"có bao nhiêu sản phẩm của shop X"* trả **92**. 95 là số hàng shop tự khai trên
sàn (`shop_info.item_count`), 92 là số listing bộ dữ liệu thu được. Cách nói
quyết định ngầm người hỏi nhận cái nào.

Vá bằng cơ chế ĐÃ CÓ: đưa cụm vào alias của **cả hai** ref biến nó thành
`alias_collision`, vốn fail-closed sẵn. Kèm hai thứ làm lời từ chối dùng được —
nó **nêu tên cả hai cách gọi** (lấy từ chính alias trong catalog, bỏ tên máy và
bỏ chính cụm đang mơ hồ), và `measure.shop_items` mang caveat nói rõ nó đếm tập
nào.

---

## §34. Trạng thái đo — 01/09/2026

| chỉ số | giá trị |
| --- | --- |
| `pytest -q` | **1656 passed, 1 skipped** |
| quét 20 shop thật, `where shop = X` + đếm | **19/20 đúng, 0 sai** |
| tên shop KHÔNG có ngoặc kép | **6/7 đúng** |
| bộ đề phá hoại 15 câu, tắt/bật `llm_terms` | **0/15 ca lật từ chối → cho phép** |
| ánh xạ LLM trên 13 câu ngoài catalog | **10/13** |
| 30 DẠNG câu hỏi, đường tất định thuần | **17/30 trả lời được, 0 crash, 0 số sai** |
| 10 ca phân tích có oracle pandas | **0 kết luận sai được rút** |

Con số cuối là con số quan trọng nhất, và nó là thứ duy nhất không được phép
tụt: mọi thất bại còn lại đều là **từ chối**, không phải số sai.

### 34.1. Dạng còn từ chối, phân theo nguyên nhân

**Từ chối ĐÚNG** — độ lệch chuẩn / IQR (`A19-OP`, IR không có toán tử phân tán),
lợi nhuận (`A-MISSING-PROFIT`), nhân quả, voucher (va chạm cố ý), tương quan.
Hai trong số này **nói sai lý do**: câu nhân quả bị báo *"chưa xác định chỉ số"*,
câu tương quan bị báo lỗi hạ tầng.

**`rating trung bình` KHÔNG phải từ chối oan** — catalog khai `rating` là thang
**thứ bậc** với lý do viết rõ: *"trung bình sao không phải trung bình của gì
cả"*. Trung vị chạy bình thường (4,905). Đây là một quyết định thống kê có chủ
đích; đừng "sửa" nó.

**Từ chối SAI, còn lại** — tra một sản phẩm theo tên (tên sản phẩm **không có**
trong chỉ mục giá trị: chỉ mục chỉ chứa danh mục, brand, shop), so hai shop khi
tắt bẻ câu.

---

## §35. Đọc tiếp

| Câu hỏi | Đọc |
| --- | --- |
| Phải sửa gì, ở file nào, theo luật nào? | `docs/Spec3008.md` |
| Bộ dữ liệu mới nối thế nào, quyết định gì? | `docs/qa/raw_extra_data_provenance.md` |
| Kiến trúc trước SolutionSpec2808? | `docs/Archibefore2208.md` |
| Testcase, ground truth, mỗi lớp kiểm sinh từ ca thật nào? | `docs/TCresultbefore2208.md` |
| Tầng binding metadata ↔ vật lý? | `docs/design/Metadata_Model_And_Binding_Layer.md` |
| 45 ca fail và sáu cơ chế? | `eval/reports/accuracy/ANALYSIS_2026-08-30.md` |
| Bản đồ code? | `graphify explain <node>`, `graphify-out/GRAPH_REPORT.md` |
| Hai cờ LLM làm gì, kiểm bằng gì? | §31 của chính tài liệu này |
| Vì sao "từ 1/7 đến 5/7" cần MỘT truy vấn chứ không phải năm? | §32 |
| Bốn lỗi ánh xạ ở biên, và cách tìm ra chúng? | §33 |
| Số đo mới nhất, và dạng nào còn từ chối? | §34 |
