"""Registry điều kiện boolean — Spec2308 §WP-A4.2.

Một điều kiện như *"chính hãng"* hay *"có voucher"* đã có cột vật lý hẳn hoi,
nhưng ``DeterministicSemanticParser.parse`` chỉ sinh predicate cho ``dim.country``
và ``dim.date``. Vì thế ``synthesizer._has_unbound_qualifier`` luôn bắn và
``synthesize()`` trả ``None`` cho **mọi** câu có điều kiện — kể cả điều kiện hệ
thống thừa sức lọc.

Registry này biến chúng thành predicate. Tập **đóng**: mở rộng phải qua review
(WP-B11), vì thêm một từ vào đây là mở rộng miền câu hỏi hệ tự nhận trả lời được.

Guard vẫn **một chiều**: một điều kiện chỉ ngừng làm synthesizer từ chối khi nó
THẬT SỰ đã trở thành predicate. Không có đường nào để một điều kiện chưa bind
lọt qua.
"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import CATALOG
from .relations import ENTITY_BY_RIGHT_SOURCE


class QualifierRegistryError(ValueError):
    """Khai báo điều kiện không khớp catalog — dừng ngay lúc import."""


@dataclass(frozen=True)
class QualifierSpec:
    qualifier_id: str
    ref: str                      # phải có trong CATALOG và có physical
    surfaces: tuple[str, ...]     # đã normalize, đã bỏ dấu
    negations: tuple[str, ...]    # surface mang nghĩa phủ định
    # W8.3: hợp đồng predicate có KIỂU, dùng chuẩn operator §12.2.1 — cờ nhãn
    # voucher bind vào vouchers_count cần "gte 1", không phải "eq True"; một
    # qualifier hard-code eq bool sẽ biên dịch sai kiểu hoặc bị catalog từ chối.
    value: object = True
    op: str = "eq"
    negated_op: str = "eq"
    negated_value: object = False
    null_policy: str = "exclude"
    # Bind được thành predicate hay chưa. Xem `_BASE_SCAN_ARTIFACT` bên dưới:
    # một điều kiện nằm ở bảng khác cần join mà grammar hiện tại đặt sai chỗ,
    # nên nó phải TIẾP TỤC bị từ chối thay vì lọc hụt trong im lặng.
    bindable: bool = False


# Tập ban đầu — ĐÓNG. Bốn điều kiện này đều đã có cột vật lý trong catalog.
QUALIFIERS: tuple[QualifierSpec, ...] = (
    QualifierSpec(
        "shop_official", "dim.shop_official",
        ("chinh hang", "official", "official shop", "shop chinh hang"),
        ("khong chinh hang",),
        bindable=True,      # A1: nF2 lọc SAU join belongs_to
    ),
    QualifierSpec(
        "shop_vacation", "dim.shop_vacation",
        ("nghi ban", "vacation"),
        ("khong nghi ban",),
        bindable=True,      # A1: nF2 lọc SAU join belongs_to
    ),
    # W8.3: "có voucher" trần là HAI khái niệm (structured 0/474 trên ID so
    # với nhãn hiển thị 210/474) — surface trần rời khỏi registry, chỉ còn hai
    # qualifier tường minh; cụm trần thành alias của CẢ HAI ref và fail-closed
    # bằng ambiguity ở _link.
    QualifierSpec(
        "has_structured_voucher", "derived.has_structured_voucher",
        ("voucher co cau truc", "ma voucher co cau truc"),
        ("khong co voucher co cau truc",),
        bindable=True,      # A1: nF2 lọc SAU join has_sales_metric
    ),
    QualifierSpec(
        # ref là cột ĐẾM nhãn (xem ghi chú _DERIVED_PHYSICAL ở catalog.py):
        # "có nhãn voucher" nghĩa là vouchers_count >= 1.
        "has_voucher_label", "measure.vouchers_count",
        ("co nhan voucher", "voucher hien thi", "nhan voucher"),
        ("khong co nhan voucher",),
        # Cột đếm nhãn: dương là "ít nhất một nhãn", phủ định là "không nhãn
        # nào" — và null KHÔNG suy thành "không có" (null_policy exclude).
        value=1, op="gte", negated_op="lte", negated_value=0,
        bindable=True,
    ),
    QualifierSpec(
        "shopee_verified", "dim.shopee_verified",
        ("da xac minh", "shopee verified"),
        ("chua xac minh",),
        bindable=True,      # products_clean — cùng bảng synthesizer quét
    ),
)


def _validate(specs: tuple[QualifierSpec, ...]) -> tuple[QualifierSpec, ...]:
    """Fail-at-import như các registry khác.

    Một điều kiện trỏ ref không có cột vật lý sẽ làm compiler chết giữa chừng
    thay vì từ chối tử tế — nên nó phải chết ở đây, lúc khởi động.
    """
    seen: set[str] = set()
    for spec in specs:
        if spec.qualifier_id in seen:
            raise QualifierRegistryError(f"qualifier_id trùng: {spec.qualifier_id}")
        seen.add(spec.qualifier_id)

        obj = CATALOG.get(spec.ref)
        if obj is None:
            raise QualifierRegistryError(
                f"{spec.qualifier_id}: ref không có trong catalog: {spec.ref}"
            )
        if not obj.physical:
            raise QualifierRegistryError(
                f"{spec.qualifier_id}: {spec.ref} không có cột vật lý nên không "
                "lọc được; khai nó ở đây chỉ làm compiler chết giữa chừng"
            )
        if "eq" not in obj.allowed_filters:
            raise QualifierRegistryError(
                f"{spec.qualifier_id}: {spec.ref} không cho phép filter 'eq'"
            )
        if not spec.surfaces:
            raise QualifierRegistryError(f"{spec.qualifier_id}: thiếu surface")
        overlap = set(spec.surfaces) & set(spec.negations)
        if overlap:
            raise QualifierRegistryError(
                f"{spec.qualifier_id}: surface vừa khẳng định vừa phủ định: {sorted(overlap)}"
            )
    return specs


# Bảng mà bộ sinh kế hoạch deterministic quét làm nguồn gốc. Điều kiện nằm ngoài
# bảng này cần một join, và grammar hiện tại đặt predicate vào SAI subquery:
# "bao nhiêu listing của shop official tại VN" sinh ra
#     WHERE ... AND is_official_shop_bool = ?   -- áp lên `products`
#     LEFT JOIN shop_info ...                   -- cột thật ở đây, join SAU
# nên bộ lọc không lọc gì: hệ trả 668 (toàn bộ VN) trong khi đáp án là 465.
#
# Một con số sai tự tin tệ hơn một lần từ chối, nên ba điều kiện kia giữ nguyên
# trạng thái từ chối cho tới khi WP-A1 đưa đồ thị quan hệ vào bộ sinh kế hoạch.
_BASE_SCAN_ARTIFACT = "products_clean.csv"


def _bindable_matches_physical(spec: QualifierSpec) -> bool:
    obj = CATALOG[spec.ref]
    return all(col.startswith(f"{_BASE_SCAN_ARTIFACT}.") for col in obj.physical)


QUALIFIERS = _validate(QUALIFIERS)
# A1.4 đã tách predicate phía phải sang node `nf2` chạy SAU join, nên cột nằm
# ngoài bảng gốc không còn bị đặt sai subquery. Điều kiện để bind giờ là: ref
# phải tới được từ tâm ProductListing bằng đúng một cạnh.
for _spec in QUALIFIERS:
    if not _spec.bindable:
        continue
    _sources = {c.rpartition(".")[0] for c in CATALOG[_spec.ref].physical}
    if _BASE_SCAN_ARTIFACT in _sources:
        continue
    if not any(src in ENTITY_BY_RIGHT_SOURCE for src in _sources):
        raise QualifierRegistryError(
            f"{_spec.qualifier_id}: khai bindable nhưng cột nằm ngoài "
            f"{_BASE_SCAN_ARTIFACT} và không có cạnh quan hệ nào mang nó về"
        )

# Mọi marker mà registry này bind được. `synthesizer` sinh guard từ đây thay vì
# giữ một danh sách thứ hai: marker của một điều kiện đã bind được sẽ TỰ rời
# khỏi guard, không cần ai nhớ xoá tay.
BOUND_QUALIFIER_SURFACES: frozenset[str] = frozenset(
    surface
    for spec in QUALIFIERS
    for surface in spec.surfaces + spec.negations
)


# Dấu hiệu câu đang GOM NHÓM theo một chiều, không LỌC theo nó. "Vouchers count
# THEO official shop" muốn bảng chia hai nhóm; biến nó thành filter là trả lời
# "vouchers count của riêng shop chính hãng" — một câu hỏi khác, và output trông
# hoàn chỉnh y hệt. Đây là ca mà khoá hồi quy P0 `grouping-dropped-official-shop`
# tồn tại để bắt.
_GROUPING_CUES: tuple[str, ...] = ("theo", "tung", "moi", "by", "per", "group by")


def _is_grouping(normalized: str, surface: str) -> bool:
    """True khi ``surface`` đang đóng vai chiều gom nhóm, không phải bộ lọc.

    Hai hình dạng, cả hai đều KHÔNG phải lọc:

    * cue đứng ngay trước — *"vouchers count THEO official shop"*: chia kết quả
      theo official/không-official;
    * surface đứng trước cue — *"SHOPEE VERIFIED theo product"*: chính nó là thứ
      được xem, product mới là chiều chia.

    Câu không có cue nào — *"bao nhiêu listing CỦA shop official"* — mới là lọc.
    """
    cue_at = min(
        (normalized.find(f" {cue} ") for cue in _GROUPING_CUES
         if f" {cue} " in normalized),
        default=-1,
    )
    start = normalized.find(surface)
    while start != -1:
        if any(normalized[:start].rstrip().endswith(cue) for cue in _GROUPING_CUES):
            return True
        if cue_at != -1 and start < cue_at:
            return True
        start = normalized.find(surface, start + 1)
    return False


@dataclass(frozen=True)
class MatchedQualifier:
    spec: QualifierSpec
    op: str
    value: object
    surface: str


def match(normalized: str) -> list["MatchedQualifier"]:
    """Điều kiện LỌC xuất hiện trong câu, kèm giá trị và surface đã khớp.

    Kiểm phủ định TRƯỚC: ``"khong co voucher"`` chứa ``"co voucher"``, nên xét
    theo chiều ngược lại sẽ bind đúng ngược nghĩa câu hỏi.

    Surface đứng sau một dấu hiệu gom nhóm thì KHÔNG phải điều kiện lọc — nó là
    chiều để chia kết quả, và phải ở lại làm dimension.
    """
    hits: list[tuple[QualifierSpec, bool, str]] = []
    for spec in QUALIFIERS:
        if not spec.bindable:
            continue
        hit = next(
            ((s, spec.negated_op, spec.negated_value) for s in spec.negations
             if s in normalized),
            next(((s, spec.op, spec.value) for s in spec.surfaces
                  if s in normalized), None),
        )
        if hit is None:
            continue
        surface, op, value = hit
        if _is_grouping(normalized, surface):
            continue
        hits.append(MatchedQualifier(spec=spec, op=op, value=value, surface=surface))
    return hits
