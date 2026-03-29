# Quant Platform (Phase 1 Scaffold)

Config-driven quant trading monorepo with:
- FastAPI backend
- React + TypeScript frontend
- PostgreSQL + Redis
- Parquet cache for market data
- Polygon historical/live aggregate bars integration points

## Services
- `backend`: API and orchestration layer
- `frontend`: UI for dashboard, backtests, and data sync
- `postgres`: persistence
- `redis`: low-latency state/cache

## Phase 1 Included
- Initial modular folder structure
- Base API routes and app wiring
- Placeholder domain packages:
  - core models
  - polygon data access
  - backtesting
  - paper simulation
  - strategies (`mr_vwap`)
  - persistence
- Frontend pages:
  - Dashboard
  - Backtests
  - Data Sync

## Quickstart
```bash
cp .env.example .env
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173
