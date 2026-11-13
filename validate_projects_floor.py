"""Real Qt tests for project lifecycle, point picking and floor alignment."""
import sys,time,json,copy,os
from pathlib import Path
import desktop
import numpy as np
from PySide6.QtCore import QTimer,Qt,QPointF
from PySide6.QtGui import QSurfaceFormat,QImage,QColor
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from PySide6.QtTest import QTest
from pipeline import read_model
from camera_track import CameraTrack
from test_camera_track import pose_from_matrix,matrix
from mesh_data import validate_mesh,save_mesh
from scene_geometry import transform_matrix

fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([])
os.environ['ALIEN_TRACKER_STATE_DIR']=str(desktop.ROOT/'validation/project_floor/recovery')
class TestWindow(desktop.Window):
    def sample(self):pass
w=TestWindow();w.show();deadline=time.monotonic()+30
folder=desktop.ROOT/'validation/project_floor';folder.mkdir(parents=True,exist_ok=True)
points=np.array([[-2,-2,-1],[2,-2,-.2],[2,2,.6],[-2,2,-.2]],float)
(folder/'cameras.txt').write_text('1 PINHOLE 640 480 500 500 320 240\n')
from camera_track import WORLD
(folder/'points3D.txt').write_text('\n'.join(' '.join(map(str,[i+1,*(xyz@WORLD),200,200,200,0])) for i,xyz in enumerate(points))+'\n')
lines=[]
for frame in range(1,4):
    pose=pose_from_matrix(frame,matrix([frame*.1,-5,3],[59,0,0]))
    lines+=[' '.join(map(str,[frame,*pose['q'],*pose['t'],1,pose['name']])),'']
    image=QImage(640,480,QImage.Format_RGB32);image.fill(QColor('#304050'));image.save(str(folder/pose['name']))
(folder/'images.txt').write_text('\n'.join(lines)+'\n')
original_save=QFileDialog.getSaveFileName;original_open=QFileDialog.getOpenFileName
original_question=QMessageBox.question;original_warning=QMessageBox.warning
messages=[];QMessageBox.warning=lambda *args:messages.append(args[-1])
path=folder/'test.tracker.json';expected=None

def first():
    global expected
    try:
        assert w.windowTitle().startswith('ALIEN TRACKER')
        assert set(('Open video…','Open project…','Save project','New project','Exit')).issubset(w.project.actions)
        w.pending=(folder,folder,30.);w.model_loaded(read_model(folder));w.project.mark_saved()
        v=w.viewport;w.graph_toggle.setChecked(False);w.show_floor();w.floor_panel.pick.setChecked(True);v.fit();v.distance*=2;app.processEvents();v.grabFramebuffer()
        for index in [0,1,2]:
            pixel=v.project(v.points[index,:3]);assert pixel is not None
            QTest.mouseClick(v,Qt.LeftButton,pos=QPointF(*pixel[:2]).toPoint())
        assert set(v.floor_indices)=={0,1,2},v.floor_indices
        QTest.mouseClick(w.floor_panel.apply_button,Qt.LeftButton)
        aligned=transform_matrix(v.scene_transform);np.testing.assert_allclose((points@aligned[:3,:3].T+aligned[:3,3])[:,2],0,atol=1e-6)
        assert w.floor_height.value()==0 and not v.floor_pick
        QTest.mouseClick(w.floor_panel.undo,Qt.LeftButton);np.testing.assert_allclose(transform_matrix(v.scene_transform),np.eye(4),atol=1e-9)
        w.floor_panel.apply();assert w.floor_panel.previous is not None
        cube=v.add_primitive('Cube');cube['position']=[1,2,3];cube['rotation']=[10,20,30]
        w.select_camera_frame(2);correction=v.pose.copy();correction[0,3]+=.25;w.camera_editor.track.set_matrix(2,correction);w.camera_editor.notify()
        mesh=validate_mesh(points,np.array([[0,1,2],[0,2,3]]),np.ones((4,3))*.7)
        mesh_path=folder/'surface.npz';save_mesh(mesh_path,mesh,w.camera_editor.track.fingerprint);w.mesh_panel.accept_mesh(mesh_path)
        w.mesh_panel.shading.setCurrentText('Solid + wire');w.floor_spacing.setValue(.5);w.fps.setValue(12)
        expected=w.project.snapshot();QFileDialog.getSaveFileName=lambda *args:(str(path),'Tracker project')
        w.project.actions['Save project'].trigger();assert path.is_file(),messages
        assert w.project.signature()==w.project.baseline
        # Cancel preserves objects and corrections; Save-and-New persists the latest edit.
        cube['position'][0]=4;QMessageBox.question=lambda *args:QMessageBox.Cancel
        assert not w.project.new();assert w.viewport.objects[0]['position'][0]==4
        QMessageBox.question=lambda *args:QMessageBox.Save
        expected=w.project.snapshot();assert w.project.new();assert not w.poses and not w.viewport.objects and w.viewport.mesh is None and w.camera_editor.track is None
        QMessageBox.question=lambda *args:QMessageBox.Cancel
        assert w.project.open_path(path)
        QTimer.singleShot(100,reopened)
    except Exception:fail()

def reopened():
    try:
        assert time.monotonic()<deadline
        if w.loader is not None:QTimer.singleShot(100,reopened);return
        assert not messages,messages
        actual=w.project.snapshot()
        for key in ('assets','layout','camera_corrections','tracking','view','meshing'):
            assert actual[key]==expected[key],key
        assert w.frame==2 and w.viewport.mesh is not None
        assert w.project.signature()==w.project.baseline
        # Invalid/missing assets must leave the currently loaded project unchanged.
        bad=json.loads(path.read_text());bad['assets']['model']='missing/model'
        invalid=folder/'broken.tracker.json';invalid.write_text(json.dumps(bad))
        assert w.project.open_path(invalid);QTimer.singleShot(100,rejected)
    except Exception:fail()

def rejected():
    try:
        if w.loader is not None:QTimer.singleShot(100,rejected);return
        assert messages and w.project.path==path.resolve()
        assert w.project.snapshot()['layout']==expected['layout']
        count=[];start=w.mesh_panel.start;w.mesh_panel.start=lambda:count.append(True)
        try:QTest.mouseClick(w.generate_mesh_button,Qt.LeftButton);assert count==[True] and w.job is None
        finally:w.mesh_panel.start=start
        w.mesh_dock.hide();w.show_floor();w.viewport.fit();w.viewport.grabFramebuffer();w.grab().save(str(folder/'project_floor.png'))
        video=desktop.SAMPLE/'02 VIDEOS/IMG_2284_nonHDR.mov'
        if video.is_file():
            w.project.mark_saved();QFileDialog.getOpenFileName=lambda *args:(str(video),'Video')
            w.project.actions['Open video…'].trigger()
            assert w.source_mode and w.video.text()==str(video) and not w.poses and not w.viewport.objects
            w.project.path=folder/'video_only.tracker.json';assert w.project.save()
            video_project=w.project.path;assert w.project.new();assert w.project.open_path(video_project)
            QTimer.singleShot(100,video_reopened)
        else:finish()
    except Exception:fail()

def video_reopened():
    try:
        if w.loader is not None:QTimer.singleShot(100,video_reopened);return
        assert w.source_mode and not w.poses and w.video.text()
        finish()
    except Exception:fail()

def finish():
    w.project.mark_saved();w.close();print('PASS File actions, point picking/plane alignment/undo, project save/reopen, corrections/objects/mesh/settings persistence, Save/Cancel guards, failed-open preservation, video-only projects and mesh-button reuse',flush=True);app.exit(0)

def fail():
    import traceback;traceback.print_exc();app.exit(1)
QTimer.singleShot(300,first)
code=app.exec();QFileDialog.getSaveFileName=original_save;QFileDialog.getOpenFileName=original_open;QMessageBox.question=original_question;QMessageBox.warning=original_warning
sys.exit(code)
