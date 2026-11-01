from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..services.customers import list_customers
from ..services.serialization import customer_payload
from .dependencies import ApiServices, get_services


router = APIRouter(prefix="/api", tags=["customers"])


@router.get("/customers")
def get_customers(
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        rows = list_customers(db, query=query, limit=limit)
        return {
            "items": [customer_payload(customer, ticket_count=count) for customer, count in rows],
            "count": len(rows),
        }
