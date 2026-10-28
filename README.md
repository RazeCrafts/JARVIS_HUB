# Jarvis

A local-first desktop assistant for Linux and Windows: wake-word voice, a Groq-hosted brain,
native system control, notes with PDF export, persistent timers, and an optional
heavy brain via the OpenCode CLI.

**Cloud brain, local body.** Speech recognition and language understanding run in
the cloud; audio capture, VAD, notes, timers, window/audio control and the UI all
run locally with no daemon to babysit.

---

## Requirements

- Linux with X11 (tested on Cinnamon / Linux Mint), PipeWire or PulseAudio; or Windows 10/11
- Python 3.12
- `arecord`/`parec`/`paplay` (alsa-utils, pulseaudio-utils)
- `amixer` or `pactl`, `wmctrl`, `xdotool`, `xclip`, `scrot`
- Optional: `mpv` + `yt-dlp`, `playerctl`, Spotify credentials, Chromecast
- A Groq API key (STT + daily brain)

## Quick start

```bash
cd ~/jarvis_hub
cp .env.example .env        # if .env does not exist yet
chmod 600 .env
$EDITOR .env                # at minimum set GROQ_API_KEY
./setup.sh                  # deps, desktop entry, autostart, hotkeys, self-check
./run_jarvis.sh             # or press Super and open "Jarvis"
```

`./setup.sh` flags:

| Flag | Effect |
| --- | --- |
| `--deps` | Force a reinstall of `requirements.txt` |
| `--start` | Launch Jarvis after the checks pass |
| `--no-hotkeys` | Skip Cinnamon global shortcuts |
| `--no-autostart` | Skip the login autostart entry |
| `--rebuild-venv` | Recreate Python packages for this computer; use after copying the folder |

### Moving Jarvis to another Linux laptop

The app can run from a different folder or Linux laptop. Copy the project folder,
but do not reuse its `venv` or share your `.env`. On the new laptop, install the
system tools below, make a fresh private `.env` from `.env.example`, add your
Groq key, then run:

```bash
cd /path/to/jarvis_hub
chmod 600 .env
./setup.sh --rebuild-venv
./run_jarvis.sh
```

The bundled Python environment is machine-specific; `--rebuild-venv` recreates
it at the copied location. Models and app data travel with the folder. Notes,
memory, timers, and settings are personal data, so copy them only if you want
them on the other laptop. Review `.env` and `config/settings.json` there for
home-specific URLs and credentials. For Windows, follow [WINDOWS_SETUP.md](WINDOWS_SETUP.md)
and create a fresh Windows virtual environment rather than copying the Linux one.

On Linux Mint / Ubuntu, install the system tools once (administrator password
may be required):

```bash
sudo apt install python3 python3-venv python3-pip wmctrl xdotool xclip scrot \
  alsa-utils pulseaudio-utils mpv playerctl ffmpeg
```

Health check any time:

```bash
venv/bin/python scripts/selfcheck.py --online --audio
```

It prints pass/warn/fail for the venv, settings, models, audio, IPC, notes,
Groq, dispatch channels and more. Optional integrations only warn.

## Using it

Say **“Jarvis”**, then a command. A follow-up window (12 s by default) lets you
keep talking without repeating the wake word. `Ctrl+Space` starts a listen
immediately, `Esc` stops speech, and `Ctrl+K` opens the command palette.

The default voice is Jarvis: concise, cool-headed, lightly dry, and British in
English. He greets you when the dashboard opens. Settings → Voice can auto-match
the spoken language; English and Hindi voices are included, and other voice
models download only when selected. “Let me interrupt Jarvis by speaking” uses
local voice activity detection while he speaks. Escape and the Stop button also
interrupt immediately and prompt “Go ahead. I am listening.”

Settings → Personalization stores only preferences you state clearly (such as
your name, language, response length, or turn-taking). It does not keep raw
audio or a private transcript diary; you can disable learning or clear the saved
preferences there.

Change the wake phrase or add up to eight alternatives in **Settings → Voice**.
Telegram, WhatsApp via Twilio, and Spotify credentials can be entered in
**Settings → Messaging connections**; secrets go to the private `.env` file.
For Drive, Calendar and user-selected Photos, see [GOOGLE_SETUP.md](GOOGLE_SETUP.md).

### Layouts

- **Minimal** – a 540×540 orb with the last reply. Light theme by default.
- **Power** – 1180×720 dashboard with Conversation, Notes, Timers, System,
  Settings and Help panes.

Toggle with the titlebar button, the tray menu, or
`./jarvis-ctl mode power|minimal`. Theme: `./jarvis-ctl theme dark|light`
(or `Ctrl+Shift+M`). Auto night theme and quiet hours are configurable under
Settings → Interface.

### Global shortcuts

Installed by `./setup.sh` on Cinnamon:

| Keys | Action |
| --- | --- |
| `Ctrl+Alt+J` | Show/hide the dashboard |
| `Ctrl+Alt+Space` | Listen now |
| `Ctrl+Alt+N` | Notes pane |
| `Ctrl+Alt+T` | Timers pane |
| `Ctrl+Alt+X` | Stop speaking |

In-app: `Ctrl+Space` listen, `Ctrl+K` palette, `Ctrl+L` focus the command box,
`Ctrl+Return` send, `Escape` stop speech, `Ctrl+Alt+S` settings.

### Terminal control

`jarvis-ctl` talks to the running app over a local socket; start the app once
per login (autostart does this).

```bash
jarvis-ctl status
jarvis-ctl ask "summarise my day"      # prints the reply, does not speak
jarvis-ctl say "Dinner is ready"       # speaks aloud
jarvis-ctl listen
jarvis-ctl notes | timers
jarvis-ctl pane notes|timers|settings|system|help|transcript
jarvis-ctl mode power|minimal
jarvis-ctl theme light|dark
jarvis-ctl heavy on|off
jarvis-ctl show|hide|stop|quit
```

## Voice examples

- “Set a timer for 8 minutes called pasta.”
- “Remind me at 18:30 to call mum.”
- “Add milk and eggs to my grocery list.”
- “Read my grocery list.” / “Export my notes to PDF.”
- “Play lo-fi beats.” / “Pause.” / “Next track.”
- “Snap the window left.” / “Focus Firefox.”
- “Server status.” / “Weather.” / “System status.”
- “Dark mode.” / “Power layout.” / “Calibrate microphone.”
- “Remember that the NAS is at 192.168.0.10.”
- “Switch to heavy mode for this.”

Local intents (time, volume, notes, timers, windows, themes, simple media) answer
in milliseconds without touching the network. Everything else streams through
Groq with tool calling.

## Brain and providers

Open **Settings → Brain** (or edit `config/settings.json`).

| Setting | Meaning |
| --- | --- |
| `llm.provider` | `groq`, `openai` (any OpenAI-compatible endpoint), or `opencode` |
| `llm.fast_model` | Default streaming model (e.g. `openai/gpt-oss-20b`) |
| `llm.complex_model` | Model used for longer/complex requests |
| `llm.base_url` | Base URL for the OpenAI-compatible provider |
| `llm.api_key_env` | Env var holding that provider's key |
| `llm.heavy_provider` | `same`, `groq`, `openai`, or `opencode` |
| `llm.heavy_model` | Model for heavy mode (e.g. `opencode/big-pickle`) |
| `llm.force_heavy` | Send every request to the heavy brain |
| `llm.heavy_escalate` | Allow automatic escalation for large requests |

Groq is the default because it is fast and hosts Whisper. To use OpenAI or a
local Ollama/OpenRouter endpoint, set `provider`, `base_url`, `api_key_env` and
the model names, then restart.

### Heavy brain via OpenCode

For large coding/research tasks Jarvis can hand the request to a configured
OpenCode model instead of the chat model:

```bash
jarvis-ctl heavy on       # force the heavy brain
jarvis-ctl heavy off      # back to the daily brain
```

Or say “switch to heavy mode for this.” Heavy mode is also available from
Settings → Brain. By default the heavy target is `opencode/big-pickle`; change
`llm.heavy_model` to any model available to your OpenCode install. OpenCode is
invoked as:

```bash
opencode run --model <model> --format json "<prompt>"
```

Set `llm.opencode_timeout_s` for long jobs and `llm.opencode_agent` to pin an
agent. If OpenCode is unavailable Jarvis reports the failure instead of hanging.

## Notes

Notes live in `data/notes/notes.json` with matching Markdown copies under
`data/notes/markdown/`. Editing the JSON externally is safe: a file watcher
reloads it and refreshes the pane.

Supported from voice or chat: create, append to a list, search, read, update,
delete, export to PDF, and share. PDFs are written to `data/exports/`.

Optional dispatch channels are used by the `share_note` tool:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
JARVIS_WEBHOOK_URL=https://...
# WhatsApp through Twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_TO=whatsapp:+91...
```

Missing credentials are not an error; Jarvis says which channel is unconfigured.

## Timers and reminders

Timers and reminders are stored in `data/state/timers.json` and survive
restarts. When one fires you get a toast and a spoken announcement, plus a small
floating “bob” on the desktop for active items. Bob positions are remembered if
`ui.remember_geometry` is on.

## Sleep, lid, and staying awake

Jarvis is meant to keep working while the lid is closed:

- logind `HandleLidSwitch=ignore` (installed by the privileged setup)
- Cinnamon lid/idle actions set to “nothing”
- `jarvis-keep-awake.service` (user unit) holds a `systemd-inhibit` lock

Check it with:

```bash
systemctl --user is-enabled jarvis-keep-awake.service
systemctl --user is-active  jarvis-keep-awake.service
systemd-inhibit --list | grep -i jarvis
```

To let the machine sleep again, disable the user service and restore your lid
settings.

## Configuration

- `config/settings.json` – runtime settings (theme, layout, audio, wake word,
  brain, integrations). Changes made in the Settings pane are saved here.
- `.env` – secrets only. Keep it `chmod 600`.
- `data/logs/jarvis.log` – application log.
- `data/logs/latency.log` – local/LLM/STT timing lines for tuning.

Useful audio keys: `audio.input_device`, `audio.vad_threshold`,
`audio.min_silence_ms` (300 by default), `wake.mode` (`phrase` or `ptt`),
`wake.follow_up_s`, `tts.backend` (`auto`, `piper`, `espeak`, `groq`),
`tts.idle_unload_s`.

Settings → Voice has a **Calibrate microphone** button; it samples ambient noise
and sets a sensible VAD threshold.

## Troubleshooting

**No reply / “Groq API key missing”** – set `GROQ_API_KEY` in `.env` and restart.

**It hears nothing** – confirm the input device (`arecord -l`, `pactl info`),
then run calibration. `venv/bin/python scripts/selfcheck.py --audio` reports VAD
and capture status.

**No speech, or speech cuts off** – check that `models/piper/*.onnx` and the
vendored Piper binary exist; `tts.backend=auto` falls back to `spd-say`. The
self-check’s audio section verifies the pipeline.

**Window control does nothing** – install `wmctrl` and `xdotool`; Wayland is not
supported for snapping/focus.

**Docker status says permission denied** – your shell predates the `docker`
group. `scripts/server_status.sh` retries through `sg docker`; otherwise log out
and back in.

**IPC fails with “Jarvis is not running”** – start the dashboard first. The
socket name is `jarvis-dashboard-<uid>`; only one instance may run.

**Quiet hours** – by default 23:00–08:00 speech is muted, replies stay on screen.
Change or disable under Settings → Interface → Quiet hours.

**Reset to first run** – stop Jarvis, then clear `data/notes/notes.json`,
`data/state/*.json`, `data/exports/*`, and remove `ui.sizes` /
`ui.bob_positions` from `config/settings.json`.

## Project layout

```
main_dashboard.py          app shell, tray, IPC, themes, bobs
scripts/jarvis_voice.py    capture, Silero VAD, STT, intents, tool loop
scripts/jarvis_tts.py      Piper → paplay pipeline, fallback, quiet hours
scripts/notes_engine.py    JSON/Markdown notes, PDF export, dispatch
scripts/system_bridges.py  audio, media, windows, cast, apps, stats
scripts/jarvis_tasks.py    persistent timers and reminders
scripts/dashboard_panes.py six panes + settings UI
scripts/dashboard_widgets.py orb, sparkline, toasts, bobs
scripts/selfcheck.py       health checks
scripts/jarvis_ctl.py      IPC client (jarvis-ctl)
setup.sh                   installer
```

## Performance notes

On the current Linux laptop, the dashboard process uses about 250–270 MB RSS;
the warm Piper speech process adds about 110 MB. The combined app stays below
500 MB in the observed setup. The large orb uses a bounded frame cache and a
slower idle animation; hidden windows stop their animation timers. Actual memory
and CPU use depends on screen size, audio device, and model selection. Voice
round-trips are ~1–2 s for local intents and ~2–5 s for cloud replies, with first
audio around 0.5 s on a warm Piper process.
