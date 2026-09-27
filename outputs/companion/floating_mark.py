from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QPushButton

class FloatingMark(QWidget):
    """An actual 44x44 window, with no fullscreen event-catching surface."""
    def __init__(self,toggle):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(44,44)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.button=QPushButton('铲');self.button.setToolTip('展开 / 收起助手 · Ctrl+Alt+F9')
        self.button.setStyleSheet('background:#191922;color:#ffdf80;border:1px solid #8d794b;border-radius:9px;font-size:19px')
        self.button.clicked.connect(toggle);layout.addWidget(self.button)
