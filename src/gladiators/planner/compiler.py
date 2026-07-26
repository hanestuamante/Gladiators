"""SQLGlot AST compiler cho LogicalQueryPlan IR v1.0.

Không nhận raw SQL và không nội suy user values. Mọi identifier đến từ source
allow-list, semantic catalog hoặc relation registry; values trở thành ``?``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import RELATIONS

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


_VIEW_NAMES = {
    "products_clean.csv": "products",
    "shop_info_clean.csv": "shop_info",
    "category_list_clean.csv": "category_list",
    "product_categories_clean.csv": "product_categories",
    "category_platform_clean.csv": "category_platform",
    "product_snapshot_metrics.csv": "product_snapshot_metrics",
    "product_transition_metrics.csv": "product_transition_metrics",
}
_RIGHT_VIEW = {
    "belongs_to": "shop_info", "in_platform_category": "category_platform",
    "in_shop_category": "category_list", "has_sales_metric": "product_snapshot_metrics",
}
_INLINE_RELATIONS = {
    "observed_at", "has_brand", "observed_promotion_id",
    "observed_structured_voucher", "has_content", "has_display_variation",
}
_PHYSICAL_JOIN_KEYS = {
    "belongs_to": (("country_code", "country_code"), ("shop_id", "shop_id")),
    "in_platform_category": (("country_code", "country_code"), ("catid_num", "category_id_num")),
    "in_shop_category": (
        ("country_code", "country_code"), ("shop_id", "shop_id"),
        ("category_id_num", "shop_category_id_num"), ("date", "date"),
    ),
    "has_sales_metric": (("product_listing_key", "product_listing_key"),),
}
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
    if ref == "derived.product_count":
        return "product_listing_key"
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


def _compile_node(
    node: PlanNode,
    compiled: dict[str, exp.Query],
    nodes: dict[str, PlanNode],
    params: list[object],
) -> exp.Query:
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
            if ref == "derived.product_count":
                aggregate = exp.Count(this=exp.column(column), distinct=True)
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
        return _from_input(inputs[0], f"q_{node.node_id}").order_by(exp.Ordered(this=exp.column(column), desc=node.descending)).limit(node.limit)
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
        if relation.name in _INLINE_RELATIONS:
            return _from_input(inputs[0], f"q_{node.node_id}")
        right_view = _RIGHT_VIEW.get(relation.name)
        if right_view is None:
            raise CompilationError(f"Relation {relation.name} chưa có SQL join adapter")
        left_alias, right_alias = "l", "r"
        conditions = [
            exp.EQ(this=exp.column(left, table=left_alias), expression=exp.column(right, table=right_alias))
            for left, right in _PHYSICAL_JOIN_KEYS.get(relation.name, relation.join_keys)
        ]
        on = conditions[0]
        for condition in conditions[1:]:
            on = exp.and_(on, condition)
        if relation.name == "belongs_to":
            selections = [
                exp.column("product_listing_key", table=left_alias),
                exp.column("country_code", table=left_alias),
                exp.column("shop_id", table=left_alias),
                exp.column("item_id", table=left_alias),
                exp.column("date", table=left_alias),
                exp.alias_(exp.column("shop_name", table=right_alias), "shop_name", quoted=True),
            ]
        elif relation.name == "in_platform_category":
            selections = [
                exp.Column(this=exp.Star(), table=exp.Identifier(this=left_alias)),
                exp.alias_(exp.column("display_category_name", table=right_alias), "display_category_name", quoted=True),
                exp.alias_(exp.column("has_children_bool", table=right_alias), "has_children_bool", quoted=True),
            ]
        elif relation.name == "in_shop_category":
            selections = [
                exp.Column(this=exp.Star(), table=exp.Identifier(this=left_alias)),
                exp.alias_(exp.column("display_name", table=right_alias), "display_name", quoted=True),
                exp.alias_(exp.column("total_num", table=right_alias), "total_num", quoted=True),
                exp.alias_(exp.column("is_parent_category_bool", table=right_alias), "is_parent_category_bool", quoted=True),
                exp.alias_(exp.column("is_sub_category_bool", table=right_alias), "is_sub_category_bool", quoted=True),
            ]
        else:
            selections = [
                exp.Column(this=exp.Star(), table=exp.Identifier(this=left_alias)),
                exp.Column(this=exp.Star(), table=exp.Identifier(this=right_alias)),
            ]
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
    pending = list(plan.nodes)
    while pending:
        progressed = False
        for node in pending[:]:
            if all(parent in compiled for parent in node.inputs):
                compiled[node.node_id] = _compile_node(node, compiled, nodes, params)
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
    )
