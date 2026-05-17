.PHONY: up down logs ps smoke clean

COMPOSE ?= docker compose

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

smoke:
	curl -fsS http://localhost:8000/healthz
	curl -fsS -X POST http://localhost:8000/events \
		-H 'content-type: application/json' \
		-d '{"site_id":"demo","page_url":"/pricing","lcp_ms":1830,"timestamp":"2026-05-17T12:00:00Z","session_id":"smoke-1"}'
	sleep 2
	curl -fsS 'http://localhost:8000/aggregates?site_id=demo'

clean:
	$(COMPOSE) down -v
	rm -f data/*.db data/*.db-*

