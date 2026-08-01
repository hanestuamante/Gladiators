"""Insight API — ultimate solution §12.4.

Five read-only endpoints over one pinned bundle.  Three response rules carry the
contract:

**Stable codes, never stack traces.**  Validation is a 422 with a code the
caller can branch on, an unknown id is a 404, and a version the repository is
not serving is a 503 ``INSIGHT_VERSION_MISMATCH``. A caller that has to parse
prose to tell these apart will get it wrong the first time the prose changes.

**The bundle is pinned per request.**  ``active_repository`` is resolved once at
the start of a request, so a rebuild landing mid-request cannot produce a
response whose chart and evidence come from different dataset versions.

**Charts are typed data.**  Points, fields and units -- never a sentence. A
model-written label in a chart payload is an unverifiable claim wearing the
costume of an axis.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .contracts import InsightCard, InsightEvidence
from .repository import InsightRepository, InsightRepositoryError, latest_bundle_dir

API_SCHEMA_VERSION = "insight-api.v1"
MAX_PAGE_SIZE = 50
DEFAULT_BUNDLE_ROOT = Path("artifacts/insights")

# Ids are matched against an allow-list pattern before any lookup: an id is a
# key into a dict here, but the pattern keeps a hostile value from reaching a
# path or a log formatter downstream.
INSIGHT_ID_PATTERN = re.compile(r"^ic:[a-z_]+:[0-9a-f]{16}$")
EVIDENCE_ID_PATTERN = re.compile(r"^ev:insight:[0-9a-f]{16}$")

router = APIRouter(prefix="/insights/v1", tags=["insights"])

_repository: InsightRepository | None = None


def set_repository(repository: InsightRepository | None) -> None:
    global _repository
    _repository = repository


def active_repository() -> InsightRepository:
    """Resolve the pinned bundle, loading it once."""
    global _repository
    if _repository is None:
        root = Path(os.environ.get("GLADIATORS_INSIGHT_ROOT", DEFAULT_BUNDLE_ROOT))
        bundle = latest_bundle_dir(root)
        if bundle is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "INSIGHT_BUNDLE_UNAVAILABLE",
                        "message": "Chưa có insight bundle nào được build."},
            )
        try:
            _repository = InsightRepository(bundle)
        except InsightRepositoryError as error:
            raise HTTPException(
                status_code=503, detail={"code": error.code, "message": str(error)},
            ) from error
    return _repository


class Envelope(BaseModel):
    """§12.4: every response carries the same identifying header."""
    schema_version: str = API_SCHEMA_VERSION
    dataset_version: str
    as_of_date: str
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class OverviewResponse(Envelope):
    overview: dict[str, Any]


class CardsResponse(Envelope):
    cards: list[InsightCard]
    next_cursor: str | None = None
    total: int


class CardResponse(Envelope):
    card: InsightCard
    evidence: list[InsightEvidence]


class EvidenceResponse(Envelope):
    evidence: InsightEvidence


class ChartResponse(Envelope):
    chart: dict[str, Any]


def _envelope(repository: InsightRepository, filters: dict, warnings=None) -> dict:
    return {
        "dataset_version": repository.dataset_version,
        "as_of_date": repository.as_of_date,
        "applied_filters": {k: v for k, v in filters.items() if v is not None},
        "warnings": warnings or [],
    }


def _check_version(repository: InsightRepository, requested: str | None) -> None:
    try:
        repository.assert_version(requested)
    except InsightRepositoryError as error:
        raise HTTPException(
            status_code=503, detail={"code": error.code, "message": str(error)},
        ) from error


def _invalid(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "message": message})


@router.get("/health")
def health() -> dict:
    return active_repository().health()


@router.get("/overview", response_model=OverviewResponse)
def overview(
    country: Literal["vn", "id"] = Query(...),
    dataset_version: str | None = Query(default=None),
) -> OverviewResponse:
    # §12.4: no country=all for monetary charts. Requiring the country makes
    # that structural rather than a rule someone remembers to apply.
    repository = active_repository()
    _check_version(repository, dataset_version)
    return OverviewResponse(
        overview=repository.overview(country),
        **_envelope(repository, {"country": country}),
    )


@router.get("/cards", response_model=CardsResponse)
def cards(
    country: Literal["vn", "id"] | None = Query(default=None),
    kind: Literal["top_mover", "price_move", "voucher_gap", "data_quality"] | None = Query(default=None),
    category_id: str | None = Query(default=None),
    priority: Literal["high", "medium", "low"] | None = Query(default=None),
    limit: int = Query(default=20),
    cursor: str | None = Query(default=None),
    dataset_version: str | None = Query(default=None),
) -> CardsResponse:
    repository = active_repository()
    _check_version(repository, dataset_version)
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise _invalid("INSIGHT_LIMIT_INVALID", f"limit phải trong khoảng 1..{MAX_PAGE_SIZE}")

    offset = _decode_cursor(cursor)
    selected = repository.cards(
        country=country, kind=kind, category_id=category_id, priority=priority,
    )
    page = selected[offset:offset + limit]
    next_offset = offset + limit
    return CardsResponse(
        cards=list(page), total=len(selected),
        next_cursor=_encode_cursor(next_offset) if next_offset < len(selected) else None,
        **_envelope(repository, {
            "country": country, "kind": kind, "category_id": category_id,
            "priority": priority, "limit": limit,
        }),
    )


@router.get("/cards/{insight_id}", response_model=CardResponse)
def card(insight_id: str, dataset_version: str | None = Query(default=None)) -> CardResponse:
    repository = active_repository()
    _check_version(repository, dataset_version)
    if not INSIGHT_ID_PATTERN.match(insight_id):
        raise _invalid("INSIGHT_ID_INVALID", "insight_id sai định dạng")
    found = repository.card(insight_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "INSIGHT_NOT_FOUND",
                    "message": "insight_id không thuộc bundle đang phục vụ"},
        )
    return CardResponse(
        card=found, evidence=list(repository.evidence_for(insight_id)),
        **_envelope(repository, {"insight_id": insight_id}),
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceResponse)
def evidence(evidence_id: str, dataset_version: str | None = Query(default=None)) -> EvidenceResponse:
    repository = active_repository()
    _check_version(repository, dataset_version)
    if not EVIDENCE_ID_PATTERN.match(evidence_id):
        raise _invalid("EVIDENCE_ID_INVALID", "evidence_id sai định dạng")
    found = repository.evidence(evidence_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "EVIDENCE_NOT_FOUND",
                    "message": "evidence_id không thuộc bundle đang phục vụ"},
        )
    return EvidenceResponse(
        evidence=found, **_envelope(repository, {"evidence_id": evidence_id}),
    )


@router.get("/charts/price_move", response_model=ChartResponse)
def price_move_chart(
    country: Literal["vn", "id"] = Query(...),
    dataset_version: str | None = Query(default=None),
) -> ChartResponse:
    repository = active_repository()
    _check_version(repository, dataset_version)
    return ChartResponse(
        chart=repository.price_move_chart(country),
        **_envelope(repository, {"country": country}),
    )


def _encode_cursor(offset: int) -> str:
    """Opaque to the caller; there is no promise about its contents."""
    import base64
    return base64.urlsafe_b64encode(f"o:{offset}".encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    import base64
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        if not raw.startswith("o:"):
            raise ValueError
        offset = int(raw[2:])
    except (ValueError, UnicodeDecodeError, Exception):
        raise _invalid("INSIGHT_CURSOR_INVALID", "cursor không hợp lệ") from None
    if offset < 0:
        raise _invalid("INSIGHT_CURSOR_INVALID", "cursor không hợp lệ")
    return offset
