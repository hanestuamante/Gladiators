"""LLM đề xuất HÌNH DẠNG câu hỏi trên một tập ĐÓNG — đề xuất, không quyết định.

Vì sao tầng này tồn tại
=======================

Parser đang làm HAI việc, và chỉ một việc là vô hạn:

    (a) cụm này là KHÁI NIỆM nào?   vô hạn — mỗi bộ dữ liệu một từ vựng
    (b) câu này có HÌNH DẠNG nào?   HỮU HẠN — đếm/cực trị/liệt kê/so/tỷ lệ/tra

(a) đã có lời giải chạy được: W32 (`term_resolver`) — LLM đề xuất, catalog đóng
định đoạt, đo được 10/13 trên từ chưa ai code.

(b) thì bị vá bằng DANH SÁCH CỤM viết tay, và danh sách đó phình mà vẫn trượt.
Đếm riêng ngày 01/09: `"thấp"` vs `"thấp nhất"`, `"tỷ lệ"` vs `"bao nhiêu phần
trăm"`, bốn cách nói cho "liệt kê", `"tên"`. Mỗi lần là thêm một cụm. Nhưng
`"thấp"`, `"kém nhất"`, `"bét"`, `"ít nhất"`, `"lowest"`, `"terendah"` đều là
MỘT hình dạng: ``argmin``. Danh sách cụm là cách tệ nhất để nhận ra một tập chín
phần tử.

Ranh giới — giống hệt W32, không nới thêm gì
=============================================

LLM **không** chọn ref, **không** tính số, **không** quyết định gate. Nó trả về
đúng MỘT chuỗi trong ``SHAPES``, và chuỗi đó bị kiểm hai lần:

    shape ∈ SHAPES                              ⇒ qua cửa một
    shape ÁP ĐƯỢC vào request hiện tại          ⇒ qua cửa hai
    ngược lại                                   ⇒ vứt, hệ giữ hành vi cũ

Cửa hai mới là cửa thật: ``argmin`` trên một request chưa bind measure nào là vô
nghĩa; ``median`` trên một measure mà catalog không chứng nhận median là một phép
tính bị cấm. Hai điều đó kiểm được TẤT ĐỊNH, nên một hình dạng bịa không thể đi
tới plan.

Điều kiện bắn — HẸP có chủ đích
================================

Chỉ khi đường tất định để lại đúng khoảng trống này: có measure, có cụm chọn-một,
mà KHÔNG suy ra được ranking lẫn phép tổng hợp. Đó chính là ca
*"cửa hàng nào có doanh thu thấp"* — hôm nay ghi ambiguity và `clarify`. Không
có proposer thì hành vi đó giữ nguyên từng bit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

# Tập ĐÓNG các hình dạng. Chín phần tử, và chúng KHÔNG đổi theo bộ dữ liệu —
# đó là điểm chính: đổi miền thì catalog viết lại, còn tập này giữ nguyên.
SHAPES = frozenset({
    "count", "argmax", "argmin", "median", "mean", "share", "list",
    "compare", "lookup",
})

# Hình dạng suy ra một CỰC TRỊ: cần một đại lượng để xếp hạng.
_RANKING_SHAPES = {"argmax": "desc", "argmin": "asc"}

# Hình dạng là một PHÉP TỔNG HỢP: phải được catalog chứng nhận cho measure đó.
_AGGREGATION_SHAPES = frozenset({"count", "median", "mean", "share"})


class ShapeProposer(Protocol):
    def propose_shape(self, payload: dict) -> dict: ...


@dataclass
class ShapeResolution:
    """Kết quả MỘT lượt, kèm đủ khoá telemetry để đếm được nhánh đã bắn.

    Rỗng mang hai nghĩa khác nhau và chúng phải phân biệt được: chưa từng hỏi
    (``called=False``) khác hẳn đã hỏi nhưng bị vứt (``called=True``,
    ``rejected`` có giá trị). Thiếu phân biệt đó thì "đã đo" và "đã chạy" trông
    giống nhau — lỗi WP-A11 đã mắc một lần.
    """

    shape: str | None = None
    rejected: str | None = None
    reason: str | None = None
    called: bool = False
    failed: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_attrs(self) -> dict[str, Any]:
        return {
            "llm_shape_called": self.called,
            "llm_shape_accepted": self.shape,
            **({"llm_shape_rejected": self.rejected} if self.rejected else {}),
            **({"llm_shape_reason": self.reason} if self.reason else {}),
            **({"llm_shape_failed": self.failed} if self.failed else {}),
        }


def applicable_shapes(measure_refs: tuple[str, ...]) -> tuple[str, ...]:
    """Hình dạng ÁP ĐƯỢC cho request hiện tại — chính là danh sách gửi đi.

    Gửi cả chín luôn cũng rẻ, nhưng gửi đúng lát thì cơ hội nhận về một hình
    dạng không dùng được biến mất — cách rẻ nhất để thu hẹp lỗi, cùng lý do
    ``term_resolver.candidate_refs`` gửi lát catalog thay vì cả kho.
    """
    from gladiators.domain.catalog import CATALOG

    if not measure_refs:
        # Chưa bind measure nào thì mọi hình dạng cần một đại lượng đều vô
        # nghĩa; chỉ còn những hình dạng nói về CÁC DÒNG.
        return ("list", "lookup", "count")
    allowed: set[str] = {"list", "lookup", "compare"}
    for ref in measure_refs:
        obj = CATALOG.get(ref)
        if obj is None:
            continue
        allowed |= set(_RANKING_SHAPES)
        allowed |= {
            shape for shape in _AGGREGATION_SHAPES
            if shape in obj.valid_aggregations
        }
    return tuple(sorted(allowed & SHAPES))


def resolve_shape(
    question: str,
    measure_refs: tuple[str, ...],
    proposer: ShapeProposer | Callable[[dict], dict] | None,
    *,
    language: str = "vi",
) -> ShapeResolution:
    """Hình dạng câu hỏi, hoặc rỗng. Không có proposer ⇒ không làm gì.

    Vắng LLM là trạng thái MẶC ĐỊNH và phải im lặng đi qua: đường tất định trả
    lời phần lớn câu, và tầng này chỉ tồn tại cho phần còn lại.
    """
    if proposer is None:
        return ShapeResolution()
    allowed = applicable_shapes(measure_refs)
    if not allowed:
        return ShapeResolution()

    payload = {
        "question": question,
        "language": language,
        "measures": list(measure_refs),
        # Danh sách ĐÓNG. Prompt nói rõ chỉ được chọn trong đây; phép kiểm bên
        # dưới không tin lời nói đó.
        "shapes": list(allowed),
    }
    call = getattr(proposer, "propose_shape", proposer)
    try:
        raw = call(payload)
    except Exception as exc:                       # noqa: BLE001 — lỗi LLM là
        # một kết cục bình thường: hệ quay về đúng hành vi khi không có LLM, và
        # ghi lại LOẠI lỗi để đếm được.
        return ShapeResolution(called=True, failed=type(exc).__name__)

    if not isinstance(raw, dict):
        return ShapeResolution(called=True, failed="shape")
    proposed = raw.get("shape")
    if proposed is None or proposed == "":
        # "Không biết" là một câu trả lời hợp lệ.
        return ShapeResolution(called=True)
    if not isinstance(proposed, str) or proposed not in SHAPES:
        return ShapeResolution(
            called=True, rejected=str(proposed), reason="ngoài tập đóng",
        )
    if proposed not in allowed:
        return ShapeResolution(
            called=True, rejected=proposed,
            reason="không áp được vào measure đã bind",
        )
    return ShapeResolution(called=True, shape=proposed)


def ranking_direction(shape: str | None) -> str | None:
    """``desc``/``asc`` nếu hình dạng là một cực trị, ngược lại ``None``."""
    return _RANKING_SHAPES.get(shape or "")


def aggregation_of(shape: str | None) -> str | None:
    """Phép tổng hợp nếu hình dạng là một phép tổng hợp, ngược lại ``None``."""
    return shape if shape in _AGGREGATION_SHAPES else None
