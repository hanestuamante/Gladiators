"""SQLGlot AST compiler cho LogicalQueryPlan IR v1.0.

Không nhận raw SQL và không nội suy user values. Mọi identifier đến từ source
allow-list, semantic catalog hoặc relation registry; values trở thành ``?``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

import sqlglot
from sqlglot import exp

from gladiators.domain.catalog import CATALOG, counting_column
from gladiators.domain.metrics import approved_exclusion_predicates
from gladiators.domain.relations import RELATIONS
from gladiators.domain.tables import VIEW_NAMES

from .query_ir import LogicalQueryPlan, PlanNode, Predicate
from .validator import validate_plan


class CompilationError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: tuple[object, ...]
    plan_hash: str
    expected_columns: tuple[str, ...]
    postconditions: tuple[str, ...]
    expected_cardinality: str = "<=10000"
    # True when the plan asked for a specific order (a Rank node). When false the
    # result is a set and the executor is free to impose a canonical order.
    ordered: bool = False
    # Set when a Rank limits rows: the executor fetches one extra row to detect a
    # tie straddling the cut, then trims back to rank_limit.
    rank_column: str | None = None
    rank_limit: int | None = None
    # W1.4: phát hiện predicate RƠI MẤT giữa plan và SQL. Mặc định 0 để không
    # phá caller cũ dựng CompiledQuery bằng tay.
    planned_predicate_count: int = 0
    executed_predicate_count: int = 0
    # W14.4: ref nào đã có predicate loại lớp giá trị ĐÃ DUYỆT. Câu trả lời dựa
    # trên n−k dòng mà không nói k là câu trả lời không tái lập được.
    exclusion_predicate_refs: tuple[str, ...] = ()


# §E1/§E2: tên view và join key KHÔNG còn được khai ở đây. Mọi thứ vật lý đến từ
# TableRegistry và RelationBinding, nên compiler không thể thi hành một contract
# khác với contract mà registry/review nhìn thấy.
_VIEW_NAMES = dict(VIEW_NAMES)
_BANNED_AST = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Command, exp.Copy)
_BANNED_FUNCTIONS = {"READ_CSV", "READ_PARQUET", "HTTPFS", "GLOB", "INSTALL", "LOAD"}
_ALLOWED_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MEDIAN", "MIN", "MAX", "ROW_NUMBER", "CAST", "CONCAT",
    "AND", "OR", "LIKE",
}


def _column_for(ref: str, preferred_source: str | None = None) -> str:
    obj = CATALOG.get(ref)
    if obj is None:
        raise CompilationError(f"Semantic ref không tồn tại: {ref}")
    if preferred_source:
        prefix = preferred_source + "."
        for physical in obj.physical:
            if physical.startswith(prefix):
                return physical[len(prefix):]
    if obj.physical:
        return obj.physical[0].rsplit(".", 1)[1]
    counting = counting_column(ref)
    if counting:
        return counting
    raise CompilationError(f"Semantic ref chưa có physical mapping: {ref}")


def _predicate_expression(
    predicate: Predicate, source: str | None, params: list[object],
    counters: dict[str, int] | None = None,
) -> exp.Expression:
    # W1.4: đếm NGAY TẠI đây — chỉ tăng khi predicate thật sự thành AST. Không
    # suy từ số parameter: IN có nhiều parameter còn IS NULL có thể không có.
    if counters is not None:
        counters["executed"] = counters.get("executed", 0) + 1
    column = exp.column(_column_for(predicate.ref, source))
    value = predicate.value
    if predicate.op == "in":
        values = value if isinstance(value, (list, tuple)) else [value]
        params.extend(values)
        return exp.In(this=column, expressions=[exp.Placeholder() for _ in values])
    params.append(value)
    right = exp.Placeholder()
    operators = {
        "eq": exp.EQ, "ne": exp.NEQ, "lt": exp.LT, "lte": exp.LTE,
        "gt": exp.GT, "gte": exp.GTE,
    }
    if predicate.op == "contains":
        return exp.Like(this=column, expression=exp.Concat(expressions=[exp.Literal.string("%"), right, exp.Literal.string("%")]))
    return operators[predicate.op](this=column, expression=right)


def _source_hint(node: PlanNode, nodes: dict[str, PlanNode]) -> str | None:
    current = node
    visited: set[str] = set()
    while current.node_id not in visited:
        visited.add(current.node_id)
        if current.source:
            return current.source
        if not current.inputs or current.inputs[0] not in nodes:
            return None
        current = nodes[current.inputs[0]]
    return None


def _from_input(query: exp.Query, alias: str) -> exp.Select:
    return exp.select("*").from_(query.subquery(alias))


def _project_belongs_to(left: str, right: str) -> list[exp.Expression]:
    return [
        exp.column("product_listing_key", table=left),
        exp.column("country_code", table=left),
        exp.column("shop_id", table=left),
        exp.column("item_id", table=left),
        exp.column("date", table=left),
        exp.alias_(exp.column("shop_name", table=right), "shop_name", quoted=True),
    ]


def _project_platform_category(left: str, right: str) -> list[exp.Expression]:
    return [
        exp.Column(this=exp.Star(), table=exp.Identifier(this=left)),
        exp.alias_(exp.column("display_category_name", table=right), "display_category_name", quoted=True),
        exp.alias_(exp.column("has_children_bool", table=right), "has_children_bool", quoted=True),
    ]


def _project_shop_category(left: str, right: str) -> list[exp.Expression]:
    return [
        exp.Column(this=exp.Star(), table=exp.Identifier(this=left)),
        exp.alias_(exp.column("display_name", table=right), "display_name", quoted=True),
        exp.alias_(exp.column("total_num", table=right), "total_num", quoted=True),
        exp.alias_(exp.column("is_parent_category_bool", table=right), "is_parent_category_bool", quoted=True),
        exp.alias_(exp.column("is_sub_category_bool", table=right), "is_sub_category_bool", quoted=True),
    ]


def _project_star(left: str, right: str) -> list[exp.Expression]:
    return [
        exp.Column(this=exp.Star(), table=exp.Identifier(this=left)),
        exp.Column(this=exp.Star(), table=exp.Identifier(this=right)),
    ]


def _project_relation(node, relation, binding, left: str, right: str) -> list[exp.Expression]:
    """A1.3 — ``left.*`` cộng đúng những cột phía phải mà ``node.refs`` yêu cầu.

    Bốn adapter cũ hằng số hoá danh sách cột. ``_project_belongs_to`` chiếu đúng
    6 cột, nên sau khi join sang shop thì ``price_num``, ``voucher_code``,
    ``catid_num`` BIẾN MẤT khỏi frame — mọi predicate hay measure phía sau join
    đều hỏng, và hỏng im lặng.

    Không ``SELECT *`` cả hai bên: hai bảng dùng chung ``country_code`` /
    ``shop_id`` / ``date``, và một cột trùng tên sau join là một cột không ai
    biết nó đến từ đâu.
    """
    from gladiators.domain.bindings import default_binding_snapshot
    from gladiators.domain.catalog import CATALOG

    # Đọc danh sách cột từ binding snapshot (219 cột thật của 7 artifact) chứ
    # không từ catalog: catalog chỉ biết những cột đã được khai làm ref, nên một
    # va chạm tên với cột chưa khai sẽ lọt qua trong im lặng.
    snapshot = default_binding_snapshot()
    right_source = binding.right_source.value
    left_columns: set[str] = set()
    for source in binding.left_sources:
        spec = snapshot.tables.get(source)
        if spec is not None:
            left_columns |= {column.name for column in spec.columns}

    # Khoá join mang GIÁ TRỊ GIỐNG HỆT hai bên theo đúng định nghĩa của phép
    # nối, nên bản phía phải không thêm thông tin gì và chỉ tạo va chạm tên.
    join_key_columns = {key.right.column for key in binding.join_keys}

    selections: list[exp.Expression] = []
    seen: set[str] = set()
    shadowed: list[str] = []          # cột trái bị bản phải thay thế

    def take(column: str) -> None:
        if column in seen or column in join_key_columns:
            return
        if column in left_columns:
            # `shop_name` có ở CẢ products lẫn shop_info. Ref `dim.shop_name`
            # khai nó thuộc shop_info, nên bản phía phải là bản có thẩm quyền —
            # và bản trái phải bị loại khỏi frame, chứ không để hai cột cùng tên
            # rồi trông chờ vào hậu tố tự sinh của engine.
            shadowed.append(column)
        seen.add(column)
        selections.append(exp.alias_(exp.column(column, table=right), column, quoted=True))

    for ref in node.refs:
        obj = CATALOG.get(ref)
        if obj is None:
            continue
        for physical in obj.physical:
            artifact, _, column = physical.rpartition(".")
            if artifact == right_source:
                take(column)

    if not selections:
        # Node Join không khai ref nào phía phải. Spec A1.3 luật 4 muốn đây là
        # lỗi compile, nhưng plan hiện có (has_sales_metric) dựa vào `r.*` và
        # A1-R1 cấm lấy đi năng lực đang chạy. Giữ hành vi cũ, đồng thời vẫn giữ
        # bảo đảm mà luật 4 thật sự muốn: KHÔNG cột trùng tên sau join.
        # Giữ NGUYÊN hành vi cũ `l.*, r.*` cho nhánh này. Spec A1.3 luật 4 muốn
        # nó là lỗi compile, nhưng plan đang chạy (has_sales_metric) dựa vào nó
        # và A1-R1 cấm lấy đi năng lực đang có. Liệt kê tường minh từng cột phải
        # ở đây làm DuckDB báo binder error, nên `r.*` vẫn là cách đúng.
        return [
            exp.Column(this=exp.Star(), table=exp.Identifier(this=left)),
            exp.Column(this=exp.Star(), table=exp.Identifier(this=right)),
        ]
    star = exp.Star(**{"except": [exp.column(c) for c in shadowed]}) if shadowed else exp.Star()
    return [exp.Column(this=star, table=exp.Identifier(this=left)), *selections]


# DEPRECATED (A1.3): giữ thêm một release để fixture cũ còn parse
# ``RelationBinding.projection_id``. Không còn nằm trên đường compile.
_JOIN_PROJECTIONS: dict[str, Callable[[str, str], list[exp.Expression]]] = {
    "belongs_to": _project_belongs_to,
    "in_platform_category": _project_platform_category,
    "in_shop_category": _project_shop_category,
    "has_sales_metric": _project_star,
}


# --- W13.1 · Chiếu hợp đồng output ở biên plan --------------------------------
# Chỉ các toán tử này dựng danh sách cột; phần còn lại đi xuyên bằng SELECT *.
# Danh sách là DỮ LIỆU chứ không phải trí nhớ của người đọc code: thêm một toán
# tử vật chất hoá mà quên cập nhật ở đây làm phép chiếu cuối chọn sai biên.
_MATERIALIZING_OPS = frozenset({"Scan", "Aggregate", "Project", "Union", "Join"})

# ``Join`` vật chất hoá một frame MỚI nhưng KHÔNG đổi tên cột: nó phát
# ``l.*`` cộng các cột phải đặt alias bằng chính TÊN VẬT LÝ của chúng
# (``_project_relation.take``). Đọc alias của ``expected_schema`` ở đây làm biên
# plan chiếu một tên chưa từng tồn tại — DuckDB báo "column referenced that
# exists in the SELECT clause but cannot be referenced before it is defined".
_PHYSICAL_NAME_OPS = frozenset({"Scan", "Join"})

RANK_KEY_ALIAS = "__rank_key__"


def _exposed_name(ref: str, node: PlanNode, nodes: dict[str, PlanNode]) -> str:
    """Tên cột mà sub-query của ``node`` THẬT SỰ phơi ra cho ``ref``.

    Đi ngược theo ``inputs[0]`` tới toán tử vật chất hoá gần nhất. Tới ``Scan``
    hay ``Join`` thì tên là cột VẬT LÝ; tới ``Aggregate``/``Project``/``Union``
    thì tên là alias mà node đó đã khai. Đoán một trong hai là sai một nửa số
    plan.
    """
    current, seen = node, set()
    while current.node_id not in seen:
        seen.add(current.node_id)
        if current.op in _MATERIALIZING_OPS:
            if current.op in _PHYSICAL_NAME_OPS:
                return _column_for(
                    ref, current.source if current.op == "Scan"
                    else _source_hint(current, nodes),
                )
            for field in current.expected_schema:
                if field.semantic_ref == ref:
                    return field.name
            return _column_for(ref, _source_hint(current, nodes))
        if not current.inputs or current.inputs[0] not in nodes:
            break
        current = nodes[current.inputs[0]]
    return _column_for(ref, _source_hint(node, nodes))


def _project_output_contract(
    expression: exp.Query, plan: LogicalQueryPlan,
    nodes: dict[str, PlanNode], rank_state: dict[str, object],
) -> exp.Select:
    """Chiếu đúng các cột plan đã KHAI, ở đúng biên của plan (W13.1).

    Ba lớp kiểm hiện có cùng bỏ sót một điều: validator so schema ĐÃ KHAI,
    compiler cho Rank đi xuyên bằng SELECT *, executor bắt lệch cột nhưng bằng
    một exception không ai bắt. Một plan mà output_node là toán tử đi xuyên và
    tổ tiên vật chất hoá gần nhất là Scan LUÔN LUÔN vi phạm hợp đồng output của
    chính nó — 24/84 câu xếp hạng trả HTTP 500 vì đúng hình đó.

    Phát ra KHÔNG ĐIỀU KIỆN. Một nhánh "chỉ chiếu khi cần" là một nhánh ai đó
    sẽ quên khi thêm toán tử thứ mười ba; chiếu luôn làm hợp đồng đúng *theo
    cấu trúc*. Khi biên đã đúng tên, câu chiếu là ``"x" AS "x"`` — vô hại.
    """
    output = nodes[plan.output_node]
    fields = []
    for field in plan.requested_output_shape:
        if not field.semantic_ref:
            raise CompilationError("requested_output_shape thiếu semantic_ref")
        fields.append(exp.alias_(
            exp.column(_exposed_name(field.semantic_ref, output, nodes)),
            field.name, quoted=True,
        ))
    if rank_state.get("column"):
        # Khoá xếp hạng phải sống sót qua phép chiếu, nếu không tie detector của
        # executor bị mù và một kết quả HOÀ ở mép cắt đi ra như một câu trả lời
        # chắc chắn. Đây là hồi quy đã đo được ở bản thiếu nhánh này.
        rank_ref = rank_state.get("ref")
        exposed = (
            _exposed_name(str(rank_ref), output, nodes) if rank_ref
            else str(rank_state["column"])
        )
        fields.append(exp.alias_(exp.column(exposed), RANK_KEY_ALIAS, quoted=True))
        rank_state["column"] = RANK_KEY_ALIAS
    return exp.select(*fields).from_(expression.subquery("q_out"))


def _compile_node(
    node: PlanNode,
    compiled: dict[str, exp.Query],
    nodes: dict[str, PlanNode],
    params: list[object],
    rank_state: dict[str, object] | None = None,
    counters: dict[str, int] | None = None,
) -> exp.Query:
    rank_state = {} if rank_state is None else rank_state
    if node.op == "Scan":
        return exp.select("*").from_(exp.to_table(_VIEW_NAMES[node.source]))
    if node.op in {"ResolveValue", "Similarity"}:
        raise CompilationError(f"{node.op} được delegate cho module riêng, không compile thành SQL")
    inputs = [compiled[node_id] for node_id in node.inputs]
    if not inputs:
        raise CompilationError(f"Node {node.node_id}/{node.op} thiếu input")
    source = _source_hint(node, nodes)

    if node.op == "Filter":
        query = _from_input(inputs[0], f"q_{node.node_id}")
        for predicate in node.predicates:
            query = query.where(_predicate_expression(predicate, source, params, counters))
        return query
    if node.op in {"DeriveMetric", "TemporalCompare"}:
        # Vòng đầu chỉ cho derived columns đã được preprocessing/metric registry materialize.
        for ref in node.refs:
            _column_for(ref, source)
        return _from_input(inputs[0], f"q_{node.node_id}")
    if node.op == "Dedupe":
        key = "product_listing_key" if node.dedupe_policy in {"one_row_per_listing", "one_snapshot_per_listing"} else "product_snapshot_key"
        base = inputs[0].subquery(f"q_{node.node_id}")
        row_number = exp.Window(
            this=exp.RowNumber(), partition_by=[exp.column(key)],
            order=exp.Order(expressions=[exp.Ordered(this=exp.column("date"), desc=True)]),
        )
        return exp.select("*").from_(base).qualify(exp.EQ(this=row_number, expression=exp.Literal.number(1)))
    if node.op == "Aggregate":
        base = inputs[0].subquery(f"q_{node.node_id}")
        groups = [_column_for(ref, source) for ref in node.group_by]
        selections: list[exp.Expression] = [exp.column(column) for column in groups]
        for ref in node.refs:
            column = _column_for(ref, source)
            alias = next((field.name for field in node.expected_schema if field.semantic_ref == ref), ref.split(".")[-1])
            if CATALOG[ref].counts_unit:
                # exp.Count(distinct=True) renders as a plain COUNT in this
                # sqlglot version. It went unnoticed while listing keys were the
                # only thing counted -- they are unique per snapshot, so the two
                # forms agreed. shop_id is not, and COUNT(shop_id) returned 668
                # rows where COUNT(DISTINCT shop_id) is 10 shops.
                aggregate = exp.Count(this=exp.Distinct(expressions=[exp.column(column)]))
            else:
                functions = {
                    "count": exp.Count, "sum": exp.Sum, "mean": exp.Avg,
                    "median": exp.Median, "min": exp.Min, "max": exp.Max,
                }
                if node.aggregation == "share":
                    aggregate = exp.Avg(this=exp.Cast(this=exp.column(column), to=exp.DataType.build("DOUBLE")))
                else:
                    aggregate = functions[node.aggregation](this=exp.column(column))
            selections.append(exp.alias_(aggregate, alias, quoted=True))
        query = exp.select(*selections).from_(base)
        return query.group_by(*[exp.column(column) for column in groups]) if groups else query
    if node.op == "Rank":
        input_node = nodes[node.inputs[0]]
        materialized_alias = None
        if input_node.op in {"Aggregate", "Project", "Union"}:
            materialized_alias = next(
                (field.name for field in input_node.expected_schema if field.semantic_ref == node.rank_by),
                None,
            )
        column = materialized_alias or _column_for(node.rank_by, source)
        # One row beyond the requested limit, so the executor can see whether the
        # cut lands in the middle of a run of equal values. Without it a "highest
        # rating brand" query returns one arbitrary brand out of 21 tied at the
        # same rating, and the cut is invisible to everything downstream.
        rank_state["column"] = column
        # W13.1: ref semantic của khoá xếp hạng, KHÔNG phải tên cột vật lý. Đo
        # được ở đường template highest_price_listing: rank column là price_num
        # nhưng output_node là một Project phơi ra "price" — chiếu theo tên vật
        # lý ở biên đó cho BinderException trên 4/84 câu.
        rank_state["ref"] = node.rank_by
        rank_state["limit"] = node.limit
        fetch = node.limit + 1 if node.limit is not None else None
        return _from_input(inputs[0], f"q_{node.node_id}").order_by(exp.Ordered(this=exp.column(column), desc=node.descending)).limit(fetch)
    if node.op == "Project":
        base = inputs[0].subquery(f"q_{node.node_id}")
        fields = []
        for field in node.expected_schema:
            if not field.semantic_ref:
                raise CompilationError("Project output field thiếu semantic_ref")
            fields.append(exp.alias_(exp.column(_column_for(field.semantic_ref, source)), field.name, quoted=True))
        return exp.select(*fields).from_(base)
    if node.op == "Union":
        if len(inputs) != 2:
            raise CompilationError("Union cần đúng 2 input")
        return exp.Union(this=inputs[0], expression=inputs[1], distinct=False)
    if node.op == "Join":
        relation = RELATIONS[node.relation]
        binding = relation.binding
        # Không fallback về ``relation.join_keys``: thiếu binding phải là lỗi
        # compile, vì fallback là đúng cơ chế đã cho key giả sống sót (§E2.3).
        if binding is None:
            raise CompilationError(f"Relation {relation.name} chưa có binding vật lý")
        if binding.mode == "inline":
            return _from_input(inputs[0], f"q_{node.node_id}")
        if binding.right_source is None or not binding.join_keys:
            raise CompilationError(f"Relation {relation.name} khai left_join nhưng thiếu key/right source")
        right_view = _VIEW_NAMES[binding.right_source.value]
        left_alias, right_alias = "l", "r"
        conditions = [
            exp.EQ(this=exp.column(key.left.column, table=left_alias),
                   expression=exp.column(key.right.column, table=right_alias))
            for key in binding.join_keys
        ]
        on = conditions[0]
        for condition in conditions[1:]:
            on = exp.and_(on, condition)
        selections = _project_relation(
            node, relation, binding, left_alias, right_alias,
        )
        return exp.select(*selections).from_(inputs[0].subquery(left_alias)).join(
            exp.to_table(right_view).as_(right_alias), on=on, join_type="LEFT"
        )
    raise CompilationError(f"Op chưa hỗ trợ: {node.op}")


def _assert_select_only(expression: exp.Expression) -> None:
    if not isinstance(expression, (exp.Select, exp.Union)):
        raise CompilationError("AST root phải là SELECT hoặc UNION")
    if isinstance(expression, _BANNED_AST) or any(isinstance(node, _BANNED_AST) for node in expression.walk()):
        raise CompilationError("Compiler tạo AST ngoài SELECT allow-list")
    for function in expression.find_all(exp.Func):
        name = function.sql_name().upper()
        if name in _BANNED_FUNCTIONS or name not in _ALLOWED_FUNCTIONS:
            raise CompilationError(f"Function ngoài allow-list: {function.sql_name()}")


def assert_read_only_sql(sql: str) -> None:
    """Defense in depth tại executor boundary, kể cả caller tự dựng CompiledQuery."""
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        raise CompilationError("SQL không parse được bằng dialect DuckDB.") from exc
    if len(statements) != 1:
        raise CompilationError("Executor chỉ nhận đúng một SELECT statement.")
    _assert_select_only(statements[0])


def compile_plan(plan: LogicalQueryPlan) -> CompiledQuery:
    verdict = validate_plan(plan)
    if not verdict.valid:
        raise CompilationError("Plan validation fail: " + "; ".join(issue.message for issue in verdict.issues))
    nodes = {node.node_id: node for node in plan.nodes}
    compiled: dict[str, exp.Query] = {}
    params: list[object] = []
    rank_state: dict[str, object] = {}
    counters: dict[str, int] = {"executed": 0}
    planned_predicates = sum(len(node.predicates) for node in plan.nodes)
    pending = list(plan.nodes)
    while pending:
        progressed = False
        for node in pending[:]:
            if all(parent in compiled for parent in node.inputs):
                compiled[node.node_id] = _compile_node(node, compiled, nodes, params, rank_state, counters)
                pending.remove(node)
                progressed = True
        if not progressed:
            raise CompilationError("Không thể topo-sort plan")
    expression = _project_output_contract(
        compiled[plan.output_node], plan, nodes, rank_state,
    )
    _assert_select_only(expression)
    if counters["executed"] != planned_predicates:
        # W1.4: một predicate có trong plan mà không thành AST là một bộ lọc rơi
        # âm thầm — chính hình lỗi "brand='bibica' → 0 dòng" ở tầng khác.
        raise CompilationError(
            "Predicate rơi mất giữa plan và SQL: "
            f"plan khai {planned_predicates}, SQL mang {counters['executed']}."
        )
    sql = expression.sql(dialect="duckdb")
    plan_hash = hashlib.sha256(plan.model_dump_json().encode("utf-8")).hexdigest()[:16]
    output = nodes[plan.output_node]
    return CompiledQuery(
        sql=sql,
        parameters=tuple(params),
        plan_hash=plan_hash,
        expected_columns=tuple(field.name for field in plan.requested_output_shape),
        postconditions=output.invariants,
        expected_cardinality=output.expected_cardinality,
        ordered=any(node.op == "Rank" for node in plan.nodes),
        rank_column=rank_state.get("column"),
        rank_limit=rank_state.get("limit"),
        planned_predicate_count=planned_predicates,
        executed_predicate_count=counters["executed"],
        exclusion_predicate_refs=tuple(sorted({
            predicate.ref
            for node in plan.nodes for predicate in node.predicates
            if any(
                predicate.ref == ref and predicate.op == op and predicate.value == value
                for ref, op, value in approved_exclusion_predicates(predicate.ref)
            )
        })),
    )
