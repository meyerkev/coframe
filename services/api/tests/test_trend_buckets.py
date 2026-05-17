from datetime import datetime, timezone
import unittest

from app.main import bucket_trend, floor_to_bucket, format_utc


class Row(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


class TrendBucketTest(unittest.TestCase):
    def test_floor_to_bucket_uses_utc_wall_clock_boundaries(self):
        timestamp = datetime(2026, 5, 17, 16, 42, 37, 123456, tzinfo=timezone.utc)

        expected = {
            15: "2026-05-17T16:42:30Z",
            30: "2026-05-17T16:42:30Z",
            60: "2026-05-17T16:42:00Z",
            300: "2026-05-17T16:40:00Z",
            600: "2026-05-17T16:40:00Z",
            1200: "2026-05-17T16:40:00Z",
            1800: "2026-05-17T16:30:00Z",
            3600: "2026-05-17T16:00:00Z",
        }

        for window_seconds, bucket_start in expected.items():
            with self.subTest(window_seconds=window_seconds):
                self.assertEqual(format_utc(floor_to_bucket(timestamp, window_seconds)), bucket_start)

    def test_bucket_trend_returns_aligned_consecutive_windows(self):
        rows = [
            Row(timestamp="2026-05-17T16:04:59Z", lcp_ms=100),
            Row(timestamp="2026-05-17T16:05:00Z", lcp_ms=200),
            Row(timestamp="2026-05-17T16:09:59Z", lcp_ms=300),
            Row(timestamp="2026-05-17T16:10:00Z", lcp_ms=400),
        ]

        windows = bucket_trend(
            rows,
            limit=3,
            window_seconds=300,
            end_at=datetime(2026, 5, 17, 16, 11, tzinfo=timezone.utc),
        )

        self.assertEqual(
            [window["window_start"] for window in windows],
            [
                "2026-05-17T16:00:00Z",
                "2026-05-17T16:05:00Z",
                "2026-05-17T16:10:00Z",
            ],
        )
        self.assertEqual(
            [window["window_end"] for window in windows],
            [
                "2026-05-17T16:05:00Z",
                "2026-05-17T16:10:00Z",
                "2026-05-17T16:11:00Z",
            ],
        )
        self.assertEqual([window["event_count"] for window in windows], [1, 2, 1])
        self.assertEqual([window["p75_lcp_ms"] for window in windows], [100, 200, 400])

    def test_bucket_trend_anchors_to_now_instead_of_latest_event(self):
        rows = [
            Row(timestamp="2026-05-17T16:04:59Z", lcp_ms=100),
        ]

        windows = bucket_trend(
            rows,
            limit=3,
            window_seconds=300,
            end_at=datetime(2026, 5, 17, 16, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(
            [window["window_start"] for window in windows],
            [
                "2026-05-17T16:05:00Z",
                "2026-05-17T16:10:00Z",
                "2026-05-17T16:15:00Z",
            ],
        )
        self.assertEqual(
            [window["window_end"] for window in windows],
            [
                "2026-05-17T16:10:00Z",
                "2026-05-17T16:15:00Z",
                "2026-05-17T16:15:00Z",
            ],
        )
        self.assertEqual([window["event_count"] for window in windows], [0, 0, 0])
        self.assertEqual([window["p75_lcp_ms"] for window in windows], [0, 0, 0])

    def test_bucket_trend_supports_subminute_windows(self):
        rows = [
            Row(timestamp="2026-05-17T16:42:00Z", lcp_ms=100),
            Row(timestamp="2026-05-17T16:42:14Z", lcp_ms=200),
            Row(timestamp="2026-05-17T16:42:15Z", lcp_ms=300),
            Row(timestamp="2026-05-17T16:42:29Z", lcp_ms=400),
        ]

        windows = bucket_trend(
            rows,
            limit=3,
            window_seconds=15,
            end_at=datetime(2026, 5, 17, 16, 42, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(
            [window["window_start"] for window in windows],
            [
                "2026-05-17T16:42:00Z",
                "2026-05-17T16:42:15Z",
                "2026-05-17T16:42:30Z",
            ],
        )
        self.assertEqual(
            [window["window_end"] for window in windows],
            [
                "2026-05-17T16:42:15Z",
                "2026-05-17T16:42:30Z",
                "2026-05-17T16:42:30Z",
            ],
        )
        self.assertEqual([window["event_count"] for window in windows], [2, 2, 0])
        self.assertEqual([window["p75_lcp_ms"] for window in windows], [100, 300, 0])


if __name__ == "__main__":
    unittest.main()
