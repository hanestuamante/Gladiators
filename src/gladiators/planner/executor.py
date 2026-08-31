"""Hardened in-process DuckDB executor cho SQL chỉ đến từ compiler."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from gladiators.data.coverage import ARTIFACTS
from gladiators.domain.tables import VIEW_NAMES

from .compiler import RANK_KEY_ALIAS, CompiledQuery, assert_read_only_sql


ExecutionIssueCode = Literal[
    "schema_invalid", "cardinality_violation",
    "postcondition_failed", "result_cap_exceeded",
    # Tách khỏi result_cap_exceeded: kết quả quá lớn và trung gian nở quá
    # rộng là hai vấn đề khác nhau, và gộp mã sẽ làm chúng đọc như một.
    "fanout_cap_exceeded",
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


# W30-R3: cận số dòng khai bằng KÝ HIỆU trên lịch, không bằng một con số của
# một bản dữ liệu. ``"<=3341"`` đúng trên bộ 3 ngày và sai trên bộ 20 ngày —
# nhưng nó sai theo kiểu fail-closed, nên nguyên nhân bị nói sai ("plan sai hợp
# đồng") thay vì nói đúng ("cận viết cho một bản dữ liệu khác").
CARDINALITY_SYMBOLS = ("snapshot_rows", "listings", "snapshots")


def _symbol_value(symbol: str) -> int | None:
    from gladiators.domain.calendar import default_calendar

    calendar = default_calendar()
    return {
        "snapshot_rows": calendar.row_count,
        "listings": calendar.listing_count,
        "snapshots": len(calendar.dates),
    }.get(symbol)


def _declared_cardinality(expected: str | None) -> tuple[int | None, bool]:
    """``"1"`` → ``(1, False)``, ``"<=snapshot_rows"`` → ``(22695, True)``.

    Trả kèm cờ **cận theo cỡ dữ liệu**. Hai loại cận này khác nhau về chất và
    trước đây bị trộn làm một:

    * cận SỐ (``1``, ``<=50``) nói *truy vấn này trả về nhiều nhất chừng ấy
      dòng* — một phát biểu về hình dạng KẾT QUẢ;
    * cận KÝ HIỆU (``snapshot_rows``, ``listing_count``) nói *nhiều nhất là
      toàn bộ dữ liệu* — một phát biểu về cỡ BẢN DỮ LIỆU, tức không hứa gì về
      kết quả.

    Trộn hai thứ làm cửa ``max_result_rows`` bắn theo cỡ dataset: câu "bao nhiêu
    listing của thương hiệu Bibica tại VN ngày 03/07" khai ``<=snapshot_rows``,
    ăn 3 341 trên bộ cũ (lọt) và 22 695 trên bộ 20 ngày (chặn) — trong khi kết
    quả thật là 4 113 dòng ở cả hai. Cửa đổi phán quyết vì DỮ LIỆU to ra, không
    vì truy vấn xấu đi, và lời từ chối nói sai nguyên nhân.

    Thứ khác → ``(None, False)`` (không khai được cận, lùi về ước tính DuckDB).
    """
    if not expected:
        return None, False
    text = expected.strip()
    if text.startswith("<="):
        text = text[2:].strip()
    if text in CARDINALITY_SYMBOLS:
        return _symbol_value(text), True
    try:
        return int(text), False
    except ValueError:
        return None, False


class QueryExecutor:
    # Bội số cho phép giữa số dòng trung gian rộng nhất và bảng lớn nhất của
    # chính bản dữ liệu. Đây là một NGƯỠNG ĐƯỢC CHỌN, không phải một số đo: nó
    # nói "một phép nối hợp lệ trong registry không nhân dữ liệu lên quá chừng
    # này". Đặt theo dữ liệu chứ không theo hằng số tuyệt đối, vì một hằng số
    # tuyệt đối sẽ lại đúng ở bộ 3 341 dòng và sai ở bộ 22 695 dòng — đúng cách
    # guard cũ hỏng.
    FANOUT_ALLOWANCE = 8

    def __init__(self, repository, *, memory_limit: str = "1GB", threads: int = 2,
                 max_result_rows: int = 10_000, max_intermediate_rows: int | None = None):
        self.repository = repository
        self.max_result_rows = max_result_rows
        available = set(repository.available_artifacts())
        self.available_artifacts = tuple(a for a in ARTIFACTS if a in available)
        self.connection = duckdb.connect(database=":memory:")
        self.connection.execute(f"SET memory_limit = '{memory_limit}'")
        self.connection.execute(f"SET threads = {int(threads)}")
        self.connection.execute("SET enable_external_access = false")
        self.connection.execute("SET autoload_known_extensions = false")
        self.connection.execute("SET allow_community_extensions = false")
        # View name đến từ TableRegistry, không suy từ tên file: một artifact đổi
        # tên file mà quên đổi view sẽ tạo view lạ thay vì fail.
        for artifact in ARTIFACTS:
            # Artifact tuỳ chọn chưa thu ⇒ KHÔNG đăng ký view. Đăng ký một frame
            # rỗng thay thế sẽ khiến mọi truy vấn lên nó trả "0 dòng" — tức
            # "đo được và không có gì", đúng thứ CLAUDE.md §3.1 cấm.
            if artifact not in available:
                continue
            self.connection.register(VIEW_NAMES[artifact], repository.read(artifact))
        self.connection.execute("SET lock_configuration = true")
        largest = max(
            (len(repository.read(artifact)) for artifact in self.available_artifacts),
            default=0,
        )
        self.max_intermediate_rows = (
            max_intermediate_rows if max_intermediate_rows is not None
            else max(largest * self.FANOUT_ALLOWANCE, max_result_rows)
        )

    def settings(self) -> dict[str, object]:
        names = ("memory_limit", "threads", "enable_external_access", "autoload_known_extensions", "allow_community_extensions", "lock_configuration")
        return {name: self.connection.execute("SELECT current_setting(?)", [name]).fetchone()[0] for name in names}

    def _estimated_rows(self, sql: str, parameters: tuple[object, ...]) -> tuple[int | None, int | None]:
        """``(số dòng KẾT QUẢ ước tính, cardinality LỚN NHẤT ở node bất kỳ)``.

        Trước đây hàm này trả đúng một số — max trên MỌI node — và
        ``max_result_rows`` so với nó. Hai đại lượng đó khác nhau: với
        "listing giá cao nhất tại VN", root ước tính 2 dòng còn ``PANDAS_SCAN``
        ước tính 3 341. Trên bộ 3 341 dòng khoảng cách đó nằm dưới ngưỡng nên
        guard chưa bao giờ bắn; trên bộ 22 695 dòng thì MỌI truy vấn bị chặn dù
        trả về một dòng — tức một guard chưa từng được thử, đúng lúc dữ liệu lớn
        lên mới lộ ra là nó đo nhầm thứ.

        Trả cả hai để người gọi so từng cái với đúng giới hạn của nó, thay vì
        gộp hai rủi ro khác nhau vào một con số.
        """
        try:
            raw = self.connection.execute(
                "EXPLAIN (FORMAT JSON) " + sql, parameters,
            ).fetchone()[-1]
            tree = json.loads(raw)
        except Exception:
            return None, None

        def cardinality(node: dict) -> int | None:
            card = (node.get("extra_info") or {}).get("Estimated Cardinality")
            try:
                return int(float(card)) if card is not None else None
            except (TypeError, ValueError, OverflowError):
                return None

        root = tree if isinstance(tree, dict) else (tree[0] if tree else None)
        if root is None:
            return None, None
        stack = [root]
        widest: int | None = None
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            parsed = cardinality(node)
            if parsed is not None:
                widest = parsed if widest is None else max(widest, parsed)
            stack.extend(node.get("children") or ())
        # Root không khai cardinality (vd. TOP_N) ⇒ lùi về ước tính rộng nhất.
        # Không biết thì phải chọn phía thận trọng, chứ không phải bỏ kiểm.
        return (cardinality(root) if cardinality(root) is not None else widest), widest

    def execute(self, query: CompiledQuery) -> ExecutionResult:
        assert_read_only_sql(query.sql)
        estimated, widest = self._estimated_rows(query.sql, query.parameters)
        # Hợp đồng của chính plan (``expected_cardinality``) thắng ước tính của
        # DuckDB khi nó khai được một cận: ước tính đó đo được là SAI cho
        # aggregate không group_by — DuckDB trả cardinality đầu vào (22 695)
        # cho một truy vấn trả về đúng 1 dòng. Cận do plan khai không phải lời
        # hứa suông: postcondition kiểm lại nó SAU khi chạy, nên plan khai sai
        # vẫn bị chặn, chỉ là chặn ở chỗ nói đúng nguyên nhân hơn.
        declared, dataset_scale = _declared_cardinality(query.expected_cardinality)
        if declared is not None:
            # Cận theo cỡ DỮ LIỆU không nói gì về kết quả, nên nó chỉ được dùng
            # cho cửa trung gian; cửa kết quả giữ ước tính của DuckDB, thứ thật
            # sự nói về số dòng trả ra.
            if dataset_scale:
                widest = declared if widest is None else max(widest, declared)
            else:
                estimated = declared
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
        if widest is not None and widest > self.max_intermediate_rows:
            raise ExecutionFailure(
                ExecutionIssue(
                    code="fanout_cap_exceeded",
                    message_key="execution.estimated_intermediate_rows_exceeded",
                    details={
                        "estimate": widest,
                        "max_intermediate_rows": self.max_intermediate_rows,
                    },
                ),
                "Plan nở ra nhiều dòng trung gian hơn mức một phép nối hợp lệ "
                "có thể tạo ra trên bản dữ liệu này.",
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
            if RANK_KEY_ALIAS in frame.columns and RANK_KEY_ALIAS not in query.expected_columns:
                # W13.2: cột kỹ thuật, không thuộc hợp đồng. Bỏ SAU tie
                # detection — bỏ trước là lấy đi đúng thứ vừa được mang theo để
                # phát hiện hoà, và thứ tự này là bắt buộc chứ không phải sở
                # thích: tie detection đọc frame[rank_column], mà rank_column
                # giờ chính là RANK_KEY_ALIAS.
                frame = frame.drop(columns=[RANK_KEY_ALIAS])
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
        # MỘT bộ phân giải cận, không hai: chỗ này từng tự gọi ``int()`` và nó
        # nổ ngay khi cận mang ký hiệu lịch (W30-R3). Hai bản của một luật là
        # cách chúng lệch nhau — đây là lần lệch thứ nhất, bắt được vì nó nổ
        # thay vì âm thầm chấp nhận.
        limit, _ = _declared_cardinality(bound)
        if limit is None:
            raise ExecutionFailure(
                ExecutionIssue(
                    code="schema_invalid", message_key="execution.schema_invalid",
                    details={"expected_cardinality": bound},
                ),
                "expected_cardinality của plan không phân giải được thành một cận.",
            )
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
