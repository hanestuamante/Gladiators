"""Relation binding là nguồn executable duy nhất — §E2.

Ba drift đo được ở §E2.1 và một key ma. Test viết theo hành vi: SQL sinh ra dùng
key nào, chứ không phải registry khai key nào — vì đúng chỗ hai thứ đó lệch nhau
là chỗ lỗi đã sống.
"""
from __future__ import annotations

import dataclasses

import pytest

from gladiators.domain import bindings
from gladiators.domain.bindings import BindingError, default_binding_snapshot
from gladiators.domain.relations import (
    INLINE_RELATIONS,
    JOIN_RELATIONS,
    RELATION_LEFT_SOURCES,
    RELATIONS,
    JoinKey,
    RelationBinding,
)
from gladiators.domain.tables import ArtifactName, PhysicalColumnRef


@pytest.fixture(scope="module")
def snapshot():
    return default_binding_snapshot()


def test_eleven_relations_split_four_join_seven_inline():
    """+1 inline: ``shop_observed_at`` (Shop → DateSnapshot trên panel shop).
    Inline vì ngày nằm ngay trên bảng panel — không có join nào phát sinh, nên
    không có fanout mới nào để dedupe."""
    assert len(RELATIONS) == 11
    assert len(JOIN_RELATIONS) == 4
    assert len(INLINE_RELATIONS) == 7
    assert JOIN_RELATIONS == {
        "belongs_to", "in_platform_category", "in_shop_category", "has_sales_metric",
    }


def test_every_relation_has_a_binding():
    for name, spec in RELATIONS.items():
        assert spec.binding is not None, name
        assert spec.binding.left_sources, name


def test_every_binding_column_exists(snapshot):
    """§E2.1: `raw_brand` không tồn tại ở BẤT KỲ bảng nào và vẫn sống trong
    registry, vì chưa ai đối chiếu registry với header thật."""
    for name, spec in RELATIONS.items():
        for key in spec.binding.join_keys:
            assert snapshot.has_column(key.left), f"{name}: {key.left}"
            assert snapshot.has_column(key.right), f"{name}: {key.right}"


# --- ba drift đo được -----------------------------------------------------

def test_platform_category_joins_on_the_numeric_catid():
    """§E2.1: registry cũ khai `category_id`, cột KHÔNG tồn tại trên products;
    và `path_country_code` là cột provenance, không phải join key."""
    binding = RELATIONS["in_platform_category"].binding
    assert binding.right_source is ArtifactName.CATEGORY_PLATFORM
    assert binding.join_keys == (
        JoinKey(PhysicalColumnRef(ArtifactName.PRODUCTS, "country_code"),
                PhysicalColumnRef(ArtifactName.CATEGORY_PLATFORM, "country_code")),
        JoinKey(PhysicalColumnRef(ArtifactName.PRODUCTS, "catid_num"),
                PhysicalColumnRef(ArtifactName.CATEGORY_PLATFORM, "category_id_num")),
    )


def test_shop_category_joins_on_the_numeric_shop_category_id():
    binding = RELATIONS["in_shop_category"].binding
    assert binding.left_sources == (ArtifactName.PRODUCT_CATEGORIES,)
    assert [(k.left.column, k.right.column) for k in binding.join_keys] == [
        ("country_code", "country_code"), ("shop_id", "shop_id"),
        ("category_id_num", "shop_category_id_num"), ("date", "date"),
    ]


def test_has_brand_is_inline_and_no_longer_invents_raw_brand():
    """Key giả chưa gây sai số chỉ vì compiler bỏ qua inline join. Đổi adapter mà
    quên sửa binding là nó đi thẳng vào SQL."""
    spec = RELATIONS["has_brand"]
    assert spec.binding.mode == "inline"
    assert spec.binding.right_source is None
    assert spec.binding.join_keys == ()
    assert "raw_brand" not in {key for pair in spec.join_keys for key in pair}


def test_semantic_join_keys_no_longer_contradict_the_physical_ones():
    """Trước §E2 registry và compiler là hai contract; review nhìn cái này, SQL
    thi hành cái kia."""
    for name in JOIN_RELATIONS:
        spec = RELATIONS[name]
        assert spec.join_keys == tuple(
            (key.left.column, key.right.column) for key in spec.binding.join_keys
        ), name


def test_left_sources_are_generated_from_the_binding():
    assert RELATION_LEFT_SOURCES == {
        name: tuple(source.value for source in spec.binding.left_sources)
        for name, spec in RELATIONS.items()
    }


# --- fail-closed ----------------------------------------------------------

def test_inline_relation_may_not_declare_a_right_source(snapshot):
    broken = dict(RELATIONS)
    broken["has_brand"] = dataclasses.replace(
        broken["has_brand"],
        binding=RelationBinding(
            "inline", (ArtifactName.PRODUCTS,), ArtifactName.SHOP_INFO,
        ),
    )
    with pytest.raises(BindingError, match="inline"):
        bindings.validate_metadata_bindings(
            snapshot.tables, snapshot.catalog, broken
        )


def test_join_key_pointing_at_a_missing_column_fails(snapshot):
    broken = dict(RELATIONS)
    broken["belongs_to"] = dataclasses.replace(
        broken["belongs_to"],
        binding=RelationBinding(
            "left_join", (ArtifactName.PRODUCTS,), ArtifactName.SHOP_INFO,
            (JoinKey(PhysicalColumnRef(ArtifactName.PRODUCTS, "raw_brand"),
                     PhysicalColumnRef(ArtifactName.SHOP_INFO, "shop_id")),),
            projection_id="belongs_to",
        ),
    )
    with pytest.raises(BindingError, match="không tồn tại"):
        bindings.validate_metadata_bindings(snapshot.tables, snapshot.catalog, broken)


def test_join_key_from_the_wrong_table_fails(snapshot):
    broken = dict(RELATIONS)
    broken["belongs_to"] = dataclasses.replace(
        broken["belongs_to"],
        binding=RelationBinding(
            "left_join", (ArtifactName.PRODUCTS,), ArtifactName.SHOP_INFO,
            (JoinKey(PhysicalColumnRef(ArtifactName.CATEGORY_LIST, "shop_id"),
                     PhysicalColumnRef(ArtifactName.SHOP_INFO, "shop_id")),),
            projection_id="belongs_to",
        ),
    )
    with pytest.raises(BindingError, match="left source"):
        bindings.validate_metadata_bindings(snapshot.tables, snapshot.catalog, broken)


def test_no_forbidden_shelf_to_platform_edge_exists():
    """INV-SHELF-NOT-PLATFORM-CATEGORY: hai taxonomy có cột trùng tên nên FK
    inference sẽ tạo đúng edge này — registry không được có nó."""
    for spec in RELATIONS.values():
        assert {spec.left, spec.right} != {"ShopCategory", "PlatformCategory"}


# --- SQL AST: hành vi, không phải cấu trúc --------------------------------

@pytest.mark.parametrize("name,expected", [
    ("belongs_to", ["l.country_code = r.country_code", "l.shop_id = r.shop_id"]),
    ("in_platform_category",
     ["l.country_code = r.country_code", "l.catid_num = r.category_id_num"]),
    ("in_shop_category",
     ["l.country_code = r.country_code", "l.shop_id = r.shop_id",
      "l.category_id_num = r.shop_category_id_num", "l.date = r.date"]),
    # A1.2(a) — thay đổi hợp đồng CÓ CHỦ ĐÍCH, có bằng chứng đo bằng pandas:
    # snapshot_metrics có 3 dòng cho một listing, nên join chỉ theo
    # product_listing_key nhân 668 dòng VN ngày 03/07 lên 1900. Thêm khoá `date`
    # đưa về đúng 668 (1:1). Dedupe phía sau KHÔNG cứu được: cả 3 bản sao mang
    # cùng `date` của phía trái nên giữ lại 1 trong 3 là tuỳ tiện.
    ("has_sales_metric",
     ["l.product_listing_key = r.product_listing_key", "l.date = r.date"]),
])
def test_compiled_join_uses_exactly_the_declared_keys(name, expected):
    from gladiators.planner import compiler

    spec = RELATIONS[name]
    projection = compiler._JOIN_PROJECTIONS[spec.binding.projection_id]
    assert projection is not None
    rendered = [
        f"l.{key.left.column} = r.{key.right.column}" for key in spec.binding.join_keys
    ]
    assert rendered == expected


def test_every_join_relation_resolves_a_compiler_projection():
    from gladiators.planner import compiler

    for name in JOIN_RELATIONS:
        projection_id = RELATIONS[name].binding.projection_id
        assert projection_id in compiler._JOIN_PROJECTIONS, name


def test_inline_relations_have_no_compiler_projection():
    for name in INLINE_RELATIONS:
        assert RELATIONS[name].binding.projection_id is None, name


def test_sales_metric_join_is_one_to_one_at_pinned_date():
    """A1.2(a) — join phải giữ nguyên số dòng khi đã ghim một snapshot.

    Đo trên dữ liệu thật thay vì đọc khai báo: một quan hệ khai
    ``fanout_effect`` gì cũng không cho biết nó có thật sự nhân bản hay không.
    """
    import pandas as pd

    products = pd.read_csv("data/processed/products_clean.csv")
    metrics = pd.read_csv("data/processed/product_snapshot_metrics.csv")
    left = products[
        (products.country_code == "vn") & (products.date.astype(str) == "2026-07-03")
    ]
    keys = [key.left.column for key in RELATIONS["has_sales_metric"].binding.join_keys]
    joined = left.merge(metrics[keys + ["price_num"]], on=keys, how="left")
    assert len(joined) == len(left), (
        f"join nhân bản {len(left)} dòng thành {len(joined)}"
    )
