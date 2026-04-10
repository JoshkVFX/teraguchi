"""
Teraguchi visual identity — dark luxury remote desktop.

Design references:
  - Parsec.app: deep blacks, gaming-meets-pro, overlay HUD, moderate rounding
  - Pizzint.watch: monospace data, semi-transparent panels, 1px borders, command center density
  - "Teraguchi" brand: luxury fashion (Gucci) + computing (tera) = emerald green + gold on near-black
"""


# ── Palette ───────────────────────────────────────────────────────────

# Backgrounds — near-black with a cool undertone
BG_PRIMARY    = "#0a0a10"     # deepest — main window
BG_SECONDARY  = "#12121c"     # elevated — toolbar, sidebar, status bar
BG_TERTIARY   = "#1a1a28"     # cards, panels, docks
BG_SURFACE    = "#222234"     # raised elements — buttons, inputs
BG_HOVER      = "#2a2a40"     # interactive hover
BG_PRESSED    = "#1e1e30"     # pressed / active

# Brand accent — emerald green ("Gucci green")
ACCENT         = "#00c878"
ACCENT_HOVER   = "#00e890"
ACCENT_PRESSED = "#00a862"
ACCENT_MUTED   = "rgba(0, 200, 120, 0.12)"
ACCENT_SUBTLE  = "rgba(0, 200, 120, 0.08)"

# Gold — secondary accent for premium feel
GOLD           = "#d4a855"
GOLD_MUTED     = "rgba(212, 168, 85, 0.15)"

# Semantic
DANGER         = "#e5484d"
DANGER_HOVER   = "#f26067"
WARNING        = "#f5a623"
SUCCESS        = "#46a758"
INFO           = "#3b9eff"

# Text — high contrast on dark
TEXT_PRIMARY   = "#ececf1"
TEXT_SECONDARY = "#8b8ba3"
TEXT_MUTED     = "#4e4e6a"

# Borders — barely visible structure
BORDER         = "#262640"
BORDER_SUBTLE  = "rgba(255, 255, 255, 0.06)"
BORDER_FOCUS   = ACCENT

# Scrollbar
SCROLLBAR       = "#2c2c44"
SCROLLBAR_HOVER = "#3c3c58"

# Tabs
TAB_ACTIVE   = BG_SECONDARY
TAB_INACTIVE = BG_PRIMARY

# Separator
SEPARATOR = BORDER

# ── Fonts ─────────────────────────────────────────────────────────────

FONT_UI   = '-apple-system, "SF Pro Display", "Inter", "Segoe UI", "Roboto", sans-serif'
FONT_MONO = '"SF Mono", "Fira Code", "JetBrains Mono", "Menlo", "Consolas", monospace'


def generate_stylesheet() -> str:
    return f"""

/* ═══════════════════════════════════════════════════════
   Teraguchi — Dark Luxury Remote Desktop Theme
   ═══════════════════════════════════════════════════════ */

/* ── Global ────────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    font-family: {FONT_UI};
    font-size: 13px;
}}
QWidget {{
    color: {TEXT_PRIMARY};
    font-family: {FONT_UI};
}}

/* ── Buttons ───────────────────────────────────── */
QPushButton {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 18px;
    font-weight: 500;
    font-size: 13px;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {TEXT_MUTED};
}}
QPushButton:pressed {{
    background-color: {BG_PRESSED};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_PRIMARY};
    border-color: {BORDER};
}}

/* Primary (accent) buttons */
QPushButton[primary="true"], QPushButton#connectBtn {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: #0a0a10;
    font-weight: 600;
}}
QPushButton[primary="true"]:hover, QPushButton#connectBtn:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton[primary="true"]:pressed, QPushButton#connectBtn:pressed {{
    background-color: {ACCENT_PRESSED};
}}

/* Danger buttons */
QPushButton[danger="true"] {{
    background-color: {DANGER};
    border-color: {DANGER};
    color: white;
    font-weight: 600;
}}
QPushButton[danger="true"]:hover {{
    background-color: {DANGER_HOVER};
    border-color: {DANGER_HOVER};
}}

/* Gold / secondary buttons */
QPushButton[gold="true"] {{
    background-color: transparent;
    border: 1px solid {GOLD};
    color: {GOLD};
    font-weight: 600;
}}
QPushButton[gold="true"]:hover {{
    background-color: {GOLD_MUTED};
}}

/* ── Inputs ────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
    selection-background-color: {ACCENT_MUTED};
    selection-color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT_MUTED};
    outline: none;
    padding: 4px;
}}

/* ── Checkboxes ────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {BORDER};
    background-color: {BG_PRIMARY};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {TEXT_SECONDARY};
}}

/* ── Tab Bar ───────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background-color: {BG_PRIMARY};
}}
QTabBar {{
    background-color: {BG_PRIMARY};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 22px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.3px;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {BORDER};
}}
QTabBar::close-button {{
    image: none;
    subcontrol-position: right;
    padding: 2px;
}}
QTabBar QToolButton {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 4px 8px;
}}

/* ── Toolbar ───────────────────────────────────── */
QToolBar {{
    background-color: {BG_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    spacing: 3px;
    padding: 5px 10px;
}}
QToolBar QToolButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
}}
QToolBar QToolButton:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
    border-color: {BORDER};
}}
QToolBar QToolButton:pressed {{
    background-color: {BG_PRESSED};
}}
QToolBar QToolButton:checked {{
    color: {ACCENT};
    border-color: {ACCENT_MUTED};
    background-color: {ACCENT_SUBTLE};
}}
QToolBar::separator {{
    width: 1px;
    background-color: {BORDER};
    margin: 4px 8px;
}}
QToolBar QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    padding: 0 4px;
}}

/* ── Dock Widgets ──────────────────────────────── */
QDockWidget {{
    color: {TEXT_PRIMARY};
    titlebar-close-icon: none;
}}
QDockWidget::title {{
    background-color: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
    padding: 10px 14px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: {TEXT_SECONDARY};
}}
QDockWidget QWidget {{
    background-color: {BG_PRIMARY};
}}

/* ── Group Box ─────────────────────────────────── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    font-weight: 600;
    color: {TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 10px;
    color: {TEXT_MUTED};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ── Sliders ───────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {BG_PRIMARY};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_MUTED};
    border-radius: 2px;
}}

/* ── Scrollbars ────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {SCROLLBAR};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {SCROLLBAR_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {SCROLLBAR};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ── List Widget ───────────────────────────────── */
QListWidget {{
    background-color: {BG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    padding: 10px 12px;
    border-radius: 6px;
    margin: 1px 0;
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_MUTED};
    color: {TEXT_PRIMARY};
}}
QListWidget::item:hover:!selected {{
    background-color: {BG_HOVER};
}}

/* ── Menu Bar & Menus ──────────────────────────── */
QMenuBar {{
    background-color: {BG_SECONDARY};
    color: {TEXT_SECONDARY};
    border-bottom: 1px solid {BORDER};
    font-size: 13px;
    padding: 2px 0;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
    margin: 2px;
}}
QMenuBar::item:selected {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QMenu {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 28px 8px 16px;
    border-radius: 5px;
    font-size: 13px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_MUTED};
    color: {TEXT_PRIMARY};
}}
QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 10px;
}}
QMenu::indicator:checked {{
    width: 16px;
    height: 16px;
    margin-left: 6px;
}}

/* ── Status Bar ────────────────────────────────── */
QStatusBar {{
    background-color: {BG_SECONDARY};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 12px;
    min-height: 28px;
}}
QStatusBar QLabel {{
    color: {TEXT_SECONDARY};
    padding: 2px 8px;
    font-size: 12px;
}}

/* ── Tooltip ───────────────────────────────────── */
QToolTip {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
}}

/* ── Form Labels ───────────────────────────────── */
QLabel {{
    color: {TEXT_PRIMARY};
}}

/* ── Message Box ───────────────────────────────── */
QMessageBox {{
    background-color: {BG_SECONDARY};
}}
QMessageBox QPushButton {{
    min-width: 80px;
}}

/* ── Splitter ──────────────────────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
}}

/* ── Frame ─────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {BORDER};
}}

/* ── Standalone Tool Buttons (outside toolbar) ─── */
QToolButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}}
QToolButton:hover {{
    background-color: {BG_HOVER};
    border-color: {BORDER};
}}
QToolButton:pressed {{
    background-color: {BG_PRESSED};
}}
"""
