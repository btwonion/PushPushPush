from pathlib import Path
import random
import tempfile
import unittest

from datetime import date, datetime, timezone

from pushpushpush.core import (
    HistoryEntry,
    Settings,
    daily_pushup_totals,
    load_history,
    load_settings,
    record_completion,
    sample_pushups,
    save_history,
    save_settings,
)


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(Settings(), Settings(30, 10, 9, True))

    def test_validation_clamps_unsafe_values(self):
        self.assertEqual(Settings(-2, 0, -4, True).validated(), Settings(1, 1, 0, True))

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            expected = Settings(45, 20, 16, False)
            save_settings(expected, path)
            self.assertEqual(load_settings(path), expected)

    def test_invalid_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(load_settings(path), Settings())

    def test_wrong_json_shape_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(load_settings(path), Settings())


class SamplingTests(unittest.TestCase):
    def test_zero_variance_is_constant(self):
        settings = Settings(mean_pushups=17, variance=0)
        self.assertEqual(sample_pushups(settings, random.Random(1)), 17)

    def test_sample_is_never_below_one(self):
        settings = Settings(mean_pushups=1, variance=10_000)
        rng = random.Random(4)
        self.assertTrue(all(sample_pushups(settings, rng) >= 1 for _ in range(100)))

    def test_seeded_sample_is_repeatable(self):
        settings = Settings(mean_pushups=10, variance=9)
        self.assertEqual(
            sample_pushups(settings, random.Random(42)),
            sample_pushups(settings, random.Random(42)),
        )


class HistoryTests(unittest.TestCase):
    def test_history_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            expected = [
                HistoryEntry("2026-09-10T12:00:00+00:00", 10),
                HistoryEntry("2026-09-10T12:30:00+00:00", 12),
            ]
            save_history(expected, path)
            self.assertEqual(load_history(path), expected)

    def test_record_completion_appends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            instant = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
            entry = record_completion(15, path, instant)
            self.assertEqual(entry, HistoryEntry("2026-09-10T14:30:00+00:00", 15))
            self.assertEqual(load_history(path), [entry])

    def test_invalid_history_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(load_history(path), [])

    def test_daily_totals_cover_the_last_14_calendar_days(self):
        entries = [
            HistoryEntry("2026-08-28T12:00:00+00:00", 7),
            HistoryEntry("2026-09-09T10:00:00+00:00", 10),
            HistoryEntry("2026-09-09T16:00:00+00:00", 12),
            HistoryEntry("2026-09-10T08:00:00+00:00", 8),
        ]

        totals = daily_pushup_totals(entries, end_date=date(2026, 9, 10))

        self.assertEqual(len(totals), 14)
        self.assertEqual(totals[0], (date(2026, 8, 28), 7))
        self.assertEqual(totals[-2], (date(2026, 9, 9), 22))
        self.assertEqual(totals[-1], (date(2026, 9, 10), 8))
        self.assertEqual(totals[1], (date(2026, 8, 29), 0))

    def test_daily_totals_ignore_entries_outside_the_window(self):
        entries = [
            HistoryEntry("2026-08-27T12:00:00+00:00", 99),
            HistoryEntry("2026-09-11T12:00:00+00:00", 99),
        ]

        totals = daily_pushup_totals(entries, end_date=date(2026, 9, 10))

        self.assertTrue(all(total == 0 for _day, total in totals))


if __name__ == "__main__":
    unittest.main()
