# pg-assignment-optimizer

Stateless service that auto-assigns pending inspection requests from `pg-inspection-service` to available inspectors using Google OR-Tools.

- **No DB.** All reads/writes go through Inspection Service HTTP APIs.
- **Strict `preferredTime`.** A request is only assigned if an inspector has an open slot at the exact preferred time. Otherwise it is reported as `skipped: NO_SLOT_AT_PREFERRED_TIME`.
- **Per-pincode batching.** All pending requests worldwide → grouped by `(pincode, date)` → solved one bucket at a time, in order of earliest date and highest urgency-weighted demand.
- **Phase 1 (current):** greedy first-fit picker. CP-SAT solver lands in Phase 2.

## Endpoints

| Method | Path           | Auth         | Notes                                        |
|--------|----------------|--------------|----------------------------------------------|
| GET    | `/healthz`     | none         | Liveness                                     |
| GET    | `/readyz`      | none         | Readiness                                    |
| POST   | `/auto-assign` | `X-API-KEY`  | Body: `{ dry_run?, pincodes?, solver_time_sec? }` |

## Auth

Symmetric shared secret. Same `INTERNAL_API_KEY` env var on both this service and `pg-inspection-service`. Pass it as `X-API-KEY` on every internal call (in either direction).

## Local development

```bash
cp .env.example .env
# Set INSPECTION_SERVICE_URL and INTERNAL_API_KEY

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Tests
pytest

# Run
uvicorn app.main:app --reload --port 8000
```

## Deploy on Render

1. Push this directory as its own Git repo (or connect the monorepo path).
2. New → Blueprint → point at `render.yaml`.
3. Set `INSPECTION_SERVICE_URL` and `INTERNAL_API_KEY` in the dashboard (both marked `sync: false`).
4. The Inspection Service Vercel cron (`/api/cron/auto-assign`) will start hitting this service.
