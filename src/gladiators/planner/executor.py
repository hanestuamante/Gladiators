"""Hardened in-process DuckDB executor cho SQL chỉ đến từ compiler."""
from __future__ import annotations

import json
from dataclasses import dataclass

import duckdb
import pandas as pd

from gladiators.data.coverage import ARTIFACTS

from .compiler import CompiledQuery, assert_read_only_sql


@dataclass(frozen=True)
class ExecutionResult:
    frame: pd.DataFrame
    plan_hash: str
    explain: str
    row_count: int
    postconditions: tuple[str, ...]


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
            raise RuntimeError(
                f"ESTIMATED_ROWS_EXCEEDED: estimate={estimated}, "
                f"max_result_rows={self.max_result_rows}"
            )
        explain_rows = self.connection.execute("EXPLAIN " + query.sql, query.parameters).fetchall()
        explain = "\n".join(str(row[-1]) for row in explain_rows)
        frame = self.connection.execute(query.sql, query.parameters).fetchdf()
        if len(frame) > self.max_result_rows:
            raise RuntimeError(f"Kết quả {len(frame)} dòng vượt max_result_rows={self.max_result_rows}")
        if tuple(frame.columns) != query.expected_columns:
            raise RuntimeError(
                f"SCHEMA_INVALID: expected={query.expected_columns}, actual={tuple(frame.columns)}"
            )
        bound = query.expected_cardinality
        exact = not bound.startswith("<=")
        limit = int(bound.removeprefix("<="))
        if (len(frame) != limit) if exact else (len(frame) > limit):
            raise RuntimeError(
                f"CARDINALITY_VIOLATION: expected={bound}, actual={len(frame)}"
            )
        passed: list[str] = []
        for invariant in query.postconditions:
            parts = invariant.split(":")
            kind = parts[0]
            if kind == "unique" and len(parts) == 2:
                columns = tuple(filter(None, parts[1].split(",")))
                if not columns or any(column not in frame for column in columns) or frame.duplicated(list(columns)).any():
                    raise RuntimeError(f"POSTCONDITION_FAILED: {invariant}")
            elif kind == "nonnegative" and len(parts) == 2:
                column = parts[1]
                if column not in frame or (frame[column].dropna() < 0).any():
                    raise RuntimeError(f"POSTCONDITION_FAILED: {invariant}")
            elif kind == "range" and len(parts) == 4:
                column, lower, upper = parts[1], float(parts[2]), float(parts[3])
                if column not in frame or not frame[column].dropna().between(lower, upper).all():
                    raise RuntimeError(f"POSTCONDITION_FAILED: {invariant}")
            else:
                raise RuntimeError(f"POSTCONDITION_UNKNOWN: {invariant}")
            passed.append(invariant)
        return ExecutionResult(
            frame=frame, plan_hash=query.plan_hash, explain=explain,
            row_count=len(frame), postconditions=tuple(passed),
        )

    def close(self) -> None:
        self.connection.close()
