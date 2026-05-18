#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import os
import time
import urllib.request
from datetime import datetime, timezone


PAGES = ["/", "/pricing", "/docs", "/signup", "/checkout", "/blog/platform"]
WEIGHTS = [9, 7, 5, 4, 3, 2]
EXPERIMENTS = ["hero-copy", "checkout-flow"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo performance events.")
    parser.add_argument("--api", default=env("API_URL", "http://localhost:8000"))
    parser.add_argument("--site-id", default=env("SITE_ID", "demo"))
    parser.add_argument("--duration-minutes", type=float, default=env_float("DURATION_MINUTES", 10))
    parser.add_argument("--events-per-minute", type=float, default=env_float("EVENTS_PER_MINUTE", 3))
    parser.add_argument("--count", type=int, default=env_int("EVENT_COUNT", 0))
    parser.add_argument("--pause-seconds", type=int, default=env_int("PAUSE_SECONDS", 0))
    parser.add_argument("--session-prefix", default=env("SESSION_PREFIX", "generated"))
    args = parser.parse_args()

    if args.count > 0:
        total_events = args.count
        sleep_seconds = 0
    else:
        total_events = max(1, round(args.duration_minutes * args.events_per_minute))
        sleep_seconds = 60 / args.events_per_minute

    for index in range(total_events):
        payload = build_event(args.site_id, args.session_prefix, index)
        post_event(args.api, payload)
        print(
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"sent={index + 1}/{total_events} page={payload['page_url']} lcp_ms={payload['lcp_ms']}",
            flush=True,
        )
        if index != total_events - 1:
            time.sleep(sleep_seconds)

    if args.pause_seconds > 0:
        print(f"{datetime.now().isoformat(timespec='seconds')} pausing={args.pause_seconds}s", flush=True)
        time.sleep(args.pause_seconds)


def build_event(site_id: str, session_prefix: str, index: int) -> dict[str, object]:
    return {
        "site_id": site_id,
        "page_url": random.choices(PAGES, weights=WEIGHTS, k=1)[0],
        "experiment": random.choice(EXPERIMENTS),
        "lcp_ms": random.randint(650, 4200),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "session_id": f"{session_prefix}-{index:04d}",
    }


def post_event(api: str, payload: dict[str, object]) -> None:
    request = urllib.request.Request(
        f"{api.rstrip('/')}/events",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()


def env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


if __name__ == "__main__":
    main()
