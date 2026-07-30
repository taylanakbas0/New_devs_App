from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month.

    The month boundaries are built in the property's own timezone, because that is
    the calendar the client reconciles against. A booking at 2024-02-29 23:30 UTC is
    2024-03-01 00:30 in Europe/Paris and therefore belongs to March, not February.
    """
    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.session_factory() as session:
        tz_row = (await session.execute(text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """), {
            "property_id": property_id,
            "tenant_id": tenant_id
        })).fetchone()

        if not tz_row:
            return Decimal('0')

        # ZoneInfo resolves the correct offset for each wall time, so the DST
        # switch on 2024-03-31 does not shift the end of the month by an hour.
        property_tz = ZoneInfo(tz_row.timezone)

        start_local = datetime(year, month, 1, tzinfo=property_tz)
        if month < 12:
            end_local = datetime(year, month + 1, 1, tzinfo=property_tz)
        else:
            end_local = datetime(year + 1, 1, 1, tzinfo=property_tz)

        start_date = start_local.astimezone(timezone.utc)
        end_date = end_local.astimezone(timezone.utc)

        print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")

        query = text("""
            SELECT SUM(total_amount) as total
            FROM reservations
            WHERE property_id = :property_id
            AND tenant_id = :tenant_id
            AND check_in_date >= :start_date
            AND check_in_date < :end_date
        """)

        total = (await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date
        })).scalar()

        return Decimal(str(total)) if total is not None else Decimal('0')

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        
        # Initialize pool if needed
        db_pool = DatabasePool()
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        # Never substitute placeholder figures for real revenue: the fallback that
        # used to live here was keyed on property_id alone, so a property id shared
        # by two tenants (prop-001) served one client's numbers to the other.
        # A failed lookup must surface as an error, not as plausible-looking data.
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise
