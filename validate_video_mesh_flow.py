"""One-button raw video -> COLMAP tracking -> mesh -> saved project integration."""
import sys,time
import desktop
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show();w.project.clear()
video=desktop.SAMPLE/'02 VIDEOS/IMG_2284_nonHDR.mov'
w.video.setText(str(video));w.fps.setValue(3);w.seconds.setValue(8);w.size.setValue(1600);w.overlap.setValue(8)
w.output.setText(str(desktop.ROOT/'validation'));w.graph_toggle.setChecked(False)
deadline=time.monotonic()+240;started=False

def tick():
    global started
    try:
        assert time.monotonic()<deadline,('timeout',w.status.text(),w.mesh_panel.status.text())
        if not started:
            assert video.is_file();QTest.mouseClick(w.generate_mesh_button,Qt.LeftButton)
            assert w.job is not None and w.mesh_after_tracking;started=True
            print('Started one-button video -> tracking -> mesh',flush=True)
        elif w.job is None and w.loader is None and not w.mesh_panel.running:
            assert len(w.poses)==24,(len(w.poses),w.status.text())
            assert w.viewport.mesh is not None,w.mesh_panel.status.text()
            assert len(w.viewport.mesh['faces'])>0
            assert not w.mesh_after_tracking
            w.select_camera_frame(12);w.show_shading();w.project.path=desktop.ROOT/'validation/video_mesh.tracker.json'
            assert w.project.save();w.viewport.grabFramebuffer();w.grab().save(str(desktop.ROOT/'validation/video_mesh_flow.png'))
            print(f'PASS raw video -> 24 cameras -> {len(w.viewport.mesh["faces"])} triangles -> saved project',flush=True)
            assert w.project.new();w.video.setText(str(video));w.seconds.setValue(8)
            w.generate_mesh();assert w.job and w.mesh_after_tracking
            w.cancel_job();assert not w.mesh_after_tracking and w.job is None and not w.mesh_panel.running
            w.project.mark_saved();w.close();print('PASS Stop cancels tracking and queued mesh generation',flush=True);app.exit(0);return
        QTimer.singleShot(200,tick)
    except Exception:
        import traceback;traceback.print_exc();w.cancel_job();app.exit(1)
QTimer.singleShot(400,tick);sys.exit(app.exec())
