package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"sort"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	_ "modernc.org/sqlite"
)

type event struct {
	SiteID    string `json:"site_id"`
	PageURL   string `json:"page_url"`
	LCPMS     int    `json:"lcp_ms"`
	Timestamp string `json:"timestamp"`
	SessionID string `json:"session_id"`
}

var (
	eventsProcessed = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "worker_events_processed_total",
		Help: "Events processed by the aggregate worker.",
	})
	eventsFailed = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "worker_events_failed_total",
		Help: "Events the worker failed to process.",
	})
)

func main() {
	prometheus.MustRegister(eventsProcessed, eventsFailed)

	ctx := context.Background()
	db, err := openDB(env("DATABASE_PATH", "/data/coframe.db"))
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	client, err := redisClient(env("REDIS_URL", "redis://localhost:6379/0"))
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close()

	queue := env("EVENT_QUEUE", "page-events")
	go serveMetrics()

	log.Printf("worker started queue=%s", queue)
	for {
		item, err := client.BLPop(ctx, 5*time.Second, queue).Result()
		if errors.Is(err, redis.Nil) {
			continue
		}
		if err != nil {
			log.Printf("redis pop failed: %v", err)
			time.Sleep(time.Second)
			continue
		}
		if len(item) != 2 {
			continue
		}
		if err := process(ctx, db, []byte(item[1])); err != nil {
			eventsFailed.Inc()
			log.Printf("process failed: %v", err)
			continue
		}
		eventsProcessed.Inc()
	}
}

func openDB(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	_, err = db.Exec(`
		PRAGMA journal_mode=WAL;
		CREATE TABLE IF NOT EXISTS raw_events (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			site_id TEXT NOT NULL,
			page_url TEXT NOT NULL,
			lcp_ms INTEGER NOT NULL,
			timestamp TEXT NOT NULL,
			session_id TEXT NOT NULL
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
	`)
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

func redisClient(rawURL string) (*redis.Client, error) {
	opts, err := redis.ParseURL(rawURL)
	if err != nil {
		return nil, err
	}
	return redis.NewClient(opts), nil
}

func process(ctx context.Context, db *sql.DB, body []byte) error {
	var ev event
	if err := json.Unmarshal(body, &ev); err != nil {
		return err
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	_, err = tx.ExecContext(ctx,
		"INSERT INTO raw_events (site_id, page_url, lcp_ms, timestamp, session_id) VALUES (?, ?, ?, ?, ?)",
		ev.SiteID, ev.PageURL, ev.LCPMS, ev.Timestamp, ev.SessionID,
	)
	if err != nil {
		return err
	}

	values, err := lcpValues(ctx, tx, ev.SiteID, ev.PageURL)
	if err != nil {
		return err
	}
	p75 := percentile(values, 0.75)

	_, err = tx.ExecContext(ctx, `
		INSERT INTO page_aggregates
			(site_id, page_url, event_count, p75_lcp_ms, last_seen_timestamp, updated_at)
		SELECT site_id, page_url, COUNT(*), ?, MAX(timestamp), ?
		FROM raw_events
		WHERE site_id = ? AND page_url = ?
		GROUP BY site_id, page_url
		ON CONFLICT(site_id, page_url) DO UPDATE SET
			event_count = excluded.event_count,
			p75_lcp_ms = excluded.p75_lcp_ms,
			last_seen_timestamp = excluded.last_seen_timestamp,
			updated_at = excluded.updated_at
	`, p75, time.Now().UTC().Format(time.RFC3339), ev.SiteID, ev.PageURL)
	if err != nil {
		return err
	}
	return tx.Commit()
}

func lcpValues(ctx context.Context, tx *sql.Tx, siteID string, pageURL string) ([]int, error) {
	rows, err := tx.QueryContext(ctx,
		"SELECT lcp_ms FROM raw_events WHERE site_id = ? AND page_url = ? ORDER BY lcp_ms ASC",
		siteID, pageURL,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var values []int
	for rows.Next() {
		var value int
		if err := rows.Scan(&value); err != nil {
			return nil, err
		}
		values = append(values, value)
	}
	return values, rows.Err()
}

func percentile(values []int, p float64) int {
	if len(values) == 0 {
		return 0
	}
	sort.Ints(values)
	index := int(float64(len(values)-1) * p)
	return values[index]
}

func serveMetrics() {
	http.Handle("/metrics", promhttp.Handler())
	http.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})
	log.Fatal(http.ListenAndServe(":9101", nil))
}

func env(key string, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}
