from __future__ import annotations

import json
import math
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, HttpUrl
from psycopg import Connection, connect
from psycopg.rows import dict_row
from redis import Redis


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://coframe:coframe@localhost:5432/coframe")
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
    experiment: str | None = Field(default=None, max_length=80)


class SiteConfig(BaseModel):
    site_id: str
    sampling_rate: float
    active_experiments: list[str]


class QueueStatus(BaseModel):
    queue_name: str
    message_count: int


class ExperimentAggregate(BaseModel):
    site_id: str
    experiment: str
    event_count: int
    p75_lcp_ms: int
    last_seen_timestamp: str | None
    updated_at: str | None


@contextmanager
def db() -> Any:
    conn: Connection[Any] = connect(DATABASE_URL, row_factory=dict_row)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_configs (
                site_id TEXT PRIMARY KEY,
                sampling_rate DOUBLE PRECISION NOT NULL,
                active_experiments TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS page_aggregates (
                site_id TEXT NOT NULL,
                page_url TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                p75_lcp_ms INTEGER NOT NULL,
                last_seen_timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (site_id, page_url)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_events (
                id BIGSERIAL PRIMARY KEY,
                site_id TEXT NOT NULL,
                page_url TEXT NOT NULL,
                lcp_ms INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
            """
        )
        conn.execute("ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS experiment TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_aggregates (
                site_id TEXT NOT NULL,
                experiment TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                p75_lcp_ms INTEGER NOT NULL,
                last_seen_timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (site_id, experiment)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO site_configs
                (site_id, sampling_rate, active_experiments)
            VALUES
                ('demo', 1.0, '["hero-copy", "checkout-flow"]')
            ON CONFLICT (site_id) DO NOTHING
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    redis.ping()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    with db() as conn:
        conn.execute("SELECT 1")
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
                "SELECT site_id, sampling_rate, active_experiments FROM site_configs WHERE site_id = %s",
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
                WHERE site_id = %s
                ORDER BY event_count DESC, page_url ASC
                LIMIT %s
                """,
                (site_id, limit),
            ).fetchall()
        return {"site_id": site_id, "pages": [dict(row) for row in rows]}


@app.get("/experiments", response_model=list[ExperimentAggregate])
def list_experiments(site_id: str = Query(default="demo")) -> list[ExperimentAggregate]:
    with REQUEST_SECONDS.labels("/experiments").time():
        with db() as conn:
            config_row = conn.execute(
                "SELECT active_experiments FROM site_configs WHERE site_id = %s",
                (site_id,),
            ).fetchone()
            if config_row is None:
                raise HTTPException(status_code=404, detail="site config not found")
            active_experiments = json.loads(config_row["active_experiments"])
            rows = conn.execute(
                """
                SELECT experiment, event_count, p75_lcp_ms, last_seen_timestamp, updated_at
                FROM experiment_aggregates
                WHERE site_id = %s
                """,
                (site_id,),
            ).fetchall()
            aggregates_by_experiment = {row["experiment"]: row for row in rows}

        return [
            ExperimentAggregate(
                site_id=site_id,
                experiment=experiment,
                event_count=aggregates_by_experiment.get(experiment, {}).get("event_count", 0),
                p75_lcp_ms=aggregates_by_experiment.get(experiment, {}).get("p75_lcp_ms", 0),
                last_seen_timestamp=aggregates_by_experiment.get(experiment, {}).get("last_seen_timestamp"),
                updated_at=aggregates_by_experiment.get(experiment, {}).get("updated_at"),
            )
            for experiment in active_experiments
        ]


@app.get("/queue", response_model=QueueStatus)
def queue_status() -> QueueStatus:
    with REQUEST_SECONDS.labels("/queue").time():
        return QueueStatus(queue_name=EVENT_QUEUE, message_count=int(redis.llen(EVENT_QUEUE)))


@app.get("/trend")
def list_trend(
    site_id: str = Query(default="demo"),
    limit: int = Query(default=30, ge=1, le=120),
    window_seconds: int | None = Query(default=None),
    window_minutes: int | None = Query(default=1),
) -> dict[str, Any]:
    resolved_window_seconds = resolve_window_seconds(window_seconds, window_minutes)

    with REQUEST_SECONDS.labels("/trend").time():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT page_url, experiment, lcp_ms, timestamp
                FROM raw_events
                WHERE site_id = %s
                ORDER BY timestamp ASC, id ASC
                """,
                (site_id,),
            ).fetchall()
        windows = bucket_trend(rows, limit, resolved_window_seconds)
        series = bucket_trend_by_experiment(rows, limit, resolved_window_seconds)
        return {
            "site_id": site_id,
            "limit": limit,
            "window_seconds": resolved_window_seconds,
            "window_minutes": resolved_window_seconds / 60,
            "windows": windows,
            "series": series,
        }


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def normalize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def bucket_trend(
    rows: list[dict[str, Any]],
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


def bucket_trend_by_experiment(
    rows: list[dict[str, Any]],
    limit: int,
    window_seconds: int,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    parsed_rows = [(parse_timestamp(row["timestamp"]), normalize_experiment(row.get("experiment")), row) for row in rows]
    anchor = end_at or datetime.now(timezone.utc)
    current_bucket = floor_to_bucket(anchor, window_seconds)
    first_bucket = current_bucket - ((limit - 1) * window_seconds)
    window_starts = [first_bucket + (index * window_seconds) for index in range(limit)]
    window_ends = [min(window_start + window_seconds, int(anchor.timestamp())) for window_start in window_starts]

    buckets_by_experiment: dict[str, dict[int, list[int]]] = {}
    for timestamp, experiment, row in parsed_rows:
        bucket_start = floor_to_bucket(timestamp, window_seconds)
        if bucket_start < first_bucket or bucket_start > current_bucket:
            continue
        buckets_by_experiment.setdefault(experiment, {window_start: [] for window_start in window_starts})
        buckets_by_experiment[experiment][bucket_start].append(row["lcp_ms"])

    series = []
    for experiment in sorted(buckets_by_experiment, key=experiment_sort_key):
        buckets = buckets_by_experiment[experiment]
        series.append(
            {
                "experiment": experiment,
                "label": experiment,
                "windows": [
                    {
                        "window_start": format_utc(window_start),
                        "window_end": format_utc(window_end),
                        "event_count": len(buckets[window_start]),
                        "p75_lcp_ms": percentile(buckets[window_start], 0.75),
                    }
                    for window_start, window_end in zip(window_starts, window_ends)
                ],
            }
        )
    return series


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalize_experiment(value: str | None) -> str:
    if value is None:
        return "unknown"
    cleaned = value.strip()
    return cleaned or "unknown"


def experiment_sort_key(value: str) -> tuple[int, str]:
    if value == "unknown":
        return (0, value)
    return (1, value)


def percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = math.floor((len(ordered) - 1) * p)
    return ordered[index]


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
