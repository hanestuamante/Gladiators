from dataclasses import dataclass


@dataclass(frozen=True)
class IntentSpec:
    name: str
    required_slots: tuple[str, ...]
    tool_plan: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()


class IntentRegistry:
    def __init__(self) -> None:
        self._items: dict[str, IntentSpec] = {}

    def register(self, spec: IntentSpec) -> None:
        if spec.name in self._items:
            raise ValueError(f"Intent đã tồn tại: {spec.name}")
        self._items[spec.name] = spec

    def get(self, name: str) -> IntentSpec | None:
        return self._items.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._items)


def default_registry() -> IntentRegistry:
    r = IntentRegistry()
    r.register(IntentSpec("sales_decline", ("entity_text",), ("resolve_entity", "get_sales_transitions"), ("monthly_sales_proxy",)))
    r.register(IntentSpec("similar_product", ("entity_text",), ("resolve_entity", "find_similar"), ("product_titles",)))
    r.register(IntentSpec("promotion_effectiveness", ("country",), ("compare_voucher_groups",), ("voucher_observation",)))
    return r

