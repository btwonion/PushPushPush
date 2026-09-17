from datetime import datetime, timedelta
import unittest

from gi.repository import GLib

from pushpushpush.app import (
    PushPushPushApp,
    _graph_point,
    _graph_snap_index,
    _graph_y_scale,
)
from pushpushpush.core import Settings


class TestReminderTests(unittest.TestCase):
    def test_clock_opens_overdue_reminder_after_suspend(self):
        calls = []

        class FakeApp:
            next_due = datetime.now() - timedelta(seconds=1)
            settings_window = None
            reminder_window = None

            def _remove_timer(self):
                calls.append("remove-timer")

            def show_reminder(self):
                calls.append("show-reminder")

            def _update_indicator_status(self):
                calls.append("update-status")

        app = FakeApp()
        result = PushPushPushApp._clock_tick(app)

        self.assertEqual(
            calls, ["remove-timer", "show-reminder", "update-status"]
        )
        self.assertIsNone(app.next_due)
        self.assertEqual(result, GLib.SOURCE_CONTINUE)

    def test_clock_leaves_future_reminder_scheduled(self):
        calls = []

        class FakeApp:
            next_due = datetime.now() + timedelta(minutes=1)
            settings_window = None
            reminder_window = None

            def _remove_timer(self):
                calls.append("remove-timer")

            def show_reminder(self):
                calls.append("show-reminder")

            def _update_indicator_status(self):
                calls.append("update-status")

        app = FakeApp()
        PushPushPushApp._clock_tick(app)

        self.assertEqual(calls, ["update-status"])

    def test_showing_test_reminder_resets_timer_before_opening_popup(self):
        calls = []

        class FakeApp:
            settings = Settings(interval_minutes=45)

            def _schedule_seconds(self, seconds):
                calls.append(("schedule", seconds))

            def show_reminder(self):
                calls.append(("show", None))

        PushPushPushApp.show_test_reminder(FakeApp())

        self.assertEqual(calls, [("schedule", 45 * 60), ("show", None)])

    def test_test_reminder_does_nothing_while_paused(self):
        calls = []

        class FakeApp:
            settings = Settings(enabled=False)

            def _schedule_seconds(self, seconds):
                calls.append(("schedule", seconds))

            def show_reminder(self):
                calls.append(("show", None))

        PushPushPushApp.show_test_reminder(FakeApp())

        self.assertEqual(calls, [])


class GraphTooltipTests(unittest.TestCase):
    def test_hover_snaps_to_the_nearest_x_entry(self):
        self.assertEqual(_graph_snap_index(201, 540, 14), 4)
        self.assertEqual(_graph_snap_index(220, 540, 14), 5)

    def test_hover_is_inactive_outside_the_plot(self):
        self.assertIsNone(_graph_snap_index(47, 540, 14))
        self.assertIsNone(_graph_snap_index(523, 540, 14))


if __name__ == "__main__":
    unittest.main()
