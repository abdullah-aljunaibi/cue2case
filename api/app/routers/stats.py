"""Stats API router for ops dashboard."""
from fastapi import APIRouter
from app.db import get_db_cursor

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("/")
async def get_stats():
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM investigation_case")
        total_cases = cur.fetchone()["count"]
        
        cur.execute("SELECT status, COUNT(*) as count FROM investigation_case GROUP BY status")
        by_status = {r["status"]: r["count"] for r in cur.fetchall()}
        
        cur.execute("SELECT alert_type, COUNT(*) as count FROM alert GROUP BY alert_type")
        alerts_by_type = {r["alert_type"]: r["count"] for r in cur.fetchall()}
        
        cur.execute("SELECT COUNT(*) FROM alert")
        total_alerts = cur.fetchone()["count"]
        
        cur.execute("SELECT COUNT(*) FROM vessel")
        total_vessels = cur.fetchone()["count"]
        
        cur.execute("SELECT COALESCE(AVG(confidence_score), 0) as avg FROM investigation_case")
        avg_confidence = float(cur.fetchone()["avg"])
        
        dismissed = by_status.get("dismissed", 0)
        fpr = round(dismissed / total_cases * 100, 1) if total_cases > 0 else 0
        
        cur.execute("""
            SELECT a.mmsi, v.vessel_name, COUNT(*) as alert_count
            FROM alert a LEFT JOIN vessel v ON a.mmsi = v.mmsi
            GROUP BY a.mmsi, v.vessel_name ORDER BY alert_count DESC LIMIT 10
        """)
        top_vessels = [dict(r) for r in cur.fetchall()]
        
    return {
        "total_cases": total_cases,
        "by_status": by_status,
        "alerts_by_type": alerts_by_type,
        "total_alerts": total_alerts,
        "total_vessels": total_vessels,
        "avg_confidence": round(avg_confidence, 1),
        "false_positive_rate": fpr,
        "top_vessels": top_vessels,
    }
