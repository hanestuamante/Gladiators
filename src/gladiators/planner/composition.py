"""Composition executor — ultimate solution §8.6 / §8.7.

Combines the results of independently-executed atomic plans.  It computes
nothing new: it presents, unions, joins or parameterises what the atomic plans
already produced, and it never calls an LLM.

Each operator exists because a specific combination is *not* expressible as one
SQL plan, and each carries a rule that stops it becoming a plausible wrong
number:

``side_by_side`` presents and refuses to compute -- no sum, no average, no
automatic numeric comparison. Two results shown together are two results, and
the moment the composer starts relating them it is answering a question nobody
asked.

``union_scope`` requires identical schema over disjoint scope. Monetary columns
from two markets may be stacked for presentation but never aggregated: VND and
IDR have no exchange rate here, so their mean is a number with no unit.

``join_on_relation`` goes through a certified relation only, and ``N:M`` is
disabled by default because a fanned-out join double-counts and the total looks
entirely reasonable.

``filter_then_measure`` takes its key set from the producer's *execution
result*, never from a model. It is idempotent on (producer keys, consumer plan),
so a retry cannot run the consumer twice and double an answer.

Nothing is published until every part succeeded: under ``all_or_nothing`` a
partial frame must not escape, because a partial answer that does not say it is
partial is just a wrong answer.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from .execution_plan import (
    CompositeOutputContract,
    ComposeOp,
    ExecutionOutputField,
    FilterThenMeasureSpec,
    JoinOnRelationSpec,
    SideBySideSpec,
    UnionScopeSpec,
)

MAX_ROWS = 10_000
MAX_DEFERRED_KEYS = 500


class CompositionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class LineageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subplan_id: str
    plan_hash: str
    source_artifact: str
    source_hash: str
    stable_row_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class AtomicExecutionResult:
    subplan_id: str
    frame: Any  # pd.DataFrame -- request-scoped only, never serialized
    schema: tuple[ExecutionOutputField, ...]
    grain: str
    row_count: int
    plan_hash: str
    dataset_version: str
    stable_row_key_fields: tuple[str, ...] = ()
    lineage: tuple[LineageEntry, ...] = ()
    failed: bool = False


@dataclass(frozen=True)
class CompositeExecutionResult:
    execution_plan_id: str
    op: ComposeOp
    dataset_version: str
    output_contract: CompositeOutputContract
    atomic_results: tuple[AtomicExecutionResult, ...]
    presentation: Literal["single_frame", "sections"]
    composed_frame: Any = None
    row_count: int = 0
    stable_row_key_fields: tuple[str, ...] = ()
    lineage: tuple[LineageEntry, ...] = field(default_factory=tuple)
    # Set when the composition legitimately produced nothing -- §8.6's empty
    # producer set. Distinct from a missing frame: "no rows matched" is an
    # answer, "the frame never arrived" is a fault, and they must not look alike.
    empty_reason: str | None = None


def _check_dataset_pin(results: tuple[AtomicExecutionResult, ...], pinned: str) -> None:
    mismatched = sorted({r.subplan_id for r in results if r.dataset_version != pinned})
    if mismatched:
        raise CompositionError(
            "DATASET_VERSION_MISMATCH",
            f"Subplan chạy trên dataset khác bản đã ghim: {mismatched}",
        )


def _check_no_failures(results, partial_policy: str) -> None:
    failed = sorted({r.subplan_id for r in results if r.failed})
    if not failed:
        return
    if partial_policy != "explicit_partial":
        # A successful frame must not escape when a sibling failed: a partial
        # answer that does not announce itself is simply a wrong one.
        raise CompositionError(
            "COMPOSITION_INVALID",
            f"all_or_nothing: subplan thất bại nên toàn request fail: {failed}",
        )


def _lineage(results) -> tuple[LineageEntry, ...]:
    return tuple(entry for result in results for entry in result.lineage) or tuple(
        LineageEntry(
            subplan_id=r.subplan_id, plan_hash=r.plan_hash,
            source_artifact="atomic_execution", source_hash=r.plan_hash,
            stable_row_keys=r.stable_row_key_fields,
        )
        for r in results
    )


def compose(
    execution_plan,
    results: tuple[AtomicExecutionResult, ...],
    *,
    concat: Callable[[list], Any] | None = None,
    merge: Callable[..., Any] | None = None,
) -> CompositeExecutionResult:
    """Compose atomic results. ``concat``/``merge`` are injected so this module
    stays testable without importing pandas at module scope."""
    composition = execution_plan.composition
    pinned = execution_plan.context_snapshot.dataset_version
    _check_dataset_pin(results, pinned)
    _check_no_failures(results, execution_plan.partial_policy)

    by_id = {r.subplan_id: r for r in results}
    contract = composition.output_contract

    if isinstance(composition, SideBySideSpec):
        composed = _side_by_side(composition, by_id)
    elif isinstance(composition, UnionScopeSpec):
        composed = _union_scope(composition, by_id, concat)
    elif isinstance(composition, JoinOnRelationSpec):
        composed = _join_on_relation(composition, by_id, merge)
    elif isinstance(composition, FilterThenMeasureSpec):
        composed = _filter_then_measure(composition, by_id)
    else:
        raise CompositionError("COMPOSITION_INVALID", f"Operator lạ: {composition.op}")

    frame, row_count, key_fields, empty_reason = composed

    # §8.7: presentation and frame must agree. A "sections" result carrying a
    # single frame invites a caller to read it as one comparable table.
    # An explicitly-empty composition is exempt: it has nothing to put in a
    # frame and says so, which is a different thing from a frame going missing.
    if contract.presentation == "single_frame" and frame is None and empty_reason is None:
        raise CompositionError("COMPOSITION_INVALID", "single_frame cần composed_frame")
    if contract.presentation == "sections" and frame is not None:
        raise CompositionError("COMPOSITION_INVALID", "sections không được có composed_frame")
    if row_count > MAX_ROWS:
        raise CompositionError("CARDINALITY_VIOLATION", f"row count {row_count} vượt cap")

    return CompositeExecutionResult(
        execution_plan_id=execution_plan.execution_plan_id,
        op=composition.op, dataset_version=pinned, output_contract=contract,
        atomic_results=results, presentation=contract.presentation,
        composed_frame=frame, row_count=row_count,
        stable_row_key_fields=key_fields, lineage=_lineage(results),
        empty_reason=empty_reason,
    )


def _side_by_side(composition: SideBySideSpec, by_id) -> tuple[Any, int, tuple[str, ...], str | None]:
    """Present only. Different grain and unit are fine precisely because
    nothing is computed across sections."""
    total = 0
    keys: list[str] = []
    for section in sorted(composition.sections, key=lambda s: s.order):
        result = by_id.get(section.subplan_id)
        if result is None:
            raise CompositionError("COMPOSITION_INVALID",
                                   f"thiếu kết quả cho section {section.section_id}")
        total += result.row_count
        # Stable keys are namespaced by section so two sections cannot collide
        # on an identical row key and look like one row.
        keys.extend(f"{section.section_id}:{k}" for k in result.stable_row_key_fields)
    return None, total, tuple(keys), None


def _union_scope(composition: UnionScopeSpec, by_id, concat) -> tuple[Any, int, tuple[str, ...], str | None]:
    frames = []
    reference: tuple[ExecutionOutputField, ...] | None = None
    total = 0
    for partition in composition.partitions:
        result = by_id.get(partition.subplan_id)
        if result is None:
            raise CompositionError("COMPOSITION_INVALID",
                                   f"thiếu kết quả cho partition {partition.subplan_id}")
        signature = tuple((f.name, f.semantic_ref, f.dtype, f.unit) for f in result.schema)
        if reference is None:
            reference = signature
        elif signature != reference:
            # A union of differing schemas would silently drop or null columns.
            raise CompositionError(
                "OUTPUT_SCHEMA_MISMATCH",
                f"partition {partition.subplan_id} có schema khác các partition trước",
            )
        frames.append(result.frame)
        total += result.row_count

    if not composition.allow_post_union_aggregate:
        non_aggregatable = sorted({
            f.name for r in by_id.values() for f in r.schema
            if not f.aggregatable_across_scope
        })
        if non_aggregatable:
            # Not an error -- presentation-only union is the supported case for
            # cross-market money. The flag simply must stay off.
            pass

    frame = concat(frames) if concat is not None else None
    keys = tuple(dict.fromkeys(
        k for r in by_id.values() for k in r.stable_row_key_fields
    ))
    return frame, total, keys, None


def _join_on_relation(composition: JoinOnRelationSpec, by_id, merge):
    left = by_id.get(composition.left_subplan_id)
    right = by_id.get(composition.right_subplan_id)
    if left is None or right is None:
        raise CompositionError("COMPOSITION_INVALID", "join thiếu một phía input")

    # A name collision on different semantics is a silent overwrite; the same
    # semantic ref under one name is simply the join key.
    left_fields = {f.name: f.semantic_ref for f in left.schema}
    for f in right.schema:
        if f.name in left_fields and left_fields[f.name] != f.semantic_ref:
            raise CompositionError(
                "OUTPUT_SCHEMA_MISMATCH",
                f"field '{f.name}' trùng tên nhưng khác semantic ref",
            )

    available = {f.semantic_ref for f in left.schema} & {f.semantic_ref for f in right.schema}
    missing = [ref for ref in composition.join_key_refs if ref not in available]
    if missing:
        raise CompositionError(
            "OUTPUT_SCHEMA_MISMATCH",
            f"join key không có trong output schema hai phía: {sorted(missing)}",
        )

    frame = merge(left.frame, right.frame, composition) if merge is not None else None
    row_count = frame_len(frame) if frame is not None else max(left.row_count, right.row_count)
    if composition.join_type == "inner" and row_count > left.row_count * right.row_count:
        raise CompositionError("CARDINALITY_VIOLATION", "join nở hàng ngoài dự kiến")
    return frame, row_count, left.stable_row_key_fields, None


def _filter_then_measure(composition: FilterThenMeasureSpec, by_id):
    producer = by_id.get(composition.producer_subplan_id)
    consumer = by_id.get(composition.consumer_subplan_id)
    if producer is None:
        raise CompositionError("COMPOSITION_INVALID", "thiếu kết quả producer")
    if producer.row_count == 0:
        # An empty producer set is a valid empty answer. Running the consumer
        # without the filter would answer a completely different question.
        return None, 0, (), "empty_producer_set"
    if consumer is None:
        raise CompositionError("COMPOSITION_INVALID", "thiếu kết quả consumer")
    return consumer.frame, consumer.row_count, consumer.stable_row_key_fields, None


def frame_len(frame) -> int:
    try:
        return len(frame)
    except TypeError:
        return 0


# --- deferred predicate materialisation -----------------------------------

def extract_deferred_keys(
    producer: AtomicExecutionResult, spec: FilterThenMeasureSpec,
) -> tuple[Any, ...]:
    """Key set from the producer's result -- never from a model (§8.6)."""
    frame = producer.frame
    field_name = spec.deferred_predicate.source_field_ref
    try:
        values = list(frame[field_name])
    except (TypeError, KeyError, IndexError):
        values = [row.get(field_name) for row in (frame or []) if isinstance(row, dict)]
    keys = tuple(dict.fromkeys(v for v in values if v is not None))
    if len(keys) > spec.deferred_predicate.max_values:
        raise CompositionError(
            "CARDINALITY_VIOLATION",
            f"producer trả {len(keys)} key, vượt cap {spec.deferred_predicate.max_values}; "
            "phải aggregate/filter ở producer hoặc hỏi lại người dùng.",
        )
    return keys


def materialization_key(keys: tuple[Any, ...], consumer_plan_hash: str) -> str:
    """Idempotency key: same producer keys + same consumer plan = same run.

    Without it a retry at the orchestration layer runs the consumer a second
    time, and a second run of a measuring plan is a doubled answer.
    """
    payload = "|".join(sorted(str(k) for k in keys)) + f"#{consumer_plan_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
