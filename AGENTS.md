# Repository Guidelines

## Project Overview

PushPushPush is a native GNOME reminder application written in Python. It uses
GTK 4, libadwaita, PyGObject, and an optional Ayatana application indicator.
User settings and history are stored locally outside the repository.

## Repository Structure

- `pushpushpush/`: application source code.
- `pushpushpush/app.py`: GTK application and user interface.
- `pushpushpush/core.py`: settings, history, scheduling data, and sampling logic.
- `pushpushpush/indicator.py`: GNOME top-bar indicator integration.
- `pushpushpush/style.css`: application styling.
- `tests/`: unit tests.
- `share/`: desktop entry template and application icon.
- `run.sh`: runs the application from the source tree.
- `install.sh`: installs or updates the local application and autostart entry.
- `uninstall.sh`: removes the installed application while preserving user data.

## Development Workflow

- Keep changes focused and preserve the existing GNOME-native behavior.
- Put non-UI logic in `core.py` where practical so it remains easy to test.
- Do not modify or remove user settings and history unless the task explicitly
  requires it.
- Run the application from the repository with `./run.sh` when developing.
- Use `./run.sh --remind-now` when a change needs the reminder popup immediately.

## Testing

- Run the full test suite after making changes:

  ```bash
  python3 -m unittest discover -s tests -v
  ```

- Add or update tests for changed behavior when practical.
- Verify UI changes in the running GTK application in addition to running unit
  tests.

## Application Replacement and Restart

- After every application update, always replace the installed application with
  the updated version by running `./install.sh`.
- Stop the currently running PushPushPush instance and restart it from the newly
  installed version. Never leave an older instance running after an update.
- Confirm that the restarted application is using the latest changes before
  considering the task complete.
