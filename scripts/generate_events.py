#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request
from datetime import datetime, timezone


PAGES = ["/", "/pricing", "/docs", "/signup", "/checkout", "/blog/platform"]
WEIGHTS = [9, 7, 5, 4, 3, 2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo performance events.")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--site-id", default="demo")
    parser.add_argument("--duration-minutes", type=float, default=10)
    parser.add_argument("--events-per-minute", type=float, default=3)
    parser.add_argument("--session-prefix", default="generated")
    args = parser.parse_args()

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


def build_event(site_id: str, session_prefix: str, index: int) -> dict[str, object]:
    return {
        "site_id": site_id,
        "page_url": random.choices(PAGES, weights=WEIGHTS, k=1)[0],
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


if __name__ == "__main__":
    main()

