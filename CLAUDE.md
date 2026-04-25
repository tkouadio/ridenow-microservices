# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RideNow is a proof-of-concept microservices architecture for a ridesharing platform, developed as part of the MGL7361 course at UQAM. It consists of 5 Python/FastAPI services orchestrated via Docker Compose.

## Running the Stack

```bash
# Start all services (builds images on first run)
docker compose up --build

# Start in detached mode
docker compose up --build -d

# View logs for a specific service
docker compose logs -f gateway

# Stop everything
docker compose down
```

Services are available at:
- Gateway: http://localhost:8000
- Identity: http://localhost:8001
- Pricing: http://localhost:8002
- Ride: http://localhost:8003
- Payment: http://localhost:8004

Each service exposes Swagger UI at `/docs`.

## Development Without Docker

Each service runs independently. From a service directory:

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8001  # adjust port per service
```

For the gateway, set environment variables pointing to running services:
```bash
IDENTITY_URL=http://localhost:8001 PRICING_URL=http://localhost:8002 \
RIDE_URL=http://localhost:8003 PAYMENT_URL=http://localhost:8004 \
uvicorn app:app --reload --port 8000
```

## Testing the API

Use the `demo.http` file with VS Code REST Client extension, or use curl:

```bash
# Request a ride
curl -X POST http://localhost:8000/demo/request-ride \
  -H "Content-Type: application/json" \
  -d '{"passenger_id": 1, "from_zone": "A", "to_zone": "B"}'

# Advance ride status (ASSIGNED → ACCEPTED → STARTED → COMPLETED)
curl -X PATCH http://localhost:8000/demo/rides/{ride_id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "ACCEPTED"}'
```

There is no automated test suite; manual testing via HTTP requests is the intended approach.

## Architecture

### Service Responsibilities

| Service | Port | Role |
|---------|------|------|
| `gateway/` | 8000 | Orchestrates the nominal flow; single entry point for clients |
| `services/identity/` | 8001 | Manages passengers, drivers, and driver availability |
| `services/pricing/` | 8002 | Returns fixed prices for zone-pair combinations |
| `services/ride/` | 8003 | Manages ride lifecycle and payment status |
| `services/payment/` | 8004 | Simulates payment authorization and capture |

### Communication Pattern

The **Gateway orchestrates all inter-service calls** — services never call each other directly. All communication is synchronous REST/JSON over HTTP using `httpx.AsyncClient`.

Nominal ride flow:
1. Gateway validates passenger (Identity)
2. Gateway finds available driver in zone (Identity)
3. Gateway fetches price (Pricing)
4. Gateway creates ride record (Ride) → status: `ASSIGNED`
5. Gateway authorizes payment (Payment)
6. Gateway marks driver unavailable (Identity)
7. Client advances ride status via Gateway patches (Ride): `ASSIGNED → ACCEPTED → STARTED → COMPLETED`
8. On `COMPLETED`: Gateway captures payment (Payment), updates ride payment status (Ride), releases driver (Identity)

### Ride State Machine

```
ASSIGNED → ACCEPTED → STARTED → COMPLETED
                    ↘ CANCELLED
```

State transitions are validated in `services/ride/app.py`. Invalid transitions return HTTP 409.

### Database-per-Service

Each service owns an independent SQLite database (created at startup). There are no shared databases or cross-service queries. Identity and Pricing services seed sample data on startup.

### Resilience (Gateway-Level)

- Configurable timeout: `REQUEST_TIMEOUT_SECONDS` env var (default: 3s)
- Simple retry: `RETRY_COUNT` env var (default: 1) with 0.2s backoff
- Timeouts propagate as HTTP 504 to the client

### Environment Variables

```
# Gateway only
IDENTITY_URL, PRICING_URL, RIDE_URL, PAYMENT_URL  # service base URLs
REQUEST_TIMEOUT_SECONDS                             # default: 3
RETRY_COUNT                                         # default: 1

# All services
DATABASE_URL                                        # e.g. sqlite:///./identity.db
```

These are set automatically by `docker-compose.yml` when running with Docker.
