#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/pushpushpush/app"
APPLICATION_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/com.local.PushPushPush.desktop"
AUTOSTART_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/com.local.PushPushPush.desktop"
ICON_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/com.local.PushPushPush.svg"

if [[ -e "$INSTALL_DIR" ]]; then
  rm -r -- "$INSTALL_DIR"
fi
rm -f -- "$APPLICATION_FILE" "$AUTOSTART_FILE" "$ICON_FILE"
printf 'PushPushPush was removed. Your settings and statistics remain available.\n'
