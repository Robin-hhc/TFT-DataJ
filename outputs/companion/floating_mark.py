from PySide6.QtCore import Qt,QEvent
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
        self.button.installEventFilter(self);self.press=None;self.dragging=False

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            self.press=event.globalPosition().toPoint();self.origin=self.pos();self.dragging=False
        elif event.type()==QEvent.Type.MouseMove and self.press is not None:
            delta=event.globalPosition().toPoint()-self.press
            if delta.manhattanLength()>6:self.dragging=True
            if self.dragging:self.move(self.origin+delta);return True
        elif event.type()==QEvent.Type.MouseButtonRelease and self.press is not None:
            self.press=None
            if self.dragging:self.button.setDown(False);return True
        return super().eventFilter(obj,event)
