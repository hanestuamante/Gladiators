"""ExecutionPlan envelope — ultimate solution §8.2.

``LogicalQueryPlan`` stays what it is: the contract for *one* SQL plan.  The
temptation was to reuse it for multi-part answers by raising ``subplan_count``,
and §8.1 rules that out for concrete reasons -- the compiler compiles one DAG,
``Join`` does not fuse two arbitrary subqueries, ``side_by_side`` is not a SQL
union, and ``filter_then_measure`` needs a parameter bound from another plan's
result. Pretending otherwise produces a plan that validates and cannot run.

So composition lives one level up, in an envelope:

    ExecutionPlan
      ├── AtomicExecutionPlan          -- one LogicalQueryPlan
      └── DecomposedExecutionPlan      -- 2..4 planned subplans + one CompositionSpec

Two invariants carry the design. **No nesting**: a subplan is always atomic, so
there is no recursion for a validator to get lost in and no way for a
composition to hide inside another. **Every plan pins the same context
snapshot**: a decomposed answer assembled from parts computed against different
dataset versions is wrong in a way nothing in the output would reveal.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .atoms import RequestAtom
from .query_ir import LogicalQueryPlan
from .topic_router import RoutingResult

SCHEMA_VERSION = "execution-plan.v1"
MAX_SUBPLANS = 4
MIN_SUBPLANS = 2

OutputShape = Literal["scalar", "table", "ranking", "comparison", "list"]
ComposeOp = Literal["side_by_side", "union_scope", "join_on_relation", "filter_then_measure"]
PlanningSource = Literal["macro", "template", "synthesizer", "decomposer"]


# --- context snapshot -----------------------------------------------------

class ExecutionContextSnapshot(BaseModel):
    """Every registry version the plan was built against.

    Present so a plan cannot be executed under a different semantic layer than
    it was planned under. Without it, a cached or replayed plan silently adopts
    whatever the registries mean today.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_version: str
    catalog_hash: str
    alias_index_hash: str
    relation_hash: str
    invariant_hash: str
    capability_hash: str
    topic_hash: str
    config_hash: str
    topic_gate_version: str
    decomposition_gate_version: str
    execution_context_hash: str = ""

    @model_validator(mode="after")
    def _seal(self) -> "ExecutionContextSnapshot":
        if self.execution_context_hash:
            return self
        payload = self.model_dump(mode="json")
        payload.pop("execution_context_hash", None)
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:32]
        object.__setattr__(self, "execution_context_hash", digest)
        return self


class ExecutionOutputField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    semantic_ref: str | None = None
    dtype: Literal["string", "integer", "number", "boolean", "date"]
    unit: str
    currency_code: str | None = None
    nullable: bool = False
    # False for anything denominated in a market-local unit: summing VND and IDR
    # produces a number that looks fine and means nothing.
    aggregatable_across_scope: bool = True


# --- issues ---------------------------------------------------------------

IssueCode = Literal[
    "ATOM_COVERAGE_MISMATCH", "UNKNOWN_ATOM", "SUBPLAN_ARITY_INVALID",
    "SUBPLAN_ID_DUPLICATE", "GATE_SIGNATURE_DISABLED",
    "DATASET_SNAPSHOT_MISMATCH", "PLAN_INVALID",
    "OUTPUT_SCHEMA_MISMATCH", "UNIT_MISMATCH", "RELATION_INVALID",
    "CARDINALITY_VIOLATION", "PARTIAL_NOT_ALLOWED",
]
TerminalCode = Literal[
    "DECOMPOSITION_INVALID", "PLAN_INVALID", "COMPOSITION_INVALID",
    "DECOMPOSITION_GATE_DISABLED", "DATASET_VERSION_MISMATCH",
]


class IssueParam(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    value: str | int | float | bool


class PlanningIssue(BaseModel):
    """A typed defect. ``issue_id`` hashes structure, never localized text.

    Nothing may branch on an exception's message: §8.2 requires repair and
    response decisions to read codes, because a message is a translation away
    from breaking every caller that parsed it.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["planning-issue.v1"] = "planning-issue.v1"
    issue_id: str = ""
    category: Literal["decomposition", "atomic_plan", "composition", "execution"]
    code: IssueCode
    path: tuple[str | int, ...] = ()
    message_key: str
    params: tuple[IssueParam, ...] = ()
    repairable: bool = False

    @model_validator(mode="after")
    def _seal(self) -> "PlanningIssue":
        if not self.issue_id:
            payload = json.dumps({
                "category": self.category, "code": self.code,
                "path": [str(p) for p in self.path],
                "params": sorted((p.name, str(p.value)) for p in self.params),
            }, sort_keys=True, ensure_ascii=False)
            object.__setattr__(
                self, "issue_id",
                hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12],
            )
        return self


# Priority registry: when a phase collects several issues, the primary is chosen
# deterministically rather than by whichever check happened to run first.
_ISSUE_PRIORITY: dict[str, int] = {
    "DATASET_SNAPSHOT_MISMATCH": 0,
    "GATE_SIGNATURE_DISABLED": 1,
    "ATOM_COVERAGE_MISMATCH": 2,
    "UNKNOWN_ATOM": 3,
    "SUBPLAN_ARITY_INVALID": 4,
    "SUBPLAN_ID_DUPLICATE": 5,
    "PLAN_INVALID": 6,
    "UNIT_MISMATCH": 7,
    "RELATION_INVALID": 8,
    "CARDINALITY_VIOLATION": 9,
    "OUTPUT_SCHEMA_MISMATCH": 10,
    "PARTIAL_NOT_ALLOWED": 11,
}


class PlanningFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    terminal_code: TerminalCode
    primary_issue_id: str
    issues: tuple[PlanningIssue, ...]

    @classmethod
    def from_issues(
        cls, terminal_code: TerminalCode, issues: tuple[PlanningIssue, ...]
    ) -> "PlanningFailure":
        if not issues:
            raise ValueError("PlanningFailure cần ít nhất một issue")
        primary = min(issues, key=lambda i: (_ISSUE_PRIORITY.get(i.code, 99), i.issue_id))
        return cls(
            terminal_code=terminal_code, primary_issue_id=primary.issue_id, issues=issues,
        )


class PlanningError(RuntimeError):
    """Carries a PlanningFailure. The message is for humans only."""

    def __init__(self, failure: PlanningFailure, message: str = ""):
        super().__init__(message or failure.terminal_code)
        self.failure = failure


# --- composition proposals (what a model may suggest) ---------------------

class SubrequestProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subplan_id: str
    request: Any
    covered_atom_ids: tuple[str, ...]
    shared_atom_ids: tuple[str, ...] = ()


class DeferredPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    consumer_node_id: str
    ref: str
    op: Literal["in"] = "in"
    source_subplan_id: str
    source_field_ref: str
    # Bounded so a producer returning a huge key set cannot turn a deferred
    # predicate into an unbounded IN list at execution time.
    max_values: int = Field(default=500, ge=1, le=500)


class SideBySideProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["side_by_side"] = "side_by_side"
    input_subplan_ids: tuple[str, ...] = Field(min_length=MIN_SUBPLANS, max_length=MAX_SUBPLANS)


class UnionScopeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["union_scope"] = "union_scope"
    input_subplan_ids: tuple[str, ...] = Field(min_length=MIN_SUBPLANS, max_length=MAX_SUBPLANS)
    scope_ref: str


class JoinOnRelationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["join_on_relation"] = "join_on_relation"
    left_subplan_id: str
    right_subplan_id: str
    relation_id: str


class FilterThenMeasureProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["filter_then_measure"] = "filter_then_measure"
    producer_subplan_id: str
    consumer_subplan_id: str
    filter_ref: str


CompositionProposal = Annotated[
    SideBySideProposal | UnionScopeProposal
    | JoinOnRelationProposal | FilterThenMeasureProposal,
    Field(discriminator="op"),
]


class DecompositionProposal(BaseModel):
    """What a model is allowed to propose -- and nothing more.

    ``request_hash``, ``digest_hash`` and ``request_atoms`` are wrapped by the
    caller from trusted root state (§8.2). A model repeating a trusted field is
    rejected rather than used to overwrite it: a proposal that can restate the
    request can quietly restate it into an easier one.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["decomposition-proposal.v1"] = "decomposition-proposal.v1"
    request_hash: str
    digest_hash: str
    request_atoms: tuple[RequestAtom, ...]
    subrequests: tuple[SubrequestProposal, ...] = Field(
        min_length=MIN_SUBPLANS, max_length=MAX_SUBPLANS
    )
    composition: CompositionProposal


# --- composition specs (what the planner produced) ------------------------

class CompositeOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    presentation: Literal["single_frame", "sections"]
    output_shape_kind: OutputShape
    output_grain: str
    fields: tuple[ExecutionOutputField, ...] = ()
    expected_cardinality: str

    @model_validator(mode="after")
    def _single_frame_needs_fields(self) -> "CompositeOutputContract":
        # "sections" takes its schema from each section's subplan; a shared
        # schema would have to be invented, and an invented schema is a claim.
        if self.presentation == "single_frame" and not self.fields:
            raise ValueError("single_frame bắt buộc có fields")
        return self


class SectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    section_id: str
    title_key: str
    subplan_id: str
    order: int


class SideBySideSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["side_by_side"] = "side_by_side"
    sections: tuple[SectionSpec, ...] = Field(min_length=MIN_SUBPLANS, max_length=MAX_SUBPLANS)
    output_contract: CompositeOutputContract


class ScopePartition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subplan_id: str
    scope_values: tuple[str, ...]


class UnionScopeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["union_scope"] = "union_scope"
    scope_ref: str
    partitions: tuple[ScopePartition, ...] = Field(min_length=MIN_SUBPLANS, max_length=MAX_SUBPLANS)
    dedupe_policy_id: str
    # Defaults false: aggregating after a scope union is how two markets get
    # averaged into one meaningless number.
    allow_post_union_aggregate: bool = False
    output_contract: CompositeOutputContract

    @model_validator(mode="after")
    def _partitions_are_disjoint(self) -> "UnionScopeSpec":
        seen: set[str] = set()
        for partition in self.partitions:
            overlap = seen & set(partition.scope_values)
            if overlap:
                raise ValueError(f"scope partition chồng lấn: {sorted(overlap)}")
            seen |= set(partition.scope_values)
        return self


class JoinOnRelationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["join_on_relation"] = "join_on_relation"
    left_subplan_id: str
    right_subplan_id: str
    relation_id: str
    join_key_refs: tuple[str, ...]
    join_type: Literal["inner", "left"]
    null_policy: Literal["drop_unmatched", "preserve_left"]
    dedupe_policy_id: str | None = None
    output_contract: CompositeOutputContract


class FilterThenMeasureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["filter_then_measure"] = "filter_then_measure"
    producer_subplan_id: str
    consumer_subplan_id: str
    deferred_predicate: DeferredPredicate
    output_contract: CompositeOutputContract


CompositionSpec = Annotated[
    SideBySideSpec | UnionScopeSpec | JoinOnRelationSpec | FilterThenMeasureSpec,
    Field(discriminator="op"),
]


# --- execution plans ------------------------------------------------------

class PlannedSubplanSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subplan_id: str
    request: Any
    covered_atom_ids: tuple[str, ...]
    shared_atom_ids: tuple[str, ...] = ()
    subrequest_digest_hash: str
    routing: RoutingResult
    context_hash: str
    topic_gate_version: str
    dataset_version: str
    plan: LogicalQueryPlan
    plan_hash: str
    output_fields: tuple[ExecutionOutputField, ...]

    @model_validator(mode="after")
    def _subplan_is_atomic(self) -> "PlannedSubplanSpec":
        if self.plan.subplan_count != 1:
            raise ValueError("subplan phải atomic: subplan_count == 1")
        if not self.output_fields:
            raise ValueError("subplan phải khai báo output_fields")
        return self


class AtomicExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["execution-plan.v1"] = SCHEMA_VERSION
    kind: Literal["atomic"] = "atomic"
    execution_plan_id: str
    request_hash: str
    digest_hash: str
    capability_id: str
    context_snapshot: ExecutionContextSnapshot
    request_atom_ids: tuple[str, ...]
    output_shape_kind: OutputShape
    output_fields: tuple[ExecutionOutputField, ...]
    planning_source: PlanningSource
    routing: RoutingResult | None = None
    context_hash: str | None = None
    plan: LogicalQueryPlan

    @model_validator(mode="after")
    def _check(self) -> "AtomicExecutionPlan":
        if not self.output_fields:
            raise ValueError("atomic plan phải có output_fields")
        if self.plan.subplan_count != 1:
            raise ValueError("atomic plan phải có subplan_count == 1")
        # A decomposer-built plan without routing provenance cannot be audited
        # for which slice of the catalogue it was allowed to see.
        if self.planning_source == "decomposer" and (
            self.routing is None or not self.context_hash
        ):
            raise ValueError("planning_source=decomposer cần routing và context_hash")
        return self


class DecomposedExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["execution-plan.v1"] = SCHEMA_VERSION
    kind: Literal["decomposed"] = "decomposed"
    execution_plan_id: str
    request_hash: str
    digest_hash: str
    capability_id: str
    context_snapshot: ExecutionContextSnapshot
    request_atoms: tuple[RequestAtom, ...]
    output_shape_kind: OutputShape
    root_routing: RoutingResult
    decomposition_proposal_hash: str
    subplans: tuple[PlannedSubplanSpec, ...] = Field(
        min_length=MIN_SUBPLANS, max_length=MAX_SUBPLANS
    )
    composition: CompositionSpec
    partial_policy: Literal["all_or_nothing", "explicit_partial"] = "all_or_nothing"

    @model_validator(mode="after")
    def _check(self) -> "DecomposedExecutionPlan":
        ids = [sub.subplan_id for sub in self.subplans]
        if len(ids) != len(set(ids)):
            raise ValueError("subplan_id trùng")

        # All parts must be computed against one dataset version. A composed
        # answer assembled across versions is wrong in a way the output cannot
        # show.
        pinned = self.context_snapshot.dataset_version
        mismatched = [s.subplan_id for s in self.subplans if s.dataset_version != pinned]
        if mismatched:
            raise ValueError(f"subplan lệch dataset version: {sorted(mismatched)}")

        referenced = _composition_subplan_ids(self.composition)
        unknown = referenced - set(ids)
        if unknown:
            raise ValueError(f"composition trỏ tới subplan không tồn tại: {sorted(unknown)}")
        return self


ExecutionPlan = Annotated[
    AtomicExecutionPlan | DecomposedExecutionPlan, Field(discriminator="kind")
]


def _composition_subplan_ids(composition) -> set[str]:
    if isinstance(composition, SideBySideSpec):
        return {section.subplan_id for section in composition.sections}
    if isinstance(composition, UnionScopeSpec):
        return {partition.subplan_id for partition in composition.partitions}
    if isinstance(composition, JoinOnRelationSpec):
        return {composition.left_subplan_id, composition.right_subplan_id}
    if isinstance(composition, FilterThenMeasureSpec):
        return {composition.producer_subplan_id, composition.consumer_subplan_id}
    return set()


def composition_arity(composition) -> int:
    return len(_composition_subplan_ids(composition))
