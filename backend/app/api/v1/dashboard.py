from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # A shared literal fallback would put every tenant that resolves to it into the
    # same cache bucket and the same query scope, so an unresolved tenant must fail
    # closed rather than silently join a shared one.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="No tenant associated with this account",
        )

    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Round to cents exactly once, here, in decimal arithmetic. The amounts carry
    # three decimals, so half-cent values have to be resolved by an explicit rounding
    # rule - float(x * 100) resolves half of them the wrong way. Rounding the summed
    # total (rather than each reservation) is also what keeps the total consistent
    # with the client's own books.
    total_revenue = Decimal(revenue_data['total']).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
