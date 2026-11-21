"""
Financial API Endpoints
REST API for Financial Record CRUD operations with approval workflow
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from datetime import date
from decimal import Decimal
import logging
import math

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.services.financial_service import FinancialService
from backend.schemas.financial_record import (
    FinancialRecordCreate,
    FinancialRecordUpdate,
    FinancialRecordResponse,
    FinancialRecordFilter,
    PaginatedFinancialRecordResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/", response_model=FinancialRecordResponse, status_code=status.HTTP_201_CREATED
)
async def create_financial_record(
    record_data: FinancialRecordCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new financial record."""
    try:
        record = await FinancialService.create_financial_record(db, record_data)
        logger.info(f"Created financial record: {record.id}")
        return record
    except Exception as e:
        logger.error(f"Failed to create financial record: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create financial record",
        )


@router.get("/{record_id}", response_model=FinancialRecordResponse)
async def get_financial_record(record_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get financial record by ID."""
    record = await FinancialService.get_financial_record(db, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial record {record_id} not found",
        )
    return record


@router.get("/", response_model=PaginatedFinancialRecordResponse)
async def list_financial_records(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    type_filter: Optional[str] = Query(None, alias="type"),
    approval_status: Optional[str] = Query(None),
    project_id: Optional[UUID] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    min_amount: Optional[Decimal] = Query(None),
    max_amount: Optional[Decimal] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List financial records with filtering and pagination."""
    try:
        filters = FinancialRecordFilter(
            type=type_filter,
            approval_status=approval_status,
            project_id=project_id,
            category=category,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
        )

        items, total = await FinancialService.list_financial_records(
            db, filters=filters, page=page, page_size=page_size
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return PaginatedFinancialRecordResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except Exception as e:
        logger.error(f"Failed to list financial records: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list financial records",
        )


@router.put("/{record_id}", response_model=FinancialRecordResponse)
async def update_financial_record(
    record_id: UUID,
    record_data: FinancialRecordUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update financial record."""
    record = await FinancialService.update_financial_record(db, record_id, record_data)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial record {record_id} not found",
        )
    logger.info(f"Updated financial record: {record_id}")
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_financial_record(record_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete financial record."""
    deleted = await FinancialService.delete_financial_record(db, record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial record {record_id} not found",
        )
    logger.info(f"Deleted financial record: {record_id}")


async def _resolve_approver(db: AsyncSession, user: dict) -> UUID:
    """The approver is the verified token subject, never a client-supplied id.

    Requires exactly one active user with ``users.external_subject == sub``
    (``sub`` is an opaque string); anything else is 403 with no fallback.
    """
    sub = user.get("id")
    rows = []
    if isinstance(sub, str) and sub:
        result = await db.execute(
            select(User).where(User.external_subject == sub).limit(2)
        )
        rows = result.scalars().all()
    if len(rows) != 1 or not rows[0].is_active:
        logger.warning("Approver identity not provisioned for sub %r", sub)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Approver identity not provisioned",
        )
    return rows[0].id


@router.post("/{record_id}/approve", response_model=FinancialRecordResponse)
async def approve_financial_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Approve a financial record as the authenticated user."""
    approver_id = await _resolve_approver(db, user)
    record = await FinancialService.approve_financial_record(db, record_id, approver_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial record {record_id} not found",
        )
    logger.info(f"Approved financial record: {record_id} by {approver_id}")
    return record


@router.post("/{record_id}/reject", response_model=FinancialRecordResponse)
async def reject_financial_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reject a financial record as the authenticated user."""
    approver_id = await _resolve_approver(db, user)
    record = await FinancialService.reject_financial_record(db, record_id, approver_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial record {record_id} not found",
        )
    logger.info(f"Rejected financial record: {record_id} by {approver_id}")
    return record
