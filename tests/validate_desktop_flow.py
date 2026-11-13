import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show();stage=0;deadline=time.monotonic()+150;phase_time=0
w.sample()
def advance():
    global stage,phase_time
    try:
        assert time.monotonic()<deadline,('timeout',stage,w.status.text())
        if stage==0 and w.poses and w.loader is None:
            w.preview_source();w.player.play();stage=1
        elif stage==1 and w.player.position()>500:
            assert w.player.duration()>1000
            w.pause();w.preview_solved();w.slider.setValue(100);w.toggle_play();phase_time=time.monotonic();stage=2
            print('PASS source video decoding/playback',flush=True)
        elif stage==2 and time.monotonic()-phase_time>1:
            assert w.frame>110,w.frame
            w.pause();w.fps.setValue(3);w.seconds.setValue(8);w.size.setValue(1600);w.overlap.setValue(8)
            w.output.setText(str(desktop.ROOT/'validation'));w.start_job();assert w.job
            stage=3;print('PASS solved timeline playback; started real COLMAP job',flush=True)
        elif stage==3 and w.job is None and w.loader is None:
            assert len(w.poses)==24,(len(w.poses),w.status.text())
            assert (w.model_folder/'cameras.txt').is_file()
            w.start_export(str(desktop.ROOT/'validation/desktop_export.blend'));assert w.export_process
            stage=4;print('PASS GUI tracking completion: 24 cameras',flush=True)
        elif stage==4 and w.export_process is None:
            assert w.status.text()=='Blender project exported.',w.status.text()
            assert (desktop.ROOT/'validation/desktop_export.blend').stat().st_size>10000
            print('PASS background .blend export',flush=True)
            w.project.mark_saved();w.close();app.exit(0);return
        QTimer.singleShot(150,advance)
    except Exception:
        import traceback;traceback.print_exc();w.cancel_job();app.exit(1)
QTimer.singleShot(500,advance)
sys.exit(app.exec())
