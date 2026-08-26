from __future__ import annotations

from collections.abc import Callable
import math

from gladiators.contracts import Evidence
from gladiators.external.contracts import SourceLocator
from gladiators.planner.semantic_parser import normalize as normalize_text
from .similarity import (
    STATUS_PHRASE_REGISTRY_HASH,
    STATUS_PHRASE_REGISTRY_VERSION,
    category_overlap,
    parse_category_path,
    strip_status_phrases,
)

OPEN_RESULT_ROW_LIMIT = 10


class AnalyticsTools:
    """Deterministic analytics. LLMs never calculate values in this class."""

    def __init__(self, repository, resolver, evidence_id: Callable[[], str]):
        self.repo, self.resolver, self.evidence_id = repository, resolver, evidence_id

    def sales_decline(self, listing_key: str) -> list[Evidence]:
        rows = self.repo.transitions.query("product_listing_key == @listing_key and transition_metric_eligible == True").sort_values("date")
        if rows.empty:
            return []
        row = rows.iloc[-1]
        common = dict(source_tier="btc_dataset", source_locator=SourceLocator(kind="internal", value="product_transition_metrics"), dataset_version=self.repo.dataset_version, attrs={"listing_key": listing_key, "previous_date": str(row.previous_date), "date": str(row.date)})
        return [
            Evidence(evidence_id=self.evidence_id(), metric="monthly_sold_delta", value=float(row.monthly_sold_delta), unit="items", source_path="monthly_sold_delta", **common),
            Evidence(evidence_id=self.evidence_id(), metric="days_since_previous", value=int(row.days_since_previous), unit="days", source_path="days_since_previous", **common),
        ]

    def similar_products(self, listing_key: str, top_k: int = 5) -> list[Evidence]:
        """§4.6: compare inside one platform category, on de-decorated titles."""
        products = self.repo.products.drop_duplicates("product_listing_key")
        source = products.loc[products.product_listing_key.astype(str) == str(listing_key)]
        if source.empty:
            return []
        source_row = source.iloc[0]
        source_path = parse_category_path(source_row.get("global_catids"))
        if not source_path:
            # §4.6: an unmapped listing must not be matched against the whole
            # catalogue. "Similar to everything" is not an answer, so the caveat
            # is the answer.
            return [Evidence(
                evidence_id=self.evidence_id(), source_tier="btc_dataset",
                metric="similarity_unavailable", value="no_platform_category",
                unit="caveat",
                source_locator=SourceLocator(kind="internal", value="products_clean"),
                source_path="global_catids", dataset_version=self.repo.dataset_version,
                attrs={
                    "source_listing_key": listing_key,
                    "reason": "listing chưa được map vào danh mục sàn nên không so sánh được",
                },
            )]

        # Category membership is read per listing from the same physical keys the
        # certified in_platform_category relation uses. Shop shelves are never
        # consulted: there is no certified edge from them to platform taxonomy.
        by_key = {
            str(row.product_listing_key): row for row in products.itertuples()
        }
        folded_source = normalize_text(str(source_row.product_name))
        _, source_removed = strip_status_phrases(folded_source)

        # Rank a wide pool then filter by category, not the reverse: a
        # distinctive title can fill its top-40 with other categories, which
        # would silently return fewer than top_k same-category neighbours.
        candidates = self.resolver.resolve(
            str(source_row.product_name), limit=max(top_k * 40, 250),
        )
        scored = []
        for candidate in candidates:
            if candidate.listing_key == listing_key:
                continue
            row = by_key.get(str(candidate.listing_key))
            if row is None:
                continue
            path = parse_category_path(getattr(row, "global_catids", None))
            overlap = category_overlap(source_path, path)
            if not overlap["same_level1"]:
                continue  # hard constraint: same level-1 or not a candidate
            _, removed = strip_status_phrases(normalize_text(candidate.product_name))
            scored.append((candidate, path, overlap, removed))

        # Deeper taxonomy agreement outranks a marginally better title score.
        scored.sort(
            key=lambda item: (item[2]["shared_depth"], item[0].final_score),
            reverse=True,
        )
        result: list[Evidence] = []
        for candidate, path, overlap, removed in scored[:top_k]:
            result.append(Evidence(
                evidence_id=self.evidence_id(), source_tier="btc_dataset", metric="similarity_score",
                value=round(candidate.final_score, 6), unit="cosine_fusion_score",
                source_locator=SourceLocator(kind="internal", value="products_clean"), source_path="product_name_clean",
                dataset_version=self.repo.dataset_version,
                attrs={
                    "source_listing_key": listing_key,
                    "candidate_listing_key": candidate.listing_key,
                    "product_name": candidate.product_name,
                    "rank": len(result) + 1,
                    "lexical_score": candidate.lexical_score,
                    "semantic_score": candidate.semantic_score,
                    "platform_category_path": list(path),
                    "source_category_path": list(source_path),
                    "same_level1": overlap["same_level1"],
                    "same_level2": overlap["same_level2"],
                    "same_leaf": overlap["same_leaf"],
                    "status_tokens_removed": list(dict.fromkeys(source_removed + removed)),
                    "status_registry_version": STATUS_PHRASE_REGISTRY_VERSION,
                    "status_registry_hash": STATUS_PHRASE_REGISTRY_HASH,
                },
            ))
        return result

    def promotion_observation(self, country: str) -> list[Evidence]:
        snapshots = self.repo.snapshots.query("country_code == @country").copy()
        if snapshots.empty:
            return []
        latest_date = str(snapshots.date.astype(str).max())
        latest = snapshots.loc[
            snapshots.date.astype(str) == latest_date
        ].drop_duplicates("product_listing_key")
        valid = latest.loc[latest.monthly_sold_value_num.notna()]
        if valid.empty or latest.has_structured_voucher.nunique() < 2:
            return []
        result = []
        # The count runs over the whole scope; the aggregates run over the rows
        # where the proxy is measurable. Sharing one filtered frame made
        # "bao nhiêu listing có voucher" answer "...và đo được lượt bán": 551
        # instead of 577, with the two groups summing to 628 against a scope of
        # 668 and nothing reporting the missing 40. Same separation as
        # ``discount_bucket_observation`` below.
        for has_voucher, group in latest.groupby("has_structured_voucher", observed=True):
            label = "with_voucher" if bool(has_voucher) else "without_voucher"
            measurable = group.loc[group.monthly_sold_value_num.notna()]
            excluded = int(len(group) - len(measurable))
            attrs = {"country": country, "snapshot_date": latest_date, "group": label, "observational_only": True}
            common = dict(source_tier="btc_dataset", source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics"), dataset_version=self.repo.dataset_version, attrs=attrs)
            # A count of the whole scope and an aggregate over a subset are two
            # different populations; only the aggregate carries the exclusion.
            proxy_attrs = {
                **attrs,
                "unmeasurable_excluded_count": excluded,
                "measurable_basis": "monthly_sold_value_num",
            }
            proxy_common = {**common, "attrs": proxy_attrs}
            result.append(Evidence(evidence_id=self.evidence_id(), metric=f"{label}_listing_count", value=int(len(group)), unit="listings", source_path="has_structured_voucher", **common))
            if measurable.empty:
                continue
            result.extend([
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_mean_monthly_sold_proxy", value=round(float(measurable.monthly_sold_value_num.mean()), 6), unit="items", source_path="monthly_sold_value_num", **proxy_common),
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_median_monthly_sold_proxy", value=round(float(measurable.monthly_sold_value_num.median()), 6), unit="items", source_path="monthly_sold_value_num", **proxy_common),
            ])
        return result

    def voucher_coverage_by_country(self) -> list[Evidence]:
        snapshots = self.repo.snapshots.copy()
        latest_date = str(snapshots.date.astype(str).max())
        latest = snapshots.loc[
            snapshots.date.astype(str) == latest_date
        ].drop_duplicates("product_listing_key")
        result = []
        for country in ("vn", "id"):
            group = latest.loc[latest.country_code == country]
            count = int(group.has_structured_voucher.fillna(False).astype(bool).sum())
            result.append(Evidence(
                evidence_id=self.evidence_id(),
                source_tier="btc_dataset",
                metric="structured_voucher_listing_count",
                value=count,
                unit="listings",
                source_locator=SourceLocator(
                    kind="internal", value="product_snapshot_metrics",
                ),
                source_path="has_structured_voucher",
                dataset_version=self.repo.dataset_version,
                attrs={
                    "country": country,
                    "snapshot_date": latest_date,
                    "group": country,
                    "dedupe": "product_listing_key",
                },
            ))
        return result

    def discount_bucket_observation(self, target_percent: float = 50.0) -> list[Evidence]:
        snapshots = self.repo.snapshots.copy()
        latest_date = str(snapshots.date.astype(str).max())
        latest = snapshots.loc[
            snapshots.date.astype(str) == latest_date
        ].drop_duplicates("product_listing_key")
        bucket = latest.loc[
            latest.discount_percent_analysis.between(
                target_percent - 5, target_percent + 5, inclusive="both",
            )
        ]
        median_sold = (
            float(bucket.monthly_sold_value_num.dropna().median())
            if bucket.monthly_sold_value_num.notna().any()
            else 0.0
        )
        common = dict(
            source_tier="btc_dataset",
            source_locator=SourceLocator(
                kind="internal", value="product_snapshot_metrics",
            ),
            dataset_version=self.repo.dataset_version,
            attrs={
                "country": "vn+id_separate_nonmonetary",
                "snapshot_date": latest_date,
                "group": "discount_45_to_55_percent",
                "observational_only": True,
            },
        )
        return [
            Evidence(
                evidence_id=self.evidence_id(),
                metric="discount_bucket_listing_count",
                value=int(len(bucket)),
                unit="listings",
                source_path="discount_percent_analysis",
                **common,
            ),
            Evidence(
                evidence_id=self.evidence_id(),
                metric="discount_bucket_median_monthly_sold_proxy",
                value=round(median_sold, 6),
                unit="items",
                source_path="monthly_sold_value_num",
                **common,
            ),
        ]

    def dataset_coverage(self) -> list[Evidence]:
        dates = sorted(self.repo.snapshots.date.astype(str).dropna().unique().tolist())
        common = dict(
            source_tier="btc_dataset",
            source_locator=SourceLocator(
                kind="internal", value="product_snapshot_metrics",
            ),
            dataset_version=self.repo.dataset_version,
            attrs={
                "country": "vn+id",
                "snapshot_date": dates[-1],
                "coverage_dates": dates,
            },
        )
        return [
            Evidence(
                evidence_id=self.evidence_id(), metric="coverage_start_date",
                value=dates[0], unit="date", source_path="date", **common,
            ),
            Evidence(
                evidence_id=self.evidence_id(), metric="coverage_end_date",
                value=dates[-1], unit="date", source_path="date", **common,
            ),
            Evidence(
                evidence_id=self.evidence_id(), metric="coverage_snapshot_count",
                value=len(dates), unit="snapshots", source_path="date", **common,
            ),
        ]

    # Định nghĩa cố định của voucher_profile_rank_v1 (V2 §2.8, T-11):
    # weights + ngưỡng sample là một phần của contract, không phải tham số tự do.
    VOUCHER_PROFILE_WEIGHTS = {"voucher_rate": 0.4, "median_discount_ratio": 0.3,
                               "descriptive_gap_median_sold": 0.3}
    VOUCHER_PROFILE_MIN_LISTINGS = 5

    def voucher_profile_rank(self, country: str) -> list[Evidence]:
        """Descriptive multi-signal voucher profile per shop — KHÔNG đo hiệu quả nhân quả.

        SP1: voucher_rate = share(has_structured_voucher) per shop.
        SP2: descriptive_gap_median_sold = median(sold|voucher) − median(sold|không) CÙNG shop.
        SP3: median_discount_ratio = median(voucher_discount/price) trên dòng có voucher.
        SYN: score = Σ wᵢ·minmax(SPᵢ) trên các shop đủ điều kiện; trả top-1 + breakdown.
        """
        snapshots = self.repo.snapshots.query("country_code == @country").copy()
        if snapshots.empty:
            return []
        latest_date = str(snapshots.date.astype(str).max())
        latest = snapshots.loc[snapshots.date.astype(str) == latest_date]
        # G6: một snapshot + dedupe listing trước mọi thống kê.
        rows = latest.drop_duplicates("product_listing_key").copy()

        components: list[dict] = []
        low_coverage_excluded = 0
        missing_group_excluded = 0
        # Same separation as ``promotion_observation``: the shop's size and the
        # min-listings gate are properties of the shop, not of how much of it is
        # measurable. Filtering first reported a shop with enough listings but
        # few measurable ones as low-coverage, which reads as "too small".
        for shop_id, group in rows.groupby("shop_id", observed=True):
            if len(group) < self.VOUCHER_PROFILE_MIN_LISTINGS:
                low_coverage_excluded += 1
                continue
            flags = group.has_structured_voucher.astype(bool)
            measurable = group.loc[group.monthly_sold_value_num.notna()]
            with_voucher = measurable.loc[measurable.has_structured_voucher.astype(bool)]
            without_voucher = measurable.loc[~measurable.has_structured_voucher.astype(bool)]
            if with_voucher.empty or without_voucher.empty:
                missing_group_excluded += 1
                continue
            priced = with_voucher.loc[
                (with_voucher.price_num > 0) & with_voucher.voucher_discount_num.notna()
            ]
            if priced.empty:
                missing_group_excluded += 1
                continue
            components.append({
                "shop_id": str(shop_id), "n_listings": int(len(group)),
                "n_measurable_listings": int(len(measurable)),
                "voucher_rate": float(flags.mean()),
                "median_discount_ratio": float((priced.voucher_discount_num / priced.price_num).median()),
                "descriptive_gap_median_sold": float(
                    with_voucher.monthly_sold_value_num.median()
                    - without_voucher.monthly_sold_value_num.median()
                ),
            })
        if not components:
            return []

        def _minmax(name: str) -> dict[str, float]:
            values = [item[name] for item in components]
            low, high = min(values), max(values)
            if high == low:
                return {item["shop_id"]: 1.0 for item in components}
            return {item["shop_id"]: (item[name] - low) / (high - low) for item in components}

        normalized = {name: _minmax(name) for name in self.VOUCHER_PROFILE_WEIGHTS}
        for item in components:
            item["score"] = round(sum(
                weight * normalized[name][item["shop_id"]]
                for name, weight in self.VOUCHER_PROFILE_WEIGHTS.items()
            ), 6)
        # Tie-break deterministic: score giảm dần rồi shop_id tăng dần.
        components.sort(key=lambda item: (-item["score"], item["shop_id"]))
        top = components[0]
        shop_name = self._shop_display_name(top["shop_id"], rows)

        common = dict(
            source_tier="btc_dataset",
            source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics"),
            dataset_version=self.repo.dataset_version,
            attrs={
                "country": country, "snapshot_date": latest_date,
                "definition": "voucher_profile_rank_v1", "observational_only": True,
                "weights": dict(self.VOUCHER_PROFILE_WEIGHTS),
                "min_listings": self.VOUCHER_PROFILE_MIN_LISTINGS,
                "shop_id": top["shop_id"], "n_listings": top["n_listings"],
                "low_coverage_excluded": low_coverage_excluded,
                "missing_group_excluded": missing_group_excluded,
            },
        )
        return [
            Evidence(evidence_id=self.evidence_id(), metric="top_voucher_profile_shop_name",
                     value=shop_name, unit="shop_name", source_path="shop_id", **common),
            Evidence(evidence_id=self.evidence_id(), metric="voucher_profile_score",
                     value=top["score"], unit="score_0_1", source_path="derived", **common),
            Evidence(evidence_id=self.evidence_id(), metric="voucher_rate",
                     value=round(top["voucher_rate"], 6), unit="share_0_1",
                     source_path="has_structured_voucher", **common),
            Evidence(evidence_id=self.evidence_id(), metric="median_discount_ratio",
                     value=round(top["median_discount_ratio"], 6), unit="ratio_0_1",
                     source_path="voucher_discount_num", **common),
            Evidence(evidence_id=self.evidence_id(), metric="descriptive_gap_median_sold",
                     value=round(top["descriptive_gap_median_sold"], 6), unit="units_recent_window",
                     source_path="monthly_sold_value_num", **common),
            Evidence(evidence_id=self.evidence_id(), metric="ranked_shop_count",
                     value=int(len(components)), unit="shops", source_path="shop_id", **common),
        ]

    def _shop_display_name(self, shop_id: str, rows) -> str:
        try:
            shops = self.repo.read("shop_info_clean.csv")
            match = shops.loc[shops.shop_id.astype(str) == shop_id]
            if not match.empty and "shop_name" in match.columns:
                name = str(match.iloc[0].shop_name)
                if name and name.lower() != "nan":
                    return name
        except Exception:
            pass
        return f"shop_id={shop_id}"

    def execute_analytical_plan(self, plan) -> list[Evidence]:
        from gladiators.planner.compiler import compile_plan
        from gladiators.planner.executor import QueryExecutor
        from gladiators.domain.catalog import CATALOG

        compiled = compile_plan(plan)
        executor = QueryExecutor(self.repo)
        try:
            result = executor.execute(compiled)
        finally:
            executor.close()
        parts = plan.plan_id.split(":")
        dataset_version = self.repo.dataset_version
        output_node = next(node for node in plan.nodes if node.node_id == plan.output_node)
        execution_attrs = {
            "expected_field_count": len(plan.requested_output_shape),
            "postconditions_passed": len(result.postconditions),
            "has_invariants": bool(output_node.invariants),
        }
        if result.rank_tie_at_cut:
            # A tie straddling the cut means different things at different
            # limits. At limit 1 the question asks which single row is highest
            # and the data does not determine one, so the answer would be
            # arbitrary. At limit N the caller asked for a sample of the top;
            # the sample is still valid even though its boundary is arbitrary,
            # so this is recorded for the trace rather than refused.
            key = ("rank_tie_at_cut" if compiled.rank_limit == 1
                   else "rank_tie_beyond_cut")
            execution_attrs[key] = True
        known_kinds = {
            "highest_revenue_day", "listing_count", "highest_price_listing",
            "highest_monthly_sold_listing", "top_shop_by_listing_count",
        }
        kind = parts[1] if len(parts) == 4 and parts[0] == "analytical" else "open"
        country = parts[2] if kind in known_kinds else next(
            (
                str(predicate.value) for node in plan.nodes for predicate in node.predicates
                if predicate.ref == "dim.country" and predicate.op == "eq"
            ),
            "unknown",
        )
        if result.frame.empty:
            observed_date = str(plan.time_scope[-1]) if plan.time_scope else "unknown"
            return [Evidence(
                evidence_id=self.evidence_id(), metric="result_count", value=0, unit="rows",
                source_tier="btc_dataset",
                source_locator=SourceLocator(kind="internal", value="compiled_semantic_plan"),
                source_path="result.row_count", dataset_version=dataset_version,
                attrs={"country": country, "observed_date": observed_date,
                       "plan_hash": compiled.plan_hash, "empty_result": True, "row_index": 0,
                       # Chỉ TÊN chiều đã lọc, không kèm giá trị: câu trả lời
                       # rỗng phải nêu được nó đã lọc theo gì, mà giá trị lọc có
                       # thể chứa chữ số và verifier.scan_numbers sẽ chấm chúng
                       # là số bịa (CLAUDE.md §3.1).
                       "filtered_refs": tuple(sorted({
                           predicate.ref for node in plan.nodes
                           for predicate in node.predicates
                       })),
                       **execution_attrs},
            )]
        row = result.frame.iloc[0]
        # Fall back to the plan's own scope, never to a hard-coded snapshot: a
        # synthesized plan for 2026-07-01 was labelling its evidence 2026-07-03,
        # which then tripped A22-ALIGN-DATE on a plan that was actually correct.
        observed_date = (
            str(row["date"]) if "date" in row
            else str(plan.time_scope[-1]) if plan.time_scope
            else "unknown"
        )
        currency = "VND" if country == "vn" else "IDR"
        common = dict(
            source_tier="btc_dataset",
            source_locator=SourceLocator(
                kind="internal",
                value="product_snapshot_metrics" if kind == "highest_revenue_day" else "products_clean",
            ),
            dataset_version=dataset_version,
            attrs={"country": country, "observed_date": observed_date, "plan_hash": compiled.plan_hash,
                   "proxy_only": True, **execution_attrs},
        )
        if kind not in known_kinds:
            output = {field.name: field for field in plan.requested_output_shape}
            returned = min(result.row_count, OPEN_RESULT_ROW_LIMIT)
            evidence: list[Evidence] = []
            for row_index, (_, result_row) in enumerate(
                result.frame.head(OPEN_RESULT_ROW_LIMIT).iterrows()
            ):
                for column, field in output.items():
                    if column not in result_row:
                        continue
                    value = result_row[column]
                    if hasattr(value, "item"):
                        value = value.item()
                    if value is None or isinstance(value, float) and math.isnan(value):
                        continue
                    if field.type == "date" and value is not None:
                        value = str(value)
                    semantic = CATALOG.get(field.semantic_ref or "")
                    unit = semantic.unit if semantic else field.type
                    if unit == "local_currency":
                        unit = currency
                    attrs = {
                        "country": country, "observed_date": observed_date,
                        "plan_hash": compiled.plan_hash, "row_index": row_index,
                        **execution_attrs,
                    }
                    if not evidence:
                        attrs.update({
                            "result_count": result.row_count,
                            "returned_rows": returned,
                            "row_limit": OPEN_RESULT_ROW_LIMIT,
                            "truncated": result.row_count > returned,
                        })
                    evidence.append(Evidence(
                        evidence_id=self.evidence_id(), metric=column, value=value,
                        unit=unit, source_path=field.semantic_ref or column,
                        source_tier="btc_dataset",
                        source_locator=SourceLocator(kind="internal", value="compiled_semantic_plan"),
                        dataset_version=dataset_version,
                        attrs=attrs,
                    ))
            return evidence
        if kind == "highest_revenue_day":
            return [
                Evidence(
                    evidence_id=self.evidence_id(), metric="highest_revenue_proxy_date", value=observed_date,
                    unit="date", source_path="date", **common,
                ),
                Evidence(
                    evidence_id=self.evidence_id(), metric="estimated_recent_revenue", value=float(row["estimated_recent_revenue"]),
                    unit=currency, source_path="estimated_recent_revenue", **common,
                ),
            ]
        if kind == "listing_count":
            return [Evidence(
                evidence_id=self.evidence_id(), metric="listing_count", value=int(row["listing_count"]),
                unit="listings", source_path="product_listing_key", **common,
            )]
        if kind == "top_shop_by_listing_count":
            shop_name = str(row["shop_name"])
            shop_id = str(row["shop_id"])
            common["source_locator"] = SourceLocator(kind="internal", value="products_clean+shop_info")
            common["attrs"] = {**common["attrs"], "shop_name": shop_name, "shop_id": shop_id}
            return [
                Evidence(
                    evidence_id=self.evidence_id(), metric="shop_name", value=shop_name,
                    unit="shop_name", source_path="shop_name", **common,
                ),
                Evidence(
                    evidence_id=self.evidence_id(), metric="listing_count", value=int(row["listing_count"]),
                    unit="listings", source_path="product_listing_key", **common,
                ),
            ]
        product_name = str(row["product_name"])
        common["attrs"] = {**common["attrs"], "product_name": product_name}
        metric, unit = ("price", currency) if kind == "highest_price_listing" else ("monthly_sold", "units_recent_window")
        return [
            Evidence(
                evidence_id=self.evidence_id(), metric="product_name", value=product_name,
                unit="listing_name", source_path="product_name", **common,
            ),
            Evidence(
                evidence_id=self.evidence_id(), metric=metric, value=float(row[metric]),
                unit=unit, source_path=f"{metric}_num", **common,
            ),
        ]
