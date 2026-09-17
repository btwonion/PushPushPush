"""Native GTK application for PushPushPush."""

from __future__ import annotations

from datetime import datetime, timedelta
from importlib.resources import files
import math
import subprocess
import sys

import cairo
import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .core import (
    Settings,
    daily_pushup_totals,
    load_history,
    load_settings,
    record_completion,
    sample_pushups,
    save_settings,
)


APP_ID = "com.local.PushPushPush"
GRAPH_LEFT = 48.0
GRAPH_RIGHT = 18.0
GRAPH_TOP = 18.0
GRAPH_BOTTOM = 42.0


def _graph_y_scale(values: list[int]) -> tuple[float, float]:
    """Return a readable tick step and four-tick y-axis maximum."""
    maximum = max(values + [1])
    raw_step = maximum / 4
    magnitude = 10 ** max(0, len(str(max(1, int(raw_step)))) - 1)
    normalized = raw_step / magnitude
    if normalized <= 1:
        factor = 1
    elif normalized <= 2:
        factor = 2
    elif normalized <= 2.5:
        factor = 2.5
    elif normalized <= 5:
        factor = 5
    else:
        factor = 10
    step = max(1.0, factor * magnitude)
    return step, step * 4


def _graph_point(
    index: int,
    value: int,
    point_count: int,
    width: int,
    height: int,
    axis_maximum: float,
) -> tuple[float, float]:
    chart_width = max(1.0, width - GRAPH_LEFT - GRAPH_RIGHT)
    chart_height = max(1.0, height - GRAPH_TOP - GRAPH_BOTTOM)
    x = GRAPH_LEFT + chart_width * index / (point_count - 1)
    y = GRAPH_TOP + chart_height * (1 - value / axis_maximum)
    return x, y


def _graph_snap_index(
    pointer_x: float, width: int, point_count: int
) -> int | None:
    """Snap an in-chart pointer x coordinate to its nearest data point."""
    if point_count < 1 or pointer_x < GRAPH_LEFT or pointer_x > width - GRAPH_RIGHT:
        return None
    if point_count == 1:
        return 0
    chart_width = max(1.0, width - GRAPH_LEFT - GRAPH_RIGHT)
    position = (pointer_x - GRAPH_LEFT) / chart_width * (point_count - 1)
    return min(point_count - 1, max(0, int(position + 0.5)))


class PushPushPushApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.settings = load_settings()
        self.history = load_history()
        self.background_start = "--background" in sys.argv
        self.remind_now = "--remind-now" in sys.argv
        self.settings_window: SettingsWindow | None = None
        self.reminder_window: ReminderWindow | None = None
        self.timer_id: int | None = None
        self.clock_id: int | None = None
        self.next_due: datetime | None = None
        self.pending_count: int | None = None
        self.indicator_process: subprocess.Popen[bytes] | None = None
        self._held = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_string(files("pushpushpush").joinpath("style.css").read_text())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        if not self._held:
            self.hold()
            self._held = True
        self._install_actions()
        self._start_indicator()
        self._start_clock()
        if self.settings.enabled:
            self.schedule_regular()

    def _install_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        show_action = Gio.SimpleAction.new("show-settings", None)
        show_action.connect("activate", lambda *_: self.show_settings())
        self.add_action(show_action)

        reminder_action = Gio.SimpleAction.new("show-reminder", None)
        reminder_action.connect("activate", lambda *_: self.show_reminder())
        self.add_action(reminder_action)

        toggle_action = Gio.SimpleAction.new("toggle-paused", None)
        toggle_action.connect(
            "activate", lambda *_: self.set_enabled(not self.settings.enabled)
        )
        self.add_action(toggle_action)

        self.timer_status_action = Gio.SimpleAction.new_stateful(
            "timer-status", None, GLib.Variant("s", "Timer · Starting…")
        )
        self.timer_status_action.set_enabled(False)
        self.add_action(self.timer_status_action)

        self.today_status_action = Gio.SimpleAction.new_stateful(
            "today-status", None, GLib.Variant("s", "Today · 0 push-ups")
        )
        self.today_status_action.set_enabled(False)
        self.add_action(self.today_status_action)
        self._update_indicator_status()

    def _start_indicator(self) -> None:
        try:
            self.indicator_process = subprocess.Popen(
                [sys.executable, "-m", "pushpushpush.indicator"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.indicator_process = None

    def do_activate(self) -> None:
        if self.background_start:
            self.background_start = False
            return
        if self.remind_now:
            self.remind_now = False
            self.show_reminder()
            return
        self.show_settings()

    def do_shutdown(self) -> None:
        self._remove_timer()
        if self.clock_id is not None:
            GLib.source_remove(self.clock_id)
            self.clock_id = None
        if self.indicator_process is not None:
            self.indicator_process.terminate()
            self.indicator_process = None
        Adw.Application.do_shutdown(self)

    def show_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
        self.settings_window.sync_from_settings()
        self.settings_window.present()

    @staticmethod
    def follow_color_scheme(widget: Gtk.Widget) -> None:
        """Mirror libadwaita's system light/dark preference on custom surfaces."""
        manager = Adw.StyleManager.get_default()

        def update(*_args: object) -> None:
            if manager.get_dark():
                widget.add_css_class("dark")
            else:
                widget.remove_css_class("dark")

        manager.connect("notify::dark", update)
        update()

    def _start_clock(self) -> None:
        self.clock_id = GLib.timeout_add_seconds(1, self._clock_tick)

    def _clock_tick(self) -> bool:
        # GLib timeout sources use a monotonic clock that pauses while the
        # computer is suspended.  Keep the wall-clock deadline authoritative
        # so sleep cannot silently push a reminder later.
        if self.next_due is not None and datetime.now() >= self.next_due:
            self._remove_timer()
            self.next_due = None
            self.show_reminder()
        self._update_indicator_status()
        if self.settings_window is not None:
            self.settings_window.update_status()
        if self.reminder_window is not None:
            self.reminder_window.update_next_label()
        return GLib.SOURCE_CONTINUE

    def _update_indicator_status(self) -> None:
        if not self.settings.enabled:
            timer_text = "Timer · Paused"
        elif self.reminder_window is not None:
            timer_text = "Timer · Reminder open"
        elif self.next_due is not None:
            remaining = max(0, int((self.next_due - datetime.now()).total_seconds()))
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = (
                f"{hours:d}:{minutes:02d}:{seconds:02d}"
                if hours
                else f"{minutes:d}:{seconds:02d}"
            )
            timer_text = f"Next reminder · {countdown}"
        else:
            timer_text = "Timer · Starting…"

        today = datetime.now().astimezone().date()
        completed_today = sum(
            entry.count
            for entry in self.history
            if datetime.fromisoformat(entry.completed_at).astimezone().date() == today
        )
        unit = "push-up" if completed_today == 1 else "push-ups"
        self.timer_status_action.set_state(GLib.Variant("s", timer_text))
        self.today_status_action.set_state(
            GLib.Variant("s", f"Today · {completed_today:,} {unit}")
        )

    def _remove_timer(self) -> None:
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def _schedule_seconds(self, seconds: int) -> None:
        self._remove_timer()
        if not self.settings.enabled:
            self.next_due = None
            return
        self.next_due = datetime.now() + timedelta(seconds=seconds)
        self.timer_id = GLib.timeout_add_seconds(seconds, self._timer_fired)
        self._clock_tick()

    def schedule_regular(self) -> None:
        self.pending_count = None
        self._schedule_seconds(self.settings.interval_minutes * 60)

    def schedule_snooze(self) -> None:
        self._schedule_seconds(5 * 60)

    def _timer_fired(self) -> bool:
        self.timer_id = None
        self.next_due = None
        self.show_reminder()
        return GLib.SOURCE_REMOVE

    def show_reminder(self) -> None:
        if not self.settings.enabled:
            return
        if self.reminder_window is not None:
            self.reminder_window.present()
            return
        if self.pending_count is None:
            self.pending_count = sample_pushups(self.settings)
        self.reminder_window = ReminderWindow(self, self.pending_count)
        self.reminder_window.present()

    def show_test_reminder(self) -> None:
        """Show a preview without leaving the old reminder countdown running."""
        if not self.settings.enabled:
            return
        self._schedule_seconds(self.settings.interval_minutes * 60)
        self.show_reminder()

    def close_reminder(self) -> None:
        window, self.reminder_window = self.reminder_window, None
        if window is not None:
            window.force_close()

    def apply_settings(self, new_settings: Settings) -> None:
        was_enabled = self.settings.enabled
        self.settings = new_settings.validated()
        save_settings(self.settings)
        if self.settings.enabled:
            self.schedule_regular()
        else:
            self._remove_timer()
            self.next_due = None
            self.close_reminder()
        if self.settings_window is not None:
            self.settings_window.update_status()
        if was_enabled != self.settings.enabled:
            self.withdraw_notification("paused")

    def set_enabled(self, enabled: bool) -> None:
        updated = Settings(
            interval_minutes=self.settings.interval_minutes,
            mean_pushups=self.settings.mean_pushups,
            variance=self.settings.variance,
            enabled=enabled,
        )
        self.apply_settings(updated)


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, app: PushPushPushApp) -> None:
        super().__init__(application=app, title="PushPushPush")
        self.app = app
        self.set_default_size(540, 720)
        self.set_resizable(True)
        # Keep the process and reusable settings view alive when the user
        # closes this window; the scheduler continues in the background.
        self.set_hide_on_close(True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("app-surface")
        app.follow_color_scheme(root)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)
        header = Adw.HeaderBar()
        header.add_css_class("app-header")
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.stack)
        header.set_title_widget(switcher)
        menu = Gio.Menu()
        menu.append("Quit PushPushPush", "app.quit")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text("Application menu")
        header.pack_end(menu_button)
        root.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(28)
        content.set_margin_end(28)

        title = Gtk.Label(label="Make it your rhythm.", xalign=0)
        title.add_css_class("page-title")
        subtitle = Gtk.Label(
            label="Gentle movement breaks, on your schedule.", xalign=0, wrap=True
        )
        subtitle.add_css_class("secondary")
        content.append(title)
        content.append(subtitle)

        status_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_card.add_css_class("status-card")
        status_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.status_title = Gtk.Label(xalign=0)
        self.status_title.add_css_class("status-title")
        self.status_detail = Gtk.Label(xalign=0)
        self.status_detail.add_css_class("secondary")
        status_text.append(self.status_title)
        status_text.append(self.status_detail)
        status_text.set_hexpand(True)
        self.pause_button = Gtk.Button()
        self.pause_button.add_css_class("flat")
        self.pause_button.connect("clicked", self._toggle_enabled)
        status_card.append(status_text)
        status_card.append(self.pause_button)
        content.append(status_card)

        grid = Gtk.Grid(column_spacing=16, row_spacing=14)
        grid.add_css_class("settings-grid")
        section = Gtk.Label(label="REMINDERS", xalign=0)
        section.add_css_class("section-label")
        grid.attach(section, 0, 0, 2, 1)
        grid.attach(Gtk.Label(label="Remind me every", xalign=0), 0, 1, 1, 1)
        self.interval = self._spin(1, 480)
        grid.attach(self.interval, 1, 1, 1, 1)
        helper = Gtk.Label(label="minutes (1–480)", xalign=1)
        helper.add_css_class("secondary")
        grid.attach(helper, 0, 2, 2, 1)

        section2 = Gtk.Label(label="YOUR PUSH-UP SET", xalign=0)
        section2.add_css_class("section-label")
        section2.set_margin_top(10)
        grid.attach(section2, 0, 3, 2, 1)
        grid.attach(Gtk.Label(label="Average push-ups", xalign=0), 0, 4, 1, 1)
        self.mean = self._spin(1, 500)
        grid.attach(self.mean, 1, 4, 1, 1)
        grid.attach(Gtk.Label(label="Variance", xalign=0), 0, 5, 1, 1)
        self.variance = self._spin(0, 10_000)
        grid.attach(self.variance, 1, 5, 1, 1)
        self.variance_help = Gtk.Label(xalign=0, wrap=True)
        self.variance_help.add_css_class("secondary")
        self.variance_help.set_max_width_chars(46)
        grid.attach(self.variance_help, 0, 6, 2, 1)
        self.variance.connect("value-changed", self._update_variance_help)
        content.append(grid)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.try_button = Gtk.Button(label="Try a reminder")
        self.try_button.connect("clicked", lambda *_: self.app.show_test_reminder())
        save = Gtk.Button(label="Save settings")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        actions.append(self.try_button)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        actions.append(spacer)
        actions.append(save)
        content.append(actions)
        settings_scroll = Gtk.ScrolledWindow()
        settings_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        settings_scroll.set_child(content)
        self.stack.add_titled(settings_scroll, "settings", "Settings")

        statistics_scroll = Gtk.ScrolledWindow()
        statistics_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        statistics_scroll.set_child(self._build_statistics_page())
        self.stack.add_titled(statistics_scroll, "statistics", "Statistics")
        root.append(self.stack)
        self.set_content(root)
        self.refresh_statistics()

    @staticmethod
    def _spin(lower: int, upper: int) -> Gtk.SpinButton:
        spin = Gtk.SpinButton.new_with_range(lower, upper, 1)
        spin.set_width_chars(7)
        spin.set_halign(Gtk.Align.END)
        return spin

    def sync_from_settings(self) -> None:
        self.interval.set_value(self.app.settings.interval_minutes)
        self.mean.set_value(self.app.settings.mean_pushups)
        self.variance.set_value(self.app.settings.variance)
        self._update_variance_help()
        self.update_status()

    def _update_variance_help(self, *_args: object) -> None:
        standard_deviation = self.variance.get_value() ** 0.5
        self.variance_help.set_label(
            f"Higher variance adds variety. This equals a standard deviation of "
            f"{standard_deviation:g} reps. Results are rounded and never below 1."
        )

    def _save(self, *_args: object) -> None:
        self.app.apply_settings(
            Settings(
                interval_minutes=self.interval.get_value_as_int(),
                mean_pushups=self.mean.get_value_as_int(),
                variance=self.variance.get_value_as_int(),
                enabled=self.app.settings.enabled,
            )
        )
        self.status_detail.set_label("Settings saved · next reminder rescheduled")

    def _toggle_enabled(self, *_args: object) -> None:
        self.app.set_enabled(not self.app.settings.enabled)

    def update_status(self) -> None:
        enabled = self.app.settings.enabled
        self.try_button.set_sensitive(enabled)
        self.pause_button.set_label("Pause" if enabled else "Resume")
        if not enabled:
            self.status_title.set_label("Reminders paused")
            self.status_detail.set_label("Resume whenever you’re ready.")
        elif self.app.next_due:
            self.status_title.set_label("Reminders active")
            remaining = max(
                0, int((self.app.next_due - datetime.now()).total_seconds())
            )
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = (
                f"{hours:d}:{minutes:02d}:{seconds:02d}"
                if hours
                else f"{minutes:d}:{seconds:02d}"
            )
            self.status_detail.set_label(
                f"Next reminder in {countdown} · at {self.app.next_due.strftime('%H:%M')}"
            )
        elif self.app.reminder_window:
            self.status_title.set_label("Movement break ready")
            self.status_detail.set_label("Your reminder is open.")
        else:
            self.status_title.set_label("Reminders active")
            self.status_detail.set_label("The next break is being scheduled.")

    def _build_statistics_page(self) -> Gtk.Widget:
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(28)
        content.set_margin_end(28)

        title = Gtk.Label(label="Your progress", xalign=0)
        title.add_css_class("page-title")
        content.append(title)
        self.stats_summary = Gtk.Label(xalign=0, wrap=True)
        self.stats_summary.add_css_class("secondary")
        content.append(self.stats_summary)

        self.graph = Gtk.DrawingArea()
        self.graph.set_content_height(210)
        self.graph.set_hexpand(True)
        self.graph.add_css_class("graph-card")
        self.graph.set_draw_func(self._draw_graph)
        self._graph_hover_index: int | None = None
        graph_motion = Gtk.EventControllerMotion()
        graph_motion.connect("motion", self._update_graph_hover)
        graph_motion.connect("leave", self._clear_graph_hover)
        self.graph.add_controller(graph_motion)
        content.append(self.graph)

        self.graph_caption = Gtk.Label(xalign=0, wrap=True)
        self.graph_caption.add_css_class("secondary")
        content.append(self.graph_caption)

        recent_title = Gtk.Label(label="RECENT SETS", xalign=0)
        recent_title.add_css_class("section-label")
        recent_title.set_margin_top(8)
        content.append(recent_title)

        self.recent_list = Gtk.ListBox()
        self.recent_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.recent_list.add_css_class("recent-list")
        content.append(self.recent_list)
        return content

    def refresh_statistics(self) -> None:
        entries = self.app.history
        total = sum(entry.count for entry in entries)
        sets = len(entries)
        noun = "set" if sets == 1 else "sets"
        self.stats_summary.set_label(
            f"{total:,} push-ups across {sets:,} completed {noun}."
        )
        daily = daily_pushup_totals(entries)
        first_day, last_day = daily[0][0], daily[-1][0]
        self._graph_hover_index = None
        self.graph.queue_draw()
        self.graph_caption.set_label(
            f"Daily totals · {first_day.strftime('%d %b')}–{last_day.strftime('%d %b')}"
        )

        child = self.recent_list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.recent_list.remove(child)
            child = following

        if not entries:
            empty = Gtk.Label(label="Your completed sets will appear here.", xalign=0)
            empty.add_css_class("empty-history")
            self.recent_list.append(empty)
            return

        for entry in reversed(entries[-10:]):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(10)
            row.set_margin_bottom(10)
            row.set_margin_start(14)
            row.set_margin_end(14)
            instant = datetime.fromisoformat(entry.completed_at).astimezone()
            when = Gtk.Label(label=instant.strftime("%d %b · %H:%M"), xalign=0)
            when.add_css_class("secondary")
            when.set_hexpand(True)
            amount = Gtk.Label(
                label=f"{entry.count} push-up{'s' if entry.count != 1 else ''}"
            )
            amount.add_css_class("history-count")
            row.append(when)
            row.append(amount)
            self.recent_list.append(row)

    def _update_graph_hover(
        self, _controller: Gtk.EventControllerMotion, x: float, _y: float
    ) -> None:
        daily = daily_pushup_totals(self.app.history)
        index = _graph_snap_index(x, self.graph.get_width(), len(daily))
        if index == self._graph_hover_index:
            return
        self._graph_hover_index = index
        self.graph.queue_draw()

    def _clear_graph_hover(self, *_args: object) -> None:
        if self._graph_hover_index is not None:
            self._graph_hover_index = None
            self.graph.queue_draw()

    def _draw_graph(
        self,
        _area: Gtk.DrawingArea,
        context: object,
        width: int,
        height: int,
    ) -> None:
        daily = daily_pushup_totals(self.app.history)
        values = [total for _day, total in daily]
        dark = Adw.StyleManager.get_default().get_dark()
        grid = (0.31, 0.39, 0.36, 0.45) if dark else (0.72, 0.77, 0.72, 0.75)
        axis = (0.69, 0.77, 0.73, 0.9) if dark else (0.31, 0.42, 0.38, 0.9)
        text_color = (0.69, 0.75, 0.72, 1.0) if dark else (0.35, 0.42, 0.40, 1.0)
        line = (0.61, 0.85, 0.74, 1.0) if dark else (0.12, 0.35, 0.30, 1.0)
        card = (0.13, 0.17, 0.16, 1.0) if dark else (1.0, 1.0, 1.0, 1.0)
        tooltip_background = (
            (0.84, 0.93, 0.88, 0.98) if dark else (0.09, 0.23, 0.21, 0.98)
        )
        tooltip_foreground = (
            (0.09, 0.23, 0.21, 1.0) if dark else (1.0, 1.0, 1.0, 1.0)
        )
        left, right, top, bottom = (
            GRAPH_LEFT,
            GRAPH_RIGHT,
            GRAPH_TOP,
            GRAPH_BOTTOM,
        )
        chart_width = max(1.0, width - left - right)
        chart_height = max(1.0, height - top - bottom)

        # Four evenly spaced, human-friendly intervals keep zero visible and
        # ensure the highest daily total always fits on the y axis.
        step, axis_maximum = _graph_y_scale(values)

        context.select_font_face(
            "Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
        )
        context.set_font_size(10.0)

        def text_width(label: str) -> float:
            extents = context.text_extents(label)
            return extents.width

        def y_for(value: float) -> float:
            return top + chart_height * (1 - value / axis_maximum)

        context.set_line_width(1.0)
        context.set_source_rgba(*grid)
        for index in range(5):
            y = y_for(index * step)
            context.move_to(left, y)
            context.line_to(width - right, y)
        context.stroke()

        context.set_source_rgba(*axis)
        context.set_line_width(1.2)
        context.move_to(left, top)
        context.line_to(left, height - bottom)
        context.line_to(width - right, height - bottom)
        context.stroke()

        context.set_source_rgba(*text_color)
        for index in range(5):
            tick_value = index * step
            label = f"{tick_value:g}"
            y = y_for(tick_value)
            context.move_to(left - 8 - text_width(label), y + 3.5)
            context.show_text(label)

        for index, (day, _total) in enumerate(daily):
            x = left + chart_width * index / (len(daily) - 1)
            context.move_to(x, height - bottom)
            context.line_to(x, height - bottom + 4)
        context.stroke()

        label_indices = (0, 3, 6, 9, 13)
        for index in label_indices:
            label = daily[index][0].strftime("%d %b")
            x = left + chart_width * index / (len(daily) - 1)
            label_x = min(
                width - right - text_width(label),
                max(left, x - text_width(label) / 2),
            )
            context.move_to(label_x, height - bottom + 19)
            context.show_text(label)

        def point(index: int, value: int) -> tuple[float, float]:
            return _graph_point(
                index, value, len(values), width, height, axis_maximum
            )

        context.set_source_rgba(*line)
        context.set_line_width(3.0)
        for index, value in enumerate(values):
            x, y = point(index, value)
            if index == 0:
                context.move_to(x, y)
            else:
                context.line_to(x, y)
        context.stroke()
        for index, value in enumerate(values):
            x, y = point(index, value)
            context.arc(x, y, 4.5, 0, 6.283)
            context.fill()

        if self._graph_hover_index is None:
            return

        hover_index = self._graph_hover_index
        hover_x, hover_y = point(hover_index, values[hover_index])

        context.save()
        context.set_source_rgba(line[0], line[1], line[2], 0.5)
        context.set_line_width(1.5)
        context.set_dash([3.0, 4.0])
        context.move_to(hover_x, top)
        context.line_to(hover_x, height - bottom)
        context.stroke()
        context.restore()

        # A larger halo makes the snapped point feel anchored to the guide.
        context.set_source_rgba(*card)
        context.arc(hover_x, hover_y, 8.0, 0, math.tau)
        context.fill()
        context.set_source_rgba(*line)
        context.arc(hover_x, hover_y, 5.0, 0, math.tau)
        context.fill()

        day, count = daily[hover_index]
        unit = "push-up" if count == 1 else "push-ups"
        tooltip_label = f"{day.strftime('%d %b')} · {count} {unit}"
        context.select_font_face(
            "Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        context.set_font_size(10.0)
        text_extents = context.text_extents(tooltip_label)
        tooltip_width = text_extents.width + 20.0
        tooltip_height = 28.0
        tooltip_x = min(
            width - right - tooltip_width,
            max(left, hover_x - tooltip_width / 2),
        )
        if hover_y - tooltip_height - 10 >= top:
            tooltip_y = hover_y - tooltip_height - 10
        else:
            tooltip_y = min(
                height - bottom - tooltip_height - 4,
                hover_y + 10,
            )
        radius = 7.0
        context.new_sub_path()
        context.arc(
            tooltip_x + tooltip_width - radius,
            tooltip_y + radius,
            radius,
            -math.pi / 2,
            0,
        )
        context.arc(
            tooltip_x + tooltip_width - radius,
            tooltip_y + tooltip_height - radius,
            radius,
            0,
            math.pi / 2,
        )
        context.arc(
            tooltip_x + radius,
            tooltip_y + tooltip_height - radius,
            radius,
            math.pi / 2,
            math.pi,
        )
        context.arc(
            tooltip_x + radius,
            tooltip_y + radius,
            radius,
            math.pi,
            3 * math.pi / 2,
        )
        context.close_path()
        context.set_source_rgba(*tooltip_background)
        context.fill()

        text_x = tooltip_x + (tooltip_width - text_extents.width) / 2
        text_y = tooltip_y + (tooltip_height - text_extents.height) / 2
        context.move_to(
            text_x - text_extents.x_bearing,
            text_y - text_extents.y_bearing,
        )
        context.set_source_rgba(*tooltip_foreground)
        context.show_text(tooltip_label)


class ReminderWindow(Adw.ApplicationWindow):
    def __init__(self, app: PushPushPushApp, count: int) -> None:
        super().__init__(application=app, title="Time to move")
        self.app = app
        self.count = count
        self.handled = False
        self.set_default_size(440, 520)
        self.set_resizable(True)
        self.connect("close-request", self._on_close_request)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("reminder-surface")
        app.follow_color_scheme(root)
        header = Adw.HeaderBar()
        header.add_css_class("app-header")
        header.set_title_widget(Gtk.Label(label="PUSH PUSH PUSH"))
        settings_button = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_button.set_tooltip_text("Open settings")
        settings_button.connect("clicked", lambda *_: self.app.show_settings())
        header.pack_end(settings_button)
        root.append(header)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.content.set_margin_top(22)
        self.content.set_margin_bottom(22)
        self.content.set_margin_start(28)
        self.content.set_margin_end(28)

        heading = Gtk.Label(label="A little movement.\nA stronger day.", xalign=0)
        heading.add_css_class("hero-heading")
        self.content.append(heading)

        count_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        count_card.add_css_class("count-card")
        eyebrow = Gtk.Label(label="YOUR NEXT SET")
        eyebrow.add_css_class("section-label")
        number = Gtk.Label(label=str(count))
        number.add_css_class("rep-count")
        number.set_tooltip_text(f"{count} push-ups")
        unit = Gtk.Label(label="push-up" if count == 1 else "push-ups")
        unit.add_css_class("rep-unit")
        encouragement = Gtk.Label(label="One good set. You’ve got this.")
        encouragement.add_css_class("secondary")
        count_card.append(eyebrow)
        count_card.append(number)
        count_card.append(unit)
        count_card.append(encouragement)
        self.content.append(count_card)

        inclusive = Gtk.Label(label="Wall or knee push-ups count, too.", xalign=0)
        inclusive.add_css_class("secondary")
        self.content.append(inclusive)

        self.done_button = Gtk.Button(label=f"Done · {count} reps")
        self.done_button.add_css_class("primary-action")
        self.done_button.connect("clicked", self._done)
        self.content.append(self.done_button)

        secondary = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        secondary.set_halign(Gtk.Align.CENTER)
        snooze = Gtk.Button(label="Snooze 5 min")
        snooze.add_css_class("flat")
        snooze.connect("clicked", self._snooze)
        skip = Gtk.Button(label="Skip this round")
        skip.add_css_class("flat")
        skip.connect("clicked", self._skip)
        secondary.append(snooze)
        secondary.append(skip)
        self.content.append(secondary)

        self.next_label = Gtk.Label()
        self.next_label.add_css_class("secondary")
        self.content.append(self.next_label)
        root.append(self.content)
        self.set_content(root)
        self.update_next_label()

    def update_next_label(self) -> None:
        if self.app.next_due:
            label = f"Your next break is at {self.app.next_due.strftime('%H:%M')}"
        else:
            label = f"Next regular break in {self.app.settings.interval_minutes} min"
        self.next_label.set_label(label)

    def _done(self, *_args: object) -> None:
        if self.handled:
            return
        self.handled = True
        self.app.pending_count = None
        entry = record_completion(self.count)
        self.app.history.append(entry)
        if self.app.settings_window is not None:
            self.app.settings_window.refresh_statistics()
        self.done_button.set_label("Set complete. Nicely done.")
        self.done_button.set_sensitive(False)
        self.app.schedule_regular()
        GLib.timeout_add(1200, self._finish_done)

    def _finish_done(self) -> bool:
        self.app.close_reminder()
        return GLib.SOURCE_REMOVE

    def _snooze(self, *_args: object) -> None:
        if self.handled:
            return
        self.handled = True
        self.app.schedule_snooze()
        self.app.close_reminder()

    def _skip(self, *_args: object) -> None:
        if self.handled:
            return
        self.handled = True
        self.app.schedule_regular()
        self.app.close_reminder()

    def _on_close_request(self, *_args: object) -> bool:
        if not self.handled:
            self.handled = True
            self.app.schedule_regular()
            self.app.reminder_window = None
        return False

    def force_close(self) -> None:
        self.handled = True
        self.destroy()


def main() -> int:
    # GApplication parses its own options, so keep our startup-only flag away
    # from its command-line parser.
    private_options = {"--background", "--remind-now"}
    argv = [argument for argument in sys.argv if argument not in private_options]
    return PushPushPushApp().run(argv)
