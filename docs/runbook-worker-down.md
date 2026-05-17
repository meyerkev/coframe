# Runbook: Worker Down

## Symptom

The dashboard stops showing new aggregate data after events are posted. API health remains green, but `worker_events_processed_total` stops increasing in Prometheus.

## Impact

Events continue to queue in Redis, but customer-facing aggregate data becomes stale until the worker returns.

## Detect

Check Compose status:

```sh
docker compose ps
```

Check worker logs:

```sh
docker compose logs --tail=100 worker
```

Check Prometheus:

```promql
rate(worker_events_processed_total[1m])
```

## Recover

Restart the worker:

```sh
docker compose restart worker
```

Confirm it is consuming again:

```sh
docker compose logs -f --tail=50 worker
make smoke
```

Then check that `worker_events_processed_total` increases and the dashboard updates.

## Demo Failure

Induce the failure:

```sh
docker compose stop worker
make smoke
```

Observe that the event is accepted by the API but the dashboard does not update. Recover with:

```sh
docker compose start worker
```

Redis retains the queued event while the worker is down, so the worker should process it after restart.

