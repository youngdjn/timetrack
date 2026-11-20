#!/usr/bin/env bash
# Remove timetrack. Your time log, settings and state are kept unless you pass --purge.
set -euo pipefail

"$HOME/.local/bin/timetrack" quit >/dev/null 2>&1 || true
rm -rf "$HOME/.local/lib/timetrack" "$HOME/.local/bin/timetrack" \
       "$HOME/.local/share/applications/timetrack.desktop" \
       "$HOME/.config/autostart/timetrack.desktop"
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$HOME/.config/timetrack" "$HOME/.local/state/timetrack" "$HOME/.local/share/timetrack"
  echo "timetrack and all its data removed."
else
  echo "timetrack removed. Data kept in ~/.local/share/timetrack, settings in ~/.config/timetrack."
fi
