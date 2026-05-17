from __future__ import annotations

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, HttpUrl
from redis import Redis


DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/coframe.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
EVENT_QUEUE = os.getenv("EVENT_QUEUE", "page-events")

EVENTS_ACCEPTED = Counter("api_events_accepted_total", "Events accepted by the ingest API")
CONFIG_READS = Counter("api_config_reads_total", "SDK config reads", ["site_id"])
REQUEST_SECONDS = Histogram("api_request_seconds", "API request latency", ["endpoint"])
ALLOWED_WINDOW_SECONDS = {15, 30, 60, 300, 600, 1200, 1800, 3600}

app = FastAPI(title="Coframe Performance API")
redis = Redis.from_url(REDIS_URL, decode_responses=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PerformanceEvent(BaseModel):
    site_id: str = Field(min_length=1, max_length=80)
    page_url: str | HttpUrl
    lcp_ms: int = Field(ge=0, le=120_000)
    timestamp: datetime
    session_id: str = Field(min_length=1, max_length=120)


class SiteConfig(BaseModel):
    site_id: str
    sampling_rate: float
    active_experiments: list[str]


class QueueStatus(BaseModel):
    queue_name: str
    message_count: int


@contextmanager
def db() -> Any:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS site_configs (
                site_id TEXT PRIMARY KEY,
                sampling_rate REAL NOT NULL,
                active_experiments TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS page_aggregates (
                site_id TEXT NOT NULL,
                page_url TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                p75_lcp_ms INTEGER NOT NULL,
                last_seen_timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (site_id, page_url)
            );

            CREATE TABLE IF NOT EXISTS raw_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                page_url TEXT NOT NULL,
                lcp_ms INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO site_configs
                (site_id, sampling_rate, active_experiments)
            VALUES
                ('demo', 1.0, '["hero-copy", "checkout-flow"]')
            """
        )
        conn.commit()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    redis.ping()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    redis.ping()
    return {"status": "ok"}


@app.post("/events", status_code=202)
def ingest_event(event: PerformanceEvent) -> dict[str, str]:
    with REQUEST_SECONDS.labels("/events").time():
        payload = event.model_dump(mode="json")
        payload["timestamp"] = normalize_timestamp(event.timestamp)
        redis.rpush(EVENT_QUEUE, json.dumps(payload))
        EVENTS_ACCEPTED.inc()
        return {"status": "queued"}


@app.get("/config/{site_id}", response_model=SiteConfig)
def get_config(site_id: str) -> SiteConfig:
    with REQUEST_SECONDS.labels("/config/{site_id}").time():
        with db() as conn:
            row = conn.execute(
                "SELECT site_id, sampling_rate, active_experiments FROM site_configs WHERE site_id = ?",
                (site_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="site config not found")
        CONFIG_READS.labels(site_id).inc()
        return SiteConfig(
            site_id=row["site_id"],
            sampling_rate=row["sampling_rate"],
            active_experiments=json.loads(row["active_experiments"]),
        )


@app.get("/aggregates")
def list_aggregates(
    site_id: str = Query(default="demo"),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    with REQUEST_SECONDS.labels("/aggregates").time():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT site_id, page_url, event_count, p75_lcp_ms, last_seen_timestamp, updated_at
                FROM page_aggregates
                WHERE site_id = ?
                ORDER BY event_count DESC, page_url ASC
                LIMIT ?
                """,
                (site_id, limit),
            ).fetchall()
        return {"site_id": site_id, "pages": [dict(row) for row in rows]}


@app.get("/queue", response_model=QueueStatus)
def queue_status() -> QueueStatus:
    with REQUEST_SECONDS.labels("/queue").time():
        return QueueStatus(queue_name=EVENT_QUEUE, message_count=int(redis.llen(EVENT_QUEUE)))


@app.get("/trend")
def list_trend(
    site_id: str = Query(default="demo"),
    limit: int = Query(default=30, ge=5, le=120),
    window_seconds: int | None = Query(default=None),
    window_minutes: int | None = Query(default=1),
) -> dict[str, Any]:
    resolved_window_seconds = resolve_window_seconds(window_seconds, window_minutes)

    with REQUEST_SECONDS.labels("/trend").time():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT page_url, lcp_ms, timestamp
                FROM raw_events
                WHERE site_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (site_id,),
            ).fetchall()
        windows = bucket_trend(rows, limit, resolved_window_seconds)
        return {
            "site_id": site_id,
            "limit": limit,
            "window_seconds": resolved_window_seconds,
            "window_minutes": resolved_window_seconds / 60,
            "windows": windows,
        }


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def normalize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def bucket_trend(
    rows: list[sqlite3.Row],
    limit: int,
    window_seconds: int,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    parsed_rows = [(parse_timestamp(row["timestamp"]), row) for row in rows]
    anchor = end_at or datetime.now(timezone.utc)
    current_bucket = floor_to_bucket(anchor, window_seconds)
    first_bucket = current_bucket - ((limit - 1) * window_seconds)

    buckets: dict[int, list[int]] = {first_bucket + (index * window_seconds): [] for index in range(limit)}
    for timestamp, row in parsed_rows:
        bucket_start = floor_to_bucket(timestamp, window_seconds)
        if bucket_start in buckets:
            buckets[bucket_start].append(row["lcp_ms"])

    windows = []
    for bucket_start in sorted(buckets):
        values = sorted(buckets[bucket_start])
        p75_lcp_ms = 0
        if values:
            p75_lcp_ms = values[math.floor((len(values) - 1) * 0.75)]
        window_end = min(bucket_start + window_seconds, int(anchor.timestamp()))
        windows.append(
            {
                "window_start": format_utc(bucket_start),
                "window_end": format_utc(window_end),
                "event_count": len(values),
                "p75_lcp_ms": p75_lcp_ms,
            }
        )
    return windows


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def floor_to_bucket(value: datetime, window_seconds: int) -> int:
    value = value.astimezone(timezone.utc)
    epoch_seconds = int(value.timestamp())
    bucket_epoch = epoch_seconds - (epoch_seconds % window_seconds)
    return bucket_epoch


def resolve_window_seconds(window_seconds: int | None, window_minutes: int | None) -> int:
    if window_seconds is not None:
        if window_seconds not in ALLOWED_WINDOW_SECONDS:
            raise HTTPException(status_code=400, detail="window_seconds must be one of 15, 30, 60, 300, 600, 1200, 1800, 3600")
        return window_seconds

    if window_minutes is None:
        window_minutes = 1

    resolved_window_seconds = window_minutes * 60
    if resolved_window_seconds not in ALLOWED_WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="window_minutes must be one of 1, 5, 10, 20, 30, 60")
    return resolved_window_seconds


def format_utc(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")
