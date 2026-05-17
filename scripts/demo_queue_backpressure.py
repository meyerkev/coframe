#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSE = "docker-compose"
API_URL = "http://localhost:8000"
QUEUE_URL = f"{API_URL}/queue"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the queue backpressure demo.")
    parser.add_argument("--events", type=int, default=100)
    parser.add_argument("--pause-seconds", type=int, default=60)
    parser.add_argument("--worker-service", default="worker")
    parser.add_argument("--expected-queue-size", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--poll-interval-seconds", type=int, default=1)
    args = parser.parse_args()

    stop_worker(args.worker_service)
    assert_worker_stopped(args.worker_service)

    run_event_burst(args.events, args.pause_seconds)
    wait_for_queue_size(args.expected_queue_size, args.timeout_seconds, args.poll_interval_seconds)

    start_worker(args.worker_service)
    wait_for_queue_size(0, args.timeout_seconds, args.poll_interval_seconds)
    assert_worker_running(args.worker_service)


def stop_worker(service: str) -> None:
    run(["docker-compose", "stop", service])


def start_worker(service: str) -> None:
    run(["docker-compose", "start", service])


def assert_worker_stopped(service: str) -> None:
    output = run(["docker-compose", "ps", service], capture_output=True)
    if "Up" in output:
        raise SystemExit(f"worker service {service} is still up:\n{output}")
    print(output.rstrip(), flush=True)


def assert_worker_running(service: str) -> None:
    output = run(["docker-compose", "ps", service], capture_output=True)
    if "Up" not in output:
        raise SystemExit(f"worker service {service} did not come back up:\n{output}")
    print(output.rstrip(), flush=True)


def run_event_burst(events: int, pause_seconds: int) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "generate_events.py"),
        "--count",
        str(events),
        "--pause-seconds",
        str(pause_seconds),
    ]
    run(command)


def wait_for_queue_size(expected: int, timeout_seconds: int, poll_interval_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while True:
        queue_size = read_queue_size()
        print(f"queue={queue_size}", flush=True)
        if queue_size == expected:
            return
        if time.time() >= deadline:
            raise SystemExit(f"timed out waiting for queue size {expected}, last seen {queue_size}")
        time.sleep(poll_interval_seconds)


def read_queue_size() -> int:
    with urllib.request.urlopen(QUEUE_URL, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return int(payload["message_count"])


def run(command: list[str], capture_output: bool = False) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture_output,
    )
    return completed.stdout if capture_output else ""


if __name__ == "__main__":
    main()
