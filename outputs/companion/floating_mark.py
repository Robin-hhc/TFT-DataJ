from PySide6.QtCore import Qt,QEvent,QRectF,QPointF,QTimer
from PySide6.QtGui import QPainter,QColor,QPen,QFont
from PySide6.QtWidgets import QWidget,QVBoxLayout,QPushButton

class LauncherButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setFixedSize(160,42)
        self.expanded=False
        self.feedback=''
        self.feedback_timer=QTimer(self);self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(lambda:self.set_panel_open(self.expanded))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.set_panel_open(False)

    def set_panel_open(self,opened):
        self.feedback='';self.feedback_timer.stop()
        self.expanded=opened
        self.setText('阵容助手 · '+('收起' if opened else '展开'))
        self.setAccessibleName(self.text())
        self.update()

    def show_feedback(self,message):
        self.feedback=message
        self.setAccessibleName('阵容助手：'+message+' · '+('收起' if self.expanded else '展开'))
        self.update()
        self.feedback_timer.start(3500)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hover=self.underMouse()
        painter.setBrush(QColor('#302b24' if self.isDown() else '#292731' if hover else '#191922'))
        painter.setPen(QPen(QColor('#d8b568' if hover else '#5b5140'),1))
        painter.drawRoundedRect(QRectF(.5,.5,self.width()-1,self.height()-1),11,11)
        painter.setPen(QPen(QColor('#e5c477'),1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(12,13,15,16),2,2)
        painter.drawLine(QPointF(17,14),QPointF(17,28))
        font=QFont('Microsoft YaHei UI');font.setPixelSize(13);font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font);painter.setPen(QColor('#f1eee8'))
        if self.feedback:font.setPixelSize(11);painter.setFont(font)
        painter.drawText(QRectF(36,0,65,42),Qt.AlignmentFlag.AlignVCenter,self.feedback or '阵容助手')
        font.setPixelSize(11);font.setWeight(QFont.Weight.Normal);painter.setFont(font)
        painter.setPen(QColor('#e5c477'))
        painter.drawText(QRectF(105,0,27,42),Qt.AlignmentFlag.AlignVCenter,'收起' if self.expanded else '展开')
        painter.setPen(QPen(QColor('#e5c477'),1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        x=143;direction=-1 if self.expanded else 1
        painter.drawLine(QPointF(x-direction*2,17),QPointF(x+direction*2,21))
        painter.drawLine(QPointF(x+direction*2,21),QPointF(x-direction*2,25))

class FloatingMark(QWidget):
    """A compact, explicit launcher; no fullscreen event-catching surface."""
    def __init__(self,toggle):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(160,42)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.button=LauncherButton();self.button.setToolTip('点击展开阵容助手 · 按住拖动位置 · Ctrl+Alt+F9')
        self.button.clicked.connect(toggle);layout.addWidget(self.button)
        self.button.installEventFilter(self);self.press=None;self.dragging=False

    def set_panel_open(self,opened):
        self.button.set_panel_open(opened)

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
