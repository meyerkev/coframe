# Design

## Service Shape

The API is a Python FastAPI service. It accepts SDK performance events on `POST /events`, validates the JSON payload, and pushes it to Redis. It serves SDK configuration from SQLite on `GET /config/{site_id}` and exposes dashboard aggregate reads on `GET /aggregates`. Its state lives in SQLite for site configuration and aggregate reads; it does not retain queued events in process memory.

The worker is a Go background process. It blocks on a Redis list, decodes page performance events, persists raw events to SQLite, and refreshes per `(site_id, page_url)` aggregates with event count, p75 LCP, and last-seen timestamp. Its durable state lives in SQLite.

The frontend is a static HTML/CSS/JS dashboard served by Nginx. It reads config and aggregate data from the API and renders top pages by event volume, a compact p75 LCP chart, and active experiments. It has no server-side state.

## Stack Choices

Docker Compose is the platform layer because this assignment must run on a laptop and needs a single command that starts the full system. Kubernetes was considered and rejected because it would add cluster mechanics, manifests, ingress, and local runtime complexity that do not improve the first-week outcome for a 5-person startup.

Redis is the queue because it is simple to operate locally, works well as a short-lived buffer, and maps cleanly to the API-to-worker contract. Kafka was considered and rejected because its operational footprint is too heavy for this product stage and this assignment scope.

SQLite is the internal datastore because it keeps the demo self-contained, inspectable, and durable enough for local operation. Postgres was considered and rejected for the initial build because it adds another server process and migration surface before the app needs concurrent multi-writer scale.

Prometheus is the observability store because both services can expose standard `/metrics` endpoints and Prometheus is easy to run in Compose. A hosted observability stack was considered and rejected because the assignment needs to run on a laptop without external accounts.

Nginx serves the frontend because the dashboard is static. A full SPA framework was considered and rejected because the assignment explicitly values platform judgment over dashboard polish.

## Least Confident Decision

SQLite is the decision I am least confident about beyond the take-home scope. It is the right tradeoff for local operability, but it would be the first component I would replace if the team needed multi-instance writes, point-in-time recovery, or production-grade operational controls.

## Deliberately Not Built

I did not build authentication, multi-tenant authorization, migrations, tracing, alert routing, CI/CD, TLS, staging, or production deployment automation. I would add auth before exposing the dashboard to real customers, migrations before schema changes became routine, tracing when request paths became hard to debug from logs and metrics, alerting once SLOs existed, and CI/CD before the team made regular production changes.

## Adding A Service

The platform convention is one directory per service under `services/`, one `Dockerfile` per service, and one Compose service entry using the shared `x-service-defaults` anchor. A fourth service should not require platform code changes. Add its Compose stanza, declare its dependencies, expose a health endpoint, and add a Prometheus scrape target if it publishes metrics.

