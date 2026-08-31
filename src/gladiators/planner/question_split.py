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

    @property
    def answered(self) -> bool:
        return self.action == "allow" and self.evidence_id is not None


@dataclass
class Split:
    """Kết quả một lượt bẻ câu, kèm đủ số liệu để kiểm lại sau khi chạy."""

    steps: tuple[StepResult, ...] = ()
    combine: str | None = None
    conclusion: str | None = None
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
    if not isinstance(steps, list) or not steps:
        return (), None, "no_steps"
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
            f"{len(unanswered)}/{len(results)} bước con không trả lời được, "
            "nên không rút được kết luận xuyên qua chúng"
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
        # Phép DUY NHẤT ở đây tạo ra một con số mới. Luật cấm cộng (monthly_sold
        # qua snapshot là tính trùng) nằm ở tầng catalog và phải giữ nguyên ở
        # đó — dựng bản sao của nó tại đây là dựng chỗ để hai bản lệch nhau.
        total = sum(step.value for step in numeric)
        ids = ", ".join(step.evidence_id or "" for step in numeric)
        return f"tổng {total} trên {len(numeric)} bước [{ids}]", None
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
        units = {step.unit for step in results if step.answered and step.unit}
        if len(units) > 1:
            return None, (
                "các bước trả về đơn vị khác nhau (" + ", ".join(sorted(units))
                + ") nên không so sánh trực tiếp được"
            )
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
    for step in steps:
        try:
            response = runtime.run(step)
        except Exception as exc:                   # noqa: BLE001 — một bước nổ
            # KHÔNG được làm hỏng cả lượt: nó là một bước không trả lời được,
            # và `combine_results` đã biết phải làm gì với thứ đó.
            results.append(StepResult(question=step, action="error",
                                      rule_id=type(exc).__name__))
            continue
        value = unit = evidence_id = None
        if response.evidence:
            first = response.evidence[0]
            value, unit, evidence_id = first.value, first.unit, first.evidence_id
        results.append(StepResult(
            question=step,
            action=response.gate.action,
            rule_id=response.gate.rule_id,
            answer=response.answer,
            value=value, unit=unit, evidence_id=evidence_id,
        ))

    conclusion, declined = combine_results(tuple(results), combine or "list")
    return Split(
        steps=tuple(results), combine=combine, called=True,
        conclusion=conclusion, declined=declined,
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
