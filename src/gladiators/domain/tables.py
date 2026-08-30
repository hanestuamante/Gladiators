"""Table registry — Metadata Model & Binding Layer §E1.

Bảy artifact frozen được khai báo ở đúng một nơi. Trước đây mỗi consumer tự trả
lời "artifact nào tồn tại": ``PlanNode.source`` có một Literal, ``compiler``
có ``_VIEW_NAMES``, ``data/coverage`` có ``ARTIFACTS``, catalog dùng chuỗi
``"<table>.<column>"``. Bốn danh sách trùng nhau hôm nay là ngẫu nhiên, không
phải bất biến — relation registry đã drift đúng theo kiểu đó (§E2).

Module này cố ý **không đọc file**. ``TABLE_DECLARATIONS`` là hằng thuần; phần
column đến từ ``semantic_coverage_manifest.json`` và chỉ được materialize khi
``build_table_registry`` được gọi (xem ``domain/bindings.py``). Nhờ vậy
``catalog.py`` import được ``ArtifactName``/``PhysicalColumnRef`` mà không kéo
theo I/O hay tạo import cycle với ``data/coverage.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Literal, Mapping, Protocol


class ArtifactName(StrEnum):
    PRODUCTS = "products_clean.csv"
    SHOP_INFO = "shop_info_clean.csv"
    CATEGORY_LIST = "category_list_clean.csv"
    PRODUCT_CATEGORIES = "product_categories_clean.csv"
    CATEGORY_PLATFORM = "category_platform_clean.csv"
    SNAPSHOT_METRICS = "product_snapshot_metrics.csv"
    TRANSITION_METRICS = "product_transition_metrics.csv"
    SHOP_STATS = "shop_stats_clean.csv"


# Artifact có thể VẮNG MẶT ở một bản dữ liệu mà bản đó vẫn hợp lệ.
#
# ``shop_stats`` (panel ngày cấp shop) chỉ tồn tại từ lần thu 01–21/07/2026 trở
# đi; bản đóng băng 01–03/07 không có nó. Ba lựa chọn, và vì sao chọn cái này:
# bắt buộc nó ⇒ một bản dữ liệu cũ ĐÚNG bị chấm là hỏng; nhét panel vào
# ``shop_info`` ⇒ grain của chín measure ``static_latest`` đổi âm thầm; khai
# tuỳ chọn ⇒ "chưa thu" là một trạng thái ĐỌC ĐƯỢC, và mọi năng lực dựa vào nó
# từ chối có lý do thay vì nổ.
OPTIONAL_ARTIFACTS: frozenset[ArtifactName] = frozenset({ArtifactName.SHOP_STATS})


class TableRegistryError(ValueError):
    """Raised at build time when a declaration contradicts the manifest."""


@dataclass(frozen=True)
class PhysicalColumnRef:
    """Một cột vật lý đã được định danh bằng enum, không phải chuỗi tự do.

    Sống ở đây (không phải catalog) vì cả catalog lẫn relation registry đều cần
    nó; đặt ở catalog sẽ buộc ``relations.py`` import catalog chỉ để lấy một
    dataclass.
    """

    table: ArtifactName
    column: str

    def __str__(self) -> str:  # giữ dạng "<table>.<column>" cho log/hash
        return f"{self.table.value}.{self.column}"


@dataclass(frozen=True)
class TableColumnSpec:
    name: str
    physical_type: str | None
    coverage_status: str
    catalog_ref: str | None
    partition: bool = False


@dataclass(frozen=True)
class QualityCheckRef:
    check_id: str
    handler_id: str
    severity: Literal["hard", "warning"] = "hard"


@dataclass(frozen=True)
class TableDeclaration:
    """Phần con người khai: tên, view, grain, quality check.

    Column KHÔNG nằm ở đây — manifest đã phủ toàn bộ 219 header và một danh sách
    thứ hai chỉ tạo cơ hội drift.
    """

    name: ArtifactName
    view_name: str
    grain: tuple[str, ...]
    quality_checks: tuple[QualityCheckRef, ...] = ()
    partition_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableSpec:
    name: ArtifactName
    view_name: str
    storage: Literal["csv"]
    grain: tuple[str, ...]
    columns: tuple[TableColumnSpec, ...]
    quality_checks: tuple[QualityCheckRef, ...]
    version_policy: Literal["dataset_hash"] = "dataset_hash"

    def column(self, name: str) -> TableColumnSpec | None:
        for spec in self.columns:
            if spec.name == name:
                return spec
        return None

    def has_column(self, name: str) -> bool:
        return self.column(name) is not None


class QualityCheckHandler(Protocol):
    """Callable thật đứng sau một ``QualityCheckRef``.

    Bài học từ ``validator_id`` (§E3): một ID không resolve tới code chỉ là prose
    mặc schema, và nguy hơn thiếu registry vì người đọc tin rule đã được enforce.
    """

    handler_id: str

    def __call__(self, data_dir: str) -> Mapping[str, object]: ...


# ``view_name`` là tên DuckDB view mà executor register; giữ đúng quy ước
# removesuffix("_clean.csv")/removesuffix(".csv") đang chạy để không đổi SQL.
TABLE_DECLARATIONS: tuple[TableDeclaration, ...] = (
    TableDeclaration(
        ArtifactName.PRODUCTS, "products",
        ("country_code", "shop_id", "item_id", "date"),
        (QualityCheckRef("products.pandera_contract", "contracts.validate_artifacts"),
         QualityCheckRef("products.coverage_manifest", "coverage.validate_manifest")),
        partition_columns=("country_code", "date"),
    ),
    TableDeclaration(
        ArtifactName.SHOP_INFO, "shop_info",
        ("country_code", "shop_id"),
        (QualityCheckRef("shop_info.coverage_manifest", "coverage.validate_manifest"),),
        partition_columns=("country_code",),
    ),
    TableDeclaration(
        ArtifactName.CATEGORY_LIST, "category_list",
        ("country_code", "shop_id", "shop_category_id", "date"),
        (QualityCheckRef("category_list.coverage_manifest", "coverage.validate_manifest"),),
        partition_columns=("country_code", "date"),
    ),
    TableDeclaration(
        ArtifactName.PRODUCT_CATEGORIES, "product_categories",
        ("country_code", "shop_id", "item_id", "category_id", "date"),
        (QualityCheckRef("product_categories.coverage_manifest", "coverage.validate_manifest"),),
        partition_columns=("country_code", "date"),
    ),
    TableDeclaration(
        ArtifactName.CATEGORY_PLATFORM, "category_platform",
        ("country_code", "category_id"),
        (QualityCheckRef("category_platform.coverage_manifest", "coverage.validate_manifest"),),
        partition_columns=("country_code",),
    ),
    TableDeclaration(
        ArtifactName.SNAPSHOT_METRICS, "product_snapshot_metrics",
        ("country_code", "shop_id", "item_id", "date"),
        (QualityCheckRef("snapshot_metrics.pandera_contract", "contracts.validate_artifacts"),
         QualityCheckRef("snapshot_metrics.coverage_manifest", "coverage.validate_manifest")),
        partition_columns=("country_code", "date"),
    ),
    TableDeclaration(
        ArtifactName.TRANSITION_METRICS, "product_transition_metrics",
        ("country_code", "shop_id", "item_id", "previous_date", "date"),
        (QualityCheckRef("transition_metrics.pandera_contract", "contracts.validate_artifacts"),
         QualityCheckRef("transition_metrics.coverage_manifest", "coverage.validate_manifest")),
        partition_columns=("country_code", "date"),
    ),
    TableDeclaration(
        ArtifactName.SHOP_STATS, "shop_stats",
        ("country_code", "shop_id", "date"),
        (QualityCheckRef("shop_stats.coverage_manifest", "coverage.validate_manifest"),),
        partition_columns=("country_code", "date"),
    ),
)

DECLARATIONS_BY_NAME: dict[ArtifactName, TableDeclaration] = {
    declaration.name: declaration for declaration in TABLE_DECLARATIONS
}

# Compatibility maps — SINH từ declarations, không khai lần hai (§E1.3).
VIEW_NAMES: dict[str, str] = {
    declaration.name.value: declaration.view_name for declaration in TABLE_DECLARATIONS
}
ARTIFACT_NAMES: tuple[str, ...] = tuple(name.value for name in ArtifactName)

# Artifact mà MỌI bản dữ liệu phải có. Consumer nào coi việc thiếu file là lỗi
# thì đọc danh sách này, không đọc ``ARTIFACT_NAMES``.
REQUIRED_ARTIFACT_NAMES: tuple[str, ...] = tuple(
    name.value for name in ArtifactName if name not in OPTIONAL_ARTIFACTS
)
OPTIONAL_ARTIFACT_NAMES: tuple[str, ...] = tuple(
    name.value for name in ArtifactName if name in OPTIONAL_ARTIFACTS
)


def artifact(value: str | ArtifactName) -> ArtifactName:
    """Parse tên artifact; fail-closed thay vì trả None cho chuỗi lạ."""
    if isinstance(value, ArtifactName):
        return value
    try:
        return ArtifactName(value)
    except ValueError as exc:
        raise TableRegistryError(f"Artifact không nằm trong registry: {value!r}") from exc


def parse_physical(value: str) -> PhysicalColumnRef:
    """``"products_clean.csv.price_num"`` → ``PhysicalColumnRef``.

    Dùng ``rpartition`` vì tên artifact chứa dấu chấm (``.csv``); tách từ trái
    sẽ cắt nhầm ngay ở phần mở rộng file.
    """
    table, _, column = value.rpartition(".")
    if not table or not column:
        raise TableRegistryError(f"Physical mapping sai định dạng: {value!r}")
    return PhysicalColumnRef(artifact(table), column)


def build_table_registry(
    manifest: Mapping[str, object],
    declarations: tuple[TableDeclaration, ...] = TABLE_DECLARATIONS,
    quality_handlers: Mapping[str, Callable[..., object]] | None = None,
) -> dict[ArtifactName, TableSpec]:
    """Materialize manifest + declarations thành registry đã kiểm.

    Fail-closed ở mọi lệch: thiếu declaration, thiếu manifest entry, view trùng,
    column trùng, hoặc quality handler không resolve.
    """
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise TableRegistryError("Coverage manifest thiếu danh sách 'entries'")

    handlers = dict(quality_handlers or {})
    declared = {declaration.name: declaration for declaration in declarations}
    if len(declared) != len(declarations):
        raise TableRegistryError("TableDeclaration trùng artifact")

    missing_declaration = sorted(set(ArtifactName) - set(declared))
    if missing_declaration:
        raise TableRegistryError(
            f"Artifact thiếu TableDeclaration: {[n.value for n in missing_declaration]}"
        )

    views: dict[str, ArtifactName] = {}
    for declaration in declarations:
        if declaration.view_name in views:
            raise TableRegistryError(
                f"View trùng: {declaration.view_name} dùng bởi "
                f"{views[declaration.view_name].value} và {declaration.name.value}"
            )
        views[declaration.view_name] = declaration.name

    columns: dict[ArtifactName, list[TableColumnSpec]] = {name: [] for name in declared}
    # Artifact tuỳ chọn vắng mặt ⇒ manifest không có entry nào cho nó. Đó là
    # "chưa thu", không phải "khai thiếu"; phân biệt hai thứ đó là toàn bộ lý do
    # OPTIONAL_ARTIFACTS tồn tại.
    seen: set[tuple[ArtifactName, str]] = set()
    for entry in entries:
        table = artifact(str(entry.get("table")))
        column = str(entry.get("column"))
        key = (table, column)
        if key in seen:
            raise TableRegistryError(f"Manifest entry trùng: {table.value}.{column}")
        seen.add(key)
        declaration = declared[table]
        columns[table].append(TableColumnSpec(
            name=column,
            # Additive trong compatibility window: manifest hiện chưa khai dtype.
            physical_type=entry.get("physical_type"),
            coverage_status=str(entry.get("status")),
            catalog_ref=entry.get("catalog_ref"),
            partition=bool(entry.get("partition", column in declaration.partition_columns)),
        ))

    registry: dict[ArtifactName, TableSpec] = {}
    for name, declaration in declared.items():
        if not columns[name]:
            if name not in OPTIONAL_ARTIFACTS:
                raise TableRegistryError(f"Artifact không có manifest entry nào: {name.value}")
            # Artifact tuỳ chọn CHƯA THU: vào registry với 0 cột. Bỏ hẳn nó khỏi
            # registry sẽ khiến consumer phải tự hỏi "artifact này có tồn tại
            # không" bằng KeyError — tức lại một danh sách artifact thứ hai,
            # đúng thứ §E1 dựng registry để xoá. Có mặt-mà-rỗng nói được cả hai:
            # nó được khai, và nó chưa có dữ liệu.
            registry[name] = TableSpec(
                name=name, view_name=declaration.view_name, storage="csv",
                grain=declaration.grain, columns=(),
                quality_checks=declaration.quality_checks,
            )
            continue
        for check in declaration.quality_checks:
            if check.severity == "hard" and check.handler_id not in handlers:
                raise TableRegistryError(
                    f"{name.value}: quality check {check.check_id} trỏ tới handler "
                    f"không tồn tại: {check.handler_id}"
                )
        column_specs = tuple(sorted(columns[name], key=lambda spec: spec.name))
        missing_grain = [key for key in declaration.grain
                         if key not in {spec.name for spec in column_specs}]
        if missing_grain:
            raise TableRegistryError(
                f"{name.value}: grain tham chiếu cột không tồn tại: {missing_grain}"
            )
        registry[name] = TableSpec(
            name=name, view_name=declaration.view_name, storage="csv",
            grain=declaration.grain, columns=column_specs,
            quality_checks=declaration.quality_checks,
        )
    return registry
