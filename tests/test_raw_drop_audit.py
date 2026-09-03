"""Đối chiếu đợt raw mới với hợp đồng pipeline — 28/08.

Điều bộ test này khoá lại: bảng đối chiếu **quan sát, không quyết**. Nó phân biệt
được ba tình huống mà nhìn ở mức file thì giống hệt nhau — cột *chuyển sang bảng
khác*, cột *đổi tên*, và cột *vắng hẳn* — và nó gắn cờ đúng lớp ứng viên nguy
hiểm nhất: tên đổi thành mã.

Dùng dữ liệu tổng hợp: ``data/raw_snapshots/`` bị gitignore, nên một test phụ
thuộc nó sẽ đỏ trên mọi máy khác.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_raw_drop import _is_name_vs_id, audit  # noqa: E402


def _write(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(columns) + "\n" + ",".join("x" for _ in columns) + "\n",
                    encoding="utf-8")


@pytest.fixture
def reference(tmp_path):
    """Đợt raw cũ, bố cục Hive như hệ đang dùng."""
    root = tmp_path / "raw"
    _write(root / "country_code=vn/dataset=products/shop_id=1/products.csv",
           ["country_code", "shop_id", "item_id", "brand", "monthly_sold_value", "catid"])
    _write(root / "country_code=vn/dataset=shop_info/shop_info.csv",
           ["country_code", "shop_id", "shop_name"])
    _write(root / "country_code=vn/dataset=category_list/shop_id=1/category_list.csv",
           ["country_code", "shop_id", "shop_category_id"])
    _write(root / "country_code=vn/dataset=product_categories/shop_id=1/product_categories.csv",
           ["country_code", "shop_id", "item_id"])
    _write(root / "country_code=vn/dataset=category_platform/category_platform.csv",
           ["country_code", "category_id"])
    return root


@pytest.fixture
def drop(tmp_path):
    """Đợt mới: phẳng, đổi tên vài cột, chuyển một cột sang bảng khác, thiếu một
    dataset, và có một file rỗng."""
    root = tmp_path / "drop"
    _write(root / "products_2026.csv",
           ["country_code", "shop_id", "item_id", "brand_id", "monthly_sold"])
    _write(root / "shop_info_2026.csv", ["country_code", "shop_id", "shop_name"])
    _write(root / "categories_2026.csv", ["country_code", "shop_id", "category_id"])
    _write(root / "product_categories_2026.csv", ["country_code", "shop_id", "item_id"])
    _write(root / "shop_stats_2026.csv", ["country_code", "shop_id", "date", "rating_star"])
    (root / "test_2026.csv").write_text("\n", encoding="utf-8")
    return root


def test_a_column_that_moved_to_another_table_is_not_reported_as_missing(reference, drop):
    """``shop_name`` vẫn còn, chỉ nằm ở bảng khác. Báo nó mất là gửi người đọc đi
    sai hướng."""
    report = audit(reference, drop)
    products = report["datasets"]["products"]
    assert "shop_name" not in products["absent_everywhere"]


def test_a_renamed_column_is_offered_as_a_candidate_not_applied(reference, drop):
    report = audit(reference, drop)
    candidates = {
        item["column"]: item
        for item in report["datasets"]["products"]["rename_candidates"]
    }
    assert candidates["monthly_sold_value"]["candidate"] == "monthly_sold"
    assert "monthly_sold_value" not in report["datasets"]["products"]["absent_everywhere"]


def test_a_name_to_id_candidate_is_flagged(reference, drop):
    """Lớp nhầm đắt nhất vì nó IM LẶNG: câu trả lời in ra một con số ở chỗ lẽ ra
    là một cái tên."""
    report = audit(reference, drop)
    candidates = {
        item["column"]: item
        for item in report["datasets"]["products"]["rename_candidates"]
    }
    assert candidates["brand"]["candidate"] == "brand_id"
    assert candidates["brand"]["name_vs_id"] is True
    assert candidates["monthly_sold_value"]["name_vs_id"] is False


def test_a_whole_missing_dataset_is_reported(reference, drop):
    report = audit(reference, drop)
    assert report["datasets"]["category_platform"]["satisfiable"] is False
    assert report["verdict"].startswith("KHÔNG dựng được")


def test_tables_the_pipeline_does_not_know_are_listed(reference, drop):
    """``shop_stats`` không phải rác — nó là năng lực MỚI. Bỏ nó khỏi báo cáo là
    giấu đi thứ đáng dùng nhất của đợt dữ liệu."""
    assert "shop_stats" in audit(reference, drop)["new_tables_pipeline_does_not_know"]


def test_an_empty_file_is_recorded_not_swallowed(reference, drop):
    """Nuốt im lặng thì không ai biết nó rỗng; để nó ném thì cả bảng không chạy."""
    assert audit(reference, drop)["empty_files"] == ["test_2026.csv"]


@pytest.mark.parametrize(
    ("expected", "candidate", "flagged"),
    [
        ("brand", "brand_id", True),
        ("original_category_name", "global_category_id", True),
        ("monthly_sold_value", "monthly_sold", False),
        ("shop_category_id", "shopee_category_id", False),
    ],
)
def test_the_name_versus_id_rule_is_mechanical(expected, candidate, flagged):
    """Luật này chỉ bắt lệch tên↔mã. ``shop_category_id`` → ``shopee_category_id``
    KHÔNG bị nó bắt — cả hai đều là mã — dù đó mới là ứng viên nguy hiểm nhất
    (kệ shop ≠ danh mục sàn, đúng thứ INV-SHELF-NOT-PLATFORM-CATEGORY cấm).
    Ghi rõ giới hạn này ở đây để không ai đọc "không bị gắn cờ" thành "an toàn".
    """
    assert _is_name_vs_id(expected, candidate) is flagged
