"""Standalone tracker UI; Blender is used only for optional .blend export."""
import os
import sys
import json
import time
import subprocess
import uuid
import math
from pathlib import Path

# QVideoWidget and QOpenGLWidget share one top-level window and graphics API.
os.environ['QSG_RHI_BACKEND']='opengl'

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from pipeline import CONFIG, Job, read_model
if CONFIG.get('qt_packages'):
    sys.path.insert(0,CONFIG['qt_packages'])
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QThread, QUrl, QSize, QEvent
from PySide6.QtGui import QSurfaceFormat, QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QPushButton,QLineEdit,QFileDialog,QSplitter,QSpinBox,QDoubleSpinBox,
    QComboBox,QCheckBox,QGroupBox,QFormLayout,QSlider,QProgressBar,QPlainTextEdit,QScrollArea,QMessageBox,QDockWidget,QAbstractSpinBox,QTextEdit)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QVideoSink,QVideoFrame
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QStackedWidget
from desktop_viewport import Viewport
from image_overlay import OverlayImage
from scene_editor import SceneEditor
from camera_editor import CameraEditor
from mesh_panel import MeshPanel
from project_manager import ProjectManager
from floor_alignment import make_panel
from preview_cache import FrameCache

SAMPLE=Path(CONFIG['sample_project']) if CONFIG.get('sample_project') else ROOT/'sample_project'


class ModelLoader(QThread):
    loaded=Signal(object); failed=Signal(str)
    def __init__(self,folder): super().__init__(); self.folder=folder
    def run(self):
        try: self.loaded.emit(read_model(self.folder))
        except Exception as exc: self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ALIEN TRACKER')
        available=QApplication.primaryScreen().availableGeometry()
        self.resize(min(1500,available.width()-60),min(920,available.height()-60))
        self.job=None; self.loader=None; self.poses=[]; self.pose_by_frame={}; self.model_folder=None
        self.images=None; self.model_fps=30.; self.playing=False; self.frame=1; self.export_process=None
        self.source_mode=False; self.log_offset=0
        self._pending_video_frame=None;self._source_scheduled=False;self._requested_frame=None
        self.frame_cache=FrameCache(self);self.frame_cache.ready.connect(self.solved_frame_ready)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setTimerType(Qt.PreciseTimer);self.preview_timer.timeout.connect(self.advance_solved)
        self.mesh_after_tracking=False
        self.viewport=Viewport();self.cameras={};self.source_cameras={}
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        header=QHBoxLayout(); brand=QLabel('ALIEN TRACKER'); brand.setObjectName('brand')
        header.addWidget(brand); header.addStretch()
        self.open_button=self.button('Open video',self.open_video,header)
        self.sample_button=self.button('Prepared scene',self.sample,header)
        self.import_button=self.button('Import TXT model',self.choose_model,header)
        self.export_button=self.button('Export .blend',self.export_blend,header); self.export_button.setEnabled(False)
        self.button('Scene & objects',self.show_editor,header)
        layout.addLayout(header)
        split=QSplitter(); layout.addWidget(split,1)
        panel=QWidget(); form=QVBoxLayout(panel); panel.setMaximumWidth(340); panel.setMinimumWidth(270)
        title=QLabel('TRACKING'); title.setObjectName('section'); form.addWidget(title)
        self.video=QLineEdit(); self.video.setPlaceholderText('Choose a video file…'); form.addWidget(self.video)
        self.settings=QGroupBox('Reconstruction settings'); fields=QFormLayout(self.settings)
        self.solver=QComboBox(); self.solver.addItems(['COLMAP','GLOMAP']); fields.addRow('Solver',self.solver)
        self.fps=QSpinBox(); self.fps.setRange(1,60); self.fps.setValue(6); fields.addRow('Tracking FPS',self.fps)
        self.size=QSpinBox(); self.size.setRange(640,8192); self.size.setSingleStep(160); self.size.setValue(1920); fields.addRow('Max image size',self.size)
        self.seconds=QDoubleSpinBox(); self.seconds.setRange(0,99999); self.seconds.setSuffix(' s'); fields.addRow('First seconds¹',self.seconds)
        self.overlap=QSpinBox(); self.overlap.setRange(2,100); self.overlap.setValue(10); fields.addRow('Neighbour frames',self.overlap)
        self.gpu=QCheckBox('Use GPU'); self.gpu.setChecked(True); fields.addRow(self.gpu)
        self.mask=QLineEdit(); self.mask.setPlaceholderText('Optional static mask'); fields.addRow('Mask',self.mask)
        self.button('Choose mask…',self.choose_mask,fields)
        form.addWidget(self.settings)
        note=QLabel('¹ 0 = full video. FPS resamples the video.\nMask: black ignores pixels, white tracks them.'); note.setWordWrap(True); form.addWidget(note)
        self.output=QLineEdit(str(ROOT/'projects')); form.addWidget(QLabel('Project output')); form.addWidget(self.output)
        self.button('Choose output folder…',self.choose_output,form)
        controls=QHBoxLayout(); self.start=self.button('Start tracking',self.start_job,controls); self.start.setObjectName('primary')
        self.stop=self.button('Stop',self.cancel_job,controls); self.stop.setEnabled(False); form.addLayout(controls)
        self.generate_mesh_button=self.button('Generate 3D mesh',self.generate_mesh,form)
        self.generate_mesh_button.setToolTip('Use the current reconstruction, or track the selected video and then generate its surface mesh.')
        self.progress=QProgressBar(); self.progress.setRange(0,6); form.addWidget(self.progress)
        self.status=QLabel('Ready'); self.status.setWordWrap(True); form.addWidget(self.status)
        self.button('Open result folder',self.open_folder,form)
        form.addStretch()
        self.stats=QLabel('No reconstruction loaded'); self.stats.setWordWrap(True); self.stats.setObjectName('stats'); form.addWidget(self.stats)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel);scroll.setMinimumWidth(280); split.addWidget(scroll)
        work=QWidget(); work_layout=QVBoxLayout(work); work_layout.setContentsMargins(0,0,0,0); split.addWidget(work)
        views=QSplitter(); work_layout.addWidget(views,1)
        image_panel=QWidget(); image_layout=QVBoxLayout(image_panel); image_layout.setContentsMargins(0,0,0,0)
        self.image_title=QLabel('IMAGE / SOURCE'); image_layout.addWidget(self.image_title)
        overlay_row=QHBoxLayout();self.overlay_toggle=QCheckBox('Object overlay');self.overlay_toggle.setChecked(True);overlay_row.addWidget(self.overlay_toggle)
        self.overlay_toggle.setText('Objects')
        self.cloud_toggle=QCheckBox('Points');overlay_row.addWidget(self.cloud_toggle)
        self.mesh_toggle=QCheckBox('Mesh');overlay_row.addWidget(self.mesh_toggle)
        self.button('Shading…',self.show_shading,overlay_row)
        self.overlay_alpha=QSlider(Qt.Horizontal);self.overlay_alpha.setRange(0,100);self.overlay_alpha.setValue(65);self.overlay_alpha.setToolTip('Geometry overlay opacity');overlay_row.addWidget(self.overlay_alpha);image_layout.addLayout(overlay_row)
        floor_row=QHBoxLayout();self.floor_toggle=QCheckBox('Floor grid');self.floor_toggle.setChecked(True);floor_row.addWidget(self.floor_toggle)
        self.floor_spacing=QDoubleSpinBox();self.floor_spacing.setRange(.001,100000);self.floor_spacing.setDecimals(3);self.floor_spacing.setValue(1);floor_row.addWidget(QLabel('Step'));floor_row.addWidget(self.floor_spacing)
        self.floor_height=QDoubleSpinBox();self.floor_height.setRange(-1e6,1e6);self.floor_height.setDecimals(3);floor_row.addWidget(QLabel('Z'));floor_row.addWidget(self.floor_height)
        self.floor_toggle.setToolTip('World XY plane. Align the reconstruction using Scene & objects. The grid does not estimate the real floor.');image_layout.addLayout(floor_row)
        self.button('Align floor…',self.show_floor,floor_row)
        self.image_stack=QStackedWidget(); self.image=OverlayImage('Load a video or prepared scene',self.viewport); self.image.setAlignment(Qt.AlignCenter); self.image.setMinimumSize(240,260); self.image.setStyleSheet('background:#10141b;')
        self.image_stack.addWidget(self.image); self.video_widget=OverlayImage('',self.viewport);self.video_widget.setAlignment(Qt.AlignCenter);self.image_stack.addWidget(self.video_widget); image_layout.addWidget(self.image_stack,1)
        self.overlay_toggle.toggled.connect(self.refresh_overlay);self.overlay_alpha.valueChanged.connect(self.refresh_overlay);self.viewport.edited.connect(self.refresh_overlay)
        self.floor_toggle.toggled.connect(self.refresh_overlay);self.floor_spacing.valueChanged.connect(self.refresh_overlay);self.floor_height.valueChanged.connect(self.refresh_overlay);self.refresh_overlay()
        self.cloud_toggle.toggled.connect(self.refresh_overlay);self.mesh_toggle.toggled.connect(self.refresh_overlay)
        views.addWidget(image_panel)
        scene_panel=QWidget(); scene_layout=QVBoxLayout(scene_panel); scene_layout.setContentsMargins(0,0,0,0)
        options=QHBoxLayout(); self.button('Fit scene',lambda:self.viewport.fit(),options)
        self.points_toggle=QCheckBox('Points'); self.points_toggle.setChecked(True); options.addWidget(self.points_toggle)
        self.path_toggle=QCheckBox('Camera path'); self.path_toggle.setChecked(True); options.addWidget(self.path_toggle)
        options.addStretch(); options.addWidget(QLabel('Z ↑')); scene_layout.addLayout(options)
        self.edit_mode=QComboBox();self.edit_mode.addItems(['Orbit','Move','Rotate']);self.edit_mode.currentTextChanged.connect(self.viewport.set_mode);self.viewport.mode_changed.connect(self.edit_mode.setCurrentText);options.addWidget(self.edit_mode)
        scene_layout.addWidget(self.viewport,1); views.addWidget(scene_panel)
        self.editor=SceneEditor(self.viewport);self.editor_dock=QDockWidget('Scene & objects',self);editor_scroll=QScrollArea();editor_scroll.setWidgetResizable(True);editor_scroll.setWidget(self.editor);self.editor_dock.setWidget(editor_scroll);self.addDockWidget(Qt.RightDockWidgetArea,self.editor_dock);self.editor_dock.hide()
        self.points_toggle.toggled.connect(self.toggle_points); self.path_toggle.toggled.connect(self.toggle_path)
        views.setSizes([420,700]); split.setSizes([300,1200])
        timeline=QHBoxLayout(); self.play=self.button('▶ Play',self.toggle_play,timeline)
        self.play.setToolTip('Play / pause (Space)')
        self.slider=QSlider(Qt.Horizontal); self.slider.setRange(1,1); self.slider.valueChanged.connect(self.seek); timeline.addWidget(self.slider,1)
        self.time_label=QLabel('—'); self.time_label.setMinimumWidth(160); timeline.addWidget(self.time_label); work_layout.addLayout(timeline)
        mode=QHBoxLayout(); self.button('Source video',self.preview_source,mode); self.button('Solved frames',self.preview_solved,mode)
        self.import_rate=QDoubleSpinBox(); self.import_rate.setDecimals(5); self.import_rate.setRange(.1,240); self.import_rate.setValue(30000/1001); mode.addWidget(QLabel('Import FPS')); mode.addWidget(self.import_rate); mode.addStretch(); work_layout.addLayout(mode)
        self.graph_toggle=QCheckBox('Keyframe graph');self.graph_toggle.setChecked(True);mode.addWidget(self.graph_toggle)
        self.camera_editor=CameraEditor();work_layout.addWidget(self.camera_editor)
        self.graph_toggle.toggled.connect(self.camera_editor.setVisible);self.camera_editor.selected.connect(self.select_camera_frame);self.camera_editor.changed.connect(self.camera_corrected)
        self.camera_editor.edit_started.connect(self.pause)
        self.mesh_panel=MeshPanel(self);self.mesh_dock=QDockWidget('Mesh & shading',self);mesh_scroll=QScrollArea();mesh_scroll.setWidgetResizable(True);mesh_scroll.setWidget(self.mesh_panel);self.mesh_dock.setWidget(mesh_scroll);self.addDockWidget(Qt.RightDockWidgetArea,self.mesh_dock);self.mesh_dock.hide()
        self.floor_panel=make_panel(self);self.floor_dock=QDockWidget('Floor alignment',self);self.floor_dock.setWidget(self.floor_panel);self.addDockWidget(Qt.RightDockWidgetArea,self.floor_dock);self.floor_dock.hide()
        self.tabifyDockWidget(self.editor_dock,self.mesh_dock);self.tabifyDockWidget(self.mesh_dock,self.floor_dock)
        self.editor_dock.hide();self.mesh_dock.hide();self.floor_dock.hide()
        self.console=QPlainTextEdit(); self.console.setReadOnly(True); self.console.setMaximumBlockCount(500); self.console.setMaximumHeight(65); work_layout.addWidget(self.console)
        self.player=QMediaPlayer(self); self.audio=QAudioOutput(self); self.audio.setVolume(0); self.player.setAudioOutput(self.audio)
        self.video_sink=QVideoSink(self);self.player.setVideoSink(self.video_sink);self.video_sink.videoFrameChanged.connect(self.source_frame)
        self.player.durationChanged.connect(self.duration_changed); self.player.positionChanged.connect(self.position_changed)
        self.player.errorOccurred.connect(lambda *_:self.status.setText(self.player.errorString()))
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(30)
        self.setStyleSheet('''QWidget{background:#191e27;color:#dbe4ef;font:10pt "Segoe UI";} QMainWindow{background:#11151c;}
QLabel#brand{font-size:19pt;font-weight:700;color:#f0f6ff;padding:10px;} QLabel#section{color:#76c7ff;font-weight:700;padding:8px 0;}
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit{background:#111720;border:1px solid #354153;border-radius:4px;padding:6px;}
QPushButton{background:#283346;border:1px solid #40516a;border-radius:5px;padding:8px;} QPushButton:hover{background:#364c67;} QPushButton:disabled{color:#6a7685;}
QPushButton#primary{background:#246cb0;border-color:#498fce;font-weight:bold;} QGroupBox{border:1px solid #354153;border-radius:6px;margin-top:12px;padding-top:14px;}
QGroupBox::title{subcontrol-origin:margin;left:10px;} QLabel#stats{background:#202d3d;padding:12px;border-radius:5px;} QSplitter::handle{background:#293342;}''')
        self.project=ProjectManager(self)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self,receiver,event):
        if (event.type() in (QEvent.ShortcutOverride,QEvent.KeyPress,QEvent.KeyRelease)
                and event.key()==Qt.Key_Space and event.modifiers()==Qt.NoModifier
                and isinstance(receiver,QWidget) and (receiver is self or self.isAncestorOf(receiver))
                and QApplication.activeModalWidget() is None and QApplication.activePopupWidget() is None):
            focus=QApplication.focusWidget()
            editing=isinstance(focus,(QLineEdit,QAbstractSpinBox,QComboBox)) or (
                isinstance(focus,(QPlainTextEdit,QTextEdit)) and not focus.isReadOnly())
            if not editing:
                if event.type()==QEvent.KeyPress and not event.isAutoRepeat() and self.viewport.drag is None:
                    self.toggle_play()
                event.accept();return True
        return super().eventFilter(receiver,event)

    def button(self,text,callback,layout):
        b=QPushButton(text); b.clicked.connect(callback)
        if isinstance(layout,QFormLayout): layout.addRow(b)
        else: layout.addWidget(b)
        return b

    def toggle_points(self,value): self.viewport.show_points=value; self.viewport.update()
    def show_editor(self):self.editor_dock.show();self.editor_dock.raise_()
    def show_shading(self):self.mesh_dock.show();self.mesh_dock.raise_();self.resizeDocks([self.mesh_dock],[320],Qt.Horizontal)
    def show_floor(self):self.floor_dock.show();self.floor_dock.raise_();self.resizeDocks([self.floor_dock],[290],Qt.Horizontal)
    def generate_mesh(self):
        if self.job or self.loader or self.mesh_panel.running or self.export_process:return
        if self.model_folder and (not self.video.text() or self.video.text()==getattr(self,'model_video',None)):
            self.show_shading();self.mesh_panel.start();return
        if not Path(self.video.text()).is_file():
            self.open_video()
            if not Path(self.video.text()).is_file():return
        if self.start_job():
            self.mesh_after_tracking=True;self.status.setText('Video → tracking → surface mesh. Stop cancels the sequence.')
    def refresh_overlay(self,*args):
        self.viewport.floor_spacing=self.floor_spacing.value();self.viewport.floor_height=self.floor_height.value();self.viewport.update()
        for widget in (self.image,self.video_widget):
            widget.enabled_overlay=self.overlay_toggle.isChecked();widget.opacity=self.overlay_alpha.value()/100;widget.enabled_grid=self.floor_toggle.isChecked();widget.enabled_points=self.cloud_toggle.isChecked();widget.enabled_mesh=self.mesh_toggle.isChecked();widget.update()
    def select_camera_frame(self,frame):
        self.pause()
        if self.source_mode:self.preview_solved()
        self.slider.setValue(frame);self.seek(frame)
    def camera_corrected(self):
        self.pause();self.viewport.update_camera_path(self.poses)
        if self.source_mode:
            pose=self.pose_by_frame.get(self.camera_editor.frame);self.viewport.set_pose(pose)
        else:self.seek(self.frame)
        self.refresh_overlay()
    def source_frame(self,frame):
        if not self.source_mode or not frame.isValid():return
        self._pending_video_frame=QVideoFrame(frame)
        if not self._source_scheduled:
            self._source_scheduled=True;QTimer.singleShot(0,self.present_source_frame)
    def present_source_frame(self):
        self._source_scheduled=False;frame=self._pending_video_frame;self._pending_video_frame=None
        if not self.source_mode or frame is None:return
        image=frame.toImage()
        if image.isNull():return
        self.video_widget.setPixmap(QPixmap.fromImage(image.scaled(self.video_widget.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation)))
        if self.video.text()==getattr(self,'model_video',None):
            timestamp=frame.startTime() if frame.startTime()>=0 else self.player.position()*1000
            frame_number=1+round(timestamp/1e6*self.model_fps);pose=self.pose_by_frame.get(frame_number)
            self.viewport.set_pose(pose);self.video_widget.camera=self.source_cameras.get(pose['camera']) if pose else None
            self.camera_editor.set_frame(frame_number)
        else:self.video_widget.camera=None;self.viewport.set_pose(None)
        self.video_widget.update()
    def toggle_path(self,value): self.viewport.show_path=value; self.viewport.update()
    def choose_mask(self):
        p,_=QFileDialog.getOpenFileName(self,'Static mask','','Images (*.png *.jpg *.bmp)')
        if p:self.mask.setText(p)
    def choose_output(self):
        p=QFileDialog.getExistingDirectory(self,'Project output',self.output.text())
        if p:self.output.setText(p)
    def open_video(self):
        self.project.open_video()
    def sample(self):
        folder=SAMPLE/'04 SCENES/IMG_2284_nonHDR/sparse'
        if folder.is_dir():
            self.video.setText(str(SAMPLE/'02 VIDEOS/IMG_2284_nonHDR.mov'))
            self.load_model(folder,folder.parent/'images',30000/1001)
    def choose_model(self):
        p=QFileDialog.getExistingDirectory(self,'Folder containing cameras.txt, images.txt, points3D.txt')
        if not p:return
        folder=Path(p); images=folder.parent/'images'; fps=self.import_rate.value()
        metadata=folder.parent/'settings.json'
        if metadata.is_file():
            try:
                s=json.loads(metadata.read_text()); fps=float(s['fps']); self.video.setText(s['video'])
            except (ValueError,KeyError):pass
        if (folder.parent/'undistorted/images').is_dir(): images=folder.parent/'undistorted/images'
        if not images.is_dir():
            selected=QFileDialog.getExistingDirectory(self,'Corresponding frame images (Cancel = 3D only)')
            images=Path(selected) if selected else None
        self.load_model(folder,images,fps)
    def load_model(self,folder,images,fps,confirmed=False):
        if self.loader is not None:return
        if self.mesh_panel.running:self.status.setText('Finish or cancel mesh generation first.');return
        if not confirmed and not self.camera_editor.confirm_discard():return
        self.pause(); self.pending=(Path(folder),images,fps); self.status.setText('Loading reconstruction…'); self.set_busy(True)
        self.loader=ModelLoader(folder); self.loader.loaded.connect(self.model_loaded); self.loader.failed.connect(self.load_failed)
        self.loader.finished.connect(self.loader_finished); self.loader.start()
    def loader_finished(self):
        self.loader.deleteLater(); self.loader=None; self.set_busy(self.job is not None)
        if self.mesh_after_tracking:
            self.mesh_after_tracking=False;self.show_shading();self.mesh_panel.start()
    def load_failed(self,message): self.mesh_after_tracking=False;self.status.setText('Import error: '+message)
    def model_loaded(self,data):
        cameras,poses,points=data
        if not poses:self.load_failed('No registered cameras'); return
        self.model_folder,self.images,self.model_fps=self.pending
        self.model_video=self.video.text()
        self.cameras=cameras;self.source_cameras=cameras
        # A new solve has undistorted intrinsics. Original video needs the raw calibration.
        if (self.model_folder.parent/'undistorted').is_dir():
            from scene_geometry import read_raw_cameras
            try:
                self.source_cameras=read_raw_cameras(self.model_folder.parent)
            except Exception:self.source_cameras={}
        self.poses=poses; self.pose_by_frame={p['frame']:p for p in poses}
        self.frame_cache.configure(self.images,poses);self._requested_frame=None
        self.floor_panel.reset()
        self.camera_editor.set_track(poses)
        self.viewport.set_model(points,poses)
        if not self.project.restoring:self.mesh_panel.model_changed()
        self.stats.setText(f"{len(poses):,} solved cameras\n{len(points):,} reconstructed points\n{self.model_fps:.3f} fps  ·  Z up")
        self.source_mode=False; self.player.pause(); self.image_stack.setCurrentWidget(self.image)
        self.slider.setRange(poses[0]['frame'],poses[-1]['frame']); self.slider.setValue(poses[0]['frame']); self.seek(poses[0]['frame'])
        self.export_button.setEnabled(True)
        distorted=any(c[0] not in ('PINHOLE','SIMPLE_PINHOLE') for c in cameras.values())
        self.status.setText('Loaded. Original distorted frames.' if distorted else 'Loaded. Undistorted camera model.')
    def preview_source(self):
        if not Path(self.video.text()).is_file():self.status.setText('Select an existing video first.'); return
        self.pause(); self.source_mode=True; self.image_stack.setCurrentWidget(self.video_widget)
        self._pending_video_frame=None
        self.image_title.setText('SOURCE VIDEO'); self.player.setSource(QUrl.fromLocalFile(self.video.text()))
        if self.video.text()!=getattr(self,'model_video',None):self.camera_editor.set_frame(-1)
        self.player.setPosition(0); self.slider.setRange(0,int(self.player.duration()))
    def preview_solved(self):
        if not self.poses:return
        self.pause(); self.source_mode=False; self.image_stack.setCurrentWidget(self.image)
        self._pending_video_frame=None
        self.slider.setRange(self.poses[0]['frame'],self.poses[-1]['frame']); self.slider.setValue(self.poses[0]['frame']); self.seek(self.slider.value())
    def duration_changed(self,duration):
        if self.source_mode:self.slider.setRange(0,int(duration))
        if self.source_mode and duration>0 and hasattr(self,'pending_source_position'):
            position=self.pending_source_position;del self.pending_source_position;self.player.setPosition(min(position,duration))
    def position_changed(self,position):
        if self.source_mode:
            self.slider.blockSignals(True); self.slider.setValue(position); self.slider.blockSignals(False)
            self.time_label.setText(f'{position/1000:.2f} / {self.player.duration()/1000:.2f} s')
            # The displayed frame timestamp updates the pose, not a separate media-clock event.
    def seek(self,value):
        if self.source_mode:self.player.setPosition(value); return
        if not self.poses:return
        if self.playing:
            self.play_origin=time.perf_counter();self.play_frame=value;self.schedule_solved()
        self.request_solved(value,immediate=not self.playing)
    def request_solved(self,value,immediate=False):
        self._requested_frame=value
        if value not in self.pose_by_frame:
            self.present_solved(value,None);return
        image=self.frame_cache.request(value,self.image.size())
        if image is None and immediate:image=self.frame_cache.load_now(value)
        if image is not None:self.present_solved(value,image)
    def solved_frame_ready(self,generation,frame):
        if self.playing and not self.source_mode and generation==self.frame_cache.generation and frame==self._requested_frame:
            image=self.frame_cache.get(frame)
            if image is not None:self.present_solved(frame,image)
    def present_solved(self,value,image):
        self.frame=value; pose=self.pose_by_frame.get(value); self.viewport.set_pose(pose)
        self.slider.blockSignals(True);self.slider.setValue(value);self.slider.blockSignals(False)
        self.camera_editor.set_frame(value)
        self.image.camera=self.cameras.get(pose['camera']) if pose else None
        self.time_label.setText(f'Frame {value} / {self.poses[-1]["frame"]}  ·  {(value-1)/self.model_fps:.2f} s')
        self.image_title.setText('SOLVED FRAME' if pose else 'UNREGISTERED FRAME — no solved camera')
        if image is not None and not image.isNull():self.image.setPixmap(QPixmap.fromImage(image))
        else:self.image.clear(); self.image.setText('No image / unsolved frame')
    def schedule_solved(self):
        elapsed=max(0.,time.perf_counter()-self.play_origin)
        deadline=self.play_origin+(math.floor(elapsed*self.model_fps)+1)/self.model_fps
        self.preview_timer.start(max(1,math.ceil((deadline-time.perf_counter())*1000)))
    def advance_solved(self):
        if not self.playing or self.source_mode or not self.poses:return
        # Keep real elapsed time even if decoding or painting misses a deadline.
        target=self.play_frame+int((time.perf_counter()-self.play_origin)*self.model_fps)
        if target>self.slider.maximum():
            self.pause();self.seek(self.slider.maximum());return
        if target!=self.frame:self.request_solved(target)
        self.schedule_solved()
    def pause(self):
        self.playing=False;self.preview_timer.stop();self.player.pause();self.play.setText('▶ Play')
        if not self.source_mode and self.poses and self._requested_frame is not None and self._requested_frame!=self.frame:
            self.request_solved(self._requested_frame,immediate=True)
    def toggle_play(self):
        if self.source_mode:
            if self.player.playbackState()==QMediaPlayer.PlayingState:self.pause()
            else:self.player.play(); self.play.setText('Ⅱ Pause')
        elif self.poses:
            if self.playing:self.pause()
            else:
                self.playing=True;self.play_origin=time.perf_counter();self.play_frame=self.frame;self.play.setText('Ⅱ Pause');self.schedule_solved()
    def set_busy(self,busy):
        for widget in (self.start,self.open_button,self.sample_button,self.import_button,self.settings,self.video,self.output,self.generate_mesh_button):widget.setEnabled(not busy)
        self.stop.setEnabled(self.job is not None or self.mesh_panel.running)
        if hasattr(self,'project'):
            for name,action in self.project.actions.items():
                if name!='Exit':action.setEnabled(not busy)
    def start_job(self):
        if self.job or self.loader or self.mesh_panel.running:return False
        if not self.camera_editor.confirm_discard():return False
        settings=dict(CONFIG,video=self.video.text(),output=self.output.text(),fps=self.fps.value(),duration=self.seconds.value(),size=self.size.value(),overlap=self.overlap.value(),gpu=self.gpu.isChecked(),solver=self.solver.currentText(),mask=self.mask.text())
        try:self.job=Job(settings)
        except Exception as exc:self.status.setText(str(exc)); return False
        self.log_offset=0; self.console.clear(); self.set_busy(True)
        return True
    def cancel_job(self):
        self.mesh_after_tracking=False
        if self.mesh_panel.running:self.mesh_panel.cancel()
        if self.job:
            self.job.cancel(); self.last_job_folder=self.job.folder; self.status.setText(self.job.message); self.job=None; self.set_busy(False)
    def tick(self):
        if self.job:
            try:
                state=self.job.tick(); self.progress.setValue(self.job.index); self.status.setText(self.job.message)
                log=self.job.folder/'tracking.log'
                with log.open(encoding='utf-8',errors='replace') as stream:
                    stream.seek(self.log_offset); text=stream.read(65536); self.log_offset=stream.tell()
                if text:self.console.appendPlainText(text.rstrip())
                if state!='running':
                    job=self.job; self.last_job_folder=job.folder; self.job=None; self.set_busy(False)
                    if state=='done':self.load_model(job.folder/'model',job.folder/'undistorted/images',job.settings['fps'],confirmed=True)
                    else:self.mesh_after_tracking=False
            except Exception as exc:
                self.cancel_job(); self.status.setText('Tracking error: '+str(exc))
        if self.export_process and self.export_process.poll() is not None:
            code=self.export_process.returncode; self.export_process=None; self.export_log.close(); self.export_button.setEnabled(True)
            self.status.setText('Blender project exported.' if code==0 else 'Export failed. See export.log.')
    def open_folder(self):
        folder=self.job.folder if self.job else getattr(self,'last_job_folder',self.model_folder)
        if folder and Path(folder).is_dir():os.startfile(str(folder))
    def export_blend(self):
        if not self.model_folder or self.export_process:return
        path,_=QFileDialog.getSaveFileName(self,'Export Blender project',str(ROOT/'tracked_camera.blend'),'Blender (*.blend)')
        if not path:return
        self.start_export(path)
    def start_export(self,path):
        if not path.lower().endswith('.blend'):path+='.blend'
        request=ROOT/('export_request_'+uuid.uuid4().hex[:10]+'.json'); request.write_text(json.dumps(dict(model=str(self.model_folder),images=str(self.images) if self.images else '',fps=self.model_fps,output=path,layout=self.editor.snapshot(),camera_corrections=self.camera_editor.track.document() if self.camera_editor.track else None,mesh=self.viewport.mesh_path,mesh_smooth=self.viewport.smooth_mesh)),encoding='utf-8')
        try:
            self.export_log=(ROOT/'export.log').open('w',encoding='utf-8')
            self.export_process=subprocess.Popen([CONFIG['blender'],'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'export_desktop.py'),'--',str(request)],stdout=self.export_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.export_button.setEnabled(False); self.status.setText('Exporting Blender project…')
        except Exception as exc:self.export_log.close(); self.status.setText(str(exc))
    def closeEvent(self,event):
        if self.loader is not None:
            self.status.setText('Finish loading before closing.'); event.ignore(); return
        if self.export_process:
            self.status.setText('Finish exporting before closing.'); event.ignore(); return
        if not self.project.confirm_discard():event.ignore();return
        self.mesh_panel.cancel();self.cancel_job();self.player.stop()
        self.preview_timer.stop();self.frame_cache.close();self._pending_video_frame=None
        self.image.renderer.close();self.video_widget.renderer.close();event.accept()


def main():
    fmt=QSurfaceFormat(); fmt.setVersion(3,3); fmt.setProfile(QSurfaceFormat.CoreProfile); fmt.setDepthBufferSize(24); QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication(sys.argv); w=Window(); w.show(); return app.exec()


if __name__=='__main__':sys.exit(main())
