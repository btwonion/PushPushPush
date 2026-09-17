# PushPushPush

PushPushPush is a small desktop reminder that helps you fit a few push-ups into
your day. Choose how often you want a reminder and roughly how many push-ups
you want to do, then let the app take care of the rest.

It stays out of the way between reminders, keeps a local record of completed
sets, and shows your progress over the last two weeks.

![PushPushPush icon](share/com.local.PushPushPush.svg)

## What it does

- Sends push-up reminders at an interval you choose
- Varies each set around your preferred number of repetitions
- Lets you complete, snooze, or skip a reminder
- Shows your completed sets and recent daily totals
- Can start automatically when you sign in
- Keeps your settings and history on your own computer

## System support

PushPushPush is made for **Linux desktops running GNOME**. It uses GTK 4 and
libadwaita, so it looks and feels at home on current GNOME-based systems such as
Fedora Workstation and Ubuntu.

The optional top-bar icon requires Ayatana AppIndicator support. The reminders
and main window still work without it.

## Install

Download the latest package from the repository's **Releases** page, extract
it, and run:

```bash
./install.sh
```

You can then open **PushPushPush** from the app grid. It will also start
automatically on future sign-ins.

To try the app directly from a source checkout without installing it, run:

```bash
./run.sh
```

To remove the installed app and its autostart entry, run:

```bash
./uninstall.sh
```

Your settings and completion history are left in place when the app is
uninstalled.

## Development

Run the test suite with:

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions runs the same tests and creates a ready-to-download archive for
every push. Tags beginning with `v` also publish that archive as a GitHub
release.
