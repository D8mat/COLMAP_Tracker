"""Interactive Qt/OpenGL integration test; synthetic solve, optional Blender check."""
import json
import sys
import time
import subprocess
from pathlib import Path
import desktop
import numpy as np
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QSurfaceFormat, QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtTest import QTest
from camera_track import camera_matrix
from pipeline import read_model, CONFIG
from test_camera_track import pose_from_matrix, matrix

fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([])
folder=desktop.ROOT/'validation/camera_tools';folder.mkdir(parents=True,exist_ok=True)
(folder/'cameras.txt').write_text('1 PINHOLE 640 480 500 500 320 240\n')
(folder/'points3D.txt').write_text('1 0 0 0 255 255 255 0\n2 1 0 1 255 100 100 0\n')
lines=[]
for frame in range(1,6):
    pose=pose_from_matrix(frame,matrix([8 if frame==3 else (frame-3)*.2,-5,3],[59,0,0]))
    lines.append(' '.join(map(str,[frame,*pose['q'],*pose['t'],1,pose['name']])))
    lines.append('')
    image=QImage(640,480,QImage.Format_RGB32);image.fill(QColor('#303d50'))
    painter=QPainter(image);painter.setPen(QColor('#e0e8ee'));painter.drawText(30,30,f'Synthetic camera test / frame {frame}');painter.end()
    image.save(str(folder/pose['name']))
(folder/'images.txt').write_text('\n'.join(lines)+'\n')

class TestWindow(desktop.Window):
    def sample(self):pass

w=TestWindow();w.show();deadline=time.monotonic()+60


def check():
    try:
        w.pending=(folder,folder,30.);w.model_loaded(read_model(folder));app.processEvents()
        e=w.camera_editor;g=e.graph
        point=QPointF(g.plot_rect().left()+g.plot_rect().width()/2,g.plot_rect().center().y()).toPoint()
        QTest.mouseClick(g,Qt.LeftButton,pos=point)
        assert w.frame==3 and e.frame==3
        assert e.track.values(1)[2,0]>7
        QTest.mouseClick(e.interpolate_button,Qt.LeftButton)
        expected=matrix([0,-5,3],[59,0,0])
        np.testing.assert_allclose(w.viewport.pose,expected,atol=1e-9)
        np.testing.assert_allclose(w.viewport.path[2,:3],[0,-5,3],atol=1e-6)
        np.testing.assert_allclose(e.track.values(1)[1:,0],.2,atol=1e-9)
        # Actual image changes with floor alone, independent from object overlay.
        w.overlay_toggle.setChecked(False);w.floor_toggle.setChecked(False)
        blank=w.image.grab().toImage();w.floor_toggle.setChecked(True)
        floor=w.image.grab().toImage();assert floor!=blank,'Floor did not render'
        w.floor_height.setValue(1);raised=w.image.grab().toImage();assert raised!=floor
        w.floor_height.setValue(0)
        w.viewport.scene_transform['position']=[1.,2.,.5];w.refresh_overlay()
        assert w.image.grab().toImage()!=floor,'Grid ignored whole-scene transform'
        e.fields[0].setValue(.75);e.fields[5].setValue(15)
        QTest.mouseClick(e.apply,Qt.LeftButton)
        np.testing.assert_allclose(w.viewport.pose,matrix([.75,-5,3],[59,0,15]),atol=1e-9)
        QTest.mouseClick(e.undo_button,Qt.LeftButton)
        np.testing.assert_allclose(w.viewport.pose,expected,atol=1e-9)
        # Save/load via UI callbacks, using a deterministic file-dialog result.
        saved=QFileDialog.getSaveFileName;opened=QFileDialog.getOpenFileName
        corrections=folder/'corrections.json'
        QFileDialog.getSaveFileName=lambda *a,**k:(str(corrections),'JSON (*.json)')
        QFileDialog.getOpenFileName=lambda *a,**k:(str(corrections),'JSON (*.json)')
        try:
            assert e.save();assert not e.track.dirty
            e.track.replace({});e.track.saved={};e.notify();e.load()
            np.testing.assert_allclose(w.viewport.pose,expected,atol=1e-9)
        finally:
            QFileDialog.getSaveFileName=saved;QFileDialog.getOpenFileName=opened
        w.select_camera_frame(1);assert not e.interpolate_button.isEnabled()
        w.select_camera_frame(3)
        w.viewport.grabFramebuffer();w.grab().save(str(folder/'camera_tools.png'))
        print('PASS graph click, spike interpolation, numeric rotation, undo, save/load, floor visibility/height/root alignment',flush=True)
        if not Path(CONFIG['blender']).is_file():
            print('SKIP Blender executable not configured',flush=True);w.project.mark_saved();w.close();app.exit(0);return
        w.start_export(str(folder/'corrected.blend'));QTimer.singleShot(100,export_done)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)


def export_done():
    try:
        assert time.monotonic()<deadline,'Export timed out'
        if w.export_process:
            QTimer.singleShot(100,export_done);return
        assert w.status.text()=='Blender project exported.',w.status.text()
        verifier=folder/'verify_export.py'
        verifier.write_text('''import bpy, numpy as np
from mathutils import Matrix
s=bpy.context.scene;s.frame_set(3);cam=s.camera
expected=np.array([[1,0,0,0],[0,np.cos(np.radians(59)),-np.sin(np.radians(59)),-5],[0,np.sin(np.radians(59)),np.cos(np.radians(59)),3],[0,0,0,1]])
np.testing.assert_allclose(np.array(cam.matrix_basis),expected,atol=1e-6)
np.testing.assert_allclose(np.array(cam.matrix_world)[:3,3],[1,-3,3.5],atol=1e-6)
path=bpy.data.objects['Camera trajectory']
np.testing.assert_allclose(path.data.splines[0].points[2].co[:3],[0,-5,3],atol=1e-6)
print('PASS exported corrected camera rotation/location, root transform and trajectory')
''',encoding='utf-8')
        result=subprocess.run([CONFIG['blender'],'--background',str(folder/'corrected.blend'),'--python-exit-code','1','--python',str(verifier)],capture_output=True,text=True,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        print(result.stdout,flush=True)
        assert result.returncode==0,result.stderr
        w.project.mark_saved();w.close();app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)


QTimer.singleShot(400,check)
sys.exit(app.exec())
