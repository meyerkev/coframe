.DEFAULT_GOAL := help

.PHONY: help up down logs ps smoke run-10m clean

COMPOSE ?= docker-compose
EVENT_RUN_MINUTES ?= 10
EVENTS_PER_MINUTE ?= 3
SITE_ID ?= demo

help:
	@printf "Available targets:\n"
	@printf "  make up      Build and start the full stack\n"
	@printf "  make down    Stop the stack\n"
	@printf "  make logs    Follow service logs\n"
	@printf "  make ps      Show Compose service status\n"
	@printf "  make smoke   Send one event and read aggregates\n"
	@printf "  make run-10m Generate demo traffic for 10 minutes at 3 events/minute\n"
	@printf "  make clean   Stop the stack and remove all persisted data\n"

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

run-10m:
	python3 scripts/generate_events.py \
		--site-id $(SITE_ID) \
		--duration-minutes $(EVENT_RUN_MINUTES) \
		--events-per-minute $(EVENTS_PER_MINUTE) \
		--session-prefix ten-minute-run

clean:
	$(COMPOSE) down --volumes --remove-orphans
	rm -rf data/*
