"""LLM BẺ câu hỏi thành các câu con; hệ tất định trả lời và gộp.

Không nhầm với ``decomposer.py``: file kia bẻ một *plan* thành các *subplan* IR
theo §8.4 và chạy shadow. Tầng này ở phía TRƯỚC parser — nó bẻ CÂU CHỮ thành
các CÂU HỎI, và mỗi câu hỏi con đi lại từ đầu qua nguyên đường đã có.

Vì sao tầng này tồn tại
=======================

Đường tất định trả lời tốt các câu có hình dạng *một phép lọc, một chỉ số, một
lát cắt*. Nó từ chối các câu cần **nhiều lượt tra rồi so** — "ngày nào shop X có
doanh thu cao nhất", "shop A hay shop B bán nhiều hơn" — không phải vì thiếu dữ
liệu mà vì thiếu một bước: bẻ câu lớn thành các câu nhỏ mà chính nó trả lời được.

Đó là một việc NGÔN NGỮ, không phải một việc số học. Nên nó là việc của LLM, và
ranh giới đặt đúng chỗ đã dùng ở W32: **LLM đề xuất, hệ tất định định đoạt.**

Hợp đồng
========

LLM chỉ được trả về hai thứ:

* ``steps`` — danh sách CÂU HỎI bằng tiếng người, mỗi câu sẽ được chạy lại qua
  chính ``AgentRuntime`` như một câu hỏi bình thường;
* ``combine`` — MỘT toán tử gộp, chọn trong tập đóng ``COMBINE_OPS``.

LLM **không** thấy dữ liệu, **không** tính số, **không** chọn evidence. Mọi con
số trong câu trả lời cuối đến từ evidence của các bước, và mỗi bước đi qua đủ
gate → plan → compiler → executor → verifier như mọi câu hỏi khác. Một bước bịa
không thể tồn tại: nó hoặc trả evidence, hoặc bị từ chối và được kể ra.

Bất biến của bước gộp — và đây là phần dễ mất nhất
==================================================

Gộp trên MỘT PHẦN các bước là trả lời một câu hỏi khác. Ca kiểm đầu tiên cho
thấy vì sao: "ngày nào cửa hàng Richy miền Nam có doanh thu cao nhất" bẻ ra 20
câu con, nhưng ``estimated_recent_revenue`` chỉ quan sát được **6/20 ngày**, và
101/130 listing chỉ có đúng một quan sát vào 21/07. Lấy ``max`` trên 20 kết quả
trong đó 14 rỗng sẽ trả "21/07" — trôi chảy, có evidence, và SAI: nó nói về ngày
dữ liệu tồn tại chứ không phải ngày bán chạy.

Nên ``argmax``/``argmin``/``sum`` **fail-closed khi có bước không trả lời được**.
Không điền 0, không bỏ qua bước rỗng — đúng luật "thiếu dữ liệu thì gắn cờ,
không điền 0" ở CLAUDE.md §3.1. ``list`` và ``compare`` được phép mang bước
hỏng, vì hình dạng của chúng là kể lại từng bước chứ không phải rút một kết luận
xuyên qua chúng.

Đệ quy
======

Câu con chạy với cờ bẻ câu TẮT. Một câu con lại được bẻ tiếp là một cây không có
đáy, và không có câu hỏi thật nào cần nó.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

# Toán tử gộp — tập ĐÓNG. Thêm một toán tử là thêm một cách rút kết luận, nên
# nó phải là một quyết định có chủ đích chứ không phải một chuỗi LLM trả về.
COMBINE_OPS = frozenset({"argmax", "argmin", "sum", "compare", "list"})

# Gộp bằng cách RÚT một kết luận xuyên qua các bước: mọi bước phải trả lời được,
# nếu không kết luận nói về tập bước đã trả lời chứ không về câu hỏi đã hỏi.
_REDUCING_OPS = frozenset({"argmax", "argmin", "sum"})

# Trần số bước. Không phải để tiết kiệm — để một câu hỏi mơ hồ không biến thành
# một trăm lượt chạy mà không ai định trước.
MAX_STEPS = 25


class PlanProposer(Protocol):
    def decompose(self, payload: dict) -> dict: ...


@dataclass
class StepResult:
    """Một bước đã chạy. ``value``/``evidence_id`` chỉ có khi bước được trả lời."""

    question: str
    action: str | None = None
    rule_id: str | None = None
    answer: str = ""
    value: float | int | str | None = None
    unit: str | None = None
    evidence_id: str | None = None
    metric: str | None = None
    dataset_version: str | None = None

    @property
    def answered(self) -> bool:
        return self.action == "allow" and self.evidence_id is not None


@dataclass
class Split:
    """Kết quả một lượt bẻ câu, kèm đủ số liệu để kiểm lại sau khi chạy."""

    steps: tuple[StepResult, ...] = ()
    combine: str | None = None
    conclusion: str | None = None
    # Evidence của CẢ LƯỢT: evidence của từng bước, cộng MỘT bản ghi cho con số
    # do bước gộp tạo ra. Bẻ câu rồi trả về một chuỗi chữ là bỏ mất lớp kiểm
    # cuối — con số sinh ra SAU verifier thì không gì chống lưng cho nó, và đó
    # đúng là thứ hệ này tồn tại để chặn.
    evidence: tuple[Any, ...] = ()
    called: bool = False
    failed: str | None = None
    declined: str | None = None

    def as_attrs(self) -> dict[str, Any]:
        return {
            "llm_plan_called": self.called,
            "llm_plan_steps": len(self.steps),
            "llm_plan_answered": sum(1 for step in self.steps if step.answered),
            "llm_plan_combine": self.combine,
            "llm_plan_concluded": self.conclusion is not None,
            **({"llm_plan_failed": self.failed} if self.failed else {}),
            **({"llm_plan_declined": self.declined} if self.declined else {}),
        }


def propose_steps(
    question: str,
    proposer: PlanProposer | Callable[[dict], dict] | None,
    *,
    country: str | None = None,
) -> tuple[tuple[str, ...], str | None, str | None]:
    """``(steps, combine, failure)`` — chỉ ĐỌC đề xuất, chưa chạy gì.

    Tách khỏi phần chạy để kiểm hình dạng test được mà không cần dữ liệu,
    DuckDB hay mạng.
    """
    if proposer is None:
        return (), None, None
    call = getattr(proposer, "decompose", proposer)
    try:
        raw = call({"question": question, "country": country,
                    "combine_ops": sorted(COMBINE_OPS), "max_steps": MAX_STEPS,
                    # Bức tranh dữ liệu, sinh từ chính dữ liệu. Không có nó thì
                    # người bẻ câu bẻ ra 20 câu hỏi về một cột chỉ quan sát được
                    # 5% số dòng, và mọi bước đều rỗng — nó bẻ đúng ngữ pháp và
                    # sai thực tế, vì không ai nói cho nó biết thực tế là gì.
                    "dataset": _cached_brief()})
    except Exception as exc:                       # noqa: BLE001 — lỗi LLM là một
        return (), None, type(exc).__name__        # kết cục bình thường, không
                                                   # phải một sự kiện ngoại lệ
    if not isinstance(raw, dict):
        return (), None, "shape"
    steps = raw.get("steps")
    combine = raw.get("combine")
    if not isinstance(steps, list):
        return (), None, "shape"
    if not steps:
        # Prompt nói rõ: câu đã đủ đơn giản thì trả `steps` rỗng. Nên rỗng là
        # một câu TRẢ LỜI, không phải một thất bại — và gọi nó là thất bại làm
        # câu hỏi dừng lại thay vì rơi về đường thường.
        #
        # Đo được: "Có bao nhiêu listing ở VN từ ngày 1/7 đến ngày 5/7?" với cờ
        # bẻ câu bật ra `steps=0, combine=None` và KHÔNG được trả lời, trong khi
        # tắt cờ thì nó đi tới tận gate và nhận một lời từ chối nói rõ hơn.
        # Bật một tính năng không được làm hệ trả lời KÉM hơn khi tắt.
        return (), None, None
    if combine not in COMBINE_OPS:
        # Toán tử ngoài tập đóng KHÔNG được suy về một toán tử gần đúng: đoán
        # "maximum" là "argmax" là để một chuỗi tự do quyết định cách rút kết
        # luận, tức đúng thứ tập đóng sinh ra để chặn.
        return (), None, "bad_combine"
    clean = tuple(
        item.strip() for item in steps
        if isinstance(item, str) and item.strip()
    )[:MAX_STEPS]
    if not clean:
        return (), None, "no_steps"
    return clean, combine, None


def combine_results(
    results: tuple[StepResult, ...], combine: str,
) -> tuple[str | None, str | None]:
    """``(kết_luận, lý_do_từ_chối)``. Đúng một trong hai khác ``None``.

    Không tự tính lại gì trừ ``sum``: nó CHỌN giữa các bước, và con số của bước
    được giữ nguyên kèm evidence id của chính bước đó.
    """
    if not results:
        return None, "không có bước nào để gộp"
    unanswered = [step for step in results if not step.answered]
    if combine in _REDUCING_OPS and unanswered:
        return None, (
            "một số bước con không trả lời được, nên không rút được kết luận "
            "xuyên qua chúng"
        )
    numeric = [
        step for step in results
        if step.answered and isinstance(step.value, (int, float))
        and not isinstance(step.value, bool)
    ]
    if combine in _REDUCING_OPS and not numeric:
        return None, "không bước nào trả về một con số so sánh được"
    if combine == "argmax":
        best = max(numeric, key=lambda step: step.value)
        return f"{best.question} — {best.value} [{best.evidence_id}]", None
    if combine == "argmin":
        best = min(numeric, key=lambda step: step.value)
        return f"{best.question} — {best.value} [{best.evidence_id}]", None
    if combine == "sum":
        # Phép DUY NHẤT ở đây tạo ra một con số mới, nên nó là chỗ duy nhất có
        # thể tạo ra một con số ĐÚNG SỐ HỌC mà SAI CÂU HỎI.
        #
        # Đo được: "Có bao nhiêu listing ở VN từ ngày 1/7 đến ngày 5/7" bẻ ra 5
        # bước, mỗi bước trả đúng số của ngày mình (581, 670, 668, 684, 680),
        # và `sum` ra 3283. Cộng đúng. Nhưng đáp án của chính câu hỏi đó là
        # 701 — số listing PHÂN BIỆT trong cửa sổ. 3283 đếm mỗi listing một lần
        # cho mỗi ngày nó xuất hiện, tức trả lời một câu hỏi không ai hỏi, kèm
        # đủ năm evidence id để trông như đã được kiểm.
        #
        # Cùng luật đã có ở tầng catalog cho `monthly_sold` ("cấm cộng qua các
        # snapshot — tính trùng"), nhưng tầng đó không với tới đây: mỗi bước là
        # một lượt chạy hợp lệ riêng, và phép cộng xảy ra SAU khi tất cả đã qua
        # verifier. Nên luật phải sống lại tại đúng chỗ phép cộng được thực
        # hiện — giống hệt cổng tiền tệ ở `compare`.
        #
        # Chặn theo NGÀY chứ không theo measure: cộng ba shop trong CÙNG một
        # ngày là các tập rời nhau và vẫn cộng được (đo được: 92+22+73=187).
        spanned = _dates_spanned(step.question for step in results)
        if len(spanned) > 1:
            # Không nêu ngày và không nêu số ngày bằng chữ số: lời từ chối
            # không mang evidence, nên mọi chữ số trong nó đều bị verifier chấm
            # là số bịa. Mô tả bằng LỜI (CLAUDE.md §3.1).
            return None, (
                "các bước hỏi nhiều ngày khác nhau, nên cộng lại là đếm trùng "
                "cùng một đối tượng qua nhiều đợt thu. Hỏi 'mỗi ngày bao nhiêu' "
                "hoặc 'ngày nào nhiều nhất' để có câu trả lời theo từng ngày."
            )
        total = sum(step.value for step in numeric)
        ids = ", ".join(step.evidence_id or "" for step in numeric)
        # Số bước viết bằng CHỮ. `verifier.scan_numbers` quét mọi chữ số trong
        # câu trả lời và đòi evidence hậu thuẫn; "trên 3 bước" bị chấm là một
        # con số bịa vì không evidence nào mang giá trị 3. Đúng bẫy CLAUDE.md
        # §3.1 — cùng lớp với "1.157 listing" trong `capability_messages` từng
        # kéo eval từ 1.0 xuống 0.77.
        return f"tổng {total} [{ids}]", None
    if combine == "compare":
        # Bẻ câu KHÔNG được đi vòng qua cổng đã có. Đo được: "Giá trung vị ở VN
        # so với Indonesia ngày 21/7" — đường thường trả
        # `A-CROSS-CURRENCY-SCOPE` ("không so sánh trực tiếp VND với IDR"),
        # nhưng bẻ thành hai câu một-thị-trường thì mỗi câu hợp lệ, và bước gộp
        # đặt 145.220 VND cạnh 79.000 IDR như thể chúng so được. Cổng không sai;
        # nó chỉ không còn được hỏi.
        #
        # Nên luật của cổng đó phải sống LẠI ở đây, tại đúng chỗ phép so được
        # thực hiện. `list` không rơi vào luật này: nó kể lại, không so.
        # So sánh cần thứ SO ĐƯỢC. Một bước trả về nhãn ("Bibica Official
        # Store") không phải một đại lượng, và đặt hai cái nhãn cạnh nhau dưới
        # chữ "so sánh" là gọi một danh sách là một kết luận.
        #
        # Đo được: câu con do LLM bẻ ra — "Số listing của shop tại VN ngày
        # 01/07" — bịa thêm ràng buộc "của shop" mà câu gốc không nêu, hệ đọc
        # thành gom nhóm theo shop và trả về TÊN shop đầu tiên. Bước `allow`,
        # có evidence, và hoàn toàn không trả lời câu hỏi.
        labelled = [
            step for step in results
            if step.answered and not isinstance(step.value, (int, float))
        ]
        if labelled:
            return None, (
                f"{len(labelled)}/{len(results)} bước trả về một nhãn chứ không "
                "phải một con số, nên không so sánh được"
            )
        units = {step.unit for step in results if step.answered and step.unit}
        if len(units) > 1:
            return None, (
                "các bước trả về đơn vị khác nhau (" + ", ".join(sorted(units))
                + ") nên không so sánh trực tiếp được"
            )
    if combine == "compare":
        # NÓI RA BÊN NÀO HƠN. Bản cũ chỉ liệt kê hai con số và để người đọc tự
        # so — nhưng câu hỏi là "cái nào cao hơn", nên một danh sách không phải
        # câu trả lời, nó là nguyên liệu của câu trả lời.
        #
        # Phép so là của PYTHON, trên hai giá trị đã có evidence và đã qua cửa
        # đơn vị ở trên. LLM không so; nó chỉ nói rằng đây là một câu hỏi so
        # sánh, và tập đóng `COMBINE_OPS` đã kiểm điều đó.
        if len(numeric) == 2:
            high, low = sorted(numeric, key=lambda step: step.value, reverse=True)
            unit = f" {high.unit}" if high.unit else ""
            if high.value == low.value:
                verdict = (
                    f"Hai bên BẰNG NHAU: {high.value}{unit} "
                    f"[{high.evidence_id}] và [{low.evidence_id}]."
                )
            else:
                verdict = (
                    f"{high.question} — {high.value}{unit} [{high.evidence_id}] "
                    f"CAO HƠN {low.question} — {low.value}{unit} "
                    f"[{low.evidence_id}]."
                )
            return verdict, None
        # Khác hai bên thì không phải một phép so đôi; kể lại như `list`.

    if combine in ("compare", "list"):
        lines = []
        for step in results:
            if step.answered:
                unit = f" {step.unit}" if step.unit else ""
                lines.append(f"- {step.question}: {step.value}{unit} "
                             f"[{step.evidence_id}]")
            else:
                why = f" ({step.rule_id})" if step.rule_id else ""
                lines.append(f"- {step.question}: không trả lời được{why}")
        return "\n".join(lines), None
    return None, f"toán tử gộp không nhận ra: {combine}"



def _dates_spanned(questions) -> set[str]:
    """Các ngày mà một tập câu hỏi nêu ra, đọc bằng BỘ ĐỌC CỦA LỊCH.

    Không viết regex ngày thứ ba. Repo này vừa mất một lớp kiểm đúng vì có hai
    bộ đọc ngày song song và một trong hai còn đóng băng ở bản dữ liệu cũ.
    """
    from gladiators.domain.calendar import default_calendar
    from gladiators.planner.semantic_parser import normalize

    from .dates import parse_date_expressions

    calendar = default_calendar()
    seen: set[str] = set()
    for question in questions:
        request = parse_date_expressions(normalize(question), calendar)
        seen.update(request.dates)
        seen.update(request.missing_snapshot)
        seen.update(request.out_of_window)
    return seen


def composed_evidence(
    results: tuple[StepResult, ...], combine: str, value: float | int,
    unit: str | None,
) -> Any:
    """``Evidence`` cho con số do BƯỚC GỘP tạo ra.

    ``parent_evidence_ids`` trỏ về evidence của từng bước, nên chuỗi truy vết
    không đứt: mỗi số hạng vẫn về được tới dòng dữ liệu sinh ra nó, và con số
    tổng hợp nói rõ nó được ghép từ những gì.

    Không có bản ghi này thì cái tổng là một con số MỚI xuất hiện sau verifier —
    mỗi số hạng có evidence, còn tổng thì không, và không lớp nào phát hiện được
    một phép cộng sai.
    """
    import uuid

    from gladiators.contracts import Evidence
    from gladiators.external.contracts import SourceLocator

    parents = tuple(
        step.evidence_id for step in results
        if step.answered and step.evidence_id
    )
    versions = {
        step.dataset_version for step in results
        if step.answered and step.dataset_version
    }
    if len(versions) != 1:
        # Hai bản dữ liệu trong một lượt gộp là một câu trả lời về hai thế giới.
        # Không dựng evidence; bước gộp mất lớp chống lưng và phải từ chối.
        return None
    metrics = {
        step.metric for step in results if step.answered and step.metric
    }
    return Evidence(
        evidence_id=f"ev:split:{uuid.uuid4().hex[:12]}",
        source_tier="btc_dataset",
        metric=f"{combine}_{'_'.join(sorted(metrics)) or 'value'}",
        value=value,
        unit=unit,
        source_locator=SourceLocator(kind="internal", value="question_split"),
        dataset_version=next(iter(versions)),
        attrs={
            "combine": combine,
            "steps": len(results),
            "answered_steps": sum(1 for step in results if step.answered),
        },
        parent_evidence_ids=parents,
    )


def run_split(
    runtime,
    question: str,
    proposer: PlanProposer | Callable[[dict], dict] | None,
    *,
    country: str | None = None,
) -> Split:
    """Bẻ câu, chạy TỪNG câu con qua ``runtime``, rồi gộp.

    ``runtime.run`` KHÔNG bị đụng tới: docstring của nó khẳng định "không truyền
    ``session_id`` ⇒ hành vi cũ từng bit", và luồn một cờ vào đó là phá đúng lời
    khẳng định ấy. Mỗi bước ở đây là một lượt ``run`` bình thường, nên nó mang
    theo nguyên gate, plan, compiler, verifier — không lớp kiểm nào bị bỏ qua
    chỉ vì câu hỏi đến từ một máy chứ không từ một người.
    """
    steps, combine, failed = propose_steps(question, proposer, country=country)
    if failed:
        return Split(called=True, failed=failed)
    if not steps:
        # "Không cần bẻ" là một câu trả lời hợp lệ, không phải một thất bại.
        return Split(called=proposer is not None, combine=combine)

    results: list[StepResult] = []
    step_evidence: list[Any] = []
    for step in steps:
        try:
            response = runtime.run(step)
        except Exception as exc:                   # noqa: BLE001 — một bước nổ
            # KHÔNG được làm hỏng cả lượt: nó là một bước không trả lời được,
            # và `combine_results` đã biết phải làm gì với thứ đó.
            results.append(StepResult(question=step, action="error",
                                      rule_id=type(exc).__name__))
            continue
        value = unit = evidence_id = metric = dataset_version = None
        if response.evidence:
            # "dimension" là ĐƠN VỊ ĐỆM catalog gán cho evidence NHÃN (tên
            # shop/brand nhóm theo) — cùng quy ước `workflow.py` đã dùng để
            # không in "dimension" ra câu trả lời. Một câu hỏi nhóm theo tên
            # ("Số listing của thương hiệu Richy…") trả về evidence NHÃN
            # TRƯỚC evidence ĐẾM, nên lấy `evidence[0]` vô điều kiện chọn nhầm
            # cái tên làm `value` — sum/argmax/argmin/compare sau đó thấy một
            # bước "trả về nhãn chứ không phải con số" dù bước đó đã trả lời
            # đúng. Đo được: tách phrasing khỏi mẫu "mỗi ngày một bước" (fix
            # decompose prompt) làm lộ bug này — trước đó cửa chặn double-count
            # luôn bắn trước và che mất nó.
            first = next(
                (item for item in response.evidence if item.unit != "dimension"),
                response.evidence[0],
            )
            value, unit, evidence_id = first.value, first.unit, first.evidence_id
            metric, dataset_version = first.metric, first.dataset_version
            step_evidence.extend(response.evidence)
        results.append(StepResult(
            question=step,
            action=response.gate.action,
            rule_id=response.gate.rule_id,
            answer=response.answer,
            value=value, unit=unit, evidence_id=evidence_id,
            metric=metric, dataset_version=dataset_version,
        ))

    frozen = tuple(results)
    conclusion, declined = combine_results(frozen, combine or "list")
    evidence = list(step_evidence)
    if declined is None and combine in ("sum", "argmax", "argmin"):
        numeric = [
            step for step in frozen
            if step.answered and isinstance(step.value, (int, float))
            and not isinstance(step.value, bool)
        ]
        if numeric:
            if combine == "sum":
                composed_value = sum(step.value for step in numeric)
                composed_unit = next(
                    (step.unit for step in numeric if step.unit), None,
                )
            else:
                pick = (max if combine == "argmax" else min)(
                    numeric, key=lambda step: step.value,
                )
                composed_value, composed_unit = pick.value, pick.unit
            record = composed_evidence(frozen, combine, composed_value, composed_unit)
            if record is None:
                declined = (
                    "các bước trả về từ nhiều bản dữ liệu khác nhau, không ghép "
                    "thành một kết luận được"
                )
                conclusion = None
            else:
                evidence.append(record)
    return Split(
        steps=frozen, combine=combine, called=True,
        conclusion=conclusion, declined=declined, evidence=tuple(evidence),
    )


# Độ phủ dưới ngưỡng này thì một câu hỏi "theo ngày" trên cột đó gần như chắc
# chắn rơi vào ngày rỗng. 0,5 chứ không phải 0,95 (`coverage_dense`): ngưỡng kia
# quyết định CÓ TRẢ LỜI KHÔNG, ngưỡng này chỉ quyết định CÓ CẢNH BÁO KHÔNG, và
# hai quyết định khác nhau không được dùng chung một con số.
_SPARSE_BELOW = 0.5


def dataset_brief(density_path: str | None = None) -> dict[str, Any]:
    """Bức tranh dữ liệu, SINH TỪ dữ liệu — không viết tay.

    Người bẻ câu cần biết cái gì tồn tại và cái gì thưa, nếu không nó sẽ bẻ ra
    20 câu hỏi về một cột chỉ quan sát được 1 ngày và mọi bước đều rỗng. Nguồn
    là ``observation_density.json``, artifact đã phải dựng lại mỗi lần đổi bản
    dữ liệu — nên bản mô tả không thể lệch khỏi bản đang phục vụ mà không ai
    thấy, thứ mà một đoạn prose viết tay thì có thể.
    """
    import json
    import os
    from pathlib import Path

    root = density_path or os.environ.get("GLADIATORS_OBSERVATION_DENSITY")
    if root is None:
        data_dir = os.environ.get("GLADIATORS_DATA_DIR") or "data/processed"
        root = str(Path(data_dir) / "observation_density.json")
    try:
        raw = json.loads(Path(root).read_text(encoding="utf-8"))
    except Exception:                              # noqa: BLE001 — thiếu artifact
        # là trạng thái ĐƯỢC KHAI, không phải lỗi: bẻ câu vẫn chạy, chỉ mất phần
        # cảnh báo về cột thưa. Trả rỗng để chỗ gọi phân biệt được với "đầy đủ".
        return {}

    columns = raw.get("columns") or {}
    dates: set[str] = set()
    sparse: dict[str, float] = {}
    for name, info in columns.items():
        by_date = info.get("by_date") or {}
        dates.update(by_date)
        coverage = info.get("overall_coverage")
        if isinstance(coverage, (int, float)) and coverage < _SPARSE_BELOW:
            # Gộp về tên cột trần: hai file cùng mang `monthly_sold_value_num`
            # là một chi tiết vật lý, và người bẻ câu không nói bằng tên file.
            short = name.rsplit(".", 1)[-1]
            sparse[short] = min(sparse.get(short, 1.0), float(coverage))
    return {
        "dataset_version": raw.get("dataset_version"),
        "dates": sorted(dates),
        "sparse_columns": {
            name: round(coverage, 3)
            for name, coverage in sorted(sparse.items(), key=lambda kv: kv[1])
        },
    }


_BRIEF_CACHE: dict[str, dict[str, Any]] = {}


def _cached_brief() -> dict[str, Any]:
    """``dataset_brief()`` nhớ theo ĐƯỜNG DẪN, không theo tiến trình.

    Khoá là đường dẫn artifact chứ không phải một cờ "đã nạp": đổi
    ``GLADIATORS_DATA_DIR`` giữa hai lượt gọi là đổi bản dữ liệu, và một bộ nhớ
    đệm không thấy điều đó sẽ mô tả bản cũ cho bản mới — đúng lớp lỗi "hai bảng
    số giống nhau không có nghĩa là không khác biệt".
    """
    import os
    from pathlib import Path

    data_dir = os.environ.get("GLADIATORS_DATA_DIR") or "data/processed"
    key = str(Path(data_dir) / "observation_density.json")
    if key not in _BRIEF_CACHE:
        _BRIEF_CACHE[key] = dataset_brief(key)
    return _BRIEF_CACHE[key]
