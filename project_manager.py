"""File menu, project lifecycle and non-destructive asynchronous reopening."""
import copy
import json
from pathlib import Path
import numpy as np
from PySide6.QtCore import QObject,QThread,Signal,QTimer,QUrl,QSize
from PySide6.QtGui import QAction,QKeySequence
from PySide6.QtWidgets import QFileDialog,QMessageBox,QCheckBox,QComboBox,QLineEdit
from pipeline import ROOT
from scene_geometry import identity_transform
from project_io import write_project,read_project
from project_recovery import Recovery,relink_document

TRACKING=('solver','fps','size','seconds','overlap','gpu','mask','output','import_rate')
VIEW=('floor_toggle','floor_spacing','floor_height','overlay_toggle','cloud_toggle','mesh_toggle','overlay_alpha','points_toggle','path_toggle','graph_toggle')
MESH=('shading','smooth','show_mesh','point_color','point_size','depth','limit','trim')


def value(widget):
    if isinstance(widget,QCheckBox):return widget.isChecked()
    if isinstance(widget,QComboBox):return widget.currentText()
    if isinstance(widget,QLineEdit):return widget.text()
    return widget.value()


def assign(widget,data):
    if isinstance(widget,QCheckBox):widget.setChecked(data)
    elif isinstance(widget,QComboBox):widget.setCurrentText(data)
    elif isinstance(widget,QLineEdit):widget.setText(data)
    else:widget.setValue(data)


class ProjectLoader(QThread):
    loaded=Signal(object);failed=Signal(str)
    def __init__(self,path,data=None):super().__init__();self.path=path;self.data=data
    def run(self):
        try:self.loaded.emit(read_project(self.path,self.data))
        except Exception as exc:self.failed.emit(str(exc))


class ProjectManager(QObject):
    def __init__(self,window):
        super().__init__(window);self.w=window;self.path=None;self.restoring=False
        self.defaults=self.snapshot();self.baseline=self.signature()
        menu=window.menuBar().addMenu('&File');self.menu=menu;self.actions={}
        for name,shortcut,callback in [('New project','Ctrl+N',self.new),('Open video…','Ctrl+O',self.open_video),('Open project…','Ctrl+Shift+O',self.open),('Save project','Ctrl+S',self.save),('Save project as…','Ctrl+Shift+S',lambda:self.save(force_path=True)),('Exit','Alt+F4',window.close)]:
            if name=='Exit':menu.addSeparator()
            action=QAction(name,window);action.setShortcut(QKeySequence(shortcut));action.triggered.connect(callback);menu.addAction(action);self.actions[name]=action
        self.timer=QTimer(self);self.timer.timeout.connect(self.update_title);self.timer.start(400)
        self.recovery=Recovery(self)

    def snapshot(self):
        w=self.w;v=w.viewport
        data=dict(format='colmap-tracker-project',version=1,
            assets=dict(video=w.video.text(),model_video=getattr(w,'model_video',''),model=str(w.model_folder or ''),images=str(w.images or ''),mesh=v.mesh_path or ''),
            model_fps=w.model_fps,layout=w.editor.snapshot(),camera_corrections=w.camera_editor.track.document() if w.camera_editor.track else None,
            tracking={k:value(getattr(w,k)) for k in TRACKING},view={k:value(getattr(w,k)) for k in VIEW},
            meshing={k:value(getattr(w.mesh_panel,k)) for k in MESH},
            orbit=dict(center=v.center.tolist(),distance=v.distance,yaw=v.yaw,pitch=v.pitch,orthographic=v.orthographic),
            playback=dict(frame=w.frame,source_mode=w.source_mode,position=w.player.position()))
        if hasattr(w,'transport'):data['transport']=w.transport.document()
        data['diagnostics']=dict(enabled=w.error_toggle.isChecked(),original=w.error_pose.currentIndex()==1,
            minimum=w.track_data_panel.minimum_error.value(),limit=w.track_data_panel.marker_limit.value())
        return copy.deepcopy(data)

    def signature(self):
        data=self.snapshot();data.pop('playback');data.pop('orbit')
        return json.dumps(data,sort_keys=True,allow_nan=False)

    def mark_saved(self):
        self.baseline=self.signature()
        if self.w.camera_editor.track:self.w.camera_editor.track.saved=self.w.camera_editor.track.edits();self.w.camera_editor.set_frame(self.w.camera_editor.frame)
        self.update_title()

    def update_title(self):
        dirty=not self.restoring and self.signature()!=self.baseline
        self.w.setWindowTitle('ALIEN TRACKER'+(' — '+self.path.name if self.path else '')+(' *' if dirty else ''))

    def available(self):
        w=self.w
        if w.camera_editor.dragging:w.status.setText('Finish the camera drag or press Esc first.');return False
        if w.loader is not None or w.job or w.mesh_panel.running or w.export_process:
            w.status.setText('Finish or cancel the current operation first.');return False
        return True

    def confirm_discard(self):
        if self.signature()==self.baseline:return True
        self.w.pause()
        answer=QMessageBox.question(self.w,'Unsaved project','Save the project before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save() if answer==QMessageBox.Save else answer==QMessageBox.Discard

    def save(self,checked=False,force_path=False):
        if not self.available():return False
        target=self.path
        if target is None or force_path:
            selected,_=QFileDialog.getSaveFileName(self.w,'Save project',str(target or ROOT/'projects/untitled.tracker.json'),'Tracker project (*.tracker.json)')
            if not selected:return False
            if not selected.lower().endswith('.tracker.json'):selected+='.tracker.json'
            target=Path(selected)
        try:write_project(target,self.snapshot())
        except Exception as exc:QMessageBox.warning(self.w,'Cannot save project',str(exc));return False
        self.path=target.resolve();self.mark_saved();self.recovery.discard();self.recovery.remember(self.path);self.w.status.setText('Project saved: '+str(self.path));return True

    def clear(self,reset_settings=True):
        self.w.camera_editor.cancel_drag()
        w=self.w;w.pause();w.player.setSource(QUrl());w.mesh_after_tracking=False
        self.recovery.discard()
        w.frame_cache.configure(None,[]);w._requested_frame=None;w._pending_video_frame=None
        w._source_image=None
        w.track_data=None;w.track_data_panel.set_tracks(None,30.);w.track_data_button.setEnabled(False);w.track_data_dock.hide()
        for widget in (w.image,w.video_widget):widget.reprojection.clear()
        if hasattr(w,'pending_source_position'):del w.pending_source_position
        w.source_mode=False;w.model_folder=None;w.images=None;w.model_fps=30.;w.model_video='';w.poses=[];w.pose_by_frame={};w.cameras={};w.source_cameras={};w.last_job_folder=None;w.frame=1
        v=w.viewport;w.floor_panel.reset();v.points=np.empty((0,6),np.float32);v.path=np.empty((0,6),np.float32);v.pose=None;v.dirty=True;v.set_mesh(None)
        v.point_ids=np.empty(0,np.int64)
        v.objects=[];v.scene_transform=identity_transform();v.selected=-1;v.set_mode('Orbit');w.edit_mode.setCurrentText('Orbit');v.center=np.zeros(3);v.distance=12.;v.fit();w.editor.refresh()
        e=w.camera_editor;e.reset_frame_scope();e.track=None;e.graph.track=None;e.file_path=None;e.set_frame(1)
        for widget in (w.image,w.video_widget):widget.clear();widget.camera=None;widget.renderer.cache_key=None
        for widget in (w.image,w.video_widget):widget.native_size=QSize();widget.fit_image()
        w.image.setText('Open a video or project');w.image_stack.setCurrentWidget(w.image);w.image_title.setText('IMAGE / SOURCE')
        w.slider.blockSignals(True);w.slider.setRange(1,1);w.slider.setValue(1);w.slider.blockSignals(False);w.time_label.setText('—')
        w.video.clear();w.export_button.setEnabled(False);w.mesh_panel.export_button.setEnabled(False);w.mesh_panel.status.setText('No mesh loaded');w.mesh_panel.progress.setRange(0,1);w.mesh_panel.progress.setValue(0)
        w.progress.setValue(0);w.stats.setText('No reconstruction loaded');w.console.clear()
        if reset_settings:
            self.restore_controls(self.defaults)
        if hasattr(w,'transport'):w.transport.reset()
        self.path=None;w.refresh_overlay();self.mark_saved()
        if hasattr(w,'history'):w.history.reset()
        w.refresh_reprojection()

    def new(self):
        if not self.available() or not self.confirm_discard():return False
        self.clear();self.w.status.setText('New project');return True

    def open_video(self):
        if not self.available():return
        selected,_=QFileDialog.getOpenFileName(self.w,'Open video','','Video (*.mp4 *.mov *.mkv *.avi *.m4v);;All files (*)')
        if not selected or not self.confirm_discard():return
        self.clear(reset_settings=False);self.w.video.setText(selected);self.w.preview_source()

    def validate_controls(self,data):
        for section,owner,names in [('tracking',self.w,TRACKING),('view',self.w,VIEW),('meshing',self.w.mesh_panel,MESH)]:
            for key in names:
                widget=getattr(owner,key);v=data[section][key]
                if isinstance(widget,QCheckBox):valid=isinstance(v,bool)
                elif isinstance(widget,QComboBox):valid=isinstance(v,str) and widget.findText(v)>=0
                elif isinstance(widget,QLineEdit):valid=isinstance(v,str)
                else:valid=isinstance(v,(int,float)) and widget.minimum()<=v<=widget.maximum()
                if not valid:raise ValueError('Invalid project setting: '+key)
        orbit=data['orbit']
        if len(orbit['center'])!=3 or any(not isinstance(v,(int,float)) or abs(v)>1e9 for v in orbit['center']) or not .01<=orbit['distance']<=1e7 or not -90<=orbit['pitch']<=90 or not isinstance(orbit['yaw'],(int,float)) or not isinstance(orbit['orthographic'],bool):raise ValueError('Invalid saved viewport.')
        playback=data['playback']
        if not isinstance(playback['frame'],int) or not isinstance(playback['position'],int) or playback['position']<0 or not isinstance(playback['source_mode'],bool):raise ValueError('Invalid saved timeline.')

    def restore_controls(self,data):
        for section,owner,names in [('tracking',self.w,TRACKING),('view',self.w,VIEW),('meshing',self.w.mesh_panel,MESH)]:
            for key in names:assign(getattr(owner,key),data[section][key])
        diagnostics=data.get('diagnostics',dict(enabled=False,original=False,minimum=0.,limit=1000))
        self.w.error_toggle.setChecked(diagnostics['enabled']);self.w.error_pose.setCurrentIndex(int(diagnostics['original']))
        self.w.track_data_panel.minimum_error.setValue(diagnostics['minimum']);self.w.track_data_panel.marker_limit.setValue(diagnostics['limit'])
        self.w.refresh_reprojection()

    def open(self):
        if not self.available():return
        path,_=QFileDialog.getOpenFileName(self.w,'Open project','','Tracker project (*.tracker.json);;JSON (*.json)')
        if path:self.open_path(path,relink=True)

    def open_path(self,path,recovery=False,relink=False):
        if not self.available() or not self.confirm_discard():return False
        data=None
        if relink or recovery:
            try:data=relink_document(self.w,path)
            except Exception as exc:self.failed(str(exc));return False
            if data is None:return False
        w=self.w;w.pause();self.opening_path=Path(path).resolve();self.restoring=True
        self.opening_recovery=recovery;self.opening_relinked=bool(data and data.get('_relinked'))
        w.centralWidget().setEnabled(False);w.editor_dock.setEnabled(False);w.mesh_dock.setEnabled(False);w.floor_dock.setEnabled(False)
        w.loader=ProjectLoader(path,data);w.loader.loaded.connect(self.apply);w.loader.failed.connect(self.failed);w.loader.finished.connect(self.finished);w.loader.start();w.set_busy(True)
        w.status.setText('Opening project…');return True

    def failed(self,message):
        self.w.status.setText('Project could not be opened: '+message)
        QMessageBox.warning(self.w,'Cannot open project',message)

    def apply(self,payload):
        data,model=payload
        try:self.validate_controls(data)
        except Exception as exc:self.failed(str(exc));return
        w=self.w;self.clear();w.video.setText(data['assets']['video'])
        if model:
            w.pending=(Path(data['assets']['model']),Path(data['assets']['images']) if data['assets']['images'] else None,data['model_fps'])
            w.model_loaded(model);w.model_video=data['assets']['model_video']
            if data.get('camera_corrections'):w.camera_editor.track.load_document(data['camera_corrections']);w.viewport.update_camera_path(w.poses)
        w.viewport.scene_transform=data['layout']['scene'];w.viewport.objects=data['layout']['objects'];w.viewport.selected=-1;w.editor.refresh()
        if data['assets']['mesh']:w.mesh_panel.accept_mesh(data['assets']['mesh'])
        self.restore_controls(data);w.viewport.center=np.array(data['orbit']['center'],float)
        for key in ('distance','yaw','pitch','orthographic'):setattr(w.viewport,key,data['orbit'][key])
        w.viewport.gizmo.update();w.viewport.update();w.refresh_overlay()
        play=data['playback']
        if play['source_mode'] and w.video.text():
            w.preview_source();w.pending_source_position=play['position'];w.player.setPosition(play['position'])
        elif w.poses:
            w.slider.setValue(max(w.slider.minimum(),min(w.slider.maximum(),play['frame'])));w.seek(w.slider.value())
        if hasattr(w,'transport'):w.transport.restore(data.get('transport',{}))
        self.path=self.opening_path;self.mark_saved()
        if self.opening_recovery:
            self.path=Path(data['recovery_source']) if data.get('recovery_source') else None;self.baseline=''
            w.status.setText('Autosave recovered — save the project to keep this version')
        else:
            self.recovery.remember(self.path);w.status.setText('Project opened: '+str(self.path))
            if self.opening_relinked:self.baseline=''
        if hasattr(w,'history'):w.history.reset()

    def finished(self):
        w=self.w;w.loader.deleteLater();w.loader=None;self.restoring=False
        w.centralWidget().setEnabled(True);w.editor_dock.setEnabled(True);w.mesh_dock.setEnabled(True);w.floor_dock.setEnabled(True);w.set_busy(False);self.update_title()
