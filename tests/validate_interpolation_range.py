import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""GUI range interpolation with pinned centre and project-level Undo/Redo."""
import copy
import os
import sys
import desktop
import numpy as np
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QSurfaceFormat,QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from pipeline import read_model
from camera_track import camera_matrix
from test_camera_track import pose_from_matrix,matrix

folder=desktop.ROOT/'validation/interpolation_range';folder.mkdir(parents=True,exist_ok=True)
os.environ['ALIEN_TRACKER_STATE_DIR']=str(folder/'recovery')
(folder/'cameras.txt').write_text('1 PINHOLE 320 240 250 250 160 120\n')
(folder/'points3D.txt').write_text('1 0 0 0 255 255 255 0\n')
lines=[]
for frame in range(1,18):
    p=pose_from_matrix(frame,matrix([frame*.1,frame%3-5,3],[59,0,frame%4]))
    lines.extend([' '.join(map(str,[frame,*p['q'],*p['t'],1,p['name']])), ''])
    image=QImage(320,240,QImage.Format_RGB32);image.fill(0xff223344);image.save(str(folder/p['name']))
(folder/'images.txt').write_text('\n'.join(lines)+'\n')
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show()

def run():
    try:
        w.pending=(folder,folder,30.);w.model_loaded(read_model(folder));app.processEvents()
        e=w.camera_editor;w.select_camera_frame(9)
        e.track.set_matrix(9,matrix([1,-5,3],[59,0,20]));e.notify()
        e.track.set_matrix(5,matrix([8,-5,3],[59,0,-20]));e.notify()
        e.frame_lock.setChecked(True);w.history.reset()
        before=copy.deepcopy(e.track.poses);edits=copy.deepcopy(e.track.edits())
        assert e.interpolation_radius.minimum()==5 and e.interpolation_radius.value()==5
        QTest.mouseClick(e.interpolate_button,Qt.LeftButton)
        after=copy.deepcopy(e.track.edits())
        assert len(w.history.undo_stack)==1 and after!=edits
        targets=set(range(4,9))|set(range(10,15))
        for p,old in zip(e.track.poses,before):
            if p['frame'] in targets:assert p!=old
            else:assert p==old
        np.testing.assert_array_equal(w.viewport.pose,camera_matrix(before[8]))
        w.history.undo();assert e.track.edits()==edits
        w.history.redo();assert e.track.edits()==after
        e.interpolation_radius.setValue(6)
        assert e.interpolate_button.text()=='Interpolate ±6'
        assert 'anchors 2 and 16' in e.interpolate_button.toolTip()
        QTest.mouseClick(e.interpolate_button,Qt.LeftButton)
        assert e.track.by_frame[9]==before[8]
        assert all('matrix' in e.track.by_frame[f] for f in (3,15))
        w.history.undo();assert e.track.edits()==after
        w.select_camera_frame(10);assert not e.interpolate_button.isEnabled()
        e.interpolate();assert e.track.edits()==after
        w.select_camera_frame(9);assert e.interpolate_button.isEnabled()
        app.processEvents();e.grab().save(str(folder/'interpolation_range.png'))
        w.project.mark_saved();w.close()
        print('PASS ±5/±6 range, exact pinned centre, untouched exterior, shared Undo/Redo and frame-lock guard',flush=True)
        app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)

QTimer.singleShot(300,run);sys.exit(app.exec())
