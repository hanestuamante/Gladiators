from __future__ import annotations

from collections.abc import Callable

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
        common = dict(source_tier="T1", source_locator=SourceLocator(kind="internal", value="product_transition_metrics"), dataset_version=self.repo.dataset_version, attrs={"listing_key": listing_key, "previous_date": str(row.previous_date), "date": str(row.date)})
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
                evidence_id=self.evidence_id(), source_tier="T1", metric="similarity_score",
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
            common = dict(source_tier="T1", source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics"), dataset_version=self.repo.dataset_version, attrs=attrs)
            result.extend([
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_listing_count", value=int(len(group)), unit="listings", source_path="has_structured_voucher", **common),
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_mean_monthly_sold_proxy", value=round(float(group.monthly_sold_value_num.mean()), 6), unit="items", source_path="monthly_sold_value_num", **common),
                Evidence(evidence_id=self.evidence_id(), metric=f"{label}_median_monthly_sold_proxy", value=round(float(group.monthly_sold_value_num.median()), 6), unit="items", source_path="monthly_sold_value_num", **common),
            ])
        return result
