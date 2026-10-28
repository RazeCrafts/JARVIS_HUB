#!/usr/bin/env bash
# One-shot installer for Jarvis. Safe to re-run.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV="${ROOT}/venv"
START=0
INSTALL_DEPS=0
INSTALL_HOTKEYS=1
INSTALL_AUTOSTART=1
REBUILD_VENV=0

for arg in "$@"; do
  case "$arg" in
    --start) START=1 ;;
    --deps) INSTALL_DEPS=1 ;;
    --no-hotkeys) INSTALL_HOTKEYS=0 ;;
    --no-autostart) INSTALL_AUTOSTART=0 ;;
    --rebuild-venv) REBUILD_VENV=1 ;;
    --help|-h)
      cat <<'EOF'
Usage: ./setup.sh [--deps] [--start] [--no-hotkeys] [--no-autostart] [--rebuild-venv]

  --deps          force a pip install of requirements.txt
  --start         launch Jarvis after the checks pass
  --no-hotkeys    do not add Cinnamon global shortcuts
  --no-autostart  do not create the login autostart entry
  --rebuild-venv  recreate the Python environment (use after copying to another laptop)
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

echo "Jarvis installer · ${ROOT}"

if [[ "$REBUILD_VENV" == "1" ]]; then
  echo "· recreating the Python environment"
  rm -rf -- "$VENV"
  INSTALL_DEPS=1
fi

if [[ ! -d "$VENV" ]]; then
  echo "· creating virtualenv"
  "$PYTHON" -m venv "$VENV"
  INSTALL_DEPS=1
fi

if [[ "$INSTALL_DEPS" == "1" ]]; then
  echo "· installing Python packages (this can take a while on slow links)"
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV/bin/python" -m pip install --retries 8 --timeout 60 -r "$ROOT/requirements.txt"
else
  echo "· Python packages already installed (use --deps to reinstall)"
fi

echo "· fixing permissions and launchers"
chmod +x "$ROOT/run_jarvis.sh" "$ROOT/jarvis-ctl" "$ROOT/setup.sh" \
  "$ROOT/scripts/notes_engine.py" "$ROOT/scripts/system_bridges.py" \
  "$ROOT/scripts/jarvis_voice.py" "$ROOT/scripts/selfcheck.py" \
  "$ROOT/scripts/install_hotkeys.py" "$ROOT/scripts/jarvis_ctl.py" 2>/dev/null || true
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/autostart"
ln -sfn "$ROOT/jarvis-ctl" "$HOME/.local/bin/jarvis-ctl"
ln -sfn "$ROOT/run_jarvis.sh" "$HOME/.local/bin/jarvis"

echo "· installing desktop entries"
cat > "$HOME/.local/share/applications/jarvis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Jarvis
GenericName=Desktop assistant
Comment=Cloud brain, local body — voice, notes, timers and system control
Exec=${ROOT}/run_jarvis.sh
Icon=${ROOT}/assets/jarvis.svg
Terminal=false
Categories=Utility;AudioVideo;
Keywords=assistant;voice;jarvis;notes;timers;
StartupNotify=false
StartupWMClass=jarvis
EOF

if [[ "$INSTALL_AUTOSTART" == "1" ]]; then
  cat > "$HOME/.config/autostart/jarvis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Jarvis
Comment=Start Jarvis at login
Exec=${ROOT}/run_jarvis.sh
Icon=${ROOT}/assets/jarvis.svg
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=8
StartupNotify=false
EOF
  echo "· autostart enabled (remove ~/.config/autostart/jarvis.desktop to disable)"
fi

echo "· installing the keep-awake user service"
mkdir -p "$HOME/.config/systemd/user"
cp "$ROOT/scripts/systemd/jarvis-keep-awake.service" "$HOME/.config/systemd/user/jarvis-keep-awake.service"
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable --now jarvis-keep-awake.service 2>/dev/null || \
  echo "  (systemd user session unavailable; the service is installed but not started)"

if [[ -n "${DISPLAY:-}" && -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]] && command -v gsettings >/dev/null; then
  echo "· disabling screen lock and idle blanking"
  gsettings set org.cinnamon.desktop.screensaver lock-enabled false 2>/dev/null || true
  gsettings set org.cinnamon.desktop.screensaver idle-activation-enabled false 2>/dev/null || true
fi

if [[ "$INSTALL_HOTKEYS" == "1" && -n "${DISPLAY:-}" && -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]] && command -v gsettings >/dev/null; then
  echo "· installing Cinnamon global shortcuts"
  "$VENV/bin/python" "$ROOT/scripts/install_hotkeys.py" || echo "  (shortcut install skipped)"
else
  echo "· global shortcuts skipped (no desktop session); in-app shortcuts still work"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  chmod 600 "$ROOT/.env"
  echo "· created .env from .env.example — add your GROQ_API_KEY"
fi

echo "· running the self-check"
set +e
"$VENV/bin/python" "$ROOT/scripts/selfcheck.py"
CHECK=$?
set -e
if [[ "$CHECK" != "0" ]]; then
  echo "Self-check found failures; fix them before starting." >&2
  exit "$CHECK"
fi

if [[ "$START" == "1" ]]; then
  echo "· starting Jarvis"
  nohup "$ROOT/run_jarvis.sh" >/dev/null 2>&1 &
  disown || true
  sleep 1
  "$ROOT/jarvis-ctl" status || true
else
  echo
  echo "Ready. Start with:  ./run_jarvis.sh"
  echo "Or from the menu:   Jarvis"
fi
