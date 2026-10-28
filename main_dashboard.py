"""Jarvis desktop dashboard.

A frameless, translucent, Stark-style control surface with a custom arc-reactor
orb, minimal and power layouts, tray integration, a local IPC socket for the
CLI and a single-instance guard.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from PySide6.QtCore import (  # noqa: E402
    QEvent,
    QPoint,
    QRect,
    QLockFile,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    QObject,
)
from PySide6.QtGui import (  # noqa: E402
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QListWidget,
)

from jarvis_core import (  # noqa: E402
    APP_NAME,
    LOG_DIR,
    STATE_DIR,
    ROOT as APP_ROOT,
    Settings,
    VERSION,
    EventBus,
    load_env,
    night_now,
    setup_logging,
)
from jarvis_tts import TTSEngine  # noqa: E402
from jarvis_tasks import TaskEngine  # noqa: E402
from jarvis_routines import RoutineEngine  # noqa: E402
from jarvis_files import FileIndex  # noqa: E402
from contact_hub import ContactHub  # noqa: E402
from jarvis_voice import VoiceEngine  # noqa: E402
from notes_engine import NotesEngine  # noqa: E402
from system_bridges import SystemBridges  # noqa: E402

from dashboard_widgets import (  # noqa: E402
    BobWindow,
    CommandDeck,
    FocusTimer,
    ModelSelector,
    OrbWidget,
    PaletteDialog,
    TaskProgressBar,
    ToastManager,
    friendly_remaining,
    orbit_pixmap,
)
from jarvis_routes import (  # noqa: E402
    ROUTES,
    apply_route,
    current_label,
    current_route,
    route_available,
)
from platform_compat import USER_KEY  # noqa: E402
from dashboard_panes import (  # noqa: E402
    FilesPane,
    ContactPane,
    HelpPane,
    ImprovementPane,
    MediaPane,
    NotesPane,
    RoutinesPane,
    SettingsPane,
    SystemPane,
    TimersPane,
    TranscriptPane,
)

SERVER_NAME = f"jarvis-dashboard-{USER_KEY}"
PANES = (
    ("transcript", "Conversation"),
    ("media", "Media"),
    ("notes", "Notes"),
    ("files", "Files"),
    ("contact", "Contact"),
    ("improve", "Improve Jarvis"),
    ("routines", "Routines"),
    ("timers", "Timers"),
    ("system", "System"),
    ("settings", "Settings"),
    ("help", "Help"),
)

PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#E9EFF7",
        "bg2": "#DEE7F2",
        "surface": "#F8FBFF",
        "surface2": "#EDF3FA",
        "border": "#D3DEEB",
        "edge": "#B9C9DC",
        "text": "#0A1626",
        "muted": "#5B7189",
        "accent": "#0284C7",
        "accent2": "#06B6D4",
        "danger": "#DC2626",
        "warn": "#D97706",
        "ok": "#059669",
        "chip": "#F4F8FC",
        "transparent": "transparent",
    },
    "dark": {
        "bg": "#05070A",
        "bg2": "#0A0D12",
        "surface": "#0D1218",
        "surface2": "#141B22",
        "border": "#26323D",
        "edge": "#3A4D5B",
        "text": "#EAF8FF",
        "muted": "#80909C",
        "accent": "#3FE3FF",
        "accent2": "#A5F4FF",
        "danger": "#FB7185",
        "warn": "#FBBF24",
        "ok": "#34D399",
        "chip": "#090D12",
        "transparent": "transparent",
    },
}

STYLE = """
QWidget {
    color: @text@;
    font-family: 'Segoe UI Variable', 'Segoe UI';
    font-size: 14px;
}
QLabel#Wordmark {
    color: @text@;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 6px;
}
QLabel#Clock, QLabel#Muted { color: @muted@; }
QLabel#Section {
    color: @muted@;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2.2px;
}
QLabel#Chip {
    color: @accent2@;
    background: @chip@;
    border: 1px solid @border@;
    border-radius: 10px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
}
QLabel#State {
    color: @accent@;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 3px;
}
QLabel#Reply {
    color: @text@;
    font-size: 15px;
}
QLabel#MiniStatus {
    color: @accent@;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
}
QFrame#Header {
    background: transparent;
    border: none;
    border-bottom: 1px solid @border@;
}
QFrame#CallStage {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 @bg2@, stop:0.58 @bg@, stop:1 @surface@);
    border: 1px solid @border@;
    border-radius: 8px;
}
QFrame#CallTranscript {
    background: rgba(5, 7, 10, 210);
    border: 1px solid @border@;
    border-radius: 8px;
}
QLabel#LiveCaption {
    color: @text@;
    background: rgba(5, 7, 10, 220);
    border: 1px solid @edge@;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 15px;
}
QLabel#CallName {
    color: @accent@;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
}
QFrame#Rail, QFrame#Card, QFrame#OrbCard {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 8px;
}
QFrame#Rail { background: @bg2@; }
QFrame#OrbCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @surface2@, stop:1 @surface@);
    border: 1px solid @edge@;
}
QTextBrowser, QTextEdit, QPlainTextEdit {
    background: @surface@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 10px;
    padding: 8px;
    selection-background-color: @accent@;
    selection-color: @chip@;
}
QListWidget {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 10px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    color: @text@;
    padding: 7px 9px;
    border-radius: 7px;
    margin: 1px 0;
}
QListWidget::item:selected { background: @surface2@; color: @text@; }
QListWidget::item:hover { background: @surface2@; }
QLineEdit, QComboBox, QSpinBox, QTimeEdit {
    background: @chip@;
    color: @text@;
    border: 1px solid @edge@;
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: @accent@;
    selection-color: #031018;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {
    border: 1px solid @accent@;
}
QLineEdit#Command {
    background: @chip@;
    border: 1px solid @edge@;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 14px;
    letter-spacing: 0.3px;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: @surface2@;
    color: @text@;
    border: 1px solid @edge@;
    selection-background-color: @surface@;
    selection-color: @accent2@;
    outline: none;
    padding: 4px;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @surface2@, stop:1 @surface@);
    color: @text@;
    border: 1px solid @edge@;
    border-radius: 9px;
    padding: 7px 12px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QPushButton:hover { border-color: @accent@; color: @accent2@; }
QPushButton:pressed { background: @surface@; }
QPushButton:disabled { color: @muted@; border-color: @border@; }
QPushButton:checked { border-color: @accent@; color: @accent2@; }
QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @accent@, stop:1 @accent2@);
    color: #031018;
    border: 1px solid @accent2@;
    font-weight: 800;
    letter-spacing: 1px;
}
QPushButton#Primary:hover { border-color: #FFFFFF; color: #000000; }
QPushButton#StopBtn {
    background: @surface@;
    color: @danger@;
    border: 1px solid @border@;
    border-radius: 9px;
    padding: 7px 10px;
    font-weight: 800;
}
QPushButton#StopBtn:hover { background: @surface2@; border-color: @danger@; }
QPushButton#Ghost {
    background: transparent;
    border: 1px solid transparent;
    color: @muted@;
    padding: 5px 9px;
    font-weight: 600;
}
QPushButton#Ghost:hover { background: @surface2@; color: @accent2@; }
QPushButton#Ghost:checked { color: @accent@; border-color: @accent@; }
QPushButton#ChipBtn {
    background: transparent;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 15px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#ChipBtn:hover { border-color: @accent@; color: @accent2@; }
QPushButton#Nav {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 9px 11px;
    text-align: left;
    color: @muted@;
    font-weight: 600;
    letter-spacing: 0.8px;
}
QPushButton#Nav:hover { color: @text@; background: @surface@; }
QPushButton#Nav:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @surface@, stop:1 @surface2@);
    color: @accent2@;
    border-color: @edge@;
    font-weight: 800;
}
QPushButton#TitleBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 2px;
}
QPushButton#TitleBtn:hover { background: @surface2@; border-color: @edge@; }
QWidget#TaskBar { background: transparent; }
QWidget#FocusTimer {
    background: @chip@;
    border: 1px solid @border@;
    border-radius: 9px;
}
QLabel#FocusMode {
    color: @muted@;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1.4px;
}
QLabel#FocusTime {
    color: @accent2@;
    font-family: 'Noto Sans Mono';
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#FocusBtn {
    background: transparent;
    border: 1px solid @border@;
    border-radius: 5px;
    color: @accent@;
    padding: 0px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton#FocusBtn:hover { border-color: @accent@; color: @accent2@; }
QComboBox#ModelSelector {
    background: @chip@;
    color: @accent2@;
    border: 1px solid @edge@;
    border-radius: 9px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.7px;
}
QWidget#CommandDeck {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @bg2@, stop:0.5 @surface@, stop:1 @bg2@);
    border: 1px solid @border@;
    border-radius: 12px;
}
QPushButton#DeckToggle {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: @muted@;
    padding: 4px 9px;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
}
QPushButton#DeckToggle:hover { color: @text@; border-color: @edge@; }
QPushButton#DeckToggle:checked {
    color: @accent2@;
    border-color: @accent@;
    background: @chip@;
}
QLabel#Ticker {
    color: @muted@;
    font-family: 'Noto Sans Mono';
    font-size: 11px;
    letter-spacing: 0.4px;
}
QLabel#DeckDivider { color: @edge@; font-size: 13px; }
QLabel#DeckMeta {
    color: @muted@;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
}
QCheckBox { color: @text@; spacing: 8px; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid @edge@;
    border-radius: 4px;
    background: @surface@;
}
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; }
QSlider::groove:horizontal {
    height: 4px; background: @border@; border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px; margin: -6px 0; border-radius: 7px;
    background: @accent@;
}
QSlider::sub-page:horizontal { background: @accent@; border-radius: 2px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical {
    background: @edge@; border-radius: 4px; min-height: 26px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: @edge@; border-radius: 4px; min-width: 26px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenu {
    background: @surface@;
    color: @text@;
    border: 1px solid @edge@;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 5px; }
QMenu::item:selected { background: @surface2@; }
QMenu::separator { height: 1px; background: @border@; margin: 5px 8px; }
QToolTip {
    background: @surface@;
    color: @text@;
    border: 1px solid @edge@;
    padding: 4px 7px;
    border-radius: 5px;
}
QDialog { background: @bg@; color: @text@; }
QDialogButtonBox QPushButton { min-width: 80px; }
"""


def stylesheet(name: str) -> str:
    palette = PALETTES.get(name, PALETTES["light"])
    return resolve_theme_tokens(STYLE, palette)


def resolve_theme_tokens(source: str, palette: dict[str, str]) -> str:
    for key, value in palette.items():
        source = source.replace(f"@{key}@", value)
    return source


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self.func = func
        self.signals = _JobSignals()


# ---------------------------------------------------------------------------
# Title bar
# ---------------------------------------------------------------------------

class TitleBar(QFrame):
    def __init__(self, owner: "JarvisDashboard") -> None:
        super().__init__()
        self.owner = owner
        self.setObjectName("Header")
        self.setFixedHeight(48)
        self._drag: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)

        mark = QLabel("JARVIS")
        mark.setObjectName("Wordmark")
        layout.addWidget(mark)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(12)
        layout.addWidget(self.dot)
        self.state = QLabel("STANDBY")
        self.state.setObjectName("Chip")
        layout.addWidget(self.state)
        layout.addStretch(1)

        self.focus = FocusTimer()
        self.focus.setToolTip("Focus timer / stopwatch")
        layout.addWidget(self.focus)

        layout.addStretch(1)

        self.model_selector = owner.model_selector
        layout.addWidget(self.model_selector)
        self.theme_btn = QPushButton("◐")
        self.theme_btn.setObjectName("TitleBtn")
        self.theme_btn.setFixedSize(30, 26)
        self.theme_btn.setToolTip("Switch between dark and light themes")
        self.theme_btn.clicked.connect(owner.toggle_theme)
        layout.addWidget(self.theme_btn)
        self.clock = QLabel("")
        self.clock.setObjectName("Clock")
        self.clock.setFixedWidth(42)
        self.clock.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.clock)

        self.pin = QPushButton("PIN")
        self.pin.setObjectName("Ghost")
        self.pin.setCheckable(True)
        self.pin.setToolTip("Keep Jarvis above other windows")
        self.pin.setFixedHeight(26)
        self.pin.clicked.connect(owner.toggle_on_top)
        layout.addWidget(self.pin)

        self.layout_btn = QPushButton()
        self.layout_btn.setObjectName("TitleBtn")
        self.layout_btn.setFixedSize(28, 26)
        self.layout_btn.setToolTip("Switch between minimal and power layout")
        self.layout_btn.clicked.connect(owner.toggle_mode)
        layout.addWidget(self.layout_btn)

        self.max_btn = QPushButton()
        self.max_btn.setObjectName("TitleBtn")
        self.max_btn.setFixedSize(28, 26)
        self.max_btn.setToolTip("Maximise window")
        self.max_btn.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMaxButton))
        self.max_btn.clicked.connect(owner.toggle_maximized)
        layout.addWidget(self.max_btn)

        self.full_btn = QPushButton("⛶")
        self.full_btn.setObjectName("TitleBtn")
        self.full_btn.setFixedSize(28, 26)
        self.full_btn.setToolTip("Fullscreen HUD (F11)")
        self.full_btn.clicked.connect(owner.toggle_fullscreen)
        layout.addWidget(self.full_btn)

        self.min_btn = QPushButton()
        self.min_btn.setObjectName("TitleBtn")
        self.min_btn.setFixedSize(28, 26)
        self.min_btn.setToolTip("Hide to tray")
        self.min_btn.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMinButton))
        self.min_btn.clicked.connect(owner.hide_window)
        layout.addWidget(self.min_btn)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("TitleBtn")
        self.close_btn.setFixedSize(28, 26)
        self.close_btn.setToolTip("Hide to tray (use Quit in the tray menu to exit)")
        self.close_btn.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton))
        self.close_btn.clicked.connect(owner.hide_window)
        layout.addWidget(self.close_btn)

        self.refresh_layout_icon()

    def refresh_layout_icon(self) -> None:
        icon = (
            QStyle.SP_TitleBarNormalButton
            if self.owner._mode == "power"
            else QStyle.SP_TitleBarMaxButton
        )
        self.layout_btn.setIcon(self.style().standardIcon(icon))
        self.refresh_window_icon()

    def refresh_window_icon(self) -> None:
        icon = (
            QStyle.SP_TitleBarNormalButton
            if self.owner.isMaximized() or self.owner.isFullScreen()
            else QStyle.SP_TitleBarMaxButton
        )
        self.max_btn.setIcon(self.style().standardIcon(icon))
        self.full_btn.setText("⤢" if self.owner.isFullScreen() else "⛶")

    def set_state(self, text: str, color: str) -> None:
        text = text.upper()
        if text == getattr(self, "_state_text", None) and color == getattr(self, "_state_color", None):
            return
        self._state_text = text
        self._state_color = color
        self.state.setText(text)
        self.state.setStyleSheet(f"color:{color}; border:1px solid {color};")
        self.dot.setStyleSheet(f"color:{color}; font-size:11px;")

    def set_route(self, text: str) -> None:
        self.model_selector.setToolTip(f"Active brain: {text}. Select here to change models.")

    def set_clock(self, text: str) -> None:
        if text != getattr(self, "_clock_text", None):
            self._clock_text = text
            self.clock.setText(text)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event: Any) -> None:
        self._drag = None
        self.owner.save_geometry()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        self.owner.toggle_maximized()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class JarvisDashboard(QMainWindow):
    def __init__(self, debug: bool = False, no_voice: bool = False, hidden: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Jarvis")
        self.setWindowIcon(QIcon(orbit_pixmap("#00E5FF", 64)))
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(480, 430)

        self.log = setup_logging(debug)
        self.settings = Settings()
        self.bus = EventBus()
        self.no_voice = no_voice
        self.hidden_start = hidden
        self._really_quit = False
        self._shutting_down = False
        self._jobs: set[_Job] = set()
        self._bobs: dict[str, BobWindow] = {}
        self._waiters: set[Any] = set()
        self._buffers: dict[int, bytes] = {}
        self._live_text = ""
        self._call_started = time.monotonic()
        self._ask_suppress = 0
        self._ask_callbacks: list[Callable[[str], None]] = []
        self._activity = ""
        self._activity_until = 0.0
        self._home_messages: list[tuple[str, str]] = []
        self._theme_styles: list[tuple[QWidget, str]] = []
        self._state = "idle"
        self._speaking = False
        self._mode = str(self.settings.get("ui.mode", "minimal") or "minimal")
        if self._mode not in ("minimal", "power"):
            self._mode = "minimal"
        self._theme = str(self.settings.get("ui.theme", "dark") or "dark")
        if self._theme not in PALETTES:
            self._theme = "dark"
        self._heavy_auto = False
        self._fullscreen = False
        self._pre_fullscreen_geometry: QRect | None = None
        self._pre_fullscreen_mode = "power"
        self._focus_mode = "idle"
        self.model_selector = ModelSelector(self)
        self.model_selector.route_changed.connect(self._on_model_changed)

        self.notes = NotesEngine(bus=self.bus, settings=self.settings)
        self.tasks = TaskEngine(bus=self.bus, settings=self.settings)
        self.routines = RoutineEngine()
        self.files = FileIndex()
        self.contacts = ContactHub()
        self.bridges = SystemBridges(bus=self.bus, settings=self.settings)
        self.tts = TTSEngine(bus=self.bus, settings=self.settings)
        self.voice = VoiceEngine(
            bus=self.bus,
            settings=self.settings,
            notes=self.notes,
            tasks=self.tasks,
            routines=self.routines,
            files=self.files,
            bridges=self.bridges,
            tts=self.tts,
            contacts=self.contacts,
        )

        self._build_ui()
        self.titlebar.focus.finished.connect(self._on_focus_finished)
        if self.settings.get("ui.always_on_top", False):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.titlebar.pin.setChecked(True)
        self._build_tray()
        self._wire_bus()
        self._install_shortcuts()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick_ui)
        self._ui_timer.start()

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(2500)
        self._stats_timer.timeout.connect(self._tick_stats)
        self._stats_timer.start()

        self._media_timer = QTimer(self)
        self._media_timer.setInterval(8000)
        self._media_timer.timeout.connect(self._tick_media)
        self._media_timer.start()

        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(60_000)
        self._theme_timer.timeout.connect(self._auto_theme)
        self._theme_timer.start()

        self._briefing_timer = QTimer(self)
        self._briefing_timer.setInterval(30_000)
        self._briefing_timer.timeout.connect(self._check_briefing)
        self._briefing_timer.start()

        if bool(self.settings.get("performance.gaming_mode", False)):
            self.set_gaming_mode(True, save=False, announce=False)

        self._server: QLocalServer | None = None
        self._start_server()

        self.apply_theme(self._theme, save=False, startup=True)
        self.set_mode(self._mode, save=False, resize=True)
        self._restore_geometry()
        self._sync_pending_bobs()

        if not no_voice:
            try:
                self.voice.start()
            except Exception as exc:  # noqa: BLE001
                self.log.warning("voice start failed: %s", exc)
                self.toast(f"Voice engine failed to start: {exc}", "error")

        QApplication.instance().aboutToQuit.connect(self._shutdown)
        QTimer.singleShot(800, self._post_start)

        if hidden:
            QTimer.singleShot(0, self.hide)
        else:
            QTimer.singleShot(0, self.show_window)
        self.log.info("Jarvis %s dashboard ready", VERSION)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _set_theme_style(self, widget: QWidget, template: str) -> None:
        self._theme_styles.append((widget, template))
        widget.setStyleSheet(resolve_theme_tokens(template, PALETTES[self._theme]))

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(0)

        self.titlebar = TitleBar(self)
        outer.addWidget(self.titlebar)

        self.task_bar = TaskProgressBar()
        outer.addWidget(self.task_bar)
        outer.addSpacing(3)

        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack, 1)

        # Initialize command_deck before building views that might reference it
        self.command_deck = CommandDeck(str(APP_ROOT))
        self.command_deck.hands_free_changed.connect(self._on_hands_free)
        self.command_deck.voice_output_changed.connect(self._on_voice_output)
        self.command_deck.screen_share_changed.connect(self._on_screen_share)
        self.command_deck.briefing_changed.connect(self._on_briefing)
        self.command_deck.palette_requested.connect(self.open_palette)

        self.toasts = ToastManager(root)
        self._toast_root = root

        self.panes: dict[str, QWidget] = {}

        self.minimal_view = self._build_minimal()
        self.power_view = self._build_power()
        self.stack.addWidget(self.minimal_view)
        self.stack.addWidget(self.power_view)

        outer.addSpacing(7)
        outer.addWidget(self.command_deck)




    def _build_minimal(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(24, 10, 24, 12)
        layout.setSpacing(7)

        self.mini_orb = OrbWidget()
        self.mini_orb.setMinimumHeight(210)
        layout.addWidget(self.mini_orb, 1)

        self.mini_status = QLabel("READY")
        self.mini_status.setObjectName("MiniStatus")
        self.mini_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mini_status)

        self.mini_reply = QLabel("Say “Jarvis” or type below.")
        self.mini_reply.setObjectName("Reply")
        self.mini_reply.setAlignment(Qt.AlignCenter)
        self.mini_reply.setWordWrap(True)
        self.mini_reply.setFixedHeight(44)
        layout.addWidget(self.mini_reply)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for label, pane in (
            ("Talk", "listen"),
            ("Notes", "notes"),
            ("Timers", "timers"),
            ("System", "system"),
            ("Settings", "settings"),
            ("⌘", "palette"),
        ):
            button = QPushButton(label)
            button.setObjectName("ChipBtn")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, target=pane: self._chip(target))
            chips.addWidget(button)
        chips.addStretch(1)
        layout.addLayout(chips)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.command = QLineEdit()
        self.command.setObjectName("Command")
        self.command.setPlaceholderText("Ask Jarvis or type a command…")
        self.command.returnPressed.connect(lambda: self._submit_from(self.command))
        row.addWidget(self.command, 1)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("Primary")
        self.send_btn.clicked.connect(lambda: self._submit_from(self.command))
        row.addWidget(self.send_btn)
        stop_btn = QPushButton("Stop")
        stop_btn.setObjectName("StopBtn")
        stop_btn.setToolTip("Interrupt Jarvis speech · Escape")
        stop_btn.clicked.connect(self.interrupt_speech)
        row.addWidget(stop_btn)
        layout.addLayout(row)

        self.mini_footer = QLabel("Ctrl+Space talk  ·  Ctrl+K commands  ·  Esc stop")
        self.mini_footer.setObjectName("Muted")
        self.mini_footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mini_footer)
        return view

    def _build_power(self) -> QWidget:
        view = QWidget()
        layout = QHBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Rail ---------------------------------------------------------
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(220)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(15, 20, 15, 20)
        rail_layout.setSpacing(8)

        # Top of Sidebar: Emblem and Title
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(orbit_pixmap("#00E5FF", 50).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo)

        name = QLabel("JARVIS")
        name.setAlignment(Qt.AlignCenter)
        self._set_theme_style(name, "font-size:14px; font-weight:800; letter-spacing:4px; color:@text@;")
        logo_layout.addWidget(name)

        subtitle = QLabel("Personal assistant")
        subtitle.setAlignment(Qt.AlignCenter)
        self._set_theme_style(subtitle, "font-size:10px; font-weight:400; letter-spacing:1px; color:@muted@;")
        logo_layout.addWidget(subtitle)

        rail_layout.addWidget(logo_container)
        rail_layout.addSpacing(20)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}

        overview_button = QPushButton("  Overview")
        overview_button.setObjectName("Nav")
        overview_button.setCheckable(True)
        overview_button.clicked.connect(self.show_overview)
        self.nav_group.addButton(overview_button, -1)
        self.nav_buttons["overview"] = overview_button
        rail_layout.addWidget(overview_button)

        FAMILY_PANES = PANES

        for index, (key, label) in enumerate(FAMILY_PANES):
            button = QPushButton(f"  {label}")
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_pane(k))
            self.nav_group.addButton(button, index)
            self.nav_buttons[key] = button
            rail_layout.addWidget(button)

        rail_layout.addStretch(1)

        # Bottom of Sidebar: Status and Clock
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setSpacing(4)

        status_indicator = QHBoxLayout()
        dot = QLabel("●")
        self._set_theme_style(dot, "color:@accent@; font-size:10px;")
        status_text = QLabel("SYSTEM ONLINE")
        self._set_theme_style(status_text, "color:@muted@; font-size:9px; font-weight:700; letter-spacing:1px;")
        status_indicator.addWidget(dot)
        status_indicator.addWidget(status_text)
        footer_layout.addLayout(status_indicator)

        self.rail_clock = QLabel("")
        self.rail_clock.setAlignment(Qt.AlignCenter)
        self._set_theme_style(self.rail_clock, "font-size:16px; font-weight:700; color:@text@; font-family:'Noto Sans Mono';")
        footer_layout.addWidget(self.rail_clock)

        self.rail_date = QLabel("")
        self.rail_date.setAlignment(Qt.AlignCenter)
        self._set_theme_style(self.rail_date, "font-size:10px; color:@muted@;")
        footer_layout.addWidget(self.rail_date)

        self.rail_stats = QLabel("")
        self.rail_stats.setAlignment(Qt.AlignCenter)
        self._set_theme_style(self.rail_stats, "font-size:10px; color:@muted@; font-family:'Noto Sans Mono';")
        footer_layout.addWidget(self.rail_stats)

        rail_layout.addWidget(footer)
        layout.addWidget(rail)

        # Main Content Area --------------------------------------------
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 0, 20, 0)
        content_layout.setSpacing(20)

        # Top Header ---------------------------------------------------
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(80)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        greeting_box = QVBoxLayout()
        self.greeting = QLabel("Welcome to Jarvis")
        self._set_theme_style(self.greeting, "font-size:22px; font-weight:700; color:@text@;")
        greeting_box.addWidget(self.greeting)

        sub_greeting = QLabel("JARVIS is ready. How can I help you today?")
        self._set_theme_style(sub_greeting, "font-size:14px; color:@muted@;")
        greeting_box.addWidget(sub_greeting)
        header_layout.addLayout(greeting_box)

        header_layout.addStretch(1)

        # Search/Command bar in header
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)

        self.header_search = QLineEdit()
        self.header_search.setObjectName("Command")
        self.header_search.setPlaceholderText("Search, ask or say \"Hey Jarvis\"...")
        self.header_search.setFixedWidth(300)
        self.header_search.returnPressed.connect(lambda: self._submit_from(self.header_search))
        search_layout.addWidget(self.header_search)

        mic_btn = QPushButton("🎤")
        mic_btn.setObjectName("Ghost")
        mic_btn.setFixedSize(36, 36)
        mic_btn.clicked.connect(self.listen)
        search_layout.addWidget(mic_btn)

        stop_btn = QPushButton("Stop")
        stop_btn.setObjectName("StopBtn")
        stop_btn.setToolTip("Interrupt Jarvis and continue talking · Escape")
        stop_btn.clicked.connect(self.interrupt_speech)
        search_layout.addWidget(stop_btn)

        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("Ghost")
        settings_btn.setFixedSize(36, 36)
        settings_btn.clicked.connect(lambda: self.show_pane("settings"))
        search_layout.addWidget(settings_btn)

        header_layout.addWidget(search_container)
        content_layout.addWidget(header)

        # Dashboard Body -----------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(20)

        # Left: call stage with the AI as the active participant.
        call_stage = QFrame()
        call_stage.setObjectName("CallStage")
        self.call_stage = call_stage
        core_section = QVBoxLayout(call_stage)
        core_section.setContentsMargins(18, 18, 18, 14)
        core_section.setSpacing(8)
        core_section.setAlignment(Qt.AlignCenter)

        call_header = QHBoxLayout()
        call_label = QLabel("JARVIS · LIVE SESSION")
        call_label.setObjectName("CallName")
        self.call_label = call_label
        call_header.addWidget(call_label)
        call_header.addStretch(1)
        self.call_clock = QLabel(time.strftime("00:00"))
        self.call_clock.setObjectName("Muted")
        call_header.addWidget(self.call_clock)
        core_section.addLayout(call_header)

        self.orb = OrbWidget()
        self.orb.setMinimumSize(300, 300)
        self.orb.setMaximumSize(520, 520)
        self.orb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        core_section.addWidget(self.orb, 1)

        self.state_label = QLabel("SYSTEM STATUS: IDLE")
        self.state_label.setObjectName("State")
        self.state_label.setAlignment(Qt.AlignCenter)
        core_section.addWidget(self.state_label)

        self.call_caption = QLabel("Say the wake word or start typing to begin.")
        self.call_caption.setObjectName("LiveCaption")
        self.call_caption.setAlignment(Qt.AlignCenter)
        self.call_caption.setWordWrap(True)
        self.call_caption.setMinimumHeight(54)
        core_section.addWidget(self.call_caption)

        # Main command input below core
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 20, 0, 0)

        self.main_command = QLineEdit()
        self.main_command.setObjectName("Command")
        self.main_command.setPlaceholderText("Ask me anything...")
        self.main_command.setMinimumWidth(220)
        self.main_command.setMaximumWidth(560)
        self.main_command.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.main_command.returnPressed.connect(lambda: self._submit_from(self.main_command))
        input_layout.addWidget(self.main_command)

        send_btn = QPushButton("Send")
        self.main_send_btn = send_btn
        send_btn.setObjectName("Primary")
        send_btn.clicked.connect(lambda: self._submit_from(self.main_command))
        input_layout.addWidget(send_btn)

        core_section.addWidget(input_container, 0, Qt.AlignCenter)

        call_controls = QHBoxLayout()
        call_controls.setAlignment(Qt.AlignCenter)
        mic = QPushButton("MIC")
        mic.setObjectName("ChipBtn")
        mic.setCheckable(True)
        mic.clicked.connect(self.listen)
        self.call_mic = mic
        stop = QPushButton("STOP")
        stop.setObjectName("StopBtn")
        stop.clicked.connect(self.interrupt_speech)
        transcript = QPushButton("TRANSCRIPT")
        transcript.setObjectName("ChipBtn")
        transcript.clicked.connect(lambda: self.show_pane("transcript"))
        for control in (mic, stop, transcript):
            call_controls.addWidget(control)
        core_section.addLayout(call_controls)

        body.addWidget(call_stage, 5)

        # Right: persistent live transcript and compact diagnostics.
        right_section = QVBoxLayout()
        right_section.setSpacing(12)

        # A responsive grid prevents long labels being clipped.
        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(8)
        cards_grid.setVerticalSpacing(8)
        CARD_DATA = (
            ("Conversation", "transcript"),
            ("Media search", "media"),
            ("Notes", "notes"),
            ("Timers", "timers"),
            ("System", "system"),
            ("Settings", "settings"),
        )
        for index, (label, target) in enumerate(CARD_DATA):
            card = QPushButton(label)
            card.setObjectName("Card")
            card.setMinimumHeight(58)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setCursor(Qt.PointingHandCursor)
            card.clicked.connect(lambda _=False, t=target: self.show_pane(t))
            cards_grid.addWidget(card, index // 2, index % 2)
        right_section.addLayout(cards_grid)

        # Recent Activity
        activity_card = QFrame()
        activity_card.setObjectName("CallTranscript")
        activity_layout = QVBoxLayout(activity_card)

        act_header = QHBoxLayout()
        act_title = QLabel("Recent Activity")
        self._set_theme_style(act_title, "font-weight:700; color:@text@;")
        act_view_all = QPushButton("View all")
        act_view_all.setObjectName("Ghost")
        act_view_all.setFixedWidth(76)
        act_view_all.clicked.connect(lambda: self.show_pane("transcript"))
        act_header.addWidget(act_title)
        act_header.addStretch(1)
        act_header.addWidget(act_view_all)
        activity_layout.addLayout(act_header)

        self.activity_list = QTextBrowser()
        self.activity_list.setObjectName("Transcript")
        self.activity_list.setMinimumHeight(140)
        self.activity_list.document().setMaximumBlockCount(120)
        self.activity_list.setPlainText("Chat with Jarvis here. Type below or press Ctrl+Space to speak.")
        activity_layout.addWidget(self.activity_list)
        right_section.addWidget(activity_card)

        # Service Status & System Overview (Two cards)
        bottom_right = QHBoxLayout()

        # Service Status
        service_card = QFrame()
        service_card.setObjectName("Card")
        service_layout = QVBoxLayout(service_card)
        service_title = QLabel("Service Status")
        self._set_theme_style(service_title, "font-weight:700; color:@text@;")
        service_layout.addWidget(service_title)

        self.service_list = QLabel("Checking microphone and brain…")
        self.service_list.setObjectName("Muted")
        self.service_list.setWordWrap(True)
        self.service_list.setMinimumHeight(62)
        service_layout.addWidget(self.service_list)
        bottom_right.addWidget(service_card)

        # System Overview
        sys_card = QFrame()
        sys_card.setObjectName("Card")
        sys_layout = QVBoxLayout(sys_card)
        sys_title = QLabel("System Overview")
        self._set_theme_style(sys_title, "font-weight:700; color:@text@;")
        sys_layout.addWidget(sys_title)

        metrics_layout = QHBoxLayout()
        self.cpu_ring = QLabel("CPU 0%")
        self.mem_ring = QLabel("MEM 0%")
        self.stg_ring = QLabel("STG 0%")
        for ring in (self.cpu_ring, self.mem_ring, self.stg_ring):
            ring.setAlignment(Qt.AlignCenter)
            self._set_theme_style(ring, "font-weight:700; color:@accent@;")
            metrics_layout.addWidget(ring)
        sys_layout.addLayout(metrics_layout)
        bottom_right.addWidget(sys_card)

        right_section.addLayout(bottom_right)

        body.addLayout(right_section, 1)
        content_layout.addLayout(body, 1)
        self.overview_page = content
        self.pane_stack = QStackedWidget()
        self.panes = {
            "transcript": TranscriptPane(self),
            "media": MediaPane(self),
            "notes": NotesPane(self),
            "files": FilesPane(self),
            "contact": ContactPane(self),
            "improve": ImprovementPane(self),
            "routines": RoutinesPane(self),
            "timers": TimersPane(self),
            "system": SystemPane(self),
            "settings": SettingsPane(self),
            "help": HelpPane(self),
        }
        for key, _label in PANES:
            self.pane_stack.addWidget(self.panes[key])
        self.pane_stack.hide()
        layout.addWidget(self.overview_page, 1)
        layout.addWidget(self.pane_stack, 1)
        self.show_overview()
        return view

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(orbit_pixmap("#00E5FF", 64)), self)
        self.tray.setToolTip("Jarvis")
        menu = QMenu()
        actions = [
            ("Show Jarvis", self.show_window),
            ("Listen now", self.listen),
            None,
            ("Notes", lambda: self.show_pane("notes")),
            ("Timers", lambda: self.show_pane("timers")),
            ("System", lambda: self.show_pane("system")),
            ("Settings", lambda: self.show_pane("settings")),
            None,
            ("Toggle night mode", self.toggle_theme),
            ("Interrupt and continue", self.interrupt_speech),
            None,
            ("Quit Jarvis", self.quit_app),
        ]
        for item in actions:
            if item is None:
                menu.addSeparator()
                continue
            label, callback = item
            action = QAction(label, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _install_shortcuts(self) -> None:
        bindings = {
            "Ctrl+Space": self.listen,
            "Ctrl+K": self.open_palette,
            "Ctrl+Alt+J": self.toggle_window,
            "Ctrl+Alt+N": lambda: self.show_pane("notes"),
            "Ctrl+Alt+T": lambda: self.show_pane("timers"),
            "Ctrl+Alt+S": lambda: self.show_pane("settings"),
            "Ctrl+Shift+M": self.toggle_theme,
            "F11": self.toggle_fullscreen,
            "Escape": self.interrupt_speech,
        }
        self._shortcuts: list[QShortcut] = []
        for keys, callback in bindings.items():
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        for keys, callback in {"Ctrl+Return": self._submit_command, "Ctrl+L": self._focus_command}.items():
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _wire_bus(self) -> None:
        self.bus.state_changed.connect(self._on_state)
        self.bus.level.connect(self._on_level)
        self.bus.transcript.connect(self._on_transcript)
        self.bus.reply_chunk.connect(self._on_chunk)
        self.bus.reply_done.connect(self._on_reply)
        self.bus.toast.connect(self._on_toast)
        self.bus.notes_changed.connect(self._on_notes)
        self.bus.notes_changed.connect(lambda _notes: self._refresh_file_results())
        self.bus.timers_changed.connect(self._on_tasks)
        self.bus.reminders_changed.connect(self._on_tasks)
        self.bus.media_changed.connect(self._on_media)
        self.bus.tts_state.connect(self._on_tts)
        self.bus.speak_requested.connect(lambda text, force: self.tts.speak(text, bool(force)))
        self.bus.duck_media.connect(lambda active: self.bridges.duck(bool(active)))
        self.bus.ui_command.connect(self._on_ui_command)
        self.bus.error.connect(lambda message: self.toast(str(message), "error"))

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def _post_start(self) -> None:
        self._update_route_chip()
        self._populate_routes()
        if hasattr(self, "command_deck"):
            self.command_deck.set_states(
                bool(self.settings.get("wake.enabled", True)),
                bool(self.settings.get("screen.sharing", False)),
                bool(self.settings.get("briefing.enabled", False)),
                bool(self.settings.get("tts.enabled", True)),
            )
        self.task_bar.finish_task(text="dashboard ready · voice and chat online")
        self._ticker("jarvis online · " + current_label(self.settings))
        try:
            self.bridges.keep_awake(bool(self.settings.get("keep_awake", True)))
        except Exception:
            pass
        self._tick_stats()
        self._tick_media()
        self._refresh_panes()

        if hasattr(self, "greeting"):
            self.greeting.setText("Welcome back. I’m Jarvis.")
        if not self.hidden_start and not self.no_voice and self.settings.get("tts.enabled", True):
            self.tts.speak("Welcome back, boss. I am Jarvis. All systems are ready.")

        status = self.voice.status()
        last_transcript = str(status.get("last_transcript", "") or "").strip()
        if last_transcript:
            self._append_home_message("YOU", last_transcript)
        if status.get("last_reply"):
            last_reply = str(status["last_reply"])
            self._append_home_message("JARVIS", last_reply)
            self.mini_reply.setText(last_reply[:220])

    def save_geometry(self) -> None:
        if not self.settings.get("ui.remember_geometry", True):
            return
        geometry = self.geometry()
        self.settings.set(
            f"ui.sizes.{self._mode}",
            [geometry.x(), geometry.y(), geometry.width(), geometry.height()],
            save=False,
        )
        positions = {}
        for key, bob in self._bobs.items():
            positions[key] = [bob.x(), bob.y()]
        self.settings.set("ui.bob_positions", positions, save=False)
        self.settings.save()

    def _restore_geometry(self) -> None:
        sizes = self.settings.get(f"ui.sizes.{self._mode}", None)
        if isinstance(sizes, list) and len(sizes) == 4:
            try:
                x, y, width, height = (int(value) for value in sizes)
                if width >= 500 and height >= 480:
                    screen = QApplication.primaryScreen().availableGeometry()
                    if width > screen.width():
                        width = screen.width()
                    if height > screen.height():
                        height = screen.height()
                    x = min(max(x, screen.left()), screen.right() - width + 1)
                    y = min(max(y, screen.top()), screen.bottom() - height + 1)
                    if not screen.intersects(QRect(x, y, width, height)):
                        x, y = screen.center().x() - width // 2, screen.center().y() - height // 2
                    self.setGeometry(x, y, width, height)
                    return
            except (TypeError, ValueError):
                pass
        self._center()

    def _center(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        size = self.size()
        self.move(screen.center().x() - size.width() // 2, screen.center().y() - size.height() // 2)

    def _resize_centered(self, width: int, height: int) -> None:
        if self.isVisible() and self.width() > 200 and self.height() > 200:
            center = self.frameGeometry().center()
            self.resize(width, height)
            self.move(center.x() - width // 2, center.y() - height // 2)
        else:
            self.resize(width, height)
            self._center()

    def _shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.save_geometry()
        try:
            self.voice.shutdown()
        except Exception:
            pass
        try:
            self.tts.shutdown()
        except Exception:
            pass
        try:
            self.notes.stop()
        except Exception:
            pass
        try:
            self.tasks._ticker.stop()  # noqa: SLF001 - deliberate orderly stop
        except Exception:
            pass
        if self._server is not None:
            self._server.close()
        for bob in list(self._bobs.values()):
            bob.close()
        self._bobs.clear()
        self.tray.hide()
        self.log.info("Jarvis stopped")

    def quit_app(self) -> None:
        self._really_quit = True
        QApplication.instance().quit()

    def closeEvent(self, event: Any) -> None:
        if self._really_quit or self._shutting_down:
            event.accept()
            return
        event.ignore()
        self.hide_window()

    # ------------------------------------------------------------------
    # layout / theme
    # ------------------------------------------------------------------
    def set_mode(self, mode: str, save: bool = True, resize: bool = True) -> None:
        mode = "power" if str(mode).lower() == "power" else "minimal"
        if resize and self._mode != mode:
            self.save_geometry()
        self._mode = mode
        if mode == "power":
            self.stack.setCurrentWidget(self.power_view)
            if resize:
                self.setMinimumSize(980, 620)
                self._resize_centered(1180, 720)
        else:
            self.stack.setCurrentWidget(self.minimal_view)
            if resize:
                self.setMinimumSize(520, 500)
                self._resize_centered(540, 540)
        self.titlebar.refresh_layout_icon()
        if hasattr(self, "titlebar"):
            self.titlebar.pin.setVisible(mode == "power")
        if save:
            self.settings.set("ui.mode", mode)
        if mode == "power":
            self.orb.set_animations(bool(self.settings.get("ui.animations", True)))
            self.mini_orb.set_animations(False)
        else:
            self.mini_orb.set_animations(bool(self.settings.get("ui.animations", True)))
            self.orb.set_animations(False)

    def toggle_mode(self) -> None:
        self.set_mode("minimal" if self._mode == "power" else "power")

    def toggle_maximized(self) -> None:
        if self.isFullScreen():
            self.toggle_fullscreen()
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.titlebar.refresh_window_icon()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self._fullscreen = False
            self.setMinimumSize(480, 430)
            if self._pre_fullscreen_mode != self._mode:
                self.set_mode(self._pre_fullscreen_mode, save=False, resize=False)
            if self._pre_fullscreen_geometry is not None:
                self.setGeometry(self._pre_fullscreen_geometry)
            self._ticker("windowed")
        else:
            self._pre_fullscreen_geometry = self.geometry()
            self._pre_fullscreen_mode = self._mode
            if self._mode != "power":
                self.set_mode("power", save=False, resize=False)
            self.setMinimumSize(0, 0)
            self.showFullScreen()
            self._fullscreen = True
            self._ticker("fullscreen HUD · F11 to exit")
        self.titlebar.refresh_window_icon()

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "titlebar"):
            self.titlebar.refresh_window_icon()

    def toggle_theme(self) -> None:
        self.apply_theme("dark" if self._theme == "light" else "light")

    def apply_theme(self, name: str, save: bool = True, startup: bool = False) -> None:
        name = name if name in PALETTES else "light"
        self._theme = name
        palette = PALETTES[name]
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(name))
        for widget, template in self._theme_styles:
            widget.setStyleSheet(resolve_theme_tokens(template, palette))
        for orb in (getattr(self, "orb", None), getattr(self, "mini_orb", None)):
            if orb is not None:
                orb.set_palette(palette)
        if hasattr(self, "titlebar"):
            self.titlebar.set_route(self._route_text())
        system = self.panes.get("system") if hasattr(self, "panes") else None
        if system is not None:
            system.cpu_spark.set_accent(palette["accent2"], palette["border"])
            system.mem_spark.set_accent(palette["accent"], palette["border"])
        tooltip = palette
        self.setStyleSheet(f"QToolTip {{ background:{tooltip['surface']}; color:{tooltip['text']}; }}")
        self.update()
        if save:
            self.settings.set("ui.theme", name)
        if not startup:
            self.toast("Night mode." if name == "dark" else "Day mode.", "info")
        self._refresh_panes()

    def _auto_theme(self) -> None:
        if not self.settings.get("ui.auto_night_theme", True):
            return
        wanted = "dark" if night_now(self.settings) else "light"
        if wanted != self._theme:
            self.apply_theme(wanted, save=False)

    def set_gaming_mode(self, enabled: bool, save: bool = True, announce: bool = True) -> None:
        """Pause dashboard polling and decorative animation while gaming."""
        enabled = bool(enabled)
        self.settings.set("performance.gaming_mode", enabled, save=save)
        if enabled:
            self._stats_timer.stop()
            self._media_timer.stop()
            self._briefing_timer.stop()
        else:
            self._stats_timer.start()
            self._media_timer.start()
            self._briefing_timer.start()
            self._tick_stats()
            self._tick_media()
        animations = bool(self.settings.get("ui.animations", True)) and not enabled
        if getattr(self, "orb", None) is not None:
            self.orb.set_animations(animations)
        if announce:
            message = "Gaming Mode on. Dashboard polling and orb animations paused." if enabled else "Gaming Mode off. Dashboard updates restored."
            self.toast(message, "info")

    def toggle_on_top(self) -> None:
        on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, not on_top)
        self.titlebar.pin.setChecked(not on_top)
        self.settings.set("ui.always_on_top", not on_top)
        self.show()

    # ------------------------------------------------------------------
    # painting
    # ------------------------------------------------------------------
    def paintEvent(self, event: Any) -> None:
        palette = PALETTES[self._theme]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height()), 18, 18)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(palette["surface"]))
        gradient.setColorAt(1.0, QColor(palette["bg"]))
        painter.setPen(QPen(QColor(palette["edge"]), 1.0))
        painter.fillPath(path, gradient)
        painter.drawPath(path)
        painter.end()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        grip = getattr(self, "_grip", None)
        if grip is not None:
            if self._mode == "power":
                grip.move(self.width() - 22, self.height() - 22)
                grip.raise_()
                grip.show()
            else:
                grip.hide()

    # ------------------------------------------------------------------
    # window actions
    # ------------------------------------------------------------------
    def show_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def hide_window(self) -> None:
        self.save_geometry()
        self.hide()

    def toggle_window(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide_window()
        else:
            self.show_window()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_window()

    def stack_set_index(self, index: int) -> None:
        if not hasattr(self, "pane_stack") or not (0 <= index < self.pane_stack.count()):
            return
        self.pane_stack.setCurrentIndex(index)
        self.overview_page.hide()
        self.pane_stack.show()
        key = PANES[index][0]
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)
        self._refresh_panes()

    def show_overview(self) -> None:
        if hasattr(self, "pane_stack"):
            self.pane_stack.hide()
        if hasattr(self, "overview_page"):
            self.overview_page.show()
        if hasattr(self, "nav_group"):
            self.nav_group.setExclusive(False)
            for button in self.nav_buttons.values():
                button.setChecked(False)
            self.nav_group.setExclusive(True)
            self.nav_buttons["overview"].setChecked(True)

    def show_pane(self, name: str) -> None:
        aliases = {
            "conversation": "transcript",
            "chat": "transcript",
            "timer": "timers",
            "reminder": "timers",
            "reminders": "timers",
            "note": "notes",
            "stats": "system",
            "preferences": "settings",
            "commands": "help",
            "knowledge": "notes",
            "groceries": "notes",
            "file": "files",
            "relationship map": "files",
            "map": "files",
            "improve jarvis": "improve",
        }
        key = aliases.get(str(name).lower(), str(name).lower())
        if key in ("overview", "home", "dashboard"):
            if self._mode != "power":
                self.set_mode("power")
            self.show_overview()
            self.show_window()
            return
        index = next((i for i, (pane, _) in enumerate(PANES) if pane == key), None)
        if index is None:
            self.toast(f"No {name} pane.", "warn")
            return
        if self._mode != "power":
            self.set_mode("power")
        self.stack_set_index(index)
        self.show_window()

    def _refresh_panes(self) -> None:
        if not hasattr(self, "panes"):
            return
        try:
            self.panes["notes"].refresh()
        except Exception:
            pass
        try:
            self.panes["timers"].refresh()
        except Exception:
            pass
        if "settings" in self.panes:
            try:
                self.panes["settings"].sync()
            except Exception:
                pass
        if "help" in self.panes:
            try:
                self.panes["help"].refresh()
            except Exception:
                pass
        self._sync_pending_bobs()

    # ------------------------------------------------------------------
    # status helpers
    # ------------------------------------------------------------------
    def _populate_routes(self) -> None:
        if not hasattr(self, "model_selector"):
            return
        items = []
        for route in ROUTES:
            available, reason = route_available(route, self.settings)
            items.append(
                {
                    "id": route["id"],
                    "label": route["label"],
                    "available": available,
                    "reason": reason,
                }
            )
        self.model_selector.set_routes(items)
        self.model_selector.set_current(current_route(self.settings)["id"])

    def _route_text(self) -> str:
        route = current_route(self.settings)
        model = str(route.get("model", "")).split("/")[-1]
        return f"{current_label(self.settings)} · {model}"

    def _update_route_chip(self) -> None:
        text = self._route_text()
        self.titlebar.set_route(text)
        if hasattr(self, "route_label"):
            self.route_label.setText(text)
        if hasattr(self, "model_selector"):
            self.model_selector.set_current(current_route(self.settings)["id"])
        if hasattr(self, "mini_footer"):
            self.mini_footer.setText(
                f"{current_label(self.settings)}  ·  Ctrl+Space talk  ·  Ctrl+K commands  ·  Esc stop"
            )

    def _apply_route_ui(self, route_id: str) -> None:
        if hasattr(self, "model_selector"):
            self.model_selector.set_current(route_id)
        self._update_route_chip()
        self._ticker(f"brain · {current_label(self.settings)}")
        self.voice._warned_key = False  # type: ignore[attr-defined]

    def _on_model_changed(self, route_id: str) -> None:
        if not route_id:
            return
        if current_route(self.settings)["id"] == route_id:
            return
        ok, message = apply_route(self.settings, route_id)
        if not ok:
            self.toast(message, "error")
            self._ticker(f"brain · {message}")
            self.model_selector.set_current(current_route(self.settings)["id"])
            return
        self._apply_route_ui(route_id)
        self.toast(message, "ok")
        if hasattr(self, "side_status"):
            self.side_status.setText(message)

    def _set_orb_state(self, state: str) -> None:
        if hasattr(self, "call_label"):
            phase = {
                "idle": "LIVE SESSION", "listening": "LISTENING", "transcribing": "TRANSCRIBING",
                "thinking": "THINKING", "speaking": "SPEAKING", "error": "SYSTEM FAULT",
            }.get(state, "LIVE SESSION")
            self.call_label.setText(f"JARVIS · {phase}")
        if hasattr(self, "call_mic"):
            self.call_mic.setChecked(state in ("listening", "transcribing"))
        if hasattr(self, "call_stage"):
            palette = PALETTES[self._theme]
            light = {
                "idle": palette["accent"], "listening": "#FF9D2E", "transcribing": palette["warn"],
                "thinking": palette["warn"], "speaking": "#FF9D2E", "error": palette["danger"],
            }.get(state, palette["accent"])
            color = QColor(light)
            alpha = 0 if not bool(self.settings.get("ui.animations", True)) else 54
            self.call_stage.setStyleSheet(
                "QFrame#CallStage {"
                f"border: 1px solid rgba({color.red()}, {color.green()}, {color.blue()}, 205);"
                f"background: qradialgradient(cx:0.5, cy:0.42, radius:0.72, "
                f"stop:0 rgba({color.red()}, {color.green()}, {color.blue()}, {alpha}), "
                "stop:0.58 rgba(5,7,10,242), stop:1 rgba(13,18,24,255));"
                "}"
            )
        for orb in (getattr(self, "orb", None), getattr(self, "mini_orb", None)):
            if orb is not None:
                orb.set_state(state)

    def _status_text(self) -> tuple[str, str]:
        palette = PALETTES[self._theme]
        if self._speaking:
            return "SPEAKING", palette["accent2"]
        mapping = {
            "idle": ("STANDBY", palette["accent"]),
            "listening": ("LISTENING", palette["accent2"]),
            "transcribing": ("TRANSCRIBING", palette["warn"]),
            "thinking": ("THINKING", palette["warn"]),
            "speaking": ("SPEAKING", palette["accent2"]),
            "error": ("FAULT", palette["danger"]),
        }
        return mapping.get(self._state, ("STANDBY", palette["accent"]))

    def _refresh_status(self) -> None:
        if time.time() < self._activity_until:
            label, color = self._activity.upper(), PALETTES[self._theme]["accent2"]
        else:
            label, color = self._status_text()
        self.titlebar.set_state(label, color)
        if hasattr(self, "state_label"):
            if self.state_label.text() != label:
                self.state_label.setText(label)
            if getattr(self, "_status_color", None) != color:
                self._status_color = color
                self.state_label.setStyleSheet(f"color:{color};")
        status = self.voice.status()
        bits = []
        if label == "STANDBY":
            follow = int(status.get("follow_up", 0) or 0)
            if follow > 0:
                bits.append(f"Listening for a follow-up · {follow}s")
            elif not status.get("wake", True):
                bits.append("Wake word off · Ctrl+Space to talk")
            elif self.no_voice:
                bits.append("Text-only mode")
            else:
                bits.append("Say “Jarvis” to begin")
        else:
            bits.append(label.capitalize() + "…")
        if status.get("mode") == "ptt":
            bits.append("push-to-talk")
        text = " · ".join(bits)
        if hasattr(self, "mini_status"):
            self.mini_status.setText(text.upper() if label != "STANDBY" else text)
        if hasattr(self, "side_status"):
            self.side_status.setText(text)
        files_pane = self.panes.get("files") if hasattr(self, "panes") else None
        if files_pane is not None:
            files_pane.update_runtime_status()

    # ------------------------------------------------------------------
    # timers / polling
    # ------------------------------------------------------------------
    def _tick_ui(self) -> None:
        now = time.localtime()
        self.titlebar.set_clock(time.strftime("%H:%M"))
        if hasattr(self, "rail_clock"):
            self.rail_clock.setText(time.strftime("%H:%M"))
        if hasattr(self, "rail_date"):
            self.rail_date.setText(time.strftime("%A, %d %B"))
        self._refresh_status()
        self._update_bobs_text()
        if self._mode == "power" and "timers" in self.panes:
            self.panes["timers"].tick()

    def _tick_stats(self) -> None:
        try:
            stats = self.bridges.system_stats()
        except Exception:
            return
        if "system" in self.panes:
            self.panes["system"].update_stats(stats)
        memory = stats.get("memory", {})
        cpu = float(stats.get("cpu", 0.0))
        available = float(memory.get("available", 0)) / 1024 / 1024
        self.rail_stats.setText(f"CPU {cpu:.0f}%\nRAM {memory.get('percent', 0):.0f}%\n{available:.1f} GB free")
        self.cpu_ring.setText(f"CPU\n{cpu:.0f}%")
        self.mem_ring.setText(f"RAM\n{memory.get('percent', 0):.0f}%")
        try:
            disk = __import__("shutil").disk_usage(ROOT)
            used = 100.0 * (disk.total - disk.free) / max(1, disk.total)
            self.stg_ring.setText(f"DISK\n{used:.0f}%")
        except OSError:
            self.stg_ring.setText("DISK\n—")
        voice = self.voice.status()
        elapsed = max(0, int(time.monotonic() - self._call_started))
        if hasattr(self, "call_clock"):
            self.call_clock.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        mic = "ready" if voice.get("capture_alive") else "unavailable"
        self.service_list.setText(f"Microphone · {mic}\nBrain · {current_label(self.settings)}")

    def _tick_media(self) -> None:
        # Media data only feeds the System pane; polling DBus/playerctl from
        # the minimal orb just burns battery.
        if self._mode != "power" or not self.isVisible():
            return
        try:
            info = self.bridges.media_info()
        except Exception:
            return
        if "system" in self.panes:
            self.panes["system"].update_media(info)

    # ------------------------------------------------------------------
    # bus handlers
    # ------------------------------------------------------------------
    def _on_state(self, state: str) -> None:
        self._state = state
        waiting = state in ("transcribing", "thinking")
        for button in (getattr(self, "send_btn", None), getattr(self, "main_send_btn", None)):
            if button is not None:
                button.setEnabled(not waiting)
                button.setText("Working…" if waiting else "Send")
        self._set_orb_state("speaking" if self._speaking else state)
        self._refresh_status()
        labels = {
            "listening": "listening · microphone armed",
            "transcribing": "transcribing · whisper",
            "thinking": "thinking · routing",
            "speaking": "speaking · voice channel",
            "idle": "ready · standing by",
            "error": "fault · check the log",
        }
        if state in labels:
            self._ticker(labels[state])

    def _on_level(self, level: float) -> None:
        for orb in (getattr(self, "orb", None), getattr(self, "mini_orb", None)):
            if orb is not None:
                orb.set_level(float(level))

    def _on_transcript(self, text: str, final: bool) -> None:
        clean = " ".join(str(text).split())
        if hasattr(self, "call_caption"):
            self.call_caption.setText(f"YOU · {clean}" if clean else "Listening…")
        if final and clean:
            self.panes["transcript"].add("user", clean)
            self._append_home_message("YOU", text.strip())
            self._ticker("heard · " + " ".join(text.split())[:90])

    def _on_chunk(self, piece: str) -> None:
        self._live_text = (self._live_text + piece)[-2000:]
        text = " ".join(self._live_text.split())
        if hasattr(self, "side_reply"):
            self.side_reply.setText(text[-260:])
        if hasattr(self, "mini_reply"):
            self.mini_reply.setText(text[-180:])
        if text:
            self.call_caption.setText(f"JARVIS · {text[-240:]}")
            self._render_home_live(text)
        # Streamed text means the model is thinking; only the audio engine's
        # tts_state signal may set the orb to SPEAKING.
        self._set_orb_state("thinking")

    def _on_reply(self, text: str) -> None:
        self._live_text = ""
        clean = " ".join(str(text).split())
        self.task_bar.finish_task(text="last reply · " + clean[:80])
        self.panes["transcript"].add("assistant", clean)
        self._append_home_message("JARVIS", clean)
        if hasattr(self, "call_caption"):
            self.call_caption.setText(f"JARVIS · {clean[:240]}")
        if hasattr(self, "mini_reply"):
            self.mini_reply.setText(clean[:220])
        self._refresh_status()
        for callback in list(self._ask_callbacks):
            try:
                callback(clean)
            except Exception:
                pass
        self._ask_callbacks.clear()
        if self._ask_suppress:
            self._ask_suppress = 0
            self.tts.set_suppressed(False)
        for waiter in list(self._waiters):
            try:
                payload = json.dumps({"reply": clean, "ok": True}) + "\n"
                waiter.write(payload.encode("utf-8"))
                waiter.flush()
                waiter.disconnectFromServer()
            except Exception:
                pass
            self._waiters.discard(waiter)

    def _append_home_message(self, speaker: str, message: str) -> None:
        clean = " ".join(str(message).split())
        if not clean:
            return
        self._home_messages.append((speaker, clean))
        self._home_messages = self._home_messages[-12:]
        self._render_home_live("")

    def _render_home_live(self, live: str) -> None:
        if not hasattr(self, "activity_list"):
            return
        blocks = []
        for speaker, message in self._home_messages[-8:]:
            color = "#0E7490" if speaker == "YOU" else "#0284C7"
            blocks.append(
                f'<p style="margin:7px 0"><b style="color:{color}">{speaker}</b><br>'
                f'{html.escape(message)}</p>'
            )
        if live:
            blocks.append(
                '<p style="margin:7px 0"><b style="color:#0284C7">JARVIS</b><br>'
                f'{html.escape(live)}</p>'
            )
        if blocks:
            self.activity_list.setHtml("".join(blocks))
        else:
            self.activity_list.setPlainText("Chat with Jarvis here. Type below or press Ctrl+Space to speak.")
        bar = self.activity_list.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_tts(self, speaking: bool) -> None:
        self._speaking = bool(speaking)
        self._set_orb_state("speaking" if speaking else self._state)
        self._refresh_status()

    def _on_toast(self, message: str, kind: str = "info") -> None:
        self.toast(message, kind)

    def _on_notes(self, notes: list) -> None:
        if "notes" in self.panes:
            try:
                self.panes["notes"].refresh()
            except Exception:
                pass
        files_pane = self.panes.get("files")
        if files_pane is not None:
            try:
                files_pane._refresh_groups()
            except Exception:
                pass
        count = len(notes or [])
        if count:
            self.titlebar.pin.setToolTip(f"Keep Jarvis on top · {count} notes stored")

    def _refresh_file_results(self) -> None:
        pane = getattr(self, "panes", {}).get("files")
        if pane is not None and pane.query.text().strip():
            pane.search()

    def _on_tasks(self, items: list) -> None:
        if "timers" in self.panes:
            try:
                self.panes["timers"].refresh()
            except Exception:
                pass
        self._sync_pending_bobs()
        self._update_bobs_text()

    def _on_media(self, info: Any) -> None:
        if "system" in self.panes and isinstance(info, dict):
            self.panes["system"].update_media(info)

    def _on_ui_command(self, action: str, payload: Any) -> None:
        if action == "confirm_action" and isinstance(payload, dict):
            answer = QMessageBox.question(
                self,
                str(payload.get("title", "Confirm assistant action")),
                str(payload.get("details", "Allow this action?")),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if self.voice is not None:
                self.voice.resolve_confirmation(str(payload.get("id", "")), answer == QMessageBox.StandardButton.Yes)
        elif action == "search_media":
            self.show_pane("media")
            self.panes["media"].search(str(payload or ""))
        elif action == "show_pane":
            self.show_pane(str(payload))
        elif action == "prepare_code_change":
            pane = self.panes.get("improve")
            if pane is not None:
                self.show_pane("improve")
                pane.prepare(str(payload or ""))
        elif action == "files_indexed":
            pane = self.panes.get("files")
            if pane is not None:
                pane.galaxy.refresh()
        elif action == "knowledge_sources":
            pane = self.panes.get("files")
            if pane is not None:
                pane.galaxy.set_sources(payload if isinstance(payload, dict) else {})
        elif action == "files_scan_progress":
            pane = self.panes.get("files")
            if pane is not None:
                pane.update_scan_progress(int(payload or 0))
        elif action == "image_tag_progress":
            pane = self.panes.get("files")
            if pane is not None:
                pane.update_image_tag_progress(payload)
        elif action == "contact_alert":
            card = payload if isinstance(payload, dict) else {}
            self.toast(f"{card.get('title', 'Jarvis alert')} · {card.get('body', '')}"[:240], "info")
            pane = self.panes.get("contact")
            if pane is not None:
                pane.refresh()
        elif action == "set_mode":
            self.set_mode(str(payload))
        elif action == "set_theme":
            self.apply_theme(str(payload))
        elif action == "hide_window":
            self.hide_window()
        elif action == "show_window":
            self.show_window()
        elif action == "clear_transcript":
            self.panes["transcript"].clear()
            self._live_text = ""
            if hasattr(self, "call_caption"):
                self.call_caption.setText("Say the wake word or start typing to begin.")
        elif action == "memory_changed":
            self.toast("Memory updated.", "ok")
        elif action == "task_fired":
            label = payload.get("label") if isinstance(payload, dict) else "Timer"
            self.contacts.add(str(label or "Reminder"), "Reminder is due.", "reminder")
            contact_pane = self.panes.get("contact")
            if contact_pane is not None:
                contact_pane.refresh()
            self.toast(f"{label} — done.", "ok")
        elif action == "tool_activity":
            self._activity = str(payload)
            self._activity_until = time.time() + 6.0
            self.task_bar.start_task(f"tool · {payload}")
            self._ticker(f"tool · {payload}")
            self._refresh_status()
        elif action == "brain_route":
            if isinstance(payload, dict):
                provider = str(payload.get("provider", ""))
                model = str(payload.get("model", "")).split("/")[-1]
                heavy = bool(payload.get("heavy"))
                self._ticker(f"route · {provider} · {model}" + (" · heavy" if heavy else ""))
        elif action == "route_applied":
            self._apply_route_ui(str(payload))
            if "files" in self.panes:
                self.panes["files"].update_runtime_status()
            if hasattr(self, "side_status"):
                self.side_status.setText(f"Brain: {current_label(self.settings)}")
        elif action == "screen_share_changed":
            self._on_screen_share(bool(payload))
        elif action == "briefing_changed":
            self._on_briefing(bool(payload))
        elif action == "ticker":
            text = payload.get("text", "") if isinstance(payload, dict) else payload
            self._ticker(str(text))
        elif action == "focus_start":
            if isinstance(payload, dict):
                self._focus_start(int(payload.get("seconds", 0) or 0), str(payload.get("mode", "countdown")))
            else:
                self._focus_start(0, "stopwatch")
        elif action == "focus_pause":
            self.titlebar.focus.pause()
        elif action == "focus_resume":
            self.titlebar.focus.resume()
        elif action == "focus_reset":
            self.titlebar.focus.reset()
            self._focus_mode = "idle"

    # ------------------------------------------------------------------
    # HUD actions
    # ------------------------------------------------------------------
    def _ticker(self, text: str) -> None:
        if not bool(self.settings.get("hud.ticker", True)):
            return
        deck = getattr(self, "command_deck", None)
        if deck is not None:
            deck.push_ticker(str(text))

    def _focus_start(self, seconds: int, mode: str = "countdown") -> None:
        focus = self.titlebar.focus
        if mode == "stopwatch" or seconds <= 0:
            focus.start_stopwatch()
            self._focus_mode = "stopwatch"
            self._ticker("focus · stopwatch running")
        else:
            focus.start(seconds, "countdown")
            self._focus_mode = "countdown"
            self._ticker(f"focus · {human_duration(seconds)} on the clock")
        if self._mode == "minimal":
            self.show_window()

    def _on_focus_finished(self) -> None:
        self._focus_mode = "idle"
        self._ticker("focus · session complete")
        self.toast("Focus session complete — well held, sir.", "ok")
        self.bridges.notify("Jarvis", "Focus session complete.")
        self.bus.speak_requested.emit("Focus session complete, sir.", True)

    def _on_hands_free(self, enabled: bool) -> None:
        enabled = bool(enabled)
        try:
            self.voice.set_wake_enabled(enabled)
        except Exception:
            pass
        self.command_deck.set_states(
            enabled,
            bool(self.settings.get("screen.sharing", False)),
            bool(self.settings.get("briefing.enabled", False)),
            bool(self.settings.get("tts.enabled", True)),
        )
        self._ticker("wake word on" if enabled else "wake word off")

    def _on_voice_output(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.set("tts.enabled", enabled)
        self.command_deck.set_states(
            bool(self.settings.get("wake.enabled", True)),
            bool(self.settings.get("screen.sharing", False)),
            bool(self.settings.get("briefing.enabled", False)),
            enabled,
        )
        self.toast("Spoken replies on." if enabled else "Spoken replies muted.", "info")

    def _on_screen_share(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.set("screen.sharing", enabled)
        self.command_deck.set_states(
            bool(self.settings.get("wake.enabled", True)),
            enabled,
            bool(self.settings.get("briefing.enabled", False)),
            bool(self.settings.get("tts.enabled", True)),
        )
        self.toast(
            "Screen context on — I can read the display when asked." if enabled
            else "Screen context off.",
            "ok" if enabled else "info",
        )
        self._ticker("screen context on" if enabled else "screen context off")

    def _on_briefing(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.set("briefing.enabled", enabled)
        self.command_deck.set_states(
            bool(self.settings.get("wake.enabled", True)),
            bool(self.settings.get("screen.sharing", False)),
            enabled,
            bool(self.settings.get("tts.enabled", True)),
        )
        self.toast("Daily briefing on." if enabled else "Daily briefing off.", "ok")
        self._ticker("briefing scheduled" if enabled else "briefing off")

    def _check_briefing(self) -> None:
        if not bool(self.settings.get("briefing.enabled", False)):
            return
        wanted = str(self.settings.get("briefing.time", "08:00") or "08:00")
        now = time.strftime("%H:%M")
        today = time.strftime("%Y-%m-%d")
        if now != wanted or str(self.settings.get("briefing.last", "")) == today:
            return
        self.settings.set("briefing.last", today)
        self.task_bar.start_task("daily briefing")
        self._ticker("briefing · compiling")

        def ready(text: Any) -> None:
            self.task_bar.finish_task(text="briefing delivered")
            message = str(text or "")
            if message:
                self.toast(message[:420], "info")
                self.bus.speak_requested.emit(message, True)
                self._ticker("briefing · delivered")

        self.run_async(self.voice.briefing, ready)

    # ------------------------------------------------------------------
    # bobs
    # ------------------------------------------------------------------
    def _sync_pending_bobs(self) -> None:
        items = {item["id"]: item for item in self.tasks.list_items()}
        screen = QApplication.primaryScreen().availableGeometry()
        positions = self.settings.get("ui.bob_positions", {}) or {}
        for key in list(self._bobs):
            if key not in items:
                self._bobs[key].close()
                self._bobs.pop(key, None)
        index = 0
        for key, item in items.items():
            bob = self._bobs.get(key)
            if bob is None:
                bob = BobWindow(str(item.get("kind", "timer")))
                self._bobs[key] = bob
                saved = positions.get(key) if isinstance(positions, dict) else None
                if isinstance(saved, list) and len(saved) == 2:
                    bob.move(int(saved[0]), int(saved[1]))
                else:
                    bob.move(screen.right() - bob.width() - 22, screen.bottom() - 78 - index * 68)
                bob.show()
            index += 1
        self._update_bobs_text()

    def _update_bobs_text(self) -> None:
        palette = PALETTES[self._theme]
        for key, bob in list(self._bobs.items()):
            item = self.tasks.get(key) if hasattr(self.tasks, "get") else None
            if item is None:
                item = next((entry for entry in self.tasks.list_items() if entry["id"] == key), None)
            if item is None:
                continue
            if item["kind"] == "timer":
                remaining = int(item.get("remaining", 0) or 0)
                bob.set_data(item.get("label", "Timer"), friendly_remaining(remaining), palette["accent2"])
                bob.setToolTip(f"{item.get('label', 'Timer')} · {friendly_remaining(remaining)} left")
            else:
                due = int(item.get("due", 0) or 0)
                bob.set_data(item.get("label", "Reminder"), time.strftime("%H:%M", time.localtime(due)), palette["accent"])
                bob.setToolTip(f"{item.get('label', 'Reminder')} at {time.strftime('%H:%M', time.localtime(due))}")

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _chip(self, target: str) -> None:
        if target == "listen":
            self.listen()
        elif target == "palette":
            self.open_palette()
        else:
            self.show_pane(target)

    def _submit_from(self, field: QLineEdit) -> None:
        text = field.text().strip()
        if not text:
            return
        field.clear()
        self.ask(text)

    def _submit_command(self) -> None:
        field = self.main_command if self._mode == "power" else self.command
        self._submit_from(field)

    def _focus_command(self) -> None:
        if self._mode != "power":
            self.show_window()
        self.command.setFocus()
        self.command.selectAll()

    def ask(self, text: str, speak: bool = True, callback: Callable[[str], None] | None = None, show: bool = True) -> None:
        text = (text or "").strip()
        if not text:
            return
        if callback is not None:
            self._ask_callbacks.append(callback)
        if not speak:
            self._ask_suppress += 1
            self.tts.set_suppressed(True)
        if show:
            self.show_window()
        self._set_orb_state("thinking")
        self.voice.submit_text(text, source="typed")

    def listen(self) -> None:
        self.show_window()
        self.voice.listen_once()

    def stop_speaking(self) -> None:
        self.tts.stop()
        self._speaking = False
        self._set_orb_state(self._state if self._state != "speaking" else "idle")
        self._refresh_status()

    def interrupt_speech(self) -> None:
        """Stop the current reply, acknowledge, then reopen the microphone."""
        self.tts.stop()
        self._speaking = False
        if self.settings.get("tts.enabled", True):
            self.tts.speak("Go ahead. I am listening.", force=True)
            self._set_orb_state("speaking")

            def reopen_mic() -> None:
                if self.tts.is_speaking():
                    QTimer.singleShot(100, reopen_mic)
                    return
                self.voice.listen_once()
                self._set_orb_state("listening")
                self._refresh_status()

            QTimer.singleShot(100, reopen_mic)
        else:
            self.voice.listen_once()
            self._set_orb_state("listening")
            self.toast("Stopped. Go ahead — I am listening.", "info")
        self._refresh_status()

    def open_palette(self) -> None:
        dialog = PaletteDialog(self, last_reply=str(self.voice.status().get("last_reply", "")))
        dialog.submitted.connect(lambda text: self.ask(text))
        dialog.exec()

    def toast(self, message: str, kind: str = "info") -> None:
        try:
            toast = getattr(self, "toasts", None)
            if toast is not None:
                toast.show(str(message), kind)
        except Exception:
            pass
        self.log.info("toast [%s] %s", kind, message)

    # ------------------------------------------------------------------
    # async helpers
    # ------------------------------------------------------------------
    def run_async(self, func: Callable[[], Any], callback: Callable[[Any], None] | None = None) -> None:
        job = _Job(func)
        self._jobs.add(job)

        def done(result: Any) -> None:
            self._jobs.discard(job)
            if callback is not None:
                try:
                    callback(result)
                except Exception as exc:  # noqa: BLE001
                    self.toast(str(exc), "error")

        def failed(message: str) -> None:
            self._jobs.discard(job)
            self.toast(message, "error")

        job.signals.done.connect(done)
        job.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(job)

    # ------------------------------------------------------------------
    # IPC
    # ------------------------------------------------------------------
    def set_heavy(self, enabled: bool) -> None:
        self.settings.set("llm.force_heavy", bool(enabled))
        if enabled:
            if str(self.settings.get("llm.heavy_provider", "same")) == "same":
                self.settings.set("llm.heavy_provider", "opencode", save=False)
                self.settings.set("llm.heavy_model", "opencode/big-pickle", save=False)
                # Remember that we changed this, so toggling back restores the
                # user's original "same as daily" choice.
                self._heavy_auto = True
        elif getattr(self, "_heavy_auto", False):
            self.settings.set("llm.heavy_provider", "same", save=False)
            self._heavy_auto = False
        self.settings.save()
        self._update_route_chip()
        self.toast("Heavy brain on." if enabled else "Fast brain on.", "ok")

    def _start_server(self) -> None:
        QLocalServer.removeServer(SERVER_NAME)
        server = QLocalServer(self)
        if not server.listen(SERVER_NAME):
            self.log.warning("IPC listen failed: %s", server.errorString())
            return
        server.newConnection.connect(self._accept_clients)
        self._server = server
        self.log.info("IPC listening as %s", SERVER_NAME)

    def _accept_clients(self) -> None:
        assert self._server is not None
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            self._buffers[id(client)] = b""
            client.readyRead.connect(lambda c=client: self._read_client(c))
            client.disconnected.connect(lambda c=client: self._drop_client(c))

    def _read_client(self, client: Any) -> None:
        try:
            while client.canReadLine():
                line = bytes(client.readLine()).decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    self._respond(client, {"ok": False, "error": "invalid json"})
                    continue
                if isinstance(payload, dict):
                    self._handle_command(client, payload)
        except Exception as exc:  # noqa: BLE001
            self._respond(client, {"ok": False, "error": str(exc)})

    def _drop_client(self, client: Any) -> None:
        self._waiters.discard(client)
        self._buffers.pop(id(client), None)
        client.deleteLater()

    @staticmethod
    def _respond(client: Any, payload: dict[str, Any]) -> None:
        try:
            client.write((json.dumps(payload) + "\n").encode("utf-8"))
            client.flush()
        except Exception:
            pass

    def _handle_command(self, client: Any, payload: dict[str, Any]) -> None:
        command = str(payload.get("cmd", "")).lower()
        if command == "ping":
            self._respond(client, {"ok": True, "app": APP_NAME, "version": VERSION})
        elif command == "ask":
            text = str(payload.get("text", "")).strip()
            if not text:
                self._respond(client, {"ok": False, "error": "text required"})
                return
            self._respond(client, {"ok": True, "status": "working"})
            self._waiters.add(client)
            self.ask(text, speak=bool(payload.get("speak", False)), show=bool(payload.get("show", False)))
            QTimer.singleShot(180_000, lambda: self._expire_waiter(client))
        elif command == "speak":
            text = str(payload.get("text", "")).strip()
            self.tts.speak(text, force=True)
            self._respond(client, {"ok": True})
        elif command == "listen":
            self.listen()
            self._respond(client, {"ok": True})
        elif command == "stop":
            self.stop_speaking()
            self._respond(client, {"ok": True})
        elif command == "show":
            self.show_window()
            self._respond(client, {"ok": True})
        elif command == "hide":
            self.hide_window()
            self._respond(client, {"ok": True})
        elif command == "pane":
            self.show_pane(str(payload.get("name", "conversation")))
            self._respond(client, {"ok": True})
        elif command == "mode":
            self.set_mode(str(payload.get("name", "minimal")))
            self._respond(client, {"ok": True, "mode": self._mode})
        elif command == "theme":
            name = str(payload.get("name", "toggle"))
            if name == "toggle":
                self.toggle_theme()
            else:
                self.apply_theme(name)
            self._respond(client, {"ok": True, "theme": self._theme})
        elif command == "heavy":
            enabled = bool(payload.get("enabled", True))
            self.set_heavy(enabled)
            self._respond(client, {"ok": True, "heavy": enabled, "route": self._route_text()})
        elif command == "status":
            status = self.voice.status()
            self._respond(
                client,
                {
                    "ok": True,
                    "state": status.get("state"),
                    "wake": status.get("wake"),
                    "capture_alive": status.get("capture_alive"),
                    "capture_pid": status.get("capture_pid"),
                    "vad_error": status.get("vad_error"),
                    "mode": self._mode,
                    "theme": self._theme,
                    "route": self._route_text(),
                    "provider": self.settings.get("llm.provider"),
                    "heavy": bool(self.settings.get("llm.force_heavy", False)),
                    "timers": len(self.tasks.timers()),
                    "reminders": len(self.tasks.reminders()),
                    "notes": len(self.notes.list_notes()),
                    "tts": self.tts.status(),
                },
            )
        elif command == "notes":
            notes = self.notes.list_notes()
            self._respond(client, {"ok": True, "notes": [{"title": n["title"], "tags": n.get("tags", [])} for n in notes]})
        elif command == "timers":
            self._respond(client, {"ok": True, "items": self.tasks.list_items()})
        elif command == "quit":
            self._respond(client, {"ok": True})
            QTimer.singleShot(150, self.quit_app)
        else:
            self._respond(client, {"ok": False, "error": f"unknown command: {command}"})

    def _expire_waiter(self, client: Any) -> None:
        if client in self._waiters:
            self._waiters.discard(client)
            self._respond(client, {"ok": False, "error": "timed out"})
            try:
                client.disconnectFromServer()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI client helpers
# ---------------------------------------------------------------------------

def ipc_request(payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any] | None:
    client = QLocalSocket()
    client.connectToServer(SERVER_NAME)
    if not client.waitForConnected(450):
        return None
    client.write((json.dumps(payload) + "\n").encode("utf-8"))
    client.flush()
    if not client.waitForReadyRead(int(timeout * 1000)):
        client.disconnectFromServer()
        return {"ok": False, "error": "no response"}
    lines = []
    deadline = time.time() + timeout
    buffer = ""
    while time.time() < deadline:
        if client.canReadLine():
            buffer += bytes(client.readLine()).decode("utf-8", "replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lines.append(message)
                if payload.get("cmd") != "ask" or "reply" in message or not message.get("ok", True):
                    client.disconnectFromServer()
                    return message
        if not client.waitForReadyRead(250):
            break
    client.disconnectFromServer()
    return lines[-1] if lines else {"ok": False, "error": "no response"}


def wait_for_reply(payload: dict[str, Any], timeout: float = 180.0) -> dict[str, Any] | None:
    client = QLocalSocket()
    client.connectToServer(SERVER_NAME)
    if not client.waitForConnected(450):
        return None
    client.write((json.dumps(payload) + "\n").encode("utf-8"))
    client.flush()
    deadline = time.time() + timeout
    buffer = ""
    while time.time() < deadline:
        if client.waitForReadyRead(1000):
            buffer += bytes(client.readAll()).decode("utf-8", "replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "reply" in message or not message.get("ok", True):
                    client.disconnectFromServer()
                    return message
        if client.state() != QLocalSocket.ConnectedState:
            break
    client.disconnectFromServer()
    return {"ok": False, "error": "timed out waiting for a reply"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis desktop assistant")
    parser.add_argument("--no-voice", action="store_true", help="start without microphone capture")
    parser.add_argument("--hidden", action="store_true", help="start hidden in the tray")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--ask", metavar="TEXT", help="send one request and print the reply")
    parser.add_argument("--pane", metavar="NAME", help="open a pane")
    parser.add_argument("--mode", choices=["minimal", "power"], help="layout")
    parser.add_argument("--theme", choices=["light", "dark"], help="theme")
    parser.add_argument("--heavy", choices=["on", "off"], help="force the heavy brain")
    parser.add_argument("--listen", action="store_true", help="start listening in the running instance")
    parser.add_argument("--stop", action="store_true", help="stop speech in the running instance")
    parser.add_argument("--status", action="store_true", help="print the running status")
    parser.add_argument("--quit", action="store_true", help="stop a running instance")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Jarvis")
    app.setDesktopFileName("jarvis")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(QFont("DejaVu Sans", 10))

    requested: dict[str, Any] | None = None
    if args.ask:
        requested = {"cmd": "ask", "text": args.ask, "speak": False}
    elif args.status:
        requested = {"cmd": "status"}
    elif args.quit:
        requested = {"cmd": "quit"}
    elif args.listen:
        requested = {"cmd": "listen"}
    elif args.stop:
        requested = {"cmd": "stop"}
    elif args.pane:
        requested = {"cmd": "pane", "name": args.pane}
    elif args.mode:
        requested = {"cmd": "mode", "name": args.mode}
    elif args.theme:
        requested = {"cmd": "theme", "name": args.theme}
    elif args.heavy:
        requested = {"cmd": "heavy", "enabled": args.heavy == "on"}

    if requested is not None:
        reply = (
            wait_for_reply(requested, timeout=200.0)
            if requested["cmd"] == "ask"
            else ipc_request(requested, timeout=15.0)
        )
        if reply is not None:
            if requested["cmd"] == "status" and reply.get("ok"):
                for key, value in reply.items():
                    if key == "ok":
                        continue
                    if isinstance(value, (dict, list)):
                        print(f"{key}: {json.dumps(value)}")
                    else:
                        print(f"{key}: {value}")
            elif requested["cmd"] == "ask":
                if reply.get("reply"):
                    print(reply["reply"])
                    return 0
                print(f"error: {reply.get('error', 'no reply')}", file=sys.stderr)
                return 1
            elif requested["cmd"] == "notes" and reply.get("notes"):
                for note in reply["notes"]:
                    print(note["title"])
            elif not reply.get("ok", True):
                print(f"error: {reply.get('error')}", file=sys.stderr)
                return 1
            return 0
        if requested["cmd"] in ("status", "quit", "listen", "stop", "pane", "mode", "theme", "heavy"):
            print("Jarvis is not running.", file=sys.stderr)
            return 1 if requested["cmd"] == "status" else 0

    elif (already_running := ipc_request({"cmd": "show"}, timeout=2.0)) and already_running.get("ok"):
        return 0

    # Hold a per-user lock for the entire app lifetime. IPC alone has a race:
    # two launchers can both miss the socket before either has started it.
    instance_lock = QLockFile(str(STATE_DIR / f"jarvis-instance-{USER_KEY}.lock"))
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(0):
        for _ in range(20):
            existing = ipc_request({"cmd": "show"}, timeout=0.5)
            if existing and existing.get("ok"):
                return 0
            time.sleep(0.1)
        print("Jarvis is already starting. Wait a moment before opening it again.", file=sys.stderr)
        return 1

    dashboard = JarvisDashboard(
        debug=args.debug,
        no_voice=args.no_voice,
        hidden=args.hidden or bool(requested is not None and not args.ask),
    )

    if args.pane:
        QTimer.singleShot(200, lambda: dashboard.show_pane(args.pane))
    if args.mode:
        QTimer.singleShot(150, lambda: dashboard.set_mode(args.mode))
    if args.theme:
        QTimer.singleShot(150, lambda: dashboard.apply_theme(args.theme))
    if args.heavy:
        QTimer.singleShot(150, lambda: dashboard.set_heavy(args.heavy == "on"))  # noqa: SLF001
    if args.ask:
        def finish(text: str) -> None:
            print(text, flush=True)
            threading.Thread(target=_quit_after_speech, args=(dashboard, app), daemon=True).start()

        QTimer.singleShot(250, lambda: dashboard.ask(args.ask, speak=False, callback=finish, show=False))

    exit_code = app.exec()
    instance_lock.unlock()
    return exit_code


def _quit_after_speech(dashboard: JarvisDashboard, app: QApplication) -> None:
    try:
        dashboard.tts.wait_until_done(45.0)
    except Exception:
        pass
    QTimer.singleShot(0, app.quit)


if __name__ == "__main__":
    raise SystemExit(main())
