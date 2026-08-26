"""Cache kết quả kế hoạch theo ``(plan_hash, dataset_version)`` — Spec2308 §A6.2.

Đây **không** phải cache ngữ nghĩa ("hai câu giống nhau thì trả cùng đáp án" —
có thể sai). Khoá là **mã kế hoạch đã qua validator** cộng **phiên bản dữ liệu**,
nên trúng cache không bao giờ đổi tính đúng đắn: cùng một plan trên cùng một
dataset chỉ có đúng một kết quả. Rẻ hơn *và* an toàn hơn.

Ba ràng buộc, mỗi cái vá một cách cache có thể nói dối:

* **A6-R1** — ``dataset_version`` nằm TRONG khoá. Không có nó, cache sống sót qua
  một lần đổi dữ liệu và trả số của dataset cũ dưới tên dataset mới.
* **A6-R2** — cache KHÔNG lưu ``Evidence``. ``Evidence`` mang ``evidence_id`` gắn
  với ``trace_id`` và nó bất biến; tái dùng một Evidence cũ là gắn câu trả lời
  này vào trace của câu khác.
* **A6-R3** — không cache plan có ``rank_tie_at_cut``. Trạng thái hoà ở mép cắt
  phụ thuộc DỮ LIỆU, không phụ thuộc plan, nên nó không phải hàm của khoá.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

CACHE_CAPACITY = 256


@dataclass(frozen=True)
class CachedResult:
    """Chỉ frame kết quả và hai con số đọc ra từ nó. Không Evidence (A6-R2)."""

    frame: Any
    row_count: int
    rank_tie_at_cut: bool


class PlanResultCache:
    """LRU trong bộ nhớ tiến trình, không ghi đĩa.

    Không ghi đĩa là có chủ đích: một cache trên đĩa sống lâu hơn tiến trình sinh
    ra nó, nên nó sống lâu hơn cả những giả định đã dựng nên nó.
    """

    def __init__(self, capacity: int = CACHE_CAPACITY) -> None:
        self.capacity = capacity
        self._items: OrderedDict[tuple[str, str], CachedResult] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, plan_hash: str, dataset_version: str) -> CachedResult | None:
        key = (str(plan_hash), str(dataset_version))
        found = self._items.get(key)
        if found is None:
            self.misses += 1
            return None
        self._items.move_to_end(key)
        self.hits += 1
        return found

    def put(
        self, plan_hash: str, dataset_version: str, result: CachedResult,
    ) -> bool:
        """Lưu, trừ khi kết quả phụ thuộc dữ liệu ngoài phạm vi khoá (A6-R3)."""
        if result.rank_tie_at_cut:
            return False
        key = (str(plan_hash), str(dataset_version))
        self._items[key] = result
        self._items.move_to_end(key)
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)
        return True

    def clear(self) -> None:
        self._items.clear()
        self.hits = self.misses = 0

    def stats(self) -> dict[str, Any]:
        lookups = self.hits + self.misses
        return {
            "hits": self.hits, "misses": self.misses, "size": len(self._items),
            "hit_rate": round(self.hits / lookups, 4) if lookups else None,
        }


PLAN_RESULT_CACHE = PlanResultCache()
