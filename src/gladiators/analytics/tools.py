from __future__ import annotations

from collections.abc import Callable
from typing import Any
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


class SparseObservationError(RuntimeError):
    """W29-R1 — phạm vi được hỏi quá thưa để phát biểu về nó.

    ``clarify``, KHÔNG phải ``abstain``: câu hỏi TRẢ LỜI ĐƯỢC, chỉ là không ở
    cái grain thời gian người dùng nêu. Lời từ chối phải đề nghị đúng cách đọc
    thay thế — nói "không còn đường nào" là sai sự thật.
    """

    def __init__(self, verdict):
        self.verdict = verdict
        super().__init__(
            "Chỉ số này được quan sát một lần cho mỗi listing chứ không phải mỗi "
            "đợt thu, nên ở phạm vi được hỏi chỉ một phần rất nhỏ listing có "
            "quan sát. Có thể trả lời theo lần quan sát gần nhất của từng "
            "listing — bạn muốn cách đó không?",
        )


class _CachedExecution:
    """Kết quả dựng lại từ cache, đúng những trường phần sau đọc tới.

    Không tái dùng object ``ExecutionResult`` thật: nó mang postcondition đã chạy
    trên MỘT lượt thực thi, và mang chúng sang lượt khác là báo cáo một phép kiểm
    chưa từng chạy cho lượt này.
    """

    frame: Any
    rank_tie_at_cut: bool
    postconditions: tuple
    rank_limit: int | None





def _count_excluded_rows(plan, compiled, repo) -> dict[str, int]:
    """Số dòng mà predicate loại lớp giá trị đã bỏ đi, theo từng ref.

    Đếm bằng cách chạy lại đúng phạm vi lọc KHÔNG có predicate loại — nếu chỉ
    trừ hai con số tổng thì mọi predicate khác của câu hỏi cũng bị tính vào ``k``
    và con số nêu ra sẽ mô tả sai thứ đã xảy ra.
    """
    from gladiators.domain.metrics import matches_value_class, value_class_rules_for

    if not compiled.exclusion_predicate_refs:
        return {}
    counts: dict[str, int] = {}
    for ref in compiled.exclusion_predicate_refs:
        column = _physical_column_of(ref)
        if column is None or column not in repo.products.columns:
            continue
        scope = repo.products
        for node in plan.nodes:
            for predicate in node.predicates:
                if predicate.ref == "dim.country" and predicate.op == "eq":
                    scope = scope[scope.country_code == predicate.value]
                elif predicate.ref == "dim.date" and predicate.op == "eq":
                    scope = scope[scope.date == predicate.value]
        approved = [
            rule for rule in value_class_rules_for(ref) if rule.decision_id is not None
        ]
        hit = sum(
            1 for value in scope[column].dropna().tolist()
            if any(matches_value_class(rule, value) for rule in approved)
        )
        if hit:
            counts[ref] = hit
    return counts


def _physical_column_of(ref: str) -> str | None:
    from gladiators.domain.catalog import CATALOG

    obj = CATALOG.get(ref)
    for physical in getattr(obj, "physical", ()) or ():
        if physical.startswith("products_clean.csv."):
            return physical.split(".")[-1]
    return None




def _link_temporal_lineage(evidence: list[Evidence], plan) -> list[Evidence]:
    """Ba evidence start/end/delta của một TemporalCompare hai đầu mút (W6.3).

    Nhận diện bằng OUTPUT NODE ``op == "TemporalCompare"``, không bằng chuỗi
    "temporal" trong plan_id. ``previous_date``/``date`` trên evidence delta là
    ĐÚNG cặp khoá mà ``alignment._scope_issues`` đọc để so span với câu hỏi —
    khối mới đi qua chính phép kiểm đang chặn nó hôm nay, không phải một cửa
    riêng.
    """
    output = next(
        (node for node in plan.nodes if node.node_id == plan.output_node), None,
    )
    if (
        output is None or output.op != "TemporalCompare"
        or output.time_scope is None or len(output.time_scope) != 2
    ):
        return evidence
    d0, d1 = min(output.time_scope), max(output.time_scope)
    by_metric = {item.metric: item for item in evidence}
    start = next((v for k, v in by_metric.items() if k.endswith("_start")), None)
    end = next((v for k, v in by_metric.items() if k.endswith("_end")), None)
    delta = next((v for k, v in by_metric.items() if k.endswith("_delta")), None)
    if start is None or end is None or delta is None:
        return evidence
    linked = {
        start.evidence_id: start.model_copy(update={
            "attrs": {**start.attrs, "observed_date": d0},
        }),
        end.evidence_id: end.model_copy(update={
            "attrs": {**end.attrs, "observed_date": d1},
        }),
        delta.evidence_id: delta.model_copy(update={
            # Delta KHÔNG phải một quan sát tại một ngày: giữ observed_date của
            # đường generic sẽ ghi đè giá trị end trong map ngày→giá trị của
            # _observed_direction, và một chuỗi TĂNG 581→668 đọc thành GIẢM
            # 581→87 — đúng chiều mà câu hỏi tiền đề sai đang khẳng định.
            "attrs": {**{k: v for k, v in delta.attrs.items() if k != "observed_date"},
                      "previous_date": d0, "date": d1,
                      "derivation_op": "end_minus_start"},
            "parent_evidence_ids": (start.evidence_id, end.evidence_id),
        }),
    }
    return [linked.get(item.evidence_id, item) for item in evidence]


def _link_share_lineage(evidence: list[Evidence], plan) -> list[Evidence]:
    """Evidence tỷ lệ phải TRỎ về tử số và mẫu số của nó (W11.2 §12.3.2).

    ``discounted_listing_rate`` là derived, nên ``verifier._lineage_gaps`` đòi
    evidence tổ tiên. Dùng ``model_copy(update=...)`` — Evidence đã frozen
    (bất biến #4), và đó là điều kiện để không ai sửa được bản gốc.
    """
    from gladiators.domain.metrics import METRICS

    share = None
    for node in plan.nodes:
        if node.op != "Aggregate" or node.aggregation != "share":
            continue
        for ref in node.refs:
            spec = METRICS.get(ref.split(".", 1)[1]) if ref.startswith("derived.") else None
            if spec is not None and spec.share is not None:
                share = spec.share
                break
    if share is None:
        return evidence

    by_metric = {item.metric: item for item in evidence}
    numerator = by_metric.get(share.numerator_metric)
    denominator = by_metric.get(share.denominator_metric)
    rate_metric = next(
        (name for name, spec in METRICS.items() if spec.share is share), None,
    )
    rate = by_metric.get(rate_metric or "")
    if numerator is None or denominator is None or rate is None:
        return evidence
    linked = rate.model_copy(update={
        "parent_evidence_ids": (numerator.evidence_id, denominator.evidence_id),
        "attrs": {**rate.attrs, "derivation_op": "share", "scale": share.scale},
    })
    return [linked if item is rate else item for item in evidence]


def _value_class_report(plan, compiled, result) -> dict:
    """Giá trị BIÊN của kết quả có rơi vào một luật CHƯA DUYỆT không (W14.3).

    Chỉ đọc những dòng ĐÃ được lấy về — không quét thêm dữ liệu. "Biên" định
    nghĩa theo hình plan:

    - có ``Rank``: các dòng trong frame sau khi cắt, cộng dòng executor vẫn giữ
      để chấm hoà;
    - có ``Aggregate`` với ``max``/``min``: chính dòng kết quả;
    - ``median``/``mean``/``sum``/``count``/``share``: KHÔNG kiểm. Trung vị bền
      với đuôi — chặn nó lấy đi năng lực mà không đổi được con số nào.
    """
    from gladiators.domain.metrics import matches_value_class, value_class_rules_for

    aggregations = {
        node.aggregation for node in plan.nodes
        if node.op == "Aggregate" and node.aggregation
    }
    has_rank = any(node.op == "Rank" for node in plan.nodes)
    if not has_rank and not (aggregations & {"max", "min"}):
        return {}

    frame = result.frame
    if frame.empty:
        return {}

    checked: list[str] = []
    hits: list[dict] = []
    columns_by_ref = {
        field.semantic_ref: field.name
        for field in plan.requested_output_shape if field.semantic_ref
    }
    for ref, column in columns_by_ref.items():
        rules = value_class_rules_for(ref)
        if not rules or column not in frame.columns:
            continue
        checked.append(ref)
        for rule in rules:
            companion_column = columns_by_ref.get(rule.companion_ref or "")
            for row_index, value in enumerate(frame[column].tolist()):
                companion = (
                    frame[companion_column].tolist()[row_index]
                    if companion_column in frame.columns else None
                ) if companion_column else None
                if not matches_value_class(rule, value, companion):
                    continue
                hits.append({
                    "ref": ref, "rule_id": rule.rule_id, "value": float(value),
                    "row_index": row_index, "approved": rule.decision_id is not None,
                })
    return {
        "checked_refs": sorted(checked),
        "boundary_hits": hits,
        # Khoá đếm bắt buộc (§0.3 ô 4): không có nó, "chưa bao giờ có ca nào" và
        # "nhánh chưa bao giờ chạy" là hai bảng số giống hệt nhau.
        "blocked": any(not hit["approved"] for hit in hits),
    }


def _literal_verified(predicate, country: str) -> bool:
    """Literal của predicate đã được chứng minh tồn tại trong value index chưa.

    ``True`` khi một trong ba: ref không dò được (không phải chỗ lỗi này sống);
    giá trị không phải chuỗi; hoặc literal đúng BẰNG bản gốc trong chỉ mục —
    ``brand = 'bibica'`` trả 0 dòng vì dữ liệu ghi ``Bibica``, và cờ này là cách
    số 0 đó phân biệt được với một zero-row thật.

    Thị trường được hỏi tra TRƯỚC, rồi mới lùi về mọi thị trường. Thứ đang được
    chứng minh là CÁCH VIẾT, không phải sự có mặt: ``brand='ORION'`` viết đúng
    như dữ liệu ghi, nên số 0 của nó ở Indonesia là một zero-row thật — ORION
    có bán ở Việt Nam. Khoá phép kiểm theo country biến "không bán ở đây" thành
    "viết sai tên", và một câu trả lời đúng thành một lời từ chối.
    """
    from gladiators.agent.value_probe import (
        INDEXED_REFS, _fold, original_anywhere, original_of,
    )

    if predicate.ref not in INDEXED_REFS:
        return True
    if not isinstance(predicate.value, str):
        return True
    folded = _fold(predicate.value)
    if original_of(predicate.ref, country, folded) == predicate.value:
        return True
    return original_anywhere(predicate.ref, folded) == predicate.value


class AnalyticsTools:
    """Deterministic analytics. LLMs never calculate values in this class."""

    def __init__(self, repository, resolver, evidence_id: Callable[[], str]):
        self.last_plan_cache: dict[str, Any] = {}
        self.repo, self.resolver, self.evidence_id = repository, resolver, evidence_id

    def sales_decline(
        self, listing_key: str, window: tuple[str, str] | None = None,
    ) -> list[Evidence]:
        """Biến động lượt bán của một listing — theo CỬA SỔ được hỏi (W6.4).

        ``window=None`` giữ nguyên hành vi cũ (chặng cuối). Có ``window`` thì
        cộng dồn các chặng liên tiếp PHỦ KÍN cửa sổ; không phủ kín ⇒ trả ``[]``
        để tầng gọi ra A-NO-EVIDENCE — trả chặng cuối là đúng lỗi tc34: câu hỏi
        01/07→03/07 với các chặng +113 và −102 có tổng +11, còn chặng cuối là
        −102 với dấu NGƯỢC.
        """
        rows = self.repo.transitions.query("product_listing_key == @listing_key and transition_metric_eligible == True").sort_values("date")
        if rows.empty:
            return []
        if window is None:
            legs = rows.iloc[[-1]]
        else:
            legs = rows[
                (rows.previous_date.astype(str) >= window[0])
                & (rows.date.astype(str) <= window[1])
            ]
            covers = (
                not legs.empty
                and str(legs.iloc[0].previous_date) == window[0]
                and str(legs.iloc[-1].date) == window[1]
                and list(legs.previous_date.astype(str))[1:] == list(legs.date.astype(str))[:-1]
            )
            if not covers:
                return []
        first, last = legs.iloc[0], legs.iloc[-1]
        common = dict(
            source_tier="btc_dataset",
            source_locator=SourceLocator(kind="internal", value="product_transition_metrics"),
            dataset_version=self.repo.dataset_version,
            attrs={
                "listing_key": listing_key,
                "previous_date": str(first.previous_date), "date": str(last.date),
                "legs": int(len(legs)),
            },
        )
        return [
            Evidence(evidence_id=self.evidence_id(), metric="monthly_sold_delta", value=float(legs.monthly_sold_delta.sum()), unit="items", source_path="monthly_sold_delta", **common),
            Evidence(evidence_id=self.evidence_id(), metric="days_since_previous", value=int(legs.days_since_previous.sum()), unit="days", source_path="days_since_previous", **common),
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
        # KHÔNG đòi `monthly_sold` đo được mới cho chạy: đếm listing theo nhóm
        # voucher là một câu hỏi về CỜ VOUCHER, không phải về lượt bán. Guard cũ
        # bỏ cả phép đếm khi proxy không đo được — trên bộ 20 ngày `monthly_sold`
        # chỉ quan sát một lần mỗi listing, nên nó im lặng trả rỗng cho một câu
        # hỏi dữ liệu trả lời được. Cùng lớp "đếm thừa hưởng bộ lọc của đo".
        if latest.has_structured_voucher.nunique() < 2:
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
        from gladiators.planner.executor import ExecutionResult, QueryExecutor
        from gladiators.domain.catalog import CATALOG

        from gladiators.planner.plan_cache import PLAN_RESULT_CACHE, CachedResult

        compiled = compile_plan(
            plan, available_sources=frozenset(self.repo.available_artifacts()),
        )
        # ── W29 (S7.5) — cửa MẬT ĐỘ QUAN SÁT ────────────────────────────────
        # Sau compile (cần plan hợp lệ để biết scope), TRƯỚC execute (phải chặn
        # trước khi một con số tồn tại — con số đã tính rồi thì mọi lớp sau đều
        # thấy nó hợp lệ).
        from gladiators.analytics.density import DensityError, check as density_check

        self.last_density = None
        try:
            _agg = next(
                (node.aggregation for node in plan.nodes if node.op == "Aggregate"),
                None,
            )
            _refs = tuple({ref for node in plan.nodes for ref in node.refs})
            _dates = tuple(plan.time_scope or ())
            _country = next(
                (
                    str(predicate.value) for node in plan.nodes
                    for predicate in node.predicates
                    if predicate.ref == "dim.country"
                ),
                None,
            )
            # Root của CHÍNH bản dữ liệu đang phục vụ. Mặc định 'data/processed'
            # sẽ đọc mật độ của MỘT BẢN KHÁC — và một cửa mật độ đọc nhầm bản là
            # một cửa không gác gì.
            # W29-R7: ref trong bộ lọc đi RIÊNG — chúng được kiểm kể cả khi
            # phép tổng hợp là `count`, vì một bộ lọc trên cột không quan sát
            # được trả về tập rỗng trông y hệt một tập thật sự rỗng.
            _filter_refs = tuple({
                predicate.ref for node in plan.nodes
                for predicate in node.predicates
                if predicate.ref and predicate.ref != "dim.country"
            })
            _rank_refs = tuple({
                node.rank_by for node in plan.nodes if getattr(node, "rank_by", None)
            })
            self.last_density = density_check(
                _refs, _dates, _country, _agg, str(self.repo.root),
                filter_refs=_filter_refs, rank_refs=_rank_refs,
            )
        except DensityError:
            raise
        if self.last_density is not None and self.last_density.action == "clarify":
            raise SparseObservationError(self.last_density)
        dataset_version = self.repo.dataset_version
        # A6.2: tra cache SAU compile và TRƯỚC execute. Khoá là plan_hash — mã
        # kế hoạch ĐÃ QUA VALIDATOR — cộng dataset_version, nên trúng cache không
        # bao giờ đổi tính đúng đắn: cùng một plan trên cùng một dataset chỉ có
        # đúng một kết quả.
        cached = PLAN_RESULT_CACHE.get(compiled.plan_hash, dataset_version)
        if cached is not None:
            # Dựng lại chính ExecutionResult chứ không một bản thế thân: một
            # object thiếu trường mà phần sau đọc tới sẽ hỏng ở một chỗ cách xa
            # nguyên nhân, và nó chỉ hỏng trên đúng đường CÓ cache — tức đường ít
            # được kiểm nhất.
            #
            # postconditions để RỖNG có chủ đích: chúng là kết quả của MỘT lượt
            # thực thi, và mang chúng sang lượt khác là báo cáo một phép kiểm chưa
            # từng chạy cho lượt này.
            result = ExecutionResult(
                frame=cached.frame, plan_hash=compiled.plan_hash, explain="cached",
                row_count=cached.row_count, postconditions=(),
                rank_tie_at_cut=cached.rank_tie_at_cut,
            )
        else:
            executor = QueryExecutor(self.repo)
            try:
                result = executor.execute(compiled)
            finally:
                executor.close()
            # A6-R2: chỉ frame, không Evidence. Evidence mang evidence_id gắn với
            # trace_id và nó bất biến — tái dùng một Evidence cũ là gắn câu trả
            # lời này vào trace của câu khác.
            PLAN_RESULT_CACHE.put(compiled.plan_hash, dataset_version, CachedResult(
                frame=result.frame, row_count=int(len(result.frame)),
                rank_tie_at_cut=bool(result.rank_tie_at_cut),
            ))
        self.last_plan_cache = {
            "hit": cached is not None,
            "plan_hash": compiled.plan_hash,
            "dataset_version": dataset_version,
            **PLAN_RESULT_CACHE.stats(),
        }
        parts = plan.plan_id.split(":")
        output_node = next(node for node in plan.nodes if node.node_id == plan.output_node)
        # W5.1: phép tổng hợp ĐÃ THỰC HIỆN, đọc từ node Aggregate đã compile —
        # KHÔNG đọc từ plan_id. plan_id là telemetry, không phải contract thực
        # thi, và một plan_id khai ":median:" trong khi SQL trả về các dòng thô
        # là chính hình lỗi W5 tồn tại để sửa.
        performed_aggregations = tuple(sorted({
            str(node.aggregation) for node in plan.nodes
            if node.op == "Aggregate" and node.aggregation
        }))
        execution_attrs = {
            "expected_field_count": len(plan.requested_output_shape),
            "postconditions_passed": len(result.postconditions),
            "has_invariants": bool(output_node.invariants),
            **({"aggregation": performed_aggregations[0]}
               if len(performed_aggregations) == 1 else {}),
        }
        # W14.3: cùng chỗ rank_tie_at_cut được đọc — sau execute, TRƯỚC khi
        # dựng Evidence.
        self.last_value_class = _value_class_report(plan, compiled, result)
        # W14.4: bao nhiêu dòng bị loại thì phải nói ra bấy nhiêu. Đếm THẬT trên
        # cùng phạm vi lọc, không suy từ hằng số.
        excluded_by_value_class = _count_excluded_rows(plan, compiled, self.repo)
        if excluded_by_value_class:
            execution_attrs["excluded_by_value_class"] = excluded_by_value_class
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
            # Tên chỉ số KHÔNG được đổi theo giá trị của nó. Một plan đếm listing
            # trả 0 vẫn là ``listing_count``; gọi nó ``result_count`` làm câu trả
            # lời rỗng mất khả năng khớp với câu hỏi đã sinh ra nó — đo được:
            # "ORION có bao nhiêu listing tại Indonesia" trả đúng số 0 nhưng bị
            # chấm sai vì evidence không mang chỉ số nào tên là ``listing_count``.
            # Plan KHÔNG đếm (vd. lọc theo rating) vẫn giữ ``result_count``: ở đó
            # số 0 nói "không dòng nào", không nói "đếm được 0".
            counts_listings = any(
                ref == "derived.product_count"
                for node in plan.nodes for ref in node.refs
            )
            empty_metric, empty_unit = (
                ("listing_count", "listings") if counts_listings
                else ("result_count", "rows")
            )
            return [Evidence(
                evidence_id=self.evidence_id(), metric=empty_metric, value=0,
                unit=empty_unit,
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
                       # W1.4: ref + CỜ đã-chứng-minh, KHÔNG kèm literal — literal
                       # có thể chứa chữ số và verifier.scan_numbers sẽ chấm
                       # chúng là số không có evidence (CLAUDE.md §3.1).
                       "filter_bindings": tuple(sorted(
                           (predicate.ref, _literal_verified(predicate, country))
                           for node in plan.nodes
                           for predicate in node.predicates
                       )),
                       # Lấy từ CompiledQuery, KHÔNG đếm lại trên plan: mục đích
                       # là phát hiện predicate rơi mất giữa plan và SQL.
                       "executed_predicate_count": compiled.executed_predicate_count,
                       "planned_predicate_count": compiled.planned_predicate_count,
                       "relaxed_filters": False,
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
            return _link_temporal_lineage(_link_share_lineage(evidence, plan), plan)
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
