# Running ACGS Enterprise Manager with Docker Compose

Run the full stack (`db`, `api`, `frontend`) locally with one command.

## Quick Start

```bash
cp .env.compose.example .env
docker compose up --build
```

Add `-d` to run in the background (`docker compose up -d --build`).

If host port `3000` or `8001` is already occupied on your machine, override `FRONTEND_PORT` or `API_PORT` in `.env` (or on the command line, e.g. `FRONTEND_PORT=13000 docker compose up --build`).

## Endpoints

| Service | Host URL | Notes |
|---------|----------|-------|
| Frontend SPA | `http://localhost:3000/` | Unprivileged Nginx (`nginxinc/nginx-unprivileged:1.27-alpine`) on container port `8080`, serving the built Vue SPA (`try_files $uri $uri/ /index.html`) |
| Proxied API | `http://localhost:3000/api/` | Proxied by Nginx to `http://api:8001` |
| Proxied Health | `http://localhost:3000/health` | Proxied by Nginx to `http://api:8001/health` |
| Backend API | `http://localhost:8001` | FastAPI + Uvicorn running as non-root `appuser` |
| Backend Health | `http://localhost:8001/health` | Public; returns `{"status":"healthy","service":"acgs-enterprise-manager","version":"1.0.0"}` |
| Backend Root | `http://localhost:8001/` | Public API info JSON |
| OpenAPI Docs | `http://localhost:8001/docs` | Disabled by default (`API_DOCS_ENABLED=false`); set `API_DOCS_ENABLED=true` in `.env` to expose `/docs`, `/redoc`, and `/openapi.json` |

## Authentication (Fail-Closed External IdP JWT)

The backend **only verifies** bearer JWT access tokens issued by an external OIDC/JWT identity provider. There is no built-in login endpoint, no token minting, and no fallback/default signing key.

- **Unconfigured default:** With `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, and `AUTH_JWKS_URL`/`AUTH_JWT_KEY` unset, the stack starts cleanly for smoke checks:
  - `GET /health` and `GET /` on `api` (and `GET /` and `GET /health` on `frontend`) remain **public** and return HTTP `200`.
  - Every protected `/api/v1/*` route **fails closed** with HTTP `503 {"detail": "Authentication not configured"}`.
  - The frontend `/login` view shows `"SSO not configured: set VITE_OIDC_AUTHORITY and VITE_OIDC_CLIENT_ID."`
- **Enabling external OIDC/JWT auth:**
  1. Configure `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, `AUTH_JWT_ALGORITHMS`, `AUTH_ROLE_CLAIM`, and **exactly one** of `AUTH_JWKS_URL` (preferred, `https://`) or `AUTH_JWT_KEY` in `.env`. See [`.env.example`](../.env.example) for full details and role-claim rules.
  2. Configure `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, and optional `VITE_OIDC_*` variables in `.env`. See [`frontend/.env.example`](../frontend/.env.example) and [`frontend/README.md`](../frontend/README.md).
  3. Rebuild the frontend image after changing any `VITE_*` variable (`docker compose up -d --build frontend`), because Vite embeds `VITE_*` values and the CSP `connect-src` origin (via `frontend/vite.config.js`) at build time.

## Database Notes

- `db` uses `postgres:16-alpine` with a named volume `pgdata` and defaults `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=acgs_manager` (override in `.env`).
- On first initialization (when `pgdata` is empty), Postgres runs:
  - `database/schema.sql` mounted as `/docker-entrypoint-initdb.d/01-schema.sql` (which already incorporates migrations `001` through `003`)
  - `database/indexes.sql` mounted as `/docker-entrypoint-initdb.d/02-indexes.sql`
- Postgres is reachable only inside the Compose network (`db:5432`). `api` waits for `db` (`pg_isready` healthcheck) before starting.
- Changing `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` after `pgdata` has been initialized does not update an existing volume; tear down with `-v` first if you need a fresh database.

## Teardown

Stop containers and keep the `pgdata` database volume:

```bash
docker compose down
```

Stop containers and remove the `pgdata` volume plus locally built images:

```bash
docker compose down -v --rmi local
```
