"""Compact, clickable camera graph and per-frame correction controls."""
import json
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QEvent
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDoubleSpinBox, QFileDialog, QMessageBox, QSizePolicy)
from camera_track import CameraTrack, camera_matrix
from scene_geometry import transform_matrix
from manipulation import euler_xyz


class CameraGraph(QWidget):
    selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.track = None
        self.frame = 1
        self.channel = 1
        self.local = False
        self.setMinimumHeight(125)
        self.setToolTip('Click or drag to select a solved frame. Dashed = original; solid = current. Amber marks = edited frames. Gaps are unsolved frames.')

    def bounds(self):
        first, last = int(self.track.frames[0]), int(self.track.frames[-1])
        if self.local:
            first, last = max(first, self.frame-50), min(last, self.frame+50)
        return first, max(first+1, last)

    def plot_rect(self):
        return QRectF(70, 20, max(1, self.width()-88), max(1, self.height()-44))

    def select_at(self, pos):
        if self.track is None:
            return
        a, b = self.bounds()
        rect = self.plot_rect()
        value = a + np.clip((pos.x()-rect.left())/rect.width(), 0, 1)*(b-a)
        self.selected.emit(int(self.track.frames[np.argmin(abs(self.track.frames-value))]))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.select_at(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.select_at(event.position())

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#101720'))
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor('#b6c4d7'))
        if self.track is None:
            p.drawText(self.rect(), Qt.AlignCenter, 'Load a reconstruction to inspect camera keyframes')
            p.end()
            return
        rect = self.plot_rect()
        a, b = self.bounds()
        mask = (self.track.frames >= a) & (self.track.frames <= b)
        frames = self.track.frames[mask]
        current = self.track.values(self.channel)[mask]
        original = self.track.values(self.channel, original=True)[mask]
        lo = float(min(current.min(), original.min()))
        hi = float(max(current.max(), original.max()))
        margin = max((hi-lo)*.08, 1e-5)
        lo -= margin
        hi += margin
        if self.channel != 0:
            lo = max(0., lo)

        def point(frame, value):
            return QPointF(rect.left()+(frame-a)/(b-a)*rect.width(), rect.bottom()-(value-lo)/(hi-lo)*rect.height())

        for t in (0., .5, 1.):
            value = lo + (hi-lo)*t
            y = point(a, value).y()
            p.setPen(QColor('#293746'))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor('#b6c4d7'))
            p.drawText(QRectF(0, y-9, 65, 18), Qt.AlignRight | Qt.AlignVCenter, f'{value:.3g}')
        p.drawText(QPointF(rect.left(), self.height()-5), str(a))
        p.drawText(QRectF(rect.right()-70, self.height()-22, 70, 20), Qt.AlignRight, str(b))
        labels = ('XYZ position · reconstruction units', 'Translation · units / frame', 'Rotation · degrees / frame')
        p.drawText(QPointF(rect.left(), 14), labels[self.channel]+'    dashed: original')
        p.save()
        p.setClipRect(rect.adjusted(-2, -2, 2, 2))
        colors = ['#f07379', '#78dba1', '#6baeff'] if self.channel == 0 else ['#79cfff']
        for data, dashed in ((original, True), (current, False)):
            for axis, color in enumerate(colors):
                pen = QPen(QColor(color), 1 if dashed else 1.7)
                if dashed:
                    pen.setStyle(Qt.DashLine)
                    c = pen.color(); c.setAlpha(100); pen.setColor(c)
                p.setPen(pen)
                path = QPainterPath()
                for i, frame in enumerate(frames):
                    pt = point(frame, data[i, axis])
                    if i == 0 or frame-frames[i-1] > 1:
                        path.moveTo(pt)
                    else:
                        path.lineTo(pt)
                    p.drawPoint(pt)
                p.drawPath(path)
        p.setPen(QPen(QColor('#ffcb70'), 2))
        for frame in self.track.edits():
            x = point(int(frame), lo).x()
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.top()+7))
        p.setPen(QPen(QColor('#ffffff'), 1))
        x = point(self.frame, lo).x()
        p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        p.restore()
        p.end()


class CameraEditor(QWidget):
    changed = Signal()
    selected = Signal(int)
    edit_started = Signal()

    def __init__(self):
        super().__init__()
        self.track = None
        self.frame = 1
        self.file_path = None
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(3)
        row = QHBoxLayout()
        row.addWidget(QLabel('CAMERA KEYFRAMES'))
        self.channel = QComboBox(); self.channel.addItems(['Position XYZ', 'Translation jump', 'Rotation jump']); self.channel.setCurrentIndex(1)
        row.addWidget(self.channel)
        self.range = QComboBox(); self.range.addItems(['All frames', 'Around frame ±50']); row.addWidget(self.range)
        self.info = QLabel('No camera'); row.addWidget(self.info, 1)
        layout.addLayout(row)
        self.graph = CameraGraph(); layout.addWidget(self.graph)
        self.graph.selected.connect(self.selected)
        self.channel.currentIndexChanged.connect(self.graph_options)
        self.range.currentIndexChanged.connect(self.graph_options)
        self.controls = QWidget(); controls = QVBoxLayout(self.controls); controls.setContentsMargins(0, 0, 0, 0); controls.setSpacing(3)
        fields = QHBoxLayout(); self.fields = []
        for name in ('X', 'Y', 'Z', 'RX°', 'RY°', 'RZ°'):
            fields.addWidget(QLabel(name))
            spin = QDoubleSpinBox(); spin.setRange(-1e9, 1e9); spin.setDecimals(5); spin.setSingleStep(.1); spin.setKeyboardTracking(False)
            spin.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); spin.setMinimumWidth(64)
            spin.setToolTip('Absolute camera pose in Z-up reconstruction coordinates, before the whole-scene transform. Press Apply pose to commit.')
            fields.addWidget(spin, 1); self.fields.append(spin)
            spin.installEventFilter(self)
        self.apply = self.button('Apply pose', self.apply_pose, fields)
        controls.addLayout(fields)
        actions = QHBoxLayout()
        self.interpolate_button = self.button('Interpolate neighbours', self.interpolate, actions)
        self.interpolate_button.setToolTip('Replace this frame using the previous and next solved cameras, weighted by frame distance. Rotation uses the shortest quaternion arc.')
        self.reset_button = self.button('Reset frame', self.reset, actions)
        self.undo_button = self.button('Undo', self.undo, actions)
        actions.addStretch()
        self.button('Save corrections…', self.save, actions)
        self.button('Load corrections…', self.load, actions)
        controls.addLayout(actions); layout.addWidget(self.controls)
        self.controls.setEnabled(False)

    def eventFilter(self, obj, event):
        if obj in self.fields and event.type() == QEvent.FocusIn:
            self.edit_started.emit()
        return super().eventFilter(obj, event)

    def button(self, text, callback, row):
        b = QPushButton(text); b.clicked.connect(callback); row.addWidget(b); return b

    def set_track(self, poses):
        self.track = CameraTrack(poses)
        self.graph.track = self.track
        self.file_path = None
        self.set_frame(poses[0]['frame'])

    def graph_options(self):
        self.graph.channel = self.channel.currentIndex()
        self.graph.local = self.range.currentIndex() == 1
        self.graph.update()

    def set_frame(self, frame):
        self.frame = frame
        self.graph.frame = frame
        valid = self.track is not None and frame in self.track.by_frame
        self.controls.setEnabled(self.track is not None)
        for widget in [*self.fields, self.apply, self.reset_button]:
            widget.setEnabled(valid)
        interior = valid and frame != self.track.frames[0] and frame != self.track.frames[-1]
        self.interpolate_button.setEnabled(interior)
        self.undo_button.setEnabled(self.track is not None and bool(self.track.history))
        if valid:
            matrix = camera_matrix(self.track.by_frame[frame])
            for field, value in zip(self.fields, [*matrix[:3, 3], *euler_xyz(matrix[:3, :3])]):
                field.setValue(float(value))
        count = len(self.track.edits()) if self.track else 0
        dirty = ' · unsaved' if self.track and self.track.dirty else ''
        self.info.setText(f'Frame {frame} · {count} corrected{dirty}' + ('' if valid else ' · unsolved'))
        self.graph.update()

    def notify(self):
        self.set_frame(self.frame)
        self.changed.emit()

    def apply_pose(self):
        values = [field.value() for field in self.fields]
        self.track.set_matrix(self.frame, transform_matrix(dict(position=values[:3], rotation=values[3:], scale=1)))
        self.notify()

    def interpolate(self):
        self.track.interpolate(self.frame)
        self.notify()

    def reset(self):
        self.track.reset(self.frame)
        self.notify()

    def undo(self):
        self.track.undo()
        self.notify()

    def save(self):
        if self.track is None:
            return False
        path, _ = QFileDialog.getSaveFileName(self, 'Save camera corrections', str(self.file_path or 'camera_corrections.json'), 'JSON (*.json)')
        if not path:
            return False
        try:
            if not path.lower().endswith('.json'): path += '.json'
            target = Path(path)
            temporary = target.with_suffix(target.suffix+'.tmp')
            temporary.write_text(json.dumps(self.track.document(), indent=2), encoding='utf-8')
            temporary.replace(target)
            self.file_path = target
            self.track.saved = self.track.edits()
            self.set_frame(self.frame)
            return True
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot save corrections', str(exc))
            return False

    def confirm_discard(self):
        if self.track is None or not self.track.dirty:
            return True
        result = QMessageBox.question(self, 'Unsaved camera corrections', 'Save camera corrections before continuing?', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        return self.save() if result == QMessageBox.Save else result == QMessageBox.Discard

    def load(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load camera corrections', '', 'JSON (*.json)')
        if not path or not self.confirm_discard():
            return
        try:
            self.track.load_document(json.loads(Path(path).read_text(encoding='utf-8')))
            self.file_path = Path(path)
            self.notify()
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot load corrections', str(exc))
