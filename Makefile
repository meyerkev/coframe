.DEFAULT_GOAL := help

.PHONY: help up down logs ps smoke run-10m run-100-paused demo-queue-backpressure clean

COMPOSE ?= docker-compose

help:
	@printf "Available targets:\n"
	@printf "  make up      Build and start the full stack\n"
	@printf "  make down    Stop the stack\n"
	@printf "  make logs    Follow service logs\n"
	@printf "  make ps      Show Compose service status\n"
	@printf "  make smoke   Send one event and read aggregates\n"
	@printf "  make run-10m Generate demo traffic for 10 minutes at 3 events/minute\n"
	@printf "  make run-100-paused Generate 100 events and pause 60 seconds after\n"
	@printf "  make demo-queue-backpressure Stop worker, queue 100, pause 60, restart\n"
	@printf "  make clean   Stop the stack and remove all persisted data\n"

up:
	$(COMPOSE) up --build -d

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
	python3 scripts/generate_events.py

run-100-paused:
	EVENT_COUNT=100 PAUSE_SECONDS=60 python3 scripts/generate_events.py

demo-queue-backpressure:
	python3 scripts/demo_queue_backpressure.py

clean:
	$(COMPOSE) down --volumes --remove-orphans
	rm -rf data/*
