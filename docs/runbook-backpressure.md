# Queue Backpressure Runbook

Use this runbook to demonstrate queue buildup and recovery when the worker is paused.

## Preconditions

- The Compose stack is up with `make up`.
- The API is reachable at `http://localhost:8000`.
- The worker service is named `worker`.

## Demo Flow

1. Stop the worker:

```sh
docker-compose stop worker
```

2. Confirm the worker is down:

```sh
docker-compose ps worker
```

3. Confirm the queue is empty before starting:

```sh
curl -fsS http://localhost:8000/queue
```

4. Burst 100 events and hold the process for 60 seconds:

```sh
python3 scripts/generate_events.py --count 100 --pause-seconds 60
```

5. Confirm the queue reaches 100:

```sh
curl -fsS http://localhost:8000/queue
```

6. Start the worker:

```sh
docker-compose start worker
```

7. Confirm the queue drains back to 0:

```sh
curl -fsS http://localhost:8000/queue
```

8. Confirm the worker is running again:

```sh
docker-compose ps worker
```

## One-Step Demo

For a scripted version of the same sequence, run:

```sh
make demo-queue-backpressure
```

## Notes

- The queue count is the Redis list length for `page-events`.
- The demo is intended to show backpressure, not data loss. Events remain queued while the worker is down and are drained after restart.
- If the queue does not drain, check `docker-compose logs worker` and `curl -fsS http://localhost:8000/healthz`.
