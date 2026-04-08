"""
Dark theme engine for Teragucci.

Generates a complete QSS stylesheet for a modern, sleek dark UI.
Think Parsec / Moonlight / Steam Remote Play.
"""


# Color palette
BG_PRIMARY = "#111119"
BG_SECONDARY = "#1a1a26"
BG_TERTIARY = "#222233"
BG_HOVER = "#2a2a3d"
BG_PRESSED = "#333350"
BG_INPUT = "#0d0d15"
ACCENT = "#4a7dff"
ACCENT_HOVER = "#5c8eff"
ACCENT_PRESSED = "#3a6de0"
ACCENT_SUBTLE = "#2a3d66"
DANGER = "#e94560"
DANGER_HOVER = "#ff5577"
SUCCESS = "#00cc88"
WARNING = "#ffaa00"
TEXT_PRIMARY = "#e0e0ee"
TEXT_SECONDARY = "#8888aa"
TEXT_MUTED = "#555577"
BORDER = "#2a2a3d"
BORDER_FOCUS = ACCENT
SCROLLBAR = "#333350"
SCROLLBAR_HOVER = "#444466"
TAB_ACTIVE = BG_SECONDARY
TAB_INACTIVE = BG_PRIMARY
SEPARATOR = "#2a2a3d"


def generate_stylesheet() -> str:
    return f"""
/* ── Global ────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    font-family: -apple-system, "Segoe UI", "Roboto", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

/* ── Buttons ───────────────────────────────────── */
QPushButton {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
    min-height: 20px;
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
}}
QPushButton[primary="true"], QPushButton#connectBtn {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton[primary="true"]:hover, QPushButton#connectBtn:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[danger="true"] {{
    background-color: {DANGER};
    border-color: {DANGER};
    color: white;
}}
QPushButton[danger="true"]:hover {{
    background-color: {DANGER_HOVER};
}}

/* ── Inputs ────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
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
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SUBTLE};
    outline: none;
}}

/* ── Checkboxes ────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    color: {TEXT_PRIMARY};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background-color: {BG_INPUT};
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
    background-color: {TAB_INACTIVE};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 20px;
    margin-right: 1px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background-color: {TAB_ACTIVE};
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
}}
QTabBar::close-button {{
    image: none;
    subcontrol-position: right;
    padding: 2px;
}}
QTabBar QToolButton {{
    background: {BG_TERTIARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT_PRIMARY};
    padding: 4px;
}}

/* ── Toolbar ───────────────────────────────────── */
QToolBar {{
    background-color: {BG_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    spacing: 4px;
    padding: 4px 8px;
}}
QToolBar QToolButton {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    background-color: {BG_HOVER};
    border-color: {BORDER};
}}
QToolBar QToolButton:pressed {{
    background-color: {BG_PRESSED};
}}
QToolBar::separator {{
    width: 1px;
    background-color: {BORDER};
    margin: 4px 6px;
}}

/* ── Dock Widgets ──────────────────────────────── */
QDockWidget {{
    color: {TEXT_PRIMARY};
    titlebar-close-icon: none;
}}
QDockWidget::title {{
    background-color: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
    padding: 8px 12px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QDockWidget QWidget {{
    background-color: {BG_PRIMARY};
}}

/* ── Group Box ─────────────────────────────────── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    color: {TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {TEXT_SECONDARY};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ── Sliders ───────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {BG_INPUT};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_SUBTLE};
    border-radius: 3px;
}}

/* ── Scrollbars ────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {SCROLLBAR};
    border-radius: 4px;
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
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {SCROLLBAR};
    border-radius: 4px;
    min-width: 30px;
}}

/* ── List Widget ───────────────────────────────── */
QListWidget {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_SUBTLE};
}}
QListWidget::item:hover:!selected {{
    background-color: {BG_HOVER};
}}

/* ── Menu ──────────────────────────────────────── */
QMenuBar {{
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item:selected {{
    background-color: {BG_HOVER};
}}
QMenu {{
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_SUBTLE};
}}
QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 8px;
}}

/* ── Status Bar ────────────────────────────────── */
QStatusBar {{
    background-color: {BG_SECONDARY};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 12px;
}}
QStatusBar QLabel {{
    color: {TEXT_SECONDARY};
    padding: 2px 8px;
}}

/* ── Tooltip ───────────────────────────────────── */
QToolTip {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Form Layout ───────────────────────────────── */
QFormLayout {{
    spacing: 8px;
}}
QLabel {{
    color: {TEXT_PRIMARY};
}}

/* ── Message Box ───────────────────────────────── */
QMessageBox {{
    background-color: {BG_SECONDARY};
}}

/* ── Splitter ──────────────────────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
}}
"""
