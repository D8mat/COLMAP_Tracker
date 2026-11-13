import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Track-data panel, project lifecycle, sampled IDs and full prepared-scene import."""
import os,sys,time
from pathlib import Path
import numpy as np
import desktop
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from pipeline import read_model
from project_io import write_project,read_project

folder=desktop.ROOT/'validation/track_data';folder.mkdir(parents=True,exist_ok=True)
os.environ['ALIEN_TRACKER_STATE_DIR']=str(folder/'recovery')
(folder/'cameras.txt').write_text('7 PINHOLE 320 240 250 250 160 120\n')
(folder/'images.txt').write_text('91 1 0 0 0 0 0 0 7 frame_000007.jpg\n160 120 501\n'
                                '3 1 0 0 0 0 0 0 7 frame_000001.jpg\n160 120 501 20 30 -1\n')
(folder/'points3D.txt').write_text('501 0 0 5 255 128 0 0 91 0 3 0\n')
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show();stage=0;deadline=time.monotonic()+90

def check():
    global stage
    try:
        assert time.monotonic()<deadline,'Track-data import timed out'
        if stage==0:
            assert w.track_data is None and not w.track_data_button.isEnabled()
            data=read_model(folder);w.pending=(folder,None,6.);w.model_loaded(data);w.show_track_data()
            panel=w.track_data_panel;assert panel.model.rowCount()==2
            assert panel.model.data(panel.model.index(1,1))=='1.000'
            assert panel.model.data(panel.model.index(0,2))==3
            panel.table.selectRow(1);panel.go.click();assert w.frame==7
            assert w.viewport.point_ids.tolist()==[501]
            # Display subsampling retains real IDs and never thins diagnostic data.
            many=[((0.,0.,5.),(.5,.5,.5),0.)]*200001;ids=np.arange(200001,dtype=np.int64)*3+101
            w.viewport.set_model(many,w.poses,ids)
            np.testing.assert_array_equal(w.viewport.point_ids,ids[::2]);assert len(w.track_data.point_ids)==1
            w.viewport.set_model(data[2],w.poses,data.tracks.point_ids)
            project=folder/'tracks.tracker.json';write_project(project,w.project.snapshot());loaded,reopened=read_project(project)
            np.testing.assert_array_equal(reopened.tracks.point_track(501),[[91,0],[3,0]])
            assert reopened.tracks.images[3].point_ids.tolist()==[501,-1]
            original=w.track_data;w.viewport.scene_transform['position']=[1,2,3];w.viewport.edited.emit()
            np.testing.assert_array_equal(original.xyz,[[0,0,5]])
            w.project.clear();assert w.track_data is None and panel.model.rowCount()==0 and not w.track_data_button.isEnabled()
            assert len(w.viewport.point_ids)==0
            w.sample();stage=1
        elif stage==1 and w.loader is None:
            assert w.track_data is not None,w.status.text()
            data=w.track_data
            assert len(data.images)==1349 and len(data.point_ids)==343352
            assert data.counts.tolist()==[8816792,5019327,0,0,0] and data.invalid_links==0
            np.testing.assert_array_equal(w.viewport.point_ids,data.point_ids[::2])
            w.graph_toggle.setChecked(False);w.show_track_data();w.track_data_panel.table.selectRow(300);w.track_data_panel.go.click()
            assert w.frame==301 and w.camera_editor.frame==301
            app.processEvents();assert w.track_data_dock.isFloating() and w.track_data_panel.table.height()>150
            assert w.track_data_dock.height()<w.screen().availableGeometry().height()
            w.track_data_dock.grab().save(str(folder/'track_data_panel.png'))
            w.project.mark_saved();w.close();print('PASS stable IDs, frame/time table, navigation, sampled-ID mapping, save/reload, reset and 13,836,119 prepared-scene observations',flush=True)
            app.exit(0);return
        QTimer.singleShot(50,check)
    except Exception:
        import traceback;traceback.print_exc();w.frame_cache.close();app.exit(1)

QTimer.singleShot(100,check);sys.exit(app.exec())
