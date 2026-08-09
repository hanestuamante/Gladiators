"""Topic registry — ultimate solution §6.2 / §6.3.

A topic is a closed slice of the relation graph: the refs it owns, the relations
it may traverse, and the invariants that apply.  It exists so the planner can be
given the part of the semantic layer a question needs instead of all of it, and
so that "which part" is data rather than a fuzzy lexical guess.

Two ownership rules carry most of the weight, both established by measuring the
eval corpus rather than by taste:

**Domains own measures; CORE owns universal grouping keys.**  Without this,
"shop nào có nhiều listing nhất" counts as a two-topic question -- counting and
shop profile -- when it is one universal measure grouped by one universal key.
Measured on the tagged eval cases, getting this wrong doubled the share of
questions that appeared to span two topics.

**Aspects own rules, not refs.**  The exception is ``context.*``, owned by the
external-context aspect, because those refs must never compile into SQL.

Cards carry no trigger lexicon: §3.2 makes ``CatalogObject.aliases`` the single
source of natural-language binding, and a second per-topic word list is exactly
how two vocabularies drift apart.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .catalog import CATALOG
from .invariants import INVARIANTS
from .relations import RELATIONS, find_path

TopicKind = Literal["core", "domain", "aspect"]

MIN_DOMAIN_REFS = 4
MAX_DOMAIN_REFS = 20
MAX_DOMAIN_RELATIONS = 4


class TopicRelationPath(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path_id: str
    anchor_entity: str
    relation_ids: tuple[str, ...]
    input_grain: str
    output_grain: str
    dedupe_policy_id: str | None = None


class TopicCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    name: str
    kind: TopicKind
    owner_refs: tuple[str, ...] = ()
    also_refs: tuple[str, ...] = ()
    inherits: tuple[str, ...] = ()
    anchor_entities: tuple[str, ...] = ()
    relation_paths: tuple[TopicRelationPath, ...] = ()
    invariant_ids: tuple[str, ...] = ()
    # Refs that must never reach a SQL plan even when the topic is selected.
    non_sql_refs: tuple[str, ...] = ()

    @property
    def relation_ids(self) -> tuple[str, ...]:
        """Effective relations, derived from the paths rather than restated."""
        return tuple(dict.fromkeys(
            relation for path in self.relation_paths for relation in path.relation_ids
        ))

    def all_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.owner_refs + self.also_refs))


def _path(path_id: str, relation: str, anchor: str = "ProductListing") -> TopicRelationPath:
    spec = RELATIONS[relation]
    return TopicRelationPath(
        path_id=path_id, anchor_entity=anchor, relation_ids=(relation,),
        input_grain=spec.input_grain, output_grain=spec.output_grain,
        dedupe_policy_id=spec.dedupe_strategy,
    )


_CARDS: tuple[TopicCard, ...] = (
    TopicCard(
        id="CORE", name="CORE", kind="core",
        anchor_entities=("ProductListing",),
        # Universal grouping keys and the one universal measure. A domain that
        # claimed these would make every grouped question look cross-topic.
        owner_refs=(
            "dim.country", "dim.date", "dim.brand", "dim.product_name", "dim.shop_name",
            # Counting the distinct instances of a unit is universal, not a
            # domain concern: if T5 owned shop_count then "bao nhiêu shop bán
            # thương hiệu X" would read as a cross-topic question.
            "derived.product_count", "derived.shop_count", "derived.brand_count",
            "derived.category_count",
            "entity.product_listing", "entity.shop", "entity.brand", "entity.country",
            "entity.date_snapshot", "entity.sales_metric", "entity.content",
            "entity.promotion_id_observation", "entity.voucher_observation",
            "entity.platform_category", "entity.shop_category",
        ),
        relation_paths=(_path("listing_by_date", "observed_at"),),
        invariant_ids=("INV-SNAPSHOT-SCOPE", "INV-CURRENCY-NO-MIX", "INV-EMPTY-RESULT-IS-VALID"),
    ),
    TopicCard(
        id="T1", name="PRICING_DISCOUNT", kind="domain",
        anchor_entities=("ProductListing",),
        owner_refs=(
            "measure.price", "measure.price_original", "measure.discount_percent",
            "derived.discount_bucket", "derived.price_change", "derived.price_change_pct",
            "derived.discount_point_change", "derived.median_discount_ratio",
        ),
        relation_paths=(_path("listing_by_date", "observed_at"), _path("listing_to_shop", "belongs_to")),
        invariant_ids=("INV-PRICE-SENTINEL-EXCLUDED", "INV-CURRENCY-NO-MIX"),
    ),
    TopicCard(
        id="T2", name="SALES_PROXY", kind="domain",
        anchor_entities=("ProductListing", "SalesMetric"),
        owner_refs=(
            "measure.monthly_sold", "measure.history_sold",
            "derived.estimated_recent_revenue", "derived.monthly_sold_delta",
            "derived.history_sold_delta_raw", "derived.history_sold_delta_clean",
            "derived.history_sold_decrease_flag", "derived.median_monthly_sold",
            "derived.median_estimated_recent_revenue", "derived.descriptive_gap_median_sold",
            "derived.descriptive_gap_vs_baseline",
        ),
        relation_paths=(_path("listing_metrics", "has_sales_metric"), _path("listing_by_date", "observed_at")),
        invariant_ids=("INV-PROXY-NOT-VERIFIED-SALES", "INV-DATE-RANGE-HONOURED"),
    ),
    TopicCard(
        id="T3", name="PROMOTION_VOUCHER", kind="domain",
        anchor_entities=("ProductListing", "VoucherObservation"),
        owner_refs=(
            "measure.voucher_discount", "measure.voucher_min_spend",
            "measure.voucher_start_time", "measure.voucher_end_time",
            "measure.vouchers_count", "derived.has_structured_voucher",
            "derived.has_voucher_label", "derived.has_promo", "derived.voucher_rate",
            "derived.voucher_state_transition", "derived.voucher_profile_score",
        ),
        relation_paths=(
            _path("listing_voucher", "observed_structured_voucher"),
            _path("listing_promotion", "observed_promotion_id"),
        ),
        invariant_ids=("INV-NO-CAUSAL-CLAIM",),
    ),
    TopicCard(
        id="T4", name="REVIEW_ENGAGEMENT", kind="domain",
        anchor_entities=("ProductListing",),
        owner_refs=(
            "measure.rating", "measure.rating_count", "measure.liked_count",
            "derived.rating_change", "derived.rating_count_delta", "derived.liked_delta",
        ),
        relation_paths=(_path("listing_by_date", "observed_at"),),
        invariant_ids=("INV-SNAPSHOT-SCOPE",),
    ),
    TopicCard(
        id="T5", name="SHOP_PROFILE", kind="domain",
        anchor_entities=("Shop",),
        owner_refs=(
            "measure.shop_rating", "measure.shop_followers", "measure.shop_items",
            "measure.shop_response_rate", "measure.shop_response_time",
            "measure.shop_rating_good", "measure.shop_rating_normal",
            "measure.shop_rating_bad", "measure.shop_cancellation_rate",
            "dim.shop_official", "dim.shop_vacation",
        ),
        # belongs_to is a bridge for listing-level questions about shop
        # attributes; it never on its own licenses a shop-grain output.
        relation_paths=(_path("listing_to_shop", "belongs_to", "Shop"),),
        invariant_ids=("INV-DEDUPE-BEFORE-AGGREGATE",),
    ),
    TopicCard(
        id="T6", name="CATALOG_STRUCTURE", kind="domain",
        anchor_entities=("ProductListing", "PlatformCategory", "ShopCategory"),
        owner_refs=(
            "dim.platform_category_name", "dim.shop_category_name",
            "dim.shop_category_parent", "dim.shop_category_child",
            "dim.platform_category_has_children", "measure.shop_category_total",
        ),
        relation_paths=(
            _path("listing_platform_category", "in_platform_category"),
            _path("listing_shop_shelf", "in_shop_category"),
        ),
        invariant_ids=("INV-SHELF-NOT-PLATFORM-CATEGORY", "INV-DEDUPE-BEFORE-AGGREGATE"),
    ),
    TopicCard(
        id="T7", name="CONTENT_VARIATION", kind="domain",
        anchor_entities=("ProductListing", "Content"),
        owner_refs=(
            "measure.images_count", "measure.variation_options_count",
            "dim.display_variation", "dim.shopee_verified",
        ),
        relation_paths=(
            _path("listing_content", "has_content"),
            _path("listing_variation", "has_display_variation"),
        ),
        invariant_ids=("INV-SNAPSHOT-SCOPE",),
    ),
    TopicCard(
        id="T8", name="SIMILARITY_COMPETITIVE", kind="domain",
        anchor_entities=("ProductListing",),
        owner_refs=(
            "derived.text_sim", "derived.category_overlap_depth", "derived.brand_match",
            "derived.price_distance", "derived.same_shelf_bonus", "derived.similarity_score",
        ),
        inherits=("T1", "T6"),
        relation_paths=(
            _path("listing_platform_category", "in_platform_category"),
            _path("listing_brand", "has_brand"),
        ),
        # §6.3: similarity refs are tool-computed and must not enter a SQL plan.
        non_sql_refs=(
            "derived.text_sim", "derived.category_overlap_depth", "derived.brand_match",
            "derived.price_distance", "derived.same_shelf_bonus", "derived.similarity_score",
        ),
        invariant_ids=("INV-SHELF-NOT-PLATFORM-CATEGORY",),
    ),
    TopicCard(id="A1", name="TEMPORAL_CHANGE", kind="aspect",
              invariant_ids=("INV-DATE-RANGE-HONOURED", "INV-SNAPSHOT-SCOPE")),
    TopicCard(id="A2", name="RANKING", kind="aspect",
              invariant_ids=("INV-PRICE-SENTINEL-EXCLUDED",)),
    TopicCard(id="A3", name="GROUP_COMPARE", kind="aspect",
              invariant_ids=("INV-CURRENCY-NO-MIX", "INV-NO-CAUSAL-CLAIM")),
    TopicCard(id="A4", name="DISTRIBUTION_AGG", kind="aspect",
              invariant_ids=("INV-DEDUPE-BEFORE-AGGREGATE",)),
    TopicCard(
        id="A5", name="EXTERNAL_CONTEXT", kind="aspect",
        # The one aspect that owns refs: context.* must never compile to SQL.
        owner_refs=("context.campaign_window", "context.theme_day", "context.market_event"),
        non_sql_refs=("context.campaign_window", "context.theme_day", "context.market_event"),
    ),
)


class TopicRegistryError(ValueError):
    pass


def _build(cards: tuple[TopicCard, ...]) -> dict[str, TopicCard]:
    registry: dict[str, TopicCard] = {}
    owners: dict[str, str] = {}
    signatures: dict[tuple, str] = {}

    for card in cards:
        if card.id in registry:
            raise TopicRegistryError(f"C1: topic trùng ID: {card.id}")
        for ref in card.all_refs():                                    # C1
            if ref not in CATALOG:
                raise TopicRegistryError(f"C1 {card.id}: ref không tồn tại: {ref}")
        for invariant_id in card.invariant_ids:                        # C1
            if invariant_id not in INVARIANTS:
                raise TopicRegistryError(f"C1 {card.id}: invariant không tồn tại: {invariant_id}")
        for relation in card.relation_ids:                             # C1
            if relation not in RELATIONS:
                raise TopicRegistryError(f"C1 {card.id}: relation không tồn tại: {relation}")
        for ref in card.owner_refs:                                    # C2
            if ref in owners:
                raise TopicRegistryError(
                    f"C2 ref {ref} có hai owner: {owners[ref]} và {card.id}"
                )
            owners[ref] = card.id
        for path in card.relation_paths:                               # C5
            spec = RELATIONS[path.relation_ids[0]]
            if spec.fanout_effect != "none" and not path.dedupe_policy_id:
                raise TopicRegistryError(
                    f"C5 {card.id}/{path.path_id}: fanout path thiếu dedupe policy"
                )
        if card.kind == "domain":                                      # C3
            size = len(card.all_refs())
            if not MIN_DOMAIN_REFS <= size <= MAX_DOMAIN_REFS:
                raise TopicRegistryError(f"C3 {card.id}: {size} refs ngoài khoảng cho phép")
            if len(card.relation_ids) > MAX_DOMAIN_RELATIONS:
                raise TopicRegistryError(f"C3 {card.id}: quá nhiều relation")
        signature = (                                                  # C6
            card.kind, tuple(sorted(card.all_refs())),
            tuple(sorted(card.relation_ids)), tuple(sorted(card.invariant_ids)),
        )
        if card.kind != "aspect" and signature in signatures:
            raise TopicRegistryError(
                f"C6 {card.id} trùng signature với {signatures[signature]}"
            )
        signatures[signature] = card.id
        registry[card.id] = card

    for card in cards:                                                 # C7
        seen: set[str] = set()
        stack = list(card.inherits)
        while stack:
            parent = stack.pop()
            if parent == card.id:
                raise TopicRegistryError(f"C7 {card.id}: inheritance cycle")
            if parent in seen:
                continue
            if parent not in registry:
                raise TopicRegistryError(f"C7 {card.id}: kế thừa topic không tồn tại {parent}")
            seen.add(parent)
            stack.extend(registry[parent].inherits)

    unowned = sorted(set(CATALOG) - set(owners))                       # C4
    if unowned:
        raise TopicRegistryError(f"C4 catalog ref không thuộc topic nào: {unowned}")

    # C8: every SQL-bound ref must be reachable from an anchor. Refs marked
    # non_sql are tool-computed or context-only and have no join path by design.
    for card in cards:
        if card.kind != "domain" or not card.relation_paths:
            continue
        for path in card.relation_paths:
            if find_path("ProductListing", RELATIONS[path.relation_ids[0]].right) is None:
                raise TopicRegistryError(
                    f"C8 {card.id}/{path.path_id}: không có join path hợp lệ"
                )
    return registry


TOPICS: dict[str, TopicCard] = _build(_CARDS)

OWNER_BY_REF: dict[str, str] = {
    ref: card.id for card in TOPICS.values() for ref in card.owner_refs
}

REGISTRY_HASH: str = hashlib.sha256(
    "|".join(
        f"{card.id}:{','.join(sorted(card.all_refs()))}:{','.join(sorted(card.relation_ids))}"
        for card in sorted(TOPICS.values(), key=lambda item: item.id)
    ).encode("utf-8")
).hexdigest()[:16]


def get(topic_id: str) -> TopicCard | None:
    return TOPICS.get(topic_id)


def domains() -> tuple[TopicCard, ...]:
    return tuple(card for card in TOPICS.values() if card.kind == "domain")


def aspects() -> tuple[TopicCard, ...]:
    return tuple(card for card in TOPICS.values() if card.kind == "aspect")


def effective_refs(topic_id: str) -> tuple[str, ...]:
    """Refs a topic can use, following inheritance (§6.4 effective card)."""
    card = TOPICS[topic_id]
    refs = list(card.all_refs())
    for parent in card.inherits:
        refs.extend(effective_refs(parent))
    return tuple(dict.fromkeys(refs))


def non_sql_refs() -> frozenset[str]:
    """Refs that must never reach a SQL plan, whatever topic selected them."""
    return frozenset(ref for card in TOPICS.values() for ref in card.non_sql_refs)
