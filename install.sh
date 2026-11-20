#!/usr/bin/env bash
# Install timetrack for the current user (no root needed except for apt packages).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$HOME/.local/lib/timetrack"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
AUTOSTART="$HOME/.config/autostart"

PKGS=(python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)
missing=()
for p in "${PKGS[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done
if ((${#missing[@]})); then
  echo "Installing system packages: ${missing[*]}"
  sudo apt-get install -y "${missing[@]}"
fi

# Stop a running copy so the new version is picked up.
[ -x "$BIN/timetrack" ] && "$BIN/timetrack" quit >/dev/null 2>&1 || true

rm -rf "$LIB"
mkdir -p "$LIB" "$BIN" "$APPS" "$AUTOSTART"
cp -r "$SRC/timetrack" "$LIB/"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +

cat > "$BIN/timetrack" <<EOF
#!/bin/sh
# Uses the system Python so the distro's GTK bindings (python3-gi) are available.
PYTHONPATH="$LIB\${PYTHONPATH:+:\$PYTHONPATH}" exec /usr/bin/python3 -m timetrack "\$@"
EOF
chmod +x "$BIN/timetrack"

desktop() {
  cat <<EOF
[Desktop Entry]
Type=Application
Name=Timetrack
Comment=Prompt-based time tracker
Exec=$BIN/timetrack
Icon=preferences-system-time-symbolic
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
}
desktop > "$APPS/timetrack.desktop"
{ desktop; echo "X-GNOME-Autostart-enabled=true"; echo "X-GNOME-Autostart-Delay=5"; } \
  > "$AUTOSTART/timetrack.desktop"

echo "Installed. timetrack will start automatically at login."
echo "Starting it now..."
nohup "$BIN/timetrack" >/dev/null 2>&1 &
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Note: $BIN is not on your PATH; open a new terminal or log out and back in." ;;
esac
