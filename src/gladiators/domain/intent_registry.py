from dataclasses import dataclass


@dataclass(frozen=True)
class IntentSpec:
    name: str
    required_slots: tuple[str, ...]
    tool_plan: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()
    macro_name: str | None = None


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
    from gladiators.planner.macros import default_macro_registry

    r = IntentRegistry()
    macros = default_macro_registry()
    for macro_name in macros.names():
        macro = macros.get(macro_name)
        r.register(IntentSpec(
            macro.name, macro.required_slots, macro.tool_plan,
            macro.required_capabilities, macro_name=macro.name,
        ))
    r.register(IntentSpec("analytical_query", (), ("execute_analytical_plan",), ("analytical_planner",)))
    r.register(IntentSpec("open_analytical", (), ("execute_analytical_plan",), ("semantic_parser", "analytical_planner")))
    return r
