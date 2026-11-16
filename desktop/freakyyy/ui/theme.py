"""Freakyyy design tokens - shared look with Freakyyy Mobile (deep navy, near-black,
electric blue, cyan, white; translucent glass with thin light edges)."""
from PySide6.QtGui import QColor, QFont

BLACK = QColor("#02040A")
NAVY = QColor("#07152C")
DEEP = QColor("#040B19")
BLUE = QColor("#238CFF")
ELECTRIC = QColor("#3D7BFF")
CYAN = QColor("#6DDCFF")
ICE = QColor("#BDEBFF")
WHITE = QColor("#F8FAFF")
MUTED = QColor("#8DA3C2")
SUCCESS = QColor("#65DDAA")
WARNING = QColor("#FFC46B")
DANGER = QColor("#FF7A8A")

OUTCOME_COLORS = {
    "COMPLETED": SUCCESS, "OPENED": CYAN, "INFO": ICE, "NEEDS_PERMISSION": WARNING,
    "NEEDS_CONFIRMATION": WARNING, "CLARIFY": WARNING, "NOT_SUPPORTED": DANGER, "FAILED": DANGER,
    "DEVICE_OFFLINE": WARNING, "UNKNOWN": WARNING,
}
OUTCOME_LABELS = {
    "COMPLETED": "DONE", "OPENED": "OPENED · YOUR TURN", "INFO": "FREAKYYY", "NEEDS_PERMISSION": "NEEDS PERMISSION",
    "NEEDS_CONFIRMATION": "CONFIRM", "CLARIFY": "WHICH ONE?", "NOT_SUPPORTED": "NOT ALLOWED", "FAILED": "COULDN'T DO IT",
    "DEVICE_OFFLINE": "DEVICE OFFLINE", "UNKNOWN": "DIDN'T UNDERSTAND",
}

STATE_COLORS = {
    "IDLE": BLUE, "WAKE_DETECTED": CYAN, "LISTENING": CYAN, "RECOGNIZING": ICE, "THINKING": ELECTRIC,
    "EXECUTING": QColor("#4FA8FF"), "WAITING_FOR_CONFIRMATION": WARNING, "SPEAKING": QColor("#8FB8FF"),
    "ERROR": DANGER, "OFFLINE": MUTED,
}
STATE_LABELS = {
    "IDLE": "STANDING BY", "WAKE_DETECTED": "WAKE WORD DETECTED", "LISTENING": "LISTENING",
    "RECOGNIZING": "RECOGNIZING", "THINKING": "THINKING", "EXECUTING": "EXECUTING",
    "WAITING_FOR_CONFIRMATION": "WAITING FOR CONFIRMATION", "SPEAKING": "SPEAKING", "ERROR": "ERROR",
    "OFFLINE": "MICROPHONE OFF",
}


def font(size: float, weight: QFont.Weight = QFont.Weight.Normal, spacing: float = 0, mono: bool = False) -> QFont:
    f = QFont("Cascadia Mono" if mono else "Segoe UI Variable Display")
    if not mono:
        f.setFamilies(["Segoe UI Variable Display", "Segoe UI", "Arial"])
    else:
        f.setFamilies(["Cascadia Mono", "Consolas"])
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


STYLESHEET = f"""
* {{ color: {WHITE.name()}; font-family: 'Segoe UI Variable Text','Segoe UI'; font-size: 10pt; }}
QWidget#root {{ background: transparent; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {NAVY.name()}; color: {WHITE.name()}; border: 1px solid {rgba(CYAN, .35)}; padding: 6px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {rgba(WHITE, .06)}; border: 1px solid {rgba(ICE, .16)}; border-radius: 12px;
    padding: 8px 12px; selection-background-color: {BLUE.name()};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {rgba(CYAN, .6)}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {NAVY.name()}; border: 1px solid {rgba(CYAN, .3)}; selection-background-color: {BLUE.name()}; }}
QPushButton {{
    background: {rgba(WHITE, .07)}; border: 1px solid {rgba(ICE, .18)}; border-radius: 14px; padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {rgba(BLUE, .25)}; border-color: {rgba(CYAN, .5)}; }}
QPushButton:pressed {{ background: {rgba(BLUE, .4)}; }}
QPushButton#primary {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {BLUE.name()}, stop:1 {CYAN.name()}); border: none; color: #021022; }}
QPushButton#danger {{ border-color: {rgba(DANGER, .5)}; color: {DANGER.name()}; }}
QPushButton#chrome {{ background: transparent; border: none; border-radius: 10px; padding: 4px 10px; font-size: 12pt; color: {ICE.name()}; }}
QPushButton#chrome:hover {{ background: {rgba(WHITE, .1)}; }}
QPushButton#close:hover {{ background: {rgba(DANGER, .6)}; }}
QCheckBox {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 38px; height: 20px; border-radius: 10px; background: {rgba(WHITE, .12)}; border: 1px solid {rgba(ICE, .2)}; }}
QCheckBox::indicator:checked {{ background: {BLUE.name()}; border-color: {CYAN.name()}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(ICE, .2)}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border-radius: 10px; padding: 6px; }}
QListWidget::item:selected {{ background: {rgba(BLUE, .25)}; }}
QTabBar::tab {{ background: transparent; color: {MUTED.name()}; padding: 10px 14px; border: none; font-weight: 600; }}
QTabBar::tab:selected {{ color: {WHITE.name()}; border-bottom: 2px solid {CYAN.name()}; }}
QTabWidget::pane {{ border: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {rgba(WHITE, .12)}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {CYAN.name()}; width: 16px; margin: -6px 0; border-radius: 8px; }}
QMenu {{ background: {NAVY.name()}; border: 1px solid {rgba(CYAN, .25)}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {rgba(BLUE, .35)}; }}
QMenu::separator {{ height: 1px; background: {rgba(ICE, .12)}; margin: 4px 8px; }}
"""
