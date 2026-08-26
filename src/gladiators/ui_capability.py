"""Bản đồ năng lực — Spec2308 §WP-B8.

Người dùng và giám khảo biết hệ làm được gì **trước khi** bị từ chối, đảo ý
nghĩa của mọi lời từ chối từ *"hệ này yếu"* thành *"hệ này biết rõ ranh giới
của nó"*.

B8-R1: mọi mục **sinh từ registry**. Thêm một intent là trang tự cập nhật —
không có danh sách viết tay nào để lệch.
B8-R3: không dùng ``streamlit`` (gói đó chưa khai trong requirements).
"""
from __future__ import annotations

from html import escape

from gladiators.agent.gate import CAPABILITY_MESSAGES
from gladiators.agent.parser import UNSUPPORTED
from gladiators.domain.catalog import CATALOG
from gladiators.domain.intent_registry import default_registry

# Ba giới hạn của chính dataset, viết BẰNG LỜI. Chúng không suy được từ registry
# nên phải khai ở đây — nhưng chúng là sự thật về dữ liệu, không phải danh sách
# năng lực (B8-R1 nói về năng lực).
DATASET_LIMITS: tuple[str, ...] = (
    "Ba snapshot trong ba ngày, nên không dự báo, không mùa vụ, không nhân quả.",
    "Đơn vị nhỏ nhất là một sản phẩm tại một shop, nên không phân tích theo mã phân loại chi tiết.",
    "Cờ hết hàng không đổi trên toàn bộ dữ liệu, nên không phân tích tình trạng hết hàng.",
)

# Câu hỏi mẫu cho mỗi intent. B8-R2 buộc chúng phải CHẠY ĐƯỢC THẬT, và test
# khẳng định điều đó — một câu mẫu không chạy được là một lời hứa sai.
SAMPLE_QUESTIONS: dict[str, str] = {
    "voucher_coverage": "Có bao nhiêu listing có voucher tại Việt Nam ngày 03/07?",
    "promotion_effectiveness": "So sánh nhóm có voucher và không voucher tại Việt Nam",
    "open_analytical": "Có bao nhiêu shop ở Việt Nam?",
    "schema_relation_explain": "Shop và listing liên quan thế nào?",
    # Hai intent dưới đây chỉ tới được qua câu HỢP PHẦN: người dùng hỏi một thứ
    # hệ không có (chuyển đổi, dự báo), và hệ trả lời phần nó CÓ. Câu mẫu đơn
    # giản như "Dataset có những gì?" không chạm tới chúng — thử bốn cách diễn
    # đạt đều rơi về open_analytical.
    "discount_bucket_observation": "Tỷ lệ chuyển đổi của listing giảm giá 50 tại VN là bao nhiêu?",
    "dataset_coverage": "Dự báo doanh số tháng 8 tại VN là bao nhiêu?",
}

# Intent chỉ phục vụ PHẦN hỗ trợ được của một câu hỏi hợp phần. Ghi rõ để bản đồ
# không hứa rằng gõ thẳng chủ đề đó sẽ ra kết quả.
PARTIAL_ANSWER_INTENTS: frozenset[str] = frozenset({
    "discount_bucket_observation", "dataset_coverage",
})


def capability_map() -> dict[str, object]:
    """Dữ liệu thuần cho cả trang HTML lẫn endpoint JSON — một nguồn duy nhất."""
    registry = default_registry()
    answerable, needs_more = [], []
    for name in sorted(registry.names()):
        spec = registry.get(name)
        row = {
            "intent": name,
            "required_slots": list(spec.required_slots),
            "sample": SAMPLE_QUESTIONS.get(name),
            "partial_answer_only": name in PARTIAL_ANSWER_INTENTS,
        }
        (needs_more if spec.required_slots else answerable).append(row)

    exposed = sorted(
        ref for ref, obj in CATALOG.items()
        if obj.answerability in {"exposed_as_dimension", "exposed_as_measure"}
    )
    unsupported = [
        {
            "capability": name,
            "surfaces": list(surfaces),
            "message": (CAPABILITY_MESSAGES.get(name) or {}).get("reason")
            or (CAPABILITY_MESSAGES.get(name) or {}).get("message")
            or "Dữ liệu công khai của sàn không chứa năng lực này.",
        }
        for name, surfaces in sorted(UNSUPPORTED.items())
    ]
    return {
        "answerable": answerable,
        "needs_more_information": needs_more,
        "not_answerable": unsupported,
        "exposed_refs": exposed,
        "dataset_limits": list(DATASET_LIMITS),
    }


def _column(title: str, rows: list[str], accent: str) -> str:
    body = "".join(f"<li>{row}</li>" for row in rows)
    return (
        f'<section style="flex:1;min-width:20rem"><h2 style="color:{accent}">'
        f"{escape(title)}</h2><ul>{body}</ul></section>"
    )


def render() -> str:
    data = capability_map()
    answerable = [
        f"<b>{escape(str(row['intent']))}</b>"
        + (f"<br><i>{escape(str(row['sample']))}</i>" if row["sample"] else "")
        + ("<br><small>chỉ trả lời phần hỗ trợ được của một câu hỏi hợp phần</small>"
           if row["partial_answer_only"] else "")
        for row in data["answerable"]
    ]
    needs = [
        f"<b>{escape(str(row['intent']))}</b> — cần: "
        + escape(", ".join(row["required_slots"]))
        for row in data["needs_more_information"]
    ]
    nope = [
        f"<b>{escape(str(row['capability']))}</b><br>{escape(str(row['message']))}"
        for row in data["not_answerable"]
    ]
    limits = "".join(f"<li>{escape(item)}</li>" for item in data["dataset_limits"])
    return (
        "<h1>Bản đồ năng lực</h1>"
        "<p>Hệ thống này được phép nói “tôi không biết”. Trang này cho biết ranh "
        "giới đó nằm ở đâu, <b>trước khi</b> bạn gặp một lời từ chối.</p>"
        '<div style="display:flex;gap:2rem;flex-wrap:wrap">'
        + _column("Hỏi được", answerable, "#2F7A4F")
        + _column("Hỏi được nhưng cần thêm thông tin", needs, "#C96F1E")
        + _column("Không hỏi được, và vì sao", nope, "#A6333F")
        + "</div>"
        + f"<h2>Giới hạn của chính dữ liệu</h2><ul>{limits}</ul>"
    )
