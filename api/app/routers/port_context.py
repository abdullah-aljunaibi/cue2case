# NOTE: Register this router in main.py: from app.routers.port_context import router as port_context_router; app.include_router(port_context_router)
"""FastAPI router for port context endpoints."""

import re

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/port-context", tags=["port-context"])

PROFILE_KEY_PATTERN = re.compile(r'^[a-z0-9_-]{1,32}$')


@router.get("/profile")
async def get_profile(profile_key: str = Query(default="duqm")):
    """Get the active port profile with all zones, corridors, and critical areas."""
    from app.services.port_context import get_active_profile

    if not PROFILE_KEY_PATTERN.match(profile_key):
        raise HTTPException(400, "Invalid profile key")

    profile = get_active_profile(profile_key)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_key}' not found")
    return profile


@router.get("/zones")
async def get_zones_at_point(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    profile_key: str = Query(default="duqm"),
):
    """Get zones containing a specific point."""
    from app.services.port_context import get_zones_for_point

    if not PROFILE_KEY_PATTERN.match(profile_key):
        raise HTTPException(400, "Invalid profile key")

    return get_zones_for_point(lon, lat, profile_key)


@router.get("/criticality")
async def get_criticality(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    profile_key: str = Query(default="duqm"),
):
    """Get zone criticality score for a point."""
    from app.services.port_context import get_zone_criticality

    if not PROFILE_KEY_PATTERN.match(profile_key):
        raise HTTPException(400, "Invalid profile key")

    return {"criticality": get_zone_criticality(lon, lat, profile_key), "lon": lon, "lat": lat}
