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

Run the queue backpressure demo:

```sh
make demo-queue-backpressure
```

Stop:

```sh
make down
```

## Demo

1. Run `make up`.
2. Open the dashboard at <http://localhost:8080>.
3. Run `make smoke` to seed a single event.
4. Run `make run-10m` to generate a live traffic sample.
5. Run `make demo-queue-backpressure` to show the worker pause and queue drain behavior.
6. Use `make down` when you are finished.

## Services

- `api`: FastAPI service that accepts SDK events, returns site config, exposes aggregate reads, and publishes Prometheus metrics.
- `worker`: Go service that consumes Redis queue entries and writes rolling aggregates to Postgres.
- `frontend`: static HTML/CSS/JS dashboard served by Nginx.
- `postgres`: primary datastore for raw events, aggregates, and config.
- `redis`: queue between API and worker.
- `prometheus`: metrics collection for API and worker.

## Runbooks

- [Queue backpressure](docs/runbook-backpressure.md)

## Adding A Fourth Service

1. Create `services/<name>/` with a `Dockerfile`.
2. Add a new entry in `docker-compose.yml` using the `x-service-defaults` anchor.
3. Put service-specific environment variables and ports in that entry.
4. If it exposes metrics, add its target to `platform/prometheus/prometheus.yml`.
5. Run `make up --build` and confirm it appears in `docker compose ps`.

No platform code changes are required unless the service needs a new shared dependency, such as a new database.

## Demo Recording

A 5-minute Loom should show: deploying the stack with `make up`, opening the dashboard and Prometheus, running `make smoke`, inducing a worker failure by stopping the worker, showing queue buildup in `GET /queue`, restarting the worker, and confirming the queue drains back to zero.
