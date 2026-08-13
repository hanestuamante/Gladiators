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


def _predicate_expression(predicate: Predicate, source: str | None, params: list[object]) -> exp.Expression:
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


# ``RelationBinding.projection_id`` phải resolve tới đúng một entry ở đây; một
# projection_id không có adapter là compile error, không phải im lặng SELECT *.
_JOIN_PROJECTIONS: dict[str, Callable[[str, str], list[exp.Expression]]] = {
    "belongs_to": _project_belongs_to,
    "in_platform_category": _project_platform_category,
    "in_shop_category": _project_shop_category,
    "has_sales_metric": _project_star,
}


def _compile_node(
    node: PlanNode,
    compiled: dict[str, exp.Query],
    nodes: dict[str, PlanNode],
    params: list[object],
    rank_state: dict[str, object] | None = None,
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
            query = query.where(_predicate_expression(predicate, source, params))
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
        projection = _JOIN_PROJECTIONS.get(binding.projection_id or "")
        if projection is None:
            raise CompilationError(
                f"Relation {relation.name}: projection_id không resolve adapter: "
                f"{binding.projection_id!r}"
            )
        selections = projection(left_alias, right_alias)
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
    pending = list(plan.nodes)
    while pending:
        progressed = False
        for node in pending[:]:
            if all(parent in compiled for parent in node.inputs):
                compiled[node.node_id] = _compile_node(node, compiled, nodes, params, rank_state)
                pending.remove(node)
                progressed = True
        if not progressed:
            raise CompilationError("Không thể topo-sort plan")
    expression = compiled[plan.output_node]
    _assert_select_only(expression)
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
    )
