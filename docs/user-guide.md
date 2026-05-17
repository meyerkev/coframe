# Engineering User Guide

## Day-To-Day Commands

Start the system:

```sh
make up
```

Check running services:

```sh
make ps
```

Follow logs:

```sh
make logs
```

Run a basic ingest smoke test:

```sh
make smoke
```

Generate a 10-minute demo traffic run:

```sh
make run-10m
```

Stop the system:

```sh
make down
```

Reset local state:

```sh
make clean
```

## Surfaces

- Dashboard: <http://localhost:8080>
- API health: <http://localhost:8000/healthz>
- API metrics: <http://localhost:8000/metrics>
- Worker metrics: <http://localhost:9101/metrics>
- Prometheus: <http://localhost:9090>

## Common Workflow

1. Pull the latest code.
2. Run `make up`.
3. Use `make smoke` to confirm API, Redis, worker, and Postgres are connected.
4. Open the dashboard and Prometheus.
5. Make service changes in `services/<name>`.
6. Rebuild with `docker compose up --build <name>`.
7. Watch logs and metrics before calling the change good.

## Adding A Service

Create `services/<name>/Dockerfile`, add it to `docker-compose.yml`, and optionally add a Prometheus scrape job. Keep `/healthz` and `/metrics` conventions when possible so operators do not need a different workflow for each service.
