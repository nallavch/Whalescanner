from fastapi import APIRouter

router = APIRouter()


@router.post("/polygon/aggregates")
def sync_polygon_aggregates() -> dict[str, str]:
    return {
        "status": "queued",
        "provider": "polygon",
        "scope": "historical_and_live_aggregate_bars",
    }
