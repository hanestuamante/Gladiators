# Context Harness 20% + TC Fix 2607 — Implementation Spec

> **Loại tài liệu:** implementation spec, không phải báo cáo hoàn thành.
> Tại thời điểm viết, **không hạng mục nào trong tài liệu này đã được triển khai**.
>
> | Trường | Giá trị |
> | --- | --- |
> | Ngày lập | 26/07/2026 |
> | Baseline code | working tree 26/07/2026, `pytest -q` = 285 passed |
> | Baseline hành vi | `docs/qa/Testcases result 2607 analysis.md` (chạy lại DR40, 40 case × 3) |
> | Tài liệu ràng buộc | `V2_Unified_Architecture.md`, `External Data Integration.md`, `2207.md`, `2507.md` |
> | Phạm vi | P0 semantic alignment + entity/ID/country + macro qualifier + compound + context carrier + cassette + oracle DR40 |

---

## 0. Cách đọc và ràng buộc chung

### 0.1 Vấn đề trung tâm

Baseline 26/07 cho thấy một lỗi đúng đắn nghiêm trọng hơn mọi lỗi hiệu năng:

| Chỉ số | Giá trị | Nguồn |
| --- | --- | --- |
| Allow | 6/40 | `Testcases result 2607 analysis.md` §7.1 |
| Evidence-path đáp ứng đúng câu hỏi | **0/6** | §7.1 |
| `verification.passed` | **40/40 mỗi run** | §7.1 |
| Quote toàn câu làm đổi `(intent, action, rule)` | **21/40** | §7.4 |
| Case rơi `A-MISSING-SLOT` | 10 | §7.2 |

Verifier hiện chứng minh *"số hiển thị có binding hợp lệ"*; nó **không** chứng minh *"plan/result trả lời đúng câu hỏi"*. TC29 hỏi discount cross-country → trả `474 listing ID`; TC39 hỏi tổng sold theo cửa sổ → trả `668 listing VN`. Cả hai `verification.passed=true`.

Toàn bộ spec này tồn tại để đóng khoảng cách đó, **không** để thêm capability mới.

### 0.2 Thứ tự bắt buộc và lý do là dependency

```
WP-0  Regression lock (đỏ trước khi sửa)
  └─ WP-1  ContextBundle + guard + hash          ← carrier
       └─ WP-2  Alignment checker (A22)           ← khóa an toàn
            ├─ WP-3  Entity/ID/country extraction ← mở van lưu lượng
            ├─ WP-4  Macro qualifier admission
            ├─ WP-5  Compound sub-request
            └─ WP-6  Gate message nghiệp vụ
                 └─ WP-7  Cassette
                      └─ WP-8  Oracle DR40 + metamorphic
                           └─ WP-9  DEF-01…DEF-06 (2507.md)
```

**Không được đảo WP-3 lên trước WP-2.** Hiện 10 case abstain an toàn ở `A-MISSING-SLOT` chỉ vì parser không bind được entity. Sửa parser trước khi có alignment check sẽ đẩy 10 case đó vào macro/analytical path đang có silent substitution (§7.3: TC21/22/24/30 cùng trả sáu metric bất kể câu hỏi), tức **nhân bản lớp lỗi TC29/TC39** thay vì thu hẹp nó.

### 0.3 Invariant không được phá

Kế thừa nguyên văn `2207.md` §4, bổ sung ba mục cho đợt này:

1. `LogicalQueryPlan.source_tier` giữ khóa `btc_dataset` (`planner/query_ir.py:97`).
2. External data không đi qua analytical compiler/DuckDB IR.
3. Deterministic gate/router/validator có quyền cao hơn output LLM.
4. Evidence/claim/plan qua Pydantic `extra="forbid"`.
5. Live external luôn `source_tier="external"`, `mapping_status="needs_review"`, `admission="context_only"`.
6. Thay đổi schema phải **additive/backward-compatible**; fixture cũ không được hỏng âm thầm.
7. **[MỚI]** Alignment check là **deterministic**, không được giao cho LLM judge.
8. **[MỚI]** `ContextBundle` chỉ chứa **bản copy** đã guard; `Evidence` object gốc bất biến — nếu sửa `Evidence`, `verifier._claim_value_matches` (`agent/verifier.py:209-214`) sẽ lệch và mọi answer chuyển `A-VERIFICATION-FINAL`.
9. **[MỚI]** Không mở raw-SQL path ở runtime dưới bất kỳ hình thức nào.

### 0.4 Namespace rule ID

Đã dùng trong `src/`: `A14-*`, `A15*`, `A16-CROSS-CURRENCY`, `A17`, `A18`, `A19-{CAT,METRIC,OP,PLAN}`, `A20-TIER` (`verifier.py:83`), `A21-PROV` (`verifier.py:110`), `A-*`.

**`A22-*` là namespace trống — spec này chiếm dụng cho alignment.** Không tái sử dụng ID cũ.

| Rule ID mới | Action | Kích hoạt khi |
| --- | --- | --- |
| `A22-ALIGN-MEASURE` | `clarify` | Measure/dimension đã link ở request không xuất hiện trong plan refs |
| `A22-ALIGN-SHAPE` | `clarify` | `requested_output_shape` khác shape thực của plan output |
| `A22-ALIGN-QUALIFIER` | `clarify` | Câu có qualifier ngoài certified shape của macro |
| `A22-ALIGN-SUBREQUEST` | `allow` (partial) | Compound: phần trả lời được đã trả, phần còn lại nêu rõ |
| `A22-ALIGN-ENTITY` | `clarify` | Entity/ID trong câu không được bind vào plan |

---

## 1. WP-0 — Regression lock

**Mục tiêu:** chốt lỗi trước khi sửa. Nếu test viết xong mà đã xanh thì test viết sai.

### 1.1 Artifact

`eval/dr2607.json` — 40 case machine-readable theo schema `Testcases result 2607 analysis.md` §12.1:

```json
{
  "suite_version": "dr2607.1",
  "dataset_version_expected": "6b425c770972380c",
  "cases": [
    {
      "id": "dr2607_tc29",
      "question": "<verbatim từ DR TASK 1407 .md, KHÔNG thêm dấu ngoặc kép bao câu>",
      "legacy_expected_intent": "analytical_query",
      "complexity_level": "L2",
      "answerability_class": "C2",
      "expected_route_mode": "clarify",
      "expected_action": "clarify",
      "allowed_rule_ids": ["A16-CROSS-CURRENCY", "A22-ALIGN-MEASURE"],
      "forbidden_rule_ids": ["A-ALLOW"],
      "forbidden_analytical_kind": ["listing_count"],
      "expected_semantic_refs": ["measure.voucher_discount", "dim.country"],
      "expected_plan_properties": {},
      "expected_tools": [],
      "oracle_ref": null,
      "must_bind_claims": [],
      "must_not_assert": ["so sánh trực tiếp VND với IDR", "listing count là câu trả lời"],
      "compound_parts": [],
      "modes": ["offline"]
    }
  ]
}
```

Quy tắc điền:
- `question` lấy **nguyên văn**, không bọc quote. Biến thể quote thuộc WP-3 §4.5.
- Case chưa quyết được oracle → `expected_action` theo §8 của báo cáo 2607, `oracle_ref: null`, đánh dấu `"status": "needs_oracle"`. Không bịa expected.
- `forbidden_analytical_kind` là trường **chống substitution**, đọc từ `response.request.slots.analytical_kind`.

### 1.2 Test

`tests/test_dr2607_regression.py`:

| Test | Assert | Trạng thái mong đợi **trước** khi sửa |
| --- | --- | --- |
| `test_tc29_khong_tra_listing_count` | `response.gate.rule_id != "A-ALLOW"` và `slots.get("analytical_kind") != "listing_count"` | **FAIL** |
| `test_tc39_khong_tra_listing_count` | như trên | **FAIL** |
| `test_dr40_khong_crash` | 40 case × 3 run, 0 exception | PASS |
| `test_dr40_on_dinh` | tuple `(intent, action, rule_id)` giống nhau qua 3 run sau khi loại `trace_id` | PASS |
| `test_forbidden_rule_ids` | không case nào trả `rule_id` thuộc `forbidden_rule_ids` | FAIL ở ≥2 case |

**DoD:** hai test đầu đỏ, có log chứng minh. Commit riêng, không kèm fix.

---

## 2. WP-1 — ContextBundle (phần 20% của Context Harness)

### 2.1 Phạm vi — đọc kỹ trước khi implement

Đây **không phải** Context Harness đầy đủ. Chỉ triển khai phần là *carrier bắt buộc* cho WP-2.

| Thành phần | Trong đợt này | Lý do |
| --- | --- | --- |
| Typed bundle: `semantic_refs`, `plan_refs`, `plan_hash`, `prompt_version`, `dataset_version`, `context_hash` | ✅ | WP-2 không assert được nếu không có carrier |
| Guard một biên (DEF-05 thu hẹp) | ✅ | Gom `workflow.py:339-352` về một chỗ |
| Per-stage isolation | ✅ | Truy vết stage nào làm lệch |
| Budget token + compaction + `dropped` | ❌ hoãn | Xem §2.6 |
| JIT `catalog_slice` nén (M-Schema) | ❌ hoãn | Xem §2.6 |
| Metric `context_tokens` / `context_precision` | ❌ hoãn | Xem §2.6 |

**Cấm gọi việc này là "đã tích hợp Context Harness" trong bất kỳ tài liệu/deck nào.** Tên đúng: *alignment context carrier*.

### 2.2 File mới: `src/gladiators/agent/context.py`

```python
"""ContextBundle — carrier có kiểu cho payload gửi LLM và cho alignment check.

Bất biến: bundle chỉ chứa BẢN COPY. Evidence object gốc không bao giờ bị sửa
(verifier._claim_value_matches đọc trực tiếp từ Evidence — sửa nó làm lệch binding).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Stage = Literal["parse", "plan", "critic", "alternate", "adjudicate", "generate", "extract"]


class RequestDigest(BaseModel):
    """Ảnh chụp có kiểu của 'user hỏi gì' — đầu vào bên trái của alignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    normalized_question: str
    language: Literal["vi", "id", "unknown"]
    intent: str
    countries: tuple[str, ...] = ()
    entity_refs: tuple[str, ...] = ()          # listing_key / item_id:… / shop_id:…
    requested_measures: tuple[str, ...] = ()   # catalog refs đã link
    requested_dimensions: tuple[str, ...] = ()
    requested_output_shape: Literal["scalar", "table", "ranking", "comparison"]
    qualifiers: tuple[str, ...] = ()           # xem §5.3
    sub_request_ids: tuple[str, ...] = ()


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: Stage
    purpose: str                    # "P1" | "P5" | "P6" | "P8" | "P9" | "P10" | "P11" | "P2"
    request_digest: RequestDigest
    plan_refs: tuple[str, ...] = ()
    plan_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    guard_hits: tuple[str, ...] = ()
    prompt_version: str
    dataset_version: str
    budget_tokens: int
    dropped: tuple[str, ...] = ()
    context_hash: str = ""

    def with_hash(self) -> "ContextBundle":
        canonical = json.dumps(
            {
                "stage": self.stage, "purpose": self.purpose,
                "request_digest": self.request_digest.model_dump(mode="json"),
                "plan_refs": list(self.plan_refs), "plan_hash": self.plan_hash,
                "payload": self.payload, "prompt_version": self.prompt_version,
                "dataset_version": self.dataset_version,
            },
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        return self.model_copy(update={"context_hash": digest})
```

### 2.3 Budget — theo stage/purpose/provider, **không** theo L-level

`V2_Unified_Architecture.md:132` ghi rõ: *"Trục L là thuộc tính output của planner nên không cần parser đoán trước"*. Budget theo L-level là không khả thi vì tại thời điểm dựng bundle cho P8, L chưa tồn tại.

```python
BUDGETS: dict[tuple[Stage, str], int] = {
    ("plan", "P8"): 6000,
    ("critic", "P9"): 4000,
    ("alternate", "P10"): 6000,
    ("adjudicate", "P11"): 3000,
    ("generate", "P2"): 4000,
    ("extract", "P6"): 2000,
}
```

Trong đợt này budget chỉ được **ghi vào bundle và trace**, chưa cưỡng chế cắt (cắt thuộc phần hoãn §2.6). Ghi trước để schema ổn định, tránh migration lần hai.

### 2.4 Guard — mở rộng `injection_guard.py`, không tái dùng nguyên bộ PATTERNS

Theo đúng thiết kế `2507.md` §5.4. Thêm vào `src/gladiators/external/injection_guard.py`:

```python
_INTERNAL_PATTERN_IDS = frozenset({
    "A17_IGNORE_INSTRUCTIONS", "A17_SYSTEM_PROMPT",
    "A17_ROLE_OVERRIDE", "A17_FAKE_CITATION",
})


def sanitize_internal_text(value: str, *, max_chars: int = 1000) -> GuardResult:
    """Chuẩn hóa + phát hiện chỉ thị cho text nội bộ đưa vào LLM context.

    KHÔNG áp pattern PII/secret: A17_PII_PHONE khớp nhầm mã model/dung lượng
    trong tiêu đề listing (2507.md §5.4). Dữ liệu nội bộ đã qua data contract;
    rủi ro duy nhất là chỉ thị chèn vào prompt của generator.
    """
```

Điểm áp dụng — thay thế `workflow.py:339-352`:

```python
def guarded_evidence_payload(evidence: list[Evidence]) -> tuple[list[dict], tuple[str, ...]]:
    payloads, hits = [], []
    for item in evidence:
        data = item.model_dump(mode="json")
        for path, raw in _text_fields(data):        # value + attrs kiểu str
            guard = sanitize_internal_text(raw)
            if guard.hits:
                hits.append(f"{item.evidence_id}:{path}:{','.join(guard.hits)}")
                _set(data, path, guard.text)
        payloads.append(data)
    return payloads, tuple(hits)
```

`guard_hits` chảy vào `llm_meta["context_guard_hits"]` và vào trace. **Không abstain** vì phát hiện chỉ thị trong dữ liệu nội bộ — dữ liệu vẫn hợp lệ, chỉ trung hòa phần text gửi model.

### 2.5 Điểm tích hợp

| Vị trí hiện tại | Thay bằng |
| --- | --- |
| `workflow.py:339-352` (`context = {...}` dựng tay) | `ContextBundle(stage="generate", purpose="P2", ...).with_hash()`, truyền `bundle.payload` cho `llm_client.generate` |
| `open_planner.plan()` dựng payload P8 | Nhận `ContextBundle(stage="plan", purpose="P8")` |
| `critic.review()` | `ContextBundle(stage="critic", purpose="P9")` |
| `AgentResponse` | Thêm `context: dict[str, Any] = Field(default_factory=dict)` chứa `{stage: {context_hash, plan_hash, budget_tokens, guard_hits, dropped}}` — **additive**, không phá caller cũ |

`llm_client.generate` giữ nguyên chữ ký nhận `dict`. Chỉ nguồn dựng dict đổi.

### 2.6 Ba mục hoãn — lý do kỹ thuật, không phải cắt bớt

`Testcases result 2607 analysis.md` §1.6 và §10 ghi: không có credential Gemini/Groq/HuggingFace trong môi trường; TC01/TC02/TC38 rơi `A19-PLAN` vì *"offline không có P8 provider"*.

Budget/compaction, catalog nén và `context_precision` đều là đòn bẩy chất lượng **prompt của P8**. Ở cấu hình đang test P8 không chạy ⇒ ba mục đó tối ưu code không được thực thi và không đo được. Mở khóa cùng bước 7 của `Testcases result 2607 analysis.md` §13 (*"chạy P7/P8 bằng provider được phép"*).

### 2.7 Test

`tests/test_context_bundle.py`:

- `test_bundle_hash_on_dinh` — cùng input → cùng `context_hash` qua 3 lần dựng.
- `test_bundle_hash_doi_khi_evidence_doi` — đổi một `Evidence.value` → hash đổi.
- `test_evidence_goc_bat_bien` — `product_name` chứa `"ignore previous instructions..."` → `guard_hits` ghi `A17_IGNORE_INSTRUCTIONS`, `Evidence.attrs["product_name"]` **không đổi**, `verification.passed is True`.
- `test_fake_citation_bi_trung_hoa` — `product_name` chứa `"[ev:forged:0001]"` → hit `A17_FAKE_CITATION`, answer không chứa citation giả.
- `test_khong_false_positive_pii` — `"Tai nghe Bluetooth 5.3 pin 40 giờ mã ABC-123456789"` → **không** hit.

---

## 3. WP-2 — Alignment checker (P0, lõi của đợt sửa)

### 3.1 Bài toán

`Testcases result 2607 analysis.md` §10 P0: *"Executor trả đúng listing count; verifier xác nhận đúng số/citation, nhưng không có lớp nào kiểm semantic alignment giữa request, plan và answer."*

Cần **ba** chốt, không phải một:

```
request ──(A)──> plan ──(B)──> evidence ──(C)──> answer
```

- (A) **pre-execution**: plan có phục vụ đúng cái request hỏi không?
- (B) **post-execution**: evidence có phủ đúng output shape đã hứa không?
- (C) **post-generation**: answer có nêu đúng phần đã trả lời và phần chưa không?

Verifier hiện chỉ làm một phần của (C), và chỉ ở mức số ↔ evidence.

### 3.2 File mới: `src/gladiators/agent/alignment.py`

```python
"""Deterministic request↔plan↔answer alignment (A22).

KHÔNG dùng LLM. Đây là lớp chặn cuối cho lỗi TC29/TC39: answer có evidence hợp lệ
nhưng không trả lời câu hỏi.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gladiators.agent.context import RequestDigest

IssueCode = Literal[
    "measure_dropped",      # request có measure, plan không có
    "measure_substituted",  # plan có measure không ai hỏi và không phải supporting dim
    "shape_mismatch",       # scalar vs ranking vs comparison
    "qualifier_ignored",    # macro nuốt qualifier ngoài certified shape
    "entity_unbound",       # câu nêu entity/ID, plan không bind
    "subrequest_dropped",   # compound: phần trả lời được bị bỏ
]


@dataclass(frozen=True)
class AlignmentIssue:
    code: IssueCode
    detail: str
    request_side: tuple[str, ...] = ()
    plan_side: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentVerdict:
    aligned: bool
    issues: tuple[AlignmentIssue, ...]

    @property
    def rule_id(self) -> str | None:
        if self.aligned:
            return None
        first = self.issues[0].code
        return {
            "measure_dropped": "A22-ALIGN-MEASURE",
            "measure_substituted": "A22-ALIGN-MEASURE",
            "shape_mismatch": "A22-ALIGN-SHAPE",
            "qualifier_ignored": "A22-ALIGN-QUALIFIER",
            "entity_unbound": "A22-ALIGN-ENTITY",
            "subrequest_dropped": "A22-ALIGN-SUBREQUEST",
        }[first]
```

### 3.3 Check (A) — pre-execution

```python
def check_plan_alignment(
    digest: RequestDigest, plan_refs: tuple[str, ...],
    plan_output_shape: str, *, supporting_refs: frozenset[str] = frozenset(),
) -> AlignmentVerdict:
```

Thuật toán, thứ tự đánh giá:

1. **measure_dropped** — `set(digest.requested_measures) - set(plan_refs)` khác rỗng ⇒ issue. Ngoại lệ: ref có `unresolved=True` đã được `classify_a19` xử lý riêng thì bỏ qua (tránh trùng rule).
2. **measure_substituted** — `set(plan_refs) - set(requested) - supporting_refs` chứa **measure/derived_metric** (tra `CATALOG[ref].kind`) ⇒ issue. Dimension và `dim.country`/`dim.date` không tính (chúng là scope bắt buộc).
3. **shape_mismatch** — bảng tương thích:

| `requested_output_shape` | plan output hợp lệ |
| --- | --- |
| `scalar` | `expected_cardinality` = `"1"` |
| `ranking` | có node `Rank`, cardinality `<=k` |
| `comparison` | ≥2 nhóm ở output grain |
| `table` | mọi shape |

4. **entity_unbound** — `digest.entity_refs` khác rỗng nhưng không ref nào xuất hiện trong plan predicates/`ResolveValue` refs ⇒ issue.

**TC29 đi qua đường nào:** câu hỏi discount cross-country → `requested_measures = {"measure.voucher_discount"}` (hoặc `measure.discount_percent`), `countries = ("vn","id")`. Plan `listing_count` có `plan_refs = {"derived.product_count", "dim.country", "dim.date"}`. Bước 1 bắt `measure_dropped`, bước 2 bắt `measure_substituted` → `clarify A22-ALIGN-MEASURE`. Đồng thời `len(countries) == 2` + measure tiền tệ ⇒ `A16-CROSS-CURRENCY` ưu tiên cao hơn (§3.6).

**TC39 đi qua đường nào:** câu hỏi tổng monthly_sold theo cửa sổ → `requested_measures = {"measure.monthly_sold"}`, shape `scalar`. Plan `listing_count` → `derived.product_count`. Bước 1 bắt `measure_dropped` → `clarify A22-ALIGN-MEASURE`, kèm `answerable_alternative` nêu rõ hệ chỉ có snapshot proxy, cấm `SUM(monthly_sold)` qua snapshot.

### 3.4 Check (B) — post-execution

```python
def check_evidence_alignment(
    digest: RequestDigest, evidence: list[Evidence],
) -> AlignmentVerdict:
```

- Mỗi `ref` trong `digest.requested_measures` phải có ≥1 `Evidence` mà `metric` map về ref đó (dùng bảng `metric → ref` từ `domain/metrics.py`). Thiếu ⇒ `measure_dropped`.
- Nếu `digest.requested_output_shape == "comparison"` mà evidence chỉ có một nhóm ⇒ `shape_mismatch`.

### 3.5 Check (C) — post-generation

Không quét ngữ nghĩa tự do. Chỉ hai assert deterministic:

- Mọi `ref` trong `digest.requested_measures` **được trả lời** phải có ≥1 `ResponseClaim` bind tới `Evidence` của ref đó.
- Mọi `ref` **không** trả lời được phải xuất hiện trong mục `Giới hạn` của answer theo template cố định (`§5.4`). Không có ⇒ `subrequest_dropped`.

### 3.6 Điểm tích hợp trong `workflow.py`

Thứ tự ưu tiên rule khi nhiều check cùng fail — **guardrail an toàn thắng alignment**:

```
A16-CROSS-CURRENCY  >  A14-EXT  >  A19-*  >  A22-ALIGN-*  >  A-MISSING-SLOT  >  A-ALLOW
```

Chèn vào `run()`:

| Vị trí | Việc |
| --- | --- |
| Sau `logical_plan` được dựng (`workflow.py:480` / `:482`), **trước** `dispatch` (`:566`) | gọi `check_plan_alignment`; không aligned ⇒ `decision = GateDecision(action="clarify", rule_id=verdict.rule_id, reason=..., answerable_alternative=...)`, `tool_plan = ()` |
| Sau `dispatch`, cạnh check `macro.accepts_evidence` (`:571`) | gọi `check_evidence_alignment` |
| Sau `_generate` (`:605`), trước `verify_numeric_claims` (`:606`) | gọi check (C); ghi vào `verification["alignment"]` |

Ghi vào `planning_meta["alignment"] = {"aligned": bool, "issues": [...]}` để vào trace.

### 3.7 Rủi ro hồi quy — bắt buộc đo

Alignment check sẽ **giảm** số allow. Đó là kết quả đúng, nhưng phải chứng minh không giảm nhầm:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_evaluation.py --runs 3 --provider offline
.\.venv\Scripts\python.exe scripts\run_phase5_evaluation.py --provider offline
.\.venv\Scripts\python.exe scripts\run_phase6_evaluation.py --suite eval\questions_external.json
```

Điều kiện đóng: **60 câu legacy giữ 100%, V2 11 câu giữ 100%, A19 6 câu giữ 100%, Phase 6 giữ 12/12**. Bất kỳ câu legacy nào chuyển sang `A22-*` là **false positive của alignment**, phải sửa checker chứ không sửa expected.

### 3.8 Test

`tests/test_alignment.py`:

| Test | Assert |
| --- | --- |
| `test_tc29_measure_dropped` | `check_plan_alignment` trả `aligned=False`, code `measure_dropped` |
| `test_tc39_measure_dropped` | như trên |
| `test_listing_count_hop_le_van_aligned` | "Có bao nhiêu listing ở VN" → `aligned=True` (chống false positive) |
| `test_shape_scalar_vs_ranking` | request `scalar`, plan có `Rank` limit 5 ⇒ `shape_mismatch` |
| `test_dim_country_khong_bi_coi_la_substituted` | plan thêm `dim.country`/`dim.date` ⇒ vẫn `aligned=True` |
| `test_uu_tien_a16_hon_a22` | câu cross-currency ⇒ `rule_id == "A16-CROSS-CURRENCY"` |
| `test_entity_unbound` | câu nêu `item_id`, plan không bind ⇒ `entity_unbound` |

---

## 4. WP-3 — Entity/ID/country extraction

### 4.1 Ba defect được chứng minh

| Defect | Vị trí | Hệ quả |
| --- | --- | --- |
| Entity chỉ lấy khi có dấu ngoặc kép | `agent/parser.py:40`, `:89` | 10 case `A-MISSING-SLOT`; ID rõ ràng ở TC17/20/34/38 không bind |
| `ID` bị nhận là Indonesia | `agent/parser.py:88` — `\b(id\|indonesia)\b` | TC09 `category ID`, TC20 `mã ID`, TC26 `promotion ID` |
| Alias `Indo` không map | `parser.py:88` | TC12 |
| Country là scalar | `contracts.py:11` | Câu nêu cả VN và ID mất một market |

### 4.2 File mới: `src/gladiators/agent/entity_extract.py`

Khóa dữ liệu đã xác minh: `product_listing_key = "{country}:{shop_id}:{item_id}"`, ví dụ `id:1112776376:42657274673`. `shop_id` 10 chữ số, `item_id` 11 chữ số.

```python
LISTING_KEY = re.compile(r"\b(vn|id):(\d{6,12}):(\d{6,14})\b", re.IGNORECASE)

_ID_NOUNS = {
    "item":      ("item", "san pham", "listing", "produk", "ma san pham"),
    "shop":      ("shop", "cua hang", "toko", "gian hang"),
    "promotion": ("promotion", "khuyen mai", "promo", "promosi", "chuong trinh"),
    "category":  ("category", "danh muc", "kategori", "catid", "nganh hang"),
}


@dataclass(frozen=True)
class ExtractedEntity:
    kind: Literal["listing_key", "item_id", "shop_id", "promotion_id", "category_id", "name"]
    value: str
    surface: str
    confidence: Literal["exact", "high", "low"]
```

Thứ tự trích xuất — **ID-first**, dừng ở mức chắc chắn nhất:

1. `listing_key` khớp regex ⇒ `confidence="exact"`.
2. Dãy số 6–14 chữ số **có noun đứng trước trong cửa sổ 4 token** ⇒ gán namespace tương ứng, `confidence="exact"`.
3. Dãy số 9–14 chữ số đứng một mình, không noun ⇒ `kind="item_id"`, `confidence="high"` (item_id là namespace phổ biến nhất; ghi assumption vào trace).
4. Text trong ngoặc kép ⇒ `kind="name"`, `confidence="high"`. **Quote là hint, không phải điều kiện bắt buộc.**
5. Cụm danh từ sản phẩm không quote, match `EntityResolver` ⇒ `kind="name"`, `confidence="low"`.

### 4.3 Country — tách khỏi ID namespace

Thay `parser.py:88` bằng:

```python
_MARKET_CTX = ("thi truong", "market", "o ", "tai ", "ben ", "negara", "pasar", "cua ")

def extract_countries(text: str, normalized: str) -> tuple[str, ...]:
    found: list[str] = []
    if re.search(r"\b(viet nam|vietnam|vn)\b", normalized):
        found.append("vn")
    # "ID" chỉ là country khi KHÔNG đứng ngay sau một id-noun
    for match in re.finditer(r"\b(indonesia|indo|id)\b", normalized):
        if match.group(1) == "id":
            prefix = normalized[max(0, match.start() - 40):match.start()]
            if any(noun in prefix[-24:] for group in _ID_NOUNS.values() for noun in group):
                continue                      # "category ID", "mã ID", "promotion ID"
            if not (re.search(r"\(id\)", text, re.IGNORECASE)
                    or any(ctx in prefix[-16:] for ctx in _MARKET_CTX)):
                continue
        found.append("id")
        break
    return tuple(dict.fromkeys(found))
```

Quy tắc rút gọn:
- `ID` **là** country khi: `(ID)`, hoặc đứng sau market context (`thị trường ID`, `ở ID`, `tại ID`), hoặc là `Indonesia`/`Indo`.
- `ID` **không** là country khi đứng ngay sau id-noun (`category ID`, `mã ID`, `promotion ID`, `item ID`, `shop ID`).

### 4.4 Thay đổi contract — additive

`src/gladiators/contracts.py`:

```python
class StructuredRequest(BaseModel):
    ...
    country: str | None = None                      # GIỮ NGUYÊN — primary market
    countries: tuple[str, ...] = ()                 # MỚI, additive
    entities: tuple[dict[str, Any], ...] = ()       # MỚI: ExtractedEntity đã dump
```

Quy tắc tương thích: `country` = `countries[0]` nếu `countries` khác rỗng, ngược lại `None`. Mọi consumer cũ (`gate.py:49`, `:58`, `:60`; `semantic_parser.py:209`) tiếp tục đọc `country` và không đổi hành vi khi câu chỉ nêu một market.

Khi `len(countries) >= 2` và có measure tiền tệ ⇒ `A16-CROSS-CURRENCY` (đã có ở `gate.py:12`), **không** im lặng lấy market đầu.

### 4.5 Test — entity matrix bắt buộc

`tests/test_entity_extract.py`, theo `Testcases result 2607 analysis.md` §12.3. Mỗi fixture entity quan trọng phải phủ đủ 10 biến thể:

| # | Biến thể | Assert |
| --- | --- | --- |
| 1 | `vn:1145316676:42232012026` | `kind="listing_key"`, `confidence="exact"` |
| 2 | `item 42232012026` | `kind="item_id"`, exact |
| 3 | `mã ID 42232012026` | `kind="item_id"`, **`countries` không chứa `"id"`** |
| 4 | `"Nutren Junior"` có quote | `kind="name"` |
| 5 | `Nutren Junior` không quote | `kind="name"` |
| 6 | product + shop | 2 entity, đúng namespace |
| 7 | `category ID 100017` | `kind="category_id"`, `countries` không chứa `"id"` |
| 8 | ID không tồn tại | resolve → `not_found`, **không** `A19-CAT` |
| 9 | Hai candidate margin < 0.05 | `clarify` kèm candidates, **không auto-pick** |
| 10 | Multi-turn sau clarification | entity giữ nguyên |

Thêm `tests/test_quote_sensitivity.py` (§7.4 của báo cáo):

- Mỗi câu trong `eval/dr2607.json` chạy 4 biến thể: không quote / quote entity / quote toàn câu / noisy có ngoặc+ID+đơn vị.
- Assert: tuple `(intent, action, rule_id)` **giống nhau** ở cả 4 biến thể.
- Ngưỡng đóng: ≥38/40 case ổn định qua 4 biến thể (hiện tại 19/40 theo §7.4).

---

## 5. WP-4/5/6 — Macro qualifier, compound, gate message

### 5.1 WP-4 — Macro nuốt qualifier

**Bằng chứng:** `parser.py:58-59` đẩy mọi câu chứa voucher/promo vào `promotion_effectiveness`; macro chỉ yêu cầu `country` (`macros.py:125`) và luôn chạy `compare_voucher_groups`; evidence contract cố định 6 metric (`macros.py:119-123`). TC21/22/24/30 vì vậy cùng ra một output.

**Sửa:** thêm certified shape vào `CertifiedMacro` và kiểm trước khi dùng.

```python
@dataclass(frozen=True)
class CertifiedShape:
    """Điều kiện đủ để macro được phép phục vụ một request."""
    required_measures: frozenset[str]
    allowed_extra_measures: frozenset[str] = frozenset()
    allowed_grouping: frozenset[str] = frozenset()
    output_shape: str = "comparison"
    forbidden_qualifiers: frozenset[str] = frozenset()
```

Cho `promotion_effectiveness`:

```python
CertifiedShape(
    required_measures=frozenset({"measure.monthly_sold"}),
    allowed_grouping=frozenset({"derived.has_structured_voucher"}),
    output_shape="comparison",
    forbidden_qualifiers=frozenset({
        "promotion_id_filter",      # TC30
        "no_promo_segment",         # TC22 — grouping 4 chiều, V2 bẫy #19 cấm
        "revenue_measure",          # TC21/TC24 — hỏi revenue, macro chỉ có sold
        "mean_requested",           # TC24 — hỏi mean, macro trả median
        "discount_bucket",          # TC25
    }),
)
```

Kiểm trong `workflow.py` tại nhánh `macro is not None` (`:558`), **trước** `dispatch`:

```python
verdict = check_macro_shape(digest, macro.certified_shape)
if not verdict.aligned:
    decision = GateDecision(
        action="clarify", rule_id="A22-ALIGN-QUALIFIER",
        reason=(
            "Câu hỏi có điều kiện nằm ngoài phạm vi so sánh đã được chứng nhận: "
            + "; ".join(issue.detail for issue in verdict.issues)
        ),
        answerable_alternative=(
            "Hệ thống có thể so sánh nhóm có structured voucher với nhóm không, "
            "trong cùng một thị trường và một snapshot. Bạn muốn dùng so sánh đó không?"
        ),
    )
    tool_plan = ()
```

**Cấm silent substitution:** answer phải nói rõ điều kiện nào không hỗ trợ. Đây là yêu cầu tường minh của §10 P1.

Điều kiện tiên quyết: `request.analytical` hiện chỉ được dựng cho `open_analytical` (`parser.py:107`). Phải dựng cho **mọi** intent để có `digest`. Thay đổi này an toàn: `classify_a19` chỉ được gọi khi `intent == "open_analytical"` (`gate.py:42-48`), nên populate thêm không đổi routing hiện có. Bắt buộc có test khẳng định điều đó.

### 5.2 WP-5 — Compound sub-request

**Bằng chứng:** `parser.py:43-49` return ngay khi gặp một capability thiếu ⇒ TC08/23/25/31 mất phần trả lời được.

**Sửa:** tách câu thành sub-request trước capability gate.

```python
@dataclass(frozen=True)
class SubRequest:
    sub_id: str                 # "sr1", "sr2"
    text: str
    capability: str | None      # None = supported
    answerable: bool
```

Tách bằng dấu phân cách deterministic: `[;.]`, ` và `, ` còn `, ` dan `, ` juga `, `?`. Không dùng LLM ở bước này.

Luồng mới:
1. Tách sub-request.
2. Mỗi sub-request qua `UNSUPPORTED` riêng.
3. Nếu **mọi** sub-request unsupported ⇒ giữ nguyên hành vi hiện tại (abstain).
4. Nếu **một phần** supported ⇒ chạy phần đó, action `allow`, rule `A22-ALIGN-SUBREQUEST`, answer có mục `Chưa trả lời được` liệt kê từng phần + lý do.
5. **Không trộn evidence giữa các sub-request**; mỗi `Evidence.attrs["sub_id"]` ghi rõ nguồn.

Case áp dụng: TC08 (sales + profit), TC13 (similarity + FX), TC14 (text + visual), TC23 (conversion + voucher coverage), TC25 (discount bucket + CVR), TC31 (out-of-window + forecast), TC35 (internal not-found + external), TC36 (local values + cross-currency).

### 5.3 WP-6 — Gate message nghiệp vụ

**Bằng chứng:** `gate.py:30` dùng một template chung `"Dữ liệu hiện tại không có capability \`{missing}\`"`. Chữ `capability` là jargon; 8 case bị chấm `SAFETY PARTIAL` chỉ vì message.

**Sửa:** bảng message theo capability, mỗi entry đủ 4 phần theo §10 P1:

```python
CAPABILITY_MESSAGES: dict[str, dict[str, str]] = {
    "profit": {
        "missing": "Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận.",
        "coverage": "Hiện chỉ có giá bán, giảm giá và proxy lượt bán ở cấp listing, 3 snapshot 01–03/07/2026.",
        "answerable": "Vẫn trả lời được: doanh thu proxy ước tính, mức giảm giá, biến động giá.",
        "alternative": "Ví dụ: 'Doanh thu proxy ước tính của shop X ở VN ngày 03/07 là bao nhiêu?'",
    },
    "sku": {
        "missing": "Dataset không có sku_id/model_id. Đơn vị nhỏ nhất là product listing (country:shop_id:item_id).",
        "coverage": "tier_variation chỉ mô tả lựa chọn hiển thị cấp listing, không phân bổ được doanh số cho từng biến thể.",
        "answerable": "Vẫn trả lời được: chỉ số ở cấp listing.",
        "alternative": "Ví dụ: 'Listing 42232012026 có bao nhiêu lượt bán proxy ngày 03/07?'",
    },
    # inventory / ads / conversion / forecast / orders / category_type / price_reconstruction / reference / external
}
```

Yêu cầu: **mọi** key trong `parser.UNSUPPORTED` (13 key) phải có entry; test khẳng định `set(CAPABILITY_MESSAGES) == set(UNSUPPORTED)`.

Bỏ jargon nội bộ khỏi text hướng tới người dùng: `T-8c` (TC13), `capability` (TC18/28), `A19-CAT`. Mã rule vẫn ghi vào `gate.rule_id` và trace — chỉ không hiện trong `reason` người đọc.

---

## 6. WP-7 — LLM cassette

### 6.1 Vì sao cần

`Testcases result 2607 analysis.md` §10 P1: *"Cần cassette/replay hoặc fixture planner để regression không phụ thuộc key/quota."* TC01/TC02/TC38 hiện không đánh giá được vì offline không có P8.

### 6.2 File mới: `src/gladiators/agent/cassette.py`

Tái dùng đúng cơ chế đã có ở `external/cache.py` (immutable write + manifest + content hash).

**Cache key — bắt buộc đủ các thành phần sau**, thiếu bất kỳ thành phần nào là lỗi triển khai:

```python
def cassette_key(*, provider: str, model: str, model_revision: str,
                 temperature: float, top_p: float, seed: int | None,
                 prompt_version: str, purpose: str, system_prompt_hash: str,
                 tool_schema_hash: str, context_hash: str,
                 dataset_version: str) -> str:
```

Lý do: replay ba lần ra cùng plan chỉ chứng minh cassette deterministic, **không** chứng minh provider ổn định. Key phải phân biệt được mọi biến số có thể làm output đổi, nếu không cassette sẽ che lỗi thay vì phát hiện lỗi.

### 6.3 Mode

`GLADIATORS_CASSETTE_MODE ∈ {off, record, replay}`, mặc định `off`.

| Mode | Hành vi |
| --- | --- |
| `off` | Không đọc/ghi cassette. Hành vi hiện tại. |
| `record` | Gọi provider thật, ghi response vào `tests/fixtures/cassettes/<key>.json`. Cần API key. |
| `replay` | **Không mở socket.** Key không tồn tại ⇒ raise `CassetteMissError`, không fallback im lặng. |

### 6.4 Redaction

Trước khi ghi: xóa `Authorization`, `api_key`, `x-api-key` khỏi mọi request metadata; áp `sanitize_internal_text` lên prompt đã lưu. Cassette committed **không** được chứa key. Chạy secret scan của `2207.md` §17 trước khi commit.

### 6.5 Test

`tests/test_cassette.py`:

- `test_replay_khong_mo_socket` — monkeypatch `socket.socket` để raise; replay mode chạy trọn suite.
- `test_key_doi_khi_temperature_doi` — cùng prompt, temperature khác ⇒ key khác.
- `test_key_doi_khi_context_hash_doi` — evidence đổi ⇒ key đổi.
- `test_miss_khong_fallback` — key thiếu ⇒ `CassetteMissError`, không gọi provider.
- `test_khong_co_key_trong_cassette` — quét toàn bộ file cassette bằng pattern của `2207.md` §17, 0 match.

---

## 7. WP-8 — Oracle DR40 + metamorphic

### 7.1 Oracle độc lập

`eval/independent/dr2607_oracle.py` — **không import bất kỳ module nào của `src/gladiators`**. Chỉ đọc CSV bằng pandas/csv và `Data_Context_and_Analysis_Notes.md` làm định nghĩa lời.

Đầu ra `eval/independent/dr2607_expected.json`, mỗi entry: `{case_id, metric, value, unit, grain, scope, method_note}`.

Chấm bằng **result/denotation equivalence**, không so chuỗi SQL, không so chuỗi answer.

Phải sửa các premise sai đã được xác minh ở §9.2 của báo cáo 2607:

| Case | Premise cũ | Oracle đúng |
| --- | --- | --- |
| TC26 | promotion 473502013010049 đổi voucher qua 3 ngày | 85 rows/85 listings, **chỉ ngày 01/07**, hai shop Richy |
| TC30 | `promotion_id=0` có 874 sản phẩm VN | 874 là raw rows hai quốc gia/ba snapshot; VN 694 raw rows, 255 distinct listing, latest 241 |
| TC34 | item 24710759163 thiếu 02/07 | có đủ 3 ngày, `snapshot_gap_flag=False` — **phải thay fixture** bằng 1 trong 10 gap rows thật |
| TC19 | giá 410.000 là sentinel | `price_sentinel_flag=False` cả 3 snapshot — cần policy/human label |
| TC23 | ID không có structured voucher | Đúng: ID = 0; VN = 1.580 toàn window, 577 latest |

### 7.2 Metamorphic relations — chỉ những phép bảo toàn ngữ nghĩa

`eval/metamorphic/relations.py`. **Mỗi MR phải có chứng minh bảo toàn ngữ nghĩa ghi trong docstring.**

| MR | Phép biến đổi | Bất biến kỳ vọng |
| --- | --- | --- |
| MR-1 | Paraphrase **cùng ngôn ngữ** (từ đồng nghĩa đã duyệt) | `(intent, action, rule_id)` và denotation giống nhau |
| MR-2 | Đổi thứ tự filter trong câu | denotation giống nhau |
| MR-3 | Thêm/bớt dấu ngoặc kép quanh entity | `(intent, action, rule_id)` giống nhau |
| MR-4 | Bỏ dấu tiếng Việt | `(intent, action, rule_id)` giống nhau |
| MR-5 | Thêm nhiễu (khoảng trắng thừa, emoji, xuống dòng) | `(intent, action, rule_id)` giống nhau |

**CẤM tuyệt đối làm MR:**

- **vi ↔ id**: đổi ngôn ngữ thường kéo theo đổi `country`/currency/entity ⇒ kết quả *phải* khác. Đây không phải phép bảo toàn.
- Đổi `country` (`vn` ↔ `id`).
- Đổi `date`/snapshot.
- Đổi đơn vị tiền.

### 7.3 Sửa oracle lệch version

- `eval/questions_boundaries.json:bnd02` đang kỳ vọng `A-MISSING-EXTERNAL`; runtime trả `A14-EXT`. Sửa expected → `A14-EXT`. Suite từ 8/9 lên 9/9.
- Đồng bộ `eval/coverage_matrix.json` (162/162) với các docs còn ghi 158/158.

---

## 8. WP-9 — Sáu defect 2507

Thực hiện **sau** toàn bộ WP-0…WP-8, theo đúng thứ tự PR-1/PR-2/PR-3 và acceptance A1–A10 tại `2507.md` §7–§8. Không đảo lên trước: `Testcases result 2607 analysis.md` §13 xếp nhóm này ở P2 (bước 8).

Hai lưu ý liên kết với spec này:

- **DEF-04** (truncation) tạo cờ `truncated` mà **DEF-06** cần; đồng thời check (C) §3.5 phải coi `truncated=True` là một `subrequest_dropped` phải nêu trong `Giới hạn`.
- **DEF-05** đã được thực hiện sớm trong WP-1 §2.4. Khi làm PR-3 của 2507, chỉ còn phần wiring `context_guard_hits` — không làm lại.

Trạng thái đã xác minh 26/07 (để tránh nhầm lẫn như các bản trước): **không defect nào đã sửa.** `query_ir.py:66` vẫn là `expected_cardinality: str` trần; `CARDINALITY_VIOLATION`/`ESTIMATED_ROWS_EXCEEDED` không tồn tại trong `src/`; `dataset_version` vẫn là `@property`.

---

## 9. Ma trận acceptance

Không đóng đợt nếu bất kỳ dòng nào chưa có bằng chứng lệnh + kết quả.

| ID | Điều kiện | Cách kiểm |
| --- | --- | --- |
| AL-01 | TC29/TC39 không còn `allow listing_count` | `pytest tests/test_dr2607_regression.py` |
| AL-02 | Không hồi quy suite kế thừa | legacy 60×3 = 100%, V2 11×3 = 100%, A19 6×3 = 100%, critic 4×3 = 100% |
| AL-03 | Phase 6 giữ nguyên | `run_phase6_evaluation.py --suite eval/questions_external.json` → 12/12, mode `offline-no-network` |
| AL-04 | Full suite không giảm test | `pytest -q` ≥ 285 passed |
| AL-05 | Quote-insensitivity | ≥38/40 case ổn định qua 4 biến thể quote |
| AL-06 | Entity matrix | 10 biến thể × mỗi fixture pass |
| AL-07 | `ID` không thành Indonesia | TC09/TC20/TC26 `countries` không chứa `"id"` |
| AL-08 | Không silent substitution | TC21/22/24/30 → `A22-ALIGN-QUALIFIER`, answer nêu rõ điều kiện không hỗ trợ |
| AL-09 | Compound partial | TC08/23/25/31 trả phần C1 + nêu phần C4 |
| AL-10 | Gate message đủ 4 phần | `set(CAPABILITY_MESSAGES) == set(UNSUPPORTED)`; không còn chữ `capability`/`T-8c` trong `reason` |
| AL-11 | Evidence gốc bất biến | test guard §2.7 |
| AL-12 | Cassette replay không mở socket | `test_replay_khong_mo_socket` |
| AL-13 | Không leak key | secret scan `2207.md` §17, 2 lệnh `rg` không trả kết quả |
| AL-14 | Oracle độc lập | `eval/independent/dr2607_oracle.py` không import `gladiators`; kiểm bằng AST scan trong test |
| AL-15 | MR hợp lệ | không MR nào đổi country/date/currency/ngôn ngữ; test khẳng định |
| AL-16 | Alignment không false positive | 0 câu legacy chuyển sang `A22-*` |
| AL-17 | Invariant giữ nguyên | `source_tier` khóa `btc_dataset`; external `context_only`; không cross-tier arithmetic |

---

## 10. Ngoài phạm vi — cố ý, ghi lại để không bị hiểu là bỏ sót

| Hạng mục | Lý do |
| --- | --- |
| Budget/compaction, JIT catalog nén, `context_precision` | P8 không chạy ở cấu hình hiện tại (§2.6) |
| Candidate generation + selection (nhiều plan + selector) | Phụ thuộc `expected_cardinality` được cưỡng chế (DEF-02, chưa làm); tăng latency/cost |
| Conformal abstention thay `_deterministic_answer` label | Cần calibration set đại diện + giả định exchangeability; suite hiện tại quá nhỏ. Không thay guardrail deterministic C4 |
| Ablation semantic-layer vs raw SQL | Chỉ chạy offline trong `run_ablation.py`; **không** mở raw-SQL path runtime (trái ADR-Q1/Q2) |
| OpenTelemetry GenAI | Chỉ làm export adapter khi tới lượt; JSON trace giữ vai trò source of truth cho audit/replay. Conventions còn ở trạng thái Development |
| NLI grounding cho claim định tính | Trước tiên biến "ổn định"/"giảm mạnh" thành typed metric có threshold rồi verify deterministic (V2 §19) |
| Tách `AgentRuntime.run()` thành stage pipeline | `2507.md` §0.2 |
| Live Tavily (W8) | E6 vẫn `PENDING`; không nằm trong đợt này |

---

## 11. Báo cáo bắt buộc khi hoàn tất

```markdown
## Outcome
- Work packages hoàn tất: ...
- Work packages còn mở: ...

## Files changed
- path: mục đích

## Tests
- command: result (số passed/failed, thời gian)

## DR40
- Allow trước/sau: 6/40 → N/40
- Evidence-path đúng câu hỏi trước/sau: 0/6 → M/N
- Quote-stability trước/sau: 19/40 → K/40

## Invariants checked
- typed IR remains btc_dataset-only: PASS/FAIL
- external admission context_only: PASS/FAIL
- alignment deterministic (không LLM): PASS/FAIL
- Evidence object bất biến: PASS/FAIL
- legacy suites không regression: PASS/FAIL

## Remaining risks
- ...
```

Không dùng "done", "compliant", "production-ready" hoặc "all tests pass" nếu không đính kèm command/result tương ứng. Không đổi trạng thái E6 trong `PHASE6_ACCEPTANCE_SIGNOFF.md`.
