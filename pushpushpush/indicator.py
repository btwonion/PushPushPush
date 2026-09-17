"""GTK3 tray helper for the GTK4 PushPushPush application.

Fedora's Ayatana AppIndicator library is GTK3-only, so the indicator runs in
its own process and invokes the main application's exported actions over D-Bus.
"""

from __future__ import annotations

import gi

gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Gtk", "3.0")
from gi.repository import AyatanaAppIndicator3, Gio, GLib, Gtk  # noqa: E402


APP_ID = "com.local.PushPushPush"
OBJECT_PATH = "/com/local/PushPushPush"


class TrayIndicator:
    def __init__(self) -> None:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.actions = Gio.DBusActionGroup.get(connection, APP_ID, OBJECT_PATH)
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            APP_ID,
            "com.local.PushPushPush",
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title("PushPushPush")
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self._build_menu())
        self._refresh_status()
        GLib.timeout_add_seconds(1, self._refresh_status)

    def _item(self, label: str, action: str) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda *_args: self.actions.activate_action(action, None))
        return item

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        menu.append(self._item("Open PushPushPush", "show-settings"))
        menu.append(self._item("Show push-up reminder now", "show-reminder"))
        menu.append(Gtk.SeparatorMenuItem())

        status_heading = Gtk.MenuItem(label="STATUS")
        status_heading.set_sensitive(False)
        menu.append(status_heading)
        self.timer_item = Gtk.MenuItem(label="Timer · Starting…")
        self.timer_item.set_sensitive(False)
        menu.append(self.timer_item)
        self.today_item = Gtk.MenuItem(label="Today · 0 push-ups")
        self.today_item.set_sensitive(False)
        menu.append(self.today_item)
        menu.append(Gtk.SeparatorMenuItem())

        menu.append(self._item("Pause / resume reminders", "toggle-paused"))
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(self._item("Quit", "quit"))
        menu.show_all()
        return menu

    def _refresh_status(self) -> bool:
        timer = self.actions.get_action_state("timer-status")
        today = self.actions.get_action_state("today-status")
        if timer is not None:
            self.timer_item.set_label(timer.get_string())
        if today is not None:
            self.today_item.set_label(today.get_string())
        return GLib.SOURCE_CONTINUE


def main() -> int:
    TrayIndicator()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
