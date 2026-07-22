from __future__ import annotations

from collections.abc import Callable
import math

from gladiators.contracts import Evidence
from gladiators.external.contracts import SourceLocator


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
        products = self.repo.products.drop_duplicates("product_listing_key")
        source = products.loc[products.product_listing_key.astype(str) == str(listing_key)]
        if source.empty:
            return []
        candidates = self.resolver.resolve(str(source.iloc[0].product_name), limit=max(top_k + 5, 20))
        result = []
        for candidate in (c for c in candidates if c.listing_key != listing_key):
            result.append(Evidence(
                evidence_id=self.evidence_id(), source_tier="btc_dataset", metric="similarity_score",
                value=round(candidate.final_score, 6), unit="cosine_fusion_score",
                source_locator=SourceLocator(kind="internal", value="products_clean"), source_path="product_name_clean",
                dataset_version=self.repo.dataset_version,
                attrs={"source_listing_key": listing_key, "candidate_listing_key": candidate.listing_key, "product_name": candidate.product_name, "rank": len(result) + 1, "lexical_score": candidate.lexical_score, "semantic_score": candidate.semantic_score},
            ))
            if len(result) >= top_k:
                break
        return result

    def promotion_observation(self, country: str) -> list[Evidence]:
        snapshots = self.repo.snapshots.query("country_code == @country").copy()
        if snapshots.empty:
            return []
        latest_date = str(snapshots.date.astype(str).max())
        latest = snapshots.loc[snapshots.date.astype(str) == latest_date]
        valid = latest.loc[latest.monthly_sold_value_num.notna()].copy()
        if valid.empty or valid.has_structured_voucher.nunique() < 2:
            return []
        result = []
        for has_voucher, group in valid.groupby("has_structured_voucher", observed=True):
            label = "with_voucher" if bool(has_voucher) else "without_voucher"
            attrs = {"country": country, "snapshot_date": latest_date, "group": label, "observational_only": True}
            common = dict(source_tier="btc_dataset", source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics"), dataset_version=self.repo.dataset_version, attrs=attrs)
            result.extend([
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_listing_count", value=int(len(group)), unit="listings", source_path="has_structured_voucher", **common),
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_mean_monthly_sold_proxy", value=round(float(group.monthly_sold_value_num.mean()), 6), unit="items", source_path="monthly_sold_value_num", **common),
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_median_monthly_sold_proxy", value=round(float(group.monthly_sold_value_num.median()), 6), unit="items", source_path="monthly_sold_value_num", **common),
            ])
        return result

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
                source_path="result.row_count", dataset_version=self.repo.dataset_version,
                attrs={"country": country, "observed_date": observed_date,
                       "plan_hash": compiled.plan_hash, "empty_result": True, "row_index": 0},
            )]
        row = result.frame.iloc[0]
        observed_date = str(row["date"]) if "date" in row else "2026-07-03"
        currency = "VND" if country == "vn" else "IDR"
        common = dict(
            source_tier="btc_dataset",
            source_locator=SourceLocator(
                kind="internal",
                value="product_snapshot_metrics" if kind == "highest_revenue_day" else "products_clean",
            ),
            dataset_version=self.repo.dataset_version,
            attrs={"country": country, "observed_date": observed_date, "plan_hash": compiled.plan_hash,
                   "proxy_only": True},
        )
        if kind not in known_kinds:
            output = {field.name: field for field in plan.requested_output_shape}
            evidence: list[Evidence] = []
            for row_index, result_row in result.frame.head(10).iterrows():
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
                    evidence.append(Evidence(
                        evidence_id=self.evidence_id(), metric=column, value=value,
                        unit=unit, source_path=field.semantic_ref or column,
                        source_tier="btc_dataset",
                        source_locator=SourceLocator(kind="internal", value="compiled_semantic_plan"),
                        dataset_version=self.repo.dataset_version,
                        attrs={"country": country, "observed_date": observed_date,
                               "plan_hash": compiled.plan_hash, "row_index": int(row_index)},
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
