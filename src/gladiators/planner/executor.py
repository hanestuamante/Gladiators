"""Hardened in-process DuckDB executor cho SQL chỉ đến từ compiler."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from gladiators.data.coverage import ARTIFACTS

from .compiler import CompiledQuery, assert_read_only_sql


ExecutionIssueCode = Literal[
    "schema_invalid", "cardinality_violation",
    "postcondition_failed", "result_cap_exceeded",
]


class ExecutionIssue(BaseModel):
    """Typed execution failure — ultimate solution §4.10.

    Execution used to fail with a ``RuntimeError`` whose *prefix* carried the
    code ("SCHEMA_INVALID: ..."), which forced anything downstream to parse
    exception text to decide what happened.  §8.2 forbids exactly that.  The
    code is now a closed vocabulary and the numbers live in ``details``, so a
    repair loop can act on the issue and a UI can render a message key without
    ever seeing the raw text.
    """

    model_config = ConfigDict(extra="forbid")
    code: ExecutionIssueCode
    node_id: str | None = None
    message_key: str
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionFailure(RuntimeError):
    """Carries an :class:`ExecutionIssue`; ``str()`` stays UI-safe."""

    def __init__(self, issue: ExecutionIssue, message: str):
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True)
class ExecutionResult:
    frame: pd.DataFrame
    plan_hash: str
    explain: str
    row_count: int
    postconditions: tuple[str, ...]
    # True when the rank limit cut through a run of equal values, i.e. the rows
    # returned are one arbitrary selection among several that tie. Presenting
    # them as "the highest" would answer a different question than the one asked.
    rank_tie_at_cut: bool = False


class QueryExecutor:
    def __init__(self, repository, *, memory_limit: str = "1GB", threads: int = 2, max_result_rows: int = 10_000):
        self.repository = repository
        self.max_result_rows = max_result_rows
        self.connection = duckdb.connect(database=":memory:")
        self.connection.execute(f"SET memory_limit = '{memory_limit}'")
        self.connection.execute(f"SET threads = {int(threads)}")
        self.connection.execute("SET enable_external_access = false")
        self.connection.execute("SET autoload_known_extensions = false")
        self.connection.execute("SET allow_community_extensions = false")
        for artifact in ARTIFACTS:
            view = artifact.removesuffix("_clean.csv").removesuffix(".csv")
            self.connection.register(view, repository.read(artifact))
        self.connection.execute("SET lock_configuration = true")

    def settings(self) -> dict[str, object]:
        names = ("memory_limit", "threads", "enable_external_access", "autoload_known_extensions", "allow_community_extensions", "lock_configuration")
        return {name: self.connection.execute("SELECT current_setting(?)", [name]).fetchone()[0] for name in names}

    def _estimated_rows(self, sql: str, parameters: tuple[object, ...]) -> int | None:
        """Return a conservative plan-cardinality bound, or None if unavailable."""
        try:
            raw = self.connection.execute(
                "EXPLAIN (FORMAT JSON) " + sql, parameters,
            ).fetchone()[-1]
            tree = json.loads(raw)
        except Exception:
            return None
        stack = [tree] if isinstance(tree, dict) else list(tree)
        best: int | None = None
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            card = (node.get("extra_info") or {}).get("Estimated Cardinality")
            try:
                parsed = int(float(card)) if card is not None else None
            except (TypeError, ValueError, OverflowError):
                parsed = None
            if parsed is not None:
                best = parsed if best is None else max(best, parsed)
            stack.extend(node.get("children") or ())
        return best

    def execute(self, query: CompiledQuery) -> ExecutionResult:
        assert_read_only_sql(query.sql)
        estimated = self._estimated_rows(query.sql, query.parameters)
        if estimated is not None and estimated > self.max_result_rows:
            raise ExecutionFailure(
                ExecutionIssue(
                    code="result_cap_exceeded",
                    message_key="execution.estimated_rows_exceeded",
                    details={
                        "estimate": estimated, "max_result_rows": self.max_result_rows,
                    },
                ),
                "Plan ước tính vượt giới hạn số dòng trước khi chạy.",
            )
        explain_rows = self.connection.execute("EXPLAIN " + query.sql, query.parameters).fetchall()
        explain = "\n".join(str(row[-1]) for row in explain_rows)
        frame = self.connection.execute(query.sql, query.parameters).fetchdf()
        rank_tie_at_cut = False
        if query.rank_limit is not None and len(frame) > query.rank_limit:
            column = query.rank_column
            if column in frame.columns:
                boundary = frame.iloc[query.rank_limit - 1][column]
                rank_tie_at_cut = bool(frame.iloc[query.rank_limit][column] == boundary)
            frame = frame.iloc[: query.rank_limit].reset_index(drop=True)
        if not query.ordered and len(frame) > 1:
            # A grouped result with no Rank is a set, and DuckDB returns sets in
            # whatever order its hash table iterated -- observed differing between
            # two processes on identical data. That makes the rendered answer
            # differ run to run, which a system built on content hashes, cassette
            # replay and a pinned evidence lock cannot afford. Imposing a
            # canonical order changes no value, only reproducibility.
            frame = frame.sort_values(
                by=list(frame.columns), kind="mergesort",
            ).reset_index(drop=True)
        if len(frame) > self.max_result_rows:
            raise ExecutionFailure(
                ExecutionIssue(
                    code="result_cap_exceeded", message_key="execution.result_cap_exceeded",
                    details={"rows": len(frame), "max_result_rows": self.max_result_rows},
                ),
                "Kết quả vượt giới hạn số dòng cho phép.",
            )
        if tuple(frame.columns) != query.expected_columns:
            raise ExecutionFailure(
                ExecutionIssue(
                    code="schema_invalid", message_key="execution.schema_invalid",
                    details={
                        "expected": list(query.expected_columns),
                        "actual": list(frame.columns),
                    },
                ),
                "Cột kết quả không khớp output contract của plan.",
            )
        bound = query.expected_cardinality
        exact = not bound.startswith("<=")
        limit = int(bound.removeprefix("<="))
        if (len(frame) != limit) if exact else (len(frame) > limit):
            raise ExecutionFailure(
                ExecutionIssue(
                    code="cardinality_violation", message_key="execution.cardinality_violation",
                    details={"expected": bound, "actual": len(frame)},
                ),
                "Số dòng kết quả không khớp expected_cardinality của plan.",
            )
        passed: list[str] = []
        for invariant in query.postconditions:
            parts = invariant.split(":")
            kind = parts[0]
            if kind == "unique" and len(parts) == 2:
                columns = tuple(filter(None, parts[1].split(",")))
                if not columns or any(column not in frame for column in columns) or frame.duplicated(list(columns)).any():
                    raise ExecutionFailure(
                        ExecutionIssue(
                            code="postcondition_failed",
                            message_key="execution.postcondition_failed",
                            details={"invariant": invariant},
                        ),
                        "Kết quả vi phạm một bất biến đã khai trong plan.",
                    )
            elif kind == "nonnegative" and len(parts) == 2:
                column = parts[1]
                if column not in frame or (frame[column].dropna() < 0).any():
                    raise ExecutionFailure(
                        ExecutionIssue(
                            code="postcondition_failed",
                            message_key="execution.postcondition_failed",
                            details={"invariant": invariant},
                        ),
                        "Kết quả vi phạm một bất biến đã khai trong plan.",
                    )
            elif kind == "range" and len(parts) == 4:
                column, lower, upper = parts[1], float(parts[2]), float(parts[3])
                if column not in frame or not frame[column].dropna().between(lower, upper).all():
                    raise ExecutionFailure(
                        ExecutionIssue(
                            code="postcondition_failed",
                            message_key="execution.postcondition_failed",
                            details={"invariant": invariant},
                        ),
                        "Kết quả vi phạm một bất biến đã khai trong plan.",
                    )
            else:
                raise ExecutionFailure(
                    ExecutionIssue(
                        code="postcondition_failed",
                        message_key="execution.postcondition_unknown",
                        details={"invariant": invariant},
                    ),
                    "Plan khai một bất biến mà executor chưa hỗ trợ.",
                )
            passed.append(invariant)
        return ExecutionResult(
            frame=frame, plan_hash=query.plan_hash, explain=explain,
            row_count=len(frame), postconditions=tuple(passed),
            rank_tie_at_cut=rank_tie_at_cut,
        )

    def close(self) -> None:
        self.connection.close()
