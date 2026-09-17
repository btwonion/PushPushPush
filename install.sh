#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/pushpushpush/app"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
ICONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

mkdir -p "$INSTALL_DIR" "$APPLICATIONS_DIR" "$AUTOSTART_DIR" "$ICONS_DIR"
cp -R "$SOURCE_DIR/pushpushpush" "$INSTALL_DIR/"
cp "$SOURCE_DIR/run.sh" "$INSTALL_DIR/run.sh"
cp "$SOURCE_DIR/share/com.local.PushPushPush.svg" "$ICONS_DIR/com.local.PushPushPush.svg"
chmod +x "$INSTALL_DIR/run.sh"

if ! python3 -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1")' 2>/dev/null; then
  printf '%s\n' 'Note: install libayatana-appindicator-gtk3 to enable the GNOME top-bar icon.'
fi

sed "s|@EXEC@|$INSTALL_DIR/run.sh|g" \
  "$SOURCE_DIR/share/com.local.PushPushPush.desktop.in" \
  > "$APPLICATIONS_DIR/com.local.PushPushPush.desktop"
sed "s|@EXEC@|$INSTALL_DIR/run.sh --background|g" \
  "$SOURCE_DIR/share/com.local.PushPushPush.desktop.in" \
  > "$AUTOSTART_DIR/com.local.PushPushPush.desktop"

printf 'Installed PushPushPush. Launch it from the app grid or run:\n  %s\n' "$INSTALL_DIR/run.sh"
