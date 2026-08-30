"""Table registry và Metadata Binding Snapshot — §E1.

Điều được kiểm ở đây là *binding*, không phải sự tồn tại của dataclass. Một
registry mới chỉ để trang trí là rủi ro lớn nhất của thay đổi này (§A), nên mỗi
test hỏi một câu về hành vi: ID có resolve không, hash có động khi semantics
động không, sai sót có làm build dừng không.
"""
from __future__ import annotations

import copy
import dataclasses

import pytest

from gladiators.data.coverage import ARTIFACTS
from gladiators.domain import bindings
from gladiators.domain.bindings import (
    BindingError,
    build_binding_snapshot,
    default_binding_snapshot,
    load_coverage_manifest,
)
from gladiators.domain.tables import (
    OPTIONAL_ARTIFACTS,
    ArtifactName,
    PhysicalColumnRef,
    QualityCheckRef,
    TableColumnSpec,
    TableDeclaration,
    TableRegistryError,
    build_table_registry,
    parse_physical,
)


@pytest.fixture(scope="module")
def manifest():
    return load_coverage_manifest()


@pytest.fixture(scope="module")
def snapshot():
    return default_binding_snapshot()


# --- shape đã đo được -----------------------------------------------------

def test_registry_covers_eight_artifacts_and_219_columns(snapshot):
    """7 → 8 artifact: ``shop_stats_clean.csv`` (panel ngày cấp shop) được KHAI
    ở registry nhưng bản dữ liệu đóng băng CHƯA THU nó, nên nó đóng góp 0 cột.
    Đó chính là hình dạng cần khoá: có mặt trong registry (nên không ai phải giữ
    một danh sách artifact thứ hai) và rỗng cột (nên không ai nhầm nó với một
    bảng đã thu mà không có dòng nào)."""
    counts = snapshot.counts()
    assert counts["tables"] == 8
    assert counts["columns"] == 219
    # 83 từ W11.2 (derived.has_promo bind cột đã materialize
    # has_displayed_discount thay vì suy lại từ discount tại query time) + 11
    # binding của panel ngày cấp shop. Đếm ở đây là binding CATALOG KHAI, không
    # phải binding đã resolve ra cột thật — 11 cái mới trỏ vào một artifact bản
    # này chưa thu, và ``columns == 219`` bên trên chính là chỗ nói điều đó.
    assert counts["catalog_bindings"] == 94
    assert set(snapshot.tables) == set(ArtifactName)
    assert snapshot.tables[ArtifactName.SHOP_STATS].columns == ()


def test_view_names_are_unique(snapshot):
    views = [spec.view_name for spec in snapshot.tables.values()]
    assert len(views) == len(set(views)) == 8


def test_coverage_artifacts_are_generated_not_declared_twice():
    """§E1: bốn consumer từng giữ bốn bản danh sách artifact."""
    assert ARTIFACTS == tuple(name.value for name in ArtifactName)


# --- fail-closed ----------------------------------------------------------

def test_unknown_artifact_in_manifest_fails_the_build(manifest):
    broken = copy.deepcopy(manifest)
    broken["entries"].append(
        {"table": "not_a_real_artifact.csv", "column": "x", "status": "identifier_only",
         "catalog_ref": None}
    )
    with pytest.raises(TableRegistryError, match="ngoài registry|không nằm trong registry"):
        build_table_registry(broken, quality_handlers=bindings.quality_check_handlers())


def test_duplicate_manifest_entry_fails_the_build(manifest):
    broken = copy.deepcopy(manifest)
    broken["entries"].append(copy.deepcopy(broken["entries"][0]))
    with pytest.raises(TableRegistryError, match="trùng"):
        build_table_registry(broken, quality_handlers=bindings.quality_check_handlers())


def test_artifact_without_manifest_entry_fails_the_build(manifest):
    broken = copy.deepcopy(manifest)
    broken["entries"] = [
        entry for entry in broken["entries"]
        if entry["table"] != ArtifactName.SHOP_INFO.value
    ]
    with pytest.raises(TableRegistryError, match="không có manifest entry"):
        build_table_registry(broken, quality_handlers=bindings.quality_check_handlers())


def test_duplicate_view_name_fails_the_build(manifest):
    declarations = tuple(
        dataclasses.replace(declaration, view_name="products")
        if declaration.name is ArtifactName.SHOP_INFO else declaration
        for declaration in _declarations()
    )
    with pytest.raises(TableRegistryError, match="View trùng"):
        build_table_registry(manifest, declarations, bindings.quality_check_handlers())


def test_unresolved_quality_handler_fails_the_build(manifest):
    """Bài học từ ``validator_id``: một ID không trỏ tới code là prose mặc schema."""
    declarations = tuple(
        dataclasses.replace(
            declaration,
            quality_checks=(QualityCheckRef("x.check", "handler.does_not_exist"),),
        )
        if declaration.name is ArtifactName.PRODUCTS else declaration
        for declaration in _declarations()
    )
    with pytest.raises(TableRegistryError, match="handler"):
        build_table_registry(manifest, declarations, bindings.quality_check_handlers())


def test_grain_referencing_a_missing_column_fails_the_build(manifest):
    declarations = tuple(
        dataclasses.replace(declaration, grain=("column_khong_ton_tai",))
        if declaration.name is ArtifactName.PRODUCTS else declaration
        for declaration in _declarations()
    )
    with pytest.raises(TableRegistryError, match="grain"):
        build_table_registry(manifest, declarations, bindings.quality_check_handlers())


def _declarations() -> tuple[TableDeclaration, ...]:
    from gladiators.domain.tables import TABLE_DECLARATIONS

    return TABLE_DECLARATIONS


# --- physical parsing -----------------------------------------------------

def test_physical_string_is_parsed_from_the_right(snapshot):
    """Tên artifact chứa dấu chấm; tách từ trái sẽ cắt ngay ở ``.csv``."""
    ref = parse_physical("products_clean.csv.price_num")
    assert ref == PhysicalColumnRef(ArtifactName.PRODUCTS, "price_num")
    assert str(ref) == "products_clean.csv.price_num"
    assert snapshot.has_column(ref)


def test_physical_string_for_unknown_artifact_is_rejected():
    with pytest.raises(TableRegistryError):
        parse_physical("khong_co_bang.csv.some_column")


def test_every_catalog_binding_resolves_to_a_real_column(snapshot):
    """§B.2 đo 0 lỗi / 82 mapping — test giữ con số đó là bất biến, không may mắn.

    Ngoại lệ DUY NHẤT được khai: binding trỏ vào một artifact TUỲ CHỌN mà bản dữ
    liệu này chưa thu. "Chưa thu" không phải "khai sai" — nếu chặn nó ở đây thì
    một năng lực mới chỉ khai được sau khi MỌI bản dữ liệu cũ được thu lại. Ngoại
    lệ hẹp đúng bằng ``OPTIONAL_ARTIFACTS``: binding tới một artifact bắt buộc,
    hoặc tới một artifact tuỳ chọn ĐÃ thu, vẫn phải resolve.
    """
    uncollected = {
        name for name in OPTIONAL_ARTIFACTS if not snapshot.tables[name].columns
    }
    for obj in snapshot.catalog.values():
        for binding in obj.physical_bindings:
            if binding.table in uncollected:
                continue
            assert snapshot.has_column(binding), f"{obj.ref} -> {binding}"


def test_a_binding_to_a_collected_optional_artifact_still_must_resolve(snapshot):
    """Ngoại lệ trên KHÔNG được nới thành 'artifact tuỳ chọn thì miễn kiểm'."""
    from gladiators.domain.tables import TableSpec

    tables = dict(snapshot.tables)
    stats = tables[ArtifactName.SHOP_STATS]
    tables[ArtifactName.SHOP_STATS] = dataclasses.replace(
        stats, columns=(TableColumnSpec("mot_cot_khac", None, "identifier_only", None),),
    )
    with pytest.raises(BindingError, match="không tồn tại"):
        bindings.validate_metadata_bindings(tables, snapshot.catalog)


def test_binding_to_a_missing_column_fails_validation(snapshot):
    broken = dict(snapshot.catalog)
    victim = broken["measure.price"]
    broken["measure.price"] = dataclasses.replace(
        victim,
        physical_bindings=(PhysicalColumnRef(ArtifactName.PRODUCTS, "cot_khong_ton_tai"),),
    )
    with pytest.raises(BindingError, match="không tồn tại"):
        bindings.validate_metadata_bindings(snapshot.tables, broken)


# --- hash -----------------------------------------------------------------

def test_hashes_are_stable_across_rebuilds():
    first = build_binding_snapshot()
    second = build_binding_snapshot()
    assert first.binding_hash == second.binding_hash
    assert len(first.binding_hash) == 16


@pytest.mark.parametrize("field,value", [
    ("unit", "đơn_vị_khác"),
    ("grain", "grain_khác"),
    ("caveats", ("caveat mới",)),
    ("answerability", "absent"),
    ("valid_aggregations", ("count",)),
])
def test_catalog_hash_moves_when_any_semantic_field_moves(snapshot, field, value):
    """Hash bỏ sót một field nghĩa là field đó đổi được mà cache/gate/proof pack
    vẫn coi là cùng một thế giới — đúng lỗi mà ``REGISTRY_HASH`` cũ mắc phải."""
    mutated = dict(snapshot.catalog)
    mutated["measure.price"] = dataclasses.replace(
        mutated["measure.price"], **{field: value}
    )
    rebuilt = bindings.validate_metadata_bindings(snapshot.tables, mutated)
    assert rebuilt.catalog_hash != snapshot.catalog_hash
    assert rebuilt.binding_hash != snapshot.binding_hash


@pytest.mark.parametrize("field,value", [
    ("physical_type", "float64"),
    ("coverage_status", "absent"),
    ("partition", True),
])
def test_table_hash_moves_when_column_metadata_moves(snapshot, field, value):
    mutated = dict(snapshot.tables)
    products = mutated[ArtifactName.PRODUCTS]
    target = products.column("price_num")
    mutated[ArtifactName.PRODUCTS] = dataclasses.replace(
        products,
        columns=tuple(
            dataclasses.replace(column, **{field: value}) if column.name == target.name
            else column
            for column in products.columns
        ),
    )
    rebuilt = bindings.validate_metadata_bindings(mutated, snapshot.catalog)
    assert rebuilt.table_hash != snapshot.table_hash
    assert rebuilt.binding_hash != snapshot.binding_hash


def test_dropping_a_bound_column_fails_before_any_hash_is_produced(snapshot):
    """Fail-closed: binding tới cột đã biến mất phải dừng build, không phải sinh
    ra một hash mới trông hợp lệ."""
    mutated = dict(snapshot.tables)
    products = mutated[ArtifactName.PRODUCTS]
    mutated[ArtifactName.PRODUCTS] = dataclasses.replace(
        products,
        columns=tuple(c for c in products.columns if c.name != "price_num"),
    )
    with pytest.raises(BindingError, match="không tồn tại"):
        bindings.validate_metadata_bindings(mutated, snapshot.catalog)


def test_binding_hash_covers_all_five_registries(snapshot):
    """Nếu binding_hash chỉ là hash của một registry thì nó không ký được cái nó
    tuyên bố ký."""
    assert len({
        snapshot.table_hash, snapshot.catalog_hash, snapshot.relation_hash,
        snapshot.metric_hash, snapshot.invariant_hash,
    }) == 5
    assert snapshot.binding_hash not in {
        snapshot.table_hash, snapshot.catalog_hash, snapshot.relation_hash,
        snapshot.metric_hash, snapshot.invariant_hash,
    }
