"""Gợi ý câu hỏi gần nhất khi từ chối — Spec2308 §WP-A8.

``GateDecision.answerable_alternative`` đã tồn tại nhưng là **chuỗi viết tay cố
định** theo từng rule: nó không biết câu hỏi vừa rồi hỏi về cái gì.

Luật quan trọng nhất ở đây là A8-R1: gợi ý phải **chạy được thật**. Gợi ý một câu
mà hệ cũng từ chối thì tệ hơn không gợi ý — người dùng làm theo và nhận lời từ
chối thứ hai.
"""
from __future__ import annotations

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import ENTITY_BY_RIGHT_SOURCE, find_path

MAX_TRIALS = 4          # A8: bước chạy thử là phần đắt nhất, phải có trần
_BASE = ("products_clean.csv", "product_snapshot_metrics.csv")
_EXPOSED = {"exposed_as_dimension", "exposed_as_measure"}

# Điều kiện đã bind được thành predicate (WP-A4) — sinh từ registry, không khai
# lần hai, nên một điều kiện mới bật lên là gợi ý tự có thêm ứng viên.
def _qualifier_surfaces() -> dict[str, str]:
    from gladiators.domain.qualifiers import QUALIFIERS

    return {
        spec.ref: spec.surfaces[0]
        for spec in QUALIFIERS if spec.bindable and spec.surfaces
    }


_QUALIFIER_SURFACE = _qualifier_surfaces()


def _vietnamese_alias(ref: str) -> str | None:
    """Alias tiếng Việt đầu tiên đã khai. Không có thì không dựng câu."""
    obj = CATALOG.get(ref)
    if obj is None:
        return None
    for alias in obj.aliases:
        if any(ord(char) > 127 for char in alias):
            return alias
    return None


def _reachable(ref: str) -> bool:
    """Nằm trên spine, hoặc nối được bằng ĐÚNG MỘT cạnh."""
    obj = CATALOG.get(ref)
    if obj is None or not obj.physical:
        return False
    artifacts = {column.rpartition(".")[0] for column in obj.physical}
    if artifacts & set(_BASE):
        return True
    for artifact in artifacts:
        entity = ENTITY_BY_RIGHT_SOURCE.get(artifact)
        path = find_path("ProductListing", entity) if entity else None
        if path is not None and len(path) == 1:
            return True
    return False


def _candidates(bound: set[str]) -> list[str]:
    from gladiators.domain.topics import TOPICS

    topics = [
        topic for topic in TOPICS.values()
        if bound & set(topic.all_refs() or ())
    ]
    pool: list[str] = []
    for topic in topics:
        pool.extend(topic.all_refs() or ())
    return sorted({
        ref for ref in pool
        if ref not in bound
        and (obj := CATALOG.get(ref)) is not None
        and obj.answerability in _EXPOSED
        and _reachable(ref)
    } | set(_QUALIFIER_SURFACE) - bound)


def _question_for(ref: str, country: str, date: str) -> str | None:
    """Khuôn mẫu lấy từ DẠNG CÂU hệ thật sự trả lời được.

    Khuôn mẫu đầu tiên tôi viết theo spec — "<alias> trung vị của listing tại
    <thị trường> ngày <ngày> là bao nhiêu?" — bị chính hệ từ chối
    (`A22-ALIGN-MEASURE`), và bước chạy thử A8-R1 bắt được. Bề mặt trả lời được
    hiện nghiêng hẳn về câu ĐẾM và câu điều kiện, nên khuôn mẫu bám theo đó.
    """
    obj = CATALOG.get(ref)
    if obj is None:
        return None
    # Tra bảng khai. Bản cũ gán "Indonesia" cho MỌI thị trường không phải vn —
    # cùng hình dạng fail-open với `"VND" if country == "vn" else "IDR"`.
    from gladiators.domain.markets import display_name_of

    market = display_name_of(country)
    if ref in _QUALIFIER_SURFACE:
        # Dùng alias tiếng Việt của catalog, không dùng surface đã normalize:
        # surface bỏ dấu là dạng để KHỚP, không phải dạng để đọc.
        surface = _vietnamese_alias(ref) or _QUALIFIER_SURFACE[ref]
        return f"Có bao nhiêu listing {surface} tại {market} ngày {date}?"
    if obj.analysis_role == "analysis_unit" and obj.counting_key:
        alias = _vietnamese_alias(ref) or ref.split(".")[-1]
        return f"Có bao nhiêu {alias} ở {market}?"
    return None


def nearest_answerable(request, runtime) -> tuple[str, ...]:
    """Tối đa hai câu hỏi gần nhất mà hệ **thật sự** trả lời được.

    A8-R2: không bind được ref nào thì im lặng đúng hơn là đoán.
    """
    analytical = request.analytical
    if not analytical:
        return ()
    bound = {
        item.get("ref")
        for key in ("requested_measures", "requested_dimensions")
        for item in analytical.get(key, []) or []
        if isinstance(item, dict) and item.get("ref") and not item.get("unresolved")
    }
    bound.discard(None)
    if not bound:
        return ()

    from gladiators.domain.markets import DEFAULT_MARKET

    country = request.country or DEFAULT_MARKET
    date = "03/07"
    accepted: list[str] = []
    for ref in _candidates(bound)[:MAX_TRIALS]:
        question = _question_for(ref, country, date)
        if question is None:
            continue
        # A8-R1: chạy thử thật. Gợi ý chưa kiểm là gợi ý có thể dẫn tới lời từ
        # chối thứ hai.
        try:
            trial = runtime.run(question)
        except Exception:                            # noqa: BLE001
            continue
        if trial.gate.action == "allow" and trial.evidence:
            accepted.append(question)
        if len(accepted) == 2:
            break
    return tuple(accepted)
