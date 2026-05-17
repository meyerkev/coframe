# Design

## Service Shape

The API is a Python FastAPI service. It accepts SDK performance events on `POST /events`, validates the JSON payload, and pushes it to Redis. It serves SDK configuration from Postgres on `GET /config/{site_id}` and exposes dashboard aggregate reads on `GET /aggregates`. Its state lives in Postgres for site configuration and aggregate reads; it does not retain queued events in process memory.

The worker is a Go background process. It blocks on a Redis list, decodes page performance events, persists raw events to Postgres, and refreshes per `(site_id, page_url)` aggregates with event count, p75 LCP, and last-seen timestamp. Its durable state lives in Postgres.

The frontend is a static HTML/CSS/JS dashboard served by Nginx. It reads config and aggregate data from the API and renders top pages by event volume, a compact p75 LCP chart, and experiment latency grouped by experiment. It has no server-side state.

## Stack Choices

Docker Compose is the platform layer because this assignment must run on a laptop and needs a single command that starts the full system. Kubernetes was considered and rejected because it would add cluster mechanics, manifests, ingress, and local runtime complexity that do not improve the first-week outcome for a 5-person startup.

Redis is the queue because it is simple to operate locally, works well as a short-lived buffer, and maps cleanly to the API-to-worker contract. Kafka was considered and rejected because its operational footprint is too heavy for this product stage and this assignment scope.

Postgres is the internal datastore because it keeps the demo close to a real deployment while still fitting comfortably inside Compose. SQLite was considered and rejected for the current build because the dashboard and worker are already writing a shared durable store and we want a production-shaped connection model.  Postgres has many answers that live in a replicated production context so your production is "just" setting up replication into the long-term hosted cloud solution.  SQLite at present does not (though Turso is putting in some work there) so you would have to do a much larger migration to pivot from SQLite to Postgres and do some sort of data mangling or dual-source work.  

Prometheus is the observability store because both services can expose standard `/metrics` endpoints and Prometheus is easy to run in Compose. A hosted observability stack was considered and rejected because the assignment needs to run on a laptop without external accounts.

Nginx serves the frontend because the dashboard is static. A full SPA framework was considered and rejected because the assignment explicitly values platform judgment over dashboard polish.

## Least Confident Decision

The choice of docker-compose vs. some sort of local k8s is still my least favorite choice here since long-term, you either end up recreating half of k8s in your not-k8s cloud option or using "simple" cloud-hosted k8s.  In fairness, simple k8s is actually pretty simple since the cloud provider gives you networking and disks that "just work" and in GCP, autoscaling is a boolean flipped to true.  

On the other hand, it was so easy to build this, I don't mind losing the work.  

## Deliberately Not Built

I did not build authentication, multi-tenant authorization, migrations, tracing, alert routing, CI/CD, TLS, staging, or production deployment automation. I would add auth before exposing the dashboard to real customers, migrations before schema changes became routine, tracing when request paths became hard to debug from logs and metrics, alerting once SLOs existed, and CI/CD before the team made regular production changes.

Also, in a minor instance of "This is an interview and not a truly production environment", we would need to have a secrets vault instead of sticking them in the docker-compose on a public github repository.  

I'm not spending money on this, but that would be a vendor of some sort and you would either pay them money or self-host some sort of encrypted vault where you would stick things like the database password that is currently hard-coded.  

This would be a hard blocker on the production launch and you would wait while I set something up and possibly handed me a credit card.  

## Adding A Service

The platform convention is one directory per service under `services/`, one `Dockerfile` per service, and one Compose service entry using the shared `x-service-defaults` anchor. A fourth service should not require platform code changes. Add its Compose stanza, declare its dependencies, expose a health endpoint, and add a Prometheus scrape target if it publishes metrics.
