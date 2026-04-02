# NOTE: Register this router in main.py: from app.routers.port_context import router as port_context_router; app.include_router(port_context_router)
"""FastAPI router for port context endpoints."""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/port-context", tags=["port-context"])


@router.get("/profile")
async def get_profile(profile_key: str = Query(default="duqm")):
    """Get the active port profile with all zones, corridors, and critical areas."""
    from app.services.port_context import get_active_profile

    profile = get_active_profile(profile_key)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_key}' not found")
    return profile


@router.get("/zones")
async def get_zones_at_point(
    lon: float = Query(...),
    lat: float = Query(...),
    profile_key: str = Query(default="duqm"),
):
    """Get zones containing a specific point."""
    from app.services.port_context import get_zones_for_point

    return get_zones_for_point(lon, lat, profile_key)


@router.get("/criticality")
async def get_criticality(
    lon: float = Query(...),
    lat: float = Query(...),
    profile_key: str = Query(default="duqm"),
):
    """Get zone criticality score for a point."""
    from app.services.port_context import get_zone_criticality

    return {"criticality": get_zone_criticality(lon, lat, profile_key), "lon": lon, "lat": lat}
