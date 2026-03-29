from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_backtests() -> dict[str, list[dict[str, str]]]:
    return {
        "items": [
            {
                "id": "phase1-placeholder",
                "strategy": "mr_vwap",
                "status": "not_started",
            }
        ]
    }
