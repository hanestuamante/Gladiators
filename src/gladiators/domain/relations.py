from dataclasses import dataclass


@dataclass(frozen=True)
class RelationSpec:
    name: str
    source: str
    allowed_countries: tuple[str, ...]


RELATIONS = {
    "listing_has_snapshot": RelationSpec("listing_has_snapshot", "product_snapshot_metrics.csv", ("vn", "id")),
    "listing_in_platform_category": RelationSpec("listing_in_platform_category", "product_categories_clean.csv", ("vn", "id")),
    "listing_on_shop_shelf": RelationSpec("listing_on_shop_shelf", "category_list_clean.csv", ("vn", "id")),
}

