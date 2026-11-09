from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import RequestMetaDep, TimeClaimServiceDep
from app.auth.dependencies import CurrentPrincipal
from app.models.time_claim import TimeClaimStatus
from app.schemas.common import ObjectIdStr
from app.schemas.time_claims import TimeClaimCreate, TimeClaimOut, TimeClaimPage, TimeClaimReview

router = APIRouter(prefix="/time-claims", tags=["time-claims"])


@router.get("", response_model=TimeClaimPage, summary="Logged time away from the computer (own, or in scope)")
async def list_claims(
    principal: CurrentPrincipal,
    service: TimeClaimServiceDep,
    status_: Annotated[TimeClaimStatus | None, Query(alias="status")] = None,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
    mine: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TimeClaimPage:
    return await service.list(
        principal, status=status_, employee_id=employee_id, mine=mine, page=page, page_size=page_size
    )


@router.get("/pending-count", summary="Claims waiting for the caller's decision")
async def pending_count(principal: CurrentPrincipal, service: TimeClaimServiceDep) -> dict[str, int]:
    return {"pending": await service.pending_count(principal)}


@router.post("", response_model=TimeClaimOut, status_code=status.HTTP_201_CREATED, summary="Log time")
async def create_claim(
    payload: TimeClaimCreate, principal: CurrentPrincipal, service: TimeClaimServiceDep, meta: RequestMetaDep
) -> TimeClaimOut:
    return await service.create(principal, payload, meta)


@router.post("/{claim_id}/review", response_model=TimeClaimOut, summary="Approve or reject logged time")
async def review_claim(
    claim_id: str,
    payload: TimeClaimReview,
    principal: CurrentPrincipal,
    service: TimeClaimServiceDep,
    meta: RequestMetaDep,
) -> TimeClaimOut:
    return await service.review(principal, claim_id, payload, meta)


@router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete own unreviewed time")
async def delete_claim(
    claim_id: str, principal: CurrentPrincipal, service: TimeClaimServiceDep, meta: RequestMetaDep
) -> Response:
    await service.delete(principal, claim_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
