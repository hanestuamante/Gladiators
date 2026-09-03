"""The four miners — ultimate solution §12.3.

Each miner reads governed data and emits cards with Evidence attached.  No LLM
is involved anywhere: text comes from the templates below, and priority comes
from a rule, because a model assigning "high" to a finding is a model deciding
what a human should look at first.

The wording constraints are the substance of this module, not decoration:

``price_move`` observes that two variables moved together and is forbidden from
saying one caused the other. The dataset has no experiment, no holdout and no
control -- a discount and a sales rise in the same window is a coincidence we
can measure, not a mechanism we can claim.

``voucher_gap`` may not say "lift" or "effectiveness" for the same reason, and
requires at least ten listings on each side, because a median over four rows
describes those four rows.

Both restrictions exist because the plausible sentence is the dangerous one: no
reader double-checks "giảm giá 15% giúp tăng doanh số".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .contracts import (
    InsightCard,
    InsightEvidence,
    InsightScope,
    stable_id,
)

DEFAULT_TOP_K = 5
DEFAULT_PRICE_DROP_PCT = -10.0
MIN_VOUCHER_GROUP_SIZE = 10

# Phrases that assert a mechanism the data cannot support. Checked, not trusted.
CAUSAL_PHRASES = (
    "vì", "do đó", "dẫn đến", "khiến", "giúp tăng", "làm tăng", "nhờ",
    "gây ra", "hiệu quả của", "tác động của", "lift", "causes", "because",
)


class CausalWordingError(ValueError):
    """Raised when generated text asserts causation. Build-breaking by design."""


def assert_no_causal_wording(text: str, *, where: str) -> str:
    lowered = text.lower()
    for phrase in CAUSAL_PHRASES:
        if phrase in lowered:
            raise CausalWordingError(
                f"{where}: câu chữ khẳng định nhân quả ('{phrase}') trong khi dữ liệu "
                "chỉ quan sát được tương quan"
            )
    return text


@dataclass(frozen=True)
class MinerConfig:
    top_k: int = DEFAULT_TOP_K
    price_drop_pct: float = DEFAULT_PRICE_DROP_PCT
    min_group_size: int = MIN_VOUCHER_GROUP_SIZE
    high_priority_percentile: float = 0.9


@dataclass(frozen=True)
class MinerOutput:
    cards: list[InsightCard]
    evidence: list[InsightEvidence]

    def __add__(self, other: "MinerOutput") -> "MinerOutput":
        return MinerOutput(self.cards + other.cards, self.evidence + other.evidence)


EMPTY = MinerOutput([], [])


def _evidence(insight_id: str, metric: str, value, unit: str, formula: str,
              artifact: str, row_key: str, dataset_version: str,
              caveat: str = "", currency_code: str | None = None) -> InsightEvidence:
    return InsightEvidence(
        evidence_id=stable_id("ev:insight", insight_id, metric, row_key),
        insight_id=insight_id, metric=metric, value=value, unit=unit, formula=formula,
        source_artifact=artifact, stable_row_key=row_key, caveat=caveat,
        dataset_version=dataset_version, currency_code=currency_code,
    )


BASE_SOLD_CAVEAT = "Sold proxy là chỉ báo hiển thị, không phải doanh số đã xác minh."


def _top_mover_caveat(tied: int, at_ceiling: bool) -> str:
    """Say when a "top mover" is one of several listings tied at the same value.

    Observed in the real bundle: in one market every positive delta topped out
    at the same round number, with several listings sharing it. Presenting five
    of them as the biggest movers reads as a ranking when it is a tie at what
    looks like a display-bucket boundary. Whether to exclude such rows is a
    product decision (§1.5); describing them accurately is not.
    """
    if not tied or tied <= 1:
        return BASE_SOLD_CAVEAT
    note = f"Có {tied} listing cùng mức thay đổi này nên thứ tự giữa chúng không có ý nghĩa xếp hạng."
    if at_ceiling:
        note += (
            " Mức này cũng là giá trị cao nhất quan sát được trong nhóm, phù hợp với "
            "việc sold proxy được làm tròn theo bậc hiển thị hơn là một phép đếm thật."
        )
    return f"{BASE_SOLD_CAVEAT} {note}"


def _num(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(result) else result


# --- 1. top movers --------------------------------------------------------

def mine_top_movers(
    transitions: pd.DataFrame, *, as_of_date: str, dataset_version: str,
    config: MinerConfig | None = None, category_of: dict[str, str] | None = None,
) -> MinerOutput:
    config = config or MinerConfig()
    if transitions.empty:
        return EMPTY
    frame = transitions.copy()
    if "transition_metric_eligible" in frame.columns:
        frame = frame[frame["transition_metric_eligible"].astype(str).str.lower().isin(("true", "1"))]
    frame["delta"] = pd.to_numeric(frame.get("snapshot_sales_delta_clean"), errors="coerce")
    frame = frame[frame["delta"] > 0]
    if frame.empty:
        return EMPTY

    cards: list[InsightCard] = []
    evidence: list[InsightEvidence] = []
    for country, group in frame.groupby("country_code"):
        top = group.sort_values(
            ["delta", "product_listing_key"], ascending=[False, True]
        ).head(config.top_k)
        threshold = group["delta"].quantile(config.high_priority_percentile)
        # How many listings share each delta. A "top mover" tied with several
        # others is not the listing that moved most -- it is one of N listings
        # whose display bucket ticked over, and picking 5 of them by key order
        # would present an arbitrary choice as a ranking.
        tie_counts = group["delta"].value_counts()
        group_max = group["delta"].max()
        for _, row in top.iterrows():
            listing = str(row["product_listing_key"])
            delta = _num(row["delta"])
            tied = int(tie_counts.get(row["delta"], 1))
            at_ceiling = delta is not None and delta == group_max and tied > 1
            insight_id = stable_id("ic:top_mover", dataset_version, listing, as_of_date)
            scope = InsightScope(
                country_code=str(country), as_of_date=as_of_date,
                platform_category_id=(category_of or {}).get(listing),
            )
            item = _evidence(
                insight_id, "snapshot_sales_delta_clean", delta, "sold_proxy_delta",
                "latest eligible transition delta", "product_transition_metrics.csv",
                f"{listing}@{row.get('date')}", dataset_version,
                caveat=_top_mover_caveat(tied, at_ceiling),
            )
            evidence.append(item)
            cards.append(InsightCard(
                insight_id=insight_id, kind="top_mover",
                title=f"Listing tăng sold proxy mạnh nhất tại {str(country).upper()}",
                finding=assert_no_causal_wording(
                    f"Listing {listing} có mức thay đổi sold proxy +{delta:,.0f} "
                    f"ở chặng chuyển tiếp gần nhất tính tới {as_of_date}.",
                    where="top_mover",
                ),
                scope=scope, evidence_ids=(item.evidence_id,),
                assumption_ids=("assume:sold_proxy_is_display_metric",),
                recommended_action="Kiểm tra tồn kho và mức giá của listing này trước đợt bán tiếp theo.",
                action_owner_role="category_manager",
                impact_metric="snapshot_sales_delta_clean", baseline_value=delta,
                target_definition="Giữ mức thay đổi sold proxy dương ở chặng kế tiếp",
                measurement_window="một chặng chuyển tiếp hợp lệ",
                confidence="observed",
                priority="high" if delta is not None and delta >= threshold else "medium",
                dataset_version=dataset_version,
            ))
    return MinerOutput(cards, evidence)


# --- 2. price move --------------------------------------------------------

def mine_price_moves(
    transitions: pd.DataFrame, *, as_of_date: str, dataset_version: str,
    config: MinerConfig | None = None, sentinel_listings: frozenset[str] = frozenset(),
    category_of: dict[str, str] | None = None,
) -> MinerOutput:
    """Two variables moved together. That is all this may say."""
    config = config or MinerConfig()
    if transitions.empty:
        return EMPTY
    frame = transitions.copy()
    if "transition_metric_eligible" in frame.columns:
        frame = frame[frame["transition_metric_eligible"].astype(str).str.lower().isin(("true", "1"))]
    frame["pct"] = pd.to_numeric(frame.get("price_change_percent"), errors="coerce")
    frame["delta"] = pd.to_numeric(frame.get("snapshot_sales_delta_clean"), errors="coerce")
    frame = frame[(frame["pct"] <= config.price_drop_pct) & (frame["delta"] > 0)]
    frame = frame[~frame["product_listing_key"].astype(str).isin(sentinel_listings)]
    if frame.empty:
        return EMPTY

    cards: list[InsightCard] = []
    evidence: list[InsightEvidence] = []
    for _, row in frame.sort_values(
        ["pct", "product_listing_key"], ascending=[True, True]
    ).head(config.top_k).iterrows():
        listing = str(row["product_listing_key"])
        pct, delta = _num(row["pct"]), _num(row["delta"])
        insight_id = stable_id("ic:price_move", dataset_version, listing, as_of_date)
        row_key = f"{listing}@{row.get('date')}"
        # Two separate Evidence records: one per variable, so a reader can see
        # they are two observations rather than one linked measurement.
        price_ev = _evidence(
            insight_id, "price_change_percent", pct, "percent",
            "(price - previous_price) / previous_price", "product_transition_metrics.csv",
            row_key, dataset_version,
        )
        sold_ev = _evidence(
            insight_id, "snapshot_sales_delta_clean", delta, "sold_proxy_delta",
            "clean sold proxy delta", "product_transition_metrics.csv", row_key,
            dataset_version,
            caveat="Hai biến số cùng thay đổi trong một cửa sổ; dữ liệu không có "
                   "nhóm đối chứng nên không kết luận được quan hệ nhân quả.",
        )
        evidence.extend((price_ev, sold_ev))
        cards.append(InsightCard(
            insight_id=insight_id, kind="price_move",
            title=f"Giá giảm và sold proxy tăng cùng chặng tại {str(row['country_code']).upper()}",
            finding=assert_no_causal_wording(
                f"Listing {listing} có giá thay đổi {pct:,.1f}% và sold proxy thay đổi "
                f"+{delta:,.0f} trong cùng một chặng chuyển tiếp. Đây là hai quan sát "
                "cùng cửa sổ thời gian, không phải quan hệ đã kiểm chứng.",
                where="price_move",
            ),
            scope=InsightScope(
                country_code=str(row["country_code"]), as_of_date=as_of_date,
                platform_category_id=(category_of or {}).get(listing),
            ),
            evidence_ids=(price_ev.evidence_id, sold_ev.evidence_id),
            assumption_ids=("assume:no_control_group", "assume:sold_proxy_is_display_metric"),
            recommended_action="Nếu muốn kết luận, thiết kế thử nghiệm có nhóm đối chứng trước khi mở rộng mức giảm giá.",
            action_owner_role="pricing_analyst",
            impact_metric="price_change_percent", baseline_value=pct,
            target_definition="Có thiết kế thử nghiệm trước khi áp dụng rộng",
            measurement_window="một chặng chuyển tiếp hợp lệ",
            confidence="observed", priority="medium", dataset_version=dataset_version,
        ))
    return MinerOutput(cards, evidence)


# --- 3. voucher gap (VN only) --------------------------------------------

def mine_voucher_gap(
    snapshots: pd.DataFrame, *, as_of_date: str, dataset_version: str,
    config: MinerConfig | None = None,
) -> MinerOutput:
    """VN only: structured vouchers are only observed there (§12.3)."""
    config = config or MinerConfig()
    if snapshots.empty:
        return EMPTY
    frame = snapshots[
        (snapshots["country_code"] == "vn") & (snapshots["date"] == as_of_date)
    ].copy()
    if frame.empty:
        return EMPTY
    frame["has_voucher"] = frame.get("has_structured_voucher").astype(str).str.lower().isin(
        ("true", "1")
    )
    frame["sold"] = pd.to_numeric(frame.get("monthly_sold_value_num"), errors="coerce")
    with_voucher = frame[frame["has_voucher"]]["sold"].dropna()
    without = frame[~frame["has_voucher"]]["sold"].dropna()
    # A median over four rows describes those four rows.
    if len(with_voucher) < config.min_group_size or len(without) < config.min_group_size:
        return EMPTY

    median_with = float(with_voucher.median())
    median_without = float(without.median())
    difference = median_with - median_without
    insight_id = stable_id("ic:voucher_gap", dataset_version, "vn", as_of_date)
    evidence = [
        _evidence(insight_id, "median_monthly_sold_with_voucher", median_with,
                  "units_recent_window", "median sold proxy, nhóm có voucher",
                  "product_snapshot_metrics.csv", f"vn@{as_of_date}#with", dataset_version,
                  caveat=f"n={len(with_voucher)}"),
        _evidence(insight_id, "median_monthly_sold_without_voucher", median_without,
                  "units_recent_window", "median sold proxy, nhóm không voucher",
                  "product_snapshot_metrics.csv", f"vn@{as_of_date}#without", dataset_version,
                  caveat=f"n={len(without)}"),
    ]
    card = InsightCard(
        insight_id=insight_id, kind="voucher_gap",
        title="Chênh lệch sold proxy giữa nhóm có và không có voucher tại VN",
        finding=assert_no_causal_wording(
            f"Tại VN ngày {as_of_date}, sold proxy trung vị của nhóm có voucher là "
            f"{median_with:,.0f} (n={len(with_voucher)}) so với {median_without:,.0f} "
            f"(n={len(without)}) ở nhóm không có voucher, chênh {difference:,.0f}. "
            "Hai nhóm không được phân bổ ngẫu nhiên nên đây là mô tả, không phải so sánh có kiểm soát.",
            where="voucher_gap",
        ),
        scope=InsightScope(country_code="vn", as_of_date=as_of_date),
        evidence_ids=tuple(e.evidence_id for e in evidence),
        assumption_ids=("assume:groups_not_randomised", "assume:sold_proxy_is_display_metric"),
        recommended_action="Xem lại tiêu chí gắn voucher trước khi coi chênh lệch này là kết quả của voucher.",
        action_owner_role="promotion_manager",
        impact_metric="median_monthly_sold", baseline_value=median_without,
        target_definition="Có phân nhóm so sánh được trước khi kết luận",
        measurement_window=f"một snapshot ({as_of_date})",
        confidence="observed", priority="medium", dataset_version=dataset_version,
    )
    return MinerOutput([card], evidence)


# --- 4. data quality ------------------------------------------------------

def mine_data_quality(
    issues: pd.DataFrame, *, as_of_date: str, dataset_version: str,
    country_code: str = "vn",
) -> MinerOutput:
    """Only issues that map to a source and rows; anything else is a rumour."""
    if issues is None or issues.empty:
        return EMPTY
    frame = issues.copy()
    source_column = next(
        (c for c in ("source_file", "artifact", "source") if c in frame.columns), None
    )
    if source_column is None:
        return EMPTY

    cards: list[InsightCard] = []
    evidence: list[InsightEvidence] = []
    issue_column = next(
        (c for c in ("issue", "issue_type", "check", "rule") if c in frame.columns), None
    )
    if issue_column is None:
        return EMPTY

    grouped = frame.groupby([issue_column, source_column]).size().reset_index(name="row_count")
    for _, row in grouped.sort_values(
        ["row_count", issue_column], ascending=[False, True]
    ).iterrows():
        issue = str(row[issue_column])
        artifact = str(row[source_column])
        count = int(row["row_count"])
        insight_id = stable_id("ic:data_quality", dataset_version, issue, artifact)
        item = _evidence(
            insight_id, "affected_rows", count, "count", "đếm row theo issue và artifact",
            artifact, f"{artifact}#{issue}", dataset_version,
        )
        evidence.append(item)
        cards.append(InsightCard(
            insight_id=insight_id, kind="data_quality",
            title=f"Vấn đề dữ liệu: {issue}",
            finding=assert_no_causal_wording(
                f"Có {count:,} dòng trong {artifact} vướng kiểm tra '{issue}'. "
                "Các phép tính đọc trực tiếp từ những dòng này bị ảnh hưởng.",
                where="data_quality",
            ),
            scope=InsightScope(country_code=country_code, as_of_date=as_of_date),
            evidence_ids=(item.evidence_id,),
            assumption_ids=("assume:issue_has_row_mapping",),
            recommended_action="Xử lý hoặc loại trừ các dòng này trước khi dùng chúng trong báo cáo.",
            action_owner_role="data_engineer",
            impact_metric="affected_rows", baseline_value=float(count),
            target_definition="Giảm số dòng vướng kiểm tra về 0",
            measurement_window="mỗi lần chạy pipeline",
            confidence="observed",
            # §12.3: "high" is reserved for issues that directly affect a
            # calculation, so it comes from a rule and never from a model.
            priority="high", dataset_version=dataset_version,
        ))
    return MinerOutput(cards, evidence)


def mine_all(
    *, snapshots: pd.DataFrame, transitions: pd.DataFrame, issues: pd.DataFrame,
    as_of_date: str, dataset_version: str, config: MinerConfig | None = None,
    sentinel_listings: frozenset[str] = frozenset(),
    category_of: dict[str, str] | None = None,
) -> MinerOutput:
    config = config or MinerConfig()
    return (
        mine_top_movers(transitions, as_of_date=as_of_date, dataset_version=dataset_version,
                        config=config, category_of=category_of)
        + mine_price_moves(transitions, as_of_date=as_of_date, dataset_version=dataset_version,
                           config=config, sentinel_listings=sentinel_listings,
                           category_of=category_of)
        + mine_voucher_gap(snapshots, as_of_date=as_of_date, dataset_version=dataset_version,
                           config=config)
        + mine_data_quality(issues, as_of_date=as_of_date, dataset_version=dataset_version)
    )
