# Coframe Platform Assignment

Minimal platform and three-service web performance product for the take-home assignment in [docs/assignment.md](docs/assignment.md).

## Run

Prerequisites:

- Docker with Compose v2
- `make`
- `curl` for the smoke test

Start everything:

```sh
make up
```

Open:

- Dashboard: <http://localhost:8080>
- API: <http://localhost:8000/healthz>
- Prometheus: <http://localhost:9090>

Seed one event and read the aggregate:

```sh
make smoke
```

Generate 10 minutes of demo traffic at 3 events per minute:

```sh
make run-10m
```

Stop:

```sh
make down
```

## Services

- `api`: FastAPI service that accepts SDK events, returns site config, exposes aggregate reads, and publishes Prometheus metrics.
- `worker`: Go service that consumes Redis queue entries and writes rolling aggregates to SQLite.
- `frontend`: static HTML/CSS/JS dashboard served by Nginx.
- `redis`: queue between API and worker.
- `prometheus`: metrics collection for API and worker.

## Adding A Fourth Service

1. Create `services/<name>/` with a `Dockerfile`.
2. Add a new entry in `docker-compose.yml` using the `x-service-defaults` anchor.
3. Put service-specific environment variables and ports in that entry.
4. If it exposes metrics, add its target to `platform/prometheus/prometheus.yml`.
5. Run `make up --build` and confirm it appears in `docker compose ps`.

No platform code changes are required unless the service needs a new shared dependency, such as a new database.

## Demo Recording

Loom: TODO

