"""Compact, clickable camera graph and per-frame correction controls."""
import json
import copy
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QEvent
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDoubleSpinBox, QFileDialog, QMessageBox, QSizePolicy,QCheckBox,QSpinBox)
from camera_track import CameraTrack, camera_matrix
from scene_geometry import transform_matrix
from manipulation import euler_xyz
from drag_value import DragValue


class CameraGraph(QWidget):
    selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.track = None
        self.frame = 1
        self.channel = 3
        self.axis=-1
        self.local = False
        self.plot_cache=None;self.plot_key=None
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
        key=(id(self.track),self.track.revision if self.track else 0,self.channel,self.axis,self.bounds() if self.track else None,self.width(),self.height(),self.devicePixelRatioF())
        if key==self.plot_key:
            self.paint_cached();return
        ratio=self.devicePixelRatioF()
        self.plot_cache=QPixmap(round(self.width()*ratio),round(self.height()*ratio));self.plot_cache.setDevicePixelRatio(ratio)
        self.plot_key=key
        p = QPainter(self.plot_cache)
        p.fillRect(self.rect(), QColor('#1f1f1f'))
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor('#d7d7d7'))
        if self.track is None:
            p.drawText(self.rect(), Qt.AlignCenter, 'Load a reconstruction to inspect camera keyframes')
            p.end()
            self.paint_cached()
            return
        rect = self.plot_rect()
        a, b = self.bounds()
        mask = (self.track.frames >= a) & (self.track.frames <= b)
        frames = self.track.frames[mask]
        current = self.track.values(self.channel)[mask]
        original = self.track.values(self.channel, original=True)[mask]
        axes=([self.axis] if self.axis>=0 else [0,1,2]) if self.channel in (0,3) else [0]
        current=current[:,axes];original=original[:,axes]
        lo = float(min(current.min(), original.min()))
        hi = float(max(current.max(), original.max()))
        margin = max((hi-lo)*.08, 1e-5)
        lo -= margin
        hi += margin
        if self.channel not in (0,3):
            lo = max(0., lo)

        def point(frame, value):
            return QPointF(rect.left()+(frame-a)/(b-a)*rect.width(), rect.bottom()-(value-lo)/(hi-lo)*rect.height())

        for t in (0., .5, 1.):
            value = lo + (hi-lo)*t
            y = point(a, value).y()
            p.setPen(QColor('#383838'))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor('#d7d7d7'))
            p.drawText(QRectF(0, y-9, 65, 18), Qt.AlignRight | Qt.AlignVCenter, f'{value:.3g}')
        p.drawText(QPointF(rect.left(), self.height()-5), str(a))
        p.drawText(QRectF(rect.right()-70, self.height()-22, 70, 20), Qt.AlignRight, str(b))
        if lo<0<hi:
            p.setPen(QPen(QColor('#777777'),1,Qt.DashLine));y=point(a,0).y()
            p.drawLine(QPointF(rect.left(),y),QPointF(rect.right(),y))
        labels = ('XYZ position · reconstruction units', 'Translation total · units / frame', 'Rotation · degrees / frame', 'Translation ΔXYZ · signed units / frame')
        p.setPen(QColor('#d7d7d7'))
        p.drawText(QPointF(rect.left(), 14), labels[self.channel]+'    dashed: original')
        palette=['#f0304d','#81cd00','#2f75bd']
        if self.channel in (0,3):
            for offset,axis in enumerate(axes):
                p.setPen(QColor(palette[axis]));p.drawText(QPointF(rect.right()-len(axes)*32+offset*32,14),'XYZ'[axis])
        p.save()
        p.setClipRect(rect.adjusted(-2, -2, 2, 2))
        colors = [palette[axis] for axis in axes] if self.channel in (0,3) else ['#7cadf0']
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
        p.restore()
        p.end()
        self.paint_cached()

    def paint_cached(self):
        p=QPainter(self);p.drawPixmap(0,0,self.plot_cache)
        if self.track is not None:
            rect=self.plot_rect();a,b=self.bounds();x=rect.left()+(self.frame-a)/(b-a)*rect.width()
            p.setClipRect(rect);p.setPen(QPen(QColor('#ffffff'),1));p.drawLine(QPointF(x,rect.top()),QPointF(x,rect.bottom()))
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
        self.drag=None;self.drag_translation_step=.01
        self.locked_frame=None
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(3)
        row = QHBoxLayout()
        row.addWidget(QLabel('CAMERA KEYFRAMES'))
        self.channel = QComboBox()
        for label,value in [('Position XYZ',0),('Translation XYZ',3),('Rotation jump',2),('Translation total',1)]:self.channel.addItem(label,value)
        self.channel.setCurrentIndex(1)
        row.addWidget(self.channel)
        self.axis_filter=QComboBox();self.axis_filter.addItems(['XYZ','X only','Y only','Z only']);row.addWidget(self.axis_filter)
        self.axis_filter.setToolTip('Show all three axes or isolate one. Translation is signed displacement per frame in Z-up reconstruction axes.')
        self.range = QComboBox(); self.range.addItems(['All frames', 'Around frame ±50']); row.addWidget(self.range)
        self.info = QLabel('No camera'); row.addWidget(self.info, 1)
        layout.addLayout(row)
        self.graph = CameraGraph(); layout.addWidget(self.graph)
        self.graph.selected.connect(self.selected)
        self.channel.currentIndexChanged.connect(self.graph_options)
        self.axis_filter.currentIndexChanged.connect(self.graph_options)
        self.range.currentIndexChanged.connect(self.graph_options)
        self.controls = QWidget(); controls = QVBoxLayout(self.controls); controls.setContentsMargins(0, 0, 0, 0); controls.setSpacing(3)
        scope=QHBoxLayout();self.frame_lock=QCheckBox('Only this frame');scope.addWidget(self.frame_lock)
        self.frame_lock.setToolTip('Lock pose fields and axis drags to the chosen solved frame. Interpolate ±N is an explicit neighbour-range action around that frame. Off: pose edits follow the selected frame. At lower tracking FPS, several source-video frames can share one solved camera.')
        self.scope_label=QLabel();scope.addWidget(self.scope_label,1)
        self.use_frame_button=self.button('Use current frame',self.use_current_frame,scope)
        self.goto_frame_button=self.button('Go to edit frame',self.go_to_edit_frame,scope)
        self.frame_lock.toggled.connect(self.frame_scope_changed);controls.addLayout(scope)
        fields = QHBoxLayout(); self.fields = [];self.drag_labels=[]
        for axis,name in enumerate(('X', 'Y', 'Z', 'RX°', 'RY°', 'RZ°')):
            label=DragValue(name);self.drag_labels.append(label);fields.addWidget(label)
            label.started.connect(lambda a=axis:self.begin_drag(a))
            label.moved.connect(self.preview_drag);label.finished.connect(self.finish_drag)
            spin = QDoubleSpinBox(); spin.setRange(-1e9, 1e9); spin.setDecimals(5); spin.setSingleStep(.1); spin.setKeyboardTracking(False)
            spin.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); spin.setMinimumWidth(64)
            spin.setToolTip('Absolute camera pose in Z-up reconstruction coordinates, before the whole-scene transform. Press Apply pose to commit.')
            fields.addWidget(spin, 1); self.fields.append(spin)
            spin.installEventFilter(self)
        self.apply = self.button('Apply pose', self.apply_pose, fields)
        controls.addLayout(fields)
        hint=QHBoxLayout();hint.addWidget(QLabel('Drag axis labels ↔ · Shift: fine · Esc: cancel'));hint.addStretch()
        hint.addWidget(QLabel('Drag speed'));self.drag_speed=QComboBox();self.drag_speed.addItems(['0.1×','1×','10×']);self.drag_speed.setCurrentIndex(1);hint.addWidget(self.drag_speed);controls.addLayout(hint)
        actions = QHBoxLayout()
        self.interpolate_button = self.button('Interpolate ±5', self.interpolate, actions)
        self.interpolation_radius=QSpinBox();self.interpolation_radius.setRange(5,100);self.interpolation_radius.setValue(5);self.interpolation_radius.setPrefix('±');self.interpolation_radius.setSuffix(' frames');self.interpolation_radius.setKeyboardTracking(False)
        self.interpolation_radius.setToolTip('Neighbour range on each side. Keep the current centre pose and unchanged outer anchors; interpolate position and rotation between them. Missing frames are skipped; clip ends remain anchors.')
        actions.addWidget(self.interpolation_radius);self.interpolation_radius.valueChanged.connect(self.update_interpolation_controls)
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
        self.cancel_drag()
        self.reset_frame_scope()
        self.track = CameraTrack(poses)
        span=float(np.linalg.norm(np.ptp(self.track.original[:,:3,3],axis=0)))
        self.drag_translation_step=max(.0001,span/2000) if span>1e-8 else .01
        self.graph.track = self.track
        self.file_path = None
        self.set_frame(poses[0]['frame'])

    def graph_options(self):
        self.graph.channel = self.channel.currentData()
        self.graph.axis=self.axis_filter.currentIndex()-1
        self.axis_filter.setEnabled(self.graph.channel in (0,3))
        self.graph.local = self.range.currentIndex() == 1
        self.graph.update()

    def set_frame(self, frame):
        interrupted=self.drag is not None and frame!=self.frame
        if interrupted:self.finish_drag(True,notify=False)
        self.frame = frame
        self.graph.frame = frame
        valid = self.track is not None and frame in self.track.by_frame
        editable=valid and (not self.frame_lock.isChecked() or frame==self.locked_frame)
        self.controls.setEnabled(self.track is not None)
        for widget in [*self.fields,*self.drag_labels,self.drag_speed,self.apply,self.reset_button]:
            widget.setEnabled(editable)
        self.frame_lock.setEnabled(valid or self.frame_lock.isChecked())
        self.use_frame_button.setEnabled(valid and self.frame_lock.isChecked())
        self.goto_frame_button.setEnabled(self.frame_lock.isChecked() and self.locked_frame is not None)
        self.scope_label.setText((f'Edit solved frame {self.locked_frame} only' + (f' · viewing {frame} (read-only)' if frame!=self.locked_frame else ''))
                                if self.frame_lock.isChecked() else f'Edit selected solved frame {frame} only')
        self.update_interpolation_controls()
        self.undo_button.setEnabled(bool(self.shared_history.undo_stack) if hasattr(self,'shared_history') else self.track is not None and bool(self.track.history))
        if valid:
            matrix = camera_matrix(self.track.by_frame[frame])
            for field, value in zip(self.fields, [*matrix[:3, 3], *euler_xyz(matrix[:3, :3])]):
                field.setValue(float(value))
        count = len(self.track.edits()) if self.track else 0
        dirty = ' · unsaved' if self.track and self.track.dirty else ''
        self.info.setText(f'Frame {frame} · {count} corrected{dirty}' + ('' if valid else ' · unsolved'))
        self.graph.update()
        if interrupted:self.changed.emit()

    @property
    def dragging(self):return self.drag is not None

    def reset_frame_scope(self):
        self.locked_frame=None;self.frame_lock.blockSignals(True);self.frame_lock.setChecked(False);self.frame_lock.blockSignals(False)

    def frame_scope_changed(self,locked):
        self.cancel_drag()
        if locked:self.use_current_frame()
        else:self.locked_frame=None;self.set_frame(self.frame)

    def use_current_frame(self):
        if self.track is None or self.frame not in self.track.by_frame:return
        self.cancel_drag();self.locked_frame=self.frame;self.edit_started.emit()
        self.selected.emit(self.locked_frame);self.set_frame(self.frame)

    def go_to_edit_frame(self):
        if self.locked_frame is not None:self.selected.emit(self.locked_frame)

    def can_edit_frame(self):
        return self.track is not None and self.frame in self.track.by_frame and (not self.frame_lock.isChecked() or self.frame==self.locked_frame)

    def begin_drag(self,axis):
        if not self.can_edit_frame():return
        self.edit_started.emit()
        matrix=camera_matrix(self.track.by_frame[self.frame])
        self.drag=dict(axis=axis,frame=self.frame,matrix=matrix,rotation=euler_xyz(matrix[:3,:3]),
                       edits=copy.deepcopy(self.track.edits()),speed=(.1,1.,10.)[self.drag_speed.currentIndex()])
        if hasattr(self,'shared_history'):self.shared_history.begin()

    def preview_drag(self,pixels):
        if self.drag is None:return
        drag=self.drag;axis=drag['axis'];matrix=drag['matrix'].copy()
        step=self.drag_translation_step if axis<3 else .1
        delta=pixels*step*drag['speed']
        if axis<3:matrix[axis,3]=np.clip(matrix[axis,3]+delta,-1e9,1e9)
        else:
            rotation=np.array(drag['rotation'],copy=True);rotation[axis-3]+=delta
            matrix[:3,:3]=transform_matrix(dict(position=[0,0,0],rotation=rotation,scale=1))[:3,:3]
        edits=copy.deepcopy(drag['edits'])
        if not np.allclose(matrix,drag['matrix'],rtol=0,atol=1e-12):edits[str(drag['frame'])]=matrix.tolist()
        self.track.replace(edits,remember=False);self.notify()

    def finish_drag(self,cancel=False,notify=True):
        if self.drag is None:return
        drag=self.drag;self.drag=None
        changed=self.track.edits()!=drag['edits']
        label=self.drag_labels[drag['axis']]
        # Also finish the mouse grab when a frame/project switch cancels the edit.
        label.finish(True)
        if cancel and changed:self.track.replace(drag['edits'],remember=False)
        elif not cancel and not hasattr(self,'shared_history') and changed:
            self.track.history.append(drag['edits']);self.track.history=self.track.history[-100:]
        if notify and changed:self.notify()
        if hasattr(self,'shared_history'):self.shared_history.end()

    def cancel_drag(self):self.finish_drag(True)

    def notify(self):
        self.set_frame(self.frame)
        self.changed.emit()

    def apply_pose(self):
        if not self.can_edit_frame():return
        values = [field.value() for field in self.fields]
        self.track.set_matrix(self.frame, transform_matrix(dict(position=values[:3], rotation=values[3:], scale=1)))
        self.notify()

    def interpolate(self):
        if not self.can_edit_frame():return
        self.edit_started.emit()
        if self.track.interpolate_neighbours(self.frame,self.interpolation_radius.value()):self.notify()

    def update_interpolation_controls(self,*args):
        radius=self.interpolation_radius.value();self.interpolate_button.setText(f'Interpolate ±{radius}')
        editable=self.can_edit_frame();self.interpolation_radius.setEnabled(editable)
        plan=self.track.interpolation_window(self.frame,radius) if editable else None
        enabled=bool(plan and plan['targets']);self.interpolate_button.setEnabled(enabled)
        if enabled:
            left=int(self.track.frames[plan['left']]);right=int(self.track.frames[plan['right']]);targets=plan['targets']
            self.interpolate_button.setToolTip(f'Keep centre frame {self.frame} exactly. Interpolate {len(targets)} solved neighbours in {targets[0]}–{targets[-1]} using fixed anchors {left} and {right}. Position is linear; rotation follows the shortest arc. One Undo restores the whole range. This explicit range action also works with Only this frame enabled.')
        else:self.interpolate_button.setToolTip('Choose the editable solved frame with at least one neighbour between it and an outer anchor. Centre and clip endpoints are preserved.')

    def reset(self):
        if not self.can_edit_frame():return
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
