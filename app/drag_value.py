"""Axis label that scrubs horizontally without taking over text-field editing."""
from PySide6.QtCore import Qt,Signal,QTimer,QEvent
from PySide6.QtWidgets import QLabel,QApplication


class DragValue(QLabel):
    started=Signal()
    moved=Signal(float)
    finished=Signal(bool)

    def __init__(self,text,parent=None):
        super().__init__(text+' ↔',parent);self.active=False;self.total=0.;self.pending=0.;self.travel=0.
        self.setCursor(Qt.SizeHorCursor);self.setFocusPolicy(Qt.StrongFocus);self.setMinimumWidth(38)
        self.setObjectName('cameraDrag');self.setAlignment(Qt.AlignCenter)
        self.setToolTip('Drag left/right to adjust this camera axis live. Shift: 10× finer. Esc: cancel. One drag = one Undo.')
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(16);self.timer.timeout.connect(self.flush)

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return super().mousePressEvent(event)
        self.setFocus();self.active=True;self.total=0.;self.pending=0.;self.travel=0.;self.last=event.globalPosition().x()
        self.grabMouse();self.started.emit();event.accept()

    def mouseMoveEvent(self,event):
        if not self.active:return super().mouseMoveEvent(event)
        self.track_position(event)
        if self.travel>=QApplication.startDragDistance() and not self.timer.isActive():self.timer.start()
        event.accept()

    def track_position(self,event):
        dx=event.globalPosition().x()-self.last;self.last=event.globalPosition().x();self.travel+=abs(dx)
        self.pending+=dx*(.1 if event.modifiers()&Qt.ShiftModifier else 1.)

    def flush(self):
        self.timer.stop()
        if self.active and self.travel>=QApplication.startDragDistance():
            self.total+=self.pending;self.pending=0.;self.moved.emit(self.total)

    def finish(self,cancel=False):
        if not self.active:return
        if not cancel:self.flush()
        self.active=False;self.timer.stop();self.releaseMouse();self.finished.emit(cancel)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.active:self.track_position(event);self.finish();event.accept()
        else:super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if self.active and event.key()==Qt.Key_Escape:self.finish(True);event.accept()
        else:super().keyPressEvent(event)

    def hideEvent(self,event):self.finish(True);super().hideEvent(event)

    def event(self,event):
        if event.type()==QEvent.UngrabMouse and getattr(self,'active',False):self.finish(True)
        return super().event(event)
