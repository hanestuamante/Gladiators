"""Diễn đạt RelationSpec BẰNG LỜI — Spec2308 §WP-A7.3.

Cạm bẫy chết người của WP này: câu trả lời giải thích lược đồ **không có
evidence nào**, mà ``verifier.scan_numbers`` quét mọi số trong answer và đòi
evidence cho từng số. Chuỗi ``"1:N"`` chứa chữ số ``1`` và sẽ bị chấm là số bịa.

Vì vậy mọi hàm ở đây **cấm trả về ký hiệu mang chữ số**.
"""
from __future__ import annotations

from .relations import RELATIONS, RelationSpec

_CARDINALITY = {
    "N:1": "nhiều {left} thuộc về một {right}",
    "1:N": "một {left} có nhiều {right}",
    "N:M": "nhiều {left} ứng với nhiều {right}",
    "1:1": "mỗi {left} ứng với đúng một {right}",
}

_TEMPORAL = {
    "static_latest_only": (
        "chỉ có một mốc thời gian, nên đây là làm giàu tĩnh; "
        "không dùng cho câu hỏi theo chuỗi thời gian"
    ),
    "per_snapshot": "hợp lệ theo từng snapshot",
}

_FANOUT = {
    "none": "nối theo chiều này không gây nhân bản dòng",
    "duplicates_left_rows": "nối theo chiều này có thể nhân bản dòng bên trái",
}


def cardinality_prose(spec: RelationSpec) -> str:
    template = _CARDINALITY.get(spec.cardinality)
    if template is None:
        return "lực lượng chưa được mô tả bằng lời"
    return template.format(left=spec.left, right=spec.right)


def temporal_prose(spec: RelationSpec) -> str:
    return _TEMPORAL.get(spec.temporal_validity, "phạm vi thời gian chưa được mô tả")


def fanout_prose(spec: RelationSpec) -> str:
    text = _FANOUT.get(spec.fanout_effect, "ảnh hưởng nhân bản chưa được mô tả")
    if spec.fanout_effect != "none" and spec.dedupe_strategy:
        text += f"; khử trùng lặp theo {spec.dedupe_strategy}"
    return text


def edges_of(entity: str) -> tuple[RelationSpec, ...]:
    return tuple(
        spec for spec in RELATIONS.values()
        if entity in (spec.left, spec.right)
    )


def edge_between(left: str, right: str) -> RelationSpec | None:
    for spec in RELATIONS.values():
        if {spec.left, spec.right} == {left, right}:
            return spec
    return None


def explain(left: str, right: str | None = None) -> str:
    """Câu giải thích quan hệ, đọc thẳng từ registry.

    A7-R3: không tìm thấy cạnh thì NÓI RÕ là không có đường nối được chứng
    nhận. Đó là một câu trả lời đúng, không phải một lỗi.
    """
    # Hai hệ phân loại này không có đường nối dù hai cột cùng tên
    # `category_id` — INV-SHELF-NOT-PLATFORM-CATEGORY.
    if right and {left, right} == {"ShopCategory", "PlatformCategory"}:
        return (
            "Kệ hàng của shop và danh mục của sàn là hai hệ phân loại khác nhau "
            "và không có đường nối được chứng nhận giữa chúng. Hai bên có cột "
            "trùng tên nhưng không cùng ý nghĩa, nên nối chúng lại là tạo ra một "
            "quan hệ không tồn tại."
        )
    if right is None:
        specs = edges_of(left)
        if not specs:
            return f"{left} chưa có quan hệ nào được chứng nhận trong hệ thống."
        lines = [f"{left} nối được với những thực thể sau:"]
        for spec in specs:
            other = spec.right if spec.left == left else spec.left
            lines.append(f"- {other} qua quan hệ {spec.name}: {cardinality_prose(spec)}.")
        return "\n".join(lines)

    spec = edge_between(left, right)
    if spec is None:
        return (
            f"{left} và {right} không có đường nối được chứng nhận trong registry "
            "quan hệ, nên hệ thống không ghép chúng lại với nhau."
        )
    keys = ", ".join(sorted({key for pair in spec.join_keys for key in pair}))
    lines = [
        f"{spec.left} và {spec.right} nối với nhau qua quan hệ {spec.name}.",
        f"Lực lượng: {cardinality_prose(spec)}.",
        f"Nối bằng: {keys}.",
        f"Thời gian: {temporal_prose(spec)}.",
        f"Nhân bản dòng: {fanout_prose(spec)}.",
    ]
    # A7-R1: `interpretation` của belongs_to chứa "2026-07-03". Câu trả lời
    # này KHÔNG có evidence nào, nên mọi chữ số trong nó bị verifier chấm là
    # số bịa. Giữ mệnh đề không có số; bỏ hẳn còn hơn đưa ra câu bị chặn.
    clauses = [
        clause.strip() for clause in (spec.interpretation or "").split(",")
        if clause.strip() and not any(char.isdigit() for char in clause)
    ]
    if clauses:
        lines.append("Diễn giải: " + ", ".join(clauses) + ".")
    return "\n".join(lines)


# Tên entity trong registry quan hệ viết PascalCase; catalog viết `entity.snake`.
# Sinh bản đồ thay vì khai tay: hai bảng tên sẽ lệch nhau.
ENTITY_BY_REF: dict[str, str] = {
    ref: "".join(word.capitalize() for word in ref.split(".", 1)[1].split("_"))
    for ref in __import__(
        "gladiators.domain.catalog", fromlist=["CATALOG"],
    ).CATALOG
    if ref.startswith("entity.")
}

STRUCTURE_CUES: tuple[str, ...] = (
    "lien quan", "quan he", "noi voi nhau", "lien ket", "join",
    "relationship", "hubungan",
)
