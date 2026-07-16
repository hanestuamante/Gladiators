from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSpec:
    name: str
    source: str
    unit: str
    interpretation: str


METRICS = {
    "monthly_sold_value_num": MetricSpec("monthly_sold_value_num", "product_snapshot_metrics.csv", "items", "Proxy lượt bán tháng tại snapshot; không phải doanh thu."),
    "monthly_sold_delta": MetricSpec("monthly_sold_delta", "product_transition_metrics.csv", "items", "Chênh lệch proxy giữa hai snapshot đủ điều kiện."),
    "price_num": MetricSpec("price_num", "product_snapshot_metrics.csv", "local_currency", "Giá niêm yết đã chuẩn hóa."),
}

