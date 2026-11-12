import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop,numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
f=QSurfaceFormat();f.setVersion(3,3);f.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(f)
app=QApplication([]);w=desktop.Window();w.show();stage=0;deadline=time.monotonic()+45
w.sample()
def check():
    global stage
    try:
        assert time.monotonic()<deadline,'Video overlay timeout'
        if stage==0 and w.poses and w.loader is None:
            w.mesh_toggle.setChecked(False);w.cloud_toggle.setChecked(False)
            item=w.viewport.add_primitive('Cone');m=w.viewport.pose
            item['position']=(m[:3,:3]@np.array([0,0,-5])+m[:3,3]).tolist();item['scale']=.4
            w.preview_source();w.player.play();stage=1
        elif stage==1 and w.player.position()>300 and w.video_widget.camera:
            w.pause();before=w.video_widget.grab().toImage();w.overlay_toggle.setChecked(False);after=w.video_widget.grab().toImage()
            assert before!=after,'Original video overlay missing'
            assert not w.video_widget.pixmap().isNull()
            print('PASS original video sink decoding and calibrated cone overlay',flush=True);w.project.mark_saved();w.close();app.exit(0);return
        QTimer.singleShot(100,check)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)
QTimer.singleShot(500,check);sys.exit(app.exec())
